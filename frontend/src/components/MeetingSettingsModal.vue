<script setup>
import { ref, watch } from 'vue'
import DateInput from './DateInput.vue'
import api from '../api'

const props = defineProps({
  settings: Object,   // { form, members, removedIds, meeting }
  nightMode: Boolean,
  saving: Boolean,
})
const emit = defineEmits(['close', 'save'])

const ROLE_MAP = { admin: '간사', member: '참여자' }

const AVATAR_COLORS = ['#6366f1','#3b82f6','#10b981','#f59e0b','#ef4444','#8b5cf6','#ec4899']
function avatarColor(name) {
  let h = 0
  for (const c of (name || '')) h = (h * 31 + c.charCodeAt(0)) % AVATAR_COLORS.length
  return AVATAR_COLORS[h]
}
function initials(name) { return (name || '?')[0] }

// 멤버 검색
const searchQ = ref('')
const searchResults = ref([])
const searchLoading = ref(false)
let searchTimer = null

watch(() => props.settings, () => {
  searchQ.value = ''
  searchResults.value = []
})

function onSearchInput(q) {
  searchQ.value = q
  clearTimeout(searchTimer)
  if (!q.trim()) { searchResults.value = []; return }
  searchTimer = setTimeout(async () => {
    searchLoading.value = true
    try {
      const res = await api.get('/api/v1/users/search', { params: { q } })
      searchResults.value = res.data
    } catch { searchResults.value = [] }
    finally { searchLoading.value = false }
  }, 300)
}

function addMember(user) {
  if (!props.settings) return
  if (props.settings.members.find(m => m.userId === user.id)) return
  props.settings.members.push({ id: null, userId: user.id, name: user.name || user.email, email: user.email, role: 'member' })
  searchQ.value = ''
  searchResults.value = []
}

function removeMember(idx) {
  const m = props.settings.members[idx]
  if (m.id) props.settings.removedIds.push(m.id)
  props.settings.members.splice(idx, 1)
}
</script>

<template>
  <Teleport to="body">
    <div v-if="settings" class="app-modal-backdrop">
      <div class="app-modal app-modal-lg" :class="{ dark: nightMode }">
        <div class="app-modal-header">
          <span class="app-modal-title">회의체 설정</span>
          <button class="app-modal-close" @click="emit('close')">
            <svg width="14" height="14" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24"><path d="M6 18L18 6M6 6l12 12"/></svg>
          </button>
        </div>
        <div class="app-modal-body settings-body">
          <!-- 기본 정보 -->
          <div class="settings-section">
            <div class="settings-section-title">기본 정보</div>
            <div class="app-modal-field">
              <label>회의체 이름 <span class="req">*</span></label>
              <input v-model="settings.form.title" class="app-modal-input" />
            </div>
            <div class="app-modal-field">
              <label>소개</label>
              <textarea v-model="settings.form.purpose" class="app-modal-input" rows="2" placeholder="이 회의체의 목적이나 소개..."></textarea>
            </div>
            <div class="app-modal-field">
              <label>유형</label>
              <select v-model="settings.form.meeting_type" class="app-modal-input">
                <option value="Weekly">Weekly</option>
                <option value="Monthly">Monthly</option>
                <option value="Quarterly">Quarterly</option>
              </select>
            </div>
            <div class="app-modal-field-row">
              <div class="app-modal-field">
                <label>시작일</label>
                <DateInput v-model="settings.form.start_date" class="app-modal-input" />
              </div>
              <div class="app-modal-field">
                <label>종료일</label>
                <DateInput v-model="settings.form.end_date" class="app-modal-input" />
              </div>
            </div>
            <div class="app-modal-field">
              <label>회의체 지침</label>
              <textarea v-model="settings.form.guidelines" class="app-modal-input" rows="4"
                placeholder="운영 지침, 규칙, 주의사항 등을 입력하세요...&#10;예: 매주 월요일 10시, 의장 승인 필수, 안건 72시간 전 제출 등"></textarea>
            </div>
          </div>

          <!-- 참여자 -->
          <div class="settings-section">
            <div class="settings-section-title">
              참여자 <span class="member-cnt-badge">{{ settings.members.length }}명</span>
            </div>
            <div class="member-search-wrap">
              <svg width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><circle cx="11" cy="11" r="8"/><path d="M21 21l-4.35-4.35"/></svg>
              <input :value="searchQ" @input="onSearchInput($event.target.value)" class="member-search-input" placeholder="이름 또는 이메일로 검색 후 추가..." />
              <span v-if="searchLoading" class="search-spinner">↻</span>
            </div>
            <div v-if="searchResults.length" class="member-search-results">
              <div v-for="u in searchResults" :key="u.id" class="member-search-item" @click="addMember(u)">
                <div class="ui-avatar ui-avatar-sm" :style="{ background: avatarColor(u.name) }">{{ initials(u.name || u.email) }}</div>
                <div class="ms-info">
                  <span class="ms-name">{{ u.name || '이름없음' }}</span>
                  <span class="ms-email">{{ u.email }}</span>
                </div>
                <span class="ms-add-hint">+ 추가</span>
              </div>
            </div>
            <div class="settings-member-list">
              <div v-if="!settings.members.length" class="settings-empty-members">참여자가 없습니다.</div>
              <div v-for="(mb, idx) in settings.members" :key="mb.userId" class="settings-member-row">
                <div class="ui-avatar ui-avatar-sm" :style="{ background: avatarColor(mb.name) }">{{ initials(mb.name) }}</div>
                <div class="sm-info">
                  <span class="sm-name">{{ mb.name }}</span>
                  <span class="sm-email">{{ mb.position || mb.department || mb.email }}</span>
                </div>
                <select v-model="mb.role" class="app-select">
                  <option v-for="(label, val) in ROLE_MAP" :key="val" :value="val">{{ label }}</option>
                </select>
                <button class="sm-remove" @click="removeMember(idx)" title="제거">
                  <svg width="12" height="12" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24"><path d="M18 6L6 18M6 6l12 12"/></svg>
                </button>
              </div>
            </div>
          </div>
        </div>
        <div class="app-modal-footer">
          <button class="app-btn-cancel" @click="emit('close')">취소</button>
          <button class="app-btn-primary" :disabled="!settings.form.title.trim() || saving" @click="emit('save')">
            {{ saving ? '저장 중...' : '저장' }}
          </button>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.settings-body { gap: 0; }
