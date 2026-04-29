<script setup>
import { ref, computed, watch, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useMeetingsStore } from '../stores/meetings'
import { useAuthStore } from '../stores/auth'
import api from '../api'

const route  = useRoute()
const router = useRouter()
const meetingsStore = useMeetingsStore()
const authStore     = useAuthStore()

const meetingId = computed(() => route.params.meetingId)

// ── 준비 상태 (role + sessions 모두 로드 완료 전까지 opacity 0) ──
const ready = ref(false)

// ── role ────────────────────────────────────────────────────────
const role     = computed(() => meetingsStore.myRole)
const isEnded  = computed(() => meetingsStore.currentMeeting?.status === 'ended')

// ── 세션(루프) 목록 ──────────────────────────────────────────────
const sessions = ref([])

// store를 통해 SessionsPage와 공유
const currentLoopIdx = computed({
  get: () => meetingsStore.currentLoopIdx,
  set: (v) => { meetingsStore.currentLoopIdx = v },
})

const canGoPrev = computed(() => currentLoopIdx.value > 0)
const canGoNext = computed(() => currentLoopIdx.value < sessions.value.length - 1)

const isLastSessionEnded = computed(() =>
  sessions.value.length > 0 &&
  sessions.value[sessions.value.length - 1]?.status === 'ended'
)

const showLoopControls = computed(() =>
  role.value === 'admin' &&
  (sessions.value.length === 0 || isLastSessionEnded.value) &&
  !isEnded.value
)

// 세션 로드 후 마지막 루프 선택
watch(sessions, (s) => {
  if (s.length > 0) meetingsStore.currentLoopIdx = s.length - 1
})

function prevLoop() { if (canGoPrev.value) currentLoopIdx.value-- }
function nextLoop() { if (canGoNext.value) currentLoopIdx.value++ }

// ── 탭 ──────────────────────────────────────────────────────────
const adminTabs = [
  { label: 'Agenda',   path: 'agenda',   icon: '📋' },
  { label: '회의준비',  path: 'prepare',  icon: '📝' },
  { label: '회의',     path: 'sessions', icon: '🎙' },
]
const presenterTabs = [
  { label: 'To-do',   path: 'todo',     icon: '✅' },
  { label: '회의준비', path: 'prepare',  icon: '📝' },
  { label: '회의',    path: 'sessions', icon: '🎙' },
]
const tabs = computed(() => role.value === 'admin' ? adminTabs : presenterTabs)

function isActive(path) { return route.path.includes(`/${path}`) }
function go(path)       { router.push(`/meetings/${meetingId.value}/${path}`) }

// ── 데이터 로드: role + sessions 동시 fetch ──────────────────────
onMounted(async () => {
  try {
    const [, sessionsData] = await Promise.all([
      meetingsStore.fetchRole(Number(meetingId.value)),
      api.get(`/api/meetings/${meetingId.value}/sessions`)
        .then(r => r.data)
        .catch(() => []),
    ])
    sessions.value = sessionsData
  } finally {
    // 성공·실패 무관하게 준비 완료 → 렌더링 표시
    ready.value = true
  }
})

// ── 새 루프 시작 ─────────────────────────────────────────────────
const creatingLoop = ref(false)
async function startNewLoop() {
  if (creatingLoop.value) return
  creatingLoop.value = true
  try {
    const nextNum = sessions.value.length + 1
    await api.post(`/api/meetings/${meetingId.value}/sessions`, {
      title: `${nextNum}차 회의`,
      scheduled_at: null,
    })
    const { data } = await api.get(`/api/meetings/${meetingId.value}/sessions`)
    sessions.value = data
    router.push(`/meetings/${meetingId.value}/agenda`)
  } finally {
    creatingLoop.value = false
  }
}

// ── 회의체 종료 ──────────────────────────────────────────────────
async function terminateMeetingGroup() {
  if (!confirm('회의체를 완전히 종료하시겠습니까?\n이후 회의를 진행할 수 없습니다.')) return
  await meetingsStore.terminateMeeting(Number(meetingId.value))
}

// ── 회의체 탈퇴 ──────────────────────────────────────────────────
const leaving = ref(false)
async function leaveMeeting() {
  if (!confirm('이 회의체에서 탈퇴하시겠습니까?')) return
  leaving.value = true
  try {
    await meetingsStore.leaveMeeting(Number(meetingId.value), authStore.user?.id)
    router.push('/')
  } catch {
    alert('탈퇴 처리 중 오류가 발생했습니다.')
  } finally {
    leaving.value = false
  }
}
</script>

