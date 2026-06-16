<script setup>
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import api from '../api'
import { confirmDialog } from '../composables/useConfirm'
import { useAuthStore } from '../stores/auth'
import { useMeetingsStore } from '../stores/meetings'
import { useThemeStore } from '../stores/theme'
import AppIcon from './AppIcon.vue'
import TokenUsageModal from './TokenUsageModal.vue'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const meetingsStore = useMeetingsStore()

const themeStore = useThemeStore()

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
  if (!memberSearch.value.trim()) {
    searchResults.value = []
    return
  }
  searchLoading.value = true
  clearTimeout(searchTimeout)
  searchTimeout = setTimeout(async () => {
    try {
      const { data } = await api.get(
        `/api/v1/users/search?q=${encodeURIComponent(memberSearch.value)}`,
      )
      // 이미 구성원인 사람 제외
      const memberUserIds = new Set(members.value.map(m => m.user_id))
      searchResults.value = data.filter(u => !memberUserIds.has(u.id))
    } finally {
      searchLoading.value = false
    }
  }, 300)
}

async function addMember(user) {
  await meetingsStore.addMember(Number(meetingId.value), user.id, 'member')
  memberSearch.value = ''
  searchResults.value = []
}

async function changeRole(member) {
  const newRole = member.role === 'admin' ? 'member' : 'admin'
  await meetingsStore.updateMemberRole(Number(meetingId.value), member.id, newRole)
}

async function removeMember(member) {
  if (
    !(await confirmDialog(`${member.user?.name}님을 구성원에서 제거하시겠습니까?`, {
      danger: true,
    }))
  )
    return
  await meetingsStore.removeMember(Number(meetingId.value), member.id)
}

watch(
  () => route.params.meetingId,
  id => {
    if (id) meetingsStore.fetchMembers(id)
    else meetingsStore.currentMembers = []
    editingTitle.value = false
    showMemberMgmt.value = false
  },
  { immediate: true },
)

function logout() {
  auth.logout()
  router.push('/landing')
}

// ── 개인설정 모달 ──────────────────────────────────────────────
// 권한 라벨 (읽기 전용 표시용)
const ROLE_LABELS = {
  SYSTEM_ADMIN: '시스템 관리자',
  COMPANY_ADMIN: '회사 관리자',
  USER: '일반 사용자',
}
const roleLabel = computed(() => ROLE_LABELS[auth.user?.role] || auth.user?.role || '일반 사용자')

const showProfileSettings = ref(false)
const showUsageModal = ref(false)
function openUsageModal() {
  showProfile.value = false
  showUsageModal.value = true
}
const profileForm = ref({
  name: '',
  company: '',
  department: '',
  position: '',
  password: '',
  passwordConfirm: '',
})
const profileSaving = ref(false)
const profileMsg = ref('')
const showNewPw = ref(false)
const showConfirmPw = ref(false)

function openProfileSettings() {
  profileForm.value = {
    name: auth.user?.name || '',
    company: auth.user?.company || '',
    department: auth.user?.department || '',
    position: auth.user?.position || '',
    password: '',
    passwordConfirm: '',
  }
  profileMsg.value = ''
  showProfile.value = false
  showProfileSettings.value = true
}

async function saveProfileSettings() {
  if (
    profileForm.value.password &&
    profileForm.value.password !== profileForm.value.passwordConfirm
  ) {
    profileMsg.value = 'error:비밀번호가 일치하지 않습니다.'
    return
  }
  profileSaving.value = true
  profileMsg.value = ''
  try {
    const payload = {
      name: profileForm.value.name,
      department: profileForm.value.department || null,
      company: profileForm.value.company || null,
      position: profileForm.value.position || null,
    }
    if (profileForm.value.password) payload.password = profileForm.value.password
    await auth.updateProfile(payload)
    profileForm.value.password = ''
    profileForm.value.passwordConfirm = ''
    showProfileSettings.value = false
  } catch (e) {
    profileMsg.value = 'error:' + (e.response?.data?.detail || '저장에 실패했습니다.')
  } finally {
    profileSaving.value = false
  }
}
</script>

