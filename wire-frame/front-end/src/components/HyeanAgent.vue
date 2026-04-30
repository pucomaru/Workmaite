<script setup>
import { ref, onMounted, onUnmounted, computed } from 'vue'
import { streamPost } from '../api'
import { useAuthStore } from '../stores/auth'
import { useMeetingsStore } from '../stores/meetings'
import { useRoute } from 'vue-router'
import api from '../api'
import hyeanAvatar from '../assets/agents/hyean.png'
import { marked } from 'marked'
const renderMd = (text) => marked.parse(text || '', { breaks: true })

const props = defineProps({ meetingId: { type: Number, default: 0 } })
const route = useRoute()
const auth = useAuthStore()
const meetingsStore = useMeetingsStore()

// ── 패널 상태 ─────────────────────────────────────────────────
const open = ref(false)
const activeTab = ref('status')

// ── 채팅 ─────────────────────────────────────────────────────
const messages = ref([])
const input = ref('')
const loading = ref(false)
const knowledgeSummary = ref(null)
const messagesEl = ref(null)

// ── 메모리 ───────────────────────────────────────────────────
const memory = ref([])
const memLoading = ref(false)
const refreshing = ref(false)
const refreshDone = ref(false)
const editingId = ref(null)
const editTitle = ref('')
const editContent = ref('')
const showAdd = ref(false)
const newItem = ref({ category: 'meeting_standard', title: '', content: '' })
const savingMem = ref(false)

const categories = [
  { value: 'report_standard',  label: '📋 보고서 기준',  color: '#dbeafe', border: '#93c5fd', text: '#1d4ed8' },
  { value: 'agenda_standard',  label: '📌 아젠다 기준',  color: '#fef9c3', border: '#fde047', text: '#854d0e' },
  { value: 'todo_standard',    label: '✅ 과제 기준',    color: '#dcfce7', border: '#86efac', text: '#166534' },
  { value: 'meeting_standard', label: '🎙 회의 기준',    color: '#f3e8ff', border: '#d8b4fe', text: '#6b21a8' },
]

const currentMeetingId = computed(() => {
  if (props.meetingId) return props.meetingId
  return Number(route.params?.meetingId) || 0
})

const grouped = computed(() => {
  const map = {}
  for (const cat of categories) {
    const items = memory.value.filter(m => m.category === cat.value)
    if (items.length) map[cat.value] = { ...cat, items }
  }
  return map
})

async function loadMemory() {
  if (!currentMeetingId.value) return
  memLoading.value = true
  try {
    const { data } = await api.get(`/api/tacit-knowledge/meeting/${currentMeetingId.value}`)
    memory.value = data
  } finally { memLoading.value = false }
}

async function refreshMemory() {
  if (!currentMeetingId.value) return
  refreshing.value = true; refreshDone.value = false
  try {
    await api.post(`/api/tacit-knowledge/meeting/${currentMeetingId.value}/refresh`)
    setTimeout(async () => {
      await loadMemory()
      refreshing.value = false; refreshDone.value = true
      setTimeout(() => { refreshDone.value = false }, 4000)
    }, 4000)
  } catch { refreshing.value = false }
}

async function saveEdit(item) {
  savingMem.value = true
  try {
    await api.patch(`/api/tacit-knowledge/meeting-item/${item.id}`, { title: editTitle.value, content: editContent.value })
    await loadMemory(); editingId.value = null
  } finally { savingMem.value = false }
}

async function deleteItem(item) {
  if (!confirm(`"${item.title}" 메모리를 삭제하시겠습니까?`)) return
  await api.delete(`/api/tacit-knowledge/meeting-item/${item.id}`)
  await loadMemory()
}

async function addItem() {
  if (!newItem.value.title.trim() || !newItem.value.content.trim()) return
  savingMem.value = true
  try {
    await api.post(`/api/tacit-knowledge/meeting/${currentMeetingId.value}`, newItem.value)
    await loadMemory(); showAdd.value = false
    newItem.value = { category: 'meeting_standard', title: '', content: '' }
  } finally { savingMem.value = false }
}

