<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import api from '../api'
import { useMeetingsStore } from '../stores/meetings'

const meetingsStore = useMeetingsStore()

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
const DEMO = [
  { id: 1, name: '김민준', role: 'chair',     position: '전략기획부장',  email: 'minjun@company.com',  meetingTitle: '회의체 운영 위원회2', meetingId: 1, joinedAt: '2026-01-10' },
  { id: 2, name: '이서연', role: 'secretary',  position: '전략기획팀장',  email: 'seoyeon@company.com', meetingTitle: '회의체 운영 위원회2', meetingId: 1, joinedAt: '2026-01-10' },
  { id: 3, name: '박도윤', role: 'member',    position: '경영기획 수석', email: 'doyun@company.com',   meetingTitle: '회의체 운영 위원회2', meetingId: 1, joinedAt: '2026-01-15' },
  { id: 4, name: '최수아', role: 'member',    position: '전략기획 선임', email: 'sua@company.com',     meetingTitle: '회의체 운영 위원회2', meetingId: 1, joinedAt: '2026-01-15' },
  { id: 5, name: '정지훈', role: 'member',    position: '경영혁신 선임', email: 'jihoon@company.com',  meetingTitle: '회의체 운영 위원회2', meetingId: 1, joinedAt: '2026-02-01' },
  { id: 6, name: '오유진', role: 'observer',  position: '재무팀 과장',   email: 'yujin@company.com',   meetingTitle: '회의체 운영 위원회2', meetingId: 1, joinedAt: '2026-02-10' },
  { id: 7, name: '한태양', role: 'chair',     position: 'CTO',          email: 'taeyang@company.com', meetingTitle: '경영전략 위원회',    meetingId: 2, joinedAt: '2026-03-01' },
  { id: 8, name: '신지영', role: 'secretary',  position: 'IT기획 팀장',   email: 'jiyoung@company.com', meetingTitle: '경영전략 위원회',    meetingId: 2, joinedAt: '2026-03-01' },
  { id: 9, name: '윤재호', role: 'member',    position: '개발팀 수석',   email: 'jaeho@company.com',   meetingTitle: '경영전략 위원회',    meetingId: 2, joinedAt: '2026-03-05' },
  { id:10, name: '임수빈', role: 'member',    position: 'UX 선임',      email: 'subin@company.com',   meetingTitle: '경영전략 위원회',    meetingId: 2, joinedAt: '2026-03-05' },
]

async function fetchAllMembers() {
  loadingMembers.value = true
  try {
    const meetings = meetingsStore.meetings
    if (!meetings.length) { allMembers.value = DEMO; return }
    const results = []
    await Promise.all(meetings.map(async m => {
      try {
        const res = await api.get(`/api/meetings/${m.id}/members`)
        res.data.forEach(member => results.push({ ...member, meetingTitle: m.title, meetingId: m.id }))
      } catch {}
    }))
    allMembers.value = results.length ? results : DEMO
  } catch {
    allMembers.value = DEMO
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
  <div class="org-page">
    <!-- Page header -->
    <div class="page-header">
      <div class="header-left">
        <div class="page-icon">🏢</div>
        <div>
          <h1 class="page-title">조직 관리</h1>
          <p class="page-sub">회의체별 구성원, 역할(의장·간사·위원·참관)을 관리합니다.</p>
        </div>
      </div>
      <button class="btn-primary" @click="openAddModal">
        <svg width="14" height="14" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24"><path d="M16 21v-2a4 4 0 00-4-4H6a4 4 0 00-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M19 8v6M22 11h-6"/></svg>
        구성원 추가
      </button>
    </div>

    <!-- Filters -->
    <div class="filter-bar">
      <div class="filter-row">
        <select v-model="selectedMeetingId" class="meeting-select">
          <option value="all">전체 회의체</option>
          <option v-for="m in meetingsStore.meetings" :key="m.id" :value="String(m.id)">{{ m.title }}</option>
        </select>
        <div class="search-wrap">
          <svg class="search-icon-sm" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><circle cx="11" cy="11" r="8"/><path d="M21 21l-4.35-4.35"/></svg>
          <input v-model="searchQuery" class="search-input" placeholder="이름, 직책, 이메일 검색..." />
        </div>
        <button class="icon-btn" @click="fetchAllMembers" title="새로고침">
          <svg width="15" height="15" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M23 4v6h-6M1 20v-6h6"/><path d="M3.51 9a9 9 0 0114.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0020.49 15"/></svg>
        </button>
      </div>

      <!-- Role stats chips -->
      <div class="role-chips">
        <button class="role-chip" :class="{ active: activeRoleFilter === 'all' }" @click="activeRoleFilter = 'all'">
          <span class="chip-count">{{ baseCounts.all }}</span> 전체
        </button>
        <button v-for="r in ROLES" :key="r.value"
          class="role-chip" :class="{ active: activeRoleFilter === r.value }"
          :style="activeRoleFilter === r.value ? { background: r.bg, color: r.color, borderColor: r.border } : {}"
          @click="activeRoleFilter = r.value">
          <span class="chip-count">{{ baseCounts[r.value] || 0 }}</span> {{ r.label }}
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
            <th style="width:220px">이름</th>
            <th style="width:90px">역할</th>
            <th style="width:140px">직책</th>
            <th style="width:220px">이메일</th>
            <th>회의체</th>
            <th style="width:130px">참여일</th>
            <th style="width:72px"></th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="member in filteredMembers" :key="`${member.meetingId}-${member.id}`" class="member-row">
            <td>
              <div class="name-cell">
                <div class="avatar" :style="{ background: avatarColor(member.name) }">{{ initials(member.name) }}</div>
                <span class="member-name-text">{{ member.name || '이름없음' }}</span>
              </div>
            </td>
            <td>
              <span class="role-pill"
                :style="{ background: roleInfo(member.role).bg, color: roleInfo(member.role).color, borderColor: roleInfo(member.role).border }">
                {{ roleInfo(member.role).label }}
              </span>
            </td>
            <td class="cell-muted">{{ member.position || '-' }}</td>
            <td class="cell-muted">{{ member.email || '-' }}</td>
            <td class="cell-meeting">{{ member.meetingTitle || '-' }}</td>
            <td class="cell-muted">{{ formatDate(member.joinedAt || member.joined_at || member.created_at) }}</td>
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
          <tr v-if="!filteredMembers.length">
            <td colspan="7" class="empty-row">
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
  height: 100%;
  overflow: hidden;
}

/* Header */
.page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-shrink: 0;
}
.header-left { display: flex; align-items: center; gap: 12px; }
.page-icon { font-size: 28px; line-height: 1; }
.page-title { font-size: 22px; font-weight: 800; color: var(--primary); margin: 0 0 2px; }
.page-sub { font-size: 13px; color: var(--text-muted); margin: 0; }

