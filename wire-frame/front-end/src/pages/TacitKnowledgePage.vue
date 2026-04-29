<script setup>
import { ref, onMounted, computed } from 'vue'
import api from '../api'

const tab = ref('proposals')
const proposals = ref([])
const globalKb = ref([])
const meetingKb = ref([])
const events = ref([])
const meetings = ref([])
const selectedMeeting = ref('')
const editingKb = ref(null)
const editContent = ref('')
const showAddGlobal = ref(false)
const newKb = ref({ category: 'report_standard', title: '', content: '' })
const reviewingId = ref(null)
const editAcceptContent = ref('')
const loading = ref(false)

const categories = [
  { value: 'report_standard', label: '📋 보고서 기준' },
  { value: 'agenda_standard', label: '📌 아젠다 기준' },
  { value: 'todo_standard', label: '✅ 과제 기준' },
  { value: 'meeting_standard', label: '🎙 회의 기준' },
]

const pendingCount = computed(() => proposals.value.filter(p => p.status === 'pending').length)

onMounted(async () => {
  await Promise.all([loadProposals(), loadGlobal(), loadMeetings(), loadEvents()])
})

async function loadProposals() {
  const { data } = await api.get('/api/tacit-knowledge/proposals')
  proposals.value = data
}

async function loadGlobal() {
  const { data } = await api.get('/api/tacit-knowledge/global')
  globalKb.value = data
}

async function loadMeetings() {
  const { data } = await api.get('/api/meetings')
  meetings.value = data
}

async function loadMeetingKb() {
  if (!selectedMeeting.value) { meetingKb.value = []; return }
  const { data } = await api.get(`/api/tacit-knowledge/meeting/${selectedMeeting.value}`)
  meetingKb.value = data
}

async function loadEvents() {
  const { data } = await api.get('/api/tacit-knowledge/events')
  events.value = data
}

async function reviewProposal(id, action, content = null) {
  loading.value = true
  try {
    await api.patch(`/api/tacit-knowledge/proposals/${id}`, { action, final_content: content })
    await loadProposals()
    await loadGlobal()
    reviewingId.value = null
  } finally {
    loading.value = false
  }
}

async function saveKb(kb) {
  await api.patch(`/api/tacit-knowledge/global/${kb.id}`, { content: editContent.value })
  await loadGlobal()
  editingKb.value = null
}

async function addGlobal() {
  if (!newKb.value.title.trim() || !newKb.value.content.trim()) return
  await api.post('/api/tacit-knowledge/global', newKb.value)
  await loadGlobal()
  showAddGlobal.value = false
  newKb.value = { category: 'report_standard', title: '', content: '' }
}

function startEdit(kb) {
  editingKb.value = kb.id
  editContent.value = kb.content
}

function formatDate(d) {
  if (!d) return ''
  return new Date(d).toLocaleDateString('ko-KR')
}

function statusCls(s) {
  const m = { pending: 'badge-warning', accepted: 'badge-success', rejected: 'badge-danger', edited_and_accepted: 'badge-success' }
  return m[s] || 'badge-muted'
}
function statusLabel(s) {
  const m = { pending: '검토 대기', accepted: '수락됨', rejected: '거절됨', edited_and_accepted: '편집 후 수락' }
  return m[s] || s
}

function catLabel(c) {
  return categories.find(x => x.value === c)?.label || c
}
</script>

