<script setup>
import { ref, computed, watch } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useMeetingsStore } from '../stores/meetings'
import { useAuthStore } from '../stores/auth'

const props = defineProps({ open: Boolean })
const router = useRouter()
const route = useRoute()
const meetingsStore = useMeetingsStore()
const auth = useAuthStore()

const search = ref('')

const filtered = computed(() =>
  meetingsStore.meetings.filter(m =>
    m.title.toLowerCase().includes(search.value.toLowerCase()) && m.status === 'active'
  )
)

function goMeeting(m) {
  router.push(`/meetings/${m.id}/agenda`)
}

const isAdmin = computed(() => meetingsStore.myRole === 'admin')
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
      <router-link to="/tacit-knowledge" class="nav-item" :class="{ active: route.path === '/tacit-knowledge' }">
        <svg width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"/></svg>
        암묵지 관리
      </router-link>
    </nav>

    <div class="sidebar-section">
      <div class="section-label">진행중인 회의체</div>
      <input v-model="search" class="form-input" placeholder="검색..." style="margin-bottom:8px" />
      <div class="meeting-list">
        <div
          v-for="m in filtered"
          :key="m.id"
          class="meeting-item"
          :class="{ active: route.params.meetingId == m.id }"
          @click="goMeeting(m)"
        >
          <div class="meeting-item-dot"></div>
          <span>{{ m.title }}</span>
        </div>
        <div v-if="!filtered.length" class="sidebar-empty">회의체 없음</div>
      </div>
    </div>
  </aside>
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
.section-label { font-size: 11px; font-weight: 600; color: var(--text-muted); text-transform: uppercase; letter-spacing: .05em; margin-bottom: 8px; }
.meeting-list { display: flex; flex-direction: column; gap: 2px; }
.meeting-item { display: flex; align-items: center; gap: 8px; padding: 7px 10px; border-radius: 6px; cursor: pointer; font-size: 13px; color: var(--text-muted); transition: all .15s; }
.meeting-item:hover, .meeting-item.active { background: #eff6ff; color: var(--primary); }
.meeting-item-dot { width: 6px; height: 6px; background: var(--success); border-radius: 50%; flex-shrink: 0; }
.sidebar-empty { font-size: 12px; color: var(--text-muted); padding: 8px 10px; }
</style>
