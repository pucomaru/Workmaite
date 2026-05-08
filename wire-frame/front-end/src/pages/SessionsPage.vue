<script setup>
import { ref, onMounted, computed, nextTick } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import api from '../api'
import { streamPost } from '../api'
import MeetingNav from '../components/MeetingNav.vue'
import AgentPanel from '../components/AgentPanel.vue'
import BaseModal from '../components/BaseModal.vue'
import { useMeetingsStore } from '../stores/meetings'
import { useChatHistory } from '../composables/useChatHistory'
import araAvatar from '../assets/agents/ara.png'
import { marked } from 'marked'
import { useSTT } from '../composables/useSTT'

const renderMd = (text) => marked.parse(text || '', { breaks: true })

const route = useRoute()
const router = useRouter()
const meetingsStore = useMeetingsStore()
const meetingId = computed(() => Number(route.params.meetingId))
const role = computed(() => meetingsStore.myRole)

const sessions = ref([])
const agendas = ref([])

const AGENDA_TYPE_LABEL = { report: '보고', discussion: '토의', decision: '결정', info: '정보공유' }
const AGENDA_TYPE_COLOR = { report: '#3b82f6', discussion: '#8b5cf6', decision: '#ef4444', info: '#6b7280' }

const showMinutesModal = ref(false)
const selectedSession = ref(null)
const minutes = ref(null)

const editingId = ref(null)
const editForm = ref({ title: '', scheduled_at: '', location: '', agenda_ids: [] })
const saving = ref(false)
const deleting = ref(null)
const ending = ref(null)

const showCreateModal = ref(false)
const createForm = ref({ title: '', scheduled_at: '', location: '', agenda_ids: [] })
const creating = ref(false)

// ── 아라 ──────────────────────────────────────
const araInput = ref('')
const araLoading = ref(false)
const messagesEl = ref(null)
const { messages: araMessages, loadMessages, saveMessage, clearHistory } = useChatHistory('sessions', meetingId.value)

// 진행 패널 state
const activeSession = ref(null)
const activeTab = ref('transcript')
const transcriptLang = ref('ko')
const scriptLang = ref('ko')
const recordingState = ref('idle')   // 'idle' | 'recording' | 'paused'
const transcriptLines = ref([])
const scriptLines = ref([])
const generatedMinutes = ref(null)
const showMinutesTab = ref(false)
const generatingMinutes = ref(false)
const showPopover = ref(null)
const micSensitivity = ref(70)
const noiseReduction = ref(true)
const transcriptAreaRef = ref(null)
// 대화기록 AI 요약
const transcriptSummary = ref('')
const summarizingTranscript = ref(false)
const showSummary = ref(false)
// 회의록 편집
const minutesEditing = ref(false)
const minutesEditText = ref('')

// 세션별 기록 영속 저장 (Map: sessionId → { transcriptLines, scriptLines, minutes, showMinutesTab })
const sessionRecords = ref(new Map())

function getOrCreateRecord(sessionId) {
  if (!sessionRecords.value.has(sessionId)) {
    sessionRecords.value.set(sessionId, {
      transcriptLines: [],
      scriptLines: [],
      generatedMinutes: null,
      showMinutesTab: false,
    })
  }
  return sessionRecords.value.get(sessionId)
}

const stt = useSTT({
  onResult: (text) => {
    const time = new Date().toLocaleTimeString('ko-KR', { hour: '2-digit', minute: '2-digit', second: '2-digit' })
    const entry = { time, text }
    transcriptLines.value.push(entry)
    scriptLines.value.push(entry)
    // 세션 기록에도 동기화
    if (activeSession.value) {
      const rec = getOrCreateRecord(activeSession.value.id)
      rec.transcriptLines.push(entry)
      rec.scriptLines.push(entry)
    }
    nextTick(() => { if (transcriptAreaRef.value) transcriptAreaRef.value.scrollTop = transcriptAreaRef.value.scrollHeight })
  },
  getLang: () => transcriptLang.value === 'ko' ? 'ko-KR' : 'en-US',
})

function togglePopover(name) { showPopover.value = showPopover.value === name ? null : name }
function closePopover() { showPopover.value = null }

function enterRoom(s) {
  activeSession.value = s
  activeTab.value = 'transcript'
  recordingState.value = 'idle'
  showPopover.value = null
  // 이전 기록 복원
  const rec = getOrCreateRecord(s.id)
  transcriptLines.value = rec.transcriptLines
  scriptLines.value = rec.scriptLines
  generatedMinutes.value = rec.generatedMinutes
  showMinutesTab.value = rec.showMinutesTab
  minutesEditText.value = rec.generatedMinutes?.content_summary || ''
  minutesEditing.value = false
  transcriptSummary.value = ''
  showSummary.value = false
}

function toggleRecording() {
  if (recordingState.value === 'idle') {
    recordingState.value = 'recording'
    stt.start()
  } else if (recordingState.value === 'recording') {
    recordingState.value = 'paused'
    stt.stop()
    fetchTranscriptSummary()
  } else {
    recordingState.value = 'recording'
    stt.start()
  }
}

function stopRecording() {
  const wasRecording = recordingState.value === 'recording'
  recordingState.value = 'idle'
  stt.stop()
  if (wasRecording) fetchTranscriptSummary()
}

async function fetchTranscriptSummary() {
  if (!transcriptLines.value.length) return
  summarizingTranscript.value = true
  showSummary.value = true
  transcriptSummary.value = ''
  const text = transcriptLines.value.map(l => `[${l.time}] ${l.text}`).join('\n')
  await streamPost(
    '/api/agent/ara/sessions-chat',
    { meeting_id: meetingId.value, message: `다음 대화 내용을 간결하게 요약해줘:\n${text}`, chat_history: [] },
    (chunk) => { transcriptSummary.value += chunk },
    () => { summarizingTranscript.value = false },
  )
}

async function endMeeting() {
  if (!confirm('회의를 종료하시겠습니까?')) return
  stopRecording()
  try {
    await api.patch(`/api/sessions/${activeSession.value.id}`, { status: 'ended' })
    await loadSessions()
  } catch {}
  activeSession.value = null
}

