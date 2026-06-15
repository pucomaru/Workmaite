<template>
  <Teleport to="body">
    <div v-if="confirmState" class="app-modal-backdrop app-confirm-backdrop" @click.self="cancel">
      <div class="app-modal app-confirm-modal" role="dialog" aria-modal="true">
        <div class="app-modal-body">
          <p class="confirm-msg">{{ confirmState.message }}</p>
          <div v-if="confirmState.mode === 'prompt'" class="app-modal-field">
            <input
              type="text"
              name="prompt"
              ref="inputEl"
              v-model="inputValue"
              class="app-modal-input"
              :placeholder="confirmState.placeholder"
              @keydown.enter="ok"
              @keydown.esc="cancel"
            />
          </div>
        </div>
        <div class="app-modal-footer">
          <button class="app-btn-cancel" @click="cancel">{{ confirmState.cancelText }}</button>
          <button :class="confirmState.danger ? 'app-btn-danger' : 'app-btn-primary'" @click="ok">
            {{ confirmState.okText }}
          </button>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup>
import { ref, watch, nextTick } from 'vue'
import { confirmState, settleConfirm } from '../composables/useConfirm'

const inputValue = ref('')
const inputEl = ref(null)

watch(confirmState, async s => {
  if (s?.mode === 'prompt') {
    inputValue.value = ''
    await nextTick()
    inputEl.value?.focus()
  }
})

function ok() {
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
  max-width: 380px;
  width: 100%;
}
.confirm-msg {
  font-size: 14px;
  color: var(--text);
  line-height: 1.65;
  margin: 0;
  white-space: pre-line;
}
.app-confirm-modal .app-modal-field {
  margin-top: 14px;
}
</style>
