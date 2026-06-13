<script setup>
import { computed } from 'vue'

const props = defineProps({
  modal: Object, // { reportId, form: { file_name, submitter_department, human_status } }
  nightMode: Boolean,
  saving: Boolean,
})
const emit = defineEmits(['close', 'save', 'delete'])

// 부모 소유 편집 draft를 로컬 별칭으로 in-place 편집 (동일 참조)
const form = computed(() => props.modal?.form || {})

const STATUS_OPTIONS = [
  { value: 'pending', label: '검토중' },
  { value: 'approved', label: '승인' },
  { value: 'rejected', label: '반려' },
]
</script>

<template>
  <Teleport to="body">
    <div v-if="modal" class="app-modal-backdrop" @click.self="emit('close')">
      <div class="app-modal report-edit-modal" :class="{ dark: nightMode }">
        <!-- Header -->
        <div class="app-modal-header">
          <span class="app-modal-title">보고자료 편집</span>
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

        <!-- Body -->
        <div class="app-modal-body">
          <!-- 파일명 -->
          <div class="app-modal-field">
            <label>파일명 <span class="req">*</span></label>
            <input
              v-model="form.file_name"
              class="app-modal-input"
              placeholder="파일명을 입력하세요"
            />
          </div>

          <!-- 작성부서 + 검토상태 한 행 -->
          <div class="app-modal-field-row">
            <div class="app-modal-field">
              <label>작성 부서</label>
              <input
                v-model="form.submitter_department"
                class="app-modal-input"
                placeholder="예: 전략기획팀"
              />
            </div>
            <div class="app-modal-field">
              <label>검토 상태</label>
              <select v-model="form.human_status" class="app-modal-input">
                <option v-for="s in STATUS_OPTIONS" :key="s.value" :value="s.value">
                  {{ s.label }}
                </option>
              </select>
            </div>
          </div>
        </div>

        <!-- Footer -->
        <div class="app-modal-footer modal-footer-split">
          <button class="app-btn-danger" @click="emit('delete')">삭제</button>
          <div class="footer-right">
            <button class="app-btn-cancel" @click="emit('close')">취소</button>
            <button
              class="app-btn-primary"
              :disabled="!form.file_name?.trim() || saving"
              @click="emit('save')"
            >
              {{ saving ? '저장 중...' : '저장' }}
            </button>
          </div>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.report-edit-modal {
  max-width: 440px;
  width: 100%;
}
.modal-footer-split {
  justify-content: space-between !important;
}
.footer-right {
  display: flex;
  gap: 8px;
}
</style>
