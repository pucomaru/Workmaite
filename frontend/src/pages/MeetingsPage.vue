<script setup>
import { ref, computed, onMounted } from 'vue'
import { useMeetingsStore } from '../stores/meetings'
import { useThemeStore } from '../stores/theme'
import { useAuthStore } from '../stores/auth'
import api from '../api'
import MemberInvite from '../components/MemberInvite.vue'
import AppTable from '../components/AppTable.vue'
import AppTableSection from '../components/AppTableSection.vue'
import { useTableSort } from '../composables/useTableSort'
import { usePagination } from '../composables/usePagination'
import { toast } from '../composables/useToast'
import MeetingSettingsModal from '../components/MeetingSettingsModal.vue'

const mgColumns = [
  { label: '회의체명', sortKey: 'title' },
  { label: '역할', width: '100px', sortKey: '_role' },
  { label: '유형', width: '130px', sortKey: 'meeting_type' },
  { label: '간사', width: '120px', sortKey: '_adminName' },
  { label: '참여조직', width: '150px', sortKey: '_companyCount' },
  { label: '참여자', width: '100px', sortKey: '_memberCount' },
  { label: '', width: '170px', noResize: true },
]

const meetingsStore = useMeetingsStore()
const themeStore = useThemeStore()
const authStore = useAuthStore()
const nightMode = computed(() => themeStore.nightMode)

const search = ref('')
const statusTab = ref('active')
const expandedId = ref(null)
// 멤버 캐시는 스토어 단일 캐시 사용 — 페이지 로컬 사본 금지
const membersCache = computed(() => meetingsStore.membersByMeeting)
const loadingMembers = ref({})

// 테이블 표시·정렬·검색용 파생 필드 부여 (역할/간사/참여조직/참여자 컬럼).
// 검색이 파생 컬럼까지 커버하도록 필터보다 먼저 계산한다.
// (간사/참여조직/참여자는 membersCache가 로드된 회의체에 한해 채워짐 — 표시값과 동일)
const enrichedGroups = computed(() =>
  meetingsStore.meetings.map(g => {
    const members = membersCache.value[g.id] || []
    const admins = members.filter(mb => mb.role === 'admin')
    const companies = [
      ...new Set(members.map(mb => mb.user?.company || mb.company).filter(Boolean)),
    ]
    return {
      ...g,
      _role:
        meetingsStore.meetingRoles[g.id] === 'admin'
          ? '간사'
          : meetingsStore.meetingRoles[g.id]
            ? '참여자'
            : '',
      _adminName: admins.map(mb => mb.user?.name || mb.name).join(', ') || '',
      _companyCount: companies.length,
      _memberCount: members.length,
    }
  }),
)

const filteredGroups = computed(() => {
  const q = search.value.trim().toLowerCase()
  // 가시성 스코프는 백엔드 getMeetings가 이미 적용(SYSTEM_ADMIN=전체·COMPANY_ADMIN=자사·USER=멤버).
  // 프런트에서 my_role(멤버십)로 재필터하면 관리자가 비멤버 회의체를 못 본다 → 멤버십 막 제거.
  return enrichedGroups.value.filter(m => {
    const matchStatus =
      statusTab.value === 'active' ? !m.status || m.status === 'active' : m.status === 'ended'
    // 모든 컬럼 검색: 회의체명·역할·유형·간사·참여조직·참여자
    const matchSearch =
      !q ||
      [m.title, m._role, m.meeting_type, m._adminName, m._companyCount, m._memberCount].some(v =>
        (v ?? '').toString().toLowerCase().includes(q),
      )
    return matchStatus && matchSearch
  })
})

// ── 정렬·페이지네이션 (공통 컴포저블) ────────────────
const {
  sortKey: mgSortKey,
  sortDir: mgSortDir,
  handleSort: handleMgSort,
  sorted: sortedGroups,
} = useTableSort(filteredGroups)

const MG_PAGE_SIZE = 15
const {
  page: mgPage,
  paged: pagedGroups,
  fillerCount: mgFillerCount,
} = usePagination(sortedGroups, MG_PAGE_SIZE)