function startEdit(item) { editingId.value = item.id; editTitle.value = item.title; editContent.value = item.content }
function formatDate(d) { if (!d) return ''; return new Date(d).toLocaleDateString('ko-KR', { month: 'short', day: 'numeric' }) }

function switchTab(tab) {
  activeTab.value = tab
  if (tab === 'memory' && !memory.value.length) loadMemory()
}
function toggleOpen() {
  open.value = !open.value
  if (open.value && activeTab.value === 'memory' && !memory.value.length) loadMemory()
}

onMounted(async () => {
  try {
    const { data } = await api.get(`/api/tacit-knowledge/summary?meeting_id=${currentMeetingId.value}`)
    knowledgeSummary.value = data
  } catch {}
})

// ── 채팅 ─────────────────────────────────────────────────────
async function sendMessage() {
  if (!input.value.trim() || loading.value) return
  const text = input.value.trim()
  messages.value.push({ role: 'user', content: text })
  input.value = ''
  const agentMsg = { role: 'agent', content: '' }
  messages.value.push(agentMsg)
  loading.value = true
  await streamPost(
    '/api/agent/hyean/chat',
    { meeting_id: currentMeetingId.value, message: text,
      chat_history: messages.value.slice(0,-1).map(m => ({ role: m.role==='user'?'user':'assistant', content: m.content })) },
    (chunk) => { agentMsg.content += chunk },
    () => { loading.value = false }
  )
}

async function askStatus() {
  const agentMsg = { role: 'agent', content: '' }
  messages.value.push(agentMsg); loading.value = true
  await streamPost('/api/agent/hyean/status',
    { meeting_id: currentMeetingId.value, user_role: meetingsStore.myRole || 'presenter' },
    (chunk) => { agentMsg.content += chunk },
    () => { loading.value = false }
  )
}

// ── 리사이즈 (왼쪽 위 모서리) ─────────────────────────────────
const panelW = ref(380)
const panelH = ref(520)
let resizing = false, rsX = 0, rsY = 0, rsW = 0, rsH = 0

function onResizeStart(e) {
  resizing = true; rsX = e.clientX; rsY = e.clientY; rsW = panelW.value; rsH = panelH.value
  e.preventDefault()
}
function onMouseMove(e) {
  if (!resizing) return
  panelW.value = Math.min(800, Math.max(300, rsW + (rsX - e.clientX)))
  panelH.value = Math.min(860, Math.max(380, rsH + (rsY - e.clientY)))
}
function onMouseUp() { resizing = false }

onMounted(() => { window.addEventListener('mousemove', onMouseMove); window.addEventListener('mouseup', onMouseUp) })
onUnmounted(() => { window.removeEventListener('mousemove', onMouseMove); window.removeEventListener('mouseup', onMouseUp) })
</script>