.btn-primary {
  display: flex;
  align-items: center;
  gap: 7px;
  padding: 9px 18px;
  background: var(--primary);
  color: #fff;
  border: none;
  border-radius: 9px;
  font-size: 13px;
  font-weight: 700;
  cursor: pointer;
  transition: opacity .15s;
  flex-shrink: 0;
}
.btn-primary:hover { opacity: .88; }
.btn-primary:disabled { opacity: .5; cursor: not-allowed; }

/* Filter bar */
.filter-bar {
  background: #fff;
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 14px 16px;
  display: flex;
  flex-direction: column;
  gap: 12px;
  flex-shrink: 0;
}
.filter-row { display: flex; align-items: center; gap: 10px; }

.meeting-select {
  padding: 8px 12px;
  border: 1px solid var(--border);
  border-radius: 8px;
  font-size: 13px;
  font-weight: 500;
  color: #1e293b;
  background: #f8fafc;
  outline: none;
  cursor: pointer;
  min-width: 160px;
}
.meeting-select:focus { border-color: var(--primary); }

.search-wrap, .rel { flex: 1; position: relative; }
.search-icon-sm {
  position: absolute;
  left: 10px;
  top: 50%;
  transform: translateY(-50%);
  color: #94a3b8;
  pointer-events: none;
}
.search-input {
  width: 100%;
  padding: 8px 10px 8px 32px;
  border: 1px solid var(--border);
  border-radius: 8px;
  font-size: 13px;
  background: #f8fafc;
  outline: none;
}
.search-input:focus { border-color: var(--primary); background: #fff; }

.icon-btn {
  width: 36px;
  height: 36px;
  border-radius: 8px;
  border: 1px solid var(--border);
  background: #f8fafc;
  color: #64748b;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  flex-shrink: 0;
  transition: all .15s;
}
.icon-btn:hover { border-color: var(--primary); color: var(--primary); }

/* Role chips */
.role-chips { display: flex; gap: 8px; flex-wrap: wrap; }
.role-chip {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 14px;
  border-radius: 20px;
  border: 1px solid var(--border);
  background: #f8fafc;
  color: #64748b;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: all .15s;
}
.role-chip:hover { border-color: #94a3b8; }
.role-chip.active { font-weight: 700; }
.role-chip.active:not([style]) { background: #eff6ff; color: var(--primary); border-color: #bfdbfe; }
.chip-count { font-size: 15px; font-weight: 800; }

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

.role-pill {
  display: inline-flex;
  align-items: center;
  padding: 3px 10px;
  border-radius: 12px;
  border: 1px solid;
  font-size: 12px;
  font-weight: 700;
  white-space: nowrap;
}
.cell-muted { color: #475569; }
.cell-meeting { color: #64748b; font-size: 12px; }

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
