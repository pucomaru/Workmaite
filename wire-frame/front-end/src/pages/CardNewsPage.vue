<script setup>
import { ref, onMounted, computed, nextTick } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import api from '../api'
import { streamPost } from '../api'
import MeetingNav from '../components/MeetingNav.vue'
import { useMeetingsStore } from '../stores/meetings'
import { useChatHistory } from '../composables/useChatHistory'
import naonAvatar from '../assets/agents/naon.png'

const route = useRoute()
const router = useRouter()
const meetingsStore = useMeetingsStore()
const meetingId = computed(() => Number(route.params.meetingId))

// ── 상태 ─────────────────────────────────────────────────────────
const sessions = ref([])
const cardNewsList = ref([])
const selectedSessions = ref([])
const chatInput = ref('')
const loading = ref(false)

// human-in-the-loop 상태 (LangGraph)
const proposingPlan = ref(false)        // 기획안 요청 중 (propose_node 실행 중)
const currentPlan = ref(null)           // interrupt() 로 반환된 기획안 (승인 대기)
const currentThreadId = ref(null)       // LangGraph thread_id (체크포인터 키)
const generating = ref(false)           // generate_node 실행 중 (resume 후)

// 우측 뷰: 'list' | 'plan' | 'card'
const rightView = ref('list')
const selectedCard = ref(null)

const chatArea = ref(null)
const { messages, loadMessages, saveMessage, clearHistory } = useChatHistory('cardnews', meetingId.value)

onMounted(async () => {
  await meetingsStore.fetchMeeting(meetingId.value)
  await Promise.all([loadSessions(), loadCardNews()])
  await loadMessages()
  if (!messages.value.length) {
    const greeting = '안녕하세요! 카드뉴스 기획 전문가 나온입니다. 📰\n\n어떤 카드뉴스를 만들고 싶으신가요? 먼저 아래 질문에 답해주시면 최적의 기획안을 제안해 드릴게요.\n\n① 이 카드뉴스를 어디에 사용하실 건가요? (임원 보고 / 팀 공유 / 사내 SNS 등)\n② 주요 독자는 누구인가요?\n③ 특별히 강조하고 싶은 내용이 있으신가요?'
    messages.value.push({ role: 'agent', content: greeting })
    saveMessage('agent', greeting)
  }
})

async function loadSessions() {
  const { data } = await api.get(`/api/meetings/${meetingId.value}/sessions`)
  sessions.value = data.filter(s => s.status === 'ended')
}

async function loadCardNews() {
  const { data } = await api.get(`/api/meetings/${meetingId.value}/card-news`)
  cardNewsList.value = data
}

function toggleSession(id) {
  if (selectedSessions.value.includes(id)) {
    selectedSessions.value = selectedSessions.value.filter(s => s !== id)
  } else {
    selectedSessions.value.push(id)
  }
}

// ── 나온과 대화 ───────────────────────────────────────────────────
async function sendMessage() {
  if (!chatInput.value.trim() || loading.value) return
  const text = chatInput.value.trim()
  messages.value.push({ role: 'user', content: text })
  saveMessage('user', text)
  chatInput.value = ''
  const agentMsg = { role: 'agent', content: '' }
  messages.value.push(agentMsg)
  loading.value = true
  await nextTick(); scrollChat()

  const history = messages.value.slice(0, -1).map(m => ({
    role: m.role === 'user' ? 'user' : 'assistant',
    content: m.content,
  }))
  await streamPost(
    '/api/agent/naon/chat',
    { meeting_id: meetingId.value, message: text, chat_history: history },
    (chunk) => { agentMsg.content += chunk; scrollChat() },
    () => { loading.value = false; saveMessage('agent', agentMsg.content) },
  )
}

