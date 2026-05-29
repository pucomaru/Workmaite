<script setup>
import { ref, onMounted, onBeforeUnmount } from 'vue'
import { useRouter } from 'vue-router'
import LoginPopup from '../components/LoginPopup.vue'
import RegisterPopup from '../components/RegisterPopup.vue'

const router = useRouter()
const showLogin = ref(false)
const showRegister = ref(false)
function openLogin() { showRegister.value = false; showLogin.value = true }
function openRegister() { showLogin.value = false; showRegister.value = true }
function closeModals() { showLogin.value = false; showRegister.value = false }

// ─── 3D Graph ───────────────────────────────────────────────
const canvasRef = ref(null)
const heroRef = ref(null)
const zoomed = ref(false)
let animId = null
let ctx = null

// Graph data: nodes + edges
const NODE_COUNT = 24
const EDGE_COUNT = 36

function buildGraph() {
  const nodes = []
  // Center hub nodes (meeting nodes)
  const hubs = [
    { label: '전략기획', type: 'hub' },
    { label: '운영위원회', type: 'hub' },
    { label: '개발팀', type: 'hub' },
    { label: '마케팅', type: 'hub' },
  ]
  hubs.forEach((h, i) => {
    const phi = (i / hubs.length) * Math.PI * 2
    nodes.push({
      ...h,
      x: Math.cos(phi) * 120,
      y: Math.sin(phi) * 70,
      z: (Math.random() - 0.5) * 60,
    })
  })
  // Leaf nodes (document nodes)
  const docLabels = ['회의록 1', '보고서 A', '회의록 2', '보고서 B', '의사결정', '회의록 3', '분석보고서', '회의록 4', '보고서 C', '회의록 5', '회의록 6', '보고서 D', '회의록 7', '보고서 E', '요약본', '회의록 8', '보고서 F', '회의록 9', '보고서 G', '회의록 10']
  for (let i = 0; i < NODE_COUNT - hubs.length; i++) {
    const phi = Math.random() * Math.PI * 2
    const theta = Math.random() * Math.PI
    const r = 160 + Math.random() * 80
    nodes.push({
      label: docLabels[i % docLabels.length],
      type: 'doc',
      x: r * Math.sin(theta) * Math.cos(phi),
      y: r * Math.sin(theta) * Math.sin(phi) * 0.6,
      z: r * Math.cos(theta),
    })
  }
  const edges = []
  // Hub-to-hub
  for (let i = 0; i < hubs.length; i++) {
    edges.push([i, (i + 1) % hubs.length])
  }
  // Hub-to-leaf
  for (let i = hubs.length; i < nodes.length; i++) {
    const hubIdx = Math.floor(Math.random() * hubs.length)
    edges.push([hubIdx, i])
    if (Math.random() > 0.6) {
      const otherHub = (hubIdx + 1 + Math.floor(Math.random() * (hubs.length - 1))) % hubs.length
      edges.push([i, otherHub])
    }
  }
  return { nodes, edges }
}

const graph = buildGraph()
let rotX = 0.15
let rotY = 0
const autoRotY = 0.003
let zoom = 1
let targetZoom = 1
let zoomCx = 0, zoomCy = 0

function project(x, y, z, w, h) {
  const cosX = Math.cos(rotX), sinX = Math.sin(rotX)
  const cosY = Math.cos(rotY), sinY = Math.sin(rotY)
  // Ry
  const x1 = cosY * x + sinY * z
  const y1 = y
  const z1 = -sinY * x + cosY * z
  // Rx
  const x2 = x1
  const y2 = cosX * y1 - sinX * z1
  const z2 = sinX * y1 + cosX * z1
  const fov = 500
  const scale = fov / (fov + z2 + 300)
  return {
    sx: w / 2 + x2 * scale,
    sy: h / 2 + y2 * scale,
    scale,
    z: z2,
  }
}

