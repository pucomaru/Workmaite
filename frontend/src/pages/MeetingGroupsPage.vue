<script setup>
import { ref, computed, onMounted } from 'vue'
import { useMeetingsStore } from '../stores/meetings'
import { useThemeStore } from '../stores/theme'
import api, { apiAI } from '../api'
import MemberInvite from '../components/MemberInvite.vue'
import AppTable from '../components/AppTable.vue'

const mgColumns = [
  { label: '', width: '28px' },
  { label: '회의체명', sortKey: 'title' },
  { label: '역할', width: '80px', sortKey: '_role' },
  { label: '유형', width: '100px', sortKey: 'meeting_type' },
  { label: '간사', width: '160px', sortKey: '_adminName' },
  { label: '참여조직', width: '180px', sortKey: '_orgCount' },
  { label: '참여자', width: '150px', sortKey: '_memberCount' },
  { label: '', width: '72px', noResize: true }
]

const meetingsStore = useMeetingsStore()
const themeStore = useThemeStore()
const nightMode = computed(() => themeStore.nightMode)

const search = ref('')
const statusTab = ref('active')
const expandedId = ref(null)
const membersCache = ref({})
const loadingMembers = ref({})

const filteredGroups = computed(() => {
  const q = search.value.trim().toLowerCase()
  return meetingsStore.meetings.filter(m => {
    const matchRole = meetingsStore.meetingRoles[m.id] != null
    const matchStatus = statusTab.value === 'active'
      ? (!m.status || m.status === 'active')
      : m.status === 'ended'
    const matchSearch = !q || (m.title || '').toLowerCase().includes(q)
    return matchRole && matchStatus && matchSearch
  })
})

const mgSortKey = ref(null)
const mgSortDir = ref(null)
function handleMgSort({ key, dir }) { mgSortKey.value = key; mgSortDir.value = dir }
const sortedGroups = computed(() => {
  const enriched = filteredGroups.value.map(g => {
    const members = membersCache.value[g.id] || []
    const admins = members.filter(mb => mb.role === 'admin')
    const orgs = [...new Set(members.map(mb => mb.user?.organization || mb.organization).filter(Boolean))]
    return {
      ...g,
      _role: meetingsStore.meetingRoles[g.id] === 'admin' ? '간사' : '참여자',
      _adminName: admins.map(mb => mb.user?.name || mb.name).join(', ') || '',
      _orgCount: orgs.length,
      _memberCount: members.length,
    }
  })
  if (!mgSortKey.value || !mgSortDir.value) return enriched
  const d = mgSortDir.value === 'asc' ? 1 : -1
  return [...enriched].sort((a, b) => {
    const av = (a[mgSortKey.value] ?? '').toString().toLowerCase()
    const bv = (b[mgSortKey.value] ?? '').toString().toLowerCase()
    if (!isNaN(Number(av)) && !isNaN(Number(bv))) return (Number(av) - Number(bv)) * d
    return av < bv ? -d : av > bv ? d : 0
  })
})

const activeCount = computed(() =>
  meetingsStore.meetings.filter(m => meetingsStore.meetingRoles[m.id] != null && (!m.status || m.status === 'active')).length)
const endedCount = computed(() =>
  meetingsStore.meetings.filter(m => meetingsStore.meetingRoles[m.id] != null && m.status === 'ended').length)

async function loadMembers(meetingId) {
  if (membersCache.value[meetingId]) return
  loadingMembers.value[meetingId] = true
  try {
    const res = await api.get(`/api/v1/meetings/${meetingId}/members`)
    membersCache.value[meetingId] = res.data
  } catch { membersCache.value[meetingId] = [] }
  finally { loadingMembers.value[meetingId] = false }
}

function toggleExpand(id) {
  if (expandedId.value === id) { expandedId.value = null; return }
  expandedId.value = id
  loadMembers(id)
}

// ── Create ────────────────────────────────────────────────────
const showCreate = ref(false)
const creating = ref(false)
const createForm = ref({ title: '', purpose: '', start_date: '', end_date: '', guidelines: '', meeting_type: 'Weekly' })
const createMembers = ref([])  // { userId, name, email, role }

function openCreate() {
  createForm.value = { title: '', purpose: '', start_date: '', end_date: '', guidelines: '', meeting_type: 'Weekly' }
  createMembers.value = []
  showCreate.value = true
}

