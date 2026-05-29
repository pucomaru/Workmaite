<script setup>
import { ref } from 'vue'
import api from '../api'

// modelValue: [{ userId, name, email, role }]
const props = defineProps({
  modelValue: { type: Array, default: () => [] }
})
const emit = defineEmits(['update:modelValue'])

const search = ref('')
const results = ref([])
const loading = ref(false)
let timer = null

const AVATAR_COLORS = ['#6366f1','#3b82f6','#10b981','#f59e0b','#ef4444','#8b5cf6','#ec4899']
function avatarColor(name) { let h=0; for(const c of (name||'')) h=(h*31+c.charCodeAt(0))%AVATAR_COLORS.length; return AVATAR_COLORS[h] }
function initials(name) { return (name||'?')[0] }

function onSearch(q) {
  search.value = q
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

function add(user, role = 'member') {
  if (props.modelValue.find(m => m.userId === user.id)) return
  emit('update:modelValue', [
    ...props.modelValue,
    { userId: user.id, name: user.name || user.email, email: user.email || user.employee_id, role }
  ])
  search.value = ''; results.value = []
}

function remove(idx) {
  const next = [...props.modelValue]
  next.splice(idx, 1)
  emit('update:modelValue', next)
}

function updateRole(idx, role) {
  const next = props.modelValue.map((m, i) => i === idx ? { ...m, role } : m)
  emit('update:modelValue', next)
}
</script>

<template>
  <div class="mi-wrap">
    <div class="mi-search">
      <svg width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><circle cx="11" cy="11" r="8"/><path d="M21 21l-4.35-4.35"/></svg>
      <input :value="search" @input="onSearch($event.target.value)" class="mi-input" placeholder="이름 또는 이메일로 검색..." />
      <span v-if="loading" class="mi-spinner">↻</span>
    </div>

    <div v-if="results.length" class="mi-results">
      <div v-for="u in results" :key="u.id" class="mi-result-item">
        <div class="mi-avatar" :style="{ background: avatarColor(u.name) }">{{ initials(u.name || u.email) }}</div>
        <div class="mi-info">
          <span class="mi-name">{{ u.name || '이름없음' }}</span>
          <span class="mi-email">{{ u.email || u.employee_id }}</span>
        </div>
        <div class="mi-role-btns">
          <button class="mi-role-btn admin" @click="add(u, 'admin')">간사</button>
          <button class="mi-role-btn" @click="add(u, 'member')">참여자</button>
        </div>
      </div>
    </div>

    <div v-if="modelValue.length" class="mi-member-list">
      <div v-for="(mb, idx) in modelValue" :key="mb.userId" class="mi-member-row">
        <div class="mi-avatar" :style="{ background: avatarColor(mb.name) }">{{ initials(mb.name) }}</div>
        <div class="mi-info">
          <span class="mi-name">{{ mb.name }}</span>
          <span class="mi-email">{{ mb.email }}</span>
        </div>
        <select :value="mb.role" @change="updateRole(idx, $event.target.value)" class="mi-role-select">
          <option value="admin">간사</option>
          <option value="member">참여자</option>
        </select>
        <button class="mi-remove" @click="remove(idx)">
          <svg width="12" height="12" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24"><path d="M18 6L6 18M6 6l12 12"/></svg>
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.mi-wrap { display:flex;flex-direction:column;gap:6px; }
.mi-search { display:flex;align-items:center;gap:6px;border:1px solid var(--border, #e2e8f0);border-radius:8px;padding:5px 8px; }
.mi-input { flex:1;border:none;outline:none;font-size:12px;color:#1e293b;background:transparent; }
.mi-spinner { font-size:11px;color:#94a3b8; }
.mi-results { border:1px solid var(--border, #e2e8f0);border-radius:8px;overflow:hidden; }
.mi-result-item { display:flex;align-items:center;gap:8px;padding:7px 10px;border-bottom:1px solid var(--border, #e2e8f0);font-size:12px; }
.mi-result-item:last-child { border-bottom:none; }
.mi-avatar { width:24px;height:24px;border-radius:50%;color:#fff;font-size:11px;font-weight:700;display:flex;align-items:center;justify-content:center;flex-shrink:0; }
.mi-info { flex:1;min-width:0;display:flex;flex-direction:column;gap:1px; }
.mi-name { font-weight:600;color:#1e293b;overflow:hidden;text-overflow:ellipsis;white-space:nowrap; }
.mi-email { font-size:11px;color:#94a3b8;overflow:hidden;text-overflow:ellipsis;white-space:nowrap; }
.mi-role-btns { display:flex;gap:4px;flex-shrink:0; }
.mi-role-btn { padding:2px 8px;font-size:11px;cursor:pointer;border-radius:4px;border:1px solid #475569;background:transparent;color:#94a3b8;transition:all .15s; }
.mi-role-btn:hover { border-color:#60a5fa;color:#60a5fa; }
.mi-role-btn.admin { background:#1d4ed8;border-color:#1d4ed8;color:#fff; }
.mi-role-btn.admin:hover { background:#2563eb; }
.mi-member-list { display:flex;flex-direction:column;gap:4px; }
.mi-member-row { display:flex;align-items:center;gap:8px;padding:5px 8px;background:#f8fafc;border-radius:7px;font-size:12px; }
.mi-role-select { font-size:11px;border:1px solid var(--border, #e2e8f0);border-radius:5px;padding:2px 4px;background:#fff;color:#475569;cursor:pointer;outline:none; }
.mi-remove { background:none;border:none;cursor:pointer;color:#94a3b8;display:flex;align-items:center;justify-content:center;flex-shrink:0;transition:color .15s; }
.mi-remove:hover { color:#ef4444; }
</style>
