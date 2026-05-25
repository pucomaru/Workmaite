<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import api from '../api'

const router = useRouter()
const meetings = ref([])
const loading = ref(true)
const search = ref('')
const expandedId = ref(null)
const sessionsByMeeting = ref({})  // meetingId → sessions[]

onMounted(async () => {
  try {
    const { data } = await api.get('/api/meetings')
    meetings.value = data.filter(m => m.status === 'ended')
  } finally {
    loading.value = false
  }
})

const filtered = computed(() =>
  meetings.value.filter(m =>
    !search.value || m.title.toLowerCase().includes(search.value.toLowerCase())
  )
)

async function toggle(m) {
  if (expandedId.value === m.id) {
    expandedId.value = null
    return
  }
  expandedId.value = m.id
  if (!sessionsByMeeting.value[m.id]) {
    try {
      const { data } = await api.get(`/api/meetings/${m.id}/sessions`)
      sessionsByMeeting.value[m.id] = data
    } catch {
      sessionsByMeeting.value[m.id] = []
    }
  }
}

function goMeeting(meetingId, path = 'sessions') {
  router.push(`/meetings/${meetingId}/${path}`)
}

function formatDate(d) {
  if (!d) return '-'
  return new Date(d).toLocaleDateString('ko-KR', { year: 'numeric', month: 'short', day: 'numeric' })
}

function formatDateTime(d) {
  if (!d) return '일정 미정'
  return new Date(d).toLocaleString('ko-KR', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
}
</script>

<template>
  <div class="page-wrap">
    <div class="page-header">
      <div>
        <h1 class="page-title">🗂 지난 회의</h1>
        <p class="page-desc">종료된 회의체와 회의 기록을 확인합니다.</p>
      </div>
    </div>

    <div class="filter-bar">
      <input v-model="search" class="form-input" placeholder="회의체명 검색..." style="flex:1;max-width:320px" />
    </div>

    <div v-if="loading" class="empty-state">불러오는 중...</div>
    <div v-else-if="!filtered.length" class="empty-state">
      <p>{{ search ? '검색 결과가 없습니다.' : '종료된 회의체가 없습니다.' }}</p>
    </div>

    <div v-else class="meeting-list">
      <div v-for="m in filtered" :key="m.id" class="meeting-card fade-in">
        <!-- 헤더 -->
        <div class="meeting-card-header" @click="toggle(m)">
          <div class="meeting-meta">
            <span class="ended-badge">종료됨</span>
            <span class="meeting-title">{{ m.title }}</span>
          </div>
          <div style="display:flex;align-items:center;gap:10px">
            <span class="meeting-date">{{ formatDate(m.created_at) }}</span>
            <svg
              width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"
              :style="{ transform: expandedId === m.id ? 'rotate(180deg)' : '', transition: 'transform .2s' }"
            ><path d="M19 9l-7 7-7-7"/></svg>
          </div>
        </div>

        <!-- 확장: 회의 목록 + 이동 버튼 -->
        <div v-if="expandedId === m.id" class="meeting-body fade-in">
          <!-- 회의체 탭 이동 버튼 -->
          <div class="tab-nav-row">
            <button class="tab-nav-btn" @click="goMeeting(m.id, 'sessions')">🎤 회의 목록</button>
            <button class="tab-nav-btn" @click="goMeeting(m.id, 'agenda')">📋 Agenda</button>
            <button class="tab-nav-btn" @click="goMeeting(m.id, 'prepare')">📝 회의준비</button>
          </div>

          <!-- 회의 세션 목록 (최신순) -->
          <div class="sessions-section">
            <div class="section-label">회의 목록</div>
            <div v-if="!sessionsByMeeting[m.id]" class="empty-state" style="padding:8px">불러오는 중...</div>
            <div v-else-if="!sessionsByMeeting[m.id].length" class="empty-state" style="padding:8px">등록된 회의가 없습니다.</div>
            <div
              v-for="s in sessionsByMeeting[m.id]"
              :key="s.id"
              class="session-row"
              @click="goMeeting(m.id, 'sessions')"
            >
              <div>
                <div class="session-title">{{ s.title }}</div>
                <div class="session-date">{{ formatDateTime(s.scheduled_at) }}</div>
              </div>
              <span class="badge" :class="s.status === 'ended' ? 'badge-muted' : 'badge-warning'">
                {{ { scheduled: '예정', ongoing: '진행중', ended: '종료' }[s.status] || s.status }}
              </span>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.filter-bar { display: flex; gap: 10px; margin-bottom: 18px; }
.meeting-list { display: flex; flex-direction: column; gap: 10px; }
.meeting-card { background: #fff; border: 1px solid var(--border); border-radius: var(--radius); overflow: hidden; }
.meeting-card-header { display: flex; align-items: center; justify-content: space-between; padding: 14px 16px; cursor: pointer; transition: background .15s; }
.meeting-card-header:hover { background: #f8fafc; }
.meeting-meta { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.meeting-title { font-weight: 600; font-size: 14px; }
.meeting-date { font-size: 12px; color: var(--text-muted); white-space: nowrap; }
.ended-badge { font-size: 11px; font-weight: 600; color: #64748b; background: #f1f5f9; border: 1px solid #e2e8f0; padding: 2px 8px; border-radius: 99px; white-space: nowrap; }
.meeting-body { padding: 0 16px 16px; border-top: 1px solid var(--border); background: #fafbfc; }

/* 탭 이동 버튼 */
.tab-nav-row { display: flex; gap: 8px; padding: 14px 0 10px; flex-wrap: wrap; }
.tab-nav-btn { display: flex; align-items: center; gap: 5px; padding: 6px 14px; border-radius: 20px; border: 1px solid var(--border); background: #fff; color: var(--text-muted); font-size: 13px; font-weight: 500; cursor: pointer; transition: all .15s; }
.tab-nav-btn:hover { background: var(--primary); color: #fff; border-color: var(--primary); }

/* 세션 목록 */
.sessions-section { margin-top: 4px; }
.section-label { font-size: 11px; font-weight: 600; color: var(--text-muted); text-transform: uppercase; letter-spacing: .05em; margin-bottom: 8px; }
.session-row { display: flex; align-items: center; justify-content: space-between; padding: 9px 12px; border-radius: 8px; cursor: pointer; transition: background .15s; }
.session-row:hover { background: #f1f5f9; }
.session-title { font-size: 13px; font-weight: 500; }
.session-date { font-size: 12px; color: var(--text-muted); margin-top: 2px; }
</style>
