<script setup>
import { ref, computed, onMounted } from 'vue'
import api from '../api'
import { useMeetingsStore } from '../stores/meetings'
import { useThemeStore } from '../stores/theme'
import AppTable from '../components/AppTable.vue'

const orgColumns = [
  { label: '이름', width: '100px' },
  { label: '조직', width: '110px' },
  { label: '부서', width: '110px' },
  { label: '직책', width: '80px' },
  { label: '이메일', width: '180px' },
  { label: '회의체' },
  { label: '', width: '72px', noResize: true }
]

const meetingsStore = useMeetingsStore()
const themeStore = useThemeStore()
const nightMode = computed(() => themeStore.nightMode)

const selectedMeetingId = ref('all')
const searchQuery = ref('')
const activeRoleFilter = ref('all')
const allMembers = ref([])
const loadingMembers = ref(false)

const showAddModal = ref(false)
const addForm = ref({ name: '', email: '', organization: '', department: '', position: '', role: 'presenter' })

const editModal = ref(null)  // { ...member }

const ROLES = [
  { value: 'admin',     label: '간사',   color: '#10b981', bg: '#ecfdf5', border: '#a7f3d0' },
  { value: 'presenter', label: '참여자', color: '#64748b', bg: '#f1f5f9', border: '#cbd5e1' },
]
function roleInfo(r) { return ROLES.find(x => x.value === r) || ROLES[1] }

// Demo data fallback (shown when API has no data)
async function fetchAllMembers() {
  loadingMembers.value = true
  try {
    const res = await api.get('/api/users/all')
    // Map API response to the shape groupedFilteredMembers expects
    allMembers.value = res.data.map(u => ({
      id: u.id,
      name: u.name,
      email: u.email,
      employee_id: u.employee_id,
      department: u.department,
      organization: u.organization,
      position: u.position,
      role: u.meetings[0]?.role || 'presenter',
      meetingId: u.meetings[0]?.id || null,
      memberId: u.meetings[0]?.member_id || null,
      meetingTitle: u.meetings[0]?.title || '',
      meetings: u.meetings,
    }))
  } catch {
    allMembers.value = []
  } finally {
    loadingMembers.value = false
  }
}

const filteredMembers = computed(() => {
  const sid = selectedMeetingId.value
  let list = allMembers.value.map(m => {
    // 선택된 회의체가 있으면 해당 meeting 정보로 override
    const mg = sid !== 'all'
      ? m.meetings.find(g => String(g.id) === String(sid))
      : m.meetings[0]
    return {
      ...m,
      role: mg?.role || 'presenter',
      meetingId: mg?.id || m.meetingId,
      memberId: mg?.member_id || m.memberId,
    }
  })
  if (sid !== 'all') list = list.filter(m => m.meetings.some(mg => String(mg.id) === String(sid)))
  if (activeRoleFilter.value !== 'all') list = list.filter(m => m.role === activeRoleFilter.value)
  const q = searchQuery.value.trim().toLowerCase()
  if (q) list = list.filter(m =>
    (m.name || '').toLowerCase().includes(q) ||
    (m.email || '').toLowerCase().includes(q) ||
    (m.position || '').toLowerCase().includes(q) ||
    (m.department || '').toLowerCase().includes(q)
  )
  return list
})

const baseCounts = computed(() => {
  const sid = selectedMeetingId.value
  const base = allMembers.value
    .map(m => {
      const mg = sid !== 'all' ? m.meetings.find(g => String(g.id) === String(sid)) : m.meetings[0]
      return { ...m, role: mg?.role || 'presenter' }
    })
    .filter(m => sid === 'all' || m.meetings.some(g => String(g.id) === String(sid)))
  const c = { all: base.length }
  ROLES.forEach(r => { c[r.value] = base.filter(m => m.role === r.value).length })
  return c
})

onMounted(async () => {
  await Promise.all([meetingsStore.fetchMeetings(), fetchAllMembers()])
})

function openAddModal() {
  addForm.value = { name: '', email: '', organization: '', department: '', position: '', role: 'presenter' }
  showAddModal.value = true
}

async function submitAdd() {
  if (!addForm.value.name.trim()) return
  // Add as a local custom member (no API user account)
  const newMember = {
    id: 'custom_' + Date.now(),
    name: addForm.value.name,
    email: addForm.value.email,
    organization: addForm.value.organization,
    department: addForm.value.department,
    position: addForm.value.position,
    role: addForm.value.role,
    meetingId: null,
    meetingTitle: '',
    meetings: [],
    isCustom: true,
  }
  allMembers.value = [newMember, ...allMembers.value]
  showAddModal.value = false
}