async function loadMembers(meetingId) {
  if (membersCache.value[meetingId]) return
  loadingMembers.value[meetingId] = true
  try {
    await meetingsStore.fetchMembersOnce(meetingId)
  } finally {
    loadingMembers.value[meetingId] = false
  }
}

// ── Create ────────────────────────────────────────────────────
const showCreate = ref(false)
const creating = ref(false)
const createForm = ref({
  title: '',
  purpose: '',
  start_date: '',
  end_date: '',
  guidelines: '',
  meeting_type: 'Weekly',
})
const createMembers = ref([]) // { userId, name, email, role }

function openCreate() {
  createForm.value = {
    title: '',
    purpose: '',
    start_date: '',
    end_date: '',
    guidelines: '',
    meeting_type: 'Weekly',
  }
  const me = authStore.user
  createMembers.value = me
    ? [{ userId: me.id, name: me.name, email: me.email || me.employee_id || '', role: 'admin' }]
    : []
  showCreate.value = true
}

async function submitCreate() {
  if (!createForm.value.title.trim()) return
  if (
    createForm.value.start_date &&
    createForm.value.end_date &&
    createForm.value.end_date < createForm.value.start_date
  ) {
    toast.error('종료일은 시작일 이후여야 합니다.')
    return
  }
  creating.value = true
  try {
    const meeting = await meetingsStore.createMeeting({
      title: createForm.value.title,
      description: createForm.value.purpose,
      start_date: createForm.value.start_date || null,
      end_date: createForm.value.end_date || null,
      guidelines: createForm.value.guidelines || null,
      meeting_type: createForm.value.meeting_type || null,
    })
    const myId = authStore.user?.id
    for (const mb of createMembers.value) {
      if (mb.userId === myId) continue // 생성 시 서버가 자동으로 admin 추가
      await api.post(`/api/v1/meetings/${meeting.id}/members`, { userId: mb.userId, role: mb.role })
    }
    await loadMembers(meeting.id)
    showCreate.value = false
  } catch (e) {
    toast.error(e.response?.data?.detail || '생성 실패')
  } finally {
    creating.value = false
  }
}

// ── End (종료 처리) ──────────────────────────────────────────
const endingId = ref(null)
const endTarget = ref(null)

function confirmEnd(m) {
  endTarget.value = m
}
function cancelEnd() {
  endTarget.value = null
}
async function executeEnd() {
  const m = endTarget.value
  if (!m) return
  endTarget.value = null
  endingId.value = m.id
  try {
    await meetingsStore.terminateMeeting(m.id)
  } catch (e) {
    toast.error(e.response?.data?.detail || '종료 처리 실패')
  } finally {
    endingId.value = null
  }
}

// ── Delete ────────────────────────────────────────────────────
const deletingId = ref(null)
const deleteTarget = ref(null)

function confirmDelete(m) {
  deleteTarget.value = m
}
function cancelDelete() {
  deleteTarget.value = null
}
async function executeDelete() {
  const m = deleteTarget.value
  if (!m) return
  deleteTarget.value = null
  deletingId.value = m.id
  try {
    await meetingsStore.deleteMeeting(m.id)
    if (expandedId.value === m.id) expandedId.value = null
    meetingsStore.invalidateMembers(m.id)
  } catch (e) {
    toast.error(e.response?.data?.detail || '삭제 실패')
  } finally {
    deletingId.value = null
  }
}

// ── Settings ──────────────────────────────────────────────────
const settingsModal = ref(null)

