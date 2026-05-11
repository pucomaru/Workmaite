<script setup>
import { ref, computed, onMounted, onBeforeUnmount, watch, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import api from '../api'

const router = useRouter()

// ─── Data ────────────────────────────────────────────────────
const minutes = ref([])
const reports = ref([])
const membersData = ref([]) // [{meetingId, meetingTitle, userId, userName, role}]
const loading = ref(true)
const search = ref('')
const listOpen = ref(false)
const showPersonNodes = ref(true)
const expandedMeeting = ref(null)

onMounted(async () => {
  await nextTick()
  initGraph()
  try {
    const [m, r, mtgs] = await Promise.all([
      api.get('/api/all-minutes').catch(() => ({ data: [] })),
      api.get('/api/all-reports').catch(() => ({ data: [] })),
      api.get('/api/meetings').catch(() => ({ data: [] })),
    ])
    minutes.value = m.data
    reports.value = r.data
    const memberResults = await Promise.all(
      mtgs.data.map(mtg =>
        api.get(`/api/meetings/${mtg.id}/members`)
          .then(res => res.data.map(mb => ({
            meetingId: mtg.id,
            meetingTitle: mtg.title,
            userId: mb.user?.id,
            userName: mb.user?.name || '?',
            role: mb.role,
          })))
          .catch(() => [])
      )
    )
    membersData.value = memberResults.flat()
  } finally {
    loading.value = false
    const g = buildGraphNodes()
    gNodes = g.nodes
    gEdges = g.edges
  }
})

// ─── Computed ────────────────────────────────────────────────
const meetingGroups = computed(() => {
  const map = new Map()
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
  return meetingGroups.value.filter(g => {
    if (g.title.toLowerCase().includes(q)) return true
    if (g.minutes.some(m => (m.session_title || '').toLowerCase().includes(q) || (m.content_summary || '').toLowerCase().includes(q))) return true
    if (g.reports.some(r => (r.file_name || '').toLowerCase().includes(q))) return true
    if (g.members.some(m => m.userName.toLowerCase().includes(q))) return true
    return false
  })
})

// ─── 3D Graph ────────────────────────────────────────────────
const canvasRef = ref(null)
let ctx = null
let animId = null
let ro = null

let rotX = 0.2, rotY = 0
let isDragging = false
let lastMx = 0, lastMy = 0
let autoRotate = true
let focusNode = null
let targetCamX = 0, targetCamY = 0, targetCamZ = 0
let camX = 0, camY = 0, camZ = 0
let worldZoom = 1.0, targetZoom = 1.0
let dpr = 1

function buildGraphNodes() {
  const nodes = [], edges = []
  const groups = meetingGroups.value.length > 0 ? meetingGroups.value : getDemoData()
  const personMap = {} // userId → nodeIdx

  groups.forEach((g, gi) => {
    const phi = (gi / Math.max(groups.length, 1)) * Math.PI * 2
    const hubIdx = nodes.length
    nodes.push({
      id: `meeting-${g.id || gi}`, label: g.title || `회의체 ${gi + 1}`,
      type: 'hub', x: Math.cos(phi) * 140, y: (Math.random() - 0.5) * 40, z: Math.sin(phi) * 140,
      groupIdx: gi, data: g,
    })

    // Doc nodes
    const docs = [
      ...(g.minutes || []).map(m => ({ label: m.session_title || `${m.session_number}차 회의록`, kind: 'minutes' })),
      ...(g.reports || []).map(r => ({ label: r.file_name || '보고서', kind: 'report' })),
    ]
    docs.forEach((doc, di) => {
      const dphi = phi + (di - docs.length / 2) * 0.42
      const dr = 210 + Math.random() * 60
      edges.push([hubIdx, nodes.length])
      nodes.push({
        id: `doc-${g.id || gi}-${di}`, label: doc.label, type: 'doc', kind: doc.kind,
        x: Math.cos(dphi) * dr, y: (Math.random() - 0.5) * 80, z: Math.sin(dphi) * dr,
        groupIdx: gi,
      })
    })

    // Person nodes
    if (showPersonNodes.value) {
      const mems = g.members || []
      mems.forEach((mb, mi) => {
        if (personMap[mb.userId] !== undefined) {
          edges.push([hubIdx, personMap[mb.userId]])
        } else {
          const mphi = phi - 0.7 + (mi - mems.length / 2) * 0.38
          const mr = 175 + Math.random() * 35
          personMap[mb.userId] = nodes.length
          edges.push([hubIdx, nodes.length])
          nodes.push({
            id: `person-${mb.userId}`, label: mb.userName, type: 'person', userId: mb.userId, role: mb.role,
            x: Math.cos(mphi) * mr, y: (Math.random() - 0.5) * 55, z: Math.sin(mphi) * mr,
            groupIdx: gi,
          })
        }
      })
    }
  })

  // Hub-hub edges
  const hubs = nodes.filter(n => n.type === 'hub')
  hubs.forEach((h, i) => {
    if (i < hubs.length - 1) edges.push([nodes.indexOf(h), nodes.indexOf(hubs[i + 1])])
  })

  return { nodes, edges }
}

function getDemoData() {
  return [
    { id: 1, title: '전략기획위원회',
      minutes: [{ session_title: '2025 전략 수립', session_number: 1 }, { session_title: '예산 계획 검토', session_number: 2 }],
      reports: [{ file_name: '전략보고서_Q1.pdf' }],
      members: [{ userId: 1, userName: '김철수', role: 'admin' }, { userId: 2, userName: '이영희', role: 'presenter' }, { userId: 3, userName: '박민준', role: 'presenter' }] },
    { id: 2, title: '운영위원회',
      minutes: [{ session_title: '운영 현황 보고', session_number: 1 }],
      reports: [{ file_name: '운영보고서_5월.pdf' }, { file_name: '성과보고서.pdf' }],
      members: [{ userId: 4, userName: '최지영', role: 'admin' }, { userId: 2, userName: '이영희', role: 'presenter' }] },
    { id: 3, title: '개발팀 주간회의',
      minutes: [{ session_title: '스프린트 계획', session_number: 1 }, { session_title: '회고', session_number: 2 }, { session_title: '기술 검토', session_number: 3 }],
      reports: [],
      members: [{ userId: 5, userName: '정도현', role: 'admin' }, { userId: 6, userName: '한소희', role: 'presenter' }] },
    { id: 4, title: '마케팅 전략회의',
      minutes: [{ session_title: '캠페인 기획', session_number: 1 }],
      reports: [{ file_name: '마케팅보고서.pdf' }],
      members: [{ userId: 7, userName: '윤재원', role: 'admin' }, { userId: 3, userName: '박민준', role: 'presenter' }] },
    { id: 5, title: '인사위원회',
      minutes: [{ session_title: '채용 검토', session_number: 1 }],
      reports: [],
      members: [{ userId: 1, userName: '김철수', role: 'admin' }, { userId: 8, userName: '오세진', role: 'presenter' }] },
  ]
}

let gNodes = [], gEdges = []

function initGraph() {
  const canvas = canvasRef.value
  if (!canvas) return
  ctx = canvas.getContext('2d')
  resizeCanvas()
  ro = new ResizeObserver(resizeCanvas)
  ro.observe(canvas)
  const g = buildGraphNodes()
  gNodes = g.nodes; gEdges = g.edges
  animateGraph()
}

function resizeCanvas() {
  const c = canvasRef.value
  if (!c) return
  dpr = window.devicePixelRatio || 1
  c.width = c.offsetWidth * dpr
  c.height = c.offsetHeight * dpr
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
}

function projectNode(n, w, h) {
  let x = (n.x - camX) * worldZoom
  let y = (n.y - camY) * worldZoom
  let z = (n.z - camZ) * worldZoom
  const cosX = Math.cos(rotX), sinX = Math.sin(rotX)
  const cosY = Math.cos(rotY), sinY = Math.sin(rotY)
  const x1 = cosY * x + sinY * z, y1 = y, z1 = -sinY * x + cosY * z
  const x2 = x1, y2 = cosX * y1 - sinX * z1, z2 = sinX * y1 + cosX * z1
  const fov = 600
  const s = fov / (fov + z2 + 400)
  return { sx: w / 2 + x2 * s, sy: h / 2 + y2 * s, scale: s, z: z2 }
}

const PALETTE = ['#60a5fa', '#34d399', '#f472b6', '#fbbf24', '#a78bfa', '#fb923c', '#38bdf8', '#86efac']

function drawArchiveGraph() {
  const canvas = canvasRef.value
  if (!canvas || !ctx) return
  const w = canvas.offsetWidth, h = canvas.offsetHeight
  ctx.clearRect(0, 0, w, h)

  if (!gNodes.length) {
    ctx.fillStyle = 'rgba(148,163,184,0.5)'
    ctx.font = '14px sans-serif'
    ctx.textAlign = 'center'
    ctx.fillText('데이터를 불러오는 중...', w / 2, h / 2)
    return
  }

  const projected = gNodes.map((n, i) => ({ ...projectNode(n, w, h), node: n, idx: i }))
  const order = projected.slice().sort((a, b) => a.z - b.z)

  // Font & size scale based on worldZoom (clamped for readability)
  const zf = Math.max(0.6, Math.min(2.5, worldZoom))

  // Edges
  gEdges.forEach(([a, b]) => {
    if (a >= projected.length || b >= projected.length) return
    const pa = projected[a], pb = projected[b]
    const isFocused = focusNode !== null && (focusNode === a || focusNode === b)
    ctx.beginPath()
    ctx.moveTo(pa.sx, pa.sy)
    ctx.lineTo(pb.sx, pb.sy)
    const color = PALETTE[gNodes[a].groupIdx % PALETTE.length]
    if (isFocused) {
      ctx.strokeStyle = color + 'cc'
      ctx.lineWidth = 1.8
    } else {
      ctx.strokeStyle = `rgba(148,163,184,${Math.max(0.05, Math.min(0.2, (pa.scale + pb.scale) / 2))})`
      ctx.lineWidth = 0.8
    }
    ctx.stroke()
  })

  // Nodes (painter's order)
  order.forEach(p => {
    const n = p.node
    const color = PALETTE[n.groupIdx % PALETTE.length]
    const isFocused = focusNode === p.idx

    if (n.type === 'hub') {
      const r = Math.min(36, (isFocused ? 26 : 22) * p.scale * zf)
      const grad = ctx.createRadialGradient(p.sx, p.sy, 0, p.sx, p.sy, r)
      grad.addColorStop(0, color + 'ee')
      grad.addColorStop(1, color + '55')
      ctx.beginPath()
      ctx.arc(p.sx, p.sy, r, 0, Math.PI * 2)
      ctx.fillStyle = grad
      ctx.fill()
      if (isFocused) {
        ctx.strokeStyle = '#fff'
        ctx.lineWidth = 2
        ctx.stroke()
      }
      // Label
      if (p.scale > 0.28) {
        const fontSize = Math.max(11, Math.min(20, Math.round(14 * zf)))
        ctx.fillStyle = `rgba(255,255,255,${Math.min(1, p.scale * 1.5)})`
        ctx.font = `bold ${fontSize}px sans-serif`
        ctx.textAlign = 'center'
        ctx.textBaseline = 'middle'
        const label = n.label.length > 7 ? n.label.slice(0, 6) + '…' : n.label
        ctx.fillText(label, p.sx, p.sy)
      }

    } else if (n.type === 'doc') {
      const r = Math.min(16, (isFocused ? 12 : 9) * p.scale * zf)
      roundRect(ctx, p.sx - r, p.sy - r, r * 2, r * 2, r * 0.4)
      ctx.fillStyle = `rgba(30,58,138,0.8)`
      ctx.fill()
      ctx.strokeStyle = color + 'bb'
      ctx.lineWidth = 1
      ctx.stroke()
      if (p.scale > 0.38 && zf > 0.75) {
        const fontSize = Math.max(9, Math.min(15, Math.round(11 * zf)))
        ctx.fillStyle = `rgba(255,255,255,${Math.min(1, p.scale * 1.6)})`
        ctx.font = `${fontSize}px sans-serif`
        ctx.textAlign = 'center'
        ctx.textBaseline = 'top'
        const label = n.label.length > 9 ? n.label.slice(0, 8) + '…' : n.label
        ctx.fillText(label, p.sx, p.sy + r + 3)
      }

    } else if (n.type === 'person') {
      const r = Math.min(18, (isFocused ? 14 : 11) * p.scale * zf)
      // Person circle with gradient
      const grad = ctx.createRadialGradient(p.sx, p.sy, 0, p.sx, p.sy, r)
      grad.addColorStop(0, `rgba(139,92,246,0.9)`)
      grad.addColorStop(1, `rgba(109,40,217,0.5)`)
      ctx.beginPath()
      ctx.arc(p.sx, p.sy, r, 0, Math.PI * 2)
      ctx.fillStyle = grad
      ctx.fill()
      ctx.strokeStyle = n.role === 'admin' ? '#fbbf24' : '#a78bfa'
      ctx.lineWidth = n.role === 'admin' ? 2 : 1
      ctx.stroke()
      // Initials inside
      if (p.scale > 0.3 && r > 7) {
        const initFontSize = Math.max(8, Math.min(14, Math.round(10 * zf * p.scale)))
        ctx.fillStyle = '#fff'
        ctx.font = `bold ${initFontSize}px sans-serif`
        ctx.textAlign = 'center'
        ctx.textBaseline = 'middle'
        ctx.fillText(n.label[0] || '?', p.sx, p.sy)
      }
      // Name below
      if (p.scale > 0.4 && zf > 0.8) {
        const fontSize = Math.max(9, Math.min(14, Math.round(11 * zf)))
        ctx.fillStyle = `rgba(196,181,253,${Math.min(1, p.scale * 1.5)})`
        ctx.font = `${fontSize}px sans-serif`
        ctx.textAlign = 'center'
        ctx.textBaseline = 'top'
        const label = n.label.length > 5 ? n.label.slice(0, 4) + '…' : n.label
        ctx.fillText(label, p.sx, p.sy + r + 3)
      }
    }
  })
}

function roundRect(ctx, x, y, w, h, r) {
  ctx.beginPath()
  ctx.moveTo(x + r, y)
  ctx.lineTo(x + w - r, y)
  ctx.quadraticCurveTo(x + w, y, x + w, y + r)
  ctx.lineTo(x + w, y + h - r)
  ctx.quadraticCurveTo(x + w, y + h, x + w - r, y + h)
  ctx.lineTo(x + r, y + h)
  ctx.quadraticCurveTo(x, y + h, x, y + h - r)
  ctx.lineTo(x, y + r)
  ctx.quadraticCurveTo(x, y, x + r, y)
  ctx.closePath()
}

function animateGraph() {
  if (autoRotate) rotY += 0.002
  camX += (targetCamX - camX) * 0.05
  camY += (targetCamY - camY) * 0.05
  camZ += (targetCamZ - camZ) * 0.05
  worldZoom += (targetZoom - worldZoom) * 0.1
  drawArchiveGraph()
  animId = requestAnimationFrame(animateGraph)
}

// ─── Mouse / Touch / Wheel ────────────────────────────────────
function onMouseDown(e) {
  isDragging = true; autoRotate = false
  lastMx = e.clientX; lastMy = e.clientY
}
function onMouseMove(e) {
  if (!isDragging) return
  rotY += (e.clientX - lastMx) * 0.004
  rotX += (e.clientY - lastMy) * 0.004
  rotX = Math.max(-1.2, Math.min(1.2, rotX))
  lastMx = e.clientX; lastMy = e.clientY
}
function onMouseUp() {
  isDragging = false
  clearTimeout(onMouseUp._t)
  onMouseUp._t = setTimeout(() => { autoRotate = true }, 2000)
}
onMouseUp._t = null

function onWheel(e) {
  e.preventDefault()
  targetZoom = Math.max(0.25, Math.min(4.0, targetZoom + (e.deltaY < 0 ? 0.12 : -0.12)))
  autoRotate = false
  clearTimeout(onWheel._t)
  onWheel._t = setTimeout(() => { autoRotate = true }, 2000)
}
onWheel._t = null

function onCanvasClick(e) {
  if (isDragging) return
  const canvas = canvasRef.value
  if (!canvas) return
  const rect = canvas.getBoundingClientRect()
  const mx = e.clientX - rect.left, my = e.clientY - rect.top
  const w = canvas.offsetWidth, h = canvas.offsetHeight
  let closest = null, minDist = Infinity
  gNodes.forEach((n, i) => {
    const p = projectNode(n, w, h)
    const zf = Math.max(0.6, Math.min(2.5, worldZoom))
    const baseR = n.type === 'hub' ? 22 : n.type === 'person' ? 11 : 9
    const threshold = baseR * p.scale * zf + 6
    const d = Math.hypot(p.sx - mx, p.sy - my)
    if (d < threshold && d < minDist) { minDist = d; closest = i }
  })
  if (closest !== null) {
    focusNode = closest
    const n = gNodes[closest]
    targetCamX = n.x * 0.55; targetCamY = n.y * 0.55; targetCamZ = n.z * 0.55
    autoRotate = false
    clearTimeout(onCanvasClick._t)
    onCanvasClick._t = setTimeout(() => { autoRotate = true }, 4000)
  } else {
    focusNode = null
    targetCamX = 0; targetCamY = 0; targetCamZ = 0
  }
}
onCanvasClick._t = null

function onTouchStart(e) {
  isDragging = true; autoRotate = false
  lastMx = e.touches[0].clientX; lastMy = e.touches[0].clientY
}
function onTouchMove(e) {
  if (!isDragging) return
  rotY += (e.touches[0].clientX - lastMx) * 0.004
  rotX += (e.touches[0].clientY - lastMy) * 0.004
  rotX = Math.max(-1.2, Math.min(1.2, rotX))
  lastMx = e.touches[0].clientX; lastMy = e.touches[0].clientY
}
function onTouchEnd() { isDragging = false; setTimeout(() => { autoRotate = true }, 2000) }

onBeforeUnmount(() => { cancelAnimationFrame(animId); ro?.disconnect() })

// ─── Search → graph focus + list filter ──────────────────────
watch(search, q => {
  if (!q) {
    focusNode = null; targetCamX = 0; targetCamY = 0; targetCamZ = 0
    return
  }
  // Auto-open list panel when searching
  listOpen.value = true
  const lower = q.toLowerCase()
  let bestIdx = null, bestScore = -1
  gNodes.forEach((n, i) => {
    let score = n.label.toLowerCase().includes(lower) ? (n.type === 'hub' ? 10 : n.type === 'person' ? 6 : 5) : 0
    if (score > bestScore) { bestScore = score; bestIdx = i }
  })
  if (bestIdx !== null && bestScore > 0) {
    focusNode = bestIdx
    const n = gNodes[bestIdx]
    targetCamX = n.x * 0.55; targetCamY = n.y * 0.55; targetCamZ = n.z * 0.55
    autoRotate = false
    clearTimeout(search._t)
    search._t = setTimeout(() => { autoRotate = true }, 5000)
  }
})
search._t = null

watch(showPersonNodes, () => {
  const g = buildGraphNodes()
  gNodes = g.nodes; gEdges = g.edges
})

// ─── List helpers ─────────────────────────────────────────────
function formatDate(d) {
  if (!d) return '-'
  return new Date(d).toLocaleDateString('ko-KR', { year: 'numeric', month: 'short', day: 'numeric' })
}
function downloadDummy(name) { alert(`"${name}" 다운로드 기능은 준비 중입니다.`) }
const roleLabel = { admin: '간사', presenter: '발제자' }
</script>

<template>
  <div class="archive-page">

    <!-- ── Header ── -->
    <div class="archive-header">
      <div class="header-left">
        <h1 class="archive-title">아카이브</h1>
        <p class="archive-desc">회의록·보고서·조직 관계를 탐색하세요</p>
      </div>
      <div class="search-wrap">
        <svg class="search-icon" width="15" height="15" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><circle cx="11" cy="11" r="8"/><path d="M21 21l-4.35-4.35"/></svg>
        <input v-model="search" class="search-input" placeholder="회의체명, 회의록, 보고서, 인물 검색..." />
        <button v-if="search" class="search-clear" @click="search = ''">
          <svg width="12" height="12" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24"><path d="M18 6L6 18M6 6l12 12"/></svg>
        </button>
      </div>
      <button class="list-toggle-btn" :class="{ active: listOpen }" @click="listOpen = !listOpen" title="목록 패널">
        <svg width="15" height="15" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01"/></svg>
        목록
        <svg width="12" height="12" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"
          :style="{ transform: listOpen ? 'rotate(0deg)' : 'rotate(180deg)', transition: 'transform .2s' }">
          <path d="M9 18l6-6-6-6"/>
        </svg>
      </button>
    </div>

    <!-- ── Body ── -->
    <div class="archive-body">

      <!-- Graph -->
      <div class="graph-container">
        <canvas
          ref="canvasRef"
          class="archive-canvas"
          @mousedown="onMouseDown"
          @mousemove="onMouseMove"
          @mouseup="onMouseUp"
          @mouseleave="onMouseUp"
          @click="onCanvasClick"
          @wheel.prevent="onWheel"
          @touchstart.prevent="onTouchStart"
          @touchmove.prevent="onTouchMove"
          @touchend="onTouchEnd"
        ></canvas>

        <!-- Legend -->
        <div class="graph-legend">
          <div class="legend-item"><div class="legend-dot hub-dot"></div><span>회의체</span></div>
          <div class="legend-item"><div class="legend-dot doc-dot"></div><span>자료</span></div>
          <div class="legend-item">
            <div class="legend-dot person-dot" :style="{ opacity: showPersonNodes ? 1 : 0.3 }"></div>
            <button class="person-toggle" @click="showPersonNodes = !showPersonNodes">
              {{ showPersonNodes ? '구성원 숨기기' : '구성원 표시' }}
            </button>
          </div>
          <div class="legend-sep"></div>
          <div class="legend-hint">드래그 회전 · 스크롤 확대/축소 · 클릭 선택</div>
        </div>
      </div>

      <!-- Slide-in List Panel -->
      <div class="list-panel" :class="{ open: listOpen }">
        <div class="list-panel-inner">
          <div class="list-panel-header">
            <span class="list-panel-title">
              {{ search ? `"${search}" 검색 결과` : '전체 목록' }}
            </span>
            <span class="list-count">{{ filteredGroups.length }}개 회의체</span>
          </div>

          <div v-if="loading" class="empty-state">불러오는 중...</div>
          <div v-else-if="!filteredGroups.length" class="empty-state">
            {{ search ? '검색 결과가 없습니다.' : '데이터가 없습니다.' }}
          </div>

          <div v-else class="meeting-groups">
            <div v-for="g in filteredGroups" :key="g.id" class="meeting-group">
              <div class="group-header" @click="expandedMeeting = expandedMeeting === g.id ? null : g.id">
                <div class="group-header-left">
                  <div class="group-dot"></div>
                  <span class="group-title">{{ g.title }}</span>
                </div>
                <div class="group-meta-right">
                  <span class="group-count">{{ g.minutes.length + g.reports.length }}건</span>
                  <svg width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"
                    :style="{ transform: expandedMeeting === g.id ? 'rotate(180deg)' : '', transition: 'transform .2s' }">
                    <path d="M19 9l-7 7-7-7"/>
                  </svg>
                </div>
              </div>

              <div v-if="expandedMeeting === g.id" class="group-body">
                <!-- Minutes -->
                <div v-if="g.minutes.length" class="doc-section">
                  <div class="doc-section-label">회의록</div>
                  <div v-for="m in g.minutes" :key="m.minutes_id || m.session_id" class="doc-item">
                    <div class="doc-icon minutes-icon">
                      <svg width="11" height="11" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"/></svg>
                    </div>
                    <div class="doc-info">
                      <div class="doc-name">{{ m.session_title || `${m.session_number}차 회의록` }}</div>
                      <div class="doc-meta">{{ formatDate(m.ended_at) }}</div>
                    </div>
                    <div class="doc-actions">
                      <button class="doc-btn" @click="router.push(`/meetings/${g.id}/sessions`)">보기</button>
                      <button class="doc-btn icon-btn" @click="downloadDummy(m.session_title || '회의록')" title="다운로드">
                        <svg width="11" height="11" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"/></svg>
                      </button>
                    </div>
                  </div>
                </div>

                <!-- Reports -->
                <div v-if="g.reports.length" class="doc-section">
                  <div class="doc-section-label">보고서</div>
                  <div v-for="r in g.reports" :key="r.id" class="doc-item">
                    <div class="doc-icon report-icon">
                      <svg width="11" height="11" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M9 17v-2m3 2v-4m3 4v-6m2 10H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"/></svg>
                    </div>
                    <div class="doc-info">
                      <div class="doc-name">{{ r.file_name || '보고서' }}</div>
                      <div class="doc-meta">{{ formatDate(r.submitted_at) }}</div>
                    </div>
                    <div class="doc-actions">
                      <button class="doc-btn" @click="router.push(`/meetings/${g.id}/prepare`)">보기</button>
                      <button class="doc-btn icon-btn" @click="downloadDummy(r.file_name || '보고서')" title="다운로드">
                        <svg width="11" height="11" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"/></svg>
                      </button>
                    </div>
                  </div>
                </div>

                <!-- Members -->
                <div v-if="g.members.length" class="doc-section">
                  <div class="doc-section-label">구성원</div>
                  <div class="member-chips">
                    <div v-for="mb in g.members" :key="mb.userId" class="member-chip">
                      <div class="member-avatar">{{ mb.userName[0] }}</div>
                      <span class="member-name">{{ mb.userName }}</span>
                      <span class="member-role" :class="mb.role === 'admin' ? 'role-admin' : 'role-presenter'">
                        {{ roleLabel[mb.role] || mb.role }}
                      </span>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

    </div><!-- /archive-body -->
  </div>
</template>

<style scoped>
.archive-page {
  display: flex;
  flex-direction: column;
  margin: -20px;
  height: calc(100vh - var(--header-h));
  background: #0f172a;
  color: #e2e8f0;
  overflow: hidden;
}

/* ── Header ── */
.archive-header {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 12px 18px;
  background: #0f172a;
  border-bottom: 1px solid rgba(255,255,255,0.08);
  flex-shrink: 0;
  flex-wrap: wrap;
}
.header-left { flex-shrink: 0; }
.archive-title { font-size: 17px; font-weight: 700; color: #f1f5f9; margin: 0; }
.archive-desc { font-size: 11px; color: #475569; margin: 0; }

.search-wrap {
  position: relative; flex: 1; min-width: 180px; max-width: 380px;
}
.search-icon { position: absolute; left: 10px; top: 50%; transform: translateY(-50%); color: #475569; pointer-events: none; }
.search-input {
  width: 100%; background: rgba(255,255,255,0.06); border: 1px solid rgba(255,255,255,0.1);
  border-radius: 8px; padding: 7px 32px; font-size: 13px; color: #e2e8f0; outline: none; transition: border-color .15s;
}
.search-input::placeholder { color: #334155; }
.search-input:focus { border-color: rgba(96,165,250,0.5); }
.search-clear {
  position: absolute; right: 8px; top: 50%; transform: translateY(-50%);
  background: none; border: none; cursor: pointer; color: #475569; padding: 2px; display: flex; align-items: center;
}
.search-clear:hover { color: #94a3b8; }

.list-toggle-btn {
  display: flex; align-items: center; gap: 6px;
  padding: 6px 12px; border-radius: 8px;
  background: rgba(255,255,255,0.06); border: 1px solid rgba(255,255,255,0.1);
  color: #64748b; font-size: 12px; font-weight: 500; cursor: pointer;
  transition: all .15s; flex-shrink: 0;
}
.list-toggle-btn:hover { color: #94a3b8; border-color: rgba(255,255,255,0.18); }
.list-toggle-btn.active { background: rgba(96,165,250,0.15); color: #93c5fd; border-color: rgba(96,165,250,0.3); }

/* ── Body ── */
.archive-body {
  flex: 1;
  display: flex;
  overflow: hidden;
  min-height: 0;
}

/* ── Graph ── */
.graph-container { flex: 1; position: relative; overflow: hidden; min-width: 0; }
.archive-canvas { width: 100%; height: 100%; cursor: grab; display: block; }
.archive-canvas:active { cursor: grabbing; }

.graph-legend {
  position: absolute; bottom: 14px; left: 14px;
  display: flex; align-items: center; gap: 10px; flex-wrap: wrap;
  background: rgba(15,23,42,0.75); backdrop-filter: blur(8px);
  border: 1px solid rgba(255,255,255,0.07); border-radius: 8px;
  padding: 7px 12px; font-size: 11px; color: #64748b;
}
.legend-item { display: flex; align-items: center; gap: 5px; }
.legend-dot { width: 9px; height: 9px; border-radius: 50%; flex-shrink: 0; }
.hub-dot { background: #60a5fa; }
.doc-dot { background: #1e3a8a; border: 1px solid #60a5fa; }
.person-dot { background: #7c3aed; border: 1px solid #a78bfa; transition: opacity .2s; }
.person-toggle {
  background: none; border: none; cursor: pointer; color: #64748b; font-size: 11px; padding: 0;
  transition: color .15s;
}
.person-toggle:hover { color: #a78bfa; }
.legend-sep { width: 1px; height: 14px; background: rgba(255,255,255,0.08); }
.legend-hint { opacity: 0.55; font-size: 10px; }

/* ── List Panel ── */
.list-panel {
  width: 0;
  overflow: hidden;
  transition: width 0.28s ease;
  background: #0a0f1e;
  border-left: 1px solid rgba(255,255,255,0.06);
  flex-shrink: 0;
}
.list-panel.open { width: 340px; }
.list-panel-inner {
  width: 340px;
  height: 100%;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
}
.list-panel-inner::-webkit-scrollbar { width: 4px; }
.list-panel-inner::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.08); border-radius: 2px; }
.list-panel-header {
  display: flex; align-items: center; justify-content: space-between;
  padding: 14px 16px 10px;
  border-bottom: 1px solid rgba(255,255,255,0.06);
  flex-shrink: 0;
}
.list-panel-title { font-size: 13px; font-weight: 600; color: #94a3b8; }
.list-count { font-size: 11px; color: #334155; }

.meeting-groups { padding: 8px; display: flex; flex-direction: column; gap: 5px; }
.meeting-group {
  background: rgba(255,255,255,0.03); border: 1px solid rgba(255,255,255,0.07);
  border-radius: 8px; overflow: hidden;
}
.group-header {
  display: flex; align-items: center; justify-content: space-between;
  padding: 10px 12px; cursor: pointer; transition: background .15s;
}
.group-header:hover { background: rgba(255,255,255,0.04); }
.group-header-left { display: flex; align-items: center; gap: 8px; min-width: 0; }
.group-dot { width: 7px; height: 7px; background: #60a5fa; border-radius: 50%; flex-shrink: 0; }
.group-title { font-size: 13px; font-weight: 600; color: #e2e8f0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.group-meta-right { display: flex; align-items: center; gap: 6px; flex-shrink: 0; }
.group-count { font-size: 11px; color: #334155; }
.group-body { border-top: 1px solid rgba(255,255,255,0.05); padding: 8px 12px; display: flex; flex-direction: column; gap: 8px; }

.doc-section { display: flex; flex-direction: column; gap: 3px; }
.doc-section-label {
  font-size: 10px; font-weight: 600; color: #334155;
  text-transform: uppercase; letter-spacing: .06em; margin-bottom: 3px;
}
.doc-item {
  display: flex; align-items: center; gap: 8px;
  padding: 6px 8px; border-radius: 5px;
  background: rgba(255,255,255,0.02); border: 1px solid rgba(255,255,255,0.05);
  transition: background .15s;
}
.doc-item:hover { background: rgba(255,255,255,0.05); }
.doc-icon {
  width: 24px; height: 24px; border-radius: 5px;
  display: flex; align-items: center; justify-content: center; flex-shrink: 0;
}
.minutes-icon { background: rgba(59,130,246,0.2); color: #60a5fa; }
.report-icon { background: rgba(16,185,129,0.2); color: #34d399; }
.doc-info { flex: 1; min-width: 0; }
.doc-name { font-size: 12px; color: #cbd5e1; font-weight: 500; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.doc-meta { font-size: 10px; color: #334155; margin-top: 1px; }
.doc-actions { display: flex; align-items: center; gap: 4px; flex-shrink: 0; }
.doc-btn {
  display: flex; align-items: center;
  background: rgba(255,255,255,0.06); border: 1px solid rgba(255,255,255,0.09);
  border-radius: 4px; padding: 3px 8px; font-size: 11px; color: #64748b;
  cursor: pointer; transition: all .15s; white-space: nowrap;
}
.doc-btn:hover { background: rgba(96,165,250,0.15); color: #93c5fd; border-color: rgba(96,165,250,0.3); }
.icon-btn { padding: 3px 6px; }

/* Member chips */
.member-chips { display: flex; flex-wrap: wrap; gap: 4px; }
.member-chip {
  display: flex; align-items: center; gap: 5px;
  background: rgba(124,58,237,0.15); border: 1px solid rgba(124,58,237,0.25);
  border-radius: 20px; padding: 3px 8px 3px 4px;
}
.member-avatar {
  width: 18px; height: 18px; border-radius: 50%;
  background: rgba(124,58,237,0.5); color: #fff;
  font-size: 10px; font-weight: 700;
  display: flex; align-items: center; justify-content: center; flex-shrink: 0;
}
.member-name { font-size: 11px; color: #c4b5fd; }
.member-role {
  font-size: 10px; font-weight: 600; padding: 1px 5px; border-radius: 99px;
}
.role-admin { background: rgba(251,191,36,0.2); color: #fbbf24; }
.role-presenter { background: rgba(96,165,250,0.15); color: #60a5fa; }

.empty-state { text-align: center; padding: 40px 16px; color: #334155; font-size: 13px; }
</style>