.settings-section { padding: 14px 0; border-bottom: 1px solid var(--surface-2); display: flex; flex-direction: column; gap: 10px; }
.settings-section:last-child { border-bottom: none; padding-bottom: 0; }
.settings-section-title { font-size: 12px; font-weight: 700; color: var(--text-muted); text-transform: uppercase; letter-spacing: .05em; display: flex; align-items: center; gap: 8px; }
.member-cnt-badge { font-size: 11px; font-weight: 700; background: rgba(96,165,250,.15); color: #93c5fd; border-radius: 99px; padding: 1px 7px; text-transform: none; letter-spacing: 0; }
.req { color: var(--danger); }

.member-search-wrap { display: flex; align-items: center; gap: 8px; padding: 7px 10px; border: 1px solid var(--border); border-radius: 8px; background: var(--surface); }
.member-search-wrap svg { color: var(--dark-muted); flex-shrink: 0; }
.member-search-input { flex: 1; border: none; background: none; color: var(--dark-card); font-size: 12px; outline: none; }
.member-search-input::placeholder { color: var(--dark-muted); }
.search-spinner { color: var(--text-muted); font-size: 14px; flex-shrink: 0; }
.member-search-results { border: 1px solid var(--border); border-radius: 8px; overflow: hidden; background: #fff; }
.member-search-item { display: flex; align-items: center; gap: 10px; padding: 9px 12px; cursor: pointer; transition: background .1s; }
.member-search-item:hover { background: var(--surface); }
.ms-info { flex: 1; display: flex; flex-direction: column; }
.ms-name { font-size: 13px; font-weight: 600; color: var(--dark-card); }
.ms-email { font-size: 11px; color: var(--dark-muted); }
.ms-add-hint { font-size: 11px; font-weight: 700; color: var(--accent); flex-shrink: 0; }

.settings-member-list { display: flex; flex-direction: column; gap: 3px; max-height: 200px; overflow-y: auto; }
.settings-empty-members { font-size: 12px; color: var(--text-muted); padding: 6px 0; }
.settings-member-row { display: flex; align-items: center; gap: 10px; padding: 5px 6px; border-radius: 7px; transition: background .1s; }
.settings-member-row:hover { background: var(--surface); }
.sm-info { flex: 1; display: flex; flex-direction: column; min-width: 0; }
.sm-name { font-size: 13px; font-weight: 600; color: var(--dark-card); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.sm-email { font-size: 11px; color: var(--dark-muted); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.sm-remove { width: 22px; height: 22px; border-radius: 5px; border: none; background: rgba(239,68,68,.08); color: #f87171; cursor: pointer; display: flex; align-items: center; justify-content: center; flex-shrink: 0; transition: background .15s; }
.sm-remove:hover { background: rgba(239,68,68,.2); }

/* Dark mode */
.app-modal.dark .settings-section { border-bottom-color: rgba(255,255,255,.07); }
.app-modal.dark .settings-section-title { color: var(--text-dim); }
.app-modal.dark .member-search-wrap { border-color: rgba(255,255,255,.12); background: rgba(255,255,255,.05); }
.app-modal.dark .member-search-wrap svg { color: var(--text-dim); }
.app-modal.dark .member-search-input { color: var(--surface-2); }
.app-modal.dark .member-search-input::placeholder { color: var(--dark-border); }
.app-modal.dark .member-search-results { border-color: rgba(255,255,255,.1); background: var(--dark-bg); }
.app-modal.dark .member-search-item:hover { background: rgba(255,255,255,.06); }
.app-modal.dark .ms-name { color: var(--surface-2); }
.app-modal.dark .ms-email, .app-modal.dark .settings-empty-members { color: var(--text-dim); }
.app-modal.dark .settings-member-row:hover { background: rgba(255,255,255,.04); }
.app-modal.dark .sm-name { color: var(--surface-2); }
.app-modal.dark .sm-email { color: var(--text-dim); }
</style>