<template>
  <nav class="meeting-nav">
    <template v-if="ready">
      <!-- ‹ N차 › 루프 탐색 -->
      <div v-if="sessions.length" class="loop-nav">
        <button class="loop-arrow" :disabled="!canGoPrev" @click="prevLoop">‹</button>
        <span class="loop-badge">{{ currentLoopIdx + 1 }}차</span>
        <button class="loop-arrow" :disabled="!canGoNext" @click="nextLoop">›</button>
      </div>

      <!-- 스크롤 탭 -->
      <div class="tabs-scroll">
        <div
          v-for="tab in tabs"
          :key="tab.path"
          class="tab-item"
          :class="{ active: isActive(tab.path) }"
          @click="go(tab.path)"
        >
          <span class="tab-icon">{{ tab.icon }}</span>
          <span class="tab-label">{{ tab.label }}</span>
        </div>
      </div>

      <!-- 오른쪽 고정 액션 -->
      <div class="nav-actions">
        <span v-if="isEnded" class="ended-badge">종료됨</span>

        <template v-else-if="showLoopControls">
          <button class="btn btn-primary btn-sm" :disabled="creatingLoop" @click="startNewLoop">
            {{ creatingLoop ? '생성 중...' : '▶ 새 루프 시작' }}
          </button>
          <button class="btn btn-danger btn-sm" @click="terminateMeetingGroup">
            ⏹ 회의체 종료
          </button>
        </template>

        <button
          v-if="role && role !== 'admin'"
          class="btn btn-ghost btn-sm leave-btn"
          :disabled="leaving"
          @click="leaveMeeting"
        >
          {{ leaving ? '처리 중...' : '탈퇴' }}
        </button>
      </div>
    </template>
  </nav>
</template>

<style scoped>
.meeting-nav {
  background: #fff;
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  padding: 0 6px;
  margin-bottom: 16px;
  box-shadow: var(--shadow);
  display: flex;
  align-items: center;
  gap: 4px;
  min-height: 44px;
  flex-shrink: 0;
  overflow: hidden;
}

/* ── 루프 탐색 ── */
.loop-nav {
  display: flex;
  align-items: center;
  gap: 2px;
  flex-shrink: 0;
}
.loop-arrow {
  flex-shrink: 0;
  width: 26px;
  height: 26px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 6px;
  border: 1px solid var(--border);
  background: none;
  font-size: 17px;
  color: var(--text-muted);
  cursor: pointer;
  line-height: 1;
  transition: all .15s;
}
.loop-arrow:hover:not(:disabled) {
  background: var(--primary);
  color: #fff;
  border-color: var(--primary);
}
.loop-arrow:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}
.loop-badge {
  flex-shrink: 0;
  font-size: 12px;
  font-weight: 700;
  color: var(--primary);
  background: #eff6ff;
  border: 1px solid #bfdbfe;
  border-radius: 99px;
  padding: 2px 9px;
  white-space: nowrap;
}

/* ── 탭 스크롤 ── */
.tabs-scroll {
  display: flex;
  align-items: center;
  gap: 2px;
  overflow-x: auto;
  flex: 1;
  scrollbar-width: none;
  min-width: 0;
}
.tabs-scroll::-webkit-scrollbar { display: none; }
.tab-item {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 14px;
  border-radius: 20px;
  cursor: pointer;
  font-size: 13px;
  font-weight: 500;
  color: var(--text-muted);
  transition: all .15s;
  white-space: nowrap;
  flex-shrink: 0;
}
.tab-item:hover { background: #f1f5f9; color: var(--text); }
.tab-item.active { background: var(--primary); color: #fff; }
.tab-icon { font-size: 14px; }

/* ── 오른쪽 액션 ── */
.nav-actions {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-shrink: 0;
}
.ended-badge {
  font-size: 11px;
  font-weight: 600;
  color: var(--text-muted);
  background: #f1f5f9;
  border: 1px solid var(--border);
  padding: 2px 8px;
  border-radius: 99px;
  white-space: nowrap;
}
.leave-btn {
  color: var(--danger, #ef4444);
  border: 1px solid var(--danger, #ef4444);
  border-radius: 99px;
  font-size: 12px;
  padding: 3px 10px;
}
.leave-btn:hover { background: #fef2f2; }
.btn-danger {
  background: var(--danger, #ef4444);
  color: #fff;
  border-radius: 99px;
}
.btn-danger:hover { opacity: .88; }
</style>
