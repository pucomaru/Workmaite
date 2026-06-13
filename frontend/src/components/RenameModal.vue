<script setup>
import { computed } from 'vue'

// 회사명·부서명 등 '이름 변경' 공용 모달 (app-modal 패턴 재사용).
const props = defineProps({
  modal: Object, // { oldName, form: { name } }
  nightMode: Boolean,
  saving: Boolean,
  title: { type: String, default: '이름 변경' },
  fieldLabel: { type: String, default: '이름' },
  placeholder: { type: String, default: '새 이름을 입력하세요' },
})
const emit = defineEmits(['close', 'save'])

// 부모가 소유한 편집 객체(modal.form)를 로컬 별칭으로 받아 v-model 바인딩.
// 같은 객체 참조이므로 부모가 저장 시 되읽는 값과 동일 — prop 직접 변형 경고 회피.
const form = computed(() => props.modal?.form || {})
</script>

<template>
  <Teleport to="body">
    <div v-if="modal" class="app-modal-backdrop" @click.self="emit('close')">
      <div class="app-modal rename-modal" :class="{ dark: nightMode }">
        <!-- Header -->
        <div class="app-modal-header">
          <span class="app-modal-title">{{ title }}</span>
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
          <div class="app-modal-field">
            <label>{{ fieldLabel }}</label>
            <input
              v-model="form.name"
              class="app-modal-input"
              :placeholder="placeholder"
              @keydown.enter="emit('save')"
            />
          </div>
        </div>

        <!-- Footer -->
        <div class="app-modal-footer">
          <button class="app-btn-cancel" @click="emit('close')">취소</button>
          <button
            class="app-btn-primary"
            :disabled="
              saving || !modal.form.name.trim() || modal.form.name.trim() === modal.oldName
            "
            @click="emit('save')"
          >
            {{ saving ? '저장 중...' : '저장' }}
          </button>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.rename-modal {
  max-width: 400px;
  width: 100%;
}
</style>