function drawGraph(canvas) {
  const w = canvas.offsetWidth, h = canvas.offsetHeight
  ctx.clearRect(0, 0, w, h)

  const projected = graph.nodes.map(n => ({
    ...project(n.x, n.y, n.z, w, h),
    type: n.type,
    label: n.label,
  }))

  // Sort by z for painter's algorithm
  const order = projected.map((_, i) => i).sort((a, b) => projected[a].z - projected[b].z)

  // Edges
  graph.edges.forEach(([a, b]) => {
    const pa = projected[a], pb = projected[b]
    const alpha = Math.max(0.05, Math.min(0.35, (pa.scale + pb.scale) / 2))
    ctx.beginPath()
    ctx.moveTo(pa.sx, pa.sy)
    ctx.lineTo(pb.sx, pb.sy)
    ctx.strokeStyle = `rgba(147,197,253,${alpha})`
    ctx.lineWidth = 0.8
    ctx.stroke()
  })

  // Nodes
  order.forEach(i => {
    const p = projected[i]
    if (p.type === 'hub') {
      const r = 18 * p.scale
      const grad = ctx.createRadialGradient(p.sx, p.sy, 0, p.sx, p.sy, r)
      grad.addColorStop(0, `rgba(251,191,36,${0.9 * p.scale})`)
      grad.addColorStop(1, `rgba(245,158,11,${0.4 * p.scale})`)
      ctx.beginPath()
      ctx.arc(p.sx, p.sy, r, 0, Math.PI * 2)
      ctx.fillStyle = grad
      ctx.fill()
      ctx.strokeStyle = `rgba(253,230,138,${0.7 * p.scale})`
      ctx.lineWidth = 1.5 * p.scale
      ctx.stroke()
      if (p.scale > 0.6) {
        ctx.fillStyle = `rgba(255,255,255,${p.scale})`
        ctx.font = `bold ${Math.round(9 * p.scale)}px sans-serif`
        ctx.textAlign = 'center'
        ctx.textBaseline = 'middle'
        ctx.fillText(graph.nodes[i].label, p.sx, p.sy)
      }
    } else {
      const r = 8 * p.scale
      ctx.beginPath()
      ctx.arc(p.sx, p.sy, r, 0, Math.PI * 2)
      ctx.fillStyle = `rgba(96,165,250,${0.7 * p.scale})`
      ctx.fill()
      ctx.strokeStyle = `rgba(147,197,253,${0.5 * p.scale})`
      ctx.lineWidth = 1
      ctx.stroke()
    }
  })
}

function resize(canvas) {
  const dpr = window.devicePixelRatio || 1
  canvas.width = canvas.offsetWidth * dpr
  canvas.height = canvas.offsetHeight * dpr
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
}

function animate() {
  const canvas = canvasRef.value
  if (!canvas) return
  rotY += autoRotY
  zoom += (targetZoom - zoom) * 0.06
  const dpr = window.devicePixelRatio || 1
  // Apply zoom on top of DPR scale (translate in CSS pixels, then scale)
  ctx.setTransform(
    zoom * dpr, 0, 0,
    zoom * dpr,
    zoomCx * (1 - zoom),
    zoomCy * (1 - zoom)
  )
  drawGraph(canvas)
  animId = requestAnimationFrame(animate)
}

function handleCanvasClick() {
  if (zoomed.value) return
  zoomed.value = true
  const canvas = canvasRef.value
  targetZoom = 4
  zoomCx = canvas.width / 2
  zoomCy = canvas.height / 2
  setTimeout(() => {
    heroRef.value?.scrollIntoView({ behavior: 'smooth' })
  }, 700)
}

let ro = null

onMounted(() => {
  const canvas = canvasRef.value
  ctx = canvas.getContext('2d')
  resize(canvas)
  ro = new ResizeObserver(() => { resize(canvas) })
  ro.observe(canvas)
  animate()
})

onBeforeUnmount(() => {
  cancelAnimationFrame(animId)
  ro?.disconnect()
})

