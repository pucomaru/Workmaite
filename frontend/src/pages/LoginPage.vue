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
    error.value = e.response?.data?.message || e.message || '이메일 또는 비밀번호가 올바르지 않습니다.'
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
