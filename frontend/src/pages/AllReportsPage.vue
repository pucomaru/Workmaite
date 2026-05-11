<script setup>
import { ref, onMounted, computed } from 'vue'
import { useRouter } from 'vue-router'
import api from '../api'

const router = useRouter()
const reports = ref([])
const loading = ref(true)
const search = ref('')
const selectedMeeting = ref('')
const selectedStatus = ref('')

onMounted(async () => {
  try {
    const { data } = await api.get('/api/all-reports')
    reports.value = data
  } finally {
    loading.value = false
  }
})

const meetingOptions = computed(() => {
  const seen = new Set()
  return reports.value
    .map(r => ({ id: r.meeting_id, title: r.meeting_title }))
    .filter(r => { if (seen.has(r.id)) return false; seen.add(r.id); return true })
})

const filtered = computed(() =>
  reports.value.filter(r => {
    const matchSearch = !search.value ||
      r.meeting_title.toLowerCase().includes(search.value.toLowerCase()) ||
      (r.presenter_name || '').toLowerCase().includes(search.value.toLowerCase()) ||
      (r.file_name || '').toLowerCase().includes(search.value.toLowerCase())
    const matchMeeting = !selectedMeeting.value || r.meeting_id == selectedMeeting.value
    const matchStatus = !selectedStatus.value || r.status === selectedStatus.value
    return matchSearch && matchMeeting && matchStatus
  })
)

const statusMap = { draft: '검토전', submitted: '검토중', approved: '승인', rejected: '반려' }
const statusCls = { draft: 'badge-muted', submitted: 'badge-primary', approved: 'badge-success', rejected: 'badge-danger' }

function formatDate(d) {
  if (!d) return '-'
  return new Date(d).toLocaleDateString('ko-KR', { year: 'numeric', month: 'short', day: 'numeric' })
}

async function deleteReport(r) {
  if (!confirm(`"${r.file_name || '보고서'}" 보고서를 삭제하시겠습니까?`)) return
  try {
    await api.delete(`/api/reports/${r.id}`)
  } catch (e) {
    if (e?.response?.status !== 404) {
      alert(e?.response?.data?.detail || '삭제 중 오류가 발생했습니다.')
      return
    }
  }
  reports.value = reports.value.filter(x => x.id !== r.id)
}

</script>

<template>
  <div class="page-wrap">
    <div class="page-header">
      <div>
        <h1 class="page-title">📊 전체 보고서</h1>
        <p class="page-desc">참여 중인 모든 회의체의 보고서를 확인합니다.</p>
      </div>
    </div>

    <div class="filter-bar">
      <input v-model="search" class="form-input" placeholder="회의체명, 발제자, 파일명 검색..." style="flex:1;max-width:280px" />
      <select v-model="selectedMeeting" class="form-input" style="max-width:180px">
        <option value="">전체 회의체</option>
        <option v-for="m in meetingOptions" :key="m.id" :value="m.id">{{ m.title }}</option>
      </select>
      <select v-model="selectedStatus" class="form-input" style="max-width:130px">
        <option value="">전체 상태</option>
        <option value="draft">검토전</option>
        <option value="submitted">검토중</option>
        <option value="approved">승인</option>
        <option value="rejected">반려</option>
      </select>
    </div>

    <div v-if="loading" class="empty-state">불러오는 중...</div>
    <div v-else-if="!filtered.length" class="empty-state">
      <p>{{ search || selectedMeeting || selectedStatus ? '검색 결과가 없습니다.' : '보고서가 없습니다.' }}</p>
    </div>

    <div v-else class="table-wrap">
      <table class="table">
        <thead>
          <tr>
            <th>회의체</th>
            <th>발제자</th>
            <th>파일명</th>
            <th>상태</th>
            <th>제출일</th>
            <th>승인일</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="r in filtered" :key="r.id" class="fade-in">
            <td>
              <span class="badge badge-primary" style="font-size:11px">{{ r.meeting_title }}</span>
            </td>
            <td style="font-weight:500">{{ r.presenter_name }}</td>
            <td style="font-size:12px;color:var(--text-muted);max-width:180px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">
              {{ r.file_name || '-' }}
            </td>
            <td>
              <span class="badge" :class="statusCls[r.status]">{{ statusMap[r.status] || r.status }}</span>
            </td>
            <td style="font-size:12px;white-space:nowrap">{{ formatDate(r.submitted_at) }}</td>
            <td style="font-size:12px;white-space:nowrap">{{ formatDate(r.approved_at) }}</td>
            <td style="text-align:right;white-space:nowrap">
              <button class="btn btn-ghost btn-sm" @click="router.push(`/meetings/${r.meeting_id}/prepare`)">
                이동 →
              </button>
              <button class="btn btn-ghost btn-sm" style="color:var(--danger)" @click="deleteReport(r)">
                삭제
              </button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<style scoped>
.page-wrap { padding: 28px 32px; max-width: 1000px; margin: 0 auto; }
.page-header { display: flex; align-items: flex-start; justify-content: space-between; margin-bottom: 20px; }
.page-title { font-size: 22px; font-weight: 700; margin: 0 0 4px; }
.page-desc { font-size: 13px; color: var(--text-muted); margin: 0; }
.filter-bar { display: flex; gap: 10px; margin-bottom: 18px; flex-wrap: wrap; }
.table-wrap { background: #fff; border: 1px solid var(--border); border-radius: var(--radius); overflow: hidden; }
</style>
