<script setup>
const props = defineProps({
  steps: { type: Array, required: true },
  currentStep: { type: Number, default: 0 },
})
const emit = defineEmits(['stepClick'])

function isDone(i) {
  return i < props.currentStep
}
function isActive(i) {
  return i === props.currentStep
}
function canNav(i) {
  return i < props.currentStep
}
function click(i) {
  if (canNav(i)) emit('stepClick', i)
}
</script>

<template>
  <div class="psb-bar">
    <template v-for="(step, i) in steps" :key="i">
      <button
        class="psb-step"
        :class="{ 'psb-active': isActive(i), 'psb-done': isDone(i), 'psb-nav': canNav(i) }"
        :style="canNav(i) ? {} : { cursor: 'default' }"
        :title="canNav(i) ? step + ' 단계로 돌아가기' : ''"
        @click="click(i)"
      >
        <span class="psb-dot">
          <svg
            v-if="isDone(i)"
            width="9"
            height="9"
            fill="none"
            stroke="currentColor"
            stroke-width="3"
            viewBox="0 0 24 24"
          >
            <path d="M20 6L9 17l-5-5" />
          </svg>
          <span v-else>{{ i + 1 }}</span>
        </span>
        <span class="psb-label">{{ step }}</span>
      </button>
      <div
        v-if="i < steps.length - 1"
        class="psb-line"
        :class="{ 'psb-line-done': currentStep > i }"
      ></div>
    </template>
  </div>
</template>

<style scoped>
.psb-bar {
  display: flex;
  align-items: flex-start;
  gap: 0;
}
.psb-step {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  background: none;
  border: none;
  padding: 0;
  cursor: default;
}
.psb-step.psb-nav {
  cursor: pointer;
}
.psb-step.psb-nav:hover .psb-dot {
  border-color: var(--accent-light);
}
.psb-dot {
  width: 22px;
  height: 22px;
  border-radius: 50%;
  border: 1.5px solid var(--dark-border);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 10px;
  font-weight: 700;
  color: var(--text-muted);
  transition: all 0.2s;
}
.psb-step.psb-active .psb-dot {
  background: var(--accent);
  border-color: var(--accent);
  color: #fff;
}
.psb-step.psb-done .psb-dot {
  background: rgba(59, 130, 246, 0.15);
  border-color: var(--accent);
  color: var(--accent-light);
}
.psb-label {
  font-size: 10px;
  color: var(--text-muted);
  font-weight: 500;
  white-space: nowrap;
}
.psb-step.psb-active .psb-label {
  color: var(--accent-soft);
  font-weight: 700;
}
.psb-step.psb-done .psb-label {
  color: var(--accent);
}
.psb-line {
  flex: 1;
  height: 1.5px;
  background: var(--dark-card);
  margin-top: 10px;
  transition: background 0.2s;
  min-width: 12px;
}
.psb-line.psb-line-done {
  background: var(--accent);
}
</style>
