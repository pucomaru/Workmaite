<script setup>
import { ref, onMounted, onUnmounted, computed, watch } from 'vue'
import { streamPost, apiAI } from '../api'
import { useMeetingsStore } from '../stores/meetings'
import { useRoute } from 'vue-router'
import hyeanAvatar from '../assets/agents/hyean.png'
import { useChatHistory } from '../composables/useChatHistory'
import { renderMd } from '../composables/useMarkdown'

const props = defineProps({ meetingId: { type: Number, default: 0 } })
const route = useRoute()
const meetingsStore = useMeetingsStore()

// ── 패널 상태 ─────────────────────────────────────────────────
const open = ref(false)

// ── 채팅 ─────────────────────────────────────────────────────
const { messages, saveMessage } = useChatHistory('hyean', null)
const input = ref('')
const loading = ref(false)
const messagesEl = ref(null)

const currentMeetingId = computed(() => {
  if (props.meetingId) return props.meetingId
  return Number(route.params?.meetingId) || 0
})

async function reloadHistory(meetingId) {
  if (!meetingId) return
  messages.value = []
  try {
    const res = await apiAI.get(`/api/chats/hyean/${meetingId}`)
    messages.value = res.data.map(m => ({ role: m.role, content: m.content }))
  } catch { /* silent */ }
}

// ── 채팅 ─────────────────────────────────────────────────────
async function _stream(text) {
  messages.value.push({ role: 'user', content: text })
  saveMessage('user', text)
  const agentMsg = { role: 'agent', content: '' }
  messages.value.push(agentMsg)
  loading.value = true
  await streamPost(
    '/api/agent/hyean/chat',
    { meeting_id: currentMeetingId.value, message: text,
      chat_history: messages.value.slice(0, -2).map(m => ({ role: m.role === 'user' ? 'user' : 'assistant', content: m.content })) },
    (chunk) => {
      agentMsg.content += chunk
      setTimeout(() => { if (messagesEl.value) messagesEl.value.scrollTop = messagesEl.value.scrollHeight }, 30)
    },
    () => {
      loading.value = false
      saveMessage('agent', agentMsg.content)
    }
  )
}

async function sendMessage() {
  const hasFiles = pendingFiles.value.length > 0
  if (!input.value.trim() && !hasFiles || loading.value) return
  const text = input.value.trim()
  input.value = ''
  if (textareaEl.value) { textareaEl.value.style.height = 'auto' }
  let fullText = text
  if (hasFiles) {
    const names = pendingFiles.value.map(f => f.name).join(', ')
    fullText = text ? `📎 ${names}\n${text}` : `📎 ${names}`
    pendingFiles.value = []
  }
  await _stream(fullText)
}

const SUGGESTED = [
  '이 회의체 운영 현황을 전반적으로 분석해줘',
  '회의체 참여율과 이행률 현황은 어때?',
  '최근 의사결정 패턴에서 개선할 점이 있어?',
  '회의 운영 효율을 높이려면 어떻게 해야 할까?',
]

function toggleOpen() {
  open.value = !open.value
}

function clearChat() {
  messages.value = []
  input.value = ''
  pendingFiles.value = []
  briefingDone.value = false
}

// ── 파일 첨부 ─────────────────────────────────────────────────
const pendingFiles = ref([]) // File[]
const fileInputEl = ref(null)
const isDragging = ref(false)
const textareaEl = ref(null)

function autoResize() {
  const el = textareaEl.value
  if (!el) return
  el.style.height = '36px'
  el.style.height = Math.min(el.scrollHeight, 140) + 'px'
}

function onFileSelected(e) {
  const files = Array.from(e.target.files || [])
  e.target.value = ''
  if (files.length) pendingFiles.value.push(...files)
}
function onDragOver(e) {
  e.preventDefault()
  isDragging.value = true
}
function onDragLeave(e) {
  if (!e.currentTarget.contains(e.relatedTarget)) isDragging.value = false
}
function onDrop(e) {
  e.preventDefault()
  isDragging.value = false
  const files = Array.from(e.dataTransfer?.files || [])
  if (files.length) pendingFiles.value.push(...files)
}
function removeFile(i) { pendingFiles.value.splice(i, 1) }

// ── 자동 브리핑 ──────────────────────────────────────────────
const briefingDone = ref(false)

