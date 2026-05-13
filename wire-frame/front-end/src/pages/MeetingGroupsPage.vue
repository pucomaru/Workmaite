<script setup>
import { ref, computed } from 'vue'
import { useMeetingsStore } from '../stores/meetings'
import { useAuthStore } from '../stores/auth'
import api from '../api'

const meetingsStore = useMeetingsStore()
const authStore = useAuthStore()

const search = ref('')
const expandedId = ref(null)

// Demo members for each group
const DEMO_GROUPS = [
  {
    id: 'demo-1', title: '전략기획위원회',
    members: [
      { id: 1, name: '김철수', role: 'chair', position: '전무이사', email: 'cskim@corp.kr', joinedAt: '2024-01-10' },
      { id: 2, name: '이영희', role: 'secretary', position: '부장', email: 'yhlee@corp.kr', joinedAt: '2024-01-10' },
      { id: 3, name: '박민준', role: 'member', position: '차장', email: 'mjpark@corp.kr', joinedAt: '2024-02-01' },
      { id: 4, name: '최지수', role: 'member', position: '과장', email: 'jschoi@corp.kr', joinedAt: '2024-03-05' },
    ],
  },
  {
    id: 'demo-2', title: '운영위원회',
    members: [
      { id: 5, name: '최지영', role: 'chair', position: '이사', email: 'jychoi@corp.kr', joinedAt: '2024-01-15' },
      { id: 2, name: '이영희', role: 'secretary', position: '부장', email: 'yhlee@corp.kr', joinedAt: '2024-01-15' },
      { id: 6, name: '한소희', role: 'observer', position: '대리', email: 'shhan@corp.kr', joinedAt: '2024-04-01' },
    ],
  },
  {
    id: 'demo-3', title: '개발팀 주간회의',
    members: [
      { id: 7, name: '정도현', role: 'chair', position: '팀장', email: 'dhjung@corp.kr', joinedAt: '2024-02-01' },
      { id: 8, name: '한소희', role: 'secretary', position: '선임연구원', email: 'shhan@corp.kr', joinedAt: '2024-02-01' },
      { id: 9, name: '오세진', role: 'member', position: '연구원', email: 'sjoh@corp.kr', joinedAt: '2024-03-10' },
    ],
  },
  {
    id: 'demo-4', title: '마케팅 전략회의',
    members: [
      { id: 10, name: '윤재원', role: 'chair', position: '팀장', email: 'jwryn@corp.kr', joinedAt: '2024-02-15' },
      { id: 3, name: '박민준', role: 'member', position: '차장', email: 'mjpark@corp.kr', joinedAt: '2024-02-15' },
    ],
  },
  {
    id: 'demo-5', title: '인사위원회',
    members: [
      { id: 1, name: '김철수', role: 'chair', position: '전무이사', email: 'cskim@corp.kr', joinedAt: '2024-01-20' },
      { id: 11, name: '정수현', role: 'secretary', position: '인사팀장', email: 'shjung@corp.kr', joinedAt: '2024-01-20' },
      { id: 12, name: '이도연', role: 'observer', position: '노무사', email: 'dylee@corp.kr', joinedAt: '2024-05-01' },
    ],
  },
]

// Member state per group (local mutations for demo)
const localMembers = ref({})

function getMembers(groupId) {
  if (localMembers.value[groupId]) return localMembers.value[groupId]
  const demo = DEMO_GROUPS.find(g => g.id === groupId)
  return demo ? demo.members : []
}

const groups = computed(() => {
  const fromStore = meetingsStore.meetings.map(m => ({ id: m.id, title: m.title }))
  const base = fromStore.length > 0 ? fromStore : DEMO_GROUPS.map(g => ({ id: g.id, title: g.title }))
  const q = search.value.trim().toLowerCase()
  return q ? base.filter(g => g.title.toLowerCase().includes(q)) : base
})

const ROLE_MAP = { chair: '의장', secretary: '간사', member: '위원', observer: '참관' }
const ROLE_COLOR = { chair: '#3b82f6', secretary: '#10b981', member: '#64748b', observer: '#f59e0b' }
const ROLE_BG = { chair: '#eff6ff', secretary: '#ecfdf5', member: '#f1f5f9', observer: '#fffbeb' }

