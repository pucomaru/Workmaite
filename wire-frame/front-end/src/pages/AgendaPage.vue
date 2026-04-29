<script setup>
import { ref, onMounted, computed } from 'vue'
import { useRoute } from 'vue-router'
import api from '../api'
import { streamPost } from '../api'
import MeetingNav from '../components/MeetingNav.vue'
import { useMeetingsStore } from '../stores/meetings'
import gaonAvatar from '../assets/agents/gaon.png'
import { useChatHistory } from '../composables/useChatHistory'

const route = useRoute()
const meetingsStore = useMeetingsStore()
const meetingId = computed(() => Number(route.params.meetingId))

const agendas = ref([])
const input = ref('')
const loading = ref(false)
const editingId = ref(null)
const editForm = ref({})
const uploading = ref(false)
const fileInput = ref(null)
const messagesEl = ref(null)
const isDragging = ref(false)

const GREETING = '안녕하세요! 저는 아젠다 추출 AI 가온입니다.\n보고자료를 업로드하거나, 이전 회의록을 기반으로 새 아젠다를 추출해 드립니다.\n파일을 첨부하거나 직접 내용을 입력해 주세요.'
const { messages, loadMessages, saveMessage, clearHistory } = useChatHistory('agenda', meetingId.value)

onMounted(async () => {
  await meetingsStore.fetchMeeting(meetingId.value)
  await meetingsStore.fetchRole(meetingId.value)
  await Promise.all([loadAgendas(), loadMessages()])
  if (messages.value.length === 0) {
    messages.value.push({ role: 'agent', content: GREETING })
    saveMessage('agent', GREETING)
  }

  // WebSocket for real-time updates
  const ws = new WebSocket(`ws://localhost:8000/ws/meetings/${meetingId.value}/agenda`)
  ws.onmessage = (e) => {
    const msg = JSON.parse(e.data)
    if (msg.type === 'agenda_updated') loadAgendas()
  }
})

async function loadAgendas() {
  const { data } = await api.get(`/api/meetings/${meetingId.value}/agendas`)
  agendas.value = data
}

async function sendMessage() {
  if (!input.value.trim() || loading.value) return
  const text = input.value.trim()
  messages.value.push({ role: 'user', content: text })
  saveMessage('user', text)
  input.value = ''
  const agentMsg = { role: 'agent', content: '' }
  messages.value.push(agentMsg)
  loading.value = true
  await scrollBottom()

  const history = messages.value.slice(0, -1).map(m => ({
    role: m.role === 'user' ? 'user' : 'assistant',
    content: m.content,
  }))

  await streamPost(
    '/api/agent/gaon/chat',
    { meeting_id: meetingId.value, message: text, chat_history: history },
    (chunk) => { agentMsg.content += chunk; scrollBottom() },
    () => { loading.value = false; loadAgendas(); saveMessage('agent', agentMsg.content) }
  )
}

async function uploadFile(fileOrEvent) {
  const file = fileOrEvent instanceof File ? fileOrEvent : fileOrEvent.target.files[0]
  if (!file) return
  uploading.value = true
  messages.value.push({ role: 'user', content: `파일 업로드: ${file.name}` })
  saveMessage('user', `파일 업로드: ${file.name}`)
  const agentMsg = { role: 'agent', content: '' }
  messages.value.push(agentMsg)
  await scrollBottom()

  const formData = new FormData()
  formData.append('file', file)
  formData.append('meeting_id', meetingId.value)
  formData.append('chat_history', '[]')

  try {
    const token = localStorage.getItem('token')
    const res = await fetch(`http://localhost:8000/api/agent/gaon/extract-agenda`, {
      method: 'POST',
      headers: { Authorization: `Bearer ${token}` },
      body: formData,
    })
    const data = await res.json()
    agentMsg.content = `${data.agendas.length}개의 아젠다를 추출했습니다. 우측에서 확인 및 수정하세요.`
    saveMessage('agent', agentMsg.content)
    await loadAgendas()
  } catch {
    agentMsg.content = '파일 처리 중 오류가 발생했습니다.'
  } finally {
    uploading.value = false
  }
}

async function confirmAgenda(id) {
  await api.post(`/api/meetings/${meetingId.value}/agendas/${id}/confirm`)
  await loadAgendas()
}

async function deleteAgenda(id) {
  await api.delete(`/api/meetings/${meetingId.value}/agendas/${id}`)
  agendas.value = agendas.value.filter(a => a.id !== id)
}

function startEdit(a) {
  editingId.value = a.id
  editForm.value = { department: a.department, content: a.content }
}

async function saveEdit(a) {
  await api.patch(`/api/meetings/${meetingId.value}/agendas/${a.id}`, editForm.value)
  editingId.value = null
  await loadAgendas()
}

async function addAgenda() {
  const { data } = await api.post(`/api/meetings/${meetingId.value}/agendas`, {
    department: '미정',
    content: '새 아젠다',
  })
  agendas.value.push(data)
  startEdit(data)
}

async function scrollBottom() {
  await new Promise(r => setTimeout(r, 50))
  if (messagesEl.value) messagesEl.value.scrollTop = messagesEl.value.scrollHeight
}

function onKeydown(e) {
  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage() }
}

function statusLabel(s) {
  return s === 'confirmed' ? '확정됨' : '미확정'
}

function onDragover() {
  isDragging.value = true
}

function onDragleave(e) {
  if (!e.currentTarget.contains(e.relatedTarget)) {
    isDragging.value = false
  }
}