<template>
  <header class="header">
    <div class="header-left">
      <router-link to="/" class="logo">
        <img src="../assets/workmaite-logo-white.png" class="logo-img" alt="Workma!te" />
      </router-link>

      <!-- 회의체 제목 영역 -->
      <template v-if="meetingTitle">
        <div class="header-divider" />

        <!-- 관리자: 인라인 편집 가능 -->
        <template v-if="isAdmin && editingTitle">
          <input
            id="edit-title"
            name="edit-title"
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
            >{{ meetingTitle }}</span
          >
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
            >
              {{ (m.user?.name || '?')[0] }}
            </div>
          </div>
        </div>
      </template>
    </div>

    <!-- 중앙 네비게이션 -->
    <nav class="header-center-nav">
      <router-link to="/" class="center-nav-item" :class="{ active: route.path === '/' }">
        <AppIcon name="home" :size="18" />
        홈
      </router-link>
      <router-link
        to="/archive"
        class="center-nav-item"
        :class="{ active: route.path === '/archive' }"
      >
        <AppIcon name="archive" :size="18" />
        아카이브
      </router-link>
      <router-link
        to="/company"
        class="center-nav-item"
        :class="{ active: route.path === '/company' }"
      >
        <AppIcon name="company" :size="18" :color="'#6ee7b7'"/>
        조직
      </router-link>
      <router-link
        to="/meetings"
        class="center-nav-item"
        :class="{ active: route.path === '/meetings' }"
      >
        <AppIcon name="Meetings" :size="18" :color="'#60a5fa'" />
        회의체
      </router-link>
      <router-link
        to="/session-record"
        class="center-nav-item"
        :class="{ active: route.path === '/session-record' }"
      >
        <AppIcon name="session" :size="17" :color="'#fdba74'" />
        회의
      </router-link>
    </nav>

    <div class="header-right">
      <!-- 주야간 모드 토글 -->
      <button
        class="btn-ghost btn-icon theme-toggle-btn"
        @click="themeStore.toggle()"
        :title="themeStore.nightMode ? '주간 모드로 전환' : '야간 모드로 전환'"
      >
        <svg
          v-if="themeStore.nightMode"
          width="16"
          height="16"
          fill="none"
          stroke="currentColor"
          stroke-width="2"
          viewBox="0 0 24 24"
        >
          <circle cx="12" cy="12" r="5" />
          <path
            d="M12 1v2M12 21v2M4.22 4.22l1.42 1.42M18.36 18.36l1.42 1.42M1 12h2M21 12h2M4.22 19.78l1.42-1.42M18.36 5.64l1.42-1.42"
          />
        </svg>
        <svg
          v-else
          width="16"
          height="16"
          fill="none"
          stroke="currentColor"
          stroke-width="2"
          viewBox="0 0 24 24"
        >
          <path d="M21 12.79A9 9 0 1111.21 3 7 7 0 0021 12.79z" />
        </svg>
      </button>

      <div class="profile-wrap" v-if="auth.user">
        <button class="btn-ghost profile-btn" @click="showProfile = !showProfile">
          <span class="avatar">{{ auth.user.name[0] }}</span>
          <span style="color: var(--dark-text)">{{ auth.user.name }}</span>
        </button>
        <div v-if="showProfile" class="profile-dropdown">
          <div class="profile-info">
            <div class="avatar-lg">{{ auth.user.name[0] }}</div>
            <div>
              <div style="font-weight: 600; color: var(--dark-text)">{{ auth.user.name }}</div>
              <div style="color: var(--text-muted); font-size: 12px">
                {{ auth.user.employee_id }}
              </div>
              <div
                v-if="auth.user.department"
                style="color: var(--text-muted); font-size: 12px; margin-top: 2px"
              >
                {{ auth.user.department }}
              </div>
            </div>
          </div>
          <button
            class="btn btn-ghost btn-sm"
            style="width: 100%; justify-content: center; display: flex; gap: 6px"
            @click="openProfileSettings"
          >
            <i class="bi bi-gear"></i>개인설정
          </button>
          <button
            class="btn btn-ghost btn-sm"
            style="width: 100%; justify-content: center; display: flex; gap: 6px"
            @click="openUsageModal"
          >
            <i class="bi bi-bar-chart-line"></i>사용량
          </button>
          <button
            class="btn btn-ghost btn-sm"
            style="width: 100%; justify-content: center"
            @click="logout"
          >
            로그아웃
          </button>
        </div>
      </div>
    </div>

    <!-- 구성원 관리 팝업 -->
    <div v-if="showMemberMgmt" class="member-mgmt-popup">
      <div class="mgmt-header">
        <div style="display: flex; align-items: baseline; gap: 6px">
          <span style="font-weight: 600; font-size: 14px">{{
            isAdmin ? '구성원 관리' : '구성원 목록'
          }}</span>
          <span style="font-size: 12px; color: var(--text-muted)">{{ memberCount }}명</span>
        </div>
        <button
          class="btn-ghost btn-icon"
          style="color: var(--text-muted)"
          @click="showMemberMgmt = false"
        >
          ✕
        </button>
      </div>

      <!-- 구성원 검색 추가 (관리자만) -->
      <div v-if="isAdmin" class="mgmt-search">
        <input
          id="member-search"
          name="member-search"
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
            <span style="color: var(--text-muted); font-size: 12px">{{ u.employee_id }}</span>
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
            >
              {{ m.role === 'admin' ? '관리자' : '구성원' }}
            </button>
            <button class="btn-ghost btn-icon mgmt-del" @click="removeMember(m)" title="제거">
              ✕
            </button>
          </template>
          <template v-else>
            <span class="role-badge" :class="m.role">{{
              m.role === 'admin' ? '관리자' : '구성원'
            }}</span>
          </template>
        </div>
      </div>
    </div>

    <!-- prettier-ignore -->
    <div
      v-if="showProfile || showMemberMgmt"
      class="backdrop"
      @click="showProfile = false; showMemberMgmt = false"
    />

    <TokenUsageModal v-if="showUsageModal" @close="showUsageModal = false" />

    <!-- 개인설정 모달 -->
    <Teleport to="body">
      <Transition name="modal-fade">
        <div v-if="showProfileSettings" class="app-modal-backdrop">
          <div class="app-modal app-modal-md">
            <div class="app-modal-header">
              <span class="app-modal-title">개인설정</span>
              <button class="app-modal-close" @click="showProfileSettings = false">
                <i class="bi bi-x-lg"></i>
              </button>
            </div>
            <div class="app-modal-body">
              <!-- 이름 -->
              <div class="app-modal-field">
                <label for="hdr-profile-name">이름</label>
                <input
                  id="hdr-profile-name"
                  name="name"
                  v-model="profileForm.name"
                  autocomplete="name"
                  class="form-control"
                  placeholder="홍길동"
                />
              </div>
              <!-- 회사명 -->
              <div class="app-modal-field">
                <label for="hdr-profile-company">회사명</label>
                <input
                  id="hdr-profile-company"
                  name="company"
                  v-model="profileForm.company"
                  autocomplete="organization"
                  class="form-control"
                  placeholder="-"
                />
              </div>
              <!-- 부서 -->
              <div class="app-modal-field">
                <label for="hdr-profile-department">부서</label>
                <input
                  id="hdr-profile-department"
                  name="department"
                  v-model="profileForm.department"
                  autocomplete="off"
                  class="form-control"
                  placeholder="예: 경영지원팀"
                />
              </div>
              <!-- 직위 -->
              <div class="app-modal-field">
                <label for="hdr-profile-position">직급</label>
                <input
                  id="hdr-profile-position"
                  name="position"
                  v-model="profileForm.position"
                  autocomplete="organization-title"
                  class="form-control"
                  placeholder="Manager"
                />
              </div>
              <!-- 이메일 (readonly) -->
              <div class="app-modal-field">
                <label for="hdr-profile-email"
                  >이메일 <span class="ps-readonly-tag">변경할 수 없습니다</span></label
                >
                <input
                  id="hdr-profile-email"
                  name="email"
                  :value="auth.user?.email"
                  autocomplete="email"
                  class="form-control"
                  readonly
                  style="background: var(--surface); color: var(--dark-muted)"
                />
              </div>
              <!-- 권한 (readonly) -->
              <div class="app-modal-field">
                <label for="hdr-profile-role"
                  >권한 <span class="ps-readonly-tag">변경할 수 없습니다</span></label
                >
                <input
                  id="hdr-profile-role"
                  name="role"
                  :value="roleLabel"
                  autocomplete="off"
                  class="form-control"
                  readonly
                  style="background: var(--surface); color: var(--dark-muted)"
                />
              </div>
              <!-- 비밀번호 -->
              <div class="ps-divider">비밀번호 변경</div>
              <div class="app-modal-field">
                <label for="hdr-profile-password">새 비밀번호</label>
                <div class="input-group">
                  <input
                    id="hdr-profile-password"
                    name="password"
                    v-model="profileForm.password"
                    :type="showNewPw ? 'text' : 'password'"
                    autocomplete="new-password"
                    class="form-control"
                    placeholder="새 비밀번호 입력 (변경 시만)"
                  />
                  <button
                    type="button"
                    class="input-group-text bg-light"
                    @click="showNewPw = !showNewPw"
                  >
                    <i :class="showNewPw ? 'bi bi-eye-slash' : 'bi bi-eye'" class="text-muted"></i>
                  </button>
                </div>
              </div>
              <div class="app-modal-field">
                <label for="hdr-profile-password-confirm">비밀번호 확인</label>
                <div class="input-group">
                  <input
                    id="hdr-profile-password-confirm"
                    name="passwordConfirm"
                    v-model="profileForm.passwordConfirm"
                    :type="showConfirmPw ? 'text' : 'password'"
                    autocomplete="new-password"
                    class="form-control"
                    :class="
                      profileForm.passwordConfirm
                        ? profileForm.password === profileForm.passwordConfirm
                          ? 'is-valid'
                          : 'is-invalid'
                        : ''
                    "
                    placeholder="비밀번호 재입력"
                  />
                  <button
                    type="button"
                    class="input-group-text bg-light"
                    @click="showConfirmPw = !showConfirmPw"
                  >
                    <i
                      :class="showConfirmPw ? 'bi bi-eye-slash' : 'bi bi-eye'"
                      class="text-muted"
                    ></i>
                  </button>
                </div>
              </div>
              <!-- 메시지 -->
              <div
                v-if="profileMsg"
                class="alert py-2 small mt-2"
                :class="profileMsg.startsWith('ok') ? 'alert-success' : 'alert-danger'"
              >
                <i
                  :class="
                    profileMsg.startsWith('ok')
                      ? 'bi bi-check-circle-fill'
                      : 'bi bi-exclamation-circle'
                  "
                  class="me-1"
                ></i>
                {{ profileMsg.split(':').slice(1).join(':') }}
              </div>
            </div>
            <div class="app-modal-footer">
              <button class="app-btn-cancel" @click="showProfileSettings = false">취소</button>
              <button
                class="app-btn-primary"
                :disabled="profileSaving"
                @click="saveProfileSettings"
              >
                <span v-if="profileSaving" class="spinner-border spinner-border-sm me-1"></span>
                저장
              </button>
            </div>
          </div>
        </div>
      </Transition>
    </Teleport>
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
.btn-icon {
  padding: 6px;
  border-radius: 6px;
  color: rgba(255, 255, 255, 0.7);
  display: flex;
  align-items: center;
  justify-content: center;
}
.btn-icon:hover {
  background: var(--white-10);
  color: #fff;
}
.header-left {
  display: flex;
  align-items: center;
  gap: 10px;
  flex: 1;
  min-width: 0;
  overflow: hidden;
  padding: 0;
}