// Add member modal
const showAddModal = ref(false)
const addGroupId = ref(null)
const addForm = ref({ name: '', email: '', role: 'member', position: '' })
const adding = ref(false)

function openAddModal(groupId) {
  addGroupId.value = groupId
  addForm.value = { name: '', email: '', role: 'member', position: '' }
  showAddModal.value = true
}

function doAddMember() {
  if (!addForm.value.name.trim()) return
  adding.value = true
  const gid = addGroupId.value
  if (!localMembers.value[gid]) {
    localMembers.value[gid] = [...getMembers(gid)]
  }
  localMembers.value[gid].push({
    id: Date.now(),
    name: addForm.value.name,
    email: addForm.value.email,
    role: addForm.value.role,
    position: addForm.value.position,
    joinedAt: new Date().toISOString().slice(0, 10),
  })
  adding.value = false
  showAddModal.value = false
}

function removeMember(groupId, memberId) {
  if (!confirm('이 멤버를 제거하시겠습니까?')) return
  if (!localMembers.value[groupId]) {
    localMembers.value[groupId] = [...getMembers(groupId)]
  }
  localMembers.value[groupId] = localMembers.value[groupId].filter(m => m.id !== memberId)
}

function changeRole(groupId, memberId, newRole) {
  if (!localMembers.value[groupId]) {
    localMembers.value[groupId] = [...getMembers(groupId)]
  }
  const m = localMembers.value[groupId].find(m => m.id === memberId)
  if (m) m.role = newRole
}

function formatDate(d) {
  if (!d) return '-'
  return new Date(d).toLocaleDateString('ko-KR', { year: 'numeric', month: 'short', day: 'numeric' })
}
</script>

<template>
  <div class="mg-page">
    <!-- Header -->
    <div class="mg-header">
      <div class="mg-title-wrap">
        <h1 class="mg-title">📋 회의체 관리</h1>
        <p class="mg-desc">회의체별 구성원을 관리하세요</p>
      </div>
      <div class="mg-search-wrap">
        <svg class="mg-search-icon" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><circle cx="11" cy="11" r="8"/><path d="M21 21l-4.35-4.35"/></svg>
        <input v-model="search" class="mg-search" placeholder="회의체 검색..." />
      </div>
      <div class="mg-count-badge">{{ groups.length }}개 회의체</div>
    </div>

    <!-- Group list -->
    <div class="mg-body">
      <div v-if="!groups.length" class="mg-empty">검색 결과가 없습니다.</div>

      <div v-for="g in groups" :key="g.id" class="mg-group">
        <!-- Group header (accordion trigger) -->
        <div class="mg-group-header" @click="expandedId = expandedId === g.id ? null : g.id">
          <div class="mg-group-left">
            <div class="mg-group-dot"></div>
            <span class="mg-group-title">{{ g.title }}</span>
            <span class="mg-member-count">{{ getMembers(g.id).length }}명</span>
          </div>
          <div class="mg-group-right">
            <button class="mg-add-btn" @click.stop="openAddModal(g.id)">
              <svg width="12" height="12" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24"><path d="M12 4v16m8-8H4"/></svg>
              멤버 추가
            </button>
            <svg class="mg-chevron" :class="{ open: expandedId === g.id }" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M19 9l-7 7-7-7"/></svg>
          </div>
        </div>

        <!-- Member table -->
        <Transition name="group-expand">
          <div v-if="expandedId === g.id" class="mg-member-wrap">
            <div v-if="!getMembers(g.id).length" class="mg-no-members">구성원이 없습니다. 멤버를 추가하세요.</div>
            <table v-else class="mg-table">
              <thead>
                <tr>
                  <th>이름</th>
                  <th>역할</th>
                  <th>직책</th>
                  <th>이메일</th>
                  <th>가입일</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="m in getMembers(g.id)" :key="m.id">
                  <td>
                    <div class="mg-member-name-cell">
                      <div class="mg-avatar">{{ m.name[0] }}</div>
                      <span class="mg-name">{{ m.name }}</span>
                    </div>
                  </td>
                  <td>
                    <select class="mg-role-select"
                      :style="{ background: ROLE_BG[m.role], color: ROLE_COLOR[m.role] }"
                      :value="m.role"
                      @change="changeRole(g.id, m.id, $event.target.value)">
                      <option v-for="(label, val) in ROLE_MAP" :key="val" :value="val">{{ label }}</option>
                    </select>
                  </td>
                  <td class="mg-td-muted">{{ m.position || '-' }}</td>
                  <td class="mg-td-muted">{{ m.email || '-' }}</td>
                  <td class="mg-td-muted">{{ formatDate(m.joinedAt) }}</td>
                  <td>
                    <button class="mg-remove-btn" @click="removeMember(g.id, m.id)" title="제거">
                      <svg width="12" height="12" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24"><path d="M18 6L6 18M6 6l12 12"/></svg>
                    </button>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </Transition>
      </div>
    </div>

    <!-- Add member modal -->
    <Teleport to="body">
      <div v-if="showAddModal" class="modal-backdrop" @click.self="showAddModal=false">
        <div class="modal-box">
          <div class="modal-header">
            <span class="modal-title">멤버 추가</span>
            <button class="modal-close" @click="showAddModal=false">✕</button>
          </div>
          <div class="modal-body">
            <div class="modal-field">
              <label>이름 <span class="req">*</span></label>
              <input v-model="addForm.name" class="modal-input" placeholder="홍길동" />
            </div>
            <div class="modal-field">
              <label>이메일</label>
              <input v-model="addForm.email" class="modal-input" placeholder="hong@corp.kr" type="email" />
            </div>
            <div class="modal-field">
              <label>직책</label>
              <input v-model="addForm.position" class="modal-input" placeholder="부장" />
            </div>
            <div class="modal-field">
              <label>역할</label>
              <select v-model="addForm.role" class="modal-input modal-select">
                <option v-for="(label, val) in ROLE_MAP" :key="val" :value="val">{{ label }}</option>
              </select>
            </div>
          </div>
          <div class="modal-footer">
            <button class="btn-cancel" @click="showAddModal=false">취소</button>
            <button class="btn-confirm" :disabled="!addForm.name.trim() || adding" @click="doAddMember">
              {{ adding ? '추가 중...' : '추가' }}
            </button>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<style scoped>
