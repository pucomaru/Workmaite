<script setup>
import { onBeforeUnmount, onMounted, ref } from 'vue'
import LoginPopup from '../components/LoginPopup.vue'
import RegisterPopup from '../components/RegisterPopup.vue'
import { useThemeStore } from '../stores/theme'

const themeStore = useThemeStore() // 주/야간 토글 — 헤더와 동일 store 재사용
const showLogin = ref(false)
const showRegister = ref(false)
function openLogin() {
  showRegister.value = false
  showLogin.value = true
}
function openRegister() {
  showLogin.value = false
  showRegister.value = true
}
function closeModals() {
  showLogin.value = false
  showRegister.value = false
}

// ─── 3D Graph (히어로 배경 — 서비스가 만드는 '연결된 회의 지식'을 설명 없이 보여준다) ───
const canvasRef = ref(null)
let animId = null
let ctx = null

const NODE_COUNT = 24

function buildGraph() {
  const nodes = []
  const hubs = ['경영전략', '전략기획', '회의록', '의사결정', '아젠다', '회사', '보고서'].map(
    (label, i, arr) => {
      const phi = (i / arr.length) * Math.PI * 2
      return {
        label,
        type: 'hub',
        x: Math.cos(phi) * 120,
        y: Math.sin(phi) * 70,
        z: (Math.random() - 0.5) * 60,
      }
    },
  )
  nodes.push(...hubs)
  const docLabels = [
    '회의록 1',
    '보고서 A',
    '회의록 2',
    '보고서 B',
    '의사결정',
    '회의록 3',
    '분석보고서',
    '회의록 4',
    '보고서 C',
    '회의록 5',
    '회의록 6',
    '보고서 D',
    '회의록 7',
    '보고서 E',
    '요약본',
    '회의록 8',
    '보고서 F',
  ]
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
  for (let i = 0; i < hubs.length; i++) edges.push([i, (i + 1) % hubs.length])
  for (let i = hubs.length; i < nodes.length; i++) {
    const hubIdx = Math.floor(Math.random() * hubs.length)
    edges.push([hubIdx, i])
    if (Math.random() > 0.6) {
      edges.push([i, (hubIdx + 1 + Math.floor(Math.random() * (hubs.length - 1))) % hubs.length])
    }
  }
  return { nodes, edges }
}

const graph = buildGraph()
let rotX = 0.15
let rotY = 0
const autoRotY = 0.0022

function project(x, y, z, w, h) {
  const cosX = Math.cos(rotX),
    sinX = Math.sin(rotX)
  const cosY = Math.cos(rotY),
    sinY = Math.sin(rotY)
  const x1 = cosY * x + sinY * z
  const z1 = -sinY * x + cosY * z
  const y2 = cosX * y - sinX * z1
  const z2 = sinX * y + cosX * z1
  const fov = 500
  const scale = fov / (fov + z2 + 300)
  return { sx: w / 2 + x1 * scale, sy: h / 2 + y2 * scale, scale, z: z2 }
}