// ── 기획안 요청 (human-in-the-loop) ─────────────────────────────
async function requestPlan() {
  if (!selectedSessions.value.length) {
    const notice = { role: 'agent', content: '⚠️ 기획안을 작성하려면 먼저 좌측에서 회의 차수를 하나 이상 선택해 주세요.' }
    messages.value.push(notice)
    return
  }
  proposingPlan.value = true
  currentPlan.value = null
  rightView.value = 'plan'

  const userMsg = '지금까지 논의한 내용으로 카드뉴스 기획안을 작성해 주세요.'
  messages.value.push({ role: 'user', content: userMsg })
  saveMessage('user', userMsg)
  const agentMsg = { role: 'agent', content: '기획안을 작성하고 있습니다. 잠시만 기다려 주세요...' }
  messages.value.push(agentMsg)
  await nextTick(); scrollChat()

  const history = messages.value.slice(0, -2).map(m => ({
    role: m.role === 'user' ? 'user' : 'assistant',
    content: m.content,
  }))

  try {
    // [LangGraph HITL Step 1]
    // propose_node 실행 → interrupt() 에서 그래프 일시 정지
    // thread_id 로 checkpointer 에 상태 보존
    const { data } = await api.post('/api/agent/naon/propose-plan', {
      meeting_id: meetingId.value,
      session_ids: selectedSessions.value,
      chat_history: history,
    })
    if (data.status !== 'plan_ready') throw new Error(data.detail || '기획안 생성 실패')
    currentPlan.value = data.plan
    currentThreadId.value = data.thread_id   // 그래프 재개 시 필요
    agentMsg.content = `기획안이 완성되었습니다! 우측에서 슬라이드 구성을 검토해 주세요.\n\n"${data.plan.title}"\n총 ${data.plan.slides?.length || 0}장 슬라이드\n\n마음에 들면 [생성 확정], 수정이 필요하면 [수정 요청]을 눌러 주세요.`
    saveMessage('agent', agentMsg.content)
  } catch (e) {
    agentMsg.content = '기획안 작성 중 오류가 발생했습니다. 다시 시도해 주세요.'
    saveMessage('agent', agentMsg.content)
    rightView.value = 'list'
  } finally {
    proposingPlan.value = false
    scrollChat()
  }
}

// ── 기획안 수정 요청 → LangGraph 그래프 거부 후 대화 복귀 ─────────
async function requestPlanRevision() {
  if (!currentThreadId.value) { rightView.value = 'list'; return }
  generating.value = true
  const agentMsg = { role: 'agent', content: '' }
  messages.value.push(agentMsg)
  await nextTick(); scrollChat()

  try {
    // [LangGraph HITL] Command(resume={approved: false}) → 그래프 종료
    await api.post('/api/agent/naon/resume-plan', {
      thread_id: currentThreadId.value,
      meeting_id: meetingId.value,
      session_ids: selectedSessions.value,
      approved: false,
      feedback: '기획안을 수정해 주세요.',
    })
    agentMsg.content = '기획안을 거부했습니다. 어떤 부분을 바꿀지 알려주시면 새 기획안을 드리겠습니다.'
    saveMessage('agent', agentMsg.content)
  } catch {
    agentMsg.content = '처리 중 오류가 발생했습니다.'
  } finally {
    currentPlan.value = null
    currentThreadId.value = null
    rightView.value = 'list'
    generating.value = false
    scrollChat()
  }
}

// ── 기획안 확정 → LangGraph generate_node 실행 ────────────────────
async function confirmAndGenerate() {
  if (!currentPlan.value || !currentThreadId.value) return
  generating.value = true

  const agentMsg = { role: 'agent', content: '기획안을 승인했습니다. 회의록 내용으로 슬라이드를 채우고 있습니다...' }
  messages.value.push(agentMsg)
  await nextTick(); scrollChat()

  try {
    // [LangGraph HITL Step 2]
    // Command(resume={approved: true}) → generate_node 실행
    const { data } = await api.post('/api/agent/naon/resume-plan', {
      thread_id: currentThreadId.value,
      meeting_id: meetingId.value,
      session_ids: selectedSessions.value,
      approved: true,
    })
    if (data.status !== 'done') throw new Error('생성 실패')
    agentMsg.content = `카드뉴스 "${data.card_news?.title}" 생성 완료! 우측에서 확인하세요. 🎉`
    saveMessage('agent', agentMsg.content)
    currentPlan.value = null
    currentThreadId.value = null
    await loadCardNews()
    rightView.value = 'list'
  } catch {
    agentMsg.content = '카드뉴스 생성 중 오류가 발생했습니다.'
    saveMessage('agent', agentMsg.content)
  } finally {
    generating.value = false
    scrollChat()
  }
}