async function submitCreate() {
  if (!createForm.value.title.trim()) return
  creating.value = true
  try {
    const meeting = await meetingsStore.createMeeting({
      title: createForm.value.title,
      purpose: createForm.value.purpose,
      start_date: createForm.value.start_date || null,
      end_date: createForm.value.end_date || null,
      guidelines: createForm.value.guidelines || null,
      meeting_type: createForm.value.meeting_type || null,
    })
    for (const mb of createMembers.value) {
      await apiAI.post(`/api/v1/meetings/${meeting.id}/members`, { userId: mb.userId, role: mb.role })
    }
    showCreate.value = false
  } catch (e) { alert(e.response?.data?.detail || '생성 실패') }
  finally { creating.value = false }
}

// ── End (완료 처리) ──────────────────────────────────────────
const endingId = ref(null)
async function endMeeting(m) {
  if (!confirm(`"${m.title}" 회의체를 완료 상태로 변경하시겠습니까?`)) return
  endingId.value = m.id
  try {
    await meetingsStore.terminateMeeting(m.id)
  } catch (e) { alert(e.response?.data?.detail || '완료 처리 실패') }
  finally { endingId.value = null }
}

// ── Delete ────────────────────────────────────────────────────
const deletingId = ref(null)
async function deleteMeeting(m) {
  if (!confirm(`"${m.title}" 회의체를 삭제하시겠습니까?\n이 작업은 되돌릴 수 없습니다.`)) return
  deletingId.value = m.id
  try {
    await meetingsStore.deleteMeeting(m.id)
    if (expandedId.value === m.id) expandedId.value = null
    delete membersCache.value[m.id]
  } catch (e) { alert(e.response?.data?.detail || '삭제 실패') }
  finally { deletingId.value = null }
}

// ── Settings ──────────────────────────────────────────────────
const settingsModal = ref(null)
const settingsSearchQ = ref('')
const settingsSearchResults = ref([])
const settingsSearchLoading = ref(false)
let settingsSearchTimer = null

async function openSettings(m) {
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
    form: { title: m.title, purpose: m.purpose || '', start_date: m.start_date ? m.start_date.slice(0,10) : '', end_date: m.end_date ? m.end_date.slice(0,10) : '', guidelines: m.guidelines || '', meeting_type: m.meeting_type || 'Weekly' },
    members: members.map(mb => ({
      id: mb.id,
      userId: mb.user?.id || mb.user_id,
      name: mb.user?.name || mb.userName || mb.name || '?',
      email: mb.user?.email || mb.email || '',
      role: mb.role || 'member',
    })),
    removedIds: [],
  }
  settingsSearchQ.value = ''
  settingsSearchResults.value = []
}

function closeSettings() { settingsModal.value = null }

function watchSettingsSearch(q) {
  settingsSearchQ.value = q
  clearTimeout(settingsSearchTimer)
  if (!q.trim()) { settingsSearchResults.value = []; return }
  settingsSearchTimer = setTimeout(async () => {
    settingsSearchLoading.value = true
    try {
      const res = await api.get('/api/v1/users/search', { params: { q } })
      settingsSearchResults.value = res.data
    } catch { settingsSearchResults.value = [] }
    finally { settingsSearchLoading.value = false }
  }, 300)
}

function addMemberToSettings(user) {
  if (!settingsModal.value) return
  if (settingsModal.value.members.find(m => m.userId === user.id)) return
  settingsModal.value.members.push({ id: null, userId: user.id, name: user.name || user.email, email: user.email, role: 'member' })
  settingsSearchQ.value = ''
  settingsSearchResults.value = []
}

function removeMemberFromSettings(idx) {
  const m = settingsModal.value.members[idx]
  if (m.id) settingsModal.value.removedIds.push(m.id)
  settingsModal.value.members.splice(idx, 1)
}

const savingSettings = ref(false)
async function saveSettings() {
  if (!settingsModal.value) return
  savingSettings.value = true
  const { meeting, form, members, removedIds } = settingsModal.value
  try {
    await apiAI.patch(`/api/v1/meetings/${meeting.id}`, { title: form.title, purpose: form.purpose, start_date: form.start_date || null, end_date: form.end_date || null, guidelines: form.guidelines, meeting_type: form.meeting_type || null })
    for (const memberId of removedIds) {
      await apiAI.delete(`/api/v1/meetings/${meeting.id}/members/${memberId}`)
    }
    for (const mb of members.filter(m => m.id === null)) {
      await apiAI.post(`/api/v1/meetings/${meeting.id}/members`, { userId: mb.userId, role: mb.role })
    }
    await meetingsStore.fetchMeetings()
    const res = await api.get(`/api/v1/meetings/${meeting.id}/members`)
    membersCache.value[meeting.id] = res.data
    settingsModal.value = null
  } catch (e) { alert(e.response?.data?.detail || '저장 실패') }
  finally { savingSettings.value = false }
}