const features = [
  { icon: 'bi bi-journal-text fs-4', title: '자동 회의록 생성', desc: '실시간 STT와 AI 요약으로 완성도 높은 회의록을 자동으로 작성합니다.', bg: '#dbeafe', color: '#1e40af' },
  { icon: 'bi bi-layout-text-window fs-4', title: '의제 관리', desc: '회의 의제를 체계적으로 관리하고 발제자료를 한 곳에서 공유합니다.', bg: '#d1fae5', color: '#065f46' },
  { icon: 'bi bi-check2-square fs-4', title: '태스크 추적', desc: '회의에서 결정된 Action Item을 자동 등록하고 완료 여부를 추적합니다.', bg: '#fef3c7', color: '#92400e' },
  { icon: 'bi bi-calendar3 fs-4', title: '일정 통합 관리', desc: '모든 회의 일정을 달력에서 한눈에 확인하고 관리합니다.', bg: '#ede9fe', color: '#5b21b6' },
  { icon: 'bi bi-robot fs-4', title: 'AI 에이전트 협업', desc: '전문화된 5개의 AI 에이전트가 회의의 각 단계에서 지원합니다.', bg: '#ffedd5', color: '#9a3412' },
]

</script>

<template>
  <div class="landing-page">

    <!-- Navbar -->
    <nav class="navbar navbar-expand-lg navbar-dark landing-nav">
      <div class="container">
        <a class="navbar-brand d-flex align-items-center gap-2" href="#">
          <div class="brand-icon">W</div>
          <span class="fw-bold fs-5">workma<span class="brand-accent">!</span>te</span>
        </a>
        <div class="ms-auto d-flex gap-2">
          <button class="btn btn-outline-light btn-sm px-3" @click="openLogin">로그인</button>
          <button class="btn btn-warning btn-sm px-3 fw-semibold" @click="openRegister">회원가입</button>
        </div>
      </div>
    </nav>

    <!-- ── 3D Graph Hero ──────────────────────────────── -->
    <section class="graph-hero" @click="handleCanvasClick">
      <canvas ref="canvasRef" class="graph-canvas"></canvas>

      <!-- overlay hint -->
      <div class="graph-overlay" :class="{ faded: zoomed }">
        <div class="graph-hint">
          <div class="hint-pulse"></div>
          <span>클릭하여 서비스 소개 보기</span>
        </div>
        <div class="graph-brand">workma<span class="brand-accent">!</span>te</div>
        <p class="graph-tagline">회의 지식이 연결되는 공간</p>
      </div>
    </section>

    <!-- ── Service Intro (revealed after zoom) ──────── -->
    <section ref="heroRef" class="hero-section" :class="{ visible: zoomed }">
      <div class="container text-center">
        <div class="hero-badge mb-3">
          <span class="badge rounded-pill bg-warning text-dark px-3 py-2">
            <i class="bi bi-stars me-1"></i>AI 기반 회의 운영 플랫폼
          </span>
        </div>
        <h1 class="hero-title mb-4">
          회의를 <span class="text-warning">스마트</span>하게,<br>
          결정을 <span class="text-warning">빠르게</span>
        </h1>
        <p class="hero-subtitle mb-5">
          AI 에이전트가 의제 준비부터 회의록 작성, 태스크 관리까지<br>
          모든 회의 프로세스를 자동화합니다.
        </p>
        <div class="d-flex gap-3 justify-content-center flex-wrap">
          <button class="btn btn-outline-light btn-lg px-5 py-3" @click="openLogin">
            로그인
          </button>
          <button class="btn btn-warning btn-lg fw-bold px-5 py-3" @click="openRegister">
            회원가입 <i class="bi bi-arrow-right ms-1"></i>
          </button>
        </div>
        <div class="hero-stats mt-5">
          <div class="stat-item">
            <span class="stat-num">85%</span>
            <span class="stat-label">회의 시간 단축</span>
          </div>
          <div class="stat-divider"></div>
          <div class="stat-item">
            <span class="stat-num">5개</span>
            <span class="stat-label">전문 AI 에이전트</span>
          </div>
          <div class="stat-divider"></div>
          <div class="stat-item">
            <span class="stat-num">100%</span>
            <span class="stat-label">자동 회의록 생성</span>
          </div>
        </div>
      </div>
    </section>

    <!-- Features -->
    <section class="features-section py-6">
      <div class="container">
        <div class="text-center mb-5">
          <h2 class="fw-bold fs-2 mb-2" style="color: var(--primary)">왜 workma!te인가요?</h2>
          <p class="text-muted">AI 에이전트들이 협업하여 회의의 모든 단계를 지원합니다</p>
        </div>
        <!-- <div class="row g-4">
          <div v-for="feat in features" :key="feat.title" class="col-md-6 col-lg-4">
            <div class="feature-card card h-100 p-4">
              <div class="feature-icon mb-3" :style="{ background: feat.bg }">
                <i :class="feat.icon" :style="{ color: feat.color }"></i>
              </div>
              <h5 class="fw-bold mb-2">{{ feat.title }}</h5>
              <p class="text-muted small mb-0">{{ feat.desc }}</p>
            </div>
          </div>
        </div> -->
      </div>
    </section>


    <!-- CTA -->
    <section class="cta-section text-center py-6">
      <div class="container">
        <h2 class="fw-bold fs-2 text-white mb-3">지금 바로 시작하세요</h2>
        <p class="text-white-50 mb-4 fs-6">무료로 가입하고 AI가 이끄는 스마트한 회의를 경험해보세요</p>
        <button class="btn btn-warning btn-lg fw-bold px-5 py-3" @click="openRegister">
          회원가입 <i class="bi bi-arrow-right ms-1"></i>
        </button>
      </div>
    </section>

    <!-- Footer -->
    <footer class="landing-footer py-4">
      <div class="container text-center text-muted small">
        <span class="fw-bold" style="color: var(--primary)">workmaite</span> © 2026 — AI Archive Link Platform
      </div>
    </footer>

    <Teleport to="body">
      <Transition name="modal-fade">
        <div v-if="showLogin" class="popup-backdrop" @click.self="closeModals">
          <div class="popup-box">
            <button class="popup-close" @click="closeModals"><i class="bi bi-x-lg"></i></button>
            <LoginPopup @close="closeModals" @go-register="openRegister" />
          </div>
        </div>
      </Transition>
    </Teleport>

    <Teleport to="body">
      <Transition name="modal-fade">
        <div v-if="showRegister" class="popup-backdrop" @click.self="closeModals">
          <div class="popup-box">
            <button class="popup-close" @click="closeModals"><i class="bi bi-x-lg"></i></button>
            <RegisterPopup @close="closeModals" @go-login="openLogin" />
          </div>
        </div>
      </Transition>
    </Teleport>
  </div>
