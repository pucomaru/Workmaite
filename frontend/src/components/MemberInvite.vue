<script setup>
import { ref } from 'vue'
import api from '../api'

const props = defineProps({
  modelValue:   { type: Array,   default: () => [] },
  lockedUserId: { type: Number,  default: null },
  nightMode:    { type: Boolean, default: false },
})
const emit = defineEmits(['update:modelValue'])

const ROLE_MAP = { admin: '간사', member: '참여자' }

const AVATAR_COLORS = ['#6366f1','#3b82f6','#10b981','#f59e0b','#ef4444','#8b5cf6','#ec4899']
function avatarColor(name) { let h = 0; for (const c of (name || '')) h = (h * 31 + c.charCodeAt(0)) % AVATAR_COLORS.length; return AVATAR_COLORS[h] }
function initials(name) { return (name || '?')[0] }

const searchQ = ref('')
const results = ref([])
const loading = ref(false)
let timer = null

function onSearch(q) {
  searchQ.value = q
  clearTimeout(timer)
  if (!q.trim()) { results.value = []; return }
  timer = setTimeout(async () => {
    loading.value = true
    try {
      const res = await api.get('/api/v1/users/search', { params: { q } })
      results.value = res.data.filter(u => !props.modelValue.find(m => m.userId === u.id))
    } catch { results.value = [] }
    finally { loading.value = false }
  }, 300)
}

function add(user) {
  if (props.modelValue.find(m => m.userId === user.id)) return
  emit('update:modelValue', [
    ...props.modelValue,
    { userId: user.id, name: user.name || user.email, email: user.email || user.employee_id, role: 'member' },
  ])
  searchQ.value = ''; results.value = []
}

function remove(idx) {
  const next = [...props.modelValue]
  next.splice(idx, 1)
  emit('update:modelValue', next)
}

function updateRole(idx, role) {
  emit('update:modelValue', props.modelValue.map((m, i) => i === idx ? { ...m, role } : m))
}
</script>

<template>
  <div class="mi-section" :class="{ dark: nightMode }">
    <div class="mi-title">
      참여자 <span class="mi-cnt-badge">{{ modelValue.length }}명</span>
    </div>

    <div class="mi-search-wrap">
      <svg width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><circle cx="11" cy="11" r="8"/><path d="M21 21l-4.35-4.35"/></svg>
      <input :value="searchQ" @input="onSearch($event.target.value)" class="mi-search-input" placeholder="이름 또는 이메일로 검색 후 추가..." />
      <span v-if="loading" class="mi-spinner">↻</span>
    </div>

    <div v-if="results.length" class="mi-search-results">
      <div v-for="u in results" :key="u.id" class="mi-search-item" @click="add(u)">
        <div class="ui-avatar ui-avatar-sm" :style="{ background: avatarColor(u.name) }">{{ initials(u.name || u.email) }}</div>
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
        <div class="ui-avatar ui-avatar-sm" :style="{ background: avatarColor(mb.name) }">{{ initials(mb.name) }}</div>
        <div class="mi-info">
          <span class="mi-name">
            {{ mb.name }}
            <span v-if="mb.userId === lockedUserId" class="mi-me-badge">나</span>
          </span>
          <span class="mi-email">{{ mb.position || mb.department || mb.email }}</span>
        </div>
        <select :value="mb.role" @change="updateRole(idx, $event.target.value)" class="app-select">
          <option v-for="(label, val) in ROLE_MAP" :key="val" :value="val">{{ label }}</option>
        </select>
        <button v-if="mb.userId !== lockedUserId" class="mi-remove" @click="remove(idx)" title="제거">
          <svg width="12" height="12" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24"><path d="M18 6L6 18M6 6l12 12"/></svg>
        </button>
        <span v-else class="mi-remove-ph"></span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.mi-section { display: flex; flex-direction: column; gap: 10px; padding: 14px 0; border-bottom: 1px solid var(--surface-2); }
.mi-section:last-child { border-bottom: none; padding-bottom: 0; }

.mi-title { font-size: 12px; font-weight: 700; color: var(--text-muted); text-transform: uppercase; letter-spacing: .05em; display: flex; align-items: center; gap: 8px; }
.mi-cnt-badge { font-size: 11px; font-weight: 700; background: rgba(96,165,250,.15); color: #93c5fd; border-radius: 99px; padding: 1px 7px; text-transform: none; letter-spacing: 0; }

.mi-search-wrap { display: flex; align-items: center; gap: 8px; padding: 7px 10px; border: 1px solid var(--border); border-radius: 8px; background: var(--surface); }
.mi-search-wrap svg { color: var(--dark-muted); flex-shrink: 0; }
.mi-search-input { flex: 1; border: none; background: none; color: var(--dark-card); font-size: 12px; outline: none; }
.mi-search-input::placeholder { color: var(--dark-muted); }
.mi-spinner { color: var(--text-muted); font-size: 14px; flex-shrink: 0; }

.mi-search-results { border: 1px solid var(--border); border-radius: 8px; overflow: hidden; background: #fff; }
.mi-search-item { display: flex; align-items: center; gap: 10px; padding: 9px 12px; cursor: pointer; transition: background .1s; }
.mi-search-item:hover { background: var(--surface); }
.mi-add-hint { font-size: 11px; font-weight: 700; color: var(--accent); flex-shrink: 0; }

.mi-member-list { display: flex; flex-direction: column; gap: 3px; max-height: 200px; overflow-y: auto; }
.mi-empty { font-size: 12px; color: var(--text-muted); padding: 6px 0; }
.mi-member-row { display: flex; align-items: center; gap: 10px; padding: 5px 6px; border-radius: 7px; transition: background .1s; }
.mi-member-row:hover { background: var(--surface); }

.mi-info { flex: 1; display: flex; flex-direction: column; min-width: 0; }
.mi-name { font-size: 13px; font-weight: 600; color: var(--dark-card); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.mi-email { font-size: 11px; color: var(--dark-muted); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.mi-me-badge { margin-left: 5px; font-size: 10px; font-weight: 700; padding: 1px 5px; border-radius: 3px; background: #dbeafe; color: #1d4ed8; vertical-align: middle; }

.mi-remove { width: 22px; height: 22px; border-radius: 5px; border: none; background: rgba(239,68,68,.08); color: #f87171; cursor: pointer; display: flex; align-items: center; justify-content: center; flex-shrink: 0; transition: background .15s; }
.mi-remove:hover { background: rgba(239,68,68,.2); }
.mi-remove-ph { width: 22px; flex-shrink: 0; }

/* Dark */
.mi-section.dark { border-bottom-color: rgba(255,255,255,.07); }
.mi-section.dark .mi-title { color: var(--text-dim); }
.mi-section.dark .mi-search-wrap { border-color: rgba(255,255,255,.12); background: rgba(255,255,255,.05); }
.mi-section.dark .mi-search-wrap svg { color: var(--text-dim); }
.mi-section.dark .mi-search-input { color: var(--surface-2); }
.mi-section.dark .mi-search-input::placeholder { color: var(--dark-border); }
.mi-section.dark .mi-search-results { border-color: rgba(255,255,255,.1); background: var(--dark-bg); }
.mi-section.dark .mi-search-item:hover { background: rgba(255,255,255,.06); }
.mi-section.dark .mi-name { color: var(--surface-2); }
.mi-section.dark .mi-email, .mi-section.dark .mi-empty { color: var(--text-dim); }
.mi-section.dark .mi-member-row:hover { background: rgba(255,255,255,.04); }
</style>