const ROLE_MAP = { admin: '간사', member: '참여자' }
function roleLabel(r) { return ROLE_MAP[r] || r || '참여자' }
function canManage(g) { return meetingsStore.meetingRoles[g.id] === 'admin' }
function fmtDate(s) {
  if (!s) return ''
  const d = new Date(s)
  return isNaN(d) ? s : `${d.getFullYear()}.${String(d.getMonth()+1).padStart(2,'0')}.${String(d.getDate()).padStart(2,'0')}`
}
function initials(name) { return (name || '?')[0] }
const AVATAR_COLORS = ['#6366f1','#3b82f6','#10b981','#f59e0b','#ef4444','#8b5cf6','#ec4899']
function avatarColor(name) { let h=0; for(const c of (name||'')) h=(h*31+c.charCodeAt(0))%AVATAR_COLORS.length; return AVATAR_COLORS[h] }
function getAdmins(gid) { return (membersCache.value[gid] || []).filter(mb => mb.role === 'admin') }
function getOrgs(gid) { const orgs = new Set(); (membersCache.value[gid] || []).forEach(mb => { const o = mb.user?.organization || mb.user?.department; if (o) orgs.add(o) }); return [...orgs] }
function getPresenterCount(gid) { return (membersCache.value[gid] || []).filter(mb => mb.role !== 'admin').length }

onMounted(async () => {
  await meetingsStore.fetchMeetings()
  // Preload member counts for table display
  meetingsStore.meetings.forEach(m => loadMembers(m.id))
})
</script>