/* ── 중앙 네비게이션 ── */
.header-center-nav {
  position: absolute;
  left: 50%;
  transform: translateX(-50%);
  display: flex;
  align-items: center;
  gap: 2px;
}
.center-nav-item {
  display: flex;
  align-items: center;
  gap: 5px;
  padding: 5px 12px;
  border-radius: 7px;
  color: #fff;
  font-size: 12px;
  font-weight: 500;
  white-space: nowrap;
  text-decoration: none;
}
.center-nav-item:hover {
  background: var(--white-12);
  color: #fff;
}
.center-nav-item.active {
  background: var(--white-18);
  color: #fff;
  font-weight: 600;
}
.logo {
  display: flex;
  align-items: center;
  color: #fff;
  margin-left: 0px;
  flex-shrink: 0;
}
.logo-img {
  height: 16px;
  width: auto;
}
.header-divider {
  width: 1px;
  height: 18px;
  background: rgba(255, 255, 255, 0.25);
  margin: 0 4px;
  flex-shrink: 0;
}
.meeting-title-inline {
  color: rgba(255, 255, 255, 0.85);
  font-size: 12px;
  font-weight: 500;
  white-space: nowrap;
  max-width: 240px;
  overflow: hidden;
  text-overflow: ellipsis;
}
.meeting-title-inline.editable {
  cursor: pointer;
  border-bottom: 1px dashed rgba(255, 255, 255, 0.4);
}
.meeting-title-inline.editable:hover {
  color: #fff;
  border-bottom-color: rgba(255, 255, 255, 0.8);
}
.meeting-title-inline.ended {
  opacity: 0.6;
}
.status-badge-ended {
  font-size: 10px;
  font-weight: 700;
  color: #fff;
  background: rgba(255, 255, 255, 0.2);
  border: 1px solid rgba(255, 255, 255, 0.3);
  padding: 2px 6px;
  border-radius: 99px;
  flex-shrink: 0;
}
.title-input {
  background: var(--white-15);
  border: 1px solid rgba(255, 255, 255, 0.5);
  border-radius: 4px;
  color: #fff;
  font-size: 12px;
  padding: 3px 8px;
  outline: none;
  min-width: 160px;
  max-width: 280px;
}
.title-input::placeholder {
  color: rgba(255, 255, 255, 0.5);
}