const isAdmin = computed(() => meetingsStore.myRole === 'admin')

function viewCard(card) {
  selectedCard.value = card
  rightView.value = 'card'
}

function formatDate(d) {
  if (!d) return ''
  return new Date(d).toLocaleDateString('ko-KR')
}

function onKeydown(e) {
  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage() }
}

async function deleteCard(card, e) {
  e.stopPropagation()
  if (!confirm(`"${card.title || '카드뉴스'}" 를 삭제하시겠습니까?`)) return
  try {
    await api.delete(`/api/card-news/${card.id}`)
    cardNewsList.value = cardNewsList.value.filter(c => c.id !== card.id)
    if (selectedCard.value?.id === card.id) {
      selectedCard.value = null
      rightView.value = 'list'
    }
  } catch {
    alert('삭제 중 오류가 발생했습니다.')
  }
}

function scrollChat() {
  nextTick(() => {
    if (chatArea.value) chatArea.value.scrollTop = chatArea.value.scrollHeight
  })
}

const SLIDE_COLORS = {
  cover: '#1e3a5f', context: '#1a4731', content: '#2d3748',
  decision: '#3b1f6e', action: '#7c2d12', closing: '#1e3a5f',
}
function slideColor(type) {
  return SLIDE_COLORS[type] || '#2d3748'
}
</script>