<template>
  <div class="hyean-wrap">
    <button class="hyean-fab" @click="toggleOpen" :class="{ active: open }">
      <img v-if="!open" :src="hyeanAvatar" class="hyean-fab-avatar" alt="혜안" />
      <svg v-else width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M6 18L18 6M6 6l12 12"/></svg>
      <span class="hyean-label">혜안</span>
    </button>

    <div v-if="open" class="hyean-panel slide-up" :style="{ width: panelW + 'px', height: panelH + 'px' }">

      <!-- 리사이즈 핸들 (왼쪽 위 모서리) -->
      <div class="resize-handle" @mousedown="onResizeStart" title="드래그해서 크기 조정">
        <svg width="10" height="10" viewBox="0 0 10 10">
          <line x1="1" y1="9" x2="9" y2="1" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
          <line x1="1" y1="5" x2="5" y2="1" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
        </svg>
      </div>

      <!-- 패널 헤더 -->
      <div class="panel-header">
        <div style="display:flex;align-items:center;gap:10px">
          <img :src="hyeanAvatar" class="agent-header-avatar" alt="혜안" />
          <div>
            <div style="font-weight:700;font-size:14px;color:var(--primary)">혜안 (Hyean)</div>
            <div style="font-size:11px;color:var(--text-muted)">회의체 운영 어시스턴트</div>
          </div>
        </div>
        <div class="tabs" style="margin:0">
          <button class="tab-btn" :class="{ active: activeTab==='status' }" @click="switchTab('status')">현황 안내</button>
          <button class="tab-btn" :class="{ active: activeTab==='memory' }" @click="switchTab('memory')">운영 메모리</button>
        </div>
      </div>

      <!-- 패널 바디 -->
      <div class="panel-body">

        <!-- ① 현황 안내 탭 -->
        <div v-if="activeTab === 'status'" class="chat-container">
          <div ref="messagesEl" class="chat-messages">
            <div v-if="!messages.length" class="empty-state" style="padding:24px">
              <p>현재 회의체 현황을 분석해드립니다.</p>
              <button class="btn btn-primary btn-sm" @click="askStatus">현황 분석하기</button>
            </div>
            <div v-for="(msg, i) in messages" :key="i" class="chat-msg-row fade-in" :class="msg.role">
              <div v-if="msg.role==='agent'" class="chat-agent-label">
                <img :src="hyeanAvatar" class="chat-avatar-sm" alt="혜안" />혜안
              </div>
              <div v-if="msg.role === 'agent'" class="chat-bubble agent" v-html="renderMd(msg.content)"></div>
              <div v-else class="chat-bubble" :class="msg.role">{{ msg.content }}</div>
            </div>
          </div>
          <div class="chat-input-area">
            <textarea v-model="input" class="chat-input" placeholder="질문하세요..." rows="1"
              @keydown.enter.exact.prevent="sendMessage" />
            <button class="btn btn-primary btn-sm" :disabled="loading || !input.trim()" @click="sendMessage">전송</button>
          </div>
        </div>

        <!-- ② 운영 메모리 탭 -->
        <div v-else class="memory-tab">
          <div class="mem-toolbar">
            <div style="font-size:12px;color:var(--text-muted)">
              <span v-if="!currentMeetingId" style="color:var(--danger)">⚠ 회의체 페이지에서 사용 가능</span>
              <span v-else>{{ memory.length }}개 메모리</span>
            </div>
            <div style="display:flex;gap:6px">
              <button v-if="currentMeetingId" class="mem-add-btn" @click="showAdd = !showAdd">＋ 추가</button>
              <button v-if="currentMeetingId" class="mem-refresh-btn" :disabled="refreshing" @click="refreshMemory">
                <span v-if="refreshing" class="spin">⟳</span>
                <span v-else-if="refreshDone">✓</span>
                <span v-else>🔄</span>
                {{ refreshing ? '분석 중...' : refreshDone ? '완료' : 'AI 갱신' }}
              </button>
            </div>
          </div>

          <div v-if="refreshing" class="mem-status-bar refreshing">
            <span class="dot-anim">●</span><span class="dot-anim" style="animation-delay:.2s">●</span><span class="dot-anim" style="animation-delay:.4s">●</span>
            혜안이 회의 활동을 분석 중입니다...
          </div>
          <div v-else-if="refreshDone" class="mem-status-bar done">✓ 메모리 갱신 완료</div>

          <div v-if="showAdd && currentMeetingId" class="mem-add-form">
            <select v-model="newItem.category" class="form-input" style="font-size:12px;margin-bottom:6px">
              <option v-for="c in categories" :key="c.value" :value="c.value">{{ c.label }}</option>
            </select>
            <input v-model="newItem.title" class="form-input" placeholder="제목" style="font-size:12px;margin-bottom:6px" />
            <textarea v-model="newItem.content" class="form-input" placeholder="내용" rows="3"
              style="font-size:12px;resize:none;margin-bottom:6px" />
            <div style="display:flex;gap:6px">
              <button class="btn btn-primary btn-sm" :disabled="savingMem" @click="addItem">저장</button>
              <button class="btn btn-ghost btn-sm" @click="showAdd=false">취소</button>
            </div>
          </div>

          <div class="mem-scroll">
            <div v-if="!currentMeetingId" class="mem-empty">
              <div>🧠</div><p>회의체 페이지에서 메모리를 관리할 수 있습니다.</p>
            </div>
            <div v-else-if="memLoading" class="mem-empty">
              <div class="spin" style="font-size:24px">⟳</div><p>불러오는 중...</p>
            </div>
            <div v-else-if="!memory.length" class="mem-empty">
              <div>🧠</div>
              <p>아직 기억된 내용이 없습니다.<br>루프 시작 시 자동 분석됩니다.</p>
              <button class="mem-refresh-btn" style="margin-top:10px" @click="refreshMemory">지금 분석하기</button>
            </div>
            <div v-for="(group, catKey) in grouped" :key="catKey" class="mem-group">
              <div class="mem-cat-header" :style="{ background: group.color, borderColor: group.border, color: group.text }">
                {{ group.label }} <span class="mem-cat-count">{{ group.items.length }}</span>
              </div>
              <div v-for="item in group.items" :key="item.id" class="mem-card" :style="{ borderLeftColor: group.border }">
                <div v-if="editingId !== item.id">
                  <div class="mem-card-head">
                    <div class="mem-title">{{ item.title }}</div>
                    <div class="mem-card-acts">
                      <button class="act-btn" @click="startEdit(item)" title="편집">✏️</button>
                      <button class="act-btn del" @click="deleteItem(item)" title="삭제">🗑</button>
                    </div>
                  </div>
                  <div class="mem-content">{{ item.content }}</div>
                </div>
                <div v-else>
                  <input v-model="editTitle" class="form-input" style="font-size:12px;font-weight:600;margin-bottom:6px" />
                  <textarea v-model="editContent" class="form-input" rows="3" style="font-size:12px;resize:none;margin-bottom:6px" />
                  <div style="display:flex;gap:6px">
                    <button class="btn btn-primary btn-sm" :disabled="savingMem" @click="saveEdit(item)">저장</button>
                    <button class="btn btn-ghost btn-sm" @click="editingId=null">취소</button>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.hyean-wrap { position: fixed; bottom: 24px; right: 24px; z-index: 500; display: flex; flex-direction: column; align-items: flex-end; gap: 12px; }