async function removeMember(member) {
  if (!confirm(`${member.name || member.email}을(를) 제거하시겠습니까?`)) return
  if (!member.meetingId || !member.memberId) { alert('회의체 정보가 없어 제거할 수 없습니다.'); return }
  try {
    await api.delete(`/api/meetings/${member.meetingId}/members/${member.memberId}`)
    await fetchAllMembers()
  } catch (e) { alert(e.response?.data?.detail || '제거 실패') }
}

function openEdit(member) { editModal.value = { ...member } }

async function saveEdit() {
  const m = editModal.value
  try {
    // Update user profile fields
    await api.patch(`/api/users/${m.id}`, {
      name: m.name,
      organization: m.organization || null,
      department: m.department || null,
      position: m.position || null,
    })
    // Update meeting role if applicable
    if (m.meetingId && m.memberId) {
      await api.patch(`/api/meetings/${m.meetingId}/members/${m.memberId}`, { role: m.role })
    }
    await fetchAllMembers()
  } catch (e) { alert(e.response?.data?.detail || '변경 실패') }
  editModal.value = null
}

async function updateMemberRole(member, newRole) {
  // filteredMembers에서 이미 선택된 회의체 기준 meetingId/memberId가 주입된 상태
  const meetingId = member.meetingId
  const memberId = member.memberId
  if (!meetingId || !memberId) { alert('회의체 정보가 없어 역할을 변경할 수 없습니다.'); return }
  try {
    await api.patch(`/api/meetings/${meetingId}/members/${memberId}`, { role: newRole })
    // allMembers의 해당 meeting 항목 role 갱신
    const target = allMembers.value.find(m => m.id === member.id)
    if (target) {
      const mg = target.meetings.find(g => String(g.id) === String(meetingId))
      if (mg) mg.role = newRole
      if (String(target.meetingId) === String(meetingId)) target.role = newRole
    }
  } catch (e) { alert(e.response?.data?.detail || '역할 변경 실패') }
}

const expandedRows = ref(new Set())
function toggleExpand(key) {
  const s = new Set(expandedRows.value)
  s.has(key) ? s.delete(key) : s.add(key)
  expandedRows.value = s
}

// Each user from /api/users/all is already unique – no grouping needed
const groupedFilteredMembers = computed(() => filteredMembers.value)

function formatDate(s) {
  if (!s) return '-'
  const d = new Date(s)
  if (isNaN(d)) return s
  return `${d.getFullYear()}년 ${d.getMonth()+1}월 ${d.getDate()}일`
}

function initials(name) { return (name || '?')[0] }

// avatar color per name (stable)
const AVATAR_COLORS = ['#6366f1','#3b82f6','#10b981','#f59e0b','#ef4444','#8b5cf6','#ec4899','#14b8a6']
function avatarColor(name) { let h = 0; for (const c of (name || '')) h = (h * 31 + c.charCodeAt(0)) % AVATAR_COLORS.length; return AVATAR_COLORS[h] }
</script>