function drawGraph(canvas) {
  const w = canvas.offsetWidth,
    h = canvas.offsetHeight
  ctx.clearRect(0, 0, w, h)
  const projected = graph.nodes.map(n => ({
    ...project(n.x, n.y, n.z, w, h),
    type: n.type,
    label: n.label,
  }))
  const order = projected.map((_, i) => i).sort((a, b) => projected[a].z - projected[b].z)

  graph.edges.forEach(([a, b]) => {
    const pa = projected[a],
      pb = projected[b]
    const alpha = Math.max(0.04, Math.min(0.28, (pa.scale + pb.scale) / 2.4))
    ctx.beginPath()
    ctx.moveTo(pa.sx, pa.sy)
    ctx.lineTo(pb.sx, pb.sy)
    ctx.strokeStyle = `rgba(147,197,253,${alpha})`
    ctx.lineWidth = 0.8
    ctx.stroke()
  })

  order.forEach(i => {
    const p = projected[i]
    if (p.type === 'hub') {
      const r = 18 * p.scale
      const grad = ctx.createRadialGradient(p.sx, p.sy, 0, p.sx, p.sy, r)
      grad.addColorStop(0, `rgba(251,191,36,${0.8 * p.scale})`)
      grad.addColorStop(1, `rgba(245,158,11,${0.35 * p.scale})`)
      ctx.beginPath()
      ctx.arc(p.sx, p.sy, r, 0, Math.PI * 2)
      ctx.fillStyle = grad
      ctx.fill()
      ctx.strokeStyle = `rgba(253,230,138,${0.6 * p.scale})`
      ctx.lineWidth = 1.5 * p.scale
      ctx.stroke()
      if (p.scale > 0.6) {
        ctx.fillStyle = `rgba(255,255,255,${0.9 * p.scale})`
        ctx.font = `bold ${Math.round(9 * p.scale)}px sans-serif`
        ctx.textAlign = 'center'
        ctx.textBaseline = 'middle'
        ctx.fillText(graph.nodes[i].label, p.sx, p.sy)
      }
    } else {
      const r = 8 * p.scale
      ctx.beginPath()
      ctx.arc(p.sx, p.sy, r, 0, Math.PI * 2)
      ctx.fillStyle = `rgba(96,165,250,${0.6 * p.scale})`
      ctx.fill()
      ctx.strokeStyle = `rgba(147,197,253,${0.4 * p.scale})`
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
  drawGraph(canvas)
  animId = requestAnimationFrame(animate)
}

let ro = null
onMounted(() => {
  if (themeStore.nightMode) themeStore.toggle()
  const canvas = canvasRef.value
  ctx = canvas.getContext('2d')
  resize(canvas)
  ro = new ResizeObserver(() => resize(canvas))
  ro.observe(canvas)
  animate()
})
onBeforeUnmount(() => {
  cancelAnimationFrame(animId)
  ro?.disconnect()
})

// ─── 콘텐츠 데이터 ───────────────────────────────────────────
// 문제 제기 — 사용자가 이미 겪고 있는 상황
const pains = [
  {
    icon: 'bi bi-pencil-square',
    title: '회의록 정리에 또 한 시간',
    desc: '회의가 끝나면 녹취를 \n다시 듣고 받아 적는 일이 시작됩니다. \n회의록 작성이 또 하나의 업무가 됩니다.',
  },
  {
    icon: 'bi bi-chat-left-dots',
    title: '"그거 누가 하기로 했죠?"',
    desc: '회의에서 정한 일들이 메신저와 메일에 흩어집니다.\n다음 회의에서 같은 얘기를 반복합니다.',
  },
  {
    icon: 'bi bi-folder2-open',
    title: '"회의에서 무슨 말 했더라?"',
    desc: '지난 보고서, 그때 그 회의…\n분명 기억 속에 있지만 정리가 안돼요.',
  },
]

// 해결 방법 — 회의 전·중·후 흐름
const steps = [
  {
    num: '01',
    phase: '회의 전',
    title: '회의 아젠다 추출',
    desc: '회의체별로 아젠다를 관리하고, AI가 지난 회의록과 보고서에서 다음 안건을 추출해 제안해드릴게요.',
  },
  {
    num: '02',
    phase: '회의 중',
    title: '회의 지원',
    desc: 'AI로 다국어 음성을 인식하고, 챗봇을 통해 실시간 도움을 드려요. \n또, 회의가 끝나면 AI가 회의록 초안을 만들어드릴게요.',
  },
  {
    num: '03',
    phase: '회의 후',
    title: '회의록 작성 후속 아젠다 추출',
    desc: '회의록 작성은 AI에게 맡기세요. \n다음 회의 아젠다 걱정도 하지 마세요.',
  },
  {
    num: '04',
    phase: '그 이후',
    title: '회의체 전반을 이해하고 있어요',
    desc: 'AI가 회의체 전반의 정보를 이해하고 있으니 어떤 것이든 물어보세요.',
  },
]

// 관점 — AI 중심 · 일하는 방식 재설계 · 데이터 가치
const visions = [
  {
    icon: 'bi bi-cpu',
    title: 'AI가 프로세스와 의사결정의 중심에',
    desc: '아젠다 배정부터 회의록 작성, 보고서 검토까지! \nAI가 회의 프로세스 전반에 개입해 더 빠르고 근거 있는 의사결정을 돕습니다.',
  },
  {
    icon: 'bi bi-arrow-repeat',
    title: 'AI가 일하는 방식을 재설계합니다',
    desc: '받아 적고, 정리하고, 준비하는 시간이 사라집니다. 사람은 논의와 결정에 집중하고, 반복 업무는 AI의 일이 됩니다.',
  },
  {
    icon: 'bi bi-database',
    title: '데이터는 가치 창출의 핵심입니다',
    desc: '흩어지면 사라질 회의 기록이 지식 그래프로 쌓여 조직의 데이터 자산이 되고, 다음 의사결정의 근거가 됩니다.',
  },
]


// 처리 흐름 — 녹음부터 아카이브까지
const flow = [
  { icon: 'bi bi-mic-fill', title: '회의 녹음', sub: '실시간 발화 기록' },
  { icon: 'bi bi-journal-text', title: 'AI 회의록 초안', sub: '요약·후속 아젠다 발굴' },
  { icon: 'bi bi-person-check-fill', title: '검토·승인', sub: '사람이 최종 확정' },
  { icon: 'bi bi-diagram-3-fill', title: '연결·아카이빙', sub: '새로운 가치 창출' },
]

// 신뢰 요소 — 과장된 수치 대신 실제 작동 방식
const trustItems = [
  { icon: 'bi bi-mic', label: '실시간 발화 기록 & AI 채팅' },
  { icon: 'bi bi-journal-text', label: 'AI 회의록 생성' },
  { icon: 'bi bi-list-check', label: 'AI 기반 아젠다 추출·배정' },
  { icon: 'bi bi-diagram-3', label: '회의체 운영 암묵지 아카이빙' },
]
</script>

<template>
  <div class="landing-page">
    <!-- Navbar -->
    <nav class="landing-nav">
      <div class="container nav-inner">
        <img src="../assets/workmaite-logo-white.png" class="nav-logo-img" alt="Workma!te" />
        <div class="nav-actions">
          <button class="btn-nav-ghost" @click="openLogin">로그인</button>
          <button class="btn-cta sm" @click="openRegister">회원가입</button>
        </div>
      </div>
    </nav>

    <!-- ── Hero: 첫 화면에서 '무엇·누구·왜'를 모두 보여준다 ── -->
    <section class="hero">
      <canvas ref="canvasRef" class="hero-canvas"></canvas>
      <div class="hero-content container">
        <!-- 누구를 위한 것인지 -->
        <span class="hero-badge">회의체 운영 Agent</span>
        <span class="hero-badge">AI Archive Link Platform</span>

        <!-- 왜 봐야 하는지 (결과 중심 헤드라인) -->
        <h1 class="hero-title">
          회의만 하세요
          <span class="accent">나머지는 워크메이트가 해드릴게요</span>
        </h1>

        <!-- 무엇인지 (한 문장) -->
        <p class="hero-sub">
          AI를 중심으로 설계된 워크메이트는 회의를 기록해 회의록을 만들고, <br />
          새로운 아젠다를 발굴하고, <br />
          모든 기록을 하나의 지식 그래프로 연결합니다.
        </p>

        <!-- CTA: 행동이 아니라 행동 이후의 결과 -->
        <div class="hero-cta">
          <button class="btn-ghost-lg" @click="openLogin">로그인</button>
          <button class="btn-cta lg" @click="openRegister">
            가입하고 시작하기 <i class="bi bi-arrow-right ms-1"></i>
          </button>
        </div>

        <!-- 신뢰 요소: 실제 작동 방식 칩 -->
        <div class="hero-chips">
          <span v-for="t in trustItems" :key="t.label" class="hero-chip">
            <i :class="t.icon"></i>{{ t.label }}
          </span>
        </div>
      </div>
      <div class="hero-fade"></div>
    </section>

    <!-- ── 1. 문제 제기: 사용자의 상황을 그대로 ── -->
    <section class="section pains-section">
      <div class="container">
        <p class="section-eyebrow">아직도 회의 후 정리에 시간을 쓰고 있나요?</p>
        <h2 class="section-title">회의가 끝나면, 업무도 끝나야죠</h2>
        <div class="pains-grid">
          <div v-for="p in pains" :key="p.title" class="pain-card">
            <i :class="p.icon" class="pain-icon"></i>
            <h3 class="pain-title">{{ p.title }}</h3>
            <p class="pain-desc">{{ p.desc }}</p>
          </div>
        </div>
      </div>
    </section>

    <!-- ── 관점: AI 중심 · 방식 재설계 · 데이터 가치 ── -->
    <section class="section vision-section">
      <div class="container">
        <p class="section-eyebrow">회의체 플랫폼 워크메이트</p>
        <h2 class="section-title">AI를 중심에 두면 일하는 방식이 달라집니다</h2>
        <div class="vision-grid">
          <div v-for="v in visions" :key="v.title" class="vision-card">
            <i :class="v.icon" class="vision-icon"></i>
            <h3 class="vision-title">{{ v.title }}</h3>
            <p class="vision-desc">{{ v.desc }}</p>
          </div>
        </div>
      </div>
    </section>

    <!-- ── 2. 해결 방법: 회의 전·중·후 흐름 ── -->
    <section class="section steps-section">
      <div class="container">
        <p class="section-eyebrow light">일하는 방식의 재설계</p>
        <h2 class="section-title light">회의체의 전과정을 통째로 맡습니다</h2>
        <div class="steps-grid">
          <div v-for="s in steps" :key="s.num" class="step-card">
            <div class="step-head">
              <span class="step-num">{{ s.num }}</span>
              <span class="step-phase">{{ s.phase }}</span>
            </div>
            <h3 class="step-title">{{ s.title }}</h3>
            <p class="step-desc">{{ s.desc }}</p>
          </div>
        </div>
      </div>
    </section>

    <!-- ── CTA ── -->
    <section class="section cta-section">
      <div class="container text-center">
        <h2 class="cta-title">이제는 회의만 하세요</h2>
        <p class="cta-sub">회의 내용을 준비하고, 받아 적고, 정리하는 일은 워크메이트에서 하세요</p>
        <button class="btn-cta lg" @click="openRegister">
          시작하기 <i class="bi bi-arrow-right ms-1"></i>
        </button>
      </div>
    </section>

    <!-- Footer -->
    <footer class="landing-footer">
      <div class="container footer-inner">
        <span class="footer-brand">Workmaite</span>
        <span>© 2026 — 회의체 운영 AI 워크스페이스</span>
      </div>
    </footer>

    <Teleport to="body">
      <Transition name="modal-fade">
        <div v-if="showLogin" class="popup-backdrop">
          <div class="popup-box">
            <button class="popup-close" @click="closeModals"><i class="bi bi-x-lg"></i></button>
            <LoginPopup @close="closeModals" @go-register="openRegister" />
          </div>
        </div>
      </Transition>
    </Teleport>

    <Teleport to="body">
      <Transition name="modal-fade">
        <div v-if="showRegister" class="popup-backdrop">
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
.landing-page {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
  background: var(--bg-card);
}
.container {
  width: 100%;
  max-width: 1080px;
  margin: 0 auto;
  padding: 0 24px;
}

/* ── Nav ── */
.landing-nav {
  position: fixed;
  padding: 0px;
  top: 0;
  left: 0;
  right: 0;
  z-index: 100;
  background: rgba(15, 23, 42, 0.55);
  backdrop-filter: blur(10px);
  border-bottom: 1px solid var(--white-08);
  height: var(--header-h);
  display: flex;
  align-items: center;
}
.nav-inner {
  padding: 2px 16px 0px;
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.nav-logo-img {
  height: 16px;
  width: auto;
}
.nav-actions {
  height: 34px;
  display: flex;
  align-items: center;
  gap: 10px;
}
.btn-nav-ghost {
  height: 34px;
  background: none;
  border: 1px solid var(--white-18);
  border-radius: 8px;
  color: var(--dark-text);
  font-size: 12px;
  padding: 7px 16px;
  cursor: pointer;
  transition: background 0.15s;
}
.btn-nav-ghost:hover {
  background: var(--white-08);
}
.btn-nav-theme {
  height: 34px;
  background: none;
  border: 1px solid var(--white-18);
  border-radius: 8px;
  color: var(--dark-text);
  font-size: 16px;
  line-height: 1;
  padding: 6px 12px;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  transition: background 0.15s;
}
.btn-nav-theme:hover {
  height: 34px;
  background: var(--white-08);
}

/* ── CTA 버튼 (공통) ── */
.btn-cta {
  background: #fbbf24;
  color: #1f2937;
  border: none;
  border-radius: 10px;
  font-weight: 700;
  cursor: pointer;
  white-space: nowrap;
  transition:
    transform 0.15s,
    box-shadow 0.15s,
    background 0.15s;
}
.btn-cta:hover {
  background: #f59e0b;
}
.btn-cta.sm {
  height: 34px;
  font-size: 12px;
  padding: 8px 16px;
}
.btn-cta.lg {
  font-size: 16px;
  padding: 15px 32px;
}
.btn-ghost-lg {
  background: none;
  border: 1px solid var(--white-18);
  border-radius: 10px;
  color: var(--dark-text);
  font-size: 16px;
  padding: 15px 28px;
  cursor: pointer;
  transition: background 0.15s;
}
.btn-ghost-lg:hover {
  background: var(--white-08);
}

/* ── Hero ── */
.hero {
  position: relative;
  min-height: 100vh;
  display: flex;
  align-items: center;
  background: linear-gradient(135deg, var(--dark-bg) 0%, var(--primary) 55%, var(--dark-bg) 100%);
  overflow: hidden;
}
.hero-canvas {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  opacity: 0.55;
}
.hero-fade {
  position: absolute;
  left: 0;
  right: 0;
  bottom: 0;
  height: 120px;
  background: linear-gradient(transparent, rgba(10, 15, 30, 0.55));
  pointer-events: none;
}
.hero-content {
  position: relative;
  z-index: 1;
  padding-top: 100px;
  padding-bottom: 60px;
}
.hero-badge {
  display: inline-block;
  background: var(--white-08);
  border: 1px solid var(--white-15);
  color: var(--accent-soft);
  font-size: 12px;
  font-weight: 600;
  border-radius: 99px;
  padding: 7px 16px;
  margin-bottom: 22px;
  backdrop-filter: blur(6px);
}
.hero-title {
  font-size: clamp(2rem, 4.6vw, 3.4rem);
  font-weight: 900;
  line-height: 1.25;
  letter-spacing: -0.02em;
  color: #fff;
  margin-bottom: 20px;
  text-shadow: 0 2px 24px rgba(15, 23, 42, 0.6);
}
.hero-title .accent {
  display: block;
  color: #fbbf24;
}
.hero-sub {
  max-width: 640px;
  font-size: clamp(1rem, 1.6vw, 1.15rem);
  color: rgba(255, 255, 255, 0.8);
  line-height: 1.75;
  margin-bottom: 34px;
  text-shadow: 0 1px 12px rgba(15, 23, 42, 0.6);
}
.hero-cta {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
  align-items: center;
}
.hero-cta-note {
  font-size: 12.5px;
  color: rgba(255, 255, 255, 0.55);
  margin: 12px 0 0 2px;
}
.hero-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 44px;
}
.hero-chip {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  background: var(--white-06);
  border: 1px solid var(--white-10);
  color: rgba(255, 255, 255, 0.85);
  font-size: 12.5px;
  border-radius: 8px;
  padding: 7px 12px;
  backdrop-filter: blur(6px);
}
.hero-chip i {
  color: var(--accent-soft);
}

/* ── 공통 섹션 ── */
.section {
  padding: 88px 0;
}
.section-eyebrow {
  font-size: 13.5px;
  font-weight: 700;
  color: var(--accent);
  margin-bottom: 10px;
  letter-spacing: 0.02em;
}
.section-eyebrow.light {
  color: #fbbf24;
}
.section-title {
  font-size: clamp(1.5rem, 3vw, 2.1rem);
  font-weight: 800;
  color: var(--text);
  line-height: 1.35;
  margin-bottom: 40px;
  letter-spacing: -0.01em;
  max-width: 720px;
}
.section-title.light {
  color: #fff;
}

/* ── 1. 문제 제기 ── */
.pains-section {
  background: var(--bg-card);
}
.pains-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 20px;
}
.pain-card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 14px;
  padding: 26px 24px;
}
.pain-icon {
  font-size: 22px;
  color: var(--warning-text);
  display: block;
  margin-bottom: 14px;
}
.pain-title {
  font-size: 16.5px;
  font-weight: 700;
  color: var(--text);
  margin-bottom: 8px;
}
.pain-desc {
  font-size: 13.5px;
  color: var(--text-muted);
  line-height: 1.7;
  margin: 0;
  white-space: pre-line;
}

/* ── 관점 (AI 중심 · 방식 재설계 · 데이터 가치) ── */
.vision-section {
  background: var(--surface);
}
.vision-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 20px;
}
.vision-card {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 14px;
  padding: 26px 24px;
}
.vision-icon {
  font-size: 22px;
  color: var(--accent);
  display: block;
  margin-bottom: 14px;
}
.vision-title {
  font-size: 16px;
  font-weight: 700;
  color: var(--text);
  margin-bottom: 8px;
  line-height: 1.45;
}
.vision-desc {
  font-size: 13.5px;
  color: var(--text-muted);
  line-height: 1.7;
  margin: 0;
  white-space: pre-line;
}

