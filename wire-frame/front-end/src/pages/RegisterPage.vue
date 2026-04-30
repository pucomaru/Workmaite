<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth'

const router = useRouter()
const auth = useAuthStore()

const form = ref({ name: '', employee_id: '', password: '', department: '' })
const error = ref('')
const loading = ref(false)

async function submit() {
  error.value = ''
  loading.value = true
  try {
    await auth.register(form.value)
    await auth.login(form.value.employee_id, form.value.password)
    router.push('/')
  } catch (e) {
    error.value = e.response?.data?.detail || '회원가입에 실패했습니다.'
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
        <h1>회원가입</h1>
        <p>WorkMate 계정을 만드세요</p>
      </div>
      <form @submit.prevent="submit" class="auth-form">
        <div class="form-group">
          <label class="form-label">이름</label>
          <input v-model="form.name" class="form-input" placeholder="이름" required />
        </div>
        <div class="form-group">
          <label class="form-label">사번</label>
          <input v-model="form.employee_id" class="form-input" placeholder="사번" required />
        </div>
        <div class="form-group">
          <label class="form-label">담당 부서</label>
          <input v-model="form.department" class="form-input" placeholder="예: 전략기획팀" />
        </div>
        <div class="form-group">
          <label class="form-label">비밀번호</label>
          <input v-model="form.password" type="password" class="form-input" placeholder="비밀번호" required />
        </div>
        <div v-if="error" class="auth-error">{{ error }}</div>
        <button type="submit" class="btn btn-primary btn-lg" style="width:100%;justify-content:center" :disabled="loading">
          {{ loading ? '처리 중...' : '회원가입' }}
        </button>
        <div class="auth-footer">
          이미 계정이 있으신가요? <router-link to="/login">로그인</router-link>
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
.auth-header h1 { font-size: 22px; font-weight: 700; color: var(--primary); margin-bottom: 6px; }
.auth-header p { color: var(--text-muted); font-size: 14px; }
.auth-form { display: flex; flex-direction: column; gap: 16px; }
.auth-error { background: #fee2e2; color: #991b1b; padding: 10px 14px; border-radius: 6px; font-size: 13px; }
.auth-footer { text-align: center; color: var(--text-muted); font-size: 13px; }
.auth-footer a { color: var(--accent); font-weight: 500; }
</style>
