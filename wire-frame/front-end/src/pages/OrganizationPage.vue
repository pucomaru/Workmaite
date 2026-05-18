<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import api from '../api'
import { useMeetingsStore } from '../stores/meetings'
import { useThemeStore } from '../stores/theme'

const meetingsStore = useMeetingsStore()
const themeStore = useThemeStore()
const nightMode = computed(() => themeStore.nightMode)

const selectedMeetingId = ref('all')
const searchQuery = ref('')
const activeRoleFilter = ref('all')
const allMembers = ref([])
const loadingMembers = ref(false)

const showAddModal = ref(false)
const addForm = ref({ searchQuery: '', searchResults: [], selectedUser: null, role: 'member', position: '' })
const addSearchLoading = ref(false)

const editModal = ref(null)  // { ...member }

const ROLES = [
  { value: 'chair',     label: '의장', color: '#3b82f6', bg: '#eff6ff', border: '#bfdbfe' },
  { value: 'secretary', label: '간사', color: '#10b981', bg: '#ecfdf5', border: '#a7f3d0' },
  { value: 'member',    label: '위원', color: '#64748b', bg: '#f1f5f9', border: '#cbd5e1' },
  { value: 'observer',  label: '참관', color: '#f59e0b', bg: '#fef3c7', border: '#fde68a' },
]
function roleInfo(r) { return ROLES.find(x => x.value === r) || ROLES[2] }

// Demo data fallback (shown when API has no data)
async function fetchAllMembers() {
  loadingMembers.value = true
  try {
    const meetings = meetingsStore.meetings
    if (!meetings.length) { allMembers.value = []; return }
    const results = []
    await Promise.all(meetings.map(async m => {
      try {
        const res = await api.get(`/api/meetings/${m.id}/members`)
        res.data.forEach(member => results.push({ ...member, meetingTitle: m.title, meetingId: m.id }))
      } catch {}
    }))
    allMembers.value = results
  } catch {
    allMembers.value = []
  } finally {
    loadingMembers.value = false
  }
}

const filteredMembers = computed(() => {
  let list = allMembers.value
  if (selectedMeetingId.value !== 'all') list = list.filter(m => String(m.meetingId) === String(selectedMeetingId.value))
  if (activeRoleFilter.value !== 'all') list = list.filter(m => (m.role || 'member') === activeRoleFilter.value)
  const q = searchQuery.value.trim().toLowerCase()
  if (q) list = list.filter(m =>
    (m.name || '').toLowerCase().includes(q) ||
    (m.email || '').toLowerCase().includes(q) ||
    (m.position || '').toLowerCase().includes(q)
  )
  return list
})

const baseCounts = computed(() => {
  const base = selectedMeetingId.value === 'all' ? allMembers.value
    : allMembers.value.filter(m => String(m.meetingId) === String(selectedMeetingId.value))
  const c = { all: base.length }
  ROLES.forEach(r => { c[r.value] = base.filter(m => (m.role || 'member') === r.value).length })
  return c
})

onMounted(async () => {
  await meetingsStore.fetchMeetings()
  await fetchAllMembers()
})

// Add member search
let addTimer = null
watch(() => addForm.value.searchQuery, q => {
  clearTimeout(addTimer)
  if (!q.trim()) { addForm.value.searchResults = []; return }
  addTimer = setTimeout(async () => {
    addSearchLoading.value = true
    try {
      const res = await api.get('/api/users/search', { params: { q } })
      addForm.value.searchResults = res.data
    } catch { addForm.value.searchResults = [] }
    finally { addSearchLoading.value = false }
  }, 300)
})

function openAddModal() {
  addForm.value = { searchQuery: '', searchResults: [], selectedUser: null, role: 'member', position: '', meetingId: selectedMeetingId.value === 'all' ? (meetingsStore.meetings[0]?.id || '') : selectedMeetingId.value }
  showAddModal.value = true
}

function selectAddUser(u) {
  addForm.value.selectedUser = u
  addForm.value.searchQuery = u.name || u.email
  addForm.value.searchResults = []
}

async function submitAdd() {
  if (!addForm.value.selectedUser || !addForm.value.meetingId) return
  try {
    await api.post(`/api/meetings/${addForm.value.meetingId}/members`, {
      userId: addForm.value.selectedUser.id,
      role: addForm.value.role,
      position: addForm.value.position,
    })
    showAddModal.value = false
    await fetchAllMembers()
  } catch (e) { alert(e.response?.data?.detail || '추가 실패') }
}

async function removeMember(member) {
  if (!confirm(`${member.name || member.email}을(를) 제거하시겠습니까?`)) return
  const mid = member.id || member.userId || member.user_id
  try {
    await api.delete(`/api/meetings/${member.meetingId}/members/${mid}`)
    await fetchAllMembers()
  } catch (e) { alert(e.response?.data?.detail || '제거 실패') }
}