async function openSettings(m) {
  // PG 최신값 fetch (Spring Boot → PG 직접)
  let pgMeeting = null
  try {
    pgMeeting = (await api.get(`/api/v1/meetings/${m.id}`)).data
  } catch {}
  const src = pgMeeting || m

  let members = membersCache.value[m.id] ? [...membersCache.value[m.id]] : []
  if (!members.length) {
    try {
      const res = await api.get(`/api/v1/meetings/${m.id}/members`)
      membersCache.value[m.id] = res.data
      members = [...res.data]
    } catch {}
  }
  settingsModal.value = {
    meeting: m,
    form: {
      title: src.title || '',
      purpose: src.description || '',
      start_date: src.start_date ? String(src.start_date).slice(0, 10) : '',
      end_date: src.end_date ? String(src.end_date).slice(0, 10) : '',
      guidelines: src.guidelines || '',
      meeting_type: src.meeting_type || src.type || 'Weekly',
    },
    members: members.map(mb => ({
      id: mb.id,
      userId: mb.user?.id || mb.user_id,
      name: mb.user?.name || mb.userName || mb.name || '?',
      email: mb.user?.email || mb.email || '',
      department: mb.user?.department || mb.department || '',
      position: mb.user?.position || mb.position || '',
      role: mb.role || 'member',
    })),
    originalRoles: Object.fromEntries(members.map(mb => [mb.id, mb.role || 'member'])),
    removedIds: [],
  }
}

function closeSettings() {
  settingsModal.value = null
}

const savingSettings = ref(false)
async function saveSettings() {
  if (!settingsModal.value) return
  const { meeting, form, members, removedIds, originalRoles } = settingsModal.value
  if (
    form.start_date &&
    form.end_date &&
    form.end_date < form.start_date
  ) {
    toast.error('종료일은 시작일 이후여야 합니다.')
    return
  }
  savingSettings.value = true
  try {
    await api.patch(`/api/v1/meetings/${meeting.id}`, {
      title: form.title,
      description: form.purpose,
      start_date: form.start_date || null,
      end_date: form.end_date || null,
      guidelines: form.guidelines,
      meeting_type: form.meeting_type || null,
    })
    for (const memberId of removedIds) {
      await api.delete(`/api/v1/meetings/${meeting.id}/members/${memberId}`)
    }
    for (const mb of members.filter(m => m.id == null)) {
      await api.post(`/api/v1/meetings/${meeting.id}/members`, { userId: mb.userId, role: mb.role })
    }
    for (const mb of members.filter(m => m.id != null && m.role !== originalRoles?.[m.id])) {
      await api.patch(`/api/v1/meetings/${meeting.id}/members/${mb.id}`, { meeting_role: mb.role })
    }
    await meetingsStore.fetchMeetings()
    const res = await api.get(`/api/v1/meetings/${meeting.id}/members`)
    membersCache.value[meeting.id] = res.data
    settingsModal.value = null
  } catch (e) {
    const detail = e.response?.data?.detail
    toast.error(typeof detail === 'string' ? detail : detail ? JSON.stringify(detail) : '저장 실패')
  } finally {
    savingSettings.value = false
  }
}

// 시스템관리자는 간사가 아니어도 설정/종료/삭제 가능
function canManage(g) {
  return authStore.isStrategicTeam || meetingsStore.meetingRoles[g.id] === 'admin'
}
function getAdmins(gid) {
  return (membersCache.value[gid] || []).filter(mb => mb.role === 'admin')
}
function getCompanies(gid) {
  const companies = new Set()
  ;(membersCache.value[gid] || []).forEach(mb => {
    const o = mb.user?.company || mb.user?.department
    if (o) companies.add(o)
  })
  return [...companies]
}

// 한 번에 테이블을 렌더링
const initialLoading = ref(true)

onMounted(async () => {
  try {
    await meetingsStore.fetchMeetings()
    // Preload member info for table display (간사/참여조직/참여자 컬럼)
    await Promise.all(meetingsStore.meetings.map(m => loadMembers(m.id)))
  } catch {
    /* 실패해도 테이블은 표시 — 셀은 '-' 폴백 */
  } finally {
    initialLoading.value = false
  }
})
</script>

