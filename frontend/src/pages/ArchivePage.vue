<script setup>
import {
  computed,
  nextTick,
  onBeforeUnmount,
  onMounted,
  provide,
  reactive,
  ref,
  shallowRef,
  watch,
} from 'vue'
import api, { apiAI, streamPostForm } from '../api'
import AgendaEditModal from '../components/AgendaEditModal.vue'
import AgentSidebar from '../components/AgentSidebar.vue'
import CreateMeetingModal from '../components/CreateMeetingModal.vue'
import CreateSessionModal from '../components/CreateSessionModal.vue'
import DetailSidebar from '../components/DetailSidebar.vue'
import FloatDragPreview from '../components/FloatDragPreview.vue'
import GraphFloatBtns from '../components/GraphFloatBtns.vue'
import GraphLegend from '../components/GraphLegend.vue'
import GraphView from '../components/GraphView.vue'
import MeetingListView from '../components/MeetingListView.vue'
import MemberEditModal from '../components/MemberEditModal.vue'
import MinutesEditModal from '../components/MinutesEditModal.vue'
import RenameModal from '../components/RenameModal.vue'
import ReportEditModal from '../components/ReportEditModal.vue'
import SessionEditModal from '../components/SessionEditModal.vue'
import SettingsModal from '../components/SettingsModal.vue'
import UploadModal from '../components/UploadModal.vue'
import { useAgentChat } from '../composables/useAgentChat'
import { confirmDialog } from '../composables/useConfirm'
import { useGraphBuilder } from '../composables/useGraphBuilder'
import { useTableSort } from '../composables/useTableSort'
import { toast } from '../composables/useToast'
import { REL_COLORS, autoRelByType, fetchRelSchema, resolveCanonical } from '../graph/relSchema'
import { useAuthStore } from '../stores/auth'
import { useMeetingsStore } from '../stores/meetings'
import { useThemeStore } from '../stores/theme'
import { formatDateTimeFull as formatDate, formatDateLong as formatDateOnly } from '../utils/date'

const lvColumns = [
  { label: '회의체명', width: '480px', sortKey: 'title' },
  { label: '유형', width: '160px', sortKey: 'meeting_type' },
  { label: '역할', width: '110px', sortKey: '_role' },
  { label: '간사', width: '300px', sortKey: '_adminName' },
  { label: '자료 수', width: '160px', sortKey: '_histCount' }, // 회의록+보고서 건수 (UX-22 라벨 명확화)
]
const meetingsStore = useMeetingsStore()
const authStore = useAuthStore()
const themeStore = useThemeStore()
const nightMode = computed(() => themeStore.nightMode)

// ─── Data ─────────────────────────────────────────────────────
const minutes = ref([])
const reports = ref([])
const membersData = ref([])
const tasksData = ref([])
const neo4jMeetings = ref([]) // Neo4j에서 직접 가져온 회의체 그래프 데이터
const manualRelations = ref([]) // 사용자가 수동 생성한 자유 관계 (구조 파생 외) — 새로고침 후에도 복원
const neo4jDepts = ref([]) // Neo4j Department 노드 id/name 매핑
const currentCompany = ref(null) // 현재 조직 (Company 노드)
const currentPerson = ref(null) // 현재 로그인 유저의 Neo4j Person 노드
const loading = ref(true)
const neo4jError = ref('')
const neo4jRetrying = ref(false)
const search = ref('')
const filterYear = ref('')
const showEndedMeetings = ref(false)
const expandedMeeting = ref(null)

// ─── View mode ────────────────────────────────────────────────
const viewMode = ref('graph')
// nightMode는 전역 themeStore.nightMode(computed)를 사용합니다

// ─── 뷰 전환 시 패널 상태 저장/복원 ─────────────────────────
const _graphSnapshot = { detailOpen: false, agentSidebarOpen: false }
const _listSnapshot = { expandedMeeting: null }

watch(viewMode, (next, prev) => {
  // graph ↔ list
  if (prev === 'graph' && next === 'list') {
    _graphSnapshot.detailOpen = detailOpen.value
    _graphSnapshot.agentSidebarOpen = agentSidebarOpen.value
    detailOpen.value = false
    agentSidebarOpen.value = false
    expandedMeeting.value = _listSnapshot.expandedMeeting
  } else if (prev === 'list' && next === 'graph') {
    _listSnapshot.expandedMeeting = expandedMeeting.value
    expandedMeeting.value = null
    nextTick(() => {
      detailOpen.value = _graphSnapshot.detailOpen
      agentSidebarOpen.value = _graphSnapshot.agentSidebarOpen
    })
  }
})

const graphViewRef = ref(null) // GraphView (PIXI) 컴포넌트 ref
const graphPanOnly = ref(false) // 그래프 이동 전용 모드 상태
function toggleGraphPanOnly() {
  graphPanOnly.value = graphViewRef.value?.togglePanOnly?.() ?? false
}

// ─── Search highlight (Meetings nodes containing match) ──
const searchHitMgIdxs = ref([])

function _recomputeSearchHits() {
  const q = search.value
  if (!q || !q.trim()) {
    searchHitMgIdxs.value = []
    graphViewRef.value?.focusSearchHits([])
    return
  }
  const lower = q.toLowerCase()
  const hits = []
  gNodes.forEach((n, i) => {
    const label = (n.label || '').toLowerCase()
    if (label.includes(lower)) {
      hits.push(i)
      return
    }
    if (n.type === 'Meetings' && n.data) {
      const g = n.data
      const inMinutes = (g.minutes || []).some(m =>
        (m.session_title || '').toLowerCase().includes(lower),
      )
      const inReports = (g.reports || []).some(r =>
        (r.file_name || r.title || '').toLowerCase().includes(lower),
      )
      const inMembers = (g.members || []).some(m =>
        (m.userName || m.name || '').toLowerCase().includes(lower),
      )
      if (inMinutes || inReports || inMembers) hits.push(i)
    }
  })
  searchHitMgIdxs.value = hits
  graphViewRef.value?.focusSearchHits(hits)
}

watch(search, _recomputeSearchHits)

// ─── Node type visibility (eye toggle) ───────────────────────
const hiddenNodeTypes = ref([]) // array of type keys: 'company-root'|'Meetings'|'dept'|'agenda'|'session'|'minutes'|'report'
function toggleNodeType(typeKey) {
  const idx = hiddenNodeTypes.value.indexOf(typeKey)
  if (idx >= 0) hiddenNodeTypes.value.splice(idx, 1)
  else hiddenNodeTypes.value.push(typeKey)
}
function isHiddenType(typeKey) {
  return hiddenNodeTypes.value.includes(typeKey)
}

// ─── Map toast ────────────────────────────────────────────────
const mapToastMsg = ref('')
let _mapToastTimer = null
function showMapToast(msg) {
  mapToastMsg.value = msg
  clearTimeout(_mapToastTimer)
  _mapToastTimer = setTimeout(() => {
    mapToastMsg.value = ''
  }, 2200)
}

