<script setup>
import { ref, computed, onMounted, onBeforeUnmount, watch, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import api from '../api'
import { streamPost } from '../api'
import { renderMd } from '../composables/useMarkdown'
import { useMeetingsStore } from '../stores/meetings'
import { useAuthStore } from '../stores/auth'
import hyeanAvatar from '../assets/agents/hyean.png'
import gaonAvatar from '../assets/agents/gaon.png'
import naruAvatar from '../assets/agents/naru.png'

const router = useRouter()
const meetingsStore = useMeetingsStore()
const authStore = useAuthStore()

// ─── Data ─────────────────────────────────────────────────────
const minutes = ref([])
const reports = ref([])
const membersData = ref([])
const loading = ref(true)
const search = ref('')
const showPersonNodes = ref(true)
const expandedMeeting = ref(null)

// ─── View mode ────────────────────────────────────────────────
const viewMode = ref('graph')
const nightMode = ref(true)

// ─── Plus snackbar ────────────────────────────────────────────
const plusOpen = ref(false)
function closePlus() { plusOpen.value = false }

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

function openCreateModal() { showCreateModal.value = true; agentOpen.value = false; closePlus() }

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
  } finally { creating.value = false }
}

// ─── Agents ───────────────────────────────────────────────────
const AGENTS = {
  hyean: {
    name: '혜안', nameEn: 'Hyean', subtitle: '회의체 운영 AI 비서', avatar: hyeanAvatar,
    accentColor: '#1d4ed8', accentBg: '#eff6ff', accentBorder: '#93c5fd',
    greeting: '안녕하세요! 저는 혜안이에요 😊\n아카이브에서 회의체 현황을 분석하거나 필요한 정보를 찾아드릴게요.',
    suggested: ['이 아카이브에서 가장 활발한 회의체는?', '최근 회의록 요약해줘', '회의체 간 연관 관계 분석해줘'],
    endpoint: '/api/agent/hyean/chat',
  },
  gaon: {
    name: '가온', nameEn: 'Gaon', subtitle: 'To-do 추출·아젠다 어시스턴트', avatar: gaonAvatar,
    accentColor: '#92400e', accentBg: '#fef3c7', accentBorder: '#fcd34d',
    greeting: '안녕하세요! 저는 가온이에요 😊\n회의 준비자료나 보고서, 이전 회의록 같은 거 업로드해주시면 아젠다랑 To-do 뽑아드릴게요. 파일 드래그해서 올려주시거나 아래 질문 눌러보세요!',
    suggested: ['회의록에서 과제를 추출해줘', '담당자별 할 일을 정리해줘', '이번 회의 아젠다를 만들어줘'],
    endpoint: '/api/agent/gaon/chat',
  },
  naru: {
    name: '나루', nameEn: 'Naru', subtitle: '자료 검토 어시스턴트', avatar: naruAvatar,
    accentColor: '#065f46', accentBg: '#ecfdf5', accentBorder: '#6ee7b7',
    greeting: '안녕하세요! 저는 나루예요 😊\n검토할 자료를 업로드하면 AI가 꼼꼼하게 검토해드릴게요.',
    suggested: ['이 보고서의 핵심 내용을 요약해줘', '자료에서 문제점을 찾아줘', '개선 방향을 제안해줘'],
    endpoint: '/api/agent/naru/chat',
  },
}

const agentOpen = ref(true)
const currentAgent = ref('hyean')
const agentInfo = computed(() => AGENTS[currentAgent.value])
const allMessages = ref({ hyean: [], gaon: [], naru: [] })
const currentMessages = computed(() => allMessages.value[currentAgent.value])
const agentInput = ref('')
const agentLoading = ref(false)
const agentMessagesEl = ref(null)
const agentFileInput = ref(null)
const agentPendingFiles = ref([])
const agentTextareaEl = ref(null)

// Agent panel resize + drag-to-move
const panelW = ref(360)
const panelH = ref(440)
let agentResizing = false, arStartX = 0, arStartY = 0, arStartW = 0, arStartH = 0
let agentBottomResizing = false, abStartY = 0, abStartH = 0
let agentDragging = false, adStartX = 0, adStartY = 0, adStartLeft = 0, adStartTop = 0

const floatingWrapRef = ref(null)
const agentPos = ref({ top: 60, left: null })  // left: null = use right:12

function onAgentResizeStart(e) {
  agentResizing = true
  arStartX = e.clientX; arStartY = e.clientY
  arStartW = panelW.value; arStartH = panelH.value
  e.preventDefault(); e.stopPropagation()
}

function onAgentBottomResizeStart(e) {
  agentBottomResizing = true
  abStartY = e.clientY; abStartH = panelH.value
  e.preventDefault(); e.stopPropagation()
}

function onAgentDragStart(e) {
  if (e.target.closest('.agent-header-actions') || e.target.closest('.agent-resize-handle') || agentResizing) return
  agentDragging = true
  const el = floatingWrapRef.value
  if (el && el.parentElement) {
    const rect = el.getBoundingClientRect()
    const parentRect = el.parentElement.getBoundingClientRect()
    adStartLeft = rect.left - parentRect.left
    adStartTop = rect.top - parentRect.top
    agentPos.value = { top: adStartTop, left: adStartLeft }
  }
  adStartX = e.clientX; adStartY = e.clientY
  e.preventDefault()
}

