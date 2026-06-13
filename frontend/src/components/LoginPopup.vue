<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth'

const emit = defineEmits(['close', 'go-register'])
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
    emit('close')
    router.push('/')
  } catch (e) {
    error.value = e.message?.includes('서버')
      ? e.message
      : e.response?.data?.detail || '이메일 또는 비밀번호가 올바르지 않습니다.'
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="popup-inner">
    <!-- Header -->
    <div class="popup-header">
      <img src="../assets/workmaite-logo-black.png" class="popup-logo-img" alt="Workma!te" />
    </div>

    <h4 class="fw-bold mb-1 mt-3" style="color: var(--primary)">로그인</h4>
    <p class="text-muted small mb-4">이메일과 비밀번호를 입력하세요</p>

    <form @submit.prevent="submit">
      <!-- Email -->
      <div class="mb-3">
        <label class="form-label">이메일</label>
        <div class="input-group">
          <span class="input-group-text bg-light border-end-0">
            <i class="bi bi-envelope text-muted"></i>
          </span>
          <input
            v-model="form.email"
            type="email"
            class="form-control border-start-0"
            placeholder="name@company.com"
            required
          />
        </div>
      </div>

      <!-- Password -->
      <div class="mb-3">
        <label class="form-label">비밀번호</label>
        <div class="input-group">
          <span class="input-group-text bg-light border-end-0">
            <i class="bi bi-lock text-muted"></i>
          </span>
          <input
            v-model="form.password"
            :type="showPw ? 'text' : 'password'"
            class="form-control border-start-0 border-end-0"
            placeholder="비밀번호를 입력하세요"
            required
          />
          <button
            type="button"
            class="input-group-text bg-light border-start-0"
            @click="showPw = !showPw"
          >
            <i :class="showPw ? 'bi bi-eye-slash' : 'bi bi-eye'" class="text-muted"></i>
          </button>
        </div>
      </div>

      <!-- Error -->
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
      <button
        class="btn btn-link btn-sm p-0 fw-semibold"
        style="color: var(--accent)"
        @click="emit('go-register')"
      >
        회원가입
      </button>
    </div>
  </div>
</template>

<style scoped>
.popup-inner {
  padding: 32px 36px 28px;
}
.popup-header {
  display: flex;
  align-items: center;
}
.popup-logo-img {
  height: 30px;
  width: auto;
  display: block;
  margin: 0 auto;
}
.input-group-text {
  border-color: var(--border);
}
.form-control {
  border-color: var(--border);
  font-size: 13px;
}
</style>
