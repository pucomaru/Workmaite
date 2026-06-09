<script setup>
import { ref, computed, reactive, shallowRef, onMounted, onBeforeUnmount, watch, nextTick, provide } from 'vue'
import GraphView from '../components/GraphView.vue'
import DetailSidebar from '../components/DetailSidebar.vue'
import AgentSidebar from '../components/AgentSidebar.vue'
import GraphLegend from '../components/GraphLegend.vue'
import GraphFloatBtns from '../components/GraphFloatBtns.vue'
import FloatDragPreview from '../components/FloatDragPreview.vue'
import MeetingListView from '../components/MeetingListView.vue'
import CreateMeetingModal from '../components/CreateMeetingModal.vue'
import CreateSessionModal from '../components/CreateSessionModal.vue'
import UploadModal from '../components/UploadModal.vue'
import SettingsModal from '../components/SettingsModal.vue'
import { useRouter } from 'vue-router'
import api, { apiAI, streamPostForm } from '../api'
import { useMeetingsStore } from '../stores/meetings'
import { useAuthStore } from '../stores/auth'
import { useThemeStore } from '../stores/theme'
import { useAgentChat } from '../composables/useAgentChat'
import { useGraphBuilder } from '../composables/useGraphBuilder'

const lvColumns = [
  { label: '회의체명', width: '480px', sortKey: 'title' },
  { label: '유형',    width: '160px', sortKey: 'meeting_type' },
  { label: '역할',   width: '110px', sortKey: '_role' },
  { label: '간사',   width: '300px', sortKey: '_adminName' },
  { label: '이력',   width: '160px', sortKey: '_histCount' }
]
const router = useRouter()
const meetingsStore = useMeetingsStore()
const authStore = useAuthStore()
const themeStore = useThemeStore()
const nightMode = computed(() => themeStore.nightMode)

// ─── Data ─────────────────────────────────────────────────────
const minutes = ref([])
const reports = ref([])
const membersData = ref([])
const tasksData = ref([])
const neo4jMeetings = ref([])   // Neo4j에서 직접 가져온 회의체 그래프 데이터
const neo4jDepts   = ref([])    // Neo4j Department 노드 id/name 매핑
const currentOrg = ref(null)    // 현재 조직 (Organization 노드)
const currentPerson = ref(null) // 현재 로그인 유저의 Neo4j Person 노드
const loading = ref(true)
const neo4jError = ref('')
const neo4jRetrying = ref(false)
const search = ref('')
const expandedMeeting = ref(null)

// ─── View mode ────────────────────────────────────────────────
const viewMode = ref('graph')
// nightMode는 전역 themeStore.nightMode(computed)를 사용합니다

// ─── 뷰 전환 시 패널 상태 저장/복원 ─────────────────────────
const _graphSnapshot = { detailOpen: false, agentSidebarOpen: false }
const _listSnapshot  = { expandedMeeting: null }

watch(viewMode, (next, prev) => {
  // graph ↔ list
  if (prev === 'graph' && next === 'list') {
    _graphSnapshot.detailOpen       = detailOpen.value
    _graphSnapshot.agentSidebarOpen = agentSidebarOpen.value
    detailOpen.value = false
    agentSidebarOpen.value = false
    expandedMeeting.value = _listSnapshot.expandedMeeting
  } else if (prev === 'list' && next === 'graph') {
    _listSnapshot.expandedMeeting = expandedMeeting.value
    expandedMeeting.value = null
    nextTick(() => {
      detailOpen.value       = _graphSnapshot.detailOpen
      agentSidebarOpen.value = _graphSnapshot.agentSidebarOpen
    })
  }
})

const graphViewRef = ref(null)  // GraphView (PIXI) 컴포넌트 ref
const graphPanOnly = ref(false) // 그래프 이동 전용 모드 상태
function toggleGraphPanOnly() {
  graphPanOnly.value = graphViewRef.value?.togglePanOnly?.() ?? false
}

// ─── Search highlight (meeting_group nodes containing match) ──
const searchHitMgIdxs = ref([])

function _recomputeSearchHits() {
  const q = search.value
  if (!q || !q.trim()) { searchHitMgIdxs.value = []; graphViewRef.value?.focusSearchHits([]); return }
  const lower = q.toLowerCase()
  const hits = []
  gNodes.forEach((n, i) => {
    const label = (n.label || '').toLowerCase()
    if (label.includes(lower)) { hits.push(i); return }
    if (n.type === 'meeting_group' && n.data) {
      const g = n.data
      const inMinutes = (g.minutes || []).some(m => (m.session_title || '').toLowerCase().includes(lower))
      const inReports = (g.reports || []).some(r => (r.file_name || r.title || '').toLowerCase().includes(lower))
      const inMembers = (g.members || []).some(m => (m.userName || m.name || '').toLowerCase().includes(lower))
      if (inMinutes || inReports || inMembers) hits.push(i)
    }
  })
  searchHitMgIdxs.value = hits
  graphViewRef.value?.focusSearchHits(hits)
}

watch(search, _recomputeSearchHits)

// ─── Node type visibility (eye toggle) ───────────────────────
const hiddenNodeTypes = ref([])  // array of type keys: 'org-root'|'meeting_group'|'dept'|'agenda'|'session'|'file'
function toggleNodeType(typeKey) {
  const idx = hiddenNodeTypes.value.indexOf(typeKey)
  if (idx >= 0) hiddenNodeTypes.value.splice(idx, 1)
  else hiddenNodeTypes.value.push(typeKey)
}
function isHiddenType(typeKey) { return hiddenNodeTypes.value.includes(typeKey) }

// ─── Map toast ────────────────────────────────────────────────
const mapToastMsg = ref('')
let _mapToastTimer = null
function showMapToast(msg) {
  mapToastMsg.value = msg
  clearTimeout(_mapToastTimer)
  _mapToastTimer = setTimeout(() => { mapToastMsg.value = '' }, 2200)
}

// ─── Neo4j query highlight (챗봇 그래프 탐색 시각화) ──────────
const queryHlIdxs     = ref(new Set())   // Set<number> — 현재 하이라이트된 노드 인덱스들
const queryHlEdgeIdxs = ref(new Set())   // Set<number> — 현재 하이라이트된 엣지 인덱스들
const queryHlStep     = ref('')          // 현재 planning step 텍스트 (HUD 표시용)
let _queryHlTimer  = null

/** Planning step 텍스트에서 관련 그래프 노드+엣지를 찾아 하이라이트 */
function _applyQueryHL(step) {
  clearTimeout(_queryHlTimer)
  queryHlStep.value = step
  const newSet = new Set()
  const specificSet = new Set() // 이름으로 정확히 매칭된 노드 (1-hop 확장 대상)

  if (step) {
    // 1) [ 이름 ] 패턴 — PLANNING 스텝에서 노드 이름 언급 시 flash
    const bracketRe = /\[([^\]]+)\]/g
    let m
    while ((m = bracketRe.exec(step)) !== null) {
      const txt = m[1]
      gNodes.forEach((n, i) => { if (n.label === txt || n.id === txt) { newSet.add(i); specificSet.add(i) } })
    }
    // 2) 타입 키워드 → 해당 타입만 flash (노드 확장 없음, PLANNING 시각 피드백용)
    if (newSet.size === 0) {
      if (step.includes('회의체') || step.includes('라우팅')) gNodes.forEach((n,i)=>{ if(n.type==='meeting_group') newSet.add(i) })
      else if (step.includes('아젠다')) gNodes.forEach((n,i)=>{ if(n.type==='agenda') newSet.add(i) })
      else if (step.includes('의사결정')) gNodes.forEach((n,i)=>{ if(n.type==='decision') newSet.add(i) })
      else if (step.includes('구성원') || step.includes('소속')) gNodes.forEach((n,i)=>{ if(n.type==='person') newSet.add(i) })
      else if (step.includes('세션') || step.includes('회의록')) gNodes.forEach((n,i)=>{ if(n.type==='session') newSet.add(i) })
    }
  }

  // 이름으로 정확히 매칭된 노드만 1-hop 확장 (타입 flash는 확장 없음)
  const hlEdgeSet = new Set()
  if (specificSet.size > 0) {
    gEdges.forEach((e, ei) => {
      if (specificSet.has(e.from) || specificSet.has(e.to)) {
        hlEdgeSet.add(ei)
        newSet.add(e.from)
        newSet.add(e.to)
      }
    })
  }

  queryHlIdxs.value = newSet
  queryHlEdgeIdxs.value = hlEdgeSet
  if (step) {
    _queryHlTimer = setTimeout(() => {
      queryHlIdxs.value = new Set()
      queryHlEdgeIdxs.value = new Set()
      queryHlStep.value = ''
    }, 2500)
  }
}

// ── AI 기반 하이라이팅: LLM 답변에서 실제 언급된 노드 레이블 기반 ──────
let _hlPersistTimer = null
function _applyHighlightLabels(labels) {
  clearTimeout(_hlPersistTimer)
  clearTimeout(_queryHlTimer)
  const newSet = new Set()
  const hlEdgeSet = new Set()
  labels.forEach(lbl => {
    gNodes.forEach((n, i) => {
      if (n.label === lbl || (lbl.length >= 6 && n.label?.startsWith(lbl.slice(0, Math.min(lbl.length, 10))))) newSet.add(i)
    })
  })
  // 매칭된 노드와 연결된 엣지 + 1-hop 인접 노드
  gEdges.forEach((e, ei) => {
    if (newSet.has(e.from) || newSet.has(e.to)) {
      hlEdgeSet.add(ei)
      newSet.add(e.from)
      newSet.add(e.to)
    }
  })
  queryHlIdxs.value = newSet
  queryHlEdgeIdxs.value = hlEdgeSet
  queryHlStep.value = ''
  // 6초 후 자동 소등
  _hlPersistTimer = setTimeout(() => {
    queryHlIdxs.value = new Set()
    queryHlEdgeIdxs.value = new Set()
  }, 6000)
}

// ─── Plus snackbar (removed - replaced by direct button) ──────

// ─── Create meeting modal ─────────────────────────────────────
const showCreateModal = ref(false)
const createForm = ref({ title: '', purpose: '', start_date: '', end_date: '', guidelines: '', meeting_type: 'Weekly' })
const createMembers = ref([])
const creating = ref(false)
const createConnectNodeId = ref('')

// ─── Create session modal ─────────────────────────────────────
const showSessionModal = ref(false)
const sessionForm = ref({ title: '', purpose: '', date: '', meeting_id: null })
const sessionMembers = ref([])
const creatingSession = ref(false)

function openCreateModal() {
  createForm.value = { title: '', purpose: '', start_date: '', end_date: '', guidelines: '', meeting_type: 'Weekly' }
  const me = authStore.user
  createMembers.value = me
    ? [{ userId: me.id, name: me.name, email: me.email || me.employee_id || '', role: 'admin' }]
    : []
  showCreateModal.value = true; agentSidebarOpen.value = false
}

function openSessionModal(meetingId = null) {
  sessionForm.value = { title: '', purpose: '', date: '', meeting_id: meetingId }
  sessionMembers.value = []
  showSessionModal.value = true; agentSidebarOpen.value = false
}
async function doCreateSession() {
  if (!sessionForm.value.title.trim()) return
  creatingSession.value = true
  try {
    const meetingId = sessionForm.value.meeting_id
    if (meetingId) {
      await apiAI.post(`/api/v1/meetings/${meetingId}/sessions`, {
        title: sessionForm.value.title,
        type: 'offline',
        description: sessionForm.value.purpose || null,
        scheduled_at: sessionForm.value.date || null,
      })
    }
    showSessionModal.value = false
    sessionForm.value = { title: '', purpose: '', date: '', meeting_id: null }
    sessionMembers.value = []
    setTimeout(refreshArchive, 600)
  } catch(e) { console.error(e) }
  finally { creatingSession.value = false }
}

async function doCreateMeeting() {
  if (!createForm.value.title.trim()) return
  creating.value = true
  try {
    const meeting = await meetingsStore.createMeeting({
      title: createForm.value.title, description: createForm.value.purpose,
      start_date: createForm.value.start_date || null, end_date: createForm.value.end_date || null,
      guidelines: createForm.value.guidelines || null, meeting_type: createForm.value.meeting_type || null,
    })
    const myId = authStore.user?.id
    for (const m of createMembers.value) {
      if (m.userId === myId) continue  // 생성 시 서버가 자동으로 admin 추가
      await api.post(`/api/v1/meetings/${meeting.id}/members`, { userId: m.userId, role: m.role })
    }
    createForm.value = { title: '', purpose: '', start_date: '', end_date: '', guidelines: '', meeting_type: 'Weekly' }
    createMembers.value = []; createMemberSearch.value = ''; createMemberResults.value = []
    createConnectNodeId.value = ''
    await meetingsStore.fetchMeetings()
    await refreshArchive()
    await nextTick()
    const g = buildGraphNodes()
    if (g.nodes.length > 0) {
      gNodes = g.nodes; gEdges = _applyLocalEdgeOverrides(g.nodes, g.edges); gNodesRef.value = gNodes
      graphViewRef.value?.reloadGraph(gNodes, gEdges)
    }
    setTimeout(refreshArchive, 1000)
  } catch(e) { console.error(e) }
  finally {
    showCreateModal.value = false
    creating.value = false
  }
}