<template>
  <div class="mg-page page-full-height" :class="{ 'day-mode': !nightMode }">

    <div class="archive-header">
      <div class="header-title-wrap">
        <h1 class="archive-title">회의체 관리</h1>
      </div>
      <div class="search-wrap">
        <svg class="search-icon" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><circle cx="11" cy="11" r="8"/><path d="M21 21l-4.35-4.35"/></svg>
        <input v-model="search" class="search-input" placeholder="회의체 검색..." />
      </div>
      <div class="app-tabs">
        <button class="app-tab" :class="{ active: statusTab==='active' }" @click="statusTab='active'">
          진행 중 <span class="app-tab-badge">{{ activeCount }}</span>
        </button>
        <button class="app-tab" :class="{ active: statusTab==='ended' }" @click="statusTab='ended'">
          완료 <span class="app-tab-badge">{{ endedCount }}</span>
        </button>
      </div>
      <div class="plus-wrap">
        <button class="create-meeting-btn" @click="openCreate">
          <svg width="13" height="13" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24"><path d="M12 4v16m8-8H4"/></svg>
          회의체 생성
        </button>
      </div>
    </div>

    <div class="mg-body">
      <div v-if="!meetingsStore.meetings.length" class="mg-empty">
        <div class="empty-icon">🗂️</div>
        <p>아직 참여 중인 회의체가 없습니다.</p>
      </div>
      <div v-else-if="!filteredGroups.length" class="mg-empty">
        <div class="empty-icon">🔍</div>
        <p>{{ search ? '검색 결과가 없습니다.' : statusTab==='ended' ? '완료된 회의체가 없습니다.' : '진행 중인 회의체가 없습니다.' }}</p>
      </div>
      <AppTable v-else :columns="mgColumns" :dark="nightMode" :sortKey="mgSortKey" :sortDir="mgSortDir" @sort="handleMgSort">
            <tr v-for="g in sortedGroups" :key="g.id" class="mg-row">
              <td><div class="mg-status-dot" :class="g.status==='ended' ? 'ended' : 'active'"></div></td>
              <td>
                <div class="mg-row-title">{{ g.title }}</div>
              </td>
              <td>
                <span class="mg-role-badge" :class="meetingsStore.meetingRoles[g.id]==='admin' ? 'role-admin' : 'role-member'">
                  {{ meetingsStore.meetingRoles[g.id] === 'admin' ? '간사' : '참여자' }}
                </span>
              </td>
              <!-- 유형 -->
              <td>
                <span v-if="g.meeting_type" class="mg-type-text">{{ g.meeting_type }}</span>
                <span v-else class="mg-row-nodates">-</span>
              </td>
              <!-- 간사 -->
              <td>
                <div v-if="membersCache[g.id]">
                  <span v-if="getAdmins(g.id).length" class="mg-admin-name">{{ getAdmins(g.id).map(mb => mb.user?.name || mb.name).slice(0,2).join(', ') }}</span>
                  <span v-else class="mg-row-nodates">-</span>
                </div>
                <span v-else class="mg-row-nodates">-</span>
              </td>
              <!-- 참여조직 -->
              <td>
                <div v-if="membersCache[g.id]">
                  <div v-if="getOrgs(g.id).length" class="mg-org-tags">
                    <span v-for="org in getOrgs(g.id).slice(0,2)" :key="org" class="mg-org-tag">{{ org }}</span>
                    <span v-if="getOrgs(g.id).length > 2" class="mg-member-more">+{{ getOrgs(g.id).length - 2 }}</span>
                  </div>
                  <span v-else class="mg-row-nodates">-</span>
                </div>
                <span v-else class="mg-row-nodates">-</span>
              </td>
              <!-- 참여자 -->
              <td>
                <span v-if="membersCache[g.id]" class="mg-member-count-label">{{ membersCache[g.id].length }}명</span>
                <span v-else class="mg-row-nodates">-</span>
              </td>
              <td>
                <div class="action-btns">
                  <button v-if="canManage(g)" class="mg-icon-btn settings" @click.stop="openSettings(g)" title="설정">
                    <svg width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 00.33 1.82l.06.06a2 2 0 010 2.83 2 2 0 01-2.83 0l-.06-.06a1.65 1.65 0 00-1.82-.33 1.65 1.65 0 00-1 1.51V21a2 2 0 01-2 2 2 2 0 01-2-2v-.09A1.65 1.65 0 009 19.4a1.65 1.65 0 00-1.82.33l-.06.06a2 2 0 01-2.83 0 2 2 0 010-2.83l.06-.06A1.65 1.65 0 004.68 15a1.65 1.65 0 00-1.51-1H3a2 2 0 01-2-2 2 2 0 012-2h.09A1.65 1.65 0 004.6 9a1.65 1.65 0 00-.33-1.82l-.06-.06a2 2 0 010-2.83 2 2 0 012.83 0l.06.06A1.65 1.65 0 009 4.68a1.65 1.65 0 001-1.51V3a2 2 0 012-2 2 2 0 012 2v.09a1.65 1.65 0 001 1.51 1.65 1.65 0 001.82-.33l.06-.06a2 2 0 012.83 0 2 2 0 010 2.83l-.06.06A1.65 1.65 0 0019.4 9a1.65 1.65 0 001.51 1H21a2 2 0 012 2 2 2 0 01-2 2h-.09a1.65 1.65 0 00-1.51 1z"/></svg>
                  </button>
                  <!-- 진행중: 완료 처리 버튼 -->
                  <button v-if="canManage(g) && statusTab==='active'" class="mg-icon-btn end" @click.stop="endMeeting(g)" :disabled="endingId===g.id" title="완료 처리">
                    <svg width="12" height="12" fill="currentColor" viewBox="0 0 24 24"><rect x="4" y="4" width="16" height="16" rx="2"/></svg>
                  </button>
                  <!-- 완료: 삭제 버튼 -->
                  <button v-if="canManage(g) && statusTab==='ended'" class="mg-icon-btn delete" @click.stop="deleteMeeting(g)" :disabled="deletingId===g.id" title="삭제">
                    <svg width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14a2 2 0 01-2 2H8a2 2 0 01-2-2L5 6"/><path d="M10 11v6M14 11v6"/><path d="M9 6V4a1 1 0 011-1h4a1 1 0 011 1v2"/></svg>
                  </button>
                </div>
              </td>
            </tr>
      </AppTable>
    </div>

    <Teleport to="body">
      <!-- Create modal -->
      <div v-if="showCreate" class="app-modal-backdrop" @click.self="showCreate=false">
        <div class="app-modal app-modal-md" :class="{ dark: nightMode }">
          <div class="app-modal-header">
            <span class="app-modal-title">회의체 생성</span>
            <button class="app-modal-close" @click="showCreate=false">
              <svg width="14" height="14" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24"><path d="M6 18L18 6M6 6l12 12"/></svg>
            </button>
          </div>
          <div class="app-modal-body">
            <div class="app-modal-field">
              <label>회의체 이름 <span class="req">*</span></label>
              <input v-model="createForm.title" class="app-modal-input" placeholder="예: 전략기획위원회" />
            </div>
            <div class="app-modal-field">
              <label>소개</label>
              <textarea v-model="createForm.purpose" class="app-modal-input" placeholder="이 회의체의 목적이나 소개..." rows="2"></textarea>
            </div>
            <div class="app-modal-field">
              <label>유형</label>
              <select v-model="createForm.meeting_type" class="app-modal-input">
                <option value="Weekly">Weekly</option>
                <option value="Monthly">Monthly</option>
                <option value="Quarterly">Quarterly</option>
              </select>
            </div>
            <div class="app-modal-field-row">
              <div class="app-modal-field">
                <label>시작일</label>
                <input type="date" v-model="createForm.start_date" class="app-modal-input" />
              </div>
              <div class="app-modal-field">
                <label>종료일</label>
                <input type="date" v-model="createForm.end_date" class="app-modal-input" />
              </div>
            </div>
            <div class="app-modal-field">
              <label>운영 지침</label>
              <textarea v-model="createForm.guidelines" class="app-modal-input" rows="3" placeholder="운영 지침, 규칙, 주의사항 등을 입력하세요...
