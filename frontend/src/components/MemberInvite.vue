<script setup>
import { ref } from 'vue'
import api from '../api'
import { avatarColor, initials } from '../utils/avatar'

const props = defineProps({
  modelValue: { type: Array, default: () => [] },
  lockedUserId: { type: Number, default: null },
  nightMode: { type: Boolean, default: false },
  // true면 역할 선택 UI를 숨긴다(역할이 자동 결정되는 회의 생성 모달용). 멤버 객체의 role은 유지.
  hideRole: { type: Boolean, default: false },
})
const emit = defineEmits(['update:modelValue'])

const ROLE_MAP = { admin: '간사', member: '참여자' }

const searchQ = ref('')
const results = ref([])
const loading = ref(false)
let timer = null

function onSearch(q) {
  searchQ.value = q
  clearTimeout(timer)
  if (!q.trim()) {
    results.value = []
    return
  }
  timer = setTimeout(async () => {
    loading.value = true
    try {
      const res = await api.get('/api/v1/users/search', { params: { q } })
      results.value = res.data.filter(u => !props.modelValue.find(m => m.userId === u.id))
    } catch {
      results.value = []
    } finally {
      loading.value = false
    }
  }, 300)
}

function add(user) {
  if (props.modelValue.find(m => m.userId === user.id)) return
  emit('update:modelValue', [
    ...props.modelValue,
    {
      userId: user.id,
      name: user.name || user.email,
      email: user.email || user.employee_id,
      role: 'member',
    },
  ])
  searchQ.value = ''
  results.value = []
}

function remove(idx) {
  const next = [...props.modelValue]
  next.splice(idx, 1)
  emit('update:modelValue', next)
}

function updateRole(idx, role) {
  emit(
    'update:modelValue',
    props.modelValue.map((m, i) => (i === idx ? { ...m, role } : m)),
  )
}
</script>

<template>
  <div class="mi-section" :class="{ dark: nightMode }">
    <div class="mi-title">
      <span>참여자 <span class="req">*</span></span>
      <span class="mi-cnt-badge">{{ modelValue.length }}명</span>
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
        id="mi-search"
        name="mi-search"
        :value="searchQ"
        @input="onSearch($event.target.value)"
        class="mi-search-input"
        placeholder="이름 또는 이메일로 검색 후 추가"
      />
      <span v-if="loading" class="mi-spinner">↻</span>
    </div>

    <div v-if="results.length" class="mi-search-results">
      <div v-for="u in results" :key="u.id" class="mi-search-item" @click="add(u)">
        <div class="ui-avatar ui-avatar-sm" :style="{ background: avatarColor(u.name) }">
          {{ initials(u.name || u.email) }}
        </div>
        <div class="mi-info">
          <span class="mi-name">{{ u.name || '이름없음' }}</span>
          <span class="mi-email">{{ u.email }}</span>
        </div>
        <span class="mi-add-hint">+ 추가</span>
      </div>
    </div>

    <div class="mi-member-list">
      <div v-if="!modelValue.length" class="mi-empty">참여자가 없습니다.</div>
      <div v-for="(mb, idx) in modelValue" :key="mb.userId" class="mi-member-row">
        <div class="ui-avatar ui-avatar-sm" :style="{ background: avatarColor(mb.name) }">
          {{ initials(mb.name) }}
        </div>
        <div class="mi-info">
          <span class="mi-name">
            {{ mb.name }}
            <span v-if="mb.userId === lockedUserId" class="mi-me-badge">나</span>
          </span>
          <span class="mi-email">{{ mb.position || mb.department || mb.email }}</span>
        </div>
        <select
          v-if="!hideRole"
          :value="mb.role"
          @change="updateRole(idx, $event.target.value)"
          name="role"
          class="app-select"
        >
          <option v-for="(label, val) in ROLE_MAP" :key="val" :value="val">{{ label }}</option>
        </select>
        <span v-else class="mi-role-text">{{ ROLE_MAP[mb.role] || '참여자' }}</span>
        <button
          v-if="mb.userId !== lockedUserId"
          class="mi-remove"
          @click="remove(idx)"
          title="제거"
        >
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
        <span v-else class="mi-remove-ph"></span>
      </div>
    </div>
  </div>
</template>

<style scoped>
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
.mi-spinner {
  color: var(--text-muted);
  font-size: 14px;
  flex-shrink: 0;
}

.mi-search-results {
  border: 1px solid var(--border);
  border-radius: 8px;
  overflow: hidden;
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
  max-height: 200px;
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
  padding: 5px 6px;
  border-radius: 7px; 
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
.mi-role-text {
  align-self: flex-start;
  font-size: 13px;
  font-weight: 600;
  color: var(--text);
}
.mi-email {
  font-size: 11px;
  color: var(--dark-muted);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.mi-me-badge {
  margin-left: 5px;
  font-size: 10px;
  font-weight: 700;
  padding: 1px 5px;
  border-radius: 3px;
  background: var(--accent-bg-2);
  color: var(--accent-strong);
  vertical-align: baseline;
  line-height: 1.6;
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
.mi-remove-ph {
  width: 22px;
  flex-shrink: 0;
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
.mi-section.dark .mi-email,
.mi-section.dark .mi-empty {
  color: var(--text-muted);
}
.mi-section.dark .mi-member-row:hover {
  background: var(--white-04);
}
</style>