<template>
  <div class="org-page page-full-height" :class="{ 'day-mode': !nightMode }">
    <!-- Archive-style header -->
    <div class="archive-header">
      <div class="header-title-wrap">
        <h1 class="archive-title">조직 관리</h1>
      </div>

      <div class="search-wrap">
        <svg class="search-icon" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><circle cx="11" cy="11" r="8"/><path d="M21 21l-4.35-4.35"/></svg>
        <input v-model="searchQuery" class="search-input" placeholder="이름, 직책, 이메일 검색..." />
      </div>

      <select v-model="selectedMeetingId" class="org-meeting-select app-select">
        <option value="all">전체 회의체</option>
        <option v-for="m in meetingsStore.meetings" :key="m.id" :value="String(m.id)">{{ m.title }}</option>
      </select>

      <div class="app-tabs">
        <button class="app-tab" :class="{ active: activeRoleFilter === 'all' }" @click="activeRoleFilter = 'all'">
          <span class="app-tab-badge">{{ baseCounts.all }}</span> 전체
        </button>
        <button v-for="r in ROLES" :key="r.value"
          class="app-tab" :class="{ active: activeRoleFilter === r.value }"
          @click="activeRoleFilter = r.value">
          <span class="app-tab-badge">{{ baseCounts[r.value] || 0 }}</span> {{ r.label }}
        </button>
      </div>

      <div class="plus-wrap">
        <button class="create-meeting-btn" @click="openAddModal">
          <svg width="13" height="13" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24"><path d="M16 21v-2a4 4 0 00-4-4H6a4 4 0 00-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M19 8v6M22 11h-6"/></svg>
          구성원 추가
        </button>
      </div>
    </div>

    <!-- Table -->
    <div class="table-wrap">
      <div v-if="loadingMembers" class="table-loading">
        <span class="spinner-border spinner-border-sm text-primary"></span>
        <span style="margin-left:10px;color:var(--text-muted);font-size:13px">불러오는 중...</span>
      </div>
      <AppTable v-else :columns="orgColumns" :dark="nightMode">
          <tr v-for="member in groupedFilteredMembers" :key="member.email||member.name" class="member-row">
            <td>
              <div class="name-cell">
                <span class="member-name-text">{{ member.name || '이름없음' }}</span>
              </div>
            </td>
            <td class="cell-muted">{{ member.organization || '-' }}</td>
            <td class="cell-muted">{{ member.department || '-' }}</td>
            <td class="cell-muted">{{ member.position || '-' }}</td>
            <td class="cell-muted">{{ member.email || '-' }}</td>
            <td>
              <div class="cell-meetings">
              <template v-if="selectedMeetingId !== 'all'">
                <span class="meeting-tag">{{ member.meetings.find(g => String(g.id) === String(selectedMeetingId))?.title || '-' }}</span>
              </template>
              <template v-else>
                <span class="meeting-tag">{{ member.meetings[0]?.title || '-' }}</span>
                <template v-if="member.meetings.length > 1">
                  <template v-if="expandedRows.has(member.email||member.name)">
                    <span v-for="mg in member.meetings.slice(1)" :key="mg.id" class="meeting-tag">{{ mg.title }}</span>
                    <button class="meeting-more-btn" @click.stop="toggleExpand(member.email||member.name)">접기</button>
                  </template>
                  <button v-else class="meeting-more-btn" @click.stop="toggleExpand(member.email||member.name)">
                    +{{ member.meetings.length - 1 }}개 더보기
                  </button>
                </template>
              </template>
              </div>
            </td>
            <td>
              <div class="action-btns">
                <button class="act-btn" @click="openEdit(member)" title="수정">
                  <svg width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M11 4H4a2 2 0 00-2 2v14a2 2 0 002 2h14a2 2 0 002-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 013 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>
                </button>
                <button class="act-btn danger" @click="removeMember(member)" title="제거">
                  <svg width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14a2 2 0 01-2 2H8a2 2 0 01-2-2L5 6"/><path d="M10 11v6M14 11v6"/><path d="M9 6V4a1 1 0 011-1h4a1 1 0 011 1v2"/></svg>
                </button>
              </div>
            </td>
          </tr>
          <tr v-if="!groupedFilteredMembers.length">
            <td colspan="7" class="empty-row">
              <div class="empty-state">
                <div class="empty-icon-lg">👤</div>
                <p>표시할 구성원이 없습니다</p>
              </div>
            </td>
          </tr>
      </AppTable>
    </div>

    <!-- Add member modal -->
    <Teleport to="body">
      <div v-if="showAddModal" class="app-modal-backdrop" @click.self="showAddModal = false">
        <div class="app-modal app-modal-sm">
          <div class="app-modal-header">
            <span class="app-modal-title">구성원 추가</span>
            <button class="app-modal-close" @click="showAddModal = false">
              <svg width="14" height="14" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24"><path d="M6 18L18 6M6 6l12 12"/></svg>
            </button>
          </div>
          <div class="app-modal-body">
            <!-- Name & Email -->
            <div class="app-modal-field-row">
              <div class="app-modal-field">
                <label>이름 <span class="req">*</span></label>
                <input v-model="addForm.name" class="app-modal-input" placeholder="홍길동" />
              </div>
              <div class="app-modal-field">
                <label>이메일</label>
                <input v-model="addForm.email" class="app-modal-input" placeholder="example@company.com" />
              </div>
            </div>
            <!-- Organization & Department -->
            <div class="app-modal-field-row">
              <div class="app-modal-field">
                <label>조직명</label>
                <input v-model="addForm.organization" class="app-modal-input" placeholder="예: 워크메이트" />
              </div>
              <div class="app-modal-field">
                <label>부서명</label>
                <input v-model="addForm.department" class="app-modal-input" placeholder="예: 전략기획팀" />
              </div>
            </div>
            <!-- Position & Role -->
            <div class="app-modal-field-row">
              <div class="app-modal-field">
                <label>직책</label>
                <input v-model="addForm.position" class="app-modal-input" placeholder="예: 팀장" />
              </div>
              <div class="app-modal-field">
                <label>역할</label>
                <select v-model="addForm.role" class="app-select" style="width:100%;font-size:13px;padding:7px 28px 7px 10px">
                  <option v-for="r in ROLES" :key="r.value" :value="r.value">{{ r.label }}</option>
                </select>
              </div>
            </div>
          </div>
          <div class="app-modal-footer">
            <button class="app-btn-cancel" @click="showAddModal = false">취소</button>
            <button class="app-btn-primary" :disabled="!addForm.name.trim()" @click="submitAdd">추가</button>
          </div>
        </div>
      </div>


      <!-- Edit member modal -->
      <div v-if="editModal" class="app-modal-backdrop" @click.self="editModal = null">
        <div class="app-modal app-modal-sm">
          <div class="app-modal-header">
            <span class="app-modal-title">구성원 정보 수정</span>
            <button class="app-modal-close" @click="editModal = null">
              <svg width="14" height="14" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24"><path d="M6 18L18 6M6 6l12 12"/></svg>
            </button>
          </div>
          <div class="app-modal-body">
            <div class="app-modal-field-row">
              <div class="app-modal-field">
                <label>이름</label>
                <input v-model="editModal.name" class="app-modal-input" placeholder="홍길동" />
              </div>
              <div class="app-modal-field">
                <label>이메일</label>
                <input :value="editModal.email" class="app-modal-input" disabled style="background:#f8fafc;color:#94a3b8" />
              </div>
            </div>
            <div class="app-modal-field-row">
              <div class="app-modal-field">
                <label>조직명</label>
                <input v-model="editModal.organization" class="app-modal-input" placeholder="예: 워크메이트" />
              </div>
              <div class="app-modal-field">
                <label>부서명</label>
                <input v-model="editModal.department" class="app-modal-input" placeholder="예: 전략기획팀" />
              </div>
            </div>
            <div class="app-modal-field-row">
              <div class="app-modal-field">
                <label>직책</label>
                <input v-model="editModal.position" class="app-modal-input" placeholder="예: 팀장" />
              </div>
              <div class="app-modal-field">
                <label>역할</label>
                <select v-model="editModal.role" class="app-select" style="width:100%;font-size:13px;padding:7px 28px 7px 10px">
                  <option v-for="r in ROLES" :key="r.value" :value="r.value">{{ r.label }}</option>
                </select>
              </div>
            </div>
          </div>
          <div class="app-modal-footer">
            <button class="app-btn-cancel" @click="editModal = null">취소</button>
            <button class="app-btn-primary" @click="saveEdit">저장</button>
          </div>
        </div>
      </div>

    </Teleport>
  </div>