function onDrop(e) {
  isDragging.value = false
  const file = e.dataTransfer.files[0]
  if (file) uploadFile(file)
}
</script>

<template>
  <div style="display:flex;flex-direction:column;height:calc(100vh - var(--header-h) - 40px)">
    <MeetingNav />
    <div class="two-col" style="flex:1;min-height:0">
      <!-- Left: Chat -->
      <div class="col-panel card" style="position:relative"
        @dragover.prevent="onDragover"
        @dragleave="onDragleave"
        @drop.prevent="onDrop"
      >
        <div v-if="isDragging" class="drag-overlay">
          <div class="drag-hint">📎 파일을 여기에 놓으세요</div>
        </div>
        <div class="card-header">
          <div style="display:flex;align-items:center;gap:10px">
            <img :src="gaonAvatar" class="agent-header-avatar" alt="가온" />
            <div>
              <div style="font-weight:700;font-size:14px">가온 (Gaon)</div>
              <div style="font-size:11px;color:var(--text-muted)">아젠다 추출 Agent</div>
            </div>
          </div>
          <div style="display:flex;gap:6px">
            <button class="btn btn-outline btn-sm" :disabled="uploading" @click="fileInput.click()">
              {{ uploading ? '업로드 중...' : '📎 파일 첨부' }}
            </button>
            <button class="btn btn-ghost btn-sm" style="color:var(--text-muted)" @click="clearHistory" title="대화 기록 지우기">🗑</button>
            <input ref="fileInput" type="file" accept=".pdf,.docx,.txt,.xlsx" style="display:none" @change="uploadFile" />
          </div>
        </div>
        <div ref="messagesEl" class="chat-messages" style="flex:1;overflow-y:auto">
          <div v-for="(msg, i) in messages" :key="i" class="chat-msg-row fade-in" :class="msg.role">
            <div v-if="msg.role === 'agent'" class="chat-agent-label">
              <img :src="gaonAvatar" class="chat-avatar-sm" alt="가온" />
              가온
            </div>
            <div class="chat-bubble" :class="msg.role">{{ msg.content }}</div>
          </div>
        </div>
        <div class="chat-input-area">
          <textarea v-model="input" class="chat-input" placeholder="가온에게 질문하거나 지시하세요..." rows="1" @keydown="onKeydown" />
          <button class="btn btn-primary btn-sm" :disabled="loading || !input.trim()" @click="sendMessage">전송</button>
        </div>
      </div>

      <!-- Right: Agenda List -->
      <div class="col-panel card">
        <div class="card-header">
          <span style="font-weight:600">아젠다 목록 ({{ agendas.length }})</span>
          <button class="btn btn-outline btn-sm" @click="addAgenda">+ 직접 추가</button>
        </div>
        <div style="flex:1;overflow-y:auto;padding:16px;display:flex;flex-direction:column;gap:10px">
          <div v-if="!agendas.length" class="empty-state">
            <p>가온에게 보고자료를 업로드하거나 아젠다를 요청해 주세요.</p>
          </div>
          <div
            v-for="a in agendas"
            :key="a.id"
            class="agenda-item fade-in"
            :class="a.status"
          >
            <div v-if="editingId !== a.id" class="agenda-content">
              <div style="display:flex;align-items:center;gap:8px;margin-bottom:6px">
                <span class="badge" :class="a.status === 'confirmed' ? 'badge-success' : 'badge-muted'">
                  {{ statusLabel(a.status) }}
                </span>
                <span v-if="a.department" style="font-size:12px;color:var(--text-muted)">{{ a.department }}</span>
              </div>
              <div style="font-size:14px;line-height:1.5;flex:1">{{ a.content }}</div>
              <div class="agenda-actions">
                <button class="btn btn-sm btn-outline" @click="startEdit(a)">편집</button>
                <button v-if="a.status !== 'confirmed'" class="btn btn-sm btn-success" @click="confirmAgenda(a.id)">확정</button>
                <button class="btn btn-sm btn-ghost" @click="deleteAgenda(a.id)">삭제</button>
              </div>
            </div>
            <div v-else class="agenda-edit">
              <input v-model="editForm.department" class="form-input" placeholder="담당 부서" style="margin-bottom:8px" />
              <textarea v-model="editForm.content" class="form-input form-textarea" placeholder="아젠다 내용" style="min-height:80px" />
              <div class="agenda-actions">
                <button class="btn btn-sm btn-primary" @click="saveEdit(a)">저장</button>
                <button class="btn btn-sm btn-ghost" @click="editingId=null">취소</button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.agenda-item { background: #f8fafc; border: 1px solid var(--border); border-radius: var(--radius); padding: 14px; }
.agenda-item.confirmed { border-left: 3px solid var(--success); background: #f0fdf4; }
.agenda-content { display: flex; flex-direction: column; gap: 6px; }
.agenda-edit { display: flex; flex-direction: column; gap: 8px; }
.agenda-actions { display: flex; gap: 6px; margin-top: 4px; }
.drag-overlay {
  position: absolute; inset: 0; z-index: 10;
  background: rgba(99, 102, 241, 0.08);
  border: 2px dashed var(--primary, #6366f1);
  border-radius: var(--radius);
  display: flex; align-items: center; justify-content: center;
  pointer-events: none;
}
.drag-hint {
  background: white;
  border: 1px solid var(--primary, #6366f1);
  border-radius: var(--radius);
  padding: 12px 24px;
  font-size: 14px;
  font-weight: 600;
  color: var(--primary, #6366f1);
  box-shadow: 0 2px 8px rgba(0,0,0,0.08);
}
</style>