// ─── Detail sidebar resize ─────────────────────────────────────
const sidebarW = ref(260)
let sidebarResizing = false, srStartX = 0, srStartW = 0
function onSidebarResizeStart(e) {
  sidebarResizing = true; srStartX = e.clientX; srStartW = sidebarW.value
  e.preventDefault()
}

// ─── Global mouse handler ───────────────────────────────────────
function onGlobalMouseMove(e) {
  if (sidebarResizing) {
    sidebarW.value = Math.max(200, Math.min(480, srStartW + (e.clientX - srStartX)))
  }

  if (floatDragging.value) {
    floatDragPos.value = { x: e.clientX, y: e.clientY }
    if (Math.hypot(e.clientX - floatDragStartX, e.clientY - floatDragStartY) > 5) floatDragMoved = true

    if (graphViewRef.value) {
      const anyNode   = graphViewRef.value.getNodeAtScreen(e.clientX, e.clientY)
      const validTypes = FLOAT_VALID_TYPES[floatDragging.value] ?? []
      const isValid   = anyNode && validTypes.includes(anyNode.type)

      floatDragTarget      = isValid ? anyNode : null
      floatDragNearInvalid = !!(anyNode && !isValid)

      if (isValid) {
        const pos = graphViewRef.value.getNodeScreenPos(anyNode.id)
        if (pos) {
          floatDragPreviewLine.value = { x1: pos.x, y1: pos.y, x2: e.clientX, y2: e.clientY }
        }
      } else {
        floatDragPreviewLine.value = null
      }
    }
  }
}

function onGlobalMouseUp() {
  sidebarResizing = false
  if (floatDragging.value) _onFloatDragEnd()
}

// ─── Hover ────────────────────────────────────────────
const hoverNode = ref(null)
let hoverNodeIdx = -1

// ─── Float button drag-to-node (mousedown 기반) ────────────────
const floatDragging      = ref(null)         // null | 'meeting' | 'session' | 'doc'
const floatDragPos       = ref({ x: 0, y: 0 }) // 뷰포트 좌표 (ghost 위치)
const floatDragPreviewLine = ref(null)        // { x1,y1,x2,y2 } 뷰포트 좌표
let floatDragTarget      = null              // gNode | null
let floatDragNearInvalid = false
let floatDragStartX = 0, floatDragStartY = 0
let floatDragMoved  = false

const FLOAT_VALID_TYPES = {
  meeting: ['meeting_group'],
  session: ['meeting_group'],
  doc:     ['meeting_group', 'dept', 'agenda'],
}

function onFloatBtnMouseDown(type, e) {
  floatDragging.value = type
  floatDragPos.value  = { x: e.clientX, y: e.clientY }
  floatDragStartX = e.clientX; floatDragStartY = e.clientY
  floatDragMoved = false; floatDragTarget = null
  floatDragNearInvalid = false; floatDragPreviewLine.value = null
  document.body.style.cursor = 'grabbing'

  function _capture() {
    document.removeEventListener('mouseup', _capture, true)
    if (floatDragging.value) _onFloatDragEnd()
  }
  document.addEventListener('mouseup', _capture, true)
  e.preventDefault()
}

function _onFloatDragEnd() {
  const type      = floatDragging.value
  const target    = floatDragTarget
  const moved     = floatDragMoved
  const nearInvalid = floatDragNearInvalid

  floatDragging.value = null; floatDragTarget = null
  floatDragPreviewLine.value = null; floatDragNearInvalid = false; floatDragMoved = false
  document.body.style.cursor = ''

  if (!moved) return  // 클릭 → @click 핸들러가 처리

  if (nearInvalid && !target) {
    showMapToast('해당 노드에 연결할 수 없습니다.')
    return
  }

  if (type === 'meeting') {
    openCreateModal()
  } else if (type === 'session') {
    const mgId = target?.type === 'meeting_group' ? toNumericId(target.id) : null
    openSessionModal(mgId ? meetingGroups.value.find(g => toNumericId(g.id) === mgId) : null)
  } else if (type === 'doc') {
    const ctx = {}
    if (target?.type === 'agenda') {
      ctx.connectNodeId = target.meetingGroupId || ''
      ctx.relatedTodoId = target.neo4jId || target.data?.id || ''
      ctx.agendaContent = target.data?.content || target.label || ''
      ctx.meetingId     = target.meetingGroupId || ''
    } else if (target?.type === 'dept') {
      ctx.connectNodeId = target.id
      ctx.meetingId     = target.meetingGroupId || ''
    } else if (target?.type === 'meeting_group') {
      ctx.meetingId = target.id
    }
    openUploadModal(ctx)
  }
}

// ─── Detail sidebar ───────────────────────────────────────────
const detailMeeting = ref(null)
const detailOpen = ref(false)
const detailTodos = ref([])
const detailNode = ref(null) // 회의체 외 노드 (부서/과제/회의/파일/사람 등)
const nodeDetailTab = ref('basic') // 'basic' | 'rel'

/** mg-001, mg-13 등 Neo4j/PG ID에서 정수 ID 추출 */
function toNumericId(id) {
  if (!id && id !== 0) return 0
  if (typeof id === 'number') return id
  const m = String(id).match(/(\d+)$/)
  return m ? parseInt(m[1], 10) : 0
}

function openNodeDetail(n) {
  detailNode.value = n
  detailMeeting.value = null
  detailOpen.value = true
  nodeDetailTab.value = 'basic'
  relAddActive.value = false
}

// 현재 회의체 참여 부서 목록
const detailMemberDepts = computed(() => {
  const depts = new Set((detailMeeting.value?.members || [])
    .map(mb => mb.department || mb.dept || '')
    .filter(Boolean))
  return depts
})

// 팀별 그룹핑 (현재 회의체 관련 부서만)
const groupedTodos = computed(() => {
  const groups = {}
  for (const todo of detailTodos.value) {
    const dept = todo.assignee_dept || todo.dept ||
      (Array.isArray(todo.department) ? todo.department[0] : todo.department) || '미배정'
    if (!groups[dept]) groups[dept] = []
    groups[dept].push(todo)
  }
  return groups
})

async function completeTodo(todo) {
  const newStatus = todo.status === 'done' ? 'ongoing' : 'done'
  try {
    await apiAI.patch(`/api/agent/archive/agendas/${todo.id}/status`, { status: newStatus })
    todo.status = newStatus
  } catch (e) { console.error('상태 변경 실패:', e) }
}

async function deleteTodo(todo) {
  try {
    await apiAI.delete(`/api/agent/archive/agendas/${todo.id}`)
    detailTodos.value = detailTodos.value.filter(t => t.id !== todo.id)
  } catch (e) { console.error('삭제 실패:', e) }
}
// D-day: detailMeeting의 end_date 기준 남은 일수
const detailDday = computed(() => {
  const ed = detailMeeting.value?.end_date
  if (!ed) return null
  const now = new Date(); now.setHours(0,0,0,0)
  const due = new Date(ed); due.setHours(0,0,0,0)
  return Math.ceil((due - now) / 86400000)
})
const detailEndDateFormatted = computed(() => {
  const ed = detailMeeting.value?.end_date
  if (!ed) return null
  const d = new Date(ed)
  return `${d.getFullYear()}.${String(d.getMonth()+1).padStart(2,'0')}.${String(d.getDate()).padStart(2,'0')}`
})

// 부서별 보고서 제출 현황
const detailDeptStatus = computed(() => {
  const depts = [...new Set((detailMeeting.value?.members||[]).map(mb => mb.department||mb.dept||'').filter(Boolean))]
  return depts.map(dept => {
    const tasks = detailTodos.value.filter(t => (t.assignee_dept||t.dept||'') === dept)
    const noTask = tasks.length === 0
    const submitted = !noTask && tasks.every(t => t.status === 'done')
    const pending = tasks.filter(t => t.status !== 'done')
    let minDays = null
    if (pending.length > 0) {
      const now = new Date(); now.setHours(0,0,0,0)
      const days = pending.filter(t => t.due_date).map(t => {
        const due = new Date(t.due_date); due.setHours(0,0,0,0)
        return Math.ceil((due - now) / 86400000)
      })
      if (days.length) minDays = Math.min(...days)
    }
    return { dept, submitted, noTask, pendingCount: pending.length, minDays }
  })
})

const groupTodoRatio = ref(new Map())
const showExtractModal = ref(false)
const detailTab = ref('basic') // 'basic' | 'task'
// 추출 상태 단순 ref (meeting 전환 시 openDetail에서 리셋)
const extractPhase = ref('context')
const selectedMinutes = ref([]) // 선택된 회의록 ID
const selectedFiles = ref([]) // 선택된 파일 ID
const selectedSimilarDocs = ref([]) // 선택된 유사 문서 ID
const uploadedCtxFiles = ref([]) // 새로 업로드된 파일

function onCtxFilesAdded(files) {
  uploadedCtxFiles.value.push(...files)
  selectedFiles.value.push(...files.map((_, i) => 'upload_' + (uploadedCtxFiles.value.length - files.length + i)))
}
const extractResult = ref([])
const showExtractFlow = ref(false)
const extractLoading = ref(false)

// draft 복원 공통 함수
async function _restoreDrafts(meetingId) {
  if (!meetingId || extractLoading.value) return
  const numId = _toNumericId(meetingId)
  if (!numId) return
  try {
    const { data: drafts } = await apiAI.get(`/api/agent/meetings/${numId}/draft-agendas`)
    if (drafts && drafts.length) {
      extractResult.value = drafts.map(ag => ({
        ...ag,
        _state: null, _editing: false,
        _editTitle: ag.title,
        _editDept: Array.isArray(ag.department) ? (ag.department[0] || '') : (ag.department || ''),
        _editStartDate: ag.start_date || '',
        _editDueDate: ag.due_date || '',
        _agentLogId: null,
        _feedbackVisible: false, _feedbackAction: '', _feedbackText: '',
      }))
    } else {
      extractResult.value = []
    }
  } catch { extractResult.value = [] }
}

// 과제추출 탭 활성화 시 draft 자동 체크
watch(detailTab, async (tab) => {
  if (tab === 'extract' && !extractResult.value.length && !extractLoading.value && detailMeeting.value) {
    await _restoreDrafts(detailMeeting.value.id)
  }
})

async function saveAgendaFeedback(ag) {
  if (ag.db_id) {
    try {
      await apiAI.post('/api/agent/hitl-reviews', {
        target_type: 'agenda',
        target_id: ag.db_id,
        agent_log_id: ag._agentLogId || null,
        status: ag._feedbackAction || 'edited',
        review_prompt: {
          agenda: ag._origTitle ?? ag.title,
          department: ag._origDept ?? ag.department ?? null,
          start_date: ag._origStartDate ?? ag.start_date ?? null,
          end_date: ag._origEndDate ?? ag.due_date ?? null,
        },
        review_comment: {
          agenda: ag.title,
          department: ag.department ?? null,
          start_date: ag.start_date ?? null,
          end_date: ag.due_date ?? null,
          comment: ag._feedbackText || null,
        },
      })
    } catch (e) { console.warn('[hitl-reviews] 저장 실패 (계속 진행):', e) }
  }
  ag._feedbackVisible = false
  ag._feedbackText = ''
  if (ag._feedbackAction === 'rejected') {
    const idx = extractResult.value.indexOf(ag)
    if (idx !== -1) extractResult.value.splice(idx, 1)
  }
}

// 추출 결과를 채팅 메시지 형식으로 포맷
function _formatExtractForChat(agendas) {
  if (!agendas.length) return '추출된 과제가 없습니다. 회의록이나 자료를 추가 후 다시 시도해주세요.'
  const lines = [`${agendas.length}개 과제를 추출했습니다. 수정이 필요하면 말씀해 주세요.\n`]
  agendas.forEach((ag, i) => {
    lines.push(`**${i + 1}. ${ag.title}**`)
    const dates = [ag.start_date && `시작 ${ag.start_date}`, ag.due_date && `마감 ${ag.due_date}`].filter(Boolean)
    if (dates.length) lines.push(`  ${dates.join(' · ')}`)
    if (ag.department) lines.push(`  담당: ${ag.department}`)
    lines.push('')
  })
  return lines.join('\n').trim()
}

