<script setup>
import { ref } from 'vue'
import { marked } from 'marked'

const renderMd = (text) => marked.parse(text || '', { breaks: true })

const props = defineProps({
  avatar:        { type: String, required: true },
  name:          { type: String, required: true },
  nameEn:        { type: String, default: '' },
  subtitle:      { type: String, default: '' },
  messages:      { type: Array,  default: () => [] },
  loading:       { type: Boolean, default: false },
  quickQuestions:{ type: Array,  default: () => [] },
  placeholder:   { type: String, default: '질문하세요...' },
  initialWidth:  { type: Number, default: 380 },
  // 에이전트별 색상 테마
  accentColor:   { type: String, default: '#f59e0b' },  // label color
  accentBorder:  { type: String, default: '#fbbf24' },  // border / ring
  accentBg:      { type: String, default: '#fef3c7' },  // light bg
  bubbleGradient:{ type: String, default: 'linear-gradient(135deg,#fef3c7,#fed7aa)' },
  bubbleColor:   { type: String, default: '#92400e' },
})

const emit = defineEmits(['send', 'clear'])

const input = ref('')
const messagesEl = ref(null)

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
  if (!input.value.trim() || props.loading) return
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
        <button
          class="btn btn-ghost btn-sm"
          style="color:var(--text-muted)"
          title="대화 초기화"
          @click="$emit('clear')"
        >🗑</button>
      </div>
    </div>

    <!-- ── 빠른 질문 ── -->
    <div v-if="quickQuestions.length" class="ap-quick">
      <button
        v-for="q in quickQuestions"
        :key="q"
        class="ap-quick-btn"
        :disabled="loading"
        @click="sendQuick(q)"
      >{{ q }}</button>
    </div>

    <!-- ── extra-header 슬롯 (세션 선택기 등) ── -->
    <slot name="extra-header" />

    <!-- ── overlay 슬롯 (드래그 오버레이 등) ── -->
    <slot name="overlay" />

    <!-- ── 메시지 영역 ── -->
    <div class="ap-messages" ref="messagesEl">
      <div
        v-for="(msg, i) in messages"
        :key="i"
        class="ap-msg-row fade-in"
        :class="msg.role"
      >
        <div v-if="msg.role === 'agent'" class="ap-agent-label">
          <img :src="avatar" class="ap-mini" :alt="name" />{{ name }}
        </div>
        <div
          v-if="msg.role === 'agent'"
          class="ap-bubble ap-bubble-agent"
          v-html="renderMd(msg.content)"
        ></div>
        <div v-else class="ap-bubble ap-bubble-user">{{ msg.content }}</div>
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
      <textarea
        v-model="input"
        class="ap-input"
        :placeholder="placeholder"
        rows="2"
        @keydown.enter.exact.prevent="send"
      />
      <button
        class="ap-send-btn"
        :disabled="loading || !input.trim()"
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

/* ── 빠른 질문 ── */
.ap-quick {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  padding: 10px 16px;
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
}
.ap-quick-btn {
  font-size: 11px;
  padding: 4px 10px;
  border-radius: 99px;
  border: 1px solid var(--ap-accent-border, #fbbf24);
  background: var(--ap-accent-bg, #fffbeb);
  color: var(--text);
  cursor: pointer;
  transition: filter .15s;
  white-space: nowrap;
}
.ap-quick-btn:hover:not(:disabled) { filter: brightness(.93); }
.ap-quick-btn:disabled { opacity: .5; cursor: not-allowed; }

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
.ap-bubble-agent :deep(p)          { margin: 0 0 6px; }
.ap-bubble-agent :deep(p:last-child){ margin-bottom: 0; }
.ap-bubble-agent :deep(ul),
.ap-bubble-agent :deep(ol)         { margin: 4px 0 6px 18px; padding: 0; }
.ap-bubble-agent :deep(li)         { margin-bottom: 2px; }
.ap-bubble-agent :deep(strong)     { font-weight: 700; }
.ap-bubble-agent :deep(h1),
.ap-bubble-agent :deep(h2),
.ap-bubble-agent :deep(h3)         { font-weight: 700; margin: 8px 0 4px; line-height: 1.3; }
.ap-bubble-agent :deep(code)       { background: rgba(0,0,0,.08); padding: 1px 5px; border-radius: 4px; font-size: 12px; }

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
  transition: opacity .15s;
  align-self: flex-end;
  white-space: nowrap;
}
.ap-send-btn:disabled { opacity: .45; cursor: not-allowed; }
.ap-send-btn:not(:disabled):hover { opacity: .88; }

/* ── 리사이즈 핸들 ── */
.ap-resize-handle {
  position: absolute;
  top: 0; right: 0;
  width: 5px; height: 100%;
  cursor: ew-resize;
  background: transparent;
  transition: background .15s;
  z-index: 10;
}
.ap-resize-handle:hover { background: rgba(99,102,241,.35); }
</style>
