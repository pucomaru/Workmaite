<script setup>
import { ref, computed, onMounted, onBeforeUnmount, watch, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import api from '../api'
import { streamPost } from '../api'
import { renderMd } from '../composables/useMarkdown'
import { useMeetingsStore } from '../stores/meetings'
import { useAuthStore } from '../stores/auth'
import { useThemeStore } from '../stores/theme'
import hyeanAvatar from '../assets/agents/hyean.png'
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
const loading = ref(true)
const search = ref('')
const expandedMeeting = ref(null)

// ─── View mode ────────────────────────────────────────────────
const viewMode = ref('graph')
// nightMode는 전역 themeStore.nightMode(computed)를 사용합니다

// ─── Plus snackbar (removed - replaced by direct button) ──────

// ─── Create meeting modal ─────────────────────────────────────
const showCreateModal = ref(false)
const createForm = ref({ title: '', purpose: '', start_date: '', end_date: '' })
const relatedMeetingIds = ref([])
const memberSearch = ref('')
const memberSearchResults = ref([])
const selectedMembers = ref([])
const creating = ref(false)

async function searchMembersFn() {
  if (!memberSearch.value.trim()) { memberSearchResults.value = []; return }
  try {
    const { data } = await api.get(`/api/users/search?q=${memberSearch.value}`)
    memberSearchResults.value = data.filter(u =>
      u.id !== authStore.user?.id && !selectedMembers.value.find(m => m.id === u.id))
  } catch {}
}
function addMember(u) { selectedMembers.value.push({ ...u, role: 'presenter' }); memberSearchResults.value = []; memberSearch.value = '' }
function removeMember(u) { selectedMembers.value = selectedMembers.value.filter(m => m.id !== u.id) }
function toggleRelated(id) {
  const idx = relatedMeetingIds.value.indexOf(id)
  idx >= 0 ? relatedMeetingIds.value.splice(idx, 1) : relatedMeetingIds.value.push(id)
}

function openCreateModal() { showCreateModal.value = true; agentSidebarOpen.value = false }

function onFloatBtnMouseDown(type, e) {
  floatDragging.value = type
  floatDragPos.value = { x: e.clientX, y: e.clientY }
  floatDragStartX = e.clientX; floatDragStartY = e.clientY
  floatDragMoved = false; floatDragTarget = null; floatDragPreviewLine.value = null
  document.body.style.cursor = 'grabbing'
  e.preventDefault(); e.stopPropagation()
}

async function doCreateMeeting() {
  if (!createForm.value.title.trim()) return
  creating.value = true
  try {
    const meeting = await meetingsStore.createMeeting({
      title: createForm.value.title, purpose: createForm.value.purpose,
      start_date: createForm.value.start_date || null, end_date: createForm.value.end_date || null,
    })
    for (const m of selectedMembers.value) {
      await api.post(`/api/meetings/${meeting.id}/members`, { user_id: m.id, role: m.role })
    }
    showCreateModal.value = false
    createForm.value = { title: '', purpose: '', start_date: '', end_date: '' }
    selectedMembers.value = []; relatedMeetingIds.value = []
    // rebuild graph with new meeting
    await nextTick()
    const g = buildGraphNodes(); gNodes = g.nodes; gEdges = g.edges
    // 사용자가 지정한 연결 엣지 추가
    if (createConnectNodeId.value) {
      const mgNode = gNodes.find(n => n.id === `mg-${meeting.id}`)
      const fromNode = gNodes.find(n => n.id === createConnectNodeId.value)
      if (mgNode && fromNode) gEdges.push({ from:gNodes.indexOf(fromNode), to:gNodes.indexOf(mgNode), rel:createRelType.value })
      createConnectNodeId.value = ''; createRelType.value = '관련'
    }
  } finally { creating.value = false }
}

// ─── Agents ───────────────────────────────────────────────────
// 내부적으로는 5개 서브에이전트가 존재하지만 사용자에게는 단일 워크메이트 AI로 표시됨
const SUPERVISOR = {
  name: '워크메이트 AI', nameEn: 'Workmate AI', subtitle: '회의체 통합 AI 어시스턴트',
  avatar: hyeanAvatar,
  greeting: '안녕하세요! 저는 워크메이트 AI예요 😊\n회의체 현황 분석, 아젠다·과제 추출, 자료 검토, 카드뉴스 생성까지\n무엇이든 말씀해 주세요.',
  suggested: ['회의체 현황을 브리핑해줘', '이번 회의 아젠다를 정리해줘', '보고서를 검토해줘'],
  endpoint: '/api/agent/supervisor/chat',
}

const agentSidebarOpen = ref(false)
const currentAgent = ref('supervisor')
const agentInfo = computed(() => SUPERVISOR)
const allMessages = ref({ supervisor: [] })
const currentMessages = computed(() => allMessages.value['supervisor'])
const agentInput = ref('')
const agentLoading = ref(false)
const agentMessagesEl = ref(null)
const agentFileInput = ref(null)
const agentPendingFiles = ref([])
const agentTextareaEl = ref(null)

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
  if ((!text && !agentPendingFiles.value.length) || agentLoading.value) return
  agentInput.value = ''
  if (agentTextareaEl.value) agentTextareaEl.value.style.height = '36px'
  let content = text
  if (agentPendingFiles.value.length) {
    const names = agentPendingFiles.value.map(f => f.name).join(', ')
    content = text ? `📎 ${names}\n${text}` : `📎 ${names}`
    agentPendingFiles.value = []
  }
  const key = 'supervisor'
  allMessages.value[key].push({ role: 'user', content })
  const agentMsg = { role: 'agent', content: '' }
  allMessages.value[key].push(agentMsg)
  agentLoading.value = true
  await nextTick()
  if (agentMessagesEl.value) agentMessagesEl.value.scrollTop = agentMessagesEl.value.scrollHeight
  const history = allMessages.value[key].slice(0, -1).map(m => ({
    role: m.role === 'user' ? 'user' : 'assistant', content: m.content,
  }))
  try {
    await streamPost(
      agentInfo.value.endpoint,
      { meeting_id: 0, message: content, chat_history: history },
      (chunk) => { agentMsg.content += chunk; if (agentMessagesEl.value) agentMessagesEl.value.scrollTop = agentMessagesEl.value.scrollHeight },
      () => { agentLoading.value = false }
    )
  } catch { agentMsg.content = '응답 중 오류가 발생했습니다.'; agentLoading.value = false }
}

function onAgentKeydown(e) { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendAgentMsg() } }
function onAgentFileSelected(e) { agentPendingFiles.value.push(...Array.from(e.target.files || [])); e.target.value = '' }
function agentAutoResize() {
  const el = agentTextareaEl.value; if (!el) return
  el.style.height = '36px'; el.style.height = Math.min(el.scrollHeight, 100) + 'px'
}

// ─── Bottom panel ─────────────────────────────────────────────
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
        let closest = null, minDist = Infinity
        gNodes.forEach((n, i) => {
          if (n.type !== 'hub') return
          const p = projectNode(n, w, h)
          const zf = Math.max(.6, Math.min(2.5, worldZoom))
          const d = Math.hypot(p.sx - mx, p.sy - my)
          if (d < 22 * p.scale * zf + 70 && d < minDist) { minDist = d; closest = { idx: i, node: n, proj: p } }
        })
        floatDragTarget = closest
        if (closest) {
          floatDragPreviewLine.value = { x1: closest.proj.sx, y1: closest.proj.sy, x2: mx, y2: my }
          if (floatDragging.value === 'doc') {
            expandedHubIdx = closest.idx; expandedDeptIdx = null
            const n = closest.node
            targetCamX = n.x * .55; targetCamY = n.y * .55; targetCamZ = n.z * .55
            targetZoom = Math.min(3.0, Math.max(targetZoom, 1.6))
          }
        } else { floatDragPreviewLine.value = null }
      } else { floatDragTarget = null; floatDragPreviewLine.value = null }
    }
  }
}
function onGlobalMouseUp() {
  sidebarResizing = false; bottomResizing = false
  if (floatDragging.value) {
    const type = floatDragging.value
    const target = floatDragTarget
    floatDragging.value = null; floatDragTarget = null; floatDragPreviewLine.value = null
    document.body.style.cursor = ''
    if (!floatDragMoved || !target) {
      // Click or missed drop → open normally
      if (type === 'meeting') openCreateModal()
      else if (type === 'doc') activateReviewMode()
    } else {
      // Dropped onto a hub node
      if (type === 'meeting') {
        relatedMeetingIds.value = [target.node.data.id]
        selectedNodeIdx.value = target.idx; expandedHubIdx = target.idx; expandedDeptIdx = null
        openCreateModal()
      } else if (type === 'doc') {
        activateReviewMode()
      }
    }
  }
}

// ─── Hover tooltip ────────────────────────────────────────────
const hoverNode = ref(null)
const tooltipPos = ref({ x: 0, y: 0 })
const tooltipHover = ref(false)
const tooltipVisible = computed(() => (hoverNode.value !== null || tooltipHover.value) && viewMode.value === 'graph')
let tooltipHideTimer = null

function showTooltipAt(node, x, y) {
  clearTimeout(tooltipHideTimer); hoverNode.value = node; tooltipPos.value = { x, y }
}
function scheduleHideTooltip() {
  tooltipHideTimer = setTimeout(() => { if (!tooltipHover.value) hoverNode.value = null }, 180)
}
function onTooltipEnter() { clearTimeout(tooltipHideTimer); tooltipHover.value = true }
function onTooltipLeave() { tooltipHover.value = false; scheduleHideTooltip() }

// ─── Detail sidebar ───────────────────────────────────────────
const detailMeeting = ref(null)
const detailOpen = ref(false)

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
    const res = await api.get(`/api/meetings/${m.id}/members`)
    members = res.data.map(mb => ({
      id: mb.id,
      userId: mb.user?.id || mb.user_id,
      name: mb.user?.name || mb.userName || mb.name || '?',
      email: mb.user?.email || mb.email || '',
      role: mb.role || 'member',
    }))
  } catch { members = (m.members || []).map(mb => ({ id: null, userId: mb.userId, name: mb.userName || '?', email: '', role: 'member' })) }
  settingsModal.value = {
    meeting: m,
    form: { title: m.title || '', purpose: m.purpose || m.description || '' },
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
      const res = await api.get('/api/users/search', { params: { q } })
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
    await api.patch(`/api/meetings/${meeting.id}`, { title: form.title, purpose: form.purpose })
    for (const memberId of removedIds) {
      await api.delete(`/api/meetings/${meeting.id}/members/${memberId}`)
    }
    for (const mb of members.filter(m => m.id === null)) {
      await api.post(`/api/meetings/${meeting.id}/members`, { user_id: mb.userId, role: mb.role })
    }
    if (detailMeeting.value?.id === meeting.id) {
      detailMeeting.value.title = form.title
    }
    await meetingsStore.fetchMeetings()
    settingsModal.value = null
  } catch (e) { alert(e.response?.data?.detail || '저장 실패') }
  finally { savingSettings.value = false }
}

const ROLE_MAP = { secretary: '간사', member: '참여자' }
function roleLabel(r) { return ROLE_MAP[r] || r || '참여자' }
const AVATAR_COLORS = ['#6366f1','#3b82f6','#10b981','#f59e0b','#ef4444','#8b5cf6','#ec4899']
function avatarColor(name) { let h=0; for(const c of (name||'')) h=(h*31+c.charCodeAt(0))%AVATAR_COLORS.length; return AVATAR_COLORS[h] }
function initials(name) { return (name || '?')[0] }

function openDetail(groupData) {
  if (!groupData) return
  detailMeeting.value = groupData; detailOpen.value = true
  hoverNode.value = null; tooltipHover.value = false
}

// ─── 3D Graph ─────────────────────────────────────────────────
const canvasRef = ref(null)
const mainAreaRef = ref(null)
let ctx = null, animId = null, ro = null
let rotX = 0.2, rotY = 0
let isDragging = false, lastMx = 0, lastMy = 0
let autoRotate = false, focusNode = null
const selectedNodeIdx = ref(null)
const breadcrumb = ref([])
let targetCamX = 0, targetCamY = 0, targetCamZ = 0
let camX = 0, camY = 0, camZ = 0
let worldZoom = 1.0, targetZoom = 1.0, dpr = 1
let gNodes = [], gEdges = []
let expandedHubIdx = null
let expandedDeptIdx = null
let rotationPaused = false
// Float button drag state
const floatDragging = ref(null)       // null | 'meeting' | 'doc'
const floatDragPos = ref({ x: 0, y: 0 })
const floatDragPreviewLine = ref(null) // { x1,y1,x2,y2 } in canvas px
let floatDragTarget = null
let floatDragStartX = 0, floatDragStartY = 0, floatDragMoved = false

// ─── Upload modal ──────────────────────────────────────────────
const showUploadModal = ref(false)
const uploadForm = ref({ label: '', fileType: '회의록', connectNodeId: '', relType: '생성' })

// ─── Ontology edge relation constants ─────────────────────────
const REL_COLORS = { '소속':'#94a3b8','참여부서':'#3b82f6','개최':'#10b981','생성':'#f59e0b','담당':'#f97316','관련':'#a78bfa' }
const REL_OPTIONS_FOR = { org:['소속'], dept:['소속','참여부서','담당'], meeting_group:['개최','참여부서','관련'], session:['생성','관련'] }
const FILE_TYPES = ['회의록','발제자료','보고자료']

function hexToRgba(hex, a) {
  const r=parseInt(hex.slice(1,3),16),g=parseInt(hex.slice(3,5),16),b=parseInt(hex.slice(5,7),16)
  return `rgba(${r},${g},${b},${a})`
}

const connectableNodes = computed(() => {
  const groups = meetingGroups.value.length ? meetingGroups.value : getDemoData()
  const result = [{ id:'org-root', label:'조직', typeLabel:'조직', type:'org' }]
  const depts = new Set()
  groups.forEach(g => (g.members||[]).forEach(mb => depts.add(mb.department||mb.dept||'미지정')))
  depts.forEach(d => result.push({ id:`dept-${d}`, label:d, typeLabel:'부서', type:'dept' }))
  groups.forEach(g => result.push({ id:`mg-${g.id}`, label:g.title, typeLabel:'회의체', type:'meeting_group' }))
  groups.forEach(g => (g.minutes||[]).forEach((m,i) => result.push({ id:`session-${g.id}-${i}`, label:m.session_title||`${m.session_number||i+1}차 회의`, typeLabel:'회의', type:'session' })))
  return result
})

function availableRels(nodeId) {
  const n = connectableNodes.value.find(n => n.id === nodeId)
  return REL_OPTIONS_FOR[n?.type] || ['관련']
}

const createConnectNodeId = ref('')
const createRelType = ref('관련')

function openUploadModal() { showUploadModal.value = true; uploadForm.value = { label:'', fileType:'회의록', connectNodeId:'', relType:'생성' } }

