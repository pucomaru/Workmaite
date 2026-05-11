<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth'

const router = useRouter()
const auth = useAuthStore()

const form = ref({ email: '', password: '' })
const error = ref('')
const loading = ref(false)
const showPw = ref(false)

async function submit() {
  error.value = ''
  loading.value = true
  try {
    await auth.loginWithEmail(form.value.email, form.value.password)
    router.push('/')
  } catch (e) {
    error.value = e.response?.data?.detail || '이메일 또는 비밀번호가 올바르지 않습니다.'
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="popup-page">
    <div class="popup-card">
      <button class="popup-page-close" @click="router.push('/landing')">
        <i class="bi bi-x-lg"></i>
      </button>

      <!-- Header -->
      <div class="d-flex align-items-center gap-2 mb-3">
        <div class="mini-logo">W</div>
        <span class="fw-bold" style="color:var(--primary);font-size:16px">
          workma<span style="color:#f59e0b">!</span>te
        </span>
      </div>

      <h4 class="fw-bold mb-1" style="color:var(--primary)">로그인</h4>
      <p class="text-muted small mb-4">이메일과 비밀번호를 입력하세요</p>

      <form @submit.prevent="submit">
        <div class="mb-3">
          <label class="form-label">이메일</label>
          <div class="input-group">
            <span class="input-group-text bg-light border-end-0">
              <i class="bi bi-envelope text-muted"></i>
            </span>
            <input v-model="form.email" type="email"
              class="form-control border-start-0"
              placeholder="name@company.com" required />
          </div>
        </div>

        <div class="mb-3">
          <label class="form-label">비밀번호</label>
          <div class="input-group">
            <span class="input-group-text bg-light border-end-0">
              <i class="bi bi-lock text-muted"></i>
            </span>
            <input v-model="form.password"
              :type="showPw ? 'text' : 'password'"
              class="form-control border-start-0 border-end-0"
              placeholder="비밀번호를 입력하세요" required />
            <button type="button" class="input-group-text bg-light border-start-0"
              @click="showPw = !showPw">
              <i :class="showPw ? 'bi bi-eye-slash' : 'bi bi-eye'" class="text-muted"></i>
            </button>
          </div>
        </div>

        <div v-if="error" class="alert alert-danger py-2 small mb-3">
          <i class="bi bi-exclamation-circle me-1"></i>{{ error }}
        </div>

        <button type="submit" class="btn btn-primary w-100 py-2 fw-semibold" :disabled="loading">
          <span v-if="loading" class="spinner-border spinner-border-sm me-2" />
          {{ loading ? '로그인 중...' : '로그인' }}
        </button>
      </form>

      <hr class="my-3" />
      <div class="text-center small text-muted">
        계정이 없으신가요?
        <router-link to="/register" class="fw-semibold" style="color:var(--accent)">회원가입</router-link>
      </div>
    </div>
  </div>
</template>

<style scoped>
.popup-page {
  min-height: 100vh;
  background: rgba(0,0,0,.55);
  backdrop-filter: blur(4px);
  display: flex; align-items: center; justify-content: center;
  padding: 20px;
}
.popup-card {
  position: relative;
  width: 100%; max-width: 440px;
  background: #fff;
  border-radius: 20px;
  padding: 36px;
  box-shadow: 0 20px 60px rgba(0,0,0,.25);
}
.popup-page-close {
  position: absolute; top: 14px; right: 16px;
  background: none; border: none; font-size: 18px; color: #94a3b8;
  cursor: pointer; padding: 4px; line-height: 1;
  transition: color .15s;
}
.popup-page-close:hover { color: #475569; }
.mini-logo {
  width: 32px; height: 32px;
  background: var(--primary); border-radius: 8px;
  display: flex; align-items: center; justify-content: center;
  font-size: 16px; font-weight: 900; color: #f59e0b;
}
.input-group-text { border-color: var(--border); }
.form-control { border-color: var(--border); font-size: 13px; }
</style>

<template>
  <div class="auth-bg">
    <!-- Left panel -->
    <div class="auth-left d-none d-lg-flex">
      <div class="auth-left-inner text-white text-center">
        <div class="brand-logo mb-4">M</div>
        <h2 class="fw-bold mb-2">meetma<span class="text-warning">!</span>te</h2>
        <p class="text-white-50 mb-5">AI 기반 회의 운영 플랫폼</p>
        <div class="feature-list">
          <div v-for="f in leftFeatures" :key="f" class="feature-item">
            <i class="bi bi-check-circle-fill text-warning me-2"></i>{{ f }}
          </div>
        </div>
      </div>
    </div>

    <!-- Right panel (form) -->
    <div class="auth-right d-flex align-items-center justify-content-center">
      <div class="auth-form-box">

        <!-- Mobile brand -->
        <div class="text-center d-lg-none mb-4">
          <div class="brand-logo-sm mx-auto mb-2">M</div>
          <span class="fw-bold fs-5" style="color:var(--primary)">meetma<span class="text-warning">!</span>te</span>
        </div>

        <h4 class="fw-bold mb-1" style="color:var(--primary)">로그인</h4>
        <p class="text-muted small mb-4">계정 정보를 입력하세요</p>

        <form @submit.prevent="submit">
          <!-- Employee ID -->
          <div class="mb-3">
            <label class="form-label">사번</label>
            <div class="input-group">
              <span class="input-group-text bg-light border-end-0">
                <i class="bi bi-person text-muted"></i>
              </span>
              <input v-model="form.employee_id" type="text"
                class="form-control border-start-0 ps-0"
                placeholder="사번을 입력하세요" required />
            </div>
          </div>

          <!-- Password -->
          <div class="mb-3">
            <label class="form-label">비밀번호</label>
            <div class="input-group">
              <span class="input-group-text bg-light border-end-0">
                <i class="bi bi-lock text-muted"></i>
              </span>
              <input v-model="form.password"
                :type="showPw ? 'text' : 'password'"
                class="form-control border-start-0 border-end-0 ps-0"
                placeholder="비밀번호를 입력하세요" required />
              <button type="button" class="input-group-text bg-light border-start-0"
                @click="showPw = !showPw">
                <i :class="showPw ? 'bi bi-eye-slash' : 'bi bi-eye'" class="text-muted"></i>
              </button>
            </div>
          </div>

          <!-- Error -->
          <div v-if="error" class="alert alert-danger py-2 small mb-3">
            <i class="bi bi-exclamation-circle me-1"></i>{{ error }}
          </div>

          <!-- Submit -->
          <button type="submit" class="btn btn-primary w-100 py-2 fw-semibold" :disabled="loading">
            <span v-if="loading" class="spinner-border spinner-border-sm me-2" />
            {{ loading ? '로그인 중...' : '로그인' }}
          </button>
        </form>

        <hr class="my-4" />

        <div class="text-center small text-muted">
          계정이 없으신가요?
          <router-link to="/register" class="fw-semibold" style="color:var(--accent)">회원가입</router-link>
        </div>
        <div class="text-center mt-2 small">
          <router-link to="/landing" class="text-muted">← 소개 페이지로</router-link>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.auth-bg {
  min-height: 100vh;
  display: flex;
}
.auth-left {
  width: 420px;
  flex-shrink: 0;
  background: linear-gradient(145deg, var(--primary), #1e40af);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 40px;
}
.auth-left-inner { max-width: 300px; }
.brand-logo {
  width: 72px; height: 72px;
  background: #f59e0b;
  border-radius: 20px;
  display: flex; align-items: center; justify-content: center;
  font-size: 32px; font-weight: 900; color: var(--primary);
  margin: 0 auto;
}
.brand-logo-sm {
  width: 44px; height: 44px;
  background: var(--primary);
  border-radius: 12px;
  display: flex; align-items: center; justify-content: center;
  font-size: 20px; font-weight: 900; color: #fff;
}
.feature-list { display: flex; flex-direction: column; gap: 12px; text-align: left; }
.feature-item { font-size: 14px; color: rgba(255,255,255,.85); }

.auth-right {
  flex: 1;
  background: #f8fafc;
  padding: 32px 20px;
}
.auth-form-box {
  width: 100%;
  max-width: 400px;
  background: #fff;
  border-radius: 16px;
  box-shadow: 0 4px 24px rgba(0,0,0,.08);
  padding: 40px 36px;
  border: 1px solid var(--border);
}
.input-group-text { border-color: var(--border); }
.form-control { border-color: var(--border); }
</style>