/* 구성원 아바타 */
.member-avatars-wrap {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-shrink: 0;
  margin-left: 2px;
  cursor: pointer;
  padding: 3px 6px;
  border-radius: 99px;
  transition: background 0.15s;
}
.member-avatars-wrap:hover {
  background: var(--white-12);
}
.member-avatars {
  display: flex;
  align-items: center;
}
.member-avatar {
  width: 26px;
  height: 26px;
  border-radius: 50%;
  background: var(--accent);
  border: 2px solid var(--primary);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  font-weight: 700;
  color: #fff;
  flex-shrink: 0;
  margin-left: -6px;
}
.member-avatar:first-child {
  margin-left: 0;
}
.member-count {
  height: 20px;
  padding: 0 6px;
  border-radius: 99px;
  background: rgba(255, 255, 255, 0.2);
  border: 1.5px solid rgba(255, 255, 255, 0.4);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  font-weight: 600;
  color: #fff;
  white-space: nowrap;
  margin-left: 4px;
  flex-shrink: 0;
}

.header-right {
  margin-left: auto;
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}
.theme-toggle-btn {
  color: #fff !important;
}
.theme-toggle-btn:hover {
  background: var(--white-12) !important;
  color: #fff !important;
}

/* 구성원 관리 팝업 */
.member-mgmt-popup {
  position: absolute;
  top: calc(var(--header-h) + 4px);
  left: 160px;
  width: 340px;
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-lg);
  z-index: 200;
  overflow: hidden;
}
.mgmt-header {
  padding: 12px 16px;
  border-bottom: 1px solid var(--border);
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.mgmt-search {
  padding: 10px 12px;
  border-bottom: 1px solid var(--border);
  position: relative;
}
.mgmt-input {
  width: 100%;
  padding: 6px 10px;
  border: 1px solid var(--border);
  border-radius: 6px;
  font-size: 12px;
  outline: none;
  box-sizing: border-box;
}
.mgmt-input:focus {
  border-color: var(--primary);
}
.search-results {
  position: absolute;
  top: 100%;
  left: 12px;
  right: 12px;
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 6px;
  box-shadow: var(--shadow-lg);
  z-index: 10;
  max-height: 160px;
  overflow-y: auto;
}
.search-result-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  cursor: pointer;
  font-size: 12px;
}
.search-result-item:hover {
  background: var(--surface);
}
.add-label {
  margin-left: auto;
  color: var(--primary);
  font-weight: 600;
  font-size: 12px;
}
.mgmt-list {
  max-height: 280px;
  overflow-y: auto;
  padding: 8px 0;
}
.mgmt-member {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 14px;
}
.mgmt-member:hover {
  background: var(--surface);
}
.mgmt-member-info {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
}
.mgmt-name {
  font-size: 12px;
  font-weight: 500;
}
.mgmt-emp {
  font-size: 12px;
  color: var(--text-muted);
}
.avatar-sm {
  width: 28px;
  height: 28px;
  border-radius: 50%;
  background: var(--accent);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  font-weight: 600;
  color: #fff;
  flex-shrink: 0;
}
.role-badge {
  font-size: 12px;
  font-weight: 600;
  padding: 2px 8px;
  border-radius: 99px;
  cursor: pointer;
  border: 1px solid;
}
.role-badge.admin {
  background: var(--accent-bg);
  color: var(--accent-strong);
  border-color: #bfdbfe;
}
.role-badge.member {
  background: var(--surface);
  color: var(--text-muted);
  border-color: var(--border);
}
.mgmt-del {
  color: var(--danger) !important;
  font-size: 12px !important;
}
.profile-wrap {
  position: relative;
}
.profile-btn {
  display: flex;
  align-items: center;
  gap: 8px;
  color: rgba(255, 255, 255, 0.9) !important;
  padding: 4px 8px;
  border-radius: 6px;
}
.profile-btn:hover {
  background: var(--white-12) !important;
  color: rgba(255, 255, 255, 0.9) !important;
}
.avatar {
  width: 26px;
  height: 26px;
  background: var(--accent);
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  font-weight: 600;
  color: #fff;
}
.avatar-lg {
  width: 36px;
  height: 36px;
  background: var(--accent);
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 16px;
  font-weight: 600;
  color: #fff;
  flex-shrink: 0;
}
.profile-dropdown {
  position: absolute;
  top: calc(100% + 8px);
  right: 0;
  width: 220px;
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-lg);
  z-index: 200;
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.profile-info {
  display: flex;
  align-items: center;
  gap: 10px;
}
.backdrop {
  position: fixed;
  inset: 0;
  z-index: 190;
}

/* 개인설정 모달 */
.ps-readonly-tag {
  font-size: 10px;
  font-weight: 500;
  padding: 1px 6px;
  border-radius: 99px;
  background: var(--surface-2);
  color: var(--dark-muted);
}
.ps-divider {
  font-size: 12px;
  font-weight: 700;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  padding: 4px 0 0;
  border-top: 1px solid var(--border);
}
.modal-fade-enter-from,
.modal-fade-leave-to {
  opacity: 0;
}
</style>
