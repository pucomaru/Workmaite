<script setup>
import { ref } from 'vue'
import { renderMd } from '../composables/useMarkdown'

const props = defineProps({
  avatar:        { type: String, required: true },
  name:          { type: String, required: true },
  nameEn:        { type: String, default: '' },
  subtitle:      { type: String, default: '' },
  messages:      { type: Array,  default: () => [] },
  loading:       { type: Boolean, default: false },
  quickQuestions:{ type: Array,  default: () => [] },
  greeting:      { type: String, default: '' },
  placeholder:   { type: String, default: '질문하세요...' },
  initialWidth:  { type: Number, default: 380 },
  pendingFiles:  { type: Array,  default: () => [] }, // [{ name: string }]
  // 에이전트별 색상 테마
  accentColor:   { type: String, default: '#f59e0b' },  // label color
  accentBorder:  { type: String, default: '#fbbf24' },  // border / ring
  accentBg:      { type: String, default: '#fef3c7' },  // light bg
  bubbleGradient:{ type: String, default: 'linear-gradient(135deg,#fef3c7,#fed7aa)' },
  bubbleColor:   { type: String, default: '#92400e' },
})

const emit = defineEmits(['send', 'clear', 'remove-file', 'add-files'])

const input = ref('')
const messagesEl = ref(null)
const fileInput = ref(null)
const isDragging = ref(false)

function onFileSelected(e) {
  const files = Array.from(e.target.files || [])
  e.target.value = ''
  if (files.length) emit('add-files', files)
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
  if (files.length) emit('add-files', files)
}

// ── 리사이즈 ──────────────────────────────────
const panelWidth = ref(props.initialWidth)
let resizing = false, startX = 0, startW = 0

function onResizeStart(e) {
  resizing = true; startX = e.clientX; startW = panelWidth.value
  document.addEventListener('mousemove', onResizeMove)
  document.addEventListener('mouseup', onResizeEnd)
}
function onResizeMove(e) {
  if (!resizing) return
  panelWidth.value = Math.min(700, Math.max(240, startW + (e.clientX - startX)))
}
function onResizeEnd() {
  resizing = false
  document.removeEventListener('mousemove', onResizeMove)
  document.removeEventListener('mouseup', onResizeEnd)
}

function send() {
  if ((!input.value.trim() && !props.pendingFiles.length) || props.loading) return
  emit('send', input.value.trim())
  input.value = ''
}
function sendQuick(q) { emit('send', q) }

function scrollBottom() {
  if (messagesEl.value)
    messagesEl.value.scrollTop = messagesEl.value.scrollHeight
}

defineExpose({ scrollBottom })
</script>

