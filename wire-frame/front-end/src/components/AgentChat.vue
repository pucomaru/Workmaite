<script setup>
import { ref, nextTick, onMounted } from 'vue'
import { streamPost } from '../api'
import { marked } from 'marked'
const renderMd = (text) => marked.parse(text || '', { breaks: true })

const props = defineProps({
  agentName: { type: String, required: true },
  agentColor: { type: String, default: '#1e3a5f' },
  endpoint: { type: String, required: true },
  meetingId: { type: Number, required: true },
  placeholder: { type: String, default: '메시지를 입력하세요...' },
  initialMessage: { type: String, default: '' },
  extraBody: { type: Object, default: () => ({}) },
})

const emit = defineEmits(['agentResponse'])

const messages = ref([])
const input = ref('')
const loading = ref(false)
const messagesEl = ref(null)

onMounted(async () => {
  if (props.initialMessage) {
    await sendMessage(props.initialMessage, true)
  }
})

async function sendMessage(text, auto = false) {
  if (!text.trim() || loading.value) return
  const userMsg = text.trim()
  if (!auto) {
    messages.value.push({ role: 'user', content: userMsg })
    input.value = ''
  }

  const agentMsg = { role: 'agent', content: '' }
  messages.value.push(agentMsg)
  loading.value = true
  await scrollBottom()

  const history = messages.value
    .filter(m => m.content)
    .slice(0, -1)
    .map(m => ({ role: m.role === 'user' ? 'user' : 'assistant', content: m.content }))

  await streamPost(
    props.endpoint,
    { meeting_id: props.meetingId, message: userMsg, chat_history: history, ...props.extraBody },
    (chunk) => {
      agentMsg.content += chunk
      scrollBottom()
    },
    () => {
      loading.value = false
      emit('agentResponse', agentMsg.content)
    }
  )
}

async function scrollBottom() {
  await nextTick()
  if (messagesEl.value) messagesEl.value.scrollTop = messagesEl.value.scrollHeight
}

function onKeydown(e) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    sendMessage(input.value)
  }
}
</script>

<template>
  <div class="chat-container card">
    <div class="card-header">
      <div class="agent-label">
        <span class="agent-dot" :style="{ background: agentColor }"></span>
        <span style="font-weight:600;font-size:13px">{{ agentName }}</span>
      </div>
    </div>
    <div ref="messagesEl" class="chat-messages">
      <div v-if="!messages.length" class="empty-state">
        <p>{{ agentName }}에게 질문하거나 작업을 요청하세요.</p>
      </div>
      <div
        v-for="(msg, i) in messages"
        :key="i"
        class="chat-msg-row fade-in"
        :class="msg.role"
      >
        <div v-if="msg.role === 'agent'" class="chat-agent-label">
          <span class="agent-dot-sm" :style="{ background: agentColor }"></span>
          {{ agentName }}
        </div>
        <div v-if="msg.role === 'agent'" class="chat-bubble agent" v-html="renderMd(msg.content)"></div>
        <div v-else class="chat-bubble" :class="msg.role">{{ msg.content }}</div>
      </div>
      <div v-if="loading && messages[messages.length-1]?.content === ''" class="chat-msg-row agent">
        <div class="chat-bubble agent typing">
          <span></span><span></span><span></span>
        </div>
      </div>
    </div>
    <div class="chat-input-area">
      <textarea
        v-model="input"
        class="chat-input"
        :placeholder="placeholder"
        rows="1"
        @keydown="onKeydown"
      />
      <button class="btn btn-primary btn-sm" :disabled="loading || !input.trim()" @click="sendMessage(input)">전송</button>
    </div>
  </div>
</template>

<style scoped>
.agent-label { display: flex; align-items: center; gap: 8px; }
.agent-dot { width: 10px; height: 10px; border-radius: 50%; flex-shrink: 0; }
.agent-dot-sm { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
.typing { display: flex; gap: 4px; align-items: center; padding: 12px 16px; }
.typing span { width: 6px; height: 6px; background: var(--text-muted); border-radius: 50%; animation: bounce .8s infinite; }
.typing span:nth-child(2) { animation-delay: .15s; }
.typing span:nth-child(3) { animation-delay: .3s; }
@keyframes bounce { 0%,80%,100% { transform: scale(0.8); opacity:.5; } 40% { transform: scale(1.2); opacity:1; } }
</style>