// 과제 탭에서 인라인으로 추출 실행
async function runExtract() {
  if (!detailMeeting.value) return

  const mgTitle = detailMeeting.value?.title || '회의체'

  // 채팅 초기화 후 사용자 메시지 + 사고 과정 + 에이전트 응답 슬롯을 순서대로 추가
  allMessages.value['supervisor'] = [{ role: 'agent', content: SUPERVISOR_EXTRACT.greeting }]
  agentSidebarOpen.value = true
  showExtractFlow.value = true
  extractPhase.value = 'result'
  detailTab.value = 'extract'
  extractLoading.value = true
  agentLoading.value = true
  extractResult.value = []

  allMessages.value['supervisor'].push({ role: 'user', content: `"${mgTitle}" 회의록·자료에서 과제를 추출해줘` })
  const planningMsg = reactive({ role: 'planning', steps: [], open: true, done: false })
  allMessages.value['supervisor'].push(planningMsg)
  const agentMsg = reactive({ role: 'agent', content: '' })
  allMessages.value['supervisor'].push(agentMsg)

  await nextTick()
  if (agentMessagesEl.value) agentMessagesEl.value.scrollTop = agentMessagesEl.value.scrollHeight

  // 사고 과정 애니메이션과 API 호출을 병렬 실행
  const planningSteps = [
    `Neo4j MATCH (mg:MeetingGroup {title:"${mgTitle}"}) 조회`,
    `MATCH (mg)-[:ATTACHED_TO|PRODUCED]-(doc:Document) 문서 수집`,
    `선택된 회의록 및 첨부 파일 텍스트 분석 중...`,
    `Context Graph: 유사 Decision 노드 참조`,
    `아젠다 후보 생성 중...`,
  ]
  const planningPromise = _runPlanningSteps(planningMsg, planningSteps)

  try {
    const formData = new FormData()
    formData.append('meeting_id', String(toNumericId(detailMeeting.value.id)))
    formData.append('selected_file_ids', JSON.stringify(
      selectedFiles.value.filter(f => !String(f).startsWith('upload_'))
    ))
    formData.append('selected_similar_docs', JSON.stringify(selectedSimilarDocs.value))
    for (const file of uploadedCtxFiles.value) {
      formData.append('files', file)
    }

    const { data } = await apiAI.post('/api/agent/archive/extract-agendas', formData)
    await planningPromise

    if (data.agendas && data.agendas.length) {
      const agentLogId = data.agent_log_id || null
      extractResult.value = data.agendas.map(ag => ({
        ...ag,
        _state: null,
        _editing: false,
        _editTitle: ag.title,
        _editStartDate: ag.start_date || '',
        _editDueDate: ag.due_date || '',
        _editDept: Array.isArray(ag.department) ? (ag.department[0] || '') : (ag.department || ''),
        db_id: ag.db_id || null,
        _agentLogId: agentLogId,
        _feedbackVisible: false, _feedbackAction: '', _feedbackText: '',
      }))
      // 실제 추출 결과를 채팅에 표시
      agentMsg.content = _formatExtractForChat(extractResult.value)
    } else {
      const errMsg = data.error ? `추출 중 오류: ${data.error}` : '추출된 과제가 없습니다. 회의록이나 자료를 선택 후 다시 시도해주세요.'
      agentMsg.content = errMsg
      extractResult.value = []
    }
  } catch (e) {
    await planningPromise
    agentMsg.content = '과제 추출 중 오류가 발생했습니다.'
    extractResult.value = []
  } finally {
    extractLoading.value = false
    agentLoading.value = false
    await nextTick()
    if (agentMessagesEl.value) agentMessagesEl.value.scrollTop = agentMessagesEl.value.scrollHeight
  }
}

// extractTextFromFile 함수 제거 (백엔드에서 처리)

async function openExtractModal() {
  showExtractModal.value = true
  agentSidebarOpen.value = true
  if (!detailMeeting.value) return
  extractLoading.value = true
  extractResult.value = []
  try {
    const { data } = await apiAI.post('/api/agent/archive/extract-agendas', {
      meeting_id: toNumericId(detailMeeting.value.id),
      graph_context: buildGraphContextStr ? buildGraphContextStr() : ''
    })
    extractResult.value = (data.agendas || []).map(ag => ({ ...ag, _state: null, _editing: false, _editTitle: ag.title, _editStartDate: ag.start_date || '', _editDueDate: ag.due_date || '' }))
  } catch {
    extractResult.value = [
      { title: 'API 성능 최적화 PoC 결과 검토', bullets: ['현재까지 진행 현황 공유', '병목 구간 원인 분석', '3주 내 개선 목표 수립'], _state: null, _editing: false },
      { title: 'Q2 캠페인 KPI 중간 점검', bullets: ['CTR / 전환율 현황', '예산 소진율 검토', '채널별 효율 재배분 제안'], _state: null, _editing: false },
    ]
  } finally { extractLoading.value = false }
}
function setExtractState(i, state) {
  extractResult.value[i]._state = extractResult.value[i]._state === state ? null : state
}
function addExtractItem() {
  extractResult.value.push({ title: '', _state: null, _editing: true, _editTitle: '', _editStartDate: '', _editDueDate: '', _feedbackVisible: false, _feedbackAction: '', _feedbackText: '' })
}

async function finishExtract() {
  const approved = extractResult.value.filter(a => a._state === 'approved')
  const rejected = extractResult.value.filter(a => a._state === 'rejected' && a.db_id)
  if ((!approved.length && !rejected.length) || !detailMeeting.value) return

  try {
    await apiAI.post('/api/agent/archive/agendas/commit', {
      meeting_id: toNumericId(detailMeeting.value.id),
      approved: approved.map(a => ({
        db_id: a.db_id,
        dept: a.department || null,
        due_date: a.due_date || null,
      })),
      rejected_ids: rejected.map(a => a.db_id),
    })

    detailTodos.value = (await apiAI.get(`/api/agent/meetings/${toNumericId(detailMeeting.value.id)}/agendas`)).data || []
    extractPhase.value = 'context'
    showExtractFlow.value = false
    extractResult.value = []
    detailTab.value = 'task'
    setTimeout(refreshArchive, 600)
  } catch (e) {
    console.error('완료 처리 오류:', e)
  }
}

const PRIORITY_LABEL = { urgent_important: '긴급·중요', important: '중요', urgent: '긴급', normal: '보통', low: '낮음' }
const STATUS_LABEL = { pending: '대기', in_progress: '진행', submitted: '승인대기', done: '완료' }

function goToProcessStep(step) {
  if (step === 'context' && extractPhase.value === 'result') {
    extractPhase.value = 'context'
  }
}

// ─── 회의체 설정 모달 (MeetingGroupsPage 동일 패턴) ────────────
const settingsModal = ref(null)
const settingsSearchQ = ref('')
const settingsSearchResults = ref([])
const settingsSearchLoading = ref(false)
const savingSettings = ref(false)
let settingsSearchTimer = null

async function openGroupSetting() {
  if (!detailMeeting.value) return
  const m = detailMeeting.value
  let members = []
  try {
    const res = await api.get(`/api/v1/meetings/${m.id}/members`)
    members = res.data.map(mb => ({
      id: mb.id,
      userId: mb.user?.id || mb.user_id,
      name: mb.user?.name || mb.userName || mb.name || '?',
      email: mb.user?.email || mb.email || '',
      department: mb.user?.department || mb.department || '',
      organization: mb.user?.organization || mb.organization || '',
      position: mb.user?.position || mb.position || '',
      role: mb.role || 'member',
    }))
  } catch { members = (m.members || []).map(mb => ({ id: null, userId: mb.userId, name: mb.userName || '?', email: '', role: 'member' })) }
  settingsModal.value = {
    meeting: m,
    form: { title: m.title || '', purpose: m.purpose || m.description || '', guidelines: m.guidelines || '' },
    members,
    removedIds: [],
  }
  settingsSearchQ.value = ''
  settingsSearchResults.value = []
}

function closeSettings() { settingsModal.value = null }

function watchSettingsSearch(q) {
  settingsSearchQ.value = q
  clearTimeout(settingsSearchTimer)
  if (!q.trim()) { settingsSearchResults.value = []; return }
  settingsSearchTimer = setTimeout(async () => {
    settingsSearchLoading.value = true
    try {
      const res = await api.get('/api/v1/users/search', { params: { q } })
      settingsSearchResults.value = res.data
    } catch { settingsSearchResults.value = [] }
    finally { settingsSearchLoading.value = false }
  }, 300)
}

function addMemberToSettings(user) {
  if (!settingsModal.value) return
  if (settingsModal.value.members.find(m => m.userId === user.id)) return
  settingsModal.value.members.push({ id: null, userId: user.id, name: user.name || user.email, email: user.email, role: 'member' })
  settingsSearchQ.value = ''
  settingsSearchResults.value = []
}

function removeMemberFromSettings(idx) {
  const m = settingsModal.value.members[idx]
  if (m.id) settingsModal.value.removedIds.push(m.id)
  settingsModal.value.members.splice(idx, 1)
}

async function saveSettings() {
  if (!settingsModal.value) return
  savingSettings.value = true
  const { meeting, form, members, removedIds } = settingsModal.value
  try {
    await apiAI.patch(`/api/v1/meetings/${meeting.id}`, { title: form.title, description: form.purpose, guidelines: form.guidelines })
    for (const memberId of removedIds) {
      await apiAI.delete(`/api/v1/meetings/${meeting.id}/members/${memberId}`)
    }
    for (const mb of members.filter(m => m.id === null)) {
      await apiAI.post(`/api/v1/meetings/${meeting.id}/members`, { userId: mb.userId, role: mb.role })
    }
    if (detailMeeting.value?.id === meeting.id) {
      detailMeeting.value.title = form.title
    }
    await meetingsStore.fetchMeetings()
    settingsModal.value = null
    // Neo4j 동기화 반영 후 그래프 재로드
    setTimeout(refreshArchive, 600)
  } catch (e) { alert(e.response?.data?.detail || '저장 실패') }
  finally { savingSettings.value = false }
}

const ROLE_MAP = { admin: '간사', member: '참여자' }
function roleLabel(r) { return ROLE_MAP[r] || r || '참여자' }

// ─── Role-based helpers ───────────────────────────────────────
/** 현재 로그인 유저가 해당 회의체 members 배열에서 가지는 역할(admin/member)을 찾는다.
 *  meetingRoles(SpringBoot)가 비어 있어도 Neo4j archive 응답의 members로 판정 가능. */
function selfRoleInGroup(group) {
  const myId    = authStore.user?.id
  const myEmail = currentPerson.value?.email || authStore.user?.email || authStore.user?.employee_id
  const myName  = currentPerson.value?.name  || authStore.user?.name
  const self = (group?.members || []).find(mb =>
    (myId != null && mb.userId != null && String(mb.userId).replace(/\D/g, '') === String(myId)) ||
    (myEmail && mb.email && mb.email === myEmail) ||
    (myName && (mb.userName === myName || mb.name === myName))
  )
  return self?.role ?? null
}
const detailMyRole = computed(() => {
  if (!detailMeeting.value?.id) return null
  const fromStore = meetingsStore.meetingRoles[toNumericId(detailMeeting.value.id)]
  if (fromStore != null) return fromStore
  // SpringBoot 역할 정보가 없으면 Neo4j members 기반으로 판정
  return selfRoleInGroup(detailMeeting.value)
})
const isDetailAdmin = computed(() => detailMyRole.value === 'admin')
const isAnyAdmin = computed(() => {
  // PostgreSQL 기반 role 확인
  if (Object.values(meetingsStore.meetingRoles).some(r => r === 'admin')) return true
  // Neo4j 기반: meetings의 members 배열에서 현재 유저 role 확인
  const myEmail = currentPerson.value?.email || authStore.user?.employee_id
  const myName  = currentPerson.value?.name  || authStore.user?.name
  return neo4jMeetings.value.some(mg =>
    (mg.members || []).some(mb =>
      (mb.email === myEmail || mb.userName === myName) && mb.role === 'admin'
    )
  )
})
const AVATAR_COLORS = ['#6366f1','#3b82f6','#10b981','#f59e0b','#ef4444','#8b5cf6','#ec4899']
function avatarColor(name) { let h=0; for(const c of (name||'')) h=(h*31+c.charCodeAt(0))%AVATAR_COLORS.length; return AVATAR_COLORS[h] }
function initials(name) { return (name || '?')[0] }

function goToList(meetingId) {
  _listSnapshot.expandedMeeting = meetingId || null
  viewMode.value = 'list'
  detailOpen.value = false
}

