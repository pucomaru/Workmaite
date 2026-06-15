<script setup>
import { ref, computed } from 'vue'

const props = defineProps({
  modelValue: { type: Array, default: () => [] }, // 선택된 부서명 문자열 배열
  options: { type: Array, default: () => [] }, // 선택 가능한 부서명 목록(검색 대상)
  nightMode: { type: Boolean, default: false },
})
const emit = defineEmits(['update:modelValue'])

const searchQ = ref('')

// 검색어로 옵션 필터(이미 선택된 부서 제외). 입력이 없으면 결과를 표시하지 않는다.
const filtered = computed(() => {
  const q = searchQ.value.trim().toLowerCase()
  if (!q) return []
  const selected = new Set(props.modelValue)
  return props.options.filter(d => d && !selected.has(d) && d.toLowerCase().includes(q))
})

// 옵션에 없는 부서명은 직접 추가 허용
const canAddCustom = computed(() => {
  const q = searchQ.value.trim()
  if (!q) return false
  const dup =
    props.modelValue.some(d => d === q) ||
    props.options.some(d => d.toLowerCase() === q.toLowerCase())
  return !dup
})

function add(dept) {
  const name = (dept || '').trim()
  if (!name || props.modelValue.includes(name)) return
  emit('update:modelValue', [...props.modelValue, name])
  searchQ.value = ''
}

function remove(idx) {
  const next = [...props.modelValue]
  next.splice(idx, 1)
  emit('update:modelValue', next)
}

function onEnter() {
  const q = searchQ.value.trim()
  if (!q) return
  if (filtered.value.length) add(filtered.value[0])
  else add(q)
}
</script>

<template>
  <div class="mi-section" :class="{ dark: nightMode }">
    <div class="mi-title">
      <span>참여 부서</span>
      <span class="mi-cnt-badge">{{ modelValue.length }}개</span>
    </div>

    <div class="mi-search-wrap">
      <svg
        width="13"
        height="13"
        fill="none"
        stroke="currentColor"
        stroke-width="2"
        viewBox="0 0 24 24"
      >
        <circle cx="11" cy="11" r="8" />
        <path d="M21 21l-4.35-4.35" />
      </svg>
      <input
        v-model="searchQ"
        @keydown.enter.prevent="onEnter"
        class="mi-search-input"
        placeholder="부서명으로 검색 후 추가 (Enter)"
      />
    </div>

    <div v-if="filtered.length || canAddCustom" class="mi-search-results">
      <div v-for="d in filtered" :key="d" class="mi-search-item" @click="add(d)">
        <span class="dept-dot"></span>
        <div class="mi-info">
          <span class="mi-name">{{ d }}</span>
        </div>
        <span class="mi-add-hint">+ 추가</span>
      </div>
      <div v-if="canAddCustom" class="mi-search-item" @click="add(searchQ)">
        <span class="dept-dot dept-dot-new"></span>
        <div class="mi-info">
          <span class="mi-name">"{{ searchQ.trim() }}" 직접 추가</span>
        </div>
        <span class="mi-add-hint">+ 추가</span>
      </div>
    </div>

    <div class="mi-member-list">
      <div v-if="!modelValue.length" class="mi-empty">참여 부서가 없습니다.</div>
      <div v-for="(d, idx) in modelValue" :key="d" class="mi-member-row">
        <span class="dept-dot"></span>
        <div class="mi-info">
          <span class="mi-name">{{ d }}</span>
        </div>
        <button class="mi-remove" @click="remove(idx)" title="제거">
          <svg
            width="12"
            height="12"
            fill="none"
            stroke="currentColor"
            stroke-width="2.5"
            viewBox="0 0 24 24"
          >
            <path d="M18 6L6 18M6 6l12 12" />
          </svg>
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* MemberInvite의 mi-section 룩을 재현 — 부서 버전 */
.mi-section {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.mi-title {
  font-size: 12px;
  font-weight: 600;
  color: var(--bs-body-color);
  text-transform: uppercase;
  letter-spacing: 0.04em;
  display: flex;
  align-items: center;
  gap: 8px;
}
.mi-cnt-badge {
  font-size: 11px;
  font-weight: 700;
  background: rgba(96, 165, 250, 0.15);
  color: var(--accent-soft);
  border-radius: 99px;
  padding: 1px 7px;
  text-transform: none;
  letter-spacing: 0;
  line-height: 1.6;
}
.mi-search-wrap {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 7px 10px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--surface);
}
.mi-search-wrap svg {
  color: var(--dark-muted);
  flex-shrink: 0;
}
.mi-search-input {
  flex: 1;
  border: none;
  background: none;
  color: var(--dark-card);
  font-size: 12px;
  outline: none;
}
.mi-search-input::placeholder {
  color: var(--dark-muted);
  background: none;
}
.mi-search-results {
  border: 1px solid var(--border);
  border-radius: 8px;
  /* 약 5줄까지만 보이고 나머지는 스크롤 */
  max-height: 175px;
  overflow-y: auto;
  background: #fff;
}
.mi-search-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 9px 12px;
  cursor: pointer;
  transition: background 0.1s;
}
.mi-search-item:hover {
  background: var(--surface);
}
.mi-add-hint {
  font-size: 11px;
  font-weight: 700;
  color: var(--accent);
  flex-shrink: 0;
}
.mi-member-list {
  display: flex;
  flex-direction: column;
  gap: 3px;
  max-height: 180px;
  overflow-y: auto;
}
.mi-empty {
  font-size: 12px;
  color: var(--text-muted);
  padding: 6px 0;
}
.mi-member-row {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 6px 8px;
  border-radius: 7px;
  transition: background 0.1s;
}
.mi-member-row:hover {
  background: var(--surface);
}
.mi-info {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
}
.mi-name {
  font-size: 13px;
  font-weight: 600;
  color: var(--text);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.dept-dot {
  width: 9px;
  height: 9px;
  border-radius: 99px;
  flex-shrink: 0;
  background: radial-gradient(circle at 38% 38%, #c4b5fd, #7c3aed);
}
.dept-dot-new {
  background: radial-gradient(circle at 38% 38%, #6ee7b7, #059669);
}
.mi-remove {
  width: 22px;
  height: 22px;
  border-radius: 5px;
  border: none;
  background: rgba(239, 68, 68, 0.08);
  color: var(--danger-soft);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  transition: background 0.15s;
}
.mi-remove:hover {
  background: rgba(239, 68, 68, 0.2);
}
/* Dark */
.mi-section.dark .mi-title {
  color: var(--dark-text);
}
.mi-section.dark .mi-search-wrap {
  border-color: var(--white-12);
  background: var(--white-05);
}
.mi-section.dark .mi-search-wrap svg {
  color: var(--text-muted);
}
.mi-section.dark .mi-search-input {
  color: var(--text-muted);
}
.mi-section.dark .mi-search-input::placeholder {
  color: var(--dark-border);
}
.mi-section.dark .mi-search-results {
  border-color: var(--white-10);
  background: var(--dark-bg);
}
.mi-section.dark .mi-search-item:hover {
  background: var(--white-06);
}
.mi-section.dark .mi-name {
  color: var(--text-muted);
}
.mi-section.dark .mi-empty {
  color: var(--text-muted);
}
.mi-section.dark .mi-member-row:hover {
  background: var(--white-04);
}
</style>