/* ── 2. 해결 방법 ── */
.steps-section {
  background: linear-gradient(160deg, var(--dark-bg), var(--primary));
}
.steps-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
}
.step-card {
  background: var(--white-05);
  border: 1px solid var(--white-10);
  border-radius: 14px;
  padding: 24px 20px;
  transition:
    transform 0.2s,
    background 0.2s;
}
.step-card:hover {
  transform: translateY(-4px);
  background: var(--white-08);
}
.step-head {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 16px;
}
.step-num {
  font-size: 12px;
  font-weight: 800;
  color: #fbbf24;
}
.step-phase {
  font-size: 11.5px;
  font-weight: 700;
  color: var(--accent-soft);
  background: var(--white-06);
  border-radius: 99px;
  padding: 3px 10px;
}
.step-title {
  font-size: 15.5px;
  font-weight: 700;
  color: #fff;
  line-height: 1.45;
  margin-bottom: 10px;
}
.step-desc {
  font-size: 12px;
  color: rgba(255, 255, 255, 0.7);
  line-height: 1.7;
  margin: 0;
  white-space: pre-line;
}

/* ── 3. 신뢰 (다른 섹션과 동일한 카드 그리드 + 하단 플로우 스트립) ── */
.trust-section {
  background: var(--surface);
}
.trust-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 20px;
  margin-bottom: 24px;
}
.trust-card {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 14px;
  padding: 26px 24px;
}
.trust-icon {
  font-size: 22px;
  color: var(--success);
  display: block;
  margin-bottom: 14px;
}
.trust-title {
  font-size: 16px;
  font-weight: 700;
  color: var(--text);
  margin-bottom: 8px;
}
.trust-desc {
  font-size: 13.5px;
  color: var(--text-muted);
  line-height: 1.7;
  margin: 0;
}
/* 처리 흐름 스트립 */
.flow-strip {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 14px;
  padding: 18px 26px;
}
.flow-item {
  display: flex;
  align-items: center;
  gap: 12px;
}
.flow-item > i {
  width: 38px;
  height: 38px;
  border-radius: 10px;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--accent-bg);
  color: var(--accent);
  font-size: 20px;
}
.flow-item b {
  display: block;
  font-size: 13.5px;
  color: var(--text);
  line-height: 1.4;
}
.flow-item span {
  display: block;
  font-size: 11.5px;
  color: var(--text-muted);
}
.flow-arrow {
  color: var(--dark-muted);
  font-size: 16px;
}

