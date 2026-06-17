<template>
  <Teleport to="body">
    <div v-if="confirmState" class="app-modal-backdrop app-confirm-backdrop" @click.self="cancel">
      <div class="app-modal app-confirm-modal" role="dialog" aria-modal="true">
        <div class="app-modal-body">
          <p class="confirm-msg">{{ confirmState.message }}</p>
          <div v-if="confirmState.mode === 'prompt'" class="app-modal-field">
            <div :class="confirmState.inputType === 'password' ? 'pw-input-wrap' : ''">
              <input
                :type="confirmState.inputType === 'password' && !showPw ? 'password' : 'text'"
                name="prompt"
                ref="inputEl"
                v-model="inputValue"
                class="app-modal-input"
                :placeholder="confirmState.placeholder"
                @keydown.enter="ok"
                @keydown.esc="cancel"
              />
              <button
                v-if="confirmState.inputType === 'password'"
                type="button"
                class="pw-toggle"
                tabindex="-1"
                @mousedown.prevent
                @click="showPw = !showPw"
                :aria-label="showPw ? '비밀번호 숨기기' : '비밀번호 표시'"
              >
                <svg v-if="!showPw" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                  <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" />
                  <circle cx="12" cy="12" r="3" />
                </svg>
                <svg v-else width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                  <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24" />
                  <line x1="1" y1="1" x2="23" y2="23" />
                </svg>
              </button>
            </div>
            <p v-if="confirmState.inputType === 'password' && confirmState.minLength > 0 && inputValue.length > 0 && inputValue.length < confirmState.minLength" class="pw-hint">
              {{ confirmState.minLength }}자 이상 입력해주세요
            </p>
          </div>
        </div>
        <div class="app-modal-footer">
          <button class="app-btn-cancel" @click="cancel">{{ confirmState.cancelText }}</button>
          <button
            :class="confirmState.danger ? 'app-btn-danger' : 'app-btn-primary'"
            :disabled="isOkDisabled"
            @click="ok"
          >
            {{ confirmState.okText }}
          </button>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup>
import { ref, computed, watch, nextTick } from 'vue'
import { confirmState, settleConfirm } from '../composables/useConfirm'

const inputValue = ref('')
const inputEl = ref(null)
const showPw = ref(false)

const isOkDisabled = computed(() => {
  const s = confirmState.value
  if (!s || s.mode !== 'prompt') return false
  if (s.minLength > 0 && inputValue.value.length > 0 && inputValue.value.length < s.minLength) return true
  return false
})

watch(confirmState, async s => {
  if (s?.mode === 'prompt') {
    inputValue.value = ''
    showPw.value = false
    await nextTick()
    inputEl.value?.focus()
  }
})

function ok() {
  if (isOkDisabled.value) return
  settleConfirm(confirmState.value.mode === 'prompt' ? inputValue.value : true)
}
function cancel() {
  settleConfirm(confirmState.value.mode === 'prompt' ? null : false)
}
</script>

<style scoped>
/* 다른 app-modal(z-index 1000)·modal-overlay(1050) 위에 항상 뜨도록 — 모달 위 확인창 */
.app-confirm-backdrop {
  z-index: 1200;
}
.app-confirm-modal {
  max-width: 400px;
  width: calc(100vw - 56px);
  box-sizing: border-box;
}

.confirm-msg {
  font-size: 14px;
  color: var(--text);
  line-height: 1.65;
  margin: 0;
  white-space: pre-line;
}

html.night-mode .confirm-msg {
  color: var(--dark-text) !important;
}

.app-confirm-modal .app-modal-field {
  margin-top: 14px;
}

.pw-input-wrap {
  position: relative;
  display: flex;
  align-items: center;
}

.pw-input-wrap .app-modal-input {
  padding-right: 36px;
  width: 100%;
}

.pw-toggle {
  position: absolute;
  right: 8px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 2px;
  border: none;
  background: transparent;
  color: var(--text-secondary, #888);
  cursor: pointer;
  border-radius: 4px;
  flex-shrink: 0;
}

.pw-toggle:hover {
  color: var(--text-primary, #333);
}

.pw-hint {
  font-size: 12px;
  color: var(--color-error, #e53e3e);
  margin: 4px 0 0;
}
</style>