.mg-page { display:flex;flex-direction:column;gap:0;height:100%;overflow:hidden; }

/* Header */
.mg-header { display:flex;align-items:center;gap:12px;padding:16px 20px;border-bottom:1px solid var(--border);flex-shrink:0;flex-wrap:wrap; }
.mg-title-wrap { flex-shrink:0; }
.mg-title { font-size:18px;font-weight:700;color:var(--primary);margin:0; }
.mg-desc { font-size:11px;color:var(--text-muted);margin:0; }
.mg-search-wrap { position:relative;flex:1;min-width:160px;max-width:320px; }
.mg-search-icon { position:absolute;left:9px;top:50%;transform:translateY(-50%);color:var(--text-muted);pointer-events:none; }
.mg-search { width:100%;padding:7px 10px 7px 30px;border:1px solid var(--border);border-radius:8px;font-size:13px;outline:none;background:#f8fafc; }
.mg-search:focus { border-color:var(--primary); }
.mg-count-badge { font-size:12px;font-weight:600;color:var(--text-muted);background:#f1f5f9;border-radius:99px;padding:4px 12px;flex-shrink:0; }

/* Body */
.mg-body { flex:1;overflow-y:auto;padding:16px 20px;display:flex;flex-direction:column;gap:10px; }
.mg-empty { text-align:center;padding:60px;color:var(--text-muted);font-size:14px; }

/* Group accordion */
.mg-group { border:1px solid var(--border);border-radius:10px;overflow:hidden;background:#fff; }
.mg-group-header { display:flex;align-items:center;justify-content:space-between;padding:12px 16px;cursor:pointer;transition:background .15s;user-select:none; }
.mg-group-header:hover { background:#f8fafc; }
.mg-group-left { display:flex;align-items:center;gap:10px; }
.mg-group-dot { width:8px;height:8px;background:var(--primary);border-radius:50%;flex-shrink:0; }
.mg-group-title { font-size:14px;font-weight:600;color:#1e293b; }
.mg-member-count { font-size:11px;font-weight:500;background:#eff6ff;color:var(--primary);border-radius:99px;padding:2px 9px; }
.mg-group-right { display:flex;align-items:center;gap:10px; }
.mg-add-btn { display:flex;align-items:center;gap:4px;padding:5px 12px;border-radius:7px;border:1px solid var(--primary);background:#eff6ff;color:var(--primary);font-size:12px;font-weight:600;cursor:pointer;transition:all .15s; }
.mg-add-btn:hover { background:var(--primary);color:#fff; }
.mg-chevron { color:var(--text-muted);transition:transform .2s;flex-shrink:0; }
.mg-chevron.open { transform:rotate(180deg); }

/* Member table */
.mg-member-wrap { border-top:1px solid var(--border);overflow:hidden; }
.mg-no-members { padding:20px;text-align:center;color:var(--text-muted);font-size:13px; }
.mg-table { width:100%;border-collapse:collapse;font-size:13px; }
.mg-table thead tr { background:#f8fafc; }
.mg-table th { padding:9px 12px;text-align:left;font-size:11px;font-weight:600;color:var(--text-muted);text-transform:uppercase;letter-spacing:.04em;border-bottom:1px solid var(--border); }
.mg-table td { padding:10px 12px;border-bottom:1px solid #f1f5f9;vertical-align:middle; }
.mg-table tbody tr:last-child td { border-bottom:none; }
.mg-table tbody tr:hover { background:#f8fafc; }
.mg-member-name-cell { display:flex;align-items:center;gap:8px; }
.mg-avatar { width:28px;height:28px;border-radius:50%;background:var(--primary);color:#fff;font-size:11px;font-weight:700;display:flex;align-items:center;justify-content:center;flex-shrink:0; }
.mg-name { font-weight:600;color:#1e293b; }
.mg-role-select { border-radius:99px;border:none;padding:3px 10px;font-size:12px;font-weight:600;cursor:pointer;outline:none;appearance:none;text-align:center; }
.mg-td-muted { color:var(--text-muted); }
.mg-remove-btn { width:24px;height:24px;border-radius:5px;border:none;background:#fef2f2;color:#dc2626;cursor:pointer;display:flex;align-items:center;justify-content:center;transition:all .15s; }
.mg-remove-btn:hover { background:#dc2626;color:#fff; }

/* Accordion transition */
.group-expand-enter-active { transition:max-height .25s ease,opacity .2s; }
.group-expand-leave-active { transition:max-height .2s ease,opacity .15s; }
.group-expand-enter-from,.group-expand-leave-to { max-height:0;opacity:0; }
.group-expand-enter-to,.group-expand-leave-from { max-height:600px;opacity:1; }

/* Modal */
.modal-backdrop { position:fixed;inset:0;background:rgba(0,0,0,.4);display:flex;align-items:center;justify-content:center;z-index:1000; }
.modal-box { background:#fff;border-radius:14px;width:400px;max-width:92vw;box-shadow:0 16px 48px rgba(0,0,0,.2); }
.modal-header { display:flex;align-items:center;justify-content:space-between;padding:16px 20px 12px;border-bottom:1px solid var(--border); }
.modal-title { font-size:15px;font-weight:700;color:#1e293b; }
.modal-close { background:none;border:none;cursor:pointer;color:var(--text-muted);font-size:16px;line-height:1; }
.modal-body { padding:16px 20px;display:flex;flex-direction:column;gap:12px; }
.modal-field { display:flex;flex-direction:column;gap:4px; }
.modal-field label { font-size:12px;font-weight:600;color:#475569; }
.req { color:#ef4444; }
.modal-input { padding:8px 10px;border:1px solid var(--border);border-radius:8px;font-size:13px;outline:none;font-family:inherit; }
.modal-input:focus { border-color:var(--primary); }
.modal-select { cursor:pointer; }
.modal-footer { display:flex;gap:8px;justify-content:flex-end;padding:12px 20px 16px;border-top:1px solid var(--border); }
.btn-cancel { padding:8px 16px;border-radius:8px;border:1px solid var(--border);background:#fff;font-size:13px;font-weight:600;cursor:pointer;color:#64748b; }
.btn-confirm { padding:8px 20px;border-radius:8px;border:none;background:var(--primary);color:#fff;font-size:13px;font-weight:700;cursor:pointer; }
.btn-confirm:disabled { opacity:.5;cursor:not-allowed; }
</style>