/* ── CTA ── */
.cta-section {
  background: linear-gradient(135deg, var(--primary), #1e40af);
}
.cta-title {
  font-size: clamp(1.5rem, 3vw, 2.1rem);
  font-weight: 800;
  color: #fff;
  margin-bottom: 10px;
}
.cta-sub {
  font-size: 16px;
  color: rgba(255, 255, 255, 0.7);
  margin-bottom: 28px;
}
.text-center {
  text-align: center;
}

/* ── Footer ── */
.landing-footer {
  background: var(--surface);
  border-top: 1px solid var(--border);
  padding: 22px 0;
  margin-top: auto;
}
.footer-inner {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  font-size: 12.5px;
  color: var(--text-muted);
}
.footer-brand {
  font-weight: 800;
  color: var(--primary);
}

/* ── Popup (로그인/회원가입) ── */
.popup-backdrop {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.55);
  backdrop-filter: blur(4px);
  z-index: 2000;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 20px;
}
.popup-box {
  position: relative;
  width: 100%;
  max-width: 460px;
  max-height: 90vh;
  overflow-y: auto;
  background: var(--bg-card);
  border-radius: 20px;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.25);
}
.popup-close {
  position: absolute;
  top: 14px;
  right: 16px;
  z-index: 10;
  background: none;
  border: none;
  font-size: 20px;
  color: var(--dark-muted);
  cursor: pointer;
  padding: 4px;
  line-height: 1;
  transition: color 0.15s;
}
.popup-close:hover {
  color: var(--text-muted);
}
.modal-fade-enter-from,
.modal-fade-leave-to {
  opacity: 0;
}
.modal-fade-enter-from .popup-box,
.modal-fade-leave-to .popup-box {
  transform: scale(0.95) translateY(8px);
}

/* ── 반응형 ── */
@media (max-width: 920px) {
  .steps-grid {
    grid-template-columns: repeat(2, 1fr);
  }
  .trust-grid {
    grid-template-columns: 1fr;
  }
}
@media (max-width: 680px) {
  .pains-grid,
  .steps-grid,
  .vision-grid {
    grid-template-columns: 1fr;
  }
  .flow-strip {
    flex-direction: column;
    align-items: flex-start;
  }
  .flow-arrow {
    display: none;
  }
  .section {
    padding: 64px 0;
  }
  .hero-content {
    padding-top: 120px;
  }
}
</style>
