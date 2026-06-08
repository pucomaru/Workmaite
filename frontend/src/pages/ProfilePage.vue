<script setup>
import { ref } from 'vue'
import { useAuthStore } from '../stores/auth'

const auth = useAuthStore()

const form = ref({
  name: auth.user?.name || '',
  organization: auth.user?.organization || '',
  department: auth.user?.department || '',
  position: auth.user?.position || '',
  password: '',
  passwordConfirm: '',
})
const saving = ref(false)
const success = ref(false)
const error = ref('')

async function save() {
  error.value = ''
  if (form.value.password && form.value.password !== form.value.passwordConfirm) {
    error.value = '비밀번호가 일치하지 않습니다.'
    return
  }
  saving.value = true
  try {
    const payload = {
      name: form.value.name,
      organization: form.value.organization || null,
      department: form.value.department || null,
      position: form.value.position || null,
    }
    if (form.value.password) payload.password = form.value.password
    await auth.updateProfile(payload)
    form.value.password = ''
    form.value.passwordConfirm = ''
    success.value = true
    setTimeout(() => { success.value = false }, 2500)
  } catch (e) {
    error.value = e.response?.data?.detail || '저장에 실패했습니다.'
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <div class="page-wrap">
    <div class="card">
      <div class="card-header">
        <span style="font-weight:600">개인설정</span>
      </div>
      <div class="modal-body" style="padding:20px">
        <div class="form-group">
          <label class="form-label">이름</label>
          <input v-model="form.name" class="form-input" placeholder="이름" />
        </div>
        <div class="form-group">
          <label class="form-label">사번</label>
          <input :value="auth.user?.employee_id" class="form-input" disabled style="background:var(--surface);color:var(--text-muted)" />
        </div>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px">
          <div class="form-group">
            <label class="form-label">조직명</label>
            <input v-model="form.organization" class="form-input" placeholder="예: 워크메이트" />
          </div>
          <div class="form-group">
            <label class="form-label">부서명</label>
            <input v-model="form.department" class="form-input" placeholder="예: 전략기획팀" />
          </div>
        </div>
        <div class="form-group">
          <label class="form-label">직책</label>
          <input v-model="form.position" class="form-input" placeholder="예: 팀장, 과장, 대리" />
        </div>
        <div class="form-group">
          <label class="form-label">새 비밀번호 (변경 시만 입력)</label>
          <input v-model="form.password" type="password" class="form-input" placeholder="새 비밀번호" />
        </div>
        <div class="form-group">
          <label class="form-label">비밀번호 확인</label>
          <input v-model="form.passwordConfirm" type="password" class="form-input" placeholder="비밀번호 재입력" />
        </div>

        <div v-if="error" style="background:#fee2e2;color:#991b1b;padding:10px 14px;border-radius:6px;font-size:13px;margin-bottom:12px">
          {{ error }}
        </div>
        <div v-if="success" style="background:#dcfce7;color:#166534;padding:10px 14px;border-radius:6px;font-size:13px;margin-bottom:12px">
          저장되었습니다.
        </div>

        <button
          class="btn btn-primary"
          style="width:100%;justify-content:center"
          :disabled="saving"
          @click="save"
        >
          {{ saving ? '저장 중...' : '저장' }}
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.page-wrap { max-width: 480px; }
</style>