async function openDetail(groupData) {
  if (!groupData) return
  const isSameMeeting = detailMeeting.value?.id === groupData.id
  detailMeeting.value = groupData; detailOpen.value = true; detailTab.value = 'basic'
  detailNode.value = null
  if (!isSameMeeting) {
    selectedMinutes.value = []; selectedFiles.value = []
    selectedSimilarDocs.value = []; uploadedCtxFiles.value = []
    extractPhase.value = 'context'; showExtractFlow.value = false; extractResult.value = []
  }
  hoverNode.value = null
  detailTodos.value = []

  const numId = _toNumericId(groupData.id)

  if (numId > 0) {
    try {
      const res = await apiAI.get(`/api/agent/meetings/${numId}/agendas`)
      detailTodos.value = res.data || []
    } catch (e) {
      console.error(`[Task] 과제 로드 실패 (meeting=${numId}):`, e?.response?.status)
      detailTodos.value = (groupData.tasks || []).filter(t => t.status !== 'draft')
    }
  } else {
    detailTodos.value = (groupData.tasks || []).filter(t => t.status !== 'draft')
  }

  if (!groupTodoRatio.value.has(groupData.id)) {
    const total = detailTodos.value.length
    const done = detailTodos.value.filter(t => t.status === 'done').length
    groupTodoRatio.value = new Map(groupTodoRatio.value).set(groupData.id, total ? done / total : null)
  }

  // draft 아젠다 복원 (다른 회의체로 전환 시)
  if (!isSameMeeting) {
    await _restoreDrafts(groupData.id)
  }
}

let gNodes = [], gEdges = []
const gNodesRef = shallowRef([])  // reactive mirror for provide/inject
const selfPersonNodeId = computed(() => {
  const myId   = authStore.user?.id
  const myName = currentPerson.value?.name || authStore.user?.name
  const node = gNodesRef.value.find(n => {
    if (n.type !== 'person') return false
    const mb = n.data
    if (myId != null && mb?.userId != null && String(mb.userId).replace(/\D/g, '') === String(myId)) return true
    if (myName && n.label === myName) return true
    return false
  })
  return node?.id ?? null
})
// ─── 로컬 관계 오버라이드: refreshArchive 후에도 유지 ────────
// key 형식: "fromNodeId|toNodeId" (양방향 모두 등록)
const localDeletedEdges = new Set()
const localAddedEdges   = [] // [{fromId, toId, rel}]
function _applyLocalEdgeOverrides(nodes, edges) {
  // 1) 삭제된 관계 제거
  let result = edges.filter(e => {
    const fId = nodes[e.from]?.id, tId = nodes[e.to]?.id
    return !localDeletedEdges.has(`${fId}|${tId}`) && !localDeletedEdges.has(`${tId}|${fId}`)
  })
  // 2) 추가된 관계 삽입
  localAddedEdges.forEach(({fromId, toId, rel}) => {
    const fi = nodes.findIndex(n => n.id === fromId)
    const ti = nodes.findIndex(n => n.id === toId)
    if (fi >= 0 && ti >= 0 && !result.find(e => e.from === fi && e.to === ti && e.rel === rel)) {
      result.push({ from: fi, to: ti, rel })
    }
  })
  return result
}
// ─── Upload modal ──────────────────────────────────────────────
const FILE_TYPES = ['보고자료', '발제자료', '회의록']
const FILE_TYPE_COLORS = { '보고자료': '#34d399', '발제자료': '#a78bfa', '회의록': '#60a5fa' }

// 발제자료 AI 검토 기준 4개 항목
const PRESENTATION_CRITERIA = [
  { key: 'recap',    label: '지난 논의 Recap',                desc: '이전 회의 논의사항 및 결정 사항 요약 포함' },
  { key: 'progress', label: '과제별 구체적 Progress',          desc: '각 과제별 현재까지의 구체적인 진행 현황' },
  { key: 'hurdle',   label: 'Hurdle & Pain point 극복 방안',  desc: '추진 과정상 장애요인 및 해결 방안 제시' },
  { key: 'plan',     label: '구체적 실행 계획 (Milestone)',    desc: '명확한 목표(수치), 100일/300일/1,000일 단위 계획' },
]

const showUploadModal = ref(false)
const uploadForm = ref({ label: '', fileType: '보고자료', connectNodeId: '', relType: '생성', meetingId: '', relatedTodoIds: [], agendaContent: '', file: null })
// 드래그로 자동 입력된 필드 추적 (직접 선택 시에는 표시 안 함)
const prefilledCtx = ref({ meetingId: false, connectNodeId: false, relatedTodoId: false })

let _pendingRelatedTodoId = ''
watch(() => uploadForm.value.meetingId, (id) => {
  const pendingTodo = _pendingRelatedTodoId
  _pendingRelatedTodoId = ''
  uploadForm.value.relatedTodoIds = []
  if (!id) return
  if (pendingTodo) uploadForm.value.relatedTodoIds = [pendingTodo]
})

// connectNodeId가 meeting_group이면 meetingId 자동 동기화
watch(() => uploadForm.value.connectNodeId, (nodeId) => {
  if (!nodeId) return
  const node = gNodes.find(n => n.id === nodeId)
  if (node?.type === 'meeting_group') {
    const mgData = node.data
    const rawId = mgData?.id ?? nodeId
    uploadForm.value.meetingId = (typeof rawId === 'string' && rawId.includes('-')) ? rawId : `mg-${rawId}`
  }
})

// ─── 파일 노드 AI 검토 패널 ────────────────────────────────────
// ─── Ontology edge relation constants ─────────────────────────
// ── Neo4j 관계명 색상 매핑 ─────────────────────────────────────
const REL_COLORS = {
  '포함':   '#a89fd4',  // org → meetingGroup
  '참여':   '#8b7fc0',  // dept/subGroup → meetingGroup
  '소속':   '#a78bfa',  // person → dept
  '간사':   '#fbbf24',  // person → meetingGroup (간사)
  '구성원': '#60a5fa',  // person → meetingGroup (구성원)
  '담당':   '#34d399',  // person → agenda
  '관할':   '#6abba5',  // agenda → meetingGroup
  '개최':   '#c9a870',  // session → meetingGroup
  '도출':   '#f472b6',  // session → agenda (캐리포워드 · 미니츠→안건)
  '다룸멌': '#6ee7b7',  // session → agenda (직접 담당 안건)
  '산출':   '#a8a5a2',  // session → document
  '첨부':   '#fb923c',  // document → meetingGroup
  '근거':   '#38bdf8',  // decision → session
  '원인':   '#86efac',  // decision → agenda
  '참조':   '#7a8090',  // generic reference
  '후속':   '#e879f9',  // session → session
  '출처':   '#94a3b8',  // document → meeting (sync)
  '생성':   '#c4b5fd',  // minutes → session
  '상위':   '#f9a8d4',  // meeting hierarchy
  '관련':   '#fcd34d',  // meeting → meeting
}
// ── 소스 타입 × 대상 타입 → Neo4j 관계 자동 추론 ──────────────
// 정방향 키 (from→to)로 관계와 Neo4j 방향 정의
// 역방향으로 드래그해도 canonical 방향을 자동으로 맞춤
const REL_MATRIX = {
  // ── Org / Dept ─────────────────────────────────────────────
  'dept→meeting_group':          '참여',
  'org→meeting_group':           '포함',
  'org→dept':                    '포함',
  'dept→dept':                   '포함',
  'person→dept':                 '소속',
  'dept→file':                   '첨부',
  'org→file':                    '참조',
  // ── MeetingGroup ───────────────────────────────────────────
  'meeting_group→meeting_group': '참여',
  'person→meeting_group':        '구성원',
  'file→meeting_group':          '첨부',
  // ── Agenda ─────────────────────────────────────────────────
  'agenda→meeting_group':        '관할',
  'person→agenda':               '담당',
  'file→agenda':                 '참조',
  // ── Session ────────────────────────────────────────────────
  'session→meeting_group':       '개최',
  'session→agenda':              '다룸멌',
  'session→file':                '산출',
  'session→session':             '후속',
  // ── Decision ───────────────────────────────────────────────
  'decision→session':            '근거',
  'decision→agenda':             '원인',
  'decision→meeting_group':      '근거',
  // ── File / Document ────────────────────────────────────────
  'file→file':                   '참조',
  'file→session':                '참조',
  'file→dept':                   '첨부',
  'person→file':                 '첨부',
}
function autoRel(sourceNodeId, targetType) {
  const srcNode = gNodes.find(n => n.id === sourceNodeId)
  const fwd = `${srcNode?.type}→${targetType}`
  if (REL_MATRIX[fwd]) return REL_MATRIX[fwd]
  // try reverse
  const rev = `${targetType}→${srcNode?.type}`
  return REL_MATRIX[rev] || '참조'
}

/**
 * 드래그 방향에 무관하게 canonical Neo4j 방향을 결정합니다.
 * @returns {{ rel, neo4jFromId, neo4jToId }}
 */
function resolveRel(fromIdx, toIdx) {
  const fn = gNodes[fromIdx], tn = gNodes[toIdx]
  const fwd = `${fn?.type}→${tn?.type}`
  if (REL_MATRIX[fwd]) return { rel: REL_MATRIX[fwd], neo4jFromId: fn?.id, neo4jToId: tn?.id }
  const rev = `${tn?.type}→${fn?.type}`
  if (REL_MATRIX[rev]) return { rel: REL_MATRIX[rev], neo4jFromId: tn?.id, neo4jToId: fn?.id }
  return { rel: '참조', neo4jFromId: fn?.id, neo4jToId: tn?.id }
}

// ─── Relationship manager ─────────────────────────────────────
const ALL_REL_TYPES = Object.keys(REL_COLORS)
const graphVersion = ref(0) // bump to force sidebar reactivity when gEdges mutate

const currentNodeId = computed(() => {
  if (detailMeeting.value) {
    // gNodes의 mgNodeId 생성 로직과 동일하게 맞춤:
    // g.id가 문자열이고 '-'를 포함하면 그대로, 아니면 "mg-{id}"
    const rawId = detailMeeting.value.id
    return (typeof rawId === 'string' && rawId.includes('-')) ? rawId : `mg-${rawId}`
  }
  return detailNode.value?.id || null
})

const currentNodeEdges = computed(() => {
  graphVersion.value // reactive dep
  const nodeId = currentNodeId.value
  if (!nodeId) return []
  const idx = gNodes.findIndex(n => n.id === nodeId)
  if (idx < 0) return []
  return gEdges
    .map((e, i) => ({ ...e, _idx: i }))
    .filter(e => e.from === idx || e.to === idx)
    .map(e => ({
      _idx: e._idx,
      fromNode: gNodes[e.from],
      toNode:   gNodes[e.to],
      rel:      e.rel,
      direction: e.from === idx ? 'out' : 'in',
    }))
})

const allGraphNodeList = computed(() => {
  graphVersion.value
  return gNodes.map(n => ({ id: n.id, label: n.label, type: n.type }))
})

const relAddActive = ref(false)
const relAddForm   = ref({ fromId: '', toId: '', rel: '참조' })
const relEditIdx   = ref(null)
const relEditRel   = ref('')

// Auto-suggest rel type when src/dst change in add form
watch(() => [relAddForm.value.fromId, relAddForm.value.toId], ([fId, tId]) => {
  if (!fId || !tId) return
  const tNode = gNodes.find(n => n.id === tId)
  relAddForm.value.rel = autoRel(fId, tNode?.type || '') || '참조'
})

