<script setup>
import { ref } from 'vue'
import { useAuthStore } from '../stores/auth'

const auth = useAuthStore()

const form = ref({
  name: auth.user?.name || '',
  department: auth.user?.department || '',
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
      department: form.value.department || null,
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
  <div style="max-width:480px;margin:0 auto;padding-top:16px">
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
          <input :value="auth.user?.employee_id" class="form-input" disabled style="background:#f8fafc;color:var(--text-muted)" />
        </div>
        <div class="form-group">
          <label class="form-label">담당 부서</label>
          <input v-model="form.department" class="form-input" placeholder="예: 전략기획팀" />
          <div style="font-size:11px;color:var(--text-muted);margin-top:4px">
            아젠다 담당 부서 자동 배정에 사용됩니다
          </div>
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
