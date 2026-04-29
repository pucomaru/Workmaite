<script setup>
import { ref, onMounted, onBeforeUnmount, computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import api from '../api'
import { streamPost } from '../api'
import { useMeetingsStore } from '../stores/meetings'
import { useAuthStore } from '../stores/auth'
import { useChatHistory } from '../composables/useChatHistory'
import LiveKitRoom from '../components/LiveKitRoom.vue'
import PreJoinLobby from '../components/PreJoinLobby.vue'

const route = useRoute()
const router = useRouter()
const meetingsStore = useMeetingsStore()
const auth = useAuthStore()
const meetingId = computed(() => Number(route.params.meetingId))
const sessionId = computed(() => Number(route.params.sessionId))
const role = computed(() => meetingsStore.myRole)

// 쿼리 파라미터로 받은 LiveKit 토큰 (참여 즉시 연결용)
const qToken = route.query.lkToken
const qUrl = route.query.lkUrl

const isRecording = ref(false)
const araTab = ref('summary')
const araInput = ref('')
const araLoading = ref(false)
const prevMinutes = ref([])
const agendas = ref([])
const participants = ref([])
const sessionStatus = ref('scheduled')
const elapsedTime = ref(0)
let timer = null

// 녹취 (STT 자막)
const transcripts = ref([])  // { name, text, time }
const transcriptRef = ref(null)

function onTranscript(seg) {
  transcripts.value.push(seg)
  // 자동 스크롤
  setTimeout(() => {
    if (transcriptRef.value) transcriptRef.value.scrollTop = transcriptRef.value.scrollHeight
  }, 50)
}

// LiveKit 로비 / 회의실
const showLobby = ref(false)       // 사전 입장 설정 화면
const showLiveKit = ref(false)     // 실제 회의실
const livekitToken = ref('')
const livekitUrl = ref('')
const lkParticipantCount = ref(0)
const lkInitialMic = ref(true)
const lkInitialCam = ref(true)
const lkRoomRef = ref(null)        // LiveKitRoom 컴포넌트 ref

// 하단 컨트롤 — LiveKit 연결 시 lkRoomRef 위임, 아닐 때 로컬 상태
const micOn = ref(true)
const camOn = ref(true)
function toggleMic() { showLiveKit.value && lkRoomRef.value ? lkRoomRef.value.toggleMic() : (micOn.value = !micOn.value) }
function toggleCam() { showLiveKit.value && lkRoomRef.value ? lkRoomRef.value.toggleCam() : (camOn.value = !camOn.value) }

const { messages: araMessages, clearHistory: clearAraHistory, loadMessages: loadAraMessages, saveMessage: saveAraMessage } = useChatHistory(
  'room',
  sessionId.value,
)

onMounted(async () => {
  await meetingsStore.fetchMeeting(meetingId.value)
  await meetingsStore.fetchRole(meetingId.value)

  const sessions = await api.get(`/api/meetings/${meetingId.value}/sessions`)
  const session = sessions.data.find(s => s.id === sessionId.value)
  if (session) sessionStatus.value = session.status

  const agendasRes = await api.get(`/api/meetings/${meetingId.value}/agendas`)
  agendas.value = agendasRes.data.filter(a => a.status === 'confirmed')

  // Simulate participants
  const membersRes = await api.get(`/api/meetings/${meetingId.value}/members`)
  participants.value = membersRes.data.map(m => ({ ...m.user, role: m.role, micOn: true }))

  await loadAraMessages()
  if (araMessages.value.length === 0) {
    const greeting = '안녕하세요! 아라입니다. 회의를 도와드리겠습니다.\n"지난 회의 요약"이나 "현재 아젠다"를 물어보세요.'
    araMessages.value.push({ role: 'agent', content: greeting })
    saveAraMessage('agent', greeting)
  }
  // 쿼리 파라미터로 토큰이 전달된 경우 → 로비 화면 먼저 표시
  if (qToken && qUrl) {
    livekitToken.value = qToken
    livekitUrl.value = qUrl
    showLobby.value = true
  }
})

onBeforeUnmount(() => {
  if (timer) clearInterval(timer)
})

async function startMeeting() {
  await api.post(`/api/sessions/${sessionId.value}/start`)
  isRecording.value = true
  sessionStatus.value = 'ongoing'
  timer = setInterval(() => elapsedTime.value++, 1000)
  // LiveKit 토큰 발급 후 팝업 열기
  await openLiveKit()
}

async function openLiveKit() {
  try {
    const res = await api.get(`/api/livekit/token/${meetingId.value}/${sessionId.value}`)
    livekitToken.value = res.data.token
    livekitUrl.value = res.data.url
    showLobby.value = true  // 토큰 발급 후 로비 화면 표시
  } catch (e) {
    alert(e.response?.data?.detail || 'LiveKit 토큰 발급 실패')
  }
}

// 로비에서 입장하기 클릭
function onLobbyJoin({ micOn, camOn }) {
  lkInitialMic.value = micOn
  lkInitialCam.value = camOn
  showLobby.value = false
  showLiveKit.value = true
  if (!isRecording.value) {
    isRecording.value = true
    sessionStatus.value = 'ongoing'
    timer = setInterval(() => elapsedTime.value++, 1000)
  }
}

function onLobbyCancel() {
  showLobby.value = false
}

async function endMeeting() {
  if (!confirm('회의를 종료하시겠습니까? 회의록이 자동 생성됩니다.')) return
  isRecording.value = false
  clearInterval(timer)
  // 발화 녹취를 함께 종료 요청
  await api.post(`/api/sessions/${sessionId.value}/end`, { transcript: transcripts.value })
  sessionStatus.value = 'ended'
  const endMsg = '회의가 종료되었습니다. 회의록을 생성하고 있습니다...'
  araMessages.value.push({ role: 'agent', content: endMsg })
  saveAraMessage('agent', endMsg)
  setTimeout(() => {
    window.close()
  }, 2000)
}

async function sendAra() {
  if (!araInput.value.trim() || araLoading.value) return
  const text = araInput.value.trim()
  araMessages.value.push({ role: 'user', content: text })
  saveAraMessage('user', text)
  araInput.value = ''
  const agentMsg = { role: 'agent', content: '' }
  araMessages.value.push(agentMsg)
  araLoading.value = true

  const history = araMessages.value.slice(0,-1).map(m => ({ role: m.role === 'user' ? 'user' : 'assistant', content: m.content }))
  await streamPost(
    '/api/agent/ara/chat',
    { meeting_id: meetingId.value, message: text, chat_history: history },
    (chunk) => { agentMsg.content += chunk },
    () => { araLoading.value = false; saveAraMessage('agent', agentMsg.content) }
  )
}

function formatTime(s) {
  const h = Math.floor(s / 3600)
  const m = Math.floor((s % 3600) / 60)
  const sec = s % 60
  if (h > 0) return `${h}:${String(m).padStart(2,'0')}:${String(sec).padStart(2,'0')}`
  return `${String(m).padStart(2,'0')}:${String(sec).padStart(2,'0')}`
}
</script>

<template>
  <div class="room-layout">
    <!-- 사전 입장 로비 (오버레이) -->
    <PreJoinLobby
      v-if="showLobby"
      :display-name="auth.user?.name || '참여자'"
      @join="onLobbyJoin"
      @cancel="onLobbyCancel"
    />

    <!-- Ara sidebar -->
    <div class="ara-sidebar card">
      <div class="ara-header">
        <span style="font-weight:700;font-size:14px;color:var(--primary)">🌊 아라 (Ara)</span>
        <div style="display:flex;align-items:center;gap:4px">
          <button class="btn btn-ghost btn-sm" style="color:var(--text-muted)" @click="clearAraHistory" title="대화 기록 지우기">🗑</button>
          <div class="tabs" style="margin:0">
            <button class="tab-btn" :class="{active: araTab==='summary'}" @click="araTab='summary'">이전 요약</button>
            <button class="tab-btn" :class="{active: araTab==='agenda'}" @click="araTab='agenda'">아젠다</button>
            <button class="tab-btn" :class="{active: araTab==='transcript'}" @click="araTab='transcript'">
              발화<span v-if="transcripts.length" class="tab-badge">{{ transcripts.length }}</span>
            </button>
            <button class="tab-btn" :class="{active: araTab==='chat'}" @click="araTab='chat'">채팅</button>
          </div>
        </div>
      </div>
      <div class="ara-body">
        <div v-if="araTab === 'summary'" style="padding:16px;overflow-y:auto;flex:1">
          <div v-for="(msg, i) in araMessages.filter(m=>m.role==='agent')" :key="i" class="ara-msg fade-in">
            {{ msg.content }}
          </div>
          <div v-if="!prevMinutes.length" class="empty-state" style="padding:16px">
            <p>이전 회의록이 없습니다.</p>
          </div>
        </div>
        <div v-else-if="araTab === 'agenda'" style="padding:16px;overflow-y:auto;flex:1">
          <div v-if="!agendas.length" class="empty-state" style="padding:16px"><p>확정된 아젠다가 없습니다.</p></div>
          <div v-for="(a, i) in agendas" :key="a.id" class="agenda-chip" style="margin-bottom:8px">
            <span class="badge badge-primary">{{ i+1 }}</span>
            <div>
              <div style="font-size:13px;font-weight:500">{{ a.content }}</div>
              <div style="font-size:11px;color:var(--text-muted)">{{ a.department }}</div>
            </div>
          </div>
        </div>
        <!-- 녹취 탭 -->
        <div v-else-if="araTab === 'transcript'" class="transcript-panel" ref="transcriptRef">
          <div v-if="!transcripts.length" class="empty-state" style="padding:24px;text-align:center">
            <p style="color:#94a3b8;font-size:13px">회의 참여 후 발화가 감지되면<br>여기에 표시됩니다.</p>
          </div>
          <div
            v-for="(seg, i) in transcripts"
            :key="i"
            class="transcript-row"
            :class="seg.isSelf ? 'self' : 'other'"
          >
            <div v-if="!seg.isSelf" class="tr-avatar">{{ seg.name[0] }}</div>
            <div class="tr-bubble-wrap">
              <div class="tr-name">{{ seg.name }}</div>
              <div class="tr-bubble">{{ seg.text }}</div>
              <div class="tr-time">{{ seg.time }}</div>
            </div>
            <div v-if="seg.isSelf" class="tr-avatar self-avatar">{{ seg.name[0] }}</div>
          </div>
        </div>
        <div v-else class="chat-container" style="height:100%">
          <div class="chat-messages" style="flex:1;overflow-y:auto">
            <div v-for="(msg, i) in araMessages" :key="i" class="chat-msg-row fade-in" :class="msg.role">
              <div v-if="msg.role==='agent'" class="chat-agent-label">아라</div>
              <div class="chat-bubble" :class="msg.role">{{ msg.content }}</div>
            </div>
          </div>
          <div class="chat-input-area">
            <textarea v-model="araInput" class="chat-input" placeholder="아라에게 질문..." rows="1" @keydown.enter.exact.prevent="sendAra" />
            <button class="btn btn-primary btn-sm" :disabled="araLoading || !araInput.trim()" @click="sendAra">전송</button>
          </div>
        </div>
      </div>
    </div>

    <!-- Main area -->
    <div class="room-main">
      <!-- 비디오 영역: LiveKit 연결 시 실제 비디오, 아닐 때 참여자 카드 -->
      <div class="video-area">
        <!-- LiveKit 인라인 비디오 그리드 -->
        <LiveKitRoom
          v-if="showLiveKit"
          ref="lkRoomRef"
          :token="livekitToken"
          :url="livekitUrl"
          :display-name="auth.user?.name || '참여자'"
          :initial-mic="lkInitialMic"
          :initial-cam="lkInitialCam"
          @participantCountChange="lkParticipantCount = $event"
          @transcript="onTranscript"
        />

        <!-- 대기 화면: 참여자 카드 -->
        <div v-else class="video-grid">
          <div v-for="p in participants" :key="p.id" class="video-tile">
            <div class="video-placeholder">
              <div class="participant-avatar">{{ p.name[0] }}</div>
              <div class="participant-name">
                {{ p.name }}
                <span class="badge badge-primary" style="font-size:10px">{{ p.role }}</span>
              </div>
            </div>
          </div>
          <div v-if="!participants.length" class="video-tile">
            <div class="video-placeholder">
              <div class="participant-avatar">{{ auth.user?.name[0] }}</div>
              <div class="participant-name">{{ auth.user?.name }} (나)</div>
            </div>
          </div>
        </div>
      </div>

      <!-- Status bar -->
      <div v-if="isRecording" class="recording-bar">
        <span class="rec-dot"></span>
        <span>녹화 중 • {{ formatTime(elapsedTime) }}</span>
      </div>

      <!-- Controls -->
      <div class="room-controls">
        <button class="ctrl-btn" :class="{ active: showLiveKit ? lkRoomRef?.micOn : micOn }" @click="toggleMic">
          <span>{{ (showLiveKit ? lkRoomRef?.micOn : micOn) ? '🎙' : '🔇' }}</span>
          <span>{{ (showLiveKit ? lkRoomRef?.micOn : micOn) ? '마이크 끄기' : '마이크 켜기' }}</span>
        </button>
        <button class="ctrl-btn" :class="{ active: showLiveKit ? lkRoomRef?.camOn : camOn }" @click="toggleCam">
          <span>{{ (showLiveKit ? lkRoomRef?.camOn : camOn) ? '📹' : '📷' }}</span>
          <span>{{ (showLiveKit ? lkRoomRef?.camOn : camOn) ? '카메라 끄기' : '카메라 켜기' }}</span>
        </button>

        <button v-if="!isRecording && sessionStatus !== 'ended'" class="ctrl-btn start" @click="startMeeting">
          <span>▶</span><span>회의 시작</span>
        </button>

        <button class="ctrl-btn leave" @click="window.close()">
          <span>↗</span><span>탭 닫기</span>
        </button>

        <button v-if="role === 'admin' && isRecording" class="ctrl-btn end" @click="endMeeting">
          <span>⏹</span><span>회의 종료</span>
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.room-layout { display: flex; height: calc(100vh - var(--header-h)); overflow: hidden; background: #0f172a; }
.ara-sidebar { width: 300px; height: 100%; border-radius: 0; display: flex; flex-direction: column; overflow: hidden; flex-shrink: 0; background: #1e293b; border: none; border-right: 1px solid #334155; }
.ara-header { padding: 12px 14px; border-bottom: 1px solid #334155; flex-shrink: 0; display: flex; flex-direction: column; gap: 8px; }
.ara-header .tab-btn { color: #94a3b8; }
.ara-header .tab-btn.active { color: var(--accent); border-bottom-color: var(--accent); }
.ara-body { flex: 1; overflow: hidden; display: flex; flex-direction: column; }
.ara-msg { font-size: 13px; line-height: 1.6; color: #cbd5e1; padding: 8px; background: #1e293b; border-radius: 8px; margin-bottom: 8px; white-space: pre-wrap; }
.agenda-chip { display: flex; align-items: flex-start; gap: 8px; padding: 10px; background: #1e293b; border-radius: 8px; }
.room-main { flex: 1; display: flex; flex-direction: column; overflow: hidden; }
.video-area { flex: 1; overflow: hidden; display: flex; flex-direction: column; }
.video-grid { flex: 1; display: grid; grid-template-columns: repeat(auto-fill, minmax(240px, 1fr)); gap: 8px; padding: 16px; overflow-y: auto; align-content: start; }
.video-tile { background: #1e293b; border-radius: 10px; aspect-ratio: 16/9; position: relative; overflow: hidden; display: flex; align-items: center; justify-content: center; }
.video-placeholder { display: flex; flex-direction: column; align-items: center; gap: 12px; }
.participant-avatar { width: 60px; height: 60px; background: var(--primary-light); border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 24px; font-weight: 700; color: #fff; }
.participant-name { color: #e2e8f0; font-size: 13px; font-weight: 500; display: flex; align-items: center; gap: 6px; }
.recording-bar { background: rgba(239,68,68,.15); border-top: 1px solid rgba(239,68,68,.3); padding: 6px 16px; display: flex; align-items: center; gap: 8px; color: #fca5a5; font-size: 13px; }
.rec-dot { width: 8px; height: 8px; background: var(--danger); border-radius: 50%; animation: pulse 1.2s infinite; }
@keyframes pulse { 0%,100%{opacity:1} 50%{opacity:.3} }
.room-controls { background: #1e293b; border-top: 1px solid #334155; padding: 12px 20px; display: flex; align-items: center; justify-content: center; gap: 8px; flex-shrink: 0; }
.ctrl-btn { display: flex; flex-direction: column; align-items: center; gap: 4px; padding: 8px 16px; background: #334155; color: #94a3b8; border-radius: 8px; font-size: 12px; transition: all .15s; min-width: 72px; }
.ctrl-btn span:first-child { font-size: 18px; }
.ctrl-btn:hover { background: #475569; color: #e2e8f0; }
.ctrl-btn.active { background: #1d4ed8; color: #fff; }
.ctrl-btn.start { background: var(--success); color: #fff; }
.ctrl-btn.livekit-btn { background: #7c3aed; color: #fff; }
.ctrl-btn.livekit-btn:hover { background: #6d28d9; }
.ctrl-btn.leave { background: #374151; color: #9ca3af; }
.ctrl-btn.end { background: var(--danger); color: #fff; }

/* 탭 뱃지 */
.tab-badge { display: inline-flex; align-items: center; justify-content: center; background: #3b82f6; color: #fff; font-size: 10px; font-weight: 700; border-radius: 10px; padding: 0 5px; min-width: 16px; height: 16px; margin-left: 4px; vertical-align: middle; }

/* 녹취 패널 — SMS 스타일 */
.transcript-panel { flex: 1; overflow-y: auto; padding: 12px 10px; display: flex; flex-direction: column; gap: 12px; }

.transcript-row { display: flex; align-items: flex-end; gap: 8px; }
.transcript-row.self { flex-direction: row-reverse; }

.tr-avatar {
  width: 32px; height: 32px; border-radius: 50%;
  background: #334155; color: #94a3b8;
  display: flex; align-items: center; justify-content: center;
  font-size: 13px; font-weight: 700; flex-shrink: 0;
}
.tr-avatar.self-avatar { background: #1d4ed8; color: #fff; }

.tr-bubble-wrap { display: flex; flex-direction: column; gap: 3px; max-width: 200px; }
.transcript-row.self .tr-bubble-wrap { align-items: flex-end; }
.transcript-row.other .tr-bubble-wrap { align-items: flex-start; }

.tr-name { font-size: 11px; color: #64748b; padding: 0 4px; }

.tr-bubble {
  font-size: 13px; line-height: 1.5; padding: 8px 10px; border-radius: 12px; word-break: break-all;
}
.transcript-row.other .tr-bubble { background: #1e3a5f; color: #e2e8f0; border-bottom-left-radius: 4px; }
.transcript-row.self  .tr-bubble { background: #1d4ed8; color: #fff; border-bottom-right-radius: 4px; }

.tr-time { font-size: 10px; color: #475569; padding: 0 4px; }
</style>