function startRelEdit(edgeIdx) {
  relEditIdx.value = edgeIdx
  relEditRel.value = gEdges[edgeIdx]?.rel || ''
}
async function saveRelEdit() {
  if (relEditIdx.value !== null && gEdges[relEditIdx.value]) {
    const e = gEdges[relEditIdx.value]
    const fromNode = gNodes[e.from], toNode = gNodes[e.to]
    const oldRel = e.rel
    e.rel = relEditRel.value
    // Neo4j 동기화
    apiAI.put('/api/neo4j/relationships', {
      from_id: fromNode?.neo4jId || fromNode?.id,
      old_rel: oldRel,
      new_rel: relEditRel.value,
      to_id: toNode?.neo4jId || toNode?.id,
    }).then(() => setTimeout(refreshArchive, 600)).catch(() => {})
  }
  relEditIdx.value = null
  graphVersion.value++
}
function cancelRelEdit() { relEditIdx.value = null; relEditRel.value = '' }
// Neo4j mg-003 → 정수 ID 추출
function _toNumericId(id) {
  if (!id) return id
  if (/^\d+$/.test(String(id))) return id
  const m = String(id).match(/\d+$/)
  return m ? Number(m[0]) : id
}
function _normalizeNeo4jId(raw) {
  if (!raw) return raw
  const prefixes = ['mg-', 'session-', 'agenda-', 'doc-', 'dept-', 'p-', 'org-']
  for (const p of prefixes) {
    if (raw.startsWith(p + p)) return raw.slice(p.length)
  }
  return raw
}
async function doDeleteEdge(edgeIdx) {
  const e = gEdges[edgeIdx]
  const fromNode = gNodes[e?.from], toNode = gNodes[e?.to]
  // 로컬 오버라이드에 기록 (rebuild 후에도 삭제 유지)
  if (fromNode && toNode) {
    localDeletedEdges.add(`${fromNode.id}|${toNode.id}`)
    localDeletedEdges.add(`${toNode.id}|${fromNode.id}`)
    // localAddedEdges에서도 제거
    const ai = localAddedEdges.findIndex(x => x.fromId === fromNode.id && x.toId === toNode.id)
    if (ai >= 0) localAddedEdges.splice(ai, 1)
    // Neo4j 동기화
    apiAI.delete('/api/neo4j/relationships', { data: {
      from_id: _normalizeNeo4jId(fromNode.neo4jId || fromNode.id),
      rel_type: e.rel || '',
      to_id: _normalizeNeo4jId(toNode.neo4jId || toNode.id),
    }}).then(() => setTimeout(refreshArchive, 600)).catch(() => {})
  }
  gEdges.splice(edgeIdx, 1)
  relEditIdx.value = null
  graphVersion.value++
}
function openAddRel() {
  relAddForm.value = { fromId: currentNodeId.value || '', toId: '', rel: '참조' }
  relAddActive.value = true
}
async function doAddRel() {
  const { fromId, toId, rel } = relAddForm.value
  if (!fromId || !toId || !rel || fromId === toId) return
  const fromIdx = gNodes.findIndex(n => n.id === fromId)
  const toIdx   = gNodes.findIndex(n => n.id === toId)
  if (fromIdx < 0 || toIdx < 0) return
  if (gEdges.find(e => e.from === fromIdx && e.to === toIdx)) {
    showMapToast('이미 연결된 노드입니다.'); return
  }
  const fromNode = gNodes[fromIdx], toNode = gNodes[toIdx]
  // 로컬 오버라이드에 기록
  localAddedEdges.push({ fromId: fromNode.id, toId: toNode.id, rel })
  localDeletedEdges.delete(`${fromNode.id}|${toNode.id}`)
  localDeletedEdges.delete(`${toNode.id}|${fromNode.id}`)
  gEdges.push({ from: fromIdx, to: toIdx, rel })
  relAddActive.value = false
  graphVersion.value++
  // Neo4j 동기화
  apiAI.post('/api/neo4j/relationships', {
    from_id: _normalizeNeo4jId(fromNode.neo4jId || fromNode.id),
    rel_type: rel,
    to_id: _normalizeNeo4jId(toNode.neo4jId || toNode.id),
  }).then(() => setTimeout(refreshArchive, 600)).catch(() => {})
}

const connectableNodes = computed(() => {
  const groups = meetingGroups.value
  // '나' 노드: currentPerson.value.id = Neo4j User ID (e.g. 'p-123')
  // buildGraphNodes에서 생성되는 person 노드 ID 포맷: `person-${mb.userId}` 와 일치
  const result = []
  const myNeo4jId = currentPerson.value?.id
  const myLabel   = currentPerson.value?.name || authStore.user?.name || '나'
  if (myNeo4jId) {
    result.push({ id: `person-${myNeo4jId}`, label: `나 (${myLabel})`, typeLabel: '구성원', type: 'person', neo4jId: myNeo4jId })
  }
  const depts = new Set()
  groups.forEach(g => (g.members||[]).forEach(mb => depts.add(mb.department||mb.dept||'미지정')))
  depts.forEach(d => result.push({ id:`dept-${d}`, label:d, typeLabel:'부서', type:'dept' }))
  groups.forEach(g => {
    const rawId = g.id
    const mgId = (typeof rawId === 'string' && rawId.includes('-')) ? rawId : `mg-${rawId}`
    result.push({ id: mgId, label:g.title, typeLabel:'회의체', type:'meeting_group' })
  })
  groups.forEach(g => (g.minutes||[]).forEach((m,i) => result.push({ id:`session-${g.id}-${i}`, sessionId: m.id, label:m.session_title||`${m.session_number||i+1}차 회의`, typeLabel:'회의', type:'session' })))
  return result
})

// ─── Upload: connectable nodes (meeting_group / dept / agenda) ──────────────
const deptConnectableNodes = computed(() => {
  const seen = new Set()
  // 회의체 선택 시: 해당 회의체에 연결된 dept 노드만
  if (uploadForm.value.meetingId) {
    return gNodes
      .filter(n => n.type === 'dept' && n.meetingGroupId === uploadForm.value.meetingId)
      .filter(n => { if (seen.has(n.label)) return false; seen.add(n.label); return true })
      .map(n => ({ id: n.id, label: n.label, typeLabel: '부서', type: 'dept' }))
  }
  // 회의체 미선택 시: 전체 dept 노드
  return gNodes
    .filter(n => n.type === 'dept')
    .filter(n => { if (seen.has(n.label)) return false; seen.add(n.label); return true })
    .map(n => ({ id: n.id, label: n.label, typeLabel: '부서', type: 'dept' }))
})

// 선택된 회의체 노드에 연결된 과제들만 드롭다운에 표시 (맵 상 agenda 노드 기준)
// 사용자가 직접 추가한 과제(customAgendas)도 포함
const customAgendas = ref([])
const 업로드회의체과제 = computed(() => {
  if (!uploadForm.value.meetingId) return []
  const custom = customAgendas.value.map(c => ({ ...c, isCustom: true }))
  // 맵 상에서 해당 회의체에 연결된 agenda 노드 우선
  const mapAgendas = gNodes.filter(
    n => n.type === 'agenda' && n.meetingGroupId === uploadForm.value.meetingId
  )
  if (mapAgendas.length > 0) {
    return [
      ...mapAgendas.map(n => ({
        id: n.neo4jId || n.id,
        content: n.data?.content || n.label,  // 전체 내용 (맵은 12자 truncate)
        agenda_id: n.data?.pg_id ?? null,
      })),
      ...custom,
    ]
  }
  // fallback: 맵에 없으면 meeting_group 노드의 tasks
  const mgNode = gNodes.find(n => n.id === uploadForm.value.meetingId && n.type === 'meeting_group')
  if (mgNode?.data?.tasks?.length) return [...mgNode.data.tasks, ...custom]
  return custom
})

// 사용자가 직접 과제를 입력 → 후보 목록에 추가하고 자동 선택
function addCustomAgenda(content) {
  const text = (content || '').trim()
  if (!text) return
  const id = `agenda-custom-${Date.now()}`
  customAgendas.value.push({ id, content: text, agenda_id: null })
  if (!uploadForm.value.relatedTodoIds.includes(id)) {
    uploadForm.value.relatedTodoIds.push(id)
  }
}

// person 노드 → 참여 회의체 목록
function personMeetingGroups(node) {
  if (!node) return []
  const name = node.label
  return meetingGroups.value
    .filter(mg => (mg.members || []).some(mb => mb.userName === name || mb.name === name))
    .map(mg => {
      const mb = (mg.members || []).find(mb => mb.userName === name || mb.name === name)
      return { id: mg.id, title: mg.title, role: mb?.role }
    })
}

// person 노드 → 할당된 과제 목록
function personTasks(node) {
  if (!node) return []
  const name = node.label
  return meetingGroups.value.flatMap(mg =>
    (mg.tasks || []).filter(t => t.assignee_name === name)
  )
}

// ─── Upload: AI analysis state ────────────────────────────────
const uploadStep = ref(1)  // 1=manual input, 2=AI analysis result
const aiAnalyzing = ref(false)
const aiResult = ref(null)  // { score, feedback, agendas, related_depts }
const aiStreamText = ref('')   // 스트리밍 중 LLM 토큰 누적 텍스트
const aiStreamStage = ref('')  // 현재 진행 단계 메시지
const reportId = ref(null)        // AI 검토 시작 시 생성된 report ID
const uploadedFilePath = ref('')  // R2 업로드된 파일 경로
const isResubmit = ref(false)     // 재검토 모드 여부
const rejectedReports = ref([])   // 반려된 보고서 목록
const selectedParentId = ref(null) // 선택된 원본 report ID
const selectedAgendas = ref([])      // indices of agendas to apply
const selectedRelDepts = ref([])     // dept names to auto-connect

function openUploadModal(ctx = {}) {
  showUploadModal.value = true
  uploadStep.value = 1
  aiResult.value = null
  aiStreamText.value = ''
  aiStreamStage.value = ''
  selectedAgendas.value = []
  selectedRelDepts.value = []
  customAgendas.value = []
  reportId.value = null
  uploadedFilePath.value = ''
  isResubmit.value = false
  selectedParentId.value = null
  // 드래그로 자동 입력된 필드 기록
  prefilledCtx.value = {
    meetingId: !!ctx.meetingId,
    connectNodeId: !!ctx.connectNodeId,
    relatedTodoId: !!ctx.relatedTodoId,
  }
  // store pending relatedTodoId so the meetingId watcher can restore it after fetching todos
  _pendingRelatedTodoId = String(ctx.relatedTodoId || '')
  uploadForm.value = {
    label: '',
    fileType: '보고자료',
    connectNodeId: ctx.connectNodeId || '',
    relType: '생성',
    meetingId: ctx.meetingId || '',
    relatedTodoIds: ctx.relatedTodoId ? [String(ctx.relatedTodoId)] : [],
    agendaContent: ctx.agendaContent || '',
    file: null
  }
}

// Build graph context string for AI
function buildGraphContextStr() {
  const nodes = gNodes.map(n => `[${n.type}] ${n.label}`).join(', ')
  const edges = gEdges.map(e => {
    const f = gNodes[e.from], t = gNodes[e.to]
    return f && t ? `${f.label} →(${e.rel})→ ${t.label}` : null
  }).filter(Boolean).slice(0, 30).join('; ')
  return `노드: ${nodes}\n관계: ${edges}`
}

async function runAiAnalysis() {
  if (!uploadForm.value.label.trim() || !uploadForm.value.connectNodeId) return
  aiAnalyzing.value = true
  uploadStep.value = 2
  aiResult.value = null
  aiStreamText.value = ''
  aiStreamStage.value = '검토를 시작합니다…'
  const deptNode = connectableNodes.value.find(n => n.id === uploadForm.value.connectNodeId)
            || deptConnectableNodes.value.find(n => n.id === uploadForm.value.connectNodeId)

  const _mid = String(uploadForm.value.meetingId || '').replace(/^mg-/, '')

  // 파일을 먼저 R2에 업로드 → reports 테이블에 pending으로 저장
  if (uploadForm.value.file && _mid && /^\d+$/.test(_mid)) {
    try {
      const uploadFd = new FormData()
      uploadFd.append('file', uploadForm.value.file)
      uploadFd.append('dept_name', deptNode?.label || '')
      uploadFd.append('related_agenda_ids', JSON.stringify(uploadForm.value.relatedTodoIds || []))
      if (selectedParentId.value) {
        uploadFd.append('parent_report_id', String(selectedParentId.value))
      }
      const { data: uploadData } = await apiAI.post(
        `/api/upload/reports/${_mid}`,
        uploadFd,
        { headers: { 'Content-Type': 'multipart/form-data' } }
      )
      reportId.value = uploadData.id
      uploadedFilePath.value = uploadData.file_path
    } catch (e) {
      console.warn('[runAiAnalysis] 파일 업로드 실패:', e)
    }
  }

  // AI 검토 스트리밍 요청
  const fd = new FormData()
  if (uploadForm.value.file) fd.append('file', uploadForm.value.file)
  fd.append('file_name', uploadForm.value.label)
  fd.append('file_type', uploadForm.value.fileType)
  fd.append('dept_name', deptNode?.label || '')
  fd.append('graph_context', buildGraphContextStr())
  if (_mid && /^\d+$/.test(_mid)) fd.append('meeting_id', _mid)
  fd.append('candidate_agendas', JSON.stringify(
    업로드회의체과제.value.map(t => ({
      id: String(t.agenda_id ?? t.id),
      content: t.content,
    }))
  ))

  const applyResult = (data) => {
    aiResult.value = data
    selectedAgendas.value = (data.agendas || []).map((_, i) => i)  // 기본 전체 선택
    selectedRelDepts.value = [...(data.related_depts || [])]       // 기본 전체 선택

    // AI가 자동으로 연관 과제(복수)를 판별 → 드래그로 이미 지정한 경우가 아니면 적용
    const aiMatchedIds = (data.matched_agendas || [])
      .map(m => String(m.id))
      .filter(id => id && id !== 'null')
    if (aiMatchedIds.length && !prefilledCtx.value.relatedTodoId) {
      uploadForm.value.relatedTodoIds = [...new Set(aiMatchedIds)]
    } else if (aiMatchedIds.length) {
      // 드래그로 지정된 과제는 유지하되 AI 추천을 추가
      uploadForm.value.relatedTodoIds = [
        ...new Set([...uploadForm.value.relatedTodoIds, ...aiMatchedIds]),
      ]
    }
  }

  try {
    await streamPostForm('/api/agent/archive/analyze-file/stream', fd, (ev) => {
      if (ev.type === 'status') {
        aiStreamStage.value = ev.message || ''
      } else if (ev.type === 'token') {
        aiStreamText.value += ev.content || ''
      } else if (ev.type === 'result') {
        applyResult(ev.data || {})
      }
    })
  } catch (e) {
    aiResult.value = {
      score: 70,
      feedback: ['AI 분석 서버에 연결할 수 없습니다.'],
      matched_agendas: [],
      agendas: [],
      related_depts: [],
      criteria: uploadForm.value.fileType==='발제자료'
        ? { recap: false, progress: false, hurdle: false, plan: false }
        : null,
    }
  } finally {
    aiAnalyzing.value = false
    aiStreamStage.value = ''
    // AI 결과를 report_scores에 저장
    if (reportId.value && aiResult.value?.score != null) {
      apiAI.post(`/api/upload/reports/${reportId.value}/score`, {
        score: aiResult.value.score,
        feedback: aiResult.value.feedback ?? [],
        detail_scores: aiResult.value.detail_scores ?? {},
      }).catch(e => console.warn('[runAiAnalysis] 점수 저장 실패:', e))
    }
  }
}