</template>

<style scoped>
.landing-page { min-height: 100vh; display: flex; flex-direction: column; }

/* Nav */
.landing-nav {
  background: var(--primary);
  padding: 12px 0;
  position: sticky; top: 0; z-index: 100;
  box-shadow: 0 2px 8px rgba(0,0,0,.15);
}
.brand-icon {
  width: 32px; height: 32px;
  background: #f59e0b;
  border-radius: 8px;
  display: flex; align-items: center; justify-content: center;
  font-weight: 900; font-size: 16px; color: var(--primary);
}
.brand-accent { color: #f59e0b; }

/* ── 3D Graph Hero ── */
.graph-hero {
  position: relative;
  height: 100vh;
  background: linear-gradient(135deg, #0f172a 0%, #1e3a5f 50%, #0f172a 100%);
  cursor: pointer;
  overflow: hidden;
}
.graph-canvas {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
}
.graph-overlay {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  pointer-events: none;
  transition: opacity 0.8s ease;
}
.graph-overlay.faded { opacity: 0; }
.graph-brand {
  font-size: clamp(2.5rem, 6vw, 4.5rem);
  font-weight: 900;
  color: #fff;
  letter-spacing: -0.02em;
  text-shadow: 0 0 40px rgba(96,165,250,0.5);
}
.graph-tagline {
  font-size: 1.1rem;
  color: rgba(255,255,255,0.6);
  margin-top: 8px;
}
.graph-hint {
  position: absolute;
  bottom: 40px;
  display: flex;
  align-items: center;
  gap: 10px;
  color: rgba(255,255,255,0.5);
  font-size: 13px;
}
.hint-pulse {
  width: 10px; height: 10px;
  background: #60a5fa;
  border-radius: 50%;
  animation: pulse 1.8s ease-in-out infinite;
}
@keyframes pulse {
  0%, 100% { transform: scale(1); opacity: 0.7; }
  50% { transform: scale(1.5); opacity: 1; }
}

/* ── Hero Section (service intro) ── */
.hero-section {
  background: linear-gradient(135deg, var(--primary) 0%, #2d5282 50%, #1e3a5f 100%);
  color: #fff;
  padding: 100px 0 80px;
  opacity: 0;
  transform: translateY(30px);
  transition: opacity 0.8s ease 0.3s, transform 0.8s ease 0.3s;
}
.hero-section.visible { opacity: 1; transform: translateY(0); }
.hero-title {
  font-size: clamp(2rem, 5vw, 3.5rem);
  font-weight: 900;
  line-height: 1.2;
  letter-spacing: -0.02em;
}
.hero-subtitle { font-size: 1.1rem; color: rgba(255,255,255,.75); line-height: 1.7; }
.hero-stats {
  display: inline-flex;
  align-items: center;
  gap: 32px;
  background: rgba(255,255,255,.1);
  backdrop-filter: blur(8px);
  border: 1px solid rgba(255,255,255,.2);
  border-radius: 16px;
  padding: 20px 40px;
}
.stat-item { display: flex; flex-direction: column; align-items: center; }
.stat-num { font-size: 1.8rem; font-weight: 900; color: #fbbf24; line-height: 1; }
.stat-label { font-size: 0.75rem; color: rgba(255,255,255,.65); margin-top: 4px; }
.stat-divider { width: 1px; height: 40px; background: rgba(255,255,255,.2); }

/* Features */
.py-6 { padding-top: 80px; padding-bottom: 80px; }
.features-section { background: #fff; }
.feature-card { border: 1px solid var(--border) !important; transition: transform .2s, box-shadow .2s; }
.feature-card:hover { transform: translateY(-4px); box-shadow: var(--shadow-lg) !important; }
.feature-icon { width: 52px; height: 52px; border-radius: 12px; display: flex; align-items: center; justify-content: center; }


/* Popup */
.popup-backdrop { position: fixed; inset: 0; background: rgba(0,0,0,.55); backdrop-filter: blur(4px); z-index: 2000; display: flex; align-items: center; justify-content: center; padding: 20px; }
.popup-box { position: relative; width: 100%; max-width: 460px; max-height: 90vh; overflow-y: auto; background: #fff; border-radius: 20px; box-shadow: 0 20px 60px rgba(0,0,0,.25); }
.popup-close { position: absolute; top: 14px; right: 16px; z-index: 10; background: none; border: none; font-size: 18px; color: #94a3b8; cursor: pointer; padding: 4px; line-height: 1; transition: color .15s; }
.popup-close:hover { color: #475569; }
.modal-fade-enter-active, .modal-fade-leave-active { transition: opacity .2s, transform .2s; }
.modal-fade-enter-from, .modal-fade-leave-to { opacity: 0; }
.modal-fade-enter-from .popup-box, .modal-fade-leave-to .popup-box { transform: scale(.95) translateY(8px); }

/* CTA */
.cta-section { background: linear-gradient(135deg, var(--primary), #1e40af); }
.landing-footer { background: #f8fafc; border-top: 1px solid var(--border); margin-top: auto; }

@media (max-width: 768px) {
  .hero-stats { flex-wrap: wrap; gap: 16px; padding: 16px 24px; }
  .stat-divider { display: none; }
}
</style>
