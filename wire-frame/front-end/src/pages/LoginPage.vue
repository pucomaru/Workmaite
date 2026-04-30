<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth'

const router = useRouter()
const auth = useAuthStore()

const form = ref({ employee_id: '', password: '' })
const error = ref('')
const loading = ref(false)

async function submit() {
  error.value = ''
  loading.value = true
  try {
    await auth.login(form.value.employee_id, form.value.password)
    router.push('/')
  } catch (e) {
    error.value = e.response?.data?.detail || '로그인에 실패했습니다.'
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="auth-page">
    <div class="auth-card">
      <div class="auth-header">
        <div class="auth-logo">W</div>
        <h1>workma!te</h1>
        <p>회의체 운영 AI Agent 서비스</p>
      </div>
      <form @submit.prevent="submit" class="auth-form">
        <div class="form-group">
          <label class="form-label">사번</label>
          <input v-model="form.employee_id" class="form-input" placeholder="사번을 입력하세요" required />
        </div>
        <div class="form-group">
          <label class="form-label">비밀번호</label>
          <input v-model="form.password" type="password" class="form-input" placeholder="비밀번호를 입력하세요" required />
        </div>
        <div v-if="error" class="auth-error">{{ error }}</div>
        <button type="submit" class="btn btn-primary btn-lg" style="width:100%;justify-content:center" :disabled="loading">
          {{ loading ? '로그인 중...' : '로그인' }}
        </button>
        <div class="auth-footer">
          계정이 없으신가요? <router-link to="/register">회원가입</router-link>
        </div>
      </form>
    </div>
  </div>
</template>

<style scoped>
.auth-page { min-height: 100vh; display: flex; align-items: center; justify-content: center; background: var(--bg); }
.auth-card { background: #fff; border-radius: var(--radius-lg); box-shadow: var(--shadow-lg); padding: 40px; width: 100%; max-width: 400px; border: 1px solid var(--border); }
.auth-header { text-align: center; margin-bottom: 32px; }
.auth-logo { width: 56px; height: 56px; background: var(--primary); color: #fff; border-radius: 14px; display: flex; align-items: center; justify-content: center; font-size: 24px; font-weight: 700; margin: 0 auto 16px; }
.auth-header h1 { font-size: 24px; font-weight: 700; color: var(--primary); margin-bottom: 6px; }
.auth-header p { color: var(--text-muted); font-size: 14px; }
.auth-form { display: flex; flex-direction: column; gap: 16px; }
.auth-error { background: #fee2e2; color: #991b1b; padding: 10px 14px; border-radius: 6px; font-size: 13px; }
.auth-footer { text-align: center; color: var(--text-muted); font-size: 13px; }
.auth-footer a { color: var(--accent); font-weight: 500; }
</style>
