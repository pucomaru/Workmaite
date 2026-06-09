<script setup>
import { ref, computed, onMounted } from 'vue'
import { useMeetingsStore } from '../stores/meetings'
import { useThemeStore } from '../stores/theme'
import { useAuthStore } from '../stores/auth'
import api, { apiAI } from '../api'
import MemberInvite from '../components/MemberInvite.vue'
import AppTable from '../components/AppTable.vue'
import DateInput from '../components/DateInput.vue'
import MeetingSettingsModal from '../components/MeetingSettingsModal.vue'

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
const authStore = useAuthStore()
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
    const orgs = [...new Set(members.map(mb => mb.user?.company || mb.company).filter(Boolean))]
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
  const me = authStore.user
  createMembers.value = me
    ? [{ userId: me.id, name: me.name, email: me.email || me.employee_id || '', role: 'admin' }]
    : []
  showCreate.value = true
}

async function submitCreate() {
  if (!createForm.value.title.trim()) return
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
      if (mb.userId === myId) continue  // 생성 시 서버가 자동으로 admin 추가
      await api.post(`/api/v1/meetings/${meeting.id}/members`, { userId: mb.userId, role: mb.role })
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

async function openSettings(m) {
  // PG 최신값 fetch (Spring Boot → PG 직접)
  let pgMeeting = null
  try { pgMeeting = (await api.get(`/api/v1/meetings/${m.id}`)).data } catch {}
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
    removedIds: [],
  }
}

function closeSettings() { settingsModal.value = null }

const savingSettings = ref(false)
async function saveSettings() {
  if (!settingsModal.value) return
  savingSettings.value = true
  const { meeting, form, members, removedIds } = settingsModal.value
  try {
    await apiAI.patch(`/api/v1/meetings/${meeting.id}`, { title: form.title, description: form.purpose, start_date: form.start_date || null, end_date: form.end_date || null, guidelines: form.guidelines, meeting_type: form.meeting_type || null })
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
  } catch (e) {
    const detail = e.response?.data?.detail
    alert(typeof detail === 'string' ? detail : detail ? JSON.stringify(detail) : '저장 실패')
  }
  finally { savingSettings.value = false }
}

function canManage(g) { return meetingsStore.meetingRoles[g.id] === 'admin' }
function getAdmins(gid) { return (membersCache.value[gid] || []).filter(mb => mb.role === 'admin') }
function getOrgs(gid) { const orgs = new Set(); (membersCache.value[gid] || []).forEach(mb => { const o = mb.user?.company || mb.user?.department; if (o) orgs.add(o) }); return [...orgs] }

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
        <button class="create-btn" @click="openCreate">
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
      <div v-if="showCreate" class="app-modal-backdrop">
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
                <DateInput v-model="createForm.start_date" class="app-modal-input" />
              </div>
              <div class="app-modal-field">
                <label>종료일</label>
                <DateInput v-model="createForm.end_date" class="app-modal-input" />
              </div>
            </div>
            <div class="app-modal-field">
              <label>운영 지침</label>
              <textarea v-model="createForm.guidelines" class="app-modal-input" rows="3" placeholder="운영 지침, 규칙, 주의사항 등을 입력하세요...
예: 매주 월요일 10시, 의장 승인 필수, 안건 72시간 전 제출 등"></textarea>
            </div>
            <div class="app-modal-field">
              <label>멤버 초대</label>
              <MemberInvite v-model="createMembers" :lockedUserId="authStore.user?.id" />
            </div>
          </div>
          <div class="app-modal-footer">
            <button class="app-btn-cancel" @click="showCreate=false">취소</button>
            <button class="app-btn-primary" :disabled="!createForm.title.trim() || creating" @click="submitCreate">{{ creating ? '생성 중...' : '생성' }}</button>
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
  </div>
</template>

<style scoped>
.mg-page { display:flex;flex-direction:column;height:100%; }
.mg-body { flex:1;overflow-y:auto;padding:16px 20px;display:flex;flex-direction:column;gap:8px; }

/* 테이블 행 */
.mg-row { border-bottom:1px solid rgba(255,255,255,.06);cursor:default;background:transparent; }
.mg-row:hover { background:rgba(255,255,255,.04); }
.mg-row-title { font-size:13px;font-weight:600;color:var(--dark-text); }
.day-mode .mg-row { border-bottom-color:var(--surface-2);background:#fff; }
.day-mode .mg-row:hover { background:var(--surface); }
.day-mode .mg-row-title { color:var(--dark-card); }
.mg-row-nodates { color:var(--text-dim); }
.day-mode .mg-row-nodates { color:#cbd5e1; }
.mg-type-text { font-size:11px;font-weight:600;color:var(--accent); }
.mg-admin-name { font-size:12px;color:var(--text-dim);margin-left:4px; }
.mg-member-count-label { font-size:12px;color:var(--text-muted);margin-left:4px; }
.mg-member-more { font-size:11px;color:var(--dark-muted);margin-left:2px; }
.mg-org-tags { display:flex;flex-wrap:wrap;gap:4px;align-items:center; }
.mg-org-tag { font-size:11px;font-weight:500;padding:2px 7px;border-radius:99px;background:var(--surface-2);color:var(--text-dim);border:1px solid var(--border);white-space:nowrap; }

/* 상태 dot */
.mg-status-dot { width:8px;height:8px;border-radius:50%;flex-shrink:0; }
.mg-status-dot.active { background:#22c55e; }
.mg-status-dot.ended { background:var(--text-muted); }

/* 아이콘 버튼 */
.action-btns { display:flex;gap:4px;align-items:center; }
.mg-icon-btn { width:28px;height:28px;border-radius:7px;border:1px solid rgba(255,255,255,.1);background:rgba(255,255,255,.05);color:var(--text-muted);display:flex;align-items:center;justify-content:center;cursor:pointer; }
.mg-icon-btn.settings:hover { border-color:rgba(96,165,250,.5);color:#93c5fd;background:rgba(96,165,250,.1); }
.mg-icon-btn.end:hover { border-color:rgba(34,197,94,.4);color:#4ade80;background:rgba(34,197,94,.08); }
.mg-icon-btn.delete:hover { border-color:rgba(239,68,68,.4);color:#f87171;background:rgba(239,68,68,.08); }
.mg-icon-btn:disabled { opacity:.4;cursor:not-allowed; }
.day-mode .mg-icon-btn { border-color:var(--border);background:#fff;color:var(--text-muted); }

/* 역할 뱃지 */
.mg-role-badge { display:inline-flex;align-items:center;padding:1px 6px;border-radius:8px;font-size:10px;font-weight:700;letter-spacing:.03em;margin-top:3px; }
.mg-role-badge.role-admin { background:rgba(59,130,246,.15);color:var(--accent-light);border:1px solid rgba(59,130,246,.25); }
.mg-role-badge.role-member { background:rgba(100,116,139,.1);color:var(--dark-muted);border:1px solid rgba(100,116,139,.18); }
.day-mode .mg-role-badge.role-admin { background:rgba(59,130,246,.08);color:#2563eb;border-color:rgba(59,130,246,.2); }
.day-mode .mg-role-badge.role-member { background:var(--surface);color:var(--text-muted);border-color:var(--border); }

/* 빈 상태 */
.mg-empty { display:flex;flex-direction:column;align-items:center;justify-content:center;flex:1;color:var(--text-muted);gap:8px;padding:60px 0; }
.mg-empty p { margin:0;font-size:14px; }

.req { color:var(--danger); }
</style>
