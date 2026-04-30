<script setup>
import { ref, onMounted, computed } from 'vue'
import { useRoute } from 'vue-router'
import api from '../api'
import { streamPost } from '../api'
import MeetingNav from '../components/MeetingNav.vue'
import AgentPanel from '../components/AgentPanel.vue'
import { useMeetingsStore } from '../stores/meetings'
import gaonAvatar from '../assets/agents/gaon.png'
import { useChatHistory } from '../composables/useChatHistory'
import { marked } from 'marked'
const renderMd = (text) => marked.parse(text || '', { breaks: true })

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
const memberDepartments = ref([])

// HITL: 추출 결과 대기 상태
const pendingExtraction = ref(null) // { agendas, todos, msgIdx }
const saving = ref(false)

const GREETING = '안녕하세요! 저는 아젠다 추출 AI 가온입니다.\n보고자료를 업로드하거나, 이전 회의록을 기반으로 새 아젠다를 추출해 드립니다.\n파일을 첨부하거나 직접 내용을 입력해 주세요.'
const { messages, loadMessages, saveMessage, clearHistory } = useChatHistory('agenda', meetingId.value)
const agentPanelRef = ref(null)

async function handleSend(text) {
  input.value = text
  await sendMessage()
}

onMounted(async () => {
  await meetingsStore.fetchMeeting(meetingId.value)
  await meetingsStore.fetchRole(meetingId.value)
  await Promise.all([loadAgendas(), loadMessages(), loadMemberDepartments()])
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

async function loadMemberDepartments() {
  try {
    const { data } = await api.get(`/api/meetings/${meetingId.value}/members`)
    memberDepartments.value = [...new Set(data.map(m => m.user?.department).filter(Boolean))]
  } catch {}
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
    async () => {
      loading.value = false
      saveMessage('agent', agentMsg.content)
      // JSON 감지 시 HITL: 바로 저장하지 않고 확인 버튼 표시
      if (agentMsg.content.includes('"agendas"')) {
        const msgIdx = messages.value.length - 1
        pendingExtraction.value = { text: agentMsg.content, msgIdx }
      }
    }
  )
}

async function confirmExtraction() {
  if (!pendingExtraction.value || saving.value) return
  saving.value = true
  try {
    const { data } = await api.post('/api/agent/gaon/extract-from-text', {
      meeting_id: meetingId.value,
      text: pendingExtraction.value.text,
    })
    const parts = [`✅ ${data.agendas.length}개 아젠다 저장 완료.`]
    if (data.todos?.length) parts.push(`To-do ${data.todos.length}건 등록.`)
    messages.value.push({ role: 'agent', content: parts.join(' ') })
    saveMessage('agent', parts.join(' '))
    pendingExtraction.value = null
    await loadAgendas()
  } finally {
    saving.value = false
  }
}

function rejectExtraction() {
  pendingExtraction.value = null
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
    if (data.error) {
      agentMsg.content = `파일 처리 실패: ${data.error}`
    } else if (!data.agendas?.length && !data.todos?.length) {
      agentMsg.content = '파일에서 아젠다를 찾지 못했습니다. 파일 내용을 확인하거나 직접 입력해 주세요.'
    } else {
      const parts = [`${data.agendas.length}개의 아젠다를 추출했습니다.`]
      if (data.todos?.length) parts.push(`To-do ${data.todos.length}건도 등록했습니다.`)
      parts.push('우측에서 확인 및 수정하세요.')
      agentMsg.content = parts.join(' ')
    }
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
  <div class="agenda-layout">
    <MeetingNav />
    <div class="agent-body">
      <!-- 왼쪽: 가온 패널 -->
      <AgentPanel
        ref="agentPanelRef"
        :avatar="gaonAvatar"
        name="가온"
        name-en="Gaon"
        subtitle="아젠다 추출 어시스턴트"
        :messages="messages"
        :loading="loading"
        placeholder="가온에게 질문하거나 지시하세요..."
        accent-color="#6366f1"
        accent-border="#818cf8"
        accent-bg="#eef2ff"
        bubble-gradient="linear-gradient(135deg,#eef2ff,#e0e7ff)"
        bubble-color="#3730a3"
        @send="handleSend"
        @clear="clearHistory"
        style="position:relative"
        @dragover.prevent="onDragover"
        @dragleave="onDragleave"
        @drop.prevent="onDrop"
      >
        <template #actions>
          <button class="btn btn-outline btn-sm" :disabled="uploading" @click="fileInput.click()">
            {{ uploading ? '업로드 중...' : '📎 파일 첨부' }}
          </button>
          <input ref="fileInput" type="file" accept=".pdf,.docx,.txt,.xlsx" style="display:none" @change="uploadFile" />
        </template>
        <template #overlay>
          <div v-if="isDragging" class="drag-overlay">
            <div class="drag-hint">📎 파일을 여기에 놓으세요</div>
          </div>
        </template>
        <template #messages-extra>
          <div v-if="pendingExtraction" class="hitl-banner fade-in">
            <div class="hitl-text">위 내용에서 아젠다와 To-do를 추출해 저장할까요?</div>
            <div class="hitl-actions">
              <button class="btn btn-primary btn-sm" :disabled="saving" @click="confirmExtraction">{{ saving ? '저장 중...' : '✔ 저장' }}</button>
              <button class="btn btn-ghost btn-sm" @click="rejectExtraction">취소</button>
            </div>
          </div>
        </template>
      </AgentPanel>

      <!-- 오른쪽: 아젠다 목록 -->
      <div class="agenda-right card">
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
              <input
                v-model="editForm.department"
                class="form-input"
                placeholder="담당 부서"
                style="margin-bottom:8px"
                list="dept-list"
              />
              <datalist id="dept-list">
                <option v-for="d in memberDepartments" :key="d" :value="d" />
              </datalist>
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
.agenda-layout {
  display: flex;
  flex-direction: column;
  height: calc(100vh - var(--header-h) - 40px);
}
.agent-body {
  flex: 1;
  min-height: 0;
  display: flex;
  gap: 16px;
  overflow: hidden;
}
.agenda-right {
  flex: 1;
  min-height: 0;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}
.agenda-item { background: #f8fafc; border: 1px solid var(--border); border-radius: var(--radius); padding: 14px; }
.agenda-item.confirmed { border-left: 3px solid var(--success); background: #f0fdf4; }
.agenda-content { display: flex; flex-direction: column; gap: 6px; }
.agenda-edit { display: flex; flex-direction: column; gap: 8px; }
.agenda-actions { display: flex; gap: 6px; margin-top: 4px; }
.hitl-banner {
  margin: 8px 12px;
  padding: 12px 14px;
  background: #eff6ff;
  border: 1px solid #bfdbfe;
  border-radius: var(--radius);
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}
.hitl-text { font-size: 13px; color: #1e40af; font-weight: 500; flex: 1; }
.hitl-actions { display: flex; gap: 6px; flex-shrink: 0; }

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
