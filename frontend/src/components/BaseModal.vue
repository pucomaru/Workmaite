<template>
  <Teleport to="body">
    <div v-if="modelValue" class="base-modal-overlay" @click.self="$emit('update:modelValue', false)">
      <div class="base-modal" :style="{ width: width }">
        <!-- 헤더 -->
        <div class="base-modal-header">
          <div class="base-modal-title">
            <slot name="title" />
          </div>
          <div class="base-modal-header-actions">
            <slot name="header-actions" />
            <button class="base-modal-close" @click="$emit('update:modelValue', false)">✕</button>
          </div>
        </div>

        <!-- 본문 -->
        <div class="base-modal-body">
          <slot />
        </div>

        <!-- 푸터 (선택) -->
        <div v-if="$slots.footer" class="base-modal-footer">
          <slot name="footer" />
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup>
defineProps({
  modelValue: { type: Boolean, required: true },
  width: { type: String, default: 'min(520px, 95vw)' },
})
defineEmits(['update:modelValue'])
</script>

<style scoped>
.base-modal-overlay {
  position: fixed; inset: 0; z-index: 1000;
  background: rgba(0, 0, 0, .45);
  display: flex; align-items: center; justify-content: center;
}
.base-modal {
  background: var(--surface, #fff);
  border-radius: 16px;
  box-shadow: 0 20px 60px rgba(0, 0, 0, .25);
  max-height: 90vh;
  display: flex; flex-direction: column;
  overflow: hidden;
}
.base-modal-header {
  display: flex; align-items: center; justify-content: space-between;
  padding: 16px 20px;
  border-bottom: 1px solid var(--border);
  flex-shrink: 0; gap: 8px;
}
.base-modal-title {
  display: flex; align-items: center; gap: 8px;
  font-size: 15px; font-weight: 700; color: var(--text);
}
.base-modal-header-actions {
  display: flex; align-items: center; gap: 6px; flex-shrink: 0;
}
.base-modal-close {
  width: 28px; height: 28px; border-radius: 50%;
  border: none; background: var(--surface-2); color: var(--text-muted);
  cursor: pointer; font-size: 14px;
  display: flex; align-items: center; justify-content: center;
  transition: background .15s;
}
.base-modal-close:hover { background: var(--border); color: var(--text); }

.base-modal-body {
  flex: 1; overflow-y: auto;
}
.base-modal-footer {
  padding: 12px 20px;
  display: flex; justify-content: space-between; align-items: center;
  flex-shrink: 0; border-top: 1px solid var(--border);
}
</style>