async function generateMinutes() {
  if (generatingMinutes.value) return
  generatingMinutes.value = true
  showMinutesTab.value = true
  activeTab.value = 'minutes'
  try {
    const { data } = await api.get(`/api/sessions/${activeSession.value.id}/minutes`)
    generatedMinutes.value = data
  } catch {
    try {
      const transcriptText = transcriptLines.value.map(l => l.text).join('\n')
      const res = await api.post(`/api/sessions/${activeSession.value.id}/minutes`, {
        content_summary: transcriptText || '(녹음 내용 없음)',
      })
      generatedMinutes.value = res.data
    } catch {
      generatedMinutes.value = { content_summary: '회의록 생성에 실패했습니다.' }
    }
  } finally {
    generatingMinutes.value = false
    minutesEditText.value = generatedMinutes.value?.content_summary || ''
    minutesEditing.value = false
    if (activeSession.value) {
      const rec = getOrCreateRecord(activeSession.value.id)
      rec.generatedMinutes = generatedMinutes.value
      rec.showMinutesTab = true
    }
  }
}

function saveMinutesEdit() {
  if (generatedMinutes.value) {
    generatedMinutes.value = { ...generatedMinutes.value, content_summary: minutesEditText.value }
  } else {
    generatedMinutes.value = { content_summary: minutesEditText.value }
  }
  minutesEditing.value = false
  if (activeSession.value) {
    const rec = getOrCreateRecord(activeSession.value.id)
    rec.generatedMinutes = generatedMinutes.value
  }
}

// 빠른 질문 목록
const quickQuestions = [
  '전체 회의를 요약해줘',
  '가장 최근 회의 내용 알려줘',
  '회의에서 결정된 사항 정리해줘',
  '아직 해결 안 된 과제가 있어?',
]

onMounted(async () => {
  await meetingsStore.fetchMeeting(meetingId.value)
  await meetingsStore.fetchRole(meetingId.value)
  await Promise.all([
    loadSessions(),
    loadMessages(),
    api.get(`/api/meetings/${meetingId.value}/agendas`).then(({ data }) => {
      agendas.value = data.filter(a => a.agenda_type === 'scheduled')
    }).catch(() => {}),
  ])
})

async function loadSessions() {
  const { data } = await api.get(`/api/meetings/${meetingId.value}/sessions`)
  sessions.value = data
}

async function createSession() {
  if (!createForm.value.title.trim() || creating.value) return
  creating.value = true
  try {
    await api.post(`/api/meetings/${meetingId.value}/sessions`, {
      title: createForm.value.title.trim(),
      scheduled_at: createForm.value.scheduled_at || null,
      location: createForm.value.location.trim() || null,
      agenda_ids: createForm.value.agenda_ids,
    })
    showCreateModal.value = false
    createForm.value = { title: '', scheduled_at: '', location: '', agenda_ids: [] }
    await loadSessions()
  } finally {
    creating.value = false
  }
}

function startEdit(s) {
  editingId.value = s.id
  editForm.value = {
    title: s.title,
    scheduled_at: s.scheduled_at ? s.scheduled_at.slice(0, 16) : '',
    agenda_ids: s.agenda_ids ? [...s.agenda_ids] : [],
  }
}

function cancelEdit() { editingId.value = null }

async function saveEdit(s) {
  if (!editForm.value.title.trim() || saving.value) return
  saving.value = true
  try {
    await api.patch(`/api/sessions/${s.id}`, {
      title: editForm.value.title.trim(),
      scheduled_at: editForm.value.scheduled_at || null,
      agenda_ids: editForm.value.agenda_ids,
    })
    editingId.value = null
    await loadSessions()
  } finally {
    saving.value = false
  }
}

async function endSession(s) {
  if (!confirm(`"${s.title}" 회의를 종료하시겠습니까?`)) return
  ending.value = s.id
  try {
    await api.patch(`/api/sessions/${s.id}`, { status: 'ended' })
    // 연결된 아젠다 종료 처리
    const ids = s.agenda_ids || []
    if (ids.length) {
      await Promise.all(ids.map(id =>
        api.patch(`/api/meetings/${meetingId.value}/agendas/${id}`, { status: 'ended' }).catch(() => {})
      ))
    }
    await loadSessions()
  } finally {
    ending.value = null
  }
}

async function deleteSession(s) {
  if (!confirm(`"${s.title}" 회의를 삭제하시겠습니까?\n삭제하면 회의록도 함께 삭제됩니다.`)) return
  deleting.value = s.id
  try {
    await api.delete(`/api/sessions/${s.id}`)
    await loadSessions()
  } finally {
    deleting.value = null
  }
}

async function viewMinutes(s) {
  selectedSession.value = s
  minutes.value = null
  showMinutesModal.value = true
  try {
    const { data } = await api.get(`/api/sessions/${s.id}/minutes`)
    minutes.value = data
  } catch {
    minutes.value = null
  }
}

function joinRoom(s) { enterRoom(s) }

// ── 아라 전송 ─────────────────────────────────
async function sendAra() {
  if (!araInput.value.trim() || araLoading.value) return
  const text = araInput.value.trim()
  araMessages.value.push({ role: 'user', content: text })
  saveMessage('user', text)
  araInput.value = ''
  const agentMsg = { role: 'agent', content: '' }
  araMessages.value.push(agentMsg)
  araLoading.value = true
  await nextTick()
  scrollMessages()

  const history = araMessages.value.slice(0, -1).map(m => ({
    role: m.role === 'user' ? 'user' : 'assistant',
    content: m.content,
  }))
  await streamPost(
    '/api/agent/ara/sessions-chat',
    { meeting_id: meetingId.value, message: text, chat_history: history },
    (chunk) => {
      agentMsg.content += chunk
      scrollMessages()
    },
    () => {
      araLoading.value = false
      saveMessage('agent', agentMsg.content)
    },
  )
}

async function sendQuick(q) {
  araInput.value = q
  await sendAra()
}

function scrollMessages() {
  if (messagesEl.value) {
    messagesEl.value.scrollTop = messagesEl.value.scrollHeight
  }
}

function formatDate(d) {
  if (!d) return '일정 미정'
  return new Date(d).toLocaleString('ko-KR', {
    month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit',
  })
}
function statusLabel(s) {
  return { scheduled: '예정', ongoing: '진행중', ended: '종료' }[s] || s
}
function statusCls(s) {
  return { scheduled: 'badge-primary', ongoing: 'badge-warning', ended: 'badge-muted' }[s] || 'badge-muted'
}
</script>