function toggleAgenda(idx) {
  const pos = selectedAgendas.value.indexOf(idx)
  pos >= 0 ? selectedAgendas.value.splice(pos, 1) : selectedAgendas.value.push(idx)
}
function toggleRelDept(dept) {
  const pos = selectedRelDepts.value.indexOf(dept)
  pos >= 0 ? selectedRelDepts.value.splice(pos, 1) : selectedRelDepts.value.push(dept)
}

function doAddFile() {
  if (!uploadForm.value.label.trim()) return
  const fromNode = gNodes.find(n => n.id === uploadForm.value.connectNodeId)
  const fromIdx = fromNode ? gNodes.indexOf(fromNode) : -1
  const fileNodeId = `file-new-${Date.now()}`

  // 연결 노드의 meeting_group을 찾아 groupIdx 상속 (getVisibleSet에서 가시성 포함되도록)
  const mgNode = gNodes.find(n => n.id === uploadForm.value.meetingId && n.type === 'meeting_group')

  // 사용자가 직접 입력한 과제 → 그래프 agenda 노드 생성 + Neo4j Agenda 노드 생성
  const relTodoIds = uploadForm.value.relatedTodoIds || []
  customAgendas.value
    .filter(c => relTodoIds.includes(c.id))
    .forEach((c, i) => {
      // 이미 그래프에 있으면 건너뜀
      if (gNodes.some(n => n.id === c.id)) return
      const angle = Math.random() * Math.PI * 2
      gNodes.push({
        id: c.id,
        neo4jId: c.id,
        label: c.content.slice(0, 12) + (c.content.length > 12 ? '…' : ''),
        type: 'agenda',
        data: { content: c.content },
        groupIdx: mgNode?.groupIdx,
        meetingGroupId: uploadForm.value.meetingId,
        x: Math.cos(angle) * 110, y: 10, z: Math.sin(angle) * 110,
      })
      // Neo4j Agenda 노드 생성 (회의체에 관할 연결)
      apiAI.post('/api/neo4j/agendas', {
        id: c.id,
        content: c.content,
        mg_id: uploadForm.value.meetingId,
      }).catch(e => console.warn('[doAddFile] agenda 생성 실패:', e))
    })

  // 연관 과제(복수)가 선택된 경우 agenda 노드들에 연결, 아니면 부서 노드에 연결
  const agendaNodes = relTodoIds
    .map(id => gNodes.find(n => n.type === 'agenda' && (n.neo4jId === id || n.id === id)))
    .filter(Boolean)
  const primaryAgenda = agendaNodes[0] || null
  const anchorNode = primaryAgenda || fromNode  // 위치·엣지 기준 노드
  const anchorIdx  = primaryAgenda ? gNodes.indexOf(primaryAgenda) : fromIdx

  const anchorX = anchorNode?.x||0, anchorZ = anchorNode?.z||0
  const phi   = Math.atan2(anchorZ, anchorX) + 0.28
  const baseR = Math.sqrt(anchorX*anchorX+anchorZ*anchorZ)

  const newNode = {
    id: fileNodeId,
    label: uploadForm.value.label,
    type: 'file',
    fileType: uploadForm.value.fileType,
    aiScore: aiResult.value?.score ?? null,
    aiReview: aiResult.value ? { ...aiResult.value } : null,
    filePath: uploadedFilePath.value || null,
    reportId: reportId.value || null,
    extractedAgendas: [],
    groupIdx: mgNode?.groupIdx,
    meetingGroupId: uploadForm.value.meetingId,
    x: Math.cos(phi)*(baseR+90), y: (anchorNode?.y||0)+42, z: Math.sin(phi)*(baseR+90)
  }
  gNodes.push(newNode)
  const fileIdx = gNodes.length - 1
  // agenda에 연결할 때는 '첨부'(복수 가능), 부서에 연결할 때는 REL_MATRIX 기준
  if (agendaNodes.length) {
    agendaNodes.forEach(ag => {
      const agIdx = gNodes.indexOf(ag)
      if (agIdx >= 0) gEdges.push({ from: fileIdx, to: agIdx, rel: '첨부' })
      // Neo4j에 파일-아젠다 관계 저장
      if (reportId.value && ag.neo4jId) {
        apiAI.post('/api/neo4j/relationships', {
          from_id: `report-${reportId.value}`,
          from_label: 'Document',
          to_id: ag.neo4jId,
          to_label: 'Agenda',
          rel_type: '첨부',
        }).catch(e => console.warn('[doAddFile] agenda 관계 Neo4j 저장 실패:', e))
      }
    })
  } else if (anchorIdx >= 0) {
    gEdges.push({ from: fileIdx, to: anchorIdx, rel: autoRel(uploadForm.value.connectNodeId, 'file') })
  }

  // AI가 추천한 유관부서 자동 연결
  selectedRelDepts.value.forEach(deptName => {
    const deptId = `dept-${deptName}`
    let deptNodeIdx = gNodes.findIndex(n => n.id === deptId)
    if (deptNodeIdx < 0) {
      const angle = Math.random() * Math.PI * 2
      gNodes.push({ id: deptId, label: deptName, type: 'dept', groupIdx: mgNode?.groupIdx, x: Math.cos(angle)*100, y: 20, z: Math.sin(angle)*100 })
      deptNodeIdx = gNodes.length - 1
    }
    gEdges.push({ from: fileIdx, to: deptNodeIdx, rel: '첨부' })
  })

  // AI가 추천한 아젠다 노드 생성 (미래 회의 연결)
  selectedAgendas.value.forEach((agIdx, i) => {
    const ag = aiResult.value?.agendas?.[agIdx]
    if (!ag) return
    const agNodeId = `agenda-${fileNodeId}-${i}`
    const agAngle = phi + 0.5 + i * 0.3
    gNodes.push({
      id: agNodeId,
      label: ag.content.slice(0, 30) + (ag.content.length > 30 ? '…' : ''),
      fullContent: ag.content,
      type: 'session',
      subType: 'agenda',
      department: ag.department,
      groupIdx: mgNode?.groupIdx,
      x: Math.cos(agAngle)*(baseR+140), y: (fromNode?.y||0)-20, z: Math.sin(agAngle)*(baseR+140)
    })
    gEdges.push({ from: fileIdx, to: gNodes.length-1, rel: '생성' })
  })

  showUploadModal.value = false
  graphViewRef.value?.reloadGraph(gNodes, gEdges)
  setTimeout(refreshArchive, 1200)
}




// PostgreSQL 기준 유효 ID 집합 — 삭제된 회의체를 Neo4j/fallback에서 제거하기 위해 사용
function _isValidMeeting(mgId) {
  if (!meetingsStore.meetings.length) return true  // 아직 로드 전이면 필터 안 함
  const s = String(mgId)
  const numId = s.startsWith('mg-sqlite-') ? parseInt(s.slice(10))
              : s.startsWith('mg-')        ? parseInt(s.slice(3))
              : parseInt(s)
  return meetingsStore.meetings.some(m => m.id === numId)
}

const meetingGroups = computed(() => {
  // Neo4j 데이터가 있으면 우선 사용 — PostgreSQL에서 삭제된 항목 제외
  if (neo4jMeetings.value.length > 0)
    return neo4jMeetings.value.filter(mg => _isValidMeeting(mg.id))

  // fallback: PostgreSQL 기반 조합
  const map = new Map()
  // 본인이 참여 중인 회의체만 포함
  meetingsStore.meetings
    .filter(m => meetingsStore.meetingRoles[m.id] != null)
    .forEach(m => {
    map.set(m.id, { id: m.id, title: m.title, meeting_type: m.meeting_type || null, status: m.status || 'active', minutes: [], reports: [], members: [], tasks: [] })
  })
  // Add minutes & reports
  minutes.value.forEach(m => {
    if (!map.has(m.meeting_id)) map.set(m.meeting_id, { id: m.meeting_id, title: m.meeting_title, minutes: [], reports: [], members: [], tasks: [] })
    map.get(m.meeting_id).minutes.push(m)
  })
  reports.value.forEach(r => {
    if (!map.has(r.meeting_id)) map.set(r.meeting_id, { id: r.meeting_id, title: r.meeting_title, minutes: [], reports: [], members: [], tasks: [] })
    map.get(r.meeting_id).reports.push(r)
  })
  membersData.value.forEach(mb => {
    if (map.has(mb.meetingId)) {
      const g = map.get(mb.meetingId)
      if (!g.members.find(m => m.userId === mb.userId)) g.members.push(mb)
    }
  })
  tasksData.value.forEach(t => {
    if (map.has(t.meetingId)) {
      const g = map.get(t.meetingId)
      if (!g.tasks.find(x => x.id === t.id)) g.tasks.push(t)
    }
  })
  const result = [...map.values()]
  return result
})

// ─── Agent Chat ───────────────────────────────────────────────
const agentChat = useAgentChat({
  meetingGroups,
  membersData,
  tasksData,
  detailMeeting,
  detailTab,
  showExtractFlow,
  extractPhase,
  extractResult,
  toNumericId,
  onQueryHighlight: (step) => _applyQueryHL(step),
  onLabelsHighlight: (labels) => _applyHighlightLabels(labels),
  onQueryClear: () => { if (queryHlIdxs.value.size > 0 && !_hlPersistTimer) _applyQueryHL('') },
})
const {
  SUPERVISOR_EXTRACT, agentSidebarOpen,
  allMessages, agentLoading, agentMessagesEl,
  _runPlanningSteps, initAgentGreeting, injectActionToAgent, runRelationshipAnalysis,
} = agentChat
provide('agentSidebar', agentChat)

// ─── 관계도 분석·재설정 (Supervisor → Knowledge agent) ─────────
// 새로고침 버튼 클릭 시 AI가 Neo4j 소속 관계를 분석/재설정하고 근거를 보고합니다.
const analyzingRelations = ref(false)
async function analyzeRelationships() {
  if (analyzingRelations.value) return
  analyzingRelations.value = true
  try {
    await runRelationshipAnalysis(async () => { await refreshArchive() })
  } finally {
    analyzingRelations.value = false
  }
}

// ─── Stats computed ──────────────────────────────────────────
const statsData = computed(() => {
  const groups = meetingGroups.value
  // 1. 회의체별 문서 수 (bar chart)
  const docPerMeeting = groups.map(g => ({ label: g.title, value: g.minutes.length + g.reports.length }))
    .sort((a,b) => b.value - a.value).slice(0, 8)
  // 2. 회의체별 구성원 수 (bar chart)
  const memberPerMeeting = groups.map(g => ({ label: g.title, value: g.members.length }))
    .sort((a,b) => b.value - a.value).slice(0, 8)
  // 3. 부서별 참여 분포 (pie chart)
  const deptMap = {}
  groups.forEach(g => g.members.forEach(mb => {
    const d = mb.department || '미지정'
    deptMap[d] = (deptMap[d] || 0) + 1
  }))
  const deptDist = Object.entries(deptMap).map(([k,v]) => ({ label: k, value: v }))
    .sort((a,b) => b.value - a.value)
  // 4. 월별 회의록 수 (line chart)
  const monthMap = {}
  groups.forEach(g => g.minutes.forEach(m => {
    const d = m.ended_at ? new Date(m.ended_at) : null
    if (!d || isNaN(d)) return
    const key = `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}`
    monthMap[key] = (monthMap[key] || 0) + 1
  }))
  const months = Object.keys(monthMap).sort().slice(-6)
  const monthSeries = months.map(k => ({ label: k.slice(5)+'월', value: monthMap[k] }))
  return { docPerMeeting, memberPerMeeting, deptDist, monthSeries,
    totalMeetings: groups.length,
    totalDocs: groups.reduce((s,g) => s + g.minutes.length + g.reports.length, 0),
    totalMembers: new Set(groups.flatMap(g => g.members.map(m => m.userId))).size,
    activeMeetings: meetingsStore.meetings.filter(m => !m.status || m.status==='active').length,
  }
})

