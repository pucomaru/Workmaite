<script setup>
import { ref, onMounted, computed } from 'vue'
import { useRouter } from 'vue-router'
import api from '../api'

const router = useRouter()
const minutes = ref([])
const loading = ref(true)
const search = ref('')
const selectedMeeting = ref('')
const expandedId = ref(null)

onMounted(async () => {
  try {
    const { data } = await api.get('/api/all-minutes')
    minutes.value = data
  } finally {
    loading.value = false
  }
})

const meetingOptions = computed(() => {
  const seen = new Set()
  return minutes.value
    .map(m => ({ id: m.meeting_id, title: m.meeting_title }))
    .filter(m => { if (seen.has(m.id)) return false; seen.add(m.id); return true })
})

const filtered = computed(() =>
  minutes.value.filter(m => {
    const matchSearch = !search.value ||
      m.meeting_title.toLowerCase().includes(search.value.toLowerCase()) ||
      (m.session_title || '').toLowerCase().includes(search.value.toLowerCase()) ||
      (m.content_summary || '').toLowerCase().includes(search.value.toLowerCase())
    const matchMeeting = !selectedMeeting.value || m.meeting_id == selectedMeeting.value
    return matchSearch && matchMeeting
  })
)

function formatDate(d) {
  if (!d) return '-'
  return new Date(d).toLocaleDateString('ko-KR', { year: 'numeric', month: 'short', day: 'numeric' })
}

function toggleExpand(id) {
  expandedId.value = expandedId.value === id ? null : id
}
</script>

<template>
  <div class="page-wrap">
    <div class="page-header">
      <div>
        <h1 class="page-title">📋 전체 회의록</h1>
        <p class="page-desc">참여 중인 모든 회의체의 회의록을 확인합니다.</p>
      </div>
    </div>

    <div class="filter-bar">
      <input v-model="search" class="form-input" placeholder="회의체명, 회의 제목, 내용 검색..." style="flex:1;max-width:320px" />
      <select v-model="selectedMeeting" class="form-input" style="max-width:200px">
        <option value="">전체 회의체</option>
        <option v-for="m in meetingOptions" :key="m.id" :value="m.id">{{ m.title }}</option>
      </select>
    </div>

    <div v-if="loading" class="empty-state">불러오는 중...</div>
    <div v-else-if="!filtered.length" class="empty-state">
      <p>{{ search || selectedMeeting ? '검색 결과가 없습니다.' : '회의록이 없습니다.' }}</p>
    </div>

    <div v-else class="minutes-list">
      <div
        v-for="m in filtered"
        :key="m.minutes_id"
        class="minutes-card fade-in"
      >
        <div class="minutes-card-header" @click="toggleExpand(m.minutes_id)">
          <div class="minutes-meta">
            <span class="badge badge-primary" style="font-size:11px">{{ m.meeting_title }}</span>
            <span class="minutes-session">{{ m.session_number }}차 회의</span>
            <span v-if="m.session_title" class="minutes-session-title">— {{ m.session_title }}</span>
          </div>
          <div style="display:flex;align-items:center;gap:12px">
            <span class="minutes-date">{{ formatDate(m.ended_at) }}</span>
            <svg
              width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"
              :style="{ transform: expandedId === m.minutes_id ? 'rotate(180deg)' : '', transition: 'transform .2s' }"
            ><path d="M19 9l-7 7-7-7"/></svg>
          </div>
        </div>

        <div v-if="expandedId === m.minutes_id" class="minutes-body fade-in">
          <div v-if="m.content_summary" class="minutes-summary">
            <div class="summary-label">📝 AI 요약</div>
            <div class="summary-content">{{ m.content_summary }}</div>
          </div>
          <div v-else-if="m.content_raw" class="minutes-raw">
            <div class="summary-label">🎙 회의록 내용</div>
            <pre class="raw-content">{{ m.content_raw }}</pre>
          </div>
          <div v-else class="empty-state" style="padding:12px">회의록 내용이 없습니다.</div>
          <div style="margin-top:12px;text-align:right">
            <button class="btn btn-outline btn-sm" @click="router.push(`/meetings/${m.meeting_id}/sessions`)">
              해당 회의체로 이동 →
            </button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.page-wrap { padding: 28px 32px; max-width: 900px; margin: 0 auto; }
.page-header { display: flex; align-items: flex-start; justify-content: space-between; margin-bottom: 20px; }
.page-title { font-size: 22px; font-weight: 700; margin: 0 0 4px; }
.page-desc { font-size: 13px; color: var(--text-muted); margin: 0; }
.filter-bar { display: flex; gap: 10px; margin-bottom: 18px; flex-wrap: wrap; }
.minutes-list { display: flex; flex-direction: column; gap: 10px; }
.minutes-card { background: #fff; border: 1px solid var(--border); border-radius: var(--radius); overflow: hidden; }
.minutes-card-header { display: flex; align-items: center; justify-content: space-between; padding: 14px 16px; cursor: pointer; transition: background .15s; }
.minutes-card-header:hover { background: #f8fafc; }
.minutes-meta { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.minutes-session { font-weight: 600; font-size: 13px; }
.minutes-session-title { font-size: 13px; color: var(--text-muted); }
.minutes-date { font-size: 12px; color: var(--text-muted); white-space: nowrap; }
.minutes-body { padding: 0 16px 16px; border-top: 1px solid var(--border); background: #fafbfc; }
.summary-label { font-size: 11px; font-weight: 600; color: var(--text-muted); text-transform: uppercase; letter-spacing: .05em; margin: 14px 0 8px; }
.summary-content { font-size: 13px; line-height: 1.7; color: var(--text); white-space: pre-wrap; }
.raw-content { font-size: 12px; line-height: 1.6; color: var(--text-muted); background: #f1f5f9; border-radius: 6px; padding: 12px; white-space: pre-wrap; word-break: break-all; max-height: 300px; overflow-y: auto; }
</style>