// ─── Neo4j query highlight (챗봇 그래프 탐색 시각화) ──────────
const queryHlIdxs = ref(new Set()) // Set<number> — 현재 하이라이트된 노드 인덱스들
const queryHlEdgeIdxs = ref(new Set()) // Set<number> — 현재 하이라이트된 엣지 인덱스들
const queryHlStep = ref('') // 현재 planning step 텍스트 (HUD 표시용)
let _queryHlTimer = null

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
      gNodes.forEach((n, i) => {
        if (n.label === txt || n.id === txt) {
          newSet.add(i)
          specificSet.add(i)
        }
      })
    }
    // 2) 타입 키워드 → 해당 타입만 flash (노드 확장 없음, PLANNING 시각 피드백용)
    if (newSet.size === 0) {
      if (step.includes('회의체') || step.includes('라우팅'))
        gNodes.forEach((n, i) => {
          if (n.type === 'Meetings') newSet.add(i)
        })
      else if (step.includes('아젠다'))
        gNodes.forEach((n, i) => {
          if (n.type === 'agenda') newSet.add(i)
        })
      else if (step.includes('구성원') || step.includes('소속'))
        gNodes.forEach((n, i) => {
          if (n.type === 'person') newSet.add(i)
        })
      else if (step.includes('세션') || step.includes('회의록'))
        gNodes.forEach((n, i) => {
          if (n.type === 'session') newSet.add(i)
        })
    }
  }

  // 이름으로 정확히 매칭된 노드만 1-hop 확장 (타입 키워드는 엣지 확장 없음)
  const hlEdgeSet = new Set()
  if (specificSet.size > 0) {
    const baseSet = new Set(specificSet)
    gEdges.forEach((e, ei) => {
      if (baseSet.has(e.from) || baseSet.has(e.to)) {
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
      if (
        n.label === lbl ||
        (lbl.length >= 6 && n.label?.startsWith(lbl.slice(0, Math.min(lbl.length, 10))))
      )
        newSet.add(i)
    })
  })
  // 매칭된 노드와 연결된 엣지 + 1-hop 인접 노드
  const baseSet = new Set(newSet)
  gEdges.forEach((e, ei) => {
    if (baseSet.has(e.from) || baseSet.has(e.to)) {
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
const createForm = ref({
  title: '',
  purpose: '',
  start_date: '',
  end_date: '',
  guidelines: '',
  meeting_type: 'Weekly',
})
const createMembers = ref([])
const createMemberSearch = ref('')
const createMemberResults = ref([])
const creating = ref(false)
const createConnectNodeId = ref('')

// ─── Create session modal ─────────────────────────────────────
const showSessionModal = ref(false)
const sessionCreateInitialId = ref(null)

function openCreateModal() {
  createForm.value = {
    title: '',
    purpose: '',
    start_date: '',
    end_date: '',
    guidelines: '',
    meeting_type: 'Weekly',
  }
  const me = authStore.user
  createMembers.value = me
    ? [{ userId: me.id, name: me.name, email: me.email || me.employee_id || '', role: 'admin' }]
    : []
  showCreateModal.value = true
  agentSidebarOpen.value = false
}

function openSessionModal(meetingId = null) {
  sessionCreateInitialId.value = meetingId
  showSessionModal.value = true
  agentSidebarOpen.value = false
}
function onSessionCreated() {
  setTimeout(refreshArchive, 600)
}

async function doCreateMeeting() {
  if (!createForm.value.title.trim()) return
  creating.value = true
  try {
    const meeting = await meetingsStore.createMeeting({
      title: createForm.value.title,
      description: createForm.value.purpose,
      start_date: createForm.value.start_date || null,
      end_date: createForm.value.end_date || null,
      guidelines: createForm.value.guidelines || null,
      meeting_type: createForm.value.meeting_type || null,
    })
    const myId = authStore.user?.id
    for (const m of createMembers.value) {
      if (m.userId === myId) continue // 생성 시 서버가 자동으로 admin 추가
      await api.post(`/api/v1/meetings/${meeting.id}/members`, { userId: m.userId, role: m.role })
    }
    createForm.value = {
      title: '',
      purpose: '',
      start_date: '',
      end_date: '',
      guidelines: '',
      meeting_type: 'Weekly',
    }
    createMembers.value = []
    createMemberSearch.value = ''
    createMemberResults.value = []
    createConnectNodeId.value = ''
    await meetingsStore.fetchMeetings()
    await refreshArchive()
    await nextTick()
    const g = buildGraphNodes()
    if (g.nodes.length > 0) {
      gNodes = g.nodes
      gEdges = _applyLocalEdgeOverrides(g.nodes, g.edges)
      gNodesRef.value = gNodes
      graphViewRef.value?.reloadGraph(gNodes, gEdges)
    }
    setTimeout(refreshArchive, 1500)
    setTimeout(refreshArchive, 4000)
  } catch (e) {
    console.error(e)
  } finally {
    showCreateModal.value = false
    creating.value = false
  }
}

// ─── Detail sidebar resize ─────────────────────────────────────
const sidebarW = ref(260)
let sidebarResizing = false,
  srStartX = 0,
  srStartW = 0
function onSidebarResizeStart(e) {
  sidebarResizing = true
  srStartX = e.clientX
  srStartW = sidebarW.value
  e.preventDefault()
}

// ─── Global mouse handler ───────────────────────────────────────
function onGlobalMouseMove(e) {
  if (sidebarResizing) {
    sidebarW.value = Math.max(200, Math.min(480, srStartW + (e.clientX - srStartX)))
  }

  if (floatDragging.value) {
    floatDragPos.value = { x: e.clientX, y: e.clientY }
    if (Math.hypot(e.clientX - floatDragStartX, e.clientY - floatDragStartY) > 5)
      floatDragMoved = true

    if (graphViewRef.value) {
      const anyNode = graphViewRef.value.getNodeAtScreen(e.clientX, e.clientY)
      const validTypes = FLOAT_VALID_TYPES[floatDragging.value] ?? []
      const isValid = anyNode && validTypes.includes(anyNode.type)

      floatDragTarget = isValid ? anyNode : null
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

// ─── Float button drag-to-node (mousedown 기반) ────────────────
const floatDragging = ref(null) // null | 'meeting' | 'session' | 'doc'
const floatDragPos = ref({ x: 0, y: 0 }) // 뷰포트 좌표 (ghost 위치)
const floatDragPreviewLine = ref(null) // { x1,y1,x2,y2 } 뷰포트 좌표
let floatDragTarget = null // gNode | null
let floatDragNearInvalid = false
let floatDragStartX = 0,
  floatDragStartY = 0
let floatDragMoved = false

const FLOAT_VALID_TYPES = {
  meeting: ['Meetings'],
  session: ['Meetings'],
  doc: ['Meetings', 'dept', 'agenda'],
}

function onFloatBtnMouseDown(type, e) {
  floatDragging.value = type
  floatDragPos.value = { x: e.clientX, y: e.clientY }
  floatDragStartX = e.clientX
  floatDragStartY = e.clientY
  floatDragMoved = false
  floatDragTarget = null
  floatDragNearInvalid = false
  floatDragPreviewLine.value = null
  document.body.style.cursor = 'grabbing'

  function _capture() {
    document.removeEventListener('mouseup', _capture, true)
    if (floatDragging.value) _onFloatDragEnd()
  }
  document.addEventListener('mouseup', _capture, true)
  e.preventDefault()
}

function _onFloatDragEnd() {
  const type = floatDragging.value
  const target = floatDragTarget
  const moved = floatDragMoved
  const nearInvalid = floatDragNearInvalid

  floatDragging.value = null
  floatDragTarget = null
  floatDragPreviewLine.value = null
  floatDragNearInvalid = false
  floatDragMoved = false
  document.body.style.cursor = ''

  if (!moved) return // 클릭 → @click 핸들러가 처리

  if (nearInvalid && !target) {
    showMapToast('해당 노드에 연결할 수 없습니다.')
    return
  }

  if (type === 'meeting') {
    openCreateModal()
  } else if (type === 'session') {
    const mgId = target?.type === 'Meetings' ? toNumericId(target.id) : null
    openSessionModal(mgId || null)
  } else if (type === 'doc') {
    const ctx = {}
    if (target?.type === 'agenda') {
      ctx.connectNodeId = target.meetingId || ''
      ctx.relatedAgendaId = target.neo4jId || target.data?.id || ''
      ctx.agendaContent = target.data?.content || target.label || ''
      ctx.meetingId = target.meetingId || ''
    } else if (target?.type === 'dept') {
      ctx.connectNodeId = target.id
      ctx.meetingId = target.meetingId || ''
    } else if (target?.type === 'Meetings') {
      ctx.meetingId = target.id
    }
    openUploadModal(ctx)
  }
}

// ─── Detail sidebar ───────────────────────────────────────────
const detailMeeting = ref(null)
const detailOpen = ref(false)
const detailAgendas = ref([])
const deletedAgendaLogs = ref([]) // { meetingId, agendaId, title, deletedAt } — API + 세션 추가분 병합
const detailNode = ref(null) // 회의체 외 노드 (부서/과제/회의/파일/사람 등)
const nodeDetailTab = ref('basic') // 'basic' | 'rel'

/** mg-001, mg-13 등 Neo4j/PG ID에서 정수 ID 추출 */
function toNumericId(id) {
  if (!id && id !== 0) return 0
  if (typeof id === 'number') return id
  const m = String(id).match(/(\d+)$/)
  return m ? parseInt(m[1], 10) : 0
}

async function openNodeDetail(n) {
  detailNode.value = n
  detailMeeting.value = null
  detailOpen.value = true
  nodeDetailTab.value = 'basic'
  relAddActive.value = false

  if (n.type === 'agenda' && n.neo4jId && n.meetingId) {
    const meetingNumId = _toNumericId(n.meetingId)
    if (meetingNumId) {
      try {
        const { data: agendas } = await apiAI.get(`/api/agent/meetings/${meetingNumId}/agendas`)
        const fresh = agendas.find(a => String(a.id) === String(n.neo4jId))
        if (fresh) {
          detailNode.value = { ...n, data: { ...n.data, ...fresh } }
        }
      } catch (e) {
        console.warn('[openNodeDetail] agenda status refresh failed', e)
      }
    }
  }

  if (n.type === 'report' && n.data?.id) {
    const rawId = n.data.id
    const reportId =
      typeof rawId === 'string' ? parseInt(rawId.split('-').pop(), 10) : Number(rawId)
    if (reportId && !isNaN(reportId)) {
      try {
        const { data: score } = await apiAI.get(`/api/upload/reports/${reportId}/score`)
        detailNode.value = { ...n, data: { ...n.data, ...score } }
      } catch (e) {
        console.warn('[score fetch]', e)
      }
    }
  }
}

const nodeReviewing = ref(false)

async function startNodeReview(reportId) {
  if (!reportId || nodeReviewing.value) return

  const fileName = detailNode.value?.data?.file_name || '보고자료'

  // 에이전트 사이드바 열기 — watch의 자동 히스토리 로드가 아래 push 메시지를 덮어쓰지 않게 managed open
  if (openSidebarManaged()) initAgentGreeting()
  await nextTick()

  allMessages.value['supervisor'].push({
    role: 'user',
    content: `"${fileName}" 보고자료를 AI로 검토해줘`,
  })
  const planningMsg = reactive({ role: 'planning', steps: [], open: true, done: false })
  allMessages.value['supervisor'].push(planningMsg)
  const agentMsg = reactive({ role: 'agent', content: '' })
  allMessages.value['supervisor'].push(agentMsg)
  if (agentMessagesEl.value) agentMessagesEl.value.scrollTop = agentMessagesEl.value.scrollHeight

  nodeReviewing.value = true
  agentLoading.value = true

  const planningSteps = [
    `Report #${reportId} → R2 파일 다운로드`,
    `파일 텍스트 추출 중...`,
    `AI 평가 기준 적용 (목적/배경, 현황분석, 핵심내용 등)`,
    `항목별 점수 산출 중...`,
    `종합 점수 및 피드백 생성`,
  ]
  const planningPromise = _runPlanningSteps(planningMsg, planningSteps)

  let resultData = null
  try {
    await streamPostForm(`/api/upload/reports/${reportId}/analyze`, new FormData(), ev => {
      if (ev.type === 'result' && ev.data) {
        resultData = ev.data
        detailNode.value = {
          ...detailNode.value,
          data: {
            ...detailNode.value?.data,
            total_score: ev.data.score ?? null,
            detail_scores: ev.data.detail_scores ?? null,
            top_improvements: ev.data.top_improvements ?? [],
            feedback: Array.isArray(ev.data.feedback)
              ? ev.data.feedback.join('\n')
              : (ev.data.feedback ?? null),
          },
        }
      }
    })
  } catch (e) {
    console.warn('[startNodeReview]', e)
    agentMsg.content = '⚠️ AI 검토 중 오류가 발생했습니다.'
    return
  } finally {
    nodeReviewing.value = false
    agentLoading.value = false
  }

  await planningPromise

  if (resultData) {
    const score = resultData.score ?? 0
    const feedback = Array.isArray(resultData.feedback) ? resultData.feedback : []
    const icon = score >= 80 ? '🟢' : score >= 60 ? '🟡' : '🔴'
    const reply = `${icon} **${fileName}** 검토 완료\n\n**종합 점수: ${score}/100**\n\n${feedback.map(f => `• ${f}`).join('\n')}`
    for (let i = 0; i < reply.length; i++) {
      agentMsg.content += reply[i]
      if (i % 4 === 0) {
        await new Promise(r => setTimeout(r, 8))
        if (agentMessagesEl.value)
          agentMessagesEl.value.scrollTop = agentMessagesEl.value.scrollHeight
      }
    }
  }
}

// 현재 회의체 참여 부서 목록
const detailMemberDepts = computed(() => {
  return [
    ...new Set(
      (detailMeeting.value?.members || [])
        .map(mb => mb.department || mb.dept || '')
        .filter(Boolean),
    ),
  ]
})

// 현재 회의체 참여 조직 목록
const detailMemberCompanies = computed(() => {
  const companies = new Set(
    (detailMeeting.value?.members || []).map(mb => mb.company || '').filter(Boolean),
  )
  if (companies.size === 0 && currentCompany.value?.name) companies.add(currentCompany.value.name)
  return [...companies]
})

// 팀별 그룹핑 (현재 회의체 관련 부서만)
const groupedAgendas = computed(() => {
  const groups = {}
  for (const agenda of detailAgendas.value) {
    if (agenda.status === 'done') continue
    const dept =
      agenda.assignee_dept ||
      agenda.dept ||
      (Array.isArray(agenda.department) ? agenda.department[0] : agenda.department) ||
      '미배정'
    if (!groups[dept]) groups[dept] = []
    groups[dept].push(agenda)
  }
  return groups
})

const doneAgendasWithReport = computed(() => {
  const done = detailAgendas.value.filter(t => t.status === 'done')
  const reports = detailMeeting.value
    ? meetings.value.find(g => String(g.id) === String(detailMeeting.value.id))?.reports || []
    : []
  return done.map(agenda => {
    const agendaIdStr = String(agenda.id)
    const report = reports.find(
      r =>
        r.human_status === 'approved' &&
        (r.related_agenda_ids || []).some(rid => {
          const s = String(rid)
          return s === agendaIdStr || s.endsWith('-' + agendaIdStr)
        }),
    )
    return {
      ...agenda,
      dept:
        agenda.assignee_dept ||
        agenda.dept ||
        (Array.isArray(agenda.department) ? agenda.department[0] : agenda.department) ||
        '미배정',
      reportFileName: report?.file_name || null,
      reportDate: report?.created_at || null,
    }
  })
})

async function completeAgenda(agenda) {
  if (agenda.status === 'done') {
    // 완료 → 진행중 되돌리기
    try {
      await apiAI.patch(`/api/agent/archive/agendas/${agenda.id}/status`, { status: 'ongoing' })
      agenda.status = 'ongoing'
    } catch (e) {
      console.error('상태 변경 실패:', e)
    }
    return
  }
  // 진행중 → 보고서 업로드 모달 열기 (아젠다 미리 연결)
  const mgId = detailMeeting.value?.id
    ? String(detailMeeting.value.id).includes('-')
      ? detailMeeting.value.id
      : `mg-${toNumericId(detailMeeting.value.id)}`
    : ''
  const dept =
    agenda.assignee_dept ||
    agenda.dept ||
    (Array.isArray(agenda.department) ? agenda.department[0] : agenda.department) ||
    ''
  const deptNode = dept
    ? gNodesRef.value.find(n => n.type === 'dept' && n.label === dept && n.meetingId === mgId)
    : null
  openUploadModal({
    meetingId: mgId,
    relatedAgendaId: `agenda-${agenda.id}`,
    agendaContent: agenda.title || agenda.content || '',
    connectNodeId: deptNode?.id || '',
  })
}

async function deleteAgenda(agenda) {
  try {
    await apiAI.delete(`/api/agent/archive/agendas/${agenda.id}`)
    detailAgendas.value = detailAgendas.value.filter(t => t.id !== agenda.id)
    const meetingId = detailMeeting.value?.id
    if (meetingId) {
      deletedAgendaLogs.value.push({
        meetingId: String(meetingId),
        agendaId: agenda.id,
        title: agenda.title || agenda.content || '',
        agendaCreatedAt: agenda.created_at || null,
        deletedAt: new Date().toISOString(),
      })
    }
  } catch (e) {
    console.error('삭제 실패:', e)
  }
}
// D-day: detailMeeting의 end_date 기준 남은 일수
const detailDday = computed(() => {
  const ed = detailMeeting.value?.end_date
  if (!ed) return null
  const now = new Date()
  now.setHours(0, 0, 0, 0)
  const due = new Date(ed)
  due.setHours(0, 0, 0, 0)
  return Math.ceil((due - now) / 86400000)
})
const detailEndDateFormatted = computed(() => {
  const ed = detailMeeting.value?.end_date
  if (!ed) return null
  const d = new Date(ed)
  return `${d.getFullYear()}.${String(d.getMonth() + 1).padStart(2, '0')}.${String(d.getDate()).padStart(2, '0')}`
})

// 부서별 보고서 제출 현황
const detailDeptStatus = computed(() => {
  const depts = [
    ...new Set(
      (detailMeeting.value?.members || [])
        .map(mb => mb.department || mb.dept || '')
        .filter(Boolean),
    ),
  ]
  return depts.map(dept => {
    const tasks = detailAgendas.value.filter(t => (t.assignee_dept || t.dept || '') === dept)
    const noTask = tasks.length === 0
    const submitted = !noTask && tasks.every(t => t.status === 'done')
    const pending = tasks.filter(t => t.status !== 'done')
    let minDays = null
    if (pending.length > 0) {
      const now = new Date()
      now.setHours(0, 0, 0, 0)
      const days = pending
        .filter(t => t.due_date)
        .map(t => {
          const due = new Date(t.due_date)
          due.setHours(0, 0, 0, 0)
          return Math.ceil((due - now) / 86400000)
        })
      if (days.length) minDays = Math.min(...days)
    }
    return { dept, submitted, noTask, pendingCount: pending.length, minDays }
  })
})

const groupAgendaRatio = ref(new Map())
const detailTab = ref('basic') // 'basic' | 'task'
// 추출 상태 단순 ref (meeting 전환 시 openDetail에서 리셋)
const extractPhase = ref('context')
const selectedMinutes = ref([]) // 선택된 회의록 ID
const selectedFiles = ref([]) // 선택된 파일 ID
const selectedSimilarDocs = ref([]) // 선택된 유사 문서 ID
const uploadedCtxFiles = ref([]) // { id, file_name, uploading, error }

async function onCtxFilesAdded(files) {
  if (!detailMeeting.value) return
  const meetingId = toNumericId(detailMeeting.value.id)
  for (const file of files) {
    const placeholder = reactive({ id: null, file_name: file.name, uploading: true, error: false })
    uploadedCtxFiles.value.push(placeholder)
    try {
      const fd = new FormData()
      fd.append('file', file)
      const { data } = await apiAI.post(`/api/upload/reports/${meetingId}`, fd)
      placeholder.id = data.id
      placeholder.file_name = data.file_name
      placeholder.uploading = false
      selectedFiles.value.push(data.id)
      setTimeout(refreshArchive, 600)
    } catch {
      placeholder.uploading = false
      placeholder.error = true
    }
  }
}

function removeCtxFile(i) {
  const file = uploadedCtxFiles.value[i]
  if (file.id) selectedFiles.value = selectedFiles.value.filter(id => id !== file.id)
  uploadedCtxFiles.value.splice(i, 1)
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
        company: ag.company || '',
        dept: Array.isArray(ag.department) ? ag.department[0] || '' : ag.department || '',
        end_date: ag.due_date || '',
        _state: null,
        _editing: false,
        _editTitle: ag.title,
        _editCompany: ag.company || '',
        _editDept: Array.isArray(ag.department) ? ag.department[0] || '' : ag.department || '',
        _editStartDate: ag.start_date || '',
        _editEndDate: ag.due_date || '',
        _agentLogId: null,
        _showReason: false,
        _feedbackAction: '',
        _reason: '',
      }))
    } else {
      extractResult.value = []
    }
  } catch {
    extractResult.value = []
  }
}

// 과제추출 탭 활성화 시 draft 자동 체크
watch(detailTab, async tab => {
  if (
    tab === 'extract' &&
    !extractResult.value.length &&
    !extractLoading.value &&
    detailMeeting.value
  ) {
    await _restoreDrafts(detailMeeting.value.id)
  }
})

// 추출 결과를 채팅 메시지 형식으로 포맷
function _formatExtractForChat(agendas) {
  if (!agendas.length)
    return '추출된 아젠다가 없습니다. 회의록이나 자료를 추가 후 다시 시도해주세요.'
  const lines = [`${agendas.length}개 아젠다를 추출했습니다. 수정이 필요하면 말씀해 주세요.\n`]
  agendas.forEach((ag, i) => {
    lines.push(`**${i + 1}. ${ag.title}**`)
    const dates = [
      ag.start_date && `시작 ${ag.start_date}`,
      ag.end_date && `마감 ${ag.end_date}`,
    ].filter(Boolean)
    if (dates.length) lines.push(`  ${dates.join(' · ')}`)
    if (ag.dept) lines.push(`  담당: ${ag.dept}`)
    lines.push('')
  })
  return lines.join('\n').trim()
}

// 과제 탭에서 인라인으로 추출 실행
async function runExtract() {
  if (!detailMeeting.value) return

  const mgTitle = detailMeeting.value?.title || '회의체'

  // 채팅 초기화 후 사용자 메시지 + 사고 과정 + 에이전트 응답 슬롯을 순서대로 추가
  // managed open: watch 자동 히스토리 로드가 방금 세팅한 extract greeting/메시지를 덮어쓰지 않게 함
  openSidebarManaged()
  allMessages.value['supervisor'] = [{ role: 'agent', content: SUPERVISOR_EXTRACT.greeting }]
  showExtractFlow.value = true
  extractPhase.value = 'result'
  detailTab.value = 'extract'
  extractLoading.value = true
  agentLoading.value = true
  extractResult.value = []

  allMessages.value['supervisor'].push({
    role: 'user',
    content: `"${mgTitle}" 회의록·자료에서 아젠다를 추출해줘`,
  })
  const planningMsg = reactive({ role: 'planning', steps: [], open: true, done: false })
  allMessages.value['supervisor'].push(planningMsg)
  const agentMsg = reactive({ role: 'agent', content: '' })
  allMessages.value['supervisor'].push(agentMsg)

  await nextTick()
  if (agentMessagesEl.value) agentMessagesEl.value.scrollTop = agentMessagesEl.value.scrollHeight

  // 사고 과정 애니메이션과 API 호출을 병렬 실행
  const planningSteps = [
    `Neo4j MATCH (m:Meeting {title:"${mgTitle}"}) 조회`,
    `MATCH (mg)-[:ATTACHED_TO|PRODUCED]-(doc:Document) 문서 수집`,
    `선택된 회의록 및 첨부 파일 텍스트 분석 중...`,
    `Context Graph: 유사 Decision 노드 참조`,
    `아젠다 후보 생성 중...`,
  ]
  const planningPromise = _runPlanningSteps(planningMsg, planningSteps)

  try {
    const formData = new FormData()
    formData.append('meeting_id', String(toNumericId(detailMeeting.value.id)))
    formData.append(
      'selected_file_ids',
      JSON.stringify(selectedFiles.value.filter(f => !String(f).startsWith('upload_'))),
    )
    formData.append('selected_similar_docs', JSON.stringify(selectedSimilarDocs.value))

    const { data } = await apiAI.post('/api/agent/archive/extract-agendas', formData)
    await planningPromise

    if (data.agendas && data.agendas.length) {
      const agentLogId = data.agent_log_id || null
      extractResult.value = data.agendas.map(ag => ({
        ...ag,
        company: ag.company || '',
        dept: Array.isArray(ag.department) ? ag.department[0] || '' : ag.department || '',
        end_date: ag.due_date || '',
        _state: null,
        _editing: false,
        _editTitle: ag.title,
        _editCompany: ag.company || '',
        _editStartDate: ag.start_date || '',
        _editEndDate: ag.due_date || '',
        _editDept: Array.isArray(ag.department) ? ag.department[0] || '' : ag.department || '',
        db_id: ag.db_id || null,
        _agentLogId: agentLogId,
        _showReason: false,
        _feedbackAction: '',
        _reason: '',
      }))
      // 실제 추출 결과를 채팅에 표시
      agentMsg.content = _formatExtractForChat(extractResult.value)
    } else {
      const errMsg = data.error
        ? `추출 중 오류: ${data.error}`
        : '추출된 아젠다가 없습니다. 회의록이나 자료를 선택 후 다시 시도해주세요.'
      agentMsg.content = errMsg
      extractResult.value = []
    }
  } catch {
    await planningPromise
    agentMsg.content = '아젠다 추출 중 오류가 발생했습니다.'
    extractResult.value = []
  } finally {
    extractLoading.value = false
    agentLoading.value = false
    await nextTick()
    if (agentMessagesEl.value) agentMessagesEl.value.scrollTop = agentMessagesEl.value.scrollHeight
  }
}

function setExtractState(i, state) {
  extractResult.value[i]._state = extractResult.value[i]._state === state ? null : state
}
function addExtractItem() {
  extractResult.value.push({
    title: '',
    company: '',
    dept: '',
    db_id: null,
    start_date: '',
    end_date: '',
    _state: null,
    _editing: true,
    _editTitle: '',
    _editCompany: '',
    _editDept: '',
    _editStartDate: '',
    _editEndDate: '',
    _agentLogId: null,
    _showReason: false,
    _feedbackAction: '',
    _reason: '',
  })
}

async function approveItem(i) {
  const ag = extractResult.value[i]
  const meeting_id = toNumericId(detailMeeting.value.id)
  try {
    await apiAI.post('/api/agent/archive/agendas/commit', {
      meeting_id,
      approved: [
        {
          db_id: ag.db_id || null,
          title: ag.title,
          dept: Array.isArray(ag.dept) ? ag.dept[0] : ag.dept || null,
          start_date: ag.start_date || null,
          due_date: ag.end_date || null,
        },
      ],
      rejected_ids: [],
    })
    extractResult.value.splice(i, 1)
    detailAgendas.value = (await apiAI.get(`/api/agent/meetings/${meeting_id}/agendas`)).data || []
    setTimeout(refreshArchive, 600)
  } catch (e) {
    console.error('[approveItem] 실패:', e)
  }
}

async function rejectItem(i) {
  const ag = extractResult.value[i]
  const meeting_id = toNumericId(detailMeeting.value.id)
  try {
    if (ag.db_id) {
      await apiAI.post('/api/agent/archive/agendas/commit', {
        meeting_id,
        approved: [],
        rejected_ids: [ag.db_id],
      })
    }
    extractResult.value.splice(i, 1)
  } catch (e) {
    console.error('[rejectItem] 실패:', e)
  }
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
        title: a.title,
        company: a.company || null,
        dept: a.dept || null,
        start_date: a.start_date || null,
        due_date: a.end_date || null,
      })),
      rejected_ids: rejected.map(a => a.db_id),
    })

    detailAgendas.value =
      (await apiAI.get(`/api/agent/meetings/${toNumericId(detailMeeting.value.id)}/agendas`))
        .data || []
    extractPhase.value = 'context'
    showExtractFlow.value = false
    extractResult.value = []
    detailTab.value = 'task'
    setTimeout(refreshArchive, 600)
  } catch (e) {
    console.error('완료 처리 오류:', e)
  }
}

