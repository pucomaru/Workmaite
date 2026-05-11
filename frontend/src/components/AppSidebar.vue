<script setup>
import { ref, computed } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useMeetingsStore } from '../stores/meetings'

const props = defineProps({ open: Boolean })
const router = useRouter()
const route = useRoute()
const meetingsStore = useMeetingsStore()

const search = ref('')
const endedCollapsed = ref(false)

// 즐겨찾기 (로컬 스토리지)
const favorites = ref(new Set(JSON.parse(localStorage.getItem('favMeetings') || '[]')))
function saveFavs() { localStorage.setItem('favMeetings', JSON.stringify([...favorites.value])) }

// 컨텍스트 메뉴
const ctxMenu = ref(null)  // { id, x, y }
const renaming = ref(null)
const renameVal = ref('')

const filtered = computed(() =>
  meetingsStore.meetings.filter(m =>
    m.title.toLowerCase().includes(search.value.toLowerCase()) && m.status === 'active'
  )
)
const filteredEnded = computed(() =>
  meetingsStore.meetings.filter(m =>
    m.title.toLowerCase().includes(search.value.toLowerCase()) && m.status === 'ended'
  )
)

function goMeeting(m) {
  if (renaming.value === m.id) return
  router.push(`/meetings/${m.id}/home`)
}

function openCtx(e, m) {
  e.stopPropagation()
  e.preventDefault()
  const x = Math.min(e.clientX, window.innerWidth - 164)
  const y = Math.min(e.clientY, window.innerHeight - 148)
  ctxMenu.value = { id: m.id, x, y }
}
function closeCtx() { ctxMenu.value = null }

function toggleFav(id) {
  if (favorites.value.has(id)) favorites.value.delete(id)
  else favorites.value.add(id)
  saveFavs()
  closeCtx()
}

function startRename(id) {
  const m = meetingsStore.meetings.find(m => m.id === id)
  renameVal.value = m?.title || ''
  renaming.value = id
  closeCtx()
}

async function submitRename(id) {
  if (!renameVal.value.trim()) { renaming.value = null; return }
  try { await meetingsStore.updateTitle(id, renameVal.value.trim()) } catch {}
  renaming.value = null
}

async function deleteMeeting(id) {
  const m = meetingsStore.meetings.find(m => m.id === id)
  if (!confirm(`"${m?.title}" 회의체를 삭제하시겠습니까?`)) { closeCtx(); return }
  closeCtx()
  try { await meetingsStore.deleteMeeting(id) } catch {}
}
</script>