// Auto-shrink when bottom panel is open
const effectivePanelH = computed(() => {
  if (bottomMode.value) return Math.min(panelH.value, 220)
  return panelH.value
})

function initAgentGreeting(key) {
  if (!allMessages.value[key].length)
    allMessages.value[key] = [{ role: 'agent', content: AGENTS[key].greeting }]
}

function switchAgent(key) {
  currentAgent.value = key; agentOpen.value = true
  initAgentGreeting(key)
}

function clearAgentChat() {
  allMessages.value[currentAgent.value] = [{ role: 'agent', content: agentInfo.value.greeting }]
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
  const key = currentAgent.value
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
  bottomMode.value = 'task'; switchAgent('gaon'); closePlus()
  nextTick(initBottomH)
}
function activateReviewMode() {
  bottomMode.value = 'review'; switchAgent('naru'); closePlus()
  nextTick(initBottomH)
}
function closeBottomPanel() { bottomMode.value = null; currentAgent.value = 'hyean' }

// ─── Global mouse handler (resize) ─────────────────────────────
function onGlobalMouseMove(e) {
  if (agentResizing) {
    panelW.value = Math.min(600, Math.max(260, arStartW + (arStartX - e.clientX)))
    panelH.value = Math.min(680, Math.max(200, arStartH + (arStartY - e.clientY)))
  }
  if (agentBottomResizing) {
    panelH.value = Math.min(680, Math.max(200, abStartH + (e.clientY - abStartY)))
  }
  if (agentDragging) {
    const el = floatingWrapRef.value
    const parent = el?.parentElement
    const maxL = parent ? parent.offsetWidth - 10 : 1200
    const maxT = parent ? parent.offsetHeight - 10 : 800
    agentPos.value = {
      top: Math.max(0, Math.min(maxT, adStartTop + (e.clientY - adStartY))),
      left: Math.max(0, Math.min(maxL, adStartLeft + (e.clientX - adStartX))),
    }
  }
  if (bottomResizing) {
    const el = mainAreaRef.value
    const maxH = el ? el.offsetHeight * 0.82 : 600
    bottomH.value = Math.max(90, Math.min(maxH, brStartH + (brStartY - e.clientY)))
  }
}
function onGlobalMouseUp() { agentResizing = false; agentBottomResizing = false; agentDragging = false; bottomResizing = false }

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
let autoRotate = true, focusNode = null
const selectedNodeIdx = ref(null)
let targetCamX = 0, targetCamY = 0, targetCamZ = 0
let camX = 0, camY = 0, camZ = 0
let worldZoom = 1.0, targetZoom = 1.0, dpr = 1
let gNodes = [], gEdges = []