</template>

<style scoped>
.org-page {
  display: flex;
  flex-direction: column;
  height: 100%;
}

/* Header – identical to ArchivePage */
.archive-header { display:flex;align-items:center;gap:12px;padding:10px 16px;background:#0f172a;border-bottom:1px solid rgba(255,255,255,.08);flex-shrink:0;flex-wrap:wrap; }
.header-title-wrap { flex-shrink:0; }
.archive-title { font-size:16px;font-weight:700;color:#f1f5f9;margin:0; }
.search-wrap { position:relative;flex:1;min-width:160px;max-width:360px; }
.search-icon { position:absolute;left:9px;top:50%;transform:translateY(-50%);color:#475569;pointer-events:none; }
.search-input { width:100%;background:rgba(255,255,255,.06);border:1px solid rgba(255,255,255,.1);border-radius:8px;padding:7px 28px;font-size:12px;color:#e2e8f0;outline:none; }
.search-input::placeholder { color:#334155; }
.search-input:focus { border-color:rgba(96,165,250,.5); }
.plus-wrap { position:relative;flex-shrink:0;margin-left:auto; }
.create-meeting-btn { display:flex;align-items:center;gap:6px;height:34px;padding:0 14px;border-radius:8px;background:#3b82f6;border:none;color:#fff;font-size:13px;font-weight:600;cursor:pointer;transition:opacity .15s;white-space:nowrap; }
.create-meeting-btn:hover { opacity:.85; }

/* Meeting select — layout-only overrides; visual style from global .app-select */
.org-meeting-select { min-width:120px;font-size:12px;font-weight:500;height:32px;padding-top:0;padding-bottom:0; }

/* Day-mode overrides */
.day-mode .archive-header { background:#eef2ff;border-bottom-color:#e2e8f0; }
.day-mode .archive-title { color:#1e293b; }
.day-mode .search-input { background:rgba(255,255,255,.6);border-color:#e2e8f0;color:#1e293b; }
.day-mode .search-input::placeholder { color:#94a3b8; }
.day-mode .search-icon { color:#94a3b8; }

/* Table */
.table-wrap {
  flex: 1;
  overflow-y: auto;
  min-height: 0;
  padding: 16px 20px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.table-loading {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 48px;
}
.member-row {
  border-bottom: 1px solid rgba(255,255,255,.06);
  transition: background .1s;
}
.member-row:last-child { border-bottom: none; }
.member-row:hover { background: rgba(255,255,255,.04); }
.day-mode .member-row { border-bottom-color: #f1f5f9; }
.day-mode .member-row:hover { background: #fafbff; }

.name-cell { display: flex; align-items: center; gap: 10px; }
.avatar {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #fff;
  font-size: 13px;
  font-weight: 700;
  flex-shrink: 0;
}
.avatar-xs { width: 28px; height: 28px; font-size: 11px; }
.member-name-text { font-weight: 600; color: #e2e8f0; }
.day-mode .member-name-text { color: #1e293b; }

.cell-role { color: #94a3b8; font-size: 12px; font-weight: 600; white-space: nowrap; }
.day-mode .cell-role { color: #475569; }
.cell-muted { color: #64748b; }
.day-mode .cell-muted { color: #475569; }
.cell-meetings { display: flex; flex-wrap: nowrap; align-items: center; gap: 4px; overflow: hidden; width: 100%; }
.meeting-tag {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 4px;
  background: #f1f5f9;
  color: #475569;
  font-size: 12px;
  white-space: nowrap;
}
.meeting-more-btn {
  border: none;
  background: none;
  color: #94a3b8;
  font-size: 11px;
  font-weight: 600;
  cursor: pointer;
  padding: 2px 4px;
  border-radius: 4px;
  transition: color .15s;
  white-space: nowrap;
  flex-shrink: 0;
}
.meeting-more-btn:hover { color: #3b82f6; }

.action-btns { display: flex; gap: 4px; width: fit-content; margin-left: auto; }
:deep(td:last-child) { padding-left: 6px; padding-right: 6px; }
.act-btn {
  width: 28px;
  height: 28px;
  border-radius: 6px;
  border: 1px solid var(--border);
  background: #fff;
  color: #64748b;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: all .15s;
}
.act-btn:hover { border-color: var(--primary); color: var(--primary); background: #eff6ff; }
.act-btn.danger:hover { border-color: #fca5a5; color: #dc2626; background: #fef2f2; }

.empty-row { padding: 0 !important; }
.empty-state { text-align: center; padding: 56px; color: var(--text-muted); }
.empty-icon-lg { font-size: 40px; margin-bottom: 10px; }
.empty-state p { margin: 0; font-size: 14px; }

.req { color:#ef4444; }
.rel { position: relative; }

.dropdown-results {
  position: absolute;
  top: calc(100% + 4px);
  left: 0;
  right: 0;
  background: #fff;
  border: 1px solid var(--border);
  border-radius: 10px;
  box-shadow: 0 8px 24px rgba(0,0,0,.12);
  z-index: 10;
  overflow: hidden;
  max-height: 200px;
  overflow-y: auto;
}
.dropdown-item-result {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
  cursor: pointer;
  transition: background .1s;
}
.dropdown-item-result:hover { background: #f1f5f9; }

.edit-member-info {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px;
  background: #f8fafc;
  border-radius: 10px;
}
.role-options { display: grid; grid-template-columns: 1fr 1fr; gap: 6px; }
.role-option {
  display: flex;
  align-items: center;
  gap: 7px;
  padding: 8px 10px;
  border-radius: 8px;
  border: 1px solid var(--border);
  cursor: pointer;
  transition: all .15s;
  background: #f8fafc;
}
.role-dot-sm { width: 7px; height: 7px; border-radius: 50%; flex-shrink: 0; }

</style>
