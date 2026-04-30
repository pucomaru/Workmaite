<script setup>
import { ref, onMounted, computed } from 'vue'
import { useRoute } from 'vue-router'
import api from '../api'

const route = useRoute()
const meetingId = computed(() => Number(route.params.meetingId))

const memory = ref([])
const meeting = ref(null)
const editingId = ref(null)
const editTitle = ref('')
const editContent = ref('')
const showAdd = ref(false)
const newItem = ref({ category: 'meeting_standard', title: '', content: '' })
const refreshing = ref(false)
const refreshDone = ref(false)
const loading = ref(false)

const categories = [
  { value: 'report_standard',  label: '📋 보고서 기준',  color: '#dbeafe', border: '#93c5fd', text: '#1d4ed8' },
  { value: 'agenda_standard',  label: '📌 아젠다 기준',  color: '#fef9c3', border: '#fde047', text: '#854d0e' },
  { value: 'todo_standard',    label: '✅ 과제 기준',    color: '#dcfce7', border: '#86efac', text: '#166534' },
  { value: 'meeting_standard', label: '🎙 회의 기준',    color: '#f3e8ff', border: '#d8b4fe', text: '#6b21a8' },
]

onMounted(async () => {
  await Promise.all([loadMemory(), loadMeeting()])
})

async function loadMemory() {
  const { data } = await api.get(`/api/tacit-knowledge/meeting/${meetingId.value}`)
  memory.value = data
}

async function loadMeeting() {
  const { data } = await api.get('/api/meetings')
  meeting.value = data.find(m => m.id === meetingId.value) || null
}

async function refreshMemory() {
  refreshing.value = true
  refreshDone.value = false
  try {
    await api.post(`/api/tacit-knowledge/meeting/${meetingId.value}/refresh`)
    setTimeout(async () => {
      await loadMemory()
      refreshing.value = false
      refreshDone.value = true
      setTimeout(() => { refreshDone.value = false }, 4000)
    }, 4000)
  } catch {
    refreshing.value = false
  }
}

async function saveEdit(item) {
  loading.value = true
  try {
    await api.patch(`/api/tacit-knowledge/meeting-item/${item.id}`, {
      title: editTitle.value,
      content: editContent.value,
    })
    await loadMemory()
    editingId.value = null
  } finally {
    loading.value = false
  }
}

async function deleteItem(item) {
  if (!confirm(`"${item.title}" 메모리를 삭제하시겠습니까?`)) return
  await api.delete(`/api/tacit-knowledge/meeting-item/${item.id}`)
  await loadMemory()
}

async function addItem() {
  if (!newItem.value.title.trim() || !newItem.value.content.trim()) return
  loading.value = true
  try {
    await api.post(`/api/tacit-knowledge/meeting/${meetingId.value}`, newItem.value)
    await loadMemory()
    showAdd.value = false
    newItem.value = { category: 'meeting_standard', title: '', content: '' }
  } finally {
    loading.value = false
  }
}

function startEdit(item) {
  editingId.value = item.id
  editTitle.value = item.title
  editContent.value = item.content
}

function catMeta(c) {
  return categories.find(x => x.value === c) || categories[3]
}

function formatDate(d) {
  if (!d) return ''
  return new Date(d).toLocaleDateString('ko-KR', { month: 'short', day: 'numeric' })
}

const grouped = computed(() => {
  const map = {}
  for (const cat of categories) {
    const items = memory.value.filter(m => m.category === cat.value)
    if (items.length) map[cat.value] = { ...cat, items }
  }
  return map
})
</script>