<template>
  <div
    class="agent-panel card"
    :style="{
      width: panelWidth + 'px',
      '--ap-accent':        accentColor,
      '--ap-accent-border': accentBorder,
      '--ap-accent-bg':     accentBg,
      '--ap-bubble-grad':   bubbleGradient,
      '--ap-bubble-color':  bubbleColor,
    }"
    @dragover.prevent="onDragOver"
    @dragleave="onDragLeave"
    @drop.prevent="onDrop"
  >
    <!-- ── 헤더 ── -->
    <div class="ap-header">
      <div class="ap-title">
        <img :src="avatar" class="ap-avatar" :alt="name" />
        <div>
          <div class="ap-name">
            {{ name }}
            <span v-if="nameEn" class="ap-name-en"> ({{ nameEn }})</span>
          </div>
          <div class="ap-subtitle">{{ subtitle }}</div>
        </div>
      </div>
      <div class="ap-actions">
        <slot name="actions" />
        <button class="ap-new-chat-btn" @click="$emit('clear')" title="새 채팅">새 채팅</button>
      </div>
    </div>

    <!-- ── extra-header 슬롯 (세션 선택기 등) ── -->
    <slot name="extra-header" />

    <!-- ── overlay 슬롯 + 내장 드래그 오버레이 ── -->
    <slot name="overlay" />
    <div v-if="isDragging" class="ap-drag-overlay">
      <div class="ap-drag-hint">📎 파일을 여기에 놓으세요</div>
    </div>

    <!-- ── 메시지 영역 ── -->
    <div class="ap-messages" ref="messagesEl">
      <div
        v-for="(msg, i) in messages"
        :key="i"
        class="ap-msg-row fade-in"
        :class="msg.role"
      >
        <template v-if="msg.role === 'agent' && msg.content">
          <div class="ap-agent-label">
            <img :src="avatar" class="ap-mini" :alt="name" />{{ name }}
          </div>
          <div
            class="ap-bubble ap-bubble-agent"
            v-html="renderMd(msg.content)"
          ></div>
        </template>
        <div v-else-if="msg.role !== 'agent'" class="ap-bubble ap-bubble-user">{{ msg.content }}</div>
      </div>

      <!-- 인사말 버블 (사용자 메시지 없을 때 항상 표시) -->
      <template v-if="greeting && !messages.some(m => m.role === 'user')">
        <div class="ap-msg-row fade-in agent">
          <div class="ap-agent-label"><img :src="avatar" class="ap-mini" :alt="name" />{{ name }}</div>
          <div class="ap-bubble ap-bubble-agent" style="white-space:pre-line" v-html="renderMd(greeting)"></div>
        </div>
      </template>

      <!-- 추천 질문 (사용자가 아직 메시지를 보내지 않은 경우 항상 표시) -->
      <div v-if="quickQuestions.length && !messages.some(m => m.role === 'user')" class="ap-inline-quick">
        <button
          v-for="q in quickQuestions"
          :key="q"
          class="ap-inline-btn"
          :disabled="loading"
          @click="sendQuick(q)"
        >{{ q }}</button>
      </div>

      <!-- 타이핑 인디케이터 -->
      <div v-if="loading" class="ap-msg-row agent">
        <div class="ap-agent-label">
          <img :src="avatar" class="ap-mini" :alt="name" />{{ name }}
        </div>
        <div class="ap-bubble ap-bubble-agent ap-typing">
          <span></span><span></span><span></span>
        </div>
      </div>

      <!-- 메시지 아래 추가 슬롯 (HITL 배너 등) -->
      <slot name="messages-extra" />
    </div>

    <!-- ── 입력창 ── -->
    <div class="ap-input-area">
      <div class="ap-input-wrap">
        <div v-if="pendingFiles.length" class="ap-file-chips">
          <span v-for="(f, i) in pendingFiles" :key="i" class="ap-file-chip">
            <span class="ap-chip-icon">📎</span>
            <span class="ap-chip-name">{{ f.name }}</span>
            <button class="ap-chip-remove" @click="$emit('remove-file', i)" title="제거">×</button>
          </span>
        </div>
        <div class="ap-input-row">
          <button class="ap-attach-btn" :disabled="loading" title="파일 첨부" @click="fileInput.click()">＋</button>
          <textarea
            v-model="input"
            class="ap-input"
            :placeholder="pendingFiles.length ? '파일에 대한 메시지를 입력하세요 (선택)...' : placeholder"
            rows="2"
            @keydown.enter.exact.prevent="send"
          />
        </div>
        <input ref="fileInput" type="file" multiple style="display:none" @change="onFileSelected" />
      </div>
      <button
        class="ap-send-btn"
        :disabled="loading || (!input.trim() && !pendingFiles.length)"
        @click="send"
      >전송</button>
    </div>

    <!-- ── footer-extra 슬롯 (기획안 요청 버튼 등) ── -->
    <slot name="footer-extra" />

    <!-- ── 리사이즈 핸들 (오른쪽 끝) ── -->
    <div class="ap-resize-handle" @mousedown.prevent="onResizeStart"></div>
  </div>
</template>

<style scoped>
.agent-panel {
  display: flex;
  flex-direction: column;
  min-height: 0;
  overflow: hidden;
  flex-shrink: 0;
  flex-grow: 0;     /* 부모 flex에 의해 늘어나지 않음 — 너비는 내부 panelWidth가 전담 */
  min-width: 0;     /* flex 오버플로우 방지 */
  position: relative;
}

