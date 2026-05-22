<script setup>
import { ref, onMounted, onUnmounted, computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import api, { streamPost, toWsUrl, BASE_URL } from '../api'
import MeetingNav from '../components/MeetingNav.vue'
import AgentPanel from '../components/AgentPanel.vue'
import { useMeetingsStore } from '../stores/meetings'
import { useAuthStore } from '../stores/auth'
import gaonAvatar from '../assets/agents/gaon.png'
import { useChatHistory } from '../composables/useChatHistory'

const route = useRoute()
const router = useRouter()
const meetingsStore = useMeetingsStore()
const auth = useAuthStore()
const meetingId = computed(() => Number(route.params.meetingId))
const isAdmin = computed(() => meetingsStore.myRole === 'admin')
const myDept = computed(() => auth.user?.department || '')
const myName = computed(() => auth.user?.name || '')

const agendas = ref([])
const todos = ref([])
const input = ref('')
const loading = ref(false)
const editingId = ref(null)
const editForm = ref({})
const uploading = ref(false)
const messagesEl = ref(null)
const isDragging = ref(false)
const memberDepartments = ref([])

const activeTab = ref('todos')  // 'todos' | 'agendas'

// Extraction HITL
const pendingExtraction = ref(null)
const extractionReason = ref('')
const saving = ref(false)

const AGENDA_TYPES = [
  { value: 'draft',     label: 'Draft',     color: '#6b7280' },
  { value: 'scheduled', label: 'Scheduled', color: '#3b82f6' },
  { value: 'closed',    label: 'Closed',    color: '#22c55e' },
]

// Todo inline editing
const editingTodoId = ref(null)
const todoEditForm = ref({ content: '', assignee_name: '', assignee_dept: '', due_date: '', how: '', why: '', priority: 'normal', tags: [], status: 'pending' })
const newTodoForm = ref({ content: '', assignee_name: '', assignee_dept: '', due_date: '', how: '', why: '', priority: 'normal', tags: [], agenda_id: null })
function defaultTodoForm(extra = {}) {
  return { content: '', assignee_name: myName.value || '', assignee_dept: myDept.value || '', due_date: '', how: '', why: '', priority: 'normal', tags: [], ...extra }
}



async function submitTodoForm(agendaId) {
  if (!newTodoForm.value.content.trim()) return
  const targetDept = newTodoForm.value.assignee_dept || myDept.value || null
  const payload = {
    content: newTodoForm.value.content.trim(),
    agenda_id: agendaId ?? newTodoForm.value.agenda_id ?? null,
    assignee_name: newTodoForm.value.assignee_name || myName.value || null,
    assignee_dept: targetDept,
    due_date: newTodoForm.value.due_date || null,
    how: newTodoForm.value.how || null,
    why: newTodoForm.value.why || null,
    priority: newTodoForm.value.priority,
    tags: newTodoForm.value.tags,
  }
  // 다른 부서 배정 경고
  if (myDept.value && targetDept && targetDept !== myDept.value) {
    todoDeptWarning.value = { show: true, dept: targetDept, action: async () => {
      await api.post(`/api/meetings/${meetingId.value}/todos`, payload)
      showStandaloneTodoForm.value = false
      await loadTodos()
    }}
    return
  }
  await api.post(`/api/meetings/${meetingId.value}/todos`, payload)
  showStandaloneTodoForm.value = false
  await loadTodos()
}

function startEditTodo(t) {
  editingTodoId.value = t.id
  todoEditForm.value = {
    content: t.content,
    assignee_name: t.assignee_name || '',
    assignee_dept: t.assignee_dept || '',
    due_date: t.due_date ? t.due_date.slice(0, 10) : '',
    how: t.how || '',
    why: t.why || '',
    priority: t.priority || 'normal',
    tags: Array.isArray(t.tags) ? [...t.tags] : [],
    status: t.status || 'pending',
  }
}
function cancelEditTodo() {
  editingTodoId.value = null
}
async function saveTodoEdit(t) {
  if (!todoEditForm.value.content.trim()) return
  const targetDept = todoEditForm.value.assignee_dept || myDept.value || null
  const payload = {
    content: todoEditForm.value.content.trim(),
    assignee_name: todoEditForm.value.assignee_name || myName.value || null,
    assignee_dept: targetDept,
    due_date: todoEditForm.value.due_date || null,
    how: todoEditForm.value.how || null,
    why: todoEditForm.value.why || null,
    priority: todoEditForm.value.priority,
    tags: todoEditForm.value.tags,
    status: todoEditForm.value.status,
  }
  if (myDept.value && targetDept && targetDept !== myDept.value) {
    todoDeptWarning.value = { show: true, dept: targetDept, action: async () => {
      await api.patch(`/api/todos/${t.id}`, payload)
      editingTodoId.value = null
      await loadTodos()
    }}
    return
  }
  await api.patch(`/api/todos/${t.id}`, payload)
  editingTodoId.value = null
  await loadTodos()
}

function deleteTodo(id) {
  deleteConfirm.value = { show: true, type: 'todo', id, label: '이 To-do를 삭제할까요?' }
}

// 아젠다 greeting용 내 부서 아젠다 (presenter greeting)
const myDeptAgendas = computed(() =>
  agendas.value.filter(a => myDept.value && a.department?.includes(myDept.value))
)

// agenda_type 기준 섹션 그룹: Draft → Scheduled → Closed
const KNOWN_TYPES = new Set(['draft', 'scheduled', 'closed'])
const collapsedSections = ref(new Set())
function toggleSection(type) {
  if (collapsedSections.value.has(type)) collapsedSections.value.delete(type)
  else collapsedSections.value.add(type)
  // trigger reactivity
  collapsedSections.value = new Set(collapsedSections.value)
}
const groupedAgendas = computed(() => {
  const order = ['draft', 'scheduled', 'closed']
  return order
    .map(type => ({
      type,
      label: AGENDA_TYPES.find(t => t.value === type)?.label || type,
      color: AGENDA_TYPES.find(t => t.value === type)?.color || '#6b7280',
      // 알 수 없는 agenda_type은 draft로 취급
      items: agendas.value.filter(a => {
        const t = a.agenda_type && KNOWN_TYPES.has(a.agenda_type) ? a.agenda_type : 'draft'
        return t === type
      }),
    }))
})

function agendaCardClass(a) {
  return 'agenda-item fade-in' + (dragOverId.value === a.id ? ' drag-over' : '')
}

// ── Drag & Drop ──────────────────────────────────────────────
const draggingId = ref(null)
const dragOverId = ref(null)
const dragOverSection = ref(null)  // 섹션 위에 드래그 중인 경우

function onDragStart(e, a) {
  draggingId.value = a.id
  e.dataTransfer.effectAllowed = 'move'
  e.dataTransfer.setData('text/plain', String(a.id))
}
function onDragEnd() {
  draggingId.value = null
  dragOverId.value = null
  dragOverSection.value = null
}
function onCardDragOver(e, a) {
  if (draggingId.value === a.id) return
  e.preventDefault()
  e.dataTransfer.dropEffect = 'move'
  dragOverId.value = a.id
  dragOverSection.value = null
}
function onCardDragLeave() {
  dragOverId.value = null
}
function onSectionDragOver(e, type) {
  e.preventDefault()
  e.dataTransfer.dropEffect = 'move'
  dragOverSection.value = type
  dragOverId.value = null
}
function onSectionDragLeave() {
  dragOverSection.value = null
}
async function onDropOnCard(e, targetAgenda) {
  e.preventDefault()
  const srcId = draggingId.value
  if (!srcId || srcId === targetAgenda.id) { onDragEnd(); return }
  const src = agendas.value.find(x => x.id === srcId)
  if (!src) { onDragEnd(); return }

  const srcType = src.agenda_type && KNOWN_TYPES.has(src.agenda_type) ? src.agenda_type : 'draft'
  const tgtType = targetAgenda.agenda_type && KNOWN_TYPES.has(targetAgenda.agenda_type) ? targetAgenda.agenda_type : 'draft'

  if (srcType !== tgtType) {
    // 섹션 이동: agenda_type 변경
    src.agenda_type = tgtType
    await api.patch(`/api/meetings/${meetingId.value}/agendas/${srcId}`, { agenda_type: tgtType })
  } else {
    // 같은 섹션 내 순서 교환
    const items = agendas.value.filter(a => {
      const t = a.agenda_type && KNOWN_TYPES.has(a.agenda_type) ? a.agenda_type : 'draft'
      return t === srcType
    })
    const srcIdx = items.findIndex(x => x.id === srcId)
    const tgtIdx = items.findIndex(x => x.id === targetAgenda.id)
    if (srcIdx !== -1 && tgtIdx !== -1) {
      items.splice(tgtIdx, 0, items.splice(srcIdx, 1)[0])
      items.forEach((a, i) => { a.order_num = i })
      await Promise.all(items.map(a =>
        api.patch(`/api/meetings/${meetingId.value}/agendas/${a.id}`, { order_num: a.order_num })
      ))
    }
  }
  onDragEnd()
  await loadAgendas()
}
async function onDropOnSection(e, type) {
  e.preventDefault()
  const srcId = draggingId.value
  if (!srcId) { onDragEnd(); return }
  const src = agendas.value.find(x => x.id === srcId)
  if (!src) { onDragEnd(); return }
  const srcType = src.agenda_type && KNOWN_TYPES.has(src.agenda_type) ? src.agenda_type : 'draft'
  if (srcType !== type) {
    src.agenda_type = type
    await api.patch(`/api/meetings/${meetingId.value}/agendas/${srcId}`, { agenda_type: type })
    await loadAgendas()
  }
  onDragEnd()
}

// To-do 탭 — 부서별 그룹화: 모든 사용자 자신 부서만
const visibleTodos = computed(() => {
  // Admin은 회의체 전체 To-do 열람 가능
  if (isAdmin.value) return todos.value
  const dept = myDept.value?.trim()
  const name = myName.value?.trim()
  // 내 부서 정보가 없으면 전체 표시 (부서 미설정 계정 대비)
  if (!dept) return todos.value
  return todos.value.filter(t => {
    if (!t.assignee_dept) return true
    if (t.assignee_dept.trim() === dept) return true
    if (name && t.assignee_name?.trim() === name) return true
    return false
  })
})
// 부서별 그룹화 (아젠다 섹션과 동일한 패턴)
const collapsedTodoDepts = ref(new Set())
function toggleTodoDept(dept) {
  if (collapsedTodoDepts.value.has(dept)) collapsedTodoDepts.value.delete(dept)
  else collapsedTodoDepts.value.add(dept)
}
const todoDeptGroups = computed(() => {
  const deptMap = new Map()
  for (const t of visibleTodos.value) {
    const key = t.assignee_dept?.trim() || '미분류'
    if (!deptMap.has(key)) deptMap.set(key, [])
    deptMap.get(key).push(t)
  }
  // 내 부서 먼저, 나머지 가나다순, 미분류 마지막
  const myD = myDept.value?.trim()
  const entries = [...deptMap.entries()].sort(([a], [b]) => {
    if (a === myD) return -1
    if (b === myD) return 1
    if (a === '미분류') return 1
    if (b === '미분류') return -1
    return a.localeCompare(b, 'ko')
  })
  function sortItems(items) {
    const isDone = t => t.status === 'done'
    const due = t => t.due_date ? new Date(t.due_date).getTime() : Infinity
    return [...items].sort((a, b) => {
      if (isDone(a) !== isDone(b)) return isDone(a) ? 1 : -1
      return due(a) - due(b)
    })
  }
  return entries.map(([dept, items]) => ({ dept, items: sortItems(items) }))
})

const WEEKDAYS_KO = ['일','월','화','수','목','금','토']
function fmtDueDate(d) {
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

async function toggleTodoStatus(t) {
  const newStatus = (t.status === 'done') ? 'pending' : 'done'
  await api.patch(`/api/todos/${t.id}`, { status: newStatus })
  await loadTodos()
}

// Standalone todo add (no agenda)
const showStandaloneTodoForm = ref(false)
function openStandaloneTodoAdd() {
  showStandaloneTodoForm.value = !showStandaloneTodoForm.value
  newTodoForm.value = defaultTodoForm({ agenda_id: null })
}
async function submitStandaloneTodoForm() {
  await submitTodoForm(null)
  showStandaloneTodoForm.value = false
}

// Todo status
const TODO_STATUSES = [
  { value: 'pending', label: '대기', icon: '🔴' },
  { value: 'in_progress', label: '진행중', icon: '🟡' },
  { value: 'at_risk', label: '위험', icon: '🟠' },
  { value: 'done', label: '완료', icon: '🟢' },
  { value: 'on_hold', label: '보류', icon: '⚫' },
]

function todosForAgenda(agendaId) {
  return todos.value.filter(t => t.agenda_id === agendaId)
}

// ── Greeting messages ────────────────────────────────────────
const ADMIN_GREETING_EMPTY   = '안녕하세요! 저는 가온이에요 😊\n회의 준비자료나 보고서, 이전 회의록 같은 거 업로드해주시면 아젠다랑 To-do 뽑아드릴게요.\n파일 드래그해서 올려주시거나 아래 질문 눌러보세요!'
const ADMIN_GREETING_HASDATA = '안녕하세요! 가온이에요.\n이미 아젠다랑 To-do가 등록되어 있네요. 추가 자료 있으면 올려주시고, 현황 요약이나 리스크 검토 필요하시면 편하게 물어봐주세요!'
const PRESENTER_GREETING_EMPTY = '안녕하세요! 가온이에요 😊\n우리 부서 발표자료나 준비 자료 올려주시면 To-do랑 준비사항 정리해드릴게요!'
const PRESENTER_GREETING = '안녕하세요! 가온이에요.\n우리 부서 아젠다랑 To-do는 우측에서 확인하실 수 있어요. 추가로 챙겨야 할 것들 있는지 같이 살펴볼까요?'

const ADMIN_QUICK = [
  '자료에서 아젠다랑 To-do 뽑아줘',
  '각 아젠다 리스크 포인트 알려줘',
  '미완료 To-do 현황 요약해줘',
  '부서별 준비 현황 정리해줘',
]
const PRESENTER_QUICK = [
  '우리 부서 To-do 뽑아줘',
  '마감 임박 항목 알려줘',
  '이번 회의 준비사항 정리해줘',
  '발표자료에서 논의 포인트 뽑아줘',
]
const quickQuestions = computed(() => isAdmin.value ? ADMIN_QUICK : PRESENTER_QUICK)
const agentGreeting = computed(() => {
  if (isAdmin.value)
    return agendas.value.length > 0 ? ADMIN_GREETING_HASDATA : ADMIN_GREETING_EMPTY
  return myDeptAgendas.value.length > 0 ? PRESENTER_GREETING : PRESENTER_GREETING_EMPTY
})

const { messages, loadMessages, saveMessage, clearHistory } = useChatHistory('agenda', meetingId.value)
const agentPanelRef = ref(null)
const pendingFile = ref(null) // 첨부된 파일 (전송 전)

async function handleSend(text) {
  if (pendingFile.value) {
    const file = pendingFile.value
    pendingFile.value = null
    await uploadFile(file, text)
  } else {
    input.value = text
    await sendMessage()
  }
}

onMounted(async () => {
  await meetingsStore.fetchMeeting(meetingId.value)
  await meetingsStore.fetchRole(meetingId.value)
  if (!meetingsStore.meetings.length) await meetingsStore.fetchMeetings()
  await Promise.all([loadAgendas(), loadTodos(), loadMessages(), loadMemberDepartments()])



  // WebSocket for real-time updates
  agendaWs = new WebSocket(toWsUrl(`/ws/meetings/${meetingId.value}/agenda`))
  agendaWs.onmessage = (e) => {
    try {
      const msg = JSON.parse(e.data)
      if (msg.type === 'agenda_updated') loadAgendas()
    } catch {}
  }
})

let agendaWs = null
onUnmounted(() => { agendaWs?.close() })

async function loadAgendas() {
  const { data } = await api.get(`/api/meetings/${meetingId.value}/agendas`)
  agendas.value = data
}

async function loadTodos() {
  try {
    const { data } = await api.get(`/api/meetings/${meetingId.value}/todos`)
    todos.value = data
  } catch {}
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

  try {
    await streamPost(
      '/api/agent/gaon/chat',
      { meeting_id: meetingId.value, message: text, chat_history: history },
      (chunk) => { agentMsg.content += chunk; scrollBottom() },
      async () => {
        saveMessage('agent', agentMsg.content)
        // JSON 감지 시 HITL: 바로 저장하지 않고 확인 버튼 표시
        if (agentMsg.content.includes('"agendas"')) {
          const originalContent = agentMsg.content
          let cleaned = originalContent
            .replace(/```(?:json)?[\s\S]*?```/g, '')
            .replace(/\{[^{}]*"agendas"[^{}]*(?:\{[^{}]*\}[^{}]*)*\}/g, '')
            .replace(/\n{3,}/g, '\n\n')
            .trim()
          extractionReason.value = cleaned
          agentMsg.content = cleaned
          pendingExtraction.value = { text: originalContent, msgIdx: messages.value.length - 1 }
          if (isAdmin.value) activeTab.value = 'todos'
        }
      }
    )
  } catch {
    agentMsg.content = '응답 중 오류가 발생했습니다.'
  } finally {
    loading.value = false
  }
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
    await Promise.all([loadAgendas(), loadTodos()])
  } finally {
    saving.value = false
  }
}

function rejectExtraction() {
  pendingExtraction.value = null
}

async function uploadFile(fileOrEvent, extraText = '') {
  const file = fileOrEvent instanceof File ? fileOrEvent : fileOrEvent.target.files[0]
  if (!file) return
  uploading.value = true
  const userMsg = extraText ? `📎 ${file.name}\n${extraText}` : `파일 업로드: ${file.name}`
  messages.value.push({ role: 'user', content: userMsg })
  saveMessage('user', userMsg)
  const agentMsg = { role: 'agent', content: '' }
  messages.value.push(agentMsg)
  await scrollBottom()

  const formData = new FormData()
  formData.append('file', file)
  formData.append('meeting_id', meetingId.value)
  formData.append('chat_history', '[]')

  try {
    const token = localStorage.getItem('token')
    const res = await fetch(`${BASE_URL}/api/agent/gaon/extract-agenda`, {
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
      // Build reason from structured data (or use backend-provided reason)
      const agendaLines = data.agendas.map(a => `- [${a.department || '부서미정'}] ${a.content}`).join('\n')
      const todoLines = data.todos?.length
        ? '\n\n[To-do 항목]\n' + data.todos.map(t => `- [${t.department || '부서미정'}] ${t.content}`).join('\n')
        : ''
      extractionReason.value = data.reason
        || `파일에서 ${data.agendas.length}개의 아젠다${data.todos?.length ? `와 To-do ${data.todos.length}건` : ''}을 추출했습니다.\n\n[추출된 아젠다]\n${agendaLines}${todoLines}`
      pendingExtraction.value = { text: JSON.stringify(data), msgIdx: messages.value.length - 1 }
      if (isAdmin.value) activeTab.value = 'todos'
      const parts = [`${data.agendas.length}개의 아젠다를 추출했습니다. 우측 미승인 탭에서 확인 및 승인하세요.`]
      if (data.todos?.length) parts.push(`To-do ${data.todos.length}건도 포함됩니다.`)
      agentMsg.content = parts.join(' ')
    }
    saveMessage('agent', agentMsg.content)
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

async function closeAgenda(id) {
  await api.post(`/api/meetings/${meetingId.value}/agendas/${id}/close`)
  await loadAgendas()
}

function deleteAgenda(id) {
  const a = agendas.value.find(x => x.id === id)
  deleteConfirm.value = { show: true, type: 'agenda', id, label: `「${a?.content || '이 아젠다'}」를 삭제할까요?` }
}

const deptInput = ref('')
function startEdit(a) {
  editingId.value = a.id
  editForm.value = {
    content: a.content,
    agenda_type: a.agenda_type && KNOWN_TYPES.has(a.agenda_type) ? a.agenda_type : 'draft',
    departments: a.department ? a.department.split(',').map(s => s.trim()).filter(Boolean) : [],
    presenter_name: a.presenter_name || '',
    purpose: a.purpose || '',
    due_date: a.due_date ? a.due_date.slice(0, 10) : '',
    related_meeting: a.related_meeting || '',
  }
  deptInput.value = ''
}
function addDept() {
  const v = deptInput.value.trim()
  if (v && !editForm.value.departments.includes(v)) editForm.value.departments.push(v)
  deptInput.value = ''
}
function onDeptKeydown(e) {
  if (e.key === ',') { e.preventDefault(); addDept() }
}
function removeDept(d) {
  editForm.value.departments = editForm.value.departments.filter(x => x !== d)
}

async function saveEdit(a) {
  const payload = {
    content: editForm.value.content,
    agenda_type: editForm.value.agenda_type,
    department: editForm.value.departments.join(', ') || null,
    presenter_name: editForm.value.presenter_name,
    purpose: editForm.value.purpose || null,
    due_date: editForm.value.due_date || null,
    related_meeting: editForm.value.related_meeting || null,
  }

  // 타 회의체에 배정되는 경우 경고
  if (editForm.value.related_meeting) {
    const target = _findMeetingByTitle(editForm.value.related_meeting)
    if (target && target.id !== meetingId.value) {
      relatedMeetingWarning.value = {
        show: true,
        targetMeeting: target,
        pendingAgendaId: a.id,
        pendingForm: payload,
      }
      return
    }
  }

  await api.patch(`/api/meetings/${meetingId.value}/agendas/${a.id}`, payload)
  editingId.value = null
  await loadAgendas()
}

async function addAgenda() {
  const { data } = await api.post(`/api/meetings/${meetingId.value}/agendas`, {
    department: myDept.value || '',
    content: '',
    agenda_type: 'draft',
  })
  agendas.value.push(data)
  startEdit(data)
}

// ── To-do 타 부서 배정 경고 ──────────────────────────────────
const todoDeptWarning = ref({ show: false, dept: '', action: null })
function dismissTodoDeptWarning() { todoDeptWarning.value = { show: false, dept: '', action: null } }
async function confirmTodoDeptWarning() {
  const fn = todoDeptWarning.value.action
  dismissTodoDeptWarning()
  if (fn) await fn()
}

// ── 삭제 확인 다이얼로그 ──────────────────────────────────────
const deleteConfirm = ref({ show: false, type: '', id: null, label: '' })
function dismissDeleteConfirm() {
  deleteConfirm.value = { show: false, type: '', id: null, label: '' }
}
async function confirmDelete() {
  const { type, id } = deleteConfirm.value
  dismissDeleteConfirm()
  if (type === 'agenda') {
    await api.delete(`/api/meetings/${meetingId.value}/agendas/${id}`)
    agendas.value = agendas.value.filter(a => a.id !== id)
  } else if (type === 'todo') {
    await api.delete(`/api/todos/${id}`)
    todos.value = todos.value.filter(t => t.id !== id)
  }
}

// ── 타 회의체 배정 경고 다이얼로그 ──────────────────────────────
const relatedMeetingWarning = ref({ show: false, targetMeeting: null, pendingAgendaId: null, pendingForm: null })
function _findMeetingByTitle(title) {
  if (!title) return null
  return meetingsStore.meetings.find(m => m.title === title) || null
}
function dismissRelatedWarning() {
  relatedMeetingWarning.value = { show: false, targetMeeting: null, pendingAgendaId: null, pendingForm: null }
}
async function confirmRelatedWarning() {
  const { pendingAgendaId, pendingForm, targetMeeting } = relatedMeetingWarning.value
  dismissRelatedWarning()
  // 먼저 저장 완료
  try {
    if (pendingAgendaId && pendingForm) {
      await api.patch(`/api/meetings/${meetingId.value}/agendas/${pendingAgendaId}`, pendingForm)
      editingId.value = null
      await loadAgendas()
    }
  } catch (e) {
    console.error('agenda save error', e)
  }
  // 해당 회의체 아젠다 페이지로 이동
  if (targetMeeting) {
    await router.push(`/meetings/${targetMeeting.id}/agenda`)
  }
}

async function scrollBottom() {
  await new Promise(r => setTimeout(r, 50))
  if (messagesEl.value) messagesEl.value.scrollTop = messagesEl.value.scrollHeight
}

function onKeydown(e) {
  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage() }
}

function onDragover() {
  isDragging.value = true
}

function onDragleave(e) {
  if (!e.currentTarget.contains(e.relatedTarget)) {
    isDragging.value = false
  }
}

function onFileSelect(e) {
  const file = e.target.files[0]
  e.target.value = ''
  if (file) pendingFile.value = file
}

function onDrop(e) {
  isDragging.value = false
  const file = e.dataTransfer.files[0]
  if (file) pendingFile.value = file
}
</script>

<template>
  <div class="agenda-layout">
    <MeetingNav />
    <div class="agent-body">

      <!-- ══ 왼쪽: 가온 에이전트 패널 (공통) ══ -->
      <AgentPanel
        ref="agentPanelRef"
        :avatar="gaonAvatar"
        name="가온"
        name-en="Gaon"
        :subtitle="'To-do 추출 · 아젠다 어시스턴트'"
        :messages="messages"
        :loading="loading"
        :quick-questions="quickQuestions"
        :greeting="agentGreeting"
        placeholder="가온에게 질문하거나 지시하세요..."
        accent-color="#16a34a"
        accent-border="#4ade80"
        accent-bg="#f0fdf4"
        bubble-gradient="linear-gradient(135deg,#f0fdf4,#dcfce7)"
        bubble-color="#14532d"
        @send="handleSend"
        @clear="clearHistory"
        :pending-files="pendingFile ? [{ name: pendingFile.name }] : []"
        @remove-file="pendingFile = null"
        @dragover.prevent="onDragover"
        @dragleave="onDragleave"
        @drop.prevent="onDrop"
      >

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

      <!-- ══ 오른쪽: 통합 패널 ══ -->
      <div class="agenda-right card">

        <!-- 탭 헤더 -->
        <div class="right-panel-header">
          <button class="panel-tab" :class="{ active: activeTab==='todos' }" @click="activeTab='todos'">
            To-do
            <span v-if="visibleTodos.length" class="tab-badge">{{ visibleTodos.length }}</span>
          </button>
          <button class="panel-tab" :class="{ active: activeTab==='agendas' }" @click="activeTab='agendas'">
            아젠다
            <span v-if="agendas.length" class="tab-badge tab-badge-green">{{ agendas.length }}</span>
          </button>
          <button v-if="activeTab==='agendas'" class="btn btn-outline btn-sm" style="margin-left:auto" @click="addAgenda">+ 등록</button>
          <button v-if="activeTab==='todos'" class="btn btn-outline btn-sm" style="margin-left:auto" @click="openStandaloneTodoAdd">+ 등록</button>
        </div>

        <!-- ── To-do 탭 ── -->
        <div v-if="activeTab==='todos'" class="tab-body">
          <div v-if="extractionReason" class="reason-section">
            <div class="reason-title">💡 가온 분석 결과</div>
            <div class="reason-text">{{ extractionReason }}</div>
          </div>

          <div v-if="showStandaloneTodoForm" class="todo-detail-form">
            <div class="todo-form-section-label">새 To-do 등록</div>
            <input v-model="newTodoForm.content" class="form-input" placeholder="할 일" autofocus />
            <div class="todo-form-row">
              <input v-model="newTodoForm.assignee_name" class="form-input" :placeholder="`담당자 (미입력 시 ${myName || '본인'})`" />
              <select v-model="newTodoForm.assignee_dept" class="form-input">
                <option value="">(미입력 시 내 부서)</option>
                <option v-for="d in memberDepartments" :key="d" :value="d">{{ d }}</option>
              </select>
            </div>
            <div class="date-with-wd">
              <input v-model="newTodoForm.due_date" class="form-input" type="date" />
              <span v-if="newTodoForm.due_date" class="weekday-hint">{{ fmtWeekday(newTodoForm.due_date) }}</span>
            </div>
            <input v-model="newTodoForm.how" class="form-input" placeholder="산출물 형태" />
            <input v-model="newTodoForm.why" class="form-input" placeholder="목적·연결된 의사결정" />
            <div class="todo-form-row">
              <select v-model="newTodoForm.priority" class="form-input">
                <option value="high">시급 — 상</option>
                <option value="normal">시급 — 중</option>
                <option value="low">시급 — 하</option>
              </select>
            </div>
            <div class="todo-form-row">
              <select v-model="newTodoForm.agenda_id" class="form-input">
                <option :value="null">연관 아젠다</option>
                <option v-for="a in agendas" :key="a.id" :value="a.id">{{ a.content || '(제목 없음)' }}</option>
              </select>
            </div>
            <div class="todo-form-actions">
              <button class="btn btn-sm btn-primary" @click="submitStandaloneTodoForm">등록</button>
              <button class="btn btn-sm btn-ghost" @click="showStandaloneTodoForm=false">취소</button>
            </div>
          </div>

          <div v-if="!visibleTodos.length" class="empty-state" style="margin:16px">
            <p>추출된 To-do가 없습니다.<br>가온에게 자료를 업로드하면 To-do를 자동으로 추출합니다.</p>
          </div>

          <!-- 부서별 섹션 -->
          <template v-for="group in todoDeptGroups" :key="group.dept">
            <div
              class="section-label agenda-group-label agenda-group-toggle"
              @click="toggleTodoDept(group.dept)"
            >
              <span class="agenda-collapse-icon">{{ collapsedTodoDepts.has(group.dept) ? '▶' : '▼' }}</span>
              {{ group.dept }}
              <span class="agenda-group-count">({{ group.items.length }})</span>
            </div>
            <template v-if="!collapsedTodoDepts.has(group.dept)">
              <div v-for="t in group.items" :key="t.id" class="todo-card agenda-item fade-in" :class="{ 'todo-done': t.status === 'done' }">
                <template v-if="editingTodoId !== t.id">
                  <div class="agenda-card-row">
                    <div class="agenda-card-main">
                      <div class="agenda-card-title" :class="{ 'todo-done-text': t.status === 'done' }">{{ t.content }}</div>
                      <div class="agenda-card-meta">
                        <span v-if="t.assignee_dept">{{ t.assignee_dept }}</span>
                        <span v-if="t.assignee_dept && t.agenda_id" class="meta-pipe">|</span>
                        <span v-if="t.agenda_id" class="agenda-card-sub">{{ agendas.find(a=>a.id===t.agenda_id)?.content }}</span>
                        <span v-if="(t.assignee_dept || t.agenda_id) && t.how" class="meta-pipe">|</span>
                        <span v-if="t.how">{{ t.how }}</span>
                        <span v-if="t.how && t.why" class="meta-pipe">|</span>
                        <span v-if="t.why">{{ t.why }}</span>
                      </div>
                    </div>
                    <div class="agenda-card-side">
                      <div class="card-side-row">
                        <span class="priority-badge" :class="'priority-' + (t.priority || 'normal')">{{ t.priority === 'high' ? '상' : t.priority === 'low' ? '하' : '중' }}</span>
                        <button
                          class="todo-status-badge"
                          :class="t.status === 'done' ? 'todo-status-done' : 'todo-status-ongoing'"
                          @click.stop="toggleTodoStatus(t)"
                        >{{ t.status === 'done' ? 'Done' : 'Ongoing' }}</button>
                      </div>
                      <span v-if="t.due_date" class="agenda-due">{{ fmtDueDate(t.due_date) }}</span>
                      <div class="card-side-row">
                        <button class="agenda-act-btn" @click="startEditTodo(t)">편집</button>
                        <button class="agenda-act-btn danger" @click="deleteTodo(t.id)">삭제</button>
                      </div>
                    </div>
                  </div>
                </template>
                <template v-else>
                  <div class="todo-edit-form">
                    <input v-model="todoEditForm.content" class="form-input" placeholder="할 일" autofocus />
                    <div class="todo-form-row">
                      <input v-model="todoEditForm.assignee_name" class="form-input" :placeholder="`담당자 (미입력 시 ${myName || '본인'})`" />
                      <select v-model="todoEditForm.assignee_dept" class="form-input">
                        <option value="">(미입력 시 내 부서)</option>
                        <option v-for="d in memberDepartments" :key="d" :value="d">{{ d }}</option>
                      </select>
                    </div>
                    <div class="date-with-wd">
                      <input v-model="todoEditForm.due_date" class="form-input" type="date" />
                      <span v-if="todoEditForm.due_date" class="weekday-hint">{{ fmtWeekday(todoEditForm.due_date) }}</span>
                    </div>
                    <input v-model="todoEditForm.how" class="form-input" placeholder="산출물" />
                    <input v-model="todoEditForm.why" class="form-input" placeholder="목적·연결된 의사결정" />
                    <select v-model="todoEditForm.priority" class="form-input">
                      <option value="high">시급 — 상</option>
                      <option value="normal">시급 — 중</option>
                      <option value="low">시급 — 하</option>
                    </select>
                    <div class="todo-form-actions">
                      <button class="btn btn-sm btn-primary" @click="saveTodoEdit(t)">저장</button>
                      <button class="btn btn-sm btn-ghost" @click="cancelEditTodo">취소</button>
                    </div>
                  </div>
                </template>
              </div>
            </template>
          </template>
        </div>

        <!-- ── 아젠다 탭 ── -->
        <div v-if="activeTab==='agendas'" class="tab-body">

          <!-- Draft / Scheduled / Closed 섹션 -->
          <template v-for="group in groupedAgendas" :key="group.type">
            <div
              class="section-label agenda-group-label agenda-group-toggle"
              :class="{ 'drag-section-over': dragOverSection === group.type }"
              @click="toggleSection(group.type)"
              @dragover.prevent="onSectionDragOver($event, group.type)"
              @dragleave="onSectionDragLeave"
              @drop="onDropOnSection($event, group.type)"
            >
              <span class="agenda-collapse-icon">{{ collapsedSections.has(group.type) ? '▶' : '▼' }}</span>
              {{ group.label }} <span class="agenda-group-count">({{ group.items.length }})</span>
            </div>
            <div
              v-show="!collapsedSections.has(group.type)"
              v-for="a in group.items"
              :key="a.id"
              :class="agendaCardClass(a)"
              draggable="true"
              @dragstart="onDragStart($event, a)"
              @dragend="onDragEnd"
              @dragover.prevent="onCardDragOver($event, a)"
              @dragleave="onCardDragLeave"
              @drop="onDropOnCard($event, a)"
            >
            <div v-if="editingId !== a.id" class="agenda-content">
              <div class="agenda-card-row">
                <div class="agenda-card-main">
                  <div class="agenda-card-title">{{ a.content || '(미입력)' }}</div>
                  <div v-if="a.purpose" class="agenda-card-sub">{{ a.purpose }}</div>
                  <div v-if="(a.department && a.department.length) || a.presenter_name" class="agenda-card-meta">
                    <template v-for="(d, i) in (a.department ? a.department.split(',').map(s=>s.trim()).filter(Boolean) : [])" :key="d">
                      <span>{{ d }}</span><span v-if="i < a.department.split(',').filter(s=>s.trim()).length - 1" class="meta-sep">,</span>
                    </template>
                    <span v-if="a.department && a.presenter_name" class="meta-sep">·</span>
                    <span v-if="a.presenter_name">{{ a.presenter_name }}</span>
                  </div>
                  <div v-if="todosForAgenda(a.id).length" class="todo-chip-list">
                    <div v-for="t in todosForAgenda(a.id)" :key="t.id" class="todo-chip-row" style="padding:2px 0">
                      <span class="todo-status-icon" style="font-size:11px">{{ TODO_STATUSES.find(s=>s.value===t.status)?.icon || '🔴' }}</span>
                      <span class="todo-chip-text">{{ t.content }}</span>
                    </div>
                  </div>
                </div>
                <div class="agenda-card-side">
                  <span v-if="a.due_date" class="agenda-due">{{ fmtDueDate(a.due_date) }}</span>
                  <button class="agenda-act-btn" @click="startEdit(a)">편집</button>
                  <button class="agenda-act-btn danger" @click="deleteAgenda(a.id)">삭제</button>
                </div>
              </div>
            </div>
            <div v-else class="agenda-edit">
              <div class="assign-form-label">안건명</div>
              <textarea v-model="editForm.content" class="form-input form-textarea" style="min-height:56px" />
              <div class="edit-form-row" style="margin-top:6px">
                <div style="flex:1">
                  <div class="assign-form-label">유형</div>
                  <select v-model="editForm.agenda_type" class="form-input">
                    <option v-for="t in AGENDA_TYPES" :key="t.value" :value="t.value">{{ t.label }}</option>
                  </select>
                </div>
                <div style="flex:1">
                  <div class="assign-form-label">마감일</div>
                  <div class="date-with-wd">
                    <input v-model="editForm.due_date" class="form-input" type="date" />
                    <span v-if="editForm.due_date" class="weekday-hint">{{ fmtWeekday(editForm.due_date) }}</span>
                  </div>
                </div>
              </div>
              <div class="edit-form-row" style="margin-top:6px">
                <div style="flex:1">
                  <div class="assign-form-label">담당 부서</div>
                  <div class="dept-tags-wrap">
                    <span v-for="d in editForm.departments" :key="d" class="dept-tag-chip">
                      {{ d }}<button type="button" class="dept-tag-remove" @click="removeDept(d)">×</button>
                    </span>
                    <input
                      v-model="deptInput"
                      class="dept-tag-input"
                      :list="'dept-list-' + a.id"
                      placeholder="부서 추가 (Enter 또는 쉼표)"
                      @keydown.enter.prevent="addDept"
                      @keydown="onDeptKeydown"
                      @change="addDept"
                    />
                    <datalist :id="'dept-list-' + a.id"><option v-for="d in memberDepartments" :key="d" :value="d" /></datalist>
                  </div>
                </div>
                <div style="flex:1">
                  <div class="assign-form-label">담당자</div>
                  <input v-model="editForm.presenter_name" class="form-input" placeholder="담당자 이름" />
                </div>
              </div>
              <div class="assign-form-label" style="margin-top:6px">목적</div>
              <textarea v-model="editForm.purpose" class="form-input form-textarea" style="min-height:48px" />
              <div class="assign-form-label" style="margin-top:6px">주관 회의체</div>
              <input v-model="editForm.related_meeting" class="form-input" :list="'meetings-dl-' + a.id" placeholder="회의체 검색" />
              <datalist :id="'meetings-dl-' + a.id"><option v-for="m in meetingsStore.meetings" :key="m.id" :value="m.title" /></datalist>
              <div class="agenda-actions" style="margin-top:8px">
                <button class="btn btn-sm btn-primary" @click="saveEdit(a)">저장</button>
                <button class="btn btn-sm btn-ghost" @click="editingId=null">취소</button>
              </div>
            </div>
            </div>
            <!-- 빈 섹션 드롭존 -->
            <div
              v-if="!collapsedSections.has(group.type) && group.items.length === 0"
              class="agenda-empty-dropzone"
              :class="{ 'drag-over': dragOverSection === group.type }"
              @dragover.prevent="onSectionDragOver($event, group.type)"
              @dragleave="onSectionDragLeave"
              @drop="onDropOnSection($event, group.type)"
            />
          </template>

          <div v-if="!agendas.length" class="empty-state" style="margin:16px">
            <p>아직 등록된 아젠다가 없어요.<br>가온에게 자료를 올리거나 직접 추가하세요.</p>
          </div>
        </div>

      </div>

    </div>
  </div>

  <Teleport to="body">
    <div v-if="relatedMeetingWarning.show" class="warn-overlay" @click.self="dismissRelatedWarning">
      <div class="warn-dialog">
        <div class="warn-icon">⚠️</div>
        <div class="warn-title">다른 회의체로 이동됩니다</div>
        <div class="warn-body">
          선택한 주관 회의체 <strong>「{{ relatedMeetingWarning.targetMeeting?.title }}」</strong>는
          현재 회의체와 다릅니다.<br>
          저장 후 해당 회의체의 아젠다 페이지로 이동하시겠습니까?
        </div>
        <div class="warn-actions">
          <button class="btn btn-primary btn-sm" @click="confirmRelatedWarning">이동하기</button>
          <button class="btn btn-ghost btn-sm" @click="dismissRelatedWarning">취소</button>
        </div>
      </div>
    </div>
  </Teleport>

  <Teleport to="body">
    <div v-if="deleteConfirm.show" class="warn-overlay" @click.self="dismissDeleteConfirm">
      <div class="warn-dialog">
        <div class="warn-icon">🗑️</div>
        <div class="warn-title">삭제 확인</div>
        <div class="warn-body">{{ deleteConfirm.label }}<br>이 작업은 되돌릴 수 없습니다.</div>
        <div class="warn-actions">
          <button class="btn btn-sm" style="background:#dc2626;color:#fff;border:none" @click="confirmDelete">삭제</button>
          <button class="btn btn-ghost btn-sm" @click="dismissDeleteConfirm">취소</button>
        </div>
      </div>
    </div>
  </Teleport>

  <Teleport to="body">
    <div v-if="todoDeptWarning.show" class="warn-overlay" @click.self="dismissTodoDeptWarning">
      <div class="warn-dialog">
        <div class="warn-icon">📤</div>
        <div class="warn-title">다른 부서에 배정</div>
        <div class="warn-body">
          이 To-do를 <strong>「{{ todoDeptWarning.dept }}」</strong> 부서에 배정하시겠습니까?<br>
          해당 부서 담당자에게 알림이 전달됩니다.
        </div>
        <div class="warn-actions">
          <button class="btn btn-primary btn-sm" @click="confirmTodoDeptWarning">배정</button>
          <button class="btn btn-ghost btn-sm" @click="dismissTodoDeptWarning">취소</button>
        </div>
      </div>
    </div>
  </Teleport>
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

/* ── Right panel ── */
.agenda-right {
  flex: 1;
  min-height: 0;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}
.right-header {
  padding: 12px 16px;
  border-bottom: 1px solid var(--border);
  display: flex;
  align-items: center;
  gap: 10px;
  flex-shrink: 0;
}

/* ── Tab body ── */
.tab-body {
  flex: 1;
  overflow-y: auto;
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

/* ── Reason section ── */
.reason-section {
  background: #fef9c3;
  border: 1px solid #fde047;
  border-radius: var(--radius);
  padding: 12px 14px;
}
.reason-title { font-size: 12px; font-weight: 700; color: #854d0e; margin-bottom: 6px; }
.reason-text { font-size: 12px; color: #78350f; line-height: 1.6; white-space: pre-wrap; }

.section-label { font-size: 12px; font-weight: 600; color: var(--text-muted); text-transform: uppercase; letter-spacing: .05em; padding: 4px 0; }

/* ── 종료된 아젠다 ── */
.section-toggle-btn {
  display: flex; align-items: center; justify-content: space-between;
  width: 100%; padding: 6px 10px; border: 1px solid var(--border);
  border-radius: var(--radius); background: #f9fafb;
  font-size: 12px; font-weight: 600; color: var(--text-muted);
  cursor: pointer; margin-bottom: 4px;
}
.section-toggle-btn:hover { background: #f1f5f9; }
.ended-agenda-list { display: flex; flex-direction: column; gap: 4px; margin-top: 4px; }
.ended-agenda-item {
  display: flex; align-items: center; gap: 8px;
  padding: 7px 10px; border: 1px solid var(--border);
  border-radius: var(--radius); background: #fafafa; opacity: .7;
}
.ended-agenda-content { flex: 1; font-size: 13px; color: var(--text-muted); text-decoration: line-through; }
.ended-badge {
  font-size: 10px; font-weight: 700; padding: 1px 7px;
  border-radius: 99px; background: #e5e7eb; color: #6b7280;
}

/* ── Pending agenda item ── */
.agenda-item {
  background: #f8fafc;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 12px 14px;
  cursor: grab;
}
.agenda-item:active { cursor: grabbing; }
.agenda-item.drag-over {
  border: 2px dashed #3b82f6;
  background: #eff6ff;
}
.agenda-empty-dropzone {
  padding: 4px;
}
.agenda-empty-dropzone.drag-over {
  border: 2px dashed #3b82f6;
  border-radius: var(--radius);
  background: #eff6ff;
}
.agenda-meta { display: flex; align-items: center; gap: 6px; margin-bottom: 6px; flex-wrap: wrap; }
.agenda-text { font-size: 14px; line-height: 1.5; color: var(--text); }
.agenda-content { display: flex; flex-direction: column; gap: 6px; }
.agenda-edit { display: flex; flex-direction: column; gap: 6px; }
.agenda-actions { display: flex; gap: 8px; margin-top: 8px; align-items: center; }
.agenda-act-btn {
  background: none;
  border: none;
  cursor: pointer;
  font-size: 11px;
  color: var(--text-muted);
  padding: 0;
  transition: color .15s;
}
.agenda-act-btn:hover { color: var(--text); }
.agenda-act-btn.confirm:hover { color: #16a34a; }
.agenda-act-btn.close-btn:hover { color: #7c3aed; }
.agenda-act-btn.danger:hover { color: #dc2626; }
/* To-do 상태 뱃지 */
.todo-status-badge {
  display: inline-block;
  font-size: 10px;
  font-weight: 600;
  padding: 2px 7px;
  border-radius: 999px;
  border: none;
  cursor: pointer;
  transition: opacity .15s;
  white-space: nowrap;
}
.todo-status-badge:hover { opacity: 0.75; }
.todo-status-ongoing {
  background: #dbeafe;
  color: #1d4ed8;
}
.todo-status-done {
  background: #dcfce7;
  color: #15803d;
}
.todo-done { opacity: 0.6; }
.todo-done-text { text-decoration: line-through; color: var(--text-muted); }
.agenda-card-row {
  display: flex;
  align-items: flex-start;
  gap: 12px;
}
.agenda-card-main { flex: 1; min-width: 0; }
.agenda-card-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--text);
  line-height: 1.4;
  margin-bottom: 3px;
}
.agenda-card-sub {
  font-size: 12px;
  color: #4b5563;
  line-height: 1.5;
  margin-bottom: 3px;
}
.agenda-card-meta {
  font-size: 11px;
  color: var(--text-muted);
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 3px;
  margin-top: 2px;
}
.meta-sep { opacity: .4; }
.meta-pipe { opacity: .3; font-size: 10px; }
.todo-chip-list { margin-top: 6px; }
.dept-tags-wrap {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 4px;
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 4px 8px;
  min-height: 34px;
  background: #fff;
}
.dept-tag-chip {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  background: #f1f5f9;
  color: #374151;
  font-size: 12px;
  padding: 2px 7px;
  border-radius: 4px;
}
.dept-tag-remove {
  background: none;
  border: none;
  cursor: pointer;
  color: var(--text-muted);
  font-size: 13px;
  line-height: 1;
  padding: 0 0 0 2px;
}
.dept-tag-remove:hover { color: #dc2626; }
.dept-tag-input {
  border: none;
  outline: none;
  font-size: 13px;
  min-width: 80px;
  flex: 1;
  padding: 0;
  background: transparent;
}
.agenda-card-side {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 4px;
  flex-shrink: 0;
}
.card-side-row {
  display: flex;
  flex-direction: row;
  align-items: center;
  gap: 4px;
}
.agenda-due {
  font-size: 11px;
  color: var(--text-muted);
  margin-bottom: 2px;
}
.priority-badge {
  font-size: 11px;
  font-weight: 600;
  padding: 1px 6px;
  border-radius: 10px;
  margin-bottom: 2px;
}
.priority-high { background: #fee2e2; color: #b91c1c; }
.priority-normal { background: #e0f2fe; color: #0369a1; }
.priority-low { background: #f3f4f6; color: #6b7280; }
.edit-form-row { display: flex; gap: 6px; }

/* 안건 유형 */
.agenda-type-badge {
  font-size: 12px; font-weight: 600; color: var(--text-muted);
}
.agenda-order { font-size: 12px; font-weight: 700; color: var(--text-muted); }
.agenda-presenter { font-size: 11px; color: var(--text-muted); }
.agenda-duration { font-size: 11px; color: var(--text-muted); }

.dept-tag {
  font-size: 12px;
  color: var(--text-muted);
  font-weight: 500;
}

/* ── Todo chips (under pending) ── */
.todo-list { display: flex; flex-direction: column; gap: 4px; margin: 6px 0 4px; }
.todo-chip-row {
  display: flex;
  align-items: center;
  gap: 6px;
  min-height: 26px;
}
.todo-dot-sm {
  width: 5px; height: 5px; border-radius: 50%;
  background: #6366f1; flex-shrink: 0;
}
.todo-chip-text { flex: 1; font-size: 12px; color: #374151; }
.todo-chip-acts { display: flex; gap: 2px; opacity: 0; transition: opacity .15s; flex-shrink: 0; }
.todo-chip-row:hover .todo-chip-acts,
.todo-card:hover .todo-chip-acts { opacity: 1; }
.icon-micro {
  font-size: 10px; line-height: 1; padding: 1px 3px;
  background: none; border: none; cursor: pointer;
  color: var(--text-muted); border-radius: 3px;
}
.icon-micro:hover { background: #f1f5f9; color: var(--text); }
.todo-inline-input {
  flex: 1; padding: 3px 6px !important; font-size: 12px !important;
  min-height: unset !important; height: 26px;
}
.todo-add-btn { font-size: 11px; color: var(--text-muted); margin-top: 4px; padding: 2px 6px; }

.agenda-group-label {
  margin: 14px 0 4px;
  border-bottom: 1px solid var(--border);
  padding-bottom: 5px;
}
.agenda-group-label:first-of-type { margin-top: 0; }
.agenda-group-count { font-weight: 400; }
.agenda-group-toggle {
  cursor: pointer;
  user-select: none;
  display: flex;
  align-items: center;
  gap: 6px;
}
.agenda-group-toggle:hover { color: var(--text); }
.agenda-group-toggle.drag-section-over {
  background: var(--bg-hover, #f1f5f9);
  border-radius: 4px;
  outline: 2px dashed var(--border);
}
.agenda-collapse-icon { font-size: 9px; color: var(--text-muted); }
.agenda-flat-top {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 6px;
  flex-wrap: wrap;
}
.approved-agenda-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
  flex-wrap: wrap;
}
.approved-agenda-title { font-size: 14px; font-weight: 600; color: var(--text); flex: 1; }
.approved-todos { display: flex; flex-direction: column; gap: 5px; }
.approved-todo-row {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  font-size: 13px;
  color: #374151;
  padding: 6px 8px;
  background: rgba(255,255,255,.7);
  border-radius: 4px;
  min-height: 28px;
}
.approved-todo-row .todo-chip-acts { opacity: 0; transition: opacity .15s; flex-shrink: 0; }
.approved-todo-row:hover .todo-chip-acts { opacity: 1; }
.todo-status-icon { font-size: 13px; flex-shrink: 0; margin-top: 1px; }
.todo-row-body { flex: 1; display: flex; flex-direction: column; gap: 3px; }
.todo-row-content { font-size: 13px; font-weight: 500; color: var(--text); }
.todo-row-meta { display: flex; gap: 6px; flex-wrap: wrap; }
.todo-meta-chip { font-size: 11px; color: var(--text-muted); background: #f1f5f9; padding: 1px 6px; border-radius: 99px; }
.todo-tag-chip { font-size: 11px; color: #7c3aed; background: #ede9fe; padding: 1px 6px; border-radius: 99px; font-weight: 600; }
.todo-row-details { display: flex; gap: 12px; font-size: 11px; color: var(--text-muted); }
.todo-add-row { display: flex; gap: 6px; margin-top: 4px; }

/* ── 상세 To-do 입력 폼 ── */
.date-with-wd {
  display: flex; align-items: center;
  width: 100%; border: 1px solid var(--border); border-radius: 6px;
  background: #fff; transition: border-color .15s; overflow: hidden;
}
.date-with-wd:focus-within { border-color: var(--accent); box-shadow: 0 0 0 3px rgba(59,130,246,.1); }
.date-with-wd input[type="date"] {
  flex: 1; border: none !important; box-shadow: none !important;
  padding: 8px 12px; font-size: 13px; background: transparent; outline: none;
}
.weekday-hint { padding-right: 12px; font-size: 13px; color: var(--text-muted); white-space: nowrap; font-weight: 600; pointer-events: none; }
.todo-detail-form, .todo-edit-form {
  background: #f8fafc; border: 1px solid var(--border); border-radius: 8px;
  padding: 12px; display: flex; flex-direction: column; gap: 6px; margin-top: 8px;
}
.edit-form-row { display: flex; gap: 6px; }
.todo-form-row { display: flex; gap: 6px; }
.todo-tags-row { display: flex; gap: 6px; flex-wrap: wrap; }
.tag-toggle-btn {
  padding: 2px 8px; border-radius: 99px; font-size: 11px; font-weight: 600;
  background: #f1f5f9; color: var(--text-muted); border: 1px solid var(--border);
  cursor: pointer; transition: all .15s;
}
.tag-toggle-btn.active { background: #ede9fe; color: #7c3aed; border-color: #c4b5fd; }
.todo-form-actions { display: flex; gap: 6px; margin-top: 4px; }

.approved-no-todo { font-size: 12px; color: var(--text-muted); padding: 4px 0; }

/* ── Agenda assign view ── */
.agenda-assign-view { display: flex; flex-direction: column; gap: 4px; }
.assign-row { display: flex; gap: 8px; align-items: flex-start; font-size: 13px; }
.assign-key { flex-shrink: 0; width: 80px; font-size: 11px; font-weight: 600; color: var(--text-muted); padding-top: 1px; }
.assign-val { flex: 1; color: var(--text); line-height: 1.5; }
.assign-form-label { font-size: 11px; font-weight: 600; color: var(--text-muted); margin-bottom: 3px; }

/* ── Todo cards (new design) ── */
.todo-group { display: flex; flex-direction: column; gap: 6px; }

.todo-card { gap: 5px; }
.todo-card-header { display: flex; align-items: center; gap: 8px; }

/* Status toggle */
.todo-status-wrap {
  display: flex; align-items: center; gap: 4px;
  position: relative; cursor: pointer;
  padding: 2px 6px; border-radius: 99px;
  background: #f8fafc; border: 1px solid var(--border);
  font-size: 12px;
  user-select: none;
}
.todo-status-label { color: var(--text-muted); font-size: 11px; }
.todo-status-dropdown {
  position: absolute; top: calc(100% + 4px); left: 0; z-index: 20;
  background: #fff; border: 1px solid var(--border); border-radius: var(--radius);
  box-shadow: 0 4px 12px rgba(0,0,0,.1);
  display: flex; flex-direction: column; min-width: 100px;
  overflow: hidden;
}
.todo-status-opt {
  padding: 7px 12px; font-size: 12px; text-align: left;
  background: none; border: none; cursor: pointer;
  color: var(--text);
}
.todo-status-opt:hover { background: #f8fafc; }
.todo-form-section-label { font-size: 12px; font-weight: 700; color: var(--text-muted); margin-bottom: 4px; }

/* ── Filter row ── */
.filter-row { display: flex; align-items: center; gap: 8px; margin-bottom: 4px; }
.dept-select {
  padding: 6px 10px;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  font-size: 13px;
  background: #fff;
  cursor: pointer;
  min-width: 120px;
}

/* ── HITL banner ── */
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

/* ── Drag overlay ── */
.drag-overlay {
  position: absolute; inset: 0; z-index: 10;
  background: rgba(99,102,241,.08);
  border: 2px dashed var(--primary,#6366f1);
  border-radius: var(--radius);
  display: flex; align-items: center; justify-content: center;
  pointer-events: none;
}
.drag-hint {
  background: white;
  border: 1px solid var(--primary,#6366f1);
  border-radius: var(--radius);
  padding: 12px 24px;
  font-size: 14px;
  font-weight: 600;
  color: var(--primary,#6366f1);
  box-shadow: 0 2px 8px rgba(0,0,0,.08);
}

/* ── 타 회의체 경고 다이얼로그 ── */
.warn-overlay {
  position: fixed; inset: 0; z-index: 9999;
  background: rgba(0,0,0,.45);
  display: flex; align-items: center; justify-content: center;
}
.warn-dialog {
  background: #fff;
  border-radius: 12px;
  box-shadow: 0 8px 32px rgba(0,0,0,.18);
  padding: 28px 32px;
  max-width: 400px;
  width: 90%;
  display: flex; flex-direction: column; align-items: center; gap: 12px;
  text-align: center;
}
.warn-icon { font-size: 32px; line-height: 1; }
.warn-title { font-size: 16px; font-weight: 700; color: #b45309; }
.warn-body { font-size: 13px; color: var(--text); line-height: 1.7; }
.warn-actions { display: flex; gap: 10px; margin-top: 4px; }
</style>
