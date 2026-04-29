<script setup>
import { ref, onMounted } from 'vue'
import { streamPost } from '../api'
import { useAuthStore } from '../stores/auth'
import { useMeetingsStore } from '../stores/meetings'
import api from '../api'
import hyeanAvatar from '../assets/agents/hyean.png'

const props = defineProps({ meetingId: { type: Number, default: 0 } })
const auth = useAuthStore()
const meetingsStore = useMeetingsStore()

const open = ref(false)
const activeTab = ref('status')
const messages = ref([])
const input = ref('')
const loading = ref(false)
const knowledgeSummary = ref(null)
const messagesEl = ref(null)

onMounted(async () => {
  try {
    const { data } = await api.get(`/api/tacit-knowledge/summary?meeting_id=${props.meetingId}`)
    knowledgeSummary.value = data
  } catch {}
})

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
    {
      meeting_id: props.meetingId,
      message: text,
      chat_history: messages.value.slice(0, -1).map(m => ({
        role: m.role === 'user' ? 'user' : 'assistant',
        content: m.content,
      })),
    },
    (chunk) => { agentMsg.content += chunk },
    () => { loading.value = false }
  )
}

async function askStatus() {
  const agentMsg = { role: 'agent', content: '' }
  messages.value.push(agentMsg)
  loading.value = true
  await streamPost(
    '/api/agent/hyean/status',
    { meeting_id: props.meetingId, user_role: meetingsStore.myRole || 'presenter' },
    (chunk) => { agentMsg.content += chunk },
    () => { loading.value = false }
  )
}
</script>

<template>
  <div class="hyean-wrap">
    <button class="hyean-fab" @click="open = !open" :class="{ active: open }">
      <img v-if="!open" :src="hyeanAvatar" class="hyean-fab-avatar" alt="혜안" />
      <svg v-else width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M6 18L18 6M6 6l12 12"/></svg>
      <span class="hyean-label">혜안</span>
    </button>

    <div v-if="open" class="hyean-panel slide-up">
      <div class="panel-header">
        <div style="display:flex;align-items:center;gap:10px">
          <img :src="hyeanAvatar" class="agent-header-avatar" alt="혜안" />
          <div>
            <div style="font-weight:700;font-size:14px;color:var(--primary)">혜안 (Hyean)</div>
            <div style="font-size:11px;color:var(--text-muted)">회의체 현황 분석</div>
          </div>
        </div>
        <div class="tabs" style="margin:0">
          <button class="tab-btn" :class="{ active: activeTab==='status' }" @click="activeTab='status'">현황 안내</button>
          <button class="tab-btn" :class="{ active: activeTab==='knowledge' }" @click="activeTab='knowledge'">운영 기준</button>
        </div>
      </div>

      <div class="panel-body">
        <div v-if="activeTab === 'status'" class="chat-container" style="height:100%">
          <div ref="messagesEl" class="chat-messages">
            <div v-if="!messages.length" class="empty-state" style="padding:24px">
              <p>현재 회의체 현황을 분석해드립니다.</p>
              <button class="btn btn-primary btn-sm" @click="askStatus">현황 분석하기</button>
            </div>
            <div v-for="(msg, i) in messages" :key="i" class="chat-msg-row fade-in" :class="msg.role">
              <div v-if="msg.role==='agent'" class="chat-agent-label">
                <img :src="hyeanAvatar" class="chat-avatar-sm" alt="혜안" />
                혜안
              </div>
              <div class="chat-bubble" :class="msg.role">{{ msg.content }}</div>
            </div>
          </div>
          <div class="chat-input-area">
            <textarea v-model="input" class="chat-input" placeholder="질문하세요..." rows="1" @keydown.enter.exact.prevent="sendMessage" />
            <button class="btn btn-primary btn-sm" :disabled="loading || !input.trim()" @click="sendMessage">전송</button>
          </div>
        </div>

        <div v-else class="knowledge-tab">
          <div v-if="knowledgeSummary">
            <div class="kb-section">
              <div class="kb-label">글로벌 기준 ({{ knowledgeSummary.global.length }}개)</div>
              <div v-for="k in knowledgeSummary.global" :key="k.id" class="kb-item">
                <span class="badge badge-primary" style="font-size:10px">{{ k.category }}</span>
                {{ k.title }}
              </div>
            </div>
            <div class="kb-section" v-if="knowledgeSummary.meeting.length">
              <div class="kb-label">회의체별 기준 ({{ knowledgeSummary.meeting.length }}개)</div>
              <div v-for="k in knowledgeSummary.meeting" :key="k.id" class="kb-item">
                {{ k.title }}
              </div>
            </div>
            <router-link to="/tacit-knowledge" class="btn btn-outline btn-sm" style="margin-top:12px;width:100%;justify-content:center">전체 기준 관리 →</router-link>
          </div>
          <div v-else class="empty-state">운영 기준을 불러오는 중...</div>
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
.hyean-fab-avatar { width: 28px; height: 28px; border-radius: 50%; object-fit: cover; border: 1.5px solid rgba(255,255,255,.4); flex-shrink: 0; }
.hyean-label { font-size: 14px; font-weight: 600; }
.hyean-panel { width: 360px; height: 500px; background: #fff; border-radius: var(--radius-lg); box-shadow: var(--shadow-lg); border: 1px solid var(--border); display: flex; flex-direction: column; overflow: hidden; }
.panel-header { padding: 12px 16px; border-bottom: 1px solid var(--border); display: flex; align-items: center; justify-content: space-between; flex-shrink: 0; gap: 10px; flex-wrap: wrap; }
.panel-body { flex: 1; overflow: hidden; display: flex; flex-direction: column; }
.knowledge-tab { padding: 16px; overflow-y: auto; }
.kb-section { margin-bottom: 16px; }
.kb-label { font-size: 11px; font-weight: 600; color: var(--text-muted); text-transform: uppercase; margin-bottom: 8px; }
.kb-item { padding: 6px 0; font-size: 13px; border-bottom: 1px solid var(--border); display: flex; align-items: center; gap: 6px; }
</style>
