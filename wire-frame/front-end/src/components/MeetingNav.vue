<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useMeetingsStore } from '../stores/meetings'
import { useAuthStore } from '../stores/auth'

const route  = useRoute()
const router = useRouter()
const meetingsStore = useMeetingsStore()
const authStore     = useAuthStore()

const meetingId = computed(() => route.params.meetingId)
const ready = ref(false)
const role    = computed(() => meetingsStore.myRole)
const isEnded = computed(() => meetingsStore.currentMeeting?.status === 'ended')

const adminTabs = [
  { label: '아젠다',  path: 'agenda',   icon: '📋' },
  { label: '회의준비', path: 'prepare',  icon: '📝' },
  { label: '회의',    path: 'sessions', icon: '🎤' },
]
const presenterTabs = [
  { label: 'To-do',  path: 'todo',     icon: '✅' },
  { label: '회의준비', path: 'prepare',  icon: '📝' },
  { label: '회의',   path: 'sessions', icon: '🎤' },
]
const tabs = computed(() => role.value === 'admin' ? adminTabs : presenterTabs)

function isActive(path) { return route.path.includes(`/${path}`) }

const spinDir = ref('fwd')

const activeIdx = computed(() => {
  const idx = tabs.value.findIndex(tab => isActive(tab.path))
  return idx === -1 ? 0 : idx
})

function go(path) {
  const t = tabs.value
  const n = t.length
  const curIdx = activeIdx.value
  const nextIdx = t.findIndex(tab => tab.path === path)
  if (nextIdx === -1 || nextIdx === curIdx) return
  spinDir.value = (nextIdx - curIdx + n) % n === 1 ? 'fwd' : 'bwd'
  router.push(`/meetings/${meetingId.value}/${path}`)
}

const CARD_NEWS_TAB = { label: '카드뉴스', path: 'card-news', icon: '🗞' }

const visibleTabs = computed(() => {
  // 카드뉴스 페이지 활성 시: 회의 - 카드뉴스 - 아젠다(or To-do) 고정 표시
  if (isActive('card-news')) {
    const t = tabs.value
    const firstTab = t[0] // 아젠다 or To-do
    const sessionsTab = t.find(tab => tab.path === 'sessions') || t[t.length - 1]
    return [
      { ...sessionsTab,  pos: 'prev' },
      { ...CARD_NEWS_TAB, pos: 'active' },
      { ...firstTab,     pos: 'next' },
    ]
  }
  const t = tabs.value
  const n = t.length
  const cur = activeIdx.value
  return [
    { ...t[(cur - 1 + n) % n], pos: 'prev' },
    { ...t[cur],                pos: 'active' },
    { ...t[(cur + 1) % n],      pos: 'next' },
  ]
})

onMounted(async () => {
  try {
    await meetingsStore.fetchRole(Number(meetingId.value))
  } finally {
    ready.value = true
  }
})

async function terminateMeetingGroup() {
  if (!confirm('회의체를 완전히 종료하시겠습니까?\n이후 회의를 진행할 수 없습니다.')) return
  await meetingsStore.terminateMeeting(Number(meetingId.value))
}

