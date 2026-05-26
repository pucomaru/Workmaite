<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import araImg from '../assets/agents/ara.png'
import gaonImg from '../assets/agents/gaon.png'
import hyeanImg from '../assets/agents/hyean.png'
import naonImg from '../assets/agents/naon.png'
import naruImg from '../assets/agents/naru.png'
import LoginPopup from '../components/LoginPopup.vue'
import RegisterPopup from '../components/RegisterPopup.vue'

const router = useRouter()

const showLogin = ref(false)
const showRegister = ref(false)

function openLogin() { showRegister.value = false; showLogin.value = true }
function openRegister() { showLogin.value = false; showRegister.value = true }
function closeModals() { showLogin.value = false; showRegister.value = false }

const features = [
  { icon: 'bi bi-journal-text fs-4', title: '자동 회의록 생성', desc: '실시간 STT와 AI 요약으로 완성도 높은 회의록을 자동으로 작성합니다.', bg: '#dbeafe', color: '#1e40af' },
  { icon: 'bi bi-layout-text-window fs-4', title: '의제 관리', desc: '회의 의제를 체계적으로 관리하고 발제자료를 한 곳에서 공유합니다.', bg: '#d1fae5', color: '#065f46' },
  { icon: 'bi bi-check2-square fs-4', title: '태스크 추적', desc: '회의에서 결정된 Action Item을 자동 등록하고 완료 여부를 추적합니다.', bg: '#fef3c7', color: '#92400e' },
  { icon: 'bi bi-newspaper fs-4', title: '카드뉴스 생성', desc: '회의 결과를 임원 보고용 카드뉴스로 자동 변환합니다.', bg: '#fce7f3', color: '#9d174d' },
  { icon: 'bi bi-calendar3 fs-4', title: '일정 통합 관리', desc: '모든 회의 일정을 달력에서 한눈에 확인하고 관리합니다.', bg: '#ede9fe', color: '#5b21b6' },
  { icon: 'bi bi-robot fs-4', title: 'AI 에이전트 협업', desc: '전문화된 5개의 AI 에이전트가 회의의 각 단계에서 지원합니다.', bg: '#ffedd5', color: '#9a3412' },
]

