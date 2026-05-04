<script setup>
import { ref, onMounted, computed } from 'vue'
import { useRoute } from 'vue-router'
import api, { streamPost } from '../api'
import MeetingNav from '../components/MeetingNav.vue'
import { useMeetingsStore } from '../stores/meetings'
import { useChatHistory } from '../composables/useChatHistory'
import gaonAvatar from '../assets/agents/gaon.png'
import { renderMd } from '../composables/useMarkdown'

const route = useRoute()
const meetingsStore = useMeetingsStore()
const meetingId = computed(() => Number(route.params.meetingId))

const agendas = ref([])
const todos = ref([])
const input = ref('')
const loading = ref(false)
const messagesEl = ref(null)
const addingTodo = ref(false)
const newTodo = ref({ content: '', assignee_name: '', due_date: '', how: '', why: '', priority: 'normal', tags: [] })

const STATUS_MAP = {
  pending:     { label: '🔴 미착수',   cls: 'badge-pending' },
  in_progress: { label: '🟡 진행중',   cls: 'badge-inprogress' },
  at_risk:     { label: '🟠 지연위험', cls: 'badge-atrisk' },
  done:        { label: '🟢 완료',     cls: 'badge-success' },
  on_hold:     { label: '⚫ 보류',     cls: 'badge-onhold' },
}

const TAG_OPTIONS = ['결재 필요', '타부서 협조', '외부 의존', '보고 연결']
const PRIORITY_OPTIONS = [
  { value: 'urgent_important', label: '🔥 긴급+중요' },
  { value: 'important',       label: '⭐ 중요' },
  { value: 'urgent',          label: '⚡ 긴급' },
  { value: 'normal',          label: '🔵 보통' },
  { value: 'low',             label: '⬇ 낮음' },
]

function priorityLabel(p) {
  return PRIORITY_OPTIONS.find(o => o.value === p)?.label || p
}

function toggleTag(tag) {
  const i = newTodo.value.tags.indexOf(tag)
  if (i === -1) newTodo.value.tags.push(tag)
  else newTodo.value.tags.splice(i, 1)
}

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
    assignee_name: newTodo.value.assignee_name || null,
    due_date: newTodo.value.due_date || null,
    how: newTodo.value.how || null,
    why: newTodo.value.why || null,
    priority: newTodo.value.priority,
    tags: newTodo.value.tags.length ? newTodo.value.tags : null,
  })
  todos.value.push(data)
  addingTodo.value = false
  newTodo.value = { content: '', assignee_name: '', due_date: '', how: '', why: '', priority: 'normal', tags: [] }
}

async function updateTodoStatus(todo, status) {
  await api.patch(`/api/todos/${todo.id}`, { status })
  todo.status = status
}

async function deleteTodo(id) {
  await api.delete(`/api/todos/${id}`)
  todos.value = todos.value.filter(t => t.id !== id)
}

const WEEKDAYS_KO = ['일','월','화','수','목','금','토']
function formatDate(d) {
  if (!d) return ''
  const parts = d.slice(0, 10).split('-').map(Number)
  const dt = new Date(parts[0], parts[1] - 1, parts[2])
  return `${parts[1]}월 ${parts[2]}일 (${WEEKDAYS_KO[dt.getDay()]})`
}
function fmtWeekday(d) {
  if (!d) return ''
  const parts = d.slice(0, 10).split('-').map(Number)
  const dt = new Date(parts[0], parts[1] - 1, parts[2])
  return `(${WEEKDAYS_KO[dt.getDay()]})`
}

function onKeydown(e) {
  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage() }
}

