<script setup>
import { ref, onMounted, computed } from 'vue'
import { useRoute } from 'vue-router'
import api from '../api'

const route = useRoute()
const meetingId = computed(() => Number(route.params.meetingId))

const meeting   = ref(null)
const doc       = ref({ content: '', version: 0, updated_at: null, updated_by: 'system' })
const editing   = ref(false)
const editBuf   = ref('')
const saving    = ref(false)
const loading   = ref(true)

onMounted(async () => {
  await Promise.all([loadDoc(), loadMeeting()])
  loading.value = false
})

async function loadDoc() {
  try {
    const { data } = await api.get(`/api/tacit-knowledge/activity/${meetingId.value}`)
    doc.value = data
  } catch { /* silent */ }
}

async function loadMeeting() {
  try {
    const { data } = await api.get('/api/meetings')
    meeting.value = data.find(m => m.id === meetingId.value) || null
  } catch { /* silent */ }
}

function startEdit() {
  editBuf.value = doc.value.content
  editing.value = true
}

function cancelEdit() {
  editing.value = false
  editBuf.value = ''
}

async function saveEdit() {
  saving.value = true
  try {
    await api.patch(`/api/tacit-knowledge/activity/${meetingId.value}`, { content: editBuf.value })
    doc.value.content = editBuf.value
    doc.value.version += 1
    doc.value.updated_by = 'manual'
    doc.value.updated_at = new Date().toISOString()
    editing.value = false
  } finally {
    saving.value = false
  }
}