<template>
  <aside class="sidebar" :class="{ open }">
    <nav class="sidebar-nav">
      <router-link to="/" class="nav-item" :class="{ active: route.path === '/' }">
        <svg width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6"/></svg>
        홈
      </router-link>
      <router-link to="/minutes" class="nav-item" :class="{ active: route.path === '/minutes' }">
        <svg width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"/></svg>
        회의록
      </router-link>
      <router-link to="/reports" class="nav-item" :class="{ active: route.path === '/reports' }">
        <svg width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M9 17v-2m3 2v-4m3 4v-6m2 10H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"/></svg>
        보고서
      </router-link>
    </nav>

    <div class="sidebar-section">
      <input v-model="search" class="form-input" placeholder="검색..." style="margin-bottom:10px" />

      <!-- 진행중인 회의체 -->
      <div class="section-label">진행중인 회의체</div>
      <div class="meeting-list">
        <div v-for="m in filtered" :key="m.id"
          class="meeting-item"
          :class="{ active: route.params.meetingId == m.id }"
          @click="goMeeting(m)">
          <div class="meeting-item-dot"></div>
          <template v-if="renaming === m.id">
            <input
              v-model="renameVal" class="rename-input" autofocus
              @keyup.enter="submitRename(m.id)"
              @keyup.esc="renaming = null"
              @blur="submitRename(m.id)"
              @click.stop />
          </template>
          <template v-else>
            <span class="meeting-title flex-grow-1 text-truncate">
              <i v-if="favorites.has(m.id)" class="bi bi-star-fill me-1" style="color:#f59e0b;font-size:10px"></i>
              {{ m.title }}
            </span>
            <button class="ctx-btn" @click.stop="openCtx($event, m)" title="옵션">
              <i class="bi bi-three-dots"></i>
            </button>
          </template>
        </div>
        <div v-if="!filtered.length" class="sidebar-empty">회의체 없음</div>
      </div>

      <!-- 지난 회의체 -->
      <template v-if="filteredEnded.length">
        <div class="section-label mt-3" style="cursor:pointer" @click="endedCollapsed = !endedCollapsed">
          지난 회의체
          <i class="bi ms-1" :class="endedCollapsed ? 'bi-chevron-right' : 'bi-chevron-down'" style="font-size:10px"></i>
        </div>
        <div v-show="!endedCollapsed" class="meeting-list">
          <div v-for="m in filteredEnded" :key="m.id"
            class="meeting-item ended"
            :class="{ active: route.params.meetingId == m.id }"
            @click="goMeeting(m)">
            <div class="meeting-item-dot ended-dot"></div>
            <template v-if="renaming === m.id">
              <input
                v-model="renameVal" class="rename-input" autofocus
                @keyup.enter="submitRename(m.id)"
                @keyup.esc="renaming = null"
                @blur="submitRename(m.id)"
                @click.stop />
            </template>
            <template v-else>
              <span class="meeting-title flex-grow-1 text-truncate">
                <i v-if="favorites.has(m.id)" class="bi bi-star-fill me-1" style="color:#f59e0b;font-size:10px"></i>
                {{ m.title }}
              </span>
              <button class="ctx-btn" @click.stop="openCtx($event, m)" title="옵션">
                <i class="bi bi-three-dots"></i>
              </button>
            </template>
          </div>
        </div>
      </template>
    </div>
  </aside>

  <!-- 컨텍스트 메뉴 -->
  <Teleport to="body">
    <div v-if="ctxMenu" class="ctx-backdrop" @click="closeCtx">
      <div class="ctx-popup"
        :style="{ top: ctxMenu.y + 'px', left: ctxMenu.x + 'px' }"
        @click.stop>
        <button class="ctx-item" @click="toggleFav(ctxMenu.id)">
          <i class="bi" :class="favorites.has(ctxMenu.id) ? 'bi-star-fill text-warning' : 'bi-star'"></i>
          {{ favorites.has(ctxMenu.id) ? '즐겨찾기 해제' : '즐겨찾기' }}
        </button>
        <button class="ctx-item" @click="startRename(ctxMenu.id)">
          <i class="bi bi-pencil"></i> 이름 변경
        </button>
        <div class="ctx-divider"></div>
        <button class="ctx-item danger" @click="deleteMeeting(ctxMenu.id)">
          <i class="bi bi-trash"></i> 삭제
        </button>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.sidebar {
  width: var(--sidebar-w);
  background: #fff;
  border-right: 1px solid var(--border);
  height: 100%;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  position: fixed;
  left: 0;
  top: var(--header-h);
  bottom: 0;
  transform: translateX(-100%);
  transition: transform .2s;
  z-index: 90;
  padding: 12px 0;
}
.sidebar.open { transform: translateX(0); }
.sidebar-nav { padding: 4px 12px 12px; border-bottom: 1px solid var(--border); display: flex; flex-direction: column; gap: 2px; }
.nav-item { display: flex; align-items: center; gap: 8px; padding: 8px 10px; border-radius: 6px; color: var(--text-muted); font-size: 13px; font-weight: 500; transition: all .15s; }
.nav-item:hover, .nav-item.active { background: #eff6ff; color: var(--primary); }
.sidebar-section { padding: 12px; flex: 1; }
.section-label { font-size: 11px; font-weight: 600; color: var(--text-muted); text-transform: uppercase; letter-spacing: .05em; margin-bottom: 8px; display: flex; align-items: center; user-select: none; }
.meeting-list { display: flex; flex-direction: column; gap: 2px; }
.meeting-item { display: flex; align-items: center; gap: 8px; padding: 7px 6px 7px 10px; border-radius: 6px; cursor: pointer; font-size: 13px; color: var(--text-muted); transition: all .15s; }
.meeting-item:hover, .meeting-item.active { background: #eff6ff; color: var(--primary); }
.meeting-item:hover .ctx-btn { opacity: 1; }
.meeting-title { font-size: 13px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.meeting-item-dot { width: 6px; height: 6px; background: var(--success); border-radius: 50%; flex-shrink: 0; }
.sidebar-empty { font-size: 12px; color: var(--text-muted); padding: 8px 10px; }
.ended-dot { background: #94a3b8 !important; }
.meeting-item.ended { opacity: .8; }
.mt-3 { margin-top: 12px; }

/* … 버튼 */
.ctx-btn {
  flex-shrink: 0;
  background: none; border: none; cursor: pointer;
  width: 22px; height: 22px;
  display: flex; align-items: center; justify-content: center;
  border-radius: 4px;
  color: var(--text-muted);
  font-size: 13px;
  opacity: 0;
  transition: opacity .15s, background .15s;
}
.ctx-btn:hover { background: rgba(0,0,0,.08); }

/* 이름 변경 입력 */
.rename-input {
  flex: 1; font-size: 13px; border: 1px solid var(--primary);
  border-radius: 4px; padding: 2px 6px; outline: none; min-width: 0;
}

/* 컨텍스트 메뉴 */
.ctx-backdrop { position: fixed; inset: 0; z-index: 9000; }
.ctx-popup {
  position: fixed; z-index: 9001;
  background: #fff; border: 1px solid var(--border);
  border-radius: 10px; box-shadow: 0 8px 24px rgba(0,0,0,.15);
  min-width: 148px; padding: 4px;
}
.ctx-item {
  display: flex; align-items: center; gap: 8px;
  width: 100%; padding: 8px 12px;
  background: none; border: none; cursor: pointer;
  font-size: 13px; color: #334155; border-radius: 6px;
  text-align: left; transition: background .1s;
}
.ctx-item:hover { background: #f1f5f9; }
.ctx-item.danger { color: #dc2626; }
.ctx-item.danger:hover { background: #fef2f2; }
.ctx-divider { height: 1px; background: var(--border); margin: 3px 8px; }
</style>