function doAddFile() {
  if (!uploadForm.value.label.trim()) return
  const fromNode = gNodes.find(n => n.id === uploadForm.value.connectNodeId)
  const fromIdx = fromNode ? gNodes.indexOf(fromNode) : -1
  const fromX = fromNode?.x||0, fromZ = fromNode?.z||0
  const phi = Math.atan2(fromZ, fromX) + 0.28
  const baseR = Math.sqrt(fromX*fromX+fromZ*fromZ)
  const newNode = { id:`file-new-${Date.now()}`, label:uploadForm.value.label, type:'file', fileType:uploadForm.value.fileType, x:Math.cos(phi)*(baseR+90), y:(fromNode?.y||0)+42, z:Math.sin(phi)*(baseR+90) }
  gNodes.push(newNode)
  if (fromIdx >= 0) gEdges.push({ from:fromIdx, to:gNodes.length-1, rel:uploadForm.value.relType })
  showUploadModal.value = false
}

// ─── Node Edit Modal ──────────────────────────────────────────
const nodeEditModal = ref(null)  // { nodeIdx, type, form: {...} }
const newMemberForm = ref({ name:'', position:'', email:'', phone:'', role:'member' })
const showNewMemberForm = ref(false)

function openNodeEdit(nodeIdx) {
  const n = gNodes[nodeIdx]
  if (!n) return
  hoverNode.value = null; tooltipHover.value = false
  if (n.type === 'meeting_group') {
    // 기존 설정 모달 활용
    openDetail(n.data)
    nextTick(() => openGroupSetting())
    return
  }
  if (n.type === 'org') {
    nodeEditModal.value = { nodeIdx, type: 'org', form: { label: n.label } }
    return
  }
  if (n.type === 'dept') {
    const members = (n.members || []).map(m => ({ ...m }))
    nodeEditModal.value = { nodeIdx, type: 'dept', form: { label: n.label, members } }
    return
  }
  if (n.type === 'session') {
    nodeEditModal.value = { nodeIdx, type: 'session', form: { label: n.label } }
    return
  }
  if (n.type === 'file') {
    nodeEditModal.value = { nodeIdx, type: 'file', form: { label: n.label, fileType: n.fileType || '회의록' } }
    return
  }
  if (n.type === 'person') {
    nodeEditModal.value = { nodeIdx, type: 'person', form: { label: n.label, role: n.role || 'member' } }
    return
  }
}

function closeNodeEdit() {
  nodeEditModal.value = null
  showNewMemberForm.value = false
  newMemberForm.value = { name:'', position:'', email:'', phone:'', role:'member' }
}

function openNewMemberForm() {
  showNewMemberForm.value = true
  newMemberForm.value = { name:'', position:'', email:'', phone:'', role:'member' }
}

function cancelNewMemberForm() {
  showNewMemberForm.value = false
  newMemberForm.value = { name:'', position:'', email:'', phone:'', role:'member' }
}

function addDeptMember() {
  const name = newMemberForm.value.name.trim()
  if (!name || !nodeEditModal.value) return
  const m = nodeEditModal.value.form.members
  if (m.find(x => x.userName === name)) return
  const newId = Date.now()
  m.push({
    userId: newId,
    userName: name,
    position: newMemberForm.value.position.trim(),
    email: newMemberForm.value.email.trim(),
    phone: newMemberForm.value.phone.trim(),
    role: newMemberForm.value.role,
    department: nodeEditModal.value.form.label
  })
  cancelNewMemberForm()
}

function removeDeptMember(idx) {
  nodeEditModal.value.form.members.splice(idx, 1)
}

function saveNodeEdit() {
  if (!nodeEditModal.value) return
  const { nodeIdx, type, form } = nodeEditModal.value
  const n = gNodes[nodeIdx]
  if (!n) return
  if (type === 'org') {
    n.label = form.label.trim() || n.label
  } else if (type === 'dept') {
    const oldLabel = n.label
    n.label = form.label.trim() || n.label
    n.id = `dept-${n.label}`
    n.members = form.members
    // 기존 person 노드 소속 업데이트
    gNodes.forEach(pn => { if (pn.type === 'person' && n.members.find(m => m.userId === pn.userId)) pn.label = pn.label })
    // 부서 구성원 노드 추가 (새로 추가된 멤버)
    const deptIdx = nodeIdx
    form.members.forEach(mb => {
      const existing = gNodes.find(pn => pn.type === 'person' && pn.userId === mb.userId)
      if (!existing) {
        const basePhi = Math.atan2(n.z, n.x)
        const baseR = Math.sqrt(n.x*n.x + n.z*n.z)
        const pPhi = basePhi + (Math.random()-0.5) * 0.8
        const pIdx = gNodes.length
        gNodes.push({ id:`person-${mb.userId}`, label:mb.userName, type:'person', userId:mb.userId, role:mb.role, x:Math.cos(pPhi)*(baseR+72), y:Math.random()>0.5?30:-30, z:Math.sin(pPhi)*(baseR+72) })
        gEdges.push({ from:deptIdx, to:pIdx, rel:'소속' })
      }
    })
  } else if (type === 'session') {
    n.label = form.label.trim() || n.label
    if (n.data) n.data.session_title = n.label
  } else if (type === 'file') {
    n.label = form.label.trim() || n.label
    n.fileType = form.fileType
  } else if (type === 'person') {
    n.label = form.label.trim() || n.label
    n.role = form.role
  }
  closeNodeEdit()
}

// Demo data used when no real data available
function getDemoData() {
  return [
    { id: 1, title: '전략기획위원회', status: 'active', urgency: 'critical', minutes: [{ session_title: '2025 전략 수립', session_number: 1 }, { session_title: '예산 계획 검토', session_number: 2 }], reports: [{ file_name: '전략보고서_Q1.pdf' }], members: [{ userId: 1, userName: '김철수', role: 'admin', department: '기획팀' }, { userId: 2, userName: '이영희', role: 'presenter', department: '운영팀' }, { userId: 3, userName: '박민준', role: 'presenter', department: '기획팀' }] },
    { id: 2, title: '운영위원회', status: 'active', urgency: 'warning', minutes: [{ session_title: '운영 현황 보고', session_number: 1 }], reports: [{ file_name: '운영보고서_5월.pdf' }, { file_name: '성과보고서.pdf' }], members: [{ userId: 4, userName: '최지영', role: 'admin', department: '경영지원팀' }, { userId: 2, userName: '이영희', role: 'presenter', department: '운영팀' }] },
    { id: 3, title: '개발팀 주간회의', status: 'active', urgency: 'normal', minutes: [{ session_title: '스프린트 계획', session_number: 1 }, { session_title: '기술 검토', session_number: 2 }], reports: [], members: [{ userId: 5, userName: '정도현', role: 'admin', department: '개발팀' }, { userId: 6, userName: '한소희', role: 'presenter', department: '개발팀' }] },
    { id: 4, title: '마케팅 전략회의', status: 'ended', urgency: 'normal', minutes: [{ session_title: '캠페인 기획', session_number: 1 }], reports: [{ file_name: '마케팅보고서.pdf' }], members: [{ userId: 7, userName: '윤재원', role: 'admin', department: '마케팅팀' }, { userId: 3, userName: '박민준', role: 'presenter', department: '기획팀' }] },
    { id: 5, title: '인사위원회', status: 'ended', urgency: 'normal', minutes: [{ session_title: '채용 검토', session_number: 1 }], reports: [], members: [{ userId: 1, userName: '김철수', role: 'admin', department: '기획팀' }, { userId: 8, userName: '오세진', role: 'presenter', department: '인사팀' }] },
  ]
}

const meetingGroups = computed(() => {
  const map = new Map()
  // All meetings from store (includes newly created ones)
  meetingsStore.meetings.forEach(m => {
    map.set(m.id, { id: m.id, title: m.title, minutes: [], reports: [], members: [] })
  })
  // Add minutes & reports
  minutes.value.forEach(m => {
    if (!map.has(m.meeting_id)) map.set(m.meeting_id, { id: m.meeting_id, title: m.meeting_title, minutes: [], reports: [], members: [] })
    map.get(m.meeting_id).minutes.push(m)
  })
  reports.value.forEach(r => {
    if (!map.has(r.meeting_id)) map.set(r.meeting_id, { id: r.meeting_id, title: r.meeting_title, minutes: [], reports: [], members: [] })
    map.get(r.meeting_id).reports.push(r)
  })
  membersData.value.forEach(mb => {
    if (map.has(mb.meetingId)) {
      const g = map.get(mb.meetingId)
      if (!g.members.find(m => m.userId === mb.userId)) g.members.push(mb)
    }
  })
  return [...map.values()]
})

const filteredGroups = computed(() => {
  if (!search.value) return meetingGroups.value
  const q = search.value.toLowerCase()
  return meetingGroups.value.filter(g =>
    g.title.toLowerCase().includes(q) ||
    g.minutes.some(m => (m.session_title || '').toLowerCase().includes(q)) ||
    g.reports.some(r => (r.file_name || '').toLowerCase().includes(q)) ||
    g.members.some(m => m.userName.toLowerCase().includes(q))
  )
})