<template>
  <div class="page-wrap">
    <MeetingNav />

    <div class="two-col" style="flex:1;min-height:0">
      <!-- ── 왼쪽: 나온 상담 채팅 ────────────────────────────── -->
      <div class="col-panel card chat-col">
        <!-- 헤더 -->
        <div class="card-header">
          <div style="display:flex;align-items:center;gap:10px">
            <img :src="naonAvatar" class="agent-header-avatar" alt="나온" />
            <div>
              <div style="font-weight:700;font-size:14px">나온 (Naon)</div>
              <div style="font-size:11px;color:var(--text-muted)">카드뉴스 기획 Agent</div>
            </div>
          </div>
          <button class="btn btn-ghost btn-sm" style="color:var(--text-muted)" @click="clearHistory" title="대화 초기화">🗑</button>
        </div>

        <!-- 회의 차수 선택 -->
        <div class="session-selector">
          <div class="section-label">회의 차수 선택 <span style="color:var(--text-muted);font-weight:400">(기획안에 반영될 회의록)</span></div>
          <div style="display:flex;flex-wrap:wrap;gap:6px;margin-top:6px">
            <div v-if="!sessions.length" style="font-size:13px;color:var(--text-muted)">종료된 회의가 없습니다.</div>
            <button
              v-for="s in sessions"
              :key="s.id"
              class="btn btn-sm"
              :class="selectedSessions.includes(s.id) ? 'btn-primary' : 'btn-outline'"
              @click="toggleSession(s.id)"
            >
              {{ s.session_number }}차 {{ s.title || '' }}
            </button>
          </div>
        </div>

        <!-- 채팅 영역 -->
        <div ref="chatArea" class="chat-messages">
          <div v-for="(msg, i) in messages" :key="i" class="chat-msg-row fade-in" :class="msg.role">
            <div v-if="msg.role === 'agent'" class="chat-agent-label">
              <img :src="naonAvatar" class="chat-avatar-sm" alt="나온" />
              나온
            </div>
            <div class="chat-bubble" :class="msg.role" style="white-space:pre-wrap">{{ msg.content }}</div>
          </div>
          <div v-if="loading" class="chat-msg-row agent">
            <div class="chat-agent-label">
              <img :src="naonAvatar" class="chat-avatar-sm" alt="나온" />
              나온
            </div>
            <div class="chat-bubble agent typing-indicator"><span></span><span></span><span></span></div>
          </div>
        </div>

        <!-- 입력 + 기획안 요청 버튼 -->
        <div class="chat-footer">
          <!-- 기획안 요청 버튼 -->
          <button
            class="btn btn-outline btn-sm plan-btn"
            :disabled="proposingPlan || generating || loading"
            @click="requestPlan"
            title="지금까지 나눈 대화와 선택한 회의 차수를 기반으로 기획안을 작성합니다"
          >
            {{ proposingPlan ? '기획안 작성 중...' : '📋 기획안 요청' }}
          </button>
          <div class="chat-input-area">
            <textarea
              v-model="chatInput"
              class="chat-input"
              placeholder="나온에게 메시지를 보내세요..."
              rows="1"
              @keydown="onKeydown"
            />
            <button class="btn btn-primary btn-sm" :disabled="loading || !chatInput.trim()" @click="sendMessage">전송</button>
          </div>
        </div>
      </div>

      <!-- ── 오른쪽: 기획안 / 카드뉴스 목록 ─────────────────── -->
      <div class="col-panel card right-col">

        <!-- ● 기획안 검토 뷰 -->
        <template v-if="rightView === 'plan'">
          <div class="card-header">
            <span style="font-weight:600">📋 기획안 검토</span>
            <button class="btn btn-ghost btn-sm" @click="rightView = 'list'">목록으로</button>
          </div>

          <div v-if="proposingPlan" class="loading-state">
            <div class="spinner" />
            <p>기획안을 작성하고 있습니다...</p>
          </div>

          <template v-else-if="currentPlan">
            <!-- 기획안 메타 정보 -->
            <div class="plan-meta">
              <div class="plan-title">{{ currentPlan.title }}</div>
              <div class="plan-tags">
                <span class="tag">🎯 {{ currentPlan.purpose }}</span>
                <span class="tag">👥 {{ currentPlan.target }}</span>
                <span class="tag">🎨 {{ currentPlan.tone }}</span>
              </div>
            </div>

            <!-- 슬라이드 목록 (모바일 카드 스타일) -->
            <div class="plan-slides">
              <div
                v-for="slide in currentPlan.slides"
                :key="slide.slide_no"
                class="plan-slide-card"
                :style="{ background: slideColor(slide.type) }"
              >
                <div class="ps-meta">
                  <span class="ps-no">{{ slide.slide_no }}</span>
                  <span class="ps-type">{{ slide.emoji }} {{ slide.type }}</span>
                </div>
                <div class="ps-headline">{{ slide.headline }}</div>
                <div class="ps-body">{{ slide.body }}</div>
                <div v-if="slide.visual_hint" class="ps-hint">🖼 {{ slide.visual_hint }}</div>
              </div>
            </div>

            <!-- 확정 / 수정 버튼 -->
            <div class="plan-actions">
              <button class="btn btn-outline btn-sm" @click="requestPlanRevision">수정 요청</button>
              <button
                class="btn btn-primary"
                :disabled="generating"
                @click="confirmAndGenerate"
              >
                {{ generating ? '생성 중...' : '✅ 이 기획으로 생성하기' }}
              </button>
            </div>
          </template>
        </template>

        <!-- ● 카드뉴스 상세 뷰 -->
        <template v-else-if="rightView === 'card' && selectedCard">
          <div class="card-header">
            <div>
              <div style="font-weight:600;font-size:14px">{{ selectedCard.title }}</div>
              <div style="font-size:11px;color:var(--text-muted)">{{ formatDate(selectedCard.created_at) }}</div>
            </div>
            <button class="btn btn-ghost btn-sm" @click="rightView = 'list'">← 목록</button>
          </div>

          <div class="card-slides-view">
            <div
              v-for="slide in selectedCard.content?.slides"
              :key="slide.slide_no"
              class="mobile-card"
              :style="{ background: slide.bg_color || slideColor(slide.type) }"
            >
              <div class="mc-number">{{ slide.slide_no }} / {{ selectedCard.content.slides.length }}</div>
              <div class="mc-emoji">{{ slide.emoji || '' }}</div>
              <div class="mc-headline">{{ slide.headline }}</div>
              <div class="mc-body">{{ slide.body }}</div>
              <div v-if="slide.visual_hint" class="mc-hint">🖼 {{ slide.visual_hint }}</div>
            </div>
          </div>
        </template>

        <!-- ● 생성된 카드뉴스 목록 -->
        <template v-else>
          <div class="card-header">
            <span style="font-weight:600">생성된 카드뉴스 ({{ cardNewsList.length }})</span>
          </div>

          <div class="card-list">
            <div v-if="!cardNewsList.length" class="empty-state">
              <p>📭 아직 생성된 카드뉴스가 없습니다.</p>
              <p style="font-size:13px;color:var(--text-muted)">나온과 대화 후 [기획안 요청]을 눌러보세요.</p>
            </div>

            <div
              v-for="card in cardNewsList"
              :key="card.id"
              class="cni-item fade-in"
              @click="viewCard(card)"
            >
              <div class="cni-preview" :style="{ background: slideColor(card.content?.slides?.[0]?.type || 'cover') }">
                <div class="cni-prev-no">{{ card.content?.slides?.length || 0 }}장</div>
                <div class="cni-prev-title">{{ card.content?.slides?.[0]?.headline || card.title }}</div>
              </div>
              <div class="cni-info">
                <div class="cni-title">{{ card.title || '카드뉴스' }}</div>
                <div class="cni-meta">
                  <span>{{ card.content?.slides?.length || 0 }}장 슬라이드</span>
                  <span>{{ formatDate(card.created_at) }}</span>
                </div>
                <div v-if="card.content?.purpose" class="cni-purpose">{{ card.content.purpose }}</div>
              </div>
              <button
                v-if="isAdmin"
                class="cni-del-btn"
                title="삭제"
                @click="deleteCard(card, $event)"
              >✕</button>
            </div>
          </div>
        </template>
      </div>
    </div>
  </div>

  <!-- 플로팅 버튼: 계속 진행 (관리자만) -->
  <div v-if="isAdmin" class="fab-group">
    <button class="fab fab-primary" @click="router.push(`/meetings/${meetingId}/sessions`)" title="다음 회의 세션으로 이동">
      ▶ 계속 진행
    </button>
  </div>