// ─── 목록 필터 ────────────────────────────────────────────────
const HISTORY_TYPE_OPTIONS = [
  { label: '자료 유형 전체', value: '' },
  { label: '회의록', value: 'minutes' },
  { label: '보고자료', value: 'report' },
]
const selectedHistoryType = ref('')
const selectedMeetingType = ref('')

const meetingTypeOptions = computed(() => {
  const types = [...new Set(meetingGroups.value.map(g => g.meeting_type).filter(Boolean))]
  return [{ label: '회의체 유형 전체', value: '' }, ...types.map(t => ({ label: t, value: t }))]
})

const filteredGroups = computed(() => {
  let list = meetingGroups.value
  if (search.value) {
    const q = search.value.toLowerCase()
    list = list.filter(g =>
      g.title.toLowerCase().includes(q) ||
      g.minutes.some(m => (m.session_title || '').toLowerCase().includes(q)) ||
      g.reports.some(r => (r.file_name || '').toLowerCase().includes(q)) ||
      g.members.some(m => m.userName.toLowerCase().includes(q))
    )
  }
  if (selectedMeetingType.value) {
    list = list.filter(g => g.meeting_type === selectedMeetingType.value)
  }
  if (selectedHistoryType.value === 'minutes') {
    list = list.filter(g => g.minutes.length > 0)
  } else if (selectedHistoryType.value === 'report') {
    list = list.filter(g => g.reports.length > 0)
  }
  return list
})

const lvSortKey = ref(null)
const lvSortDir = ref(null)
function handleLvSort({ key, dir }) { lvSortKey.value = key; lvSortDir.value = dir }
const sortedGroups = computed(() => {
  const enriched = filteredGroups.value.map(g => {
    const adminMember = g.members.find(m => m.role === 'admin')
    const histCount = (g.minutes?.length || 0) + (g.reports?.length || 0)
    return {
      ...g,
      _role: (meetingsStore.meetingRoles[toNumericId(g.id)] ?? selfRoleInGroup(g)) === 'admin' ? '간사' : '참여자',
      _adminName: adminMember?.userName || adminMember?.name || '',
      _histCount: histCount,
    }
  })
  if (!lvSortKey.value || !lvSortDir.value) return enriched
  const d = lvSortDir.value === 'asc' ? 1 : -1
  return [...enriched].sort((a, b) => {
    const av = (a[lvSortKey.value] ?? '').toString().toLowerCase()
    const bv = (b[lvSortKey.value] ?? '').toString().toLowerCase()
    if (!isNaN(Number(av)) && !isNaN(Number(bv))) return (Number(av) - Number(bv)) * d
    return av < bv ? -d : av > bv ? d : 0
  })
})

// ─── 회의체별 전체 이력 (목록 탭) ────────────────────────────
const groupHistoryMap = computed(() => {
  const map = new Map()
  meetingGroups.value.forEach(g => {
    const adminMember = g.members.find(m => m.role === 'admin')
    const managerName = adminMember?.userName || adminMember?.name || '간사'
    const items = []
    // 회의록
    g.minutes.forEach(m => {
      const rawId = String(m.id || '')
      const pgSessionId = rawId.startsWith('session-') ? parseInt(rawId.replace('session-', '')) : null
      items.push({
        type: 'minutes',
        fileName: m.session_title || '회의록',
        score: null,
        dept: null,
        date: m.ended_at,
        hasFile: true,
        filePath: null,
        sessionId: Number.isFinite(pgSessionId) ? pgSessionId : null,
      })
    })
    // 보고서 — parent_id 기준으로 버전 그룹핑
    const rMap = {}
    g.reports.forEach(r => { rMap[r.id] = r })
    function getRootId(r) {
      if (!r.parent_id || !rMap[r.parent_id]) return r.id
      return getRootId(rMap[r.parent_id])
    }
    const rGroups = {}
    g.reports.forEach(r => {
      const rootId = getRootId(r)
      if (!rGroups[rootId]) rGroups[rootId] = []
      rGroups[rootId].push(r)
    })
    const toReportItem = (r) => ({
      type: 'report',
      fileName: (r.file_name || '파일') + (r.version ? ` (v${r.version})` : ''),
      score: r.score ?? null,
      dept: r.submitter_department || null,
      date: r.created_at || r.submitted_at,
      hasFile: !!(r.file_path || r.file_url),
      filePath: r.file_path || r.file_url || null,
      rejected: r.human_status === 'rejected' || r.status === 'rejected',
      approved: r.human_status === 'approved' || r.status === 'approved',
      reportId: r.id,
    })
    Object.values(rGroups).forEach(group => {
      group.sort((a, b) => (b.version || 1) - (a.version || 1))
      const latest = group[0]
      const older = group.slice(1)
      items.push({
        ...toReportItem(latest),
        olderVersions: older.slice().reverse().map(toReportItem),
      })
    })
    items.sort((a, b) => {
      const da = a.date ? new Date(a.date) : new Date(0)
      const db = b.date ? new Date(b.date) : new Date(0)
      return da - db
    })
    map.set(g.id, items)
  })
  return map
})

const filteredGroupHistoryMap = computed(() => {
  if (!selectedHistoryType.value) return groupHistoryMap.value
  const map = new Map()
  groupHistoryMap.value.forEach((items, id) => {
    map.set(id, items.filter(item => item.type === selectedHistoryType.value))
  })
  return map
})

const { buildGraphNodes, computeUrgency, getHubFill } = useGraphBuilder({
  meetingGroups,
  currentPerson,
  authStore,
  currentOrg,
  neo4jDepts,
  meetingsStore,
})

/** GraphView (PIXI) 노드 클릭 핸들러 */
function onGraphNodeClick(node) {
  if (!node) return
  if (node.type === 'meeting_group' && node.data) {
    openDetail(node.data)
  } else if (node.id !== 'org-node' && node.type !== 'company') {
    openNodeDetail(node)
  }
}

/** GraphView (PIXI) 배경 클릭 → 사이드바 닫기 */
function onGraphBgClick() {
  detailOpen.value = false
}

// ─── Lifecycle ─────────────────────────────────────────────────
onMounted(async () => {
  await nextTick()
  initAgentGreeting('hyean')
  window.addEventListener('mousemove', onGlobalMouseMove)
  window.addEventListener('mouseup', onGlobalMouseUp)

  // meetingsStore(SpringBoot)와 Neo4j를 병렬로 요청 — 어느 쪽이 느려도 블로킹 없음
  const [neo4jResult] = await Promise.allSettled([
    apiAI.get('/api/neo4j/archive'),
    meetingsStore.fetchMeetings().catch(e => console.error('meetings fetch error', e)),
  ])

  try {
    if (neo4jResult.status === 'fulfilled') {
      const data = neo4jResult.value?.data
      currentPerson.value = data?.current_person || null
      currentOrg.value    = data?.org || null
      neo4jMeetings.value = data?.meetings     || []
      neo4jDepts.value    = data?.departments  || []
      minutes.value       = data?.minutes      || []
      reports.value       = data?.reports      || []
      membersData.value   = (data?.meetings || []).flatMap(m => m.members || [])
      tasksData.value     = (data?.meetings || []).flatMap(m => m.tasks   || [])
    } else {
      console.error('archive fetch error', neo4jResult.reason)
      neo4jError.value = '연결 실패'
    }
  } finally {
    loading.value = false
    if (!neo4jError.value) {
      const g = buildGraphNodes(); gNodes = g.nodes; gEdges = _applyLocalEdgeOverrides(g.nodes, g.edges); gNodesRef.value = gNodes
    }
  }
})

onBeforeUnmount(()=>{
  window.removeEventListener('mousemove', onGlobalMouseMove)
  window.removeEventListener('mouseup', onGlobalMouseUp)
})

// ── archive 데이터 재로드 헬퍼 (CRUD 후 호출) ─────────────────
async function refreshArchive() {
  neo4jRetrying.value = true
  neo4jError.value = ''   // 즉시 오버레이 해제 → 로딩 상태로 전환
  loading.value = true
  try {
    const res = await apiAI.get('/api/neo4j/archive')
    neo4jError.value = ''
    currentPerson.value = res?.data?.current_person || null
    currentOrg.value    = res?.data?.org || null
    neo4jMeetings.value = res?.data?.meetings || []
    neo4jDepts.value    = res?.data?.departments || []
    minutes.value       = res?.data?.minutes  || []
    reports.value       = res?.data?.reports  || []
    membersData.value   = (res?.data?.meetings || []).flatMap(m => m.members || [])
    tasksData.value     = (res?.data?.meetings || []).flatMap(m => m.tasks   || [])
    await nextTick()
    const g = buildGraphNodes()
    if (g.nodes.length > 0) {
      gNodes = g.nodes; gEdges = _applyLocalEdgeOverrides(g.nodes, g.edges); gNodesRef.value = gNodes
      _recomputeSearchHits()
      graphViewRef.value?.reloadGraph(gNodes, gEdges)
    }
  } catch(e) {
    console.error('archive refresh error', e)
    neo4jError.value = '연결 실패'
  } finally {
    loading.value = false
    neo4jRetrying.value = false
  }
}

// Rebuild graph when new meetings are created
watch(() => meetingsStore.meetings.length, (newLen, oldLen) => {
  if (loading.value) return  // 초기 로딩 중에는 무시 — finally에서 한 번만 빌드

  // 회의체가 삭제된 경우: neo4jMeetings에서도 즉시 제거
  if (newLen < oldLen && neo4jMeetings.value.length > 0) {
    const currentIds = new Set(meetingsStore.meetings.map(m => m.id))
    neo4jMeetings.value = neo4jMeetings.value.filter(mg => {
      const s = String(mg.id)
      const numId = s.startsWith('mg-sqlite-') ? parseInt(s.slice(10))
                  : s.startsWith('mg-')        ? parseInt(s.slice(3))
                  : parseInt(s)
      return currentIds.has(numId)
    })
  }

  const g = buildGraphNodes()
  if (g.nodes.length === 0 && gNodes.length > 0) return  // 빈 데이터로 기존 그래프 지우지 않음
  gNodes = g.nodes; gEdges = _applyLocalEdgeOverrides(g.nodes, g.edges); gNodesRef.value = gNodes
  graphViewRef.value?.reloadGraph(gNodes, gEdges)
})

// Neo4j 데이터 로드 완료 시 그래프 재빌드
watch(() => neo4jMeetings.value.length, () => {
  if (loading.value) return
  const g = buildGraphNodes()
  if (g.nodes.length === 0 && gNodes.length > 0) return  // 빈 데이터로 기존 그래프 지우지 않음
  gNodes = g.nodes; gEdges = _applyLocalEdgeOverrides(g.nodes, g.edges); gNodesRef.value = gNodes
  graphViewRef.value?.reloadGraph(gNodes, gEdges)
})


// ─── Helpers ──────────────────────────────────────────────────
function formatDate(d){if(!d)return'-';return new Date(d).toLocaleString('ko-KR',{year:'numeric',month:'short',day:'numeric',hour:'2-digit',minute:'2-digit'})}
async function _openPresigned(filePath) {
  const { data } = await apiAI.get('/api/upload/presigned', { params: { file_path: filePath } })
  window.open(data.url, '_blank')
}
async function _fetchMinutesFilePath(sessionId) {
  const res = await api.get(`/api/v1/sessions/${sessionId}/minutes`)
  return res?.data?.data?.filePath || res?.data?.filePath || null
}
async function downloadFile(item) {
  try {
    let filePath = item?.filePath || null
    if (!filePath && item?.sessionId) filePath = await _fetchMinutesFilePath(item.sessionId)
    if (!filePath) { alert('다운로드할 파일이 없습니다.'); return }
    await _openPresigned(filePath)
  } catch(e) { console.error('[download]', e); alert('파일 다운로드에 실패했습니다.') }
}
async function downloadNode(node) {
  try {
    let filePath = node?.data?.file_path || node?.data?.file_url || null
    if (!filePath) {
      const neoId = node?.data?.session_neo_id || (node?.type === 'session' ? node?.data?.id : null) || null
      if (neoId) {
        const rawId = String(neoId)
        const sessionId = rawId.startsWith('session-') ? parseInt(rawId.replace('session-', '')) : null
        if (Number.isFinite(sessionId)) filePath = await _fetchMinutesFilePath(sessionId)
      }
    }
    if (!filePath) { alert('다운로드할 파일이 없습니다.'); return }
    await _openPresigned(filePath)
  } catch(e) { console.error('[downloadNode]', e); alert('파일 다운로드에 실패했습니다.') }
}
const downloadDummy = downloadNode
async function deleteReport(reportId) {
  if (!reportId) return
  if (!confirm('보고서를 삭제하시겠습니까? 이 작업은 되돌릴 수 없습니다.')) return
  try {
    await apiAI.delete(`/api/upload/reports/${reportId}`)
    // 그래프에서 노드 제거
    const idx = gNodes.findIndex(n => n.reportId === reportId || n.id === `file-report-${reportId}`)
    if (idx >= 0) {
      gNodes.splice(idx, 1)
      graphViewRef.value?.reloadGraph(gNodes, gEdges)
    }
    detailNode.value = null
    setTimeout(refreshArchive, 600)
  } catch (e) {
    alert('삭제에 실패했습니다.')
  }
}
const TYPES=['Draft','In Progress','Done','Pending']

