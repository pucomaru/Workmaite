<template>
  <div class="app-pagination" :class="{ 'app-pagination-dark': dark }">
    <button class="page-btn" :disabled="modelValue <= 1" @click="go(modelValue - 1)">
      <i class="bi bi-chevron-left"></i>
    </button>
    <button
      v-for="p in visiblePages" :key="p"
      class="page-btn page-num"
      :class="{ active: p === modelValue }"
      @click="go(p)"
    >{{ p }}</button>
    <button class="page-btn" :disabled="modelValue >= totalPages" @click="go(modelValue + 1)">
      <i class="bi bi-chevron-right"></i>
    </button>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  modelValue: { type: Number, default: 1 },
  totalItems: { type: Number, default: 0 },
  pageSize: { type: Number, default: 10 },
  maxVisible: { type: Number, default: 5 },
  dark: { type: Boolean, default: false },
})

const emit = defineEmits(['update:modelValue'])

const totalPages = computed(() => Math.max(1, Math.ceil(props.totalItems / props.pageSize)))

const visiblePages = computed(() => {
  const total = totalPages.value
  const max = props.maxVisible
  let start = Math.max(1, props.modelValue - Math.floor(max / 2))
  const end = Math.min(total, start + max - 1)
  start = Math.max(1, end - max + 1)
  return Array.from({ length: end - start + 1 }, (_, i) => start + i)
})

function go(p) {
  if (p < 1 || p > totalPages.value || p === props.modelValue) return
  emit('update:modelValue', p)
}
</script>

<style>
.app-pagination {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 4px;
}
.app-pagination .page-btn {
  min-width: 18px;
  height: 18px;
  padding: 0 6px;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: var(--bg-card);
  color: var(--text-muted);
  font-size: 12px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
}
.app-pagination .page-btn:hover:not(:disabled):not(.active) {
  background: var(--surface);
  color: var(--text);
}
.app-pagination .page-btn:disabled {
  opacity: .4;
  cursor: default;
}
.app-pagination .page-btn.active {
  background: var(--primary);
  border-color: var(--primary);
  color: #fff;
  font-weight: 600;
  cursor: default;
}
/* ── Dark variant (AppTable의 dark prop과 동일하게 사용) ── */
.app-pagination-dark .page-btn {
  background: var(--white-06);
  border-color: var(--white-10);
  color: var(--dark-muted);
}
.app-pagination-dark .page-btn:hover:not(:disabled):not(.active) {
  background: var(--white-12);
  color: var(--dark-text);
}
.app-pagination-dark .page-btn.active {
  background: var(--accent);
  border-color: var(--accent);
  color: #fff;
}
</style>
