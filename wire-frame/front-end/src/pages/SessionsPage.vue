<script setup>
import { ref, onMounted, computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import api from '../api'
import { streamPost } from '../api'
import MeetingNav from '../components/MeetingNav.vue'
import AgentPanel from '../components/AgentPanel.vue'
import { useMeetingsStore } from '../stores/meetings'
import { useChatHistory } from '../composables/useChatHistory'
import araAvatar from '../assets/agents/ara.png'
import { marked } from 'marked'

const renderMd = (text) => marked.parse(text || '', { breaks: true })

const route = useRoute()
const router = useRouter()
const meetingsStore = useMeetingsStore()
const meetingId = computed(() => Number(route.params.meetingId))
const role = computed(() => meetingsStore.myRole)

const sessions = ref([])

const showMinutesModal = ref(false)
const selectedSession = ref(null)
const minutes = ref(null)

const editingId = ref(null)
const editForm = ref({ title: '', scheduled_at: '' })
const saving = ref(false)
const deleting = ref(null)

const showCreateModal = ref(false)
const createForm = ref({ title: '', scheduled_at: '' })
const creating = ref(false)

// ── 아라 ──────────────────────────────────────
const araInput = ref('')
const araLoading = ref(false)
const messagesEl = ref(null)
const { messages: araMessages, loadMessages, saveMessage, clearHistory } = useChatHistory('sessions', meetingId.value)

// 빠른 질문 목록
const quickQuestions = [
  '전체 회의를 요약해줘',
  '가장 최근 회의 내용 알려줘',
  '회의에서 결정된 사항 정리해줘',
  '아직 해결 안 된 과제가 있어?',
]

onMounted(async () => {
  await meetingsStore.fetchMeeting(meetingId.value)
  await meetingsStore.fetchRole(meetingId.value)
  await loadSessions()
  await loadMessages()
  if (araMessages.value.length === 0) {
    const greeting = '안녕하세요, 아라입니다! 🎤\n회의 전체 또는 특정 회의에 대해 자연어로 질문해보세요.\n예: "가장 최근 회의 요약해줘", "전체 회의에서 결정된 사항 정리해줘"'
    araMessages.value.push({ role: 'agent', content: greeting })
    saveMessage('agent', greeting)
  }
})

async function loadSessions() {
  const { data } = await api.get(`/api/meetings/${meetingId.value}/sessions`)
  sessions.value = data
}

async function createSession() {
  if (!createForm.value.title.trim() || creating.value) return
  creating.value = true
  try {
    await api.post(`/api/meetings/${meetingId.value}/sessions`, {
      title: createForm.value.title.trim(),
      scheduled_at: createForm.value.scheduled_at || null,
    })
    showCreateModal.value = false
    createForm.value = { title: '', scheduled_at: '' }
    await loadSessions()
  } finally {
    creating.value = false
  }
}

function startEdit(s) {
  editingId.value = s.id
  editForm.value = {
    title: s.title,
    scheduled_at: s.scheduled_at ? s.scheduled_at.slice(0, 16) : '',
  }
}

function cancelEdit() { editingId.value = null }

async function saveEdit(s) {
  if (!editForm.value.title.trim() || saving.value) return
  saving.value = true
  try {
    await api.patch(`/api/sessions/${s.id}`, {
      title: editForm.value.title.trim(),
      scheduled_at: editForm.value.scheduled_at || null,
    })
    editingId.value = null
    await loadSessions()
  } finally {
    saving.value = false
  }
}

async function deleteSession(s) {
  if (!confirm(`"${s.title}" 회의를 삭제하시겠습니까?\n삭제하면 회의록도 함께 삭제됩니다.`)) return
  deleting.value = s.id
  try {
    await api.delete(`/api/sessions/${s.id}`)
    await loadSessions()
  } finally {
    deleting.value = null
  }
}

async function viewMinutes(s) {
  selectedSession.value = s
  minutes.value = null
  showMinutesModal.value = true
  try {
    const { data } = await api.get(`/api/sessions/${s.id}/minutes`)
    minutes.value = data
  } catch {
    minutes.value = null
  }
}

async function joinRoom(s) {
  try {
    const { data } = await api.get(`/api/livekit/token/${meetingId.value}/${s.id}`)
    const url = router.resolve(`/meetings/${meetingId.value}/sessions/${s.id}/room`).href
    const params = new URLSearchParams({ lkToken: data.token, lkUrl: data.url })
    window.open(`${url}?${params.toString()}`, '_blank')
  } catch (e) {
    alert(e.response?.data?.detail || 'LiveKit 토큰 발급 실패')
  }
}

// ── 아라 전송 ─────────────────────────────────
async function sendAra() {
  if (!araInput.value.trim() || araLoading.value) return
  const text = araInput.value.trim()
  araMessages.value.push({ role: 'user', content: text })
  saveMessage('user', text)
  araInput.value = ''
  const agentMsg = { role: 'agent', content: '' }
  araMessages.value.push(agentMsg)
  araLoading.value = true
  await nextTick()
  scrollMessages()

  const history = araMessages.value.slice(0, -1).map(m => ({
    role: m.role === 'user' ? 'user' : 'assistant',
    content: m.content,
  }))
  await streamPost(
    '/api/agent/ara/sessions-chat',
    { meeting_id: meetingId.value, message: text, chat_history: history },
    (chunk) => {
      agentMsg.content += chunk
      scrollMessages()
    },
    () => {
      araLoading.value = false
      saveMessage('agent', agentMsg.content)
    },
  )
}

async function sendQuick(q) {
  araInput.value = q
  await sendAra()
}

function scrollMessages() {
  if (messagesEl.value) {
    messagesEl.value.scrollTop = messagesEl.value.scrollHeight
  }
}

import { nextTick } from 'vue'

function formatDate(d) {
  if (!d) return '일정 미정'
  return new Date(d).toLocaleString('ko-KR', {
    month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit',
  })
}
function statusLabel(s) {
  return { scheduled: '예정', ongoing: '진행중', ended: '종료' }[s] || s
}
function statusCls(s) {
  return { scheduled: 'badge-primary', ongoing: 'badge-warning', ended: 'badge-muted' }[s] || 'badge-muted'
}
</script>

<template>
  <div class="sessions-layout">
    <MeetingNav />

    <div class="sessions-body">
      <!-- 왼쪽: 아라 AgentPanel -->
      <AgentPanel
        :avatar="araAvatar"
        name="아라"
        name-en="Ara"
        subtitle="회의 요약 · 질의응답"
        :messages="araMessages"
        :loading="araLoading"
        :quick-questions="quickQuestions"
        placeholder="회의에 대해 자유롭게 질문하세요..."
        accent-color="#f59e0b"
        accent-border="#fbbf24"
        accent-bg="#fffbeb"
        bubble-gradient="linear-gradient(135deg,#fef3c7,#fed7aa)"
        bubble-color="#92400e"
        @send="sendQuick"
        @clear="clearHistory"
      />

      <!-- 오른쪽: 회의 목록 -->
      <div class="card sessions-panel">
        <div class="card-header">
          <span style="font-weight:600">회의 목록</span>
          <div style="display:flex;gap:8px;align-items:center">
            <button
              v-if="role === 'admin'"
              class="btn btn-primary btn-sm"
              @click="showCreateModal = true"
            >+ 회의 만들기</button>
            <button
              v-if="role === 'admin'"
              class="btn btn-outline btn-sm"
              @click="router.push(`/meetings/${meetingId}/card-news`)"
            >📰 카드뉴스</button>
          </div>
        </div>

        <div class="sessions-list">
          <div v-if="!sessions.length" class="empty-state">
            <p>등록된 회의가 없습니다.</p>
            <button v-if="role === 'admin'" class="btn btn-primary btn-sm" style="margin-top:12px" @click="showCreateModal = true">+ 회의 만들기</button>
          </div>

          <div v-for="s in sessions" :key="s.id" class="session-card fade-in">
            <!-- 수정 모드 -->
            <div v-if="editingId === s.id" class="session-edit">
              <div class="form-group" style="margin-bottom:8px">
                <label class="form-label" style="font-size:11px">회의명</label>
                <input v-model="editForm.title" class="form-input"
                  @keydown.enter="saveEdit(s)" @keydown.esc="cancelEdit" autofocus />
              </div>
              <div class="form-group" style="margin-bottom:12px">
                <label class="form-label" style="font-size:11px">일정</label>
                <input type="datetime-local" v-model="editForm.scheduled_at" class="form-input" />
              </div>
              <div style="display:flex;gap:6px">
                <button class="btn btn-primary btn-sm" :disabled="!editForm.title.trim() || saving" @click="saveEdit(s)">
                  {{ saving ? '저장 중...' : '저장' }}
                </button>
                <button class="btn btn-ghost btn-sm" @click="cancelEdit">취소</button>
              </div>
            </div>

            <!-- 보기 모드 -->
            <div v-else>
              <div class="session-header">
                <div>
                  <div style="font-weight:600;font-size:14px">{{ s.title }}</div>
                  <div style="font-size:12px;color:var(--text-muted);margin-top:2px">{{ formatDate(s.scheduled_at) }}</div>
                </div>
                <span class="badge" :class="statusCls(s.status)">{{ statusLabel(s.status) }}</span>
              </div>
              <div class="session-actions">
                <button class="btn btn-primary btn-sm" @click="joinRoom(s)">
                  {{ s.status === 'ended' ? '다시 보기' : '참여하기' }}
                </button>
                <button class="btn btn-outline btn-sm" :disabled="s.status !== 'ended'" @click="viewMinutes(s)">회의록</button>
                <template v-if="role === 'admin' && s.status !== 'ongoing'">
                  <button class="btn btn-ghost btn-sm" @click="startEdit(s)">수정</button>
                  <button class="btn btn-ghost btn-sm" style="color:var(--danger)" :disabled="deleting === s.id" @click="deleteSession(s)">
                    {{ deleting === s.id ? '삭제 중...' : '삭제' }}
                  </button>
                </template>
              </div>
            </div>
          </div>
        </div>
      </div>

    </div>
  </div>

  <!-- 회의 만들기 모달 -->
  <div v-if="showCreateModal" class="modal-overlay" @click.self="showCreateModal = false">
    <div class="modal slide-up">
      <div class="modal-header">
        <span class="modal-title">새 회의 만들기</span>
        <button class="btn-ghost btn-icon" @click="showCreateModal = false">✕</button>
      </div>
      <div class="modal-body">
        <div class="form-group">
          <label class="form-label">회의 제목 <span style="color:var(--danger)">*</span></label>
          <input v-model="createForm.title" class="form-input" placeholder="예: 1차 회의" @keydown.enter="createSession" autofocus />
        </div>
        <div class="form-group">
          <label class="form-label">일정</label>
          <input type="datetime-local" v-model="createForm.scheduled_at" class="form-input" />
        </div>
      </div>
      <div class="modal-footer">
        <button class="btn btn-outline" @click="showCreateModal = false">취소</button>
        <button class="btn btn-primary" :disabled="!createForm.title.trim() || creating" @click="createSession">
          {{ creating ? '생성 중...' : '회의 만들기' }}
        </button>
      </div>
    </div>
  </div>

  <!-- 회의록 모달 -->
  <div v-if="showMinutesModal" class="modal-overlay" @click.self="showMinutesModal = false">
    <div class="modal" style="max-width:680px">
      <div class="modal-header">
        <span class="modal-title">{{ selectedSession?.title }} 회의록</span>
        <button class="btn-ghost btn-icon" @click="showMinutesModal = false">✕</button>
      </div>
      <div class="modal-body">
        <div v-if="!minutes" class="empty-state"><p>회의록을 불러오는 중...</p></div>
        <div v-else class="minutes-content">{{ minutes.content_summary }}</div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.sessions-layout {
  display: flex;
  flex-direction: column;
  height: calc(100vh - var(--header-h) - 40px);
}

.sessions-body {
  flex: 1;
  min-height: 0;
  display: grid;
  grid-template-columns: 380px 1fr;
  gap: 16px;
}

/* ── 회의 목록 패널 ── */
.sessions-panel {
  display: flex;
  flex-direction: column;
  min-height: 0;
}

.sessions-list {
  flex: 1;
  overflow-y: auto;
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.session-card {
  background: #f8fafc;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 14px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.session-header { display: flex; justify-content: space-between; align-items: flex-start; }
.session-actions { display: flex; gap: 6px; flex-wrap: wrap; }
.session-edit { display: flex; flex-direction: column; }
.minutes-content { white-space: pre-wrap; font-size: 13px; line-height: 1.7; }

/* ── 아라 패널 ── */
.ara-panel {
  display: flex;
  flex-direction: column;
  min-height: 0;
  overflow: hidden;
}

.ara-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 16px 10px;
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
}
.ara-title { display: flex; align-items: center; gap: 10px; }
.ara-avatar {
  width: 38px; height: 38px; border-radius: 50%; object-fit: cover;
  border: 2px solid #fbbf24;
  box-shadow: 0 0 0 3px #fef3c7;
}

/* 빠른 질문 */
.quick-questions {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  padding: 10px 14px;
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
}
.quick-btn {
  font-size: 11px;
  padding: 4px 10px;
  border-radius: 99px;
  border: 1px solid #fbbf24;
  background: #fffbeb;
  color: #92400e;
  cursor: pointer;
  transition: background .15s;
  white-space: nowrap;
}
.quick-btn:hover:not(:disabled) { background: #fef3c7; }
.quick-btn:disabled { opacity: .5; cursor: not-allowed; }

/* 메시지 */
.ara-messages {
  flex: 1;
  overflow-y: auto;
  padding: 14px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.msg-row { display: flex; flex-direction: column; gap: 3px; }
.msg-row.user { align-items: flex-end; }
.msg-row.agent { align-items: flex-start; }

.agent-label {
  display: flex;
  align-items: center;
  gap: 5px;
  font-size: 11px;
  font-weight: 600;
  color: #f59e0b;
  margin-bottom: 2px;
}
.ara-mini { width: 16px; height: 16px; border-radius: 50%; object-fit: cover; }

.bubble {
  padding: 8px 12px;
  border-radius: 12px;
  font-size: 13px;
  line-height: 1.65;
  max-width: 92%;
  word-break: break-word;
}
.ara-bubble {
  background: linear-gradient(135deg, #fef3c7, #fed7aa);
  border: 1px solid #fbbf24;
  color: #92400e;
  border-radius: 2px 12px 12px 12px;
}
.user-bubble {
  background: var(--primary);
  color: #fff;
  border-radius: 12px 12px 2px 12px;
}

/* 타이핑 애니메이션 */
.typing {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 10px 14px;
}
.typing span {
  width: 7px; height: 7px;
  background: #d97706;
  border-radius: 50%;
  animation: bounce 1.2s infinite;
}
.typing span:nth-child(2) { animation-delay: .2s; }
.typing span:nth-child(3) { animation-delay: .4s; }
@keyframes bounce { 0%,80%,100%{transform:translateY(0)} 40%{transform:translateY(-6px)} }

/* 입력창 */
.ara-input-area {
  display: flex;
  gap: 8px;
  padding: 10px 12px;
  border-top: 1px solid var(--border);
  flex-shrink: 0;
}
.ara-input {
  flex: 1;
  resize: none;
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 7px 10px;
  font-size: 13px;
  outline: none;
  font-family: inherit;
  line-height: 1.5;
}
.ara-input:focus { border-color: #fbbf24; box-shadow: 0 0 0 2px #fef3c7; }

.btn-ara {
  background: linear-gradient(135deg, #f59e0b, #ea580c);
  color: #fff;
  border: none;
  border-radius: 8px;
  padding: 6px 14px;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  transition: opacity .15s;
  align-self: flex-end;
}
.btn-ara:disabled { opacity: .45; cursor: not-allowed; }
.btn-ara:not(:disabled):hover { opacity: .88; }
</style>
