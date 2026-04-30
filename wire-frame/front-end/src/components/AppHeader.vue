<script setup>
import { ref, computed, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth'
import { useNotificationsStore } from '../stores/notifications'
import { useMeetingsStore } from '../stores/meetings'
import api from '../api'

function formatTime(ts) {
  if (!ts) return ''
  const d = new Date(ts)
  const now = new Date()
  const diff = Math.floor((now - d) / 1000)
  if (diff < 60) return '방금 전'
  if (diff < 3600) return `${Math.floor(diff / 60)}분 전`
  if (diff < 86400) return `${Math.floor(diff / 3600)}시간 전`
  return d.toLocaleDateString('ko-KR')
}

const props = defineProps({ sidebarOpen: Boolean })
const emit = defineEmits(['toggle-sidebar'])

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const notifStore = useNotificationsStore()
const meetingsStore = useMeetingsStore()

const showNotif = ref(false)
const showProfile = ref(false)

// ── 회의체 제목 인라인 편집 (관리자) ─────────────────────────────
const editingTitle = ref(false)
const editTitle = ref('')
const savingTitle = ref(false)

const meetingId = computed(() => route.params.meetingId)
const isAdmin = computed(() => meetingsStore.myRole === 'admin')
const meetingStatus = computed(() => meetingsStore.currentMeeting?.status)
const meetingTitle = computed(() => {
  const id = route.params.meetingId
  if (!id) return null
  return meetingsStore.currentMeeting?.title || meetingsStore.meetings.find(m => m.id == id)?.title
})

function startEditTitle() {
  if (!isAdmin.value) return
  editTitle.value = meetingTitle.value || ''
  editingTitle.value = true
}

async function saveTitle() {
  if (!editTitle.value.trim() || savingTitle.value) return
  savingTitle.value = true
  try {
    await meetingsStore.updateTitle(Number(meetingId.value), editTitle.value.trim())
    editingTitle.value = false
  } finally {
    savingTitle.value = false
  }
}

function cancelEditTitle() {
  editingTitle.value = false
}

// ── 구성원 관리 팝업 ───────────────────────────────────────────
const showMemberMgmt = ref(false)
const memberSearch = ref('')
const searchResults = ref([])
const searchLoading = ref(false)
let searchTimeout = null

const members = computed(() => meetingsStore.currentMembers)
const visibleAvatars = computed(() => members.value.slice(0, 3))
const memberCount = computed(() => members.value.length)

async function searchUsers() {
  if (!memberSearch.value.trim()) { searchResults.value = []; return }
  searchLoading.value = true
  clearTimeout(searchTimeout)
  searchTimeout = setTimeout(async () => {
    try {
      const { data } = await api.get(`/api/users/search?q=${encodeURIComponent(memberSearch.value)}`)
      // 이미 구성원인 사람 제외
      const memberUserIds = new Set(members.value.map(m => m.user_id))
      searchResults.value = data.filter(u => !memberUserIds.has(u.id))
    } finally {
      searchLoading.value = false
    }
  }, 300)
}

async function addMember(user) {
  await meetingsStore.addMember(Number(meetingId.value), user.id, 'presenter')
  memberSearch.value = ''
  searchResults.value = []
}

async function changeRole(member) {
  const newRole = member.role === 'admin' ? 'presenter' : 'admin'
  await meetingsStore.updateMemberRole(Number(meetingId.value), member.id, newRole)
}

async function removeMember(member) {
  if (!confirm(`${member.user?.name}님을 구성원에서 제거하시겠습니까?`)) return
  await meetingsStore.removeMember(Number(meetingId.value), member.id)
}

watch(
  () => route.params.meetingId,
  (id) => {
    if (id) meetingsStore.fetchMembers(id)
    else meetingsStore.currentMembers = []
    editingTitle.value = false
    showMemberMgmt.value = false
  },
  { immediate: true }
)

function handleNotifClick(n) {
  notifStore.markRead(n.id)
  showNotif.value = false
  if (n.ref_type === 'meeting' && n.ref_id) router.push(`/meetings/${n.ref_id}/agenda`)
  if (n.ref_type === 'session' && n.ref_id) router.push(`/meetings/${n.meeting_id}/sessions`)
}

function logout() {
  auth.logout()
  router.push('/login')
}
</script>

<template>
  <header class="header">
    <div class="header-left">
      <button class="btn-ghost btn-icon" @click="emit('toggle-sidebar')">
        <svg width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
          <path d="M3 12h18M3 6h18M3 18h18"/>
        </svg>
      </button>
      <router-link to="/" class="logo">
        <span class="logo-icon">W</span>
        <span class="logo-text">WorkMate</span>
      </router-link>

      <!-- 회의체 제목 영역 -->
      <template v-if="meetingTitle">
        <div class="header-divider" />

        <!-- 관리자: 인라인 편집 가능 -->
        <template v-if="isAdmin && editingTitle">
          <input
            v-model="editTitle"
            class="title-input"
            @keydown.enter="saveTitle"
            @keydown.escape="cancelEditTitle"
            @blur="saveTitle"
            autofocus
          />
        </template>
        <template v-else>
          <span
            class="meeting-title-inline"
            :class="{ editable: isAdmin, ended: meetingStatus === 'ended' }"
            :title="isAdmin ? '클릭하여 제목 수정' : meetingTitle"
            @click="startEditTitle"
          >{{ meetingTitle }}</span>
          <span v-if="meetingStatus === 'ended'" class="status-badge-ended">종료</span>
        </template>

        <!-- 구성원 아바타 + 관리 버튼 -->
        <div
          class="member-avatars-wrap"
          v-if="memberCount > 0"
          :title="isAdmin ? '구성원 관리' : '구성원 목록'"
          @click="showMemberMgmt = !showMemberMgmt"
        >
          <div class="member-avatars">
            <div
              v-for="(m, i) in visibleAvatars"
              :key="m.id"
              class="member-avatar"
              :style="{ zIndex: 3 - i }"
              :title="m.user?.name"
            >{{ (m.user?.name || '?')[0] }}</div>

          </div>
        </div>
      </template>
    </div>

    <div class="header-right">
      <!-- 알림 -->
      <div class="notif-wrap">
        <button class="btn-ghost btn-icon" @click="showNotif = !showNotif">
          <svg width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
            <path d="M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6 6 0 10-12 0v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9"/>
          </svg>
          <span v-if="notifStore.unreadCount" class="notif-badge">{{ notifStore.unreadCount }}</span>
        </button>
        <div v-if="showNotif" class="notif-dropdown">
          <div class="notif-header">
            <span>알림</span>
            <button class="btn-ghost btn-sm" @click="notifStore.markAllRead(); showNotif=false">전체 읽음</button>
          </div>
          <div class="notif-list">
            <div v-if="!notifStore.notifications.length" class="notif-empty">알림이 없습니다</div>
            <div
              v-for="n in notifStore.notifications"
              :key="n.id"
              class="notif-item"
              :class="{ unread: !n.is_read }"
              @click="handleNotifClick(n)"
            >
              <span class="notif-msg">{{ n.message }}</span>
              <span class="notif-time">{{ formatTime(n.created_at) }}</span>
            </div>
          </div>
        </div>
      </div>

      <div class="profile-wrap" v-if="auth.user">
        <button class="btn-ghost profile-btn" @click="showProfile = !showProfile">
          <span class="avatar">{{ auth.user.name[0] }}</span>
          <span>{{ auth.user.name }}</span>
        </button>
        <div v-if="showProfile" class="profile-dropdown">
          <div class="profile-info">
            <div class="avatar-lg">{{ auth.user.name[0] }}</div>
            <div>
              <div style="font-weight:600">{{ auth.user.name }}</div>
              <div style="color:var(--text-muted);font-size:12px">{{ auth.user.employee_id }}</div>
              <div v-if="auth.user.department" style="color:var(--text-muted);font-size:11px;margin-top:2px">{{ auth.user.department }}</div>
            </div>
          </div>
          <router-link to="/profile" class="btn btn-outline btn-sm" style="width:100%;justify-content:center;display:flex;text-decoration:none" @click="showProfile=false">
            개인설정
          </router-link>
          <button class="btn btn-ghost btn-sm" style="width:100%;justify-content:center" @click="logout">로그아웃</button>
        </div>
      </div>
    </div>

    <!-- 구성원 관리 팝업 -->
    <div v-if="showMemberMgmt" class="member-mgmt-popup">
      <div class="mgmt-header">
        <div style="display:flex;align-items:baseline;gap:6px">
          <span style="font-weight:600;font-size:14px">{{ isAdmin ? '구성원 관리' : '구성원 목록' }}</span>
          <span style="font-size:12px;color:var(--text-muted)">{{ memberCount }}명</span>
        </div>
        <button class="btn-ghost btn-icon" style="color:#64748b" @click="showMemberMgmt = false">✕</button>
      </div>

      <!-- 구성원 검색 추가 (관리자만) -->
      <div v-if="isAdmin" class="mgmt-search">
        <input
          v-model="memberSearch"
          class="mgmt-input"
          placeholder="이름 또는 사번으로 검색"
          @input="searchUsers"
        />
        <div v-if="searchResults.length" class="search-results">
          <div
            v-for="u in searchResults"
            :key="u.id"
            class="search-result-item"
            @click="addMember(u)"
          >
            <span class="avatar-sm">{{ u.name[0] }}</span>
            <span>{{ u.name }}</span>
            <span style="color:var(--text-muted);font-size:11px">{{ u.employee_id }}</span>
            <span class="add-label">+ 추가</span>
          </div>
        </div>
      </div>

      <!-- 구성원 목록 -->
      <div class="mgmt-list">
        <div v-for="m in members" :key="m.id" class="mgmt-member">
          <span class="avatar-sm">{{ (m.user?.name || '?')[0] }}</span>
          <div class="mgmt-member-info">
            <span class="mgmt-name">{{ m.user?.name }}</span>
            <span class="mgmt-emp">{{ m.user?.employee_id }}</span>
          </div>
          <template v-if="isAdmin">
            <button
              class="role-badge"
              :class="m.role"
              @click="changeRole(m)"
              title="클릭하여 권한 변경"
            >{{ m.role === 'admin' ? '관리자' : '구성원' }}</button>
            <button class="btn-ghost btn-icon mgmt-del" @click="removeMember(m)" title="제거">✕</button>
          </template>
          <template v-else>
            <span class="role-badge" :class="m.role">{{ m.role === 'admin' ? '관리자' : '구성원' }}</span>
          </template>
        </div>
      </div>
    </div>

    <div v-if="showNotif || showProfile || showMemberMgmt" class="backdrop"
      @click="showNotif=false; showProfile=false; showMemberMgmt=false" />
  </header>
</template>

<style scoped>
.header {
  height: var(--header-h);
  background: var(--primary);
  display: flex;
  align-items: center;
  padding: 0 16px;
  gap: 0;
  position: relative;
  z-index: 100;
  flex-shrink: 0;
}
.btn-icon { padding: 6px; border-radius: 6px; color: rgba(255,255,255,.7); display: flex; align-items: center; justify-content: center; }
.btn-icon:hover { background: rgba(255,255,255,.1); color: #fff; }
.header-left { display: flex; align-items: center; gap: 10px; flex: 1; min-width: 0; overflow: hidden; }
.logo { display: flex; align-items: center; gap: 8px; color: #fff; margin-left: 6px; flex-shrink: 0; }
.logo-icon { width: 28px; height: 28px; background: var(--accent); border-radius: 6px; display: flex; align-items: center; justify-content: center; font-weight: 700; font-size: 14px; color: #fff; }
.logo-text { font-weight: 700; font-size: 16px; }
.header-divider { width: 1px; height: 18px; background: rgba(255,255,255,.25); margin: 0 4px; flex-shrink: 0; }
.meeting-title-inline {
  color: rgba(255,255,255,.85);
  font-size: 13px;
  font-weight: 500;
  white-space: nowrap;
  max-width: 240px;
  overflow: hidden;
  text-overflow: ellipsis;
}
.meeting-title-inline.editable { cursor: pointer; border-bottom: 1px dashed rgba(255,255,255,.4); }
.meeting-title-inline.editable:hover { color: #fff; border-bottom-color: rgba(255,255,255,.8); }
.meeting-title-inline.ended { opacity: .6; }
.status-badge-ended {
  font-size: 10px; font-weight: 700; color: #fff;
  background: rgba(255,255,255,.2); border: 1px solid rgba(255,255,255,.3);
  padding: 2px 6px; border-radius: 99px; flex-shrink: 0;
}
.title-input {
  background: rgba(255,255,255,.15);
  border: 1px solid rgba(255,255,255,.5);
  border-radius: 4px;
  color: #fff;
  font-size: 13px;
  padding: 3px 8px;
  outline: none;
  min-width: 160px;
  max-width: 280px;
}
.title-input::placeholder { color: rgba(255,255,255,.5); }

/* 구성원 아바타 */
.member-avatars-wrap { display: flex; align-items: center; gap: 6px; flex-shrink: 0; margin-left: 2px; cursor: pointer; padding: 3px 6px; border-radius: 99px; transition: background .15s; }
.member-avatars-wrap:hover { background: rgba(255,255,255,.12); }
.member-avatars { display: flex; align-items: center; }
.member-avatar { width: 26px; height: 26px; border-radius: 50%; background: var(--accent); border: 2px solid var(--primary); display: flex; align-items: center; justify-content: center; font-size: 11px; font-weight: 700; color: #fff; flex-shrink: 0; margin-left: -6px; }
.member-avatar:first-child { margin-left: 0; }
.member-count { height: 20px; padding: 0 6px; border-radius: 99px; background: rgba(255,255,255,.2); border: 1.5px solid rgba(255,255,255,.4); display: flex; align-items: center; justify-content: center; font-size: 11px; font-weight: 600; color: #fff; white-space: nowrap; margin-left: 4px; flex-shrink: 0; }



.header-right { margin-left: auto; display: flex; align-items: center; gap: 8px; flex-shrink: 0; }

/* 구성원 관리 팝업 */
.member-mgmt-popup {
  position: absolute;
  top: calc(var(--header-h) + 4px);
  left: 240px;
  width: 340px;
  background: #fff;
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-lg);
  z-index: 200;
  overflow: hidden;
}
.mgmt-header { padding: 12px 16px; border-bottom: 1px solid var(--border); display: flex; justify-content: space-between; align-items: center; }
.mgmt-search { padding: 10px 12px; border-bottom: 1px solid var(--border); position: relative; }
.mgmt-input { width: 100%; padding: 6px 10px; border: 1px solid var(--border); border-radius: 6px; font-size: 13px; outline: none; box-sizing: border-box; }
.mgmt-input:focus { border-color: var(--primary); }
.search-results { position: absolute; top: 100%; left: 12px; right: 12px; background: #fff; border: 1px solid var(--border); border-radius: 6px; box-shadow: var(--shadow-lg); z-index: 10; max-height: 160px; overflow-y: auto; }
.search-result-item { display: flex; align-items: center; gap: 8px; padding: 8px 12px; cursor: pointer; font-size: 13px; }
.search-result-item:hover { background: #f8fafc; }
.add-label { margin-left: auto; color: var(--primary); font-weight: 600; font-size: 12px; }
.mgmt-list { max-height: 280px; overflow-y: auto; padding: 8px 0; }
.mgmt-member { display: flex; align-items: center; gap: 8px; padding: 8px 14px; }
.mgmt-member:hover { background: #f8fafc; }
.mgmt-member-info { flex: 1; min-width: 0; display: flex; flex-direction: column; }
.mgmt-name { font-size: 13px; font-weight: 500; }
.mgmt-emp { font-size: 11px; color: var(--text-muted); }
.avatar-sm { width: 28px; height: 28px; border-radius: 50%; background: var(--accent); display: flex; align-items: center; justify-content: center; font-size: 12px; font-weight: 600; color: #fff; flex-shrink: 0; }
.role-badge {
  font-size: 11px; font-weight: 600; padding: 2px 8px; border-radius: 99px; cursor: pointer;
  border: 1px solid;
}
.role-badge.admin { background: #eff6ff; color: #1d4ed8; border-color: #bfdbfe; }
.role-badge.presenter { background: #f8fafc; color: var(--text-muted); border-color: var(--border); }
.mgmt-del { color: var(--danger) !important; font-size: 12px !important; }

/* 알림/프로필 (기존과 동일) */
.notif-wrap { position: relative; }
.notif-badge { position: absolute; top: -2px; right: -2px; background: var(--danger); color: #fff; font-size: 10px; font-weight: 700; min-width: 16px; height: 16px; border-radius: 99px; display: flex; align-items: center; justify-content: center; padding: 0 3px; }
.notif-dropdown { position: absolute; top: calc(100% + 8px); right: 0; width: 320px; background: #fff; border: 1px solid var(--border); border-radius: var(--radius-lg); box-shadow: var(--shadow-lg); z-index: 200; overflow: hidden; }
.notif-header { padding: 12px 16px; border-bottom: 1px solid var(--border); display: flex; align-items: center; justify-content: space-between; font-weight: 600; font-size: 13px; }
.notif-list { max-height: 360px; overflow-y: auto; }
.notif-empty { padding: 24px; text-align: center; color: var(--text-muted); font-size: 13px; }
.notif-item { padding: 12px 16px; cursor: pointer; border-bottom: 1px solid var(--border); display: flex; flex-direction: column; gap: 4px; }
.notif-item:last-child { border-bottom: none; }
.notif-item:hover { background: #f8fafc; }
.notif-item.unread { background: #eff6ff; }
.notif-msg { font-size: 13px; line-height: 1.4; }
.notif-time { font-size: 11px; color: var(--text-muted); }
.profile-wrap { position: relative; }
.profile-btn { display: flex; align-items: center; gap: 8px; color: rgba(255,255,255,.9); padding: 4px 8px; border-radius: 6px; }
.profile-btn:hover { background: rgba(255,255,255,.1); color: #fff; }
.avatar { width: 26px; height: 26px; background: var(--accent); border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 12px; font-weight: 600; color: #fff; }
.avatar-lg { width: 36px; height: 36px; background: var(--accent); border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 16px; font-weight: 600; color: #fff; flex-shrink: 0; }
.profile-dropdown { position: absolute; top: calc(100% + 8px); right: 0; width: 220px; background: #fff; border: 1px solid var(--border); border-radius: var(--radius-lg); box-shadow: var(--shadow-lg); z-index: 200; padding: 16px; display: flex; flex-direction: column; gap: 12px; }
.profile-info { display: flex; align-items: center; gap: 10px; }
.backdrop { position: fixed; inset: 0; z-index: 190; }
</style>

