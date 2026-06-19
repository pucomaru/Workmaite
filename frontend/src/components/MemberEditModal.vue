<script setup>
import { computed, ref, watch } from 'vue'
import api, { apiAI } from '../api'
import { confirmDialog } from '../composables/useConfirm'
import { toast } from '../composables/useToast'
import { useAuthStore } from '../stores/auth'

const props = defineProps({
  // 통합 구성원 객체(없으면 모달 닫힘):
  // { id, name, email, company, department, position, role, meetings: [{ id, member_id, title }] }
  member: { type: Object, default: null },
  nightMode: Boolean,
})
const emit = defineEmits(['close', 'saved', 'deleted'])

const auth = useAuthStore()
// 조직 권한(company role) 변경은 SYSTEM_ADMIN만 — 백엔드 updateCompanyRole도 동일하게 강제(이중 방어)
const isSystemAdmin = computed(() => auth.user?.role === 'SYSTEM_ADMIN')
// 이메일(로그인 자격) 변경은 관리자(SYSTEM_ADMIN 또는 COMPANY_ADMIN)만 — 같은 회사 여부는 백엔드가 최종 검증
const canEditEmail = computed(() => isSystemAdmin.value || auth.user?.role === 'COMPANY_ADMIN')

const form = ref({ name: '', email: '', company: '', department: '', position: '', role: 'USER' })
const origRole = ref('USER') // 실제 변경이 있을 때만 권한 PATCH를 쏘기 위한 기준값
const saving = ref(false)

// 부모가 member를 새로 열 때마다 폼을 동기화(편집 중 외부 갱신과 충돌 방지)
watch(
  () => props.member,
  m => {
    if (!m) return
    form.value = {
      name: m.name || '',
      email: m.email || '',
      company: m.company || '',
      department: m.department || '',
      position: m.position || '',
      role: m.role || 'USER',
    }
    origRole.value = m.role || 'USER'
  },
  { immediate: true },
)

async function save() {
  const m = props.member
  if (!m?.id) {
    toast.error('구성원 식별 정보를 찾을 수 없어 저장할 수 없습니다.')
    return
  }
  saving.value = true
  try {
    // 프로필 수정 — 본인/SYSTEM_ADMIN/같은 회사 COMPANY_ADMIN만(서버 require_user_update_permission)
    const payload = {
      name: form.value.name,
      company: form.value.company || null,
      department: form.value.department || null,
      position: form.value.position || null,
    }
    // 이메일 변경은 관리자만(서버도 강제) — 권한이 있고 값이 바뀐 경우에만 포함
    if (canEditEmail.value && form.value.email && form.value.email !== (m.email || '')) {
      payload.email = form.value.email.trim()
    }
    await apiAI.patch(`/api/ai/users/${m.id}`, payload)
    // 조직 권한 변경 — SYSTEM_ADMIN이 값을 실제로 바꿨을 때만(서버도 SYSTEM_ADMIN 강제)
    if (isSystemAdmin.value && form.value.role && form.value.role !== origRole.value) {
      await api.patch(`/api/v1/users/${m.id}/role`, { role: form.value.role })
    }
    emit('saved')
    emit('close')
  } catch (e) {
    toast.error(e.response?.data?.detail || e.response?.data?.message || '변경 실패')
  } finally {
    saving.value = false
  }
}

async function remove() {
  const m = props.member
  if (!m?.id) {
    toast.error('구성원 식별 정보를 찾을 수 없어 제거할 수 없습니다.')
    return
  }
  // 본인 자기 삭제 금지 — 관리자라도 자신은 제거할 수 없다.
  if (m.id === auth.user?.id) {
    toast.error('자기 자신은 제거할 수 없습니다.')
    return
  }
  if (
    !(await confirmDialog(
      `${m.name || m.email}님의 계정을 삭제하시겠습니까? 모든 회의체에서 제외됩니다.`,
      { danger: true },
    ))
  )
    return
  saving.value = true
  try {
    // 계정 삭제(한 번에) — 서버가 모든 회의체 멤버십·FK를 정리하고 소프트 삭제한다.
    await apiAI.delete(`/api/ai/users/${m.id}`)
    emit('deleted')
    emit('close')
  } catch (e) {
    toast.error(e.response?.data?.detail || '제거 실패')
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <Teleport to="body">
    <div v-if="member" class="app-modal-backdrop" @click.self="emit('close')">
      <div class="app-modal app-modal-sm" :class="{ dark: nightMode }">
        <div class="app-modal-header">
          <span class="app-modal-title">구성원 정보 수정</span>
          <button class="app-modal-close" @click="emit('close')">
            <svg
              width="14"
              height="14"
              fill="none"
              stroke="currentColor"
              stroke-width="2.5"
              viewBox="0 0 24 24"
            >
              <path d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        <div class="app-modal-body">
          <div class="app-modal-field-row">
            <div class="app-modal-field">
              <label for="member-name">이름</label>
              <input
                id="member-name"
                v-model="form.name"
                autocomplete="off"
                class="app-modal-input"
                placeholder="홍길동"
              />
            </div>
            <div class="app-modal-field">
              <label for="member-email">이메일</label>
              <input
                id="member-email"
                v-if="canEditEmail"
                v-model="form.email"
                autocomplete="off"
                class="app-modal-input"
                placeholder="example@company.com"
              />
              <input
                id="member-email"
                name="member-email"
                v-else
                :value="form.email"
                autocomplete="off"
                class="app-modal-input"
                disabled
                style="background: var(--surface); color: var(--dark-muted)"
              />
            </div>
          </div>
          <div v-if="isSystemAdmin" class="app-modal-field">
            <label for="member-role">역할 (관리자 전용)</label>
            <select id="member-role" v-model="form.role" class="app-modal-input">
              <option value="USER">일반 사용자</option>
              <option value="COMPANY_ADMIN">회사 관리자 (자사 구성원 관리)</option>
              <option value="SYSTEM_ADMIN">시스템 관리자 (전체 관리)</option>
            </select>
          </div>
          <div class="app-modal-field-row">
            <div class="app-modal-field">
              <label for="member-company">회사명</label>
              <input
                id="member-company"
                v-model="form.company"
                autocomplete="off"
                class="app-modal-input"
                placeholder="예: SK AX"
              />
            </div>
            <div class="app-modal-field">
              <label for="member-department">부서명</label>
              <input
                id="member-department"
                v-model="form.department"
                autocomplete="off"
                class="app-modal-input"
                placeholder="예: 전략기획팀"
              />
            </div>
          </div>
          <div class="app-modal-field-row">
            <div class="app-modal-field">
              <label for="member-position">직책</label>
              <input
                id="member-position"
                v-model="form.position"
                autocomplete="off"
                class="app-modal-input"
                placeholder="예: 팀장"
              />
            </div>
          </div>
        </div>

        <div class="app-modal-footer modal-footer-split">
          <button
            v-if="member?.id !== auth.user?.id"
            class="app-btn-danger"
            :disabled="saving"
            @click="remove"
          >
            삭제
          </button>
          <div class="footer-right">
            <button class="app-btn-cancel" @click="emit('close')">취소</button>
            <button class="app-btn-primary" :disabled="saving" @click="save">
              {{ saving ? '저장 중...' : '저장' }}
            </button>
          </div>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.modal-footer-split {
  justify-content: space-between !important;
}
.footer-right {
  display: flex;
  gap: 8px;
  /* 삭제 버튼(좌측)이 숨겨져도 취소·저장은 항상 우측에 고정 */
  margin-left: auto;
}
</style>