async function loadBriefing(force = false) {
  if (loading.value) return
  if (briefingDone.value && !force) return
  briefingDone.value = false
  loading.value = true
  const agentMsg = { role: 'agent', content: '' }
  messages.value.push(agentMsg)
  try {
    await streamPost(
      '/api/agent/hyean/status',
      { meeting_id: currentMeetingId.value, user_role: meetingsStore.myRole || 'member' },
      (chunk) => {
        agentMsg.content += chunk
        setTimeout(() => { if (messagesEl.value) messagesEl.value.scrollTop = messagesEl.value.scrollHeight }, 30)
      },
      () => { loading.value = false; saveMessage('agent', agentMsg.content) },
    )
    briefingDone.value = true
  } catch {
    agentMsg.content = '현황 브리핑을 불러오는 중 오류가 발생했습니다.'
    loading.value = false
  }
}

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

onMounted(async () => {
  window.addEventListener('mousemove', onMouseMove)
  window.addEventListener('mouseup', onMouseUp)
  await reloadHistory(currentMeetingId.value)
})

watch(currentMeetingId, (id) => {
  reloadHistory(id)
})
onUnmounted(() => { window.removeEventListener('mousemove', onMouseMove); window.removeEventListener('mouseup', onMouseUp) })
</script>

<template>
  <div class="hyean-wrap">
    <button v-if="!open" class="hyean-fab" @click="toggleOpen" title="혜안">
      <img :src="hyeanAvatar" class="hyean-fab-avatar" alt="혜안" />
    </button>

    <div v-if="open" class="hyean-panel slide-up" :style="{ width: panelW + 'px', height: panelH + 'px' }"
      @dragover.prevent="onDragOver"
      @dragleave="onDragLeave"
      @drop.prevent="onDrop"
    >

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
            <div style="font-size:11px;color:var(--text-muted)">회의체 운영 AI 비서</div>
          </div>
        </div>
        <div style="display:flex;align-items:center;gap:6px">
          <button class="hy-new-chat-btn" @click="clearChat" title="새 채팅">새 채팅</button>
          <button class="btn btn-ghost btn-xs" @click="toggleOpen" title="닫기" style="color:var(--text-muted)">✕</button>
        </div>
      </div>

      <!-- 패널 바디 -->
      <div class="panel-body">

        <!-- 채팅 컨테이너 -->
        <div class="chat-container">
          <!-- 추천 요청 버튼 (항상 상단 고정) -->
          <div ref="messagesEl" class="chat-messages">
            <!-- 빈 대화일 때 인사 멘트 -->
            <template v-if="messages.length === 0">
              <div class="chat-msg-row fade-in agent">
                <div class="chat-agent-label"><img :src="hyeanAvatar" class="chat-avatar-sm" alt="혜안" />혜안</div>
                <div class="chat-bubble agent">
                  안녕하세요! 회의체 운영 AI 비서 <strong>혜안</strong>입니다.<br>현황 브리핑이 필요하시면 아래 버튼을 눌러주세요.
                  <div class="hy-inline-quick">
                    <button v-for="s in SUGGESTED" :key="s" class="hy-inline-btn" :disabled="loading" @click="_stream(s)">{{ s }}</button>
                  </div>
                </div>
              </div>
            </template>
            <div v-for="(msg, i) in messages" :key="i" class="chat-msg-row fade-in" :class="msg.role">
              <template v-if="msg.role === 'agent' && msg.content">
                <div class="chat-agent-label">
                  <img :src="hyeanAvatar" class="chat-avatar-sm" alt="혜안" />혜안
                </div>
                <div class="chat-bubble agent" v-html="renderMd(msg.content)"></div>
              </template>
              <div v-else-if="msg.role !== 'agent'" class="chat-bubble" :class="msg.role">{{ msg.content }}</div>
            </div>
          </div>
          <div class="chat-input-area">
            <div v-if="pendingFiles.length" class="chat-file-chips">
              <span v-for="(f, i) in pendingFiles" :key="i" class="chat-file-chip">
                <span>📎 {{ f.name }}</span>
                <button class="chip-remove" @click="removeFile(i)">×</button>
              </span>
            </div>
            <div class="chat-input-row">
              <button class="chat-attach-btn" :disabled="loading" title="파일 첨부" @click="fileInputEl.click()">＋</button>
              <textarea ref="textareaEl" v-model="input" class="chat-input" :placeholder="pendingFiles.length ? '파일에 대한 메시지... (선택)' : '질문하세요...'" rows="1"
                @input="autoResize"
                @keydown.enter.exact.prevent="sendMessage" />
              <button class="btn btn-primary btn-sm" :disabled="loading || (!input.trim() && !pendingFiles.length)" @click="sendMessage">전송</button>
            </div>
            <input ref="fileInputEl" type="file" multiple style="display:none" @change="onFileSelected" />
          </div>
        </div>
      </div>
      <!-- 드래그 오버레이 -->
      <div v-if="isDragging" class="hy-drag-overlay">
        <div class="hy-drag-hint">📎 파일을 여기에 놓으세요</div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.hyean-wrap { position: fixed; bottom: 24px; right: 24px; z-index: 500; display: flex; flex-direction: column; align-items: flex-end; gap: 12px; }