예: 매주 월요일 10시, 의장 승인 필수, 안건 72시간 전 제출 등"></textarea>
            </div>
            <div class="app-modal-field">
              <label>멤버 초대</label>
              <MemberInvite v-model="createMembers" />
            </div>
          </div>
          <div class="app-modal-footer">
            <button class="app-btn-cancel" @click="showCreate=false">취소</button>
            <button class="app-btn-primary" :disabled="!createForm.title.trim() || creating" @click="submitCreate">{{ creating ? '생성 중...' : '생성' }}</button>
          </div>
        </div>
      </div>

      <!-- Settings modal -->
      <div v-if="settingsModal" class="app-modal-backdrop" @click.self="closeSettings">
        <div class="app-modal app-modal-lg" :class="{ dark: nightMode }">
          <div class="app-modal-header">
            <span class="app-modal-title">회의체 설정</span>
            <button class="app-modal-close" @click="closeSettings">
              <svg width="14" height="14" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24"><path d="M6 18L18 6M6 6l12 12"/></svg>
            </button>
          </div>
          <div class="app-modal-body settings-body">
            <div class="settings-section">
              <div class="settings-section-title">기본 정보</div>
              <div class="app-modal-field">
                <label>회의체 이름 <span class="req">*</span></label>
                <input v-model="settingsModal.form.title" class="app-modal-input" />
              </div>
              <div class="app-modal-field">
                <label>소개</label>
                <textarea v-model="settingsModal.form.purpose" class="app-modal-input" rows="2" placeholder="이 회의체의 목적이나 소개..."></textarea>
              </div>
              <div class="app-modal-field">
                <label>유형</label>
                <select v-model="settingsModal.form.meeting_type" class="app-modal-input">
                  <option value="Weekly">Weekly</option>
                  <option value="Monthly">Monthly</option>
                  <option value="Quarterly">Quarterly</option>
                </select>
              </div>
              <div class="app-modal-field-row">
                <div class="app-modal-field">
                  <label>시작일</label>
                  <input type="date" v-model="settingsModal.form.start_date" class="app-modal-input" />
                </div>
                <div class="app-modal-field">
                  <label>종료일</label>
                  <input type="date" v-model="settingsModal.form.end_date" class="app-modal-input" />
                </div>
              </div>
              <div class="app-modal-field">
                <label>회의체 지침</label>
                <textarea v-model="settingsModal.form.guidelines" class="app-modal-input" rows="4" placeholder="운영 지침, 규칙, 주의사항 등을 입력하세요...\n예: 매주 월요일 10시, 의장 승인 필수, 안건 72시간 전 제출 등"></textarea>
              </div>
            </div>
            <div class="settings-section">
              <div class="settings-section-title">
                참여자 <span class="member-cnt-badge">{{ settingsModal.members.length }}명</span>
              </div>
              <div class="member-search-wrap">
                <svg width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><circle cx="11" cy="11" r="8"/><path d="M21 21l-4.35-4.35"/></svg>
                <input :value="settingsSearchQ" @input="watchSettingsSearch($event.target.value)" class="member-search-input" placeholder="이름 또는 이메일로 검색 후 추가..." />
                <span v-if="settingsSearchLoading" class="search-spinner">↻</span>
              </div>
              <div v-if="settingsSearchResults.length" class="member-search-results">
                <div v-for="u in settingsSearchResults" :key="u.id" class="member-search-item" @click="addMemberToSettings(u)">
                  <div class="ms-avatar" :style="{ background: avatarColor(u.name) }">{{ initials(u.name || u.email) }}</div>
                  <div class="ms-info">
                    <span class="ms-name">{{ u.name || '이름없음' }}</span>
                    <span class="ms-email">{{ u.email }}</span>
                  </div>
                  <span class="ms-add-hint">+ 추가</span>
                </div>
              </div>
              <div class="settings-member-list">
                <div v-if="!settingsModal.members.length" class="settings-empty-members">참여자가 없습니다.</div>
                <div v-for="(mb, idx) in settingsModal.members" :key="mb.userId" class="settings-member-row">
                  <div class="sm-avatar" :style="{ background: avatarColor(mb.name) }">{{ initials(mb.name) }}</div>
                  <div class="sm-info">
                    <span class="sm-name">{{ mb.name }}</span>
                    <span class="sm-email">{{ mb.email }}</span>
                  </div>
                  <select v-model="mb.role" class="app-select">
                    <option v-for="(label, val) in ROLE_MAP" :key="val" :value="val">{{ label }}</option>
                  </select>
                  <button class="sm-remove" @click="removeMemberFromSettings(idx)" title="제거">
                    <svg width="12" height="12" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24"><path d="M18 6L6 18M6 6l12 12"/></svg>
                  </button>
                </div>
              </div>
            </div>
          </div>
          <div class="app-modal-footer">
            <button class="app-btn-cancel" @click="closeSettings">취소</button>
            <button class="app-btn-primary" :disabled="!settingsModal.form.title.trim() || savingSettings" @click="saveSettings">{{ savingSettings ? '저장 중...' : '저장' }}</button>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<style scoped>
