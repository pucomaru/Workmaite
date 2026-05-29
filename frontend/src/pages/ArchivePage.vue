<script setup>
import { ref, computed, reactive, onMounted, onBeforeUnmount, watch, nextTick } from 'vue'
import MemberInvite from '../components/MemberInvite.vue'
import BaseModal from '../components/BaseModal.vue'
import AppTable from '../components/AppTable.vue'
import ProcessStepBar from '../components/ProcessStepBar.vue'
import FileUploadArea from '../components/FileUploadArea.vue'
import SidebarInfoRow from '../components/SidebarInfoRow.vue'
import { useRouter } from 'vue-router'
import api, { apiAI } from '../api'
import { streamPost } from '../api'
import { renderMd } from '../composables/useMarkdown'
import { useMeetingsStore } from '../stores/meetings'
import { useAuthStore } from '../stores/auth'
import { useThemeStore } from '../stores/theme'
import hyeanAvatar from '../assets/agents/hyean.png'

const lvColumns = [
  { label: '회의체명', width: '100px', sortKey: 'title' },
  { label: '유형', width: '10px', sortKey: 'meeting_type' },
  { label: '역할', width: '10px', sortKey: '_role' },
  { label: '간사', width: '10px', sortKey: '_adminName' },
  { label: '이력', width: '10px', sortKey: '_histCount' }
]
// 서브에이전트 아바타는 내부 라우팅용으로 보존 (사용자에게는 비노출)
// import gaonAvatar from '../assets/agents/gaon.png'
// import naruAvatar from '../assets/agents/naru.png'
// import araAvatar from '../assets/agents/ara.png'
// import naonAvatar from '../assets/agents/naon.png'
import agentHierarchyIcon from '../assets/agents/agent_hierarchy_icon.svg'

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
const search = ref('')
const expandedMeeting = ref(null)

// ─── View mode ────────────────────────────────────────────────
const viewMode = ref('graph')
// nightMode는 전역 themeStore.nightMode(computed)를 사용합니다

// ─── 뷰 전환 시 패널 상태 저장/복원 ─────────────────────────
const _graphSnapshot = { detailOpen: false, agentSidebarOpen: false, bottomMode: null }
const _listSnapshot  = { expandedMeeting: null }

watch(viewMode, (next, prev) => {
  // graph ↔ list
  if (prev === 'graph' && next === 'list') {
    _graphSnapshot.detailOpen      = detailOpen.value
    _graphSnapshot.agentSidebarOpen = agentSidebarOpen.value
    _graphSnapshot.bottomMode      = bottomMode.value
    detailOpen.value = false
    agentSidebarOpen.value = false
    bottomMode.value = null
    expandedMeeting.value = _listSnapshot.expandedMeeting
  } else if (prev === 'list' && next === 'graph') {
    _listSnapshot.expandedMeeting = expandedMeeting.value
    expandedMeeting.value = null
    nextTick(() => {
      detailOpen.value      = _graphSnapshot.detailOpen
      agentSidebarOpen.value = _graphSnapshot.agentSidebarOpen
      bottomMode.value      = _graphSnapshot.bottomMode
    })
  }
  // constellation 진입/이탈
  if (next === 'constellation') {
    nextTick(() => initConstellation())
  } else if (prev === 'constellation') {
    stopConstellation()
  }
})

// ─── Constellation state ─────────────────────────────────────
const constCanvasRef = ref(null)
const constSelMgIdx  = ref(null)   // 선택된 meeting_group 인덱스
let constCtx = null, constAnimId = null, constRo = null
let cPos = []                       // { x, y } 배열 (gNodes 인덱스 대응)
let constScale = 1, constTargetScale = 1
let constCamX = 0, constCamY = 0, constTargetCamX = 0, constTargetCamY = 0
let constDragging = false, constLastMx = 0, constLastMy = 0, constDragMoved = false

// ─── Search highlight (meeting_group nodes containing match) ──
const searchHitMgIdxs = ref([])

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
  createMembers.value = []
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
      await api.post(`/api/v1/meetings/${meetingId}/sessions`, {
        title: sessionForm.value.title,
        purpose: sessionForm.value.purpose || null,
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

function onFloatBtnMouseDown(type, e) {
  floatDragging.value = type
  floatDragPos.value = { x: e.clientX, y: e.clientY }
  floatDragStartX = e.clientX; floatDragStartY = e.clientY
  floatDragMoved = false; floatDragTarget = null; floatDragNearInvalidNode = false; floatDragPreviewLine.value = null
  document.body.style.cursor = 'grabbing'
  // document capture 단계 리스너: window.mouseup 이 누락될 경우에도 항상 처리
  function _floatDragCapture() {
    document.removeEventListener('mouseup', _floatDragCapture, true)
    if (floatDragging.value) onGlobalMouseUp()
  }
  document.addEventListener('mouseup', _floatDragCapture, true)
  e.preventDefault()
}

async function doCreateMeeting() {
  if (!createForm.value.title.trim()) return
  creating.value = true
  try {
    const meeting = await meetingsStore.createMeeting({
      title: createForm.value.title, purpose: createForm.value.purpose,
      start_date: createForm.value.start_date || null, end_date: createForm.value.end_date || null,
      guidelines: createForm.value.guidelines || null, meeting_type: createForm.value.meeting_type || null,
    })
    const membersSnapshot = [...createMembers.value]  // save before clearing
    for (const m of createMembers.value) {
      await api.post(`/api/v1/meetings/${meeting.id}/members`, { userId: m.userId, role: m.role })
    }
    showCreateModal.value = false
    createForm.value = { title: '', purpose: '', start_date: '', end_date: '', guidelines: '', meeting_type: 'Weekly' }
    createMembers.value = []; createMemberSearch.value = ''; createMemberResults.value = []
    createConnectNodeId.value = ''
    // 아카이브 재로드: SQLite 즉시 반영 후 Neo4j 동기화까지 대기(1s)
    await refreshArchive()
    setTimeout(refreshArchive, 1000)
  } finally { creating.value = false }
}

// ─── Agents ───────────────────────────────────────────────────
// 내부적으로는 5개 서브에이전트가 존재하지만 사용자에게는 단일 워크메이트 AI로 표시됨
const SUPERVISOR = {
  name: '워크메이트 AI', nameEn: 'Workmate AI',
  avatar: hyeanAvatar,
  greeting: '안녕하세요! 저는 워크메이트 AI예요 😊\n무엇이든 물어보세요.',
  suggested: ['회의체 현황을 브리핑해줘', '이번 회의 아젠다를 정리해줘', '보고서를 검토해줘'],
  endpoint: '/api/agent/supervisor/chat',
}

const SUPERVISOR_EXTRACT = {
  name: '워크메이트 AI', nameEn: 'Workmate AI',
  avatar: hyeanAvatar,
  greeting: '회의록과 자료를 분석해서 과제를 추출했습니다.\n추출된 과제 목록을 검토해보시고, 수정이 필요한 항목이 있으면 말씀해주세요.\n\n예시: "3번 과제 담당자를 홍길동으로 바꿔줘", "2번과 4번 과제를 합쳐줘", "이 과제가 왜 추출됐는지 설명해줘"',
  suggested: ['각 과제가 추출된 이유를 설명해줘', '비슷한 과제들을 하나로 합쳐줘', '담당 부서 배정이 적절한지 검토해줘'],
  endpoint: '/api/agent/supervisor/chat',
}

const agentSidebarOpen = ref(false)
const currentAgent = ref('supervisor')
const agentInfo = computed(() => {
  if (detailTab.value === 'task' && showExtractFlow.value && extractPhase.value !== 'context') {
    return SUPERVISOR_EXTRACT
  }
  return SUPERVISOR
})
const allMessages = ref({ supervisor: [] })
const currentMessages = computed(() => allMessages.value['supervisor'])
const agentInput = ref('')
const agentLoading = ref(false)
const agentMessagesEl = ref(null)
const agentFileInput = ref(null)
const agentPendingFiles = ref([])
const agentTextareaEl = ref(null)

// ─── @ mention ────────────────────────────────────────────────
const atMenuOpen = ref(false)
const atQuery = ref('')
const atCursorPos = ref(0)
const atHighlight = ref(0)
const mentionedContexts = ref([]) // [{id, type, label, icon, summary}]

const AT_TYPE_ICONS = { meeting: '🏢', person: '👤', task: '✅', department: '🏬', session: '📅', document: '📄' }
const AT_TYPE_LABELS = { meeting: '회의체', person: '구성원', task: '과제', department: '부서', session: '회의', document: '문서' }

const atMenuItems = computed(() => {
  const q = atQuery.value.toLowerCase()
  const seen = new Set()
  const items = []
  // 회의체
  for (const mg of meetingGroups.value) {
    const label = mg.title || mg.name || ''
    if (!label) continue
    if (!q || label.toLowerCase().includes(q)) {
      const id = `mg-${mg.id}`
      if (!seen.has(id)) {
        seen.add(id)
        const memberNames = (mg.members || []).map(m => m.name).filter(Boolean).join(', ')
        const agendaList = (mg.agendas || []).map(a => a.content || a.title).filter(Boolean).slice(0, 3).join(', ')
        items.push({
          id, type: 'meeting', label, icon: '🏢',
          summary: ['[회의체] ' + label, mg.purpose ? '목적: ' + mg.purpose : '', memberNames ? '구성원: ' + memberNames : '', agendaList ? '아젠다: ' + agendaList : ''].filter(Boolean).join('\n'),
        })
      }
    }
  }
  // 구성원
  for (const m of membersData.value) {
    const label = m.name || ''
    if (!label) continue
    if (!q || label.toLowerCase().includes(q)) {
      const id = `person-${m.id || m.employee_id || m.name}`
      if (!seen.has(id)) {
        seen.add(id)
        items.push({
          id, type: 'person', label, icon: '👤',
          summary: ['[구성원] ' + label, m.department ? '부서: ' + m.department : '', m.position ? '직책: ' + m.position : ''].filter(Boolean).join('\n'),
        })
      }
    }
  }
  // 과제
  for (const t of tasksData.value) {
    const label = (t.content || t.title || '').slice(0, 40)
    if (!label) continue
    if (!q || label.toLowerCase().includes(q)) {
      const id = `task-${t.id}`
      if (!seen.has(id)) {
        seen.add(id)
        const statusLabel = { pending: '대기', done: '완료', in_progress: '진행중', at_risk: '위험' }[t.status] || t.status || ''
        items.push({
          id, type: 'task', label, icon: '✅',
          summary: ['[과제] ' + label, statusLabel ? '상태: ' + statusLabel : '', t.deadline ? '마감: ' + t.deadline : ''].filter(Boolean).join('\n'),
        })
      }
    }
  }
  // 현재 선택된 회의체의 세션
  if (detailMeeting.value?.sessions?.length) {
    for (const s of detailMeeting.value.sessions) {
      const label = s.title || s.name || ''
      if (!label) continue
      if (!q || label.toLowerCase().includes(q)) {
        const id = `session-${s.id}`
        if (!seen.has(id)) {
          seen.add(id)
          items.push({ id, type: 'session', label, icon: '📅', summary: ['[회의] ' + label, s.date ? '일시: ' + s.date : ''].filter(Boolean).join('\n') })
        }
      }
    }
  }
  return items.slice(0, 8)
})

function onAgentInput(e) {
  agentAutoResize()
  const val = agentInput.value
  const cursor = e.target.selectionStart
  const before = val.slice(0, cursor)
  const atIdx = before.lastIndexOf('@')
  if (atIdx !== -1) {
    const query = before.slice(atIdx + 1)
    if (!query.includes(' ') && !query.includes('\n')) {
      atQuery.value = query
      atCursorPos.value = atIdx
      atMenuOpen.value = true
      atHighlight.value = 0
      return
    }
  }
  atMenuOpen.value = false
}

function selectAtItem(item) {
  const el = agentTextareaEl.value
  const cursor = el ? el.selectionStart : agentInput.value.length
  const val = agentInput.value
  agentInput.value = val.slice(0, atCursorPos.value) + val.slice(cursor)
  if (!mentionedContexts.value.find(c => c.id === item.id)) {
    mentionedContexts.value.push(item)
  }
  atMenuOpen.value = false
  atQuery.value = ''
  nextTick(() => { agentTextareaEl.value?.focus(); agentAutoResize() })
}

function removeMentionCtx(id) {
  mentionedContexts.value = mentionedContexts.value.filter(c => c.id !== id)
}

function initAgentGreeting() {
  if (!allMessages.value['supervisor'].length)
    allMessages.value['supervisor'] = [{ role: 'agent', content: SUPERVISOR.greeting }]
}

function switchAgent(_key) {
  // 사용자에게는 단일 워크메이트 AI로 표시 — 내부 라우팅은 supervisor 엔드포인트가 처리
  agentSidebarOpen.value = true
  initAgentGreeting()
}

function clearAgentChat() {
  allMessages.value['supervisor'] = [{ role: 'agent', content: SUPERVISOR.greeting }]
  agentInput.value = ''; agentPendingFiles.value = []
}

async function sendAgentMsg() {
  const text = agentInput.value.trim()
  if ((!text && !agentPendingFiles.value.length && !mentionedContexts.value.length) || agentLoading.value) return
  agentInput.value = ''
  atMenuOpen.value = false
  if (agentTextareaEl.value) agentTextareaEl.value.style.height = '36px'
  let content = text
  if (agentPendingFiles.value.length) {
    const names = agentPendingFiles.value.map(f => f.name).join(', ')
    content = text ? `📎 ${names}\n${text}` : `📎 ${names}`
    agentPendingFiles.value = []
  }
  // @ 컨텍스트를 API 메시지에 주입 (화면에는 chips로만 표시)
  const ctxSnapshot = [...mentionedContexts.value]
  if (ctxSnapshot.length) {
    const ctxBlock = ctxSnapshot.map(c => c.summary).join('\n---\n')
    content = `${content}\n\n[참조 컨텍스트]\n${ctxBlock}`
    mentionedContexts.value = []
  }
  const key = 'supervisor'
  // 화면에는 원본 텍스트만 + 참조된 컨텍스트 칩 표시 (API엔 full content 전달)
  const displayText = text || (agentPendingFiles.value.length ? `📎 파일` : '')
  allMessages.value[key].push({ role: 'user', content: displayText, contexts: ctxSnapshot })

  // ── 사고 과정 블록 (실시간 백엔드 이벤트로 채움) ──────────────────
  // reactive()로 감싸야 로컬 변수 변경이 Vue 반응성 시스템에 즉시 반영됨
  const planningMsg = reactive({ role: 'planning', steps: [], open: true, done: false })
  allMessages.value[key].push(planningMsg)
  const agentMsg = reactive({ role: 'agent', content: '' })
  allMessages.value[key].push(agentMsg)
  agentLoading.value = true
  await nextTick()
  if (agentMessagesEl.value) agentMessagesEl.value.scrollTop = agentMessagesEl.value.scrollHeight

  // 과제 탭 추출 결과 단계 → chat-extract 엔드포인트로 과제 목록 업데이트
  const isExtractMode = detailTab.value === 'task' &&
    (extractPhase.value === 'result' || extractPhase.value === 'assign') &&
    detailMeeting.value

  if (isExtractMode) {
    const mgTitle = detailMeeting.value?.title || '선택된 회의체'
    const extractSteps = [
      `추출 과제 컨텍스트 로드 중 (${extractResult.value.length}건)...`,
      `MATCH (mg:MeetingGroup {title:"${mgTitle}"})-[:HAS_AGENDA]->(a:Agenda) 조회`,
      `사용자 수정 요청 분석 중...`,
      `응답 생성 중...`,
    ]
    try {
      await _runPlanningSteps(planningMsg, extractSteps)
      const { data } = await apiAI.post('/api/agent/archive/chat-extract', {
        meeting_id: toSqliteId(detailMeeting.value.id),
        message: content,
        chat_history: [{ agendas: extractResult.value }],
      })
      agentMsg.content = data.reply || '과제 목록을 업데이트했습니다.'
      if (data.agendas && data.agendas.length) {
        extractResult.value = data.agendas.map(ag => ({
          ...ag, _state: null, _editing: false,
          _editTitle: ag.title,
          _editBullets: (ag.bullets || []).join('\n')
        }))
      }
    } catch {
      agentMsg.content = '과제 업데이트 중 오류가 발생했습니다.'
    } finally {
      agentLoading.value = false
    }
    return
  }

  // 일반 모드: supervisor 채팅 — [PLANNING] 이벤트를 실시간으로 수신
  const history = allMessages.value[key]
    .filter(m => m.role === 'user' || m.role === 'agent')
    .slice(0, -1)
    .map(m => ({ role: m.role === 'user' ? 'user' : 'assistant', content: m.content }))
  try {
    await streamPost(
      agentInfo.value.endpoint,
      { meeting_id: toSqliteId(detailMeeting.value?.id), message: content, chat_history: history },
      (chunk) => {
        agentMsg.content += chunk
        nextTick(() => { if (agentMessagesEl.value) agentMessagesEl.value.scrollTop = agentMessagesEl.value.scrollHeight })
      },
      () => {
        planningMsg.done = true
        agentLoading.value = false
        // PLANNING 중 임시 flash 소등 (AI HIGHLIGHT가 없을 경우 대비)
        if (queryHlIdxs.value.size > 0 && !_hlPersistTimer) _applyQueryHL('')
        // 응답이 모두 도착한 뒤 1.5초 후 사고 과정 블록 접기
        setTimeout(() => { planningMsg.open = false }, 1500)
      },
      (step) => {
        planningMsg.steps.push(step)
        _applyQueryHL(step)
        nextTick(() => { if (agentMessagesEl.value) agentMessagesEl.value.scrollTop = agentMessagesEl.value.scrollHeight })
      },
      (labels) => {
        // AI 기반 하이라이팅: LLM 답변에 실제 언급된 노드
        _applyHighlightLabels(labels)
      }
    )
  } catch {
    agentMsg.content = '응답 중 오류가 발생했습니다.'
    planningMsg.done = true; planningMsg.open = false
    agentLoading.value = false
  }
}

function isExtractModeActive() {
  return detailTab.value === 'task' &&
    (extractPhase.value === 'result' || extractPhase.value === 'assign') &&
    !!detailMeeting.value
}

function onAgentKeydown(e) {
  if (atMenuOpen.value && atMenuItems.value.length) {
    if (e.key === 'ArrowDown') { e.preventDefault(); atHighlight.value = (atHighlight.value + 1) % atMenuItems.value.length; return }
    if (e.key === 'ArrowUp') { e.preventDefault(); atHighlight.value = (atHighlight.value - 1 + atMenuItems.value.length) % atMenuItems.value.length; return }
    if (e.key === 'Enter' || e.key === 'Tab') { e.preventDefault(); selectAtItem(atMenuItems.value[atHighlight.value]); return }
    if (e.key === 'Escape') { atMenuOpen.value = false; return }
  }
  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendAgentMsg() }
}
function onAgentFileSelected(e) { agentPendingFiles.value.push(...Array.from(e.target.files || [])); e.target.value = '' }
function agentAutoResize() {
  const el = agentTextareaEl.value; if (!el) return
  el.style.height = '36px'; el.style.height = Math.min(el.scrollHeight, 100) + 'px'
}

// ─── 사고 과정 helper ─────────────────────────────────────────
async function _runPlanningSteps(planningMsg, steps, delayMs = 360) {
  for (const step of steps) {
    planningMsg.steps.push(step)
    await new Promise(r => setTimeout(r, delayMs))
    nextTick(() => { if (agentMessagesEl.value) agentMessagesEl.value.scrollTop = agentMessagesEl.value.scrollHeight })
  }
  planningMsg.done = true
  // extract/inject 모드는 응답 생성 후 바로 접기
  setTimeout(() => { planningMsg.open = false }, 1200)
}

// ─── 좌측 액션 → 우측 에이전트 채팅 주입 ─────────────────────
async function injectActionToAgent(userText, planningSteps, agentReply) {
  if (!agentSidebarOpen.value) { agentSidebarOpen.value = true; initAgentGreeting() }
  await nextTick()
  allMessages.value['supervisor'].push({ role: 'user', content: userText })
  const planningMsg = reactive({ role: 'planning', steps: [], open: true, done: false })
  allMessages.value['supervisor'].push(planningMsg)
  if (agentMessagesEl.value) agentMessagesEl.value.scrollTop = agentMessagesEl.value.scrollHeight
  await _runPlanningSteps(planningMsg, planningSteps)
  const agentMsg = { role: 'agent', content: '' }
  allMessages.value['supervisor'].push(agentMsg)
  for (let i = 0; i < agentReply.length; i++) {
    agentMsg.content += agentReply[i]
    if (i % 4 === 0) {
      await new Promise(r => setTimeout(r, 10))
      if (agentMessagesEl.value) agentMessagesEl.value.scrollTop = agentMessagesEl.value.scrollHeight
    }
  }
}

const bottomMode = ref(null)
const bottomH = ref(0)
let bottomResizing = false, brStartY = 0, brStartH = 0

function initBottomH() {
  const el = mainAreaRef.value
  if (el) bottomH.value = Math.round(el.offsetHeight * 0.46)
  else bottomH.value = Math.round(window.innerHeight * 0.42)
}

function onBottomResizeStart(e) {
  bottomResizing = true
  brStartY = e.clientY; brStartH = bottomH.value
  e.preventDefault()
}

const taskForm = ref({ title: '장소 등록', type: 'Draft', deadline: new Date().toISOString().slice(0,10), depts: ['운영팀'], assignee: '홍길동', purpose: '위원회 추진을 위한 장소 탐색 및 예약', meetingId: '' })
const taskDeptInput = ref('')
function addDept() { if (taskDeptInput.value.trim()) { taskForm.value.depts.push(taskDeptInput.value.trim()); taskDeptInput.value = '' } }
function removeDept(i) { taskForm.value.depts.splice(i, 1) }

function activateTaskMode() {
  bottomMode.value = 'task'; switchAgent('gaon')
  nextTick(initBottomH)
}
function activateReviewMode() {
  bottomMode.value = 'review'; switchAgent('naru')
  nextTick(initBottomH)
}
function closeBottomPanel() { bottomMode.value = null }

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
  if (bottomResizing) {
    const el = mainAreaRef.value
    const maxH = el ? el.offsetHeight * 0.82 : 600
    bottomH.value = Math.max(90, Math.min(maxH, brStartH + (brStartY - e.clientY)))
  }
  if (floatDragging.value) {
    floatDragPos.value = { x: e.clientX, y: e.clientY }
    if (Math.hypot(e.clientX - floatDragStartX, e.clientY - floatDragStartY) > 5) floatDragMoved = true
    const canvas = canvasRef.value
    if (canvas && viewMode.value === 'graph') {
      const rect = canvas.getBoundingClientRect()
      const mx = e.clientX - rect.left, my = e.clientY - rect.top
      const w = canvas.offsetWidth, h = canvas.offsetHeight
      if (mx >= 0 && my >= 0 && mx <= w && my <= h) {
        const docValidTypes = ['meeting_group', 'dept', 'agenda']
        const zf = Math.max(.6, Math.min(2.5, worldZoom))
        const snapR = 22 * zf + 70
        // Find closest valid target — tree 모드에서는 화면에 보이는 노드만 탐색
        let closest = null, minDist = Infinity
        gNodes.forEach((n, i) => {
          if (expandedHubIdx !== null && !_treePositions?.has(i)) return
          const isDoc = floatDragging.value === 'doc'
          if (isDoc ? !docValidTypes.includes(n.type) : (n.type !== 'meeting_group' && n.id !== 'org-root')) return
          let sx, sy
          if (_treePositions?.has(i)) { const tp = _treePositions.get(i); sx=tp.sx; sy=tp.sy }
          else { const p = projectNode(n, w, h); sx=p.sx; sy=p.sy }
          const d = Math.hypot(sx - mx, sy - my)
          if (d < snapR && d < minDist) { minDist = d; closest = { idx: i, node: n, proj: { sx, sy } } }
        })
        // Find closest node of ANY type (to detect invalid hover) — only check visible nodes
        // In tree mode (expandedHubIdx set), only nodes in _treePositions are visible
        let anyClosest = null, anyMinDist = Infinity
        gNodes.forEach((n, i) => {
          if (expandedHubIdx !== null && !_treePositions?.has(i)) return
          let sx, sy
          if (_treePositions?.has(i)) { const tp = _treePositions.get(i); sx=tp.sx; sy=tp.sy }
          else { const p = projectNode(n, w, h); sx=p.sx; sy=p.sy }
          const d = Math.hypot(sx - mx, sy - my)
          if (d < snapR && d < anyMinDist) { anyMinDist = d; anyClosest = { idx: i, node: n } }
        })
        // 유효 타겟이 없는 경우에만 invalid로 처리 (가까운 거리 비교 제거)
        const overInvalid = anyClosest && !closest
        floatDragNearInvalidNode = !!overInvalid
        floatDragTarget = overInvalid ? null : closest
        if (!overInvalid && closest) {
          floatDragPreviewLine.value = { x1: closest.proj.sx, y1: closest.proj.sy, x2: mx, y2: my }
          if (floatDragging.value === 'doc' || floatDragging.value === 'session') {
            const hubNode = closest.node
            let hubIdx = closest.idx
            if (hubNode.type !== 'meeting_group') {
              if (hubNode.meetingGroupId) {
                const mgi = gNodes.findIndex(n => n.id === hubNode.meetingGroupId)
                if (mgi >= 0) hubIdx = mgi
              } else {
                const mgEdge = gEdges.find(e => e.to === closest.idx && gNodes[e.from]?.type === 'meeting_group')
                if (mgEdge) hubIdx = mgEdge.from
              }
            }
            if (expandedHubIdx !== hubIdx) {
              expandedHubIdx = hubIdx; expandedDeptIdx = null
              targetZoom = 1.0; targetCamX=0; targetCamY=0; targetCamZ=0
              targetPan2DX=0; targetPan2DY=0; pan2DX=0; pan2DY=0
            }
          }
        } else { floatDragPreviewLine.value = null }
      } else { floatDragTarget = null; floatDragNearInvalidNode = false; floatDragPreviewLine.value = null }
    }
  }
}
function onGlobalMouseUp() {
  sidebarResizing = false; bottomResizing = false
  if (floatDragging.value) {
    const type = floatDragging.value
    const target = floatDragTarget
    const nearInvalid = floatDragNearInvalidNode
    floatDragging.value = null; floatDragTarget = null; floatDragPreviewLine.value = null
    floatDragNearInvalidNode = false
    const moved = floatDragMoved
    floatDragMoved = false
    document.body.style.cursor = ''
    // Dropped onto an invalid node type → show toast (only if no valid target was found)
    if (moved && nearInvalid && !target) {
      const label = type === 'meeting' ? '회의체' : type === 'session' ? '회의' : '자료'
      showMapToast(`${label}는 해당 노드에 연결할 수 없습니다.`)
      return
    }
    if (!moved || !target) {
      // Click or missed drop → open normally
      if (type === 'meeting') openCreateModal()
      else if (type === 'doc') openUploadModal()
      else if (type === 'session') openSessionModal()
    } else {
      // Dropped onto a valid node
      if (type === 'meeting') {
        const connectId = target.node.id
        if (target.node.type === 'meeting_group') {
          selectedNodeIdx.value = target.idx; expandedHubIdx = target.idx; expandedDeptIdx = null
          targetZoom=1.0;targetCamX=0;targetCamY=0;targetCamZ=0
          targetPan2DX=0;targetPan2DY=0;pan2DX=0;pan2DY=0
        }
        openCreateModal()
        createConnectNodeId.value = connectId
      } else if (type === 'doc') {
        const tn = target.node
        const ctx = {}
        if (tn.type === 'meeting_group') {
          ctx.meetingId = tn.id
          ctx.connectNodeId = tn.id  // meeting_group 자체도 connectNode로 설정
        } else if (tn.type === 'dept') {
          ctx.connectNodeId = tn.id
          ctx.meetingId = tn.meetingGroupId || ''
          if (!ctx.meetingId) {
            const mgEdge = gEdges.find(e => e.to === target.idx && gNodes[e.from]?.type === 'meeting_group')
            if (mgEdge) ctx.meetingId = gNodes[mgEdge.from]?.id || ''
          }
        } else if (tn.type === 'agenda') {
          ctx.relatedTodoId = String(tn.data?.id || '')
          // meetingGroupId: node 속성 또는 edge로 찾기
          ctx.meetingId = tn.meetingGroupId || ''
          if (!ctx.meetingId) {
            const mgEdge = gEdges.find(e => e.to === target.idx && gNodes[e.from]?.type === 'meeting_group')
            if (mgEdge) ctx.meetingId = gNodes[mgEdge.from]?.id || ''
          }
          // dept: agenda 부모 edge로 찾기
          const deptEdge = gEdges.find(e => e.to === target.idx && gNodes[e.from]?.type === 'dept')
          if (deptEdge) {
            ctx.connectNodeId = gNodes[deptEdge.from]?.id || ''
          } else {
            // dept가 없는 경우 회의체 직접을 connectNode로
            ctx.connectNodeId = ctx.meetingId
          }
        }
        openUploadModal(ctx)
      } else if (type === 'session') {
        openSessionModal(target.node.data?.id || null)
      }
    }
  }
}

// ─── Hover ────────────────────────────────────────────
const hoverNode = ref(null)
let hoverNodeIdx = -1

// ─── Detail sidebar ───────────────────────────────────────────
const detailMeeting = ref(null)
const detailOpen = ref(false)
const detailTodos = ref([])
const detailNode = ref(null) // 회의체 외 노드 (부서/과제/회의/파일/사람 등)
const nodeDetailTab = ref('basic') // 'basic' | 'rel'

/** Neo4j ID("mg-001") 또는 정수 ID를 SQLite 정수 ID로 변환 */
function toSqliteId(id) {
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
    const dept = todo.assignee_dept || todo.dept || '미배정'
    if (!groups[dept]) groups[dept] = []
    groups[dept].push(todo)
  }
  return groups
})
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
    const submitted = tasks.length === 0 || tasks.every(t => t.status === 'done')
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
    return { dept, submitted, pendingCount: pending.length, minDays }
  })
})

const groupTodoRatio = ref(new Map())
const assignDeptOptions = computed(() =>
  [...new Set((detailMeeting.value?.members || []).map(m => m.department || m.dept || '').filter(Boolean))])
const showExtractModal = ref(false)
const detailTab = ref('basic') // 'basic' | 'task'
const showAssignModal = ref(false)
const showAssignView = ref(false) // 인라인 배정 뷰
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
const assignResult = ref([])
const extractLoading = ref(false)
const assignLoading = ref(false)

// 과제 탭에서 인라인으로 추출 실행
async function runExtract() {
  if (!detailMeeting.value) return
  // 추출 전용 인사말로 에이전트 채팅 초기화
  allMessages.value['supervisor'] = [{ role: 'agent', content: SUPERVISOR_EXTRACT.greeting }]
  agentSidebarOpen.value = true
  showExtractFlow.value = true
  extractPhase.value = 'result'
  detailTab.value = 'extract'
  extractLoading.value = true
  extractResult.value = []

  // ── 사고 과정 주입 (비동기, 백엔드 API와 병렬) ──────────────────
  const mgTitle = detailMeeting.value?.title || '회의체'
  injectActionToAgent(
    `"${mgTitle}" 회의록·자료에서 과제를 추출해줘`,
    [
      `Neo4j MATCH (mg:MeetingGroup {title:"${mgTitle}"}) 조회`,
      `MATCH (mg)-[:ATTACHED_TO|PRODUCED]-(doc:Document) 문서 수집`,
      `선택된 회의록 및 첨부 파일 텍스트 분석 중...`,
      `Context Graph: 유사 Decision 노드 참조`,
      `아젠다 후보 생성 중...`,
    ],
    `과제 추출이 완료되었습니다.\n추출된 과제를 검토하고, 수정이 필요하면 말씀해 주세요.`
  )
  try {
    // multipart form 구성 (파일 직접 전송)
    const formData = new FormData()
    formData.append('meeting_id', String(detailMeeting.value.id))
    formData.append('selected_file_ids', JSON.stringify(
      selectedFiles.value.filter(f => !String(f).startsWith('upload_'))
    ))
    formData.append('selected_similar_docs', JSON.stringify(selectedSimilarDocs.value))

    // 새로 업로드된 파일 추가
    for (const file of uploadedCtxFiles.value) {
      formData.append('files', file)
    }

    const { data } = await apiAI.post('/api/agent/archive/extract-agendas', formData, {
      headers: { 'Content-Type': 'multipart/form-data' }
    })

    if (data.agendas && data.agendas.length) {
      extractResult.value = data.agendas.map(ag => ({
        ...ag,
        _state: null,
        _editing: false,
        _editTitle: ag.title,
        _editBullets: (ag.bullets || []).join('\n')
      }))
    } else if (data.error) {
      console.error('추출 오류:', data.error)
      extractResult.value = []
    } else {
      extractResult.value = []
    }
  } catch (e) {
    console.error('extract error', e)
    extractResult.value = []
  } finally {
    extractLoading.value = false
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
      meeting_id: toSqliteId(detailMeeting.value.id),
      graph_context: buildGraphContextStr ? buildGraphContextStr() : ''
    })
    extractResult.value = (data.agendas || []).map(ag => ({ ...ag, _state: null, _editing: false, _editTitle: ag.title, _editBullets: [...(ag.bullets||[])] }))
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
  extractResult.value.push({ title: '', bullets: [''], _state: null, _editing: true, _editTitle: '', _editBullets: [''] })
}

async function openAssignModal() {
  showAssignModal.value = true
  if (!detailMeeting.value) return
  assignLoading.value = true
  assignResult.value = []

  // 승인된 추출 과제를 배정 목록으로 변환
  const approved = extractResult.value.filter(a => a._state === 'approved')
  if (approved.length) {
    assignResult.value = approved.map(a => ({
      content: a.title,
      assignee: '',
      dept: a.department || '',
      due: null,
      status: 'pending',
      priority: a.priority || 'normal',
      bullets: a.bullets || [],
      _editing: false,
      _editContent: a.title,
      _editAssignee: '',
      _editDept: a.department || '',
      _editStatus: 'pending',
      _editPriority: a.priority || 'normal',
      _state: null,
    }))
  }
  assignLoading.value = false
}
function saveAssignItem(i) {
  const t = assignResult.value[i]
  t.content = t._editContent
  t.assignee = t._editAssignee
  t.dept = t._editDept
  t.status = t._editStatus
  t.priority = t._editPriority
  t._editing = false
  t._state = 'approved'
}
function cancelAssignEdit(i) {
  const t = assignResult.value[i]
  t._editContent = t.content
  t._editAssignee = t.assignee
  t._editDept = t.dept
  t._editStatus = t.status
  t._editPriority = t.priority
  t._editing = false
}
function rejectAssignItem(i) {
  assignResult.value.splice(i, 1)
}
function addAssignItem() {
  assignResult.value.push({ content: '', assignee: '', dept: '', due: null, status: 'pending', priority: 'normal', _editing: true, _editContent: '', _editAssignee: '', _editDept: '', _editStatus: 'pending', _editPriority: 'normal', _state: null })
}
async function saveApprovedTasks() {
  const approved = assignResult.value.filter(t => t._state === 'approved')
  if (!approved.length || !detailMeeting.value) return

  const savingFlag = ref(false)
  if (savingFlag.value) return
  savingFlag.value = true

  try {
    const saved = []
    for (const t of approved) {
      try {
        const { data } = await apiAI.post(`/api/meetings/${_toSqliteId(detailMeeting.value.id)}/todos`, {
          content: t.content,
          assignee_name: t.assignee || null,
          assignee_dept: t.dept || null,
          priority: t.priority || 'normal',
          status: t.status || 'pending',
          source_type: 'meeting_minutes',
          due_date: t.due || null,
        })
        saved.push(data)
      } catch (e) {
        console.error('과제 저장 실패:', t.content, e)
      }
    }

    // DB 저장 후 목록 새로고침
    detailTodos.value = (await apiAI.get(`/api/meetings/${_toSqliteId(detailMeeting.value.id)}/todos`)).data || []

    const total = detailTodos.value.length
    const done = detailTodos.value.filter(t => t.status === 'done').length
    groupTodoRatio.value = new Map(groupTodoRatio.value).set(
      detailMeeting.value.id, total ? done / total : null
    )

    // 추출 단계 초기화
    extractPhase.value = 'context'
    showExtractFlow.value = false
    extractResult.value = []
    assignResult.value = []
    detailTab.value = 'task'

    alert(`${saved.length}개 과제가 저장되었습니다.`)
    setTimeout(refreshArchive, 600)
  } catch (e) {
    console.error('저장 오류:', e)
    alert('저장 중 오류가 발생했습니다.')
  }
}

const PRIORITY_LABEL = { urgent_important: '긴급·중요', important: '중요', urgent: '긴급', normal: '보통', low: '낮음' }
const STATUS_LABEL = { pending: '대기', in_progress: '진행', submitted: '승인대기', done: '완료' }

function goToProcessStep(step) {
  if (step === 'context' && (extractPhase.value === 'result' || extractPhase.value === 'assign')) {
    extractPhase.value = 'context'
  } else if (step === 'result' && extractPhase.value === 'assign') {
    extractPhase.value = 'result'
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
      role: mb.role || 'presenter',
    }))
  } catch { members = (m.members || []).map(mb => ({ id: null, userId: mb.userId, name: mb.userName || '?', email: '', role: 'presenter' })) }
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
  settingsModal.value.members.push({ id: null, userId: user.id, name: user.name || user.email, email: user.email, role: 'presenter' })
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
    await api.patch(`/api/v1/meetings/${meeting.id}`, { title: form.title, purpose: form.purpose, guidelines: form.guidelines })
    for (const memberId of removedIds) {
      await api.delete(`/api/v1/meetings/${meeting.id}/members/${memberId}`)
    }
    for (const mb of members.filter(m => m.id === null)) {
      await api.post(`/api/v1/meetings/${meeting.id}/members`, { userId: mb.userId, role: mb.role })
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

const ROLE_MAP = { admin: '간사', presenter: '참여자' }
function roleLabel(r) { return ROLE_MAP[r] || r || '참여자' }

// ─── Role-based helpers ───────────────────────────────────────
const detailMyRole = computed(() =>
  detailMeeting.value?.id ? (meetingsStore.meetingRoles[detailMeeting.value.id] ?? null) : null
)
const isDetailAdmin = computed(() => detailMyRole.value === 'admin')
const isAnyAdmin = computed(() => {
  // SQLite 기반 role 확인
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
  detailNode.value = null // 회의체 오픈 시 노드 초기화
  if (!isSameMeeting) {
    selectedMinutes.value = []; selectedFiles.value = []
    selectedSimilarDocs.value = []; uploadedCtxFiles.value = []
    extractPhase.value = 'context'; showExtractFlow.value = false; extractResult.value = []; assignResult.value = []
  }
  hoverNode.value = null
  detailTodos.value = []
  try {
    detailTodos.value = (await apiAI.get(`/api/meetings/${_toSqliteId(groupData.id)}/todos`)).data || []
    // ratio는 승인 후 saveApprovedTasks에서 설정됨.
    // 이미 저장된 ratio가 없으면 로드된 todos 기준으로 초기화
    if (!groupTodoRatio.value.has(groupData.id)) {
      const total = detailTodos.value.length
      const done = detailTodos.value.filter(t => t.status === 'done').length
      groupTodoRatio.value = new Map(groupTodoRatio.value).set(groupData.id, total ? done / total : null)
    }
  } catch { detailTodos.value = [] }
}

// ─── 3D Graph ─────────────────────────────────────────────────
const canvasRef = ref(null)
const mainAreaRef = ref(null)
let ctx = null, animId = null, ro = null
let rotX = 0.35, rotY = 0.1
let isDragging = false, lastMx = 0, lastMy = 0
const isPanMode = ref(false)
let autoRotate = false, focusNode = null
const selectedNodeIdx = ref(null)
const breadcrumb = ref([])
let targetCamX = 0, targetCamY = 0, targetCamZ = 0
let camX = 0, camY = 0, camZ = 0
let worldZoom = 1.0, targetZoom = 1.0, dpr = 1
let gNodes = [], gEdges = []
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
let expandedHubIdx = null
let expandedDeptIdx = null
let rotationPaused = false
// 2D tree mode pan state (used when expandedHubIdx !== null)
let pan2DX = 0, pan2DY = 0, targetPan2DX = 0, targetPan2DY = 0
let _treePositions = null // Map<idx, {sx, sy}> cached each frame in 2D mode
let dragNode2D = null // idx of node being dragged in 2D tree mode
let dragNode2DMoved = false
const _node2DOffsets = new Map() // Map<idx, {dx,dy}> — accumulated screen-pixel offsets from dragging
// Float button drag state
const floatDragging = ref(null)       // null | 'meeting' | 'doc'
const floatDragPos = ref({ x: 0, y: 0 })
const floatDragPreviewLine = ref(null) // { x1,y1,x2,y2 } in canvas px
let floatDragTarget = null
let floatDragStartX = 0, floatDragStartY = 0, floatDragMoved = false
let floatDragNearInvalidNode = false

// ─── Connection dot / edge-draw state ─────────────────────────
const connDotVisible = ref(false)   // reactive → drives cursor style
let connDotNodeIdx = -1
let connDotSx = 0, connDotSy = 0
const connDragging = ref(false)     // reactive → drives cursor style
let connDragFromIdx = -1
let connDragFromSx = 0, connDragFromSy = 0
let connDragCurSx = 0, connDragCurSy = 0
let connDragTargetIdx = -1

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
const uploadForm = ref({ label: '', fileType: '보고자료', connectNodeId: '', relType: '생성', meetingId: '', relatedTodoId: '', file: null })
const uploadMeetingTodos = ref([]) // 선택된 회의체의 과제 목록
// 드래그로 자동 입력된 필드 추적 (직접 선택 시에는 표시 안 함)
const prefilledCtx = ref({ meetingId: false, connectNodeId: false, relatedTodoId: false })

let _pendingRelatedTodoId = ''
watch(() => uploadForm.value.meetingId, async (id) => {
  const pendingTodo = _pendingRelatedTodoId
  _pendingRelatedTodoId = ''
  uploadMeetingTodos.value = []
  uploadForm.value.relatedTodoId = ''
  if (!id) return
  // node id가 'mg-13' 또는 'mg-sqlite-3' 형식이므로 숫자만 추출
  const meetingId = id.match(/\d+$/)?.[0]
  if (!meetingId) return
  try {
    uploadMeetingTodos.value = (await apiAI.get(`/api/meetings/${meetingId}/todos`)).data || []
    if (pendingTodo) uploadForm.value.relatedTodoId = pendingTodo
  } catch { uploadMeetingTodos.value = [] }
})

// connectNodeId가 meeting_group이면 meetingId 자동 동기화
watch(() => uploadForm.value.connectNodeId, (nodeId) => {
  if (!nodeId) return
  const node = gNodes.find(n => n.id === nodeId)
  if (node?.type === 'meeting_group') {
    const mgData = node.data
    // SQLite id: 숫자이면 'mg-{id}', 아니면 Neo4j id
    const rawId = mgData?.id ?? nodeId
    uploadForm.value.meetingId = (typeof rawId === 'string' && rawId.includes('-')) ? rawId : `mg-${rawId}`
  }
})

// ─── 파일 노드 AI 검토 패널 ────────────────────────────────────
const fileReviewPanel = ref(null)  // { node, aiResult, extracting, assigning, extractedAgendas }
const fileReviewAnalyzing = ref(false)

async function openFileReview(node) {
  fileReviewPanel.value = {
    node,
    aiResult: node.aiReview || null,
    extracting: false,
    assigning: false,
    extractedAgendas: node.extractedAgendas || [],
  }
}

async function rerunFileReview() {
  if (!fileReviewPanel.value) return
  fileReviewAnalyzing.value = true

  // ── 사고 과정 주입 ──────────────────────────────────────
  const fileName = fileReviewPanel.value.node.label
  injectActionToAgent(
    `"${fileName}" 파일을 AI로 검토해줘`,
    [
      `파일 메타데이터 분석 중: ${fileName}`,
      `Neo4j MATCH (doc:Document {label:"${fileName}"}) 조회`,
      `MATCH (doc)-[:ATTACHED_TO]->(mg:MeetingGroup) 관련 회의체 확인`,
      `Graph Context 기반 내용 적합성 평가 중...`,
      `AI 검토 결과 생성 중...`,
    ],
    `**${fileName}** 검토가 완료되었습니다.\n검토 결과는 좌측 파일 패널에서 확인하세요.`
  )

  try {
    const { data } = await apiAI.post('/api/agent/archive/analyze-file', {
      file_name: fileReviewPanel.value.node.label,
      file_type: fileReviewPanel.value.node.fileType,
      graph_context: buildGraphContextStr(),
    })
    fileReviewPanel.value.aiResult = data
    fileReviewPanel.value.node.aiReview = data
  } catch {
    fileReviewPanel.value.aiResult = fileReviewPanel.value.node.aiReview || {
      score: 70, feedback: ['AI 서버 연결 실패'], agendas: [], related_depts: [],
      criteria: { recap: false, progress: false, hurdle: false, plan: false },
    }
  } finally { fileReviewAnalyzing.value = false }
}

async function extractAgendas() {
  if (!fileReviewPanel.value) return
  fileReviewPanel.value.extracting = true

  // ── 사고 과정 주입 ──────────────────────────────────────
  const fileName = fileReviewPanel.value.node.label
  injectActionToAgent(
    `"${fileName}"에서 아젠다를 추출해줘`,
    [
      `문서 텍스트 파싱: ${fileName}`,
      `Neo4j MATCH (doc:Document)-[:ATTACHED_TO]->(mg) 맥락 조회`,
      `핵심 의제 및 결정 사항 식별 중...`,
      `아젠다 구조화 및 우선순위 분류 중...`,
    ],
    `아젠다 추출이 완료되었습니다.\n추출된 아젠다를 검토하고 과제 배정으로 이동하세요.`
  )

  try {
    const { data } = await apiAI.post('/api/agent/archive/extract-agendas', {
      file_name: fileReviewPanel.value.node.label,
      file_type: fileReviewPanel.value.node.fileType,
      graph_context: buildGraphContextStr(),
    })
    fileReviewPanel.value.extractedAgendas = data.agendas || []
    fileReviewPanel.value.node.extractedAgendas = data.agendas || []
  } catch {
    // 목업 아젠다
    const mock = [
      { title: '기술 투자를 위한 협업 체계 구축', bullets: ['멤버사 간 공동 투자 전략을 통해 사업 시너지 제고', '지속적인 사업 Needs 반영 및 문제 정의를 통한 해결 방안 모색'] },
      { title: '데이터 기반 의사결정 체계 수립', bullets: ['핵심 KPI 정의 및 대시보드 구축 계획', '부서별 데이터 오너십 및 거버넌스 정책 마련'] },
    ]
    fileReviewPanel.value.extractedAgendas = mock
    fileReviewPanel.value.node.extractedAgendas = mock
  } finally { fileReviewPanel.value.extracting = false }
}

async function assignTasks() {
  if (!fileReviewPanel.value) return
  fileReviewPanel.value.assigning = true

  // ── 사고 과정 주입 ──────────────────────────────────────
  const agendaCount = fileReviewPanel.value.extractedAgendas?.length || 0
  injectActionToAgent(
    `추출된 ${agendaCount}개 아젠다를 부서·담당자에게 배정해줘`,
    [
      `Neo4j MATCH (p:Person)-[:BELONGS_TO]->(d:Department) 구성원 조회`,
      `각 아젠다 담당 부서 적합도 분석 중...`,
      `MATCH (mg)-[:PARTICIPATES_IN]-(d:Department) 참여 부서 확인`,
      `GraphRAG 기반 최적 배정 후보 생성 중...`,
      `과제 배정 요청 전송 중...`,
    ],
    `${agendaCount}개 아젠다 배정 요청이 완료되었습니다.\nNeo4j에 과제 노드가 생성됩니다.`
  )

  try {
    await apiAI.post('/api/agent/archive/assign-tasks', {
      file_name: fileReviewPanel.value.node.label,
      agendas: fileReviewPanel.value.extractedAgendas,
      graph_context: buildGraphContextStr(),
    })
    alert('과제 배정이 완료되었습니다. (GraphRAG 기반)')
  } catch {
    alert('과제 배정 요청이 전송되었습니다.')
  } finally { fileReviewPanel.value.assigning = false }
}

// ─── Ontology edge relation constants ─────────────────────────
// ── Neo4j 관계명 색상 매핑 ─────────────────────────────────────
const REL_COLORS = {
  'PART_OF':        '#a89fd4',  // org → meetingGroup
  'PARTICIPATES_IN':'#8b7fc0',  // dept/subGroup → meetingGroup
  'BELONGS_TO':     '#a78bfa',  // person → dept
  'ADMIN_OF':       '#fbbf24',  // person → meetingGroup (간사)
  'MEMBER_OF':      '#60a5fa',  // person → meetingGroup (구성원)
  'ASSIGNED_TO':    '#34d399',  // person → agenda
  'OWNED_BY':       '#6abba5',  // agenda → meetingGroup
  'HELD_BY':        '#c9a870',  // session → meetingGroup
  'COVERS':         '#f472b6',  // session → agenda
  'PRODUCED':       '#a8a5a2',  // session → document
  'ATTACHED_TO':    '#fb923c',  // document → meetingGroup
  'BASED_ON':       '#38bdf8',  // decision → session
  'CAUSED_BY':      '#86efac',  // decision → agenda
  'REFERENCES':     '#7a8090',  // generic reference
}
function hexToRgba(hex, a) {
  const r=parseInt(hex.slice(1,3),16),g=parseInt(hex.slice(3,5),16),b=parseInt(hex.slice(5,7),16)
  return `rgba(${r},${g},${b},${a})`
}
// ── 소스 타입 × 대상 타입 → Neo4j 관계 자동 추론 ──────────────
// 정방향 키 (from→to)로 관계와 Neo4j 방향 정의
// 역방향으로 드래그해도 canonical 방향을 자동으로 맞춤
const REL_MATRIX = {
  // ── Org / Dept ─────────────────────────────────────────────
  'dept→meeting_group':          'PARTICIPATES_IN',
  'org→meeting_group':           'PART_OF',
  'org→dept':                    'PART_OF',
  'dept→dept':                   'PART_OF',
  'person→dept':                 'BELONGS_TO',
  'dept→file':                   'ATTACHED_TO',
  'org→file':                    'REFERENCES',
  // ── MeetingGroup ───────────────────────────────────────────
  'meeting_group→meeting_group': 'PARTICIPATES_IN',
  'person→meeting_group':        'MEMBER_OF',
  'file→meeting_group':          'ATTACHED_TO',
  // ── Agenda ─────────────────────────────────────────────────
  'agenda→meeting_group':        'OWNED_BY',
  'person→agenda':               'ASSIGNED_TO',
  'file→agenda':                 'REFERENCES',
  // ── Session ────────────────────────────────────────────────
  'session→meeting_group':       'HELD_BY',
  'session→agenda':              'COVERS',
  'session→file':                'PRODUCED',
  'session→session':             'FOLLOWED_BY',
  // ── Decision ───────────────────────────────────────────────
  'decision→session':            'BASED_ON',
  'decision→agenda':             'CAUSED_BY',
  'decision→meeting_group':      'BASED_ON',
  // ── File / Document ────────────────────────────────────────
  'file→file':                   'REFERENCES',
  'file→session':                'REFERENCES',
  'file→dept':                   'ATTACHED_TO',
  'person→file':                 'ATTACHED_TO',
}
function autoRel(sourceNodeId, targetType) {
  const srcNode = gNodes.find(n => n.id === sourceNodeId)
  const fwd = `${srcNode?.type}→${targetType}`
  if (REL_MATRIX[fwd]) return REL_MATRIX[fwd]
  // try reverse
  const rev = `${targetType}→${srcNode?.type}`
  return REL_MATRIX[rev] || 'REFERENCES'
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
  return { rel: 'REFERENCES', neo4jFromId: fn?.id, neo4jToId: tn?.id }
}

// ─── Relationship manager ─────────────────────────────────────
const ALL_REL_TYPES = Object.keys(REL_COLORS)
const graphVersion = ref(0) // bump to force sidebar reactivity when gEdges mutate

const currentNodeId = computed(() => {
  if (detailMeeting.value) return `mg-${detailMeeting.value.id}`
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
const relAddForm   = ref({ fromId: '', toId: '', rel: 'REFERENCES' })
const relEditIdx   = ref(null)
const relEditRel   = ref('')

// Auto-suggest rel type when src/dst change in add form
watch(() => [relAddForm.value.fromId, relAddForm.value.toId], ([fId, tId]) => {
  if (!fId || !tId) return
  const tNode = gNodes.find(n => n.id === tId)
  relAddForm.value.rel = autoRel(fId, tNode?.type || '') || 'REFERENCES'
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
// Neo4j mg-003 / mg-sqlite-3 → SQLite 정수 ID 추출
function _toSqliteId(id) {
  if (!id) return id
  // 숫자만으로 이루어진 경우 그대로 반환
  if (/^\d+$/.test(String(id))) return id
  // 끝에서 숫자만 추출: "mg-003" → "3", "mg-sqlite-3" → "3"
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
  relAddForm.value = { fromId: currentNodeId.value || '', toId: '', rel: 'REFERENCES' }
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
  const result = [{ id:'org-root', label:'나', typeLabel:'구성원', type:'person' }]
  const depts = new Set()
  groups.forEach(g => (g.members||[]).forEach(mb => depts.add(mb.department||mb.dept||'미지정')))
  depts.forEach(d => result.push({ id:`dept-${d}`, label:d, typeLabel:'부서', type:'dept' }))
  groups.forEach(g => {
    const rawId = g.id
    const mgId = (typeof rawId === 'string' && rawId.includes('-')) ? rawId : `mg-${rawId}`
    result.push({ id: mgId, label:g.title, typeLabel:'회의체', type:'meeting_group' })
  })
  groups.forEach(g => (g.minutes||[]).forEach((m,i) => result.push({ id:`session-${g.id}-${i}`, label:m.session_title||`${m.session_number||i+1}차 회의`, typeLabel:'회의', type:'session' })))
  return result
})

// ─── Upload: dept-only connectable nodes ──────────────────────
const deptConnectableNodes = computed(() => {
  // 선택된 회의체가 있으면 해당 회의체에 속한 부서 + 회의체 자체도 포함, 없으면 전체 유니크 부서
  if (uploadForm.value.meetingId) {
    const nodes = []
    // meeting_group 자체도 연결 대상으로 포함
    const mgNode = gNodes.find(n => n.id === uploadForm.value.meetingId && n.type === 'meeting_group')
    if (mgNode) nodes.push({ id: mgNode.id, label: mgNode.label, typeLabel: '회의체', type: 'meeting_group' })
    gNodes
      .filter(n => n.type === 'dept' && n.meetingGroupId === uploadForm.value.meetingId)
      .forEach(n => nodes.push({ id: n.id, label: n.label, typeLabel: '부서', type: 'dept' }))
    return nodes
  }
  const seen = new Set()
  return gNodes
    .filter(n => n.type === 'dept')
    .filter(n => { if (seen.has(n.label)) return false; seen.add(n.label); return true })
    .map(n => ({ id: n.id, label: n.label, typeLabel: '부서', type: 'dept' }))
})

// 선택된 회의체 노드에 연결된 과제들만 드롭다운에 표시
const 업로드회의체과제 = computed(() => {
  if (!uploadForm.value.meetingId) return []
  // connectNodeId가 meeting_group 노드인 경우 해당 회의체의 과제
  const mgNodeId = uploadForm.value.connectNodeId
  const mgNode = gNodes.find(n => n.id === mgNodeId && n.type === 'meeting_group')
  if (mgNode?.data?.tasks?.length) return mgNode.data.tasks
  // fallback: uploadMeetingTodos (API 로드)
  return uploadMeetingTodos.value
})

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
const selectedAgendas = ref([])      // indices of agendas to apply
const selectedRelDepts = ref([])     // dept names to auto-connect

function openUploadModal(ctx = {}) {
  showUploadModal.value = true
  uploadStep.value = 1
  aiResult.value = null
  selectedAgendas.value = []
  selectedRelDepts.value = []
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
    relatedTodoId: ctx.relatedTodoId ? String(ctx.relatedTodoId) : '',
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
  const deptNode = connectableNodes.value.find(n => n.id === uploadForm.value.connectNodeId)

  // 실제 파일 내용 읽기 (텍스트 기반 파일만)
  let file_content = ''
  const file = uploadForm.value.file
  if (file) {
    const TEXT_EXTS = /\.(txt|md|html|htm|csv|json|xml|log|yaml|yml)$/i
    if (TEXT_EXTS.test(file.name) || file.type.startsWith('text/')) {
      try {
        file_content = await new Promise((resolve, reject) => {
          const reader = new FileReader()
          reader.onload = e => resolve(e.target.result?.slice(0, 4000) || '')
          reader.onerror = reject
          reader.readAsText(file, 'UTF-8')
        })
      } catch { file_content = '' }
    } else {
      // PDF/이미지 등 — 파일명만 있고 내용 없음을 명시
      file_content = '[바이너리 파일 — 내용 추출 불가]'
    }
  }
  // 파일 자체가 없으면 (이름만 입력한 경우) 명시
  if (!file_content) file_content = '[파일 미첨부 — 이름만 입력됨]'

  try {
    const { data } = await apiAI.post('/api/agent/archive/analyze-file', {
      file_name: uploadForm.value.label,
      file_type: uploadForm.value.fileType,
      dept_name: deptNode?.label || '',
      graph_context: buildGraphContextStr(),
      file_content,
    })
    aiResult.value = data
    selectedAgendas.value = data.agendas.map((_, i) => i)      // 기본 전체 선택
    selectedRelDepts.value = [...(data.related_depts || [])]   // 기본 전체 선택
  } catch (e) {
    aiResult.value = {
      score: 70,
      feedback: ['AI 분석 서버에 연결할 수 없습니다.'],
      agendas: [],
      related_depts: [],
      criteria: uploadForm.value.fileType==='발제자료'
        ? { recap: false, progress: false, hurdle: false, plan: false }
        : null,
    }
  } finally {
    aiAnalyzing.value = false
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
  const fromX = fromNode?.x||0, fromZ = fromNode?.z||0
  const phi = Math.atan2(fromZ, fromX) + 0.28
  const baseR = Math.sqrt(fromX*fromX+fromZ*fromZ)
  const fileNodeId = `file-new-${Date.now()}`

  // 연결 노드의 meeting_group을 찾아 groupIdx 상속 (getVisibleSet에서 가시성 포함되도록)
  const mgNode = gNodes.find(n => n.id === uploadForm.value.meetingId && n.type === 'meeting_group')

  const newNode = {
    id: fileNodeId,
    label: uploadForm.value.label,
    type: 'file',
    fileType: uploadForm.value.fileType,
    aiScore: aiResult.value?.score ?? null,
    aiReview: aiResult.value ? { ...aiResult.value } : null,
    extractedAgendas: [],
    groupIdx: mgNode?.groupIdx,
    meetingGroupId: uploadForm.value.meetingId,
    x: Math.cos(phi)*(baseR+90), y: (fromNode?.y||0)+42, z: Math.sin(phi)*(baseR+90)
  }
  gNodes.push(newNode)
  const fileIdx = gNodes.length - 1
  const rel = autoRel(uploadForm.value.connectNodeId, 'file')
  // 엣지 방향: file → connectNode (computeTreeLayout kids() 탐색 방향과 일치)
  if (fromIdx >= 0) gEdges.push({ from: fileIdx, to: fromIdx, rel })

  // AI가 추천한 유관부서 자동 연결
  selectedRelDepts.value.forEach(deptName => {
    const deptId = `dept-${deptName}`
    let deptNodeIdx = gNodes.findIndex(n => n.id === deptId)
    if (deptNodeIdx < 0) {
      const angle = Math.random() * Math.PI * 2
      gNodes.push({ id: deptId, label: deptName, type: 'dept', groupIdx: mgNode?.groupIdx, x: Math.cos(angle)*100, y: 20, z: Math.sin(angle)*100 })
      deptNodeIdx = gNodes.length - 1
    }
    gEdges.push({ from: fileIdx, to: deptNodeIdx, rel: 'ATTACHED_TO' })
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
  initGraph()

  // 백엔드 업로드 + Neo4j 임베딩 동기화
  const file = uploadForm.value.file
  if (file) {
    const fd = new FormData()
    fd.append('file', file)
    const rawMgId = uploadForm.value.meetingId
    const mgNumId = rawMgId ? _toSqliteId(rawMgId) : null
    if (mgNumId) fd.append('meeting_id', String(mgNumId))
    apiAI.post('/api/sync/file', fd, { headers: { 'Content-Type': 'multipart/form-data' } })
      .then(() => setTimeout(refreshArchive, 1200))
      .catch(e => console.warn('[doAddFile] sync/file 실패:', e))
  }
}




const meetingGroups = computed(() => {
  // Neo4j 데이터가 있으면 우선 사용 (그래프 온톨로지 기반)
  if (neo4jMeetings.value.length > 0) return neo4jMeetings.value

  // fallback: SQLite 기반 조합
  const map = new Map()
  // 본인이 참여 중인 회의체만 포함
  meetingsStore.meetings
    .filter(m => meetingsStore.meetingRoles[m.id] != null)
    .forEach(m => {
    map.set(m.id, { id: m.id, title: m.title, meeting_type: m.meeting_type || null, minutes: [], reports: [], members: [], tasks: [] })
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
      _role: meetingsStore.meetingRoles[g.id] === 'admin' ? '간사' : '참여자',
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
      items.push({
        type: 'minutes',
        desc: `${m.session_number ? m.session_number + '차 ' : ''}회의 진행 및 회의록 작성`,
        manager: managerName,
        date: m.ended_at,
        hasFile: true,
        fileName: m.session_title || '회의록',
      })
    })
    // 보고서
    g.reports.forEach(r => {
      const dept = r.submitted_by_dept || r.department || ''
      items.push({
        type: 'report',
        desc: dept ? `${dept}에서 업로드한 보고서` : `보고서 업로드 (${r.file_name || '파일'})`,
        manager: r.submitted_by || managerName,
        date: r.submitted_at,
        hasFile: true,
        fileName: r.file_name || '보고서',
      })
      // 보고서 승인 이력 (상태가 있을 경우)
      if (r.status === 'approved') {
        items.push({
          type: 'approved',
          desc: `${dept ? dept + '에서 업로드한 ' : ''}보고서 승인`,
          manager: managerName,
          date: r.approved_at || r.submitted_at,
          hasFile: false,
          fileName: '',
        })
      } else if (r.status === 'rejected') {
        items.push({
          type: 'rejected',
          desc: `${dept ? dept + '에서 업로드한 ' : ''}보고서 반려`,
          manager: managerName,
          date: r.rejected_at || r.submitted_at,
          hasFile: false,
          fileName: '',
        })
      }
    })
    items.sort((a, b) => {
      const da = a.date ? new Date(a.date) : new Date(0)
      const db = b.date ? new Date(b.date) : new Date(0)
      return db - da
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

function buildGraphNodes() {
  const nodes = [], edges = []
  const data = meetingGroups.value

  // ── 반경 정의 (Neo4j 그래프 온톨로지 계층 반영) ─────────────
  // Organization(중심) → MeetingGroup → Department/Person → Document/Agenda → Session → Decision
  const R = { meeting_group: 240, dept: 400, person: 340, agenda: 580, session: 750, file: 920, decision: 600 }
  const Y = { org: 0, meeting_group: 0, dept: -15, person: -50, agenda: 20, session: 30, file: 12, decision: -20 }
  const TWO_PI = Math.PI * 2

  // ── Person 노드 (현재 로그인 사용자, 중심) ────────────────────
  const orgIdx = nodes.length
  const orgLabel = currentPerson.value?.name || authStore.user?.name || authStore.user?.email?.split('@')[0] || '나'
  nodes.push({ id: 'org-root', label: orgLabel, type: 'person', x: 0, y: Y.org, z: 0, data: currentOrg.value })

  // 소속 회의체 없으면 본인 노드만 표시
  if (!data.length) return { nodes, edges }

  // ── Organization 노드 (회의체 클릭 시 하단에 표시) ───────────
  const orgNodeIdx = nodes.length
  nodes.push({ id: 'org-node', label: currentOrg.value?.name || '조직', type: 'org', x: 0, y: Y.meeting_group + 40, z: 0, data: currentOrg.value })

  const mgCount = data.length
  const sectorWidth = TWO_PI / Math.max(mgCount, 1)

  // dept name → neo4j id 룩업 맵
  const deptIdByName = new Map(neo4jDepts.value.map(d => [d.name, d.id]))

  data.forEach((g, gi) => {
    const ang = (gi / Math.max(mgCount, 1)) * TWO_PI
    // g.id가 Neo4j 전체 ID("mg-001" 등)이면 그대로 사용, SQLite 정수이면 prefix 추가
    const rawId = g.id || gi
    const mgNodeId = (typeof rawId === 'string' && rawId.includes('-')) ? rawId : `mg-${rawId}`
    // Neo4j에 전달할 실제 ID (새 SQLite 회의체는 "mg-sqlite-{id}" 형식)
    const neo4jId = (typeof rawId === 'string' && rawId.includes('-')) ? rawId : `mg-sqlite-${rawId}`

    // ── MeetingGroup 노드 ─────────────────────────────────────
    const mgIdx = nodes.length
    nodes.push({
      id: mgNodeId, label: g.title || `회의체${gi + 1}`, type: 'meeting_group',
      x: Math.cos(ang) * R.meeting_group, y: Y.meeting_group, z: Math.sin(ang) * R.meeting_group,
      data: g, groupIdx: gi, neo4jId,
    })
    // person -[ADMIN_OF / MEMBER_OF]→ meetingGroup (본인 역할 기반)
    // Neo4j 응답의 members 배열에서 현재 유저를 찾아 role을 우선 사용
    // (meetingRoles는 SQLite 기반이라 Neo4j와 불일치할 수 있음)
    const myName = currentPerson.value?.name || authStore.user?.name
    const myEmail = currentPerson.value?.email || authStore.user?.employee_id
    const selfMember = g.members?.find(mb =>
      mb.email === myEmail || mb.userName === myName
    )
    const selfRole = selfMember?.role ?? meetingsStore.meetingRoles?.[g.id]
    const selfRel = selfRole === 'admin' ? 'ADMIN_OF' : 'MEMBER_OF'
    edges.push({ from: orgIdx, to: mgIdx, rel: selfRel })
    edges.push({ from: mgIdx, to: orgNodeIdx, rel: 'PART_OF' })

    // ── Department 노드: 회의에 PARTICIPATES_IN ───────────────
    const membersByDept = new Map()
    ;(g.members || []).forEach(mb => {
      const d = mb.department || mb.dept || '미지정'
      if (!membersByDept.has(d)) membersByDept.set(d, [])
      membersByDept.get(d).push(mb)
    })
    const depts = [...membersByDept.keys()]
    const dCount = depts.length
    const deptFan = dCount > 1 ? Math.min(sectorWidth * 0.42, 0.55) / (dCount - 1) : 0
    const deptIdxMap = new Map()

    depts.forEach((deptName, di) => {
      const dAng = ang + (di - (dCount - 1) / 2) * deptFan
      const deptIdx = nodes.length
      deptIdxMap.set(deptName, deptIdx)
      nodes.push({
        id: `dept-${g.id || gi}-${deptName}`, label: deptName, type: 'dept',
        x: Math.cos(dAng) * R.dept, y: Y.dept, z: Math.sin(dAng) * R.dept,
        members: membersByDept.get(deptName), groupIdx: gi, meetingGroupId: mgNodeId,
        neo4jId: deptIdByName.get(deptName) || null,
      })
      // dept -[PARTICIPATES_IN]→ meetingGroup
      edges.push({ from: deptIdx, to: mgIdx, rel: 'PARTICIPATES_IN' })

      // ── Person 노드: BELONGS_TO dept, ADMIN_OF/MEMBER_OF meetingGroup ─
      const deptMembers = membersByDept.get(deptName) || []
      const pCount = deptMembers.length
      deptMembers.forEach((mb, pi) => {
        const pFan = pCount > 1 ? Math.min(0.3, sectorWidth * 0.15) / (pCount - 1) : 0
        const pAng = dAng + (pi - (pCount - 1) / 2) * pFan
        const pIdx = nodes.length
        const pName = mb.userName || mb.name || '?'
        nodes.push({
          id: `person-${g.id || gi}-${mb.userId || pi}`, label: pName, type: 'person',
          x: Math.cos(pAng) * R.person, y: Y.person, z: Math.sin(pAng) * R.person,
          groupIdx: gi, meetingGroupId: mgNodeId, data: mb,
          neo4jId: mb.userId || null,
        })
        // person -[BELONGS_TO]→ dept
        edges.push({ from: pIdx, to: deptIdx, rel: 'BELONGS_TO' })
        // person -[ADMIN_OF or MEMBER_OF]→ meetingGroup
        const memberRel = mb.role === 'admin' ? 'ADMIN_OF' : 'MEMBER_OF'
        edges.push({ from: pIdx, to: mgIdx, rel: memberRel })
      })
    })

    // ── Agenda 노드: OWNED_BY meetingGroup ───────────────────
    const taskList = g.tasks || []
    const tasksByDept = new Map()
    depts.forEach(d => tasksByDept.set(d, []))
    const unassigned = []
    taskList.forEach(task => {
      const d = task.assignee_dept || task.dept || ''
      if (d && tasksByDept.has(d)) tasksByDept.get(d).push(task)
      else unassigned.push(task)
    })
    unassigned.forEach((task, ti) => {
      if (depts.length > 0) tasksByDept.get(depts[ti % depts.length]).push(task)
    })

    const agendaIdxByTodoId = new Map()
    const allAgendaIdxList = []

    depts.forEach(deptName => {
      const deptIdx = deptIdxMap.get(deptName)
      const deptNode = nodes[deptIdx]
      const dAng = deptNode ? Math.atan2(deptNode.z, deptNode.x) : ang
      const deptTasks = tasksByDept.get(deptName) || []
      const tCount = deptTasks.length
      const tFan = tCount > 1 ? Math.min(0.22, 0.14) : 0
      deptTasks.forEach((task, ti) => {
        const tAng = dAng + (ti - (tCount - 1) / 2) * tFan
        const agIdx = nodes.length
        allAgendaIdxList.push(agIdx)
        const agLabel = (task.content || `아젠다 ${ti + 1}`).slice(0, 12) + ((task.content || '').length > 12 ? '…' : '')
        nodes.push({
          id: `agenda-${g.id || gi}-${task.id || ti}`, label: agLabel, type: 'agenda',
          x: Math.cos(tAng) * R.agenda, y: Y.agenda, z: Math.sin(tAng) * R.agenda,
          groupIdx: gi, data: task, meetingGroupId: mgNodeId,
          neo4jId: task.id || null,
        })
        // agenda -[OWNED_BY]→ meetingGroup
        edges.push({ from: agIdx, to: mgIdx, rel: 'OWNED_BY' })
        // person -[ASSIGNED_TO]→ agenda (담당 부서의 첫 번째 구성원)
        const assigneeDept = task.assignee_dept || deptName
        const assigneeMembers = membersByDept.get(assigneeDept) || []
        if (assigneeMembers.length > 0) {
          const personId = `person-${g.id || gi}-${assigneeMembers[0].userId || 0}`
          const personIdx = nodes.findIndex(n => n.id === personId)
          if (personIdx >= 0) edges.push({ from: personIdx, to: agIdx, rel: 'ASSIGNED_TO' })
        }
        agendaIdxByTodoId.set(String(task.id), agIdx)
      })
    })

    // 부서 없을 때 아젠다를 회의체에 직접 연결
    if (depts.length === 0 && taskList.length > 0) {
      taskList.forEach((task, ti) => {
        const tAng = ang + (ti - (taskList.length - 1) / 2) * 0.2
        const agIdx = nodes.length
        allAgendaIdxList.push(agIdx)
        const agLabel = (task.content || `아젠다 ${ti + 1}`).slice(0, 12) + ((task.content || '').length > 12 ? '…' : '')
        nodes.push({
          id: `agenda-${g.id || gi}-${task.id || ti}`, label: agLabel, type: 'agenda',
          x: Math.cos(tAng) * R.agenda, y: Y.agenda, z: Math.sin(tAng) * R.agenda,
          groupIdx: gi, data: task, meetingGroupId: mgNodeId
        })
        edges.push({ from: mgIdx, to: agIdx, rel: 'OWNED_BY' })
        agendaIdxByTodoId.set(String(task.id), agIdx)
      })
    }

    // ── Session 노드: HELD_BY meetingGroup, COVERS agenda ────
    const sessions = g.minutes || []
    const aTotal = allAgendaIdxList.length
    sessions.forEach((m, mi) => {
      const parentAgIdx = aTotal > 0 ? allAgendaIdxList[mi % aTotal] : mgIdx
      const parentNode = nodes[parentAgIdx]
      const pAng = parentNode ? Math.atan2(parentNode.z, parentNode.x) : ang
      const sibCount = sessions.filter((_, j) => (aTotal > 0 ? allAgendaIdxList[j % aTotal] : mgIdx) === parentAgIdx).length
      const sibIdx = sessions.slice(0, mi).filter((_, j) => (aTotal > 0 ? allAgendaIdxList[j % aTotal] : mgIdx) === parentAgIdx).length
      const sFan = sibCount > 1 ? Math.min(0.22, 0.14) : 0
      const sAng = pAng + (sibIdx - (sibCount - 1) / 2) * sFan
      const sIdx = nodes.length
      nodes.push({
        id: `session-${g.id || gi}-${mi}`,
        label: m.session_title || `${m.session_number || mi + 1}차 회의`, type: 'session',
        x: Math.cos(sAng) * R.session, y: Y.session, z: Math.sin(sAng) * R.session,
        groupIdx: gi, data: { ...m, participants: g.members || [] },
        neo4jId: m.id || null,
      })
      // session -[HELD_BY]→ meetingGroup
      edges.push({ from: sIdx, to: mgIdx, rel: 'HELD_BY' })
      // session -[COVERS]→ agenda (순환 배분)
      if (aTotal > 0) edges.push({ from: sIdx, to: allAgendaIdxList[mi % aTotal], rel: 'COVERS' })

      // ── Document 노드 (회의록): session -[PRODUCED]→ document
      const dIdx = nodes.length
      nodes.push({
        id: `file-min-${g.id || gi}-${mi}`,
        label: m.session_title || `${m.session_number || mi + 1}차 회의록`, type: 'file', fileType: '회의록',
        x: Math.cos(sAng) * R.file, y: Y.file, z: Math.sin(sAng) * R.file, groupIdx: gi,
        data: {
          title: m.doc_title || (m.session_title ? m.session_title + ' 회의록' : null),
          doc_type: m.doc_type || '회의록',
          author: m.doc_author,
          created_at: m.doc_created_at || m.ended_at || m.date,
          file_name: m.file_name,
        }
      })
      edges.push({ from: sIdx, to: dIdx, rel: 'PRODUCED' })
    })

    // ── Document 노드 (보고자료): ATTACHED_TO meetingGroup ───
    ;(g.reports || []).forEach((rp, ri) => {
      const relTodoId = String(rp.related_todo_id || '')
      let fromIdx = allAgendaIdxList.length > 0 ? allAgendaIdxList[0] : mgIdx
      if (relTodoId && agendaIdxByTodoId.has(relTodoId)) fromIdx = agendaIdxByTodoId.get(relTodoId)
      const fromNode = nodes[fromIdx]
      const bAng = fromNode ? Math.atan2(fromNode.z, fromNode.x) : ang
      const rAng = bAng + (ri - ((g.reports || []).length - 1) / 2) * 0.12
      const rIdx = nodes.length
      nodes.push({
        id: `file-rep-${g.id || gi}-${ri}`, label: rp.file_name || '보고자료', type: 'file', fileType: '보고자료',
        x: Math.cos(rAng) * R.file, y: Y.file - 15, z: Math.sin(rAng) * R.file, groupIdx: gi,
        data: { ...rp, created_at: rp.submitted_at },
        neo4jId: rp.id || null,
      })
      // document -[ATTACHED_TO]→ meetingGroup
      edges.push({ from: rIdx, to: mgIdx, rel: 'ATTACHED_TO' })
    })
  })

  // ── 소위원회 (MeetingGroup -[PARTICIPATES_IN]→ MeetingGroup) ─
  data.forEach(g => {
    if (!g.parent_id) return
    const rawId = g.id, rawPid = g.parent_id
    const subId = (typeof rawId === 'string' && rawId.includes('-')) ? rawId : `mg-${rawId}`
    const parId = (typeof rawPid === 'string' && rawPid.includes('-')) ? rawPid : `mg-${rawPid}`
    const subIdx = nodes.findIndex(n => n.id === subId)
    const parentIdx = nodes.findIndex(n => n.id === parId)
    if (subIdx >= 0 && parentIdx >= 0)
      edges.push({ from: subIdx, to: parentIdx, rel: 'PARTICIPATES_IN' })
  })

  return { nodes, edges }
}

/** 노드의 논리적 히트 반경 (연결 점 검출에 사용) */
function getNodeHitRadius(n, zf, scale = 1.0) {
  if (n.id === 'org-root')       return Math.min(30, 18 * scale * zf)
  if (n.type === 'meeting_group') return Math.min(36, 22 * scale * zf)
  if (n.type === 'person')        return Math.min(22, 14 * scale * zf)
  return Math.min(28, 18 * scale * zf) // dept, agenda, session, file
}

function initGraph() {
  const canvas = canvasRef.value; if (!canvas) return
  ctx = canvas.getContext('2d')
  resizeCanvas()
  ro = new ResizeObserver(resizeCanvas); ro.observe(canvas)
  animateGraph()
}

function resizeCanvas() {
  const c = canvasRef.value; if (!c) return
  dpr = window.devicePixelRatio || 1
  c.width = c.offsetWidth * dpr; c.height = c.offsetHeight * dpr
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
}

function projectNode(n, w, h) {
  let x=(n.x-camX)*worldZoom, y=(n.y-camY)*worldZoom, z=(n.z-camZ)*worldZoom
  const cosX=Math.cos(rotX),sinX=Math.sin(rotX),cosY=Math.cos(rotY),sinY=Math.sin(rotY)
  const x1=cosY*x+sinY*z,y1=y,z1=-sinY*x+cosY*z
  const x2=x1,y2=cosX*y1-sinX*z1,z2=sinX*y1+cosX*z1
  const fov=600,s=fov/(fov+z2+400)
  return { sx: w/2+x2*s, sy: h/2+y2*s, scale: s, z: z2 }
}

const PALETTE=['#60a5fa','#34d399','#f472b6','#fbbf24','#a78bfa','#fb923c','#38bdf8','#86efac']

function computeUrgency(g) {
  if (g?.urgency) return g.urgency
  const tasks = g?.tasks || []
  const now = new Date(); now.setHours(0,0,0,0)
  let minDays = Infinity
  tasks.forEach(t => {
    if (t.status === 'done') return
    if (!t.due_date) return
    const due = new Date(t.due_date); due.setHours(0,0,0,0)
    const days = Math.ceil((due - now) / 86400000)
    if (days >= 0 && days < minDays) minDays = days
  })
  if (minDays <= 1) return 'critical'   // 하루 이하: 빨간색
  if (minDays <= 3) return 'warning'    // 3일 이하: 노란색
  return 'normal'
}
function getHubFill(g) {
  const u = computeUrgency(g)
  if (u === 'critical') return '#ef4444'
  if (u === 'warning') return '#f59e0b'
  return '#3b82f6'
}
function getVisibleSet() {
  const vis = new Set()
  if (expandedHubIdx === null) {
    // 기본: 본인(충심 person) + 회의체만 표시
    gNodes.forEach((n, i) => { if (n.id === 'org-root' || n.type === 'meeting_group') vis.add(i) })
  } else {
    const hubNode = gNodes[expandedHubIdx]
    if (hubNode?.type === 'meeting_group') {
      // ── 기본: 같은 groupIdx를 가진 노드는 엣지 여부와 무관하게 항상 표시 ──
      // (엣지 삭제 시 노드가 사라지는 문제 방지)
      const hubGroupIdx = hubNode.groupIdx
      gNodes.forEach((n, i) => {
        if (n.groupIdx === hubGroupIdx) {
          if (n.type === 'person') return  // person 노드는 맵에 표시 안 함
          vis.add(i)
        }
      })
      vis.add(expandedHubIdx)
      // org 노드 (PART_OF 관계) 표시
      gEdges.forEach(e => { if (e.from === expandedHubIdx && e.rel === 'PART_OF') vis.add(e.to) })
      // 엣지로만 연결된 추가 노드도 표시 (localAddedEdges로 추가된 크로스-그룹 연결 등)
      gEdges.forEach(e => {
        const fromNode = gNodes[e.from], toNode = gNodes[e.to]
        if (!fromNode || !toNode) return
        if (e.to === expandedHubIdx || e.from === expandedHubIdx) {
          const otherIdx = e.to === expandedHubIdx ? e.from : e.to
          const other = gNodes[otherIdx]
          if (other && other.type !== 'person') vis.add(otherIdx)
        }
      })
    } else {
      gNodes.forEach((n, i) => { if (n.id === 'org-root' || n.type === 'meeting_group') vis.add(i) })
    }
  }
  return vis
}

function roundRect(c,x,y,w,h,r){c.beginPath();c.moveTo(x+r,y);c.lineTo(x+w-r,y);c.quadraticCurveTo(x+w,y,x+w,y+r);c.lineTo(x+w,y+h-r);c.quadraticCurveTo(x+w,y+h,x+w-r,y+h);c.lineTo(x+r,y+h);c.quadraticCurveTo(x,y+h,x,y+h-r);c.lineTo(x,y+r);c.quadraticCurveTo(x,y,x+r,y);c.closePath()}

function getRelatedIndices(mgIdx) {
  const related = new Set([mgIdx])
  gEdges.forEach(e => {
    if (e.from === mgIdx) related.add(e.to)
    if (e.to === mgIdx) related.add(e.from)
  })
  return related
}

function computeTreeLayout(hubIdx, w, h) {
  const naturalPos = new Map()
  const visSet = getVisibleSet()
  const TOP = 60, GAP = 140, PAD = 60

  // ── Neo4j 온톨로지 계층 구조 (타입별 명시적 부모→자식 규칙) ──
  // meetingGroup → dept, agenda, standalone file
  // dept         → person
  // agenda       → session
  // session      → file (PRODUCED)
  const visited = new Set()

  function kids(idx) {
    const node = gNodes[idx]
    if (!node) return []
    const result = []

    if (node.type === 'meeting_group') {
      // dept: dept -[PARTICIPATES_IN]→ mg  (역방향 탐색)
      gEdges.forEach(e => {
        if (e.to === idx && gNodes[e.from]?.type === 'dept' && visSet.has(e.from) && !visited.has(e.from))
          result.push(e.from)
      })
      // agenda: agenda -[OWNED_BY]→ mg  (역방향 탐색)
      gEdges.forEach(e => {
        if (e.to === idx && gNodes[e.from]?.type === 'agenda' && visSet.has(e.from) && !visited.has(e.from))
          result.push(e.from)
      })
      // standalone doc: file -[ATTACHED_TO]→ mg  (역방향 탐색)
      gEdges.forEach(e => {
        if (e.to === idx && gNodes[e.from]?.type === 'file' && visSet.has(e.from) && !visited.has(e.from))
          result.push(e.from)
      })
    } else if (node.type === 'dept') {
      // person: person -[BELONGS_TO]→ dept  (역방향)
      gEdges.forEach(e => {
        if (e.to === idx && gNodes[e.from]?.type === 'person' && visSet.has(e.from) && !visited.has(e.from))
          result.push(e.from)
      })
    } else if (node.type === 'agenda') {
      // session: session -[COVERS]→ agenda  (역방향)
      gEdges.forEach(e => {
        if (e.to === idx && gNodes[e.from]?.type === 'session' && visSet.has(e.from) && !visited.has(e.from))
          result.push(e.from)
      })
    } else if (node.type === 'session') {
      // file: session -[PRODUCED]→ file  (정방향)
      gEdges.forEach(e => {
        if (e.from === idx && gNodes[e.to]?.type === 'file' && visSet.has(e.to) && !visited.has(e.to))
          result.push(e.to)
      })
    }

    return [...new Set(result)]
  }

  const _lc = new Map()
  function leafCount(idx) {
    if (_lc.has(idx)) return _lc.get(idx)
    visited.add(idx)
    const ch = kids(idx)
    const c = ch.length ? ch.reduce((s, ci) => s + leafCount(ci), 0) : 1
    _lc.set(idx, c); return c
  }
  // leafCount 먼저 실행해서 visited 구성
  leafCount(hubIdx)
  visited.clear()

  function placeNatural(idx, cx, y) {
    if (visited.has(idx)) return
    visited.add(idx)
    naturalPos.set(idx, { cx, y })
    const ch = kids(idx)
    if (!ch.length) return
    const total = _lc.get(idx) ?? ch.length
    const spread = Math.min(w - PAD * 2, Math.max(ch.length * 110, total * 110))
    let x = cx - spread / 2
    for (const ci of ch) {
      const frac = (_lc.get(ci) ?? 1) / total
      placeNatural(ci, x + frac * spread / 2, y + GAP)
      x += frac * spread
    }
  }
  placeNatural(hubIdx, w / 2, TOP)
  // Apply zoom (anchored at hub top-center) and pan
  const pos = new Map()
  naturalPos.forEach(({ cx, y }, idx) => {
    pos.set(idx, {
      sx: w/2 + (cx - w/2) * worldZoom + pan2DX,
      sy: TOP  + (y  - TOP) * worldZoom + pan2DY,
    })
  })
  return pos
}

function drawArchiveGraph() {
  const canvas = canvasRef.value; if (!canvas||!ctx) return
  const w=canvas.offsetWidth,h=canvas.offsetHeight
  if(w===0||h===0) return
  ctx.clearRect(0,0,w,h)
  const isDark = nightMode.value
  if(!isDark){ctx.fillStyle='#eef2ff';ctx.fillRect(0,0,w,h)}
  if(!gNodes.length){ctx.fillStyle=isDark?'rgba(148,163,184,.5)':'rgba(100,116,139,.6)';ctx.font='14px sans-serif';ctx.textAlign='center';ctx.fillText('데이터를 불러오는 중...',w/2,h/2);return}
  const visibleSet = getVisibleSet()
  const is2D = expandedHubIdx !== null
  let projected
  if (is2D) {
    _treePositions = computeTreeLayout(expandedHubIdx, w, h)
    if (_node2DOffsets.size > 0) {
      _node2DOffsets.forEach((off, idx) => {
        const tp = _treePositions.get(idx)
        if (tp) _treePositions.set(idx, { sx: tp.sx + off.dx, sy: tp.sy + off.dy })
      })
    }
    projected = gNodes.map((n, i) => {
      const tp = _treePositions.get(i)
      return { sx: tp ? tp.sx : -9999, sy: tp ? tp.sy : -9999, scale: 1.0, z: tp ? tp.sy : 0, node: n, idx: i }
    })
  } else {
    _treePositions = null
    projected = gNodes.map((n,i)=>({...projectNode(n,w,h),node:n,idx:i}))
  }
  const order=projected.slice().sort((a,b)=>a.z-b.z)
  const zf=Math.max(0.6,Math.min(2.5,worldZoom))
  const now = Date.now() / 1000

  // ── 하이라이트 엣지 glow pre-pass (노드보다 먼저 그려서 아래 레이어) ──
  if (queryHlEdgeIdxs.value.size > 0) {
    const tHL = Date.now() / 350
    gEdges.forEach((e, ei) => {
      if (!queryHlEdgeIdxs.value.has(ei)) return
      const { from, to } = e
      if (is2D) { if (!_treePositions?.has(from) || !_treePositions?.has(to)) return }
      else { if (!visibleSet.has(from) || !visibleSet.has(to)) return }
      if (from >= projected.length || to >= projected.length) return
      const pa = projected[from], pb = projected[to]
      const pulse = 0.55 + 0.45 * Math.sin(tHL * 4)
      ctx.save()
      ctx.strokeStyle = `rgba(139,92,246,${0.55 * pulse})`
      ctx.lineWidth = is2D ? 7 : 6
      ctx.lineCap = 'round'
      if (is2D) {
        const midY = (pa.sy + pb.sy) / 2
        ctx.beginPath(); ctx.moveTo(pa.sx, pa.sy)
        ctx.bezierCurveTo(pa.sx, midY, pb.sx, midY, pb.sx, pb.sy); ctx.stroke()
      } else {
        const dx = pb.sx - pa.sx, dy = pb.sy - pa.sy
        const len = Math.sqrt(dx * dx + dy * dy)
        if (len < 8) { ctx.restore(); return }
        const ux = dx / len, uy = dy / len
        const cpBow = Math.min(len * 0.25, 40)
        const cpX = (pa.sx + pb.sx) / 2 - uy * cpBow
        const cpY = (pa.sy + pb.sy) / 2 + ux * cpBow
        ctx.beginPath(); ctx.moveTo(pa.sx + ux * 12, pa.sy + uy * 12)
        ctx.quadraticCurveTo(cpX, cpY, pb.sx - ux * 18, pb.sy - uy * 18); ctx.stroke()
      }
      ctx.restore()
    })
  }

  gEdges.forEach(e => {
    const { from, to, rel } = e
    if (is2D) { if (!_treePositions?.has(from) || !_treePositions?.has(to)) return }
    else { if (!visibleSet.has(from)||!visibleSet.has(to)) return }
    if (from>=projected.length||to>=projected.length) return
    const pa=projected[from], pb=projected[to]
    const relColor = REL_COLORS[rel] || '#60a5fa'
    const isFocused = focusNode!==null&&(focusNode===from||focusNode===to)
    const alpha = is2D ? (isFocused ? 0.85 : 0.55) : (isFocused ? 0.75 : Math.max(0.07, Math.min(0.35,(pa.scale+pb.scale)/2)))
    const lw = isFocused ? 1.8 : (is2D ? 1.2 : 0.9)
    const dx=pb.sx-pa.sx, dy=pb.sy-pa.sy
    const len=Math.sqrt(dx*dx+dy*dy)
    if (len < 8) return
    const ux=dx/len, uy=dy/len
    const as = Math.max(5, 8*Math.min(1.4,(pa.scale+pb.scale)/2)*Math.min(1.5,zf))

    ctx.strokeStyle=hexToRgba(relColor,alpha); ctx.lineWidth=lw

    if (is2D) {
      // ── 2D 트리: 위→아래 S커브 베지어 연결선 (org차트 스타일) ──
      const midY = (pa.sy + pb.sy) / 2
      ctx.beginPath()
      ctx.moveTo(pa.sx, pa.sy)
      ctx.bezierCurveTo(pa.sx, midY, pb.sx, midY, pb.sx, pb.sy)
      ctx.stroke()
      // 화살표: 종점에서 수직으로 내려오는 방향
      const aLen = as
      const tipX = pb.sx, tipY = pb.sy
      const ax = 0, ay = -1  // 아래→위 방향 (끝점에서 역방향)
      const px2 = -ay * aLen * 0.44, py2 = ax * aLen * 0.44
      ctx.beginPath()
      ctx.moveTo(tipX, tipY)
      ctx.lineTo(tipX + ax * (-aLen) + px2, tipY + ay * (-aLen) + py2)
      ctx.lineTo(tipX + ax * (-aLen) - px2, tipY + ay * (-aLen) - py2)
      ctx.closePath(); ctx.fillStyle=hexToRgba(relColor,alpha); ctx.fill()
    } else {
      // ── 3D 글로브: 살짝 휘는 2차 베지어 ──
      const cpBow = Math.min(len * 0.25, 40)
      const cpX = (pa.sx + pb.sx) / 2 - uy * cpBow
      const cpY = (pa.sy + pb.sy) / 2 + ux * cpBow
      const x1=pa.sx+ux*12, y1=pa.sy+uy*12
      const x2=pb.sx-ux*(as+10), y2=pb.sy-uy*(as+10)
      if (Math.sqrt((x2-x1)**2+(y2-y1)**2) < 4) return
      ctx.beginPath(); ctx.moveTo(x1,y1); ctx.quadraticCurveTo(cpX,cpY,x2,y2)
      ctx.stroke()
      // 화살표
      const tipX=x2+ux*as, tipY=y2+uy*as
      const px2=-uy*as*0.44, py2=ux*as*0.44
      ctx.beginPath(); ctx.moveTo(tipX,tipY); ctx.lineTo(x2+px2,y2+py2); ctx.lineTo(x2-px2,y2-py2)
      ctx.closePath(); ctx.fillStyle=hexToRgba(relColor,alpha); ctx.fill()
    }
    // Relation label
    if (rel && len > 42 && zf > 0.85) {
      const lx = is2D ? (pa.sx + pb.sx) / 2 + 6 : (pa.sx+pb.sx)/2-uy*8
      const ly = is2D ? (pa.sy + pb.sy) / 2       : (pa.sy+pb.sy)/2+ux*8
      ctx.font=`${Math.max(7,Math.round(8*Math.min(1.8,zf)))}px sans-serif`
      ctx.textAlign='center'; ctx.textBaseline='middle'
      ctx.fillStyle=hexToRgba(relColor,Math.min(1,alpha+0.35))
      ctx.fillText(rel,lx,ly)
    }
  })
  order.forEach(p=>{
    if(!visibleSet.has(p.idx)) return
    if(is2D && !_treePositions?.has(p.idx)) return
    const n=p.node,isFocused=focusNode===p.idx
    const _htKey = n.id === 'org-root' ? 'org-root' : n.type
    if(hiddenNodeTypes.value.includes(_htKey)) return
    const isEnded=n.data?.status==='ended'
    ctx.globalAlpha=1
    if(n.id === 'org-root'){  // 중심 노드: 사용자 (Person) — 검정 원 + 사람 아이콘
      const r=Math.min(30,(isFocused?22:18)*p.scale*zf)
      ctx.beginPath(); ctx.arc(p.sx,p.sy,r,0,Math.PI*2)
      ctx.fillStyle='#1f2937'; ctx.fill()
      ctx.strokeStyle=selectedNodeIdx.value===p.idx||isFocused?'rgba(255,255,255,0.9)':'rgba(255,255,255,0.35)'
      ctx.lineWidth=selectedNodeIdx.value===p.idx||isFocused?2.5:1.5; ctx.stroke()
      if(p.scale>.22){
        const ic='rgba(255,255,255,0.9)'
        const headR=r*0.22,bodyR=r*0.29,headY=p.sy-r*0.2,bodyY=p.sy+r*0.08
        ctx.fillStyle=ic
        ctx.beginPath(); ctx.arc(p.sx,headY,headR,0,Math.PI*2); ctx.fill()
        ctx.beginPath(); ctx.arc(p.sx,bodyY+bodyR*0.7,bodyR,Math.PI,Math.PI*2); ctx.fill()
      }
      if(p.scale>.3){const fs=Math.max(8,Math.min(13,Math.round(9*zf)));ctx.fillStyle=isDark?'rgba(226,232,240,0.9)':'rgba(15,23,42,0.85)';ctx.font=`bold ${fs}px sans-serif`;ctx.textAlign='center';ctx.textBaseline='top';const nm=n.label||'나';ctx.fillText(nm.length>7?nm.slice(0,6)+'…':nm,p.sx,p.sy+r+3)}
    } else if(n.type==='meeting_group'){
      const hubColor=getHubFill(n.data)
      const urgency=computeUrgency(n.data)
      const r=Math.min(36,(isFocused?26:22)*p.scale*zf)
      // Search highlight ring
      if(searchHitMgIdxs.value.includes(p.idx)){
        const now2=Date.now()/1000;const pulse=0.55+0.3*Math.sin(now2*2.5)
        ctx.beginPath();ctx.arc(p.sx,p.sy,r+8*Math.min(1,zf),0,Math.PI*2)
        ctx.strokeStyle=isDark?`rgba(251,191,36,${pulse})`:`rgba(234,179,8,${pulse})`
        ctx.lineWidth=2.5;ctx.setLineDash([5,3]);ctx.stroke();ctx.setLineDash([])
      }
      if(!isEnded&&urgency==='critical'){const pulse=0.3+0.25*Math.sin(now*3.5);const auraR=r*(1.8+0.4*Math.sin(now*2.2));const ag=ctx.createRadialGradient(p.sx,p.sy,r*.5,p.sx,p.sy,auraR);ag.addColorStop(0,`rgba(239,68,68,${pulse})`);ag.addColorStop(1,'rgba(239,68,68,0)');ctx.beginPath();ctx.arc(p.sx,p.sy,auraR,0,Math.PI*2);ctx.fillStyle=ag;ctx.fill()}
      const grad=ctx.createRadialGradient(p.sx,p.sy,0,p.sx,p.sy,r)
      if(isEnded){grad.addColorStop(0,'rgba(100,116,139,0.45)');grad.addColorStop(1,'rgba(71,85,105,0.2)')}
      else{const rgb=urgency==='critical'?'239,68,68':urgency==='warning'?'245,158,11':'59,130,246';grad.addColorStop(0,`rgba(${rgb},0.9)`);grad.addColorStop(1,`rgba(${rgb},0.4)`)}
      ctx.beginPath();ctx.arc(p.sx,p.sy,r,0,Math.PI*2);ctx.fillStyle=grad;ctx.fill()
      const isHovered=hoverNodeIdx===p.idx
      if(isFocused||selectedNodeIdx.value===p.idx){ctx.strokeStyle=isDark?'#fff':'#1e293b';ctx.lineWidth=2.5;ctx.stroke()}
      else if(isHovered){ctx.strokeStyle=isDark?'rgba(255,255,255,0.9)':'rgba(15,23,42,0.8)';ctx.lineWidth=3;ctx.stroke();ctx.strokeStyle=isDark?'rgba(255,255,255,0.2)':'rgba(15,23,42,0.1)';ctx.lineWidth=6;ctx.stroke()}
      // progress arc
      const ratio=groupTodoRatio.value.get(n.data?.id??n.id)
      if(ratio!=null&&ratio>0){
        const ar=r+3.5*Math.min(1,zf)
        ctx.beginPath();ctx.arc(p.sx,p.sy,ar,-Math.PI/2,-Math.PI/2+ratio*Math.PI*2)
        ctx.strokeStyle=isDark?'rgba(134,239,172,0.85)':'rgba(22,163,74,0.75)'
        ctx.lineWidth=Math.max(1.5,2.5*Math.min(1,zf));ctx.stroke()
      }
      if(p.scale>.28){const fs=Math.max(11,Math.min(20,Math.round(14*zf)));if(isEnded)ctx.fillStyle=isDark?`rgba(148,163,184,${Math.min(1,p.scale*1.4)})`:`rgba(71,85,105,${Math.min(1,p.scale*1.6)})`;else ctx.fillStyle=isDark?`rgba(255,255,255,${Math.min(1,p.scale*1.5)})`:`rgba(30,58,138,${Math.min(1,p.scale*1.8)})`;ctx.font=`bold ${fs}px sans-serif`;ctx.textAlign='center';ctx.textBaseline='middle';ctx.fillText(n.label.length>7?n.label.slice(0,6)+'…':n.label,p.sx,p.sy)}
    } else if(n.type==='agenda'){  // amber 원 + 체크마크 아이콘
      const r=Math.min(28,(isFocused?22:18)*p.scale*zf)
      ctx.beginPath(); ctx.arc(p.sx,p.sy,r,0,Math.PI*2); ctx.fillStyle='#f59e0b'; ctx.fill()
      if(isFocused||selectedNodeIdx.value===p.idx){ctx.strokeStyle='rgba(255,255,255,0.9)';ctx.lineWidth=2;ctx.stroke()}
      if(p.scale>.2){
        ctx.save(); ctx.strokeStyle='rgba(255,255,255,0.92)'; ctx.lineWidth=Math.max(1.5,r*0.14)
        ctx.lineCap='round'; ctx.lineJoin='round'
        const cs=r*0.52
        ctx.beginPath(); ctx.moveTo(p.sx-cs,p.sy+cs*0.1); ctx.lineTo(p.sx-cs*0.18,p.sy+cs*0.78); ctx.lineTo(p.sx+cs,p.sy-cs*0.62)
        ctx.stroke(); ctx.restore()
      }
      if(p.scale>.25){const fs=Math.max(9,Math.min(14,Math.round(11*zf)));ctx.fillStyle=isDark?'rgba(226,232,240,0.9)':'rgba(15,23,42,0.85)';ctx.font=`${fs}px sans-serif`;ctx.textAlign='center';ctx.textBaseline='top';ctx.fillText(n.label.length>10?n.label.slice(0,9)+'…':n.label,p.sx,p.sy+r+3)}
    } else if(n.type==='person'){
      const r=Math.min(22,(isFocused?18:14)*p.scale*zf)
      ctx.beginPath();ctx.arc(p.sx,p.sy,r,0,Math.PI*2)
      ctx.fillStyle='#f472b6'; ctx.fill()
      if(p.scale>.25){const fs=Math.max(8,Math.min(12,Math.round(10*zf)));ctx.fillStyle=isDark?'rgba(226,232,240,0.9)':'rgba(15,23,42,0.85)';ctx.font=`${fs}px sans-serif`;ctx.textAlign='center';ctx.textBaseline='top';ctx.fillText(n.label.length>6?n.label.slice(0,5)+'…':n.label,p.sx,p.sy+r+3)}
    } else if(n.type==='session'){  // coral 원 + 캘린더 아이콘
      const r=Math.min(28,(isFocused?22:18)*p.scale*zf)
      ctx.beginPath(); ctx.arc(p.sx,p.sy,r,0,Math.PI*2); ctx.fillStyle='#f97316'; ctx.fill()
      if(isFocused||selectedNodeIdx.value===p.idx){ctx.strokeStyle='rgba(255,255,255,0.9)';ctx.lineWidth=2;ctx.stroke()}
      if(p.scale>.2){
        ctx.save(); ctx.strokeStyle='rgba(255,255,255,0.92)'; ctx.fillStyle='rgba(255,255,255,0.92)'
        const cw=r*0.68,ch=r*0.6,cx=p.sx-cw/2,cy=p.sy-ch/2+r*0.06
        ctx.lineWidth=Math.max(1,r*0.09); ctx.strokeRect(cx,cy,cw,ch)
        ctx.beginPath(); ctx.moveTo(cx,cy+ch*0.33); ctx.lineTo(cx+cw,cy+ch*0.33); ctx.stroke()
        const clipR=r*0.09
        ctx.beginPath(); ctx.arc(cx+cw*0.28,cy-clipR*0.3,clipR,0,Math.PI*2); ctx.fill()
        ctx.beginPath(); ctx.arc(cx+cw*0.72,cy-clipR*0.3,clipR,0,Math.PI*2); ctx.fill()
        ctx.fillRect(cx+cw*0.52,cy+ch*0.5,cw*0.33,ch*0.33)
        ctx.restore()
      }
      if(p.scale>.25&&zf>.5){const fs=Math.max(9,Math.min(14,Math.round(11*zf)));ctx.fillStyle=isDark?'rgba(226,232,240,0.9)':'rgba(15,23,42,0.85)';ctx.font=`${fs}px sans-serif`;ctx.textAlign='center';ctx.textBaseline='top';ctx.fillText(n.label.length>10?n.label.slice(0,9)+'…':n.label,p.sx,p.sy+r+3)}
    } else if(n.type==='file'){  // gray 원 + 접힌 문서 아이콘
      const r=Math.min(22,(isFocused?17:14)*p.scale*zf)
      ctx.beginPath(); ctx.arc(p.sx,p.sy,r,0,Math.PI*2); ctx.fillStyle='#64748b'; ctx.fill()
      if(isFocused||selectedNodeIdx.value===p.idx){ctx.strokeStyle='rgba(255,255,255,0.9)';ctx.lineWidth=2;ctx.stroke()}
      if(p.scale>.2){
        ctx.save(); ctx.strokeStyle='rgba(255,255,255,0.9)'; ctx.fillStyle='rgba(255,255,255,0.9)'
        const fw=r*0.5,fh=r*0.62,fx=p.sx-fw/2,fy=p.sy-fh/2,fold=fw*0.3
        ctx.lineWidth=Math.max(1,r*0.08)
        ctx.beginPath(); ctx.moveTo(fx,fy); ctx.lineTo(fx+fw-fold,fy); ctx.lineTo(fx+fw,fy+fold); ctx.lineTo(fx+fw,fy+fh); ctx.lineTo(fx,fy+fh); ctx.closePath(); ctx.stroke()
        ctx.beginPath(); ctx.moveTo(fx+fw-fold,fy); ctx.lineTo(fx+fw-fold,fy+fold); ctx.lineTo(fx+fw,fy+fold); ctx.stroke()
        ctx.lineWidth=Math.max(0.8,r*0.07)
        ctx.beginPath(); ctx.moveTo(fx+fw*0.2,fy+fh*0.54); ctx.lineTo(fx+fw*0.82,fy+fh*0.54); ctx.stroke()
        ctx.beginPath(); ctx.moveTo(fx+fw*0.2,fy+fh*0.74); ctx.lineTo(fx+fw*0.68,fy+fh*0.74); ctx.stroke()
        ctx.restore()
      }
      if(p.scale>.25&&zf>.5){const fs=Math.max(9,Math.min(14,Math.round(11*zf)));ctx.fillStyle=isDark?'rgba(226,232,240,0.9)':'rgba(15,23,42,0.85)';ctx.font=`${fs}px sans-serif`;ctx.textAlign='center';ctx.textBaseline='top';ctx.fillText(n.label.length>10?n.label.slice(0,9)+'…':n.label,p.sx,p.sy+r+3)}
    } else if(n.type==='dept'){  // purple 원 + 두 명 그룹 아이콘
      const isExpanded=expandedDeptIdx===p.idx
      const r=Math.min(28,(isFocused||isExpanded?22:18)*p.scale*zf)
      ctx.beginPath(); ctx.arc(p.sx,p.sy,r,0,Math.PI*2); ctx.fillStyle='#8b5cf6'; ctx.fill()
      if(isFocused||selectedNodeIdx.value===p.idx||isExpanded){ctx.strokeStyle='rgba(255,255,255,0.9)';ctx.lineWidth=2;ctx.stroke()}
      if(p.scale>.2){
        ctx.save(); ctx.fillStyle='rgba(255,255,255,0.92)'
        // 왼쪽 작은 사람
        const shr=r*0.13,sbr=r*0.16,shx=p.sx-r*0.24,shy=p.sy-r*0.14
        ctx.beginPath(); ctx.arc(shx,shy,shr,0,Math.PI*2); ctx.fill()
        ctx.beginPath(); ctx.arc(shx,shy+shr+sbr*1.1,sbr,Math.PI,Math.PI*2); ctx.fill()
        // 오른쪽 큰 사람
        const bhr=r*0.18,bbr=r*0.22,bhx=p.sx+r*0.2,bhy=p.sy-r*0.17
        ctx.beginPath(); ctx.arc(bhx,bhy,bhr,0,Math.PI*2); ctx.fill()
        ctx.beginPath(); ctx.arc(bhx,bhy+bhr+bbr*1.1,bbr,Math.PI,Math.PI*2); ctx.fill()
        ctx.restore()
      }
      if(p.scale>.25){const fs=Math.max(9,Math.min(14,Math.round(11*zf)));ctx.fillStyle=isDark?'rgba(226,232,240,0.9)':'rgba(15,23,42,0.85)';ctx.font=`${fs}px sans-serif`;ctx.textAlign='center';ctx.textBaseline='top';ctx.fillText(n.label.length>8?n.label.slice(0,7)+'…':n.label,p.sx,p.sy+r+3)}
    } else if(n.type==='org'&&n.id!=='org-root'){  // teal 원 + 건물 아이콘
      const r=Math.min(26,(isFocused?20:17)*p.scale*zf)
      ctx.beginPath(); ctx.arc(p.sx,p.sy,r,0,Math.PI*2); ctx.fillStyle='#0d9488'; ctx.fill()
      if(isFocused||selectedNodeIdx.value===p.idx){ctx.strokeStyle='rgba(255,255,255,0.9)';ctx.lineWidth=2;ctx.stroke()}
      if(p.scale>.25){const fs=Math.max(8,Math.min(13,Math.round(10*zf)));ctx.fillStyle=isDark?'rgba(226,232,240,0.9)':'rgba(15,23,42,0.85)';ctx.font=`${fs}px sans-serif`;ctx.textAlign='center';ctx.textBaseline='top';ctx.fillText(n.label.length>9?n.label.slice(0,8)+'…':n.label,p.sx,p.sy+r+3)}
    }
    ctx.globalAlpha=1
  })

  // ── Neo4j query highlight rings (챗봇 그래프 탐색 시각화) ─────
  if (queryHlIdxs.value.size > 0) {
    const t = Date.now() / 350
    queryHlIdxs.value.forEach(idx => {
      if (!visibleSet.has(idx)) return
      const pp = projected[idx]
      if (!pp) return
      const sx = pp.sx, sy = pp.sy
      const nr = getNodeHitRadius(pp.node, zf, pp.scale || 1)
      ctx.save()
      // 1번 파동 — 빠른 확산
      const phase = (t % 1.0)
      const scanR  = nr * (1 + phase * 3.0)
      const scanA  = (1 - phase) * 0.85
      ctx.beginPath(); ctx.arc(sx, sy, scanR, 0, Math.PI * 2)
      ctx.strokeStyle = `rgba(99,102,241,${scanA})`
      ctx.lineWidth = 3.5; ctx.stroke()
      // 2번 파동 — 0.4 위상 차
      const phase2 = ((t + 0.4) % 1.0)
      const scanR2 = nr * (1 + phase2 * 3.0)
      const scanA2 = (1 - phase2) * 0.6
      ctx.beginPath(); ctx.arc(sx, sy, scanR2, 0, Math.PI * 2)
      ctx.strokeStyle = `rgba(139,92,246,${scanA2})`
      ctx.lineWidth = 2.5; ctx.stroke()
      // 3번 파동 — 0.7 위상 차
      const phase3 = ((t + 0.7) % 1.0)
      const scanR3 = nr * (1 + phase3 * 3.0)
      const scanA3 = (1 - phase3) * 0.35
      ctx.beginPath(); ctx.arc(sx, sy, scanR3, 0, Math.PI * 2)
      ctx.strokeStyle = `rgba(167,139,250,${scanA3})`
      ctx.lineWidth = 2; ctx.stroke()
      // 고정 내부 링 — 밝고 두꺼운 테두리
      const pulse = 0.7 + 0.3 * Math.sin(t * 6)
      ctx.beginPath(); ctx.arc(sx, sy, nr + 5, 0, Math.PI * 2)
      ctx.strokeStyle = `rgba(199,170,255,${pulse})`
      ctx.lineWidth = 3.5; ctx.stroke()
      // 노드 중심 glow fill
      const grad = ctx.createRadialGradient(sx, sy, 0, sx, sy, nr)
      grad.addColorStop(0, `rgba(139,92,246,${0.22 * pulse})`)
      grad.addColorStop(1, 'rgba(139,92,246,0)')
      ctx.beginPath(); ctx.arc(sx, sy, nr, 0, Math.PI * 2)
      ctx.fillStyle = grad; ctx.fill()
      ctx.restore()
    })
  }

  // ── Connection dot (node-edge hover indicator) ────────────────
  if (connDotNodeIdx >= 0 && !connDragging.value) {
    const t = Date.now() / 280
    const pulse = 0.65 + 0.35 * Math.sin(t)
    ctx.save()
    // outer glow ring
    ctx.beginPath(); ctx.arc(connDotSx, connDotSy, 11, 0, Math.PI * 2)
    ctx.strokeStyle = `rgba(52,211,153,${pulse * 0.38})`
    ctx.lineWidth = 2.5; ctx.stroke()
    // inner filled dot
    ctx.beginPath(); ctx.arc(connDotSx, connDotSy, 6, 0, Math.PI * 2)
    ctx.fillStyle = `rgba(52,211,153,${pulse})`
    ctx.fill()
    ctx.beginPath(); ctx.arc(connDotSx, connDotSy, 6, 0, Math.PI * 2)
    ctx.strokeStyle = 'rgba(255,255,255,0.7)'; ctx.lineWidth = 1.5; ctx.stroke()
    ctx.restore()
  }

  // ── Connection drag preview (dashed line + arrowhead + target ring) ─
  if (connDragging.value) {
    const fsx = connDragFromSx, fsy = connDragFromSy
    const tsx = connDragCurSx, tsy = connDragCurSy
    const dx = tsx - fsx, dy = tsy - fsy
    const len = Math.sqrt(dx * dx + dy * dy)
    ctx.save()
    // animated dashed line
    const dashOffset = -(Date.now() / 50) % 14
    ctx.setLineDash([8, 5]); ctx.lineDashOffset = dashOffset
    ctx.strokeStyle = 'rgba(52,211,153,0.88)'; ctx.lineWidth = 2.2
    ctx.beginPath(); ctx.moveTo(fsx, fsy); ctx.lineTo(tsx, tsy); ctx.stroke()
    ctx.setLineDash([]); ctx.lineDashOffset = 0
    // arrowhead at cursor end
    if (len > 24) {
      const ux = dx / len, uy = dy / len, as = 11
      ctx.beginPath()
      ctx.moveTo(tsx, tsy)
      ctx.lineTo(tsx - ux * as - uy * as * 0.44, tsy - uy * as + ux * as * 0.44)
      ctx.lineTo(tsx - ux * as + uy * as * 0.44, tsy - uy * as - ux * as * 0.44)
      ctx.closePath()
      ctx.fillStyle = 'rgba(52,211,153,0.92)'; ctx.fill()
    }
    // source node dot
    ctx.beginPath(); ctx.arc(fsx, fsy, 6, 0, Math.PI * 2)
    ctx.fillStyle = 'rgba(52,211,153,0.95)'; ctx.fill()
    ctx.beginPath(); ctx.arc(fsx, fsy, 6, 0, Math.PI * 2)
    ctx.strokeStyle = 'rgba(255,255,255,0.75)'; ctx.lineWidth = 1.5; ctx.stroke()
    // target highlight ring
    if (connDragTargetIdx >= 0) {
      let tgtSx, tgtSy
      if (_treePositions?.has(connDragTargetIdx)) {
        const tp = _treePositions.get(connDragTargetIdx); tgtSx = tp.sx; tgtSy = tp.sy
      } else {
        const p = projectNode(gNodes[connDragTargetIdx], w, h); tgtSx = p.sx; tgtSy = p.sy
      }
      const tPulse = 0.4 + 0.4 * Math.sin(Date.now() / 180)
      ctx.beginPath(); ctx.arc(tgtSx, tgtSy, 32, 0, Math.PI * 2)
      ctx.strokeStyle = `rgba(52,211,153,${tPulse})`
      ctx.lineWidth = 2.8; ctx.setLineDash([5, 3]); ctx.stroke(); ctx.setLineDash([])
    }
    ctx.restore()
  }
}

// ── CONSTELLATION FUNCTIONS ─────────────────────────────────
function buildConstPositions() {
  const canvas = constCanvasRef.value
  const w = canvas ? canvas.offsetWidth : 900
  const h = canvas ? canvas.offsetHeight : 600
  const cx = w / 2, cy = h / 2
  if (!gNodes.length) { cPos = []; return }
  // meeting_group 인덱스 맵 (groupIdx → nodeIdx)
  const mgByGroup = new Map()
  gNodes.forEach((n, i) => { if (n.type === 'meeting_group') mgByGroup.set(n.groupIdx ?? i, i) })
  const mgList = [...mgByGroup.values()]
  const mgCount = mgList.length
  const radius = Math.min(w, h) * 0.30
  // 1st pass: MG 노드 원형 배치
  cPos = gNodes.map(() => ({ x: cx, y: cy }))
  mgList.forEach((idx, gi) => {
    const ang = (gi / Math.max(mgCount, 1)) * Math.PI * 2 - Math.PI / 2
    cPos[idx] = { x: cx + Math.cos(ang) * radius, y: cy + Math.sin(ang) * radius }
  })
  // 2nd pass: 세부 노드는 부모 MG 주위에 파이토탁시스 배치
  const placed = new Map()
  gNodes.forEach((n, i) => {
    if (n.type === 'meeting_group' || n.id === 'org-root' || n.id === 'org-node') return
    const mgIdx = mgByGroup.get(n.groupIdx)
    if (mgIdx === undefined) return
    const cnt = placed.get(mgIdx) || 0
    placed.set(mgIdx, cnt + 1)
    const goldenAng = cnt * 2.399963
    const r = 22 + 9 * Math.sqrt(cnt)
    cPos[i] = {
      x: cPos[mgIdx].x + Math.cos(goldenAng) * r,
      y: cPos[mgIdx].y + Math.sin(goldenAng) * r,
    }
  })
  // org-root 중앙
  const orgIdx = gNodes.findIndex(n => n.id === 'org-root')
  if (orgIdx >= 0) cPos[orgIdx] = { x: cx, y: cy }
}

function initConstellation() {
  const canvas = constCanvasRef.value; if (!canvas) return
  constCtx = canvas.getContext('2d')
  resizeConstCanvas()
  if (constRo) constRo.disconnect()
  constRo = new ResizeObserver(() => { resizeConstCanvas(); buildConstPositions() })
  constRo.observe(canvas)
  constScale = 1; constTargetScale = 1
  constCamX = 0; constCamY = 0; constTargetCamX = 0; constTargetCamY = 0
  constSelMgIdx.value = null
  buildConstPositions()
  if (constAnimId) cancelAnimationFrame(constAnimId)
  constAnimId = requestAnimationFrame(animateConst)
}

function stopConstellation() {
  if (constAnimId) { cancelAnimationFrame(constAnimId); constAnimId = null }
  if (constRo) { constRo.disconnect(); constRo = null }
}

function resizeConstCanvas() {
  const c = constCanvasRef.value; if (!c || !constCtx) return
  const dpr2 = window.devicePixelRatio || 1
  c.width = c.offsetWidth * dpr2; c.height = c.offsetHeight * dpr2
  constCtx.setTransform(dpr2, 0, 0, dpr2, 0, 0)
}

function animateConst() {
  constCamX   += (constTargetCamX   - constCamX)   * 0.09
  constCamY   += (constTargetCamY   - constCamY)   * 0.09
  constScale  += (constTargetScale  - constScale)   * 0.09
  drawConstellation()
  constAnimId = requestAnimationFrame(animateConst)
}

function drawConstellation() {
  const canvas = constCanvasRef.value; if (!canvas || !constCtx) return
  const w = canvas.offsetWidth, h = canvas.offsetHeight
  if (!w || !h || !cPos.length) return
  constCtx.clearRect(0, 0, w, h)
  const isDark = nightMode.value
  // 배경: 별자리 느낌의 짙은 배경
  constCtx.fillStyle = isDark ? '#080f1e' : '#e8eeff'
  constCtx.fillRect(0, 0, w, h)
  // 배경에 작은 별 점들
  if (isDark) {
    constCtx.fillStyle = 'rgba(255,255,255,0.25)'
    for (let i = 0; i < 120; i++) {
      const hx = ((i * 7919) % w), hy = ((i * 6271) % h)
      constCtx.beginPath(); constCtx.arc(hx, hy, 0.6, 0, Math.PI*2); constCtx.fill()
    }
  }
  if (!gNodes.length) return
  const sel = constSelMgIdx.value
  const zf = constScale
  const toS = (px, py) => ({ sx: w/2 + (px - constCamX) * zf, sy: h/2 + (py - constCamY) * zf })
  // 선택된 MG의 groupIdx
  const selGroup = sel !== null ? (gNodes[sel]?.groupIdx ?? null) : null

  // ── 엣지 ────────────────────────────────────────────────────
  gEdges.forEach(e => {
    const pA = cPos[e.from], pB = cPos[e.to]
    const nA = gNodes[e.from], nB = gNodes[e.to]
    if (!pA || !pB || !nA || !nB) return
    if (nA.id === 'org-node' || nB.id === 'org-node') return
    if (nA.id === 'org-root' || nB.id === 'org-root') return
    const a = toS(pA.x, pA.y), b = toS(pB.x, pB.y)
    let alpha = isDark ? 0.18 : 0.14
    if (sel !== null) {
      const aRel = nA.type === 'meeting_group' ? e.from === sel : nA.groupIdx === selGroup
      const bRel = nB.type === 'meeting_group' ? e.to === sel : nB.groupIdx === selGroup
      alpha = (aRel && bRel) ? (isDark ? 0.55 : 0.45) : (isDark ? 0.05 : 0.04)
    }
    constCtx.save()
    constCtx.strokeStyle = isDark ? `rgba(148,163,184,${alpha})` : `rgba(100,116,139,${alpha})`
    constCtx.lineWidth = 0.7
    constCtx.beginPath(); constCtx.moveTo(a.sx, a.sy); constCtx.lineTo(b.sx, b.sy); constCtx.stroke()
    constCtx.restore()
  })

  // ── 세부 노드 ────────────────────────────────────────────────
  gNodes.forEach((n, i) => {
    if (n.type === 'meeting_group' || n.id === 'org-root' || n.id === 'org-node') return
    const pos = cPos[i]; if (!pos) return
    const s = toS(pos.x, pos.y)
    const isRelated = sel === null ? false : (n.groupIdx === selGroup)
    const showDetail = isRelated && zf > 0.8
    let alpha = sel === null ? 0.55 : (isRelated ? 1.0 : 0.18)
    const r = showDetail ? Math.min(14, 11 * zf) : 4
    const color = { dept:'#8b5cf6', agenda:'#f59e0b', session:'#f97316', file:'#64748b', person:'#f472b6' }[n.type] || '#60a5fa'
    constCtx.save()
    constCtx.globalAlpha = alpha
    constCtx.beginPath(); constCtx.arc(s.sx, s.sy, r, 0, Math.PI*2)
    constCtx.fillStyle = color; constCtx.fill()
    if (showDetail) {
      _constDrawIcon(n, s.sx, s.sy, r)
      const fs = Math.max(9, Math.round(10 * Math.min(1.5, zf)))
      constCtx.fillStyle = isDark ? 'rgba(226,232,240,0.9)' : 'rgba(15,23,42,0.85)'
      constCtx.font = `${fs}px sans-serif`
      constCtx.textAlign = 'center'; constCtx.textBaseline = 'top'
      constCtx.fillText((n.label||'').slice(0,9), s.sx, s.sy + r + 3)
    }
    constCtx.restore()
  })

  // ── MG 노드 ─────────────────────────────────────────────────
  gNodes.forEach((n, i) => {
    if (n.type !== 'meeting_group') return
    const pos = cPos[i]; if (!pos) return
    const s = toS(pos.x, pos.y)
    const isSel = sel === i
    const alpha = sel === null ? 1.0 : (isSel ? 1.0 : 0.3)
    const r = isSel ? 30 * Math.min(1.5, zf) : 22
    const hubColor = getHubFill(n.data)
    constCtx.save()
    constCtx.globalAlpha = alpha
    // 선택된 노드 glow
    if (isSel) {
      const glow = constCtx.createRadialGradient(s.sx, s.sy, r*0.4, s.sx, s.sy, r*3)
      glow.addColorStop(0, 'rgba(59,130,246,0.28)'); glow.addColorStop(1, 'rgba(59,130,246,0)')
      constCtx.beginPath(); constCtx.arc(s.sx, s.sy, r*3, 0, Math.PI*2)
      constCtx.fillStyle = glow; constCtx.fill()
    }
    const grad = constCtx.createRadialGradient(s.sx, s.sy, 0, s.sx, s.sy, r)
    grad.addColorStop(0, hubColor + 'ee'); grad.addColorStop(1, hubColor + '66')
    constCtx.beginPath(); constCtx.arc(s.sx, s.sy, r, 0, Math.PI*2)
    constCtx.fillStyle = grad; constCtx.fill()
    if (isSel) { constCtx.strokeStyle = isDark ? '#fff' : '#1e293b'; constCtx.lineWidth = 2.5; constCtx.stroke() }
    // 라벨
    const fs = Math.max(10, Math.round(12 * Math.min(1.4, zf)))
    constCtx.fillStyle = isDark ? 'rgba(255,255,255,0.95)' : 'rgba(30,58,138,0.95)'
    constCtx.font = `bold ${fs}px sans-serif`
    constCtx.textAlign = 'center'; constCtx.textBaseline = 'middle'
    constCtx.fillText((n.label||'').slice(0,7), s.sx, s.sy)
    constCtx.restore()
  })

  // org-root (나)
  const orgIdx = gNodes.findIndex(n => n.id === 'org-root')
  if (orgIdx >= 0 && cPos[orgIdx]) {
    const s = toS(cPos[orgIdx].x, cPos[orgIdx].y)
    constCtx.save()
    constCtx.globalAlpha = sel === null ? 0.9 : 0.35
    constCtx.beginPath(); constCtx.arc(s.sx, s.sy, 14, 0, Math.PI*2)
    constCtx.fillStyle = '#1f2937'; constCtx.fill()
    constCtx.strokeStyle = 'rgba(255,255,255,0.35)'; constCtx.lineWidth = 1.5; constCtx.stroke()
    constCtx.restore()
  }
}

function _constDrawIcon(n, sx, sy, r) {
  constCtx.save()
  constCtx.strokeStyle = 'rgba(255,255,255,0.92)'; constCtx.fillStyle = 'rgba(255,255,255,0.92)'
  constCtx.lineWidth = Math.max(1, r*0.12); constCtx.lineCap = 'round'; constCtx.lineJoin = 'round'
  if (n.type === 'agenda') {
    const cs = r*0.5
    constCtx.beginPath(); constCtx.moveTo(sx-cs,sy+cs*0.1); constCtx.lineTo(sx-cs*0.18,sy+cs*0.78); constCtx.lineTo(sx+cs,sy-cs*0.62); constCtx.stroke()
  } else if (n.type === 'session') {
    const cw=r*0.68,ch=r*0.6,cx2=sx-cw/2,cy2=sy-ch/2+r*0.06,fold=cw*0.22
    constCtx.strokeRect(cx2,cy2,cw,ch)
    constCtx.beginPath(); constCtx.moveTo(cx2,cy2+ch*0.33); constCtx.lineTo(cx2+cw,cy2+ch*0.33); constCtx.stroke()
    constCtx.beginPath(); constCtx.arc(cx2+cw*0.28,cy2-fold*0.3,fold*0.4,0,Math.PI*2); constCtx.fill()
    constCtx.beginPath(); constCtx.arc(cx2+cw*0.72,cy2-fold*0.3,fold*0.4,0,Math.PI*2); constCtx.fill()
  } else if (n.type === 'file') {
    const fw=r*0.5,fh=r*0.62,fx=sx-fw/2,fy=sy-fh/2,fold=fw*0.3
    constCtx.beginPath(); constCtx.moveTo(fx,fy); constCtx.lineTo(fx+fw-fold,fy); constCtx.lineTo(fx+fw,fy+fold); constCtx.lineTo(fx+fw,fy+fh); constCtx.lineTo(fx,fy+fh); constCtx.closePath(); constCtx.stroke()
  } else if (n.type === 'dept') {
    const shx=sx-r*0.24,shy=sy-r*0.14,shr=r*0.13,sbr=r*0.16
    constCtx.beginPath(); constCtx.arc(shx,shy,shr,0,Math.PI*2); constCtx.fill()
    constCtx.beginPath(); constCtx.arc(shx,shy+shr+sbr*1.1,sbr,Math.PI,Math.PI*2); constCtx.fill()
    const bhx=sx+r*0.2,bhy=sy-r*0.17,bhr=r*0.18,bbr=r*0.22
    constCtx.beginPath(); constCtx.arc(bhx,bhy,bhr,0,Math.PI*2); constCtx.fill()
    constCtx.beginPath(); constCtx.arc(bhx,bhy+bhr+bbr*1.1,bbr,Math.PI,Math.PI*2); constCtx.fill()
  }
  constCtx.restore()
}

function onConstCanvasClick(e) {
  if (constDragMoved) return
  const canvas = constCanvasRef.value; if (!canvas) return
  const rect = canvas.getBoundingClientRect()
  const mx = e.clientX - rect.left, my = e.clientY - rect.top
  const w = canvas.offsetWidth, h = canvas.offsetHeight
  let hitIdx = null, minDist = Infinity
  gNodes.forEach((n, i) => {
    if (n.type !== 'meeting_group') return
    const pos = cPos[i]; if (!pos) return
    const sx = w/2 + (pos.x - constCamX) * constScale
    const sy = h/2 + (pos.y - constCamY) * constScale
    const r = (constSelMgIdx.value === i ? 30 * Math.min(1.5, constScale) : 22) + 8
    const d = Math.hypot(sx - mx, sy - my)
    if (d <= r && d < minDist) { minDist = d; hitIdx = i }
  })
  if (hitIdx !== null) {
    if (constSelMgIdx.value === hitIdx) {
      constSelMgIdx.value = null
      constTargetScale = 1; constTargetCamX = 0; constTargetCamY = 0
    } else {
      constSelMgIdx.value = hitIdx
      constTargetCamX = cPos[hitIdx].x; constTargetCamY = cPos[hitIdx].y
      constTargetScale = 2.4
    }
  } else {
    constSelMgIdx.value = null
    constTargetScale = 1; constTargetCamX = 0; constTargetCamY = 0
  }
}

function onConstMouseDown(e) { constDragging=true; constDragMoved=false; constLastMx=e.clientX; constLastMy=e.clientY }
function onConstMouseMove(e) {
  if (!constDragging) return
  const dx=e.clientX-constLastMx, dy=e.clientY-constLastMy
  if (Math.abs(dx)+Math.abs(dy) > 3) constDragMoved = true
  constTargetCamX -= dx/constScale; constCamX -= dx/constScale
  constTargetCamY -= dy/constScale; constCamY -= dy/constScale
  constLastMx=e.clientX; constLastMy=e.clientY
}
function onConstMouseUp() { constDragging=false }
function onConstWheel(e) {
  e.preventDefault()
  constTargetScale = Math.max(0.3, Math.min(6, constTargetScale * (e.deltaY < 0 ? 1.12 : 0.88)))
}
function onConstResetView() {
  constSelMgIdx.value = null; constTargetScale=1; constTargetCamX=0; constTargetCamY=0
}
// END CONSTELLATION FUNCTIONS

function animateGraph() {
  if(expandedHubIdx === null && autoRotate && !rotationPaused) rotY+=.002
  camX+=(targetCamX-camX)*.05;camY+=(targetCamY-camY)*.05;camZ+=(targetCamZ-camZ)*.05
  worldZoom+=(targetZoom-worldZoom)*.1
  pan2DX+=(targetPan2DX-pan2DX)*.12;pan2DY+=(targetPan2DY-pan2DY)*.12
  drawArchiveGraph()
  animId=requestAnimationFrame(animateGraph)
}

// ─── Mouse ────────────────────────────────────────────────────
function onMouseDown(e) {
  // float 드래그 중에는 canvas mousedown 무시 — onGlobalMouseUp에서만 처리
  if (floatDragging.value) return
  // ── Connection dot drag: start drawing a new edge ───────────────
  if (connDotNodeIdx >= 0 && !floatDragging.value) {
    connDragging.value = true
    connDragFromIdx = connDotNodeIdx
    connDragFromSx = connDotSx; connDragFromSy = connDotSy
    const canvas = canvasRef.value
    if (canvas) {
      const rect = canvas.getBoundingClientRect()
      connDragCurSx = e.clientX - rect.left
      connDragCurSy = e.clientY - rect.top
    }
    connDragTargetIdx = -1
    connDotNodeIdx = -1; connDotVisible.value = false
    e.preventDefault(); return
  }
  if (expandedHubIdx !== null && !isPanMode.value && _treePositions) {
    const canvas = canvasRef.value
    if (canvas) {
      const rect = canvas.getBoundingClientRect()
      const mx = e.clientX - rect.left, my = e.clientY - rect.top
      const zf = Math.max(.6, Math.min(2.5, worldZoom))
      let hitNode = null, minDist = Infinity
      _treePositions.forEach((tp, idx) => {
        const n = gNodes[idx]
        if (!n || n.type === 'meeting_group') return
        const d = Math.hypot(tp.sx - mx, tp.sy - my)
        const baseR = n.type==='org'?22:n.type==='dept'?18:22
        if (d < baseR * zf + 10 && d < minDist) { minDist = d; hitNode = idx }
      })
      if (hitNode !== null) {
        dragNode2D = hitNode; dragNode2DMoved = false
        lastMx = e.clientX; lastMy = e.clientY
        e.preventDefault(); return
      }
    }
  }
  isDragging=true;autoRotate=false;lastMx=e.clientX;lastMy=e.clientY
  if(isPanMode.value) e.preventDefault()
}

function onMouseMove(e) {
  if (bottomResizing) return
  if (dragNode2D !== null) {
    const dx = e.clientX - lastMx, dy = e.clientY - lastMy
    const cur = _node2DOffsets.get(dragNode2D) || { dx: 0, dy: 0 }
    _node2DOffsets.set(dragNode2D, { dx: cur.dx + dx, dy: cur.dy + dy })
    lastMx = e.clientX; lastMy = e.clientY
    dragNode2DMoved = true
    return
  }
  if(isDragging){
    const dx=e.clientX-lastMx, dy=e.clientY-lastMy
    if(expandedHubIdx !== null) {
      // 2D tree mode: always pan
      targetPan2DX += dx; pan2DX += dx
      targetPan2DY += dy; pan2DY += dy
    } else if(isPanMode.value){
      const canvas=canvasRef.value
      const fovScale = 600 / (600 + 400)
      const panScale = 1 / (fovScale * worldZoom)
      targetCamX -= dx * panScale
      targetCamY -= dy * panScale
    } else {
      rotY+=dx*.004;rotX+=dy*.004
      rotX=Math.max(-1.2,Math.min(1.2,rotX))
    }
    lastMx=e.clientX;lastMy=e.clientY
    if(hoverNode.value){hoverNode.value=null}
    hoverNodeIdx=-1
    return
  }
  // ── Connection drag in progress ────────────────────────────
  if (connDragging.value) {
    const canvas = canvasRef.value; if (!canvas) return
    const rect = canvas.getBoundingClientRect()
    connDragCurSx = e.clientX - rect.left
    connDragCurSy = e.clientY - rect.top
    const w = canvas.offsetWidth, h = canvas.offsetHeight
    const zf = Math.max(.6, Math.min(2.5, worldZoom))
    const vis = getVisibleSet()
    let tIdx = -1, tDist = Infinity
    gNodes.forEach((n, i) => {
      if (i === connDragFromIdx) return
      if (!vis.has(i)) return
      let sx, sy
      if (_treePositions?.has(i)) { const tp = _treePositions.get(i); sx = tp.sx; sy = tp.sy }
      else if (expandedHubIdx === null) { const p = projectNode(n, w, h); sx = p.sx; sy = p.sy }
      else return
      const d = Math.hypot(sx - connDragCurSx, sy - connDragCurSy)
      const nr = getNodeHitRadius(n, zf)
      if (d <= nr + 28 && d < tDist) { tDist = d; tIdx = i }
    })
    connDragTargetIdx = tIdx
    return
  }
  if(viewMode.value!=='graph') return
  const canvas=canvasRef.value;if(!canvas) return
  const rect=canvas.getBoundingClientRect()
  const mx=e.clientX-rect.left,my=e.clientY-rect.top
  if(mx<0||my<0||mx>canvas.offsetWidth||my>canvas.offsetHeight){hoverNode.value=null;hoverNodeIdx=-1;connDotNodeIdx=-1;connDotVisible.value=false;return}
  const w=canvas.offsetWidth,h=canvas.offsetHeight
  let closest=null,minDist=Infinity
  const hoverVis = getVisibleSet()
  const zf=Math.max(.6,Math.min(2.5,worldZoom))
  gNodes.forEach((n,i)=>{
    if(!['meeting_group','dept','org','agenda','person','session','file','decision'].includes(n.type)) return
    if(!hoverVis.has(i)) return
    let sx, sy
    if(_treePositions?.has(i)) {
      const tp = _treePositions.get(i); sx = tp.sx; sy = tp.sy
    } else if(expandedHubIdx === null) {
      const p = projectNode(n,w,h); sx = p.sx; sy = p.sy
    } else return
    const d=Math.hypot(sx-mx,sy-my)
    if(d<30*zf+10&&d<minDist){minDist=d;closest=i}
  })
  hoverNodeIdx = closest !== null ? closest : -1
  hoverNode.value = closest !== null ? gNodes[closest] : null
  // ── Connection dot: detect edge zone ────────────────────────────
  if (!floatDragging.value) {
    const DOT_ZONE = 16 // px beyond node radius
    let newDotIdx = -1, newDotSx = 0, newDotSy = 0, minEdgeDist = Infinity
    gNodes.forEach((n, i) => {
      if (!hoverVis.has(i)) return
      let sx, sy, scale = 1.0
      if (_treePositions?.has(i)) { const tp = _treePositions.get(i); sx = tp.sx; sy = tp.sy }
      else if (expandedHubIdx === null) { const p = projectNode(n, w, h); sx = p.sx; sy = p.sy; scale = p.scale }
      else return
      const d = Math.hypot(sx - mx, sy - my)
      const nr = getNodeHitRadius(n, zf, scale)
      const edgeDist = d - nr
      if (edgeDist >= -4 && edgeDist <= DOT_ZONE && edgeDist < minEdgeDist) {
        minEdgeDist = edgeDist
        newDotIdx = i
        const angle = Math.atan2(my - sy, mx - sx)
        newDotSx = sx + Math.max(nr, 12) * Math.cos(angle)
        newDotSy = sy + Math.max(nr, 12) * Math.sin(angle)
      }
    })
    connDotNodeIdx = newDotIdx
    connDotSx = newDotSx; connDotSy = newDotSy
    connDotVisible.value = newDotIdx >= 0
  } else {
    connDotNodeIdx = -1; connDotVisible.value = false
  }
}

function onMouseUp() {
  // ── Complete connection drag ────────────────────────────────
  if (connDragging.value) {
    if (connDragTargetIdx >= 0 && connDragTargetIdx !== connDragFromIdx) {
      const already = gEdges.some(e =>
        (e.from === connDragFromIdx && e.to === connDragTargetIdx) ||
        (e.from === connDragTargetIdx && e.to === connDragFromIdx)
      )
      if (already) {
        showMapToast('이미 연결된 노드입니다.')
      } else {
        const fromNode = gNodes[connDragFromIdx]
        const toNode   = gNodes[connDragTargetIdx]
        const { rel, neo4jFromId, neo4jToId } = resolveRel(connDragFromIdx, connDragTargetIdx)
        gEdges.push({ from: connDragFromIdx, to: connDragTargetIdx, rel })
        graphVersion.value++
        showMapToast(`${fromNode?.label} → ${toNode?.label} (${rel})`)
        // ── Neo4j 영속화 ─────────────────────────────────────────
        if (neo4jFromId && neo4jToId) {
          apiAI.post('/api/neo4j/relationships', {
            from_id: neo4jFromId,
            rel_type: rel,
            to_id: neo4jToId,
          }).catch(err => {
            console.warn('[Neo4j] 관계 저장 실패:', err?.response?.data?.detail || err.message)
            showMapToast('Neo4j 저장 실패 (로컬에는 반영됨)')
          })
        }
      }
    }
    connDragging.value = false; connDragFromIdx = -1; connDragTargetIdx = -1
    return
  }
  isDragging=false; dragNode2D=null
}

function onMouseLeave() {
  if (connDragging.value) {
    connDragging.value = false; connDragFromIdx = -1; connDragTargetIdx = -1
  }
  connDotNodeIdx = -1; connDotVisible.value = false
  isDragging=false; dragNode2D=null
  hoverNode.value=null
  hoverNodeIdx=-1
}

function onWheel(e) {
  e.preventDefault()
  targetZoom=Math.max(.25,Math.min(4,targetZoom+(e.deltaY<0?.12:-.12)))
}
onWheel._t=null

function onCanvasClick(e) {
  if(isDragging) return
  if(dragNode2DMoved) { dragNode2DMoved=false; return }
  if(isPanMode.value) return  // 패닝 모드일 때 노드 클릭 무시
  const canvas=canvasRef.value;if(!canvas) return
  const rect=canvas.getBoundingClientRect()
  const mx=e.clientX-rect.left,my=e.clientY-rect.top
  const w=canvas.offsetWidth,h=canvas.offsetHeight
  const visSet = getVisibleSet()
  let closest=null,minDist=Infinity
  const zf=Math.max(.6,Math.min(2.5,worldZoom))
  gNodes.forEach((n,i)=>{
    if(!visSet.has(i)) return
    let sx, sy
    if(_treePositions?.has(i)) {
      const tp = _treePositions.get(i); sx = tp.sx; sy = tp.sy
    } else {
      const p = projectNode(n,w,h); sx = p.sx; sy = p.sy
    }
    const baseR=n.type==='meeting_group'?22:n.type==='org'?20:n.type==='dept'?14:n.type==='agenda'?13:n.type==='person'?11:n.type==='session'?12:10
    const d=Math.hypot(sx-mx,sy-my)
    if(d<baseR*zf+6&&d<minDist){minDist=d;closest=i}
  })
  if(closest!==null){
    const n=gNodes[closest]
    if(n.type==='meeting_group') {
      if(selectedNodeIdx.value===closest) {
        // 선택 해제: 전체 맵으로 복귀
        selectedNodeIdx.value=null; expandedHubIdx=null; expandedDeptIdx=null; focusNode=null
        _node2DOffsets.clear()
        targetZoom=1.0
        targetCamX=0;targetCamY=0;targetCamZ=0
        targetPan2DX=0;targetPan2DY=0;pan2DX=0;pan2DY=0
        breadcrumb.value=[]
      } else {
        selectedNodeIdx.value=closest; expandedHubIdx=closest; expandedDeptIdx=null
        targetZoom=1.0;targetCamX=0;targetCamY=0;targetCamZ=0
        targetPan2DX=0;targetPan2DY=0;pan2DX=0;pan2DY=0
        breadcrumb.value=[{ label: n.label, idx: closest, type: 'meeting_group' }]
        focusNode=closest
        openDetail(n.data)
      }
    } else if(n.type==='dept') {
      expandedDeptIdx = expandedDeptIdx===closest ? null : closest
      if(expandedDeptIdx!==null) {
        const hubEntry = breadcrumb.value.find(b=>b.type==='meeting_group')
        breadcrumb.value = hubEntry ? [hubEntry,{label:n.label,idx:closest,type:'dept'}] : [{label:n.label,idx:closest,type:'dept'}]
      } else {
        breadcrumb.value = breadcrumb.value.filter(b=>b.type!=='dept')
      }
      openNodeDetail(n)
      focusNode=closest
    } else if(n.type==='file') {
      openFileReview(n)
      openNodeDetail(n)
      focusNode=closest
    } else {
      openNodeDetail(n)
      focusNode=closest
    }
  } else {
    // 배경 클릭: 아무것도 하지 않음
  }
}



function onTouchStart(e){isDragging=true;autoRotate=false;lastMx=e.touches[0].clientX;lastMy=e.touches[0].clientY}
function onTouchMove(e){if(!isDragging)return;rotY+=(e.touches[0].clientX-lastMx)*.004;rotX+=(e.touches[0].clientY-lastMy)*.004;rotX=Math.max(-1.2,Math.min(1.2,rotX));lastMx=e.touches[0].clientX;lastMy=e.touches[0].clientY}
function onTouchEnd(){isDragging=false}

function onBreadcrumbReset() {
  breadcrumb.value = []; selectedNodeIdx.value = null
  expandedHubIdx = null; expandedDeptIdx = null
  _node2DOffsets.clear()
  targetCamX = 0; targetCamY = 0; targetCamZ = 0
  targetZoom = 1.0
  targetPan2DX=0;targetPan2DY=0;pan2DX=0;pan2DY=0
}

function onBreadcrumbClick(item, index) {
  breadcrumb.value = breadcrumb.value.slice(0, index + 1)
  if(item.type === 'meeting_group') {
    selectedNodeIdx.value = item.idx; expandedHubIdx = item.idx; expandedDeptIdx = null
    targetZoom = 1.0; targetCamX=0; targetCamY=0; targetCamZ=0
    targetPan2DX=0;targetPan2DY=0;pan2DX=0;pan2DY=0
  } else if(item.type === 'dept') {
    expandedDeptIdx = item.idx
  }
}

// ─── Lifecycle ─────────────────────────────────────────────────
onMounted(async () => {
  await nextTick()
  initAgentGreeting('hyean')
  window.addEventListener('mousemove', onGlobalMouseMove)
  window.addEventListener('mouseup', onGlobalMouseUp)
  try {
    await meetingsStore.fetchMeetings()
  } catch(e) {
    console.error('meetings fetch error', e)
  }
  try {
    // ── Neo4j 그래프 데이터 (단일 소스) ──────────────────────────
    const neo4jResult = await apiAI.get('/api/neo4j/archive')
    currentPerson.value = neo4jResult?.data?.current_person || null
    currentOrg.value = neo4jResult?.data?.org || null
    if (!neo4jResult?.data?.meetings?.length) {
      // 회의체 없음 — 본인 노드만 그래프에 표시 (에러 아님)
      return
    }
    neo4jMeetings.value = neo4jResult.data.meetings
    neo4jDepts.value    = neo4jResult.data.departments || []
    minutes.value = neo4jResult.data.minutes || []
    reports.value = neo4jResult.data.reports || []
    membersData.value = neo4jResult.data.meetings.flatMap(m => m.members || [])
    tasksData.value = neo4jResult.data.meetings.flatMap(m => m.tasks   || [])
  } catch(e) {
    console.error('archive fetch error', e)
    // 연결 실패 시에도 본인 노드는 표시 (currentPerson은 auth store에서 fallback)
  } finally {
    loading.value = false
    const g = buildGraphNodes(); gNodes = g.nodes; gEdges = _applyLocalEdgeOverrides(g.nodes, g.edges)
    initGraph()
    buildConstPositions()
  }
})

onBeforeUnmount(()=>{
  cancelAnimationFrame(animId);ro?.disconnect()
  window.removeEventListener('mousemove', onGlobalMouseMove)
  window.removeEventListener('mouseup', onGlobalMouseUp)
})

// ── archive 데이터 재로드 헬퍼 (CRUD 후 호출) ─────────────────
async function refreshArchive() {
  try {
    const res = await apiAI.get('/api/neo4j/archive')
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
      gNodes = g.nodes; gEdges = _applyLocalEdgeOverrides(g.nodes, g.edges)
      buildConstPositions()
      initGraph()  // 캔버스 시각 즉시 반영
    }
  } catch(e) { console.error('archive refresh error', e) }
}

// Rebuild graph when new meetings are created
watch(() => meetingsStore.meetings.length, () => {
  if (loading.value) return  // 초기 로딩 중에는 무시 — finally에서 한 번만 빌드
  const g = buildGraphNodes()
  if (g.nodes.length === 0 && gNodes.length > 0) return  // 빈 데이터로 기존 그래프 지우지 않음
  gNodes = g.nodes; gEdges = _applyLocalEdgeOverrides(g.nodes, g.edges)
  buildConstPositions()
})

// Neo4j 데이터 로드 완료 시 그래프 재빌드
watch(() => neo4jMeetings.value.length, () => {
  if (loading.value) return
  const g = buildGraphNodes()
  if (g.nodes.length === 0 && gNodes.length > 0) return  // 빈 데이터로 기존 그래프 지우지 않음
  gNodes = g.nodes; gEdges = _applyLocalEdgeOverrides(g.nodes, g.edges)
  buildConstPositions()
})

watch(search, q=>{
  if(!q){focusNode=null;searchHitMgIdxs.value=[];targetCamX=0;targetCamY=0;targetCamZ=0;return}
  const lower=q.toLowerCase()
  let bestIdx=null,bestScore=-1
  // compute which meeting_group nodes contain matching sub-nodes
  const hitMgs=new Set()
  gNodes.forEach((n,i)=>{
    let score=n.label.toLowerCase().includes(lower)?(n.type==='meeting_group'?10:5):0
    if(score>bestScore){bestScore=score;bestIdx=i}
    if(n.type!=='meeting_group'&&n.label.toLowerCase().includes(lower)){
      const mgEdge=gEdges.find(e=>e.to===i&&gNodes[e.from]?.type==='meeting_group')
      if(mgEdge)hitMgs.add(mgEdge.from)
      else if(n.meetingGroupId){const mi=gNodes.findIndex(nd=>nd.id===n.meetingGroupId);if(mi>=0)hitMgs.add(mi)}
    }
  })
  searchHitMgIdxs.value=[...hitMgs]
  if(bestIdx!==null&&bestScore>0){
    focusNode=bestIdx;const n=gNodes[bestIdx]
    targetCamX=n.x*.55;targetCamY=n.y*.55;targetCamZ=n.z*.55;autoRotate=false
  }
})

// ─── Helpers ──────────────────────────────────────────────────
function formatDate(d){if(!d)return'-';return new Date(d).toLocaleDateString('ko-KR',{year:'numeric',month:'short',day:'numeric'})}
function downloadDummy(name){alert(`"${name}" 다운로드 기능은 준비 중입니다.`)}
const TYPES=['Draft','In Progress','Done','Pending']
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
        <button class="app-tab" :class="{ active: viewMode==='constellation' }" @click="viewMode='constellation'">
          <svg width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><circle cx="12" cy="3" r="1.5"/><circle cx="3" cy="19" r="1.5"/><circle cx="21" cy="19" r="1.5"/><circle cx="17" cy="8" r="1.5"/><circle cx="7" cy="14" r="1.5"/><line x1="12" y1="4.5" x2="17" y2="8"/><line x1="17" y1="8" x2="21" y2="19"/><line x1="7" y1="14" x2="3" y2="19"/><line x1="7" y1="14" x2="12" y2="4.5"/><line x1="7" y1="14" x2="17" y2="8"/></svg>
          별자리
        </button>
      </div>

      <button class="agent-header-btn" :class="{ active: agentSidebarOpen }" @click="agentSidebarOpen=!agentSidebarOpen" title="AI 에이전트">
        <svg class="ai-btn-icon" viewBox="0 0 40 20" xmlns="http://www.w3.org/2000/svg">
          <defs>
            <linearGradient id="aiGrad" x1="0%" y1="0%" x2="100%" y2="100%">
              <stop offset="0%" stop-color="#93c5fd"/>
              <stop offset="100%" stop-color="#7b80cc"/>
            </linearGradient>
          </defs>
          <text x="20" y="15" text-anchor="middle" font-family="'SF Pro Display',system-ui,sans-serif" font-weight="800" font-size="15" fill="url(#aiGrad)" letter-spacing="-0.5">AI</text>
        </svg>
        <span class="ai-btn-label">채팅</span>
      </button>
    </div>

    <!-- ── Graph Breadcrumb ── -->
    <div v-if="viewMode==='graph'" class="graph-breadcrumb">
      <button class="bc-home" @click="onBreadcrumbReset">
        <svg width="12" height="12" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M3 12L12 4l9 8"/><path d="M9 21V12h6v9"/></svg>
        전체
      </button>
      <template v-for="(item, i) in breadcrumb" :key="i">
        <span class="bc-sep">›</span>
        <button class="bc-item" :class="'bc-'+item.type" @click="onBreadcrumbClick(item, i)">{{ item.label }}</button>
      </template>
    </div>

    <!-- ── Body ── -->
    <div class="archive-body">

      <!-- Main area -->
      <div ref="mainAreaRef" class="main-area">

        <!-- Detail sidebar (absolute overlay, canvas 크기 불변) -->
        <Transition name="sidebar-slide">
          <div v-if="detailOpen" class="detail-sidebar" :style="{ width: sidebarW+'px' }">
          <div class="sidebar-resize-handle" @mousedown="onSidebarResizeStart"></div>

          <!-- ── Header: meeting_group ── -->
          <template v-if="detailMeeting">
          <div class="detail-header">
            <div class="detail-header-icon">
              <svg width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M17 21v-2a4 4 0 00-4-4H5a4 4 0 00-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 00-3-3.87M16 3.13a4 4 0 010 7.75"/></svg>
            </div>
            <div class="detail-header-left">
              <div class="detail-name-badge-row">
                <div class="detail-meeting-name">{{ detailMeeting?.title }}</div>
                <div class="detail-role-badge" :class="isDetailAdmin ? 'role-admin' : 'role-presenter'">{{ isDetailAdmin ? '간사' : '참여자' }}</div>
              </div>
              <div class="detail-meta-row">
                <span class="detail-meta">{{ detailMeeting?.members?.length||0 }}명</span>
                <span class="detail-meta-dot">·</span>
                <span class="detail-meta">{{ (detailMeeting?.minutes?.length||0)+(detailMeeting?.reports?.length||0) }}건</span>
                <template v-if="detailMeeting?.meeting_type">
                  <span class="detail-meta-dot">·</span>
                  <span class="detail-meta">{{ detailMeeting.meeting_type }}</span>
                </template>
              </div>
            </div>
            <div class="detail-header-actions">
              <button v-if="isDetailAdmin" class="detail-icon-btn" @click="openGroupSetting" title="회의체 설정 (간사만 가능)">
                <svg width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M12 15a3 3 0 100-6 3 3 0 000 6z"/><path d="M19.4 15a1.65 1.65 0 00.33 1.82l.06.06a2 2 0 010 2.83 2 2 0 01-2.83 0l-.06-.06a1.65 1.65 0 00-1.82-.33 1.65 1.65 0 00-1 1.51V21a2 2 0 01-2 2 2 2 0 01-2-2v-.09A1.65 1.65 0 009 19.4a1.65 1.65 0 00-1.82.33l-.06.06a2 2 0 01-2.83 0 2 2 0 010-2.83l.06-.06A1.65 1.65 0 004.68 15a1.65 1.65 0 00-1.51-1H3a2 2 0 01-2-2 2 2 0 012-2h.09A1.65 1.65 0 004.6 9a1.65 1.65 0 00-.33-1.82l-.06-.06a2 2 0 010-2.83 2 2 0 012.83 0l.06.06A1.65 1.65 0 009 4.68a1.65 1.65 0 001-1.51V3a2 2 0 012-2 2 2 0 012 2v.09a1.65 1.65 0 001 1.51 1.65 1.65 0 001.82-.33l.06-.06a2 2 0 012.83 0 2 2 0 010 2.83l-.06.06A1.65 1.65 0 0019.4 9a1.65 1.65 0 001.51 1H21a2 2 0 012 2 2 2 0 01-2 2h-.09a1.65 1.65 0 00-1.51 1z"/></svg>
              </button>
            </div>
          </div>

          <!-- 탭 -->
          <div class="detail-tabs">
            <button class="detail-tab" :class="{ active: detailTab==='basic' }" @click="detailTab='basic'">기본</button>
            <button class="detail-tab" :class="{ active: detailTab==='task' }" @click="detailTab='task'">과제</button>
            <button v-if="showExtractFlow" class="detail-tab detail-tab-extract" :class="{ active: detailTab==='extract' }" @click="detailTab='extract'">과제추출</button>
            <button class="detail-tab" :class="{ active: detailTab==='rel' }" @click="detailTab='rel'">관계</button>
          </div>

          <div class="detail-body">

            <!-- ── 기본 탭 ── -->
            <template v-if="detailTab==='basic'">

            <!-- 소개 -->
            <div v-if="detailMeeting?.purpose || detailMeeting?.description" class="detail-section">
              <div class="detail-section-label">소개</div>
              <div class="detail-purpose">{{ detailMeeting.purpose || detailMeeting.description }}</div>
            </div>

            <!-- 간사 + 참여부서 -->
            <div class="detail-section" style="gap:7px">
              <SidebarInfoRow label="간사" :value="detailMeeting?.members?.find(mb => mb.role === 'admin')?.userName || detailMeeting?.members?.find(mb => mb.role === 'admin')?.name || '-'" />
              <SidebarInfoRow label="참여부서" :value="[...new Set((detailMeeting?.members||[]).map(mb => mb.department||mb.dept||'').filter(Boolean))].join(' · ') || '-'" />
              <SidebarInfoRow label="최종 보고일">
                <div style="display:flex;align-items:center;gap:4px;flex-wrap:nowrap;overflow:hidden">
                  <template v-if="detailDday !== null">
                    <span class="dday-date" style="white-space:nowrap">{{ detailEndDateFormatted }}</span>
                    <span class="dday-badge" :class="detailDday <= 0 ? 'dday-over' : detailDday <= 1 ? 'dday-critical' : detailDday <= 3 ? 'dday-warning' : 'dday-normal'" style="white-space:nowrap">{{ detailDday <= 0 ? '마감 초과' : `D-${detailDday}` }}</span>
                  </template>
                  <span v-else class="dday-label" style="font-size:10px;white-space:nowrap">미지정</span>
                </div>
              </SidebarInfoRow>
            </div>

            <!-- 팀 제출 현황 -->
            <div class="detail-section">
              <div class="detail-section-label-row">
                <span class="detail-section-label">팀 제출 현황</span>
                <span class="dept-submit-summary">
                  <span class="dss-done">{{ detailDeptStatus.filter(d=>d.submitted).length }}팀 완료</span>
                  <template v-if="detailDeptStatus.filter(d=>!d.submitted).length">
                    <span class="dss-sep">·</span>
                    <span class="dss-pending">{{ detailDeptStatus.filter(d=>!d.submitted).length }}팀 미제출</span>
                  </template>
                </span>
              </div>
              <template v-if="detailDeptStatus.length">
                <div class="dept-submit-list">
                  <div v-for="ds in detailDeptStatus" :key="ds.dept" class="dept-submit-item" :class="{ 'dsi-done': ds.submitted, 'dsi-pending': !ds.submitted, 'dsi-urgent': !ds.submitted && ds.minDays !== null && ds.minDays <= 3 }">
                    <div class="dsi-dot" :class="{ 'dsi-dot-done': ds.submitted, 'dsi-dot-pending': !ds.submitted, 'dsi-dot-urgent': !ds.submitted && ds.minDays !== null && ds.minDays <= 3 }"></div>
                    <span class="dsi-name">{{ ds.dept }}</span>
                    <template v-if="ds.submitted">
                      <span class="dsi-status dsi-status-done">제출 완료</span>
                    </template>
                    <template v-else>
                      <span class="dsi-status dsi-status-pending">미제출 {{ ds.pendingCount }}건</span>
                      <span v-if="ds.minDays !== null" class="dsi-deadline" :class="{ 'dsi-deadline-urgent': ds.minDays <= 3, 'dsi-deadline-critical': ds.minDays <= 1 }">
                        {{ ds.minDays <= 0 ? '마감초과' : `D-${ds.minDays}` }}
                      </span>
                    </template>
                  </div>
                </div>
              </template>
              <div v-else class="detail-log-empty">참여 부서 정보가 없습니다.</div>
            </div>

            <!-- 최근 로그 -->
            <div class="detail-section">
              <div class="detail-section-label-row">
                <span class="detail-section-label">최근 로그</span>
                <button v-if="(groupHistoryMap.get(detailMeeting?.id)||[]).length > 3" class="detail-more-btn" @click="goToList(detailMeeting?.id)">전체 {{ (groupHistoryMap.get(detailMeeting?.id)||[]).length }}건 →</button>
              </div>
              <div class="detail-log-list">
                <template v-if="(groupHistoryMap.get(detailMeeting?.id)||[]).length">
                  <div v-for="(item, i) in (groupHistoryMap.get(detailMeeting?.id)||[]).slice(0,3)" :key="i" class="detail-log-item">
                    <span class="detail-log-dot" :class="'ht-'+item.type"></span>
                    <div class="detail-log-content">
                      <div class="detail-log-desc">{{ item.desc }}</div>
                      <div class="detail-log-meta">{{ item.manager }} · {{ formatDate(item.date) }}</div>
                    </div>
                  </div>
                </template>
                <div v-else class="detail-log-empty">기록된 로그가 없습니다.</div>
              </div>
            </div>

            </template><!-- /기본 탭 -->

            <!-- ── 과제 탭 ── -->
            <template v-if="detailTab==='task'">

                <!-- 등록된 과제 목록 (맨 위) -->
                <div class="detail-section">
                  <div class="detail-section-label-row">
                    <span class="detail-section-label">등록된 과제</span>
                    <span class="detail-section-label" style="font-weight:400">{{ detailTodos.length }}건</span>
                  </div>
                  <div v-if="!detailTodos.length" class="detail-log-empty">등록된 과제가 없습니다.</div>
                  <template v-else>
                    <div v-for="(todos, dept) in groupedTodos" :key="dept" class="todo-dept-group">
                      <div class="todo-dept-header">
                        <span class="todo-dept-name">{{ dept || '미배정' }}</span>
                        <span class="todo-dept-count">{{ todos.length }}건</span>
                      </div>
                      <div class="detail-todo-list">
                        <div v-for="todo in todos" :key="todo.id||todo.content" class="detail-todo-item">
                          <div class="detail-todo-status" :class="{
                            'ts-done': todo.status==='done',
                            'ts-progress': todo.status==='in_progress',
                            'ts-risk': todo.status==='at_risk',
                            'ts-pending': !todo.status||todo.status==='pending'
                          }">
                            {{ todo.status==='done' ? '완료' : todo.status==='in_progress' ? '진행' : todo.status==='at_risk' ? '위험' : '대기' }}
                          </div>
                          <div class="detail-todo-info">
                            <div class="detail-todo-title">{{ todo.content }}</div>
                            <div class="detail-todo-meta">
                              <span v-if="todo.assignee_name||todo.assignee">{{ todo.assignee_name||todo.assignee }}</span>
                              <span v-if="todo.due_date"> · {{ formatDate(todo.due_date) }}</span>
                            </div>
                          </div>
                        </div>
                      </div>
                    </div>
                  </template>
                </div>

                <!-- AI 과제 추출 실행 버튼 -->
                <button class="ctx-run-btn" @click="showExtractFlow=true; detailTab='extract'">
                  <svg width="12" height="12" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24"><path d="M4 4l16 8-16 8V4z"/></svg>
                  AI 과제 추출 실행
                </button>

            </template><!-- /과제 탭 -->

            <!-- ── 과제추출 탭 ── -->
            <template v-if="detailTab==='extract'">

                <!-- 프로세스 인디케이터 -->
                <div class="task-process-bar">
                  <ProcessStepBar
                    :steps="['자료선정', '추출', '배정']"
                    :current-step="extractPhase==='context' ? 0 : extractPhase==='result' ? 1 : 2"
                    @step-click="i => goToProcessStep(i===0 ? 'context' : 'result')"
                  />
                </div>

                <!-- 자료선정 단계 -->
                <template v-if="extractPhase==='context'">
                  <div class="ctx-section">
                    <div class="detail-section-label ctx-section-title-flex">
                      <svg width="11" height="11" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M15.172 7l-6.586 6.586a2 2 0 102.828 2.828l6.414-6.586a4 4 0 00-5.656-5.656l-6.415 6.585a6 6 0 108.486 8.486L20.5 13"/></svg>
                      추가 자료 선택
                    </div>
                    <!-- 기존 자료 목록: 실제 파일이 있는 항목만 표시 -->
                    <div class="ctx-file-list">
                      <label v-for="r in (detailMeeting?.reports||[]).filter(r=>r.file_name||r.file_url)" :key="'r'+r.id" class="ctx-file-item">
                        <input type="checkbox" :value="r.id" v-model="selectedFiles" class="ctx-checkbox" />
                        <svg width="10" height="10" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M9 17v-2m3 2v-4m3 4v-6m2 10H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"/></svg>
                        <span class="ctx-file-name">{{ r.file_name }}</span>
                        <span class="ctx-file-date">{{ r.submitted_at ? formatDate(r.submitted_at) : '' }}</span>
                      </label>
                      <label v-for="f in (detailMeeting?.files||[]).filter(f=>f.file_name||f.name||f.file_url)" :key="'f'+f.id" class="ctx-file-item">
                        <input type="checkbox" :value="f.id" v-model="selectedFiles" class="ctx-checkbox" />
                        <svg width="10" height="10" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M15.172 7l-6.586 6.586a2 2 0 102.828 2.828l6.414-6.585a4 4 0 00-5.656-5.656l-6.415 6.585a6 6 0 108.486 8.486L20.5 13"/></svg>
                        <span class="ctx-file-name">{{ f.file_name || f.name }}</span>
                      </label>
                      <!-- 새로 업로드된 파일 -->
                      <div v-for="(uf, i) in uploadedCtxFiles" :key="'uf'+i" class="ctx-file-item ctx-file-uploaded">
                        <input type="checkbox" :value="'upload_'+i" v-model="selectedFiles" class="ctx-checkbox" checked />
                        <svg width="10" height="10" fill="none" stroke="#10b981" stroke-width="2" viewBox="0 0 24 24"><path d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"/></svg>
                        <span class="ctx-file-name">{{ uf.name }}</span>
                        <span class="ctx-file-date ctx-new-tag">새 파일</span>
                        <button class="ctx-file-remove" @click.prevent="uploadedCtxFiles.splice(i,1)">×</button>
                      </div>
                    </div>
                    <!-- 파일 업로드 영역 -->
                    <FileUploadArea multiple @change="onCtxFilesAdded" />
                  </div>

                  <div class="ctx-section">
                    <div class="detail-section-label ctx-section-title-flex">
                      <svg width="11" height="11" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M13 10V3L4 14h7v7l9-11h-7z"/></svg>
                      유사 문서 추천
                    </div>
                    <div class="ctx-file-list">
                      <label class="ctx-file-item">
                        <input type="checkbox" v-model="selectedSimilarDocs" value="sim_1" class="ctx-checkbox" />
                        <svg width="10" height="10" fill="none" stroke="#a78bfa" stroke-width="2" viewBox="0 0 24 24"><path d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"/></svg>
                        <span class="ctx-file-name">운영위원회 회의록 3월</span>
                        <span class="ctx-sim-score">유사도 87%</span>
                      </label>
                      <label class="ctx-file-item">
                        <input type="checkbox" v-model="selectedSimilarDocs" value="sim_2" class="ctx-checkbox" />
                        <svg width="10" height="10" fill="none" stroke="#a78bfa" stroke-width="2" viewBox="0 0 24 24"><path d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"/></svg>
                        <span class="ctx-file-name">2025_전략보고서.pdf</span>
                        <span class="ctx-sim-score">유사도 79%</span>
                      </label>
                    </div>
                  </div>

                  <button class="ctx-run-btn" @click="runExtract">
                    <svg width="12" height="12" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24"><path d="M4 4l16 8-16 8V4z"/></svg>
                    과제 추출하기
                  </button>
                </template><!-- /자료선정 단계 -->

                <!-- 추출·배정 단계 -->
                <template v-if="extractPhase==='result' || extractPhase==='assign'">

                  <template v-if="extractPhase==='result'">
                    <div v-if="extractLoading" class="detail-extract-loading"><div class="gm-spinner"></div><span>AI가 분석 중입니다...</span></div>
                    <template v-else-if="extractResult.length">
                      <div class="detail-extract-meta">AI가 {{ extractResult.length }}개 과제를 추천했습니다.</div>
                      <div class="detail-extract-list">
                        <div v-for="(ag, i) in extractResult" :key="i" class="detail-extract-item" :class="{ 'ei-approved': ag._state==='approved', 'ei-rejected': ag._state==='rejected' }">
                          <div class="dei-num">{{ i+1 }}</div>
                          <div class="dei-body">
                            <template v-if="!ag._editing">
                              <div class="dei-title">{{ ag.title }}</div>
                              <ul class="dei-bullets"><li v-for="(b, bi) in ag.bullets" :key="bi">{{ b }}</li></ul>
                            </template>
                            <template v-else>
                              <input class="dei-input" v-model="ag._editTitle" placeholder="과제 제목" />
                              <textarea class="dei-textarea" v-model="ag._editBullets" placeholder="세부 내용" rows="3"></textarea>
                            </template>
                          </div>
                          <div class="dei-actions">
                            <template v-if="!ag._editing">
                              <button class="gm-ei-btn gm-ei-edit" @click="ag._editing=true"><svg width="10" height="10" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M11 4H4a2 2 0 00-2 2v14a2 2 0 002 2h14a2 2 0 002-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 013 3L12 15l-4 1 1-4 9.5-9.5z"/></svg></button>
                              <button class="gm-ei-btn" :class="ag._state==='approved' ? 'gm-ei-approved-active' : 'gm-ei-approve'" @click="setExtractState(i,'approved')"><svg width="10" height="10" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24"><path d="M20 6L9 17l-5-5"/></svg></button>
                              <button class="gm-ei-btn" :class="ag._state==='rejected' ? 'gm-ei-rejected-active' : 'gm-ei-reject'" @click="setExtractState(i,'rejected')"><svg width="10" height="10" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24"><path d="M18 6L6 18M6 6l12 12"/></svg></button>
                            </template>
                            <template v-else>
                              <button class="gm-ei-btn gm-ei-save" @click="ag.title=ag._editTitle; ag._editing=false; ag._state='approved'"><svg width="10" height="10" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24"><path d="M20 6L9 17l-5-5"/></svg></button>
                              <button class="gm-ei-btn gm-ei-cancel-edit" @click="ag._editing=false"><svg width="10" height="10" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24"><path d="M18 6L6 18M6 6l12 12"/></svg></button>
                            </template>
                          </div>
                        </div>
                      </div>
                      <button class="gm-add-btn" style="margin-top:6px" @click="addExtractItem"><svg width="10" height="10" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24"><path d="M12 5v14M5 12h14"/></svg> 항목 직접 추가</button>
                      <div class="detail-extract-footer detail-extract-footer--col">
                        <span class="dei-count">승인 {{ extractResult.filter(a=>a._state==='approved').length }} / 반려 {{ extractResult.filter(a=>a._state==='rejected').length }} / 미검토 {{ extractResult.filter(a=>!a._state).length }}</span>
                        <button class="detail-action-btn btn-assign" :disabled="!extractResult.filter(a=>a._state==='approved').length" @click="extractPhase='assign'; openAssignModal()">배정으로 이동 →</button>
                      </div>
                    </template>
                    <div v-else class="detail-log-empty" style="margin-top:18px">
                      <svg width="28" height="28" fill="none" stroke="#64748b" stroke-width="1.5" viewBox="0 0 24 24" style="margin-bottom:8px"><path d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2"/><rect x="9" y="3" width="6" height="4" rx="1"/></svg>
                      <div>추출된 과제가 없습니다.</div>
                      <div style="font-size:11px;opacity:.6;margin-top:4px">자료를 선택하거나 파일을 추가한 후 다시 시도해보세요.</div>
                      <button class="ctx-run-btn" style="margin-top:10px" @click="extractPhase='context'">
                        <svg width="11" height="11" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24"><path d="M19 12H5M12 19l-7-7 7-7"/></svg>
                        자료 선정으로 돌아가기
                      </button>
                    </div>
                  </template>

                  <template v-if="extractPhase==='assign'">
                    <div v-if="assignLoading" class="detail-extract-loading"><div class="gm-spinner"></div><span>과제를 불러오는 중...</span></div>
                    <div v-else-if="!assignResult.length" class="detail-log-empty">배정된 과제가 없습니다.</div>
                    <template v-else>
                      <div class="detail-extract-list">
                        <div v-for="(t, i) in assignResult" :key="i" class="detail-extract-item" :class="{ 'ei-approved': t._state==='approved', 'ei-rejected': t._state==='rejected' }">
                          <div class="gm-ai-status-bar" :class="'asb-'+t.status"></div>
                          <div class="dei-body">
                            <template v-if="!t._editing">
                              <div class="dei-title" :class="{ 'ai-rejected-text': t._state==='rejected' }">{{ t.content }}</div>
                              <div class="dei-meta-row">
                                <span class="gm-chip gm-chip-priority" :class="'cp-'+t.priority">{{ PRIORITY_LABEL[t.priority]||t.priority }}</span>
                                <span v-if="t.status && t.status !== 'pending'" class="gm-chip gm-chip-status" :class="'cs-'+t.status">{{ STATUS_LABEL[t.status]||t.status }}</span>
                                <span class="dei-assignee">{{ t.assignee }} · {{ t.dept }}</span>
                              </div>
                            </template>
                            <template v-else>
                              <input class="dei-input" v-model="t._editContent" placeholder="과제 내용" style="margin-bottom:4px" />
                              <div class="dei-edit-row">
                                <select class="app-select dei-app-select" v-model="t._editDept">
                                  <option value="">담당부서 선택</option>
                                  <option v-for="d in assignDeptOptions" :key="d" :value="d">{{ d }}</option>
                                </select>
                                <select class="app-select dei-app-select" v-model="t._editPriority">
                                  <option v-for="(label, val) in PRIORITY_LABEL" :key="val" :value="val">{{ label }}</option>
                                </select>
                              </div>
                            </template>
                          </div>
                          <div class="dei-actions">
                            <template v-if="!t._editing">
                              <button class="gm-ei-btn gm-ei-edit" @click="t._editing=true"><svg width="10" height="10" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M11 4H4a2 2 0 00-2 2v14a2 2 0 002 2h14a2 2 0 002-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 013 3L12 15l-4 1 1-4 9.5-9.5z"/></svg></button>
                              <button class="gm-ei-btn" :class="t._state==='approved' ? 'gm-ei-approved-active' : 'gm-ei-approve'" @click="t._state = t._state==='approved' ? null : 'approved'"><svg width="10" height="10" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24"><path d="M20 6L9 17l-5-5"/></svg></button>
                              <button class="gm-ei-btn" :class="t._state==='rejected' ? 'gm-ei-rejected-active' : 'gm-ei-reject'" @click="rejectAssignItem(i)"><svg width="10" height="10" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24"><path d="M18 6L6 18M6 6l12 12"/></svg></button>
                            </template>
                            <template v-else>
                              <button class="gm-ei-btn gm-ei-save" @click="saveAssignItem(i)"><svg width="10" height="10" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24"><path d="M20 6L9 17l-5-5"/></svg></button>
                              <button class="gm-ei-btn gm-ei-cancel-edit" @click="cancelAssignEdit(i)"><svg width="10" height="10" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24"><path d="M18 6L6 18M6 6l12 12"/></svg></button>
                            </template>
                          </div>
                        </div>
                      </div>
                      <button class="gm-add-btn" style="margin-top:6px" @click="addAssignItem"><svg width="10" height="10" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24"><path d="M12 5v14M5 12h14"/></svg> 과제 직접 추가</button>
                      <div class="detail-extract-footer detail-extract-footer--col">
                        <span class="dei-count">승인 {{ assignResult.filter(t=>t._state==='approved').length }} / 반려 {{ assignResult.filter(t=>t._state==='rejected').length }} / 미검토 {{ assignResult.filter(t=>!t._state).length }}</span>
                        <button class="detail-action-btn btn-extract" :disabled="!assignResult.filter(t=>t._state==='approved').length" @click="saveApprovedTasks">승인 {{ assignResult.filter(t=>t._state==='approved').length }}건 저장</button>
                      </div>
                    </template>
                  </template><!-- /assign -->

                </template><!-- /추출·배정 단계 -->

            </template><!-- /과제추출 탭 -->

            <!-- ── 관계 탭 ── -->
            <template v-if="detailTab==='rel'">
              <div class="detail-section">
                <div class="detail-section-label-row">
                  <span class="detail-section-label">연결 관계</span>
                  <button class="detail-more-btn rel-add-trigger" @click="openAddRel">+ 추가</button>
                </div>

                <div v-if="currentNodeEdges.length" class="rel-list">
                  <div v-for="edge in currentNodeEdges" :key="edge._idx" class="rel-item">
                    <!-- 인라인 편집 -->
                    <template v-if="relEditIdx === edge._idx">
                      <div class="rel-edit-row">
                        <select v-model="relEditRel" class="rel-type-select">
                          <option v-for="rt in ALL_REL_TYPES" :key="rt" :value="rt">{{ rt }}</option>
                        </select>
                        <button class="rel-btn rel-btn-save" @click="saveRelEdit">저장</button>
                        <button class="rel-btn rel-btn-cancel" @click="cancelRelEdit">취소</button>
                      </div>
                    </template>
                    <!-- 표시 -->
                    <template v-else>
                      <div class="rel-item-main">
                        <span class="rel-dir">{{ edge.direction==='out' ? '→' : '←' }}</span>
                        <span class="rel-badge" :style="{ background: REL_COLORS[edge.rel] || '#6b7280' }">{{ edge.rel }}</span>
                        <span class="rel-target-name" :title="edge.direction==='out' ? edge.toNode?.label : edge.fromNode?.label">
                          {{ edge.direction==='out' ? edge.toNode?.label : edge.fromNode?.label }}
                        </span>
                      </div>
                      <div class="rel-item-actions">
                        <button class="rel-btn rel-btn-edit" @click="startRelEdit(edge._idx)" title="관계 유형 수정">
                          <svg width="10" height="10" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M11 4H4a2 2 0 00-2 2v14a2 2 0 002 2h14a2 2 0 002-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 013 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>
                        </button>
                        <button class="rel-btn rel-btn-delete" @click="doDeleteEdge(edge._idx)" title="관계 삭제">
                          <svg width="10" height="10" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24"><path d="M18 6L6 18M6 6l12 12"/></svg>
                        </button>
                      </div>
                    </template>
                  </div>
                </div>
                <div v-else class="detail-log-empty">연결된 관계가 없습니다.</div>
              </div>

              <!-- 관계 추가 폼 -->
              <div v-if="relAddActive" class="detail-section rel-add-panel">
                <div class="detail-section-label-row" style="margin-bottom:8px">
                  <span class="detail-section-label">새 관계 추가</span>
                  <button class="rel-btn rel-btn-cancel" @click="relAddActive=false">
                    <svg width="10" height="10" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24"><path d="M18 6L6 18M6 6l12 12"/></svg>
                  </button>
                </div>
                <div class="rel-add-form">
                  <div class="rel-add-field">
                    <label class="rel-add-label">출발 노드</label>
                    <select v-model="relAddForm.fromId" class="rel-type-select">
                      <option value="">선택...</option>
                      <option v-for="n in allGraphNodeList" :key="n.id" :value="n.id">{{ n.label }} ({{ n.type }})</option>
                    </select>
                  </div>
                  <div class="rel-add-field">
                    <label class="rel-add-label">관계 유형</label>
                    <select v-model="relAddForm.rel" class="rel-type-select">
                      <option v-for="rt in ALL_REL_TYPES" :key="rt" :value="rt">
                        {{ rt }}
                      </option>
                    </select>
                  </div>
                  <div class="rel-add-field">
                    <label class="rel-add-label">도착 노드</label>
                    <select v-model="relAddForm.toId" class="rel-type-select">
                      <option value="">선택...</option>
                      <option v-for="n in allGraphNodeList" :key="n.id" :value="n.id" :disabled="n.id===relAddForm.fromId">
                        {{ n.label }} ({{ n.type }})
                      </option>
                    </select>
                  </div>
                  <button
                    class="app-btn-primary"
                    style="width:100%;margin-top:6px;font-size:12px;padding:7px 0"
                    :disabled="!relAddForm.fromId || !relAddForm.toId || !relAddForm.rel"
                    @click="doAddRel">
                    관계 추가
                  </button>
                </div>
              </div>
            </template><!-- /관계 탭 -->

          </div>
          </template><!-- /detailMeeting -->

          <!-- ── Node detail (부서/과제/회의/파일/사람/아젠다) ── -->
          <template v-else-if="detailNode">
          <div class="detail-header">
            <!-- 노드 유형별 아이콘 -->
            <div class="detail-header-icon">
              <!-- 부서 -->
              <svg v-if="detailNode.type==='dept'" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/></svg>
              <!-- 조직 -->
              <svg v-else-if="detailNode.type==='org'" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M3 9l9-7 9 7v11a2 2 0 01-2 2H5a2 2 0 01-2-2z"/><polyline points="9 22 9 12 15 12 15 22"/></svg>
              <!-- 아젠다 -->
              <svg v-else-if="detailNode.type==='agenda'" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M9 11l3 3L22 4"/><path d="M21 12v7a2 2 0 01-2 2H5a2 2 0 01-2-2V5a2 2 0 012-2h11"/></svg>
              <!-- 회의(session) -->
              <svg v-else-if="detailNode.type==='session'" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><rect x="3" y="4" width="18" height="18" rx="2"/><path d="M16 2v4M8 2v4M3 10h18"/></svg>
              <!-- 파일 -->
              <svg v-else-if="detailNode.type==='file'" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
              <!-- 사람 -->
              <svg v-else width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M20 21v-2a4 4 0 00-4-4H8a4 4 0 00-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>
            </div>
            <div class="detail-header-left">
              <div class="detail-meeting-name">{{ detailNode.label }}</div>
              <div class="detail-meta-row">
                <span class="detail-meta">{{ { dept:'부서', agenda:'아젠다', session: detailNode.subType==='agenda'?'아젠다':'회의', file:'문서', person:'구성원', org:'조직', decision:'의사결정' }[detailNode.type] || detailNode.type }}</span>
              </div>
            </div>
            <div class="detail-header-actions">
              <button class="detail-icon-btn" @click="detailOpen=false" title="닫기">
                <svg width="11" height="11" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24"><path d="M18 6L6 18M6 6l12 12"/></svg>
              </button>
            </div>
          </div>

          <!-- 탭 -->
          <div class="detail-tabs">
            <button class="detail-tab" :class="{ active: nodeDetailTab==='basic' }" @click="nodeDetailTab='basic'">기본</button>
            <button class="detail-tab" :class="{ active: nodeDetailTab==='rel' }" @click="nodeDetailTab='rel'">관계</button>
          </div>

          <div class="detail-body">

            <!-- ── 기본 탭 ── -->
            <template v-if="nodeDetailTab==='basic'">

            <!-- 부서 -->
            <template v-if="detailNode.type==='dept'">
              <div class="detail-section">
                <div class="detail-info-grid">
                  <div class="detail-info-item">
                    <span class="detail-info-key">부서명</span>
                    <span class="detail-info-val">{{ detailNode.label }}</span>
                  </div>
                </div>
              </div>
              <div class="detail-section">
                <div class="detail-section-label">부서 구성원</div>
                <div v-if="detailNode.members?.length" class="node-member-list">
                  <div v-for="mb in detailNode.members" :key="mb.userId||mb.userName" class="node-member-row">
                    <div class="node-avatar" :style="{ background: mb.role==='admin' ? '#3b82f6' : '#475569' }">{{ (mb.userName||mb.name||'?')[0] }}</div>
                    <div class="node-member-info">
                      <span class="node-member-name">{{ mb.userName || mb.name || '-' }}</span>
                      <span class="node-member-role">{{ mb.role==='admin' ? '간사' : '참여자' }}</span>
                    </div>
                  </div>
                </div>
                <div v-else class="node-empty">구성원 정보 없음</div>
              </div>
            </template>

            <!-- 조직 -->
            <template v-else-if="detailNode.type==='org'">
              <div class="detail-section">
                <div class="detail-info-grid">
                  <div class="detail-info-item" style="grid-column:span 2">
                    <span class="detail-info-key">조직명</span>
                    <span class="detail-info-val">{{ detailNode.data?.name || detailNode.label }}</span>
                  </div>
                  <div class="detail-info-item">
                    <span class="detail-info-key">타입</span>
                    <span class="detail-info-val">{{ detailNode.data?.org_type || '-' }}</span>
                  </div>
                </div>
              </div>
              <div v-if="meetingGroups.length" class="detail-section">
                <div class="detail-section-label">회의체 목록 ({{ meetingGroups.length }}개)</div>
                <div class="detail-info-grid">
                  <div v-for="mg in meetingGroups" :key="mg.id" class="detail-info-item" style="grid-column:span 2">
                    <span class="detail-info-val">{{ mg.title }}</span>
                  </div>
                </div>
              </div>
            </template>

            <!-- 아젠다 -->
            <template v-else-if="detailNode.type==='agenda'">
              <div class="detail-section">
                <div class="detail-info-grid">
                  <div class="detail-info-item" style="grid-column:span 2">
                    <span class="detail-info-key">아젠다명</span>
                    <span class="detail-info-val">{{ detailNode.data?.content || detailNode.label }}</span>
                  </div>
                  <div class="detail-info-item">
                    <span class="detail-info-key">카테고리</span>
                    <span class="detail-info-val">{{ detailNode.data?.category || '-' }}</span>
                  </div>
                  <div class="detail-info-item">
                    <span class="detail-info-key">상태</span>
                    <span class="detail-info-val">
                      <span class="status-badge" :class="{
                        'sb-done': detailNode.data?.status==='완료' || detailNode.data?.status==='done',
                        'sb-progress': detailNode.data?.status==='진행' || detailNode.data?.status==='진행중' || detailNode.data?.status==='in_progress',
                        'sb-pending': detailNode.data?.status==='대기' || detailNode.data?.status==='pending' || !detailNode.data?.status
                      }">{{ detailNode.data?.status || '-' }}</span>
                    </span>
                  </div>
                  <div class="detail-info-item">
                    <span class="detail-info-key">우선순위</span>
                    <span class="detail-info-val">{{ { high:'상', medium:'중', low:'하', 상:'상', 중:'중', 하:'하' }[detailNode.data?.priority] || detailNode.data?.priority || '-' }}</span>
                  </div>
                  <div class="detail-info-item">
                    <span class="detail-info-key">발생일</span>
                    <span class="detail-info-val">{{ detailNode.data?.created_at ? formatDate(detailNode.data.created_at) : '-' }}</span>
                  </div>
                  <div class="detail-info-item">
                    <span class="detail-info-key">마감일</span>
                    <span class="detail-info-val">{{ detailNode.data?.due_date ? formatDate(detailNode.data.due_date) : '-' }}</span>
                  </div>
                </div>
              </div>
            </template>

            <!-- 회의(session) -->
            <template v-else-if="detailNode.type==='session'">
              <div class="detail-section">
                <div class="detail-info-grid">
                  <div class="detail-info-item" style="grid-column:span 2">
                    <span class="detail-info-key">회의명</span>
                    <span class="detail-info-val">{{ detailNode.data?.session_title || detailNode.label }}</span>
                  </div>
                  <div class="detail-info-item">
                    <span class="detail-info-key">회의일자</span>
                    <span class="detail-info-val">{{ detailNode.data?.date ? formatDate(detailNode.data.date) : (detailNode.data?.ended_at ? formatDate(detailNode.data.ended_at) : '-') }}</span>
                  </div>
                  <div class="detail-info-item">
                    <span class="detail-info-key">타입</span>
                    <span class="detail-info-val">{{ detailNode.data?.session_type || '-' }}</span>
                  </div>
                  <div class="detail-info-item" style="grid-column:span 2">
                    <span class="detail-info-key">회의소개</span>
                    <span class="detail-info-val">{{ detailNode.data?.description || '-' }}</span>
                  </div>
                  <div class="detail-info-item" style="grid-column:span 2; display:flex; align-items:center; gap:8px">
                    <span class="detail-info-key">회의록</span>
                    <button class="dl-icon-btn" :title="detailNode.data?.doc_title || detailNode.data?.file_name || '회의록 다운로드'" @click="downloadDummy(detailNode.data?.doc_title || detailNode.data?.file_name || detailNode.data?.session_title || detailNode.label)">
                      <svg width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
                    </button>
                  </div>
                </div>
              </div>
              <div v-if="detailNode.data?.participants?.length" class="detail-section">
                <div class="detail-section-label">참여자</div>
                <div class="node-member-list">
                  <div v-for="p in detailNode.data.participants" :key="p.userId||p.userName" class="node-member-row">
                    <div class="node-avatar" style="background:#475569">{{ (p.userName||p.name||'?')[0] }}</div>
                    <div class="node-member-info">
                      <span class="node-member-name">{{ p.userName || p.name }}</span>
                      <span v-if="p.department" class="node-member-role">{{ p.department }}</span>
                    </div>
                  </div>
                </div>
              </div>
            </template>

            <!-- 파일(문서/회의록) -->
            <template v-else-if="detailNode.type==='file'">
              <div class="detail-section">
                <div class="detail-info-grid">
                  <div class="detail-info-item" style="grid-column:span 2">
                    <span class="detail-info-key">파일명</span>
                    <span class="detail-info-val">{{ detailNode.data?.title || detailNode.data?.file_name || detailNode.label }}</span>
                  </div>
                  <div class="detail-info-item">
                    <span class="detail-info-key">종류</span>
                    <span class="detail-info-val">{{ detailNode.data?.doc_type || detailNode.fileType || '-' }}</span>
                  </div>
                  <div class="detail-info-item">
                    <span class="detail-info-key">작성일</span>
                    <span class="detail-info-val">{{ detailNode.data?.created_at ? formatDate(detailNode.data.created_at) : (detailNode.data?.submitted_at ? formatDate(detailNode.data.submitted_at) : '-') }}</span>
                  </div>
                  <div class="detail-info-item">
                    <span class="detail-info-key">작성자</span>
                    <span class="detail-info-val">{{ detailNode.data?.author || detailNode.data?.department || '-' }}</span>
                  </div>
                  <div class="detail-info-item" style="grid-column:span 2; display:flex; align-items:center; gap:8px">
                    <span class="detail-info-key">파일</span>
                    <button class="dl-icon-btn" :title="detailNode.data?.title || detailNode.data?.file_name || '파일 다운로드'" @click="downloadDummy(detailNode.data?.title || detailNode.data?.file_name || detailNode.label)">
                      <svg width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
                    </button>
                  </div>
                </div>
              </div>
            </template>

            <!-- 구성원 (person) -->
            <template v-else-if="detailNode.type==='person'">
              <div class="detail-section">
                <div class="detail-info-grid">
                  <SidebarInfoRow label="조직" :value="detailNode.data?.organization || currentOrg?.name || '-'" />
                  <SidebarInfoRow label="부서" :value="detailNode.data?.department || '-'" />
                  <SidebarInfoRow label="직첸" :value="detailNode.data?.position || '-'" />
                </div>
              </div>
              <div class="detail-section">
                <div class="detail-section-label">참여 회의체</div>
                <div v-if="personMeetingGroups(detailNode).length" class="detail-info-grid">
                  <div v-for="mg in personMeetingGroups(detailNode)" :key="mg.id" class="detail-info-item" style="grid-column:span 2">
                    <span class="detail-info-key">{{ mg.role==='admin' ? '간사' : '참여' }}</span>
                    <span class="detail-info-val">{{ mg.title }}</span>
                  </div>
                </div>
                <div v-else class="node-empty">회의체 정보 없음</div>
              </div>
              <div class="detail-section">
                <div class="detail-section-label">할당된 과제</div>
                <div v-if="personTasks(detailNode).length" class="detail-info-grid">
                  <div v-for="t in personTasks(detailNode)" :key="t.id" class="detail-info-item" style="grid-column:span 2">
                    <span class="detail-info-key">
                      <span class="status-badge" :class="{'sb-done':t.status==='done','sb-progress':t.status==='in_progress','sb-pending':!t.status||t.status==='pending'}">{{ {done:'완료',in_progress:'진행',pending:'대기'}[t.status]||t.status }}</span>
                    </span>
                    <span class="detail-info-val" style="white-space:normal;line-height:1.4">{{ t.content }}</span>
                  </div>
                </div>
                <div v-else class="node-empty">할당된 과제 없음</div>
              </div>
            </template>

            </template><!-- /기본 탭 -->

            <!-- ── 관계 탭 ── -->
            <template v-if="nodeDetailTab==='rel'">

            <div class="detail-section">
              <div class="detail-section-label-row">
                <span class="detail-section-label">연결 관계</span>
                <button class="detail-more-btn rel-add-trigger" @click="openAddRel">+ 추가</button>
              </div>

              <div v-if="currentNodeEdges.length" class="rel-list">
                <div v-for="edge in currentNodeEdges" :key="edge._idx" class="rel-item">
                  <template v-if="relEditIdx === edge._idx">
                    <div class="rel-edit-row">
                      <select v-model="relEditRel" class="rel-type-select">
                        <option v-for="rt in ALL_REL_TYPES" :key="rt" :value="rt">{{ rt }}</option>
                      </select>
                      <button class="rel-btn rel-btn-save" @click="saveRelEdit">저장</button>
                      <button class="rel-btn rel-btn-cancel" @click="cancelRelEdit">취소</button>
                    </div>
                  </template>
                  <template v-else>
                    <div class="rel-item-main">
                      <span class="rel-dir">{{ edge.direction==='out' ? '→' : '←' }}</span>
                      <span class="rel-badge" :style="{ background: REL_COLORS[edge.rel] || '#6b7280' }">{{ edge.rel }}</span>
                      <span class="rel-target-name" :title="edge.direction==='out' ? edge.toNode?.label : edge.fromNode?.label">
                        {{ edge.direction==='out' ? edge.toNode?.label : edge.fromNode?.label }}
                      </span>
                    </div>
                    <div class="rel-item-actions">
                      <button class="rel-btn rel-btn-edit" @click="startRelEdit(edge._idx)" title="관계 유형 수정">
                        <svg width="10" height="10" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M11 4H4a2 2 0 00-2 2v14a2 2 0 002 2h14a2 2 0 002-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 013 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>
                      </button>
                      <button class="rel-btn rel-btn-delete" @click="doDeleteEdge(edge._idx)" title="관계 삭제">
                        <svg width="10" height="10" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24"><path d="M18 6L6 18M6 6l12 12"/></svg>
                      </button>
                    </div>
                  </template>
                </div>
              </div>
              <div v-else class="detail-log-empty">연결된 관계가 없습니다.</div>
            </div>

            <!-- 관계 추가 폼 (노드 공통) -->
            <div v-if="relAddActive" class="detail-section rel-add-panel">
              <div class="detail-section-label-row" style="margin-bottom:8px">
                <span class="detail-section-label">새 관계 추가</span>
                <button class="rel-btn rel-btn-cancel" @click="relAddActive=false">
                  <svg width="10" height="10" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24"><path d="M18 6L6 18M6 6l12 12"/></svg>
                </button>
              </div>
              <div class="rel-add-form">
                <div class="rel-add-field">
                  <label class="rel-add-label">출발 노드</label>
                  <select v-model="relAddForm.fromId" class="rel-type-select">
                    <option value="">선택...</option>
                    <option v-for="n in allGraphNodeList" :key="n.id" :value="n.id">{{ n.label }} ({{ n.type }})</option>
                  </select>
                </div>
                <div class="rel-add-field">
                  <label class="rel-add-label">관계 유형</label>
                  <select v-model="relAddForm.rel" class="rel-type-select">
                    <option v-for="rt in ALL_REL_TYPES" :key="rt" :value="rt">{{ rt }}</option>
                  </select>
                </div>
                <div class="rel-add-field">
                  <label class="rel-add-label">도착 노드</label>
                  <select v-model="relAddForm.toId" class="rel-type-select">
                    <option value="">선택...</option>
                    <option v-for="n in allGraphNodeList" :key="n.id" :value="n.id" :disabled="n.id===relAddForm.fromId">
                      {{ n.label }} ({{ n.type }})
                    </option>
                  </select>
                </div>
                <button
                  class="app-btn-primary"
                  style="width:100%;margin-top:6px;font-size:12px;padding:7px 0"
                  :disabled="!relAddForm.fromId || !relAddForm.toId || !relAddForm.rel"
                  @click="doAddRel">
                  관계 추가
                </button>
              </div>
            </div>

            </template><!-- /관계 탭 -->

          </div>
          </template><!-- /detailNode -->

          </div>
        </Transition>

        <!-- Sidebar toggle handle — visible whenever a meeting or node is selected -->
        <button v-if="(detailMeeting || detailNode) && viewMode==='graph'"
          class="sidebar-toggle-handle"
          :style="{ left: (detailOpen ? sidebarW : 0) + 'px', transition: 'left 0.28s cubic-bezier(.22,.68,0,1.2)' }"
          @click="detailOpen = !detailOpen"
          :title="detailOpen ? '사이드바 접기' : '사이드바 펼치기'">
          <svg width="8" height="14" viewBox="0 0 8 14" fill="none" xmlns="http://www.w3.org/2000/svg">
            <path v-if="detailOpen" d="M6 1L1 7L6 13" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>
            <path v-else d="M2 1L7 7L2 13" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>
          </svg>
        </button>

        <!-- Graph view -->
        <div v-if="loading && viewMode==='graph'" class="graph-loading">
          <div class="graph-loading-spinner"></div>
          <span>불러오는 중...</span>
        </div>

        <!-- Zoom controls (top-left) -->
        <div v-if="!loading && viewMode==='graph'" class="graph-zoom-controls"
          :style="{ left: (detailOpen ? sidebarW + 10 : 10) + 'px', transition: 'left 0.28s cubic-bezier(.22,.68,0,1.2)' }">
          <button class="zoom-btn" @click="targetZoom = Math.min(4, targetZoom * 1.3)" title="확대 (Zoom In)">+</button>
          <button class="zoom-btn zoom-reset" @click="targetZoom = 1.0; targetCamX = 0; targetCamY = 0; targetCamZ = 0" title="초기화 (Reset)">⌂</button>
          <button class="zoom-btn" @click="targetZoom = Math.max(0.25, targetZoom / 1.3)" title="축소 (Zoom Out)">−</button>
          <button class="zoom-btn zoom-pan" :class="{ active: isPanMode }" @click="isPanMode = !isPanMode" title="패닝 모드 (Pan Mode)">
            <svg width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><polyline points="5 9 2 12 5 15"/><polyline points="9 5 12 2 15 5"/><polyline points="15 19 12 22 9 19"/><polyline points="19 9 22 12 19 15"/><line x1="2" y1="12" x2="22" y2="12"/><line x1="12" y1="2" x2="12" y2="22"/></svg>
          </button>
        </div>
        <canvas v-show="!loading && viewMode==='graph'"
          ref="canvasRef"
          class="archive-canvas"
          :style="{ cursor: connDragging ? 'crosshair' : connDotVisible ? 'crosshair' : isPanMode ? (isDragging ? 'grabbing' : 'grab') : 'default' }"
          @mousedown="onMouseDown"
          @mousemove="onMouseMove"
          @mouseup="onMouseUp"
          @mouseleave="onMouseLeave"
          @click="onCanvasClick"

          @wheel.prevent="onWheel"
          @touchstart.prevent="onTouchStart"
          @touchmove.prevent="onTouchMove"
          @touchend="onTouchEnd"
        ></canvas>

        <!-- ── Constellation view ── -->
        <template v-if="viewMode==='constellation'">
          <canvas
            ref="constCanvasRef"
            class="archive-canvas const-canvas"
            @mousedown="onConstMouseDown"
            @mousemove="onConstMouseMove"
            @mouseup="onConstMouseUp"
            @mouseleave="onConstMouseUp"
            @click="onConstCanvasClick"
            @wheel.prevent="onConstWheel"
          ></canvas>
          <!-- Zoom controls -->
          <div class="const-zoom-controls">
            <button class="zoom-btn" @click="constTargetScale = Math.min(6, constTargetScale * 1.25)">+</button>
            <button class="zoom-btn zoom-reset" @click="onConstResetView">⌂</button>
            <button class="zoom-btn" @click="constTargetScale = Math.max(0.3, constTargetScale / 1.25)">−</button>
          </div>
          <!-- Hint -->
          <div class="const-hint" v-if="constSelMgIdx === null">
            <svg width="12" height="12" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><circle cx="12" cy="12" r="10"/><path d="M12 8v4M12 16h.01"/></svg>
            회의체 노드를 클릭하면 상세보기로 확대됩니다
          </div>
          <div class="const-hint" v-else>
            <svg width="12" height="12" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><circle cx="12" cy="12" r="10"/><path d="M12 8v4M12 16h.01"/></svg>
            {{ gNodes[constSelMgIdx]?.label }} · 빈 공간 클릭 시 전체 보기
          </div>
        </template>

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

        <!-- 온톨로지 범례 -->
        <div v-if="!loading && viewMode==='graph'" class="graph-legend-onto"
          :style="{ left: (detailOpen ? sidebarW + 12 : 12) + 'px', transition: 'left 0.28s cubic-bezier(.22,.68,0,1.2)' }">
          <div class="legend-onto-item" :class="{ 'legend-item-hidden': isHiddenType('org-root') }" @click="toggleNodeType('org-root')">
            <svg class="legend-dot-pentagon" width="12" height="12" viewBox="0 0 12 12"><polygon points="6,0.5 11.5,4.1 9.4,11 2.6,11 0.5,4.1" fill="rgba(71,85,105,0.85)" stroke="rgba(148,163,184,0.75)" stroke-width="1"/></svg>
            나
            <svg class="legend-eye" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <template v-if="!isHiddenType('org-root')"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></template>
              <template v-else><path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19"/><line x1="1" y1="1" x2="23" y2="23"/></template>
            </svg>
          </div>
          <div class="legend-onto-item" :class="{ 'legend-item-hidden': isHiddenType('meeting_group') }" @click="toggleNodeType('meeting_group')">
            <div class="legend-onto-dot legend-dot-circle" style="background:#3b82f6"></div>
            회의체
            <svg class="legend-eye" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <template v-if="!isHiddenType('meeting_group')"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></template>
              <template v-else><path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19"/><line x1="1" y1="1" x2="23" y2="23"/></template>
            </svg>
          </div>
          <div class="legend-onto-item" :class="{ 'legend-item-hidden': isHiddenType('dept') }" @click="toggleNodeType('dept')">
            <div class="legend-onto-dot legend-dot-rect" style="background:#b8aee0"></div>
            부서
            <svg class="legend-eye" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <template v-if="!isHiddenType('dept')"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></template>
              <template v-else><path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19"/><line x1="1" y1="1" x2="23" y2="23"/></template>
            </svg>
          </div>
          <div class="legend-onto-item" :class="{ 'legend-item-hidden': isHiddenType('agenda') }" @click="toggleNodeType('agenda')">
            <div class="legend-onto-dot legend-dot-rect" style="background:#7ac8b0"></div>
            과제
            <svg class="legend-eye" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <template v-if="!isHiddenType('agenda')"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></template>
              <template v-else><path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19"/><line x1="1" y1="1" x2="23" y2="23"/></template>
            </svg>
          </div>
          <div class="legend-onto-item" :class="{ 'legend-item-hidden': isHiddenType('session') }" @click="toggleNodeType('session')">
            <div class="legend-onto-dot legend-dot-rect" style="background:#d4b483"></div>
            회의
            <svg class="legend-eye" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <template v-if="!isHiddenType('session')"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></template>
              <template v-else><path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19"/><line x1="1" y1="1" x2="23" y2="23"/></template>
            </svg>
          </div>
          <div class="legend-onto-item" :class="{ 'legend-item-hidden': isHiddenType('file') }" @click="toggleNodeType('file')">
            <div class="legend-onto-dot legend-dot-rect" style="background:#c5c2be"></div>
            파일
            <svg class="legend-eye" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <template v-if="!isHiddenType('file')"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></template>
              <template v-else><path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19"/><line x1="1" y1="1" x2="23" y2="23"/></template>
            </svg>
          </div>
        </div>

        <!-- Graph floating action buttons (top-right of canvas) -->
        <div v-if="!loading && viewMode==='graph'" class="graph-float-btns">
          <div class="float-btn-item" @click="openCreateModal" @mousedown.prevent="onFloatBtnMouseDown('meeting', $event)" title="클릭해서 회의체 생성">
            <div class="float-node-preview meeting-preview">
              <svg width="16" height="16" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24"><path d="M12 4v16m8-8H4"/></svg>
            </div>
            <span class="float-btn-label">회의체 생성</span>
          </div>
          <div v-if="isAnyAdmin" class="float-btn-item" @mousedown.prevent="onFloatBtnMouseDown('session', $event)" title="회의체 노드에 드래그하여 회의 생성">
            <div class="float-node-preview session-preview">
              <svg width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M12 1a3 3 0 00-3 3v8a3 3 0 006 0V4a3 3 0 00-3-3z"/><path d="M19 10v2a7 7 0 01-14 0v-2M12 19v4M8 23h8"/></svg>
            </div>
            <span class="float-btn-label">회의 생성</span>
          </div>
          <div v-if="isAnyAdmin" class="float-btn-item" @mousedown.prevent="onFloatBtnMouseDown('doc', $event)" title="자료 업로드 및 노드 연결">
            <div class="float-node-preview doc-preview">
              <svg width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12"/></svg>
            </div>
            <span class="float-btn-label">자료 업로드</span>
          </div>
        </div>

        <!-- Drag preview line SVG overlay -->
        <svg v-if="floatDragging && floatDragPreviewLine"
          width="100%" height="100%"
          style="position:absolute;inset:0;pointer-events:none;z-index:16;overflow:visible">
          <defs>
            <marker id="drag-arrow" markerWidth="6" markerHeight="6" refX="3" refY="3" orient="auto">
              <circle cx="3" cy="3" r="2.5"
                :fill="floatDragging==='meeting'?'rgba(59,130,246,0.9)':'rgba(52,211,153,0.9)'"/>
            </marker>
          </defs>
          <line
            :x1="floatDragPreviewLine.x1" :y1="floatDragPreviewLine.y1"
            :x2="floatDragPreviewLine.x2" :y2="floatDragPreviewLine.y2"
            :stroke="floatDragging==='meeting'?'rgba(59,130,246,0.75)':'rgba(52,211,153,0.75)'"
            stroke-width="2.5" stroke-dasharray="9,5" stroke-linecap="round"
            marker-end="url(#drag-arrow)"
          />
          <circle
            :cx="floatDragPreviewLine.x1" :cy="floatDragPreviewLine.y1" r="10"
            :fill="floatDragging==='meeting'?'rgba(59,130,246,0.2)':'rgba(52,211,153,0.2)'"
            :stroke="floatDragging==='meeting'?'rgba(59,130,246,0.6)':'rgba(52,211,153,0.6)'"
            stroke-width="2" stroke-dasharray="4,2"
          />
        </svg>


        <!-- List view -->
        <div v-show="viewMode==='list'" class="list-view">
          <div class="lv-inner">
          <div class="lv-header">
            <div class="lv-filter-wrap">
              <select v-model="selectedMeetingType" class="lv-type-filter">
                <option v-for="opt in meetingTypeOptions" :key="opt.value" :value="opt.value">{{ opt.label }}</option>
              </select>
              <select v-model="selectedHistoryType" class="lv-type-filter">
                <option v-for="opt in HISTORY_TYPE_OPTIONS" :key="opt.value" :value="opt.value">{{ opt.label }}</option>
              </select>
            </div>
            <div class="lv-header-right">
              <span class="lv-title">{{ search ? `"${search}" 검색 결과` : '전체 목록' }}</span>
              <span class="lv-count">{{ filteredGroups.length }}개 회의체</span>
            </div>
          </div>
          <div v-if="loading" class="lv-empty">불러오는 중...</div>
          <div v-else-if="!meetingGroups.length" class="lv-empty">소속된 회의체가 없습니다.</div>
          <AppTable v-else :columns="lvColumns" :dark="nightMode" :sortKey="lvSortKey" :sortDir="lvSortDir" @sort="handleLvSort">
                <tr v-if="!filteredGroups.length">
                  <td colspan="5" class="lv-hist-empty" style="padding:20px;text-align:center;color:#94a3b8">{{ search ? '검색 결과가 없습니다.' : '데이터가 없습니다.' }}</td>
                </tr>
                <template v-for="g in sortedGroups" :key="g.id">
                  <!-- Group row -->
                  <tr class="lv-group-row" @click="expandedMeeting = expandedMeeting===g.id ? null : g.id">
                    <td class="lv-td-name">
                      <div class="lv-name-cell">
                        <svg class="lv-expand-icon" :style="{ transform: expandedMeeting===g.id ? 'rotate(90deg)' : '' }" width="11" height="11" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24"><path d="M9 18l6-6-6-6"/></svg>
                        <div class="lv-group-name">{{ g.title }}</div>
                      </div>
                    </td>
                    <td class="lv-td-type">
                      <span v-if="g.meeting_type" class="lv-type-text">{{ g.meeting_type }}</span>
                      <span v-else class="lv-type-text" style="color:#94a3b8">-</span>
                    </td>
                    <td class="lv-td-role">
                      <span class="lv-role-badge" :class="meetingsStore.meetingRoles[g.id]==='admin' ? 'role-admin' : 'role-presenter'">
                        {{ meetingsStore.meetingRoles[g.id] === 'admin' ? '간사' : '참여자' }}
                      </span>
                    </td>
                    <td class="lv-td-secretary">
                      <span class="lv-secretary-text">{{ g.members.find(m => m.role === 'admin')?.userName || g.members.find(m => m.role === 'admin')?.name || '-' }}</span>
                    </td>
                    <td class="lv-td-cnt">{{ (filteredGroupHistoryMap.get(g.id) || []).length }}건</td>
                  </tr>
                  <!-- Expanded history rows -->
                  <tr v-if="expandedMeeting===g.id" class="lv-expanded-row">
                    <td colspan="5" class="lv-expanded-td">
                      <table class="app-table lv-hist-table">
                        <thead>
                          <tr>
                            <th>설명</th>
                            <th style="width:110px">담당자</th>
                            <th style="width:100px">진행일</th>
                            <th style="width:60px">자료</th>
                          </tr>
                        </thead>
                        <tbody>
                          <tr v-if="!(filteredGroupHistoryMap.get(g.id) || []).length">
                            <td colspan="4" class="lv-hist-empty">{{ selectedHistoryType ? '해당 유형의 이력이 없습니다.' : '이력이 없습니다.' }}</td>
                          </tr>
                          <tr v-for="(item, i) in (filteredGroupHistoryMap.get(g.id) || [])" :key="i" class="lv-hist-row">
                            <td class="lv-hist-desc">
                              <div class="lv-hist-desc-inner">
                                <span class="lv-hist-type-dot" :class="'ht-' + item.type"></span>
                                {{ item.desc }}
                              </div>
                            </td>
                            <td class="lv-hist-manager">{{ item.manager }}</td>
                            <td class="lv-hist-date">{{ formatDate(item.date) }}</td>
                            <td class="lv-hist-file">
                              <button v-if="item.hasFile" class="lv-dl-btn" @click.stop="downloadDummy(item.fileName)" title="다운로드">
                                <svg width="11" height="11" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"/></svg>
                              </button>
                              <span v-else class="lv-no-file">-</span>
                            </td>
                          </tr>
                        </tbody>
                      </table>
                    </td>
                  </tr>
                </template>
          </AppTable>
          </div><!-- /lv-inner -->
        </div>

        <!-- Bottom panel (slides up) -->
        <div class="bottom-panel" :class="{ active: bottomMode }" :style="bottomMode ? { height: bottomH+'px' } : {}">
          <!-- Drag handle -->
          <div class="bottom-drag-handle" @mousedown="onBottomResizeStart">
            <div class="drag-bar"></div>
          </div>

          <!-- Task extraction -->
          <div v-if="bottomMode==='task'" class="bottom-inner">
            <div class="bottom-left">
              <div class="bottom-panel-label">▶ DRAFT (1)</div>
              <div class="task-form-scroll">
                <div class="tf-row"><div class="tf-label">안건명</div><input v-model="taskForm.title" class="tf-input" placeholder="장소 등록" /></div>
                <div class="tf-row"><div class="tf-label">유형</div>
                  <select v-model="taskForm.type" class="tf-input tf-select">
                    <option v-for="t in TYPES" :key="t" :value="t">{{ t }}</option>
                  </select>
                </div>
                <div class="tf-row"><div class="tf-label">마감일</div><input v-model="taskForm.deadline" type="date" class="tf-input" /></div>
                <div class="tf-row">
                  <div class="tf-label">담당 부서</div>
                  <div class="tag-input-wrap tf-input" style="padding:3px 7px;">
                    <span v-for="(d,i) in taskForm.depts" :key="i" class="dept-tag">{{ d }}<button @click="removeDept(i)" class="tag-rm">×</button></span>
                    <input v-model="taskDeptInput" class="tag-bare-input" placeholder="부서 추가" @keydown.enter.prevent="addDept" />
                  </div>
                </div>
                <div class="tf-row"><div class="tf-label">담당자</div><input v-model="taskForm.assignee" class="tf-input" placeholder="홍길동" /></div>
                <div class="tf-row tf-row-top"><div class="tf-label" style="padding-top:6px">목적</div><textarea v-model="taskForm.purpose" class="tf-input tf-textarea" placeholder="위원회 추진을 위한 장소 탐색 및 예약"></textarea></div>
                <div class="tf-row"><div class="tf-label">주관 회의체</div><input class="tf-input" placeholder="회의체 검색" /></div>
              </div>
              <div class="task-form-footer">
                <button class="tf-btn-save">저장</button>
                <button class="tf-btn-cancel" @click="closeBottomPanel">취소</button>
              </div>
            </div>
            <div class="bottom-right">
              <div class="ai-reason-title">AI 생성 근거</div>
              <div class="ai-reason-body">AI가 회의록 내용을 기반으로 위 과제를 추출했습니다.<br><br><strong>주요 근거:</strong><br>• 3차 회의에서 "담당자 지정 필요" 언급<br>• 이전 회의록의 후속 과제 미이행 항목<br>• 참석자 간 합의된 실행 계획</div>
              <div class="bottom-approve-row">
                <button class="btn-approve" @click="closeBottomPanel">승인</button>
                <button class="btn-reject" @click="closeBottomPanel">취소</button>
              </div>
            </div>
          </div>

          <!-- Material review -->
          <div v-if="bottomMode==='review'" class="bottom-inner">
            <div class="bottom-left">
              <div class="bottom-panel-label">AI 검토 결과</div>
              <div class="ai-reason-body" style="color:#94a3b8;font-size:13px">자료를 나루 채팅창에 업로드하면 AI가 검토 결과를 여기에 표시합니다.</div>
            </div>
            <div class="bottom-right">
              <div class="ai-reason-title">업로드 자료</div>
              <div class="upload-area">
                <svg width="28" height="28" fill="none" stroke="currentColor" stroke-width="1.5" viewBox="0 0 24 24" style="color:#475569"><path d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12"/></svg>
                <div style="font-size:12px;color:#64748b;margin-top:6px">파일을 드래그하거나 클릭해서 업로드</div>
              </div>
              <div class="bottom-approve-row">
                <button class="btn-approve">업로드</button>
                <button class="btn-reject" @click="closeBottomPanel">취소</button>
              </div>
            </div>
          </div>
        </div>

      </div><!-- /main-area -->

    </div><!-- /archive-body -->

    <!-- Agent right sidebar (overlay, covers header) -->
    <Transition name="agent-sidebar-slide">
      <div v-if="agentSidebarOpen" class="agent-right-sidebar">
          <!-- Supervisor header -->
          <div class="agent-supervisor-header">
            <div class="supervisor-brand">
              <img :src="SUPERVISOR.avatar" class="supervisor-logo" />
              <div class="supervisor-brand-text">
                <span class="supervisor-title">{{ SUPERVISOR.name }}</span>
                <span class="supervisor-sub">{{ SUPERVISOR.subtitle }}</span>
              </div>

            </div>
            <div class="supervisor-header-actions">
              <button class="agent-new-chat-btn" @click="clearAgentChat">새 채팅</button>
              <button class="agent-sidebar-close" @click="agentSidebarOpen=false">✕</button>
            </div>
          </div>
          <!-- Messages -->
          <div ref="agentMessagesEl" class="agent-messages">
            <div v-for="(msg,i) in currentMessages" :key="i" class="agent-msg-row" :class="msg.role === 'planning' ? 'planning' : msg.role">

              <!-- 사고 과정 블록 -->
              <template v-if="msg.role==='planning'">
                <div class="agent-msg-label">
                  <img :src="agentInfo.avatar" class="agent-msg-avatar" />
                  {{ agentInfo.name }}
                </div>
                <div class="agent-planning-block" :class="{ done: msg.done, open: msg.open }">
                  <button class="agent-planning-toggle" @click="msg.open = !msg.open">
                    <svg v-if="!msg.done" class="agent-planning-spinner" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="#00ab36" stroke-width="2.5"><path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83"/></svg>
                    <svg v-else width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="#00ab36" stroke-width="2.5"><path d="M9 12l2 2 4-4"/><circle cx="12" cy="12" r="10"/></svg>
                    <span class="agent-planning-label">
                      <template v-if="!msg.steps.length">{{ msg.done ? '완료' : '분석 중...' }}</template>
                      <template v-else>{{ msg.steps[msg.steps.length - 1].length > 58 ? msg.steps[msg.steps.length - 1].slice(0, 57) + '…' : msg.steps[msg.steps.length - 1] }}</template>
                    </span>
                    <span class="agent-planning-count">{{ msg.steps.length }} steps</span>
                    <svg class="agent-planning-chev" :class="{ rotated: msg.open }" width="11" height="11" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M19 9l-7 7-7-7"/></svg>
                  </button>
                  <div v-if="msg.open" class="agent-planning-steps">
                    <div v-for="(step, si) in msg.steps" :key="si"
                         class="agent-planning-step fade-in"
                         :class="{
                           'agent-step-data':  step.includes('→') || step.includes('확인') || step.includes('수집') || step.includes('분석'),
                           'agent-step-route': step.includes('위임') || step.includes('라우팅'),
                         }">
                      <span v-if="step.includes('위임') || step.includes('라우팅')" class="agent-step-icon-data">
                        <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M5 12h14M12 5l7 7-7 7"/></svg>
                      </span>
                      <span v-else-if="step.includes('확인') || step.includes('분석') || step.includes('수집') || step.includes('탐색')" class="agent-step-icon-data">
                        <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><circle cx="8" cy="12" r="3"/><circle cx="18" cy="7" r="2"/><circle cx="18" cy="17" r="2"/><line x1="11" y1="11" x2="16" y2="8"/><line x1="11" y1="13" x2="16" y2="16"/></svg>
                      </span>
                      <span v-else class="agent-step-num">{{ si + 1 }}</span>
                      <span class="agent-step-text">{{ step }}</span>
                    </div>
                    <div v-if="!msg.done" class="agent-planning-step agent-step-pending">
                      <span class="agent-step-dots"><span></span><span></span><span></span></span>
                    </div>
                  </div>
                </div>
              </template>

              <!-- AI 응답 -->
              <template v-else-if="msg.role==='agent'&&msg.content">
                <div v-if="currentMessages[i-1]?.role !== 'planning'" class="agent-msg-label">
                  <img :src="agentInfo.avatar" class="agent-msg-avatar" />
                  {{ agentInfo.name }}
                </div>
                <div class="agent-bubble agent theme-supervisor"
                     :class="{ 'is-streaming': agentLoading && i === currentMessages.length - 2 }"
                     v-html="renderMd(msg.content)"></div>
                <div v-if="i===0&&agentInfo.suggested?.length" class="agent-suggested">
                  <button v-for="s in agentInfo.suggested" :key="s" class="suggested-btn" :disabled="agentLoading" @click="agentInput=s;sendAgentMsg()">{{ s }}</button>
                </div>
              </template>

              <!-- 사용자 메시지 -->
              <div v-else-if="msg.role==='user'" class="agent-bubble user">
                <div>{{ msg.content }}</div>
                <div v-if="msg.contexts?.length" class="user-ctx-chips">
                  <span v-for="c in msg.contexts" :key="c.id" class="user-ctx-chip">{{ c.icon }} {{ c.label }}</span>
                </div>
              </div>
            </div>
            <div v-if="agentLoading&&currentMessages[currentMessages.length-1]?.role==='agent'&&currentMessages[currentMessages.length-1]?.content===''" class="agent-msg-row agent">
              <div class="agent-bubble agent typing"><span></span><span></span><span></span></div>
            </div>
          </div>
          <!-- Input -->
          <div class="agent-input-area">
            <!-- @ 드롭다운 -->
            <Transition name="at-menu">
              <div v-if="atMenuOpen && atMenuItems.length" class="at-menu">
                <div v-for="(item, i) in atMenuItems" :key="item.id"
                  class="at-menu-item" :class="{ active: i === atHighlight }"
                  @mousedown.prevent="selectAtItem(item)" @mouseover="atHighlight = i">
                  <span class="at-icon">{{ item.icon }}</span>
                  <span class="at-type">{{ AT_TYPE_LABELS[item.type] }}</span>
                  <span class="at-label">{{ item.label }}</span>
                </div>
                <div class="at-menu-hint">↑↓ 이동 · Enter 선택 · Esc 닫기</div>
              </div>
            </Transition>
            <!-- 파일 chips -->
            <div v-if="agentPendingFiles.length" class="agent-file-chips">
              <span v-for="f in agentPendingFiles" :key="f.name" class="agent-file-chip">📎 {{ f.name }}</span>
            </div>
            <!-- @ 컨텍스트 chips -->
            <div v-if="mentionedContexts.length" class="agent-ctx-chips">
              <span v-for="c in mentionedContexts" :key="c.id" class="agent-ctx-chip">
                {{ c.icon }} {{ c.label }}
                <button class="ctx-chip-remove" @click="removeMentionCtx(c.id)">×</button>
              </span>
            </div>
            <div class="agent-input-row">
              <button class="agent-attach-btn" @click="agentFileInput?.click()">＋</button>
              <textarea ref="agentTextareaEl" v-model="agentInput" class="agent-textarea"
                placeholder="질문하세요... (@로 그래프 컨텍스트 참조)" rows="1"
                @input="onAgentInput" @keydown="onAgentKeydown" />
              <button class="agent-send-btn" :disabled="agentLoading||(!agentInput.trim()&&!agentPendingFiles.length&&!mentionedContexts.length)" @click="sendAgentMsg">전송</button>
            </div>
            <input ref="agentFileInput" type="file" multiple style="display:none" @change="onAgentFileSelected" />
          </div>
        </div>
      </Transition>

    <!-- Float drag ghost cursor follow -->
    <Teleport to="body">
      <div v-if="floatDragging" class="float-drag-ghost"
        :style="{ left: (floatDragPos.x - 22) + 'px', top: (floatDragPos.y - 22) + 'px' }">
        <div class="ghost-node" :class="floatDragging === 'meeting' ? 'ghost-meeting' : floatDragging === 'session' ? 'ghost-session' : 'ghost-doc'">
          <svg v-if="floatDragging==='meeting'" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24"><path d="M12 4v16m8-8H4"/></svg>
          <svg v-else-if="floatDragging==='session'" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M12 1a3 3 0 00-3 3v8a3 3 0 006 0V4a3 3 0 00-3-3z"/><path d="M19 10v2a7 7 0 01-14 0v-2"/></svg>
          <svg v-else width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12"/></svg>
        </div>
        <span class="ghost-label">{{ floatDragging==='meeting' ? '회의체 생성' : floatDragging==='session' ? '회의 생성' : '자료 업로드' }}</span>
        <span v-if="floatDragPreviewLine" class="ghost-connect-hint">✓ 연결 가능</span>
      </div>
    </Teleport>

    <!-- ── Create Meeting Modal ── -->
    <Teleport to="body">
      <div v-if="showCreateModal" class="app-modal-backdrop" @click.self="showCreateModal=false">
        <div class="app-modal app-modal-md" :class="{ dark: nightMode }">
          <div class="app-modal-header">
            <span class="app-modal-title">회의체 생성</span>
            <button class="app-modal-close" @click="showCreateModal=false">
              <svg width="14" height="14" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24"><path d="M6 18L18 6M6 6l12 12"/></svg>
            </button>
          </div>
          <div class="app-modal-body">
            <div class="app-modal-field">
              <label>회의체 이름 <span class="req">*</span></label>
              <input v-model="createForm.title" class="app-modal-input" placeholder="예: 전략기획위원회" />
            </div>
            <div class="app-modal-field">
              <label>소개</label>
              <textarea v-model="createForm.purpose" class="app-modal-input" placeholder="이 회의체의 목적이나 소개..." rows="2"></textarea>
            </div>
            <div class="app-modal-field">
              <label>유형</label>
              <select v-model="createForm.meetㅇing_type" class="app-select" style="width:100%;font-size:13px;padding:7px 28px 7px 10px">
                <option value="Weekly">Weekly</option>
                <option value="Monthly">Monthly</option>
                <option value="Quarterly">Quarterly</option>
              </select>
            </div>
            <div class="app-modal-field-row">
              <div class="app-modal-field">
                <label>시작일</label>
                <input type="date" v-model="createForm.start_date" class="app-modal-input" />
              </div>
              <div class="app-modal-field">
                <label>종료일</label>
                <input type="date" v-model="createForm.end_date" class="app-modal-input" />
              </div>
            </div>
            <div class="app-modal-field">
              <label>운영 지침</label>
              <textarea v-model="createForm.guidelines" class="app-modal-input" rows="3" placeholder="운영 지침, 규칙, 주의사항 등을 입력하세요...
예: 매주 월요일 10시, 의장 승인 필수, 안건 72시간 전 제출 등"></textarea>
            </div>
            <div class="app-modal-field">
              <label>멤버 초대</label>
              <MemberInvite v-model="createMembers" />
            </div>
          </div>
          <div class="app-modal-footer">
            <button class="app-btn-cancel" @click="showCreateModal=false">취소</button>
            <button class="app-btn-primary" :disabled="creating||!createForm.title.trim()" @click="doCreateMeeting">{{ creating ? '생성 중...' : '생성' }}</button>
          </div>
        </div>
      </div>
    </Teleport>

  <!-- 회의 생성 모달 -->
  <Teleport to="body">
    <div v-if="showSessionModal" class="app-modal-backdrop" @click.self="showSessionModal=false">
      <div class="app-modal app-modal-md" :class="{ dark: nightMode }">
        <div class="app-modal-header">
          <span class="app-modal-title">회의 생성</span>
          <button class="app-modal-close" @click="showSessionModal=false">
            <svg width="14" height="14" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24"><path d="M6 18L18 6M6 6l12 12"/></svg>
          </button>
        </div>
        <div class="app-modal-body">
          <div class="app-modal-field">
            <label>회의명 <span class="req">*</span></label>
            <input v-model="sessionForm.title" class="app-modal-input" placeholder="예: 2025 전략 수립 1차" />
          </div>
          <div class="app-modal-field">
            <label>회의 소개</label>
            <textarea v-model="sessionForm.purpose" class="app-modal-input" placeholder="이번 회의의 목적이나 주요 내용..." rows="2"></textarea>
          </div>
          <div class="app-modal-field">
            <label>회의 날짜</label>
            <input type="datetime-local" v-model="sessionForm.date" class="app-modal-input" />
          </div>
          <div v-if="sessionForm.meeting_id" class="app-modal-field">
            <label>연결된 회의체</label>
            <div class="app-modal-input" style="background:var(--bg2);color:var(--text2);cursor:default">
              {{ sessionForm.meeting_id }}
            </div>
          </div>
          <div class="app-modal-field">
            <label>구성원</label>
            <MemberInvite v-model="sessionMembers" />
          </div>
        </div>
        <div class="app-modal-footer">
          <button class="app-btn-cancel" @click="showSessionModal=false">취소</button>
          <button class="app-btn-primary" :disabled="creatingSession||!sessionForm.title.trim()" @click="doCreateSession">{{ creatingSession ? '생성 중...' : '생성' }}</button>
        </div>
      </div>
    </div>
  </Teleport>

  </div><!-- /archive-page -->
  <!-- 자료 업로드 모달 -->
  <Teleport to="body">
    <div v-if="showUploadModal" class="app-modal-backdrop" @click.self="showUploadModal=false">
      <div class="app-modal app-modal-md" :class="{ dark: nightMode }">

        <!-- Step indicator -->
        <div class="upload-step-bar">
          <ProcessStepBar
            :steps="['자료 정보 입력', 'AI 검토 결과']"
            :current-step="uploadStep - 1"
            @step-click="i => { if (i === 0) uploadStep = 1 }"
          />
        </div>

        <!-- ── Step 1: 수동 입력 ── -->
        <template v-if="uploadStep===1">
          <div class="app-modal-header">
            <span class="app-modal-title">자료 정보 입력</span>
            <button class="app-modal-close" @click="showUploadModal=false"><svg width="14" height="14" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24"><path d="M6 18L18 6M6 6l12 12"/></svg></button>
          </div>
          <div class="app-modal-body">
            <!-- 파일 첨부 -->
            <div class="app-modal-field">
              <label>파일 첨부 <span class="req">*</span></label>
              <FileUploadArea
                :file="uploadForm.file"
                @change="files => { uploadForm.file = files[0]; uploadForm.label = uploadForm.label || files[0]?.name }"
              />
            </div>
            <div class="app-modal-field">
              <label>자료명 <span class="req">*</span></label>
              <input v-model="uploadForm.label" class="app-modal-input" placeholder="예: 2025년 1분기 전략보고서.pdf" />
            </div>

            <!-- 관련 회의체 -->
            <div class="app-modal-field">
              <label>관련 회의체 <span class="req">*</span><span v-if="prefilledCtx.meetingId" class="prefill-label">자동 입력됨</span></label>
              <select v-model="uploadForm.meetingId" class="app-modal-input" :class="{ 'prefilled': uploadForm.meetingId }"
                @change="prefilledCtx.meetingId = false; prefilledCtx.connectNodeId = false">
                <option value="">회의체 선택...</option>
                <option v-for="n in gNodes.filter(n=>n.type==='meeting_group')" :key="n.id" :value="n.id">{{ n.label }}</option>
              </select>
            </div>

            <!-- 업로드 부서 -->
            <div class="app-modal-field">
              <label>업로드 부서 <span class="req">*</span><span v-if="prefilledCtx.connectNodeId" class="prefill-label">자동 입력됨</span></label>
              <select v-model="uploadForm.connectNodeId" class="app-modal-input" :class="{ 'prefilled': uploadForm.connectNodeId }"
                @change="prefilledCtx.connectNodeId = false">
                <option value="">부서 선택...</option>
                <option v-for="n in deptConnectableNodes" :key="n.id" :value="n.id">{{ n.label }}</option>
              </select>
            </div>

            <!-- 연관 과제 -->
            <div class="app-modal-field">
              <label>연관 과제 <span class="req">*</span><span v-if="prefilledCtx.relatedTodoId" class="prefill-label">자동 입력됨</span></label>
              <select v-model="uploadForm.relatedTodoId" class="app-modal-input" :class="{ 'prefilled': uploadForm.relatedTodoId }"
                :disabled="!uploadForm.meetingId" @change="prefilledCtx.relatedTodoId = false">
                <option value="">{{ uploadForm.meetingId ? (업로드회의체과제.length ? '과제 선택...' : '연결된 과제가 없습니다') : '회의체를 먼저 선택하세요' }}</option>
                <option v-for="t in 업로드회의체과제" :key="t.id" :value="t.id">{{ t.content }}</option>
              </select>
            </div>

            <div v-if="uploadForm.connectNodeId && uploadForm.label" class="conn-preview-box">
              <span class="conn-node">{{ deptConnectableNodes.find(n=>n.id===uploadForm.connectNodeId)?.label }}</span>
              <span class="conn-arrow">→</span>
              <span class="conn-rel" :style="{color:REL_COLORS[autoRel(uploadForm.connectNodeId,'file')]||'#a78bfa'}">{{ autoRel(uploadForm.connectNodeId,'file') }}</span>
              <span class="conn-arrow">→</span>
              <span class="conn-node file">{{ uploadForm.label }}</span>
            </div>
          </div>
          <div class="app-modal-footer">
            <button class="app-btn-cancel" @click="showUploadModal=false">취소</button>
            <button class="app-btn-primary"
              :disabled="!uploadForm.label.trim() || !uploadForm.connectNodeId"
              @click="runAiAnalysis">
              <svg width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24" style="margin-right:5px"><path d="M12 2a10 10 0 100 20A10 10 0 0012 2z"/><path d="M12 8v4l3 3"/></svg>
              AI 검토 시작
            </button>
          </div>
        </template>

        <!-- ── Step 2: AI 분석 결과 ── -->
        <template v-else-if="uploadStep===2">
          <div class="app-modal-header">
            <span class="app-modal-title">AI 검토 결과 <span style="font-size:11px;opacity:.6;font-weight:400">— {{ uploadForm.label }}</span></span>
            <button class="app-modal-close" @click="showUploadModal=false"><svg width="14" height="14" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24"><path d="M6 18L18 6M6 6l12 12"/></svg></button>
          </div>
          <div class="app-modal-body ai-result-body">

            <!-- 로딩 -->
            <div v-if="aiAnalyzing" class="ai-loading-wrap">
              <div class="ai-loading-spinner"></div>
              <div class="ai-loading-text">AI가 자료를 검토하고 있습니다…<br><span style="font-size:11px;opacity:.6">GraphDB 맥락 + 조직 암묵지 분석 중</span></div>
            </div>

            <!-- 결과 -->
            <template v-else-if="aiResult">
              <!-- 점수 게이지 -->
              <div class="ai-score-section">
                <div class="ai-score-label">자료 적합성 점수</div>
                <div class="ai-score-gauge-wrap">
                  <svg width="110" height="60" viewBox="0 0 110 60">
                    <path d="M10 55 A45 45 0 0 1 100 55" fill="none" stroke="#e2e8f0" stroke-width="10" stroke-linecap="round"/>
                    <path d="M10 55 A45 45 0 0 1 100 55" fill="none"
                      :stroke="aiResult.score>=80?'#10b981':aiResult.score>=60?'#f59e0b':'#ef4444'"
                      stroke-width="10" stroke-linecap="round"
                      :stroke-dasharray="`${(aiResult.score/100)*141.3} 141.3`"/>
                    <text x="55" y="53" text-anchor="middle" font-size="18" font-weight="700"
                      :fill="aiResult.score>=80?'#10b981':aiResult.score>=60?'#f59e0b':'#ef4444'">{{ aiResult.score }}</text>
                  </svg>
                  <div class="ai-score-desc" :style="{color:aiResult.score>=80?'#10b981':aiResult.score>=60?'#d97706':'#dc2626'}">
                    {{ aiResult.score>=80?'우수':'적합'}} / 100
                  </div>
                </div>
                <div class="ai-feedback-list">
                  <div v-for="(fb,i) in aiResult.feedback" :key="i" class="ai-feedback-item">
                    <span class="fb-dot">•</span> {{ fb }}
                  </div>
                </div>
              </div>

              <!-- 발제자료 기준 체크리스트 -->
              <div v-if="uploadForm.fileType==='발제자료'" class="ai-section">
                <div class="ai-section-title">
                  <svg width="13" height="13" fill="none" stroke="#f59e0b" stroke-width="2" viewBox="0 0 24 24"><path d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>
                  발제자료 검토 기준 (Why/What/How)
                </div>
                <div class="criteria-list">
                  <div v-for="c in PRESENTATION_CRITERIA" :key="c.key" class="criteria-row">
                    <span class="criteria-dot" :class="aiResult.criteria?.[c.key] ? 'pass' : 'fail'">
                      <svg v-if="aiResult.criteria?.[c.key]" width="9" height="9" fill="none" stroke="currentColor" stroke-width="3" viewBox="0 0 24 24"><path d="M5 13l4 4L19 7"/></svg>
                      <svg v-else width="9" height="9" fill="none" stroke="currentColor" stroke-width="3" viewBox="0 0 24 24"><path d="M6 18L18 6M6 6l12 12"/></svg>
                    </span>
                    <div class="criteria-text">
                      <div class="criteria-label">{{ c.label }}</div>
                      <div class="criteria-desc">{{ c.desc }}</div>
                    </div>
                  </div>
                </div>
              </div>

              <!-- 제안 아젠다 -->
              <div class="ai-section">
                <div class="ai-section-title">
                  <svg width="13" height="13" fill="none" stroke="#6366f1" stroke-width="2" viewBox="0 0 24 24"><path d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2"/></svg>
                  AI 제안 아젠다 <span class="ai-badge">{{ selectedAgendas.length }}/{{ aiResult.agendas.length }} 선택</span>
                </div>
                <div v-if="!aiResult.agendas.length" class="ai-empty">제안 아젠다 없음</div>
                <div v-for="(ag, i) in aiResult.agendas" :key="i"
                  class="ai-check-row" :class="{ selected: selectedAgendas.includes(i) }"
                  @click="toggleAgenda(i)">
                  <span class="ai-checkbox" :class="{ checked: selectedAgendas.includes(i) }">
                    <svg v-if="selectedAgendas.includes(i)" width="10" height="10" fill="none" stroke="currentColor" stroke-width="3" viewBox="0 0 24 24"><path d="M5 13l4 4L19 7"/></svg>
                  </span>
                  <div class="ai-check-content">
                    <div class="ag-content">{{ ag.content }}</div>
                    <div v-if="ag.department" class="ag-dept">담당: {{ ag.department }}</div>
                  </div>
                </div>
              </div>

              <!-- 유관부서 -->
              <div class="ai-section">
                <div class="ai-section-title">
                  <svg width="13" height="13" fill="none" stroke="#10b981" stroke-width="2" viewBox="0 0 24 24"><path d="M17 21v-2a4 4 0 00-4-4H5a4 4 0 00-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 00-3-3.87M16 3.13a4 4 0 010 7.75"/></svg>
                  AI 추천 유관부서 <span class="ai-badge">{{ selectedRelDepts.length }}/{{ aiResult.related_depts.length }} 선택</span>
                </div>
                <div v-if="!aiResult.related_depts.length" class="ai-empty">추천 유관부서 없음</div>
                <div class="ai-dept-chips">
                  <span v-for="dept in aiResult.related_depts" :key="dept"
                    class="ai-dept-chip" :class="{ selected: selectedRelDepts.includes(dept) }"
                    @click="toggleRelDept(dept)">
                    <svg v-if="selectedRelDepts.includes(dept)" width="10" height="10" fill="none" stroke="currentColor" stroke-width="3" viewBox="0 0 24 24"><path d="M5 13l4 4L19 7"/></svg>
                    {{ dept }}
                  </span>
                </div>
              </div>
            </template>
          </div>
          <div class="app-modal-footer" style="justify-content:space-between">
            <button class="app-btn-cancel" @click="uploadStep=1; aiResult=null">← 다시 입력</button>
            <button class="app-btn-primary" :disabled="aiAnalyzing || !aiResult" @click="doAddFile">
              <svg width="12" height="12" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24" style="margin-right:4px"><path d="M5 13l4 4L19 7"/></svg>
              아카이브 등록 확정
            </button>
          </div>
        </template>

      </div>
    </div>
  </Teleport>

  <!-- 회의체 설정 모달 -->
  <Teleport to="body">
    <div v-if="settingsModal" class="app-modal-backdrop" @click.self="closeSettings">
      <div class="app-modal app-modal-lg" :class="{ dark: nightMode }">
        <div class="app-modal-header">
          <span class="app-modal-title">회의체 설정</span>
          <button class="app-modal-close" @click="closeSettings">
            <svg width="14" height="14" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24"><path d="M6 18L18 6M6 6l12 12"/></svg>
          </button>
        </div>
        <div class="app-modal-body settings-body">
          <div class="settings-section">
            <div class="settings-section-title">기본 정보</div>
            <div class="app-modal-field">
              <label>회의체 이름 <span class="req">*</span></label>
              <input v-model="settingsModal.form.title" class="app-modal-input" />
            </div>
            <div class="app-modal-field">
              <label>소개</label>
              <textarea v-model="settingsModal.form.purpose" class="app-modal-input" rows="2" placeholder="이 회의체의 목적이나 소개..."></textarea>
            </div>
            <div class="app-modal-field">
              <label>회의체 지침</label>
              <textarea v-model="settingsModal.form.guidelines" class="app-modal-input" rows="4" placeholder="이 회의체의 운영 지침, 규칙, 주의사항 등을 입력하세요...\n예: 매주 월요일 10시, 의장 승인 필수, 안건 72시간 전 제출 등"></textarea>
            </div>
          </div>
          <div class="settings-section">
            <div class="settings-section-title">
              참여자 <span class="member-cnt-badge">{{ settingsModal.members.length }}명</span>
            </div>
            <div class="member-search-wrap">
              <svg width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><circle cx="11" cy="11" r="8"/><path d="M21 21l-4.35-4.35"/></svg>
              <input :value="settingsSearchQ" @input="watchSettingsSearch($event.target.value)" class="member-search-input" placeholder="이름 또는 이메일로 검색 후 추가..." />
              <span v-if="settingsSearchLoading" class="search-spinner">↻</span>
            </div>
            <div v-if="settingsSearchResults.length" class="member-search-results">
              <div v-for="u in settingsSearchResults" :key="u.id" class="member-search-item" @click="addMemberToSettings(u)">
                <div class="ms-avatar" :style="{ background: avatarColor(u.name) }">{{ initials(u.name || u.email) }}</div>
                <div class="ms-info">
                  <span class="ms-name">{{ u.name || '이름없음' }}</span>
                  <span class="ms-email">{{ u.email }}</span>
                </div>
                <span class="ms-add-hint">+ 추가</span>
              </div>
            </div>
            <div class="settings-member-list">
              <div v-if="!settingsModal.members.length" class="settings-empty-members">참여자가 없습니다.</div>
              <div v-for="(mb, idx) in settingsModal.members" :key="mb.userId" class="settings-member-row">
                <div class="sm-avatar" :style="{ background: avatarColor(mb.name) }">{{ initials(mb.name) }}</div>
                <div class="sm-info">
                  <span class="sm-name">{{ mb.name }}</span>
                  <span class="sm-email">{{ mb.position || mb.department || mb.email }}</span>
                </div>
                <select v-model="mb.role" class="app-select">
                  <option v-for="(label, val) in ROLE_MAP" :key="val" :value="val">{{ label }}</option>
                </select>
                <button class="sm-remove" @click="removeMemberFromSettings(idx)" title="제거">
                  <svg width="12" height="12" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24"><path d="M18 6L6 18M6 6l12 12"/></svg>
                </button>
              </div>
            </div>
          </div>
        </div>
        <div class="app-modal-footer">
          <button class="app-btn-cancel" @click="closeSettings">취소</button>
          <button class="app-btn-primary" :disabled="!settingsModal.form.title.trim() || savingSettings" @click="saveSettings">{{ savingSettings ? '저장 중...' : '저장' }}</button>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
/* ── Page ── */
.archive-page { display:flex;flex-direction:column;margin:-24px -28px;height:calc(100% + 48px);background:#0f172a;color:#e2e8f0;overflow:hidden;position:relative; }

/* ── Header ── */
.archive-header { display:flex;align-items:center;gap:12px;padding:10px 16px;background:#0f172a;border-bottom:1px solid rgba(255,255,255,.08);flex-shrink:0;flex-wrap:wrap; }
.header-title-wrap { flex-shrink:0; }
.archive-title { font-size:16px;font-weight:700;color:#f1f5f9;margin:0; }
.archive-desc { font-size:10px;color:#475569;margin:0; }
.search-wrap { position:relative;flex:1;min-width:160px;max-width:360px; }
.search-icon { position:absolute;left:9px;top:50%;transform:translateY(-50%);color:#475569;pointer-events:none; }
.search-input { width:100%;background:rgba(255,255,255,.06);border:1px solid rgba(255,255,255,.1);border-radius:8px;padding:7px 28px;font-size:12px;color:#e2e8f0;outline:none; }
.search-input::placeholder { color:#334155; }
.search-input:focus { border-color:rgba(96,165,250,.5); }
.search-clear { position:absolute;right:7px;top:50%;transform:translateY(-50%);background:none;border:none;cursor:pointer;color:#475569;display:flex;align-items:center; }
.plus-wrap { position:relative;flex-shrink:0; }
.create-meeting-btn { display:flex;align-items:center;gap:6px;height:34px;padding:0 14px;border-radius:8px;background:#3b82f6;border:none;color:#fff;font-size:13px;font-weight:600;cursor:pointer;transition:opacity .15s;white-space:nowrap; }
.create-meeting-btn:hover { opacity:.85; }

/* ── Body ── */
/* ── Graph Breadcrumb ── */
.graph-breadcrumb {
  display: flex; align-items: center; gap: 4px;
  padding: 5px 20px;
  min-height: 32px;
  background: rgba(255,255,255,.04);
  border-bottom: 1px solid rgba(255,255,255,.07);
  font-size: 12px; color: rgba(255,255,255,.55);
  flex-shrink: 0;
}
.bc-home, .bc-item {
  background: none; border: none; cursor: pointer;
  display: flex; align-items: center; gap: 4px;
  padding: 2px 8px; border-radius: 10px;
  font-size: 12px; color: rgba(255,255,255,.55);
  transition: background .15s, color .15s;
}
.bc-home:hover, .bc-item:hover { background: rgba(255,255,255,.1); color: #fff; }
.bc-item.bc-hub { color: #93c5fd; }
.bc-item.bc-hub:hover { background: rgba(147,197,253,.12); color: #bfdbfe; }
.bc-item.bc-dept { color: #86efac; }
.bc-item.bc-dept:hover { background: rgba(134,239,172,.12); color: #bbf7d0; }
.bc-sep { opacity: .35; user-select: none; }

/* day-mode breadcrumb */
.day-mode .graph-breadcrumb {
  background: rgba(0,0,0,.03);
  border-bottom: 1px solid rgba(0,0,0,.08);
  color: rgba(30,30,30,.5);
}
.day-mode .bc-home, .day-mode .bc-item { color: rgba(30,30,30,.5); }
.day-mode .bc-home:hover, .day-mode .bc-item:hover { background: rgba(0,0,0,.07); color: #1e1e1e; }
.day-mode .bc-item.bc-hub { color: #2563eb; }
.day-mode .bc-item.bc-hub:hover { background: rgba(37,99,235,.1); }
.day-mode .bc-item.bc-dept { color: #16a34a; }
.day-mode .bc-item.bc-dept:hover { background: rgba(22,163,74,.1); }

.archive-body { flex:1;display:flex;overflow:hidden;min-height:0; }

/* Detail sidebar — absolute overlay so canvas never resizes */
.detail-sidebar { position:absolute;top:0;left:0;bottom:0;z-index:20;background:#0c0c0c;border-right:1px solid rgba(255,255,255,.07);display:flex;flex-direction:column;overflow:hidden; }
.sidebar-resize-handle { position:absolute;top:0;right:0;bottom:0;width:5px;cursor:ew-resize;z-index:10;background:transparent;transition:background .15s; }
.sidebar-resize-handle:hover { background:rgba(255,255,255,.1); }
.sidebar-slide-enter-active,.sidebar-slide-leave-active { transition:transform .28s cubic-bezier(.22,.68,0,1.2),opacity .22s; }
.sidebar-slide-enter-from,.sidebar-slide-leave-to { transform:translateX(-100%);opacity:0; }
/* Header */
.detail-header { display:flex;align-items:center;padding:14px 14px 13px;border-bottom:1px solid rgba(255,255,255,.06);flex-shrink:0;gap:10px; }
.detail-header-icon { width:30px;height:30px;border-radius:8px;background:rgba(255,255,255,.06);border:1px solid rgba(255,255,255,.08);display:flex;align-items:center;justify-content:center;color:#888;flex-shrink:0; }
.detail-header-left { flex:1;min-width:0;overflow:hidden; }
.detail-name-badge-row { display:flex;align-items:center;gap:4px;min-width:0;overflow:hidden; }
.detail-name-badge-row .detail-meeting-name { flex:0 1 auto;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap; }
.detail-name-badge-row .detail-role-badge { flex-shrink:0;margin-top:0; }
.detail-header-actions { display:flex;align-items:center;gap:4px;flex-shrink:0; }
.detail-meeting-name { font-size:13px;font-weight:700;color:#e8e8e8;white-space:nowrap;overflow:hidden;text-overflow:ellipsis; }
.detail-meta-row { display:flex;align-items:center;gap:4px;margin-top:2px;flex-wrap:wrap; }
.detail-meta { font-size:11px;color:#555; }
.detail-meta-dot { font-size:11px;color:#333; }
.detail-icon-btn { background:none;border:1px solid rgba(255,255,255,.08);cursor:pointer;color:#555;width:26px;height:26px;border-radius:6px;display:flex;align-items:center;justify-content:center;transition:all .15s;flex-shrink:0;padding:0; }
.detail-icon-btn:hover { background:rgba(255,255,255,.07);color:#aaa;border-color:rgba(255,255,255,.15); }
.detail-close { background:none;border:1px solid rgba(255,255,255,.08);cursor:pointer;color:#555;padding:0;width:26px;height:26px;border-radius:6px;display:flex;align-items:center;justify-content:center;transition:all .15s; }
.detail-close:hover { color:#ccc;background:rgba(255,255,255,.07);border-color:rgba(255,255,255,.15); }
.sidebar-toggle-handle { position:absolute;top:50%;transform:translateY(-50%);width:16px;height:48px;background:rgba(30,30,40,0.92);border:1px solid rgba(255,255,255,.1);border-left:none;border-radius:0 8px 8px 0;display:flex;align-items:center;justify-content:center;cursor:pointer;color:#64748b;z-index:25;padding:0;transition:background .15s,color .15s; }
.sidebar-toggle-handle:hover { background:rgba(50,50,70,0.98);color:#94a3b8; }
/* Body */
.dei-meta-row { display:flex;align-items:center;gap:5px;margin-top:4px;flex-wrap:wrap; }
.dei-assignee { font-size:10px;color:#64748b; }
.dei-edit-row { display:flex;gap:4px;margin-top:4px; }
.dei-select { background:rgba(255,255,255,.06);border:1px solid rgba(255,255,255,.1);border-radius:5px;padding:3px 5px;font-size:11px;color:#e2e8f0;outline:none; }
.dei-app-select { flex:1;font-size:11px;padding:4px 22px 4px 7px; }
.ctx-upload-area { margin-top:8px;border:1.5px dashed rgba(255,255,255,.12);border-radius:8px;padding:12px;display:flex;flex-direction:column;align-items:center;gap:4px;cursor:pointer;transition:border-color .18s,background .18s;color:#475569; }
.ctx-upload-area:hover { border-color:rgba(59,130,246,.5);background:rgba(59,130,246,.04);color:#64748b; }
.ctx-upload-area svg { color:#475569; }
.ctx-upload-area span { font-size:11px; }
.ctx-upload-hint { font-size:10px;color:#334155; }
.ctx-file-uploaded { background:rgba(16,185,129,.04); }
.ctx-new-tag { color:#10b981 !important;font-weight:600; }
.ctx-file-remove { margin-left:auto;background:none;border:none;color:#ef4444;cursor:pointer;font-size:13px;padding:0 2px;line-height:1; }
.ctx-section { padding:10px 0;border-bottom:1px solid rgba(255,255,255,.05); }
.ctx-section:last-of-type { border-bottom:none; }
.ctx-section-title { display:flex;align-items:center;gap:5px;font-size:10px;font-weight:700;color:#64748b;text-transform:uppercase;letter-spacing:.06em;margin-bottom:8px; }
.ctx-auto-tag { font-size:9px;padding:1px 5px;border-radius:3px;background:rgba(16,185,129,.15);color:#10b981;font-weight:600;text-transform:none;letter-spacing:0; }
.ctx-opt-tag { font-size:9px;padding:1px 5px;border-radius:3px;background:rgba(59,130,246,.15);color:#3b82f6;font-weight:600;text-transform:none;letter-spacing:0; }
.ctx-emb-tag { font-size:9px;padding:1px 5px;border-radius:3px;background:rgba(167,139,250,.15);color:#a78bfa;font-weight:600;text-transform:none;letter-spacing:0; }
.ctx-auto-list { display:flex;flex-direction:column;gap:5px; }
.ctx-auto-item { display:flex;align-items:center;gap:6px;font-size:11px;color:#94a3b8; }
.ctx-file-list { display:flex;flex-direction:column;gap:5px; }
.ctx-file-item { display:flex;align-items:center;gap:6px;font-size:11px;color:#94a3b8;cursor:pointer;padding:4px 6px;border-radius:5px;transition:background .15s; }
.ctx-file-item:hover { background:rgba(255,255,255,.04); }
.ctx-checkbox { width:12px;height:12px;accent-color:#3b82f6;cursor:pointer; }
.ctx-file-name { flex:1;color:#cbd5e1; }
.ctx-file-date { font-size:10px;color:#475569; }
.ctx-sim-score { font-size:10px;color:#a78bfa;font-weight:600; }
.ctx-empty { font-size:11px;color:#475569;padding:4px 0; }
.ctx-run-btn { width:100%;margin-top:14px;padding:9px;background:#3b82f6;border:none;border-radius:8px;color:#fff;font-size:12px;font-weight:600;cursor:pointer;display:flex;align-items:center;justify-content:center;gap:6px;transition:background .18s; }
.ctx-run-btn:hover { background:#2563eb; }
.ctx-phase-header { display:flex;align-items:center;gap:6px;padding:8px 0 10px; }
.ctx-back-btn { font-size:10px;color:#64748b;background:none;border:none;cursor:pointer;padding:0; }
.ctx-back-btn:hover { color:#94a3b8; }
.ctx-phase-label { font-size:11px;color:#475569;font-weight:600; }
.ctx-phase-label.active { color:#3b82f6; }
.ctx-phase-arrow { font-size:11px;color:#334155; }
.task-process-bar { padding:8px 0 14px;border-bottom:1px solid rgba(255,255,255,.06);margin-bottom:4px; }
.task-back-header { display:flex;justify-content:flex-end;margin-bottom:8px; }
.task-back-btn { background:none;border:1px solid rgba(255,255,255,.1);cursor:pointer;color:#555;width:26px;height:26px;border-radius:6px;display:flex;align-items:center;justify-content:center;flex-shrink:0;transition:all .15s;padding:0; }
.task-back-btn:hover { background:rgba(255,255,255,.07);color:#aaa;border-color:rgba(255,255,255,.18); }
.day-mode .task-back-btn { border-color:#e2e8f0;color:#94a3b8; }
.day-mode .task-back-btn:hover { background:#f1f5f9;color:#475569; }
.ctx-section-title-flex { display:flex;align-items:center;gap:5px;margin-bottom:8px; }
.detail-extract-footer--col { flex-direction:column;align-items:stretch;gap:8px; }
.detail-extract-footer--col .detail-action-btn { width:100%; }
.detail-extract-header { display:flex;align-items:center;justify-content:space-between;padding:10px 0 8px; }
.detail-extract-title { display:flex;align-items:center;gap:5px;font-size:11px;font-weight:700;color:#94a3b8;text-transform:uppercase;letter-spacing:.06em; }
.detail-extract-loading { display:flex;align-items:center;gap:8px;padding:14px 0;color:#64748b;font-size:12px; }
.detail-extract-meta { font-size:11px;color:#64748b;padding:4px 0 8px; }
.detail-extract-list { display:flex;flex-direction:column;gap:6px; }
.detail-extract-item { display:flex;align-items:flex-start;gap:7px;padding:9px 10px;background:rgba(255,255,255,.04);border-radius:8px;border:1px solid rgba(255,255,255,.06);transition:border-color .18s; }
.detail-extract-item.ei-approved { border-color:rgba(16,185,129,.35);background:rgba(16,185,129,.06); }
.detail-extract-item.ei-rejected { border-color:rgba(239,68,68,.25);background:rgba(239,68,68,.04);opacity:.6; }
.dei-num { font-size:10px;font-weight:700;color:#475569;min-width:16px;margin-top:2px; }
.dei-body { flex:1;min-width:0; }
.dei-title { font-size:12px;font-weight:600;color:#e2e8f0;line-height:1.4; }
.dei-bullets { margin:4px 0 0 12px;padding:0;font-size:11px;color:#64748b;line-height:1.6; }
.dei-input { width:100%;background:rgba(255,255,255,.06);border:1px solid rgba(255,255,255,.1);border-radius:5px;padding:4px 7px;font-size:12px;color:#e2e8f0;outline:none; }
.dei-textarea { width:100%;background:rgba(255,255,255,.06);border:1px solid rgba(255,255,255,.1);border-radius:5px;padding:4px 7px;font-size:11px;color:#e2e8f0;outline:none;resize:vertical;margin-top:4px; }
.dei-actions { display:flex;flex-direction:column;gap:4px; }
.detail-extract-footer { display:flex;align-items:center;justify-content:space-between;padding:10px 0 4px; }
.dei-count { font-size:11px;color:#64748b; }
.detail-divider { height:1px;background:rgba(255,255,255,.06);margin:10px 0; }
.detail-tabs { display:flex;gap:0;border-bottom:1px solid rgba(255,255,255,.07);padding:0 14px; }
.detail-tab { background:none;border:none;padding:8px 14px;font-size:12px;font-weight:600;color:#64748b;cursor:pointer;border-bottom:2px solid transparent;transition:all .18s; }
.detail-tab.active { color:#fff;border-bottom-color:#3b82f6; }
.detail-tab:hover:not(.active) { color:#94a3b8; }
.detail-tab-extract { color:#7ac8b0; }
.detail-tab-extract.active { color:#7ac8b0;border-bottom-color:#7ac8b0; }
.detail-tab-extract:hover:not(.active) { color:#a0d8c8; }
.detail-todo-list { display:flex;flex-direction:column;gap:6px;margin-top:4px; }
.todo-dept-group { margin-bottom:10px; }
.todo-dept-header { display:flex;align-items:center;justify-content:space-between;padding:4px 6px;background:rgba(255,255,255,.04);border-radius:5px;margin-bottom:5px; }
.todo-dept-name { font-size:11px;font-weight:700;color:#94a3b8; }
.todo-dept-count { font-size:10px;color:#475569; }
.upload-file-drop { border:1.5px dashed rgba(255,255,255,.15);border-radius:8px;padding:12px;display:flex;align-items:center;gap:8px;cursor:pointer;font-size:12px;color:#64748b;transition:border-color .18s,background .18s; }
.upload-file-drop:hover { border-color:rgba(59,130,246,.5);background:rgba(59,130,246,.04);color:#94a3b8; }
.detail-todo-item { display:flex;align-items:flex-start;gap:8px;padding:8px 10px;background:rgba(255,255,255,.03);border-radius:7px;border:1px solid rgba(255,255,255,.05); }
.detail-todo-status { font-size:10px;font-weight:700;padding:2px 7px;border-radius:4px;white-space:nowrap;margin-top:1px; }
.ts-done { background:rgba(16,185,129,.15);color:#10b981; }
.ts-progress { background:rgba(59,130,246,.15);color:#3b82f6; }
.ts-risk { background:rgba(239,68,68,.15);color:#ef4444; }
.ts-pending { background:rgba(100,116,139,.15);color:#94a3b8; }
.detail-todo-info { flex:1;min-width:0; }
.detail-todo-title { font-size:12px;font-weight:500;color:#e2e8f0;line-height:1.4; }
.detail-todo-meta { font-size:10px;color:#64748b;margin-top:3px; }
.detail-body { flex:1;overflow-y:auto;padding:12px 14px 20px;display:flex;flex-direction:column;gap:0; }
.detail-body::-webkit-scrollbar { width:3px; }
.detail-body::-webkit-scrollbar-track { background:transparent; }
.detail-body::-webkit-scrollbar-thumb { background:rgba(255,255,255,.08);border-radius:99px; }
/* Section */
.detail-section { display:flex;flex-direction:column;gap:6px;padding:12px 0;border-bottom:1px solid rgba(255,255,255,.04); }
.detail-section:last-child { border-bottom:none; }
.detail-section-label { font-size:10px;font-weight:700;color:#555;text-transform:uppercase;letter-spacing:.07em; }
.detail-section-label-row { display:flex;align-items:center;justify-content:space-between; }
.detail-section-label-row .detail-section-label { margin-bottom:0; }
/* gauge bar */
/* ── D-day ──────────────────────────────────────────────────── */
.dday-row { display:flex;align-items:center;gap:7px;margin-bottom:10px; }
.dday-badge { font-size:11px;font-weight:800;padding:3px 9px;border-radius:99px;letter-spacing:.02em;flex-shrink:0; }
.dday-normal { background:rgba(59,130,246,.18);color:#93c5fd; }
.dday-warning { background:rgba(245,158,11,.2);color:#fbbf24; }
.dday-critical { background:rgba(239,68,68,.22);color:#f87171; }
.dday-over { background:rgba(100,116,139,.18);color:#94a3b8; }
.dday-label { font-size:11px;color:#64748b;flex:1; }
.dday-date { font-size:10px;color:#3b4152;flex-shrink:0; }
/* ── 팀 제출 현황 ───────────────────────────────────────────── */
.dept-submit-section { display:flex;flex-direction:column;gap:5px; }
.dept-submit-header { display:flex;align-items:center;justify-content:space-between;margin-bottom:2px; }
.dept-submit-title { font-size:11px;font-weight:600;color:#64748b; }
.dept-submit-summary { font-size:10.5px;display:flex;align-items:center;gap:4px; }
.dss-done { color:#4ade80; }
.dss-sep { color:#374151; }
.dss-pending { color:#f87171; }
.dept-submit-list { display:flex;flex-direction:column;gap:3px; }
.dept-submit-item { display:flex;align-items:center;gap:6px;padding:5px 8px;border-radius:7px;background:rgba(255,255,255,.03);border:1px solid rgba(255,255,255,.05); }
.dept-submit-item.dsi-done { border-color:rgba(74,222,128,.1); }
.dept-submit-item.dsi-urgent { border-color:rgba(245,158,11,.2);background:rgba(245,158,11,.04); }
.dsi-dot { width:6px;height:6px;border-radius:50%;flex-shrink:0; }
.dsi-dot-done { background:#4ade80; }
.dsi-dot-pending { background:#64748b; }
.dsi-dot-urgent { background:#f59e0b; }
.dsi-name { flex:1;font-size:11.5px;color:#94a3b8; }
.dsi-status { font-size:10.5px;font-weight:600;flex-shrink:0; }
.dsi-status-done { color:#4ade80; }
.dsi-status-pending { color:#64748b; }
.dsi-deadline { font-size:10px;font-weight:700;padding:1px 6px;border-radius:99px;flex-shrink:0; }
.dsi-deadline-urgent { background:rgba(245,158,11,.18);color:#fbbf24; }
.dsi-deadline-critical { background:rgba(239,68,68,.2);color:#f87171; }
/* day-mode overrides */
.day-mode .dday-normal { background:rgba(59,130,246,.1);color:#1d4ed8; }
.day-mode .dday-warning { background:rgba(245,158,11,.12);color:#d97706; }
.day-mode .dday-critical { background:rgba(239,68,68,.12);color:#dc2626; }
.day-mode .dday-over { background:#f1f5f9;color:#64748b; }
.day-mode .dday-label { color:#94a3b8; }
.day-mode .dday-date { color:#cbd5e1; }
.day-mode .dept-submit-item { background:#f8fafc;border-color:#f1f5f9; }
.day-mode .dept-submit-item.dsi-done { border-color:rgba(22,163,74,.15); }
.day-mode .dept-submit-item.dsi-urgent { border-color:rgba(245,158,11,.2);background:rgba(245,158,11,.04); }
.day-mode .dsi-name { color:#475569; }
.day-mode .dss-done { color:#16a34a; }
.day-mode .dss-pending { color:#dc2626; }
/* legacy gauge (kept for other uses) */
.detail-gauge-wrap { display:flex;align-items:center;gap:8px; }
.detail-gauge-track { flex:1;height:4px;border-radius:99px;background:rgba(255,255,255,.08);overflow:hidden; }
.detail-gauge-fill { height:100%;border-radius:99px;background:rgba(134,239,172,.7);transition:width .4s ease; }
.detail-gauge-label { font-size:10.5px;color:#666;white-space:nowrap; }
/* inline stats */
.detail-inline-stats { display:flex;flex-direction:column;gap:4px; }
.detail-inline-stat { display:flex;align-items:center;gap:5px;font-size:11px;color:#555;line-height:1.4; }
.detail-inline-stat strong { color:#999;font-weight:600; }
.dis-recent { margin-left:auto;font-size:10px;color:#444; }
/* 생선 문서 */
.detail-doc-oneliner { display:flex;flex-direction:column;gap:5px; }
.detail-doc-line { display:flex;align-items:center;gap:6px;font-size:11.5px;color:#666; }
.ddl-icon { display:flex;align-items:center;flex-shrink:0; }
.ddl-type { font-size:11px;color:#777;min-width:44px; }
.ddl-count { font-weight:600;color:#999;min-width:24px; }
.ddl-recent { font-size:10.5px;color:#444;margin-left:auto; }
.detail-more-btn { font-size:10px;font-weight:600;color:#454545;background:none;border:none;cursor:pointer;padding:0;white-space:nowrap;transition:color .15s; }
.detail-more-btn:hover { color:#999; }
/* ── Relationship manager ── */
.rel-add-trigger { color:#7c6fe0; }
.rel-add-trigger:hover { color:#a78bfa; }
.rel-list { display:flex;flex-direction:column;gap:4px;margin-top:6px; }
.rel-item { display:flex;align-items:center;justify-content:space-between;gap:6px;padding:5px 7px;border-radius:6px;background:rgba(255,255,255,.04);border:1px solid rgba(255,255,255,.06);min-height:30px; }
.rel-item-main { display:flex;align-items:center;gap:5px;flex:1;min-width:0; }
.rel-dir { font-size:11px;font-weight:700;color:#a78bfa;flex-shrink:0; }
.rel-badge { font-size:9px;font-weight:700;color:#fff;padding:2px 5px;border-radius:4px;flex-shrink:0;letter-spacing:.04em; }
.rel-target-name { font-size:11px;color:#bbb;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;max-width:110px; }
.rel-item-actions { display:flex;gap:3px;flex-shrink:0; }
.rel-edit-row { display:flex;align-items:center;gap:5px;width:100%; }
.rel-type-select { flex:1;background:#1e1e2e;border:1px solid rgba(255,255,255,.12);color:#ccc;border-radius:5px;font-size:11px;padding:4px 6px;cursor:pointer;min-width:0; }
.rel-type-select:focus { outline:none;border-color:#7c6fe0; }
.rel-btn { display:inline-flex;align-items:center;justify-content:center;border:none;cursor:pointer;border-radius:4px;padding:4px 7px;font-size:11px;font-weight:600;transition:all .15s; }
.rel-btn-edit   { background:rgba(99,102,241,.15);color:#818cf8; }
.rel-btn-edit:hover { background:rgba(99,102,241,.28); }
.rel-btn-delete { background:rgba(239,68,68,.12);color:#f87171; }
.rel-btn-delete:hover { background:rgba(239,68,68,.25); }
.rel-btn-save   { background:rgba(16,185,129,.15);color:#34d399; }
.rel-btn-save:hover { background:rgba(16,185,129,.28); }
.rel-btn-cancel { background:rgba(107,114,128,.12);color:#9ca3af; }
.rel-btn-cancel:hover { background:rgba(107,114,128,.25); }
.rel-node-section { margin-top:4px; }
.rel-add-panel { border:1px solid rgba(167,139,250,.18);border-radius:8px;background:rgba(167,139,250,.04);padding:10px; }
.rel-add-form { display:flex;flex-direction:column;gap:7px; }
.rel-add-field { display:flex;flex-direction:column;gap:3px; }
.rel-add-label { font-size:10px;font-weight:600;color:#666;text-transform:uppercase;letter-spacing:.06em; }
/* 소개 */
.detail-purpose { font-size:11.5px;color:#777;line-height:1.65;padding:0 1px; }
/* 간사·참여부서 key-value 행 */
.detail-kv-row { display:flex;align-items:baseline;gap:10px;margin-bottom:4px; }
.detail-kv-val { flex:1;font-size:11px;color:#999;line-height:1.5; }
/* 기존 호환용 (session/task 노드 등) */
.detail-info-grid { display:flex;flex-direction:column;gap:7px; }
.detail-info-item { display:flex;align-items:baseline;gap:10px;font-size:11.5px; }
.detail-info-key { width:48px;flex-shrink:0;color:#444;font-weight:600;font-size:11px; }
.detail-info-val { flex:1;color:#999;line-height:1.5; }
/* 진행 현황 */
.detail-metrics { display:flex;flex-direction:column;gap:12px; }
.detail-metric-row { display:flex;flex-direction:column;gap:5px; }
.detail-metric-header { display:flex;align-items:center;justify-content:space-between; }
.detail-metric-label { display:flex;align-items:center;gap:5px;font-size:11px;font-weight:600;color:#666; }
.detail-metric-val { font-size:11px;font-weight:700;color:#ccc; }
.detail-metric-track { height:3px;background:rgba(255,255,255,.06);border-radius:99px;overflow:hidden;display:flex;gap:1px; }
.detail-metric-fill { height:100%;border-radius:99px;transition:width .6s cubic-bezier(.22,.68,0,1.2); }
.mf-minutes { background:rgba(200,200,200,.5); }
.mf-reports { background:rgba(160,160,200,.5); }
.mf-tasks { background:rgba(120,220,150,.55); }
.detail-metric-sub { font-size:10px;color:#404040; }
/* 과제 버튼 */
.detail-action-row { display:flex;gap:7px;padding:12px 0; }
.detail-action-btn { flex:1;display:flex;align-items:center;justify-content:center;gap:5px;padding:8px 8px;border-radius:8px;font-size:11px;font-weight:600;cursor:pointer;transition:all .18s;border:1px solid; }
.btn-extract { background:rgba(251,191,36,.06);color:#a08040;border-color:rgba(251,191,36,.15); }
.btn-extract:hover { background:rgba(251,191,36,.13);color:#d4a830;border-color:rgba(251,191,36,.3); }
.btn-assign { background:rgba(99,179,237,.06);color:#4a80a0;border-color:rgba(99,179,237,.15); }
.btn-assign:hover { background:rgba(99,179,237,.13);color:#63b3ed;border-color:rgba(99,179,237,.3); }
/* 로그 */
.detail-log-list { display:flex;flex-direction:column;gap:1px; }
.detail-log-item { display:flex;align-items:flex-start;gap:9px;padding:7px 8px;border-radius:6px;transition:background .12s; }
.detail-log-item:hover { background:rgba(255,255,255,.03); }
.detail-log-dot { width:6px;height:6px;border-radius:50%;flex-shrink:0;margin-top:4px; }
.ht-minutes { background:#6b8cba; }
.ht-report { background:#7aab8a; }
.ht-approved { background:#b0b87a; }
.detail-log-content { flex:1;min-width:0; }
.detail-log-desc { font-size:11.5px;color:#bbb;overflow:hidden;text-overflow:ellipsis;white-space:nowrap; }
.detail-log-meta { font-size:10px;color:#454545;margin-top:2px; }
.detail-log-empty { font-size:11px;color:#3a3a3a;padding:6px 8px; }
/* 문서 (회의록/보고서) */
.detail-doc-item { display:flex;align-items:center;gap:9px;padding:6px 8px;border-radius:6px;cursor:pointer;transition:background .12s; }
.detail-doc-item:hover { background:rgba(255,255,255,.03); }
.detail-doc-icon { width:24px;height:24px;border-radius:5px;display:flex;align-items:center;justify-content:center;flex-shrink:0; }
.doc-minutes { background:rgba(100,140,190,.12);color:#6a8cba; }
.doc-report { background:rgba(100,180,130,.1);color:#6aab8a; }
.detail-doc-info { flex:1;min-width:0; }
.detail-doc-name { font-size:11.5px;color:#c0c0c0;font-weight:500;overflow:hidden;text-overflow:ellipsis;white-space:nowrap; }
.detail-doc-date { font-size:10px;color:#454545;margin-top:1px; }
/* 구성원 */
.detail-member-list { display:flex;flex-direction:column;gap:1px; }
.detail-member-row { display:flex;align-items:center;gap:9px;padding:5px 8px;border-radius:6px;transition:background .12s; }
.detail-member-row:hover { background:rgba(255,255,255,.03); }
.detail-member-avatar { width:24px;height:24px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:10px;font-weight:700;color:#fff;flex-shrink:0; }
.detail-member-info { flex:1;min-width:0;display:flex;flex-direction:column;gap:1px; }
.detail-member-name { font-size:11.5px;font-weight:500;color:#c0c0c0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap; }
.detail-member-dept { font-size:10px;color:#454545;overflow:hidden;text-overflow:ellipsis;white-space:nowrap; }
/* 과제 모달 공통 */
.gm-modal-title { display:flex;align-items:center;gap:8px;font-size:14px;font-weight:700;color:var(--text); }
.gm-modal-ai-tag { font-size:10px;font-weight:600;padding:2px 7px;border-radius:4px;background:var(--surface-raised,rgba(0,0,0,.06));color:var(--text-muted);border:1px solid var(--border);letter-spacing:.02em; }
.gm-body-inner { padding:16px 20px;display:flex;flex-direction:column;gap:10px;min-height:220px; }
/* 로딩 */
.gm-loading-block { display:flex;align-items:center;justify-content:center;gap:14px;padding:48px 20px; }
.gm-spinner { width:18px;height:18px;border:2px solid var(--border);border-top-color:var(--text-muted);border-radius:50%;animation:gm-spin .7s linear infinite;flex-shrink:0; }
@keyframes gm-spin { to { transform:rotate(360deg) } }
.gm-loading-text { display:flex;flex-direction:column;gap:3px; }
.gm-loading-main { font-size:13px;font-weight:600;color:var(--text); }
.gm-loading-sub { font-size:11px;color:var(--text-muted); }
/* 빈 */
.gm-empty-block { display:flex;flex-direction:column;align-items:center;justify-content:center;gap:10px;padding:48px 20px;color:var(--text-muted);font-size:12px; }
/* 메타 */
.gm-list-meta { font-size:11.5px;color:var(--text-muted);line-height:1.6;padding:2px 0 4px; }
/* 과제 추출 리스트 */
.gm-extract-list { display:flex;flex-direction:column;gap:4px; }
.gm-extract-item { display:flex;align-items:flex-start;gap:0;border-radius:8px;border:1px solid var(--border);background:var(--surface-raised,rgba(0,0,0,.03));overflow:hidden;transition:opacity .15s; }
.gm-extract-item.ei-approved { border-color:rgba(120,170,120,.35);background:rgba(120,170,120,.05); }
.gm-extract-item.ei-rejected { opacity:.45; }
.gm-ei-left { width:36px;flex-shrink:0;display:flex;align-items:flex-start;justify-content:center;padding:12px 0;border-right:1px solid var(--border); }
.gm-ei-num { font-size:11px;font-weight:700;color:var(--text-muted); }
.gm-ei-body { flex:1;padding:11px 12px;min-width:0; }
.gm-ei-title { font-size:13px;font-weight:600;color:var(--text);margin-bottom:5px; }
.gm-ei-bullets { margin:0;padding-left:14px;display:flex;flex-direction:column;gap:3px; }
.gm-ei-bullets li { font-size:11.5px;color:var(--text-muted);line-height:1.5; }
.gm-ei-actions { display:flex;flex-direction:column;gap:2px;padding:8px 7px;border-left:1px solid var(--border);flex-shrink:0; }
/* 배정 리스트 */
.gm-assign-list { display:flex;flex-direction:column;gap:4px; }
.gm-assign-item { display:flex;align-items:stretch;border-radius:8px;border:1px solid var(--border);background:var(--surface-raised,rgba(0,0,0,.03));overflow:hidden;transition:opacity .15s; }
.gm-assign-item.ai-approved { border-color:rgba(120,170,120,.35);background:rgba(120,170,120,.05); }
.gm-assign-item.ai-rejected { opacity:.4; }
.gm-ai-status-bar { width:3px;flex-shrink:0; }
.asb-done { background:rgba(100,160,100,.5); }
.asb-in_progress { background:rgba(100,130,180,.5); }
.asb-pending { background:var(--border); }
.asb-at_risk { background:rgba(180,140,60,.5); }
.asb-delayed { background:rgba(180,80,80,.5); }
.gm-ai-main { flex:1;padding:10px 12px;min-width:0; }
.gm-ai-row1 { display:flex;align-items:flex-start;justify-content:space-between;gap:8px;margin-bottom:5px; }
.gm-ai-content { font-size:12.5px;font-weight:600;color:var(--text);flex:1;min-width:0; }
.gm-ai-content.ai-rejected-text { text-decoration:line-through;color:var(--text-muted); }
.gm-ai-chips { display:flex;gap:4px;flex-shrink:0; }
.gm-ai-row2 { display:flex;align-items:center;gap:5px;font-size:11px;color:var(--text-muted); }
.gm-ai-dept { opacity:.6; }
.gm-ai-actions { display:flex;flex-direction:column;gap:2px;padding:8px 7px;border-left:1px solid var(--border);flex-shrink:0; }
/* 칩 - 단색 */
.gm-chip { font-size:10px;font-weight:600;padding:2px 6px;border-radius:4px;white-space:nowrap;border:1px solid var(--border);background:var(--surface-raised,rgba(0,0,0,.04));color:var(--text-muted); }
.cp-urgent_important { color:var(--text);border-color:var(--border); }
.cp-important,.cp-urgent { color:var(--text-muted); }
.cs-done { color:var(--text); }
.cs-submitted { color:#fb923c;font-weight:600; }
.cs-in_progress { color:var(--text-muted); }
.cs-pending,.cs-at_risk,.cs-delayed { color:var(--text-muted);opacity:.8; }
/* 액션 버튼 */
.gm-ei-btn { width:24px;height:24px;border-radius:5px;border:1px solid var(--border);background:none;cursor:pointer;display:flex;align-items:center;justify-content:center;color:var(--text-muted);transition:all .12s; }
.gm-ei-btn:hover { background:var(--surface-raised,rgba(0,0,0,.06)); }
.gm-ei-edit:hover { color:var(--text); }
.gm-ei-approve { color:var(--text-muted); }
.gm-ei-approve:hover { color:rgba(100,160,100,1);border-color:rgba(100,160,100,.4);background:rgba(100,160,100,.08); }
.gm-ei-approved-active { color:rgba(80,150,80,1)!important;border-color:rgba(80,150,80,.45)!important;background:rgba(80,150,80,.1)!important; }
.gm-ei-reject { color:var(--text-muted); }
.gm-ei-reject:hover { color:rgba(180,80,80,1);border-color:rgba(180,80,80,.4);background:rgba(180,80,80,.08); }
.gm-ei-rejected-active { color:rgba(180,80,80,1)!important;border-color:rgba(180,80,80,.45)!important;background:rgba(180,80,80,.1)!important; }
.gm-ei-save { color:rgba(80,150,80,.9);border-color:rgba(80,150,80,.3); }
.gm-ei-save:hover { background:rgba(80,150,80,.12); }
.gm-ei-cancel-edit { color:var(--text-muted); }
/* 편집 인풋 */
.gm-ei-input { width:100%;padding:5px 8px;border-radius:5px;border:1px solid var(--border);background:var(--surface,#fff);color:var(--text);font-size:12px;outline:none;margin-bottom:5px;box-sizing:border-box; }
.gm-ei-input:focus { border-color:var(--text-muted); }
.gm-ei-textarea { width:100%;padding:5px 8px;border-radius:5px;border:1px solid var(--border);background:var(--surface,#fff);color:var(--text);font-size:11.5px;outline:none;resize:vertical;font-family:inherit;box-sizing:border-box; }
.gm-ei-select { flex:1;padding:5px 7px;border-radius:5px;border:1px solid var(--border);background:var(--surface,#fff);color:var(--text);font-size:11.5px;outline:none;cursor:pointer; }
.gm-edit-row { display:flex;gap:5px;align-items:center; }
.gm-edit-half { flex:1;margin-bottom:0; }
/* 추가 버튼 */
.gm-add-btn { align-self:flex-start;display:flex;align-items:center;gap:5px;padding:5px 10px;border-radius:6px;border:1px dashed var(--border);background:none;color:var(--text-muted);font-size:11.5px;cursor:pointer;transition:all .12s;margin-top:2px; }
.gm-add-btn:hover { border-color:var(--text-muted);color:var(--text); }
/* footer */
.gm-footer-count { font-size:11px;color:var(--text-muted);flex-shrink:0;align-self:center; }
.gm-btn-secondary { padding:7px 14px;border-radius:7px;border:1px solid var(--border);background:none;color:var(--text-muted);font-size:13px;cursor:pointer;transition:all .15s; }
.gm-btn-secondary:hover { background:var(--surface-raised,rgba(0,0,0,.05));color:var(--text); }
.gm-btn-primary { padding:7px 14px;border-radius:7px;border:1px solid var(--border);background:var(--surface-raised,rgba(0,0,0,.06));color:var(--text);font-size:13px;font-weight:600;cursor:pointer;transition:all .15s; }
.gm-btn-primary:hover:not(:disabled) { background:var(--surface-hover,rgba(0,0,0,.1));border-color:var(--text-muted); }
.gm-btn-primary:disabled { opacity:.35;cursor:not-allowed; }

.detail-section { display:flex;flex-direction:column;gap:4px; }
.detail-section-label { font-size:10px;font-weight:700;color:#3a3a3a;text-transform:uppercase;letter-spacing:.06em;margin-bottom:2px; }
.detail-doc-item { display:flex;align-items:center;gap:7px;padding:5px 6px;border-radius:5px;background:rgba(255,255,255,.02);border:1px solid rgba(255,255,255,.04); }
.detail-doc-icon { width:22px;height:22px;border-radius:4px;display:flex;align-items:center;justify-content:center;flex-shrink:0; }
.detail-doc-icon.minutes { background:rgba(255,255,255,.06);color:#888; }
.detail-doc-icon.report { background:rgba(255,255,255,.06);color:#888; }
.detail-doc-info { flex:1;min-width:0; }
.detail-doc-name { font-size:11px;color:#bbb;font-weight:500;overflow:hidden;text-overflow:ellipsis;white-space:nowrap; }
.detail-doc-date { font-size:10px;color:#444; }
.detail-dept-table { width:100%;border-collapse:collapse;font-size:11px; }
.detail-dept-table td { padding:3px 4px;border-bottom:1px solid rgba(255,255,255,.05);vertical-align:middle; }
.detail-dept-table tr:last-child td { border-bottom:none; }
.dept-name { color:#cbd5e1;font-weight:500; }
.dept-count { color:#475569;text-align:right;white-space:nowrap; }
.detail-action-row { display:flex;gap:7px;padding:12px 0; }

/* ── Main area ── */
.main-area { flex:1;position:relative;overflow:hidden;min-width:0; }
/* ── Map drag invalid toast ── */
.map-toast { position:absolute;top:16px;left:50%;transform:translateX(-50%);background:rgba(15,23,42,.88);color:#e2e8f0;padding:8px 20px;border-radius:10px;font-size:12px;font-weight:600;z-index:30;pointer-events:none;backdrop-filter:blur(6px);border:1px solid rgba(255,255,255,.12);white-space:nowrap;box-shadow:0 4px 16px rgba(0,0,0,.3); }

/* ── Neo4j query HUD ── */
.query-hud {
  position: absolute;
  bottom: 58px;
  left: 50%;
  transform: translateX(-50%);
  background: rgba(23, 20, 60, 0.93);
  color: #c4b5fd;
  padding: 7px 18px 7px 12px;
  border-radius: 20px;
  font-size: 11.5px;
  font-weight: 600;
  border: 1px solid rgba(139, 92, 246, 0.45);
  backdrop-filter: blur(10px);
  display: flex;
  align-items: center;
  gap: 8px;
  z-index: 30;
  pointer-events: none;
  max-width: 420px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  box-shadow: 0 0 24px rgba(99, 102, 241, 0.28), 0 4px 16px rgba(0,0,0,.35);
}
.query-hud-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #818cf8;
  flex-shrink: 0;
  box-shadow: 0 0 8px #818cf8, 0 0 16px rgba(129,140,248,0.5);
  animation: qhud-blink 0.75s ease-in-out infinite;
}
@keyframes qhud-blink {
  0%, 100% { opacity: 1; transform: scale(1); }
  50%       { opacity: 0.3; transform: scale(0.75); }
}
.query-hud-text {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-family: 'JetBrains Mono', 'Fira Code', ui-monospace, monospace;
  letter-spacing: -0.01em;
}
/* HUD transition */
.query-hud-fade-enter-active, .query-hud-fade-leave-active {
  transition: opacity 0.25s ease, transform 0.25s ease;
}
.query-hud-fade-enter-from, .query-hud-fade-leave-to {
  opacity: 0;
  transform: translateX(-50%) translateY(8px);
}
.map-toast-fade-enter-active,.map-toast-fade-leave-active { transition:opacity .2s,transform .2s; }
.map-toast-fade-enter-from,.map-toast-fade-leave-to { opacity:0;transform:translateX(-50%) translateY(-6px); }
.archive-canvas { width:100%;height:100%;cursor:grab;display:block; }
.archive-canvas:active { cursor:grabbing; }
.graph-loading { width:100%;height:100%;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:12px;color:#475569;font-size:13px; }
.graph-loading-spinner { width:28px;height:28px;border:2px solid rgba(96,165,250,.2);border-top-color:#60a5fa;border-radius:50%;animation:spin .8s linear infinite; }

/* Zoom controls */
.graph-zoom-controls {
  position:absolute; top:10px; z-index:30;
  display:flex; flex-direction:column; gap:3px;
  pointer-events:all;
}
.zoom-btn {
  width:30px; height:30px; border-radius:7px;
  background:rgba(15,23,42,.75); border:1px solid rgba(255,255,255,.15);
  color:#94a3b8; font-size:16px; font-weight:700; line-height:1;
  display:flex; align-items:center; justify-content:center;
  cursor:pointer; transition:all .15s;
  backdrop-filter:blur(6px);
}
.zoom-btn:hover { background:rgba(59,130,246,.35); border-color:rgba(96,165,250,.5); color:#93c5fd; }
.zoom-reset { font-size:14px; }
.zoom-pan { font-size:14px; }
.zoom-btn.active { background:rgba(59,130,246,.5); border-color:rgba(96,165,250,.7); color:#bfdbfe; }
.day-mode .zoom-btn { background:rgba(255,255,255,.85); border-color:#e2e8f0; color:#475569; }
.day-mode .zoom-btn:hover { background:#dbeafe; border-color:#93c5fd; color:#1d4ed8; }
.day-mode .zoom-btn.active { background:#dbeafe; border-color:#93c5fd; color:#1d4ed8; }
@keyframes spin { to { transform:rotate(360deg); } }
.graph-legend { position:absolute;bottom:14px;left:14px;display:flex;align-items:center;gap:10px;flex-wrap:wrap;background:rgba(15,23,42,.75);backdrop-filter:blur(8px);border:1px solid rgba(255,255,255,.07);border-radius:8px;padding:6px 12px;font-size:11px;color:#64748b; }
.legend-item { display:flex;align-items:center;gap:5px; }
.legend-dot { width:9px;height:9px;border-radius:50%;flex-shrink:0; }
.hub-critical { background:#ef4444;box-shadow:0 0 6px rgba(239,68,68,.6); }
.hub-warning { background:#f59e0b; }
.hub-dot { background:#3b82f6; }
.hub-ended { background:#475569;opacity:.5; }
.doc-dot { background:#1e3a8a;border:1px solid #60a5fa; }
.dept-dot { background:#475569;border:1px solid #94a3b8;clip-path:polygon(50% 0%,93% 25%,93% 75%,50% 100%,7% 75%,7% 25%); }
.person-dot { background:#7c3aed;border:1px solid #a78bfa; }
.legend-sep { width:1px;height:14px;background:rgba(255,255,255,.08); }
.legend-hint { opacity:.55;font-size:10px; }

/* ── List view ── */
.list-view { position:absolute;inset:0;overflow-y:auto;background:#0a0f1e;display:flex;flex-direction:column;align-items:center; }
.lv-inner { width:100%;padding:24px 28px;display:flex;flex-direction:column;gap:0; }
.lv-th-secretary { width:120px;text-align:left; }
.lv-td-secretary { width:120px; }
.lv-secretary-text { font-size:11px;color:var(--text-muted); }
.lv-secretary-empty { font-size:11px;color:#334155; }
.lv-th-secretary { width:120px;text-align:left; }
.lv-td-secretary { width:120px; }
.list-view::-webkit-scrollbar { width:4px; }
.list-view::-webkit-scrollbar-thumb { background:rgba(255,255,255,.08); }
.list-header { display:flex;align-items:center;justify-content:space-between;padding:12px 16px 8px;border-bottom:1px solid rgba(255,255,255,.06);flex-shrink:0; }
.list-title { font-size:13px;font-weight:600;color:#94a3b8; }
.list-count { font-size:11px;color:#334155; }
.list-empty { text-align:center;padding:40px;color:#334155;font-size:13px; }
.meeting-groups { padding:8px;display:flex;flex-direction:column;gap:5px; }
.meeting-group { background:rgba(255,255,255,.03);border:1px solid rgba(255,255,255,.07);border-radius:8px;overflow:hidden; }
.group-header { display:flex;align-items:center;justify-content:space-between;padding:10px 12px;cursor:pointer;transition:background .15s; }
.group-header:hover { background:rgba(255,255,255,.04); }
.group-header-left { display:flex;align-items:center;gap:8px;min-width:0; }
.group-dot { width:7px;height:7px;background:#60a5fa;border-radius:50%;flex-shrink:0; }
.group-title { font-size:13px;font-weight:600;color:#e2e8f0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap; }
.group-type-text { font-size:11px;font-weight:600;color:#60a5fa;white-space:nowrap;flex-shrink:0; }
.group-meta-right { display:flex;align-items:center;gap:6px;flex-shrink:0; }
.group-count { font-size:11px;color:#334155; }
.group-body { border-top:1px solid rgba(255,255,255,.05);padding:8px 12px;display:flex;flex-direction:column;gap:8px; }
.doc-section { display:flex;flex-direction:column;gap:3px; }
.doc-section-label { font-size:10px;font-weight:600;color:#334155;text-transform:uppercase;letter-spacing:.06em;margin-bottom:3px; }
.doc-item { display:flex;align-items:center;gap:8px;padding:5px 7px;border-radius:5px;background:rgba(255,255,255,.02);border:1px solid rgba(255,255,255,.04); }
.doc-icon { width:22px;height:22px;border-radius:4px;display:flex;align-items:center;justify-content:center;flex-shrink:0; }
.minutes-icon { background:rgba(59,130,246,.2);color:#60a5fa; }
.report-icon { background:rgba(16,185,129,.2);color:#34d399; }
.doc-info { flex:1;min-width:0; }
.doc-name { font-size:12px;color:#cbd5e1;font-weight:500;overflow:hidden;text-overflow:ellipsis;white-space:nowrap; }
.doc-meta { font-size:10px;color:#334155;margin-top:1px; }
.doc-actions { display:flex;align-items:center;gap:3px;flex-shrink:0; }
.doc-btn { display:flex;align-items:center;background:rgba(255,255,255,.06);border:1px solid rgba(255,255,255,.09);border-radius:4px;padding:2px 7px;font-size:11px;color:#64748b;cursor:pointer;transition:all .15s; }
.doc-btn:hover { background:rgba(96,165,250,.15);color:#93c5fd;border-color:rgba(96,165,250,.3); }
.icon-only { padding:3px 5px; }
.member-chips { display:flex;flex-wrap:wrap;gap:4px; }
.member-chip { display:flex;align-items:center;gap:4px;background:rgba(124,58,237,.15);border:1px solid rgba(124,58,237,.25);border-radius:20px;padding:2px 7px 2px 3px; }
.member-avatar { width:17px;height:17px;border-radius:50%;background:rgba(124,58,237,.5);color:#fff;font-size:9px;font-weight:700;display:flex;align-items:center;justify-content:center; }
.member-name { font-size:11px;color:#c4b5fd; }
.member-role { font-size:9px;font-weight:600;padding:1px 5px;border-radius:99px; }
.role-admin { background:rgba(251,191,36,.2);color:#fbbf24; }
.role-presenter { background:rgba(96,165,250,.15);color:#60a5fa; }

/* ── Bottom panel ── */
.bottom-panel { position:absolute;left:0;right:0;bottom:0;height:46%;background:#fff;border-top:2px solid #e2e8f0;transform:translateY(100%);transition:transform .3s ease;z-index:50;display:flex;flex-direction:column;overflow:hidden; }
.bottom-panel.active { transform:translateY(0); }
.bottom-drag-handle { flex-shrink:0;height:18px;display:flex;align-items:center;justify-content:center;cursor:ns-resize;background:#f8fafc;border-bottom:1px solid #f1f5f9;user-select:none; }
.drag-bar { width:40px;height:4px;border-radius:2px;background:#cbd5e1; }
.bottom-drag-handle:hover .drag-bar { background:#94a3b8; }
.bottom-inner { display:flex;flex:1;overflow:hidden; }
.bottom-left { flex:1.4;border-right:1px solid #e2e8f0;display:flex;flex-direction:column;overflow:hidden; }
.bottom-right { flex:1;display:flex;flex-direction:column;overflow:hidden; }
.bottom-panel-label { font-size:11px;font-weight:700;color:#64748b;text-transform:uppercase;letter-spacing:.04em;padding:8px 14px 6px;border-bottom:1px solid #f1f5f9;flex-shrink:0; }
.task-form-scroll { flex:1;overflow-y:auto;padding:8px 12px;display:flex;flex-direction:column;gap:5px; }
.tf-row { display:flex;align-items:center;gap:8px;min-height:32px; }
.tf-row-top { align-items:flex-start; }
.tf-label { width:60px;flex-shrink:0;font-size:11px;font-weight:600;color:#64748b;text-align:right; }
.tf-input { flex:1;padding:5px 8px;border:1px solid #e2e8f0;border-radius:6px;font-size:12px;color:#1e293b;outline:none;background:#f8fafc;font-family:inherit;min-width:0; }
.tf-input:focus { border-color:#3b82f6;background:#fff; }
.tf-select { cursor:pointer; }
.tf-textarea { resize:none;height:52px;line-height:1.4; }
.tag-input-wrap { flex:1;display:flex;flex-wrap:wrap;align-items:center;gap:3px;border:1px solid #e2e8f0;border-radius:6px;padding:3px 7px;background:#f8fafc;min-height:32px;min-width:0; }
.dept-tag { display:inline-flex;align-items:center;gap:2px;background:#eff6ff;border:1px solid #bfdbfe;border-radius:4px;padding:1px 5px;font-size:11px;color:#1d4ed8; }
.tag-rm { background:none;border:none;cursor:pointer;font-size:12px;color:#6b7280;padding:0;line-height:1; }
.tag-bare-input { border:none;outline:none;font-size:12px;background:none;min-width:50px;flex:1; }
.task-form-footer { display:flex;gap:6px;padding:8px 12px;border-top:1px solid #f1f5f9;flex-shrink:0; }
.tf-btn-save { padding:6px 16px;border-radius:6px;border:none;background:#3b82f6;color:#fff;font-size:12px;font-weight:600;cursor:pointer; }
.tf-btn-cancel { padding:6px 12px;border-radius:6px;border:1px solid #e2e8f0;background:#fff;color:#64748b;font-size:12px;cursor:pointer; }
.ai-reason-title { font-size:11px;font-weight:700;color:#64748b;text-transform:uppercase;letter-spacing:.04em;padding:8px 14px 6px;border-bottom:1px solid #f1f5f9;flex-shrink:0; }
.ai-reason-body { flex:1;padding:10px 14px;font-size:12px;color:#475569;line-height:1.7;overflow-y:auto; }
.upload-area { flex:1;margin:10px 14px;border:2px dashed #cbd5e1;border-radius:10px;display:flex;flex-direction:column;align-items:center;justify-content:center;cursor:pointer;min-height:80px; }
.upload-area:hover { border-color:#3b82f6; }
.bottom-approve-row { display:flex;gap:8px;padding:8px 14px;border-top:1px solid #f1f5f9;flex-shrink:0;justify-content:flex-end; }
.btn-approve { padding:7px 18px;border-radius:8px;border:none;background:#3b82f6;color:#fff;font-size:13px;font-weight:700;cursor:pointer; }
.btn-reject { padding:7px 14px;border-radius:8px;border:1px solid #e2e8f0;background:#fff;color:#64748b;font-size:13px;cursor:pointer; }

/* ── Agent header button ── */
.agent-header-btn { height:34px;padding:0 10px;gap:4px;border-radius:8px;border:1px solid rgba(123,128,204,.4);background:rgba(100,110,200,.14);display:flex;align-items:center;justify-content:center;cursor:pointer;flex-shrink:0;transition:all .15s; }
.agent-header-btn:hover { background:rgba(123,128,204,.28);border-color:rgba(123,128,204,.65); }
.agent-header-btn.active { background:rgba(123,128,204,.35);border-color:#7b80cc;box-shadow:0 0 0 2px rgba(123,128,204,.25); }
.ai-btn-icon { width:28px;height:14px;flex-shrink:0; }
.ai-btn-label { font-size:11px;font-weight:600;color:#93c5fd;letter-spacing:0.02em;flex-shrink:0; }

/* ── Agent right sidebar ── */
.agent-right-sidebar { position:absolute;top:0;right:0;bottom:0;width:320px;background:#fff;border-left:1px solid rgba(0,0,0,.1);display:flex;flex-direction:column;overflow:hidden;z-index:50; }
.agent-sidebar-slide-enter-active,.agent-sidebar-slide-leave-active { transition:transform .25s ease,opacity .2s; }
.agent-sidebar-slide-enter-from,.agent-sidebar-slide-leave-to { transform:translateX(100%);opacity:0; }
/* Supervisor single header (탭 없음) */
.agent-supervisor-header { display:flex;align-items:center;justify-content:space-between;padding:10px 12px;border-bottom:1px solid var(--border);background:linear-gradient(135deg,#eff6ff 0%,#f0fdf4 100%);flex-shrink:0; }
.supervisor-brand { display:flex;align-items:center;gap:8px;flex:1;min-width:0; }
.supervisor-logo { width:30px;height:30px;border-radius:50%;object-fit:cover;border:2px solid #93c5fd;flex-shrink:0; }
.supervisor-brand-text { display:flex;flex-direction:column;min-width:0;flex:1; }
.supervisor-title { font-size:13px;font-weight:700;color:#1e293b;white-space:nowrap;overflow:hidden;text-overflow:ellipsis; }
.supervisor-sub { font-size:10px;color:#64748b;white-space:nowrap;overflow:hidden;text-overflow:ellipsis; }

.supervisor-header-actions { display:flex;align-items:center;gap:5px;flex-shrink:0; }
.agent-sidebar-close { width:26px;height:26px;border-radius:6px;border:none;background:#f1f5f9;color:#64748b;cursor:pointer;font-size:12px;display:flex;align-items:center;justify-content:center;flex-shrink:0; }
.agent-sidebar-close:hover { background:#e2e8f0;color:#1e293b; }
.agent-sidebar-info { display:flex;align-items:center;gap:8px;padding:8px 12px;border-bottom:1px solid var(--border);flex-shrink:0; }
.agent-sidebar-avatar { width:28px;height:28px;border-radius:50%;object-fit:cover;flex-shrink:0; }
.agent-sidebar-text { flex:1;min-width:0; }
.agent-sidebar-name { font-size:12px;font-weight:700;color:#1e293b;white-space:nowrap;overflow:hidden;text-overflow:ellipsis; }
.agent-sidebar-en { font-weight:400;color:#64748b;font-size:11px; }
.agent-sidebar-subtitle { font-size:10px;color:#94a3b8; }
.agent-new-chat-btn { background:none;border:1px solid var(--border);border-radius:6px;padding:3px 9px;font-size:11px;color:var(--text-muted);cursor:pointer;transition:all .15s;flex-shrink:0;white-space:nowrap; }
.agent-new-chat-btn:hover { background:#eff6ff;border-color:#93c5fd;color:var(--primary); }
.agent-messages { flex:1;overflow-y:auto;padding:8px;display:flex;flex-direction:column;gap:7px; }
.agent-messages::-webkit-scrollbar { width:3px; }
.agent-messages::-webkit-scrollbar-thumb { background:#e2e8f0; }
.agent-msg-row { display:flex;flex-direction:column;gap:3px; }
.agent-msg-row.user { align-items:flex-end; }
.agent-msg-label { display:flex;align-items:center;gap:4px;font-size:11px;font-weight:600;color:var(--text-muted); }
.agent-msg-avatar { width:15px;height:15px;border-radius:50%;object-fit:cover; }
.agent-bubble { padding:8px 11px;border-radius:10px;font-size:13px;line-height:1.55;max-width:90%;word-break:break-word;border:1px solid transparent; }
.agent-bubble.user { background:var(--primary);color:#fff;border-radius:10px 10px 2px 10px; }
.agent-bubble.agent.theme-supervisor { background:linear-gradient(135deg,#eff6ff,#f0fdf4);border-color:#93c5fd;color:#1e3a5f;border-radius:2px 10px 10px 10px; }
.agent-bubble.agent.theme-hyean { background:#eff6ff;border-color:#93c5fd;color:#1e40af;border-radius:2px 10px 10px 10px; }
.agent-bubble.agent.theme-gaon  { background:#fef3c7;border-color:#fcd34d;color:#78350f;border-radius:2px 10px 10px 10px; }
.agent-bubble.agent.theme-naru  { background:#ecfdf5;border-color:#6ee7b7;color:#064e3b;border-radius:2px 10px 10px 10px; }
.agent-bubble.agent.theme-ara   { background:#e6f1fb;border-color:#85b7eb;color:#185fa5;border-radius:2px 10px 10px 10px; }
.agent-bubble.agent.theme-naon  { background:#faece7;border-color:#f0997b;color:#993c1d;border-radius:2px 10px 10px 10px; }
.agent-suggested { display:flex;flex-direction:column;gap:3px;margin-top:5px; }
.suggested-btn { text-align:left;background:rgba(255,255,255,.7);border:1px solid #c7d2fe;border-radius:6px;padding:4px 9px;font-size:11px;color:var(--primary);cursor:pointer;font-weight:500;transition:background .15s; }
.suggested-btn:hover:not(:disabled) { background:#fff; }
.suggested-btn:disabled { opacity:.4;cursor:not-allowed; }
.typing { display:flex;gap:4px;align-items:center; }
.typing span { width:5px;height:5px;background:#94a3b8;border-radius:50%;animation:bounce .8s infinite; }
.typing span:nth-child(2) { animation-delay:.15s; }
.typing span:nth-child(3) { animation-delay:.3s; }
@keyframes bounce { 0%,80%,100%{transform:scale(.8);opacity:.5}40%{transform:scale(1.2);opacity:1} }

/* ── Neo4j Knowledge Graph 사고 과정 블록 ── */
.agent-msg-row.planning { padding:0; }
.agent-planning-block { width:100%;border:1px solid rgba(0,171,54,.3);border-radius:10px;background:rgba(0,171,54,.03);overflow:hidden;margin:2px 0; }
.agent-planning-block.done { border-color:rgba(0,171,54,.5);background:rgba(0,171,54,.04); }
.agent-planning-toggle { display:flex;align-items:center;gap:6px;width:100%;padding:7px 10px;background:none;border:none;cursor:pointer;color:#374151;font-size:11.5px;font-weight:600;text-align:left; }

.agent-planning-label { flex:1;min-width:0;color:#374151;font-size:11px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap; }
.agent-planning-count { font-size:10px;font-weight:600;color:#00ab36;background:rgba(0,171,54,.1);padding:1px 7px;border-radius:20px;border:1px solid rgba(0,171,54,.2); }
.agent-planning-chev { transition:transform .2s;flex-shrink:0;color:#9ca3af; }
.agent-planning-chev.rotated { transform:rotate(180deg); }
.agent-planning-steps { padding:4px 10px 10px;display:flex;flex-direction:column;gap:5px;border-top:1px solid rgba(0,171,54,.12); }
.agent-planning-step { display:flex;align-items:flex-start;gap:7px;font-size:11px;line-height:1.5; }

/* 스텝 진입 fade-in 애니메이션 */
@keyframes step-slide-in {
  from { opacity: 0; transform: translateY(6px); }
  to   { opacity: 1; transform: translateY(0); }
}
.fade-in { animation: step-slide-in 0.28s ease forwards; }

/* 응답 스트리밍 커서 */
.agent-bubble.is-streaming::after {
  content: '▍';
  display: inline;
  color: #a78bfa;
  font-size: 0.88em;
  line-height: 1;
  animation: cursor-blink 0.65s step-end infinite;
  vertical-align: baseline;
}
@keyframes cursor-blink {
  0%, 100% { opacity: 1; }
  50%       { opacity: 0; }
}
.agent-step-num { flex-shrink:0;width:16px;height:16px;background:rgba(0,0,0,.08);color:#6b7280;border-radius:50%;font-size:8.5px;font-weight:700;display:flex;align-items:center;justify-content:center;margin-top:1.5px; }
.agent-step-text { color:#4b5563;word-break:break-all; }
/* 데이터 수신 단계 */
.agent-step-data { background:rgba(0,171,54,.06);border:1px solid rgba(0,171,54,.2);border-radius:6px;padding:4px 8px; }
.agent-step-data .agent-step-text { color:#15803d;font-weight:500; }
.agent-step-icon-data { flex-shrink:0;color:#00ab36;margin-top:2px; }
/* 라우팅 단계 */
.agent-step-route .agent-step-text { color:#7c3aed;font-style:italic; }
.agent-step-pending { padding-left:2px; }
.agent-step-dots { display:flex;gap:3px;align-items:center; }
.agent-step-dots span { width:4px;height:4px;background:#00ab36;border-radius:50%;animation:bounce .8s infinite; }
.agent-step-dots span:nth-child(2) { animation-delay:.15s; }
.agent-step-dots span:nth-child(3) { animation-delay:.3s; }
@keyframes agent-spin { to { transform:rotate(360deg); } }
.agent-planning-spinner { animation:agent-spin 1s linear infinite;flex-shrink:0; }
/* dark mode */
.dark .agent-planning-block { border-color:rgba(0,171,54,.35);background:rgba(0,171,54,.07); }
.dark .agent-planning-block.done { border-color:rgba(0,171,54,.5);background:rgba(0,171,54,.1); }
.dark .agent-planning-step { color:#cbd5e1; }
.dark .agent-step-text { color:#94a3b8; }
.dark .agent-step-data { background:rgba(0,171,54,.1);border-color:rgba(0,171,54,.3); }
.dark .agent-step-data .agent-step-text { color:#4ade80; }

.agent-file-chips { display:flex;flex-wrap:wrap;gap:4px;margin-bottom:5px; }
.agent-file-chip { font-size:11px;background:#eff6ff;border:1px solid #bfdbfe;border-radius:4px;padding:2px 7px;color:#1d4ed8; }
.agent-input-area { padding:7px 9px;border-top:1px solid var(--border);flex-shrink:0;position:relative; }
.agent-input-row { display:flex;align-items:flex-end;gap:4px; }

/* @ 컨텍스트 chips */
.agent-ctx-chips { display:flex;flex-wrap:wrap;gap:4px;margin-bottom:5px; }
.agent-ctx-chip { font-size:11px;background:#f0fdf4;border:1px solid #86efac;border-radius:4px;padding:2px 5px 2px 7px;color:#166534;display:flex;align-items:center;gap:3px; }
.ctx-chip-remove { background:none;border:none;cursor:pointer;color:#166534;padding:0 0 0 2px;font-size:13px;line-height:1;opacity:.6; }
.ctx-chip-remove:hover { opacity:1; }
.dark .agent-ctx-chip { background:#052e16;border-color:#166534;color:#4ade80; }
.dark .ctx-chip-remove { color:#4ade80; }

/* 사용자 메시지 context chips */
.user-ctx-chips { display:flex;flex-wrap:wrap;gap:3px;margin-top:5px; }
.user-ctx-chip { font-size:10px;background:rgba(255,255,255,.18);border:1px solid rgba(255,255,255,.3);border-radius:3px;padding:1px 5px;color:rgba(255,255,255,.9); }

/* @ 드롭다운 메뉴 */
.at-menu { position:absolute;bottom:calc(100% + 4px);left:9px;right:9px;background:var(--bg);border:1px solid var(--border);border-radius:8px;box-shadow:0 4px 16px rgba(0,0,0,.12);z-index:200;overflow:hidden;max-height:260px;overflow-y:auto; }
.at-menu-item { display:flex;align-items:center;gap:7px;padding:7px 11px;cursor:pointer;transition:background .1s; }
.at-menu-item.active, .at-menu-item:hover { background:var(--hover-bg, #f1f5f9); }
.dark .at-menu-item.active, .dark .at-menu-item:hover { background:#1e293b; }
.at-icon { font-size:14px;flex-shrink:0; }
.at-type { font-size:10px;color:var(--text-muted);background:var(--surface-2,#f1f5f9);border-radius:3px;padding:1px 5px;flex-shrink:0; }
.dark .at-type { background:#1e293b; }
.at-label { font-size:12px;color:var(--text);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;flex:1; }
.at-menu-hint { font-size:10px;color:var(--text-muted);padding:4px 11px;border-top:1px solid var(--border);text-align:right; }
.at-menu-enter-active, .at-menu-leave-active { transition:opacity .12s, transform .12s; }
.at-menu-enter-from, .at-menu-leave-to { opacity:0;transform:translateY(4px); }
.agent-attach-btn { width:26px;height:26px;border-radius:50%;border:1px solid var(--border);background:#f8fafc;color:var(--text-muted);font-size:16px;line-height:1;cursor:pointer;display:flex;align-items:center;justify-content:center;flex-shrink:0; }
.agent-textarea { flex:1;resize:none;overflow:hidden;min-height:34px;border:1px solid var(--border);border-radius:7px;padding:6px 8px;font-size:12px;outline:none;font-family:inherit;line-height:1.5;box-sizing:border-box; }
.agent-textarea:focus { border-color:var(--primary); }
.agent-send-btn { padding:6px 12px;border-radius:7px;border:none;background:var(--primary);color:#fff;font-size:12px;font-weight:600;cursor:pointer;flex-shrink:0; }
.agent-send-btn:disabled { opacity:.4;cursor:not-allowed; }

.req { color:#ef4444; }

/* ── Graph floating action buttons ── */
.graph-float-btns {
  position: absolute; top: 14px; right: 14px; z-index: 15;
  display: flex; flex-direction: column; gap: 12px; align-items: center;
}
.float-btn-item {
  display: flex; flex-direction: column; align-items: center; gap: 5px;
  cursor: grab; user-select: none; transition: transform .15s, opacity .15s;
}
.float-btn-item:hover { transform: scale(1.1); opacity: 1; }
.float-btn-item:active { cursor: grabbing; transform: scale(1.05); }
.float-node-preview {
  display: flex; align-items: center; justify-content: center;
  transition: box-shadow .15s;
}
.meeting-preview {
  width: 46px; height: 46px; border-radius: 50%;
  background: radial-gradient(circle, rgba(59,130,246,.95) 0%, rgba(37,99,235,.55) 100%);
  border: 2px solid rgba(147,197,253,.7); color: #fff;
  box-shadow: 0 0 14px rgba(59,130,246,.5), 0 2px 10px rgba(0,0,0,.4);
}
.float-btn-item:hover .meeting-preview { box-shadow: 0 0 22px rgba(59,130,246,.75), 0 4px 16px rgba(0,0,0,.5); }
.doc-preview {
  width: 44px; height: 34px; border-radius: 6px;
  background: rgba(15,23,42,.9);
  border: 2px solid rgba(96,165,250,.65); color: #60a5fa;
  box-shadow: 0 0 12px rgba(96,165,250,.35), 0 2px 8px rgba(0,0,0,.45);
}
.float-btn-item:hover .doc-preview { box-shadow: 0 0 20px rgba(96,165,250,.55), 0 4px 14px rgba(0,0,0,.5); }
.session-preview {
  width: 44px; height: 32px; border-radius: 5px;
  background: rgba(5,150,105,0.55);
  border: 2px solid rgba(52,211,153,.7); color: #6ee7b7;
  box-shadow: 0 0 12px rgba(52,211,153,.35), 0 2px 8px rgba(0,0,0,.45);
}
.float-btn-item:hover .session-preview { box-shadow: 0 0 20px rgba(52,211,153,.65), 0 4px 14px rgba(0,0,0,.5); }
.float-btn-label {
  font-size: 10px; font-weight: 700; color: rgba(255,255,255,.65);
  white-space: nowrap;
  text-shadow: 0 1px 4px rgba(0,0,0,.9);
  letter-spacing: .02em;
}

/* Float drag ghost */
.float-drag-ghost {
  position: fixed; z-index: 9999; pointer-events: none;
  display: flex; flex-direction: column; align-items: center; gap: 4px;
  transition: none;
  filter: drop-shadow(0 4px 14px rgba(0,0,0,.6));
}
.ghost-node {
  display: flex; align-items: center; justify-content: center;
  opacity: .9; transform: scale(1.12);
}
.ghost-meeting {
  width: 44px; height: 44px; border-radius: 50%;
  background: radial-gradient(circle, rgba(59,130,246,.95) 0%, rgba(37,99,235,.5) 100%);
  border: 2px solid rgba(147,197,253,.8); color: #fff;
}
.ghost-doc {
  width: 44px; height: 34px; border-radius: 6px;
  background: rgba(15,23,42,.9); border: 2px solid rgba(96,165,250,.8); color: #60a5fa;
}
.ghost-session {
  width: 44px; height: 32px; border-radius: 5px;
  background: rgba(5,150,105,0.6); border: 2px solid rgba(52,211,153,.85); color: #6ee7b7;
}
.ghost-label {
  font-size: 10px; font-weight: 700; color: #fff;
  text-shadow: 0 1px 5px rgba(0,0,0,.95); white-space: nowrap;
}
.ghost-connect-hint {
  font-size: 10px; font-weight: 700; color: #34d399;
  text-shadow: 0 1px 4px rgba(0,0,0,.9); white-space: nowrap;
  animation: pulse-hint .6s ease-in-out infinite alternate;
}
@keyframes pulse-hint { from { opacity: .6 } to { opacity: 1 } }

/* day-mode float button labels */
.day-mode .float-btn-label { color: rgba(15,23,42,.6); text-shadow: 0 1px 3px rgba(255,255,255,.7); }
.day-mode .meeting-preview { box-shadow: 0 0 14px rgba(59,130,246,.4), 0 2px 10px rgba(0,0,0,.15); }
.day-mode .doc-preview { background: rgba(239,246,255,.95); box-shadow: 0 0 12px rgba(59,130,246,.25), 0 2px 8px rgba(0,0,0,.1); }

/* ── Day mode overrides ── */
.archive-page.day-mode { background:#eef2ff !important;color:#1e293b; }
.day-mode .agent-header-btn { border-color:rgba(99,102,241,.35);background:rgba(99,102,241,.1); }
.day-mode .agent-header-btn:hover { background:rgba(99,102,241,.18);border-color:rgba(99,102,241,.55); }
.day-mode .agent-header-btn.active { background:rgba(99,102,241,.22);border-color:#6366f1;box-shadow:0 0 0 2px rgba(99,102,241,.2); }
.day-mode .ai-btn-label { color:#6366f1; }
.day-mode .archive-header { background:#eef2ff;border-bottom-color:#e2e8f0; }
.day-mode .archive-title { color:#1e293b; }
.day-mode .archive-desc { color:#94a3b8; }
.day-mode .search-input { background:#fff;border-color:#e2e8f0;color:#1e293b; }
.day-mode .search-input::placeholder { color:#94a3b8; }
.day-mode .search-input:focus { border-color:#3b82f6; }
.day-mode .search-clear { color:#94a3b8; }
.day-mode .plus-snackbar { background:#fff;border-color:#e2e8f0;box-shadow:0 8px 24px rgba(0,0,0,.1); }
.day-mode .snack-btn { color:#475569; }
.day-mode .snack-btn:hover { background:#f1f5f9;color:#1e293b; }
.day-mode .snack-divider { background:#e2e8f0; }
.day-mode .detail-sidebar { background:#f8fafc;border-right-color:#e2e8f0; }
.day-mode .detail-meeting-name { color:#1e293b; }
.day-mode .detail-meta { color:#94a3b8; }
.day-mode .detail-icon-btn { border-color:#e2e8f0;color:#94a3b8; }
.day-mode .detail-icon-btn:hover { background:#f1f5f9; }
.day-mode .detail-close { color:#94a3b8;border-color:#e2e8f0; }
.day-mode .detail-close:hover { background:#f1f5f9; }
.day-mode .sidebar-toggle-handle { background:rgba(241,245,249,0.96);border-color:#e2e8f0;color:#94a3b8; }
.day-mode .sidebar-toggle-handle:hover { background:#e2e8f0;color:#475569; }
.day-mode .detail-section-label { color:#94a3b8; }
/* Day mode: relationship manager */
.day-mode .rel-item { background:rgba(0,0,0,.03);border-color:rgba(0,0,0,.08); }
.day-mode .rel-target-name { color:#374151; }
.day-mode .rel-type-select { background:#f8fafc;border-color:#cbd5e1;color:#334155; }
.day-mode .rel-add-panel { border-color:rgba(124,111,224,.2);background:rgba(124,111,224,.04); }
.day-mode .rel-add-label { color:#64748b; }
.day-mode .rel-btn-edit   { background:rgba(99,102,241,.1);color:#6366f1; }
.day-mode .rel-btn-delete { background:rgba(239,68,68,.08);color:#ef4444; }
.day-mode .rel-btn-save   { background:rgba(16,185,129,.1);color:#10b981; }
.day-mode .rel-btn-cancel { background:rgba(107,114,128,.08);color:#6b7280; }
.day-mode .ctx-upload-area { border-color:rgba(0,0,0,.12); }
.day-mode .ctx-upload-area:hover { border-color:rgba(59,130,246,.4);background:rgba(59,130,246,.04); }
.day-mode .detail-tabs { border-bottom-color:rgba(0,0,0,.08); }
.day-mode .detail-tab { color:#94a3b8; }
.day-mode .detail-tab.active { color:#1e293b;border-bottom-color:#3b82f6; }
.day-mode .detail-todo-item { background:rgba(0,0,0,.03);border-color:rgba(0,0,0,.06); }
.day-mode .detail-todo-title { color:#1e293b; }
.day-mode .detail-extract-item { background:rgba(0,0,0,.03);border-color:rgba(0,0,0,.06); }
.day-mode .dei-title { color:#1e293b; }
.day-mode .dei-input,.day-mode .dei-textarea { background:rgba(0,0,0,.04);border-color:rgba(0,0,0,.1);color:#1e293b; }
.day-mode .detail-purpose { background:#fff;border-color:#e2e8f0;color:#475569; }
.day-mode .detail-info-key { color:#94a3b8; }
.day-mode .detail-info-val { color:#1e293b; }
.day-mode .detail-kv-val { color:#475569; }
.day-mode .detail-stat-card { background:#fff;border-color:#e2e8f0; }
.day-mode .detail-stat-label { color:#94a3b8; }
.day-mode .detail-progress-track { background:#e2e8f0; }
.day-mode .detail-doc-item { background:#fff;border-color:#e2e8f0; }
.day-mode .detail-doc-name { color:#334155; }
.day-mode .detail-doc-date { color:#94a3b8; }
.day-mode .detail-member-table td { border-bottom-color:#e2e8f0; }
.day-mode .mb-name { color:#1e293b; }
.day-mode .mb-dept,.day-mode .mb-role { color:#94a3b8; }
.day-mode .detail-log-item { background:#fff;border-color:#e2e8f0; }
.day-mode .detail-log-desc { color:#334155; }
.day-mode .detail-log-meta { color:#94a3b8; }
.day-mode .detail-log-empty { color:#94a3b8; }
.day-mode .gm-modal { background:#fff;border-color:#e2e8f0; }
.day-mode .gm-header { border-bottom-color:#e2e8f0; }
.day-mode .gm-title { color:#1e293b; }
.day-mode .gm-close { color:#94a3b8; }
.day-mode .gm-close:hover { background:#f1f5f9;color:#1e293b; }
.day-mode .gm-agenda-card { background:#f8fafc;border-color:#e2e8f0; }
.day-mode .gm-agenda-title { color:#1e293b; }
.day-mode .gm-agenda-bullets li { color:#64748b; }
.day-mode .gm-assign-table th { border-bottom-color:#e2e8f0;color:#94a3b8; }
.day-mode .gm-assign-table td { border-bottom-color:#f1f5f9;color:#334155; }
.day-mode .gm-footer { border-top-color:#e2e8f0; }
.day-mode .gm-btn-cancel { border-color:#e2e8f0;color:#64748b; }
.day-mode .gm-btn-cancel:hover { background:#f1f5f9; }
.day-mode .person-toggle { color:#64748b; }
.day-mode .legend-hint { color:#94a3b8; }
.day-mode .list-view { background:#f8fafc; }
.day-mode .lv-secretary-badge { color:#d97706;background:rgba(217,119,6,.1);border-color:rgba(217,119,6,.25); }
.day-mode .list-header { border-bottom-color:#e2e8f0; }
.day-mode .list-title { color:#475569; }
.day-mode .list-count { color:#94a3b8; }
.day-mode .meeting-group { background:#fff;border-color:#e2e8f0; }
.day-mode .group-header:hover { background:#f8fafc; }
.day-mode .group-title { color:#1e293b; }
.day-mode .group-count { color:#94a3b8; }
.day-mode .group-body { border-top-color:#f1f5f9; }
.day-mode .doc-section-label { color:#94a3b8; }
.day-mode .doc-item { background:#f8fafc;border-color:#e2e8f0; }
.day-mode .doc-name { color:#334155; }
.day-mode .doc-meta { color:#94a3b8; }
.day-mode .doc-btn { background:#f1f5f9;border-color:#e2e8f0;color:#475569; }
.day-mode .doc-btn:hover { background:#eff6ff;color:#2563eb;border-color:#bfdbfe; }
.lv-header { display:flex;align-items:center;justify-content:space-between;padding:0 0 12px 0; }
.lv-filter-wrap { display:flex;gap:6px; }
.lv-header-right { display:flex;align-items:center;gap:6px; }
.lv-title { font-size:12px;font-weight:500;color:#64748b; }
.lv-count { font-size:12px;color:#475569; }
.lv-type-filter { appearance:none;-webkit-appearance:none;background:rgba(255,255,255,.06) url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='10' height='6'%3E%3Cpath d='M0 0l5 6 5-6z' fill='%2394a3b8'/%3E%3C/svg%3E") no-repeat right 8px center;background-size:10px 6px;border:1px solid rgba(255,255,255,.12);border-radius:7px;color:#cbd5e1;font-size:12px;padding:5px 26px 5px 10px;cursor:pointer;outline:none;transition:border-color .15s,background-color .15s; }
.lv-type-filter:hover { border-color:rgba(255,255,255,.22); }
.lv-type-filter:focus { border-color:rgba(99,102,241,.6); }
.day-mode .lv-type-filter { background-color:#fff;background-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='10' height='6'%3E%3Cpath d='M0 0l5 6 5-6z' fill='%2394a3b8'/%3E%3C/svg%3E");border-color:#e2e8f0;color:#334155; }
.day-mode .lv-type-filter:hover { border-color:#cbd5e1; }
.day-mode .lv-type-filter:focus { border-color:#6366f1; }
.lv-group-row { border-bottom:1px solid rgba(255,255,255,.06);cursor:pointer;transition:background .1s;background:transparent; }
.lv-group-row:hover { background:rgba(255,255,255,.04); }
.day-mode .lv-group-row { border-bottom-color:#f1f5f9;background:#fff; }
.day-mode .lv-group-row:hover { background:#f8fafc; }
.lv-name-cell { display:flex;align-items:center;gap:6px; }
.lv-expand-icon { color:#475569;flex-shrink:0;transition:transform .2s; }
.lv-group-name { font-size:13px;font-weight:600;color:#e2e8f0; }
.lv-name-meta { display:flex;flex-direction:column;align-items:flex-start;gap:2px;margin-top:3px; }
.lv-type-text { font-size:11px;font-weight:600;color:#3b82f6; }
.day-mode .lv-group-name { color:#1e293b; }
.lv-expanded-td { padding:0 !important;background:rgba(255,255,255,.02); }
.lv-hist-table { font-size:12px; }
.lv-hist-table th { padding:7px 12px;font-size:11px;font-weight:600;color:#64748b;text-align:left;text-transform:none;letter-spacing:0;border-bottom:1px solid rgba(255,255,255,.07);background:rgba(255,255,255,.03); }
.lv-hist-table td { padding:8px 12px; }
.lv-hist-row { border-bottom:1px solid rgba(255,255,255,.05); }
.lv-hist-row td { padding:8px 12px;vertical-align:middle;color:#cbd5e1;font-size:12px; }
.lv-hist-desc-inner { display:flex;align-items:center;gap:6px; }
.lv-hist-type-dot { width:6px;height:6px;border-radius:50%;flex-shrink:0;background:#64748b; }
.ht-session { background:#3b82f6; }
.ht-report { background:#a855f7; }
.ht-minutes { background:#22c55e; }
.lv-hist-manager { color:#94a3b8; }
.lv-hist-date { color:#94a3b8;white-space:nowrap; }
.lv-dl-btn { width:24px;height:24px;border-radius:6px;border:1px solid rgba(255,255,255,.12);background:rgba(255,255,255,.06);color:#94a3b8;display:flex;align-items:center;justify-content:center;cursor:pointer; }
.lv-dl-btn:hover { background:rgba(59,130,246,.15);color:#93c5fd;border-color:rgba(96,165,250,.4); }
.lv-no-file { color:#475569; }
.lv-hist-empty { padding:14px 12px;color:#64748b;font-size:12px; }
.day-mode .lv-expanded-td { background:#f8fafc; }
.day-mode .lv-hist-table th { border-bottom-color:#e2e8f0;background:#f1f5f9;color:#64748b;text-transform:none;letter-spacing:0; }
.day-mode .lv-hist-row { border-bottom-color:#f1f5f9; }
.day-mode .lv-hist-row td { color:#334155; }
.day-mode .lv-hist-manager { color:#64748b; }
.day-mode .lv-hist-date { color:#94a3b8; }
.day-mode .lv-dl-btn { border-color:#e2e8f0;background:#f1f5f9;color:#475569; }
.day-mode .lv-dl-btn:hover { background:#eff6ff;color:#2563eb;border-color:#bfdbfe; }
.day-mode .lv-title { color:#64748b; }
.day-mode .lv-count { color:#94a3b8; }
/* ── Role badges ── */
.detail-role-badge { display:inline-flex;align-items:center;padding:2px 8px;border-radius:10px;font-size:10px;font-weight:700;letter-spacing:.04em;margin-top:3px;width:fit-content; }
.detail-role-badge.role-admin { background:rgba(59,130,246,.15);color:#60a5fa;border:1px solid rgba(59,130,246,.3); }
.detail-role-badge.role-presenter { background:rgba(100,116,139,.12);color:#94a3b8;border:1px solid rgba(100,116,139,.2); }
.lv-role-badge { display:inline-flex;align-items:center;padding:1px 6px;border-radius:8px;font-size:10px;font-weight:700;letter-spacing:.03em;margin-left:5px; }
.lv-role-badge.role-admin { background:rgba(59,130,246,.15);color:#60a5fa;border:1px solid rgba(59,130,246,.25); }
.lv-role-badge.role-presenter { background:rgba(100,116,139,.1);color:#94a3b8;border:1px solid rgba(100,116,139,.18); }
.day-mode .detail-role-badge.role-admin { background:rgba(59,130,246,.1);color:#2563eb;border-color:rgba(59,130,246,.25); }
.day-mode .detail-role-badge.role-presenter { background:rgba(100,116,139,.08);color:#64748b;border-color:#e2e8f0; }
.day-mode .lv-role-badge.role-admin { background:rgba(59,130,246,.08);color:#2563eb;border-color:rgba(59,130,246,.2); }
.day-mode .lv-role-badge.role-presenter { background:#f8fafc;color:#64748b;border-color:#e2e8f0; }
/* ── Node detail styles ── */
.node-member-list { display:flex;flex-direction:column;gap:5px; }
.node-member-row { display:flex;align-items:center;gap:9px;padding:4px 0; }
.node-avatar { width:26px;height:26px;border-radius:50%;color:#fff;font-size:11px;font-weight:700;display:flex;align-items:center;justify-content:center;flex-shrink:0; }
.node-member-info { display:flex;flex-direction:column;gap:1px; }
.node-member-name { font-size:12px;font-weight:600;color:#e2e8f0; }
.node-member-role { font-size:10px;color:#64748b; }
.node-empty { font-size:12px;color:#475569;padding:8px 0; }
.status-badge { display:inline-block;font-size:10px;font-weight:600;padding:2px 8px;border-radius:10px;letter-spacing:.3px; }
.sb-done { background:rgba(16,185,129,.18);color:#10b981; }
.sb-progress { background:rgba(59,130,246,.18);color:#3b82f6; }
.sb-pending { background:rgba(100,116,139,.18);color:#94a3b8; }
.node-feedback-list { margin:4px 0 0 12px;padding:0;list-style:disc;display:flex;flex-direction:column;gap:4px; }
.node-feedback-list li { font-size:12px;color:#94a3b8;line-height:1.45; }
.day-mode .node-member-name { color:#1e293b; }
.day-mode .node-feedback-list li { color:#64748b; }
</style>

<!-- Teleport(body) 대상 모달은 scoped CSS가 적용되지 않으므로 별도 전역 스타일 블록 사용 -->
<style>
/* ── Archive modal page-specific inner elements (light default) ── */
.modal-dropdown { border:1px solid #e2e8f0;border-radius:8px;overflow:hidden;margin-top:4px; }
.modal-dropdown-item { display:flex;align-items:center;gap:8px;padding:8px 10px;cursor:pointer;transition:background .1s;color:#1e293b; }
.modal-dropdown-item:hover { background:#f1f5f9; }
.modal-user-avatar { width:26px;height:26px;border-radius:50%;background:#3b82f6;color:#fff;font-size:11px;font-weight:700;display:flex;align-items:center;justify-content:center;flex-shrink:0; }
.selected-members { display:flex;flex-direction:column;gap:4px;margin-top:6px; }
.selected-member { display:flex;align-items:center;gap:7px;padding:5px 8px;background:#f8fafc;border:1px solid #e2e8f0;border-radius:7px; }
.selected-member span { flex:1;font-size:13px;color:#1e293b; }
.role-select-sm { padding:3px 6px;border:1px solid #e2e8f0;border-radius:5px;font-size:12px;background:#fff;color:#475569;outline:none; }
.remove-btn-sm { background:none;border:none;cursor:pointer;color:#94a3b8;font-size:16px;line-height:1;padding:0 2px; }
.related-meetings { display:flex;flex-wrap:wrap;gap:6px; }
.related-chip { display:flex;align-items:center;gap:5px;padding:4px 10px;border-radius:20px;border:1px solid #e2e8f0;background:#fff;color:#64748b;font-size:12px;cursor:pointer;transition:all .15s; }
.related-chip:hover { border-color:#60a5fa;color:#3b82f6; }
.related-chip.selected { background:#eff6ff;border-color:#93c5fd;color:#1d4ed8; }
.related-dot { width:6px;height:6px;border-radius:50%;flex-shrink:0; }
.settings-body { gap:0; }
.settings-section { padding:14px 0;border-bottom:1px solid #f1f5f9;display:flex;flex-direction:column;gap:10px; }
.settings-section:last-child { border-bottom:none;padding-bottom:0; }
.settings-section-title { font-size:12px;font-weight:700;color:#94a3b8;text-transform:uppercase;letter-spacing:.05em;display:flex;align-items:center;gap:8px; }
.member-cnt-badge { font-size:11px;font-weight:600;background:rgba(96,165,250,.15);border-radius:99px;padding:1px 7px;color:#93c5fd; }
.ms-role-btn { padding:2px 8px;font-size:11px;cursor:pointer;border-radius:4px;border:1px solid #475569;background:transparent;color:#94a3b8;transition:all .15s; }
.ms-role-btn:hover { border-color:#60a5fa;color:#60a5fa; }
.ms-role-btn.admin { background:#1d4ed8;border-color:#1d4ed8;color:#fff; }
.ms-role-btn.admin:hover { background:#2563eb; }
.member-search-wrap { display:flex;align-items:center;gap:7px;padding:7px 10px;border:1px solid #e2e8f0;border-radius:8px;background:#f8fafc; }
.member-search-input { flex:1;border:none;background:none;color:#1e293b;font-size:13px;outline:none; }
.member-search-input::placeholder { color:#94a3b8; }
.search-spinner { color:#64748b;font-size:14px;animation:archive-spin .8s linear infinite;display:inline-block; }
@keyframes archive-spin { to { transform:rotate(360deg); } }
.member-search-results { border:1px solid #e2e8f0;border-radius:8px;overflow:hidden;max-height:140px;overflow-y:auto; }
.member-search-item { display:flex;align-items:center;gap:8px;padding:8px 10px;cursor:pointer;transition:background .1s; }
.member-search-item:hover { background:#f8fafc; }
.ms-avatar { width:26px;height:26px;border-radius:50%;color:#fff;font-size:11px;font-weight:700;display:flex;align-items:center;justify-content:center;flex-shrink:0; }
.ms-info { flex:1;display:flex;flex-direction:column;gap:1px;min-width:0; }
.ms-name { font-size:12px;font-weight:600;color:#1e293b; }
.ms-email { font-size:11px;color:#94a3b8; }
.ms-add-hint { font-size:11px;color:#3b82f6;font-weight:600;flex-shrink:0; }
.settings-member-list { display:flex;flex-direction:column;gap:4px;max-height:180px;overflow-y:auto; }
.settings-empty-members { font-size:12px;color:#64748b;padding:6px 2px; }
.settings-member-row { display:flex;align-items:center;gap:8px;padding:5px 4px;border-radius:7px;transition:background .1s; }
.settings-member-row:hover { background:#f8fafc; }
.sm-avatar { width:26px;height:26px;border-radius:50%;color:#fff;font-size:11px;font-weight:700;display:flex;align-items:center;justify-content:center;flex-shrink:0; }
.sm-info { flex:1;display:flex;flex-direction:column;gap:1px;min-width:0; }
.sm-name { font-size:12px;font-weight:600;color:#1e293b; }
.sm-email { font-size:11px;color:#94a3b8; }
.sm-remove { width:22px;height:22px;border-radius:5px;border:none;background:rgba(239,68,68,.1);color:#f87171;display:flex;align-items:center;justify-content:center;cursor:pointer;transition:all .15s;flex-shrink:0; }
.sm-remove:hover { background:rgba(239,68,68,.2); }
/* Dark overrides */
.app-modal.dark .modal-dropdown { border-color:rgba(255,255,255,.1); }
.app-modal.dark .modal-dropdown-item { color:#e2e8f0; }
.app-modal.dark .modal-dropdown-item:hover { background:rgba(255,255,255,.06); }
.app-modal.dark .selected-member { background:rgba(255,255,255,.06);border-color:rgba(255,255,255,.1); }
.app-modal.dark .selected-member span { color:#e2e8f0; }
.app-modal.dark .role-select-sm { background:rgba(255,255,255,.08);border-color:rgba(255,255,255,.12);color:#e2e8f0; }
.app-modal.dark .related-chip { border-color:rgba(255,255,255,.1);background:rgba(255,255,255,.04);color:#64748b; }
.app-modal.dark .related-chip.selected { background:rgba(59,130,246,.15);border-color:#93c5fd;color:#60a5fa; }
.app-modal.dark .settings-section { border-bottom-color:rgba(255,255,255,.07); }
.app-modal.dark .settings-section-title { color:#475569; }
.app-modal.dark .member-search-wrap { border-color:rgba(255,255,255,.1);background:rgba(255,255,255,.04); }
.app-modal.dark .member-search-input { color:#e2e8f0; }
.app-modal.dark .member-search-input::placeholder { color:#475569; }
.app-modal.dark .member-search-results { border-color:rgba(255,255,255,.1); }
.app-modal.dark .member-search-item:hover { background:rgba(255,255,255,.06); }
.app-modal.dark .ms-name { color:#e2e8f0; }
.app-modal.dark .settings-member-row:hover { background:rgba(255,255,255,.04); }
.app-modal.dark .sm-name { color:#e2e8f0; }
/* 업로드 모달 */
.file-type-row,.rel-type-row { display:flex;flex-wrap:wrap;gap:6px; }
.file-type-btn,.rel-type-btn { padding:5px 14px;border-radius:20px;border:1px solid #e2e8f0;background:#f8fafc;color:#64748b;font-size:12px;cursor:pointer;transition:all .15s; }
.file-type-btn:hover,.rel-type-btn:hover { border-color:#60a5fa;color:#60a5fa;background:rgba(96,165,250,.08); }
.file-type-btn.active,.rel-type-btn.active { font-weight:600; }
/* 연결 프리뷰 */
.conn-preview { display:flex;align-items:center;gap:6px;margin-top:8px;padding:7px 10px;border-radius:8px;background:#f0f4f8;border:1px solid #e2e8f0;flex-wrap:wrap; }
.conn-preview-box { display:flex;align-items:center;gap:6px;padding:9px 12px;border-radius:8px;background:#f0f4f8;border:1px solid #e2e8f0;flex-wrap:wrap;margin-top:4px; }
.conn-node { font-size:12px;font-weight:600;color:#1e293b;padding:2px 8px;border-radius:5px;background:#f1f5f9; }
.conn-node.file { color:#1e293b; }
.conn-arrow { font-size:14px;color:#475569; }
.conn-rel { font-size:11px;font-weight:700;padding:2px 7px;border-radius:4px;background:#f1f5f9; }
.file-type-tag { font-size:10px;font-weight:700;color:#94a3b8;margin-left:2px; }
.app-modal.dark .file-type-btn,.app-modal.dark .rel-type-btn { border-color:rgba(255,255,255,.12);background:rgba(255,255,255,.05); }
.app-modal.dark .conn-preview,.app-modal.dark .conn-preview-box { background:rgba(255,255,255,.04);border-color:rgba(255,255,255,.07); }
.app-modal.dark .conn-node { color:#e2e8f0;background:rgba(255,255,255,.07); }
.app-modal.dark .conn-rel { background:rgba(255,255,255,.06); }
/* 온톨로지 범례 */
.graph-legend-onto { position:absolute;bottom:12px;left:12px;z-index:15;display:flex;flex-direction:column;gap:4px;background:rgba(15,23,42,.82);border:1px solid rgba(255,255,255,.1);border-radius:8px;padding:8px 12px; }
.legend-onto-item { display:flex;align-items:center;gap:6px;font-size:10px;color:#94a3b8;cursor:pointer;border-radius:4px;padding:2px 3px;transition:background .12s; }
.legend-onto-item:hover { background:rgba(255,255,255,.07); }
.legend-item-hidden { opacity:.38; }
.legend-onto-dot { width:9px;height:9px;flex-shrink:0; }
.legend-dot-pentagon { flex-shrink:0;display:block; }
.legend-dot-circle { border-radius:50%; }
.legend-dot-rect { border-radius:2px;width:14px;height:9px; }
.legend-onto-dash { width:18px;height:2px;flex-shrink:0; }
.legend-eye { flex-shrink:0;margin-left:auto;padding-left:4px;opacity:.5;transition:opacity .12s; }
.legend-onto-item:hover .legend-eye { opacity:.9; }
.legend-item-hidden .legend-eye { opacity:.75; }
.day-mode .graph-legend-onto { background:rgba(238,242,255,.88);border-color:#e2e8f0;color:#64748b; }
.day-mode .conn-preview,.day-mode .conn-preview-box { background:#f0f4f8;border-color:#e2e8f0; }
.day-mode .legend-onto-item { color:#64748b; }
.day-mode .legend-onto-item:hover { background:rgba(0,0,0,.05); }
/* 툴팁 편집 버튼 */
.tt-edit-btn { margin-top:6px;width:100%;padding:5px 0;border-radius:6px;border:1px solid rgba(255,255,255,.12);background:rgba(255,255,255,.05);color:#94a3b8;font-size:11px;cursor:pointer;transition:all .15s; }
.tt-edit-btn:hover { background:rgba(96,165,250,.15);border-color:#60a5fa;color:#93c5fd; }
/* ── Upload 2-step styles ──────────────────────────────────── */
.upload-step-bar { padding:14px 20px 10px; }
.upload-dept-hint { display:flex;align-items:center;gap:5px;font-size:11px;color:#f59e0b;margin-top:6px;padding:5px 8px;border-radius:6px;background:rgba(245,158,11,.08);border:1px solid rgba(245,158,11,.2); }
/* 자동입력됨 텍스트 */
.prefill-label { font-size:11px;font-weight:500;color:#16a34a;margin-left:6px; }
.app-modal.dark .prefill-label { color:#4ade80; }
/* 자동입력된 필드 시각적 강조 */
.app-modal-input.prefilled { border-color:rgba(22,163,74,.4);background:rgba(22,163,74,.06); }
.app-modal.dark .app-modal-input.prefilled { border-color:rgba(34,197,94,.4);background:rgba(34,197,94,.06); }
/* AI result body */
.ai-result-body { max-height:420px;overflow-y:auto; }

/* ── 파일 AI 검토 패널 ── */
.file-review-box { width:500px; }
.fr-actions { display:flex;gap:6px;flex-wrap:wrap;padding:10px 16px;border-bottom:1px solid #e2e8f0; }
.fr-action-btn { display:flex;align-items:center;gap:5px;padding:5px 12px;border-radius:20px;border:1px solid #e2e8f0;background:#f8fafc;color:#475569;font-size:12px;font-weight:500;cursor:pointer;transition:all .15s; }
.fr-action-btn:hover:not(:disabled) { background:#f1f5f9;color:#1e293b; }
.fr-action-btn:disabled { opacity:.4;cursor:not-allowed; }
.fr-action-btn.accent { border-color:rgba(99,102,241,.3);color:#6366f1; }
.fr-action-btn.accent:hover:not(:disabled) { background:rgba(99,102,241,.08); }
.fr-action-btn.green { border-color:rgba(16,185,129,.3);color:#059669; }
.fr-action-btn.green:hover:not(:disabled) { background:rgba(16,185,129,.08); }
.dl-icon-btn { display:inline-flex;align-items:center;justify-content:center;width:28px;height:28px;border-radius:8px;border:1px solid #e2e8f0;background:#f8fafc;color:#475569;cursor:pointer;transition:all .15s;flex-shrink:0; }
.dl-icon-btn:hover { background:#f1f5f9;color:#6366f1;border-color:rgba(99,102,241,.3); }
.archive-graph.dark .dl-icon-btn { border-color:rgba(255,255,255,.14);background:rgba(255,255,255,.05);color:#94a3b8; }
.archive-graph.dark .dl-icon-btn:hover { background:rgba(255,255,255,.1);color:#818cf8; }
.app-modal.dark .fr-actions { border-bottom-color:rgba(255,255,255,.06); }
.app-modal.dark .fr-action-btn { border-color:rgba(255,255,255,.14);background:rgba(255,255,255,.05);color:#94a3b8; }
.app-modal.dark .fr-action-btn:hover:not(:disabled) { background:rgba(255,255,255,.1);color:#e2e8f0; }
.app-modal.dark .fr-action-btn.accent { border-color:rgba(99,102,241,.4);color:#818cf8; }
.app-modal.dark .fr-action-btn.green { border-color:rgba(16,185,129,.4);color:#34d399; }

/* 발제자료 기준 체크리스트 */
.criteria-list { display:flex;flex-direction:column;gap:8px;margin-top:4px; }
.criteria-row { display:flex;align-items:flex-start;gap:8px; }
.criteria-dot { width:18px;height:18px;border-radius:50%;display:flex;align-items:center;justify-content:center;flex-shrink:0;margin-top:1px; }
.criteria-dot.pass { background:rgba(16,185,129,.2);color:#10b981; }
.criteria-dot.fail { background:rgba(239,68,68,.15);color:#ef4444; }
.criteria-text { display:flex;flex-direction:column;gap:2px; }
.criteria-label { font-size:12px;font-weight:600;color:#1e293b; }
.criteria-desc { font-size:11px;color:#64748b;line-height:1.4; }
.app-modal.dark .criteria-label { color:#e2e8f0; }

/* 추출된 아젠다 카드 */
.extracted-agenda-card { background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;padding:10px 12px;margin-bottom:8px; }
.ea-title { font-size:13px;font-weight:600;color:#1e293b;margin-bottom:6px; }
.ea-bullets { padding-left:16px;margin:0;display:flex;flex-direction:column;gap:3px; }
.ea-bullets li { font-size:12px;color:#475569;line-height:1.5; }
.app-modal.dark .extracted-agenda-card { background:rgba(255,255,255,.04);border-color:rgba(255,255,255,.08); }
.app-modal.dark .ea-title { color:#e2e8f0; }
.app-modal.dark .ea-bullets li { color:#94a3b8; }
.ai-loading-wrap { display:flex;flex-direction:column;align-items:center;justify-content:center;gap:14px;padding:40px 20px;text-align:center; }
.ai-loading-spinner { width:36px;height:36px;border:3px solid rgba(99,102,241,.2);border-top-color:#6366f1;border-radius:50%;animation:spin .7s linear infinite; }
@keyframes spin { to { transform:rotate(360deg) } }
.ai-loading-text { font-size:13px;color:#64748b;line-height:1.6; }
.ai-score-section { margin-bottom:16px; }
.ai-score-label { font-size:11px;color:#94a3b8;margin-bottom:6px;font-weight:600;text-transform:uppercase;letter-spacing:.04em; }
.ai-score-gauge-wrap { display:flex;align-items:center;gap:10px;margin-bottom:8px; }
.ai-score-desc { font-size:13px;font-weight:700; }
.ai-feedback-list { display:flex;flex-direction:column;gap:4px; }
.ai-feedback-item { font-size:12px;color:#475569;line-height:1.5;display:flex;gap:4px; }
.fb-dot { color:#6366f1;flex-shrink:0;font-size:14px;line-height:1.3; }
.ai-section { margin-bottom:14px; }
.ai-section-title { display:flex;align-items:center;gap:6px;font-size:12px;font-weight:600;color:#1e293b;margin-bottom:8px; }
.ai-badge { font-size:10px;font-weight:500;padding:1px 6px;border-radius:99px;background:#f1f5f9;color:#64748b;margin-left:auto; }
.ai-empty { font-size:12px;color:#475569;padding:4px 0; }
.ai-check-row { display:flex;align-items:flex-start;gap:8px;padding:8px 10px;border-radius:8px;border:1px solid #e2e8f0;background:#f8fafc;margin-bottom:6px;cursor:pointer;transition:all .15s; }
.ai-check-row:hover { border-color:rgba(99,102,241,.3); }
.ai-check-row.selected { border-color:#6366f1;background:#eef2ff; }
.ai-checkbox { width:16px;height:16px;border-radius:4px;border:1.5px solid #cbd5e1;background:#fff;flex-shrink:0;display:flex;align-items:center;justify-content:center;margin-top:1px;transition:all .15s; }
.ai-checkbox.checked { background:#6366f1;border-color:#6366f1; }
.ai-check-content { flex:1;min-width:0; }
.ag-content { font-size:12px;color:#1e293b;font-weight:500;line-height:1.4; }
.ag-dept { font-size:10px;color:#64748b;margin-top:2px; }
.ai-dept-chips { display:flex;flex-wrap:wrap;gap:6px; }
.ai-dept-chip { padding:5px 12px;border-radius:99px;border:1px solid #e2e8f0;background:#f8fafc;color:#64748b;font-size:11px;font-weight:500;cursor:pointer;transition:all .15s; }
.ai-dept-chip:hover { border-color:rgba(16,185,129,.4);color:#6ee7b7; }
.ai-dept-chip.selected { border-color:#10b981;background:#ecfdf5;color:#065f46; }
/* dark overrides */
.app-modal.dark .ai-section-title { color:#e2e8f0; }
.app-modal.dark .ai-badge { background:rgba(255,255,255,.08);color:#94a3b8; }
.app-modal.dark .ai-check-row { border-color:rgba(255,255,255,.07);background:rgba(255,255,255,.03); }
.app-modal.dark .ai-check-row.selected { border-color:rgba(99,102,241,.4);background:rgba(99,102,241,.07); }
.app-modal.dark .ai-checkbox { border-color:rgba(255,255,255,.2);background:rgba(255,255,255,.05); }
.app-modal.dark .ag-content { color:#e2e8f0; }
.app-modal.dark .ai-dept-chip { border-color:rgba(255,255,255,.1);background:rgba(255,255,255,.05);color:#94a3b8; }
.app-modal.dark .ai-dept-chip.selected { background:rgba(16,185,129,.1);border-color:#10b981;color:#6ee7b7; }
.app-modal.dark .ai-feedback-item { color:#94a3b8; }
.app-modal.dark .ai-loading-text { color:#94a3b8; }
/* Node edit modal */
.node-edit-modal-box { width:480px; }
.member-list-header { display:flex;align-items:center;justify-content:space-between;margin-bottom:6px; }
.member-list-header label { margin:0; }
.btn-add-member-open { padding:4px 12px;border-radius:6px;border:1px solid rgba(96,165,250,.4);background:rgba(96,165,250,.08);color:#60a5fa;font-size:11px;font-weight:600;cursor:pointer;transition:all .15s; }
.btn-add-member-open:hover { background:rgba(96,165,250,.18); }
/* new member form */
.new-member-form { border:1px solid rgba(255,255,255,.1);border-radius:10px;padding:14px 14px 10px;background:rgba(255,255,255,.03);margin-bottom:10px; }
.new-member-form-grid { display:grid;grid-template-columns:1fr 1fr;gap:8px 12px;margin-bottom:10px; }
.nmf-field { display:flex;flex-direction:column;gap:4px; }
/* ── Stats view ── */
.stats-view { padding: 20px 24px; overflow-y: auto; height: 100%; }
.stats-kpis { display: grid; grid-template-columns: repeat(4, 1fr); gap: 14px; margin-bottom: 20px; }
.stats-kpi { background: rgba(255,255,255,.05); border: 1px solid rgba(255,255,255,.08); border-radius: 12px; padding: 16px 20px; text-align: center; }
.stats-kpi-value { font-size: 28px; font-weight: 700; color: #e2e8f0; line-height: 1; }
.stats-kpi-label { font-size: 12px; color: #64748b; margin-top: 6px; }
.day-mode .stats-kpi { background: #fff; border-color: #e2e8f0; }
.day-mode .stats-kpi-value { color: #1e293b; }
.stats-charts-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
.stats-chart-card { background: rgba(255,255,255,.04); border: 1px solid rgba(255,255,255,.08); border-radius: 12px; padding: 18px 20px; }
.day-mode .stats-chart-card { background: #fff; border-color: #e2e8f0; }
.stats-chart-title { font-size: 13px; font-weight: 600; color: #94a3b8; margin-bottom: 14px; }
.day-mode .stats-chart-title { color: #64748b; }
.stats-empty { font-size: 12px; color: #475569; text-align: center; padding: 20px 0; }
.stats-bar-chart { display: flex; flex-direction: column; gap: 9px; }
.stats-bar-row { display: flex; align-items: center; gap: 8px; }
.stats-bar-label { width: 90px; font-size: 11px; color: #94a3b8; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; flex-shrink: 0; }
.day-mode .stats-bar-label { color: #64748b; }
.stats-bar-track { flex: 1; height: 10px; background: rgba(255,255,255,.07); border-radius: 99px; overflow: hidden; }
.day-mode .stats-bar-track { background: #f1f5f9; }
.stats-bar-fill { height: 100%; border-radius: 99px; transition: width .5s ease; }
.stats-bar-fill.blue { background: linear-gradient(90deg, #3b82f6, #6366f1); }
.stats-bar-fill.purple { background: linear-gradient(90deg, #8b5cf6, #ec4899); }
.stats-bar-val { font-size: 11px; color: #64748b; width: 22px; text-align: right; flex-shrink: 0; }
.stats-pie-wrap { display: flex; align-items: center; gap: 16px; }
.stats-pie-svg { width: 120px; height: 120px; flex-shrink: 0; }
.stats-pie-legend { display: flex; flex-direction: column; gap: 6px; }
/* ── Constellation ─────────────────────────────────────────── */
.const-canvas { position:absolute;inset:0;width:100%;height:100%;z-index:1;cursor:grab; }
.const-canvas:active { cursor:grabbing; }
.const-zoom-controls { position:absolute;top:10px;left:10px;z-index:10;display:flex;flex-direction:column;gap:3px; }
.const-hint { position:absolute;bottom:14px;left:50%;transform:translateX(-50%);z-index:10;display:flex;align-items:center;gap:5px;background:rgba(15,23,42,0.7);color:rgba(226,232,240,0.85);font-size:11px;padding:5px 12px;border-radius:20px;pointer-events:none;backdrop-filter:blur(4px);white-space:nowrap; }
.day-mode .const-hint { background:rgba(255,255,255,0.82);color:#475569; }
/* ── Stats ───────────────────────────────────────────────────── */
.stats-pie-legend-item { display: flex; align-items: center; gap: 6px; font-size: 11px; }
.stats-pie-dot { width: 9px; height: 9px; border-radius: 50%; flex-shrink: 0; }
.stats-pie-text { color: #94a3b8; flex: 1; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 100px; }
.day-mode .stats-pie-text { color: #64748b; }
.stats-pie-pct { color: #475569; font-weight: 600; }
.stats-line-wrap { display: flex; flex-direction: column; }
.stats-line-svg { width: 100%; height: 100px; }
.stats-line-labels { display: flex; justify-content: space-between; margin-top: 4px; }
.stats-line-label { font-size: 10px; color: #64748b; }
.nmf-field-full { grid-column:1/-1; }
.nmf-label { font-size:11px;color:#64748b;font-weight:500; }
.nmf-input { background:#fff;border:1px solid #e2e8f0;border-radius:7px;padding:6px 10px;font-size:12px;color:#1e293b;outline:none;width:100%;box-sizing:border-box; }
.nmf-input:focus { border-color:rgba(96,165,250,.5); }
.nmf-input::placeholder { color:#94a3b8; }
.nmf-role-row { display:flex;gap:14px; }
.nmf-radio { display:flex;align-items:center;gap:5px;font-size:12px;color:#64748b;cursor:pointer; }
.nmf-radio input { accent-color:#3b82f6; }
.nmf-actions { display:flex;justify-content:flex-end;gap:6px; }
/* member list rows - richer */
.node-edit-member-list { display:flex;flex-direction:column;gap:4px;max-height:200px;overflow-y:auto;padding:2px 0; }
.node-edit-empty { font-size:12px;color:#94a3b8;padding:6px 0; }
.node-edit-member-row { display:flex;align-items:center;gap:7px;padding:6px 8px;border-radius:7px;background:#f1f5f9; }
.node-edit-avatar { width:28px;height:28px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:11px;font-weight:700;color:#fff;flex-shrink:0; }
.node-edit-member-info { flex:1;min-width:0; }
.node-edit-member-top { display:flex;align-items:center;gap:6px; }
.node-edit-name { font-size:12px;font-weight:600;color:#1e293b; }
.node-edit-position { font-size:10px;color:#64748b;background:rgba(255,255,255,.06);border-radius:4px;padding:1px 6px; }
.node-edit-member-sub { display:flex;gap:8px;margin-top:1px; }
.node-edit-sub-text { font-size:10px;color:#475569; }
.node-edit-add-member { display:flex;align-items:center;gap:6px;margin-top:6px; }
.btn-add-member { padding:6px 14px;border-radius:7px;border:none;background:#3b82f6;color:#fff;font-size:12px;font-weight:600;cursor:pointer;white-space:nowrap; }
.btn-add-member:hover { background:#2563eb; }
/* dark overrides */
.app-modal.dark .new-member-form { background:rgba(255,255,255,.03);border-color:rgba(255,255,255,.1); }
.app-modal.dark .nmf-input { background:rgba(255,255,255,.06);border-color:rgba(255,255,255,.12);color:#e2e8f0; }
.app-modal.dark .nmf-input::placeholder { color:#334155; }
.app-modal.dark .nmf-label { color:#94a3b8; }
.app-modal.dark .nmf-radio { color:#94a3b8; }
.app-modal.dark .node-edit-member-row { background:rgba(255,255,255,.04); }
.app-modal.dark .node-edit-name { color:#e2e8f0; }
.app-modal.dark .node-edit-empty { color:#64748b; }
.app-modal.dark .btn-add-member-open { border-color:rgba(96,165,250,.4);color:#60a5fa;background:rgba(96,165,250,.08); }
</style>