.hyean-fab { display: flex; align-items: center; justify-content: center; width: 52px; height: 52px; padding: 0; background: var(--primary); color: #fff; border-radius: 50%; box-shadow: var(--shadow-lg); transition: all .2s; border: none; cursor: pointer; }
.hyean-fab:hover { background: var(--primary-light); transform: scale(1.04); }
.hyean-fab-avatar { width: 44px; height: 44px; border-radius: 50%; object-fit: cover; }

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

.hy-new-chat-btn { background: none; border: 1px solid var(--border); border-radius: 6px; padding: 3px 10px; font-size: 12px; font-weight: 500; color: var(--text-muted); cursor: pointer; transition: background .15s, color .15s, border-color .15s; }
.hy-new-chat-btn:hover { background: #eff6ff; border-color: #93c5fd; color: var(--primary); }
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
.chat-input-area { display: flex; flex-direction: column; gap: 6px; padding: 10px 12px; border-top: 1px solid var(--border); flex-shrink: 0; width: 100%; box-sizing: border-box; }
.chat-file-chips { display: flex; flex-wrap: wrap; gap: 5px; }
.chat-file-chip { display: inline-flex; align-items: center; gap: 4px; background: #eff6ff; border: 1px solid #93c5fd; border-radius: 6px; padding: 2px 8px; font-size: 11px; color: #1e40af; max-width: 200px; }
.chip-remove { background: none; border: none; cursor: pointer; font-size: 13px; color: #6b7280; padding: 0 2px; line-height: 1; }
.chip-remove:hover { color: #ef4444; }
.chat-input-row { display: flex; align-items: flex-end; gap: 6px; width: 100%; }
.chat-attach-btn { flex-shrink: 0; width: 28px; height: 28px; border-radius: 50%; border: 1px solid var(--border); background: #f8fafc; color: var(--text-muted); font-size: 18px; line-height: 1; cursor: pointer; display: flex; align-items: center; justify-content: center; transition: background .15s, color .15s; margin-bottom: 1px; }
.chat-attach-btn:hover:not(:disabled) { background: #eff6ff; border-color: #93c5fd; color: var(--primary); }
.chat-attach-btn:disabled { opacity: .4; cursor: not-allowed; }
.chat-input { flex: 1; resize: none; overflow: hidden; min-height: 36px; border: 1px solid var(--border); border-radius: 8px; padding: 7px 10px; font-size: 13px; outline: none; font-family: inherit; line-height: 1.5; box-sizing: border-box; }
.chat-input:focus { border-color: var(--primary); }
.hy-drag-overlay { position: absolute; inset: 0; z-index: 20; background: rgba(99,102,241,.07); border: 2px dashed var(--primary); border-radius: var(--radius-lg); display: flex; align-items: center; justify-content: center; pointer-events: none; }
.hy-drag-hint { background: white; border: 1px solid var(--primary); border-radius: 10px; padding: 12px 24px; font-size: 14px; font-weight: 600; color: var(--primary); box-shadow: 0 2px 8px rgba(0,0,0,.08); }
.hy-inline-quick { display: flex; flex-direction: column; gap: 5px; margin-top: 8px; }
.hy-inline-btn { text-align: left; background: rgba(255,255,255,.55); border: 1px solid #c7d2fe; border-radius: 7px; padding: 6px 10px; font-size: 12px; color: var(--primary); cursor: pointer; transition: background .15s; line-height: 1.4; font-weight: 500; }
.hy-inline-btn:hover:not(:disabled) { background: rgba(255,255,255,.9); }
.hy-inline-btn:disabled { opacity: .4; cursor: not-allowed; }

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