.mg-page { display:flex;flex-direction:column;height:100%; }

.archive-header { display:flex;align-items:center;gap:12px;padding:10px 16px;background:#0f172a;border-bottom:1px solid rgba(255,255,255,.08);flex-shrink:0;flex-wrap:wrap; }
.header-title-wrap { flex-shrink:0; }
.archive-title { font-size:16px;font-weight:700;color:#f1f5f9;margin:0; }
.search-wrap { position:relative;flex:1;min-width:160px;max-width:320px; }
.search-icon { position:absolute;left:9px;top:50%;transform:translateY(-50%);color:#475569;pointer-events:none; }
.search-input { width:100%;background:rgba(255,255,255,.06);border:1px solid rgba(255,255,255,.1);border-radius:8px;padding:7px 28px;font-size:12px;color:#e2e8f0;outline:none;box-sizing:border-box; }
.search-input::placeholder { color:#334155; }
.search-input:focus { border-color:rgba(96,165,250,.5); }
.plus-wrap { flex-shrink:0;margin-left:auto; }
.create-meeting-btn { display:flex;align-items:center;gap:6px;height:34px;padding:0 14px;border-radius:8px;background:#3b82f6;border:none;color:#fff;font-size:13px;font-weight:600;cursor:pointer;transition:opacity .15s; }
.create-meeting-btn:hover { opacity:.85; }

.day-mode .archive-header { background:#eef2ff;border-bottom-color:#e2e8f0; }
.day-mode .archive-title { color:#1e293b; }
.day-mode .search-input { background:rgba(255,255,255,.6);border-color:#e2e8f0;color:#1e293b; }
.day-mode .search-input::placeholder { color:#94a3b8; }
.day-mode .search-icon { color:#94a3b8; }
.mg-body { flex:1;overflow-y:auto;padding:16px 20px;display:flex;flex-direction:column;gap:8px; }
.mg-row { border-bottom:1px solid rgba(255,255,255,.06);transition:background .1s;cursor:default;background:transparent; }
.mg-row:hover { background:rgba(255,255,255,.04); }
.mg-row-title { font-size:13px;font-weight:600;color:#e2e8f0; }
.day-mode .mg-row { border-bottom-color:#f1f5f9;background:#fff; }
.day-mode .mg-row:hover { background:#f8fafc; }
.day-mode .mg-row-title { color:#1e293b; }
.mg-row-desc { font-size:11px;color:#94a3b8;margin-top:2px;max-width:320px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap; }
.mg-row-members { display:flex;align-items:center;gap:3px; }
.mg-mini-avatar { width:22px;height:22px;border-radius:50%;color:#fff;font-size:10px;font-weight:700;display:flex;align-items:center;justify-content:center;flex-shrink:0;border:1.5px solid #fff; }
.mg-member-more { font-size:11px;color:#94a3b8;margin-left:2px; }
.mg-admin-name { font-size:12px;color:#475569;margin-left:4px; }
.mg-member-count-label { font-size:12px;color:#64748b;margin-left:4px; }
.mg-org-tags { display:flex;flex-wrap:wrap;gap:4px;align-items:center; }
.mg-org-tag { font-size:11px;font-weight:500;padding:2px 7px;border-radius:99px;background:#f1f5f9;color:#475569;border:1px solid #e2e8f0;white-space:nowrap; }
.mg-row-meta { display:flex;align-items:center;flex-wrap:wrap;margin-top:2px; }
.mg-type-text { font-size:11px;font-weight:600;color:#3b82f6; }
.mg-row-dates { font-size:11px;color:#94a3b8;white-space:nowrap; }
.mg-row-nodates { color:#475569; }
.day-mode .mg-row-nodates { color:#cbd5e1; }
.action-btns { display:flex;gap:4px;align-items:center; }
.mg-empty { display:flex;flex-direction:column;align-items:center;justify-content:center;flex:1;color:#64748b;gap:8px;padding:60px 0; }
.empty-icon { font-size:36px; }
.mg-empty p { margin:0;font-size:14px; }

.mg-card { border:1px solid rgba(255,255,255,.09);border-radius:10px;overflow:hidden;background:rgba(255,255,255,.03); }
.mg-card-header { display:flex;align-items:center;justify-content:space-between;padding:13px 16px;cursor:pointer;transition:background .15s;user-select:none; }
.mg-card-header:hover { background:rgba(255,255,255,.04); }
.mg-card-left { display:flex;align-items:center;gap:10px;min-width:0;flex:1; }
.mg-status-dot { width:8px;height:8px;border-radius:50%;flex-shrink:0; }
.mg-status-dot.active { background:#22c55e; }
.mg-status-dot.ended { background:#64748b; }
.mg-card-info { display:flex;flex-direction:column;gap:2px;min-width:0; }
.mg-card-title { font-size:14px;font-weight:600;color:#f1f5f9; }
.mg-card-desc { font-size:11px;color:#475569;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:400px; }
.mg-card-right { display:flex;align-items:center;gap:6px;flex-shrink:0; }
.mg-member-badge { font-size:11px;font-weight:600;color:#64748b;background:rgba(255,255,255,.06);border-radius:99px;padding:2px 8px;border:1px solid rgba(255,255,255,.08); }
.mg-icon-btn { width:28px;height:28px;border-radius:7px;border:1px solid rgba(255,255,255,.1);background:rgba(255,255,255,.05);color:#64748b;display:flex;align-items:center;justify-content:center;cursor:pointer;transition:all .15s; }
.mg-icon-btn.settings:hover { border-color:rgba(96,165,250,.5);color:#93c5fd;background:rgba(96,165,250,.1); }
.mg-icon-btn.end:hover { border-color:rgba(34,197,94,.4);color:#4ade80;background:rgba(34,197,94,.08); }
.mg-icon-btn.delete:hover { border-color:rgba(239,68,68,.4);color:#f87171;background:rgba(239,68,68,.08); }
.mg-icon-btn:disabled { opacity:.4;cursor:not-allowed; }
.mg-chevron { color:#475569;transition:transform .2s;flex-shrink:0; }
.mg-chevron.open { transform:rotate(180deg); }

.day-mode .mg-card { border-color:#e2e8f0;background:#fff; }\n.day-mode .mg-row { border-bottom-color:#f1f5f9; }\n.day-mode .mg-row:hover { background:#f8fafc; }\n.day-mode .mg-row-title { color:#1e293b; }
.day-mode .mg-card-header:hover { background:#f8fafc; }
.day-mode .mg-card-title { color:#1e293b; }
.day-mode .mg-card-desc { color:#94a3b8; }
.day-mode .mg-member-badge { background:#f1f5f9;border-color:#e2e8f0;color:#475569; }
.day-mode .mg-icon-btn { border-color:#e2e8f0;background:#fff;color:#64748b; }
/* ── Role badges ── */
.mg-role-badge { display:inline-flex;align-items:center;padding:1px 6px;border-radius:8px;font-size:10px;font-weight:700;letter-spacing:.03em;margin-top:3px; }
.mg-role-badge.role-admin { background:rgba(59,130,246,.15);color:#60a5fa;border:1px solid rgba(59,130,246,.25); }
.mg-role-badge.role-member { background:rgba(100,116,139,.1);color:#94a3b8;border:1px solid rgba(100,116,139,.18); }
.day-mode .mg-role-badge.role-admin { background:rgba(59,130,246,.08);color:#2563eb;border-color:rgba(59,130,246,.2); }
.day-mode .mg-role-badge.role-member { background:#f8fafc;color:#64748b;border-color:#e2e8f0; }

.mg-member-wrap { border-top:1px solid rgba(255,255,255,.07);padding:10px 16px;display:flex;flex-direction:column;gap:6px; }
.mg-members-state { font-size:12px;color:#475569;padding:4px 0; }
.mg-member-list { display:flex;flex-direction:column;gap:3px; }
.mg-member-row { display:flex;align-items:center;gap:10px;padding:5px 6px;border-radius:7px;transition:background .1s; }
.mg-member-row:hover { background:rgba(255,255,255,.04); }
.mg-avatar { width:26px;height:26px;border-radius:50%;color:#fff;font-size:11px;font-weight:700;display:flex;align-items:center;justify-content:center;flex-shrink:0; }
.mg-member-info { flex:1;display:flex;flex-direction:column;gap:1px;min-width:0; }
.mg-member-name { font-size:13px;font-weight:600;color:#e2e8f0; }
.mg-member-email { font-size:11px;color:#475569; }
.mg-role-text { font-size:11px;color:#64748b;font-weight:600;flex-shrink:0; }
.day-mode .mg-member-wrap { border-top-color:#f1f5f9; }
.day-mode .mg-member-row:hover { background:#f8fafc; }
.day-mode .mg-member-name { color:#1e293b; }

.expand-enter-active,.expand-leave-active { transition:opacity .2s; }
.expand-enter-from,.expand-leave-to { opacity:0; }

.req { color:#ef4444; }

.settings-body { gap:0; }
.settings-section { padding:14px 0;border-bottom:1px solid #f1f5f9;display:flex;flex-direction:column;gap:10px; }
.settings-section:last-child { border-bottom:none;padding-bottom:0; }
.settings-section-title { font-size:12px;font-weight:700;color:#64748b;text-transform:uppercase;letter-spacing:.05em;display:flex;align-items:center;gap:8px; }
.member-cnt-badge { font-size:11px;font-weight:700;background:rgba(96,165,250,.15);color:#93c5fd;border-radius:99px;padding:1px 7px;text-transform:none;letter-spacing:0; }

.member-search-wrap { display:flex;align-items:center;gap:8px;padding:7px 10px;border:1px solid #e2e8f0;border-radius:8px;background:#f8fafc; }
.member-search-wrap svg { color:#94a3b8;flex-shrink:0; }
.member-search-input { flex:1;border:none;background:none;color:#1e293b;font-size:12px;outline:none; }
.member-search-input::placeholder { color:#94a3b8; }
.search-spinner { color:#64748b;font-size:14px;flex-shrink:0; }

.member-search-results { border:1px solid #e2e8f0;border-radius:8px;overflow:hidden;background:#fff; }
.member-search-item { display:flex;align-items:center;gap:10px;padding:9px 12px;cursor:pointer;transition:background .1s; }
.member-search-item:hover { background:#f8fafc; }
.ms-avatar { width:26px;height:26px;border-radius:50%;color:#fff;font-size:11px;font-weight:700;display:flex;align-items:center;justify-content:center;flex-shrink:0; }
.ms-info { flex:1;display:flex;flex-direction:column; }
.ms-name { font-size:13px;font-weight:600;color:#1e293b; }
.ms-email { font-size:11px;color:#94a3b8; }
.ms-add-hint { font-size:11px;font-weight:700;color:#3b82f6;flex-shrink:0; }

.settings-member-list { display:flex;flex-direction:column;gap:3px;max-height:200px;overflow-y:auto; }
.settings-empty-members { font-size:12px;color:#64748b;padding:6px 0; }
.settings-member-row { display:flex;align-items:center;gap:10px;padding:5px 6px;border-radius:7px;transition:background .1s; }
.settings-member-row:hover { background:#f8fafc; }
.sm-avatar { width:26px;height:26px;border-radius:50%;color:#fff;font-size:11px;font-weight:700;display:flex;align-items:center;justify-content:center;flex-shrink:0; }
.sm-info { flex:1;display:flex;flex-direction:column;min-width:0; }
.sm-name { font-size:13px;font-weight:600;color:#1e293b;white-space:nowrap;overflow:hidden;text-overflow:ellipsis; }
.sm-email { font-size:11px;color:#94a3b8;white-space:nowrap;overflow:hidden;text-overflow:ellipsis; }
.sm-remove { width:22px;height:22px;border-radius:5px;border:none;background:rgba(239,68,68,.08);color:#f87171;cursor:pointer;display:flex;align-items:center;justify-content:center;flex-shrink:0;transition:background .15s; }
.sm-remove:hover { background:rgba(239,68,68,.2); }

/* ── Dark modal overrides ─────────────────────────────── */
.app-modal.dark .settings-section { border-bottom-color:rgba(255,255,255,.07); }
.app-modal.dark .settings-section-title { color:#475569; }
.app-modal.dark .member-search-wrap { border-color:rgba(255,255,255,.12);background:rgba(255,255,255,.05); }
.app-modal.dark .member-search-wrap svg { color:#475569; }
.app-modal.dark .member-search-input { color:#f1f5f9; }
.app-modal.dark .member-search-input::placeholder { color:#334155; }
.app-modal.dark .member-search-results { border-color:rgba(255,255,255,.1);background:#0f172a; }
.app-modal.dark .member-search-item:hover { background:rgba(255,255,255,.06); }
.app-modal.dark .ms-name { color:#f1f5f9; }
.app-modal.dark .ms-email { color:#475569; }
.app-modal.dark .settings-member-row:hover { background:rgba(255,255,255,.04); }
.app-modal.dark .sm-name { color:#f1f5f9; }
.app-modal.dark .sm-email { color:#475569; }
.app-modal.dark .settings-empty-members { color:#475569; }
</style>
