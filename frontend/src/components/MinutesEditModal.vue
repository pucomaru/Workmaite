<script setup>
import { computed } from 'vue'

const props = defineProps({
  modal: Object, // { minutesId, form: { file_name, status } }
  nightMode: Boolean,
  saving: Boolean,
})
const emit = defineEmits(['close', 'save', 'delete'])

// 부모 소유 편집 draft를 로컬 별칭으로 in-place 편집 (동일 참조)
const form = computed(() => props.modal?.form || {})
</script>

<template>
  <Teleport to="body">
    <div v-if="modal" class="app-modal-backdrop" @click.self="emit('close')">
      <div class="app-modal minutes-edit-modal" :class="{ dark: nightMode }">
        <!-- Header -->
        <div class="app-modal-header">
          <span class="app-modal-title">회의록 편집</span>
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
          <!-- 회의록명 -->
          <div class="app-modal-field">
            <label>회의록명</label>
            <input
              id="minutes-file-name"
              name="minutes-file-name"
              v-model="form.file_name"
              class="app-modal-input"
              placeholder="파일명을 입력하세요"
            />
          </div>
        </div>

        <!-- Footer -->
        <div class="app-modal-footer modal-footer-split">
          <button class="app-btn-danger" @click="emit('delete')">삭제</button>
          <div class="footer-right">
            <button class="app-btn-cancel" @click="emit('close')">취소</button>
            <button class="app-btn-primary" :disabled="saving" @click="emit('save')">
              {{ saving ? '저장 중...' : '저장' }}
            </button>
          </div>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.minutes-edit-modal {
  max-width: 400px;
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