<template>
  <div class="tacit-page">
    <div class="page-header">
      <div>
        <h2 style="font-size:20px;font-weight:700;margin-bottom:4px">암묵지 관리</h2>
        <p style="color:var(--text-muted);font-size:13px">혜안 AI가 학습한 조직 운영 기준을 검토하고 관리합니다.</p>
      </div>
    </div>

    <div class="tabs">
      <button class="tab-btn" :class="{ active: tab==='proposals' }" @click="tab='proposals'">
        검토 대기 중
        <span v-if="pendingCount" class="badge badge-danger" style="margin-left:6px">{{ pendingCount }}</span>
      </button>
      <button class="tab-btn" :class="{ active: tab==='global' }" @click="tab='global'">글로벌 기준</button>
      <button class="tab-btn" :class="{ active: tab==='meeting' }" @click="tab='meeting'; loadMeetingKb()">회의체별 기준</button>
      <button class="tab-btn" :class="{ active: tab==='events' }" @click="tab='events'">학습 로그</button>
    </div>

    <!-- Tab 1: Proposals -->
    <div v-if="tab === 'proposals'">
      <div v-if="!proposals.filter(p => p.status === 'pending').length" class="empty-state">
        <p>검토 대기 중인 제안이 없습니다.</p>
      </div>
      <div class="proposal-list">
        <div v-for="p in proposals.filter(p2 => p2.status === 'pending')" :key="p.id" class="proposal-card card fade-in">
          <div class="proposal-header">
            <div style="display:flex;align-items:center;gap:8px">
              <span class="badge badge-primary">{{ p.scope === 'global' ? '글로벌' : '회의체' }}</span>
              <span style="font-size:11px;color:var(--text-muted)">{{ catLabel(p.category) }}</span>
            </div>
            <span style="font-size:11px;color:var(--text-muted)">{{ formatDate(p.created_at) }}</span>
          </div>
          <div style="font-weight:600;font-size:14px;margin:8px 0">{{ p.title }}</div>

          <div v-if="p.evidence_summary" class="evidence-box">
            <div style="font-size:12px;font-weight:600;color:var(--primary);margin-bottom:4px">📊 제안 근거</div>
            <div style="font-size:13px;line-height:1.5">{{ p.evidence_summary }}</div>
          </div>

          <div v-if="p.diff_summary" class="diff-box">
            <div style="font-size:12px;font-weight:600;margin-bottom:4px">📝 변경 내용</div>
            <div style="font-size:13px;white-space:pre-wrap">{{ p.diff_summary }}</div>
          </div>

          <div class="proposed-content">
            <div style="font-size:12px;font-weight:600;margin-bottom:4px">제안 내용</div>
            <div style="font-size:13px;white-space:pre-wrap;line-height:1.6">{{ p.proposed_content }}</div>
          </div>

          <!-- Edit accept form -->
          <div v-if="reviewingId === p.id" class="edit-form">
            <textarea v-model="editAcceptContent" class="form-input form-textarea" style="min-height:120px" />
            <div style="display:flex;gap:8px;margin-top:8px">
              <button class="btn btn-success btn-sm" @click="reviewProposal(p.id, 'edit_accept', editAcceptContent)">최종 확정</button>
              <button class="btn btn-ghost btn-sm" @click="reviewingId=null">취소</button>
            </div>
          </div>

          <div v-else class="proposal-actions">
            <button class="btn btn-success btn-sm" @click="reviewProposal(p.id, 'accept')">수락</button>
            <button class="btn btn-danger btn-sm" @click="reviewProposal(p.id, 'reject')">거절</button>
            <button class="btn btn-outline btn-sm" @click="reviewingId=p.id; editAcceptContent=p.proposed_content">편집 후 수락</button>
          </div>
        </div>
      </div>
    </div>

    <!-- Tab 2: Global -->
    <div v-else-if="tab === 'global'">
      <div style="display:flex;justify-content:flex-end;margin-bottom:16px">
        <button class="btn btn-primary btn-sm" @click="showAddGlobal = true">+ 기준 직접 추가</button>
      </div>

      <div v-if="showAddGlobal" class="card" style="padding:16px;margin-bottom:16px">
        <div style="font-weight:600;margin-bottom:12px">새 글로벌 기준 추가</div>
        <div class="form-group" style="margin-bottom:10px">
          <label class="form-label">카테고리</label>
          <select v-model="newKb.category" class="form-input">
            <option v-for="c in categories" :key="c.value" :value="c.value">{{ c.label }}</option>
          </select>
        </div>
        <div class="form-group" style="margin-bottom:10px">
          <label class="form-label">제목</label>
          <input v-model="newKb.title" class="form-input" placeholder="기준 제목" />
        </div>
        <div class="form-group" style="margin-bottom:12px">
          <label class="form-label">내용</label>
          <textarea v-model="newKb.content" class="form-input form-textarea" placeholder="기준 내용 (마크다운)" style="min-height:100px" />
        </div>
        <div style="display:flex;gap:8px">
          <button class="btn btn-primary btn-sm" @click="addGlobal">추가</button>
          <button class="btn btn-ghost btn-sm" @click="showAddGlobal=false">취소</button>
        </div>
      </div>

      <div v-for="cat in categories" :key="cat.value">
        <div v-if="globalKb.filter(k => k.category === cat.value).length">
          <div class="cat-header">{{ cat.label }}</div>
          <div class="kb-list">
            <div v-for="kb in globalKb.filter(k => k.category === cat.value)" :key="kb.id" class="kb-card card">
              <div class="kb-card-header">
                <div>
                  <div style="font-weight:600;font-size:14px">{{ kb.title }}</div>
                  <div style="font-size:11px;color:var(--text-muted)">v{{ kb.version }} · {{ formatDate(kb.updated_at) }}</div>
                </div>
                <button class="btn btn-outline btn-sm" @click="startEdit(kb)">편집</button>
              </div>
              <div v-if="editingKb !== kb.id" style="font-size:13px;white-space:pre-wrap;line-height:1.6;margin-top:8px">{{ kb.content }}</div>
              <div v-else>
                <textarea v-model="editContent" class="form-input form-textarea" style="min-height:100px;margin-top:8px" />
                <div style="display:flex;gap:8px;margin-top:8px">
                  <button class="btn btn-primary btn-sm" @click="saveKb(kb)">저장</button>
                  <button class="btn btn-ghost btn-sm" @click="editingKb=null">취소</button>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
      <div v-if="!globalKb.length" class="empty-state"><p>등록된 글로벌 기준이 없습니다.</p></div>
    </div>

    <!-- Tab 3: Meeting -->
    <div v-else-if="tab === 'meeting'">
      <div style="margin-bottom:16px;display:flex;gap:12px;align-items:center">
        <select v-model="selectedMeeting" class="form-input" style="width:240px" @change="loadMeetingKb">
          <option value="">회의체 선택...</option>
          <option v-for="m in meetings" :key="m.id" :value="m.id">{{ m.title }}</option>
        </select>
      </div>
      <div v-if="!selectedMeeting" class="empty-state"><p>회의체를 선택하세요.</p></div>
      <div v-else-if="!meetingKb.length" class="empty-state"><p>이 회의체에 커스텀 기준이 없습니다. 글로벌 기준이 적용됩니다.</p></div>
      <div v-else class="kb-list">
        <div v-for="kb in meetingKb" :key="kb.id" class="kb-card card">
          <div style="font-weight:600;font-size:14px;margin-bottom:4px">{{ kb.title }}</div>
          <div style="font-size:13px;white-space:pre-wrap;line-height:1.6">{{ kb.content }}</div>
        </div>
      </div>
    </div>

    <!-- Tab 4: Events -->
    <div v-else-if="tab === 'events'">
      <div class="events-list">
        <div v-if="!events.length" class="empty-state"><p>학습 로그가 없습니다.</p></div>
        <div v-for="e in events" :key="e.id" class="event-row">
          <span class="event-type badge badge-primary">{{ e.event_type }}</span>
          <span style="font-size:13px;flex:1">
            {{ e.payload ? JSON.stringify(e.payload).slice(0,80) : '-' }}
          </span>
          <span style="font-size:11px;color:var(--text-muted)">{{ formatDate(e.created_at) }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.tacit-page { max-width: 900px; margin: 0 auto; }
.page-header { margin-bottom: 20px; }
.proposal-list { display: flex; flex-direction: column; gap: 16px; }
.proposal-card { padding: 20px; display: flex; flex-direction: column; gap: 12px; }
.proposal-header { display: flex; justify-content: space-between; align-items: center; }
.evidence-box { background: #eff6ff; border: 1px solid #bfdbfe; border-radius: 6px; padding: 12px; }
.diff-box { background: #f0fdf4; border: 1px solid #bbf7d0; border-radius: 6px; padding: 12px; }
.proposed-content { background: #f8fafc; border: 1px solid var(--border); border-radius: 6px; padding: 12px; }
.proposal-actions { display: flex; gap: 8px; }
.cat-header { font-size: 14px; font-weight: 600; margin: 20px 0 10px; color: var(--primary); }
.kb-list { display: flex; flex-direction: column; gap: 10px; }
.kb-card { padding: 16px; }
.kb-card-header { display: flex; justify-content: space-between; align-items: flex-start; }
.events-list { display: flex; flex-direction: column; gap: 8px; }
.event-row { display: flex; align-items: center; gap: 12px; padding: 10px 14px; background: #f8fafc; border-radius: 6px; border: 1px solid var(--border); }
.event-type { font-size: 11px; }
.edit-form { background: #f8fafc; border-radius: 8px; padding: 12px; }
</style>