async function addDirectAgenda(form) {
  const meeting_id = toNumericId(detailMeeting.value.id)
  await apiAI.post('/api/agent/archive/agendas/commit', {
    meeting_id,
    approved: [
      {
        db_id: null,
        title: form.title,
        dept: form.dept || null,
        start_date: form.start_date || null,
        due_date: form.end_date || null,
      },
    ],
    rejected_ids: [],
  })
  // 아젠다 목록 즉시 갱신 (과제 탭)
  detailAgendas.value = (await apiAI.get(`/api/agent/meetings/${meeting_id}/agendas`)).data || []
  // 관계도 + 기본탭 로그: Neo4j 동기화 완료 후 두 번 갱신 (빠른 표시 + 확실한 반영)
  setTimeout(refreshArchive, 600)
  setTimeout(refreshArchive, 2500)
}

const PRIORITY_LABEL = {
  urgent_important: '긴급·중요',
  important: '중요',
  urgent: '긴급',
  normal: '보통',
  low: '낮음',
}
const STATUS_LABEL = { pending: '대기', in_progress: '진행', submitted: '승인대기', done: '완료' }
const NODE_TYPE_COLORS = {
  Meetings: '#3b82f6',
  agenda: '#f59e0b',
  session: '#f97316',
  minutes: '#60a5fa',
  report: '#34d399',
  dept: '#8b5cf6',
  person: '#f472b6',
  company: '#0d9488',
}

function goToProcessStep(step) {
  if (step === 'context') {
    extractPhase.value = 'context'
    extractResult.value = []
  }
}

// ─── 회의체 설정 모달 ────────────────────────────────────────────
const settingsModal = ref(null)
const savingSettings = ref(false)

async function openGroupSetting() {
  if (!detailMeeting.value) return
  const m = detailMeeting.value
  const numId = toNumericId(m.id)

  let pgMeeting = null
  try {
    const r = await api.get(`/api/v1/meetings/${numId}`)
    pgMeeting = r.data
  } catch {
    /* fallback */
  }
  const src = pgMeeting || m

  let members
  try {
    const res = await api.get(`/api/v1/meetings/${numId}/members`)
    members = res.data.map(mb => ({
      id: mb.id,
      userId: mb.user?.id || mb.user_id,
      name: mb.user?.name || mb.userName || mb.name || '?',
      email: mb.user?.email || mb.email || '',
      department: mb.user?.department || mb.department || '',
      company: mb.user?.company || mb.company || '',
      position: mb.user?.position || mb.position || '',
      role: mb.role || 'member',
    }))
  } catch {
    members = (m.members || []).map(mb => ({
      id: null,
      userId: mb.userId,
      name: mb.userName || mb.name || '?',
      email: mb.email || '',
      department: mb.department || '',
      position: mb.position || '',
      role: mb.role || 'member',
    }))
  }
  settingsModal.value = {
    meeting: { ...m, _numId: numId },
    form: {
      title: src.title || '',
      purpose: src.description || src.purpose || '',
      guidelines: src.guidelines || '',
      context: src.context || '',
      meeting_type: src.meeting_type || src.type || 'Weekly',
      start_date: src.start_date ? String(src.start_date).slice(0, 10) : '',
      end_date: src.end_date ? String(src.end_date).slice(0, 10) : '',
    },
    members,
    removedIds: [],
  }
}

function closeSettings() {
  settingsModal.value = null
}

async function saveSettings() {
  if (!settingsModal.value) return
  savingSettings.value = true
  const { meeting, form, members, removedIds } = settingsModal.value
  const numId = meeting._numId || toNumericId(meeting.id)
  try {
    await api.patch(`/api/v1/meetings/${numId}`, {
      title: form.title,
      description: form.purpose,
      guidelines: form.guidelines,
      context: form.context || null,
      start_date: form.start_date || null,
      end_date: form.end_date || null,
      meeting_type: form.meeting_type || null,
    })
    for (const memberId of removedIds) {
      await api.delete(`/api/v1/meetings/${numId}/members/${memberId}`)
    }
    for (const mb of members.filter(m => m.id === null)) {
      await api.post(`/api/v1/meetings/${numId}/members`, { userId: mb.userId, role: mb.role })
    }
    if (detailMeeting.value?.id === meeting.id) {
      detailMeeting.value.title = form.title
      detailMeeting.value.purpose = form.purpose
      detailMeeting.value.guidelines = form.guidelines
      detailMeeting.value.context = form.context
    }
    await meetingsStore.fetchMeetings()
    settingsModal.value = null
    // Neo4j 동기화 반영 후 그래프 재로드
    setTimeout(refreshArchive, 600)
  } catch (e) {
    toast.error(e.response?.data?.detail || '저장 실패')
  } finally {
    savingSettings.value = false
  }
}

// ─── Role-based helpers ───────────────────────────────────────
/** 현재 로그인 유저가 해당 회의체 members 배열에서 가지는 역할(admin/member)을 찾는다.
 *  meetingRoles(SpringBoot)가 비어 있어도 Neo4j archive 응답의 members로 판정 가능. */
function selfRoleInGroup(group) {
  const myId = authStore.user?.id
  const myEmail = currentPerson.value?.email || authStore.user?.email || authStore.user?.employee_id
  const myName = currentPerson.value?.name || authStore.user?.name
  const self = (group?.members || []).find(
    mb =>
      (myId != null &&
        mb.userId != null &&
        String(mb.userId).replace(/\D/g, '') === String(myId)) ||
      (myEmail && mb.email && mb.email === myEmail) ||
      (myName && (mb.userName === myName || mb.name === myName)),
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
// 시스템관리자는 간사가 아니어도 회의체 설정/종료/삭제 등 편집 가능
const isDetailAdmin = computed(() => authStore.isStrategicTeam || detailMyRole.value === 'admin')
const isAnyAdmin = computed(() => {
  if (authStore.isStrategicTeam) return true
  // PostgreSQL 기반 role 확인
  if (Object.values(meetingsStore.meetingRoles).some(r => r === 'admin')) return true
  // Neo4j 기반: meetings의 members 배열에서 현재 유저 role 확인
  const myEmail = currentPerson.value?.email || authStore.user?.employee_id
  const myName = currentPerson.value?.name || authStore.user?.name
  return neo4jMeetings.value.some(mg =>
    (mg.members || []).some(
      mb => (mb.email === myEmail || mb.userName === myName) && mb.role === 'admin',
    ),
  )
})
// 회사명·부서명 변경 권한: SYSTEM_ADMIN 또는 COMPANY_ADMIN (백엔드가 같은 회사 여부를 최종 검증)
const canEditCompany = computed(
  () => authStore.isStrategicTeam || authStore.user?.role === 'COMPANY_ADMIN',
)
const canEditDept = canEditCompany
function goToList(meetingId) {
  _listSnapshot.expandedMeeting = meetingId || null
  viewMode.value = 'list'
  detailOpen.value = false
}

async function openDetail(groupData) {
  if (!groupData) return
  const isSameMeeting = detailMeeting.value?.id === groupData.id
  detailMeeting.value = groupData
  detailOpen.value = true
  detailTab.value = 'basic'
  detailNode.value = null
  relAddActive.value = false
  if (!isSameMeeting) {
    selectedMinutes.value = []
    selectedFiles.value = []
    selectedSimilarDocs.value = []
    uploadedCtxFiles.value = []
    extractPhase.value = 'context'
    showExtractFlow.value = false
    extractResult.value = []
  }
  hoverNode.value = null
  detailAgendas.value = []

  const numId = _toNumericId(groupData.id)

  if (numId > 0) {
    const [agendasRes, deleteLogsRes] = await Promise.allSettled([
      apiAI.get(`/api/agent/meetings/${numId}/agendas`),
      apiAI.get(`/api/agent/meetings/${numId}/agenda-delete-logs`),
    ])
    detailAgendas.value =
      agendasRes.status === 'fulfilled'
        ? agendasRes.value.data || []
        : (groupData.tasks || []).filter(t => t.status !== 'draft')
    if (agendasRes.status === 'rejected') {
      console.error(
        `[Task] 과제 로드 실패 (meeting=${numId}):`,
        agendasRes.reason?.response?.status,
      )
    }
    const meetingKey = String(groupData.id)
    const sessionLogs = deletedAgendaLogs.value.filter(l => l.meetingId === meetingKey)
    const apiLogs =
      deleteLogsRes.status === 'fulfilled'
        ? (deleteLogsRes.value.data || []).map(r => ({
            meetingId: meetingKey,
            agendaId: r.agenda_id,
            title: r.title,
            agendaCreatedAt: r.agenda_created_at || null,
            deletedAt: r.deleted_at,
          }))
        : []
    const apiIds = new Set(apiLogs.map(l => l.agendaId))
    deletedAgendaLogs.value = [
      ...deletedAgendaLogs.value.filter(l => l.meetingId !== meetingKey),
      ...apiLogs,
      ...sessionLogs.filter(l => !apiIds.has(l.agendaId)),
    ]
  } else {
    detailAgendas.value = (groupData.tasks || []).filter(t => t.status !== 'draft')
  }

  if (!groupAgendaRatio.value.has(groupData.id)) {
    const total = detailAgendas.value.length
    const done = detailAgendas.value.filter(t => t.status === 'done').length
    groupAgendaRatio.value = new Map(groupAgendaRatio.value).set(
      groupData.id,
      total ? done / total : null,
    )
  }

  // draft 아젠다 복원 (다른 회의체로 전환 시)
  if (!isSameMeeting) {
    await _restoreDrafts(groupData.id)
  }
}

let gNodes = [],
  gEdges = []
const gNodesRef = shallowRef([]) // reactive mirror for provide/inject
const selfPersonNodeId = computed(() => {
  const myId = authStore.user?.id
  const myName = currentPerson.value?.name || authStore.user?.name
  const node = gNodesRef.value.find(n => {
    if (n.type !== 'person') return false
    const mb = n.data
    if (myId != null && mb?.userId != null && String(mb.userId).replace(/\D/g, '') === String(myId))
      return true
    if (myName && n.label === myName) return true
    return false
  })
  return node?.id ?? null
})
// ─── 로컬 관계 오버라이드: refreshArchive 후에도 유지 ────────
// key 형식: "fromNodeId|toNodeId" (양방향 모두 등록)
const localDeletedEdges = new Set()
const localAddedEdges = [] // [{fromId, toId, rel}]
function _applyLocalEdgeOverrides(nodes, edges) {
  // 1) 삭제된 관계 제거
  let result = edges.filter(e => {
    const fId = nodes[e.from]?.id,
      tId = nodes[e.to]?.id
    return !localDeletedEdges.has(`${fId}|${tId}`) && !localDeletedEdges.has(`${tId}|${fId}`)
  })
  // 2) 추가된 관계 삽입
  localAddedEdges.forEach(({ fromId, toId, rel }) => {
    const fi = nodes.findIndex(n => n.id === fromId)
    const ti = nodes.findIndex(n => n.id === toId)
    if (fi >= 0 && ti >= 0 && !result.find(e => e.from === fi && e.to === ti && e.rel === rel)) {
      result.push({ from: fi, to: ti, rel })
    }
  })
  return result
}
// ─── Upload modal ──────────────────────────────────────────────

// 발제자료 AI 검토 기준 4개 항목
const PRESENTATION_CRITERIA = [
  { key: 'recap', label: '지난 논의 Recap', desc: '이전 회의 논의사항 및 결정 사항 요약 포함' },
  {
    key: 'progress',
    label: '아젠다별 구체적 Progress',
    desc: '각 아젠다별 현재까지의 구체적인 진행 현황',
  },
  {
    key: 'hurdle',
    label: 'Hurdle & Pain point 극복 방안',
    desc: '추진 과정상 장애요인 및 해결 방안 제시',
  },
  {
    key: 'plan',
    label: '구체적 실행 계획 (Milestone)',
    desc: '명확한 목표(수치), 100일/300일/1,000일 단위 계획',
  },
]

const showUploadModal = ref(false)
const uploadForm = ref({
  label: '',
  fileType: '보고자료',
  connectNodeId: '',
  relType: '생성',
  meetingId: '',
  relatedAgendaIds: [],
  agendaContent: '',
  file: null,
})
// 드래그로 자동 입력된 필드 추적 (직접 선택 시에는 표시 안 함)
const prefilledCtx = ref({ meetingId: false, connectNodeId: false, relatedAgendaId: false })

let _pendingRelatedAgendaId = ''
watch(
  () => uploadForm.value.meetingId,
  id => {
    const pendingAgenda = _pendingRelatedAgendaId
    _pendingRelatedAgendaId = ''
    uploadForm.value.relatedAgendaIds = []
    if (!id) return
    if (pendingAgenda) uploadForm.value.relatedAgendaIds = [pendingAgenda]

    // dept 노드가 없으면 PostgreSQL에서 멤버 fetch (새 회의체 대응)
    const numericId = toNumericId(id)
    const hasDeptNodes = gNodesRef.value.some(n => n.type === 'dept' && n.meetingId === id)
    if (!hasDeptNodes && numericId) {
      meetingsStore.fetchMembers(numericId)
    }
  },
)

// connectNodeId가 Meetings이면 meetingId 자동 동기화
watch(
  () => uploadForm.value.connectNodeId,
  nodeId => {
    if (!nodeId) return
    const node = gNodes.find(n => n.id === nodeId)
    if (node?.type === 'Meetings') {
      const mgData = node.data
      const rawId = mgData?.id ?? nodeId
      uploadForm.value.meetingId =
        typeof rawId === 'string' && rawId.includes('-') ? rawId : `mg-${rawId}`
    }
  },
)

// ─── 파일 노드 AI 검토 패널 ────────────────────────────────────
// ─── 관계 스키마 (SSOT: backend/fastapi/rel_schema.py, 프런트 모듈로 단일화) ──────
// REL_COLORS·REL_MATRIX·autoRelByType는 src/graph/relSchema.js에서 가져온다.
function autoRel(sourceNodeId, targetType) {
  const srcNode = gNodes.find(n => n.id === sourceNodeId)
  return autoRelByType(srcNode?.type, targetType)
}

// ─── Relationship manager ─────────────────────────────────────
const graphVersion = ref(0) // bump to force sidebar reactivity when gEdges mutate

const currentNodeId = computed(() => {
  if (detailMeeting.value) {
    // gNodes의 mgNodeId 생성 로직과 동일하게 맞춤:
    // g.id가 문자열이고 '-'를 포함하면 그대로, 아니면 "mg-{id}"
    const rawId = detailMeeting.value.id
    return typeof rawId === 'string' && rawId.includes('-') ? rawId : `mg-${rawId}`
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
      toNode: gNodes[e.to],
      rel: e.rel,
      direction: e.from === idx ? 'out' : 'in',
    }))
})