// ─── Provide for Canvas components (GraphLegend, GraphFloatBtns, FloatDragPreview) ─
provide('archiveCanvas', {
  loading, viewMode, detailOpen, sidebarW,
  isHiddenType, toggleNodeType,
  openCreateModal, onFloatBtnMouseDown, openSessionModal, openUploadModal,
  floatDragging, floatDragPos, floatDragPreviewLine,
})

// ─── Provide for MeetingListView ──────────────────────────────
provide('archiveList', {
  viewMode, selectedMeetingType, meetingTypeOptions,
  selectedHistoryType, HISTORY_TYPE_OPTIONS,
  search, filteredGroups, sortedGroups,
  loading, meetingGroups, nightMode,
  lvColumns, lvSortKey, lvSortDir, handleLvSort,
  expandedMeeting, meetingsStore, filteredGroupHistoryMap,
  formatDate, downloadDummy: downloadFile, deleteReport,
})

// ─── Provide for Modals ───────────────────────────────────────
async function fetchRejectedReports() {
  try {
    const { data } = await apiAI.get('/api/upload/reports/rejected')
    rejectedReports.value = data || []
  } catch (e) {
    console.warn('[fetchRejectedReports] 실패:', e)
  }
}

async function submitReview(action, feedback) {
  if (action === 'rejected') {
    showUploadModal.value = false
  }
  if (!reportId.value) {
    if (action === 'approved') doAddFile()
    return
  }
  try {
    await apiAI.post(`/api/upload/reports/${reportId.value}/review`, {
      action,
      feedback,
      ai_result: {
        score: aiResult.value?.score,
        detail_scores: aiResult.value?.detail_scores,
      },
      ai_rationale: (aiResult.value?.feedback ?? []).join('\n'),
      related_agenda_ids: uploadForm.value.relatedTodoIds || [],
    })
  } catch (e) {
    console.warn('[submitReview] hitl 저장 실패:', e)
  } finally {
    if (action === 'approved') doAddFile()
  }
}

provide('archiveModals', {
  nightMode,
  showCreateModal, createForm, creating, doCreateMeeting, createMembers,
  showSessionModal, sessionForm, sessionMembers, creatingSession, doCreateSession,
  showUploadModal, uploadStep, uploadForm, gNodes: gNodesRef,
  deptConnectableNodes, 업로드회의체과제, prefilledCtx,
  addCustomAgenda,
  REL_COLORS, autoRel, runAiAnalysis, aiAnalyzing, aiResult,
  aiStreamText, aiStreamStage,
  PRESENTATION_CRITERIA, doAddFile, submitReview, reportId,
  isResubmit, rejectedReports, selectedParentId, fetchRejectedReports,
  settingsModal, closeSettings,
  settingsSearchQ, watchSettingsSearch, settingsSearchLoading,
  settingsSearchResults, addMemberToSettings, avatarColor, initials,
  removeMemberFromSettings, ROLE_MAP, savingSettings, saveSettings,
})

// ─── Provide for DetailSidebar ────────────────────────────────
provide('archiveSidebar', {
  detailOpen, sidebarW, onSidebarResizeStart,
  detailMeeting, isDetailAdmin, openGroupSetting,
  detailTab, showExtractFlow, nodeDetailTab,
  detailDday, detailEndDateFormatted, detailDeptStatus,
  groupHistoryMap, goToList, formatDate,
  detailTodos, groupedTodos, completeTodo, deleteTodo,
  extractPhase, extractLoading, extractResult,
  selectedFiles, uploadedCtxFiles, selectedSimilarDocs, onCtxFilesAdded,
  runExtract, setExtractState, addExtractItem, finishExtract,
  saveAgendaFeedback,
  detailMemberDepts,
  goToProcessStep,
  PRIORITY_LABEL, STATUS_LABEL,
  currentNodeEdges, relEditIdx, relEditRel, ALL_REL_TYPES, REL_COLORS,
  saveRelEdit, cancelRelEdit, startRelEdit, doDeleteEdge,
  relAddActive, openAddRel, allGraphNodeList, relAddForm, doAddRel,
  detailNode, downloadDummy, downloadFile, deleteReport, currentOrg, personMeetingGroups, personTasks,
  meetingGroups,
  viewMode,
})
</script>

<template>
  <div class="archive-page" :class="{ 'day-mode': !nightMode }">

    <!-- ── Header ── -->
    <div class="archive-header">
      <div class="header-title-wrap">
        <h1 class="archive-title">아카이브</h1>
      </div>

      <div class="search-wrap">
        <svg class="search-icon" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><circle cx="11" cy="11" r="8"/><path d="M21 21l-4.35-4.35"/></svg>
        <input v-model="search" class="search-input" placeholder="회의체명, 회의록, 보고서, 인물 검색..." />
        <button v-if="search" class="search-clear" @click="search=''">
          <svg width="11" height="11" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24"><path d="M18 6L6 18M6 6l12 12"/></svg>
        </button>
      </div>

      <div class="app-tabs">
        <button class="app-tab" :class="{ active: viewMode==='graph' }" @click="viewMode='graph'">
          <svg width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><circle cx="5" cy="12" r="2"/><circle cx="19" cy="5" r="2"/><circle cx="19" cy="19" r="2"/><path d="M7 12h5l5-5M12 12l5 5"/></svg>
          관계도
        </button>
        <button class="app-tab" :class="{ active: viewMode==='list' }" @click="viewMode='list'">
          <svg width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01"/></svg>
          목록
        </button>
      </div>

      <button class="agent-header-btn refresh-map-btn" :class="{ analyzing: analyzingRelations }"
        :disabled="analyzingRelations"
        @click="analyzeRelationships"
        title="관계도 새로고침 — AI가 소속 관계를 분석·재설정하고 근거를 알려드립니다">
        <svg class="refresh-icon" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" width="18" height="18">
          <defs>
            <linearGradient id="refreshGrad" x1="0%" y1="0%" x2="100%" y2="100%">
              <stop offset="0%" stop-color="#93c5fd"/>
              <stop offset="100%" stop-color="#818cf8"/>
            </linearGradient>
          </defs>
          <path d="M4.5 12a7.5 7.5 0 0 1 12.52-5.59l1.48-1.98" stroke="url(#refreshGrad)" stroke-width="2" stroke-linecap="round"/>
          <path d="M19.5 12a7.5 7.5 0 0 1-12.52 5.59L5.5 19.57" stroke="url(#refreshGrad)" stroke-width="2" stroke-linecap="round"/>
          <polyline points="18.5,4.43 18.5,7.43 15.5,7.43" stroke="url(#refreshGrad)" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
          <polyline points="5.5,19.57 5.5,16.57 8.5,16.57" stroke="url(#refreshGrad)" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
        </svg>
      </button>
      <button class="agent-header-btn" :class="{ active: agentSidebarOpen }" @click="agentSidebarOpen=!agentSidebarOpen" title="AI 에이전트">
        <svg class="ai-btn-icon" viewBox="0 0 40 22" xmlns="http://www.w3.org/2000/svg">
          <defs>
            <linearGradient id="aiGrad" x1="0%" y1="0%" x2="100%" y2="100%">
              <stop offset="0%" stop-color="#93c5fd"/>
              <stop offset="100%" stop-color="#7b80cc"/>
            </linearGradient>
          </defs>
          <text x="20" y="17" text-anchor="middle" font-family="'SF Pro Display',system-ui,sans-serif" font-weight="800" font-size="19" fill="url(#aiGrad)" letter-spacing="-0.5">AI</text>
        </svg>
      </button>
    </div>

    <!-- ── Graph Breadcrumb ── -->
    <!-- ── Body ── -->
    <div class="archive-body">

      <!-- Main area -->
      <div class="main-area">

        <DetailSidebar />

        <!-- Graph view -->
        <div v-if="loading && viewMode==='graph'" class="graph-loading">
          <div class="graph-loading-spinner"></div>
          <span>불러오는 중...</span>
        </div>

        <!-- Zoom controls (top-left) -->
        <div v-if="!loading && viewMode==='graph'" class="graph-zoom-controls"
          :style="{ left: (detailOpen ? sidebarW + 10 : 10) + 'px', transition: 'left 0.28s cubic-bezier(.22,.68,0,1.2)' }">
          <template v-if="viewMode==='graph'">
            <button class="zoom-btn" @click="graphViewRef?.zoomIn()" title="확대 (Zoom In)">+</button>
            <button class="zoom-btn zoom-reset" @click="graphViewRef?.resetView()" title="초기화 (Reset)">⌂</button>
            <button class="zoom-btn" @click="graphViewRef?.zoomOut()" title="축소 (Zoom Out)">−</button>
            <button class="zoom-btn zoom-pan-hint" :class="{ active: graphPanOnly }" @click="toggleGraphPanOnly" title="이동 전용 모드 (노드 클릭 없이 배경 드래그로만 이동)">
              <i class="bi bi-arrows-move"></i>
            </button>
          </template>
          <template v-else>
            <button class="zoom-btn" @click="constViewRef?.zoomIn()" title="확대 (Zoom In)">+</button>
            <button class="zoom-btn zoom-reset" @click="constViewRef?.resetView()" title="초기화 (Reset)">⌂</button>
            <button class="zoom-btn" @click="constViewRef?.zoomOut()" title="축소 (Zoom Out)">−</button>
          </template>
        </div>
        <!-- Graph view (PIXI.js force-directed) -->
        <div v-if="!loading && viewMode==='graph' && neo4jError" class="neo4j-error-overlay">
          <svg width="36" height="36" fill="none" stroke="currentColor" stroke-width="1.5" viewBox="0 0 24 24" style="color:#f87171;margin-bottom:10px"><circle cx="12" cy="12" r="10"/><path d="M12 8v4M12 16h.01"/></svg>
          <div class="neo4j-error-title">그래프 연결 실패</div>
          <div class="neo4j-error-msg">{{ neo4jError }}</div>
          <button class="neo4j-error-retry" :disabled="neo4jRetrying" @click="refreshArchive">
            <span v-if="neo4jRetrying" class="spinner-border spinner-border-sm me-1" style="width:12px;height:12px;border-width:2px"></span>
            {{ neo4jRetrying ? '연결 중...' : '다시 시도' }}
          </button>
        </div>
        <GraphView
          v-if="!loading && viewMode==='graph' && !neo4jError"
          ref="graphViewRef"
          class="archive-canvas"
          :class="{ 'graph-pan-only': graphPanOnly }"
          :gNodes="gNodes"
          :gEdges="gEdges"
          :nightMode="nightMode"
          :hiddenNodeTypes="hiddenNodeTypes"
          :queryHlIdxs="queryHlIdxs"
          :queryHlEdgeIdxs="queryHlEdgeIdxs"
          :searchHitMgIdxs="searchHitMgIdxs"
          :getHubFill="getHubFill"
          :computeUrgency="computeUrgency"
          :relColors="REL_COLORS"
          :groupTodoRatio="groupTodoRatio"
          :selfNodeId="selfPersonNodeId"
          @nodeClick="onGraphNodeClick"
          @bgClick="onGraphBgClick"
        />

        <!-- ── Constellation view ── -->
        <!-- Map drag invalid toast -->
        <Transition name="map-toast-fade">
          <div v-if="mapToastMsg" class="map-toast">{{ mapToastMsg }}</div>
        </Transition>

        <!-- Neo4j query HUD (챗봇 그래프 탐색 실시간 표시) -->
        <Transition name="query-hud-fade">
          <div v-if="queryHlStep" class="query-hud">
            <span class="query-hud-dot"></span>
            <span class="query-hud-text">{{ queryHlStep }}</span>
          </div>
        </Transition>

        <GraphLegend />
        <GraphFloatBtns />
        <MeetingListView />

        <!-- Bottom panel (slides up) -->

      </div><!-- /main-area -->

    </div><!-- /archive-body -->

    <!-- Agent right sidebar (overlay, covers header) -->
        <AgentSidebar />

    <FloatDragPreview />

    <CreateMeetingModal />
    <CreateSessionModal />

  </div><!-- /archive-page -->
  <UploadModal />
  <SettingsModal />
</template>

<style>
@import '../styles/archive/layout.css';
@import '../styles/archive/sidebar.css';
@import '../styles/archive/agent.css';
@import '../styles/archive/graph.css';
@import '../styles/archive/list.css';
@import '../styles/archive/modals.css';
</style>
