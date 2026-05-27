<script setup>
import { ref, computed } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth'

const router = useRouter()
const auth = useAuthStore()

const step = ref(1)
const form = ref({ email: '', name: '', password: '', confirm: '', organization: '', department: '', position: '' })
const error = ref('')
const loading = ref(false)
const showPw = ref(false)
const showConfirm = ref(false)

const emailValid = computed(() => /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(form.value.email))
const pwStrength = computed(() => {
  const pw = form.value.password
  if (!pw) return 0
  let s = 0
  if (pw.length >= 8) s++
  if (/[a-zA-Z]/.test(pw)) s++
  if (/\d/.test(pw)) s++
  if (/[!@#$%^&*]/.test(pw)) s++
  return s
})
const pwStrengthLabel = computed(() => ['', '매우 약함', '약함', '보통', '강함'][pwStrength.value] || '')
const pwStrengthColor = computed(() => ['', '#ef4444', '#f59e0b', '#3b82f6', '#10b981'][pwStrength.value] || '')
const pwMatch = computed(() => form.value.confirm && form.value.password === form.value.confirm)
const step2Valid = computed(() =>
  form.value.name.trim() && form.value.password.length >= 8 && pwStrength.value >= 2 && pwMatch.value &&
  form.value.organization.trim() && form.value.department.trim() && form.value.position.trim()
)
const steps = [
  { label: '이메일 입력' },
  { label: '세부 정보' },
]

async function submit() {
  error.value = ''
  loading.value = true
  try {
    await auth.register({
      name: form.value.name,
      email: form.value.email,
      password: form.value.password,
      company: form.value.organization,
      department: form.value.department,
      position: form.value.position,
    })
    await auth.loginWithEmail(form.value.email, form.value.password)
    step.value = 3
  } catch (e) {
    error.value = e.response?.data?.message || e.message || '회원가입에 실패했습니다.'
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

      <!-- Step indicator -->
      <div v-if="step < 3" class="step-bar mb-4">
        <div v-for="(s, i) in steps" :key="i" class="step-dot-wrap">
          <div class="step-node" :class="{ active: step === i+1, done: step > i+1 }">
            <i v-if="step > i+1" class="bi bi-check-lg"></i>
            <span v-else>{{ i+1 }}</span>
          </div>
          <div class="step-node-label">{{ s.label }}</div>
        </div>
      </div>

      <!-- ── STEP 1 ── -->
      <div v-if="step === 1">
        <h5 class="fw-bold mb-1" style="color:var(--primary)">이메일 입력</h5>
        <p class="text-muted small mb-4">사용할 이메일 주소를 입력하세요</p>
        <div class="mb-4">
          <label class="form-label">이메일 <span class="text-danger">*</span></label>
          <div class="input-group">
            <span class="input-group-text bg-light border-end-0">
              <i class="bi bi-envelope text-muted"></i>
            </span>
            <input v-model="form.email" type="email"
              class="form-control border-start-0"
              :class="form.email ? (emailValid ? 'is-valid' : 'is-invalid') : ''"
              placeholder="name@company.com"
              @keyup.enter="emailValid && sendCode()" />
          </div>
          <div v-if="form.email && !emailValid" class="invalid-feedback d-block small">
            올바른 이메일 형식을 입력하세요
          </div>
        </div>
        <button class="btn btn-primary w-100 py-2 fw-semibold"
          :disabled="!emailValid" @click="step = 2">
          다음
          <i class="bi bi-arrow-right ms-1"></i>
        </button>
      </div>

      <!-- ── STEP 2 ── -->
      <div v-else-if="step === 2">
        <h5 class="fw-bold mb-1" style="color:var(--primary)">세부 정보 입력</h5>
        <p class="text-muted small mb-4">이름, 소속 정보, 비밀번호를 설정하세요</p>
        <div class="mb-3">
          <label class="form-label">이름 <span class="text-danger">*</span></label>
          <div class="input-group">
            <span class="input-group-text bg-light border-end-0">
              <i class="bi bi-person text-muted"></i>
            </span>
            <input v-model="form.name" type="text"
              class="form-control border-start-0" placeholder="홍길동" />
          </div>
        </div>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px" class="mb-3">
          <div>
            <label class="form-label">조직 <span class="text-danger">*</span></label>
            <input v-model="form.organization" type="text" class="form-control" placeholder="예: SK AX" />
          </div>
          <div>
            <label class="form-label">부서명 <span class="text-danger">*</span></label>
            <input v-model="form.department" type="text" class="form-control" placeholder="예: AX서비스팀" />
          </div>
        </div>
        <div class="mb-3">
          <label class="form-label">직책 <span class="text-danger">*</span></label>
          <input v-model="form.position" type="text" class="form-control" placeholder="예: 매니저" />
        </div>
        <div class="mb-3">
          <label class="form-label">비밀번호 <span class="text-danger">*</span></label>
          <div class="input-group">
            <span class="input-group-text bg-light border-end-0">
              <i class="bi bi-lock text-muted"></i>
            </span>
            <input v-model="form.password"
              :type="showPw ? 'text' : 'password'"
              class="form-control border-start-0 border-end-0" placeholder="8자 이상 입력" />
            <button type="button" class="input-group-text bg-light border-start-0" @click="showPw = !showPw">
              <i :class="showPw ? 'bi bi-eye-slash' : 'bi bi-eye'" class="text-muted"></i>
            </button>
          </div>
          <div v-if="form.password" class="mt-2">
            <div class="progress" style="height:4px">
              <div class="progress-bar"
                :style="{ width: (pwStrength/4*100)+'%', background: pwStrengthColor }"
                style="transition: width .3s"></div>
            </div>
            <div class="d-flex justify-content-between mt-1">
              <small class="text-muted">비밀번호 강도</small>
              <small :style="{ color: pwStrengthColor }" class="fw-semibold">{{ pwStrengthLabel }}</small>
            </div>
            <div class="d-flex gap-3 mt-1 flex-wrap">
              <small :class="form.password.length >= 8 ? 'text-success' : 'text-muted'">
                <i :class="form.password.length >= 8 ? 'bi bi-check-circle-fill' : 'bi bi-circle'"></i> 8자 이상
              </small>
              <small :class="/[a-zA-Z]/.test(form.password) ? 'text-success' : 'text-muted'">
                <i :class="/[a-zA-Z]/.test(form.password) ? 'bi bi-check-circle-fill' : 'bi bi-circle'"></i> 영문 포함
              </small>
              <small :class="/\d/.test(form.password) ? 'text-success' : 'text-muted'">
                <i :class="/\d/.test(form.password) ? 'bi bi-check-circle-fill' : 'bi bi-circle'"></i> 숫자 포함
              </small>
            </div>
          </div>
        </div>
        <div class="mb-4">
          <label class="form-label">비밀번호 확인</label>
          <div class="input-group">
            <span class="input-group-text bg-light border-end-0">
              <i class="bi bi-lock-fill text-muted"></i>
            </span>
            <input v-model="form.confirm"
              :type="showConfirm ? 'text' : 'password'"
              class="form-control border-start-0 border-end-0"
              :class="form.confirm ? (pwMatch ? 'is-valid' : 'is-invalid') : ''"
              placeholder="비밀번호 재입력" />
            <button type="button" class="input-group-text bg-light border-start-0" @click="showConfirm = !showConfirm">
              <i :class="showConfirm ? 'bi bi-eye-slash' : 'bi bi-eye'" class="text-muted"></i>
            </button>
          </div>
          <div v-if="form.confirm && !pwMatch" class="invalid-feedback d-block small">비밀번호가 일치하지 않습니다</div>
          <div v-if="pwMatch" class="valid-feedback d-block small">비밀번호가 일치합니다</div>
        </div>
        <div v-if="error" class="alert alert-danger py-2 small mb-3">
          <i class="bi bi-exclamation-circle me-1"></i>{{ error }}
        </div>
        <div class="d-flex gap-2">
          <button class="btn btn-outline-secondary" @click="step = 1">
            <i class="bi bi-arrow-left"></i>
          </button>
          <button class="btn btn-primary flex-grow-1 py-2 fw-semibold"
            :disabled="!step2Valid || loading" @click="submit">
            <span v-if="loading" class="spinner-border spinner-border-sm me-2" />
            {{ loading ? '가입 중...' : '회원가입 완료' }}
          </button>
        </div>
      </div>

      <!-- ── STEP 3 (success) ── -->
      <div v-else-if="step === 3" class="text-center py-3">
        <div class="success-icon mb-3">
          <i class="bi bi-check-lg text-white fs-2"></i>
        </div>
        <h5 class="fw-bold mb-2" style="color:var(--primary)">가입 완료!</h5>
        <p class="text-muted mb-4">
          <strong>{{ form.name }}</strong>님, 환영합니다!<br>
          workma!te와 함께 스마트한 회의를 시작하세요.
        </p>
        <button class="btn btn-primary px-5 py-2 fw-semibold" @click="router.push('/')">
          시작하기 <i class="bi bi-arrow-right ms-1"></i>
        </button>
      </div>

      <div v-if="step < 3" class="text-center mt-4 small text-muted">
        이미 계정이 있으신가요?
        <router-link to="/login" class="fw-semibold" style="color:var(--accent)">로그인</router-link>
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
  width: 100%; max-width: 460px;
  max-height: 90vh; overflow-y: auto;
  background: #fff;
  border-radius: 20px;
  padding: 36px;
  box-shadow: 0 20px 60px rgba(0,0,0,.25);
}
.popup-page-close {
  position: absolute; top: 14px; right: 16px;
  background: none; border: none; font-size: 18px; color: #94a3b8;
  cursor: pointer; padding: 4px; line-height: 1; transition: color .15s;
}
.popup-page-close:hover { color: #475569; }
.mini-logo {
  width: 32px; height: 32px;
  background: var(--primary); border-radius: 8px;
  display: flex; align-items: center; justify-content: center;
  font-size: 16px; font-weight: 900; color: #f59e0b;
}

/* Step bar */
.step-bar { display: flex; align-items: flex-start; gap: 0; }
.step-dot-wrap {
  display: flex; flex-direction: column; align-items: center;
  flex: 1; position: relative;
}
.step-dot-wrap:not(:last-child)::after {
  content: '';
  position: absolute; top: 14px; left: 50%;
  width: 100%; height: 2px; background: var(--border); z-index: 0;
}
.step-node {
  width: 28px; height: 28px; border-radius: 50%;
  border: 2px solid var(--border); background: #fff;
  display: flex; align-items: center; justify-content: center;
  font-size: 12px; font-weight: 700; color: var(--text-muted);
  position: relative; z-index: 1; transition: all .2s;
}
.step-node.active { border-color: var(--primary); background: var(--primary); color: #fff; }
.step-node.done { border-color: var(--success); background: var(--success); color: #fff; }
.step-node-label { font-size: 10px; color: var(--text-muted); margin-top: 4px; text-align: center; white-space: nowrap; }

/* Form */
.input-group-text { border-color: var(--border); }
.form-control { border-color: var(--border); font-size: 13px; }
.ls-wide { letter-spacing: 4px; }

/* Success icon */
.success-icon {
  width: 64px; height: 64px; border-radius: 50%;
  background: linear-gradient(135deg, #10b981, #059669);
  display: flex; align-items: center; justify-content: center;
  margin: 0 auto; box-shadow: 0 8px 24px rgba(16,185,129,.3);
}
</style>