<template>
  <div class="memory-page">

    <!-- 혜안 헤더 배너 -->
    <div class="hyean-banner">
      <div class="hyean-avatar">
        <img src="/src/assets/agents/hyean.png" @error="e => e.target.style.display='none'" alt="" />
        <span class="hyean-emoji">🧠</span>
      </div>
      <div class="hyean-info">
        <div class="hyean-name">혜안 <span class="hyean-badge">AI 메모리 관리자</span></div>
        <div class="hyean-desc">
          {{ meeting?.title || '이 회의체' }}의 활동 패턴을 분석해 메모리를 관리합니다.
          루프가 시작될 때마다 자동으로 학습합니다.
        </div>
      </div>
      <div class="hyean-actions">
        <button class="btn-hyean-add" @click="showAdd = !showAdd">＋ 직접 추가</button>
        <button class="btn-hyean-refresh" :disabled="refreshing" @click="refreshMemory">
          <span v-if="refreshing" class="spin">⟳</span>
          <span v-else-if="refreshDone">✓ 완료</span>
          <span v-else>🔄 AI 갱신</span>
        </button>
      </div>
    </div>

    <!-- 갱신 중 상태 -->
    <div v-if="refreshing" class="thinking-bar">
      <span class="dot-anim">●</span><span class="dot-anim" style="animation-delay:.2s">●</span><span class="dot-anim" style="animation-delay:.4s">●</span>
      혜안이 회의 활동을 분석하고 있습니다...
    </div>
    <div v-else-if="refreshDone" class="done-bar">
      ✓ 메모리 갱신이 완료됐습니다.
    </div>

    <!-- 직접 추가 폼 -->
    <div v-if="showAdd" class="add-form card">
      <div class="add-form-title">🧠 메모리 직접 추가</div>
      <div class="form-row">
        <div class="form-group">
          <label class="form-label">카테고리</label>
          <select v-model="newItem.category" class="form-input">
            <option v-for="c in categories" :key="c.value" :value="c.value">{{ c.label }}</option>
          </select>
        </div>
        <div class="form-group" style="flex:1">
          <label class="form-label">제목</label>
          <input v-model="newItem.title" class="form-input" placeholder="메모리 제목" />
        </div>
      </div>
      <div class="form-group">
        <label class="form-label">내용</label>
        <textarea v-model="newItem.content" class="form-input form-textarea" placeholder="기억할 내용을 입력하세요..." style="min-height:90px" />
      </div>
      <div style="display:flex;gap:8px">
        <button class="btn btn-primary btn-sm" :disabled="loading" @click="addItem">저장</button>
        <button class="btn btn-ghost btn-sm" @click="showAdd=false">취소</button>
      </div>
    </div>

    <!-- 빈 상태 -->
    <div v-if="!memory.length && !refreshing" class="empty-state">
      <div class="empty-hyean">🧠</div>
      <p class="empty-title">아직 기억된 내용이 없어요</p>
      <p class="empty-sub">
        루프가 시작되면 혜안이 회의 활동을 분석해<br>자동으로 메모리를 채웁니다.
      </p>
      <button class="btn-hyean-refresh" style="margin-top:20px" :disabled="refreshing" @click="refreshMemory">
        🔄 지금 바로 분석하기
      </button>
    </div>

    <!-- 메모리 카드 그룹 -->
    <div v-for="(group, catKey) in grouped" :key="catKey" class="cat-section">
      <div class="cat-header" :style="{ background: group.color, borderColor: group.border, color: group.text }">
        {{ group.label }}
        <span class="cat-count">{{ group.items.length }}개</span>
      </div>
      <div class="memory-list">
        <div v-for="item in group.items" :key="item.id" class="memory-card"
          :style="{ borderLeftColor: group.border }">
          <div v-if="editingId !== item.id">
            <div class="memory-card-header">
              <div>
                <div class="memory-title">{{ item.title }}</div>
                <div class="memory-meta">
                  <span class="ver-badge">v{{ item.version }}</span>
                  <span v-if="item.loop_number" class="loop-badge-sm">{{ item.loop_number }}차 루프</span>
                  {{ formatDate(item.updated_at) }}
                </div>
              </div>
              <div class="card-actions">
                <button class="act-btn edit" @click="startEdit(item)" title="편집">✏️</button>
                <button class="act-btn del" @click="deleteItem(item)" title="삭제">🗑</button>
              </div>
            </div>
            <div class="memory-content">{{ item.content }}</div>
          </div>
          <div v-else class="edit-form-inline">
            <input v-model="editTitle" class="form-input" style="font-weight:600;margin-bottom:8px" />
            <textarea v-model="editContent" class="form-input form-textarea" style="min-height:90px" />
            <div style="display:flex;gap:8px;margin-top:8px">
              <button class="btn btn-primary btn-sm" :disabled="loading" @click="saveEdit(item)">저장</button>
              <button class="btn btn-ghost btn-sm" @click="editingId=null">취소</button>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.memory-page { max-width: 860px; margin: 0 auto; }