<template>
  <div class="mg-page page-full-height" :class="{ 'day-mode': !nightMode }">
    <div class="archive-header">
      <div class="header-title-wrap">
        <h1 class="archive-title">회의체 관리</h1>
      </div>
      <div class="search-wrap">
        <svg
          class="search-icon"
          width="14"
          height="14"
          fill="none"
          stroke="currentColor"
          stroke-width="2"
          viewBox="0 0 24 24"
        >
          <circle cx="11" cy="11" r="8" />
          <path d="M21 21l-4.35-4.35" />
        </svg>
        <input v-model="search" name="search" class="search-input" placeholder="회의체 검색..." />
      </div>
      <div class="app-tabs">
        <button
          class="app-tab"
          :class="{ active: statusTab === 'active' }"
          @click="statusTab = 'active'"
        >
          진행 중
        </button>
        <button
          class="app-tab"
          :class="{ active: statusTab === 'ended' }"
          @click="statusTab = 'ended'"
        >
          종료
        </button>
      </div>
      <div class="plus-wrap">
        <button class="create-btn" @click="openCreate">
          <svg
            width="13"
            height="13"
            fill="none"
            stroke="currentColor"
            stroke-width="2.5"
            viewBox="0 0 24 24"
          >
            <path d="M12 4v16m8-8H4" />
          </svg>
          회의체 생성
        </button>
      </div>
    </div>

    <!-- 목록 본문 (공통 레이아웃: lv-header + table-wrap) -->
    <AppTableSection
      v-model:page="mgPage"
      :total-items="sortedGroups.length"
      :page-size="MG_PAGE_SIZE"
      :dark="nightMode"
      :show-pagination="!initialLoading"
    >
      <template #header-right>
        <span class="lv-title">{{
          search
            ? `"${search}" 검색 결과`
            : statusTab === 'active'
              ? '진행 중 회의체'
              : '종료된 회의체'
        }}</span>
        <span class="lv-count">{{ sortedGroups.length }}건</span>
      </template>

      <div v-if="initialLoading" class="table-loading">
        <span class="spinner-border spinner-border-sm text-primary"></span>
        <span style="margin-left: 10px; color: var(--text-muted); font-size: 12px"
          >불러오는 중...</span
        >
      </div>
      <div v-else-if="!meetingsStore.meetings.length" class="mg-empty">
        <div class="empty-icon">🗂️</div>
        <p>아직 참여 중인 회의체가 없습니다.</p>
      </div>
      <div v-else-if="!filteredGroups.length" class="mg-empty">
        <div class="empty-icon">🔍</div>
        <p>
          {{
            search
              ? '검색 결과가 없습니다.'
              : statusTab === 'ended'
                ? '종료된 회의체가 없습니다.'
                : '진행 중인 회의체가 없습니다.'
          }}
        </p>
      </div>
      <template v-else>
        <AppTable
          fixed
          :columns="mgColumns"
          :dark="nightMode"
          :sortKey="mgSortKey"
          :sortDir="mgSortDir"
          @sort="handleMgSort"
        >
          <tr v-for="g in pagedGroups" :key="g.id" class="mg-row">
            <td>
              <div class="mg-row-title">{{ g.title }}</div>
            </td>
            <td>
              <span
                v-if="meetingsStore.meetingRoles[g.id]"
                class="mg-role-text"
                :class="meetingsStore.meetingRoles[g.id] === 'admin' ? 'role-admin' : 'role-member'"
              >
                {{ meetingsStore.meetingRoles[g.id] === 'admin' ? '간사' : '참여자' }}
              </span>
              <span v-else class="mg-row-nodates"></span>
            </td>
            <!-- 유형 -->
            <td>
              <span v-if="g.meeting_type" class="mg-type-text">{{ g.meeting_type }}</span>
              <span v-else class="mg-row-nodates"></span>
            </td>
            <!-- 간사 -->
            <td>
              <div v-if="membersCache[g.id]">
                <span v-if="getAdmins(g.id).length" class="mg-admin-name">{{
                  getAdmins(g.id)
                    .map(mb => mb.user?.name || mb.name)
                    .slice(0, 2)
                    .join(', ')
                }}</span>
                <span v-else class="mg-row-nodates"></span>
              </div>
              <span v-else class="mg-row-nodates"></span>
            </td>
            <!-- 참여조직 -->
            <td>
              <div v-if="membersCache[g.id]">
                <span v-if="getCompanies(g.id).length" class="mg-company-plain"
                  >{{ getCompanies(g.id).slice(0, 3).join(', ')
                  }}{{
                    getCompanies(g.id).length > 3 ? ` 외 ${getCompanies(g.id).length - 3}개` : ''
                  }}</span
                >
                <span v-else class="mg-row-nodates"></span>
              </div>
              <span v-else class="mg-row-nodates"></span>
            </td>
            <!-- 참여자 -->
            <td>
              <span v-if="membersCache[g.id]" class="mg-member-count-label"
                >{{ membersCache[g.id].length }}명</span
              >
              <span v-else class="mg-row-nodates"></span>
            </td>
            <td>
              <div class="action-btns">
                <button
                  v-if="canManage(g)"
                  class="mg-icon-btn settings"
                  @click.stop="openSettings(g)"
                >
                  <svg
                    width="14"
                    height="14"
                    fill="none"
                    stroke="currentColor"
                    stroke-width="2"
                    viewBox="0 0 24 24"
                  >
                    <circle cx="12" cy="12" r="3" />
                    <path
                      d="M19.4 15a1.65 1.65 0 00.33 1.82l.06.06a2 2 0 010 2.83 2 2 0 01-2.83 0l-.06-.06a1.65 1.65 0 00-1.82-.33 1.65 1.65 0 00-1 1.51V21a2 2 0 01-2 2 2 2 0 01-2-2v-.09A1.65 1.65 0 009 19.4a1.65 1.65 0 00-1.82.33l-.06.06a2 2 0 01-2.83 0 2 2 0 010-2.83l.06-.06A1.65 1.65 0 004.68 15a1.65 1.65 0 00-1.51-1H3a2 2 0 01-2-2 2 2 0 012-2h.09A1.65 1.65 0 004.6 9a1.65 1.65 0 00-.33-1.82l-.06-.06a2 2 0 010-2.83 2 2 0 012.83 0l.06.06A1.65 1.65 0 009 4.68a1.65 1.65 0 001-1.51V3a2 2 0 012-2 2 2 0 012 2v.09a1.65 1.65 0 001 1.51 1.65 1.65 0 001.82-.33l.06-.06a2 2 0 012.83 0 2 2 0 010 2.83l-.06.06A1.65 1.65 0 0019.4 9a1.65 1.65 0 001.51 1H21a2 2 0 012 2 2 2 0 01-2 2h-.09a1.65 1.65 0 00-1.51 1z"
                    />
                  </svg>
                </button>
                <!-- 진행중: 종료 처리 버튼 -->
                <button
                  v-if="canManage(g) && statusTab === 'active'"
                  class="mg-action-btn mg-btn-end"
                  @click.stop="confirmEnd(g)"
                  :disabled="endingId === g.id"
                >
                  <svg
                    width="12"
                    height="12"
                    fill="none"
                    stroke="currentColor"
                    stroke-width="2.5"
                    viewBox="0 0 24 24"
                  >
                    <polyline points="20 6 9 17 4 12" />
                  </svg>
                  {{ endingId === g.id ? '처리 중…' : '종료' }}
                </button>
                <!-- 삭제 버튼 (항상) -->
                <button
                  v-if="canManage(g)"
                  class="mg-action-btn mg-btn-delete"
                  @click.stop="confirmDelete(g)"
                  :disabled="deletingId === g.id"
                >
                  <svg
                    width="12"
                    height="12"
                    fill="none"
                    stroke="currentColor"
                    stroke-width="2"
                    viewBox="0 0 24 24"
                  >
                    <polyline points="3 6 5 6 21 6" />
                    <path d="M19 6l-1 14a2 2 0 01-2 2H8a2 2 0 01-2-2L5 6" />
                    <path d="M10 11v6M14 11v6" />
                    <path d="M9 6V4a1 1 0 011-1h4a1 1 0 011 1v2" />
                  </svg>
                  {{ deletingId === g.id ? '삭제 중…' : '삭제' }}
                </button>
              </div>
            </td>
          </tr>
        </AppTable>
      </template>
    </AppTableSection>

    <Teleport to="body">
      <!-- Create modal -->
      <div v-if="showCreate" class="app-modal-backdrop">
        <div class="app-modal app-modal-md" :class="{ dark: nightMode }">
          <div class="app-modal-header">
            <span class="app-modal-title">회의체 생성</span>
            <button class="app-modal-close" @click="showCreate = false">
              <svg
                width="14"
                height="14"
                fill="none"
                stroke="currentColor"
                stroke-width="2.5"
                viewBox="0 0 24 24"
              >
                <path d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
          <div class="app-modal-body">
            <div class="app-modal-field">
              <label for="create-meeting-title">회의체명 <span class="req">*</span></label>
              <input
                id="create-meeting-title"
                v-model="createForm.title"
                class="app-modal-input"
                placeholder="예: 전략기획위원회"
              />
            </div>
            <div class="app-modal-field">
              <label for="create-meeting-purpose">소개</label>
              <textarea
                id="create-meeting-purpose"
                v-model="createForm.purpose"
                class="app-modal-input"
                placeholder="이 회의체의 목적이나 소개..."
                rows="2"
              ></textarea>
            </div>
            <div class="app-modal-field">
              <label for="create-meeting-type">유형</label>
              <select
                id="create-meeting-type"
                v-model="createForm.meeting_type"
                class="app-modal-input"
              >
                <option value="Weekly">Weekly</option>
                <option value="Monthly">Monthly</option>
                <option value="Quarterly">Quarterly</option>
              </select>
            </div>
            <div class="app-modal-field-row">
              <div class="app-modal-field">
                <label for="create-meeting-start-date">시작일</label>
                <input
                  id="create-meeting-start-date"
                  type="date"
                  v-model="createForm.start_date"
                  class="app-modal-input"
                />
              </div>
              <div class="app-modal-field">
                <label for="create-meeting-end-date">종료일</label>
                <input
                  id="create-meeting-end-date"
                  type="date"
                  v-model="createForm.end_date"
                  class="app-modal-input"
                />
              </div>
            </div>
            <div class="app-modal-field">
              <label for="create-meeting-guidelines">운영 지침</label>
              <textarea
                id="create-meeting-guidelines"
                v-model="createForm.guidelines"
                class="app-modal-input"
                rows="3"
                placeholder="운영 지침, 규칙, 주의사항 등을 입력하세요...