function exportMarkdown() {
  const title = meeting.value?.title || '회의체'
  const filename = `${title}_활동기록.md`
  const header = `# ${title} — 활동 기록\n> v${doc.value.version} · 마지막 수정: ${formatDate(doc.value.updated_at)}\n\n`
  const blob = new Blob([header + (doc.value.content || '')], { type: 'text/markdown;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url; a.download = filename; a.click()
  URL.revokeObjectURL(url)
}

function formatDate(d) {
  if (!d) return '—'
  return new Date(d).toLocaleString('ko-KR', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
}

const isEmpty = computed(() => !doc.value.content?.trim())
</script>

<template>
  <div class="am-page">

    <!-- 헤더 -->
    <div class="am-header">
      <div class="am-header-left">
        <div class="am-avatar">🧠</div>
        <div>
          <div class="am-title">활동 기록 <span class="am-badge">자동 관리</span></div>
          <div class="am-sub">{{ meeting?.title || '이 회의체' }}의 에이전트 활동이 자동으로 기록됩니다.</div>
        </div>
      </div>
      <div class="am-header-actions">
        <button class="btn-edit" @click="startEdit" :disabled="editing">✏️ 수정</button>
        <button class="btn-export" @click="exportMarkdown">⬇ 내보내기</button>
      </div>
    </div>

    <!-- 메타 바 -->
    <div class="am-meta" v-if="doc.version > 0">
      <span class="ver-chip">v{{ doc.version }}</span>
      <span class="meta-by">{{ doc.updated_by === 'manual' ? '수동 편집' : '자동 기록' }}</span>
      <span class="meta-dot">·</span>
      <span class="meta-date">{{ formatDate(doc.updated_at) }}</span>
    </div>

    <!-- 로딩 -->
    <div v-if="loading" class="am-loading">기록을 불러오는 중...</div>

    <!-- 빈 상태 -->
    <div v-else-if="isEmpty && !editing" class="am-empty">
      <div class="am-empty-icon">📋</div>
      <div class="am-empty-title">아직 기록된 활동이 없습니다</div>
      <div class="am-empty-sub">에이전트(가온·나루·아라·나온)를 사용하면<br>활동이 여기에 자동으로 기록됩니다.</div>
    </div>

    <!-- 편집 모드 -->
    <div v-else-if="editing" class="am-editor-wrap">
      <textarea v-model="editBuf" class="am-editor" placeholder="활동 기록을 마크다운으로 작성하세요..." />
      <div class="am-editor-actions">
        <button class="btn btn-primary btn-sm" :disabled="saving" @click="saveEdit">
          {{ saving ? '저장 중...' : '저장' }}
        </button>
        <button class="btn btn-ghost btn-sm" @click="cancelEdit">취소</button>
      </div>
    </div>

    <!-- 문서 뷰 -->
    <div v-else class="am-doc">
      <pre class="am-pre">{{ doc.content }}</pre>
    </div>

  </div>
</template>

<style scoped>
.am-page { max-width: 860px; margin: 0 auto; display: flex; flex-direction: column; gap: 16px; }

/* ── 헤더 ── */
.am-header {
  display: flex; align-items: center; justify-content: space-between; gap: 12px;
  background: linear-gradient(135deg, #f5f3ff 0%, #ede9fe 100%);
  border: 1px solid #ddd6fe; border-radius: 14px; padding: 18px 20px;
}
.am-header-left { display: flex; align-items: center; gap: 14px; }
.am-avatar {
  width: 48px; height: 48px; border-radius: 50%; background: #7c3aed;
  display: flex; align-items: center; justify-content: center; font-size: 26px; flex-shrink: 0;
}
.am-title { font-size: 15px; font-weight: 700; color: #4c1d95; display: flex; align-items: center; gap: 8px; margin-bottom: 3px; }
.am-badge { font-size: 11px; font-weight: 500; background: #7c3aed; color: #fff; padding: 2px 8px; border-radius: 99px; }
.am-sub { font-size: 13px; color: #6b21a8; }
.am-header-actions { display: flex; gap: 8px; flex-shrink: 0; }

.btn-edit {
  background: transparent; color: #7c3aed; border: 1.5px solid #a78bfa;
  border-radius: 8px; padding: 7px 14px; font-size: 13px; font-weight: 500;
  cursor: pointer; transition: background .15s;
}
.btn-edit:hover:not(:disabled) { background: #f5f3ff; }
.btn-edit:disabled { opacity: .5; cursor: not-allowed; }

.btn-export {
  background: #7c3aed; color: #fff; border: none;
  border-radius: 8px; padding: 8px 14px; font-size: 13px; font-weight: 600;
  cursor: pointer; transition: background .15s;
}
.btn-export:hover { background: #6d28d9; }

/* ── 메타 ── */
.am-meta {
  display: flex; align-items: center; gap: 6px;
  font-size: 12px; color: var(--text-muted); padding: 0 4px;
}
.ver-chip {
  background: #ede9fe; color: #6d28d9; border-radius: 4px;
  padding: 1px 6px; font-size: 11px; font-weight: 600;
}
.meta-by { color: #7c3aed; font-weight: 500; }
.meta-dot { color: #cbd5e1; }

/* ── 로딩 / 빈 상태 ── */
.am-loading { text-align: center; color: var(--text-muted); padding: 48px; font-size: 14px; }
.am-empty {
  text-align: center; padding: 56px 20px;
  background: #fafafa; border: 1px dashed var(--border); border-radius: 12px;
}
.am-empty-icon { font-size: 40px; margin-bottom: 12px; }
.am-empty-title { font-size: 15px; font-weight: 600; color: var(--text); margin-bottom: 8px; }
.am-empty-sub { font-size: 13px; color: var(--text-muted); line-height: 1.7; }

/* ── 편집기 ── */
.am-editor-wrap { display: flex; flex-direction: column; gap: 10px; }
.am-editor {
  width: 100%; min-height: 480px; border: 1.5px solid #a78bfa; border-radius: 10px;
  padding: 16px; font-size: 13px; font-family: 'Pretendard', monospace; line-height: 1.7;
  resize: vertical; outline: none; box-sizing: border-box; color: var(--text);
}
.am-editor:focus { border-color: #7c3aed; box-shadow: 0 0 0 3px #ede9fe; }
.am-editor-actions { display: flex; gap: 8px; }

/* ── 문서 뷰 ── */
.am-doc {
  background: #fff; border: 1px solid var(--border); border-radius: 12px; padding: 24px;
}
.am-pre {
  white-space: pre-wrap; word-break: break-word;
  font-size: 13px; font-family: 'Pretendard', sans-serif; line-height: 1.8;
  color: var(--text); margin: 0;
}
</style>