function buildGraphNodes() {
  const nodes = [], edges = []
  const data = meetingGroups.value.length ? meetingGroups.value : getDemoData()

  // ── 조직 root ─────────────────────────────────────────────
  const orgIdx = nodes.length
  nodes.push({ id:'org-root', label:'조직', type:'org', x:0, y:0, z:0 })

  // ── 부서 (조직 →[소속]→ 부서) ──────────────────────────
  const deptIdxMap = new Map()
  const deptMembersMap = new Map()
  data.forEach(g => {
    ;(g.members||[]).forEach(mb => {
      const d = mb.department || mb.dept || '미지정'
      if (!deptMembersMap.has(d)) deptMembersMap.set(d, [])
      const list = deptMembersMap.get(d)
      if (!list.find(m => m.userId === mb.userId)) list.push(mb)
    })
  })
  const uniqueDepts = [...deptMembersMap.keys()]
  uniqueDepts.forEach((deptName, di) => {
    const phi = (di / Math.max(uniqueDepts.length, 1)) * Math.PI * 2
    const deptIdx = nodes.length
    deptIdxMap.set(deptName, deptIdx)
    nodes.push({ id:`dept-${deptName}`, label:deptName, type:'dept', x:Math.cos(phi)*130, y:8, z:Math.sin(phi)*130, members:deptMembersMap.get(deptName) })
    edges.push({ from:orgIdx, to:deptIdx, rel:'소속' })
  })

  // ── 사람 (부서 →[소속]→ 사람) ──────────────────────────
  const personIdxMap = new Map()
  uniqueDepts.forEach(deptName => {
    const deptIdx = deptIdxMap.get(deptName)
    const members = deptMembersMap.get(deptName) || []
    const dn = nodes[deptIdx]
    const basePhi = Math.atan2(dn.z, dn.x)
    const baseR = Math.sqrt(dn.x*dn.x + dn.z*dn.z)
    members.forEach((mb, mi) => {
      const pKey = String(mb.userId)
      if (!personIdxMap.has(pKey)) {
        const pPhi = basePhi + (mi - (members.length-1)/2) * 0.48
        const personIdx = nodes.length
        personIdxMap.set(pKey, personIdx)
        nodes.push({ id:`person-${mb.userId}`, label:mb.userName||mb.name||'?', type:'person', userId:mb.userId, role:mb.role, x:Math.cos(pPhi)*(baseR+72), y:mi%2===0?30:-30, z:Math.sin(pPhi)*(baseR+72) })
        edges.push({ from:deptIdx, to:personIdx, rel:'소속' })
      }
    })
  })

  // ── 회의체 (회의체 →[참여부서]→ 부서, 회의체 →[개최]→ 회의 →[생성]→ 파일) ──
  data.forEach((g, gi) => {
    const phi = (gi / Math.max(data.length, 1)) * Math.PI * 2 + 0.45
    const mgR = 265
    const mgIdx = nodes.length
    nodes.push({ id:`mg-${g.id||gi}`, label:g.title||`회의체${gi+1}`, type:'meeting_group', x:Math.cos(phi)*mgR, y:-55, z:Math.sin(phi)*mgR, data:g, groupIdx:gi })

    // 회의체 →[참여부서]→ 부서
    const partDepts = new Set((g.members||[]).map(mb => mb.department||mb.dept||'미지정'))
    partDepts.forEach(d => { const di = deptIdxMap.get(d); if (di !== undefined) edges.push({ from:mgIdx, to:di, rel:'참여부서' }) })

    // 회의체 →[개최]→ 회의 →[생성]→ 파일(회의록)
    ;(g.minutes||[]).forEach((m, mi) => {
      const sPhi = phi + (mi - (g.minutes.length-1)/2)*0.4
      const sR = mgR + 100
      const sIdx = nodes.length
      nodes.push({ id:`session-${g.id||gi}-${mi}`, label:m.session_title||`${m.session_number||mi+1}차 회의`, type:'session', x:Math.cos(sPhi)*sR, y:-55+(mi%3===0?38:mi%3===1?0:-38), z:Math.sin(sPhi)*sR, groupIdx:gi, data:m })
      edges.push({ from:mgIdx, to:sIdx, rel:'개최' })
      const fPhi = sPhi + 0.22
      const fIdx = nodes.length
      nodes.push({ id:`file-min-${g.id||gi}-${mi}`, label:m.session_title||`${m.session_number||mi+1}차 회의록`, type:'file', fileType:'회의록', x:Math.cos(fPhi)*(sR+78), y:-55+(mi%3===0?62:mi%3===1?24:-62), z:Math.sin(fPhi)*(sR+78), groupIdx:gi })
      edges.push({ from:sIdx, to:fIdx, rel:'생성' })
    })

    // 회의체 →[생성]→ 파일(보고자료)
    ;(g.reports||[]).forEach((rp, ri) => {
      const rPhi = phi - 0.4 + ri*0.28
      const rIdx = nodes.length
      nodes.push({ id:`file-rep-${g.id||gi}-${ri}`, label:rp.file_name||'보고자료', type:'file', fileType:'보고자료', x:Math.cos(rPhi)*(mgR+88), y:-80+ri*26, z:Math.sin(rPhi)*(mgR+88), groupIdx:gi })
      edges.push({ from:mgIdx, to:rIdx, rel:'생성' })
    })
  })

  return { nodes, edges }
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
  if (!g?.minutes?.length && !g?.reports?.length) return 'critical'
  if (!g?.reports?.length) return 'warning'
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
    // Default view: org + dept + meeting_group
    gNodes.forEach((n, i) => { if (['org','dept','meeting_group'].includes(n.type)) vis.add(i) })
  } else {
    const hubNode = gNodes[expandedHubIdx]
    if (hubNode?.type === 'meeting_group') {
      vis.add(expandedHubIdx)
      gEdges.forEach(e => {
        if (e.from === expandedHubIdx) {
          vis.add(e.to)
          // session 하위 file도 표시
          if (gNodes[e.to]?.type === 'session') gEdges.forEach(e2 => { if (e2.from === e.to) vis.add(e2.to) })
        }
        if (e.to === expandedHubIdx) vis.add(e.from)
      })
      if (expandedDeptIdx !== null) {
        gEdges.forEach(e => { if (e.from === expandedDeptIdx && gNodes[e.to]?.type === 'person') vis.add(e.to) })
      }
    } else {
      gNodes.forEach((n, i) => { if (['org','dept','meeting_group'].includes(n.type)) vis.add(i) })
      if (expandedDeptIdx !== null) {
        gEdges.forEach(e => { if (e.from === expandedDeptIdx && gNodes[e.to]?.type === 'person') vis.add(e.to) })
      }
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

function drawArchiveGraph() {
  const canvas = canvasRef.value; if (!canvas||!ctx) return
  const w=canvas.offsetWidth,h=canvas.offsetHeight
  if(w===0||h===0) return
  ctx.clearRect(0,0,w,h)
  const isDark = nightMode.value
  if(!isDark){ctx.fillStyle='#eef2ff';ctx.fillRect(0,0,w,h)}
  if(!gNodes.length){ctx.fillStyle=isDark?'rgba(148,163,184,.5)':'rgba(100,116,139,.6)';ctx.font='14px sans-serif';ctx.textAlign='center';ctx.fillText('데이터를 불러오는 중...',w/2,h/2);return}
  const visibleSet = getVisibleSet()
  const projected=gNodes.map((n,i)=>({...projectNode(n,w,h),node:n,idx:i}))
  const order=projected.slice().sort((a,b)=>a.z-b.z)
  const zf=Math.max(0.6,Math.min(2.5,worldZoom))
  const now = Date.now() / 1000
  gEdges.forEach(e => {
    const { from, to, rel } = e
    if (!visibleSet.has(from)||!visibleSet.has(to)) return
    if (from>=projected.length||to>=projected.length) return
    const pa=projected[from], pb=projected[to]
    const relColor = REL_COLORS[rel] || '#60a5fa'
    const isFocused = focusNode!==null&&(focusNode===from||focusNode===to)
    const alpha = isFocused ? 0.75 : Math.max(0.07, Math.min(0.35,(pa.scale+pb.scale)/2))
    const lw = isFocused ? 1.8 : 0.9
    const dx=pb.sx-pa.sx, dy=pb.sy-pa.sy
    const len=Math.sqrt(dx*dx+dy*dy)
    if (len < 8) return
    const ux=dx/len, uy=dy/len
    const as = Math.max(5, 8*Math.min(1.4,(pa.scale+pb.scale)/2)*Math.min(1.5,zf))
    const x1=pa.sx+ux*12, y1=pa.sy+uy*12
    const x2=pb.sx-ux*(as+10), y2=pb.sy-uy*(as+10)
    if (Math.sqrt((x2-x1)**2+(y2-y1)**2) < 4) return
    // Line
    ctx.beginPath(); ctx.moveTo(x1,y1); ctx.lineTo(x2,y2)
    ctx.strokeStyle=hexToRgba(relColor,alpha); ctx.lineWidth=lw; ctx.stroke()
    // Arrowhead
    const tipX=x2+ux*as, tipY=y2+uy*as
    const px2=-uy*as*0.44, py2=ux*as*0.44
    ctx.beginPath(); ctx.moveTo(tipX,tipY); ctx.lineTo(x2+px2,y2+py2); ctx.lineTo(x2-px2,y2-py2)
    ctx.closePath(); ctx.fillStyle=hexToRgba(relColor,alpha); ctx.fill()
    // Relation label
    if (rel && len > 42 && zf > 0.85) {
      const lx=(pa.sx+pb.sx)/2-uy*8, ly=(pa.sy+pb.sy)/2+ux*8
      ctx.font=`${Math.max(7,Math.round(8*Math.min(1.8,zf)))}px sans-serif`
      ctx.textAlign='center'; ctx.textBaseline='middle'
      ctx.fillStyle=hexToRgba(relColor,Math.min(1,alpha+0.35))
      ctx.fillText(rel,lx,ly)
    }
  })
  order.forEach(p=>{
    if(!visibleSet.has(p.idx)) return
    const n=p.node,isFocused=focusNode===p.idx
    const isEnded=n.data?.status==='ended'
    ctx.globalAlpha=1
    if(n.type==='org'){
      const r=Math.min(30,(isFocused?22:18)*p.scale*zf)
      const grad=ctx.createRadialGradient(p.sx,p.sy,0,p.sx,p.sy,r)
      grad.addColorStop(0,isDark?'rgba(100,116,139,0.95)':'rgba(71,85,105,0.9)')
      grad.addColorStop(1,isDark?'rgba(51,65,85,0.6)':'rgba(100,116,139,0.5)')
      // Pentagon shape
      ctx.beginPath()
      for(let a=0;a<5;a++){const ang=a*Math.PI*2/5-Math.PI/2;const px2=p.sx+r*Math.cos(ang),py2=p.sy+r*Math.sin(ang);a===0?ctx.moveTo(px2,py2):ctx.lineTo(px2,py2)}
      ctx.closePath(); ctx.fillStyle=grad; ctx.fill()
      ctx.strokeStyle=isDark?'rgba(148,163,184,0.6)':'rgba(71,85,105,0.8)'; ctx.lineWidth=1.5; ctx.stroke()
      if(p.scale>.25){const fs=Math.max(10,Math.min(16,Math.round(12*zf)));ctx.fillStyle=isDark?'rgba(226,232,240,0.9)':'rgba(255,255,255,0.95)';ctx.font=`bold ${fs}px sans-serif`;ctx.textAlign='center';ctx.textBaseline='middle';ctx.fillText('조직',p.sx,p.sy)}
    } else if(n.type==='meeting_group'){
      const hubColor=getHubFill(n.data)
      const urgency=computeUrgency(n.data)
      const r=Math.min(36,(isFocused?26:22)*p.scale*zf)
      if(!isEnded&&urgency==='critical'){const pulse=0.3+0.25*Math.sin(now*3.5);const auraR=r*(1.8+0.4*Math.sin(now*2.2));const ag=ctx.createRadialGradient(p.sx,p.sy,r*.5,p.sx,p.sy,auraR);ag.addColorStop(0,`rgba(239,68,68,${pulse})`);ag.addColorStop(1,'rgba(239,68,68,0)');ctx.beginPath();ctx.arc(p.sx,p.sy,auraR,0,Math.PI*2);ctx.fillStyle=ag;ctx.fill()}
      const grad=ctx.createRadialGradient(p.sx,p.sy,0,p.sx,p.sy,r)
      if(isEnded){grad.addColorStop(0,'rgba(100,116,139,0.45)');grad.addColorStop(1,'rgba(71,85,105,0.2)')}
      else{const rgb=urgency==='critical'?'239,68,68':urgency==='warning'?'245,158,11':'59,130,246';grad.addColorStop(0,`rgba(${rgb},0.9)`);grad.addColorStop(1,`rgba(${rgb},0.4)`)}
      ctx.beginPath();ctx.arc(p.sx,p.sy,r,0,Math.PI*2);ctx.fillStyle=grad;ctx.fill()
      if(isFocused||selectedNodeIdx.value===p.idx){ctx.strokeStyle=isDark?'#fff':'#1e293b';ctx.lineWidth=2.5;ctx.stroke()}
      if(p.scale>.28){const fs=Math.max(11,Math.min(20,Math.round(14*zf)));if(isEnded)ctx.fillStyle=isDark?`rgba(148,163,184,${Math.min(1,p.scale*1.4)})`:`rgba(71,85,105,${Math.min(1,p.scale*1.6)})`;else ctx.fillStyle=isDark?`rgba(255,255,255,${Math.min(1,p.scale*1.5)})`:`rgba(30,58,138,${Math.min(1,p.scale*1.8)})`;ctx.font=`bold ${fs}px sans-serif`;ctx.textAlign='center';ctx.textBaseline='middle';ctx.fillText(n.label.length>7?n.label.slice(0,6)+'…':n.label,p.sx,p.sy)}
    } else if(n.type==='session'){
      const r=Math.min(18,(isFocused?14:11)*p.scale*zf)
      roundRect(ctx,p.sx-r,p.sy-r*0.75,r*2,r*1.5,r*.3)
      ctx.fillStyle=isDark?'rgba(5,150,105,0.7)':'rgba(209,250,229,0.9)'; ctx.fill()
      ctx.strokeStyle=isDark?'#34d399':'#10b981'; ctx.lineWidth=isFocused?1.8:0.9; ctx.stroke()
      if(p.scale>.35&&zf>.7){const fs=Math.max(8,Math.min(13,Math.round(10*zf)));ctx.fillStyle=isDark?`rgba(167,243,208,${Math.min(1,p.scale*1.6)})`:`rgba(6,78,59,${Math.min(1,p.scale*1.8)})`;ctx.font=`${fs}px sans-serif`;ctx.textAlign='center';ctx.textBaseline='middle';ctx.fillText(n.label.length>8?n.label.slice(0,7)+'…':n.label,p.sx,p.sy)}
    } else if(n.type==='file'){
      const ftColor = n.fileType==='회의록'?'#60a5fa':n.fileType==='발제자료'?'#a78bfa':'#34d399'
      const ftBg = n.fileType==='회의록'?(isDark?'rgba(30,58,138,0.8)':'rgba(219,234,254,0.9)'):n.fileType==='발제자료'?(isDark?'rgba(76,29,149,0.8)':'rgba(237,233,254,0.9)'):(isDark?'rgba(5,78,22,0.8)':'rgba(220,252,231,0.9)')
      const r=Math.min(15,(isFocused?11:8)*p.scale*zf)
      roundRect(ctx,p.sx-r,p.sy-r,r*2,r*2,r*.4)
      ctx.fillStyle=ftBg; ctx.fill(); ctx.strokeStyle=ftColor+'bb'; ctx.lineWidth=0.9; ctx.stroke()
      // File type icon letter
      if(r>6){const letter=n.fileType==='회의록'?'문':n.fileType==='발제자료'?'제':'보';ctx.fillStyle=ftColor;ctx.font=`bold ${Math.max(7,Math.round(r*0.9))}px sans-serif`;ctx.textAlign='center';ctx.textBaseline='middle';ctx.fillText(letter,p.sx,p.sy)}
      if(p.scale>.38&&zf>.75){const fs=Math.max(8,Math.min(13,Math.round(10*zf)));ctx.fillStyle=isDark?`rgba(255,255,255,${Math.min(1,p.scale*1.5)})`:`rgba(30,41,59,${Math.min(1,p.scale*1.6)})`;ctx.font=`${fs}px sans-serif`;ctx.textAlign='center';ctx.textBaseline='top';ctx.fillText(n.label.length>9?n.label.slice(0,8)+'…':n.label,p.sx,p.sy+r+3)}
    } else if(n.type==='dept'){
      const isExpanded=expandedDeptIdx===p.idx
      const r=Math.min(18,(isFocused||isExpanded?14:11)*p.scale*zf)
      ctx.beginPath()
      for(let a=0;a<6;a++){const ang=a*Math.PI/3-Math.PI/6;const px2=p.sx+r*Math.cos(ang),py2=p.sy+r*Math.sin(ang);a===0?ctx.moveTo(px2,py2):ctx.lineTo(px2,py2)}
      ctx.closePath()
      ctx.fillStyle=isDark?'rgba(71,85,105,0.75)':'rgba(148,163,184,0.85)'; ctx.fill()
      ctx.strokeStyle=isExpanded?'#f1f5f9':'rgba(148,163,184,0.5)'; ctx.lineWidth=isExpanded?1.5:0.8; ctx.stroke()
      if(p.scale>.32){const fs=Math.max(8,Math.min(13,Math.round(10*zf)));ctx.fillStyle=isDark?`rgba(226,232,240,${Math.min(1,p.scale*1.5)})`:`rgba(30,41,59,${Math.min(1,p.scale*1.8)})`;ctx.font=`${fs}px sans-serif`;ctx.textAlign='center';ctx.textBaseline='middle';ctx.fillText(n.label.length>5?n.label.slice(0,4)+'…':n.label,p.sx,p.sy)}
    } else if(n.type==='person'){
      const r=Math.min(18,(isFocused?14:11)*p.scale*zf)
      const grad=ctx.createRadialGradient(p.sx,p.sy,0,p.sx,p.sy,r)
      if(isDark){grad.addColorStop(0,'rgba(139,92,246,.9)');grad.addColorStop(1,'rgba(109,40,217,.5)')}
      else{grad.addColorStop(0,'rgba(167,139,250,.95)');grad.addColorStop(1,'rgba(124,58,237,.6)')}
      ctx.beginPath();ctx.arc(p.sx,p.sy,r,0,Math.PI*2);ctx.fillStyle=grad;ctx.fill()
      ctx.strokeStyle=n.role==='admin'?'#fbbf24':'#a78bfa';ctx.lineWidth=n.role==='admin'?2:1;ctx.stroke()
      if(p.scale>.3&&r>7){ctx.fillStyle='#fff';ctx.font=`bold ${Math.max(8,Math.min(14,Math.round(10*zf*p.scale)))}px sans-serif`;ctx.textAlign='center';ctx.textBaseline='middle';ctx.fillText(n.label[0]||'?',p.sx,p.sy)}
      if(p.scale>.4&&zf>.8){ctx.fillStyle=isDark?`rgba(196,181,253,${Math.min(1,p.scale*1.5)})`:`rgba(76,29,149,${Math.min(1,p.scale*1.5)})`;ctx.font=`${Math.max(9,Math.min(14,Math.round(11*zf)))}px sans-serif`;ctx.textAlign='center';ctx.textBaseline='top';ctx.fillText(n.label.length>5?n.label.slice(0,4)+'…':n.label,p.sx,p.sy+r+3)}
    }
    ctx.globalAlpha=1
  })
}

function animateGraph() {
  if(autoRotate && !rotationPaused) rotY+=.002
  camX+=(targetCamX-camX)*.05;camY+=(targetCamY-camY)*.05;camZ+=(targetCamZ-camZ)*.05
  worldZoom+=(targetZoom-worldZoom)*.1
  drawArchiveGraph()
  animId=requestAnimationFrame(animateGraph)
}

// ─── Mouse ────────────────────────────────────────────────────
function onMouseDown(e) { isDragging=true;autoRotate=false;lastMx=e.clientX;lastMy=e.clientY }

function onMouseMove(e) {
  if (bottomResizing) return
  if(isDragging){
    rotY+=(e.clientX-lastMx)*.004;rotX+=(e.clientY-lastMy)*.004
    rotX=Math.max(-1.2,Math.min(1.2,rotX));lastMx=e.clientX;lastMy=e.clientY
    if(hoverNode.value){clearTimeout(tooltipHideTimer);hoverNode.value=null}
    return
  }
  if(viewMode.value!=='graph') return
  const canvas=canvasRef.value;if(!canvas) return
  const rect=canvas.getBoundingClientRect()
  const mx=e.clientX-rect.left,my=e.clientY-rect.top
  if(mx<0||my<0||mx>canvas.offsetWidth||my>canvas.offsetHeight){scheduleHideTooltip();return}
  const w=canvas.offsetWidth,h=canvas.offsetHeight
  let closest=null,minDist=Infinity
  gNodes.forEach((n,i)=>{
    if(!['meeting_group','dept','org'].includes(n.type)) return
    const p=projectNode(n,w,h)
    const zf=Math.max(.6,Math.min(2.5,worldZoom))
    const d=Math.hypot(p.sx-mx,p.sy-my)
    if(d<22*p.scale*zf+10&&d<minDist){minDist=d;closest=i}
  })
  if(closest!==null){
    const tx=Math.min(e.clientX+16,window.innerWidth-220)
    const ty=Math.max(e.clientY-60,60)
    showTooltipAt(gNodes[closest],tx,ty)
  } else { scheduleHideTooltip() }
}

function onMouseUp() {
  isDragging=false
}

function onWheel(e) {
  e.preventDefault()
  targetZoom=Math.max(.25,Math.min(4,targetZoom+(e.deltaY<0?.12:-.12)))
}
onWheel._t=null

function onCanvasClick(e) {
  if(isDragging) return
  const canvas=canvasRef.value;if(!canvas) return
  const rect=canvas.getBoundingClientRect()
  const mx=e.clientX-rect.left,my=e.clientY-rect.top
  const w=canvas.offsetWidth,h=canvas.offsetHeight
  let closest=null,minDist=Infinity
  gNodes.forEach((n,i)=>{
    if(!getVisibleSet().has(i)) return
    const p=projectNode(n,w,h)
    const zf=Math.max(.6,Math.min(2.5,worldZoom))
    const baseR=n.type==='meeting_group'?22:n.type==='org'?20:n.type==='dept'?13:n.type==='session'?11:n.type==='person'?11:9
    const d=Math.hypot(p.sx-mx,p.sy-my)
    if(d<baseR*p.scale*zf+6&&d<minDist){minDist=d;closest=i}
  })
  if(closest!==null){
    const n=gNodes[closest]
    if(n.type==='meeting_group') {
      if(selectedNodeIdx.value===closest) {
        selectedNodeIdx.value=null; expandedHubIdx=null; expandedDeptIdx=null
        targetZoom=Math.max(1.0,targetZoom/1.6)
        targetCamX=0;targetCamY=0;targetCamZ=0
      } else {
        selectedNodeIdx.value=closest; expandedHubIdx=closest; expandedDeptIdx=null
        targetZoom=Math.min(3.0,Math.max(targetZoom,1.0)*1.6)
        targetCamX=n.x*.55;targetCamY=n.y*.55;targetCamZ=n.z*.55
        breadcrumb.value=[{ label: n.label, idx: closest, type: 'meeting_group' }]
        openDetail(n.data)
      }
    } else if(n.type==='dept') {
      expandedDeptIdx = expandedDeptIdx===closest ? null : closest
      if(expandedDeptIdx!==null) {
        targetCamX=n.x*.6;targetCamY=n.y*.6;targetCamZ=n.z*.6
        targetZoom=Math.min(3.5,targetZoom*1.2)
        const hubEntry = breadcrumb.value.find(b=>b.type==='meeting_group')
        breadcrumb.value = hubEntry ? [hubEntry,{label:n.label,idx:closest,type:'dept'}] : [{label:n.label,idx:closest,type:'dept'}]
      } else {
        breadcrumb.value = breadcrumb.value.filter(b=>b.type!=='dept')
      }
    }
    focusNode=closest
  } else {
    // 배경 클릭: 아무것도 하지 않음
  }
}

function onCanvasDblClick(e) {
  const canvas=canvasRef.value;if(!canvas) return
  const rect=canvas.getBoundingClientRect()
  const mx=e.clientX-rect.left,my=e.clientY-rect.top
  const w=canvas.offsetWidth,h=canvas.offsetHeight
  let closest=null,minDist=Infinity
  gNodes.forEach((n,i)=>{
    if(!getVisibleSet().has(i)) return
    const p=projectNode(n,w,h)
    const zf=Math.max(.6,Math.min(2.5,worldZoom))
    const baseR=n.type==='meeting_group'?22:n.type==='org'?20:n.type==='dept'?13:n.type==='session'?11:n.type==='person'?11:9
    const d=Math.hypot(p.sx-mx,p.sy-my)
    if(d<baseR*p.scale*zf+10&&d<minDist){minDist=d;closest=i}
  })
  if(closest!==null) openNodeEdit(closest)
}

function onTouchStart(e){isDragging=true;autoRotate=false;lastMx=e.touches[0].clientX;lastMy=e.touches[0].clientY}
function onTouchMove(e){if(!isDragging)return;rotY+=(e.touches[0].clientX-lastMx)*.004;rotX+=(e.touches[0].clientY-lastMy)*.004;rotX=Math.max(-1.2,Math.min(1.2,rotX));lastMx=e.touches[0].clientX;lastMy=e.touches[0].clientY}
function onTouchEnd(){isDragging=false}

function onBreadcrumbReset() {
  breadcrumb.value = []; selectedNodeIdx.value = null
  expandedHubIdx = null; expandedDeptIdx = null
  targetCamX = 0; targetCamY = 0; targetCamZ = 0
  targetZoom = Math.max(1.0, targetZoom / 1.5)
}

function onBreadcrumbClick(item, index) {
  breadcrumb.value = breadcrumb.value.slice(0, index + 1)
  if(item.type === 'meeting_group') {
    selectedNodeIdx.value = item.idx; expandedHubIdx = item.idx; expandedDeptIdx = null
    const n = gNodes[item.idx]
    if(n) { targetCamX=n.x*.55; targetCamY=n.y*.55; targetCamZ=n.z*.55 }
    targetZoom = Math.min(3.0, Math.max(targetZoom, 1.0) * 1.2)
  } else if(item.type === 'dept') {
    expandedDeptIdx = item.idx
    const n = gNodes[item.idx]
    if(n) { targetCamX=n.x*.6; targetCamY=n.y*.6; targetCamZ=n.z*.6 }
  }
}

// ─── Lifecycle ─────────────────────────────────────────────────
onMounted(async () => {
  await nextTick()
  initAgentGreeting('hyean')
  window.addEventListener('mousemove', onGlobalMouseMove)
  window.addEventListener('mouseup', onGlobalMouseUp)
  await meetingsStore.fetchMeetings()
  try {
    const [m, r, mtgs] = await Promise.all([
      api.get('/api/all-minutes').catch(()=>({data:[]})),
      api.get('/api/all-reports').catch(()=>({data:[]})),
      api.get('/api/meetings').catch(()=>({data:[]})),
    ])
    minutes.value=m.data; reports.value=r.data
    const memberResults = await Promise.all(
      mtgs.data.map(mtg =>
        api.get(`/api/meetings/${mtg.id}/members`)
          .then(res=>res.data.map(mb=>({meetingId:mtg.id,meetingTitle:mtg.title,userId:mb.user?.id,userName:mb.user?.name||'?',role:mb.role})))
          .catch(()=>[])
      )
    )
    membersData.value=memberResults.flat()
  } finally {
    loading.value=false
    const g=buildGraphNodes();gNodes=g.nodes;gEdges=g.edges
    initGraph()
  }
})

onBeforeUnmount(()=>{
  cancelAnimationFrame(animId);ro?.disconnect()
  window.removeEventListener('mousemove', onGlobalMouseMove)
  window.removeEventListener('mouseup', onGlobalMouseUp)
})

// Rebuild graph when new meetings are created
watch(() => meetingsStore.meetings.length, () => {
  const g = buildGraphNodes(); gNodes = g.nodes; gEdges = g.edges
})

watch(search, q=>{
  if(!q){focusNode=null;targetCamX=0;targetCamY=0;targetCamZ=0;return}
  const lower=q.toLowerCase()
  let bestIdx=null,bestScore=-1
  gNodes.forEach((n,i)=>{
    let score=n.label.toLowerCase().includes(lower)?(n.type==='hub'?10:n.type==='person'?6:5):0
    if(score>bestScore){bestScore=score;bestIdx=i}
  })
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

      <div class="view-toggle">
        <button :class="{ active: viewMode==='graph' }" @click="viewMode='graph'">
          <svg width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><circle cx="5" cy="12" r="2"/><circle cx="19" cy="5" r="2"/><circle cx="19" cy="19" r="2"/><path d="M7 12h5l5-5M12 12l5 5"/></svg>
          관계도
        </button>
        <button :class="{ active: viewMode==='list' }" @click="viewMode='list'">
          <svg width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01"/></svg>
          목록
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
          <div class="detail-header">
            <div>
              <div class="detail-meeting-name">{{ detailMeeting?.title }}</div>
              <div class="detail-meta">{{ detailMeeting?.members?.length||0 }}명 · {{ (detailMeeting?.minutes?.length||0)+(detailMeeting?.reports?.length||0) }}건</div>
            </div>
            <button class="detail-close" @click="detailOpen=false">✕</button>
          </div>
          <div class="detail-body">
            <button class="detail-setting-btn" @click="openGroupSetting" title="회의체 설정">
              <svg width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M12 15a3 3 0 100-6 3 3 0 000 6z"/><path d="M19.4 15a1.65 1.65 0 00.33 1.82l.06.06a2 2 0 010 2.83 2 2 0 01-2.83 0l-.06-.06a1.65 1.65 0 00-1.82-.33 1.65 1.65 0 00-1 1.51V21a2 2 0 01-2 2 2 2 0 01-2-2v-.09A1.65 1.65 0 009 19.4a1.65 1.65 0 00-1.82.33l-.06.06a2 2 0 01-2.83 0 2 2 0 010-2.83l.06-.06A1.65 1.65 0 004.68 15a1.65 1.65 0 00-1.51-1H3a2 2 0 01-2-2 2 2 0 012-2h.09A1.65 1.65 0 004.6 9a1.65 1.65 0 00-.33-1.82l-.06-.06a2 2 0 010-2.83 2 2 0 012.83 0l.06.06A1.65 1.65 0 009 4.68a1.65 1.65 0 001-1.51V3a2 2 0 012-2 2 2 0 012 2v.09a1.65 1.65 0 001 1.51 1.65 1.65 0 001.82-.33l.06-.06a2 2 0 012.83 0 2 2 0 010 2.83l-.06.06A1.65 1.65 0 0019.4 9a1.65 1.65 0 001.51 1H21a2 2 0 012 2 2 2 0 01-2 2h-.09a1.65 1.65 0 00-1.51 1z"/></svg>
              회의체 설정
            </button>
            <div v-if="detailMeeting?.minutes?.length" class="detail-section">
              <div class="detail-section-label">회의록</div>
              <div v-for="m in detailMeeting.minutes" :key="m.session_id||m.minutes_id" class="detail-doc-item">
                <div class="detail-doc-icon minutes"><svg width="10" height="10" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"/></svg></div>
                <div class="detail-doc-info"><div class="detail-doc-name">{{ m.session_title||`${m.session_number}차 회의록` }}</div><div class="detail-doc-date">{{ formatDate(m.ended_at) }}</div></div>
              </div>
            </div>
            <div v-if="detailMeeting?.reports?.length" class="detail-section">
              <div class="detail-section-label">보고서</div>
              <div v-for="r in detailMeeting.reports" :key="r.id" class="detail-doc-item">
                <div class="detail-doc-icon report"><svg width="10" height="10" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M9 17v-2m3 2v-4m3 4v-6m2 10H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"/></svg></div>
                <div class="detail-doc-info"><div class="detail-doc-name">{{ r.file_name||'보고서' }}</div><div class="detail-doc-date">{{ formatDate(r.submitted_at) }}</div></div>
              </div>
            </div>
            <div v-if="detailMeeting?.members?.length" class="detail-section">
              <div class="detail-section-label">참여부서</div>
              <table class="detail-dept-table">
                <tbody>
                  <tr v-for="dept in [...new Set(detailMeeting.members.map(mb => mb.department || mb.dept || '미지정'))].filter(Boolean)" :key="dept">
                    <td class="dept-name">{{ dept }}</td>
                    <td class="dept-count">{{ detailMeeting.members.filter(mb => (mb.department||mb.dept||'미지정') === dept).length }}명</td>
                  </tr>
                </tbody>
              </table>
            </div>
            <div v-if="detailMeeting?.members?.length" class="detail-section">
              <div class="detail-section-label">구성원</div>
              <table class="detail-member-table">
                <tbody>
                  <tr v-for="mb in detailMeeting.members" :key="mb.userId">
                    <td class="mb-name">{{ mb.userName || mb.name }}</td>
                    <td class="mb-dept">{{ mb.department || mb.dept || '' }}</td>
                    <td class="mb-role">{{ roleLabel(mb.role) }}</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
          </div>
        </Transition>

        <!-- Graph view -->
        <div v-if="loading && viewMode==='graph'" class="graph-loading">
          <div class="graph-loading-spinner"></div>
          <span>데이터 불러오는 중...</span>
        </div>
        <canvas v-show="!loading && viewMode==='graph'"
          ref="canvasRef"
          class="archive-canvas"
          @mousedown="onMouseDown"
          @mousemove="onMouseMove"
          @mouseup="onMouseUp"
          @mouseleave="onMouseUp(); scheduleHideTooltip()"
          @click="onCanvasClick"
          @dblclick="onCanvasDblClick"
          @wheel.prevent="onWheel"
          @touchstart.prevent="onTouchStart"
          @touchmove.prevent="onTouchMove"
          @touchend="onTouchEnd"
        ></canvas>

        <!-- 온톨로지 범례 -->
        <div v-if="!loading && viewMode==='graph'" class="graph-legend-onto">
          <div class="legend-onto-item"><div class="legend-onto-dot" style="background:#94a3b8;border-radius:0;clip-path:polygon(50% 0%,100% 38%,82% 100%,18% 100%,0% 38%)"></div>조직</div>
          <div class="legend-onto-item"><div class="legend-onto-dot" style="background:#3b82f6"></div>회의체</div>
          <div class="legend-onto-item"><div class="legend-onto-dot" style="background:#10b981;border-radius:2px"></div>회의</div>
          <div class="legend-onto-item"><div class="legend-onto-dot" style="background:#f59e0b;border-radius:2px"></div>파일</div>
          <div class="legend-onto-item"><div class="legend-onto-dot" style="background:#94a3b8;clip-path:polygon(50% 0%,100% 25%,100% 75%,50% 100%,0% 75%,0% 25%)"></div>부서</div>
          <div class="legend-onto-item"><div class="legend-onto-dot" style="background:#a78bfa"></div>사람</div>
          <div style="border-top:1px solid rgba(255,255,255,.1);margin:2px 0;padding-top:4px;display:flex;flex-direction:column;gap:3px">
            <div class="legend-onto-item"><div class="legend-onto-dash" style="background:#94a3b8"></div><span>소속</span></div>
            <div class="legend-onto-item"><div class="legend-onto-dash" style="background:#3b82f6"></div><span>참여부서</span></div>
            <div class="legend-onto-item"><div class="legend-onto-dash" style="background:#10b981"></div><span>개최</span></div>
            <div class="legend-onto-item"><div class="legend-onto-dash" style="background:#f59e0b"></div><span>생성</span></div>
          </div>
        </div>

        <!-- Graph floating action buttons (top-right of canvas) -->
        <div v-if="!loading && viewMode==='graph'" class="graph-float-btns">
          <div class="float-btn-item" @click="openCreateModal" @mousedown.prevent.stop="onFloatBtnMouseDown('meeting', $event)" title="클릭해서 회의체 생성">
            <div class="float-node-preview meeting-preview">
              <svg width="16" height="16" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24"><path d="M12 4v16m8-8H4"/></svg>
            </div>
            <span class="float-btn-label">회의체 생성</span>
          </div>
          <div class="float-btn-item" @click="openUploadModal" title="자료 업로드 및 노드 연결">
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
          <div class="list-header">
            <span class="list-title">{{ search ? `"${search}" 검색 결과` : '전체 목록' }}</span>
            <span class="list-count">{{ filteredGroups.length }}개 회의체</span>
          </div>
          <div v-if="loading" class="list-empty">불러오는 중...</div>
          <div v-else-if="!filteredGroups.length" class="list-empty">{{ search ? '검색 결과가 없습니다.' : '데이터가 없습니다.' }}</div>
          <div v-else class="meeting-groups">
            <div v-for="g in filteredGroups" :key="g.id" class="meeting-group">
              <div class="group-header" @click="expandedMeeting = expandedMeeting===g.id ? null : g.id">
                <div class="group-header-left">
                  <div class="group-dot"></div>
                  <span class="group-title">{{ g.title }}</span>
                </div>
                <div class="group-meta-right">
                  <span class="group-count">{{ g.minutes.length + g.reports.length }}건</span>
                  <svg width="12" height="12" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24" :style="{ transform: expandedMeeting===g.id?'rotate(180deg)':'', transition:'transform .2s' }"><path d="M19 9l-7 7-7-7"/></svg>
                </div>
              </div>
              <div v-if="expandedMeeting===g.id" class="group-body">
                <div v-if="g.minutes.length" class="doc-section">
                  <div class="doc-section-label">회의록</div>
                  <div v-for="m in g.minutes" :key="m.minutes_id||m.session_id" class="doc-item">
                    <div class="doc-icon minutes-icon"><svg width="10" height="10" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"/></svg></div>
                    <div class="doc-info"><div class="doc-name">{{ m.session_title||`${m.session_number}차 회의록` }}</div><div class="doc-meta">{{ formatDate(m.ended_at) }}</div></div>
                    <div class="doc-actions">

                      <button class="doc-btn icon-only" @click="downloadDummy(m.session_title||'회의록')"><svg width="10" height="10" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"/></svg></button>
                    </div>
                  </div>
                </div>
                <div v-if="g.reports.length" class="doc-section">
                  <div class="doc-section-label">보고서</div>
                  <div v-for="r in g.reports" :key="r.id" class="doc-item">
                    <div class="doc-icon report-icon"><svg width="10" height="10" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M9 17v-2m3 2v-4m3 4v-6m2 10H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"/></svg></div>
                    <div class="doc-info"><div class="doc-name">{{ r.file_name||'보고서' }}</div><div class="doc-meta">{{ formatDate(r.submitted_at) }}</div></div>
                    <div class="doc-actions">

                      <button class="doc-btn icon-only" @click="downloadDummy(r.file_name||'보고서')"><svg width="10" height="10" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"/></svg></button>
                    </div>
                  </div>
                </div>
                <div v-if="g.members.length" class="doc-section">
                  <div class="doc-section-label">구성원</div>
                  <div class="member-chips">
                    <div v-for="mb in g.members" :key="mb.userId" class="member-chip">
                      <div class="member-avatar">{{ mb.userName[0] }}</div>
                      <span class="member-name">{{ mb.userName }}</span>
                      <span class="member-role" :class="mb.role==='admin'?'role-admin':'role-presenter'">{{ roleLabel[mb.role]||mb.role }}</span>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
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
              <span class="supervisor-badge">AI</span>
            </div>
            <div class="supervisor-header-actions">
              <button class="agent-new-chat-btn" @click="clearAgentChat">새 채팅</button>
              <button class="agent-sidebar-close" @click="agentSidebarOpen=false">✕</button>
            </div>
          </div>
          <!-- Messages -->
          <div ref="agentMessagesEl" class="agent-messages">
            <div v-for="(msg,i) in currentMessages" :key="i" class="agent-msg-row" :class="msg.role">
              <template v-if="msg.role==='agent'&&msg.content">
                <div class="agent-msg-label">
                  <img :src="agentInfo.avatar" class="agent-msg-avatar" />
                  {{ agentInfo.name }}
                </div>
                <div class="agent-bubble agent theme-supervisor" v-html="renderMd(msg.content)"></div>
                <div v-if="i===0&&agentInfo.suggested?.length" class="agent-suggested">
                  <button v-for="s in agentInfo.suggested" :key="s" class="suggested-btn" :disabled="agentLoading" @click="agentInput=s;sendAgentMsg()">{{ s }}</button>
                </div>
              </template>
              <div v-else-if="msg.role==='user'" class="agent-bubble user">{{ msg.content }}</div>
            </div>
            <div v-if="agentLoading&&currentMessages[currentMessages.length-1]?.content===''" class="agent-msg-row agent">
              <div class="agent-bubble agent typing"><span></span><span></span><span></span></div>
            </div>
          </div>
          <!-- Input -->
          <div class="agent-input-area">
            <div v-if="agentPendingFiles.length" class="agent-file-chips">
              <span v-for="f in agentPendingFiles" :key="f.name" class="agent-file-chip">📎 {{ f.name }}</span>
            </div>
            <div class="agent-input-row">
              <button class="agent-attach-btn" @click="agentFileInput?.click()">＋</button>
              <textarea ref="agentTextareaEl" v-model="agentInput" class="agent-textarea"
                placeholder="질문하세요..." rows="1"
                @input="agentAutoResize" @keydown="onAgentKeydown" />
              <button class="agent-send-btn" :disabled="agentLoading||(!agentInput.trim()&&!agentPendingFiles.length)" @click="sendAgentMsg">전송</button>
            </div>
            <input ref="agentFileInput" type="file" multiple style="display:none" @change="onAgentFileSelected" />
          </div>
        </div>
      </Transition>

    <!-- ── Hover Tooltip ── -->
    <Teleport to="body">
      <Transition name="tooltip-fade">
        <div v-if="tooltipVisible&&hoverNode" class="node-tooltip"
          :style="{ left: tooltipPos.x+'px', top: tooltipPos.y+'px' }"
          @mouseenter="onTooltipEnter" @mouseleave="onTooltipLeave">
          <div class="tt-title">{{ hoverNode.label }}</div>
          <div class="tt-rows">
            <div class="tt-row"><span class="tt-label">회의수</span><span>{{ hoverNode.data?.minutes?.length||0 }}건</span></div>
            <div class="tt-row"><span class="tt-label">보고서</span><span>{{ hoverNode.data?.reports?.length||0 }}건</span></div>
            <div class="tt-row"><span class="tt-label">구성원</span><span>{{ hoverNode.data?.members?.length||0 }}명</span></div>
          </div>
          <button class="tt-detail-btn" @click="openDetail(hoverNode.data)">상세 보기 →</button>
          <button class="tt-edit-btn" @click="openNodeEdit(gNodes.indexOf(hoverNode))">✏ 편집</button>
        </div>
      </Transition>
    </Teleport>

    <!-- Float drag ghost cursor follow -->
    <Teleport to="body">
      <div v-if="floatDragging" class="float-drag-ghost"
        :style="{ left: (floatDragPos.x - 22) + 'px', top: (floatDragPos.y - 22) + 'px' }">
        <div class="ghost-node" :class="floatDragging === 'meeting' ? 'ghost-meeting' : 'ghost-doc'">
          <svg v-if="floatDragging==='meeting'" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24"><path d="M12 4v16m8-8H4"/></svg>
          <svg v-else width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12"/></svg>
        </div>
        <span class="ghost-label">{{ floatDragging==='meeting' ? '회의체 생성' : '자료 업로드' }}</span>
        <span v-if="floatDragPreviewLine" class="ghost-connect-hint">✓ 연결 가능</span>
      </div>
    </Teleport>

    <!-- ── Create Meeting Modal ── -->
    <Teleport to="body">
      <div v-if="showCreateModal" class="archive-modal-backdrop" @click.self="showCreateModal=false">
        <div class="archive-modal-box create-modal-box" :class="{ 'day-mode': !nightMode }">
          <div class="modal-header">
            <span class="modal-title">새 회의체 만들기</span>
            <button class="modal-close-btn" @click="showCreateModal=false">✕</button>
          </div>
          <div class="modal-body">
            <div class="modal-field"><label>회의체명 <span class="req">*</span></label><input v-model="createForm.title" class="modal-input" placeholder="예: 전략기획위원회" /></div>
            <div class="modal-field"><label>목적/설명</label><textarea v-model="createForm.purpose" class="modal-input modal-textarea" rows="2" placeholder="회의체의 목적을 입력하세요"></textarea></div>
            <div class="modal-field-row">
              <div class="modal-field"><label>시작일</label><input v-model="createForm.start_date" type="date" class="modal-input" /></div>
              <div class="modal-field"><label>종료일</label><input v-model="createForm.end_date" type="date" class="modal-input" /></div>
            </div>
            <div class="modal-field">
              <label>연관 회의체</label>
              <div class="related-meetings">
                <div v-for="m in meetingsStore.meetings" :key="m.id"
                  class="related-chip" :class="{ selected: relatedMeetingIds.includes(m.id) }"
                  @click="toggleRelated(m.id)">
                  <div class="related-dot" :style="{ background: relatedMeetingIds.includes(m.id)?'#60a5fa':'#475569' }"></div>
                  {{ m.title }}
                </div>
                <div v-if="!meetingsStore.meetings.length" style="font-size:12px;color:#64748b">현재 회의체가 없습니다</div>
              </div>
            </div>
            <div class="modal-field">
              <label>구성원 추가</label>
              <input v-model="memberSearch" class="modal-input" placeholder="이름 또는 이메일 검색..." @input="searchMembersFn" />
              <div v-if="memberSearchResults.length" class="modal-dropdown">
                <div v-for="u in memberSearchResults" :key="u.id" class="modal-dropdown-item" @click="addMember(u)">
                  <div class="modal-user-avatar">{{ (u.name||u.email)[0].toUpperCase() }}</div>
                  <div><div style="font-size:13px;font-weight:600">{{ u.name||'이름없음' }}</div><div style="font-size:11px;color:#64748b">{{ u.email }}</div></div>
                </div>
              </div>
              <div v-if="selectedMembers.length" class="selected-members">
                <div v-for="m in selectedMembers" :key="m.id" class="selected-member">
                  <div class="modal-user-avatar">{{ (m.name||m.email)[0].toUpperCase() }}</div>
                  <span>{{ m.name||m.email }}</span>
                  <select v-model="m.role" class="role-select-sm"><option value="admin">간사</option><option value="presenter">발제자</option><option value="member">위원</option></select>
                  <button class="remove-btn-sm" @click="removeMember(m)">×</button>
                </div>
              </div>
            </div>
            <div class="modal-field">
              <label>연결 노드 <span style="color:#94a3b8;font-weight:400;text-transform:none">— 은 그래프에 연결</span></label>
              <select v-model="createConnectNodeId" class="modal-input">
                <option value="">연결 안 함</option>
                <option v-for="n in connectableNodes" :key="n.id" :value="n.id">{{ n.typeLabel }}: {{ n.label }}</option>
              </select>
            </div>
            <div v-if="createConnectNodeId" class="modal-field">
              <label>관계 타입</label>
              <select v-model="createRelType" class="modal-input">
                <option v-for="rel in availableRels(createConnectNodeId)" :key="rel" :value="rel">{{ rel }}</option>
              </select>
              <div class="conn-preview">
                <span class="conn-node">{{ connectableNodes.find(n=>n.id===createConnectNodeId)?.label }}</span>
                <span class="conn-arrow">→</span>
                <span class="conn-rel" :style="{color: REL_COLORS[createRelType]||'#a78bfa'}">{{ createRelType }}</span>
                <span class="conn-arrow">→</span>
                <span class="conn-node">{{ createForm.title || '새 회의체' }}</span>
              </div>
            </div>
          </div>
          <div class="modal-footer">
            <button class="btn-cancel" @click="showCreateModal=false">취소</button>
            <button class="btn-confirm" :disabled="creating||!createForm.title.trim()" @click="doCreateMeeting">
              <span v-if="creating" class="spinner-border spinner-border-sm me-1"></span>
              {{ creating?'생성 중...':'회의체 만들기' }}
            </button>
          </div>
        </div>
      </div>
    </Teleport>

  </div><!-- /archive-page -->
  <!-- 자료 업로드 모달 -->
  <Teleport to="body">
    <div v-if="showUploadModal" class="archive-modal-backdrop" @click.self="showUploadModal=false">
      <div class="archive-modal-box upload-modal-box" :class="{ 'day-mode': !nightMode }">
        <div class="modal-header">
          <span class="modal-title">자료 노드 생성</span>
          <button class="modal-close" @click="showUploadModal=false"><svg width="14" height="14" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24"><path d="M6 18L18 6M6 6l12 12"/></svg></button>
        </div>
        <div class="modal-body">
          <div class="form-field">
            <label>파일 이름 <span class="req">*</span></label>
            <input v-model="uploadForm.label" class="form-input" placeholder="예: 2025년 1분기 전략보고서.pdf" />
          </div>
          <div class="form-field">
            <label>파일 유형</label>
            <div class="file-type-row">
              <button v-for="ft in FILE_TYPES" :key="ft"
                class="file-type-btn" :class="{ active: uploadForm.fileType===ft }"
                :style="uploadForm.fileType===ft ? { borderColor: ft==='회의록'?'#60a5fa':ft==='발제자료'?'#a78bfa':'#34d399', color: ft==='회의록'?'#60a5fa':ft==='발제자료'?'#a78bfa':'#34d399', background: ft==='회의록'?'rgba(96,165,250,.12)':ft==='발제자료'?'rgba(167,139,250,.12)':'rgba(52,211,153,.12)' } : {}"
                @click="uploadForm.fileType=ft">{{ ft }}</button>
            </div>
          </div>
          <div class="form-field">
            <label>연결할 노드 <span class="req">*</span></label>
            <select v-model="uploadForm.connectNodeId" class="form-input">
              <option value="">노드 선택...</option>
              <option v-for="n in connectableNodes" :key="n.id" :value="n.id">[{{ n.typeLabel }}] {{ n.label }}</option>
            </select>
          </div>
          <div v-if="uploadForm.connectNodeId" class="form-field">
            <label>관계 타입</label>
            <div class="rel-type-row">
              <button v-for="rel in availableRels(uploadForm.connectNodeId)" :key="rel"
                class="rel-type-btn" :class="{ active: uploadForm.relType===rel }"
                :style="uploadForm.relType===rel ? { borderColor: REL_COLORS[rel]||'#a78bfa', color: REL_COLORS[rel]||'#a78bfa', background: (REL_COLORS[rel]||'#a78bfa')+'22' } : {}"
                @click="uploadForm.relType=rel">{{ rel }}</button>
            </div>
          </div>
          <div v-if="uploadForm.connectNodeId && uploadForm.label" class="conn-preview-box">
            <span class="conn-node">{{ connectableNodes.find(n=>n.id===uploadForm.connectNodeId)?.label }}</span>
            <span class="conn-arrow">→</span>
            <span class="conn-rel" :style="{color:REL_COLORS[uploadForm.relType]||'#a78bfa'}">{{ uploadForm.relType }}</span>
            <span class="conn-arrow">→</span>
            <span class="conn-node file">{{ uploadForm.label }}</span>
            <span class="file-type-tag" :style="{color: uploadForm.fileType==='회의록'?'#60a5fa':uploadForm.fileType==='발제자료'?'#a78bfa':'#34d399'}">{{ uploadForm.fileType }}</span>
          </div>
        </div>
        <div class="modal-footer">
          <button class="btn-cancel" @click="showUploadModal=false">취소</button>
          <button class="btn-primary" :disabled="!uploadForm.label.trim()||!uploadForm.connectNodeId" @click="doAddFile">그래프에 추가</button>
        </div>
      </div>
    </div>
  </Teleport>
  <!-- 회의체 설정 모달 -->
  <Teleport to="body">
    <div v-if="settingsModal" class="archive-modal-backdrop" @click.self="closeSettings">
      <div class="archive-modal-box" :class="{ 'day-mode': !nightMode }">
        <div class="modal-header">
          <span class="modal-title">회의체 설정</span>
          <button class="modal-close" @click="closeSettings">
            <svg width="14" height="14" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24"><path d="M6 18L18 6M6 6l12 12"/></svg>
          </button>
        </div>
        <div class="modal-body settings-body">
          <div class="settings-section">
            <div class="settings-section-title">기본 정보</div>
            <div class="form-field">
              <label>회의체 이름 <span class="req">*</span></label>
              <input v-model="settingsModal.form.title" class="form-input" />
            </div>
            <div class="form-field">
              <label>소개</label>
              <textarea v-model="settingsModal.form.purpose" class="form-input form-textarea" rows="2" placeholder="이 회의체의 목적이나 소개..."></textarea>
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
                  <span class="sm-email">{{ mb.email }}</span>
                </div>
                <select v-model="mb.role" class="sm-role-select">
                  <option v-for="(label, val) in ROLE_MAP" :key="val" :value="val">{{ label }}</option>
                </select>
                <button class="sm-remove" @click="removeMemberFromSettings(idx)" title="제거">
                  <svg width="12" height="12" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24"><path d="M18 6L6 18M6 6l12 12"/></svg>
                </button>
              </div>
            </div>
          </div>
        </div>
        <div class="modal-footer">
          <button class="btn-cancel" @click="closeSettings">취소</button>
          <button class="btn-primary" :disabled="!settingsModal.form.title.trim() || savingSettings" @click="saveSettings">{{ savingSettings ? '저장 중...' : '저장' }}</button>
        </div>
      </div>
    </div>
  </Teleport>

  <!-- ── Node Edit Modal ── -->
  <Teleport to="body">
    <div v-if="nodeEditModal" class="archive-modal-backdrop" @click.self="closeNodeEdit">
      <div class="archive-modal-box node-edit-modal-box" :class="{ 'day-mode': !nightMode }">
        <div class="modal-header">
          <span class="modal-title">
            <span v-if="nodeEditModal.type==='org'">&#x1F3E2; 조직 편집</span>
            <span v-else-if="nodeEditModal.type==='dept'">&#x1F4CB; 부서 편집</span>
            <span v-else-if="nodeEditModal.type==='session'">&#x1F4C5; 회의 편집</span>
            <span v-else-if="nodeEditModal.type==='file'">&#x1F4C4; 파일 편집</span>
            <span v-else-if="nodeEditModal.type==='person'">&#x1F464; 구성원 편집</span>
          </span>
          <button class="modal-close-btn" @click="closeNodeEdit">✕</button>
        </div>
        <div class="modal-body">
          <!-- Org: name only -->
          <template v-if="nodeEditModal.type==='org'">
            <div class="modal-field">
              <label>조직명 <span class="req">*</span></label>
              <input v-model="nodeEditModal.form.label" class="modal-input" placeholder="조직명 입력" />
            </div>
          </template>

          <!-- Dept: name + member list -->
          <template v-if="nodeEditModal.type==='dept'">
            <div class="modal-field">
              <label>부서명 <span class="req">*</span></label>
              <input v-model="nodeEditModal.form.label" class="modal-input" placeholder="부서명 입력" />
            </div>
            <div class="modal-field">
              <div class="member-list-header">
                <label>구성원 <span style="color:#64748b;font-weight:400">({{ nodeEditModal.form.members.length }}명)</span></label>
                <button v-if="!showNewMemberForm" class="btn-add-member-open" @click="openNewMemberForm">+ 구성원 추가</button>
              </div>

              <!-- 구성원 추가 폼 -->
              <div v-if="showNewMemberForm" class="new-member-form">
                <div class="new-member-form-grid">
                  <div class="nmf-field">
                    <label class="nmf-label">이름 <span class="req">*</span></label>
                    <input v-model="newMemberForm.name" class="nmf-input" placeholder="홍길동" />
                  </div>
                  <div class="nmf-field">
                    <label class="nmf-label">직책/직급</label>
                    <input v-model="newMemberForm.position" class="nmf-input" placeholder="선임연구원" />
                  </div>
                  <div class="nmf-field">
                    <label class="nmf-label">이메일</label>
                    <input v-model="newMemberForm.email" class="nmf-input" placeholder="user@company.com" type="email" />
                  </div>
                  <div class="nmf-field">
                    <label class="nmf-label">연락처</label>
                    <input v-model="newMemberForm.phone" class="nmf-input" placeholder="010-0000-0000" />
                  </div>
                  <div class="nmf-field nmf-field-full">
                    <label class="nmf-label">역할</label>
                    <div class="nmf-role-row">
                      <label v-for="r in [{v:'admin',l:'간사'},{v:'presenter',l:'발제자'},{v:'member',l:'위원'}]" :key="r.v" class="nmf-radio">
                        <input type="radio" v-model="newMemberForm.role" :value="r.v" />
                        {{ r.l }}
                      </label>
                    </div>
                  </div>
                </div>
                <div class="nmf-actions">
                  <button class="btn-cancel" @click="cancelNewMemberForm">취소</button>
                  <button class="btn-confirm" :disabled="!newMemberForm.name.trim()" @click="addDeptMember">추가</button>
                </div>
              </div>

              <!-- 구성원 목록 -->
              <div class="node-edit-member-list">
                <div v-if="!nodeEditModal.form.members.length" class="node-edit-empty">구성원이 없습니다</div>
                <div v-for="(mb, idx) in nodeEditModal.form.members" :key="mb.userId" class="node-edit-member-row">
                  <div class="node-edit-avatar" :style="{background: avatarColor(mb.userName)}">{{ initials(mb.userName) }}</div>
                  <div class="node-edit-member-info">
                    <div class="node-edit-member-top">
                      <span class="node-edit-name">{{ mb.userName }}</span>
                      <span v-if="mb.position" class="node-edit-position">{{ mb.position }}</span>
                    </div>
                    <div class="node-edit-member-sub">
                      <span v-if="mb.email" class="node-edit-sub-text">{{ mb.email }}</span>
                      <span v-if="mb.phone" class="node-edit-sub-text">{{ mb.phone }}</span>
                    </div>
                  </div>
                  <select v-model="mb.role" class="role-select-sm">
                    <option value="admin">간사</option>
                    <option value="presenter">발제자</option>
                    <option value="member">위원</option>
                  </select>
                  <button class="remove-btn-sm" @click="removeDeptMember(idx)">×</button>
                </div>
              </div>
            </div>
          </template>

          <!-- Session: label only -->
          <template v-if="nodeEditModal.type==='session'">
            <div class="modal-field">
              <label>회의명 <span class="req">*</span></label>
              <input v-model="nodeEditModal.form.label" class="modal-input" placeholder="회의명 입력" />
            </div>
          </template>

          <!-- File: label + fileType -->
          <template v-if="nodeEditModal.type==='file'">
            <div class="modal-field">
              <label>파일명 <span class="req">*</span></label>
              <input v-model="nodeEditModal.form.label" class="modal-input" placeholder="파일명" />
            </div>
            <div class="modal-field">
              <label>파일 유형</label>
              <div class="file-type-row">
                <button v-for="ft in FILE_TYPES" :key="ft"
                  class="file-type-btn" :class="{ active: nodeEditModal.form.fileType===ft }"
                  :style="nodeEditModal.form.fileType===ft ? { borderColor: ft==='회의록'?'#60a5fa':ft==='발제자료'?'#a78bfa':'#34d399', color: ft==='회의록'?'#60a5fa':ft==='발제자료'?'#a78bfa':'#34d399', background: ft==='회의록'?'rgba(96,165,250,.12)':ft==='발제자료'?'rgba(167,139,250,.12)':'rgba(52,211,153,.12)' } : {}"
                  @click="nodeEditModal.form.fileType=ft">{{ ft }}</button>
              </div>
            </div>
          </template>

          <!-- Person: name + role -->
          <template v-if="nodeEditModal.type==='person'">
            <div class="modal-field">
              <label>이름 <span class="req">*</span></label>
              <input v-model="nodeEditModal.form.label" class="modal-input" placeholder="이름 입력" />
            </div>
            <div class="modal-field">
              <label>역할</label>
              <select v-model="nodeEditModal.form.role" class="modal-input">
                <option value="admin">간사</option>
                <option value="presenter">발제자</option>
                <option value="member">위원</option>
              </select>
            </div>
          </template>
        </div>
        <div class="modal-footer">
          <button class="btn-cancel" @click="closeNodeEdit">취소</button>
          <button class="btn-confirm" @click="saveNodeEdit">저장</button>
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
.view-toggle { display:flex;background:rgba(255,255,255,.06);border:1px solid rgba(255,255,255,.1);border-radius:8px;padding:2px;gap:2px;flex-shrink:0; }
.view-toggle button { display:flex;align-items:center;gap:5px;padding:5px 12px;border-radius:6px;border:none;background:none;color:#64748b;font-size:12px;font-weight:500;cursor:pointer;transition:all .15s; }
.view-toggle button.active { background:rgba(96,165,250,.2);color:#93c5fd; }
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
.detail-sidebar { position:absolute;top:0;left:0;bottom:0;z-index:20;background:#0a0f1e;border-right:1px solid rgba(255,255,255,.08);display:flex;flex-direction:column;overflow:hidden; }
.sidebar-resize-handle { position:absolute;top:0;right:0;bottom:0;width:5px;cursor:ew-resize;z-index:10;background:transparent;transition:background .15s; }
.sidebar-resize-handle:hover { background:rgba(96,165,250,.25); }
.sidebar-slide-enter-active,.sidebar-slide-leave-active { transition:transform .28s cubic-bezier(.22,.68,0,1.2),opacity .22s; }
.sidebar-slide-enter-from,.sidebar-slide-leave-to { transform:translateX(-100%);opacity:0; }
.detail-header { display:flex;align-items:flex-start;justify-content:space-between;padding:14px 12px 10px;border-bottom:1px solid rgba(255,255,255,.06);flex-shrink:0; }
.detail-meeting-name { font-size:13px;font-weight:700;color:#f1f5f9; }
.detail-meta { font-size:11px;color:#475569;margin-top:2px; }
.detail-close { background:none;border:none;cursor:pointer;color:#475569;font-size:14px;line-height:1;padding:2px;transition:color .15s; }
.detail-close:hover { color:#94a3b8; }
.detail-body { flex:1;overflow-y:auto;padding:10px 12px;display:flex;flex-direction:column;gap:10px; }
.detail-goto-btn { width:100%;padding:7px;border-radius:7px;border:1px solid rgba(96,165,250,.3);background:rgba(96,165,250,.08);color:#60a5fa;font-size:12px;font-weight:600;cursor:pointer; }
.detail-setting-btn { width:100%;display:flex;align-items:center;justify-content:center;gap:6px;padding:7px;border-radius:7px;border:1px solid rgba(148,163,184,.3);background:rgba(148,163,184,.08);color:#94a3b8;font-size:12px;font-weight:600;cursor:pointer;transition:all .15s; }
.detail-setting-btn:hover { border-color:rgba(96,165,250,.4);background:rgba(96,165,250,.1);color:#60a5fa; }

/* 회의체 설정 모달 */
.gsm-overlay { position:fixed;inset:0;background:rgba(0,0,0,.5);z-index:2000;display:flex;align-items:center;justify-content:center; }
.gsm-modal { background:#1e293b;border:1px solid #334155;border-radius:14px;width:420px;max-width:calc(100vw - 32px);display:flex;flex-direction:column;box-shadow:0 24px 60px rgba(0,0,0,.5); }
.gsm-header { display:flex;align-items:center;justify-content:space-between;padding:16px 20px;border-bottom:1px solid #334155; }
.gsm-title { font-size:15px;font-weight:700;color:#f1f5f9; }
.gsm-close { background:none;border:none;color:#64748b;font-size:16px;cursor:pointer;line-height:1;padding:2px 6px;border-radius:4px; }
.gsm-close:hover { color:#e2e8f0;background:#334155; }
.gsm-body { padding:20px;display:flex;flex-direction:column;gap:16px; }
.gsm-field { display:flex;flex-direction:column;gap:6px; }
.gsm-label { font-size:12px;font-weight:600;color:#94a3b8;text-transform:uppercase;letter-spacing:.04em; }
.gsm-input { padding:8px 12px;background:#0f172a;border:1px solid #334155;border-radius:8px;color:#e2e8f0;font-size:13px;outline:none; }
.gsm-input:focus { border-color:#3b82f6; }
.gsm-textarea { padding:8px 12px;background:#0f172a;border:1px solid #334155;border-radius:8px;color:#e2e8f0;font-size:13px;outline:none;resize:vertical;font-family:inherit; }
.gsm-textarea:focus { border-color:#3b82f6; }
.gsm-members { display:flex;flex-wrap:wrap;gap:6px; }
.gsm-member-chip { display:flex;align-items:center;gap:5px;background:#334155;border-radius:99px;padding:3px 10px 3px 5px;font-size:12px;color:#cbd5e1; }
.gsm-avatar { width:20px;height:20px;border-radius:50%;background:#1d4ed8;color:#fff;display:flex;align-items:center;justify-content:center;font-size:10px;font-weight:700; }
.gsm-empty { font-size:12px;color:#475569; }
.gsm-footer { display:flex;justify-content:flex-end;gap:8px;padding:14px 20px;border-top:1px solid #334155; }
.gsm-cancel { padding:7px 18px;border-radius:7px;border:1px solid #334155;background:none;color:#94a3b8;font-size:13px;cursor:pointer; }
.gsm-cancel:hover { background:#334155;color:#e2e8f0; }
.gsm-save { padding:7px 18px;border-radius:7px;border:none;background:#3b82f6;color:#fff;font-size:13px;font-weight:600;cursor:pointer; }
.gsm-save:hover { background:#2563eb; }
.detail-section { display:flex;flex-direction:column;gap:4px; }
.detail-section-label { font-size:10px;font-weight:700;color:#334155;text-transform:uppercase;letter-spacing:.06em;margin-bottom:2px; }
.detail-doc-item { display:flex;align-items:center;gap:7px;padding:5px 6px;border-radius:5px;background:rgba(255,255,255,.02);border:1px solid rgba(255,255,255,.04); }
.detail-doc-icon { width:22px;height:22px;border-radius:4px;display:flex;align-items:center;justify-content:center;flex-shrink:0; }
.detail-doc-icon.minutes { background:rgba(59,130,246,.2);color:#60a5fa; }
.detail-doc-icon.report { background:rgba(16,185,129,.2);color:#34d399; }
.detail-doc-info { flex:1;min-width:0; }
.detail-doc-name { font-size:11px;color:#cbd5e1;font-weight:500;overflow:hidden;text-overflow:ellipsis;white-space:nowrap; }
.detail-doc-date { font-size:10px;color:#334155; }
.detail-dept-table,.detail-member-table { width:100%;border-collapse:collapse;font-size:11px; }
.detail-dept-table td,.detail-member-table td { padding:3px 4px;border-bottom:1px solid rgba(255,255,255,.05);vertical-align:middle; }
.detail-dept-table tr:last-child td,.detail-member-table tr:last-child td { border-bottom:none; }
.dept-name { color:#cbd5e1;font-weight:500; }
.dept-count { color:#475569;text-align:right;white-space:nowrap; }
.mb-name { color:#cbd5e1;font-weight:500;width:35%; }
.mb-dept { color:#64748b;width:40%; }
.mb-role { color:#475569;text-align:right;white-space:nowrap; }
.detail-action-row { display:flex;gap:6px; }
.detail-action-btn { flex:1;display:flex;align-items:center;justify-content:center;gap:5px;padding:6px 8px;border-radius:6px;border:none;font-size:11px;font-weight:600;cursor:pointer;transition:all .15s; }
.task-action-btn { background:rgba(251,191,36,.12);color:#fbbf24;border:1px solid rgba(251,191,36,.25); }
.task-action-btn:hover { background:rgba(251,191,36,.22); }
.review-action-btn { background:rgba(52,211,153,.12);color:#34d399;border:1px solid rgba(52,211,153,.25); }
.review-action-btn:hover { background:rgba(52,211,153,.22); }

/* ── Main area ── */
.main-area { flex:1;position:relative;overflow:hidden;min-width:0; }
.archive-canvas { width:100%;height:100%;cursor:grab;display:block; }
.archive-canvas:active { cursor:grabbing; }
.graph-loading { width:100%;height:100%;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:12px;color:#475569;font-size:13px; }
.graph-loading-spinner { width:28px;height:28px;border:2px solid rgba(96,165,250,.2);border-top-color:#60a5fa;border-radius:50%;animation:spin .8s linear infinite; }
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
.list-view { position:absolute;inset:0;overflow-y:auto;background:#0a0f1e;display:flex;flex-direction:column; }
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
.agent-header-btn { width:42px;height:34px;border-radius:8px;border:1px solid rgba(255,255,255,.12);background:rgba(255,255,255,.06);display:flex;align-items:center;justify-content:center;cursor:pointer;flex-shrink:0;transition:all .15s;padding:0; }
.agent-header-btn:hover { background:rgba(123,128,204,.25);border-color:rgba(123,128,204,.5); }
.agent-header-btn.active { background:rgba(123,128,204,.3);border-color:#7b80cc;box-shadow:0 0 0 2px rgba(123,128,204,.2); }
.ai-btn-icon { width:36px;height:18px; }

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
.supervisor-badge { font-size:9px;font-weight:800;background:linear-gradient(135deg,#3b82f6,#10b981);color:#fff;border-radius:99px;padding:2px 6px;letter-spacing:.04em;flex-shrink:0; }
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
.agent-file-chips { display:flex;flex-wrap:wrap;gap:4px;margin-bottom:5px; }
.agent-file-chip { font-size:11px;background:#eff6ff;border:1px solid #bfdbfe;border-radius:4px;padding:2px 7px;color:#1d4ed8; }
.agent-input-area { padding:7px 9px;border-top:1px solid var(--border);flex-shrink:0; }
.agent-input-row { display:flex;align-items:flex-end;gap:4px; }
.agent-attach-btn { width:26px;height:26px;border-radius:50%;border:1px solid var(--border);background:#f8fafc;color:var(--text-muted);font-size:16px;line-height:1;cursor:pointer;display:flex;align-items:center;justify-content:center;flex-shrink:0; }
.agent-textarea { flex:1;resize:none;overflow:hidden;min-height:34px;border:1px solid var(--border);border-radius:7px;padding:6px 8px;font-size:12px;outline:none;font-family:inherit;line-height:1.5;box-sizing:border-box; }
.agent-textarea:focus { border-color:var(--primary); }
.agent-send-btn { padding:6px 12px;border-radius:7px;border:none;background:var(--primary);color:#fff;font-size:12px;font-weight:600;cursor:pointer;flex-shrink:0; }
.agent-send-btn:disabled { opacity:.4;cursor:not-allowed; }

/* ── Tooltip ── */
.node-tooltip { position:fixed;z-index:9000;background:#1e293b;border:1px solid rgba(255,255,255,.15);border-radius:12px;padding:12px 14px;min-width:170px;box-shadow:0 8px 28px rgba(0,0,0,.5); }
.tt-title { font-size:13px;font-weight:700;color:#f1f5f9;margin-bottom:7px; }
.tt-rows { display:flex;flex-direction:column;gap:3px;margin-bottom:9px; }
.tt-row { display:flex;align-items:center;justify-content:space-between;font-size:12px;color:#94a3b8; }
.tt-label { color:#475569; }
.tt-detail-btn { width:100%;padding:6px;border-radius:7px;border:1px solid rgba(96,165,250,.3);background:rgba(96,165,250,.1);color:#60a5fa;font-size:12px;font-weight:600;cursor:pointer; }
.tt-detail-btn:hover { background:rgba(96,165,250,.2); }
.tooltip-fade-enter-active,.tooltip-fade-leave-active { transition:opacity .12s,transform .12s; }
.tooltip-fade-enter-from,.tooltip-fade-leave-to { opacity:0;transform:scale(.95); }

/* ── Modal ── */
.modal-backdrop { position:fixed;inset:0;background:rgba(0,0,0,.5);display:flex;align-items:center;justify-content:center;z-index:1000; }
.modal-box { background:#fff;border-radius:16px;width:480px;max-width:92vw;max-height:88vh;overflow-y:auto;box-shadow:0 20px 60px rgba(0,0,0,.25); }
.modal-header { display:flex;align-items:center;justify-content:space-between;padding:18px 20px 12px;border-bottom:1px solid var(--border);position:sticky;top:0;background:#fff;z-index:1; }
.modal-title { font-size:15px;font-weight:700;color:#1e293b; }
.modal-close-btn { width:28px;height:28px;border-radius:6px;border:none;background:#f1f5f9;color:#64748b;cursor:pointer;font-size:14px;display:flex;align-items:center;justify-content:center; }
.modal-body { padding:16px 20px;display:flex;flex-direction:column;gap:12px; }
.modal-field { display:flex;flex-direction:column;gap:5px; }
.modal-field label { font-size:12px;font-weight:700;color:#475569; }
.req { color:#ef4444; }
.modal-input { padding:8px 10px;border:1px solid var(--border);border-radius:8px;font-size:13px;background:#f8fafc;outline:none;width:100%;box-sizing:border-box;font-family:inherit; }
.modal-input:focus { border-color:var(--primary); }
.modal-textarea { resize:none; }
.modal-field-row { display:grid;grid-template-columns:1fr 1fr;gap:12px; }
.modal-dropdown { border:1px solid var(--border);border-radius:8px;overflow:hidden;margin-top:4px; }
.modal-dropdown-item { display:flex;align-items:center;gap:8px;padding:8px 10px;cursor:pointer;transition:background .1s; }
.modal-dropdown-item:hover { background:#f1f5f9; }
.modal-user-avatar { width:26px;height:26px;border-radius:50%;background:var(--primary);color:#fff;font-size:11px;font-weight:700;display:flex;align-items:center;justify-content:center;flex-shrink:0; }
.selected-members { display:flex;flex-direction:column;gap:4px;margin-top:6px; }
.selected-member { display:flex;align-items:center;gap:7px;padding:5px 8px;background:#f8fafc;border:1px solid var(--border);border-radius:7px; }
.selected-member span { flex:1;font-size:13px; }
.role-select-sm { padding:3px 6px;border:1px solid var(--border);border-radius:5px;font-size:12px;background:#fff;outline:none; }
.remove-btn-sm { background:none;border:none;cursor:pointer;color:#94a3b8;font-size:16px;line-height:1;padding:0 2px; }
.related-meetings { display:flex;flex-wrap:wrap;gap:6px; }
.related-chip { display:flex;align-items:center;gap:5px;padding:4px 10px;border-radius:20px;border:1px solid rgba(255,255,255,.1);background:rgba(255,255,255,.04);color:#64748b;font-size:12px;cursor:pointer;transition:all .15s;background:#f8fafc;border-color:var(--border); }
.related-chip:hover { border-color:#60a5fa;color:#3b82f6; }
.related-chip.selected { background:#eff6ff;border-color:#93c5fd;color:#1d4ed8; }
.related-dot { width:6px;height:6px;border-radius:50%;flex-shrink:0; }
.modal-footer { display:flex;gap:8px;justify-content:flex-end;padding:12px 20px 16px;border-top:1px solid var(--border);position:sticky;bottom:0;background:#fff; }
.btn-cancel { padding:8px 16px;border-radius:8px;border:1px solid var(--border);background:#fff;font-size:13px;font-weight:600;cursor:pointer;color:#64748b; }
.btn-confirm { padding:8px 20px;border-radius:8px;border:none;background:var(--primary);color:#fff;font-size:13px;font-weight:700;cursor:pointer;transition:opacity .15s; }
.btn-confirm:disabled { opacity:.5;cursor:not-allowed; }

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
.day-mode .archive-header { background:#eef2ff;border-bottom-color:#e2e8f0; }
.day-mode .archive-title { color:#1e293b; }
.day-mode .archive-desc { color:#94a3b8; }
.day-mode .search-input { background:#fff;border-color:#e2e8f0;color:#1e293b; }
.day-mode .search-input::placeholder { color:#94a3b8; }
.day-mode .search-input:focus { border-color:#3b82f6; }
.day-mode .search-clear { color:#94a3b8; }
.day-mode .view-toggle { background:#fff;border-color:#e2e8f0; }
.day-mode .view-toggle button { color:#94a3b8; }
.day-mode .view-toggle button.active { background:#eff6ff;color:#2563eb; }
.day-mode .plus-snackbar { background:#fff;border-color:#e2e8f0;box-shadow:0 8px 24px rgba(0,0,0,.1); }
.day-mode .snack-btn { color:#475569; }
.day-mode .snack-btn:hover { background:#f1f5f9;color:#1e293b; }
.day-mode .snack-divider { background:#e2e8f0; }
.day-mode .detail-sidebar { background:#f8fafc;border-right-color:#e2e8f0; }
.day-mode .detail-meeting-name { color:#1e293b; }
.day-mode .detail-meta { color:#94a3b8; }
.day-mode .detail-close { color:#94a3b8; }
.day-mode .detail-section-label { color:#94a3b8; }
.day-mode .detail-doc-item { background:#fff;border-color:#e2e8f0; }
.day-mode .detail-doc-name { color:#334155; }
.day-mode .detail-doc-date { color:#94a3b8; }
.day-mode .detail-dept-table td,.day-mode .detail-member-table td { border-bottom-color:#e2e8f0; }
.day-mode .dept-name,.day-mode .mb-name { color:#1e293b; }
.day-mode .dept-count,.day-mode .mb-dept,.day-mode .mb-role { color:#94a3b8; }
.day-mode .person-toggle { color:#64748b; }
.day-mode .legend-hint { color:#94a3b8; }
.day-mode .list-view { background:#f8fafc; }
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
</style>

<!-- Teleport(body) 대상 모달은 scoped CSS가 적용되지 않으므로 별도 전역 스타일 블록 사용 -->
<style>
.archive-modal-backdrop { position:fixed;inset:0;background:rgba(0,0,0,.5);display:flex;align-items:center;justify-content:center;z-index:2000; }
.archive-modal-box { background:#1e293b;border-radius:14px;width:520px;max-width:92vw;box-shadow:0 24px 64px rgba(0,0,0,.4);border:1px solid rgba(255,255,255,.1); }
.create-modal-box { width:480px;max-height:88vh;overflow-y:auto; }
/* create modal inner styles */
.archive-modal-box .modal-field { display:flex;flex-direction:column;gap:5px;margin-bottom:4px; }
.archive-modal-box .modal-field label { font-size:12px;font-weight:700;color:#64748b; }
.archive-modal-box .modal-input { padding:8px 10px;border:1px solid rgba(255,255,255,.12);border-radius:8px;font-size:13px;background:rgba(255,255,255,.06);color:#f1f5f9;outline:none;width:100%;box-sizing:border-box;font-family:inherit; }
.archive-modal-box .modal-input:focus { border-color:rgba(96,165,250,.5); }
.archive-modal-box .modal-textarea { resize:none; }
.archive-modal-box .modal-field-row { display:grid;grid-template-columns:1fr 1fr;gap:12px; }
.archive-modal-box .modal-dropdown { border:1px solid rgba(255,255,255,.1);border-radius:8px;overflow:hidden;margin-top:4px; }
.archive-modal-box .modal-dropdown-item { display:flex;align-items:center;gap:8px;padding:8px 10px;cursor:pointer;transition:background .1s;color:#e2e8f0; }
.archive-modal-box .modal-dropdown-item:hover { background:rgba(255,255,255,.06); }
.archive-modal-box .modal-user-avatar { width:26px;height:26px;border-radius:50%;background:#3b82f6;color:#fff;font-size:11px;font-weight:700;display:flex;align-items:center;justify-content:center;flex-shrink:0; }
.archive-modal-box .selected-member { display:flex;align-items:center;gap:7px;padding:5px 8px;background:rgba(255,255,255,.06);border:1px solid rgba(255,255,255,.1);border-radius:7px; }
.archive-modal-box .selected-member span { flex:1;font-size:13px;color:#e2e8f0; }
.archive-modal-box .role-select-sm { padding:3px 6px;border:1px solid rgba(255,255,255,.12);border-radius:5px;font-size:12px;background:rgba(255,255,255,.08);color:#e2e8f0;outline:none; }
.archive-modal-box .remove-btn-sm { background:none;border:none;cursor:pointer;color:#94a3b8;font-size:16px;line-height:1;padding:0 2px; }
.archive-modal-box .related-meetings { display:flex;flex-wrap:wrap;gap:6px; }
.archive-modal-box .related-chip { display:flex;align-items:center;gap:5px;padding:4px 10px;border-radius:20px;border:1px solid rgba(255,255,255,.1);background:rgba(255,255,255,.04);color:#64748b;font-size:12px;cursor:pointer;transition:all .15s; }
.archive-modal-box .related-chip:hover { border-color:#60a5fa;color:#3b82f6; }
.archive-modal-box .related-chip.selected { background:rgba(59,130,246,.15);border-color:#93c5fd;color:#60a5fa; }
.archive-modal-box .related-dot { width:6px;height:6px;border-radius:50%;flex-shrink:0; }
.archive-modal-box .modal-close-btn { background:rgba(255,255,255,.07);border:none;border-radius:7px;width:28px;height:28px;color:#64748b;cursor:pointer;font-size:16px;line-height:1;display:flex;align-items:center;justify-content:center; }
.archive-modal-box .modal-close-btn:hover { background:rgba(255,255,255,.12);color:#94a3b8; }
.archive-modal-box .btn-confirm { padding:8px 20px;border-radius:8px;border:none;background:#1e3a5f;color:#fff;font-size:13px;font-weight:700;cursor:pointer;transition:opacity .15s; }
.archive-modal-box .btn-confirm:disabled { opacity:.5;cursor:not-allowed; }
/* day-mode create-modal */
.archive-modal-box.day-mode .modal-input { background:#f8fafc;border-color:#e2e8f0;color:#1e293b; }
.archive-modal-box.day-mode .modal-dropdown-item { color:#1e293b; }
.archive-modal-box.day-mode .modal-dropdown-item:hover { background:#f8fafc; }
.archive-modal-box.day-mode .selected-member { background:#f8fafc;border-color:#e2e8f0; }
.archive-modal-box.day-mode .selected-member span { color:#1e293b; }
.archive-modal-box.day-mode .role-select-sm { background:#fff;border-color:#e2e8f0;color:#475569; }
.archive-modal-box.day-mode .related-chip { border-color:#e2e8f0;background:#fff;color:#64748b; }
.archive-modal-box.day-mode .related-chip.selected { background:#eff6ff;border-color:#93c5fd;color:#1d4ed8; }
.archive-modal-box.day-mode .modal-close-btn { background:#f1f5f9;color:#64748b; }
.archive-modal-box.day-mode .btn-confirm { background:#1e3a5f; }
.archive-modal-box .modal-header { display:flex;align-items:center;justify-content:space-between;padding:16px 20px 12px;border-bottom:1px solid rgba(255,255,255,.08); }
.archive-modal-box .modal-title { font-size:15px;font-weight:700;color:#f1f5f9; }
.archive-modal-box .modal-close { width:28px;height:28px;border-radius:7px;border:none;background:rgba(255,255,255,.07);color:#64748b;display:flex;align-items:center;justify-content:center;cursor:pointer;transition:all .15s; }
.archive-modal-box .modal-close:hover { background:rgba(255,255,255,.12);color:#94a3b8; }
.archive-modal-box .modal-body { padding:16px 20px;display:flex;flex-direction:column;gap:12px;max-height:70vh;overflow-y:auto; }
.archive-modal-box .modal-footer { display:flex;gap:8px;justify-content:flex-end;padding:12px 20px 16px;border-top:1px solid rgba(255,255,255,.08);background:inherit; }
.archive-modal-box .form-field { display:flex;flex-direction:column;gap:5px; }
.archive-modal-box .form-field label { font-size:12px;font-weight:600;color:#64748b;text-transform:uppercase;letter-spacing:.04em; }
.archive-modal-box .req { color:#ef4444; }
.archive-modal-box .form-input { padding:8px 10px;border:1px solid rgba(255,255,255,.12);border-radius:8px;font-size:13px;background:rgba(255,255,255,.06);color:#f1f5f9;outline:none;font-family:inherit;width:100%;box-sizing:border-box; }
.archive-modal-box .form-input:focus { border-color:rgba(96,165,250,.5); }
.archive-modal-box .form-textarea { resize:vertical;min-height:64px; }
.archive-modal-box .btn-cancel { padding:8px 16px;border-radius:8px;border:1px solid rgba(255,255,255,.12);background:rgba(255,255,255,.06);font-size:13px;font-weight:600;cursor:pointer;color:#94a3b8;transition:all .15s; }
.archive-modal-box .btn-cancel:hover { background:rgba(255,255,255,.1); }
.archive-modal-box .btn-primary { padding:8px 20px;border-radius:8px;border:none;background:#3b82f6;color:#fff;font-size:13px;font-weight:700;cursor:pointer;transition:opacity .15s; }
.archive-modal-box .btn-primary:hover { opacity:.85; }
.archive-modal-box .btn-primary:disabled { opacity:.4;cursor:not-allowed; }
.archive-modal-box .settings-section { padding:14px 0;border-bottom:1px solid rgba(255,255,255,.07);display:flex;flex-direction:column;gap:10px; }
.archive-modal-box .settings-section:last-child { border-bottom:none;padding-bottom:0; }
.archive-modal-box .settings-section-title { font-size:12px;font-weight:700;color:#475569;text-transform:uppercase;letter-spacing:.05em;display:flex;align-items:center;gap:8px; }
.archive-modal-box .member-cnt-badge { font-size:11px;font-weight:600;background:rgba(255,255,255,.08);border-radius:99px;padding:1px 7px;color:#64748b; }
.archive-modal-box .member-search-wrap { display:flex;align-items:center;gap:7px;padding:7px 10px;border:1px solid rgba(255,255,255,.1);border-radius:8px;background:rgba(255,255,255,.04); }
.archive-modal-box .member-search-input { flex:1;border:none;background:none;color:#e2e8f0;font-size:13px;outline:none; }
.archive-modal-box .member-search-input::placeholder { color:#475569; }
.archive-modal-box .search-spinner { color:#64748b;font-size:14px;animation:archive-spin .8s linear infinite;display:inline-block; }
@keyframes archive-spin { to { transform:rotate(360deg); } }
.archive-modal-box .settings-body { gap:0; }
.archive-modal-box .member-search-results { border:1px solid rgba(255,255,255,.1);border-radius:8px;overflow:hidden;max-height:140px;overflow-y:auto; }
.archive-modal-box .member-search-item { display:flex;align-items:center;gap:8px;padding:8px 10px;cursor:pointer;transition:background .1s; }
.archive-modal-box .member-search-item:hover { background:rgba(255,255,255,.06); }
.archive-modal-box .ms-avatar { width:26px;height:26px;border-radius:50%;color:#fff;font-size:11px;font-weight:700;display:flex;align-items:center;justify-content:center;flex-shrink:0; }
.archive-modal-box .ms-info { flex:1;display:flex;flex-direction:column;gap:1px;min-width:0; }
.archive-modal-box .ms-name { font-size:12px;font-weight:600;color:#e2e8f0; }
.archive-modal-box .ms-email { font-size:11px;color:#475569; }
.archive-modal-box .ms-add-hint { font-size:11px;color:#3b82f6;font-weight:600;flex-shrink:0; }
.archive-modal-box .settings-member-list { display:flex;flex-direction:column;gap:4px;max-height:180px;overflow-y:auto; }
.archive-modal-box .settings-empty-members { font-size:12px;color:#475569;padding:6px 2px; }
.archive-modal-box .settings-member-row { display:flex;align-items:center;gap:8px;padding:5px 4px;border-radius:7px;transition:background .1s; }
.archive-modal-box .settings-member-row:hover { background:rgba(255,255,255,.04); }
.archive-modal-box .sm-avatar { width:26px;height:26px;border-radius:50%;color:#fff;font-size:11px;font-weight:700;display:flex;align-items:center;justify-content:center;flex-shrink:0; }
.archive-modal-box .sm-info { flex:1;display:flex;flex-direction:column;gap:1px;min-width:0; }
.archive-modal-box .sm-name { font-size:12px;font-weight:600;color:#e2e8f0; }
.archive-modal-box .sm-email { font-size:11px;color:#475569; }
.archive-modal-box .sm-role-select { font-size:11px;background:rgba(255,255,255,.06);border:1px solid rgba(255,255,255,.1);border-radius:5px;color:#94a3b8;padding:2px 5px;cursor:pointer;flex-shrink:0; }
.archive-modal-box .sm-remove { width:22px;height:22px;border-radius:5px;border:none;background:rgba(239,68,68,.1);color:#f87171;display:flex;align-items:center;justify-content:center;cursor:pointer;transition:all .15s;flex-shrink:0; }
.archive-modal-box .sm-remove:hover { background:rgba(239,68,68,.2); }
/* 주간 모드 */
.archive-modal-box.day-mode { background:#fff !important;border-color:#e2e8f0; }
.archive-modal-box.day-mode .modal-header { border-bottom-color:#e2e8f0; }
.archive-modal-box.day-mode .modal-title { color:#1e293b; }
.archive-modal-box.day-mode .modal-close { background:#f1f5f9;color:#64748b; }
.archive-modal-box.day-mode .modal-footer { border-top-color:#e2e8f0; }
.archive-modal-box.day-mode .form-field label { color:#64748b; }
.archive-modal-box.day-mode .form-input { background:#f8fafc;border-color:#e2e8f0;color:#1e293b; }
.archive-modal-box.day-mode .form-input:focus { border-color:#3b82f6;background:#fff; }
.archive-modal-box.day-mode .settings-section { border-bottom-color:#f1f5f9; }
.archive-modal-box.day-mode .settings-section-title { color:#94a3b8; }
.archive-modal-box.day-mode .member-search-wrap { background:#f8fafc;border-color:#e2e8f0; }
.archive-modal-box.day-mode .member-search-input { color:#1e293b; }
.archive-modal-box.day-mode .member-search-results { border-color:#e2e8f0; }
.archive-modal-box.day-mode .member-search-item:hover { background:#f8fafc; }
.archive-modal-box.day-mode .ms-name { color:#1e293b; }
.archive-modal-box.day-mode .settings-member-row:hover { background:#f8fafc; }
.archive-modal-box.day-mode .sm-name { color:#1e293b; }
.archive-modal-box.day-mode .sm-role-select { background:#f1f5f9;border-color:#e2e8f0;color:#475569; }
.archive-modal-box.day-mode .btn-cancel { border-color:#e2e8f0;background:#f8fafc;color:#475569; }
.archive-modal-box.day-mode .btn-cancel:hover { background:#f1f5f9; }
/* 업로드 모달 */
.upload-modal-box { width:480px; }
.file-type-row,.rel-type-row { display:flex;flex-wrap:wrap;gap:6px; }
.file-type-btn,.rel-type-btn { padding:5px 14px;border-radius:20px;border:1px solid rgba(255,255,255,.12);background:rgba(255,255,255,.05);color:#64748b;font-size:12px;cursor:pointer;transition:all .15s; }
.file-type-btn:hover,.rel-type-btn:hover { border-color:#60a5fa;color:#60a5fa;background:rgba(96,165,250,.08); }
.file-type-btn.active,.rel-type-btn.active { font-weight:600; }
/* 연결 프리뷰 */
.conn-preview { display:flex;align-items:center;gap:6px;margin-top:8px;padding:7px 10px;border-radius:8px;background:rgba(255,255,255,.04);border:1px solid rgba(255,255,255,.07);flex-wrap:wrap; }
.conn-preview-box { display:flex;align-items:center;gap:6px;padding:9px 12px;border-radius:8px;background:rgba(255,255,255,.04);border:1px solid rgba(255,255,255,.07);flex-wrap:wrap;margin-top:4px; }
.conn-node { font-size:12px;font-weight:600;color:#e2e8f0;padding:2px 8px;border-radius:5px;background:rgba(255,255,255,.07); }
.conn-node.file { color:#f1f5f9; }
.conn-arrow { font-size:14px;color:#475569; }
.conn-rel { font-size:11px;font-weight:700;padding:2px 7px;border-radius:4px;background:rgba(255,255,255,.06); }
.file-type-tag { font-size:10px;font-weight:700;color:#94a3b8;margin-left:2px; }
/* day-mode upload */
.archive-modal-box.day-mode .file-type-btn,.archive-modal-box.day-mode .rel-type-btn { border-color:#e2e8f0;color:#64748b;background:#f8fafc; }
.archive-modal-box.day-mode .conn-preview,.archive-modal-box.day-mode .conn-preview-box { background:#f8fafc;border-color:#e2e8f0; }
.archive-modal-box.day-mode .conn-node { color:#1e293b;background:#f1f5f9; }
/* 온톨로지 범례 */
.graph-legend-onto { position:absolute;bottom:12px;left:12px;z-index:15;display:flex;flex-direction:column;gap:5px;background:rgba(15,23,42,.82);border:1px solid rgba(255,255,255,.1);border-radius:8px;padding:8px 12px;pointer-events:none; }
.legend-onto-item { display:flex;align-items:center;gap:6px;font-size:10px;color:#94a3b8; }
.legend-onto-dot { width:9px;height:9px;border-radius:50%;flex-shrink:0; }
.legend-onto-dash { width:18px;height:2px;flex-shrink:0; }
.day-mode .graph-legend-onto { background:rgba(238,242,255,.88);border-color:#e2e8f0;color:#64748b; }
.day-mode .conn-preview,.day-mode .conn-preview-box { background:#f0f4f8;border-color:#e2e8f0; }
.day-mode .legend-onto-item { color:#64748b; }
/* 툴팁 편집 버튼 */
.tt-edit-btn { margin-top:6px;width:100%;padding:5px 0;border-radius:6px;border:1px solid rgba(255,255,255,.12);background:rgba(255,255,255,.05);color:#94a3b8;font-size:11px;cursor:pointer;transition:all .15s; }
.tt-edit-btn:hover { background:rgba(96,165,250,.15);border-color:#60a5fa;color:#93c5fd; }
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
.nmf-field-full { grid-column:1/-1; }
.nmf-label { font-size:11px;color:#94a3b8;font-weight:500; }
.nmf-input { background:rgba(255,255,255,.06);border:1px solid rgba(255,255,255,.12);border-radius:7px;padding:6px 10px;font-size:12px;color:#e2e8f0;outline:none;width:100%;box-sizing:border-box; }
.nmf-input:focus { border-color:rgba(96,165,250,.5); }
.nmf-input::placeholder { color:#334155; }
.nmf-role-row { display:flex;gap:14px; }
.nmf-radio { display:flex;align-items:center;gap:5px;font-size:12px;color:#94a3b8;cursor:pointer; }
.nmf-radio input { accent-color:#3b82f6; }
.nmf-actions { display:flex;justify-content:flex-end;gap:6px; }
/* member list rows - richer */
.node-edit-member-list { display:flex;flex-direction:column;gap:4px;max-height:200px;overflow-y:auto;padding:2px 0; }
.node-edit-empty { font-size:12px;color:#64748b;padding:6px 0; }
.node-edit-member-row { display:flex;align-items:center;gap:7px;padding:6px 8px;border-radius:7px;background:rgba(255,255,255,.04); }
.node-edit-avatar { width:28px;height:28px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:11px;font-weight:700;color:#fff;flex-shrink:0; }
.node-edit-member-info { flex:1;min-width:0; }
.node-edit-member-top { display:flex;align-items:center;gap:6px; }
.node-edit-name { font-size:12px;font-weight:600;color:#e2e8f0; }
.node-edit-position { font-size:10px;color:#64748b;background:rgba(255,255,255,.06);border-radius:4px;padding:1px 6px; }
.node-edit-member-sub { display:flex;gap:8px;margin-top:1px; }
.node-edit-sub-text { font-size:10px;color:#475569; }
.node-edit-add-member { display:flex;align-items:center;gap:6px;margin-top:6px; }
.btn-add-member { padding:6px 14px;border-radius:7px;border:none;background:#3b82f6;color:#fff;font-size:12px;font-weight:600;cursor:pointer;white-space:nowrap; }
.btn-add-member:hover { background:#2563eb; }
/* day-mode */
.archive-modal-box.day-mode .new-member-form { background:#f8fafc;border-color:#e2e8f0; }
.archive-modal-box.day-mode .nmf-input { background:#fff;border-color:#e2e8f0;color:#1e293b; }
.archive-modal-box.day-mode .nmf-input::placeholder { color:#94a3b8; }
.archive-modal-box.day-mode .nmf-label { color:#64748b; }
.archive-modal-box.day-mode .nmf-radio { color:#64748b; }
.archive-modal-box.day-mode .node-edit-member-row { background:#f1f5f9; }
.archive-modal-box.day-mode .node-edit-name { color:#1e293b; }
.archive-modal-box.day-mode .node-edit-empty { color:#94a3b8; }
.archive-modal-box.day-mode .btn-add-member-open { border-color:#93c5fd;color:#3b82f6;background:rgba(59,130,246,.06); }
</style>