/* ── 혜안 헤더 배너 ── */
.hyean-banner {
  display: flex;
  align-items: center;
  gap: 16px;
  background: linear-gradient(135deg, #f5f3ff 0%, #ede9fe 100%);
  border: 1px solid #ddd6fe;
  border-radius: 14px;
  padding: 18px 20px;
  margin-bottom: 20px;
}
.hyean-avatar {
  position: relative;
  width: 52px;
  height: 52px;
  flex-shrink: 0;
}
.hyean-avatar img {
  width: 52px;
  height: 52px;
  border-radius: 50%;
  object-fit: cover;
  border: 2px solid #a78bfa;
}
.hyean-emoji {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 28px;
  background: #7c3aed;
  border-radius: 50%;
  color: #fff;
}
.hyean-info { flex: 1; min-width: 0; }
.hyean-name { font-size: 15px; font-weight: 700; color: #4c1d95; margin-bottom: 4px; display: flex; align-items: center; gap: 8px; }
.hyean-badge {
  font-size: 11px; font-weight: 500; background: #7c3aed; color: #fff;
  padding: 2px 8px; border-radius: 99px;
}
.hyean-desc { font-size: 13px; color: #6b21a8; line-height: 1.5; }
.hyean-actions { display: flex; gap: 8px; flex-shrink: 0; }

.btn-hyean-refresh {
  display: flex; align-items: center; gap: 6px;
  background: #7c3aed; color: #fff;
  border: none; border-radius: 8px;
  padding: 8px 14px; font-size: 13px; font-weight: 600;
  cursor: pointer; transition: background .15s;
}
.btn-hyean-refresh:hover:not(:disabled) { background: #6d28d9; }
.btn-hyean-refresh:disabled { opacity: .6; cursor: not-allowed; }

.btn-hyean-add {
  display: flex; align-items: center; gap: 4px;
  background: transparent; color: #7c3aed;
  border: 1.5px solid #a78bfa; border-radius: 8px;
  padding: 7px 13px; font-size: 13px; font-weight: 500;
  cursor: pointer; transition: background .15s;
}
.btn-hyean-add:hover { background: #f5f3ff; }

/* ── 상태 바 ── */
.thinking-bar {
  display: flex; align-items: center; gap: 6px;
  background: #f5f3ff; border: 1px solid #ddd6fe; border-radius: 8px;
  padding: 10px 16px; font-size: 13px; color: #6d28d9; margin-bottom: 16px;
}
.done-bar {
  background: #f0fdf4; border: 1px solid #bbf7d0; border-radius: 8px;
  padding: 10px 16px; font-size: 13px; color: #15803d; margin-bottom: 16px;
}
.dot-anim {
  font-size: 8px; color: #7c3aed;
  animation: blink 1s infinite;
}
@keyframes blink { 0%,80%,100%{opacity:.2} 40%{opacity:1} }
.spin { display: inline-block; animation: spin 1s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }

/* ── 추가 폼 ── */
.add-form { padding: 20px; margin-bottom: 20px; }
.add-form-title { font-weight: 700; font-size: 14px; color: #4c1d95; margin-bottom: 14px; }
.form-row { display: flex; gap: 12px; margin-bottom: 10px; }
.form-group { margin-bottom: 10px; }

/* ── 빈 상태 ── */
.empty-state { text-align: center; padding: 64px 20px; }
.empty-hyean { font-size: 56px; margin-bottom: 14px; }
.empty-title { font-size: 15px; font-weight: 600; color: #374151; margin-bottom: 6px; }
.empty-sub { font-size: 13px; color: #6b7280; line-height: 1.7; }

/* ── 카테고리 섹션 ── */
.cat-section { margin-bottom: 24px; }
.cat-header {
  display: flex; align-items: center; justify-content: space-between;
  font-size: 13px; font-weight: 700;
  padding: 6px 14px; border-radius: 8px; border: 1px solid;
  margin-bottom: 10px;
}
.cat-count { font-size: 11px; font-weight: 500; opacity: .7; }
.memory-list { display: flex; flex-direction: column; gap: 10px; }

/* ── 메모리 카드 ── */
.memory-card {
  background: #fff;
  border: 1px solid var(--border, #e2e8f0);
  border-left: 4px solid;
  border-radius: 10px;
  padding: 16px;
  transition: box-shadow .15s;
}
.memory-card:hover { box-shadow: 0 2px 8px rgba(0,0,0,.07); }
.memory-card-header { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 10px; }
.memory-title { font-weight: 600; font-size: 14px; color: #111827; }
.memory-meta { display: flex; align-items: center; gap: 6px; margin-top: 4px; font-size: 11px; color: #9ca3af; }
.ver-badge { background: #f3f4f6; padding: 1px 6px; border-radius: 4px; font-weight: 500; }
.loop-badge-sm { background: #ede9fe; color: #6d28d9; padding: 1px 6px; border-radius: 4px; font-weight: 500; }
.memory-content { font-size: 13px; white-space: pre-wrap; line-height: 1.75; color: #374151; }

.card-actions { display: flex; gap: 4px; }
.act-btn {
  background: transparent; border: none; cursor: pointer;
  font-size: 14px; padding: 4px 6px; border-radius: 6px; opacity: .5;
  transition: opacity .15s, background .15s;
}
.act-btn:hover { opacity: 1; background: #f3f4f6; }
.act-btn.del:hover { background: #fee2e2; }

.edit-form-inline { display: flex; flex-direction: column; gap: 0; }
</style>