// STATUS_MAP is defined in script setup above
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
            <div v-if="msg.role === 'agent'" class="chat-bubble agent" v-html="renderMd(msg.content)"></div>
            <div v-else class="chat-bubble" :class="msg.role">{{ msg.content }}</div>
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
            <button class="btn btn-outline btn-sm" @click="addingTodo = !addingTodo">+ 추가</button>
          </div>
          <div style="padding:16px;display:flex;flex-direction:column;gap:8px;overflow-y:auto">
            <!-- 5요소 입력 폼 -->
            <div v-if="addingTodo" class="todo-add-form">
              <input v-model="newTodo.content" class="form-input" placeholder="할 일 (필수)" />
              <div class="tf-row">
                <input v-model="newTodo.assignee_name" class="form-input" placeholder="Who — 담당자" />
                <div class="date-with-wd">
                  <input v-model="newTodo.due_date" type="datetime-local" class="form-input" />
                  <span v-if="newTodo.due_date" class="weekday-hint">{{ fmtWeekday(newTodo.due_date) }}</span>
                </div>
              </div>
              <input v-model="newTodo.how" class="form-input" placeholder="산출물 형태" />
              <input v-model="newTodo.why" class="form-input" placeholder="목적 / 연결된 의사결정" />
              <select v-model="newTodo.priority" class="form-input">
                <option v-for="p in PRIORITY_OPTIONS" :key="p.value" :value="p.value">{{ p.label }}</option>
              </select>
              <div class="tf-tags-row">
                <button v-for="tag in TAG_OPTIONS" :key="tag" class="tag-toggle-btn" :class="{ active: newTodo.tags.includes(tag) }" @click="toggleTag(tag)">[{{ tag }}]</button>
              </div>
              <div class="tf-actions">
                <button class="btn btn-primary btn-sm" @click="addTodo">등록</button>
                <button class="btn btn-ghost btn-sm" @click="addingTodo=false">취소</button>
              </div>
            </div>
            <div v-if="!todos.length && !addingTodo" class="empty-state" style="padding:16px">
              <p>등록된 To-do가 없습니다.</p>
            </div>
            <div v-for="t in todos" :key="t.id" class="todo-item fade-in" :class="t.status">
              <div class="todo-item-header">
                <span class="todo-status-icon">{{ { pending:'🔴', in_progress:'🟡', at_risk:'🟠', done:'🟢', on_hold:'⚫' }[t.status] || '🔴' }}</span>
                <span class="todo-item-content" :style="{ textDecoration: t.status==='done' ? 'line-through' : 'none' }">{{ t.content }}</span>
                <select class="status-select" :value="t.status" @change="updateTodoStatus(t, $event.target.value)">
                  <option v-for="(v, k) in STATUS_MAP" :key="k" :value="k">{{ v.label }}</option>
                </select>
                <button class="btn btn-ghost btn-sm" @click="deleteTodo(t.id)" style="padding:2px 6px">✕</button>
              </div>
              <div class="todo-item-meta">
                <span v-if="t.assignee_name" class="todo-meta-chip">👤 {{ t.assignee_name }}</span>
                <span v-if="t.due_date" class="todo-meta-chip" :style="{ color: new Date(t.due_date) < new Date() && t.status !== 'done' ? '#ef4444' : '' }">📅 {{ formatDate(t.due_date) }}</span>
                <span v-if="t.priority && t.priority !== 'normal'" class="todo-meta-chip">{{ priorityLabel(t.priority) }}</span>
                <span v-for="tag in (t.tags || [])" :key="tag" class="todo-tag-chip">[{{ tag }}]</span>
              </div>
              <div v-if="t.how || t.why" class="todo-item-details">
                <span v-if="t.how">📋 {{ t.how }}</span>
                <span v-if="t.why">🎯 {{ t.why }}</span>
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

/* ── Todo item ── */
.todo-item { background: #f8fafc; border: 1px solid var(--border); border-radius: var(--radius); padding: 10px 12px; display: flex; flex-direction: column; gap: 5px; }
.todo-item.done { opacity: .7; }
.todo-item.at_risk { border-color: #fb923c; background: #fff7ed; }
.todo-item.on_hold { opacity: .55; }

.todo-item-header { display: flex; align-items: center; gap: 8px; }
.todo-status-icon { font-size: 13px; flex-shrink: 0; }
.todo-item-content { flex: 1; font-size: 13px; font-weight: 500; }

.status-select {
  font-size: 11px; border: 1px solid var(--border); border-radius: 99px;
  padding: 2px 6px; background: #f8fafc; cursor: pointer; flex-shrink: 0;
}

.todo-item-meta { display: flex; gap: 6px; flex-wrap: wrap; }
.todo-meta-chip { font-size: 11px; color: var(--text-muted); background: #f1f5f9; padding: 1px 6px; border-radius: 99px; }
.todo-tag-chip { font-size: 11px; color: #7c3aed; background: #ede9fe; padding: 1px 6px; border-radius: 99px; font-weight: 600; }
.todo-item-details { display: flex; gap: 12px; font-size: 11px; color: var(--text-muted); flex-wrap: wrap; }

/* ── Add form ── */
.todo-add-form {
  background: #f8fafc; border: 1px solid var(--border); border-radius: 8px;
  padding: 12px; display: flex; flex-direction: column; gap: 6px;
}
.tf-row { display: flex; gap: 6px; }
.date-with-wd {
  display: flex; align-items: center; flex: 1;
  border: 1px solid var(--border); border-radius: 6px;
  background: #fff; transition: border-color .15s; overflow: hidden;
}
.date-with-wd:focus-within { border-color: var(--accent); box-shadow: 0 0 0 3px rgba(59,130,246,.1); }
.date-with-wd input[type="datetime-local"] {
  flex: 1; border: none !important; box-shadow: none !important;
  padding: 8px 12px; font-size: 13px; background: transparent; outline: none;
}
.weekday-hint { padding-right: 12px; font-size: 13px; color: var(--text-muted); white-space: nowrap; font-weight: 600; pointer-events: none; }
.tf-tags-row { display: flex; gap: 6px; flex-wrap: wrap; }
.tag-toggle-btn {
  padding: 2px 8px; border-radius: 99px; font-size: 11px; font-weight: 600;
  background: #f1f5f9; color: var(--text-muted); border: 1px solid var(--border);
  cursor: pointer; transition: all .15s;
}
.tag-toggle-btn.active { background: #ede9fe; color: #7c3aed; border-color: #c4b5fd; }
.tf-actions { display: flex; gap: 6px; margin-top: 2px; }
</style>