예: 매주 월요일 10시, 의장 승인 필수, 안건 72시간 전 제출 등"
              ></textarea>
            </div>
            <MemberInvite
              v-model="createMembers"
              :lockedUserId="authStore.user?.id"
              :nightMode="nightMode"
            />
          </div>
          <div class="app-modal-footer">
            <button class="app-btn-cancel" @click="showCreate = false">취소</button>
            <button
              class="app-btn-primary"
              :disabled="!createForm.title.trim() || creating"
              @click="submitCreate"
            >
              {{ creating ? '생성 중...' : '생성' }}
            </button>
          </div>
        </div>
      </div>

      <MeetingSettingsModal
        :settings="settingsModal"
        :night-mode="nightMode"
        :saving="savingSettings"
        @close="closeSettings"
        @save="saveSettings"
      />
    </Teleport>

    <!-- 종료 확인 모달 -->
    <Teleport to="body">
      <div v-if="endTarget" class="app-modal-backdrop" @click.self="cancelEnd">
        <div class="app-modal delete-confirm-modal">
          <div class="app-modal-header">
            <span class="app-modal-title">회의체 종료</span>
            <button class="app-modal-close" @click="cancelEnd">
              <svg
                width="14"
                height="14"
                fill="none"
                stroke="currentColor"
                stroke-width="2"
                viewBox="0 0 24 24"
              >
                <path d="M18 6L6 18M6 6l12 12" />
              </svg>
            </button>
          </div>
          <div class="delete-confirm-body">
            <div class="delete-confirm-icon">
              <svg
                width="28"
                height="28"
                fill="none"
                stroke="#f59e0b"
                stroke-width="1.8"
                viewBox="0 0 24 24"
              >
                <circle cx="12" cy="12" r="10" />
                <path d="M12 8v4M12 16h.01" />
              </svg>
            </div>
            <p class="delete-confirm-msg">
              {{ endTarget.title }} 회의체를 종료합니다.<br />
              <span class="delete-confirm-sub"
                >종료된 회의체는 더 이상 회의를 진행할 수 없습니다.</span
              >
            </p>
          </div>
          <div class="app-modal-footer">
            <button class="app-btn-cancel" @click="cancelEnd">취소</button>
            <button class="app-btn-danger" @click="executeEnd">종료</button>
          </div>
        </div>
      </div>
    </Teleport>

    <!-- 삭제 확인 모달 -->
    <Teleport to="body">
      <div v-if="deleteTarget" class="app-modal-backdrop" @click.self="cancelDelete">
        <div class="app-modal delete-confirm-modal">
          <div class="app-modal-header">
            <span class="app-modal-title">회의체 삭제</span>
            <button class="app-modal-close" @click="cancelDelete">
              <svg
                width="14"
                height="14"
                fill="none"
                stroke="currentColor"
                stroke-width="2"
                viewBox="0 0 24 24"
              >
                <path d="M18 6L6 18M6 6l12 12" />
              </svg>
            </button>
          </div>
          <div class="delete-confirm-body">
            <div class="delete-confirm-icon">
              <svg
                width="28"
                height="28"
                fill="none"
                stroke="#ef4444"
                stroke-width="1.8"
                viewBox="0 0 24 24"
              >
                <circle cx="12" cy="12" r="10" />
                <path d="M12 8v4M12 16h.01" />
              </svg>
            </div>
            <p class="delete-confirm-msg">
              {{ deleteTarget.title }} 회의체를 삭제합니다.<br />
              <span class="delete-confirm-sub"
                >보고서, 아젠다, 회의록 등 관련 데이터가 모두 삭제되며<br />이 작업은 되돌릴 수
                없습니다.</span
              >
            </p>
          </div>
          <div class="app-modal-footer">
            <button class="app-btn-cancel" @click="cancelDelete">취소</button>
            <button class="app-btn-danger" @click="executeDelete">삭제</button>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<style scoped>
