<script setup>
import { ref, onMounted, computed } from 'vue'
import { useRoute } from 'vue-router'
import api from '../api'
import { streamPost } from '../api'
import MeetingNav from '../components/MeetingNav.vue'
import { useMeetingsStore } from '../stores/meetings'
import { useChatHistory } from '../composables/useChatHistory'
import gaonAvatar from '../assets/agents/gaon.png'

const route = useRoute()
const meetingsStore = useMeetingsStore()
const meetingId = computed(() => Number(route.params.meetingId))

const agendas = ref([])
const todos = ref([])
const input = ref('')
const loading = ref(false)
const messagesEl = ref(null)
const addingTodo = ref(false)
const newTodo = ref({ content: '', due_date: '' })

const { messages, loadMessages, saveMessage, clearHistory } = useChatHistory('todo', meetingId.value)

onMounted(async () => {
  await meetingsStore.fetchMeeting(meetingId.value)
  await meetingsStore.fetchRole(meetingId.value)
  await Promise.all([loadAgendas(), loadTodos()])
  await loadMessages()

  if (messages.value.length === 0) {
    const greeting = agendas.value.length
      ? `확정된 아젠다 ${agendas.value.filter(a => a.status==='confirmed').length}건이 있습니다. To-do 작성을 도와드릴게요!`
      : '아직 확정된 아젠다가 없습니다. Admin이 아젠다를 확정하면 알림을 받게 됩니다.'
    messages.value.push({ role: 'agent', content: greeting })
    saveMessage('agent', greeting)
  }
})

async function loadAgendas() {
  const { data } = await api.get(`/api/meetings/${meetingId.value}/agendas/assigned`)
  agendas.value = data
}

async function loadTodos() {
  const { data } = await api.get(`/api/meetings/${meetingId.value}/todos/mine`)
  todos.value = data
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

  const history = messages.value.slice(0,-1).map(m => ({
    role: m.role === 'user' ? 'user' : 'assistant', content: m.content
  }))
  await streamPost(
    '/api/agent/gaon/chat',
    { meeting_id: meetingId.value, message: text, chat_history: history },
    (chunk) => { agentMsg.content += chunk },
    () => { loading.value = false; saveMessage('agent', agentMsg.content) }
  )
}

async function addTodo() {
  if (!newTodo.value.content.trim()) return
  const { data } = await api.post(`/api/meetings/${meetingId.value}/todos`, {
    content: newTodo.value.content,
    due_date: newTodo.value.due_date || null,
  })
  todos.value.push(data)
  addingTodo.value = false
  newTodo.value = { content: '', due_date: '' }
}

async function updateTodoStatus(todo, status) {
  await api.patch(`/api/todos/${todo.id}`, { status })
  todo.status = status
}

async function deleteTodo(id) {
  await api.delete(`/api/todos/${id}`)
  todos.value = todos.value.filter(t => t.id !== id)
}

function formatDate(d) {
  if (!d) return ''
  return new Date(d).toLocaleDateString('ko-KR')
}

function onKeydown(e) {
  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage() }
}

const statusMap = { pending: { label: '대기', cls: 'badge-warning' }, done: { label: '완료', cls: 'badge-success' }, delayed: { label: '지연', cls: 'badge-danger' } }
</script>