/* ── 헤더 ── */
.ap-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 22px 10px 16px; /* 오른쪽 여백: 핸들 공간 */
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
}
.ap-title { display: flex; align-items: center; gap: 10px; }
.ap-avatar {
  width: 40px; height: 40px; border-radius: 50%; object-fit: cover;
  border: 2px solid var(--ap-accent-border, #fbbf24);
  box-shadow: 0 0 0 3px var(--ap-accent-bg, #fef3c7);
  flex-shrink: 0;
}
.ap-name { font-weight: 700; font-size: 14px; }
.ap-name-en { font-weight: 400; color: var(--text-muted); font-size: 13px; }
.ap-subtitle { font-size: 11px; color: var(--text-muted); margin-top: 1px; }
.ap-actions { display: flex; align-items: center; gap: 6px; flex-shrink: 0; }

/* ── 새 채팅 버튼 ── */
.ap-new-chat-btn {
  background: none;
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 3px 10px;
  font-size: 12px;
  font-weight: 500;
  color: var(--text-muted);
  cursor: pointer;
}
.ap-new-chat-btn:hover {
  background: var(--ap-accent-bg, #fffbeb);
  border-color: var(--ap-accent-border, #fbbf24);
  color: var(--ap-accent, #f59e0b);
}

/* ── 인라인 추천 버튼 ── */
.ap-inline-quick {
  display: flex;
  flex-direction: column;
  gap: 5px;
  margin-top: 4px;
  padding: 0 2px;
}
.ap-inline-btn {
  text-align: left;
  background: var(--ap-accent-bg, #fffbeb);
  border: 1px solid var(--ap-accent-border, #fbbf24);
  border-radius: 7px;
  padding: 7px 12px;
  font-size: 12px;
  color: var(--ap-accent, #f59e0b);
  cursor: pointer;
  line-height: 1.4;
  font-weight: 500;
}
.ap-inline-btn:hover:not(:disabled) { filter: brightness(.92); }
.ap-inline-btn:disabled { opacity: .4; cursor: not-allowed; }

/* ── 메시지 ── */
.ap-messages {
  flex: 1;
  overflow-y: auto;
  padding: 14px 16px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.ap-msg-row { display: flex; flex-direction: column; gap: 3px; }
.ap-msg-row.user  { align-items: flex-end; }
.ap-msg-row.agent { align-items: flex-start; }

.ap-agent-label {
  display: flex; align-items: center; gap: 5px;
  font-size: 11px; font-weight: 600;
  color: var(--ap-accent, #f59e0b);
  margin-bottom: 2px;
}
.ap-mini { width: 16px; height: 16px; border-radius: 50%; object-fit: cover; flex-shrink: 0; }

.ap-bubble {
  padding: 8px 12px;
  border-radius: 12px;
  font-size: 13px;
  line-height: 1.65;
  max-width: 92%;
  word-break: break-word;
}
.ap-bubble-agent {
  background: var(--ap-bubble-grad, linear-gradient(135deg,#fef3c7,#fed7aa));
  border: 1px solid var(--ap-accent-border, #fbbf24);
  color: var(--ap-bubble-color, #92400e);
  border-radius: 2px 12px 12px 12px;
  white-space: normal;
}
/* 마크다운 스타일 */
.ap-bubble-agent :deep(p)             { margin: 0 0 6px; }
.ap-bubble-agent :deep(p:last-child)  { margin-bottom: 0; }
.ap-bubble-agent :deep(ul),
.ap-bubble-agent :deep(ol)            { margin: 4px 0 6px 18px; padding: 0; }
.ap-bubble-agent :deep(li)            { margin-bottom: 2px; }
.ap-bubble-agent :deep(strong)        { font-weight: 700; }
.ap-bubble-agent :deep(em)            { font-style: italic; }
.ap-bubble-agent :deep(h1),
.ap-bubble-agent :deep(h2),
.ap-bubble-agent :deep(h3),
.ap-bubble-agent :deep(h4)            { font-weight: 700; margin: 8px 0 4px; line-height: 1.3; }
.ap-bubble-agent :deep(h1)            { font-size: 15px; }
.ap-bubble-agent :deep(h2)            { font-size: 14px; border-bottom: 1px solid rgba(0,0,0,.1); padding-bottom: 2px; }
.ap-bubble-agent :deep(h3)            { font-size: 13px; }
.ap-bubble-agent :deep(h4)            { font-size: 13px; font-style: italic; }
.ap-bubble-agent :deep(code)          { background: rgba(0,0,0,.08); padding: 1px 5px; border-radius: 4px; font-size: 12px; font-family: monospace; }
.ap-bubble-agent :deep(pre)           { background: var(--dark-card); color: var(--dark-text); padding: 10px 12px; border-radius: 8px; overflow-x: auto; margin: 6px 0; font-size: 12px; }
.ap-bubble-agent :deep(pre code)      { background: none; padding: 0; }
.ap-bubble-agent :deep(blockquote)    { border-left: 3px solid rgba(0,0,0,.2); padding-left: 10px; margin: 6px 0; opacity: .8; }
.ap-bubble-agent :deep(hr)            { border: none; border-top: 1px solid rgba(0,0,0,.15); margin: 8px 0; }
.ap-bubble-agent :deep(table)         { border-collapse: collapse; width: 100%; margin: 6px 0; font-size: 12px; }
.ap-bubble-agent :deep(th),
.ap-bubble-agent :deep(td)            { border: 1px solid rgba(0,0,0,.15); padding: 4px 8px; }
.ap-bubble-agent :deep(th)            { background: rgba(0,0,0,.06); font-weight: 600; }

.ap-bubble-user {
  background: var(--primary);
  color: #fff;
  border-radius: 12px 12px 2px 12px;
}

/* 타이핑 */
.ap-typing {
  display: flex !important;
  align-items: center;
  gap: 4px;
  padding: 10px 14px !important;
}
.ap-typing span {
  width: 7px; height: 7px;
  background: var(--ap-accent, #d97706);
  border-radius: 50%;
  animation: ap-bounce 1.2s infinite;
}
.ap-typing span:nth-child(2) { animation-delay: .2s; }
.ap-typing span:nth-child(3) { animation-delay: .4s; }
@keyframes ap-bounce { 0%,80%,100%{transform:translateY(0)} 40%{transform:translateY(-6px)} }

/* ── 입력창 ── */
.ap-input-area {
  display: flex;
  gap: 8px;
  padding: 10px 16px;
  border-top: 1px solid var(--border);
  flex-shrink: 0;
}
.ap-input-wrap {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.ap-file-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 5px;
}
.ap-file-chip {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  background: var(--ap-accent-bg, #fef3c7);
  border: 1px solid var(--ap-accent-border, #fbbf24);
  border-radius: 6px;
  padding: 2px 6px;
  font-size: 11px;
  color: var(--text);
  max-width: 200px;
}
.ap-chip-icon { flex-shrink: 0; }
.ap-chip-name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  flex: 1;
}
.ap-chip-remove {
  background: none;
  border: none;
  cursor: pointer;
  font-size: 13px;
  line-height: 1;
  padding: 0 2px;
  color: var(--text-muted);
  flex-shrink: 0;
}
.ap-chip-remove:hover { color: var(--danger); }
.ap-input {
  flex: 1;
  resize: none;
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 7px 10px;
  font-size: 13px;
  outline: none;
  font-family: inherit;
  line-height: 1.5;
}
.ap-input:focus {
  border-color: var(--ap-accent-border, #fbbf24);
  box-shadow: 0 0 0 2px var(--ap-accent-bg, #fef3c7);
}
.ap-send-btn {
  background: var(--ap-accent, #f59e0b);
  color: #fff;
  border: none;
  border-radius: 8px;
  padding: 6px 14px;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  align-self: flex-end;
  white-space: nowrap;
}
.ap-send-btn:disabled { opacity: .45; cursor: not-allowed; }
.ap-send-btn:not(:disabled):hover { opacity: .88; }

.ap-input-row {
  display: flex;
  align-items: flex-end;
  gap: 6px;
}
.ap-attach-btn {
  flex-shrink: 0;
  width: 30px; height: 30px;
  border-radius: 50%;
  border: 1px solid var(--border);
  background: var(--surface);
  color: var(--text-muted);
  font-size: 18px;
  line-height: 1;
  cursor: pointer;
  display: flex; align-items: center; justify-content: center;
  align-self: flex-end;
  margin-bottom: 2px;
}
.ap-attach-btn:hover:not(:disabled) {
  background: var(--ap-accent-bg, #fef3c7);
  border-color: var(--ap-accent-border, #fbbf24);
  color: var(--ap-accent, #f59e0b);
}
.ap-attach-btn:disabled { opacity: .4; cursor: not-allowed; }

/* 드래그 오버레이 */
.ap-drag-overlay {
  position: absolute; inset: 0; z-index: 20;
  background: rgba(99,102,241,.07);
  border: 2px dashed var(--ap-accent-border, #fbbf24);
  border-radius: var(--radius, 10px);
  display: flex; align-items: center; justify-content: center;
  pointer-events: none;
}
.ap-drag-hint {
  background: white;
  border: 1px solid var(--ap-accent-border, #fbbf24);
  border-radius: var(--radius, 10px);
  padding: 12px 24px;
  font-size: 14px; font-weight: 600;
  color: var(--ap-accent, #f59e0b);
  box-shadow: 0 2px 8px rgba(0,0,0,.08);
  display: flex; align-items: center; gap: 8px;
}

/* ── 리사이즈 핸들 ── */
.ap-resize-handle {
  position: absolute;
  top: 0; right: 0;
  width: 5px; height: 100%;
  cursor: ew-resize;
  background: transparent;
  z-index: 10;
}
.ap-resize-handle:hover { background: rgba(99,102,241,.35); }
</style>