.mg-page {
  display: flex;
  flex-direction: column;
}

/* 목록 레이아웃(lv-*, table-wrap, table-loading)은 style.css 전역 단일 정의 + AppTableSection 사용
   (lv-header height:36px 포함 — 전역으로 이동) */

/* 테이블 행 */
.mg-row {
  border-bottom: 1px solid var(--white-06);
  cursor: default;
  background: transparent;
}
.mg-row td:last-child {
  border-bottom: 1px solid var(--white-06);
}
.mg-row:hover {
  background: var(--white-04);
}
.mg-row:hover td:last-child {
  background: var(--white-04);
}
.mg-row-title {
  font-size: 12px;
  font-weight: 600;
  color: var(--dark-text);
}
.day-mode .mg-row {
  border-bottom-color: var(--surface-2);
  background: #fff;
}
.day-mode .mg-row td:last-child {
  border-bottom-color: var(--surface-2);
}
.day-mode .mg-row:hover {
  background: var(--surface);
}
.day-mode .mg-row:hover td:last-child {
  background: var(--surface);
}
.day-mode .mg-row-title {
  color: var(--dark-card);
}
.mg-row-nodates {
  color: var(--text-muted);
}
.day-mode .mg-row-nodates {
  color: var(--dark-text-2);
}
.mg-type-text {
  font-size: 12px;
  color: var(--text-muted);
}
.mg-admin-name {
  font-size: 12px;
  color: var(--text-muted);
}
.mg-member-count-label {
  font-size: 12px;
  color: var(--text-muted);
}
.mg-company-plain {
  font-size: 12px;
  color: var(--text-muted);
}