function openEdit(member) { editModal.value = { ...member } }

async function saveEdit() {
  const m = editModal.value
  const mid = m.id || m.userId || m.user_id
  try {
    await api.patch(`/api/meetings/${m.meetingId}/members/${mid}`, { role: m.role, position: m.position })
    await fetchAllMembers()
  } catch (e) { alert(e.response?.data?.detail || '변경 실패') }
  editModal.value = null
}

const expandedRows = ref(new Set())
function toggleExpand(key) {
  const s = new Set(expandedRows.value)
  s.has(key) ? s.delete(key) : s.add(key)
  expandedRows.value = s
}

// Group by email (same person in multiple meetings → 1 row)
const groupedFilteredMembers = computed(() => {
  const map = new Map()
  filteredMembers.value.forEach(m => {
    const key = m.email || m.name || String(m.id)
    if (!map.has(key)) {
      map.set(key, { ...m, meetings: [{ id: m.meetingId, title: m.meetingTitle, role: m.role }] })
    } else {
      map.get(key).meetings.push({ id: m.meetingId, title: m.meetingTitle, role: m.role })
    }
  })
  return [...map.values()]
})

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

      <select v-model="selectedMeetingId" class="org-meeting-select">
        <option value="all">전체 회의체</option>
        <option v-for="m in meetingsStore.meetings" :key="m.id" :value="String(m.id)">{{ m.title }}</option>
      </select>

      <div class="org-role-chips">
        <button class="org-chip" :class="{ active: activeRoleFilter === 'all' }" @click="activeRoleFilter = 'all'">
          <span class="org-chip-count">{{ baseCounts.all }}</span> 전체
        </button>
        <button v-for="r in ROLES" :key="r.value"
          class="org-chip" :class="{ active: activeRoleFilter === r.value }"
          @click="activeRoleFilter = r.value">
          <span class="org-chip-count">{{ baseCounts[r.value] || 0 }}</span> {{ r.label }}
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
      <table v-else class="member-table">
        <thead>
          <tr>
            <th style="width:200px">이름</th>
            <th style="width:60px">역할</th>
            <th style="width:120px">회사</th>
            <th style="width:120px">부서</th>
            <th style="width:130px">직책</th>
            <th style="width:200px">이메일</th>
            <th>회의체</th>
            <th style="width:72px"></th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="member in groupedFilteredMembers" :key="member.email||member.name" class="member-row">
            <td>
              <div class="name-cell">
                <div class="avatar" :style="{ background: avatarColor(member.name) }">{{ initials(member.name) }}</div>
                <span class="member-name-text">{{ member.name || '이름없음' }}</span>
              </div>
            </td>
            <td class="cell-role">{{ roleInfo(member.role).label }}</td>
            <td class="cell-muted">{{ member.company || '-' }}</td>
            <td class="cell-muted">{{ member.department || '-' }}</td>
            <td class="cell-muted">{{ member.position || '-' }}</td>
            <td class="cell-muted">{{ member.email || '-' }}</td>
            <td class="cell-meetings">
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
            </td>
            <td>
              <div class="action-btns">
                <button class="act-btn" @click="openEdit(member)" title="역할 변경">
                  <svg width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M11 4H4a2 2 0 00-2 2v14a2 2 0 002 2h14a2 2 0 002-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 013 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>
                </button>
                <button class="act-btn danger" @click="removeMember(member)" title="제거">
                  <svg width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14a2 2 0 01-2 2H8a2 2 0 01-2-2L5 6"/><path d="M10 11v6M14 11v6"/><path d="M9 6V4a1 1 0 011-1h4a1 1 0 011 1v2"/></svg>
                </button>
              </div>
            </td>
          </tr>
          <tr v-if="!groupedFilteredMembers.length">
            <td colspan="8" class="empty-row">
              <div class="empty-state">
                <div class="empty-icon-lg">👤</div>
                <p>표시할 구성원이 없습니다</p>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- Add member modal -->
    <Teleport to="body">
      <div v-if="showAddModal" class="modal-backdrop" @click.self="showAddModal = false">
        <div class="modal-box">
          <div class="modal-header">
            <span class="modal-title">구성원 추가</span>
            <button class="modal-close-btn" @click="showAddModal = false">
              <svg width="14" height="14" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24"><path d="M6 18L18 6M6 6l12 12"/></svg>
            </button>
          </div>
          <div class="modal-body">
            <!-- Meeting selector -->
            <div class="form-group">
              <label class="form-label">회의체</label>
              <select v-model="addForm.meetingId" class="form-select-sm">
                <option v-for="m in meetingsStore.meetings" :key="m.id" :value="m.id">{{ m.title }}</option>
              </select>
            </div>
            <!-- User search -->
            <div class="form-group">
              <label class="form-label">구성원 검색</label>
              <div class="rel">
                <svg class="search-icon-sm" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><circle cx="11" cy="11" r="8"/><path d="M21 21l-4.35-4.35"/></svg>
                <input v-model="addForm.searchQuery" class="search-input" placeholder="이름 또는 이메일로 검색..." />
                <span v-if="addSearchLoading" class="spinner-border spinner-border-sm text-muted" style="position:absolute;right:10px;top:50%;transform:translateY(-50%)"></span>
              </div>
              <div v-if="addForm.searchResults.length" class="dropdown-results">
                <div v-for="u in addForm.searchResults" :key="u.id" class="dropdown-item-result" @click="selectAddUser(u)">
                  <div class="avatar avatar-xs" :style="{ background: avatarColor(u.name) }">{{ initials(u.name || u.email) }}</div>
                  <div>
                    <div style="font-size:13px;font-weight:600;color:#1e293b">{{ u.name || '이름없음' }}</div>
                    <div style="font-size:11px;color:var(--text-muted)">{{ u.email }}</div>
                  </div>
                </div>
              </div>
            </div>
            <!-- Role & position -->
            <div class="form-row-2">
              <div class="form-group">
                <label class="form-label">역할</label>
                <select v-model="addForm.role" class="form-select-sm">
                  <option v-for="r in ROLES" :key="r.value" :value="r.value">{{ r.label }}</option>
                </select>
              </div>
              <div class="form-group">
                <label class="form-label">직책</label>
                <input v-model="addForm.position" class="form-input-sm" placeholder="예: 팀장" />
              </div>
            </div>
          </div>
          <div class="modal-footer">
            <button class="btn-cancel" @click="showAddModal = false">취소</button>
            <button class="btn-primary" :disabled="!addForm.selectedUser || !addForm.meetingId" @click="submitAdd">추가</button>
          </div>
        </div>
      </div>

      <!-- Edit modal -->
      <div v-if="editModal" class="modal-backdrop" @click.self="editModal = null">
        <div class="modal-box">
          <div class="modal-header">
            <span class="modal-title">구성원 정보 수정</span>
            <button class="modal-close-btn" @click="editModal = null">
              <svg width="14" height="14" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24"><path d="M6 18L18 6M6 6l12 12"/></svg>
            </button>
          </div>
          <div class="modal-body">
            <div class="edit-member-info">
              <div class="avatar" :style="{ background: avatarColor(editModal.name) }">{{ initials(editModal.name) }}</div>
              <div>
                <div style="font-size:14px;font-weight:700;color:#1e293b">{{ editModal.name || '이름없음' }}</div>
                <div style="font-size:12px;color:var(--text-muted)">{{ editModal.email }}</div>
              </div>
            </div>
            <div class="form-row-2" style="margin-top:14px">
              <div class="form-group">
                <label class="form-label">역할</label>
                <div class="role-options">
                  <label v-for="r in ROLES" :key="r.value" class="role-option" :class="{ selected: editModal.role === r.value }"
                    :style="editModal.role === r.value ? { background: r.bg, borderColor: r.border } : {}">
                    <input type="radio" :value="r.value" v-model="editModal.role" style="display:none" />
                    <span class="role-dot-sm" :style="{ background: r.color }"></span>
                    <span :style="{ color: editModal.role === r.value ? r.color : '#64748b', fontWeight: 600, fontSize: '13px' }">{{ r.label }}</span>
                  </label>
                </div>
              </div>
              <div class="form-group">
                <label class="form-label">직책</label>
                <input v-model="editModal.position" class="form-input-sm" placeholder="예: 팀장" />
              </div>
            </div>
          </div>
          <div class="modal-footer">
            <button class="btn-cancel" @click="editModal = null">취소</button>
            <button class="btn-primary" @click="saveEdit">저장</button>
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
  gap: 16px;
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
.plus-wrap { position:relative;flex-shrink:0; }
.create-meeting-btn { display:flex;align-items:center;gap:6px;height:34px;padding:0 14px;border-radius:8px;background:#3b82f6;border:none;color:#fff;font-size:13px;font-weight:600;cursor:pointer;transition:opacity .15s;white-space:nowrap; }
.create-meeting-btn:hover { opacity:.85; }

/* Meeting select */
.org-meeting-select { padding:6px 10px;border:1px solid rgba(255,255,255,.1);border-radius:8px;font-size:12px;font-weight:500;color:#e2e8f0;background:rgba(255,255,255,.06);outline:none;cursor:pointer;min-width:120px; }
.org-meeting-select option { background:#1e293b;color:#f1f5f9; }

/* Role chips */
.org-role-chips { display:flex;gap:6px;flex-wrap:wrap; }
.org-chip { display:flex;align-items:center;gap:5px;padding:4px 10px;border-radius:20px;border:1px solid rgba(255,255,255,.1);background:rgba(255,255,255,.06);color:#64748b;font-size:12px;font-weight:500;cursor:pointer;transition:all .15s;white-space:nowrap; }
.org-chip:hover { color:#94a3b8;border-color:rgba(255,255,255,.2); }
.org-chip.active { background:rgba(96,165,250,.15);border-color:rgba(96,165,250,.4);color:#93c5fd;font-weight:700; }
.org-chip-count { font-size:13px;font-weight:800; }

/* Day-mode overrides – identical to ArchivePage */
.day-mode .archive-header { background:#eef2ff;border-bottom-color:#e2e8f0; }
.day-mode .archive-title { color:#1e293b; }
.day-mode .search-input { background:rgba(255,255,255,.6);border-color:#e2e8f0;color:#1e293b; }
.day-mode .search-input::placeholder { color:#94a3b8; }
.day-mode .search-icon { color:#94a3b8; }
.day-mode .org-meeting-select { background:rgba(255,255,255,.6);border-color:#e2e8f0;color:#1e293b; }
.day-mode .org-meeting-select option { background:#fff;color:#1e293b; }
.day-mode .org-chip { background:#f1f5f9;border-color:#e2e8f0;color:#475569; }
.day-mode .org-chip:hover { border-color:#94a3b8; }
.day-mode .org-chip.active { background:#dbeafe;border-color:#93c5fd;color:#1d4ed8; }

/* Table */
.table-wrap {
  background: #fff;
  border: 1px solid var(--border);
  border-radius: 12px;
  overflow: hidden;
  flex: 1;
  overflow-y: auto;
}
.table-loading {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 48px;
}
.member-table {
  width: 100%;
  border-collapse: collapse;
}
.member-table thead th {
  padding: 11px 16px;
  font-size: 12px;
  font-weight: 700;
  color: #64748b;
  text-transform: uppercase;
  letter-spacing: .04em;
  background: #f8fafc;
  border-bottom: 1px solid var(--border);
  text-align: left;
  white-space: nowrap;
}
.member-row {
  border-bottom: 1px solid #f1f5f9;
  transition: background .1s;
}
.member-row:last-child { border-bottom: none; }
.member-row:hover { background: #fafbff; }
.member-row td { padding: 12px 16px; font-size: 13px; vertical-align: middle; }

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
.member-name-text { font-weight: 600; color: #1e293b; }

.cell-role { color: #475569; font-size: 12px; font-weight: 600; white-space: nowrap; }
.cell-muted { color: #475569; }
.cell-meetings { display: flex; flex-wrap: wrap; align-items: center; gap: 4px; }
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
}
.meeting-more-btn:hover { color: #3b82f6; }

.action-btns { display: flex; gap: 4px; justify-content: flex-end; }
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

/* Modal */
.modal-backdrop {
  position: fixed;
  inset: 0;
  background: rgba(0,0,0,.4);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}
.modal-box {
  background: #fff;
  border-radius: 16px;
  width: 420px;
  max-width: 92vw;
  box-shadow: 0 20px 60px rgba(0,0,0,.2);
  overflow: hidden;
}
.modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 18px 20px 14px;
  border-bottom: 1px solid var(--border);
}
.modal-title { font-size: 15px; font-weight: 700; color: #1e293b; }
.modal-close-btn {
  width: 28px;
  height: 28px;
  border-radius: 6px;
  border: none;
  background: #f1f5f9;
  color: #64748b;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
}
.modal-body { padding: 16px 20px; display: flex; flex-direction: column; gap: 12px; }
.modal-footer {
  display: flex;
  gap: 8px;
  justify-content: flex-end;
  padding: 12px 20px 16px;
  border-top: 1px solid var(--border);
}

.form-group { display: flex; flex-direction: column; gap: 5px; }
.form-label { font-size: 12px; font-weight: 700; color: #475569; text-transform: uppercase; letter-spacing: .04em; }
.form-select-sm, .form-input-sm {
  padding: 8px 10px;
  border: 1px solid var(--border);
  border-radius: 8px;
  font-size: 13px;
  background: #f8fafc;
  outline: none;
  width: 100%;
}
.form-select-sm:focus, .form-input-sm:focus { border-color: var(--primary); background: #fff; }
.form-row-2 { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
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

.btn-cancel {
  padding: 8px 16px;
  border-radius: 8px;
  border: 1px solid var(--border);
  background: #fff;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  color: #64748b;
}
</style>