const allGraphNodeList = computed(() => {
  graphVersion.value
  return gNodes.map(n => ({ id: n.id, label: n.label, type: n.type }))
})

const relAddActive = ref(false)
const relAddForm = ref({ fromId: '', toId: '', rel: '참조' })

// Auto-suggest rel type when src/dst change in add form
watch(
  () => [relAddForm.value.fromId, relAddForm.value.toId],
  ([fId, tId]) => {
    if (!fId || !tId) return
    const tNode = gNodes.find(n => n.id === tId)
    relAddForm.value.rel = autoRel(fId, tNode?.type || '') || '참조'
  },
)

// Neo4j mg-003 → 정수 ID 추출
function _toNumericId(id) {
  if (!id) return id
  if (/^\d+$/.test(String(id))) return id
  const m = String(id).match(/\d+$/)
  return m ? Number(m[0]) : id
}
function _normalizeNeo4jId(raw) {
  if (!raw) return raw
  const prefixes = ['mg-', 'session-', 'agenda-', 'doc-', 'dept-', 'p-', 'company-']
  for (const p of prefixes) {
    if (raw.startsWith(p + p)) return raw.slice(p.length)
  }
  return raw
}
async function doDeleteEdge(edgeIdx) {
  if (!(await confirmDialog('이 관계를 삭제하시겠습니까?', { danger: true }))) return
  const e = gEdges[edgeIdx]
  const fromNode = gNodes[e?.from],
    toNode = gNodes[e?.to]
  // 로컬 오버라이드에 기록 (rebuild 후에도 삭제 유지)
  if (fromNode && toNode) {
    localDeletedEdges.add(`${fromNode.id}|${toNode.id}`)
    localDeletedEdges.add(`${toNode.id}|${fromNode.id}`)
    // localAddedEdges에서도 제거
    const ai = localAddedEdges.findIndex(x => x.fromId === fromNode.id && x.toId === toNode.id)
    if (ai >= 0) localAddedEdges.splice(ai, 1)
    // Neo4j 동기화
    apiAI
      .delete('/api/neo4j/relationships', {
        data: {
          from_id: _normalizeNeo4jId(fromNode.neo4jId || fromNode.id),
          rel_type: e.rel || '',
          to_id: _normalizeNeo4jId(toNode.neo4jId || toNode.id),
        },
      })
      .then(() => setTimeout(refreshArchive, 600))
      .catch(() =>
        toast.error('관계 삭제를 서버에 반영하지 못했습니다. 새로고침 시 다시 나타날 수 있습니다.'),
      )
  }
  gEdges.splice(edgeIdx, 1)
  graphVersion.value++
}
function openAddRel() {
  relAddForm.value = { fromId: currentNodeId.value || '', toId: '', rel: '참조' }
  relAddActive.value = true
}
async function doAddRel() {
  const { fromId, toId } = relAddForm.value
  if (!fromId || !toId || fromId === toId) return
  let fromIdx = gNodes.findIndex(n => n.id === fromId)
  let toIdx = gNodes.findIndex(n => n.id === toId)
  if (fromIdx < 0 || toIdx < 0) return
  // 단방향 저장 원칙 — 역방향이 이미 있어도 중복으로 간주 (GraphRAG 확장 시 중복 경로 방지)
  if (
    gEdges.find(
      e => (e.from === fromIdx && e.to === toIdx) || (e.from === toIdx && e.to === fromIdx),
    )
  ) {
    showMapToast('이미 연결된 노드입니다.')
    return
  }
  // canonical 방향 보정 — 매트릭스가 역방향만 정의하면 저장 방향을 뒤집는다
  const { rel, reversed } = resolveCanonical(gNodes[fromIdx].type, gNodes[toIdx].type)
  if (reversed) {
    ;[fromIdx, toIdx] = [toIdx, fromIdx]
  }
  const fromNode = gNodes[fromIdx],
    toNode = gNodes[toIdx]
  // 로컬 오버라이드에 기록
  localAddedEdges.push({ fromId: fromNode.id, toId: toNode.id, rel })
  localDeletedEdges.delete(`${fromNode.id}|${toNode.id}`)
  localDeletedEdges.delete(`${toNode.id}|${fromNode.id}`)
  gEdges.push({ from: fromIdx, to: toIdx, rel })
  relAddActive.value = false
  graphVersion.value++
  // Neo4j 동기화
  apiAI
    .post('/api/neo4j/relationships', {
      from_id: _normalizeNeo4jId(fromNode.neo4jId || fromNode.id),
      rel_type: rel,
      to_id: _normalizeNeo4jId(toNode.neo4jId || toNode.id),
    })
    .then(() => setTimeout(refreshArchive, 600))
    .catch(() =>
      toast.error('관계 추가를 서버에 반영하지 못했습니다. 새로고침 시 사라질 수 있습니다.'),
    )
}

const connectableNodes = computed(() => {
  const groups = meetings.value
  // '나' 노드: currentPerson.value.id = Neo4j User ID (e.g. 'p-123')
  // buildGraphNodes에서 생성되는 person 노드 ID 포맷: `person-${mb.userId}` 와 일치
  const result = []
  const myNeo4jId = currentPerson.value?.id
  const myLabel = currentPerson.value?.name || authStore.user?.name || '나'
  if (myNeo4jId) {
    result.push({
      id: `person-${myNeo4jId}`,
      label: `나 (${myLabel})`,
      typeLabel: '구성원',
      type: 'person',
      neo4jId: myNeo4jId,
    })
  }
  const depts = new Set()
  groups.forEach(g =>
    (g.members || []).forEach(mb => depts.add(mb.department || mb.dept || '미지정')),
  )
  depts.forEach(d => result.push({ id: `dept-${d}`, label: d, typeLabel: '부서', type: 'dept' }))
  groups.forEach(g => {
    const rawId = g.id
    const mgId = typeof rawId === 'string' && rawId.includes('-') ? rawId : `mg-${rawId}`
    result.push({ id: mgId, label: g.title, typeLabel: '회의체', type: 'Meetings' })
  })
  groups.forEach(g =>
    (g.minutes || []).forEach((m, i) =>
      result.push({
        id: `session-${g.id}-${i}`,
        sessionId: m.id,
        label: m.session_title || `${m.session_number || i + 1}차 회의`,
        typeLabel: '회의',
        type: 'session',
      }),
    ),
  )
  return result
})

// ─── Upload: connectable nodes (Meetings / dept / agenda) ──────────────
const deptConnectableNodes = computed(() => {
  const nodes = gNodesRef.value
  const seen = new Set()
  if (uploadForm.value.meetingId) {
    const fromGraph = nodes
      .filter(n => n.type === 'dept' && n.meetingId === uploadForm.value.meetingId)
      .filter(n => {
        if (seen.has(n.label)) return false
        seen.add(n.label)
        return true
      })
      .map(n => ({ id: n.id, label: n.label, typeLabel: '부서', type: 'dept' }))
    if (fromGraph.length > 0) return fromGraph

    // Neo4j에 dept 노드가 없는 경우(새 회의체 등) → PostgreSQL 멤버 데이터로 폴백
    const deptSeen = new Set()
    return meetingsStore.currentMembers
      .map(m => m.user?.department || m.department || '')
      .filter(d => d && !deptSeen.has(d) && deptSeen.add(d))
      .map(d => ({ id: `dept-${d}`, label: d, typeLabel: '부서', type: 'dept' }))
  }
  return nodes
    .filter(n => n.type === 'dept')
    .filter(n => {
      if (seen.has(n.label)) return false
      seen.add(n.label)
      return true
    })
    .map(n => ({ id: n.id, label: n.label, typeLabel: '부서', type: 'dept' }))
})

// 선택된 회의체 노드에 연결된 과제 목록
const 업로드회의체과제 = computed(() => {
  const nodes = gNodesRef.value
  if (!uploadForm.value.meetingId) return []
  const mapAgendas = nodes.filter(
    n => n.type === 'agenda' && n.meetingId === uploadForm.value.meetingId,
  )
  if (mapAgendas.length > 0) {
    return mapAgendas.map(n => ({
      id: n.neo4jId || n.id,
      content: n.data?.content || n.label,
      agenda_id: n.data?.pg_id ?? null,
    }))
  }
  const mgNode = gNodes.find(n => n.id === uploadForm.value.meetingId && n.type === 'Meetings')
  if (mgNode?.data?.tasks?.length) return mgNode.data.tasks
  return []
})

// person 노드 → 참여 회의체 목록
function personMeetings(node) {
  if (!node) return []
  const name = node.label
  return meetings.value
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
  return meetings.value.flatMap(mg => (mg.tasks || []).filter(t => t.assignee_name === name))
}

// report 노드 → 연관 과제(아젠다) 목록
function reportRelatedAgendas(node) {
  if (!node) return []
  // related_agenda_ids는 'agenda-263' 또는 263 혼재 → 끝의 숫자만 비교 (UX-3/5: ID 형식 불일치로
  // 항상 빈 목록이 되던 버그 수정). 노드 data.id도 동일 방식으로 정규화.
  const norm = v => String(v ?? '').match(/\d+$/)?.[0] ?? ''
  const ids = new Set((node.data?.related_agenda_ids || []).map(norm).filter(Boolean))
  if (!ids.size) return []
  return gNodesRef.value.filter(n => n.type === 'agenda' && ids.has(norm(n.data?.id)))
}

// ─── Upload: AI analysis state ────────────────────────────────
const uploadStep = ref(1) // 1=manual input, 2=AI analysis result
const aiAnalyzing = ref(false)
const aiResult = ref(null) // { score, feedback, agendas, related_depts }
const aiStreamText = ref('') // 스트리밍 중 LLM 토큰 누적 텍스트
const aiStreamStage = ref('') // 현재 진행 단계 메시지
const reportId = ref(null) // AI 검토 시작 시 생성된 report ID
const uploadedFilePath = ref('') // R2 업로드된 파일 경로
const isResubmit = ref(false) // 재검토 모드 여부
const isResultReadOnly = ref(false) // 이미 결정된 보고서 결과 보기 전용
const rejectedReports = ref([]) // 반려된 보고서 목록
const selectedParentId = ref(null) // 선택된 원본 report ID
const selectedAgendas = ref([]) // indices of agendas to apply
const selectedRelDepts = ref([]) // dept names to auto-connect

function openUploadModal(ctx = {}) {
  showUploadModal.value = true
  uploadStep.value = 1
  aiResult.value = null
  aiStreamText.value = ''
  aiStreamStage.value = ''
  selectedAgendas.value = []
  selectedRelDepts.value = []
  reportId.value = null
  uploadedFilePath.value = ''
  isResubmit.value = false
  selectedParentId.value = null
  // 드래그로 자동 입력된 필드 기록
  prefilledCtx.value = {
    meetingId: !!ctx.meetingId,
    connectNodeId: !!ctx.connectNodeId,
    relatedAgendaId: !!ctx.relatedAgendaId,
  }
  // store pending relatedAgendaId so the meetingId watcher can restore it after fetching agendas
  _pendingRelatedAgendaId = String(ctx.relatedAgendaId || '')
  uploadForm.value = {
    label: '',
    fileType: '보고자료',
    connectNodeId: ctx.connectNodeId || '',
    relType: '생성',
    meetingId: ctx.meetingId || '',
    relatedAgendaIds: ctx.relatedAgendaId ? [String(ctx.relatedAgendaId)] : [],
    agendaContent: ctx.agendaContent || '',
    file: null,
  }
}

// Build graph context string for AI
function buildGraphContextStr() {
  const nodes = gNodes.map(n => `[${n.type}] ${n.label}`).join(', ')
  const edges = gEdges
    .map(e => {
      const f = gNodes[e.from],
        t = gNodes[e.to]
      return f && t ? `${f.label} →(${e.rel})→ ${t.label}` : null
    })
    .filter(Boolean)
    .slice(0, 30)
    .join('; ')
  return `노드: ${nodes}\n관계: ${edges}`
}