/* 상태 dot */
.mg-status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}
.mg-status-dot.active {
  background: #22c55e;
}
.mg-status-dot.ended {
  background: var(--text-muted);
}

/* 아이콘 버튼 (설정) */
.action-btns {
  display: flex;
  gap: 6px;
  align-items: center;
}
.mg-icon-btn {
  width: 28px;
  height: 28px;
  border-radius: 7px;
  border: 1px solid var(--white-10);
  background: var(--white-05);
  color: var(--text-muted);
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
}
.mg-icon-btn.settings:hover {
  border-color: rgba(96, 165, 250, 0.5);
  color: var(--accent-soft);
  background: rgba(96, 165, 250, 0.1);
}
.mg-icon-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}
.day-mode .mg-icon-btn {
  border-color: var(--border);
  background: #fff;
  color: var(--text-muted);
}

/* 텍스트 액션 버튼 (종료 / 삭제) — 설정 버튼과 동일 베이스 */
.mg-action-btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  height: 28px;
  padding: 0 9px;
  border-radius: 7px;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  border: 1px solid var(--white-10);
  background: var(--white-05);
  color: var(--text-muted);
  white-space: nowrap;
}
.mg-action-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}
.mg-btn-end:hover:not(:disabled) {
  border-color: rgba(34, 197, 94, 0.4);
  color: #4ade80;
  background: rgba(34, 197, 94, 0.08);
}
.mg-btn-delete:hover:not(:disabled) {
  border-color: rgba(239, 68, 68, 0.4);
  color: var(--danger-soft);
  background: rgba(239, 68, 68, 0.08);
}
.day-mode .mg-action-btn {
  border-color: var(--border);
  background: #fff;
  color: var(--text-muted);
}
.day-mode .mg-btn-end:hover:not(:disabled) {
  border-color: #bbf7d0;
  color: #16a34a;
  background: #f0fdf4;
}
.day-mode .mg-btn-delete:hover:not(:disabled) {
  border-color: #fecaca;
  color: #dc2626;
  background: #fef2f2;
}