<template>
  <div style="display:flex;flex-direction:column;height:calc(100vh - var(--header-h) - 40px)">
    <MeetingNav />
    <div class="two-col" style="flex:1;min-height:0">
      <!-- Left: Chat -->
      <div class="col-panel card">
        <div class="card-header">
          <div style="display:flex;align-items:center;gap:10px">
            <img :src="gaonAvatar" class="agent-header-avatar" alt="가온" />
            <div>
              <div style="font-weight:700;font-size:14px">가온 (Gaon)</div>
              <div style="font-size:11px;color:var(--text-muted)">To-do 보조</div>
            </div>
          </div>
          <button class="btn btn-ghost btn-sm" style="color:var(--text-muted)" @click="clearHistory" title="대화 기록 지우기">🗑</button>
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
          <textarea v-model="input" class="chat-input" placeholder="가온에게 질문하세요..." rows="1" @keydown="onKeydown" />
          <button class="btn btn-primary btn-sm" :disabled="loading || !input.trim()" @click="sendMessage">전송</button>
        </div>
      </div>

      <!-- Right: Agendas + Todos -->
      <div class="col-panel" style="display:flex;flex-direction:column;gap:16px;overflow-y:auto">
        <!-- Confirmed Agendas -->
        <div class="card">
          <div class="card-header">
            <span style="font-weight:600">확정된 아젠다 ({{ agendas.filter(a=>a.status==='confirmed').length }})</span>
          </div>
          <div class="card-body" style="display:flex;flex-direction:column;gap:8px">
            <div v-if="!agendas.filter(a=>a.status==='confirmed').length" class="empty-state" style="padding:16px">
              <p>확정된 아젠다가 없습니다.</p>
            </div>
            <div v-for="a in agendas.filter(a=>a.status==='confirmed')" :key="a.id" class="agenda-chip">
              <span v-if="a.department" class="badge badge-primary">{{ a.department }}</span>
              <span>{{ a.content }}</span>
            </div>
          </div>
        </div>

        <!-- Todos -->
        <div class="card" style="flex:1">
          <div class="card-header">
            <span style="font-weight:600">내 To-do ({{ todos.length }})</span>
            <button class="btn btn-outline btn-sm" @click="addingTodo = true">+ 추가</button>
          </div>
          <div style="padding:16px;display:flex;flex-direction:column;gap:8px;overflow-y:auto">
            <div v-if="addingTodo" class="todo-add-form card" style="padding:12px">
              <input v-model="newTodo.content" class="form-input" placeholder="과제 내용" style="margin-bottom:8px" />
              <input v-model="newTodo.due_date" type="date" class="form-input" style="margin-bottom:8px" />
              <div style="display:flex;gap:6px">
                <button class="btn btn-primary btn-sm" @click="addTodo">추가</button>
                <button class="btn btn-ghost btn-sm" @click="addingTodo=false">취소</button>
              </div>
            </div>
            <div v-if="!todos.length && !addingTodo" class="empty-state" style="padding:16px">
              <p>등록된 To-do가 없습니다.</p>
            </div>
            <div v-for="t in todos" :key="t.id" class="todo-item fade-in" :class="t.status">
              <div style="display:flex;align-items:flex-start;gap:10px">
                <input
                  type="checkbox"
                  :checked="t.status === 'done'"
                  @change="updateTodoStatus(t, t.status === 'done' ? 'pending' : 'done')"
                  style="margin-top:2px;width:16px;height:16px;cursor:pointer"
                />
                <div style="flex:1">
                  <div :style="{ textDecoration: t.status === 'done' ? 'line-through' : 'none', color: t.status === 'done' ? 'var(--text-muted)' : '' }">
                    {{ t.content }}
                  </div>
                  <div v-if="t.due_date" style="font-size:11px;color:var(--text-muted);margin-top:2px">마감: {{ formatDate(t.due_date) }}</div>
                </div>
                <span class="badge" :class="statusMap[t.status]?.cls">{{ statusMap[t.status]?.label }}</span>
                <button class="btn btn-ghost btn-sm" @click="deleteTodo(t.id)" style="padding:2px 6px">✕</button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.agenda-chip { display: flex; align-items: center; gap: 8px; padding: 8px 12px; background: #f0fdf4; border: 1px solid #bbf7d0; border-radius: 6px; font-size: 13px; }
.todo-item { background: #f8fafc; border: 1px solid var(--border); border-radius: var(--radius); padding: 12px; }
.todo-item.done { opacity: .7; }
</style>