.hyean-fab { display: flex; align-items: center; gap: 8px; padding: 10px 16px; background: var(--primary); color: #fff; border-radius: 99px; box-shadow: var(--shadow-lg); transition: all .2s; }
.hyean-fab:hover { background: var(--primary-light); transform: scale(1.04); }
.hyean-fab.active { background: var(--primary-dark); }
.hyean-fab-avatar { width: 28px; height: 28px; border-radius: 50%; object-fit: cover; border: 1.5px solid rgba(255,255,255,.4); }
.hyean-label { font-size: 14px; font-weight: 600; }

.hyean-panel {
  background: #fff; border-radius: var(--radius-lg); box-shadow: var(--shadow-lg);
  border: 1px solid var(--border); display: flex; flex-direction: column;
  overflow: hidden; position: relative; min-width: 300px; min-height: 380px;
}
.resize-handle {
  position: absolute; top: 0; left: 0; width: 20px; height: 20px;
  cursor: nw-resize; z-index: 10; display: flex; align-items: center; justify-content: center;
  color: #cbd5e1; border-radius: 0 0 6px 0; transition: color .15s, background .15s;
  user-select: none;
}
.resize-handle:hover { color: var(--primary); background: #f1f5f9; }

.panel-header { padding: 10px 16px 10px 24px; border-bottom: 1px solid var(--border); display: flex; align-items: center; justify-content: space-between; flex-shrink: 0; gap: 10px; flex-wrap: wrap; }
.agent-header-avatar { width: 32px; height: 32px; border-radius: 50%; object-fit: cover; }
.panel-body { flex: 1; overflow: hidden; display: flex; flex-direction: column; }

/* 채팅 탭 */
.chat-container { flex: 1; display: flex; flex-direction: column; overflow: hidden; }
.chat-messages { flex: 1; overflow-y: auto; padding: 12px; display: flex; flex-direction: column; gap: 10px; }
.chat-msg-row { display: flex; flex-direction: column; gap: 4px; }
.chat-msg-row.user { align-items: flex-end; }
.chat-agent-label { display: flex; align-items: center; gap: 6px; font-size: 11px; font-weight: 600; color: var(--text-muted); }
.chat-avatar-sm { width: 18px; height: 18px; border-radius: 50%; object-fit: cover; }
.chat-bubble { padding: 8px 12px; border-radius: 12px; font-size: 13px; line-height: 1.6; max-width: 90%; word-break: break-word; }
.chat-bubble.user { background: var(--primary); color: #fff; border-radius: 12px 12px 2px 12px; }
.chat-bubble.agent { background: #f8fafc; border: 1px solid var(--border); border-radius: 2px 12px 12px 12px; }
.chat-input-area { display: flex; gap: 8px; padding: 10px 12px; border-top: 1px solid var(--border); flex-shrink: 0; }
.chat-input { flex: 1; resize: none; border: 1px solid var(--border); border-radius: 8px; padding: 7px 10px; font-size: 13px; outline: none; font-family: inherit; }
.chat-input:focus { border-color: var(--primary); }

/* 운영 메모리 탭 */
.memory-tab { flex: 1; display: flex; flex-direction: column; overflow: hidden; }
.mem-toolbar { display: flex; align-items: center; justify-content: space-between; padding: 8px 12px; border-bottom: 1px solid var(--border); flex-shrink: 0; }
.mem-add-btn { background: none; border: 1.5px solid #a78bfa; color: #7c3aed; border-radius: 6px; padding: 4px 10px; font-size: 12px; font-weight: 500; cursor: pointer; transition: background .15s; }
.mem-add-btn:hover { background: #f5f3ff; }
.mem-refresh-btn { display: inline-flex; align-items: center; gap: 4px; background: #7c3aed; color: #fff; border: none; border-radius: 6px; padding: 4px 10px; font-size: 12px; font-weight: 500; cursor: pointer; transition: background .15s; }
.mem-refresh-btn:hover:not(:disabled) { background: #6d28d9; }
.mem-refresh-btn:disabled { opacity: .6; cursor: not-allowed; }
.mem-status-bar { padding: 6px 12px; font-size: 12px; display: flex; align-items: center; gap: 6px; flex-shrink: 0; }
.mem-status-bar.refreshing { background: #f5f3ff; color: #6d28d9; }
.mem-status-bar.done { background: #f0fdf4; color: #15803d; }
.mem-add-form { padding: 10px 12px; border-bottom: 1px solid var(--border); flex-shrink: 0; }
.mem-scroll { flex: 1; overflow-y: auto; padding: 10px 12px; display: flex; flex-direction: column; gap: 12px; }
.mem-empty { text-align: center; padding: 32px 16px; color: var(--text-muted); font-size: 13px; display: flex; flex-direction: column; align-items: center; gap: 8px; }
.mem-empty div { font-size: 28px; }
.mem-group { display: flex; flex-direction: column; gap: 8px; }
.mem-cat-header { display: flex; align-items: center; justify-content: space-between; font-size: 11px; font-weight: 700; padding: 4px 10px; border-radius: 6px; border: 1px solid; }
.mem-cat-count { font-size: 10px; opacity: .7; }
.mem-card { background: #fff; border: 1px solid var(--border); border-left: 3px solid; border-radius: 8px; padding: 10px 12px; }
.mem-card-head { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 6px; }
.mem-title { font-size: 13px; font-weight: 600; color: #111827; flex: 1; line-height: 1.4; }
.mem-content { font-size: 12px; color: #374151; line-height: 1.6; white-space: pre-wrap; margin-bottom: 6px; }
.mem-card-acts { display: flex; gap: 2px; flex-shrink: 0; }
.act-btn { background: none; border: none; cursor: pointer; font-size: 13px; padding: 2px 4px; border-radius: 4px; opacity: .5; transition: opacity .15s; }
.act-btn:hover { opacity: 1; }
.act-btn.del:hover { background: #fee2e2; }

/* 공통 */
.dot-anim { font-size: 8px; color: #7c3aed; animation: blink 1s infinite; }
@keyframes blink { 0%,80%,100%{opacity:.2} 40%{opacity:1} }
.spin { display: inline-block; animation: spin 1s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }
.fade-in { animation: fadeIn .2s ease; }
@keyframes fadeIn { from { opacity:0; transform:translateY(4px); } to { opacity:1; } }
</style>
