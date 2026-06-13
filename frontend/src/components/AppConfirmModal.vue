<template>
  <Teleport to="body">
    <Transition name="confirm-fade">
      <div v-if="confirmState" class="confirm-backdrop" @click.self="cancel">
        <div class="confirm-box" role="dialog" aria-modal="true">
          <p class="confirm-msg">{{ confirmState.message }}</p>
          <input
            v-if="confirmState.mode === 'prompt'"
            ref="inputEl"
            v-model="inputValue"
            class="confirm-input"
            :placeholder="confirmState.placeholder"
            @keydown.enter="ok"
            @keydown.esc="cancel"
          />
          <div class="confirm-actions">
            <button class="confirm-btn cancel" @click="cancel">{{ confirmState.cancelText }}</button>
            <button class="confirm-btn ok" :class="{ danger: confirmState.danger }" @click="ok">{{ confirmState.okText }}</button>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup>
import { ref, watch, nextTick } from 'vue'
import { confirmState, settleConfirm } from '../composables/useConfirm'

const inputValue = ref('')
const inputEl = ref(null)

watch(confirmState, async (s) => {
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
.confirm-backdrop {
  position: fixed; inset: 0; z-index: 2900;
  background: rgba(0,0,0,.45); backdrop-filter: blur(2px);
  display: flex; align-items: center; justify-content: center; padding: 20px;
}
.confirm-box {
  width: 100%; max-width: 360px;
  background: var(--bg-card); border-radius: 14px;
  box-shadow: 0 20px 60px rgba(0,0,0,.25);
  padding: 22px 22px 18px;
}
.confirm-msg { font-size: 14px; color: var(--text); line-height: 1.65; margin: 0 0 16px; white-space: pre-line; }
.confirm-input {
  width: 100%; padding: 8px 12px; margin-bottom: 16px;
  border: 1px solid var(--border); border-radius: 8px;
  font-size: 13px; background: var(--bg-card); color: var(--text); outline: none;
}
.confirm-input:focus { border-color: var(--accent); }
.confirm-actions { display: flex; justify-content: flex-end; gap: 8px; }
.confirm-btn {
  padding: 7px 16px; border-radius: 8px; font-size: 13px; font-weight: 600; cursor: pointer;
  border: 1px solid var(--border); background: var(--bg-card); color: var(--text-muted);
}
.confirm-btn.cancel:hover { background: var(--surface); }
.confirm-btn.ok { background: var(--primary); border-color: var(--primary); color: #fff; }
.confirm-btn.ok:hover { opacity: .9; }
.confirm-btn.ok.danger { background: var(--danger); border-color: var(--danger); }
.confirm-fade-enter-active, .confirm-fade-leave-active { transition: opacity .15s; }
.confirm-fade-enter-from, .confirm-fade-leave-to { opacity: 0; }
</style>