<template>
  <div class="sessions-layout">
    <MeetingNav />

    <div class="sessions-body">
      <!-- 왼쪽: 아라 AgentPanel -->
      <AgentPanel
        :avatar="araAvatar"
        name="아라"
        name-en="Ara"
        subtitle="회의 요약 · 질의응답"
        :messages="araMessages"
        :loading="araLoading"
        :quick-questions="quickQuestions"
        greeting="안녕하세요, 아라입니다! 🎤
회의 전체 또는 특정 회의에 대해 자연어로 질문해보세요.
예: &quot;가장 최근 회의 요약해줘&quot;, &quot;전체 회의에서 결정된 사항 정리해줘&quot;"
        placeholder="회의에 대해 자유롭게 질문하세요..."
        accent-color="#f59e0b"
        accent-border="#fbbf24"
        accent-bg="#fffbeb"
        bubble-gradient="linear-gradient(135deg,#fef3c7,#fed7aa)"
        bubble-color="#92400e"
        @send="sendQuick"
        @clear="clearHistory"
      />

      <!-- 오른쪽 패널 -->

      <!-- ── 회의 진행 중 뷰 ── -->
      <div v-if="activeSession" class="card sessions-panel in-meeting" @click="closePopover">
        <!-- 헤더: 제목 + 탭 -->
        <div class="right-panel-header in-meeting-header">
          <div class="in-mtitle">
            <span class="fw-semibold" style="font-size:13px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;max-width:220px">{{ activeSession.title }}</span>
            <span v-if="recordingState === 'recording'" class="rec-live"><i class="bi bi-record-fill"></i> REC</span>
          </div>
          <div class="mtabs">
            <button class="mtab" :class="{ active: activeTab === 'transcript' }" @click.stop="activeTab = 'transcript'">대화 기록</button>
            <button class="mtab" :class="{ active: activeTab === 'script' }" @click.stop="activeTab = 'script'">스크립트</button>
            <button v-if="showMinutesTab" class="mtab" :class="{ active: activeTab === 'minutes' }" @click.stop="activeTab = 'minutes'">회의록</button>
          </div>
        </div>

        <!-- 탭 본문 -->
        <div ref="transcriptAreaRef" class="tab-body in-meeting-body">
          <template v-if="activeTab === 'transcript'">
            <!-- AI 요약 섹션 -->
            <div v-if="showSummary" class="ts-summary-box">
              <div class="ts-summary-header">
                <span><i class="bi bi-stars"></i> AI 요약</span>
                <button class="ts-summary-close" @click.stop="showSummary = false">✕</button>
              </div>
              <div v-if="summarizingTranscript" class="ts-summary-body">
                <span class="spinner-border spinner-border-sm text-primary"></span>
                <span style="font-size:12px;color:var(--text-muted);margin-left:6px">요약 중...</span>
              </div>
              <div v-else class="ts-summary-body minutes-md" v-html="renderMd(transcriptSummary)"></div>
            </div>
            <div v-if="!transcriptLines.length" class="empty-state">
              <i class="bi bi-mic" style="font-size:28px;opacity:.25"></i>
              <p class="text-muted small mb-0">녹음을 시작하면 대화가 실시간으로 기록됩니다.</p>
            </div>
            <div v-for="(line, idx) in transcriptLines" :key="idx" class="tline">
              <span class="tline-time">{{ line.time }}</span>
              <span class="tline-text">{{ line.text }}</span>
            </div>
          </template>

          <template v-else-if="activeTab === 'script'">
            <div v-if="!scriptLines.length" class="empty-state">
              <i class="bi bi-file-earmark-text" style="font-size:28px;opacity:.25"></i>
              <p class="text-muted small mb-0">스크립트가 여기에 표시됩니다.</p>
            </div>
            <div v-for="(line, idx) in scriptLines" :key="idx" class="tline">
              <span class="tline-time">{{ line.time }}</span>
              <span class="tline-text">{{ line.text }}</span>
            </div>
          </template>

          <template v-else-if="activeTab === 'minutes'">
            <div v-if="generatingMinutes" class="empty-state">
              <span class="spinner-border spinner-border-sm text-primary mb-2"></span>
              <p class="text-muted small">AI가 회의록을 생성 중입니다...</p>
            </div>
            <template v-else-if="generatedMinutes">
              <div class="minutes-edit-toolbar">
                <template v-if="!minutesEditing">
                  <button class="minutes-tool-btn" @click.stop="minutesEditing = true; minutesEditText = generatedMinutes.content_summary || ''">
                    <i class="bi bi-pencil"></i> 편집
                  </button>
                </template>
                <template v-else>
                  <button class="minutes-tool-btn primary" @click.stop="saveMinutesEdit">
                    <i class="bi bi-check-lg"></i> 저장
                  </button>
                  <button class="minutes-tool-btn" @click.stop="minutesEditing = false">
                    취소
                  </button>
                </template>
              </div>
              <textarea v-if="minutesEditing" v-model="minutesEditText" class="minutes-edit-area"></textarea>
              <div v-else class="minutes-md" v-html="renderMd(generatedMinutes.content_summary || '')"></div>
            </template>
            <div v-else class="empty-state"><p class="text-muted small">회의록이 없습니다.</p></div>
          </template>
        </div>

        <!-- 하단 컨트롤 바 -->
        <div class="meeting-ctrl-bar" @click.stop>
          <div class="ctrl-group-left">
            <!-- 🎤 마이크 설정 -->
            <div class="ctrl-pop-wrap">
              <button class="ctrl-btn" :class="{ 'ctrl-active': showPopover === 'mic' }"
                @click.stop="togglePopover('mic')" title="녹음 설정">
                <i class="bi bi-mic"></i><i class="bi bi-chevron-down ctrl-chev"></i>
              </button>
              <div v-if="showPopover === 'mic'" class="ctrl-popover" @click.stop>
                <div class="cpop-title">마이크 설정</div>
                <div class="cpop-row">
                  <span class="cpop-label">감도</span>
                  <input type="range" v-model.number="micSensitivity" min="0" max="100" class="cpop-range" />
                  <span class="cpop-val">{{ micSensitivity }}%</span>
                </div>
                <div class="cpop-row">
                  <span class="cpop-label">노이즈 제거</span>
                  <input type="checkbox" v-model="noiseReduction" />
                </div>
              </div>
            </div>

            <!-- 🎧 대화기록 언어 -->
            <div class="ctrl-pop-wrap">
              <button class="ctrl-btn ctrl-lang" :class="{ 'ctrl-active': showPopover === 'tLang' }"
                @click.stop="togglePopover('tLang')" title="대화기록 언어">
                <i class="bi bi-headphones"></i>
                <span>{{ transcriptLang === 'ko' ? '한국어' : 'English' }}</span>
                <i class="bi bi-chevron-down ctrl-chev"></i>
              </button>
              <div v-if="showPopover === 'tLang'" class="ctrl-popover" @click.stop>
                <div class="cpop-title">대화기록 언어</div>
                <button class="cpop-opt" :class="{ selected: transcriptLang === 'ko' }"
                  @click="transcriptLang = 'ko'; closePopover()">🇰🇷 한국어</button>
                <button class="cpop-opt" :class="{ selected: transcriptLang === 'en' }"
                  @click="transcriptLang = 'en'; closePopover()">🇺🇸 English</button>
              </div>
            </div>

            <!-- 📝 스크립트 언어 -->
            <div class="ctrl-pop-wrap">
              <button class="ctrl-btn ctrl-lang" :class="{ 'ctrl-active': showPopover === 'sLang' }"
                @click.stop="togglePopover('sLang')" title="스크립트 언어">
                <i class="bi bi-file-earmark-text"></i>
                <span>{{ scriptLang === 'ko' ? '한국어' : 'English' }}</span>
                <i class="bi bi-chevron-down ctrl-chev"></i>
              </button>
              <div v-if="showPopover === 'sLang'" class="ctrl-popover" @click.stop>
                <div class="cpop-title">스크립트 언어</div>
                <button class="cpop-opt" :class="{ selected: scriptLang === 'ko' }"
                  @click="scriptLang = 'ko'; closePopover()">🇰🇷 한국어</button>
                <button class="cpop-opt" :class="{ selected: scriptLang === 'en' }"
                  @click="scriptLang = 'en'; closePopover()">🇺🇸 English</button>
              </div>
            </div>

            <!-- ▶/⏸ 녹음 버튼 -->
            <button class="ctrl-rec-btn" :class="{ recording: recordingState === 'recording' }"
              @click.stop="toggleRecording"
              :title="recordingState === 'idle' ? '녹음 시작' : recordingState === 'recording' ? '일시정지' : '재개'">
              <i v-if="recordingState !== 'recording'" class="bi bi-play-fill"></i>
              <i v-else class="bi bi-pause-fill"></i>
            </button>

            <!-- ⏹ 중지 -->
            <button v-if="recordingState !== 'idle'" class="ctrl-btn ctrl-stop"
              @click.stop="stopRecording" title="중지">
              <i class="bi bi-stop-fill"></i>
            </button>

            <!-- 기록 종료 -->
            <button class="ctrl-end" @click.stop="endMeeting">기록 종료</button>
          </div>
          <div class="ctrl-group-right">
            <button class="ctrl-minutes" :disabled="generatingMinutes" @click.stop="generateMinutes">
              <i class="bi bi-stars"></i> 회의록 생성
            </button>
          </div>
        </div>
      </div>

      <!-- ── 회의 목록 뷰 ── -->
      <div v-else class="card sessions-panel">
        <div class="right-panel-header">
          <span class="panel-tab active" style="cursor:default">회의 목록</span>
          <button class="btn btn-outline btn-sm" style="margin-left:auto;margin-right:6px" @click="showCreateModal = true">+ 회의 등록</button>
          <button v-if="role === 'admin'" class="btn btn-outline btn-sm" @click="router.push(`/meetings/${meetingId}/card-news`)">📰 카드뉴스</button>
        </div>

        <div class="tab-body">
          <div v-if="!sessions.length" class="empty-state">
            <p>등록된 회의가 없습니다.</p>
            <button class="btn btn-outline btn-sm" style="margin-top:12px" @click="showCreateModal = true">+ 회의 등록</button>
          </div>

          <div v-for="s in sessions" :key="s.id" class="session-card fade-in">
            <!-- 수정 모드 -->
            <div v-if="editingId === s.id" class="session-edit">
              <div class="form-group" style="margin-bottom:8px">
                <label class="form-label" style="font-size:11px">회의명</label>
                <input v-model="editForm.title" class="form-input"
                  @keydown.enter="saveEdit(s)" @keydown.esc="cancelEdit" autofocus />
              </div>
              <div class="form-group" style="margin-bottom:8px">
                <label class="form-label" style="font-size:11px">일정</label>
                <input type="datetime-local" v-model="editForm.scheduled_at" class="form-input" />
              </div>
              <div class="form-group" style="margin-bottom:12px">
                <label class="form-label" style="font-size:11px">아젠다 연결</label>
                <div class="agenda-check-list">
                  <label v-if="!agendas.length" style="font-size:12px;color:var(--text-muted)">등록된 아젠다가 없습니다</label>
                  <label v-for="a in agendas" :key="a.id" class="agenda-check-item">
                    <input type="checkbox" :value="a.id" v-model="editForm.agenda_ids" />
                    <span class="agenda-type-dot" :style="{ background: AGENDA_TYPE_COLOR[a.agenda_type] || '#6366f1' }"></span>
                    <span>{{ a.content }}</span>
                  </label>
                </div>
              </div>
              <div style="display:flex;gap:6px">
                <button class="btn btn-primary btn-sm" :disabled="!editForm.title.trim() || saving" @click="saveEdit(s)">
                  {{ saving ? '저장 중...' : '저장' }}
                </button>
                <button class="btn btn-ghost btn-sm" @click="cancelEdit">취소</button>
              </div>
            </div>

            <!-- 보기 모드 -->
            <div v-else>
              <div class="session-header">
                <div>
                  <div style="font-weight:600;font-size:14px">{{ s.title }}</div>
                  <div style="font-size:12px;color:var(--text-muted);margin-top:2px">{{ formatDate(s.scheduled_at) }}</div>
                  <!-- 연결된 아젠다 칩 -->
                  <div v-if="s.agenda_ids?.length" class="session-agenda-chips">
                    <span
                      v-for="id in s.agenda_ids"
                      :key="id"
                      class="session-agenda-chip"
                      :style="{ background: AGENDA_TYPE_COLOR[agendas.find(a=>a.id===id)?.agenda_type] || '#6366f1' }"
                    >
                      {{ (agendas.find(a=>a.id===id)?.content || '아젠다').slice(0,14) }}
                    </span>
                  </div>
                </div>
                <span class="badge" :class="statusCls(s.status)">{{ statusLabel(s.status) }}</span>
              </div>
              <div class="session-actions">
                <button class="btn btn-primary btn-sm" @click="joinRoom(s)">
                  {{ s.status === 'ended' ? '다시 보기' : '참여하기' }}
                </button>
                <button class="btn btn-outline btn-sm" :disabled="s.status !== 'ended'" @click="viewMinutes(s)">회의록</button>
                <template v-if="role === 'admin'">
                  <!-- 미종료 세션: 수정 + 종료 -->
                  <template v-if="s.status !== 'ended'">
                    <button v-if="s.status !== 'ongoing'" class="btn btn-ghost btn-sm" @click="startEdit(s)">수정</button>
                    <button class="btn-end-session" :disabled="ending === s.id" @click="endSession(s)">
                      {{ ending === s.id ? '종료 중...' : '종료' }}
                    </button>
                  </template>
                  <!-- 종료된 세션: 삭제만 -->
                  <template v-else>
                    <button class="btn btn-ghost btn-sm" style="color:var(--danger)" :disabled="deleting === s.id" @click="deleteSession(s)">
                      {{ deleting === s.id ? '삭제 중...' : '삭제' }}
                    </button>
                  </template>
                </template>
              </div>
            </div>
          </div>
        </div>

      </div><!-- end v-else list panel -->

    </div>
  </div>

  <!-- 회의 만들기 모달 -->
  <BaseModal v-model="showCreateModal">
    <template #title>회의 일정 추가</template>
    <div class="modal-inner">
      <div class="form-group">
        <label class="form-label">회의 제목 <span style="color:var(--danger)">*</span></label>
        <input v-model="createForm.title" class="form-input" placeholder="예: 1차 회의" @keydown.enter="createSession" autofocus />
      </div>
      <div class="form-group">
        <label class="form-label">일정</label>
        <input type="datetime-local" v-model="createForm.scheduled_at" class="form-input" />
      </div>
      <div class="form-group">
        <label class="form-label">장소 <span style="font-size:11px;color:var(--text-muted);font-weight:400">(TPO)</span></label>
        <input v-model="createForm.location" class="form-input" placeholder="예: 3층 회의실 A / 비대면 회의 등" />
      </div>
      <div class="form-group">
        <label class="form-label">아젠다 연결 <span style="font-size:11px;color:var(--text-muted);font-weight:400">(이 회의에서 다룰 아젠다)</span></label>
        <div class="agenda-check-list">
          <label v-if="!agendas.length" style="font-size:12px;color:var(--text-muted)">등록된 아젠다가 없습니다</label>
          <label v-for="a in agendas" :key="a.id" class="agenda-check-item">
            <input type="checkbox" :value="a.id" v-model="createForm.agenda_ids" />
            <span class="agenda-type-dot" :style="{ background: AGENDA_TYPE_COLOR[a.agenda_type] || '#6366f1' }"></span>
            <span style="font-size:13px">
              <strong style="font-size:11px;margin-right:4px;opacity:.7">{{ AGENDA_TYPE_LABEL[a.agenda_type] }}</strong>{{ a.content }}
            </span>
          </label>
        </div>
      </div>
    </div>
    <template #footer>
      <button class="btn btn-outline" @click="showCreateModal = false">취소</button>
      <button class="btn btn-primary" :disabled="!createForm.title.trim() || creating" @click="createSession">
        {{ creating ? '추가 중...' : '일정 추가' }}
      </button>
    </template>
  </BaseModal>

  <!-- 회의록 모달 -->
  <BaseModal v-model="showMinutesModal" width="min(680px, 95vw)">
    <template #title>{{ selectedSession?.title }} 회의록</template>
    <div class="modal-inner">
        <div v-if="!minutes" class="empty-state"><p>회의록을 불러오는 중...</p></div>
        <div v-else class="minutes-structured">
          <!-- 회의록 마크다운 요약 -->
          <div v-if="minutes.content_summary" class="minutes-md" v-html="renderMd(minutes.content_summary)"></div>

          <!-- 5대 필수요소 구조적 표시 (AI가 생성한 JSON 기반) -->
          <template v-if="!minutes.content_summary && (minutes.attendees_json?.length || minutes.decisions_json?.length || minutes.action_items_json?.length)">
            <!-- Joiner -->
            <section v-if="minutes.attendees_json?.length" class="ms-section">
              <div class="ms-section-title">👥 참석자 (Joiner)</div>
              <div class="ms-attendee-list">
                <div v-for="a in minutes.attendees_json" :key="a.name" class="ms-attendee" :class="{absent: !a.present}">
                  <span class="ms-att-name">{{ a.name }}</span>
                  <span class="ms-att-dept">{{ a.dept }}</span>
                  <span class="ms-att-role">{{ a.role === 'admin' ? '관리자' : '발제자' }}</span>
                  <span class="ms-att-status" :class="a.present ? 'present' : 'absent'">{{ a.present ? '참석' : '불참' }}</span>
                  <span v-if="a.note" class="ms-att-note">({{ a.note }})</span>
                </div>
              </div>
            </section>

            <!-- Done -->
            <section v-if="minutes.decisions_json?.length" class="ms-section">
              <div class="ms-section-title">✅ 결정 사항 (Done)</div>
              <div v-for="(d, i) in minutes.decisions_json" :key="i" class="ms-decision">
                <span class="ms-dec-num">{{ i+1 }}</span>
                <span class="ms-dec-content">{{ d.content }}</span>
                <span v-if="d.decided_by" class="ms-dec-by">— {{ d.decided_by }}</span>
              </div>
            </section>

            <!-- WILL DO -->
            <section v-if="minutes.action_items_json?.length" class="ms-section">
              <div class="ms-section-title">📌 실행 계획 (WILL DO)</div>
              <table class="ms-action-table">
                <thead><tr><th>업무</th><th>담당자</th><th>기한</th><th>상태</th></tr></thead>
                <tbody>
                  <tr v-for="(a, i) in minutes.action_items_json" :key="i">
                    <td>{{ a.content }}</td>
                    <td>{{ a.assignee || '-' }}</td>
                    <td>{{ a.due_date || '-' }}</td>
                    <td><span class="ms-status-chip" :class="'status-' + (a.status || 'pending')">{{ {'pending':'대기','done':'완료','delayed':'지연'}[a.status] || a.status }}</span></td>
                  </tr>
                </tbody>
              </table>
            </section>

            <!-- TBD -->
            <section v-if="minutes.tbd_items_json?.length" class="ms-section">
              <div class="ms-section-title">⚠️ 미결 안건 (TBD)</div>
              <div v-for="(t, i) in minutes.tbd_items_json" :key="i" class="ms-tbd-item">
                <span class="ms-tbd-dot">●</span>
                <span>{{ t.content }}</span>
                <span v-if="t.reason" class="ms-tbd-reason">— {{ t.reason }}</span>
              </div>
            </section>

            <!-- Next -->
            <section v-if="minutes.next_meeting_note" class="ms-section">
              <div class="ms-section-title">📅 차기 회의</div>
              <p class="ms-next">{{ minutes.next_meeting_note }}</p>
            </section>
          </template>
        </div>
    </div>
  </BaseModal>