</template>

<style scoped>
.page-wrap { display: flex; flex-direction: column; height: calc(100vh - var(--header-h) - 40px); }

/* ── 채팅 열 ── */
.chat-col { display: flex; flex-direction: column; }
.session-selector { padding: 10px 16px; border-bottom: 1px solid var(--border); }
.section-label { font-size: 12px; font-weight: 600; color: var(--text-muted); }
.chat-messages { flex: 1; overflow-y: auto; padding: 12px 16px; display: flex; flex-direction: column; gap: 8px; }
.chat-footer { padding: 10px 12px; border-top: 1px solid var(--border); display: flex; flex-direction: column; gap: 8px; }
.plan-btn { width: 100%; font-size: 13px; }

/* 타이핑 인디케이터 */
.typing-indicator { display: flex; align-items: center; gap: 4px; padding: 12px 16px; }
.typing-indicator span { width: 7px; height: 7px; background: rgba(255,255,255,.7); border-radius: 50%; animation: bounce 1.2s infinite; }
.typing-indicator span:nth-child(2) { animation-delay: .2s; }
.typing-indicator span:nth-child(3) { animation-delay: .4s; }
@keyframes bounce { 0%,60%,100% { transform: translateY(0); } 30% { transform: translateY(-6px); } }

/* ── 오른쪽 열 ── */
.right-col { display: flex; flex-direction: column; }