async function runAiAnalysis() {
  if (!uploadForm.value.label.trim() || !uploadForm.value.connectNodeId) return
  isResultReadOnly.value = false
  aiAnalyzing.value = true
  uploadStep.value = 2
  aiResult.value = null
  aiStreamText.value = ''
  aiStreamStage.value = '검토를 시작합니다…'
  const deptNode =
    connectableNodes.value.find(n => n.id === uploadForm.value.connectNodeId) ||
    deptConnectableNodes.value.find(n => n.id === uploadForm.value.connectNodeId)

  const _mid = String(uploadForm.value.meetingId || '').replace(/^mg-/, '')

  // 파일을 먼저 R2에 업로드 → reports 테이블에 pending으로 저장
  if (uploadForm.value.file && _mid && /^\d+$/.test(_mid)) {
    try {
      const uploadFd = new FormData()
      uploadFd.append('file', uploadForm.value.file)
      uploadFd.append('dept_name', deptNode?.label || '')
      uploadFd.append('related_agenda_ids', JSON.stringify(uploadForm.value.relatedAgendaIds || []))
      if (selectedParentId.value) {
        uploadFd.append('parent_report_id', String(selectedParentId.value))
      }
      const { data: uploadData } = await apiAI.post(`/api/upload/reports/${_mid}`, uploadFd, {
        headers: { 'Content-Type': 'multipart/form-data' },
      })
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
  fd.append(
    'candidate_agendas',
    JSON.stringify(
      업로드회의체과제.value.map(t => ({
        id: String(t.agenda_id ?? t.id),
        content: t.content,
      })),
    ),
  )

  const applyResult = data => {
    aiResult.value = data
    selectedAgendas.value = (data.agendas || []).map((_, i) => i) // 기본 전체 선택
    selectedRelDepts.value = [...(data.related_depts || [])] // 기본 전체 선택

    // AI가 자동으로 연관 과제(복수)를 판별 → 드래그로 이미 지정한 경우가 아니면 적용
    const aiMatchedIds = (data.matched_agendas || [])
      .map(m => String(m.id))
      .filter(id => id && id !== 'null')
    if (aiMatchedIds.length && !prefilledCtx.value.relatedAgendaId) {
      uploadForm.value.relatedAgendaIds = [...new Set(aiMatchedIds)]
    } else if (aiMatchedIds.length) {
      // 드래그로 지정된 과제는 유지하되 AI 추천을 추가
      uploadForm.value.relatedAgendaIds = [
        ...new Set([...uploadForm.value.relatedAgendaIds, ...aiMatchedIds]),
      ]
    }
  }

  try {
    await streamPostForm('/api/agent/archive/analyze-file/stream', fd, ev => {
      if (ev.type === 'status') {
        aiStreamStage.value = ev.message || ''
      } else if (ev.type === 'token') {
        aiStreamText.value += ev.content || ''
      } else if (ev.type === 'result') {
        applyResult(ev.data || {})
      }
    })
  } catch {
    aiResult.value = {
      score: 70,
      feedback: ['AI 분석 서버에 연결할 수 없습니다.'],
      matched_agendas: [],
      agendas: [],
      related_depts: [],
      criteria:
        uploadForm.value.fileType === '발제자료'
          ? { recap: false, progress: false, hurdle: false, plan: false }
          : null,
    }
  } finally {
    aiAnalyzing.value = false
    aiStreamStage.value = ''
    // AI 결과를 report_scores에 저장
    if (reportId.value && aiResult.value?.score != null) {
      apiAI
        .post(`/api/upload/reports/${reportId.value}/score`, {
          score: aiResult.value.score,
          feedback: aiResult.value.feedback ?? [],
          detail_scores: aiResult.value.detail_scores ?? {},
          top_improvements: aiResult.value.top_improvements ?? [],
        })
        .catch(e => console.warn('[runAiAnalysis] 점수 저장 실패:', e))
    }
  }
}

function doAddFile() {
  if (!uploadForm.value.label.trim()) return
  const fromNode = gNodes.find(n => n.id === uploadForm.value.connectNodeId)
  const fromIdx = fromNode ? gNodes.indexOf(fromNode) : -1
  const fileNodeId = `file-new-${Date.now()}`

  // 연결 노드의 Meetings를 찾아 groupIdx 상속 (getVisibleSet에서 가시성 포함되도록)
  const mgNode = gNodes.find(n => n.id === uploadForm.value.meetingId && n.type === 'Meetings')

  // 연관 과제(복수)가 선택된 경우 agenda 노드들에 연결, 아니면 부서 노드에 연결
  const relAgendaIds = uploadForm.value.relatedAgendaIds || []
  const agendaNodes = relAgendaIds
    .map(id => gNodes.find(n => n.type === 'agenda' && (n.neo4jId === id || n.id === id)))
    .filter(Boolean)
  const primaryAgenda = agendaNodes[0] || null
  const anchorNode = primaryAgenda || fromNode // 위치·엣지 기준 노드
  const anchorIdx = primaryAgenda ? gNodes.indexOf(primaryAgenda) : fromIdx

  const anchorX = anchorNode?.x || 0,
    anchorZ = anchorNode?.z || 0
  const phi = Math.atan2(anchorZ, anchorX) + 0.28
  const baseR = Math.sqrt(anchorX * anchorX + anchorZ * anchorZ)

  const newNode = {
    id: fileNodeId,
    label: uploadForm.value.label,
    type: uploadForm.value.fileType === '회의록' ? 'minutes' : 'report',
    fileType: uploadForm.value.fileType,
    aiScore: aiResult.value?.score ?? null,
    aiReview: aiResult.value ? { ...aiResult.value } : null,
    filePath: uploadedFilePath.value || null,
    reportId: reportId.value || null,
    extractedAgendas: [],
    groupIdx: mgNode?.groupIdx,
    meetingId: uploadForm.value.meetingId,
    x: Math.cos(phi) * (baseR + 90),
    y: (anchorNode?.y || 0) + 42,
    z: Math.sin(phi) * (baseR + 90),
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
        apiAI
          .post('/api/neo4j/relationships', {
            from_id: `report-${reportId.value}`,
            from_label: 'Document',
            to_id: ag.neo4jId,
            to_label: 'Agenda',
            rel_type: '첨부',
          })
          .catch(e => console.warn('[doAddFile] agenda 관계 Neo4j 저장 실패:', e))
      }
    })
  } else if (anchorIdx >= 0) {
    gEdges.push({
      from: fileIdx,
      to: anchorIdx,
      rel: autoRel(uploadForm.value.connectNodeId, 'report'),
    })
  }

  // AI가 추천한 유관부서 자동 연결
  selectedRelDepts.value.forEach(deptName => {
    const deptId = `dept-${deptName}`
    let deptNodeIdx = gNodes.findIndex(n => n.id === deptId)
    if (deptNodeIdx < 0) {
      const angle = Math.random() * Math.PI * 2
      gNodes.push({
        id: deptId,
        label: deptName,
        type: 'dept',
        groupIdx: mgNode?.groupIdx,
        x: Math.cos(angle) * 100,
        y: 20,
        z: Math.sin(angle) * 100,
      })
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
      x: Math.cos(agAngle) * (baseR + 140),
      y: (fromNode?.y || 0) - 20,
      z: Math.sin(agAngle) * (baseR + 140),
    })
    gEdges.push({ from: fileIdx, to: gNodes.length - 1, rel: '생성' })
  })

  showUploadModal.value = false
  graphViewRef.value?.reloadGraph(gNodes, gEdges)
  setTimeout(refreshArchive, 1200)
}

// PostgreSQL 기준 유효 ID 집합 — 삭제된 회의체를 Neo4j/fallback에서 제거하기 위해 사용
function _isValidMeeting(mgId) {
  if (!meetingsStore.meetings.length) return true // 아직 로드 전이면 필터 안 함
  const s = String(mgId)
  const numId = s.startsWith('mg-sqlite-')
    ? parseInt(s.slice(10))
    : s.startsWith('mg-')
      ? parseInt(s.slice(3))
      : parseInt(s)
  return meetingsStore.meetings.some(m => m.id === numId)
}