const agents = [
  { img: araImg,   name: '아라', role: '회의 진행' },
  { img: gaonImg,  name: '가온', role: '의제 분석' },
  { img: hyeanImg, name: '혜안', role: '인사이트' },
  { img: naonImg,  name: '나온', role: '회의록' },
  { img: naruImg,  name: '나루', role: '후속조치' },
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

    <!-- Hero Section -->
    <section class="hero-section">
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
          <button class="btn btn-warning btn-lg fw-bold px-5 py-3" @click="openRegister">
            무료로 시작하기 <i class="bi bi-arrow-right ms-1"></i>
          </button>
          <button class="btn btn-outline-light btn-lg px-5 py-3" @click="openLogin">
            로그인
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

    <!-- Features Section -->
    <section class="features-section py-6">
      <div class="container">
        <div class="text-center mb-5">
          <h2 class="fw-bold fs-2 mb-2" style="color: var(--primary)">왜 meetma!te인가요?</h2>
          <p class="text-muted">AI 에이전트들이 협업하여 회의의 모든 단계를 지원합니다</p>
        </div>
        <div class="row g-4">
          <div v-for="feat in features" :key="feat.title" class="col-md-6 col-lg-4">
            <div class="feature-card card h-100 p-4">
              <div class="feature-icon mb-3" :style="{ background: feat.bg }">
                <i :class="feat.icon" :style="{ color: feat.color }"></i>
              </div>
              <h5 class="fw-bold mb-2">{{ feat.title }}</h5>
              <p class="text-muted small mb-0">{{ feat.desc }}</p>
            </div>
          </div>
        </div>
      </div>
    </section>

    <!-- Agents Section -->
    <section class="agents-section py-6" style="background: var(--bg)">
      <div class="container">
        <div class="text-center mb-5">
          <h2 class="fw-bold fs-2 mb-2" style="color: var(--primary)">5명의 AI 에이전트</h2>
          <p class="text-muted">각 역할에 특화된 AI가 회의를 함께합니다</p>
        </div>
        <div class="row g-3 justify-content-center">
          <div v-for="agent in agents" :key="agent.name" class="col-6 col-md-4 col-lg-2-4">
            <div class="agent-card card text-center p-4 h-100">
              <div class="agent-avatar mb-3">
                <img :src="agent.img" :alt="agent.name" class="agent-img" />
              </div>
              <h6 class="fw-bold mb-1">{{ agent.name }}</h6>
              <p class="text-muted small mb-0">{{ agent.role }}</p>
            </div>
          </div>
        </div>
      </div>
    </section>

    <!-- CTA Section -->
    <section class="cta-section text-center py-6">
      <div class="container">
        <h2 class="fw-bold fs-2 text-white mb-3">지금 바로 시작하세요</h2>
        <p class="text-white-50 mb-4 fs-6">무료로 가입하고 AI가 이끄는 스마트한 회의를 경험해보세요</p>
        <button class="btn btn-warning btn-lg fw-bold px-5 py-3" @click="openRegister">
          무료 회원가입 <i class="bi bi-arrow-right ms-1"></i>
        </button>
      </div>
    </section>

    <!-- Footer -->
    <footer class="landing-footer py-4">
      <div class="container text-center text-muted small">
        <span class="fw-bold" style="color: var(--primary)">workma!te</span> © 2025 — AI 기반 회의 운영 플랫폼
      </div>
    </footer>

    <!-- ── 로그인 팝업 모달 ────────────────────────────── -->
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

    <!-- ── 회원가입 팝업 모달 ──────────────────────────── -->
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

/* Hero */
.hero-section {
  background: linear-gradient(135deg, var(--primary) 0%, #2d5282 50%, #1e3a5f 100%);
  color: #fff;
  padding: 100px 0 80px;
}
.hero-title {
  font-size: clamp(2rem, 5vw, 3.5rem);
  font-weight: 900;
  line-height: 1.2;
  letter-spacing: -0.02em;
}
.hero-subtitle {
  font-size: 1.1rem;
  color: rgba(255,255,255,.75);
  line-height: 1.7;
}

/* Stats */
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
.feature-icon {
  width: 52px; height: 52px;
  border-radius: 12px;
  display: flex; align-items: center; justify-content: center;
}

/* Agents */
.col-lg-2-4 { width: 20%; }
.agent-card { border: 1px solid var(--border) !important; transition: transform .2s, box-shadow .2s; }
.agent-card:hover { transform: translateY(-4px); box-shadow: var(--shadow-lg) !important; }
.agent-avatar {
  width: 80px; height: 80px;
  border-radius: 50%;
  overflow: hidden;
  margin: 0 auto;
  border: 2px solid var(--border);
}
.agent-img { width: 100%; height: 100%; object-fit: cover; }

/* Popup modal */
.popup-backdrop {
  position: fixed; inset: 0;
  background: rgba(0,0,0,.55);
  backdrop-filter: blur(4px);
  z-index: 2000;
  display: flex; align-items: center; justify-content: center;
  padding: 20px;
}
.popup-box {
  position: relative;
  width: 100%; max-width: 460px;
  max-height: 90vh;
  overflow-y: auto;
  background: #fff;
  border-radius: 20px;
  box-shadow: 0 20px 60px rgba(0,0,0,.25);
}
.popup-close {
  position: absolute; top: 14px; right: 16px; z-index: 10;
  background: none; border: none;
  font-size: 18px; color: #94a3b8;
  cursor: pointer; padding: 4px;
  line-height: 1;
  transition: color .15s;
}
.popup-close:hover { color: #475569; }

/* Modal transition */
.modal-fade-enter-active, .modal-fade-leave-active { transition: opacity .2s, transform .2s; }
.modal-fade-enter-from, .modal-fade-leave-to { opacity: 0; }
.modal-fade-enter-from .popup-box, .modal-fade-leave-to .popup-box { transform: scale(.95) translateY(8px); }

/* CTA */
.cta-section {
  background: linear-gradient(135deg, var(--primary), #1e40af);
}

/* Footer */
.landing-footer {
  background: #f8fafc;
  border-top: 1px solid var(--border);
  margin-top: auto;
}

@media (max-width: 768px) {
  .hero-stats { flex-wrap: wrap; gap: 16px; padding: 16px 24px; }
  .stat-divider { display: none; }
  .col-lg-2-4 { width: 50%; }
}
</style>
