<template>
  <Teleport to="body">
    <div class="toast-stack" aria-live="polite">
      <TransitionGroup name="toast">
        <div v-for="t in toasts" :key="t.id" class="toast-item" :class="`toast-${t.type}`" @click="dismissToast(t.id)">
          <i :class="ICONS[t.type]"></i>
          <span class="toast-msg">{{ t.message }}</span>
        </div>
      </TransitionGroup>
    </div>
  </Teleport>
</template>

<script setup>
import { toasts, dismissToast } from '../composables/useToast'

const ICONS = {
  success: 'bi bi-check-circle-fill',
  error: 'bi bi-exclamation-triangle-fill',
  info: 'bi bi-info-circle-fill',
}
</script>

<style scoped>
.toast-stack {
  position: fixed; bottom: 24px; left: 50%; transform: translateX(-50%);
  display: flex; flex-direction: column-reverse; align-items: center; gap: 8px;
  z-index: 3000; pointer-events: none;
}
.toast-item {
  display: flex; align-items: center; gap: 9px;
  max-width: min(480px, calc(100vw - 40px));
  background: var(--dark-card); color: var(--dark-text);
  border: 1px solid var(--white-12); border-radius: 10px;
  padding: 11px 16px; font-size: 13px; line-height: 1.5;
  box-shadow: 0 8px 24px rgba(0,0,0,.25);
  pointer-events: auto; cursor: pointer;
  white-space: pre-line;
}
.toast-success i { color: var(--success); }
.toast-error i { color: var(--danger-soft); }
.toast-info i { color: var(--accent-light); }
.toast-msg { word-break: break-word; }
.toast-enter-active, .toast-leave-active { transition: opacity .18s, transform .18s; }
.toast-enter-from, .toast-leave-to { opacity: 0; transform: translateY(8px); }
</style>