const deleting = ref(false)
async function deleteMeetingGroup() {
  if (!confirm('회의체를 영구 삭제하시겠습니까?\n모든 회의록, 발제자료, 아젠다 데이터가 삭제되며 복구할 수 없습니다.')) return
  deleting.value = true
  try {
    await meetingsStore.deleteMeeting(Number(meetingId.value))
    router.push('/')
  } catch {
    alert('삭제 중 오류가 발생했습니다.')
  } finally {
    deleting.value = false
  }
}

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
      <!-- perspective wrapper: 3D 드럼 효과 -->
      <div class="drum-scene">
        <Transition :name="'drum-' + spinDir">
          <div class="drum-track" :key="activeIdx">
            <div
              v-for="tab in visibleTabs"
              :key="tab.pos"
              class="tab-item"
              :class="tab.pos"
              @click="go(tab.path)"
            >
              <span class="tab-icon">{{ tab.icon }}</span>
              <span class="tab-label">{{ tab.label }}</span>
            </div>
          </div>
        </Transition>
      </div>

      <div class="nav-actions">
        <span v-if="isEnded" class="ended-badge">종료됨</span>
        <button
          v-if="role === 'admin' && !isEnded"
          class="btn btn-ghost btn-sm"
          @click="terminateMeetingGroup"
          title="회의체 종료"
        >⏹ 종료</button>
        <button
          v-if="role === 'admin'"
          class="btn btn-ghost btn-sm delete-btn"
          :disabled="deleting"
          @click="deleteMeetingGroup"
          title="회의체 영구 삭제"
        >{{ deleting ? '삭제 중...' : '🗑' }}</button>
        <button
          v-if="role && role !== 'admin'"
          class="btn btn-ghost btn-sm leave-btn"
          :disabled="leaving"
          @click="leaveMeeting"
        >{{ leaving ? '처리 중...' : '탈퇴' }}</button>
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
  min-height: 52px;
  flex-shrink: 0;
}

/* ── 3D 드럼 씬 ── */
.drum-scene {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  position: relative;
  height: 44px;
  /* 원통 회전 원근감 */
  perspective: 600px;
  perspective-origin: 50% 50%;
}

/* 탭 3개가 나란히 놓이는 트랙 */
.drum-track {
  display: flex;
  align-items: center;
  gap: 4px;
  width: 100%;
  height: 100%;
  position: absolute;
  /* 3D 공간에서 자식도 함께 */
  transform-style: preserve-3d;
  /* 회전 기준점: 중심 */
  transform-origin: 50% 50%;
  backface-visibility: hidden;
}

.tab-item {
  display: flex;
  align-items: center;
  gap: 5px;
  padding: 6px 14px;
  border-radius: 20px;
  cursor: pointer;
  font-size: 13px;
  font-weight: 500;
  white-space: nowrap;
  flex: 1;
  justify-content: center;
  user-select: none;
  transition: background 0.15s, color 0.15s;
}

.tab-item.active {
  background: var(--primary);
  color: #fff;
  font-weight: 700;
  cursor: default;
  flex: 1.4;
}

.tab-item.prev,
.tab-item.next {
  color: var(--text-muted);
  opacity: 0.5;
}
.tab-item.prev:hover,
.tab-item.next:hover {
  background: #f1f5f9;
  color: var(--text);
  opacity: 1;
}

.tab-icon { font-size: 14px; }

/* ══════════════════════════════════════════════
   슬롯머신 드럼 애니메이션
   트랙 전체가 X축(가로 회전축) 기준으로 회전
   fwd(앞으로): 아래서 올라오는 릴
   bwd(뒤로):   위에서 내려오는 릴
   ══════════════════════════════════════════════ */
.drum-fwd-enter-active,
.drum-fwd-leave-active,
.drum-bwd-enter-active,
.drum-bwd-leave-active {
  transition:
    transform 0.42s cubic-bezier(0.25, 0.8, 0.25, 1),
    opacity   0.42s ease;
  position: absolute;
  width: 100%;
}

/* 앞으로 — 아래에서 올라오는 릴 */
.drum-fwd-enter-from {
  transform: rotateX(-75deg) translateY(10px);
  opacity: 0;
}
.drum-fwd-leave-to {
  transform: rotateX(75deg) translateY(-10px);
  opacity: 0;
}

/* 뒤로 — 위에서 내려오는 릴 */
.drum-bwd-enter-from {
  transform: rotateX(75deg) translateY(-10px);
  opacity: 0;
}
.drum-bwd-leave-to {
  transform: rotateX(-75deg) translateY(10px);
  opacity: 0;
}

/* 오른쪽 액션 */
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
.delete-btn { color: var(--text-muted); }
</style>