// Demo data used when no real data available
function getDemoData() {
  return [
    { id: 1, title: '전략기획위원회', minutes: [{ session_title: '2025 전략 수립', session_number: 1 }, { session_title: '예산 계획 검토', session_number: 2 }], reports: [{ file_name: '전략보고서_Q1.pdf' }], members: [{ userId: 1, userName: '김철수', role: 'admin' }, { userId: 2, userName: '이영희', role: 'presenter' }, { userId: 3, userName: '박민준', role: 'presenter' }] },
    { id: 2, title: '운영위원회', minutes: [{ session_title: '운영 현황 보고', session_number: 1 }], reports: [{ file_name: '운영보고서_5월.pdf' }, { file_name: '성과보고서.pdf' }], members: [{ userId: 4, userName: '최지영', role: 'admin' }, { userId: 2, userName: '이영희', role: 'presenter' }] },
    { id: 3, title: '개발팀 주간회의', minutes: [{ session_title: '스프린트 계획', session_number: 1 }, { session_title: '기술 검토', session_number: 2 }], reports: [], members: [{ userId: 5, userName: '정도현', role: 'admin' }, { userId: 6, userName: '한소희', role: 'presenter' }] },
    { id: 4, title: '마케팅 전략회의', minutes: [{ session_title: '캠페인 기획', session_number: 1 }], reports: [{ file_name: '마케팅보고서.pdf' }], members: [{ userId: 7, userName: '윤재원', role: 'admin' }, { userId: 3, userName: '박민준', role: 'presenter' }] },
    { id: 5, title: '인사위원회', minutes: [{ session_title: '채용 검토', session_number: 1 }], reports: [], members: [{ userId: 1, userName: '김철수', role: 'admin' }, { userId: 8, userName: '오세진', role: 'presenter' }] },
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
  const result = [...map.values()]
  return result.length > 0 ? result : getDemoData()
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
  const groups = meetingGroups.value
  const personMap = {}
  groups.forEach((g, gi) => {
    const phi = (gi / Math.max(groups.length, 1)) * Math.PI * 2
    const hubIdx = nodes.length
    nodes.push({ id: `meeting-${g.id||gi}`, label: g.title||`회의체 ${gi+1}`, type: 'hub', x: Math.cos(phi)*140, y: (Math.random()-.5)*40, z: Math.sin(phi)*140, groupIdx: gi, data: g })
    const docs = [...(g.minutes||[]).map(m=>({label:m.session_title||`${m.session_number}차 회의록`,kind:'minutes'})), ...(g.reports||[]).map(r=>({label:r.file_name||'보고서',kind:'report'}))]
    docs.forEach((doc, di) => {
      const dphi = phi + (di - docs.length/2)*0.42, dr = 210 + Math.random()*60
      edges.push([hubIdx, nodes.length])
      nodes.push({ id: `doc-${g.id||gi}-${di}`, label: doc.label, type: 'doc', kind: doc.kind, x: Math.cos(dphi)*dr, y: (Math.random()-.5)*80, z: Math.sin(dphi)*dr, groupIdx: gi })
    })
    if (showPersonNodes.value) {
      (g.members||[]).forEach((mb, mi) => {
        if (personMap[mb.userId] !== undefined) { edges.push([hubIdx, personMap[mb.userId]]) }
        else {
          const mphi = phi - 0.7 + (mi - (g.members||[]).length/2)*0.38, mr = 175 + Math.random()*35
          personMap[mb.userId] = nodes.length
          edges.push([hubIdx, nodes.length])
          nodes.push({ id: `person-${mb.userId}`, label: mb.userName, type: 'person', userId: mb.userId, role: mb.role, x: Math.cos(mphi)*mr, y: (Math.random()-.5)*55, z: Math.sin(mphi)*mr, groupIdx: gi })
        }
      })
    }
  })
  const hubs = nodes.filter(n => n.type === 'hub')
  hubs.forEach((h, i) => { if (i < hubs.length-1) edges.push([nodes.indexOf(h), nodes.indexOf(hubs[i+1])]) })
  return { nodes, edges }
}

function initGraph() {
  const canvas = canvasRef.value; if (!canvas) return
  ctx = canvas.getContext('2d')
  resizeCanvas()
  ro = new ResizeObserver(resizeCanvas); ro.observe(canvas)
  const g = buildGraphNodes(); gNodes = g.nodes; gEdges = g.edges
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

function roundRect(c,x,y,w,h,r){c.beginPath();c.moveTo(x+r,y);c.lineTo(x+w-r,y);c.quadraticCurveTo(x+w,y,x+w,y+r);c.lineTo(x+w,y+h-r);c.quadraticCurveTo(x+w,y+h,x+w-r,y+h);c.lineTo(x+r,y+h);c.quadraticCurveTo(x,y+h,x,y+h-r);c.lineTo(x,y+r);c.quadraticCurveTo(x,y,x+r,y);c.closePath()}

function getRelatedIndices(hubIdx) {
  const related = new Set([hubIdx])
  gEdges.forEach(([a, b]) => {
    if (a === hubIdx) related.add(b)
    if (b === hubIdx) related.add(a)
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
  const relatedSet = selectedNodeIdx.value !== null ? getRelatedIndices(selectedNodeIdx.value) : null
  const projected=gNodes.map((n,i)=>({...projectNode(n,w,h),node:n,idx:i}))
  const order=projected.slice().sort((a,b)=>a.z-b.z)
  const zf=Math.max(0.6,Math.min(2.5,worldZoom))
  gEdges.forEach(([a,b])=>{
    if(a>=projected.length||b>=projected.length)return
    const pa=projected[a],pb=projected[b]
    const isFocused=focusNode!==null&&(focusNode===a||focusNode===b)
    const isRelated=relatedSet===null||(relatedSet.has(a)&&relatedSet.has(b))
    ctx.beginPath();ctx.moveTo(pa.sx,pa.sy);ctx.lineTo(pb.sx,pb.sy)
    const color=PALETTE[gNodes[a].groupIdx%PALETTE.length]
    if(!isRelated){ctx.strokeStyle=isDark?'rgba(148,163,184,.04)':'rgba(148,163,184,.12)';ctx.lineWidth=.5}
    else if(isFocused){ctx.strokeStyle=color+'cc';ctx.lineWidth=1.8}
    else{ctx.strokeStyle=isDark?`rgba(148,163,184,${Math.max(.05,Math.min(.2,(pa.scale+pb.scale)/2))})`:`rgba(100,116,139,${Math.max(.08,Math.min(.25,(pa.scale+pb.scale)/2))})`;ctx.lineWidth=.8}
    ctx.stroke()
  })
  order.forEach(p=>{
    const n=p.node,color=PALETTE[n.groupIdx%PALETTE.length],isFocused=focusNode===p.idx
    const isRelated=relatedSet===null||relatedSet.has(p.idx)
    ctx.globalAlpha=isRelated?1:0.12
    if(n.type==='hub'){
      const r=Math.min(36,(isFocused?26:22)*p.scale*zf)
      const grad=ctx.createRadialGradient(p.sx,p.sy,0,p.sx,p.sy,r)
      grad.addColorStop(0,color+'ee');grad.addColorStop(1,color+'55')
      ctx.beginPath();ctx.arc(p.sx,p.sy,r,0,Math.PI*2);ctx.fillStyle=grad;ctx.fill()
      if(isFocused||selectedNodeIdx.value===p.idx){ctx.strokeStyle=isDark?'#fff':'#1e293b';ctx.lineWidth=2.5;ctx.stroke()}
      if(p.scale>.28){
        const fs=Math.max(11,Math.min(20,Math.round(14*zf)))
        ctx.fillStyle=isDark?`rgba(255,255,255,${Math.min(1,p.scale*1.5)})`:`rgba(30,58,138,${Math.min(1,p.scale*1.8)})`
        ctx.font=`bold ${fs}px sans-serif`;ctx.textAlign='center';ctx.textBaseline='middle'
        ctx.fillText(n.label.length>7?n.label.slice(0,6)+'…':n.label,p.sx,p.sy)
      }
    } else if(n.type==='doc'){
      const r=Math.min(16,(isFocused?12:9)*p.scale*zf)
      roundRect(ctx,p.sx-r,p.sy-r,r*2,r*2,r*.4)
      ctx.fillStyle=isDark?'rgba(30,58,138,.8)':'rgba(219,234,254,.9)';ctx.fill()
      ctx.strokeStyle=color+'bb';ctx.lineWidth=1;ctx.stroke()
      if(p.scale>.38&&zf>.75){
        const fs=Math.max(9,Math.min(15,Math.round(11*zf)))
        ctx.fillStyle=isDark?`rgba(255,255,255,${Math.min(1,p.scale*1.6)})`:`rgba(30,41,59,${Math.min(1,p.scale*1.6)})`;ctx.font=`${fs}px sans-serif`
        ctx.textAlign='center';ctx.textBaseline='top'
        ctx.fillText(n.label.length>9?n.label.slice(0,8)+'…':n.label,p.sx,p.sy+r+3)
      }
    } else if(n.type==='person'){
      const r=Math.min(18,(isFocused?14:11)*p.scale*zf)
      const grad=ctx.createRadialGradient(p.sx,p.sy,0,p.sx,p.sy,r)
      if(isDark){grad.addColorStop(0,'rgba(139,92,246,.9)');grad.addColorStop(1,'rgba(109,40,217,.5)')}
      else{grad.addColorStop(0,'rgba(167,139,250,.95)');grad.addColorStop(1,'rgba(124,58,237,.6)')}
      ctx.beginPath();ctx.arc(p.sx,p.sy,r,0,Math.PI*2);ctx.fillStyle=grad;ctx.fill()
      ctx.strokeStyle=n.role==='admin'?'#fbbf24':'#a78bfa';ctx.lineWidth=n.role==='admin'?2:1;ctx.stroke()
      if(p.scale>.3&&r>7){
        ctx.fillStyle='#fff';ctx.font=`bold ${Math.max(8,Math.min(14,Math.round(10*zf*p.scale)))}px sans-serif`
        ctx.textAlign='center';ctx.textBaseline='middle';ctx.fillText(n.label[0]||'?',p.sx,p.sy)
      }
      if(p.scale>.4&&zf>.8){
        ctx.fillStyle=isDark?`rgba(196,181,253,${Math.min(1,p.scale*1.5)})`:`rgba(76,29,149,${Math.min(1,p.scale*1.5)})`;ctx.font=`${Math.max(9,Math.min(14,Math.round(11*zf)))}px sans-serif`
        ctx.textAlign='center';ctx.textBaseline='top'
        ctx.fillText(n.label.length>5?n.label.slice(0,4)+'…':n.label,p.sx,p.sy+r+3)
      }
    }
    ctx.globalAlpha=1
  })
}

function animateGraph() {
  if(autoRotate) rotY+=.002
  camX+=(targetCamX-camX)*.05;camY+=(targetCamY-camY)*.05;camZ+=(targetCamZ-camZ)*.05
  worldZoom+=(targetZoom-worldZoom)*.1
  drawArchiveGraph()
  animId=requestAnimationFrame(animateGraph)
}

// ─── Mouse ────────────────────────────────────────────────────
function onMouseDown(e) { isDragging=true;autoRotate=false;lastMx=e.clientX;lastMy=e.clientY }

function onMouseMove(e) {
  if (agentResizing || bottomResizing) return
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
    if(n.type!=='hub') return
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
  clearTimeout(onMouseUp._t);onMouseUp._t=setTimeout(()=>{autoRotate=true},2000)
}
onMouseUp._t=null

function onWheel(e) {
  e.preventDefault()
  targetZoom=Math.max(.25,Math.min(4,targetZoom+(e.deltaY<0?.12:-.12)))
  autoRotate=false;clearTimeout(onWheel._t);onWheel._t=setTimeout(()=>{autoRotate=true},2000)
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
    const p=projectNode(n,w,h)
    const zf=Math.max(.6,Math.min(2.5,worldZoom))
    const baseR=n.type==='hub'?22:n.type==='person'?11:9
    const d=Math.hypot(p.sx-mx,p.sy-my)
    if(d<baseR*p.scale*zf+6&&d<minDist){minDist=d;closest=i}
  })
  if(closest!==null){
    const n=gNodes[closest]
    if(n.type==='hub') {
      selectedNodeIdx.value = selectedNodeIdx.value===closest ? null : closest
    }
    focusNode=closest
    targetCamX=n.x*.55;targetCamY=n.y*.55;targetCamZ=n.z*.55;autoRotate=false
    clearTimeout(onCanvasClick._t);onCanvasClick._t=setTimeout(()=>{autoRotate=true},4000)
  } else {focusNode=null;selectedNodeIdx.value=null;targetCamX=0;targetCamY=0;targetCamZ=0}
}
onCanvasClick._t=null

function onTouchStart(e){isDragging=true;autoRotate=false;lastMx=e.touches[0].clientX;lastMy=e.touches[0].clientY}
function onTouchMove(e){if(!isDragging)return;rotY+=(e.touches[0].clientX-lastMx)*.004;rotX+=(e.touches[0].clientY-lastMy)*.004;rotX=Math.max(-1.2,Math.min(1.2,rotX));lastMx=e.touches[0].clientX;lastMy=e.touches[0].clientY}
function onTouchEnd(){isDragging=false;setTimeout(()=>{autoRotate=true},2000)}

// ─── Lifecycle ─────────────────────────────────────────────────
onMounted(async () => {
  await nextTick()
  initGraph()
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

watch(showPersonNodes,()=>{const g=buildGraphNodes();gNodes=g.nodes;gEdges=g.edges})

// ─── Helpers ──────────────────────────────────────────────────
function formatDate(d){if(!d)return'-';return new Date(d).toLocaleDateString('ko-KR',{year:'numeric',month:'short',day:'numeric'})}
function downloadDummy(name){alert(`"${name}" 다운로드 기능은 준비 중입니다.`)}
const roleLabel={admin:'간사',presenter:'발제자'}
const TYPES=['Draft','In Progress','Done','Pending']
</script>

<template>
  <div class="archive-page" :class="{ 'day-mode': !nightMode }" @click.self="closePlus">

    <!-- ── Header ── -->
    <div class="archive-header">
      <div class="header-title-wrap">
        <h1 class="archive-title">아카이브</h1>
        <p class="archive-desc">회의록·보고서·조직 관계를 탐색하세요</p>
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

      <button class="mode-toggle-btn" @click="nightMode=!nightMode" :title="nightMode?'주간 모드':'야간 모드'">
        <svg v-if="nightMode" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><circle cx="12" cy="12" r="5"/><path d="M12 1v2M12 21v2M4.22 4.22l1.42 1.42M18.36 18.36l1.42 1.42M1 12h2M21 12h2M4.22 19.78l1.42-1.42M18.36 5.64l1.42-1.42"/></svg>
        <svg v-else width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M21 12.79A9 9 0 1111.21 3 7 7 0 0021 12.79z"/></svg>
      </button>

      <div class="plus-wrap">
        <button class="plus-btn" @click.stop="plusOpen=!plusOpen">
          <svg width="16" height="16" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24"><path d="M12 4v16m8-8H4"/></svg>
        </button>
        <Transition name="snack">
          <div v-if="plusOpen" class="plus-snackbar" @click.stop>
            <button class="snack-btn" @click="openCreateModal">
              <svg width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M17 21v-2a4 4 0 00-4-4H5a4 4 0 00-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 00-3-3.87M16 3.13a4 4 0 010 7.75"/></svg>
              회의체
            </button>
            <div class="snack-divider"></div>
            <button class="snack-btn" @click="activateTaskMode">
              <svg width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>
              과제 추출
            </button>
            <div class="snack-divider"></div>
            <button class="snack-btn" @click="activateReviewMode">
              <svg width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M9 17v-2m3 2v-4m3 4v-6m2 10H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"/></svg>
              자료 검토
            </button>
          </div>
        </Transition>
      </div>
    </div>

    <!-- ── Body ── -->
    <div class="archive-body">

      <!-- Detail sidebar -->
      <Transition name="sidebar-slide">
        <div v-if="detailOpen" class="detail-sidebar">
          <div class="detail-header">
            <div>
              <div class="detail-meeting-name">{{ detailMeeting?.title }}</div>
              <div class="detail-meta">{{ detailMeeting?.members?.length||0 }}명 · {{ (detailMeeting?.minutes?.length||0)+(detailMeeting?.reports?.length||0) }}건</div>
            </div>
            <button class="detail-close" @click="detailOpen=false">✕</button>
          </div>
          <div class="detail-body">
            <button class="detail-goto-btn" @click="router.push(`/meetings/${detailMeeting?.id}/home`)">회의체 홈으로 →</button>
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
              <div class="detail-section-label">구성원</div>
              <div class="detail-members">
                <div v-for="mb in detailMeeting.members" :key="mb.userId" class="detail-member-chip">
                  <div class="detail-avatar">{{ mb.userName[0] }}</div>
                  <span>{{ mb.userName }}</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </Transition>

      <!-- Main area -->
      <div ref="mainAreaRef" class="main-area">

        <!-- Graph view -->
        <canvas v-show="viewMode==='graph'"
          ref="canvasRef"
          class="archive-canvas"
          @mousedown="onMouseDown"
          @mousemove="onMouseMove"
          @mouseup="onMouseUp"
          @mouseleave="onMouseUp(); scheduleHideTooltip()"
          @click="onCanvasClick"
          @wheel.prevent="onWheel"
          @touchstart.prevent="onTouchStart"
          @touchmove.prevent="onTouchMove"
          @touchend="onTouchEnd"
        ></canvas>

        <div v-show="viewMode==='graph'" class="graph-legend">
          <div class="legend-item"><div class="legend-dot hub-dot"></div><span>회의체</span></div>
          <div class="legend-item"><div class="legend-dot doc-dot"></div><span>자료</span></div>
          <div class="legend-item">
            <div class="legend-dot person-dot" :style="{ opacity: showPersonNodes?1:.3 }"></div>
            <button class="person-toggle" @click="showPersonNodes=!showPersonNodes">{{ showPersonNodes?'구성원 숨기기':'구성원 표시' }}</button>
          </div>
          <div class="legend-sep"></div>
          <span class="legend-hint">드래그 회전 · 스크롤 확대/축소 · 클릭 선택</span>
        </div>

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
                      <button class="doc-btn" @click="router.push(`/meetings/${g.id}/sessions`)">보기</button>
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
                      <button class="doc-btn" @click="router.push(`/meetings/${g.id}/prepare`)">보기</button>
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

    <!-- ── Floating Agent (draggable, top-right of archive area) ── -->
    <div ref="floatingWrapRef" class="floating-agent-wrap"
      :style="agentPos.left !== null
        ? { top: agentPos.top+'px', left: agentPos.left+'px', right: 'unset' }
        : { top: agentPos.top+'px', right: '12px' }">
      <button v-if="!agentOpen" class="agent-fab" @click="agentOpen=true" :title="agentInfo.name">
        <img :src="agentInfo.avatar" class="agent-fab-img" :alt="agentInfo.name" />
      </button>
      <div v-else class="agent-panel" :style="{ width: panelW+'px', height: effectivePanelH+'px' }">
        <!-- Resize handle (top-left, nw) -->
        <div class="agent-resize-handle" @mousedown="onAgentResizeStart" title="크기 조정">
          <svg width="10" height="10" viewBox="0 0 10 10">
            <line x1="1" y1="9" x2="9" y2="1" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
            <line x1="1" y1="5" x2="5" y2="1" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
          </svg>
        </div>
        <!-- Draggable header -->
        <div class="agent-panel-header" style="cursor:move" @mousedown="onAgentDragStart">
          <div class="agent-header-info">
            <img :src="agentInfo.avatar" class="agent-avatar" />
            <div>
              <div class="agent-name">{{ agentInfo.name }} ({{ agentInfo.nameEn }})</div>
              <div class="agent-subtitle">{{ agentInfo.subtitle }}</div>
            </div>
          </div>
          <div class="agent-header-actions">
            <button class="agent-new-chat-btn" @click="clearAgentChat">새 채팅</button>
            <button class="agent-close-btn" @click="agentOpen=false">✕</button>
          </div>
        </div>

        <div ref="agentMessagesEl" class="agent-messages">
          <div v-for="(msg,i) in currentMessages" :key="i" class="agent-msg-row" :class="msg.role">
            <template v-if="msg.role==='agent'&&msg.content">
              <div class="agent-msg-label">
                <img :src="agentInfo.avatar" class="agent-msg-avatar" />
                {{ agentInfo.name }}
              </div>
              <div class="agent-bubble agent" :class="`theme-${currentAgent}`" v-html="renderMd(msg.content)"></div>
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

        <div class="agent-input-area">
          <div class="agent-input-row">
            <button class="agent-attach-btn" @click="agentFileInput?.click()">＋</button>
            <textarea ref="agentTextareaEl" v-model="agentInput" class="agent-textarea"
              placeholder="질문하세요..." rows="1"
              @input="agentAutoResize" @keydown="onAgentKeydown" />
            <button class="agent-send-btn" :disabled="agentLoading||(!agentInput.trim()&&!agentPendingFiles.length)" @click="sendAgentMsg">전송</button>
          </div>
          <input ref="agentFileInput" type="file" multiple style="display:none" @change="onAgentFileSelected" />
        </div>
        <!-- Bottom resize handle -->
        <div class="agent-resize-bottom" @mousedown="onAgentBottomResizeStart" title="높이 조정">
          <div class="agent-resize-bottom-bar"></div>
        </div>
      </div>
    </div>

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
        </div>
      </Transition>
    </Teleport>

    <!-- ── Create Meeting Modal ── -->
    <Teleport to="body">
      <div v-if="showCreateModal" class="modal-backdrop" @click.self="showCreateModal=false">
        <div class="modal-box">
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

  </div>
</template>

<style scoped>
/* ── Page ── */
.archive-page { display:flex;flex-direction:column;margin:-20px;height:calc(100vh - var(--header-h));background:#0f172a;color:#e2e8f0;overflow:hidden;position:relative; }

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
.plus-btn { width:34px;height:34px;border-radius:50%;background:#3b82f6;border:none;color:#fff;display:flex;align-items:center;justify-content:center;cursor:pointer;transition:opacity .15s; }
.plus-btn:hover { opacity:.85; }
.plus-snackbar { position:absolute;top:calc(100%+8px);right:0;background:#1e293b;border:1px solid rgba(255,255,255,.12);border-radius:12px;padding:4px;display:flex;align-items:center;gap:2px;z-index:200;white-space:nowrap;box-shadow:0 8px 24px rgba(0,0,0,.4); }
.snack-btn { display:flex;align-items:center;gap:6px;padding:8px 14px;border-radius:8px;border:none;background:none;color:#cbd5e1;font-size:13px;font-weight:500;cursor:pointer;transition:background .15s; }
.snack-btn:hover { background:rgba(255,255,255,.08);color:#f1f5f9; }
.snack-divider { width:1px;height:24px;background:rgba(255,255,255,.08); }
.snack-enter-active,.snack-leave-active { transition:all .15s; }
.snack-enter-from,.snack-leave-to { opacity:0;transform:translateY(-6px); }

/* ── Body ── */
.archive-body { flex:1;display:flex;overflow:hidden;min-height:0; }

/* Detail sidebar */
.detail-sidebar { width:260px;flex-shrink:0;background:#0a0f1e;border-right:1px solid rgba(255,255,255,.06);display:flex;flex-direction:column;overflow:hidden; }
.sidebar-slide-enter-active,.sidebar-slide-leave-active { transition:width .25s ease,opacity .2s; }
.sidebar-slide-enter-from,.sidebar-slide-leave-to { width:0;opacity:0; }
.detail-header { display:flex;align-items:flex-start;justify-content:space-between;padding:14px 12px 10px;border-bottom:1px solid rgba(255,255,255,.06);flex-shrink:0; }
.detail-meeting-name { font-size:13px;font-weight:700;color:#f1f5f9; }
.detail-meta { font-size:11px;color:#475569;margin-top:2px; }
.detail-close { background:none;border:none;cursor:pointer;color:#475569;font-size:14px;line-height:1;padding:2px;transition:color .15s; }
.detail-close:hover { color:#94a3b8; }
.detail-body { flex:1;overflow-y:auto;padding:10px 12px;display:flex;flex-direction:column;gap:10px; }
.detail-goto-btn { width:100%;padding:7px;border-radius:7px;border:1px solid rgba(96,165,250,.3);background:rgba(96,165,250,.08);color:#60a5fa;font-size:12px;font-weight:600;cursor:pointer; }
.detail-section { display:flex;flex-direction:column;gap:4px; }
.detail-section-label { font-size:10px;font-weight:700;color:#334155;text-transform:uppercase;letter-spacing:.06em;margin-bottom:2px; }
.detail-doc-item { display:flex;align-items:center;gap:7px;padding:5px 6px;border-radius:5px;background:rgba(255,255,255,.02);border:1px solid rgba(255,255,255,.04); }
.detail-doc-icon { width:22px;height:22px;border-radius:4px;display:flex;align-items:center;justify-content:center;flex-shrink:0; }
.detail-doc-icon.minutes { background:rgba(59,130,246,.2);color:#60a5fa; }
.detail-doc-icon.report { background:rgba(16,185,129,.2);color:#34d399; }
.detail-doc-info { flex:1;min-width:0; }
.detail-doc-name { font-size:11px;color:#cbd5e1;font-weight:500;overflow:hidden;text-overflow:ellipsis;white-space:nowrap; }
.detail-doc-date { font-size:10px;color:#334155; }
.detail-members { display:flex;flex-wrap:wrap;gap:4px; }
.detail-member-chip { display:flex;align-items:center;gap:4px;background:rgba(124,58,237,.15);border:1px solid rgba(124,58,237,.25);border-radius:20px;padding:2px 7px 2px 3px; }
.detail-avatar { width:16px;height:16px;border-radius:50%;background:rgba(124,58,237,.5);color:#fff;font-size:9px;font-weight:700;display:flex;align-items:center;justify-content:center; }
.detail-member-chip span { font-size:11px;color:#c4b5fd; }

/* ── Main area ── */
.main-area { flex:1;position:relative;overflow:hidden;min-width:0; }
.archive-canvas { width:100%;height:100%;cursor:grab;display:block; }
.archive-canvas:active { cursor:grabbing; }
.graph-legend { position:absolute;bottom:14px;left:14px;display:flex;align-items:center;gap:10px;flex-wrap:wrap;background:rgba(15,23,42,.75);backdrop-filter:blur(8px);border:1px solid rgba(255,255,255,.07);border-radius:8px;padding:6px 12px;font-size:11px;color:#64748b; }
.legend-item { display:flex;align-items:center;gap:5px; }
.legend-dot { width:9px;height:9px;border-radius:50%;flex-shrink:0; }
.hub-dot { background:#60a5fa; }
.doc-dot { background:#1e3a8a;border:1px solid #60a5fa; }
.person-dot { background:#7c3aed;border:1px solid #a78bfa;transition:opacity .2s; }
.person-toggle { background:none;border:none;cursor:pointer;color:#64748b;font-size:11px;padding:0; }
.person-toggle:hover { color:#a78bfa; }
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

/* ── Floating agent (draggable, top-right of archive area) ── */
.floating-agent-wrap { position:absolute;z-index:100;display:flex;flex-direction:column;align-items:flex-end;user-select:none; }
.agent-fab { width:48px;height:48px;border-radius:50%;border:none;background:var(--primary);padding:0;cursor:pointer;box-shadow:0 4px 16px rgba(0,0,0,.4);transition:transform .2s; }
.agent-fab:hover { transform:scale(1.05); }
.agent-fab-img { width:40px;height:40px;border-radius:50%;object-fit:cover; }
.agent-panel { background:#fff;border-radius:14px;box-shadow:0 12px 40px rgba(0,0,0,.35);border:1px solid var(--border);display:flex;flex-direction:column;overflow:hidden;position:relative;min-width:260px;min-height:200px; }
.agent-resize-handle { position:absolute;top:0;left:0;width:22px;height:22px;cursor:nw-resize;z-index:10;display:flex;align-items:center;justify-content:center;color:#cbd5e1;border-radius:0 0 6px 0;user-select:none;transition:color .15s,background .15s; }
.agent-resize-handle:hover { color:var(--primary);background:#f1f5f9; }
.agent-resize-bottom { flex-shrink:0;height:10px;display:flex;align-items:center;justify-content:center;cursor:s-resize;background:#f8fafc;border-top:1px solid var(--border);user-select:none; }
.agent-resize-bottom-bar { width:32px;height:3px;border-radius:2px;background:#cbd5e1; }
.agent-resize-bottom:hover .agent-resize-bottom-bar { background:#94a3b8; }
.agent-panel-header { display:flex;align-items:center;justify-content:space-between;padding:10px 12px 8px 22px;border-bottom:1px solid var(--border);flex-shrink:0; }
.agent-header-info { display:flex;align-items:center;gap:8px; }
.agent-avatar { width:30px;height:30px;border-radius:50%;object-fit:cover; }
.agent-name { font-size:13px;font-weight:700;color:var(--primary);line-height:1.2; }
.agent-subtitle { font-size:10px;color:var(--text-muted); }
.agent-header-actions { display:flex;align-items:center;gap:5px; }
.agent-new-chat-btn { background:none;border:1px solid var(--border);border-radius:6px;padding:3px 9px;font-size:11px;color:var(--text-muted);cursor:pointer;transition:all .15s; }
.agent-new-chat-btn:hover { background:#eff6ff;border-color:#93c5fd;color:var(--primary); }
.agent-close-btn { width:24px;height:24px;border-radius:6px;border:none;background:#f1f5f9;color:#64748b;cursor:pointer;font-size:12px;line-height:1;display:flex;align-items:center;justify-content:center; }
.agent-messages { flex:1;overflow-y:auto;padding:8px;display:flex;flex-direction:column;gap:7px; }
.agent-messages::-webkit-scrollbar { width:3px; }
.agent-messages::-webkit-scrollbar-thumb { background:#e2e8f0; }
.agent-msg-row { display:flex;flex-direction:column;gap:3px; }
.agent-msg-row.user { align-items:flex-end; }
.agent-msg-label { display:flex;align-items:center;gap:4px;font-size:11px;font-weight:600;color:var(--text-muted); }
.agent-msg-avatar { width:15px;height:15px;border-radius:50%;object-fit:cover; }
.agent-bubble { padding:8px 11px;border-radius:10px;font-size:13px;line-height:1.55;max-width:90%;word-break:break-word;border:1px solid transparent; }
.agent-bubble.user { background:var(--primary);color:#fff;border-radius:10px 10px 2px 10px; }
/* Agent bubble colors per agent type */
.agent-bubble.agent.theme-hyean { background:#eff6ff;border-color:#93c5fd;color:#1e40af;border-radius:2px 10px 10px 10px; }
.agent-bubble.agent.theme-gaon  { background:#fef3c7;border-color:#fcd34d;color:#78350f;border-radius:2px 10px 10px 10px; }
.agent-bubble.agent.theme-naru  { background:#ecfdf5;border-color:#6ee7b7;color:#064e3b;border-radius:2px 10px 10px 10px; }
.agent-suggested { display:flex;flex-direction:column;gap:3px;margin-top:5px; }
.suggested-btn { text-align:left;background:rgba(255,255,255,.7);border:1px solid #c7d2fe;border-radius:6px;padding:4px 9px;font-size:11px;color:var(--primary);cursor:pointer;font-weight:500;transition:background .15s; }
.suggested-btn:hover:not(:disabled) { background:#fff; }
.suggested-btn:disabled { opacity:.4;cursor:not-allowed; }
.typing { display:flex;gap:4px;align-items:center; }
.typing span { width:5px;height:5px;background:#94a3b8;border-radius:50%;animation:bounce .8s infinite; }
.typing span:nth-child(2) { animation-delay:.15s; }
.typing span:nth-child(3) { animation-delay:.3s; }
@keyframes bounce { 0%,80%,100%{transform:scale(.8);opacity:.5}40%{transform:scale(1.2);opacity:1} }
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

/* ── Mode toggle button ── */
.mode-toggle-btn { width:32px;height:32px;border-radius:8px;border:1px solid rgba(255,255,255,.12);background:rgba(255,255,255,.06);color:#94a3b8;display:flex;align-items:center;justify-content:center;cursor:pointer;flex-shrink:0;transition:all .15s; }
.mode-toggle-btn:hover { background:rgba(255,255,255,.12);color:#e2e8f0; }
.day-mode .mode-toggle-btn { border-color:#e2e8f0;background:#f1f5f9;color:#475569; }
.day-mode .mode-toggle-btn:hover { background:#e2e8f0;color:#1e293b; }

/* ── Day mode overrides ── */
.day-mode { background:#eef2ff !important;color:#1e293b; }
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
.day-mode .graph-legend { background:rgba(238,242,255,.92);border-color:#e2e8f0;color:#64748b; }
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
