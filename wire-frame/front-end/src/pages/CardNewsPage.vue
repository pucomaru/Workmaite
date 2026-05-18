<script setup>
import { ref, onMounted, computed, nextTick, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import api, { streamPost } from '../api'
import MeetingNav from '../components/MeetingNav.vue'
import AgentPanel from '../components/AgentPanel.vue'
import BaseModal from '../components/BaseModal.vue'
import { useMeetingsStore } from '../stores/meetings'
import { useChatHistory } from '../composables/useChatHistory'
import naonAvatar from '../assets/agents/naon.png'
import { renderMd } from '../composables/useMarkdown'

const route = useRoute()
const router = useRouter()
const meetingsStore = useMeetingsStore()
const meetingId = computed(() => Number(route.params.meetingId))

// ── 상태 ─────────────────────────────────────────────────────────
const sessions = ref([])
const cardNewsList = ref([])
const chatInput = ref('')
const loading = ref(false)

// 스타일 설정 팝업
const styleSettingsOpen = ref(false)
const styleSettings = ref({
  target_audience: null,
  session_ids: [],
  include_minutes: true,
  include_reports: true,
  include_agendas: true,
  include_todos: true,
  include_decisions: true,
  // 스타일 (널 = 선택안함, 나온이 판단)
  slide_count: null,
  first_card: null,
  tone: null,
  visual_style: null,
  // 공통 포함 요소
  include_cta: false,
  include_source_date: false,
  include_brand_logo: false,
  // 나온에게 직접 요청
  custom_request: '',
})

function resetStyleSettings() {
  Object.assign(styleSettings.value, {
    target_audience: null,
    session_ids: [],
    slide_count: null,
    first_card: null,
    tone: null,
    visual_style: null,
    include_cta: false,
    include_source_date: false,
    include_brand_logo: false,
    custom_request: '',
  })
}
const TARGET_OPTIONS = [
  { value: 'c_level',   label: '👔 C레벨',  desc: 'CEO·CFO·CSO — 5~7장, 결론 우선' },
  { value: 'executive', label: '🏢 임원',    desc: '본부장·이사 — 7~10장, 전략 중심' },
  { value: 'staff',     label: '👥 구성원',  desc: '팀장·실무자 — 6~10장, 공감·행동 유도' },
  { value: 'external',  label: '🌐 외부인',  desc: '고객·파트너 — 6~8장, 브랜드·CTA' },
]
const SOURCE_OPTIONS = [
  { key: 'include_minutes',   label: '📝 회의록' },
  { key: 'include_reports',   label: '📋 보고서' },
  { key: 'include_agendas',   label: '🗂 아젠다' },
  { key: 'include_todos',     label: '✅ To-do' },
]

const AUDIENCE_PRESETS = {
  c_level:   { slide_count: 6, first_card: 'conclusion', tone: 'concise',   visual_style: 'simple_graph',  include_brand_logo: false },
  executive: { slide_count: 8, first_card: 'issue_bg',   tone: 'logical',   visual_style: 'roadmap',       include_brand_logo: false },
  staff:     { slide_count: 7, first_card: 'hook',        tone: 'friendly',  visual_style: 'infographic',   include_brand_logo: false },
  external:  { slide_count: 7, first_card: 'visual_hook', tone: 'emotional', visual_style: 'image_brand',   include_brand_logo: true  },
}

const SLIDE_COUNT_OPTIONS = [5, 6, 7, 8, 10]

const FIRST_CARD_OPTIONS = [
  { value: 'conclusion',  label: '결론·수치 우선',     desc: '핵심 지표를 첫 장에 즉시 노출', badge: 'C레벨' },
  { value: 'issue_bg',    label: '이슈 배경+메시지',   desc: '발제 배경과 핵심 메시지로 시작', badge: '임원' },
  { value: 'hook',        label: '공감형 훅 카피',     desc: '"혹시 이런 경험 있으신가요?"',  badge: '구성원' },
  { value: 'visual_hook', label: '비주얼+궁금증 카피', desc: '강한 비주얼로 시선을 끄는 첫 장', badge: '외부인' },
]

const TONE_OPTIONS = [
  { value: 'concise',   label: '간결·단정·객관',     desc: '배경 최소화, 감성 카피 금지', badge: 'C레벨' },
  { value: 'logical',   label: '논리적·설득적',       desc: '리스크·협조사항 반드시 포함',  badge: '임원' },
  { value: 'friendly',  label: '친근·명확·동기부여',  desc: '구어체·실생활 예시 활용',       badge: '구성원' },
  { value: 'emotional', label: '감성적·신뢰·매력',    desc: '스토리텔링·브랜드 일관성',      badge: '외부인' },
]

const VISUAL_OPTIONS = [
  { value: 'simple_graph', label: '단순 그래프·아이콘',     desc: '복잡한 표 금지' },
  { value: 'roadmap',      label: '로드맵·비교표·플로우',   desc: '전략적 시각화' },
  { value: 'infographic',  label: '인포그래픽·이모지',       desc: '캐릭터·이미지 활용 가능' },
  { value: 'image_brand',  label: '고품질 이미지·브랜드컬러', desc: '일관된 브랜드 정체성' },
]

watch(() => styleSettings.value.target_audience, (val) => {
  const p = AUDIENCE_PRESETS[val]
  if (p) Object.assign(styleSettings.value, p)
})

function toggleStyleSession(id) {
  const idx = styleSettings.value.session_ids.indexOf(id)
  if (idx >= 0) styleSettings.value.session_ids.splice(idx, 1)
  else styleSettings.value.session_ids.push(id)
}

// 현재 설정 요약 레이블 (헤더 버튼 옆에 표시)
const settingsSummary = computed(() => {
  const t = TARGET_OPTIONS.find(o => o.value === styleSettings.value.target_audience)?.label
  const sCount = styleSettings.value.session_ids.length
  const parts = []
  if (t) parts.push(t)
  if (sCount) parts.push(`${sCount}개 차수`)
  return parts.length ? parts.join(' · ') : '나온이 판단'
})

// human-in-the-loop 상태 (LangGraph)
const proposingPlan = ref(false)
const currentPlan = ref(null)
const currentThreadId = ref(null)
const generating = ref(false)
const clarifyingAnswers = ref({})

// 우측 뷰: 'list' | 'plan' | 'card'
const rightView = ref('list')
const selectedCard = ref(null)

const chatArea = ref(null)
const agentPanelRef = ref(null)
const { messages, loadMessages, saveMessage, clearHistory } = useChatHistory('cardnews', meetingId.value)

async function handleSend(text) {
  chatInput.value = text
  await sendMessage()
}

onMounted(async () => {
  await meetingsStore.fetchMeeting(meetingId.value)
  await Promise.all([loadSessions(), loadCardNews()])
  await loadMessages()
})

async function loadSessions() {
  const { data } = await api.get(`/api/meetings/${meetingId.value}/sessions`)
  sessions.value = data.filter(s => s.status === 'ended')
}

async function loadCardNews() {
  const { data } = await api.get(`/api/meetings/${meetingId.value}/card-news`)
  cardNewsList.value = data
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

// ── 카드뉴스 생성 (스타일 설정 + 채팅 기반) ─────────────────────
async function requestPlan() {
  if (loading.value || proposingPlan.value) return
  proposingPlan.value = true
  currentPlan.value = null
  rightView.value = 'plan'

  const s = styleSettings.value
  const sessionIds = s.session_ids.length ? s.session_ids : sessions.value.map(x => x.id)

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
    const { data } = await api.post('/api/agent/naon/propose-plan', {
      meeting_id: meetingId.value,
      session_ids: sessionIds,
      chat_history: history,
      target_audience: s.target_audience,
      include_minutes: s.include_minutes,
      include_reports: s.include_reports,
      include_agendas: s.include_agendas,
      include_todos: s.include_todos,
      include_decisions: s.include_decisions,
      slide_count: s.slide_count,
      first_card: s.first_card,
      tone: s.tone,
      visual_style: s.visual_style,
      include_cta: s.include_cta,
      include_source_date: s.include_source_date,
      include_brand_logo: s.include_brand_logo,
      custom_request: s.custom_request || undefined,
    })
    if (data.status !== 'plan_ready') throw new Error(data.detail || '기획안 생성 실패')
    currentPlan.value = data.plan
    currentThreadId.value = data.thread_id
    clarifyingAnswers.value = {}
    const hasQ = data.plan.clarifying_questions?.length
    agentMsg.content = hasQ
      ? `기획안을 작성했습니다. 확인이 필요한 사항이 있습니다. 우측에서 답변해 주시면 더 정확한 결과를 드릴 수 있습니다.`
      : `기획안이 완성되었습니다! 우측에서 슬라이드 구성을 검토해 주세요.\n\n"${data.plan.title}"\n총 ${data.plan.slides?.length || 0}장 슬라이드\n\n마음에 들면 [생성 확정], 수정이 필요하면 [수정 요청]을 눌러 주세요.`
    saveMessage('agent', agentMsg.content)
  } catch {
    agentMsg.content = '기획안 작성 중 오류가 발생했습니다. 다시 시도해 주세요.'
    saveMessage('agent', agentMsg.content)
    rightView.value = 'list'
  } finally {
    proposingPlan.value = false
    scrollChat()
  }
}

// ── HITL 질문 답변 반영 후 재기획 ──────────────────────────────────
async function replanWithAnswers() {
  if (!currentThreadId.value) return
  generating.value = true
  const questions = currentPlan.value?.clarifying_questions || []
  const qa = questions.map((q, i) =>
    `Q: ${q.question}\nA: ${clarifyingAnswers.value[i] || '(미입력)'}`
  ).join('\n\n')
  const feedback = `다음 답변을 반영하여 기획안을 다시 작성해 주세요:\n\n${qa}`
  const agentMsg = { role: 'agent', content: '' }
  messages.value.push(agentMsg)
  await nextTick(); scrollChat()
  try {
    await api.post('/api/agent/naon/resume-plan', {
      thread_id: currentThreadId.value,
      meeting_id: meetingId.value,
      session_ids: styleSettings.value.session_ids.length
        ? styleSettings.value.session_ids
        : sessions.value.map(s => s.id),
      approved: false,
      feedback,
    })
    agentMsg.content = '답변을 반영하여 재기획 중입니다. [카드뉴스 생성] 버튼을 다시 눌러 주세요.'
    saveMessage('agent', agentMsg.content)
  } catch {
    agentMsg.content = '처리 중 오류가 발생했습니다.'
  } finally {
    currentPlan.value = null
    currentThreadId.value = null
    clarifyingAnswers.value = {}
    rightView.value = 'list'
    generating.value = false
    scrollChat()
  }
}

// ── 기획안 수정 요청 ─────────────────────────────────────────────
async function requestPlanRevision() {
  if (!currentThreadId.value) { rightView.value = 'list'; return }
  generating.value = true
  const agentMsg = { role: 'agent', content: '' }
  messages.value.push(agentMsg)
  await nextTick(); scrollChat()

  try {
    await api.post('/api/agent/naon/resume-plan', {
      thread_id: currentThreadId.value,
      meeting_id: meetingId.value,
      session_ids: styleSettings.value.session_ids.length
        ? styleSettings.value.session_ids
        : sessions.value.map(s => s.id),
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
    const { data } = await api.post('/api/agent/naon/resume-plan', {
      thread_id: currentThreadId.value,
      meeting_id: meetingId.value,
      session_ids: styleSettings.value.session_ids.length
        ? styleSettings.value.session_ids
        : sessions.value.map(s => s.id),
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
  <div class="page-wrap page-full-height">
    <MeetingNav />

    <div class="cardnews-body">
      <!-- ── 왼쪽: 나온 AgentPanel ─────────────────────────── -->
      <AgentPanel
        ref="agentPanelRef"
        :avatar="naonAvatar"
        name="나온"
        name-en="Naon"
        subtitle="카드뉴스 기획 Agent"
        :messages="messages"
        :loading="loading"
        greeting="안녕하세요! 카드뉴스 전문가 나온입니다. 🗞

대화를 통해 원하는 내용을 자유롭게 말씀해 주세요.
(강조할 내용, 빠뜨리면 안 될 항목, 톤앤매너 등 무엇이든!)

대상 독자·회의 차수·활용 자료는 좌측 상단의 [스타일설정]에서 선택하실 수 있습니다.
설정이 완료되면 아래 [카드뉴스 생성] 버튼을 눌러주세요!"
        placeholder="나온에게 커스텀 요청사항을 메시지로 보내세요..."
        accent-color="#f97316"
        accent-border="#fb923c"
        accent-bg="#fff7ed"
        bubble-gradient="linear-gradient(135deg,#fff7ed,#ffedd5)"
        bubble-color="#7c2d12"
        @send="handleSend"
        @clear="clearHistory"
      >
        <template #actions>
          <button class="ap-style-btn" @click="styleSettingsOpen = true" title="대상 독자, 회의 차수, 활용 자료 설정">
            ⚙ 스타일설정
          </button>
        </template>
        <template #footer-extra>
          <div style="padding: 0 16px 12px">
            <button
              class="btn btn-outline btn-sm plan-btn"
              :disabled="proposingPlan || generating || loading"
              @click="requestPlan"
              title="설정과 대화 내용을 바탕으로 카드뉴스 기획안을 생성합니다"
            >
              {{ proposingPlan ? '기획안 작성 중...' : '🗞 카드뉴스 생성' }}
            </button>
          </div>
        </template>
      </AgentPanel>

      <!-- ── 스타일설정 팝업 모달 ─────────────────────────────── -->
      <BaseModal v-model="styleSettingsOpen" width="460px">
        <template #title>⚙ 스타일 설정</template>

        <div class="ss-body">
              <!-- 1. 대상 독자 -->
              <div class="ss-section">
                <div class="ss-section-label">대상 독자 <span class="ss-hint">선택 시 관련 항목 자동 설정 / 다시 누르면 해제</span></div>
                <div class="ss-target-grid">
                  <button
                    v-for="opt in TARGET_OPTIONS"
                    :key="opt.value"
                    class="ss-target-btn"
                    :class="{ active: styleSettings.target_audience === opt.value }"
                    @click="styleSettings.target_audience = styleSettings.target_audience === opt.value ? null : opt.value"
                  >
                    <span class="ss-target-label">{{ opt.label }}</span>
                  </button>
                </div>
              </div>

              <!-- 2. 슬라이드 분량 -->
              <div class="ss-section">
                <div class="ss-section-label">분량</div>
                <div class="ss-count-row">
                  <button
                    v-for="n in SLIDE_COUNT_OPTIONS"
                    :key="n"
                    class="ss-count-btn"
                    :class="{ active: styleSettings.slide_count === n }"
                    @click="styleSettings.slide_count = styleSettings.slide_count === n ? null : n"
                  >{{ n }}장</button>
                </div>
              </div>

              <!-- 3. 언어·톤 -->
              <div class="ss-section">
                <div class="ss-section-label">언어·톤</div>
                <div class="ss-radio-grid">
                  <button
                    v-for="opt in TONE_OPTIONS"
                    :key="opt.value"
                    class="ss-radio-btn"
                    :class="{ active: styleSettings.tone === opt.value }"
                    @click="styleSettings.tone = styleSettings.tone === opt.value ? null : opt.value"
                  >
                    <span class="ss-radio-label">{{ opt.label }}</span>
                  </button>
                </div>
              </div>

              <!-- 4. 회의 차수 -->
              <div class="ss-section">
                <div class="ss-section-label">
                  회의 차수
                  <span class="ss-hint">미선택 시 전체 회의 활용</span>
                </div>
                <div class="ss-session-row">
                  <div v-if="!sessions.length" class="ss-empty">종료된 회의가 없습니다.</div>
                  <button
                    v-for="s in sessions"
                    :key="s.id"
                    class="ss-session-btn"
                    :class="{ active: styleSettings.session_ids.includes(s.id) }"
                    @click="toggleStyleSession(s.id)"
                  >
                    {{ s.session_number }}차<template v-if="s.title"> — {{ s.title }}</template>
                  </button>
                </div>
              </div>

              <!-- 7. 활용 자료 -->
              <div class="ss-section">
                <div class="ss-section-label">활용 자료 <span class="ss-hint">기획에 포함할 자료를 선택하세요</span></div>
                <div class="ss-source-row">
                  <label v-for="s in SOURCE_OPTIONS" :key="s.key" class="ss-source-opt">
                    <input type="checkbox" v-model="styleSettings[s.key]" />
                    <span>{{ s.label }}</span>
                  </label>
                </div>
              </div>

              <!-- 8. 공통 포함 요소 -->
              <div class="ss-section" style="border-bottom:none">
                <div class="ss-section-label">공통 포함 요소</div>
                <div class="ss-common-list">
                  <label class="ss-common-opt">
                    <input type="checkbox" v-model="styleSettings.include_cta" />
                    <div>
                      <span class="ss-common-label">마지막 장 CTA 포함</span>
                      <span class="ss-common-desc">행동 유도</span>
                    </div>
                  </label>
                  <label class="ss-common-opt">
                    <input type="checkbox" v-model="styleSettings.include_source_date" />
                    <div>
                      <span class="ss-common-label">출처·날짜 명시</span>
                      <span class="ss-common-desc">수치 데이터 신뢰도 확보</span>
                    </div>
                  </label>
                  <label class="ss-common-opt">
                    <input type="checkbox" v-model="styleSettings.include_brand_logo" />
                    <div>
                      <span class="ss-common-label">브랜드 로고 포함</span>
                      <span class="ss-common-desc">외부 공개·마케팅용 콘텐츠에 권장</span>
                    </div>
                  </label>
                </div>
              </div>

              <!-- 9. 나온에게 직접 요청 -->
              <div class="ss-section" style="border-bottom:none">
                <div class="ss-section-label">나온에게 직접 요청 <span class="ss-hint">자유롭게 원하는 방향을 적어주세요</span></div>
                <textarea
                  v-model="styleSettings.custom_request"
                  class="ss-custom-input"
                  placeholder="예: 3분기 실적 강조, 긍정적인 분위기로, 경쟁사 비교 슬라이드 포함..."
                  rows="3"
                />
              </div>
        </div>

        <template #footer>
          <button class="btn btn-ghost btn-sm" @click="resetStyleSettings">전체 초기화</button>
          <button class="btn btn-primary" @click="styleSettingsOpen = false">확인</button>
        </template>
      </BaseModal>

      <!-- ── 오른쪽: 기획안 / 카드뉴스 목록 ─────────────────── -->
      <div class="cardnews-right card">

        <!-- 공통 패널 헤더 -->
        <div class="right-panel-header">
          <button class="panel-tab" :class="{ active: rightView === 'list' }" @click="rightView = 'list'">
            목록
            <span v-if="cardNewsList.length" class="tab-badge">{{ cardNewsList.length }}</span>
          </button>
          <button v-if="rightView === 'plan'" class="panel-tab active">
            📋 기획안 검토
          </button>
          <button v-if="rightView === 'card' && selectedCard" class="panel-tab active" style="max-width:180px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">
            {{ selectedCard.title }}
          </button>
        </div>

        <!-- ● 기획안 검토 뷰 -->
        <template v-if="rightView === 'plan'">
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
                <span class="tag">{{ TARGET_OPTIONS.find(o=>o.value===currentPlan.target_audience)?.label || '👥 구성원' }}</span>
                <span class="tag">🎨 {{ currentPlan.tone }}</span>
              </div>
            </div>

            <!-- 나온의 HITL 확인 질문 -->
            <div v-if="currentPlan.clarifying_questions?.length" class="plan-questions">
              <div class="pq-header">💬 나온이 확인이 필요한 사항</div>
              <div v-for="(q, i) in currentPlan.clarifying_questions" :key="i" class="pq-item">
                <div class="pq-question">{{ q.question }}</div>
                <div v-if="q.options?.length" class="pq-opts">
                  <button
                    v-for="opt in q.options"
                    :key="opt"
                    class="pq-opt-btn"
                    :class="{ active: clarifyingAnswers[i] === opt }"
                    @click="clarifyingAnswers[i] = clarifyingAnswers[i] === opt ? undefined : opt"
                  >{{ opt }}</button>
                </div>
                <input v-else v-model="clarifyingAnswers[i]" class="pq-input" placeholder="답변을 입력하세요..." />
              </div>
              <button class="btn btn-primary btn-sm" style="margin-top:4px" @click="replanWithAnswers">
                답변 반영하여 재기획
              </button>
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
          <div class="card-list">
            <div v-if="!cardNewsList.length" class="empty-state">
              <p>📭 아직 생성된 카드뉴스가 없어요</p>
              <p style="font-size:13px;color:var(--text-muted)">나온과 대화 후 [카드뉴스 생성]을 눌러보세요</p>
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

</template>

<style scoped>
.cardnews-body { flex: 1; min-height: 0; display: flex; gap: 16px; overflow: hidden; }
.cardnews-right { flex: 1; min-height: 0; overflow: hidden; display: flex; flex-direction: column; }

/* 세션 참고 표시 (AgentPanel extra-header 슬롯 안) */
.session-ref { padding: 8px 16px 10px; border-bottom: 1px solid var(--border); }
.session-ref-chips { display: flex; flex-wrap: wrap; gap: 5px; margin-top: 5px; }
.session-ref-chip {
  font-size: 11px;
  color: var(--text-muted);
  background: #f1f5f9;
  border: 1px solid var(--border);
  border-radius: 99px;
  padding: 2px 8px;
}

/* ── AgentPanel 헤더 스타일설정 버튼 ── */
.ap-style-btn {
  font-size: 11px;
  font-weight: 600;
  padding: 4px 10px;
  border: 1.5px solid #fb923c;
  border-radius: 99px;
  background: #fff7ed;
  color: #c2410c;
  cursor: pointer;
  white-space: nowrap;
  transition: all .15s;
}
.ap-style-btn:hover { background: #ffedd5; border-color: #ea580c; }

/* ── 스타일설정 팝업 모달 ── */
.ss-body { flex: 1; overflow-y: auto; }

.ss-section {
  padding: 14px 20px;
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
}
.ss-section-label {
  font-size: 12px; font-weight: 700; color: var(--text);
  margin-bottom: 10px; display: flex; align-items: baseline; gap: 6px;
}
.ss-hint { font-size: 11px; font-weight: 400; color: var(--text-muted); }

/* 대상 독자 — 2×2 그리드 */
.ss-target-grid {
  display: grid; grid-template-columns: 1fr 1fr; gap: 7px;
}
.ss-target-btn {
  display: flex; flex-direction: column; align-items: flex-start; gap: 2px;
  padding: 8px 10px;
  border: 1.5px solid var(--border); border-radius: 10px;
  background: #f8fafc; cursor: pointer; text-align: left;
  transition: all .15s;
}
.ss-target-btn:hover { border-color: #fb923c; background: #fff7ed; }
.ss-target-btn.active { border-color: #ea580c; background: #ffedd5; }
.ss-target-label { font-size: 12px; font-weight: 700; color: var(--text); }
.ss-target-desc { font-size: 10px; color: var(--text-muted); line-height: 1.3; }

/* 슬라이드 분량 */
.ss-count-row { display: flex; gap: 6px; flex-wrap: wrap; }
.ss-count-btn {
  font-size: 13px; font-weight: 600; padding: 5px 14px;
  border: 1.5px solid var(--border); border-radius: 99px;
  background: #f8fafc; cursor: pointer; transition: all .15s; color: var(--text);
}
.ss-count-btn:hover { border-color: #fb923c; background: #fff7ed; }
.ss-count-btn.active { border-color: #ea580c; background: #ffedd5; color: #c2410c; }

/* 첫 장 구성 / 언어·톤 / 시각화 — 2×2 라디오 그리드 */
.ss-radio-grid {
  display: grid; grid-template-columns: 1fr 1fr; gap: 7px;
}
.ss-radio-btn {
  display: flex; flex-direction: column; align-items: flex-start; gap: 2px;
  padding: 8px 10px;
  border: 1.5px solid var(--border); border-radius: 10px;
  background: #f8fafc; cursor: pointer; text-align: left;
  transition: all .15s;
}
.ss-radio-btn:hover { border-color: #fb923c; background: #fff7ed; }
.ss-radio-btn.active { border-color: #ea580c; background: #ffedd5; }
.ss-radio-badge {
  font-size: 9px; font-weight: 700; color: #ea580c;
  background: #ffedd5; padding: 1px 5px; border-radius: 4px;
  letter-spacing: .3px;
}
.ss-radio-label { font-size: 12px; font-weight: 700; color: var(--text); }
.ss-radio-desc { font-size: 10px; color: var(--text-muted); line-height: 1.3; }

/* 회의 차수 */
.ss-session-row { display: flex; flex-wrap: wrap; gap: 6px; }
.ss-empty { font-size: 12px; color: var(--text-muted); }
.ss-session-btn {
  font-size: 12px; padding: 4px 12px;
  border: 1.5px solid var(--border); border-radius: 99px;
  background: #f8fafc; cursor: pointer; transition: all .15s;
  color: var(--text);
}
.ss-session-btn:hover { border-color: #fb923c; background: #fff7ed; }
.ss-session-btn.active { border-color: #ea580c; background: #ffedd5; color: #c2410c; font-weight: 600; }

/* 활용 자료 */
.ss-source-row { display: flex; flex-wrap: wrap; gap: 6px; }
.ss-source-opt {
  display: flex; align-items: center; gap: 4px;
  font-size: 12px; color: var(--text);
  background: #f8fafc; border: 1px solid var(--border);
  border-radius: 99px; padding: 4px 10px;
  cursor: pointer; user-select: none; transition: all .15s;
}
.ss-source-opt:has(input:checked) { background: #ffedd5; border-color: #fb923c; color: #c2410c; }
.ss-source-opt input { width: 12px; height: 12px; accent-color: #ea580c; }

/* 공통 포함 요소 */
.ss-common-list { display: flex; flex-direction: column; gap: 10px; }
.ss-common-opt {
  display: flex; align-items: flex-start; gap: 8px;
  cursor: pointer;
}
.ss-common-opt input { margin-top: 2px; accent-color: #ea580c; flex-shrink: 0; }
.ss-common-label { display: block; font-size: 12px; font-weight: 600; color: var(--text); }
.ss-common-desc { display: block; font-size: 11px; color: var(--text-muted); margin-top: 1px; }

/* 나온에게 직접 요청 */
.ss-custom-input {
  width: 100%; box-sizing: border-box;
  padding: 9px 12px;
  font-size: 12px; line-height: 1.6; color: var(--text);
  background: #f8fafc; border: 1.5px solid var(--border);
  border-radius: 10px; resize: vertical;
  font-family: inherit;
  transition: border-color .15s;
}
.ss-custom-input:focus { outline: none; border-color: #ea580c; background: #fff; }

/* 나온 HITL 확인 질문 */
.plan-questions {
  margin: 12px 16px 0;
  background: #fff7ed; border: 1.5px solid #fdba74;
  border-radius: 12px; padding: 14px;
}
.pq-header { font-size: 12px; font-weight: 700; color: #c2410c; margin-bottom: 12px; }
.pq-item { margin-bottom: 12px; }
.pq-item:last-of-type { margin-bottom: 8px; }
.pq-question { font-size: 13px; font-weight: 600; color: var(--text); margin-bottom: 6px; }
.pq-opts { display: flex; flex-wrap: wrap; gap: 6px; }
.pq-opt-btn {
  font-size: 12px; padding: 4px 12px;
  border: 1.5px solid #fdba74; border-radius: 99px;
  background: #fff; cursor: pointer; color: #c2410c; transition: all .15s;
}
.pq-opt-btn:hover { background: #ffedd5; }
.pq-opt-btn.active { background: #ea580c; color: #fff; border-color: #ea580c; }
.pq-input {
  width: 100%; box-sizing: border-box;
  padding: 7px 10px; font-size: 12px;
  border: 1.5px solid #fdba74; border-radius: 8px;
  background: #fff; color: var(--text); font-family: inherit;
}
.pq-input:focus { outline: none; border-color: #ea580c; }

.section-label { font-size: 12px; font-weight: 600; color: var(--text-muted); }
.plan-btn { width: 100%; font-size: 13px; }

/* 타이핑 인디케이터 (AgentPanel 내장) */
.typing-indicator { display: flex; align-items: center; gap: 4px; padding: 12px 16px; }
.typing-indicator span { width: 7px; height: 7px; background: rgba(255,255,255,.7); border-radius: 50%; animation: bounce 1.2s infinite; }
.typing-indicator span:nth-child(2) { animation-delay: .2s; }
.typing-indicator span:nth-child(3) { animation-delay: .4s; }
@keyframes bounce { 0%,60%,100% { transform: translateY(0); } 30% { transform: translateY(-6px); } }

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