/* 기획안 */
.plan-meta { padding: 16px; border-bottom: 1px solid var(--border); }
.plan-title { font-size: 18px; font-weight: 700; margin-bottom: 8px; }
.plan-tags { display: flex; flex-wrap: wrap; gap: 6px; }
.tag { font-size: 12px; background: #f1f5f9; padding: 3px 8px; border-radius: 12px; color: #475569; }
.plan-slides { flex: 1; overflow-y: auto; padding: 12px 16px; display: flex; flex-direction: column; gap: 10px; }
.plan-slide-card { padding: 16px; border-radius: 10px; color: #fff; }
.ps-meta { display: flex; justify-content: space-between; margin-bottom: 6px; font-size: 11px; opacity: .75; }
.ps-no { font-weight: 700; }
.ps-type { text-transform: uppercase; letter-spacing: .5px; }
.ps-headline { font-size: 15px; font-weight: 700; margin-bottom: 6px; line-height: 1.3; }
.ps-body { font-size: 12px; opacity: .85; line-height: 1.6; margin-bottom: 6px; }
.ps-hint { font-size: 11px; opacity: .65; border-top: 1px solid rgba(255,255,255,.2); padding-top: 6px; margin-top: 4px; }
.plan-actions { padding: 12px 16px; border-top: 1px solid var(--border); display: flex; gap: 8px; justify-content: flex-end; }

/* 카드뉴스 상세 (모바일 카드 스타일) */
.card-slides-view { flex: 1; overflow-y: auto; padding: 16px; display: flex; flex-direction: column; gap: 12px; }
.mobile-card {
  border-radius: 12px; padding: 24px 20px; color: #fff;
  min-height: 200px; display: flex; flex-direction: column;
  box-shadow: 0 4px 12px rgba(0,0,0,.15);
}
.mc-number { font-size: 11px; opacity: .6; margin-bottom: 8px; align-self: flex-end; }
.mc-emoji { font-size: 28px; margin-bottom: 10px; }
.mc-headline { font-size: 20px; font-weight: 800; line-height: 1.25; margin-bottom: 12px; }
.mc-body { font-size: 13px; opacity: .9; line-height: 1.7; flex: 1; }
.mc-hint { font-size: 11px; opacity: .55; border-top: 1px solid rgba(255,255,255,.2); padding-top: 8px; margin-top: 10px; }

/* 카드뉴스 목록 */
.card-list { flex: 1; overflow-y: auto; padding: 12px 16px; display: flex; flex-direction: column; gap: 10px; }
.cni-item { display: flex; gap: 12px; border: 1px solid var(--border); border-radius: 10px; overflow: hidden; cursor: pointer; transition: box-shadow .15s; position: relative; align-items: stretch; }
.cni-item:hover { box-shadow: 0 2px 8px rgba(0,0,0,.08); }
.cni-del-btn { position: absolute; top: 6px; right: 6px; background: rgba(239,68,68,.1); border: 1px solid rgba(239,68,68,.25); color: #ef4444; width: 20px; height: 20px; border-radius: 50%; font-size: 10px; cursor: pointer; display: flex; align-items: center; justify-content: center; opacity: 0; transition: opacity .15s; }
.cni-item:hover .cni-del-btn { opacity: 1; }
.fab-group { position: fixed; bottom: 24px; right: 24px; display: flex; flex-direction: column; align-items: flex-end; gap: 10px; z-index: 50; }
.fab { display: flex; align-items: center; gap: 6px; padding: 10px 18px; border-radius: 24px; font-size: 13px; font-weight: 600; cursor: pointer; box-shadow: 0 4px 12px rgba(0,0,0,.15); border: none; transition: all .15s; white-space: nowrap; }
.fab:hover { transform: translateY(-1px); box-shadow: 0 6px 16px rgba(0,0,0,.2); }
.fab-primary { background: var(--primary); color: #fff; }
.cni-preview { width: 80px; min-height: 80px; display: flex; flex-direction: column; justify-content: center; align-items: center; padding: 8px; text-align: center; flex-shrink: 0; }
.cni-prev-no { font-size: 11px; color: rgba(255,255,255,.7); }
.cni-prev-title { font-size: 11px; font-weight: 700; color: #fff; margin-top: 4px; line-height: 1.3; }
.cni-info { padding: 12px; display: flex; flex-direction: column; gap: 4px; justify-content: center; }
.cni-title { font-size: 14px; font-weight: 600; }
.cni-meta { display: flex; gap: 12px; font-size: 11px; color: var(--text-muted); }
.cni-purpose { font-size: 12px; color: var(--text-muted); }

/* 로딩 */
.loading-state { flex: 1; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 12px; color: var(--text-muted); }
.spinner { width: 32px; height: 32px; border: 3px solid var(--border); border-top-color: var(--primary); border-radius: 50%; animation: spin .8s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }
</style>

const selectedSessions = ref([])
const input = ref('')
const loading = ref(false)
const generating = ref(false)
const selectedCard = ref(null)

const { messages, loadMessages, saveMessage, clearHistory } = useChatHistory('cardnews', meetingId.value)

onMounted(async () => {
  await meetingsStore.fetchMeeting(meetingId.value)
  await loadSessions()
  await loadCardNews()
  messages.value.push({ role: 'agent', content: '안녕하세요! 카드뉴스 생성 AI 나온입니다.\n회의 차수를 선택하고 강조할 내용을 알려주시면 카드뉴스를 생성해드립니다.' })
})

async function loadSessions() {
  const { data } = await api.get(`/api/meetings/${meetingId.value}/sessions`)
  sessions.value = data.filter(s => s.status === 'ended')
}

async function loadCardNews() {
  const { data } = await api.get(`/api/meetings/${meetingId.value}/card-news`)
  cardNewsList.value = data
}

function toggleSession(id) {
  if (selectedSessions.value.includes(id)) {
    selectedSessions.value = selectedSessions.value.filter(s => s !== id)
  } else {
    selectedSessions.value.push(id)
  }
}

async function generateCardNews() {
  if (!selectedSessions.value.length) {
    alert('회의 차수를 선택하세요.')
    return
  }
  generating.value = true
  const userMsg = `${selectedSessions.value.length}개 회의 차수 카드뉴스 생성 요청`
  messages.value.push({ role: 'user', content: userMsg })
  saveMessage('user', userMsg)
  const agentMsg = { role: 'agent', content: '카드뉴스를 생성하고 있습니다...' }
  messages.value.push(agentMsg)

  try {
    const { data } = await api.post('/api/agent/naon/generate-card-news', {
      meeting_id: meetingId.value,
      session_ids: selectedSessions.value,
      emphasis_points: input.value,
    })
    agentMsg.content = `카드뉴스 "${data.content.title}"가 생성되었습니다! 우측에서 확인하세요.`
    saveMessage('agent', agentMsg.content)
    await loadCardNews()
  } catch {
    agentMsg.content = '카드뉴스 생성 중 오류가 발생했습니다.'
    saveMessage('agent', agentMsg.content)
  } finally {
    generating.value = false
  }
}

async function sendMessage() {
  if (!input.value.trim() || loading.value) return
  const text = input.value.trim()
  messages.value.push({ role: 'user', content: text })
  saveMessage('user', text)
  input.value = ''
  const agentMsg = { role: 'agent', content: '' }
  messages.value.push(agentMsg)
  loading.value = true

  const history = messages.value.slice(0,-1).map(m => ({ role: m.role === 'user' ? 'user' : 'assistant', content: m.content }))
  await streamPost(
    '/api/agent/naon/chat',
    { meeting_id: meetingId.value, message: text, chat_history: history },
    (chunk) => { agentMsg.content += chunk },
    () => { loading.value = false; saveMessage('agent', agentMsg.content) }
  )
}