/* 삭제 확인 모달 */
.delete-confirm-modal {
  max-width: 380px;
  min-height: auto;
  resize: none;
}
.delete-confirm-body {
  display: flex;
  align-items: flex-start;
  gap: 14px;
  padding: 20px 24px;
}
.delete-confirm-icon {
  flex-shrink: 0;
  margin-top: 2px;
}
.delete-confirm-msg {
  font-size: 12px;
  color: #111827;
  line-height: 1.6;
  margin: 0;
}

html.night-mode .delete-confirm-msg {
  color: var(--dark-text) !important;
}

.delete-confirm-sub {
  font-size: 11.5px;
  color: #6b7280;
}

.app-btn-danger {
  padding: 8px 16px;
  border-radius: 8px;
  border: 1px solid #fca5a5;
  background: transparent;
  color: var(--danger);
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
}
html.day-mode-global .app-btn-danger {
  background: #fff !important;
}

html.day-mode-global .app-btn-danger:hover {
  background: #fef2f2 !important;
}

.app-btn-danger:hover {
  background: #f7c3c353;
  opacity: 0.85;
}
.app-btn-danger:disabled {
  opacity: 0.85;
  cursor: not-allowed;
}
/* 역할 텍스트 */
.mg-role-text {
  font-size: 12px;
  color: var(--text-muted);
}

.day-mode .mg-role-text {
  color: var(--text-muted);
}
.day-mode .mg-type-text,
.day-mode .mg-admin-name,
.day-mode .mg-member-count-label,
.day-mode .mg-company-plain {
  color: var(--text-muted);
}

/* 빈 상태 */
.mg-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  flex: 1;
  color: var(--text-muted);
  gap: 8px;
  padding: 60px 0;
}
.mg-empty p {
  margin: 0;
  font-size: 14px;
}

.req {
  color: var(--danger);
}
</style>