const meetings = computed(() => {
  // Neo4j 데이터가 있으면 우선 사용 — PostgreSQL에서 삭제된 항목 제외
  if (neo4jMeetings.value.length > 0) {
    const neo4jResult = neo4jMeetings.value.filter(mg => _isValidMeeting(mg.id))

    // Neo4j 동기화 전(생성 직후)에도 PG 회의체가 목록에 보이도록 보완
    const neo4jNumIds = new Set(
      neo4jResult.map(mg => {
        const s = String(mg.id)
        return s.startsWith('mg-') ? parseInt(s.slice(3)) : parseInt(s)
      }),
    )
    const pgOnly = meetingsStore.meetings
      .filter(m => m.status !== 'deleted' && !neo4jNumIds.has(m.id))
      .map(m => ({
        id: `mg-${m.id}`,
        title: m.title,
        meeting_type: m.meeting_type || null,
        status: m.status || 'active',
        minutes: [],
        reports: [],
        members: [],
        tasks: [],
        agendas: [],
        sessions: [],
      }))

    return [...neo4jResult, ...pgOnly]
  }

  // fallback: PostgreSQL 기반 조합
  const map = new Map()
  // 본인이 참여 중인 회의체만 포함
  meetingsStore.meetings
    .filter(m => meetingsStore.meetingRoles[m.id] != null)
    .forEach(m => {
      map.set(m.id, {
        id: m.id,
        title: m.title,
        meeting_type: m.meeting_type || null,
        status: m.status || 'active',
        minutes: [],
        reports: [],
        members: [],
        tasks: [],
      })
    })
  // Add minutes & reports
  minutes.value.forEach(m => {
    if (!map.has(m.meeting_id))
      map.set(m.meeting_id, {
        id: m.meeting_id,
        title: m.meeting_title,
        minutes: [],
        reports: [],
        members: [],
        tasks: [],
      })
    map.get(m.meeting_id).minutes.push(m)
  })
  reports.value.forEach(r => {
    if (!map.has(r.meeting_id))
      map.set(r.meeting_id, {
        id: r.meeting_id,
        title: r.meeting_title,
        minutes: [],
        reports: [],
        members: [],
        tasks: [],
      })
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
  meetings,
  membersData,
  tasksData,
  detailMeeting,
  detailTab,
  showExtractFlow,
  extractPhase,
  extractResult,
  toNumericId,
  onQueryHighlight: step => _applyQueryHL(step),
  onLabelsHighlight: labels => _applyHighlightLabels(labels),
  onQueryClear: () => {
    if (queryHlIdxs.value.size > 0 && !_hlPersistTimer) _applyQueryHL('')
  },
})
const {
  SUPERVISOR_EXTRACT,
  agentSidebarOpen,
  allMessages,
  agentLoading,
  agentMessagesEl,
  _runPlanningSteps,
  initAgentGreeting,
  runRelationshipAnalysis,
  openSidebarManaged,
} = agentChat
provide('agentSidebar', agentChat)

// ─── 관계도 분석·재설정 (Supervisor → Knowledge agent) ─────────
// 새로고침 버튼 클릭 시 AI가 Neo4j 소속 관계를 분석/재설정하고 근거를 보고합니다.
const analyzingRelations = ref(false)
async function analyzeRelationships() {
  if (analyzingRelations.value) return
  analyzingRelations.value = true
  try {
    await runRelationshipAnalysis(async () => {
      await refreshArchive()
    })
  } finally {
    analyzingRelations.value = false
  }
}

// ─── 목록 필터 ────────────────────────────────────────────────
const HISTORY_TYPE_OPTIONS = [
  { label: '자료 유형 전체', value: '' },
  { label: '회의록', value: 'minutes' },
  { label: '보고자료', value: 'report' },
]
const selectedHistoryType = ref('')
const selectedMeetingType = ref('')

const meetingTypeOptions = computed(() => {
  const types = [...new Set(meetings.value.map(g => g.meeting_type).filter(Boolean))]
  return [{ label: '회의체 유형 전체', value: '' }, ...types.map(t => ({ label: t, value: t }))]
})

const availableYears = computed(() => {
  const years = new Set()
  meetings.value.forEach(g => {
    const addYear = d => {
      if (!d) return
      const y = new Date(d).getFullYear()
      if (!isNaN(y) && y > 2000) years.add(y)
    }
    addYear(g.start_date)
    ;(g.minutes || []).forEach(m => {
      addYear(m.date)
      addYear(m.started_at)
      addYear(m.ended_at)
    })
    ;(g.reports || []).forEach(r => addYear(r.created_at))
    ;(g.tasks || []).forEach(t => addYear(t.created_at))
  })
  return [...years].sort((a, b) => b - a)
})

const yearFilteredMeetings = computed(() => {
  let base = meetings.value
  if (!showEndedMeetings.value) base = base.filter(g => g.status !== 'ended')
  if (!filterYear.value) return base
  const yr = Number(filterYear.value)
  return base.filter(g => {
    const inYear = d => !!d && new Date(d).getFullYear() === yr
    if (inYear(g.start_date) || inYear(g.end_date)) return true
    if ((g.minutes || []).some(m => inYear(m.date) || inYear(m.started_at) || inYear(m.ended_at)))
      return true
    if ((g.reports || []).some(r => inYear(r.created_at))) return true
    if ((g.tasks || []).some(t => inYear(t.created_at) || inYear(t.due_date))) return true
    return false
  })
})

const filteredGroups = computed(() => {
  let list = yearFilteredMeetings.value
  if (search.value) {
    const q = search.value.toLowerCase()
    list = list.filter(
      g =>
        g.title.toLowerCase().includes(q) ||
        g.minutes.some(m => (m.session_title || '').toLowerCase().includes(q)) ||
        g.reports.some(r => (r.file_name || '').toLowerCase().includes(q)) ||
        g.members.some(m => m.userName.toLowerCase().includes(q)),
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

// 목록 표시·정렬용 파생 필드 부여
const enrichedGroups = computed(() =>
  filteredGroups.value.map(g => {
    const adminMember = g.members.find(m => m.role === 'admin')
    const histCount = (g.minutes?.length || 0) + (g.reports?.length || 0)
    return {
      ...g,
      _role:
        (meetingsStore.meetingRoles[toNumericId(g.id)] ?? selfRoleInGroup(g)) === 'admin'
          ? '간사'
          : '참여자',
      _adminName: adminMember?.userName || adminMember?.name || '',
      _histCount: histCount,
    }
  }),
)

// 정렬 (공통 컴포저블)
const {
  sortKey: lvSortKey,
  sortDir: lvSortDir,
  handleSort: handleLvSort,
  sorted: sortedGroups,
} = useTableSort(enrichedGroups)

// ─── 사이드바 로그용: 회의록 + 보고서 + 과제, 최신순 ─────────────
const groupHistoryMap = computed(() => {
  const map = new Map()
  meetings.value.forEach(g => {
    const adminMember = g.members.find(m => m.role === 'admin')
    const managerName = adminMember?.userName || adminMember?.name || '간사'
    const items = []
    g.minutes.forEach(m => {
      items.push({
        type: 'minutes',
        desc: `${m.session_title || '회의'} 진행`,
        manager: managerName,
        date: m.ended_at || m.started_at || m.date,
      })
    })
    g.reports.forEach(r => {
      const isReference = r.human_status === 'approved' && r.score == null
      const statusLabel = isReference
        ? '업로드'
        : r.human_status === 'approved'
          ? '승인'
          : r.human_status === 'rejected'
            ? '반려'
            : '검토 중'
      items.push({
        type: 'report',
        desc: `${r.file_name || '파일'} ${statusLabel}`,
        manager: r.submitter_department || managerName,
        date: r.created_at || r.submitted_at,
      })
    })
    // g.tasks에 있는 아젠다 pg_id 집합 (삭제되어 g.tasks에서 사라진 것들은 별도 재구성)
    const existingPgIds = new Set(
      (g.tasks || []).map(
        t =>
          t.pg_id ??
          (typeof t.id === 'string' && t.id.startsWith('agenda-') ? Number(t.id.slice(7)) : t.id),
      ),
    )
    const meetingDeletedLogs = deletedAgendaLogs.value.filter(
      l => String(l.meetingId) === String(g.id),
    )

    // g.tasks 기반 추가 로그 (현존하는 아젠다)
    const ongoingTasks = (g.tasks || []).filter(t => t.status !== 'draft')
    if (ongoingTasks.length > 0) {
      // created_at 기준 오래된순 정렬 후 2분 간격으로 배치 묶기
      const sorted = [...ongoingTasks].sort((a, b) => {
        const da = a.created_at ? new Date(a.created_at) : new Date(0)
        const db = b.created_at ? new Date(b.created_at) : new Date(0)
        return da - db
      })
      const BATCH_GAP_MS = 2 * 60 * 1000
      const batches = []
      let batch = [sorted[0]]
      for (let i = 1; i < sorted.length; i++) {
        const prev = batch[batch.length - 1]
        const curr = sorted[i]
        const gap =
          (curr.created_at ? new Date(curr.created_at) : new Date(0)) -
          (prev.created_at ? new Date(prev.created_at) : new Date(0))
        if (gap <= BATCH_GAP_MS) {
          batch.push(curr)
        } else {
          batches.push(batch)
          batch = [curr]
        }
      }
      batches.push(batch)
      batches.forEach(batchTasks => {
        const count = batchTasks.length
        const first = batchTasks[0]
        items.push({
          type: 'agenda',
          desc: count === 1 ? '아젠다 1개 추가' : `아젠다 ${count}개 등록`,
          manager: managerName,
          date: first.created_at || first.due_date || null,
          agendas: batchTasks.map(t => t.content || t.title || '(제목 없음)'),
        })
      })
    }
    // 삭제된 아젠다 중 g.tasks에 없는 것: agendaCreatedAt으로 추가 로그 재구성
    const ghostAddLogs = meetingDeletedLogs
      .filter(l => !existingPgIds.has(l.agendaId) && l.agendaCreatedAt)
      .sort((a, b) => new Date(a.agendaCreatedAt) - new Date(b.agendaCreatedAt))
    ghostAddLogs.forEach(l => {
      items.push({
        type: 'agenda',
        desc: '아젠다 1개 추가',
        manager: managerName,
        date: l.agendaCreatedAt,
        agendas: [l.title || '(제목 없음)'],
      })
    })
    const deletedLogs = deletedAgendaLogs.value
      .filter(l => String(l.meetingId) === String(g.id))
      .sort((a, b) => new Date(a.deletedAt) - new Date(b.deletedAt))
    if (deletedLogs.length > 0) {
      const BATCH_GAP_MS = 2 * 60 * 1000
      const delBatches = []
      let delBatch = [deletedLogs[0]]
      for (let i = 1; i < deletedLogs.length; i++) {
        const gap = new Date(deletedLogs[i].deletedAt) - new Date(deletedLogs[i - 1].deletedAt)
        if (gap <= BATCH_GAP_MS) {
          delBatch.push(deletedLogs[i])
        } else {
          delBatches.push(delBatch)
          delBatch = [deletedLogs[i]]
        }
      }
      delBatches.push(delBatch)
      delBatches.forEach(batch => {
        const count = batch.length
        items.push({
          type: 'agenda',
          desc: count === 1 ? '아젠다 1개 삭제' : `아젠다 ${count}개 삭제`,
          manager: managerName,
          date: batch[0].deletedAt,
          agendas: batch.map(l => l.title || '(제목 없음)'),
        })
      })
    }
    items.sort(
      (a, b) =>
        (b.date ? new Date(b.date) : new Date(0)) - (a.date ? new Date(a.date) : new Date(0)),
    )
    map.set(g.id, items)
  })
  return map
})

// ─── 목록 뷰용: 회의록 + 보고서 파일만, 버전 그룹핑, 오래된순 ────
function _toReportFileItem(r, managerName) {
  const baseName = r.file_name || '파일'
  const isReference = r.human_status === 'approved' && r.score == null
  const statusLabel = isReference
    ? '참고자료'
    : r.human_status === 'approved'
      ? '승인'
      : r.human_status === 'rejected'
        ? '반려'
        : '검토 중'
  // isReference는 템플릿 뱃지 분기에도 사용
  return {
    type: 'report',
    desc: `${baseName} ${statusLabel}`,
    manager: r.submitter_department || managerName,
    fileName: baseName + (r.version ? ` (v${r.version})` : ''),
    score: r.score ?? null,
    dept: r.submitter_department || null,
    date: r.created_at || r.submitted_at,
    hasFile: !!(r.file_path || r.file_url),
    filePath: r.file_path || r.file_url || null,
    isReference,
    rejected: r.human_status === 'rejected' || r.status === 'rejected',
    approved: !isReference && (r.human_status === 'approved' || r.status === 'approved'),
    pending: !r.human_status || r.human_status === 'pending',
    reportId: r.id,
    aiFeedback: r.ai_feedback || null,
  }
}
const fileListMap = computed(() => {
  const map = new Map()
  meetings.value.forEach(g => {
    const adminMember = g.members.find(m => m.role === 'admin')
    const managerName = adminMember?.userName || adminMember?.name || '간사'
    const hostDept = adminMember?.department || adminMember?.dept || managerName
    const items = []
    g.minutes
      .filter(m => m.session_status === 'archived')
      .forEach(m => {
        const rawId = String(m.id || '')
        const pgSessionId = rawId.startsWith('session-')
          ? parseInt(rawId.replace('session-', ''))
          : null
        items.push({
          type: 'minutes',
          desc: `${m.session_title || '회의'} 진행`,
          manager: hostDept,
          fileName: m.session_title || '회의록',
          score: null,
          dept: hostDept || null,
          date: m.ended_at,
          hasFile: !!m.minutes_file_name,
          filePath: null,
          sessionId: Number.isFinite(pgSessionId) ? pgSessionId : null,
        })
      })
    const rMap = {}
    g.reports.forEach(r => {
      rMap[r.id] = r
    })
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
    Object.values(rGroups).forEach(group => {
      group.sort((a, b) => (b.version || 1) - (a.version || 1))
      items.push({
        ..._toReportFileItem(group[0], managerName),
        olderVersions: group
          .slice(1)
          .reverse()
          .map(r => _toReportFileItem(r, managerName)),
      })
    })
    items.sort(
      (a, b) =>
        (a.date ? new Date(a.date) : new Date(0)) - (b.date ? new Date(b.date) : new Date(0)),
    )
    map.set(g.id, items)
  })
  return map
})

const filteredFileListMap = computed(() => {
  if (!selectedHistoryType.value) return fileListMap.value
  const map = new Map()
  fileListMap.value.forEach((items, id) => {
    map.set(
      id,
      items.filter(item => item.type === selectedHistoryType.value),
    )
  })
  return map
})

const { buildGraphNodes, computeUrgency, getHubFill } = useGraphBuilder({
  meetings: yearFilteredMeetings,
  currentPerson,
  authStore,
  currentCompany,
  neo4jDepts,
  meetingsStore,
  manualRelations,
})

watch([filterYear, showEndedMeetings], async () => {
  await nextTick()
  const g = buildGraphNodes()
  if (g.nodes.length > 0) {
    gNodes = g.nodes
    gEdges = _applyLocalEdgeOverrides(g.nodes, g.edges)
    gNodesRef.value = gNodes
    _recomputeSearchHits()
    graphViewRef.value?.reloadGraph(gNodes, gEdges)
  }
})

/** GraphView (PIXI) 노드 클릭 핸들러 */
function onGraphNodeClick(node) {
  if (!node) return
  if (node.type === 'Meetings' && node.data) {
    openDetail(node.data)
  } else {
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
  fetchRelSchema() // 관계 스키마 SSOT를 백엔드에서 받아 번들 기본값 갱신 (비차단)
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
      currentCompany.value = data?.company || null
      neo4jMeetings.value = data?.meetings || []
      manualRelations.value = data?.manual_relations || []
      neo4jDepts.value = data?.departments || []
      minutes.value = data?.minutes || []
      reports.value = data?.reports || []
      membersData.value = (data?.meetings || []).flatMap(m => m.members || [])
      tasksData.value = (data?.meetings || []).flatMap(m => m.tasks || [])
    } else {
      console.error('archive fetch error', neo4jResult.reason)
      neo4jError.value = '연결 실패'
    }
  } finally {
    loading.value = false
    if (!neo4jError.value) {
      const g = buildGraphNodes()
      gNodes = g.nodes
      gEdges = _applyLocalEdgeOverrides(g.nodes, g.edges)
      gNodesRef.value = gNodes
    }
  }
})

onBeforeUnmount(() => {
  window.removeEventListener('mousemove', onGlobalMouseMove)
  window.removeEventListener('mouseup', onGlobalMouseUp)
})

// ── archive 데이터 재로드 헬퍼 (CRUD 후 호출) ─────────────────
async function refreshArchive() {
  // 그래프 재빌드 시 노드 인덱스가 바뀌므로 기존 하이라이트 인덱스를 먼저 초기화
  clearTimeout(_queryHlTimer)
  _queryHlTimer = null
  clearTimeout(_hlPersistTimer)
  _hlPersistTimer = null
  queryHlIdxs.value = new Set()
  queryHlEdgeIdxs.value = new Set()
  queryHlStep.value = ''

  neo4jRetrying.value = true
  neo4jError.value = ''
  // 최초 로딩일 때만 loading을 올림 — 이미 그래프가 있으면 백그라운드 갱신(깜빡임 방지)
  const isFirstLoad = gNodes.length === 0
  if (isFirstLoad) loading.value = true
  try {
    const res = await apiAI.get('/api/neo4j/archive')
    neo4jError.value = ''
    currentPerson.value = res?.data?.current_person || null
    currentCompany.value = res?.data?.company || null
    neo4jMeetings.value = res?.data?.meetings || []
    manualRelations.value = res?.data?.manual_relations || []
    neo4jDepts.value = res?.data?.departments || []
    minutes.value = res?.data?.minutes || []
    reports.value = res?.data?.reports || []
    membersData.value = (res?.data?.meetings || []).flatMap(m => m.members || [])
    tasksData.value = (res?.data?.meetings || []).flatMap(m => m.tasks || [])
    await nextTick()
    const g = buildGraphNodes()
    if (g.nodes.length > 0) {
      gNodes = g.nodes
      gEdges = _applyLocalEdgeOverrides(g.nodes, g.edges)
      gNodesRef.value = gNodes
      _recomputeSearchHits()
      graphViewRef.value?.reloadGraph(gNodes, gEdges)
    }
  } catch (e) {
    console.error('archive refresh error', e)
    neo4jError.value = '연결 실패'
  } finally {
    loading.value = false
    neo4jRetrying.value = false
  }
}

// Rebuild graph when new meetings are created
watch(
  () => meetingsStore.meetings.length,
  (newLen, oldLen) => {
    if (loading.value) return // 초기 로딩 중에는 무시 — finally에서 한 번만 빌드

    // 회의체가 삭제된 경우: neo4jMeetings에서도 즉시 제거
    if (newLen < oldLen && neo4jMeetings.value.length > 0) {
      const currentIds = new Set(meetingsStore.meetings.map(m => m.id))
      neo4jMeetings.value = neo4jMeetings.value.filter(mg => {
        const s = String(mg.id)
        const numId = s.startsWith('mg-sqlite-')
          ? parseInt(s.slice(10))
          : s.startsWith('mg-')
            ? parseInt(s.slice(3))
            : parseInt(s)
        return currentIds.has(numId)
      })
    }

    const g = buildGraphNodes()
    if (g.nodes.length === 0 && gNodes.length > 0) return // 빈 데이터로 기존 그래프 지우지 않음
    gNodes = g.nodes
    gEdges = _applyLocalEdgeOverrides(g.nodes, g.edges)
    gNodesRef.value = gNodes
    graphViewRef.value?.reloadGraph(gNodes, gEdges)
  },
)

// Neo4j 데이터 로드 완료 시 그래프 재빌드
watch(
  () => neo4jMeetings.value.length,
  () => {
    if (loading.value) return
    const g = buildGraphNodes()
    if (g.nodes.length === 0 && gNodes.length > 0) return // 빈 데이터로 기존 그래프 지우지 않음
    gNodes = g.nodes
    gEdges = _applyLocalEdgeOverrides(g.nodes, g.edges)
    gNodesRef.value = gNodes
    graphViewRef.value?.reloadGraph(gNodes, gEdges)
  },
)

// ─── Helpers ──────────────────────────────────────────────────
async function _openPresigned(filePath) {
  const { data } = await apiAI.get('/api/upload/presigned', { params: { file_path: filePath } })
  window.open(data.url, '_blank')
}
async function _fetchMinutesFilePath(sessionId) {
  const res = await apiAI.get(`/api/ai/sessions/${sessionId}/minutes`)
  return res?.data?.file_path || null
}
async function downloadFile(item) {
  try {
    let filePath = item?.filePath || null
    if (!filePath && item?.sessionId) filePath = await _fetchMinutesFilePath(item.sessionId)
    if (!filePath) {
      toast.info('다운로드할 파일이 없습니다.')
      return
    }
    await _openPresigned(filePath)
  } catch (e) {
    console.error('[download]', e)
    toast.error('파일 다운로드에 실패했습니다.')
  }
}
async function downloadNode(node) {
  try {
    let filePath = node?.data?.file_path || node?.data?.file_url || null
    if (!filePath) {
      const neoId =
        node?.data?.session_neo_id || (node?.type === 'session' ? node?.data?.id : null) || null
      if (neoId) {
        const rawId = String(neoId)
        const sessionId = rawId.startsWith('session-')
          ? parseInt(rawId.replace('session-', ''))
          : null
        if (Number.isFinite(sessionId)) filePath = await _fetchMinutesFilePath(sessionId)
      }
    }
    if (!filePath) {
      toast.info('다운로드할 파일이 없습니다.')
      return
    }
    await _openPresigned(filePath)
  } catch (e) {
    console.error('[downloadNode]', e)
    toast.error('파일 다운로드에 실패했습니다.')
  }
}
const downloadDummy = downloadNode
async function deleteMinutes(sessionId) {
  if (!(await confirmDialog('회의록을 삭제하시겠습니까?', { danger: true }))) return
  try {
    await apiAI.delete(`/api/ai/sessions/${sessionId}/minutes`)
    setTimeout(refreshArchive, 600)
  } catch {
    toast.error('삭제에 실패했습니다.')
  }
}

async function downloadScript(sessionId) {
  try {
    const { data } = await api.get(`/api/v1/sessions/${sessionId}/scripts`)
    if (!data?.length) {
      toast.info('저장된 스크립트가 없습니다.')
      return
    }
    const rows = data
      .map(s => `<tr><td>${s.speakerLabel || '발화자'}</td><td>${s.content || ''}</td></tr>`)
      .join('')
    const w = window.open('', '_blank')
    if (!w) return
    w.document.write(`<!DOCTYPE html><html><head><meta charset="utf-8"><title>STT 스크립트</title>
      <style>body{font-family:'Malgun Gothic',Arial,sans-serif;font-size:13px;line-height:1.7;color:var(--dark-card);padding:40px;max-width:820px;margin:0 auto}
      h1{font-size:18px;font-weight:800;border-bottom:2px solid #e2e8f0;padding-bottom:10px;margin-bottom:16px}
      table{width:100%;border-collapse:collapse;font-size:12px}
      td{border:1px solid #e2e8f0;padding:6px 10px;vertical-align:top}
      td:first-child{width:100px;font-weight:600;color:var(--text-muted);white-space:nowrap}
      @media print{body{padding:20px}}</style>
      </head><body><h1>STT 스크립트</h1><table>${rows}</table></body></html>`)
    w.document.close()
    setTimeout(() => {
      w.focus()
      w.print()
    }, 400)
  } catch {
    toast.error('스크립트 다운로드에 실패했습니다.')
  }
}

async function deleteReport(reportId) {
  if (!reportId) return
  if (
    !(await confirmDialog('보고서를 삭제하시겠습니까? 이 작업은 되돌릴 수 없습니다.', {
      danger: true,
    }))
  )
    return
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
  } catch {
    toast.error('삭제에 실패했습니다.')
  }
}

async function resumePendingReport(rId, readOnly = false) {
  try {
    const { data } = await apiAI.get(`/api/upload/reports/${rId}/score`)
    aiResult.value = {
      score: data.score,
      detail_scores: data.detail_scores,
      feedback: data.feedback,
      top_improvements: data.top_improvements || [],
      matched_agendas: [],
      agendas: [],
      related_depts: [],
    }
    reportId.value = data.report.id
    uploadedFilePath.value = data.report.file_path
    uploadForm.value.label = data.report.file_name || ''
    uploadForm.value.relatedAgendaIds = data.report.related_agenda_ids || []
    isResultReadOnly.value = readOnly
    uploadStep.value = 2
    showUploadModal.value = true
  } catch {
    toast.error('검토 결과를 불러오지 못했습니다.')
  }
}

// ─── Provide for Canvas components (GraphLegend, GraphFloatBtns, FloatDragPreview) ─
provide('archiveCanvas', {
  loading,
  viewMode,
  detailOpen,
  sidebarW,
  isHiddenType,
  toggleNodeType,
  openCreateModal,
  onFloatBtnMouseDown,
  openSessionModal,
  openUploadModal,
  floatDragging,
  floatDragPos,
  floatDragPreviewLine,
})

// ─── Provide for MeetingListView ──────────────────────────────
provide('archiveList', {
  viewMode,
  selectedMeetingType,
  meetingTypeOptions,
  selectedHistoryType,
  HISTORY_TYPE_OPTIONS,
  search,
  filteredGroups,
  sortedGroups,
  loading,
  meetings,
  nightMode,
  lvColumns,
  lvSortKey,
  lvSortDir,
  handleLvSort,
  expandedMeeting,
  meetingsStore,
  filteredGroupHistoryMap: filteredFileListMap,
  formatDate,
  downloadDummy: downloadFile,
  deleteReport,
  deleteMinutes,
  downloadScript,
  resumePendingReport,
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
      related_agenda_ids: uploadForm.value.relatedAgendaIds || [],
    })
  } catch (e) {
    console.warn('[submitReview] hitl 저장 실패:', e)
  } finally {
    if (action === 'approved') doAddFile()
  }
}

provide('archiveModals', {
  nightMode,
  showCreateModal,
  createForm,
  creating,
  doCreateMeeting,
  createMembers,
  showUploadModal,
  uploadStep,
  uploadForm,
  gNodes: gNodesRef,
  deptConnectableNodes,
  업로드회의체과제,
  prefilledCtx,
  REL_COLORS,
  autoRel,
  runAiAnalysis,
  aiAnalyzing,
  aiResult,
  aiStreamText,
  aiStreamStage,
  PRESENTATION_CRITERIA,
  doAddFile,
  submitReview,
  reportId,
  isResubmit,
  rejectedReports,
  selectedParentId,
  fetchRejectedReports,
  isResultReadOnly,
  settingsModal,
  closeSettings,
  savingSettings,
  saveSettings,
})

// ─── Agenda 편집 모달 ─────────────────────────────────────────
const agendaEditModal = ref(null) // { agendaId, form: { title, department, due_date, priority } }
const savingAgendaEdit = ref(false)

// 검색 가능한 부서명 목록 — Neo4j Department 노드 + 구성원 부서 합집합
const deptOptionNames = computed(() => {
  const names = [
    ...(neo4jDepts.value || []).map(d => d.name),
    ...(membersData.value || []).map(m => m.department || m.dept),
  ].filter(Boolean)
  return [...new Set(names)]
})

function openAgendaEditModal() {
  if (!detailNode.value || detailNode.value.type !== 'agenda') return
  const d = detailNode.value.data || {}
  // 담당부서를 '참여 부서' 배열로 — 검색 다중선택 UI(DeptSelect)와 형식 일치
  const deptArr = Array.isArray(d.department)
    ? d.department.filter(Boolean)
    : d.department
      ? [d.department]
      : d.assignee_dept
        ? [d.assignee_dept]
        : []
  agendaEditModal.value = {
    agendaId: d.id || detailNode.value.neo4jId,
    form: {
      title: d.content || d.title || detailNode.value.label || '',
      department: deptArr,
      due_date: d.due_date ? String(d.due_date).slice(0, 10) : '',
      priority: d.priority || 'medium',
      status: ['pending', 'ongoing', 'done'].includes(d.status) ? d.status : 'pending',
    },
  }
}

function closeAgendaEdit() {
  agendaEditModal.value = null
}

async function deleteAgendaEdit() {
  if (!agendaEditModal.value) return
  const { agendaId } = agendaEditModal.value
  const numId =
    typeof agendaId === 'string' ? parseInt(agendaId.replace('agenda-', ''), 10) : Number(agendaId)
  if (!numId || isNaN(numId)) return
  agendaEditModal.value = null
  if (!(await confirmDialog('이 아젠다를 삭제하시겠습니까?', { danger: true }))) return
  try {
    await apiAI.delete(`/api/agent/archive/agendas/${numId}`)
    detailNode.value = null
    setTimeout(refreshArchive, 600)
  } catch (e) {
    console.error('[deleteAgendaEdit]', e)
  }
}

async function saveAgendaEdit() {
  if (!agendaEditModal.value) return
  const { agendaId, form } = agendaEditModal.value
  const numId =
    typeof agendaId === 'string' ? parseInt(agendaId.replace('agenda-', ''), 10) : Number(agendaId)
  if (!numId || isNaN(numId)) return
  savingAgendaEdit.value = true
  try {
    const { data } = await apiAI.patch(`/api/agent/archive/agendas/${numId}`, {
      title: form.title.trim(),
      department: Array.isArray(form.department)
        ? form.department.filter(Boolean)
        : form.department
          ? [form.department]
          : null,
      due_date: form.due_date || null,
      priority: form.priority || 'medium',
      status: form.status || 'ongoing',
    })
    // detailNode 즉시 업데이트
    if (detailNode.value) {
      detailNode.value = {
        ...detailNode.value,
        label: data.title,
        data: {
          ...detailNode.value.data,
          content: data.title,
          title: data.title,
          department: data.department,
          due_date: data.due_date,
          priority: data.priority,
          status: data.status,
        },
      }
    }
    agendaEditModal.value = null
    setTimeout(refreshArchive, 600)
  } catch (e) {
    console.error('[saveAgendaEdit]', e)
  } finally {
    savingAgendaEdit.value = false
  }
}

// ─── 보고자료 편집 모달 ───────────────────────────────────────────────────────
const reportEditModal = ref(null)
const savingReportEdit = ref(false)

function openReportEditModal() {
  if (!detailNode.value || detailNode.value.type !== 'report') return
  const d = detailNode.value.data || {}
  reportEditModal.value = {
    reportId: d.id,
    form: {
      file_name: d.file_name || detailNode.value.label || '',
      submitter_department: d.submitter_department || d.department || '',
      human_status: ['pending', 'approved', 'rejected'].includes(d.human_status)
        ? d.human_status
        : 'pending',
    },
  }
}

function closeReportEdit() {
  reportEditModal.value = null
}

async function saveReportEdit() {
  if (!reportEditModal.value) return
  const { reportId, form } = reportEditModal.value
  const numId = Number(reportId)
  if (!numId || isNaN(numId)) return
  savingReportEdit.value = true
  try {
    const { data } = await apiAI.patch(`/api/agent/archive/reports/${numId}`, {
      file_name: form.file_name.trim() || null,
      submitter_department: form.submitter_department.trim() || null,
      human_status: form.human_status || 'pending',
    })
    if (detailNode.value) {
      detailNode.value = {
        ...detailNode.value,
        label: data.file_name || detailNode.value.label,
        data: {
          ...detailNode.value.data,
          file_name: data.file_name,
          submitter_department: data.submitter_department,
          human_status: data.human_status,
        },
      }
    }
    reportEditModal.value = null
    setTimeout(refreshArchive, 600)
  } catch (e) {
    console.error('[saveReportEdit]', e)
  } finally {
    savingReportEdit.value = false
  }
}

// ─── 회의록 편집 모달 ─────────────────────────────────────────────────────────
const minutesEditModal = ref(null)
const savingMinutesEdit = ref(false)

function openMinutesEditModal() {
  if (!detailNode.value || detailNode.value.type !== 'minutes') return
  const d = detailNode.value.data || {}
  // session_neo_id 형식: "session-{pg_id}" → pg session id 추출
  const sessionNeoId = d.session_neo_id || ''
  const sessionPgId = parseInt(String(sessionNeoId).replace('session-', ''), 10) || null
  minutesEditModal.value = {
    minutesId: d.minutes_pg_id || null,
    sessionId: sessionPgId,
    form: {
      file_name: d.file_name || d.minutes_file_name || detailNode.value.label || '',
      status: ['DRAFT', 'completed'].includes(d.minutes_status) ? d.minutes_status : 'DRAFT',
    },
  }
}

// 편집 모달의 '삭제' 버튼 배선 — 모달은 delete를 emit하지만 부모(ArchivePage)가 안 받고 있어 무동작이었음
async function deleteMinutesFromModal() {
  const sid = minutesEditModal.value?.sessionId
  closeMinutesEdit()
  if (sid) await deleteMinutes(sid) // 확인 다이얼로그 + Neo4j 노드까지 삭제 + 목록 새로고침
}

function closeMinutesEdit() {
  minutesEditModal.value = null
}

async function saveMinutesEdit() {
  if (!minutesEditModal.value) return
  const { minutesId, sessionId, form } = minutesEditModal.value
  const numId = Number(minutesId)
  const numSessionId = Number(sessionId)
  // minutesId 또는 sessionId 중 하나라도 있어야 저장 가능
  if ((!numId || isNaN(numId)) && (!numSessionId || isNaN(numSessionId))) return
  savingMinutesEdit.value = true
  const endpoint =
    numId && !isNaN(numId)
      ? `/api/agent/archive/minutes/${numId}`
      : `/api/agent/archive/minutes/by-session/${numSessionId}`
  try {
    const { data } = await apiAI.patch(endpoint, {
      file_name: form.file_name.trim() || null,
      status: form.status || 'DRAFT',
    })
    if (detailNode.value) {
      detailNode.value = {
        ...detailNode.value,
        label: data.file_name || detailNode.value.label,
        data: { ...detailNode.value.data, file_name: data.file_name, minutes_status: data.status },
      }
    }
    minutesEditModal.value = null
    setTimeout(refreshArchive, 600)
  } catch (e) {
    console.error('[saveMinutesEdit]', e)
  } finally {
    savingMinutesEdit.value = false
  }
}

// ─── 구성원 정보 수정 모달 (CompanyPage와 동일한 공용 모달 사용) ──────────
// 공용 MemberEditModal에 넘길 통합 구성원 객체:
//   { id(=PostgreSQL user id), name, email, company, department, position, role(조직권한), meetings:[{id, member_id, title}] }
const memberEditModal = ref(null)

async function openMemberEditModal() {
  const node = detailNode.value
  if (!node || node.type !== 'person') return
  const mb = node.data || {}
  const rawUserId = mb.userId ?? node.neo4jId
  const numId = toNumericId(node.meetingId)

  // 1) 노드 데이터 기반 1차 표시값 (멤버십/조직권한 조회 실패 시 폴백)
  memberEditModal.value = {
    id: toNumericId(rawUserId) || null,
    name: mb.userName || mb.name || '?',
    email: mb.email || '',
    company: mb.company || currentCompany.value?.name || '',
    department: mb.department || mb.dept || '',
    position: mb.position || '',
    role: 'USER',
    meetings: [],
  }

  // 2) 회의체 멤버 목록에서 멤버십(member_id)·PostgreSQL user id·프로필을 best-effort 매칭
  let pgUserId = memberEditModal.value.id
  if (numId) {
    try {
      const res = await api.get(`/api/v1/meetings/${numId}/members`)
      const list = Array.isArray(res.data) ? res.data : res.data?.data || []
      const uidNum = toNumericId(rawUserId)
      const memUid = m => toNumericId(m.user?.id ?? m.user_id ?? m.userId)
      const found =
        (uidNum ? list.find(m => memUid(m) === uidNum) : null) ||
        list.find(m => (m.user?.name || m.userName || m.name) === memberEditModal.value?.name)
      if (found && memberEditModal.value) {
        pgUserId = toNumericId(found.user?.id ?? found.user_id) || pgUserId
        memberEditModal.value = {
          ...memberEditModal.value,
          id: pgUserId,
          name: found.user?.name || memberEditModal.value.name,
          email: found.user?.email || memberEditModal.value.email,
          company: found.user?.company || memberEditModal.value.company,
          department: found.user?.department || memberEditModal.value.department,
          position: found.user?.position || memberEditModal.value.position,
          meetings: [
            {
              id: numId,
              member_id: found.id,
              title: detailMeeting.value?.title || node.label || '',
            },
          ],
        }
      }
    } catch {
      /* 멤버 조회 실패해도 모달은 유지 — 노드 데이터로 표시 */
    }
  }

  // 3) 조직 권한(company role)은 회의체 멤버 응답에 없으므로 by-ids로 별도 조회
  if (pgUserId && memberEditModal.value) {
    try {
      const r = await api.get(`/api/v1/users/by-ids?ids=${pgUserId}`)
      const u = (r.data?.data || r.data || [])[0]
      if (u && memberEditModal.value) {
        memberEditModal.value = {
          ...memberEditModal.value,
          role: u.role || memberEditModal.value.role,
          company: u.company || memberEditModal.value.company,
          department: u.department ?? memberEditModal.value.department,
          position: u.position ?? memberEditModal.value.position,
        }
      }
    } catch {
      /* 조직 권한 조회 실패 시 기본값(USER) 유지 */
    }
  }
}

function closeMemberEdit() {
  memberEditModal.value = null
}

// 저장 성공: 상세 노드를 새 권한으로 즉시 반영하고 그래프를 갱신
function onMemberSaved() {
  const newRole = memberEditModal.value?.role
  if (detailNode.value?.type === 'person' && newRole) {
    detailNode.value = {
      ...detailNode.value,
      data: { ...detailNode.value.data, role: newRole },
    }
  }
  memberEditModal.value = null
  setTimeout(refreshArchive, 600)
}

// 제거 성공: 상세 패널을 닫고 그래프를 갱신
function onMemberDeleted() {
  memberEditModal.value = null
  detailOpen.value = false
  setTimeout(refreshArchive, 600)
}

const showSessionEdit = ref(false)
const sessionEditData = ref(null)

function openSessionEditModal() {
  if (!detailNode.value || detailNode.value.type !== 'session') return
  const d = detailNode.value.data || {}
  sessionEditData.value = {
    id: detailNode.value.neo4jId,
    meetingId: null,
    title: d.session_title || detailNode.value.label || '',
    location: d.location || '',
    scheduled_at: d.date || d.started_at || '',
    type: d.session_type || 'localwhisper',
    members: (d.participants || []).map(p => ({
      userId: p.userId,
      name: p.userName || p.name || '',
      email: p.email || p.department || '',
      role: p.role || 'member',
    })),
  }
  showSessionEdit.value = true
}

function onSessionEditSaved() {
  setTimeout(refreshArchive, 600)
}

/** 회사 노드 설정: 회사명 변경 (SYSTEM_ADMIN / 해당 회사 COMPANY_ADMIN) */
const companyRenameModal = ref(null) // { oldName, form: { name } }
const savingCompanyRename = ref(false)

function renameCompanyNode() {
  const oldName = detailNode.value?.label || detailNode.value?.data?.name
  if (!oldName) return
  companyRenameModal.value = { oldName, form: { name: oldName } }
}
function closeCompanyRename() {
  companyRenameModal.value = null
}

async function saveCompanyRename() {
  if (!companyRenameModal.value) return
  const { oldName, form } = companyRenameModal.value
  const newName = (form.name || '').trim()
  if (!newName || newName === oldName) {
    companyRenameModal.value = null
    return
  }
  savingCompanyRename.value = true
  try {
    await apiAI.patch('/api/ai/companies/rename', { old_name: oldName, new_name: newName })
    toast.success('회사명을 변경했습니다.')
    companyRenameModal.value = null
    detailOpen.value = false
    setTimeout(refreshArchive, 400)
  } catch (e) {
    toast.error(e.response?.data?.detail || '회사명 변경에 실패했습니다.')
  } finally {
    savingCompanyRename.value = false
  }
}

// ─── 부서명 변경 (dept 노드 설정) ──────────────────────────────
// 부서는 users.department 문자열로만 식별 → 회사 scope 안에서 일괄 변경.
const deptRenameModal = ref(null) // { oldName, companyName, form: { name } }
const savingDeptRename = ref(false)

function renameDeptNode() {
  const oldName = detailNode.value?.label
  if (!oldName) return
  // 부서가 속한 회사: 부서 구성원의 회사명 (백엔드 scope·권한 검증용)
  const companyName =
    (detailNode.value?.members || []).map(mb => mb.company || mb.user?.company).find(Boolean) ||
    currentCompany.value?.name ||
    ''
  deptRenameModal.value = { oldName, companyName, form: { name: oldName } }
}
function closeDeptRename() {
  deptRenameModal.value = null
}

async function saveDeptRename() {
  if (!deptRenameModal.value) return
  const { oldName, companyName, form } = deptRenameModal.value
  const newName = (form.name || '').trim()
  if (!newName || newName === oldName) {
    deptRenameModal.value = null
    return
  }
  savingDeptRename.value = true
  try {
    await apiAI.patch('/api/ai/departments/rename', {
      old_name: oldName,
      new_name: newName,
      company_name: companyName || null,
    })
    toast.success('부서명을 변경했습니다.')
    deptRenameModal.value = null
    detailOpen.value = false
    setTimeout(refreshArchive, 400)
  } catch (e) {
    toast.error(e.response?.data?.detail || '부서명 변경에 실패했습니다.')
  } finally {
    savingDeptRename.value = false
  }
}

/** 비-Meetings 노드(dept/agenda/세션 등) 헤더의 설정 버튼: 아젠다면 아젠다 편집 모달, 아니면 부모 회의체 설정 모달 */
async function openNodeGroupSetting() {
  if (!detailNode.value) return
  if (detailNode.value.type === 'agenda') {
    openAgendaEditModal()
    return
  }
  if (detailNode.value.type === 'report') {
    openReportEditModal()
    return
  }
  if (detailNode.value.type === 'minutes') {
    openMinutesEditModal()
    return
  }
  if (detailNode.value.type === 'session') {
    openSessionEditModal()
    return
  }
  if (detailNode.value.type === 'company') {
    await renameCompanyNode()
    return
  }
  if (detailNode.value.type === 'dept') {
    renameDeptNode()
    return
  }
  if (detailNode.value.type === 'person') {
    await openMemberEditModal()
    return
  }
  const mgId = detailNode.value.meetingId || detailNode.value.neo4jId
  if (!mgId) return
  const mg = neo4jMeetings.value.find(m => m.id === mgId)
  if (!mg) return
  // detailMeeting을 일시적으로 설정하고 설정 모달 오픈
  detailMeeting.value = mg
  await openGroupSetting()
}

// ─── Provide for DetailSidebar ────────────────────────────────
provide('archiveSidebar', {
  detailOpen,
  sidebarW,
  onSidebarResizeStart,
  detailMeeting,
  isDetailAdmin,
  isAnyAdmin,
  canEditCompany,
  canEditDept,
  openGroupSetting,
  openNodeGroupSetting,
  detailTab,
  showExtractFlow,
  nodeDetailTab,
  detailDday,
  detailEndDateFormatted,
  detailDeptStatus,
  groupHistoryMap,
  goToList,
  formatDate,
  formatDateOnly,
  detailAgendas,
  groupedAgendas,
  doneAgendasWithReport,
  completeAgenda,
  deleteAgenda,
  extractPhase,
  extractLoading,
  extractResult,
  selectedFiles,
  uploadedCtxFiles,
  selectedSimilarDocs,
  onCtxFilesAdded,
  removeCtxFile,
  runExtract,
  setExtractState,
  addExtractItem,
  finishExtract,
  addDirectAgenda,
  approveItem,
  rejectItem,
  detailMemberDepts,
  detailMemberCompanies,
  goToProcessStep,
  PRIORITY_LABEL,
  STATUS_LABEL,
  NODE_TYPE_COLORS,
  currentNodeEdges,
  REL_COLORS,
  doDeleteEdge,
  relAddActive,
  openAddRel,
  allGraphNodeList,
  relAddForm,
  doAddRel,
  detailNode,
  downloadDummy,
  downloadFile,
  deleteReport,
  currentCompany,
  personMeetings,
  personTasks,
  reportRelatedAgendas,
  meetings,
  viewMode,
  nodeReviewing,
  startNodeReview,
  agendaEditModal,
  closeAgendaEdit,
  savingAgendaEdit,
  saveAgendaEdit,
  reportEditModal,
  closeReportEdit,
  savingReportEdit,
  saveReportEdit,
  minutesEditModal,
  closeMinutesEdit,
  savingMinutesEdit,
  saveMinutesEdit,
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
        <svg
          class="search-icon"
          width="14"
          height="14"
          fill="none"
          stroke="currentColor"
          stroke-width="2"
          viewBox="0 0 24 24"
        >
          <circle cx="11" cy="11" r="8" />
          <path d="M21 21l-4.35-4.35" />
        </svg>
        <input
          v-model="search"
          class="search-input"
          placeholder="회의체명, 회의록, 보고서, 인물 검색..."
        />
        <button v-if="search" class="search-clear" @click="search = ''">
          <svg
            width="11"
            height="11"
            fill="none"
            stroke="currentColor"
            stroke-width="2.5"
            viewBox="0 0 24 24"
          >
            <path d="M18 6L6 18M6 6l12 12" />
          </svg>
        </button>
      </div>
      <div class="year-filter-wrap">
        <select v-model="filterYear" class="year-filter-select">
          <option value="">전체 연도</option>
          <option v-for="y in availableYears" :key="y" :value="y">{{ y }}년</option>
        </select>
        <label class="ended-filter-check">
          <input type="checkbox" v-model="showEndedMeetings" />
          종료된 회의체
        </label>
      </div>

      <div class="app-tabs">
        <button
          class="app-tab"
          :class="{ active: viewMode === 'graph' }"
          @click="viewMode = 'graph'"
        >
          <svg
            width="13"
            height="13"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
            viewBox="0 0 24 24"
          >
            <circle cx="5" cy="12" r="2" />
            <circle cx="19" cy="5" r="2" />
            <circle cx="19" cy="19" r="2" />
            <path d="M7 12h5l5-5M12 12l5 5" />
          </svg>
          관계도
        </button>
        <button class="app-tab" :class="{ active: viewMode === 'list' }" @click="viewMode = 'list'">
          <svg
            width="13"
            height="13"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
            viewBox="0 0 24 24"
          >
            <path d="M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01" />
          </svg>
          목록
        </button>
      </div>

      <button
        class="agent-header-btn refresh-map-btn"
        :class="{ analyzing: analyzingRelations }"
        :disabled="analyzingRelations"
        @click="analyzeRelationships"
        title="관계도 새로고침 — AI가 소속 관계를 분석·재설정하고 근거를 알려드립니다"
      >
        <svg
          class="refresh-icon"
          viewBox="0 0 24 24"
          fill="none"
          xmlns="http://www.w3.org/2000/svg"
          width="18"
          height="18"
        >
          <defs>
            <linearGradient id="refreshGrad" x1="0%" y1="0%" x2="100%" y2="100%">
              <stop offset="0%" stop-color="#93c5fd" />
              <stop offset="100%" stop-color="#818cf8" />
            </linearGradient>
          </defs>
          <path
            d="M7.5 5.6L10 7L8.6 4.5L10 2L7.5 3.4L5 2l1.4 2.5L5 7zm12 9.8L17 14l1.4 2.5L17 19l2.5-1.4L22 19l-1.4-2.5L22 14zM22 2l-2.5 1.4L17 2l1.4 2.5L17 7l2.5-1.4L22 7l-1.4-2.5zm-7.63 5.29a.996.996 0 0 0-1.41 0L1.29 18.96a.996.996 0 0 0 0 1.41l2.34 2.34c.39.39 1.02.39 1.41 0L16.7 11.05a.996.996 0 0 0 0-1.41zm-1.03 5.49l-2.12-2.12l2.44-2.44l2.12 2.12z"
            stroke="url(#refreshGrad)"
            stroke-width="1"
            stroke-linecap="round"
          />
          <polyline
            points="18.5,4.43 18.5,7.43 15.5,7.43"
            stroke="url(#refreshGrad)"
            stroke-width="2"
            stroke-linecap="round"
            stroke-linejoin="round"
          />
          <polyline
            points="5.5,19.57 5.5,16.57 8.5,16.57"
            stroke="url(#refreshGrad)"
            stroke-width="2"
            stroke-linecap="round"
            stroke-linejoin="round"
          />
        </svg>
      </button>
      <button
        class="agent-header-btn"
        :class="{ active: agentSidebarOpen }"
        @click="agentSidebarOpen = !agentSidebarOpen"
        title="AI 에이전트"
      >
        <svg class="ai-btn-icon" viewBox="0 0 40 22" xmlns="http://www.w3.org/2000/svg">
          <defs>
            <linearGradient id="aiGrad" x1="0%" y1="0%" x2="100%" y2="100%">
              <stop offset="0%" stop-color="#93c5fd" />
              <stop offset="100%" stop-color="#7b80cc" />
            </linearGradient>
          </defs>
          <text
            x="20"
            y="17"
            text-anchor="middle"
            font-family="'SF Pro Display',system-ui,sans-serif"
            font-weight="800"
            font-size="19"
            fill="url(#aiGrad)"
            letter-spacing="-0.5"
          >
            AI
          </text>
        </svg>
      </button>
    </div>

    <!-- ── Graph Breadcrumb ── -->
    <!-- ── Body ── -->
    <div class="archive-body">
      <!-- Main area -->
      <div class="main-area">
        <DetailSidebar />

        <!-- Graph view: 최초 로딩 스피너 -->
        <div v-if="loading && viewMode === 'graph'" class="graph-loading">
          <div class="graph-loading-spinner"></div>
          <span>불러오는 중...</span>
        </div>
        <!-- 리프레시 중 오버레이 (그래프 유지한 채 상단에 표시) -->
        <Transition name="graph-refresh-fade">
          <div
            v-if="neo4jRetrying && !loading && viewMode === 'graph'"
            class="graph-refresh-overlay"
          >
            <div
              class="graph-loading-spinner"
              style="width: 16px; height: 16px; border-width: 2px"
            ></div>
            <span>갱신 중...</span>
          </div>
        </Transition>

        <!-- Zoom controls (top-left) -->
        <div
          v-if="(!loading || neo4jRetrying) && viewMode === 'graph'"
          class="graph-zoom-controls"
          :style="{
            left: (detailOpen ? sidebarW + 10 : 10) + 'px',
            transition: 'left 0.28s cubic-bezier(.22,.68,0,1.2)',
          }"
        >
          <template v-if="viewMode === 'graph'">
            <button class="zoom-btn" @click="graphViewRef?.zoomIn()" title="확대 (Zoom In)">
              +
            </button>
            <button
              class="zoom-btn zoom-reset"
              @click="graphViewRef?.resetView()"
              title="초기화 (Reset)"
            >
              ⌂
            </button>
            <button class="zoom-btn" @click="graphViewRef?.zoomOut()" title="축소 (Zoom Out)">
              −
            </button>
            <button
              class="zoom-btn zoom-pan-hint"
              :class="{ active: graphPanOnly }"
              @click="toggleGraphPanOnly"
              title="이동 전용 모드 (노드 클릭 없이 배경 드래그로만 이동)"
            >
              <i class="bi bi-arrows-move"></i>
            </button>
          </template>
          <template v-else>
            <button class="zoom-btn" @click="constViewRef?.zoomIn()" title="확대 (Zoom In)">
              +
            </button>
            <button
              class="zoom-btn zoom-reset"
              @click="constViewRef?.resetView()"
              title="초기화 (Reset)"
            >
              ⌂
            </button>
            <button class="zoom-btn" @click="constViewRef?.zoomOut()" title="축소 (Zoom Out)">
              −
            </button>
          </template>
        </div>
        <!-- Graph view (PIXI.js force-directed) -->
        <div v-if="!loading && viewMode === 'graph' && neo4jError" class="neo4j-error-overlay">
          <svg
            width="36"
            height="36"
            fill="none"
            stroke="currentColor"
            stroke-width="1.5"
            viewBox="0 0 24 24"
            style="color: #f87171; margin-bottom: 10px"
          >
            <circle cx="12" cy="12" r="10" />
            <path d="M12 8v4M12 16h.01" />
          </svg>
          <div class="neo4j-error-title">그래프 연결 실패</div>
          <div class="neo4j-error-msg">{{ neo4jError }}</div>
          <button class="neo4j-error-retry" :disabled="neo4jRetrying" @click="refreshArchive">
            <span
              v-if="neo4jRetrying"
              class="spinner-border spinner-border-sm me-1"
              style="width: 12px; height: 12px; border-width: 2px"
            ></span>
            {{ neo4jRetrying ? '연결 중...' : '다시 시도' }}
          </button>
        </div>
        <GraphView
          v-if="viewMode === 'graph' && !neo4jError && (!loading || neo4jRetrying)"
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
          :groupAgendaRatio="groupAgendaRatio"
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
      </div>
      <!-- /main-area -->
    </div>
    <!-- /archive-body -->

    <!-- Agent right sidebar (overlay, covers header) -->
    <AgentSidebar />

    <FloatDragPreview />

    <CreateMeetingModal />
    <CreateSessionModal
      :show="showSessionModal"
      :meetings="meetings"
      :lockedUserId="authStore.user?.id"
      :initialMeetingId="sessionCreateInitialId"
      @close="showSessionModal = false"
      @saved="onSessionCreated"
    />
  </div>
  <!-- /archive-page -->
  <UploadModal />
  <SettingsModal />
  <AgendaEditModal
    :modal="agendaEditModal"
    :night-mode="nightMode"
    :saving="savingAgendaEdit"
    :dept-options="deptOptionNames"
    @close="closeAgendaEdit"
    @save="saveAgendaEdit"
    @delete="deleteAgendaEdit"
  />
  <ReportEditModal
    :modal="reportEditModal"
    :night-mode="nightMode"
    :saving="savingReportEdit"
    @close="closeReportEdit"
    @save="saveReportEdit"
  />
  <MinutesEditModal
    :modal="minutesEditModal"
    :night-mode="nightMode"
    :saving="savingMinutesEdit"
    @close="closeMinutesEdit"
    @save="saveMinutesEdit"
    @delete="deleteMinutesFromModal"
  />
  <MemberEditModal
    :member="memberEditModal"
    :night-mode="nightMode"
    @close="closeMemberEdit"
    @saved="onMemberSaved"
    @deleted="onMemberDeleted"
  />
  <RenameModal
    :modal="companyRenameModal"
    :night-mode="nightMode"
    :saving="savingCompanyRename"
    title="회사명 변경"
    field-label="회사명"
    placeholder="새 회사명을 입력하세요"
    @close="closeCompanyRename"
    @save="saveCompanyRename"
  />
  <RenameModal
    :modal="deptRenameModal"
    :night-mode="nightMode"
    :saving="savingDeptRename"
    title="부서명 변경"
    field-label="부서명"
    placeholder="새 부서명을 입력하세요"
    @close="closeDeptRename"
    @save="saveDeptRename"
  />
  <SessionEditModal
    :show="showSessionEdit"
    :session="sessionEditData"
    @close="showSessionEdit = false"
    @saved="onSessionEditSaved"
  />
</template>

<style>
@import '../styles/archive/layout.css';
@import '../styles/archive/sidebar.css';
@import '../styles/archive/agent.css';
@import '../styles/archive/graph.css';
@import '../styles/archive/list.css';
@import '../styles/archive/modals.css';
</style>
