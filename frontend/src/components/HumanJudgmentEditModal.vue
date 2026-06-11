<script setup>
const props = defineProps({
  modal: Object,   // { hjId, form: { judgment, reason } }
  nightMode: Boolean,
  saving: Boolean,
})
const emit = defineEmits(['close', 'save', 'delete'])
</script>

<template>
  <Teleport to="body">
    <div v-if="modal" class="app-modal-backdrop" @click.self="emit('close')">
      <div class="app-modal hj-edit-modal" :class="{ dark: nightMode }">
        <div class="app-modal-header">
          <span class="app-modal-title">의사결정 편집</span>
          <button class="app-modal-close" @click="emit('close')">
            <svg width="14" height="14" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24">
              <path d="M6 18L18 6M6 6l12 12"/>
            </svg>
          </button>
        </div>

        <div class="app-modal-body">
          <div class="app-modal-field">
            <label>결정 내용 <span class="req">*</span></label>
            <textarea
              v-model="modal.form.judgment"
              class="app-modal-input hj-judgment-textarea"
              placeholder="예: 예산 30% 절감안으로 수정 승인, 다음 분기로 연기 결정 등"
              rows="3"
              autofocus
            />
          </div>
          <div class="app-modal-field">
            <label>결정 사유 <span class="hj-optional">(선택)</span></label>
            <textarea
              v-model="modal.form.reason"
              class="app-modal-input hj-reason-textarea"
              placeholder="결정 배경, 조건, 세부 사항 등을 자유롭게 입력하세요"
              rows="4"
            />
          </div>
        </div>

        <div class="app-modal-footer modal-footer-split">
          <button class="app-btn-danger" @click="emit('delete')">삭제</button>
          <div class="footer-right">
            <button class="app-btn-cancel" @click="emit('close')">취소</button>
            <button class="app-btn-primary" :disabled="!modal.form.judgment?.trim() || saving" @click="emit('save')">
              {{ saving ? '저장 중...' : '저장' }}
            </button>
          </div>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.hj-edit-modal { max-width: 460px; width: 100%; }
.hj-judgment-textarea,
.hj-reason-textarea { resize: vertical; }
.hj-judgment-textarea { min-height: 70px; }
.hj-reason-textarea  { min-height: 90px; }
.hj-optional { font-size: 11px; color: var(--text-muted, #888); font-weight: 400; }
.modal-footer-split { justify-content: space-between !important; }
.footer-right { display: flex; gap: 8px; }
</style>