</template>

<style scoped>
.modal-inner { padding: 20px 24px; display: flex; flex-direction: column; gap: 16px; }
.sessions-layout {
  display: flex;
  flex-direction: column;
  height: calc(100vh - var(--header-h) - 40px);
}

.sessions-body {
  flex: 1;
  min-height: 0;
  display: flex;
  gap: 16px;
  overflow: hidden;
}

/* ── 회의 목록 패널 ── */
.sessions-panel {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  min-height: 0;
}

.session-card {
  background: #f8fafc;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 14px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.session-header { display: flex; justify-content: space-between; align-items: flex-start; }
.session-actions { display: flex; gap: 6px; flex-wrap: wrap; }
.session-edit { display: flex; flex-direction: column; }

/* 아젠다 연결 칩 */
.session-agenda-chips { display: flex; flex-wrap: wrap; gap: 4px; margin-top: 6px; }
.session-agenda-chip {
  padding: 2px 8px; border-radius: 99px;
  font-size: 11px; font-weight: 600; color: #fff;
  white-space: nowrap; max-width: 120px;
  overflow: hidden; text-overflow: ellipsis;
}

/* 아젠다 체크리스트 */
.agenda-check-list { display: flex; flex-direction: column; gap: 6px; }
.agenda-check-item {
  display: flex; align-items: center; gap: 8px;
  padding: 6px 10px; border: 1px solid var(--border);
  border-radius: var(--radius); cursor: pointer; font-size: 13px;
  transition: background .12s;
}
.agenda-check-item:hover { background: #f1f5f9; }
.agenda-check-item input[type="checkbox"] { width: 15px; height: 15px; cursor: pointer; flex-shrink: 0; }
.agenda-type-dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
.btn-end-session {
  padding: 4px 10px;
  border-radius: var(--radius);
  border: 1px solid var(--danger);
  background: transparent;
  color: var(--danger);
  font-size: 12px;
  font-weight: 700;
  cursor: pointer;
  transition: background .15s, color .15s;
  line-height: 1.5;
}
.btn-end-session:hover:not(:disabled) { background: var(--danger); color: #fff; }
.btn-end-session:disabled { opacity: .45; cursor: not-allowed; }
.minutes-content { white-space: pre-wrap; font-size: 13px; line-height: 1.7; }

/* ── 회의록 구조적 표시 ── */
.minutes-structured { display: flex; flex-direction: column; gap: 18px; }
.minutes-md :deep(h2), .minutes-md :deep(h3) {
  font-size: 14px; font-weight: 700; margin: 16px 0 8px; color: var(--text);
  padding-bottom: 4px; border-bottom: 1px solid var(--border);
}
.minutes-md :deep(p) { font-size: 13px; line-height: 1.7; margin: 4px 0; }
.minutes-md :deep(ul), .minutes-md :deep(ol) { padding-left: 20px; font-size: 13px; line-height: 1.7; }
.minutes-md :deep(table) { width: 100%; border-collapse: collapse; font-size: 13px; }
.minutes-md :deep(th), .minutes-md :deep(td) { padding: 6px 10px; border: 1px solid var(--border); }
.minutes-md :deep(th) { background: #f9fafb; font-weight: 600; }

.ms-section { border: 1px solid var(--border); border-radius: 8px; overflow: hidden; }
.ms-section-title {
  padding: 10px 14px; background: #f8fafc; font-size: 13px; font-weight: 700;
  color: var(--text); border-bottom: 1px solid var(--border);
}
.ms-attendee-list { padding: 10px 14px; display: flex; flex-direction: column; gap: 6px; }
.ms-attendee { display: flex; align-items: center; gap: 8px; font-size: 13px; }
.ms-att-name { font-weight: 600; }
.ms-att-dept { color: var(--text-muted); font-size: 12px; }
.ms-att-role { background: #f1f5f9; padding: 1px 7px; border-radius: 99px; font-size: 11px; }
.ms-att-status { padding: 1px 8px; border-radius: 99px; font-size: 11px; font-weight: 600; }
.ms-att-status.present { background: #dcfce7; color: #166534; }
.ms-att-status.absent { background: #fef2f2; color: #dc2626; }
.ms-att-note { font-size: 11px; color: var(--text-muted); }

.ms-decision { display: flex; align-items: flex-start; gap: 8px; padding: 8px 14px; font-size: 13px; border-bottom: 1px solid var(--border); }
.ms-decision:last-child { border-bottom: none; }
.ms-dec-num { width: 20px; height: 20px; background: var(--primary); color: #fff; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 11px; font-weight: 700; flex-shrink: 0; }
.ms-dec-content { flex: 1; font-weight: 500; }
.ms-dec-by { color: var(--text-muted); font-size: 12px; white-space: nowrap; }

.ms-action-table { width: 100%; border-collapse: collapse; font-size: 13px; }
.ms-action-table th { padding: 8px 12px; background: #f9fafb; text-align: left; font-size: 12px; color: var(--text-muted); font-weight: 600; border-bottom: 1px solid var(--border); }
.ms-action-table td { padding: 8px 12px; border-bottom: 1px solid var(--border); vertical-align: middle; }
.ms-action-table tr:last-child td { border-bottom: none; }
.ms-status-chip { padding: 2px 8px; border-radius: 99px; font-size: 11px; font-weight: 600; }
.status-pending { background: #fef9c3; color: #a16207; }
.status-done { background: #dcfce7; color: #166534; }
.status-delayed { background: #fef2f2; color: #dc2626; }

.ms-tbd-item { display: flex; align-items: flex-start; gap: 8px; padding: 8px 14px; font-size: 13px; border-bottom: 1px solid var(--border); }
.ms-tbd-item:last-child { border-bottom: none; }
.ms-tbd-dot { color: #f59e0b; font-size: 8px; margin-top: 4px; flex-shrink: 0; }
.ms-tbd-reason { color: var(--text-muted); font-size: 12px; }
.ms-next { padding: 8px 14px; font-size: 13px; color: var(--text); margin: 0; }

/* ── 아라 패널 ── */
.ara-panel {
  display: flex;
  flex-direction: column;
  min-height: 0;
  overflow: hidden;
}

.ara-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 16px 10px;
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
}
.ara-title { display: flex; align-items: center; gap: 10px; }
.ara-avatar {
  width: 38px; height: 38px; border-radius: 50%; object-fit: cover;
  border: 2px solid #fbbf24;
  box-shadow: 0 0 0 3px #fef3c7;
}

/* 빠른 질문 */
.quick-questions {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  padding: 10px 14px;
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
}
.quick-btn {
  font-size: 11px;
  padding: 4px 10px;
  border-radius: 99px;
  border: 1px solid #fbbf24;
  background: #fffbeb;
  color: #92400e;
  cursor: pointer;
  transition: background .15s;
  white-space: nowrap;
}
.quick-btn:hover:not(:disabled) { background: #fef3c7; }
.quick-btn:disabled { opacity: .5; cursor: not-allowed; }

/* 메시지 */
.ara-messages {
  flex: 1;
  overflow-y: auto;
  padding: 14px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.msg-row { display: flex; flex-direction: column; gap: 3px; }
.msg-row.user { align-items: flex-end; }
.msg-row.agent { align-items: flex-start; }

.agent-label {
  display: flex;
  align-items: center;
  gap: 5px;
  font-size: 11px;
  font-weight: 600;
  color: #f59e0b;
  margin-bottom: 2px;
}
.ara-mini { width: 16px; height: 16px; border-radius: 50%; object-fit: cover; }

.bubble {
  padding: 8px 12px;
  border-radius: 12px;
  font-size: 13px;
  line-height: 1.65;
  max-width: 92%;
  word-break: break-word;
}
.ara-bubble {
  background: linear-gradient(135deg, #fef3c7, #fed7aa);
  border: 1px solid #fbbf24;
  color: #92400e;
  border-radius: 2px 12px 12px 12px;
}
.user-bubble {
  background: var(--primary);
  color: #fff;
  border-radius: 12px 12px 2px 12px;
}

/* 타이핑 애니메이션 */
.typing {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 10px 14px;
}
.typing span {
  width: 7px; height: 7px;
  background: #d97706;
  border-radius: 50%;
  animation: bounce 1.2s infinite;
}
.typing span:nth-child(2) { animation-delay: .2s; }
.typing span:nth-child(3) { animation-delay: .4s; }
@keyframes bounce { 0%,80%,100%{transform:translateY(0)} 40%{transform:translateY(-6px)} }

/* 입력창 */
.ara-input-area {
  display: flex;
  gap: 8px;
  padding: 10px 12px;
  border-top: 1px solid var(--border);
  flex-shrink: 0;
}
.ara-input {
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
.ara-input:focus { border-color: #fbbf24; box-shadow: 0 0 0 2px #fef3c7; }

.btn-ara {
  background: linear-gradient(135deg, #f59e0b, #ea580c);
  color: #fff;
  border: none;
  border-radius: 8px;
  padding: 6px 14px;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  transition: opacity .15s;
  align-self: flex-end;
}
.btn-ara:disabled { opacity: .45; cursor: not-allowed; }
.btn-ara:not(:disabled):hover { opacity: .88; }

/* ── 회의 진행 패널 ────────────────────────────────────────── */
.in-meeting { position: relative; }
.in-meeting-header { flex-direction: column !important; align-items: flex-start !important; padding: 0 !important; }
.in-mtitle { display: flex; align-items: center; gap: 8px; padding: 12px 14px 8px; width: 100%; box-sizing: border-box; }
.rec-live { font-size: 11px; font-weight: 700; color: #ef4444; animation: blink-rec 1.2s infinite; flex-shrink: 0; }
@keyframes blink-rec { 0%,100%{opacity:1} 50%{opacity:.3} }
.mtabs { display: flex; border-bottom: 1px solid var(--border); width: 100%; padding: 0 6px; }
.mtab { padding: 7px 12px; font-size: 13px; font-weight: 500; color: var(--text-muted); background: none; border: none; border-bottom: 2px solid transparent; cursor: pointer; transition: all .15s; white-space: nowrap; margin-bottom: -1px; }
.mtab:hover { color: var(--primary); }
.mtab.active { color: var(--primary); border-bottom-color: var(--primary); font-weight: 600; }

.in-meeting-body { padding: 12px 14px; gap: 2px !important; }
.tline { display: flex; align-items: flex-start; gap: 10px; padding: 6px 0; border-bottom: 1px solid #f1f5f9; font-size: 13px; }
.tline:last-child { border-bottom: none; }
.tline-time { font-size: 11px; color: var(--text-muted); white-space: nowrap; flex-shrink: 0; margin-top: 3px; font-variant-numeric: tabular-nums; min-width: 62px; }
.tline-text { flex: 1; line-height: 1.65; }

/* 하단 컨트롤 바 */
.meeting-ctrl-bar {
  display: flex; align-items: center; justify-content: space-between;
  padding: 10px 12px; border-top: 1px solid var(--border);
  background: #fff; flex-shrink: 0; gap: 8px; flex-wrap: wrap; border-radius: 0 0 var(--radius-lg) var(--radius-lg);
}
.ctrl-group-left { display: flex; align-items: center; gap: 5px; flex-wrap: wrap; }
.ctrl-group-right { display: flex; align-items: center; gap: 6px; margin-left: auto; }

.ctrl-btn {
  display: inline-flex; align-items: center; gap: 3px;
  padding: 6px 9px; border-radius: 8px; border: 1px solid var(--border);
  background: #f8fafc; color: #475569; font-size: 13px; cursor: pointer;
  transition: all .15s; white-space: nowrap; line-height: 1;
}
.ctrl-btn:hover { background: #f1f5f9; border-color: #cbd5e1; }
.ctrl-active { background: #eff6ff !important; border-color: var(--primary) !important; color: var(--primary) !important; }
.ctrl-chev { font-size: 9px; opacity: .6; }
.ctrl-lang { gap: 5px; }
.ctrl-lang span { font-size: 12px; }
.ctrl-stop { color: #dc2626 !important; }
.ctrl-stop:hover { background: #fef2f2 !important; border-color: #fca5a5 !important; }

.ctrl-rec-btn {
  width: 34px; height: 34px; border-radius: 50%; flex-shrink: 0;
  border: 2px solid var(--primary); background: var(--primary); color: #fff;
  display: inline-flex; align-items: center; justify-content: center;
  font-size: 14px; cursor: pointer; transition: all .15s;
}
.ctrl-rec-btn:hover { opacity: .85; }
.ctrl-rec-btn.recording { background: #ef4444; border-color: #ef4444; animation: pulse-rec .9s infinite; }
@keyframes pulse-rec { 0%,100%{box-shadow:0 0 0 0 rgba(239,68,68,.4)} 50%{box-shadow:0 0 0 5px rgba(239,68,68,0)} }

.ctrl-end {
  padding: 6px 12px; border-radius: 8px; border: 1px solid #cbd5e1;
  background: #f8fafc; color: #475569; font-size: 13px; font-weight: 500;
  cursor: pointer; transition: all .15s;
}
.ctrl-end:hover { background: #fef2f2; border-color: #fca5a5; color: #dc2626; }

.ctrl-minutes {
  display: inline-flex; align-items: center; gap: 5px;
  padding: 8px 14px; border-radius: 8px;
  background: linear-gradient(135deg, #1e3a5f, #3b82f6);
  color: #fff; font-size: 13px; font-weight: 600; border: none; cursor: pointer;
  transition: opacity .15s; white-space: nowrap;
}
.ctrl-minutes:disabled { opacity: .5; cursor: not-allowed; }
.ctrl-minutes:not(:disabled):hover { opacity: .88; }

/* 대화기록 AI 요약 박스 */
.ts-summary-box {
  border: 1px solid #bfdbfe;
  border-radius: 10px;
  background: #eff6ff;
  margin-bottom: 12px;
  overflow: hidden;
  flex-shrink: 0;
}
.ts-summary-header {
  display: flex; align-items: center; justify-content: space-between;
  padding: 8px 12px;
  background: #dbeafe;
  font-size: 12px; font-weight: 700; color: #1e40af;
}
.ts-summary-close {
  background: none; border: none; cursor: pointer;
  font-size: 12px; color: #3b82f6; padding: 0 2px;
  line-height: 1;
}
.ts-summary-body {
  padding: 10px 14px;
  font-size: 13px; line-height: 1.7; color: #1e3a5f;
  display: flex; align-items: center;
}

/* 회의록 편집 */
.minutes-edit-toolbar {
  display: flex; gap: 6px; padding: 6px 0 8px;
  flex-shrink: 0; border-bottom: 1px solid var(--border); margin-bottom: 10px;
}
.minutes-tool-btn {
  display: inline-flex; align-items: center; gap: 4px;
  padding: 5px 12px; border-radius: 6px; border: 1px solid var(--border);
  background: #f8fafc; color: #475569; font-size: 12px; cursor: pointer;
  transition: all .15s;
}
.minutes-tool-btn:hover { background: #f1f5f9; }
.minutes-tool-btn.primary { background: var(--primary); color: #fff; border-color: var(--primary); }
.minutes-tool-btn.primary:hover { opacity: .88; }
.minutes-edit-area {
  flex: 1; width: 100%; min-height: 200px;
  border: 1px solid #93c5fd; border-radius: 8px;
  padding: 10px 12px; font-size: 13px; line-height: 1.7;
  font-family: inherit; resize: vertical; outline: none;
  background: #fff; color: var(--text);
  box-sizing: border-box;
}
.minutes-edit-area:focus { border-color: var(--primary); box-shadow: 0 0 0 2px #bfdbfe; }

/* 팝오버 */
.ctrl-pop-wrap { position: relative; }
.ctrl-popover {
  position: absolute; bottom: calc(100% + 8px); left: 0;
  background: #fff; border: 1px solid var(--border);
  border-radius: 10px; box-shadow: 0 8px 24px rgba(0,0,0,.14);
  min-width: 180px; padding: 8px; z-index: 300;
}
.cpop-title { font-size: 11px; font-weight: 700; color: var(--text-muted); text-transform: uppercase; letter-spacing: .05em; padding: 2px 6px 8px; border-bottom: 1px solid var(--border); margin-bottom: 6px; }
.cpop-row { display: flex; align-items: center; gap: 8px; padding: 5px 6px; }
.cpop-label { font-size: 12px; color: #475569; min-width: 60px; flex-shrink: 0; }
.cpop-range { flex: 1; height: 4px; accent-color: var(--primary); cursor: pointer; }
.cpop-val { font-size: 12px; color: var(--text-muted); min-width: 32px; text-align: right; }
.cpop-opt {
  display: flex; width: 100%; padding: 7px 10px;
  background: none; border: none; cursor: pointer; font-size: 13px;
  color: #334155; border-radius: 6px; text-align: left; transition: background .1s;
}
.cpop-opt:hover { background: #f1f5f9; }
.cpop-opt.selected { background: #eff6ff; color: var(--primary); font-weight: 600; }
</style>
