<script setup>
import {
  ref,
  reactive,
  computed,
  onMounted,
  onUnmounted,
  onBeforeUnmount,
  nextTick,
  watch,
} from 'vue'
import { useRoute } from 'vue-router'
import { useEditor, EditorContent } from '@tiptap/vue-3'
import StarterKit from '@tiptap/starter-kit'
import { Table, TableRow, TableCell, TableHeader } from '@tiptap/extension-table'
import SessionEditModal from '../components/SessionEditModal.vue'
import CreateSessionModal from '../components/CreateSessionModal.vue'
import AgentComposer from '../components/AgentComposer.vue'
import AgendaReviewList from '../components/AgendaReviewList.vue'
import api, { apiAI } from '../api'
import { streamPost } from '../api'
import { useRealtimeSTT } from '../composables/useRealtimeSTT'
import { useAgentMention } from '../composables/useAgentMention'
import hyeanAvatar from '../assets/agents/hyean.png'
import { useThemeStore } from '../stores/theme'
import { useAuthStore } from '../stores/auth'
import { useMeetingsStore } from '../stores/meetings'
import { useSessionsStore } from '../stores/sessions'
import { selectedModel } from '../stores/llmModel'
import { formatDateTimeShort } from '../utils/date'
import { toast } from '../composables/useToast'
import { confirmDialog, promptDialog } from '../composables/useConfirm'
const themeStore = useThemeStore()
const authStore = useAuthStore()
const meetingsStore = useMeetingsStore()
const sessionsStore = useSessionsStore()
const route = useRoute()

import { renderMd } from '../composables/useMarkdown'

// ─── State ────────────────────────────────────────────────────
const meetings = ref([]) // [{ id, title, sessions: [] }] — 사이드바 트리 표시용 (원본은 스토어)
const loadingMeetings = ref(true) // 첫 페인트부터 로딩 표시 — onMounted 이전 빈 목록 깜빡임 방지
const sessionsCache = computed(() => sessionsStore.sessionsByMeeting) // 단일 캐시

const selectedMeetingId = ref(null)
const expandedMeetingIds = ref(new Set())
const activeSession = ref(null)
const sidebarSearch = ref('')
const sessionStatusFilter = ref('all') // 'all' | 'scheduled' | 'ongoing' | 'ended'
const hideEndedSessions = ref(false)
const showFilterDrop = ref(false)
const sidebarCollapsed = ref(false)
const sidebarW = ref(330)
let sidebarResizing = false,
  srStartX = 0,
  srStartW = 0
function onSidebarResizeStart(e) {
  if (sidebarCollapsed.value) return
  sidebarResizing = true
  srStartX = e.clientX
  srStartW = sidebarW.value
  document.addEventListener('mousemove', onSidebarResizeMove)
  document.addEventListener('mouseup', onSidebarResizeEnd)
  e.preventDefault()
}
function onSidebarResizeMove(e) {
  if (!sidebarResizing) return
  sidebarW.value = Math.max(330, Math.min(450, srStartW + (e.clientX - srStartX)))
}
function onSidebarResizeEnd() {
  sidebarResizing = false
  document.removeEventListener('mousemove', onSidebarResizeMove)
  document.removeEventListener('mouseup', onSidebarResizeEnd)
}

// ─── 우측 AI 사이드바 리사이즈 ────────────────────────────────
const agentSidebarW = ref(290)
let agentResizing = false,
  arStartX = 0,
  arStartW = 0
function onAgentResizeStart(e) {
  agentResizing = true
  arStartX = e.clientX
  arStartW = agentSidebarW.value
  document.addEventListener('mousemove', onAgentResizeMove)
  document.addEventListener('mouseup', onAgentResizeEnd)
  e.preventDefault()
}
function onAgentResizeMove(e) {
  if (!agentResizing) return
  agentSidebarW.value = Math.max(240, Math.min(480, arStartW - (e.clientX - arStartX)))
}
function onAgentResizeEnd() {
  agentResizing = false
  document.removeEventListener('mousemove', onAgentResizeMove)
  document.removeEventListener('mouseup', onAgentResizeEnd)
}

// 회의(세션) 검색: 제목·장소·날짜/시간(원본 ISO + 표시형식)·내용(description) 매칭
function sessionMatches(s, q) {
  return [
    s.title,
    s.location,
    s.scheduled_at, // 원본 ISO (예: "2026-06" 검색)
    formatDateTimeShort(s.scheduled_at, ''), // 표시 형식 (예: "6월", "오후" 검색)
    s.description, // 내용
    s.content_summary, // 회의록 요약(있으면)
  ].some(v => (v ?? '').toString().toLowerCase().includes(q))
}

const filteredMeetings = computed(() => {
  const q = sidebarSearch.value.trim().toLowerCase()
  const active = meetings.value.filter(m => m.status !== 'ended')
  if (!q) return active
  const out = []
  for (const m of active) {
    const titleMatch = (m.title || '').toLowerCase().includes(q)
    if (titleMatch) {
      // 회의체명이 매칭되면 그 회의체의 모든 회의를 보여준다
      out.push(m)
      continue
    }
    // 회의(세션)가 매칭된 경우 → 매칭된 회의만 남겨서 노출
    const matched = (m.sessions || []).filter(s => sessionMatches(s, q))
    if (matched.length) out.push({ ...m, sessions: matched })
  }
  return out
})

// 검색 중에는 매칭된 회의체를 자동으로 펼쳐 결과(필터된 회의)를 바로 보이게 한다
function isMtgExpanded(id) {
  return !!sidebarSearch.value.trim() || expandedMeetingIds.value.has(id)
}

const selectedMeeting = computed(() => meetings.value.find(m => m.id === selectedMeetingId.value))

// 현재 세션의 회의 참여자 수 — 세션 응답의 attendee_ids(또는 attendees) 길이
const participantCount = computed(() => {
  const a = activeSession.value?.attendee_ids ?? activeSession.value?.attendees
  return Array.isArray(a) ? a.length : 0
})

async function loadSessions(meetingId) {
  const list = await sessionsStore.loadSessions(meetingId)
  const m = meetings.value.find(m => m.id === meetingId)
  if (m) m.sessions = list
  return list
}

async function fetchMeetings() {
  loadingMeetings.value = true
  try {
    // 회의체 목록은 스토어 단일 fetch — 페이지별 중복 HTTP 호출 제거
    await meetingsStore.fetchMeetings()
    meetings.value = meetingsStore.meetings.map(m => ({ ...m, sessions: null }))
    meetings.value.forEach(m => loadSessions(m.id))
  } catch (e) {
    console.error('meetings fetch error', e)
  } finally {
    loadingMeetings.value = false
  }
}

async function selectMeeting(m) {
  if (expandedMeetingIds.value.has(m.id)) {
    expandedMeetingIds.value.delete(m.id)
    expandedMeetingIds.value = new Set(expandedMeetingIds.value)
    return
  }
  expandedMeetingIds.value = new Set([...expandedMeetingIds.value, m.id])
  selectedMeetingId.value = m.id
  await loadSessions(m.id)
}

async function enterSession(s) {
  activeSession.value = s
  activeTab.value = 'transcript'
  recordingState.value = 'idle'
  minutesSavedAt.value = null
  const rec = getOrCreateRecord(s.id)
  transcriptLines.value = rec.transcriptLines
  generatedMinutes.value = rec.generatedMinutes
  showMinutesTab.value = rec.showMinutesTab
  conversationBlocks.value = rec.conversationBlocks
  lastRefineIdx.value = rec.lastRefineIdx
  nextAgendaItems.value = rec.nextAgendaItems || []
  showNextAgendaBlock.value = rec.showNextAgendaBlock || false
  sessionContext.value = s.context || ''

  try {
    const { data } = await api.get(`/api/v1/sessions/${s.id}`)
    const full = data.data ?? data
    // 서버의 권위 있는 status로 동기화 — 목록의 stale 상태로 start/resume을 오판해
    // /start(=SCHEDULED 전용)가 ONGOING/ENDED 세션에 호출되어 400나는 것을 막는다.
    if (full.status) activeSession.value = { ...activeSession.value, status: full.status }
    // 참여자 수 표시용 — 상세 응답의 attendee_ids를 활성 세션에 반영
    if (full.attendee_ids)
      activeSession.value = { ...activeSession.value, attendee_ids: full.attendee_ids }
    if (full.summary_blocks?.length) {
      conversationBlocks.value = full.summary_blocks.map(b => ({
        title: b.title,
        bullets: b.bullets,
        recording_start_sec: b.recording_start_sec,
        recording_end_sec: b.recording_end_sec,
      }))
      lastRefineIdx.value = conversationBlocks.value.length * REFINE_EVERY
      rec.conversationBlocks = conversationBlocks.value
      rec.lastRefineIdx = lastRefineIdx.value
    }
    if (full.context) sessionContext.value = full.context
    if (full.recording_seconds != null) {
      let secs = full.recording_seconds
      if (full.last_resumed_at && full.status === 'ongoing') {
        // 서버가 elapsed 계산 (timezone 문제 없음)
        recordingState.value = 'paused'
        api
          .post(`/api/v1/sessions/${full.id}/pause`)
          .then(res => {
            const data = res.data?.data ?? res.data
            const saved = data?.recording_seconds ?? secs
            recordingSecs.value = saved
            _lastRefineEndSec = saved
          })
          .catch(() => {
            recordingSecs.value = secs
            _lastRefineEndSec = secs
          })
      } else {
        recordingSecs.value = secs
        _lastRefineEndSec = secs
      }
    }
  } catch (e) {
    console.error('세션 상세 조회 실패', e)
  }
  await nextTick()
  loadMinutesToEditor(rec.generatedMinutes?.content_summary || '')

  if (!rec.transcriptLines.length) await loadScripts(s.id)

  // DB에서 저장된 회의록 불러오기 (in-memory에 없을 때만)
  if (!rec.generatedMinutes) {
    try {
      const { data } = await apiAI.get(`/api/ai/sessions/${s.id}/minutes`)
      const minutesContent = data?.content_original || data?.content_summary
      if (minutesContent) {
        // 초안 편집본은 에디터 HTML로 저장됨 → HTML이면 그대로, (생성직후/레거시) 마크다운이면 변환
        const html = minutesContent.startsWith('<') ? minutesContent : renderMd(minutesContent)
        generatedMinutes.value = { content_summary: html }
        showMinutesTab.value = true
        rec.generatedMinutes = generatedMinutes.value
        rec.showMinutesTab = true
        await nextTick()
        loadMinutesToEditor(html)
        if (!rec.showNextAgendaBlock)
          loadDraftAgendas(s.meeting_id || s.meetingId || selectedMeeting.value?.id, s.id)
      }
    } catch {
      /* 404 = 저장된 회의록 없음, 정상 */
    }
  }
}

// ─── Recording ────────────────────────────────────────────────
const recordingState = ref('idle')
const activeTab = ref('transcript')
const transcriptLines = ref([])
const generatedMinutes = ref(null)
const showMinutesTab = ref(false)
const generatingMinutes = ref(false)
const transcriptAreaRef = ref(null)
const minutesScrollAreaRef = ref(null)
const nabHeightPercent = ref(32)

function onNabResizeStart(e) {
  e.preventDefault()
  const container = e.target.closest('.sp-tab-body')
  if (!container) return
  const startY = e.clientY
  const containerH = container.getBoundingClientRect().height
  const startPercent = nabHeightPercent.value
  const onMove = e => {
    const delta = e.clientY - startY
    nabHeightPercent.value = Math.min(60, Math.max(15, startPercent - (delta / containerH) * 100))
  }
  const onUp = () => {
    document.removeEventListener('mousemove', onMove)
    document.removeEventListener('mouseup', onUp)
  }
  document.addEventListener('mousemove', onMove)
  document.addEventListener('mouseup', onUp)
}

const editor = useEditor({
  extensions: [StarterKit, Table.configure({ resizable: false }), TableRow, TableHeader, TableCell],
  content: '',
  editable: true,
  onUpdate: ({ editor }) => {
    if (!generatingMinutes.value && generatedMinutes.value) {
      generatedMinutes.value = { ...generatedMinutes.value, content_summary: editor.getHTML() }
      if (activeSession.value) {
        getOrCreateRecord(activeSession.value.id).generatedMinutes = generatedMinutes.value
      }
      _scheduleDraftSave() // 편집 내용도 DB에 draft로 자동저장 — 닫아도 유지
    }
  },
})

function loadMinutesToEditor(content) {
  if (!editor.value) return
  if (!content) {
    editor.value.commands.clearContent()
    return
  }
  const html = content.startsWith('<') ? content : renderMd(content)
  editor.value.commands.setContent(html, false)
}

// 초안 편집 자동저장(디바운스) — 에디터 HTML을 minutes 테이블에 draft로 저장(그래프 미노출).
// 닫거나 새로고침해도 다시 조회되도록. schedule 시점에 내용을 캡처해 unmount 후 타이머가 떠도 안전.
let _draftSaveTimer = null
function _scheduleDraftSave() {
  const sid = activeSession.value?.id
  const html = generatedMinutes.value?.content_summary || '' // onUpdate가 에디터 HTML로 갱신함
  if (!sid || !html.trim()) return
  clearTimeout(_draftSaveTimer)
  _draftSaveTimer = setTimeout(() => {
    apiAI
      .post(`/api/ai/sessions/${sid}/minutes?draft=true`, {
        content: html,
        content_summary: html.replace(/<[^>]+>/g, '').slice(0, 500),
      })
      .catch(e => console.error('초안 자동저장 실패', e))
  }, 1000)
}

onUnmounted(() => editor.value?.destroy())
const showPopover = ref(null)
const transcriptLang = ref('ko')
// STT 모델 선택. 기본 = gpt-realtime-whisper. 실시간 전사 WS의 start 메시지로 전달됨.
const sttModel = ref('gpt-realtime-whisper')
const STT_MODELS = [
  { value: 'gpt-realtime-whisper', label: 'gpt-realtime-whisper' },
  { value: 'gpt-4o-transcribe', label: 'gpt-4o-transcribe' },
  { value: 'gpt-4o-mini-transcribe', label: 'gpt-4o-mini-transcribe' },
  { value: 'whisper-1', label: 'whisper-1' },
]
const micError = ref('')

const sessionRecords = ref(new Map())
function getOrCreateRecord(id) {
  if (!sessionRecords.value.has(id))
    sessionRecords.value.set(id, {
      transcriptLines: [],
      generatedMinutes: null,
      showMinutesTab: false,
      conversationBlocks: [],
      lastRefineIdx: 0,
      nextAgendaItems: [],
      showNextAgendaBlock: false,
    })
  return sessionRecords.value.get(id)
}

// ─── 대화기록 ─────────────────────────────────────────────────
const conversationBlocks = ref([])
const sessionContext = ref('')
const showContextModal = ref(false)
const contextDraft = ref('')
const lastRefineIdx = ref(0)
const refiningConversation = ref(false)
const REFINE_EVERY = 5

const unprocessedLines = computed(() => transcriptLines.value.slice(lastRefineIdx.value))

async function saveContext() {
  sessionContext.value = contextDraft.value
  showContextModal.value = false
  if (activeSession.value) {
    try {
      await api.patch(`/api/v1/sessions/${activeSession.value.id}/context`, {
        context: contextDraft.value,
      })
    } catch (e) {
      console.error('맥락 저장 실패', e)
    }
  }
}

async function refineChunk() {
  const newLines = transcriptLines.value.slice(lastRefineIdx.value)
  if (newLines.length < REFINE_EVERY || refiningConversation.value) return
  refiningConversation.value = true
  const processedIdx = lastRefineIdx.value + newLines.length
  const text = newLines.map(l => l.text).join('\n')
  try {
    const startSec = _lastRefineEndSec
    const endSec = recordingSecs.value
    const { data } = await apiAI.post('/api/ai/sessions/refine-chunk', {
      session_id: activeSession.value.id,
      text,
      context: sessionContext.value || null,
      recording_start_sec: startSec,
      recording_end_sec: endSec,
    })
    _lastRefineEndSec = endSec
    conversationBlocks.value.push({
      title: data.title,
      bullets: data.bullets,
      text,
      recording_start_sec: startSec,
      recording_end_sec: endSec,
    })
    lastRefineIdx.value = processedIdx
    if (activeSession.value) {
      const rec = getOrCreateRecord(activeSession.value.id)
      rec.conversationBlocks = conversationBlocks.value
      rec.lastRefineIdx = lastRefineIdx.value
    }
    nextTick(() => {
      if (transcriptAreaRef.value)
        transcriptAreaRef.value.scrollTop = transcriptAreaRef.value.scrollHeight
    })
  } catch (e) {
    console.error('대화기록 정제 실패', e)
  } finally {
    refiningConversation.value = false
  }
}

// 스피커 레이블 — 발화 등장 순서 기반으로 A/B/C... 동적 할당

const KST = { hour: '2-digit', minute: '2-digit', second: '2-digit', timeZone: 'Asia/Seoul' }
function nowTime() {
  return new Date().toLocaleTimeString('ko-KR', KST)
}
function utcToKst(str) {
  if (!str) return '--:--:--'
  // Spring Boot LocalDateTime은 Z 없이 오므로 UTC임을 명시
  const iso = str.endsWith('Z') || str.includes('+') ? str : str + 'Z'
  return new Date(iso).toLocaleTimeString('ko-KR', KST)
}

function _pushLine(time, text, id = null, speaker = '화자01', corrected = false) {
  const entry = { time, text, id, speaker, corrected }
  transcriptLines.value.push(entry)
  if (activeSession.value)
    getOrCreateRecord(activeSession.value.id).transcriptLines = transcriptLines.value
  // 전문용어 교정이 일어난 줄은 잠깐 무지개 글로우 → 애니메이션 후 플래그 해제(1회성)
  if (corrected) {
    setTimeout(() => {
      entry.corrected = false
    }, 2600)
  }
  nextTick(() => {
    if (transcriptAreaRef.value)
      transcriptAreaRef.value.scrollTop = transcriptAreaRef.value.scrollHeight
  })
  if (transcriptLines.value.length - lastRefineIdx.value >= REFINE_EVERY) refineChunk()
}

const partialText = ref('') // 실시간 부분 전사(미확정) — 라이브 표시 (P5)

const stt = useRealtimeSTT({
  onResult: (text, id = null, meta = {}) => {
    partialText.value = ''
    _pushLine(nowTime(), text, id, '화자01', !!meta.corrected)
  },
  onPartial: t => {
    partialText.value = t
    // 부분 전사(미확정)도 확정 줄처럼 화면 맨 아래로 따라 올라가 항상 보이도록 자동 스크롤
    nextTick(() => {
      if (transcriptAreaRef.value)
        transcriptAreaRef.value.scrollTop = transcriptAreaRef.value.scrollHeight
    })
  },
  onError: msg => {
    micError.value = msg
  },
  getLang: () => transcriptLang.value,
  getModel: () => sttModel.value,
  getSessionId: () => activeSession.value?.id ?? null,
})

// ─── 녹음 타이머 ──────────────────────────────────────────────
const recordingSecs = ref(0)
let _timerInterval = null
let _lastRefineEndSec = 0

function _startTimer() {
  if (_timerInterval) clearInterval(_timerInterval)
  _timerInterval = setInterval(() => {
    recordingSecs.value++
  }, 1000)
}
function _pauseTimer() {
  clearInterval(_timerInterval)
  _timerInterval = null
}
function _resetTimer() {
  _pauseTimer()
  recordingSecs.value = 0
  _lastRefineEndSec = 0
}
function formatTimer(s) {
  const sec = Math.floor(s)
  return `${String(Math.floor(sec / 60)).padStart(2, '0')}:${String(sec % 60).padStart(2, '0')}`
}

// ─── rec-wave 실시간 오디오 스펙트럼 ──────────────────────────────
const WAVE_BARS = 14
const waveLevels = ref(new Array(WAVE_BARS).fill(0))
let _waveRaf = null
let _waveLast = 0
function _waveTick(ts) {
  _waveRaf = requestAnimationFrame(_waveTick)
  if (ts - _waveLast < 33) return // ~30fps로 제한
  _waveLast = ts
  waveLevels.value = stt.getWaveLevels?.(WAVE_BARS) || new Array(WAVE_BARS).fill(0)
}
function startWave() {
  if (_waveRaf) return
  _waveLast = 0
  _waveRaf = requestAnimationFrame(_waveTick)
}
function stopWave() {
  if (_waveRaf) cancelAnimationFrame(_waveRaf)
  _waveRaf = null
  waveLevels.value = new Array(WAVE_BARS).fill(0) // 녹음 중 아닐 땐 평평하게
}
// 녹음 중일 때만 실제 오디오로 막대를 구동(그 외에는 평평한 막대로 조회 시에도 표시)
watch(
  () => recordingState.value,
  st => (st === 'recording' ? startWave() : stopWave()),
)

// ─── 스크립트(발화) 로더 — 세션 진입 시 저장된 발화 세그먼트를 불러온다 ──────────
async function loadScripts(sessionId, { force = false } = {}) {
  const rec = getOrCreateRecord(sessionId)
  if (!force && rec.transcriptLines.length) return
  try {
    const { data } = await api.get(`/api/v1/sessions/${sessionId}/scripts`)
    // 실시간 녹음마다 start_sec가 0부터 재시작할 수 있어 createdAt(동률이면 id)으로 정렬한다.
    const lines = (data || [])
      .slice()
      .sort(
        (a, b) =>
          String(a.createdAt || '').localeCompare(String(b.createdAt || '')) ||
          (a.id || 0) - (b.id || 0),
      )
      .map(seg => {
        const raw = seg.speakerLabel || '화자01'
        const clevel = raw.startsWith('[C]')
        return {
          id: seg.id,
          time: utcToKst(seg.createdAt),
          text: seg.content,
          speaker: clevel ? raw.slice(3) : raw,
          clevel,
        }
      })
    rec.transcriptLines = lines
    if (activeSession.value?.id === sessionId) transcriptLines.value = lines
  } catch (e) {
    console.error('STT 세그먼트 로드 실패', e)
  }
}

// ─── 발화 편집 ────────────────────────────────────────────────
const editingIdx = ref(null)
const editDraft = ref({ text: '', speaker: '', isClevel: false })

function startEdit(idx) {
  const line = transcriptLines.value[idx]
  editingIdx.value = idx
  editDraft.value = { text: line.text, speaker: line.speaker === '화자01' ? '' : (line.speaker || ''), isClevel: !!line.clevel }
}
function cancelEdit() {
  editingIdx.value = null
}
async function saveEdit(idx) {
  const line = transcriptLines.value[idx]
  if (!line.id) return
  const speaker = (editDraft.value.speaker || '').trim() || '화자01'
  const speakerLabel = editDraft.value.isClevel ? `[C]${speaker}` : speaker
  await api.patch(`/api/v1/sessions/${activeSession.value.id}/scripts`, {
    segments: [{ id: line.id, content: editDraft.value.text, speakerLabel }],
  })
  line.text = editDraft.value.text
  line.speaker = speaker
  line.clevel = editDraft.value.isClevel
  editingIdx.value = null
  refreshSummaryBlock(line.id)
}

async function refreshSummaryBlock(segmentId) {
  try {
    const { data } = await apiAI.post(
      `/api/ai/sessions/${activeSession.value.id}/blocks/refresh`,
      { segment_id: segmentId }
    )
    if (data.ok && data.block_index != null) {
      const blocks = conversationBlocks.value
      if (blocks[data.block_index]) {
        blocks[data.block_index] = {
          title: data.title,
          bullets: data.bullets,
          recording_start_sec: data.recording_start_sec,
          recording_end_sec: data.recording_end_sec,
        }
        conversationBlocks.value = [...blocks]
        const rec = getOrCreateRecord(activeSession.value.id)
        rec.conversationBlocks = conversationBlocks.value
      }
    }
  } catch {}
}

// ─── 화자별 뱃지 색상 ─────────────────────────────────────────────────────────
// 화자 라벨마다 구분되는 색을 부여한다. '화자0N'은 N 순번으로, 그 외 라벨은 문자 해시로
// 안정적으로 팔레트에 매핑한다(같은 라벨 → 항상 같은 색).
const SPEAKER_COLORS = [
  { bg: 'rgba(96, 165, 250, 0.16)', fg: '#2563eb' }, // 파랑
  { bg: 'rgba(52, 211, 153, 0.16)', fg: '#059669' }, // 초록
  { bg: 'rgba(251, 146, 60, 0.18)', fg: '#ea580c' }, // 주황
  { bg: 'rgba(167, 139, 250, 0.18)', fg: '#7c3aed' }, // 보라
  { bg: 'rgba(244, 114, 182, 0.16)', fg: '#db2777' }, // 분홍
  { bg: 'rgba(45, 212, 191, 0.16)', fg: '#0d9488' }, // 청록
  { bg: 'rgba(250, 204, 21, 0.20)', fg: '#a16207' }, // 노랑
  { bg: 'rgba(248, 113, 113, 0.16)', fg: '#dc2626' }, // 빨강
]
function speakerStyle(label) {
  if (!label) return {}
  const m = String(label).match(/(\d+)/)
  let idx
  if (m) idx = parseInt(m[1], 10) - 1
  else {
    idx = 0
    for (const ch of String(label)) idx += ch.charCodeAt(0)
  }
  const n = SPEAKER_COLORS.length
  const c = SPEAKER_COLORS[((idx % n) + n) % n]
  return { background: c.bg, color: c.fg }
}

function toggleRecording() {
  micError.value = ''
  if (recordingState.value === 'idle') {
    stt
      .start()
      .then(() => {
        recordingState.value = 'recording'
        if (activeSession.value?.id) {
          const isOngoing = activeSession.value.status === 'ongoing'
          const endpoint = isOngoing ? 'resume' : 'start'
          api
            .post(`/api/v1/sessions/${activeSession.value.id}/${endpoint}`)
            .then(res => {
              const data = res.data?.data ?? res.data
              if (data?.status)
                activeSession.value = { ...activeSession.value, status: data.status }
              recordingSecs.value = data?.recording_seconds ?? recordingSecs.value
              _startTimer()
            })
            .catch(() => {
              _startTimer()
            })
        } else {
          _startTimer()
        }
      })
      .catch(() => {
        micError.value = '마이크 권한이 필요합니다. 브라우저 설정을 확인해 주세요.'
      })
  } else if (recordingState.value === 'recording') {
    recordingState.value = 'paused'
    stt.stop()
    _pauseTimer()
    if (activeSession.value?.id) {
      api
        .post(`/api/v1/sessions/${activeSession.value.id}/pause`)
        .then(res => {
          const data = res.data?.data ?? res.data
          if (data?.recording_seconds != null) recordingSecs.value = data.recording_seconds
        })
        .catch(() => {})
    }
  } else {
    stt
      .start()
      .then(() => {
        if (activeSession.value?.id) {
          api
            .post(`/api/v1/sessions/${activeSession.value.id}/resume`)
            .then(res => {
              recordingSecs.value = res.data?.data?.recording_seconds ?? recordingSecs.value
              recordingState.value = 'recording'
              _startTimer()
            })
            .catch(() => {
              recordingState.value = 'recording'
              _startTimer()
            })
        } else {
          recordingState.value = 'recording'
          _startTimer()
        }
      })
      .catch(() => {
        micError.value = '마이크 권한이 필요합니다.'
      })
  }
}

function stopRecording() {
  recordingState.value = 'idle'
  // 기록 종료 — 실시간 전사를 종료하고 마이크를 완전히 해제한다.
  stt.stop({ finalize: true })
  _resetTimer()
}

async function generateMinutes() {
  if (generatingMinutes.value) return
  if (activeSession.value?.status === 'ongoing') {
    showOngoingWarning.value = true
    setTimeout(() => { showOngoingWarning.value = false }, 10000)
    return
  }
  generatingMinutes.value = true
  showMinutesTab.value = true
  activeTab.value = 'minutes'
  nextAgendaItems.value = []
  showNextAgendaBlock.value = false

  const sessionTitle = activeSession.value?.title || '회의'
  // 같은 발화자의 연속 발화를 하나로 합치기
  const transcriptText = transcriptLines.value.map(l => l.text).join('\n')

  // ── 우측 채팅에 AI 사고 과정 표시 (완료 메시지는 생성 후 추가) ──
  wmMessages.value.push({ role: 'user', content: `"${sessionTitle}" 회의록을 생성해줘` })
  const thinkingMsg = { role: 'thinking', steps: [], open: true, done: false }
  wmMessages.value.push(thinkingMsg)
  wmLoading.value = true
  await nextTick()
  const sttCount = transcriptLines.value.length
  const thinkingSteps = [
    `대화 기록 ${sttCount}개 발화 분석 중...`,
    `핵심 논의 및 방향 추출 중...`,
    `결정 사항 및 액션 아이템 정리 중...`,
    `회의록 초안 구성 중...`,
  ]
  await _runThinkingSteps(thinkingMsg, thinkingSteps)
  const agentMsg = reactive({ role: 'agent', content: '회의록을 생성하고 있습니다...' })
  wmMessages.value.push(agentMsg)
  await nextTick()

  let minutesContent = ''
  generatedMinutes.value = { content_summary: '' }
  // 재생성 시 기존 초안이 아래로 덧붙는 현상 방지 — 에디터를 먼저 비운다.
  editor.value?.commands.clearContent()

  try {
    await streamPost(
      '/api/agent/minutes/generate-minutes',
      {
        meeting_id: activeSession.value?.meeting_id || 0,
        session_id: activeSession.value?.id || null,
        message: transcriptText,
        chat_history: [],
      },
      chunk => {
        minutesContent += chunk
        generatedMinutes.value = { ...generatedMinutes.value, content_summary: minutesContent }
        nextTick(() => {
          if (minutesScrollAreaRef.value)
            minutesScrollAreaRef.value.scrollTop = minutesScrollAreaRef.value.scrollHeight
        })
      },
      async () => {
        let html = ''
        try {
          html = renderMd(minutesContent)
          generatedMinutes.value = {
            content_summary: html,
            sources: {
              stt_count: sttCount,
              session_title: sessionTitle,
              transcript: [...transcriptLines.value],
            },
          }
          if (activeSession.value) {
            const rec = getOrCreateRecord(activeSession.value.id)
            rec.generatedMinutes = generatedMinutes.value
            rec.showMinutesTab = true
            // 초안 자동 저장(draft) — 새로고침/탭 이동에도 유지되도록 minutes 테이블에 저장한다.
            // content_original에 마크다운 원문을 넣어 재진입 시 renderMd로 복원(그래프엔 미노출).
            apiAI
              .post(`/api/ai/sessions/${activeSession.value.id}/minutes?draft=true`, {
                content: minutesContent,
                content_summary: minutesContent.slice(0, 500),
              })
              .catch(e => console.error('초안 자동저장 실패', e))
          }
          agentMsg.content = `회의록 생성이 완료되었습니다.\n\n📄 **${sessionTitle}** 회의록이 회의록 탭에 저장되었습니다.\n\n결정 사항이나 액션 아이템에 대해 더 궁금한 점이 있으면 질문해 주세요.`
          wmLoading.value = false
        } catch (e) {
          console.error('[generateMinutes onDone]', e)
          agentMsg.content = '회의록 생성 중 오류가 발생했습니다.'
          wmLoading.value = false
        } finally {
          generatingMinutes.value = false // 먼저 editor-content를 DOM에 마운트
          await nextTick() // 마운트 완료 대기
          if (html) loadMinutesToEditor(html) // 마운트된 에디터에 내용 설정
          extractNextAgendas()
        }
      },
    )
  } catch {
    agentMsg.content = '회의록 생성 중 오류가 발생했습니다.'
    generatedMinutes.value = {
      content_summary: '회의록 생성 중 오류가 발생했습니다. 다시 시도해주세요.',
    }
    wmLoading.value = false
    generatingMinutes.value = false
  }
}

function downloadPDF() {
  const html = editor.value?.getHTML() || generatedMinutes.value?.content_summary || ''
  const title = activeSession.value?.title || '회의록'
  const w = window.open('', '_blank')
  if (!w) return
  w.document.write(`<!DOCTYPE html><html><head>
    <meta charset="utf-8"><title>${title}</title>
    <style>
      body{font-family:'Malgun Gothic',Arial,sans-serif;font-size:12px;line-height:1.7;color:var(--dark-card);padding:40px;max-width:820px;margin:0 auto}
      h1{font-size:20px;font-weight:800;border-bottom:2px solid #e2e8f0;padding-bottom:10px;margin-bottom:16px}
      h2{font-size:16px;font-weight:700;color:#1e40af;margin-top:20px;margin-bottom:6px}
      h3{font-size:14px;font-weight:700;color:var(--text-muted);margin-top:12px;margin-bottom:4px}
      p{margin:0 0 6px}ul,ol{padding-left:20px;margin:4px 0}li{margin-bottom:2px}
      table{width:100%;border-collapse:collapse;margin:8px 0;font-size:12px}
      th,td{border:1px solid #e2e8f0;padding:6px 10px;text-align:left}th{background:var(--surface-2);font-weight:600}
      hr{border:none;border-top:1px solid #e2e8f0;margin:14px 0}
      @media print{body{padding:20px}}
    

.wm-feedback { display:flex; gap:4px; margin:3px 0 6px 2px; }
.wm-suggested { display:flex; flex-wrap:wrap; gap:6px; margin:8px 0 4px 2px; }
.wm-suggested-btn {
  font-size:12px; padding:4px 10px; border:1px solid var(--border,#3a3a3a);
  border-radius:14px; background:transparent; color:var(--dark-muted,#aaa); cursor:pointer;
}
.wm-suggested-btn:hover:not(:disabled) { border-color:var(--primary,var(--indigo)); color:var(--dark-text,#eee); }
.wm-suggested-btn:disabled { opacity:.4; cursor:default; }
</style>
  </head><body>${html}</body></html>`)
  w.document.close()
  setTimeout(() => {
    w.focus()
    w.print()
  }, 400)
}

const savingMinutes = ref(false)
const showOngoingWarning = ref(false)
const minutesSavedAt = ref(null)

// ── 다음 회의 과제 승인/반려 블록 ─────────────────────────────
const nextAgendaItems = ref([])
const showNextAgendaBlock = ref(false)
const nextAgendaExtracting = ref(false)
const nabCollapsed = ref(false)

const cleanStr = v => (v && v !== 'null' && v !== 'NULL' ? String(v).trim() : '')

async function loadDraftAgendas(meetingId, sessionId) {
  if (!meetingId) return
  try {
    const params = sessionId ? `?session_id=${sessionId}` : ''
    const { data } = await apiAI.get(`/api/agent/meetings/${meetingId}/draft-agendas${params}`)
    if (!data?.length) return
    nextAgendaItems.value = data.map(a => {
      const dept = Array.isArray(a.department) ? a.department[0] || '' : a.department || ''
      const company = cleanStr(a.company)
      return {
        title: a.title || '',
        company,
        dept,
        db_id: a.db_id,
        start_date: a.start_date || null,
        end_date: a.due_date || null,
        _agentLogId: null,
        _state: null,
        _reason: '',
        _showReason: false,
        _editing: false,
        _editTitle: a.title || '',
        _editCompany: company,
        _editDept: dept,
        _editStartDate: a.start_date || null,
        _editEndDate: a.due_date || null,
      }
    })
    showNextAgendaBlock.value = true
    if (activeSession.value) {
      const rec = getOrCreateRecord(activeSession.value.id)
      rec.nextAgendaItems = nextAgendaItems.value
      rec.showNextAgendaBlock = true
    }
  } catch {
    /* 과제 없음, 정상 */
  }
}

async function extractNextAgendas() {
  const meetingId = activeSession.value?.meeting_id || selectedMeeting.value?.id || 0
  if (!meetingId) return

  nextAgendaExtracting.value = true
  nextAgendaItems.value = []
  showNextAgendaBlock.value = true
  try {
    const formData = new FormData()
    formData.append('meeting_id', String(meetingId))
    // 출처 회의록 세션(B안) — 추출 아젠다를 이 세션의 회의록과 연결(minutes↔agenda 조인 근거)
    if (activeSession.value?.id) formData.append('session_id', String(activeSession.value.id))

    // content_summary 있으면 현재 회의록을 파일로 첨부
    if (generatedMinutes.value?.content_summary) {
      const parser = new DOMParser()
      const doc = parser.parseFromString(generatedMinutes.value.content_summary, 'text/html')
      const plainText = doc.body.textContent || generatedMinutes.value.content_summary
      const blob = new Blob([plainText], { type: 'text/plain' })
      formData.append('files', blob, '현재_회의록.txt')
    }
    // content_summary 없어도 meeting_id만으로 추출 시도 (백엔드가 DB에서 회의록 파일 직접 읽음)

    const { data } = await apiAI.post('/api/agent/archive/extract-agendas', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    const agentLogId = data?.agent_log_id || null
    const items = data?.agendas || []
    const toNounTitle = t =>
      (t || '')
        .replace(/\s*(검토\s*)?결과\s*보고\s*$/, '')
        .replace(/\s*보고\s*$/, '')
        .replace(/\s*논의\s*$/, '')
        .replace(/\s*수립\s*$/, '')
        .replace(/\s*확인\s*$/, '')
        .replace(/\s*예정\s*$/, '')
        .replace(/\s*완료\s*$/, '')
        .trim()
    nextAgendaItems.value = items.map(a => {
      const title = toNounTitle(a.title || a.content || '')
      const company = cleanStr(a.company)
      const dept = a.department || a.dept || a.assignee_dept || ''
      return {
        title,
        company,
        dept,
        db_id: a.db_id || null,
        start_date: a.start_date || null,
        end_date: a.due_date || null,
        _agentLogId: agentLogId,
        _state: null,
        _reason: '',
        _showReason: false,
        _editing: false,
        _editTitle: title,
        _editCompany: company,
        _editDept: dept,
        _editStartDate: a.start_date || null,
        _editEndDate: a.due_date || null,
      }
    })
    if (!nextAgendaItems.value.length) {
      nextAgendaItems.value = [
        {
          title: '다음 회의 아젠다를 입력해주세요',
          company: '',
          dept: '',
          db_id: null,
          start_date: null,
          end_date: null,
          _agentLogId: null,
          _state: null,
          _reason: '',
          _showReason: false,
          _editing: false,
          _editTitle: '',
          _editCompany: '',
          _editDept: '',
          _editStartDate: null,
          _editEndDate: null,
        },
      ]
    }
  } catch {
    nextAgendaItems.value = [
      {
        title: '다음 회의 아젠다를 입력해주세요',
        company: '',
        dept: '',
        db_id: null,
        start_date: null,
        end_date: null,
        _agentLogId: null,
        _state: null,
        _reason: '',
        _showReason: false,
        _editing: false,
        _editTitle: '',
        _editCompany: '',
        _editDept: '',
        _editStartDate: null,
        _editEndDate: null,
      },
    ]
  } finally {
    nextAgendaExtracting.value = false
    if (activeSession.value) {
      const rec = getOrCreateRecord(activeSession.value.id)
      // 실제 항목(db_id 있는 것)이 있을 때만 block 캐시
      const hasRealItems = nextAgendaItems.value.some(a => a.db_id)
      rec.nextAgendaItems = hasRealItems ? nextAgendaItems.value : []
      rec.showNextAgendaBlock = hasRealItems
      if (!hasRealItems) showNextAgendaBlock.value = false
    }
  }
}

function addNextAgendaItem() {
  nextAgendaItems.value.unshift({
    title: '',
    company: '',
    dept: '',
    db_id: null,
    start_date: null,
    end_date: null,
    _agentLogId: null,
    _state: null,
    _reason: '',
    _showReason: false,
    _editing: true,
    _directAdd: true,
    _editTitle: '',
    _editCompany: '',
    _editDept: '',
    _editStartDate: null,
    _editEndDate: null,
  })
}

async function removeNextAgendaItem(i) {
  const item = nextAgendaItems.value[i]
  const meetingId =
    activeSession.value?.meeting_id ||
    activeSession.value?.meetingId ||
    selectedMeeting.value?.id ||
    0
  if (item?.db_id && meetingId) {
    try {
      await apiAI.post('/api/agent/archive/agendas/commit', {
        meeting_id: meetingId,
        approved: [],
        rejected_ids: [item.db_id],
      })
    } catch (e) {
      console.warn('[removeNextAgendaItem] draft 삭제 실패:', e)
    }
  }
  nextAgendaItems.value.splice(i, 1)
}

async function saveApprovedNextAgendas() {
  const approved = nextAgendaItems.value.filter(a => a._state === 'approved')
  const rejected = nextAgendaItems.value.filter(a => a._state === 'rejected' && a.db_id)
  if (!approved.length && !rejected.length) return

  // SpringBoot는 camelCase로 반환하므로 양쪽 모두 체크
  const meetingId =
    activeSession.value?.meeting_id ||
    activeSession.value?.meetingId ||
    selectedMeeting.value?.id ||
    0
  const myRole = meetingsStore.meetingRoles?.[selectedMeetingId.value]
  if (!authStore.isStrategicTeam && myRole !== 'admin') {
    toast.error('간사만 승인 저장할 수 있습니다', { duration: 1500 })
    return
  }
  if (!meetingId) {
    toast.error('회의체 정보를 찾을 수 없습니다.')
    return
  }

  try {
    await apiAI.post('/api/agent/archive/agendas/commit', {
      meeting_id: meetingId,
      approved: approved.map(a => ({
        db_id: a.db_id || null,
        title: a.title,
        dept: a.dept || null,
        start_date: a.start_date || null,
        due_date: a.end_date || null,
      })),
      rejected_ids: rejected.map(a => a.db_id),
    })
    // 승인된 아젠다를 에디터 섹션에 주입
    if (editor.value && approved.length) {
      let html = editor.value.getHTML()

      // 4. 액션 아이템 → 표로 주입 (담당자=부서, 내용=제목, 기한=마감일)
      const tableRows = approved.map(a => {
        const dept = a._editDept || a.dept || '-'
        const date = a._editEndDate || a.end_date || '-'
        return `<tr><td><p>${dept}</p></td><td><p>${a.title}</p></td><td><p>${date}</p></td></tr>`
      }).join('')
      const tableHtml = `<table><tbody><tr><th><p>담당자</p></th><th><p>내용</p></th><th><p>기한</p></th></tr>${tableRows}</tbody></table>`
      html = html.replace(
        /(<h2[^>]*>(?:.*?액션 아이템.*?)<\/h2>)([\s\S]*?)(?=<h2|$)/,
        `$1${tableHtml}`,
      )

      // 5. 다음 회의 아젠다 → bullet으로 주입
      const bulletHtml = `<ul>${approved.map(a => `<li><p>${a.title}</p></li>`).join('')}</ul>`
      html = html.replace(
        /(<h2[^>]*>(?:.*?다음 회의 아젠다.*?)<\/h2>)([\s\S]*?)(?=<h2|$)/,
        `$1${bulletHtml}`,
      )

      loadMinutesToEditor(html)
      if (generatedMinutes.value) {
        generatedMinutes.value = { ...generatedMinutes.value, content_summary: html }
        if (activeSession.value) getOrCreateRecord(activeSession.value.id).generatedMinutes = generatedMinutes.value
      }
    }
    nextAgendaItems.value = []
    showNextAgendaBlock.value = false
    if (activeSession.value) {
      const rec = getOrCreateRecord(activeSession.value.id)
      rec.nextAgendaItems = []
      rec.showNextAgendaBlock = false
    }
  } catch (e) {
    console.error('[saveApprovedNextAgendas]', e)
    toast.error(
      '저장에 실패했습니다: ' + (e?.response?.data?.detail || e?.message || '알 수 없는 오류'),
    )
  }
}

async function saveMinutesToDB() {
  if (!activeSession.value) return
  if (activeSession.value?.status === 'ongoing') {
    showOngoingWarning.value = true
    setTimeout(() => { showOngoingWarning.value = false }, 10000)
    return
  }
  if (!generatedMinutes.value?.content_summary) {
    toast.error('회의록을 먼저 생성해주세요.', { icon: false })
    return
  }
  savingMinutes.value = true
  try {
    const sessionId = activeSession.value.id
    const meetingId = activeSession.value.meeting_id || activeSession.value.meetingId
    const html = editor.value?.getHTML() || generatedMinutes.value.content_summary
    const fd = new FormData()
    fd.append('content', html)
    await apiAI.post(`/api/upload/minutes/${sessionId}`, fd, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    minutesSavedAt.value = new Date().toLocaleTimeString('ko-KR', {
      hour: '2-digit',
      minute: '2-digit',
    })
    if (activeSession.value?.status !== 'archived') {
      await api.post(`/api/v1/sessions/${sessionId}/archive`)
      if (activeSession.value) activeSession.value.status = 'archived'
    }
    // 사이드바 세션 목록 업데이트
    if (meetingId && sessionsCache.value[meetingId]) {
      const s = sessionsCache.value[meetingId].find(s => s.id === sessionId)
      if (s) s.status = 'archived'
    }
  } catch (e) {
    const msg = e?.response?.data?.detail || e?.message || '알 수 없는 오류'
    toast.error(`저장에 실패했습니다: ${msg}`)
  } finally {
    savingMinutes.value = false
  }
}

async function deleteMinutes() {
  if (!(await confirmDialog('작성된 회의록을 삭제하시겠습니까?', { danger: true }))) return
  generatedMinutes.value = null
  showMinutesTab.value = false
  editor.value?.commands.clearContent()
  if (activeSession.value) {
    const rec = getOrCreateRecord(activeSession.value.id)
    rec.generatedMinutes = null
    rec.showMinutesTab = false
    try {
      await apiAI.delete(`/api/ai/sessions/${activeSession.value.id}/minutes`)
    } catch {
      /* 404(없는 경우) 무시 */
    }
  }
}

async function endMeeting() {
  // UX-26: 녹음을 시작한 적 없으면(대기 상태+0초) 잘못 누른 것 — 안내 후 중단
  if (recordingState.value === 'idle' && recordingSecs.value === 0) {
    toast.info('아직 녹음을 시작하지 않았습니다. 먼저 녹음을 시작해주세요.')
    return
  }
  if (!(await confirmDialog('기록을 종료하시겠습니까?'))) return
  const sessionId = activeSession.value?.id
  const meetingId = activeSession.value?.meeting_id
  stopRecording()
  if (sessionId) {
    await api.post(`/api/v1/sessions/${sessionId}/end`).catch(() => {})
    if (meetingId && sessionsCache.value[meetingId]) {
      const s = sessionsCache.value[meetingId].find(s => s.id === sessionId)
      if (s) s.status = 'ended'
    }
    activeSession.value = { ...activeSession.value, status: 'ended' }
  }
  // 회의록 탭으로 자동 전환하지 않는다 — 발화(스크립트) 탭으로 이동한다.
  showMinutesTab.value = true
  activeTab.value = 'script'
}

function togglePopover(name) {
  showPopover.value = showPopover.value === name ? null : name
}

// ─── Agent (워크메이트 AI / Supervisor) ─────────────────────────────────────
const wmMessages = ref([
  {
    role: 'agent',
    content:
      '안녕하세요! 워크메이트 AI입니다 😊\n회의 내용에 대해 무엇이든 질문하세요.\n예: "오늘 회의를 요약해줘", "결정 사항 정리해줘"',
  },
])
const wmInput = ref('')
const wmLoading = ref(false)
const messagesEl = ref(null)

// ─── @ 멘션 (아카이브 그래프 전체 노드 검색, 공통 컴포저블) ─────
const wmTextareaEl = ref(null)
const wmComposerRef = ref(null)
const mentionMeetings = ref([])
const mentionMembers = ref([])
const mentionTasks = ref([])

async function loadMentionGraph() {
  try {
    const { data } = await apiAI.get('/api/neo4j/archive')
    mentionMeetings.value = data?.meetings || []
    mentionMembers.value = (data?.meetings || []).flatMap(m => m.members || [])
    mentionTasks.value = (data?.meetings || []).flatMap(m => m.tasks || [])
  } catch {
    /* 그래프 미연결 시 @멘션은 비활성 */
  }
}

const sessionMemberCompanies = computed(() => [
  ...new Set((mentionMembers.value || []).map(mb => mb.company || '').filter(Boolean)),
])
const sessionMemberDepts = computed(() => [
  ...new Set(
    (mentionMembers.value || []).map(mb => mb.department || mb.dept || '').filter(Boolean),
  ),
])

function wmAutoResize() {
  const el = wmTextareaEl.value
  if (!el) return
  el.style.height = '36px'
  el.style.height = Math.min(el.scrollHeight, 100) + 'px'
}

const {
  atMenuOpen,
  atHighlight,
  mentionedContexts,
  AT_TYPE_LABELS,
  atMenuItems,
  onAgentInput: onWmInput,
  selectAtItem: selectWmAtItem,
  removeMentionCtx: removeWmCtx,
  setAutoContext: setWmAutoContext,
  setCtxPinned: setWmCtxPinned,
  handleMentionKeydown: handleWmMentionKeydown,
  consumeMentionContext: consumeWmMention,
} = useAgentMention({
  meetings: mentionMeetings,
  membersData: mentionMembers,
  tasksData: mentionTasks,
  agentInput: wmInput,
  agentTextareaEl: wmTextareaEl,
  autoResize: wmAutoResize,
})

// ─── 회의 AI 채팅 히스토리 (session_{session_id} 스레드) ──────
const _WM_GREETING =
  '안녕하세요! 워크메이트 AI입니다 😊\n회의 내용에 대해 무엇이든 질문하세요.\n예: "오늘 회의를 요약해줘", "결정 사항 정리해줘"'

// 회의 채팅 추천 문구 — 세션 status별로 다름
const WM_SUGGESTIONS = computed(() => {
  switch (activeSession.value?.status) {
    case 'scheduled': return ['참석자 알려줘', '안건이 뭐야?', '언제 어디서 해?']
    case 'ongoing':   return ['지금까지 뭐 얘기했어?', '현재 안건이 뭐야?']
    case 'ended':     return ['지금까지 뭐 얘기했어?', '안건이 뭐였어?', '참석자 알려줘']
    case 'archived':  return ['회의 요약해줘', '결정사항 뭐야?', '액션아이템 알려줘']
    default:          return ['곧 시작하는 회의 있어?', '내 회의 일정 알려줘']
  }
})

// 피드백 버튼 시각 상태 (active 시 색·배경) — AgentSidebar와 동일 방식
function fbBtnStyle(active, color) {
  return {
    border: 'none',
    borderRadius: '6px',
    padding: '1px 5px',
    cursor: 'pointer',
    display: 'inline-flex',
    alignItems: 'center',
    lineHeight: '1',
    background: active ? color + '22' : 'none',
    color: active ? color : 'rgb(147,197,253)',
    opacity: active ? 1 : 0.5,
  }
}

async function sendWmFeedback(msg, rating) {
  if (msg._fb === rating) return
  let reason = null
  if (rating === -1) reason = (await promptDialog('어떤 점이 아쉬웠나요? (선택)')) || null
  msg._fb = rating
  try {
    await apiAI.post('/api/agent/feedback', {
      thread_id: _wmThreadId(),
      rating,
      reason,
      content_snippet: (msg.content || '').slice(0, 300),
    })
  } catch {
    /* 피드백 실패는 무시 */
  }
}

function _wmThreadId() {
  return activeSession.value?.id ? `session_${activeSession.value.id}` : null
}

async function wmLoadHistory() {
  const sid = activeSession.value?.id
  if (!sid) {
    wmMessages.value = [{ role: 'agent', content: _WM_GREETING }]
    return
  }
  try {
    const res = await apiAI.get(`/api/chats/sessions/${sid}`)
    const messages = Array.isArray(res.data) ? res.data : []
    wmMessages.value = messages.length
      ? messages.map(m => ({ role: m.role === 'assistant' ? 'agent' : m.role, content: m.content }))
      : [{ role: 'agent', content: _WM_GREETING }]
    await nextTick()
    requestAnimationFrame(() => {
      if (messagesEl.value) messagesEl.value.scrollTop = messagesEl.value.scrollHeight
    })
  } catch {
    wmMessages.value = [{ role: 'agent', content: _WM_GREETING }]
  }
}

async function wmClearHistory() {
  const sid = activeSession.value?.id
  if (sid) {
    try {
      await apiAI.delete(`/api/chats/sessions/${sid}`)
    } catch {}
  }
  wmMessages.value = [{ role: 'agent', content: _WM_GREETING }]
}

// 세션 진입/변경 시 해당 세션 채팅 히스토리 로드
watch(activeSession, s => {
  if (s) {
    wmLoadHistory()
    // 선택한 회의(sp-session-item active)를 AI 컨텍스트로 자동 선택
    setWmAutoContext({
      id: `session-${s.id}`,
      type: 'session',
      label: s.title || '회의',
      icon: '📅',
      summary: [
        '[회의] ' + (s.title || ''),
        s.location ? '장소: ' + s.location : '',
        s.scheduled_at ? '일시: ' + String(s.scheduled_at).slice(0, 16) : '',
      ]
        .filter(Boolean)
        .join('\n'),
    })
  } else {
    wmMessages.value = [{ role: 'agent', content: _WM_GREETING }]
    setWmAutoContext(null)
  }
})

// ─── 사고 과정 helper ─────────────────────────────────────────
async function _runThinkingSteps(thinkingMsg, steps, delayMs = 380) {
  for (const step of steps) {
    thinkingMsg.steps.push(step)
    await new Promise(r => setTimeout(r, delayMs))
    if (messagesEl.value) messagesEl.value.scrollTop = messagesEl.value.scrollHeight
  }
  thinkingMsg.done = true
  thinkingMsg.open = false // 완료 후 자동 접힘
}

async function sendSessionChat() {
  const text = wmInput.value.trim()
  if (!text || wmLoading.value) return
  wmInput.value = ''
  atMenuOpen.value = false
  if (wmTextareaEl.value) wmTextareaEl.value.style.height = '36px'

  // @ 참조 컨텍스트 — 화면엔 칩으로, API엔 본문에 주입
  const { block: ctxBlock, contexts: ctxSnapshot } = consumeWmMention()
  const content = `${text}${ctxBlock}`

  wmMessages.value.push({ role: 'user', content: text, contexts: ctxSnapshot })

  // 사고 과정 블록 (실시간 [THINKING] 이벤트로 채움)
  const thinkingMsg = { role: 'thinking', steps: [], open: true, done: false }
  wmMessages.value.push(thinkingMsg)
  wmLoading.value = true
  await nextTick()
  if (messagesEl.value) messagesEl.value.scrollTop = messagesEl.value.scrollHeight

  const agentMsg = { role: 'agent', content: '' }
  wmMessages.value.push(agentMsg)

  const history = wmMessages.value
    .filter(m => m.role === 'user' || m.role === 'agent')
    .slice(0, -1)
    .map(m => ({ role: m.role === 'user' ? 'user' : 'assistant', content: m.content }))
  try {
    const endpoint = activeSession.value?.id
      ? '/api/agent/session/chat'
      : '/api/agent/supervisor/chat'
    await streamPost(
      endpoint,
      {
        thread_id: _wmThreadId(),
        meeting_id: selectedMeeting.value?.id || 0,
        session_id: activeSession.value?.id || null,
        message: content,
        chat_history: history,
        model: selectedModel.value || undefined,
      },
      chunk => {
        agentMsg.content += chunk
        if (messagesEl.value) messagesEl.value.scrollTop = messagesEl.value.scrollHeight
      },
      () => {
        thinkingMsg.done = true
        thinkingMsg.open = false
        wmLoading.value = false
      },
      step => {
        thinkingMsg.steps.push(step)
        nextTick(() => {
          if (messagesEl.value) messagesEl.value.scrollTop = messagesEl.value.scrollHeight
        })
      },
    )
  } catch {
    agentMsg.content = '응답 중 오류가 발생했습니다.'
    thinkingMsg.done = true
    thinkingMsg.open = false
    wmLoading.value = false
  }
}

function onWmKeydown(e) {
  if (handleWmMentionKeydown(e)) return
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    sendSessionChat()
  }
}

const formatDate = d => formatDateTimeShort(d, '일정 미정')

const STATUS_LABEL = {
  scheduled: '예정',
  ongoing: '진행중',
  ended: '회의록 미생성',
  archived: '종료',
}

// ─── Session edit modal ───────────────────────────────────────
const showEditSession = ref(false)
const currentEditSession = ref(null)

function openEditSession(s, e) {
  e.stopPropagation()
  currentEditSession.value = s
  showEditSession.value = true
}

async function onSessionEditSaved({ meetingId }) {
  if (meetingId) {
    sessionsStore.invalidate(meetingId)
    await loadSessions(meetingId)
  }
}

async function onSessionDeleted({ meetingId }) {
  if (activeSession.value && activeSession.value.meeting_id === meetingId) {
    activeSession.value = null
  }
  if (meetingId) {
    sessionsStore.invalidate(meetingId)
    await loadSessions(meetingId)
  }
  showEditSession.value = false
}

// ─── Session create modal (sidebar) ──────────────────────────
const showCreateSession = ref(false)

function openCreateSession() {
  showCreateSession.value = true
}
async function onSessionCreated({ meetingId, sessionId }) {
  sessionsStore.invalidate(meetingId)
  const list = await loadSessions(meetingId)
  // 좌측에서 해당 회의체를 펼치고, 생성한 회의를 선택해 세션 화면으로 이동한다.
  expandedMeetingIds.value = new Set([...expandedMeetingIds.value, meetingId])
  selectedMeetingId.value = meetingId
  const s = sessionId ? (list || []).find(x => x.id === sessionId) : null
  if (s) await enterSession(s)
}

onMounted(async () => {
  await fetchMeetings()
  loadMentionGraph()

  // 홈 '예정된 회의' 등에서 ?meetingId=&sessionId= 로 진입 시:
  // 해당 회의체를 펼치고(expanded) 회의를 선택해 'AI 실시간 요약' 탭을 띄운다.
  const mid = route.query.meetingId ? Number(route.query.meetingId) : null
  const sid = route.query.sessionId ? Number(route.query.sessionId) : null
  if (mid) {
    const m = meetings.value.find(x => x.id === mid)
    if (m) {
      expandedMeetingIds.value = new Set([...expandedMeetingIds.value, mid])
      selectedMeetingId.value = mid
      const list = await loadSessions(mid)
      const s = sid ? (list || []).find(x => x.id === sid) : null
      if (s) await enterSession(s) // enterSession이 activeTab='transcript'(실시간 요약)로 설정
    }
  }
})

onBeforeUnmount(() => {
  stopWave()
  if (recordingState.value === 'recording' && activeSession.value?.id) {
    _pauseTimer()
    recordingState.value = 'paused'
    api.post(`/api/v1/sessions/${activeSession.value.id}/pause`).catch(() => {})
  }
  // 페이지 이탈 시 마이크를 완전히 해제한다. 일시정지 상태로 스트림이 살아있는 경우의
  // 마이크 누수도 함께 정리한다.
  stt.release()
})

// 공통 컴포저가 마운트되면 내부 textarea를 @멘션 ref에 연결
function onWmComposerReady({ textareaEl }) {
  wmTextareaEl.value = textareaEl
}

// ─── 채팅 파일 첨부 ──────────────────────────────────────────
const chatFileUploading = ref(false)

async function sendChatFile(file) {
  if (!file || chatFileUploading.value) return
  chatFileUploading.value = true
  // 세션이 없어도 첨부 허용 — 회의체/사용자 스레드로 폴백
  const sess = activeSession.value
  const meetingId = sess?.meeting_id || selectedMeeting.value?.id || null
  const fd = new FormData()
  fd.append('file', file)
  fd.append(
    'thread_id',
    sess
      ? `session-${sess.id}`
      : meetingId
        ? `meeting-${meetingId}`
        : `user-${authStore.user?.id ?? 'anon'}`,
  )
  fd.append('context_type', sess ? 'session' : 'chat')
  if (sess) fd.append('session_id', String(sess.id))
  if (meetingId) fd.append('meeting_id', String(meetingId))
  try {
    const { data } = await apiAI.post('/api/upload/chat', fd, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    wmMessages.value.push({
      role: 'user',
      content: `[파일 첨부] ${data.file_name}`,
      filePath: data.file_path,
      fileName: data.file_name,
    })
    await nextTick()
    if (messagesEl.value) messagesEl.value.scrollTop = messagesEl.value.scrollHeight
  } catch {
    toast.error('파일 업로드에 실패했습니다.')
  } finally {
    chatFileUploading.value = false
    if (wmComposerRef.value?.fileInput) wmComposerRef.value.fileInput.value = ''
  }
}

async function downloadChatFile(filePath) {
  try {
    const { data } = await apiAI.get('/api/upload/presigned', { params: { file_path: filePath } })
    window.open(data.url, '_blank')
  } catch {
    toast.error('다운로드 링크 생성에 실패했습니다.')
  }
}
</script>

<template>
  <div
    class="sp-layout page-full-height"
    :class="{ 'day-mode': !themeStore.nightMode }"
    @click="showPopover = null"
  >
    <!-- Left: Meeting / session selector -->
    <div
      class="sp-sidebar"
      :class="{ collapsed: sidebarCollapsed }"
      :style="{ width: sidebarCollapsed ? '0px' : sidebarW + 'px' }"
    >
      <button
        class="sidebar-toggle-handle sp-toggle-handle"
        @click.stop="sidebarCollapsed = !sidebarCollapsed"
        :title="sidebarCollapsed ? '사이드바 펼치기' : '사이드바 접기'"
      >
        <svg
          width="8"
          height="14"
          viewBox="0 0 8 14"
          fill="none"
          xmlns="http://www.w3.org/2000/svg"
        >
          <path
            v-if="!sidebarCollapsed"
            d="M6 1L1 7L6 13"
            stroke="currentColor"
            stroke-width="1.8"
            stroke-linecap="round"
            stroke-linejoin="round"
          />
          <path
            v-else
            d="M2 1L7 7L2 13"
            stroke="currentColor"
            stroke-width="1.8"
            stroke-linecap="round"
            stroke-linejoin="round"
          />
        </svg>
      </button>
      <div class="sp-sidebar-inner">
        <div class="sp-sidebar-header">
          <div class="sp-header-top">
            <span class="sp-sidebar-title">회의</span>
            <button class="create-btn sm" @click.stop="openCreateSession()" title="회의 생성">
              <svg
                width="11"
                height="11"
                fill="none"
                stroke="currentColor"
                stroke-width="2.5"
                viewBox="0 0 24 24"
              >
                <path d="M12 4v16m8-8H4" />
              </svg>
              회의 생성
            </button>
          </div>
          <div class="sp-search-wrap">
            <svg
              class="sp-search-icon"
              width="12"
              height="12"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
              viewBox="0 0 24 24"
            >
              <circle cx="11" cy="11" r="8" />
              <path d="M21 21l-4.35-4.35" />
            </svg>
            <input id="sidebar-search" name="sidebar-search" v-model="sidebarSearch" class="sp-search-input" placeholder="회의 검색" />
            <button id="sidebar-search-clear" name="sidebar-search-clear" v-if="sidebarSearch" class="sp-search-clear" @click="sidebarSearch = ''">
              &times;
            </button>
            <div class="sp-filter-icon-btn-wrap">
              <button
                class="sp-filter-icon-btn"
                :class="{ active: sessionStatusFilter !== 'all' }"
                @click="showFilterDrop = !showFilterDrop"
              >
                <svg width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
                  <path d="M4 6h16M7 12h10M10 18h4"/>
                </svg>
              </button>
              <div v-if="showFilterDrop" class="sp-filter-drop">
                <button
                  v-for="tab in [{ key: 'all', label: '전체' }, { key: 'scheduled', label: '예정' }, { key: 'ongoing', label: '진행중' }, { key: 'ended', label: '종료' }]"
                  :key="tab.key"
                  class="sp-filter-drop-item"
                  :class="{ active: sessionStatusFilter === tab.key }"
                  @click="sessionStatusFilter = tab.key; showFilterDrop = false"
                >{{ tab.label }}</button>
              </div>
            </div>
          </div>
        </div>
        <div class="sp-sidebar-body">
          <div v-if="loadingMeetings" class="sp-search-empty">불러오는 중...</div>
          <div v-else-if="!filteredMeetings.length" class="sp-search-empty">
            {{ sidebarSearch ? '검색 결과 없음' : '참여 중인 회의체가 없습니다' }}
          </div>
          <div v-for="mtg in filteredMeetings" :key="mtg.id" class="sp-mtg-group">
            <div
              class="sp-mtg-header"
              @click="selectMeeting(mtg)"
              :class="{ expanded: isMtgExpanded(mtg.id) }"
            >
              <span class="lv-group-name">{{ mtg.title }}</span>
              <svg
                class="sp-mtg-chev"
                :class="{ open: isMtgExpanded(mtg.id) }"
                width="12"
                height="12"
                fill="none"
                stroke="currentColor"
                stroke-width="2"
                viewBox="0 0 24 24"
              >
                <path d="M19 9l-7 7-7-7" />
              </svg>
            </div>
            <div v-if="isMtgExpanded(mtg.id)" class="sp-session-list">
              <div
                v-if="!mtg.sessions"
                class="sp-session-item"
                style="justify-content: center; color: var(--dark-muted); font-size: 12px"
              >
                불러오는 중...
              </div>
              <div
                v-else-if="!mtg.sessions.filter(s => s.status !== 'archived' && (sessionStatusFilter === 'all' || s.status === sessionStatusFilter)).length && !mtg.sessions.filter(s => s.status === 'archived' && (sessionStatusFilter === 'all' || sessionStatusFilter === 'ended')).length"
                class="sp-session-item"
                style="justify-content: center; color: var(--dark-muted); font-size: 12px"
              >
                등록된 회의가 없습니다
              </div>
              <div
                v-for="s in (mtg.sessions || []).filter(s => s.status !== 'archived' && (sessionStatusFilter === 'all' || s.status === sessionStatusFilter))"
                :key="s.id"
                class="sp-session-item"
                :class="{ active: activeSession?.id === s.id }"
                @click="enterSession(s)"
              >
                <div class="sp-session-info">
                  <div class="sp-session-name">
                    <span class="sp-session-title-text">{{ s.title }}</span>
                    <span class="sp-session-status">{{ STATUS_LABEL[s.status] }}</span>
                  </div>
                  <div class="sp-session-meta">
                    <span v-if="s.location" class="sp-session-location"
                      ><i class="bi bi-geo-alt"></i> {{ s.location }}</span
                    >
                    <span class="sp-session-date">{{ formatDate(s.scheduled_at) }}</span>
                  </div>
                </div>
                <button class="sp-edit-btn" @click="openEditSession(s, $event)" title="편집">
                  <svg
                    width="13"
                    height="13"
                    fill="none"
                    stroke="currentColor"
                    stroke-width="2"
                    viewBox="0 0 24 24"
                  >
                    <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7" />
                    <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z" />
                  </svg>
                </button>
              </div>
              <!-- archived 세션 구분선 + 목록 -->
              <template v-if="mtg.sessions.filter(s => s.status === 'archived').length && (sessionStatusFilter === 'all' || sessionStatusFilter === 'ended')">
                <div style="margin: 4px 8px; border-top: 1px solid var(--border-color); opacity: 0.4"></div>
                <div
                  v-for="s in (mtg.sessions || []).filter(s => s.status === 'archived')"
                  :key="s.id"
                  class="sp-session-item"
                  :class="{ active: activeSession?.id === s.id }"
                  style="opacity: 0.6"
                  @click="enterSession(s)"
                >
                  <div class="sp-session-info">
                    <div class="sp-session-name">
                      <span class="sp-session-title-text">{{ s.title }}</span>
                      <span class="sp-session-status">{{ STATUS_LABEL[s.status] }}</span>
                    </div>
                    <div class="sp-session-meta">
                      <span v-if="s.location" class="sp-session-location"
                        ><i class="bi bi-geo-alt"></i> {{ s.location }}</span
                      >
                      <span class="sp-session-date">{{ formatDate(s.scheduled_at) }}</span>
                    </div>
                  </div>
                  <button class="sp-edit-btn" @click="openEditSession(s, $event)" title="편집">
                    <svg width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
                      <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7" />
                      <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z" />
                    </svg>
                  </button>
                </div>
              </template>
            </div>
          </div>
        </div>
      </div>
      <div
        v-if="!sidebarCollapsed"
        class="sidebar-resize-handle sp-resize-handle"
        @mousedown="onSidebarResizeStart"
      ></div>
    </div>

    <!-- Center: Recording panel -->
    <div class="sp-main" @click.stop>
      <!-- No session selected -->
      <div v-if="!activeSession" class="sp-no-session">
        <svg
          width="48"
          height="48"
          fill="none"
          stroke="currentColor"
          stroke-width="1.5"
          viewBox="0 0 24 24"
          style="color: #cbd5e1"
        >
          <path d="M12 14c1.66 0 3-1.34 3-3V5c0-1.66-1.34-3-3-3S9 3.34 9 5v6c0 1.66 1.34 3 3 3z" />
          <path
            d="M17 11c0 2.76-2.24 5-5 5s-5-2.24-5-5H5c0 3.53 2.61 6.43 6 6.92V21h2v-3.08c3.39-.49 6-3.39 6-6.92h-2z"
          />
        </svg>
        <p class="sp-no-session-text">좌측에서 회의를 선택하세요</p>
        <p class="sp-no-session-sub">회의를 클릭하면 녹음하고 회의록을 생성할 수 있습니다.</p>
      </div>

      <!-- Active session recording view -->
      <div v-else class="sp-panel card">
        <!-- Panel header: title + tabs -->
        <div class="sp-panel-header">
          <div class="sp-panel-title-row">
            <div class="sp-panel-title-group">
              <div class="sp-panel-title-line">
                <div class="sp-panel-title">{{ activeSession.title }}</div>
                <span
                  v-if="participantCount"
                  class="sp-participant-count"
                  title="회의 참여자 수"
                >
                  <i class="bi bi-people-fill"></i> {{ participantCount }}
                </span>
              </div>
            </div>
          </div>
          <div class="app-tabs">
            <button
              class="app-tab"
              :class="{ active: activeTab === 'transcript' }"
              @click="activeTab = 'transcript'"
            >
              AI 실시간 요약
            </button>
            <button
              class="app-tab"
              :class="{ active: activeTab === 'script' }"
              @click="activeTab = 'script'"
            >
              발화
            </button>
            <button
              class="app-tab"
              :class="{ active: activeTab === 'minutes' }"
              @click="activeTab = 'minutes'"
            >
              회의록
            </button>
          </div>
        </div>

        <!-- Tab content -->
        <div
          ref="transcriptAreaRef"
          class="sp-tab-body"
          :class="{ 'minutes-mode': activeTab === 'minutes' }"
        >
          <template v-if="activeTab === 'transcript'">
            <div v-if="!transcriptLines.length" class="sp-empty">
              <i class="bi bi-mic" style="font-size: 28px; opacity: 0.25"></i>
              <p class="text-muted small mb-0">녹음을 시작하면 대화가 실시간으로 기록됩니다.</p>
            </div>
            <!-- 완성된 블록들 — 위 -->
            <div v-for="(block, i) in conversationBlocks" :key="i" class="conv-block">
              <div class="conv-block-header">
                <span class="conv-block-title">{{ block.title }}</span>
                <span
                  v-if="block.recording_start_sec != null && block.recording_end_sec != null"
                  class="conv-block-time"
                  >{{ formatTimer(block.recording_start_sec) }} ~
                  {{ formatTimer(block.recording_end_sec) }}</span
                >
              </div>
              <div v-for="bullet in block.bullets" :key="bullet" class="conv-block-bullet">
                {{ bullet }}
              </div>
            </div>
            <!-- 미처리 원문 — 아래, 로딩 중이면 애니메이션 -->
            <div v-if="unprocessedLines.length" class="conv-raw">
              <div v-if="refiningConversation" class="conv-raw-loading-wrapper">
                <div class="conv-raw-loading-bar"></div>
              </div>
              <div v-for="(line, idx) in unprocessedLines" :key="idx" class="conv-raw-line">
                {{ line.text }}
              </div>
            </div>
          </template>

          <template v-else-if="activeTab === 'script'">
            <div v-if="!transcriptLines.length" class="sp-empty">
              <i class="bi bi-file-earmark-text" style="font-size: 28px; opacity: 0.25"></i>
              <p class="text-muted small mb-0">스크립트가 여기에 표시됩니다.</p>
            </div>
            <template v-for="(line, idx) in transcriptLines" :key="idx">
              <div v-if="editingIdx === idx" class="tline tline-editing">
                <div class="tline-head">
                  <span class="tline-time">{{ line.time }}</span>
                  <input
                    id="edit-speaker"
                    name="edit-speaker"
                    v-model="editDraft.speaker"
                    class="tline-edit-speaker"
                    placeholder="화자 이름"
                  />
                  <label class="tline-clevel-label">
                    <input type="checkbox" v-model="editDraft.isClevel" class="tline-clevel-check" />
                    <span class="tline-clevel-text">임원</span>
                  </label>
                </div>
                <div class="tline-body">
                  <textarea name="tline-edit" id="tline-edit" v-model="editDraft.text" class="tline-edit-text" rows="2" />
                  <div class="tline-edit-btns">
                    <button class="tline-save-btn" @click="saveEdit(idx)">저장</button>
                    <button class="tline-cancel-btn" @click="cancelEdit">취소</button>
                  </div>
                </div>
              </div>
              <div v-else class="tline">
                <div class="tline-head">
                  <span class="tline-time">{{ line.time }}</span>
                  <span
                    v-if="line.speaker && line.speaker !== '화자01'"
                    class="tline-speaker"
                    :style="speakerStyle(line.speaker)"
                    >{{ line.speaker }}</span
                  >
                </div>
                <div class="tline-body">
                  <span class="tline-text">{{ line.text }}</span>
                  <button
                    v-if="line.id"
                    class="tline-edit-btn"
                    @click="startEdit(idx)"
                    title="편집"
                  >
                    <i class="bi bi-pencil"></i>
                  </button>
                </div>
              </div>
            </template>
            <!-- 실시간 부분 전사 (미확정) -->
            <div v-if="partialText" class="tline" style="opacity: 0.55; font-style: italic">
              <div class="tline-head"><span class="tline-time">···</span></div>
              <div class="tline-body">
                <span class="tline-text">{{ partialText }}</span>
              </div>
            </div>
          </template>

          <template v-else-if="activeTab === 'minutes'">
            <div
              class="minutes-scroll-area"
              :class="{ 'has-nab': showNextAgendaBlock && generatedMinutes }"
              ref="minutesScrollAreaRef"
            >
              <div v-if="generatingMinutes && !generatedMinutes?.content_summary" class="sp-empty">
                <span class="spinner-border spinner-border-sm text-primary mb-2"></span>
                <p class="text-muted small">AI가 회의록을 생성 중입니다...</p>
              </div>
              <template v-else-if="generatedMinutes">
                <!-- Tiptap Toolbar -->
                <div class="tiptap-toolbar">
                  <button
                    class="tt-btn"
                    :class="{ active: editor?.isActive('bold') }"
                    @click="editor?.chain().focus().toggleBold().run()"
                    title="굵게"
                  >
                    <b>B</b>
                  </button>
                  <button
                    class="tt-btn"
                    :class="{ active: editor?.isActive('italic') }"
                    @click="editor?.chain().focus().toggleItalic().run()"
                    title="기울임"
                  >
                    <i>I</i>
                  </button>
                  <button
                    class="tt-btn"
                    :class="{ active: editor?.isActive('underline') }"
                    @click="editor?.chain().focus().toggleUnderline().run()"
                    title="밑줄"
                  >
                    <u>U</u>
                  </button>
                  <div class="tt-sep"></div>
                  <button
                    class="tt-btn"
                    :class="{ active: editor?.isActive('heading', { level: 1 }) }"
                    @click="editor?.chain().focus().toggleHeading({ level: 1 }).run()"
                  >
                    H1
                  </button>
                  <button
                    class="tt-btn"
                    :class="{ active: editor?.isActive('heading', { level: 2 }) }"
                    @click="editor?.chain().focus().toggleHeading({ level: 2 }).run()"
                  >
                    H2
                  </button>
                  <button
                    class="tt-btn"
                    :class="{ active: editor?.isActive('heading', { level: 3 }) }"
                    @click="editor?.chain().focus().toggleHeading({ level: 3 }).run()"
                  >
                    H3
                  </button>
                  <div class="tt-sep"></div>
                  <button
                    class="tt-btn"
                    :class="{ active: editor?.isActive('bulletList') }"
                    @click="editor?.chain().focus().toggleBulletList().run()"
                    title="글머리"
                  >
                    •≡
                  </button>
                  <button
                    class="tt-btn"
                    :class="{ active: editor?.isActive('orderedList') }"
                    @click="editor?.chain().focus().toggleOrderedList().run()"
                    title="번호목록"
                  >
                    1≡
                  </button>
                  <div class="tt-sep"></div>
                  <button
                    class="tt-btn"
                    @click="editor?.chain().focus().setHorizontalRule().run()"
                    title="구분선"
                  >
                    —
                  </button>
                  <div class="tt-sep"></div>
                  <button
                    class="tt-btn"
                    @click="editor?.chain().focus().undo().run()"
                    title="실행취소"
                  >
                    ↩
                  </button>
                  <button
                    class="tt-btn"
                    @click="editor?.chain().focus().redo().run()"
                    title="다시실행"
                  >
                    ↪
                  </button>
                  <div style="flex: 1"></div>
                  <span
                    v-if="generatedMinutes.sources"
                    class="tt-source-info"
                    :title="`기반 자료: 발화 ${generatedMinutes.sources.stt_count}개 · ${generatedMinutes.sources.session_title}`"
                  >
                    <i class="bi bi-mic-fill"></i> {{ generatedMinutes.sources.stt_count }}개
                  </span>
                  <div class="tt-sep" v-if="generatedMinutes.sources"></div>
                  <button
                    class="tt-btn tt-delete"
                    :disabled="generatingMinutes"
                    @click="deleteMinutes"
                    title="삭제"
                  >
                    <i class="bi bi-trash"></i>
                  </button>
                </div>

                <!-- Streaming preview (Markdown rendered) -->
                <div
                  v-if="generatingMinutes"
                  class="tiptap-content minutes-md"
                  v-html="renderMd(generatedMinutes.content_summary || '')"
                ></div>
                <!-- Tiptap Editor -->
                <editor-content v-else :editor="editor" class="tiptap-content" />
              </template>
              <div v-else class="sp-empty"><p class="text-muted small">회의록이 없습니다.</p></div>
            </div>

            <!-- ── 다음 회의 과제 승인/반려 블록 (에디터 영역 밖) ── -->
            <div
              v-if="generatedMinutes && showNextAgendaBlock && !nabCollapsed"
              class="nab-resize-handle"
              @mousedown="onNabResizeStart"
            ></div>
            <div
              v-if="generatedMinutes && showNextAgendaBlock"
              class="next-agenda-block"
              :class="{ 'nab-collapsed': nabCollapsed }"
              :style="nabCollapsed ? {} : { flex: `0 0 ${nabHeightPercent}%`, minHeight: 0 }"
            >
              <div class="nab-header">
                <div class="nab-title-row">
                  <svg
                    width="14"
                    height="14"
                    fill="none"
                    stroke="currentColor"
                    stroke-width="2"
                    viewBox="0 0 24 24"
                  >
                    <path d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2" />
                    <rect x="9" y="3" width="6" height="4" rx="1" ry="1" />
                    <path d="M9 12h6M9 16h4" />
                  </svg>
                  <span>다음 회의 아젠다</span>
                  <span class="nab-badge">회의록 기반 AI 추출</span>
                  <button
                    class="nab-collapse-btn"
                    @click="nabCollapsed = !nabCollapsed"
                    :title="nabCollapsed ? '펼치기' : '접기'"
                  >
                    <svg
                      width="12"
                      height="12"
                      fill="none"
                      stroke="currentColor"
                      stroke-width="2.5"
                      viewBox="0 0 24 24"
                    >
                      <path :d="nabCollapsed ? 'M18 15l-6-6-6 6' : 'M6 9l6 6 6-6'" />
                    </svg>
                  </button>
                </div>
                <p class="nab-desc">회의록에서 추출한 아젠다를 검토하고 승인/반려해 주세요.</p>
              </div>

              <div v-if="nextAgendaExtracting" class="nab-loading">
                <div class="nab-spinner"></div>
                <span>아젠다 추출 중...</span>
              </div>
              <template v-else-if="nextAgendaItems.length">
                <div class="nab-list">
                  <button class="nab-direct-add-btn" @click="addNextAgendaItem">
                    <svg width="10" height="10" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24">
                      <path d="M12 5v14M5 12h14" />
                    </svg>
                    아젠다 직접 추가
                  </button>
                  <AgendaReviewList
                    :items="nextAgendaItems"
                    :memberCompanies="sessionMemberCompanies"
                    :memberDepts="sessionMemberDepts"
                    :removeOnApprove="false"
                    :showFooter="true"
                    @approved="() => {}"
                    @rejected="() => {}"
                    @remove="removeNextAgendaItem"
                    @save="saveApprovedNextAgendas"
                  />
                </div>
              </template>
            </div>
          </template>
        </div>

        <!-- Control bar (AI 실시간 요약/발화 탭) -->
        <div v-if="activeTab !== 'minutes'" class="sp-ctrl-bar" @click.stop>
          <div
            v-show="!['archived', 'ended'].includes(activeSession?.status)"
            class="ctrl-group-left"
          >
            <!-- Language selector -->
            <div class="ctrl-pop-wrap">
              <button
                class="ctrl-btn ctrl-lang"
                :class="{ 'ctrl-active': showPopover === 'lang' }"
                @click.stop="togglePopover('lang')"
                title="언어"
              >
                <i class="bi bi-headphones"></i>
                <span>{{ transcriptLang === 'ko' ? '한국어' : 'English' }}</span>
                <i class="bi bi-chevron-down ctrl-chev"></i>
              </button>
              <div v-if="showPopover === 'lang'" class="ctrl-popover" @click.stop>
                <div class="cpop-title">대화기록 언어</div>
                <!-- prettier-ignore -->
                <button
                  class="cpop-opt"
                  :class="{ selected: transcriptLang === 'ko' }"
                  @click="transcriptLang = 'ko'; showPopover = null"
                >
                  🇰🇷 한국어
                </button>
                <!-- prettier-ignore -->
                <button
                  class="cpop-opt"
                  :class="{ selected: transcriptLang === 'en' }"
                  @click="transcriptLang = 'en'; showPopover = null"
                >
                  🇺🇸 English
                </button>
              </div>
            </div>

            <!-- STT 모델 선택 -->
            <div class="ctrl-pop-wrap">
              <button
                class="ctrl-btn ctrl-lang"
                :class="{ 'ctrl-active': showPopover === 'stt' }"
                @click.stop="togglePopover('stt')"
                title="STT 모델"
              >
                <i class="bi bi-soundwave"></i>
                <span>{{
                  (STT_MODELS.find(m => m.value === sttModel) || STT_MODELS[0]).label
                }}</span>
                <i class="bi bi-chevron-down ctrl-chev"></i>
              </button>
              <div v-if="showPopover === 'stt'" class="ctrl-popover" @click.stop>
                <div class="cpop-title">STT 모델</div>
                <!-- prettier-ignore -->
                <button
                  v-for="m in STT_MODELS"
                  :key="m.value || 'default'"
                  class="cpop-opt"
                  :class="{ selected: sttModel === m.value }"
                  @click="sttModel = m.value; showPopover = null"
                >
                  {{ m.label }}
                </button>
              </div>
            </div>

            <!-- Record / pause -->
            <!-- 맥락 입력 버튼 -->
            <div class="ctrl-pop-wrap">
              <!-- prettier-ignore -->
              <button
                class="ctrl-btn ctrl-lang"
                :class="{ 'ctrl-active': showContextModal }"
                @click.stop="showContextModal = true; contextDraft = sessionContext"
                title="회의 맥락 입력"
              >
                <i class="bi bi-text-left"></i>
                <span>맥락</span>
              </button>
            </div>

            <button
              class="ctrl-rec-btn"
              :class="{ recording: recordingState === 'recording' }"
              @click.stop="toggleRecording"
              :title="
                recordingState === 'idle'
                  ? '녹음 시작'
                  : recordingState === 'recording'
                    ? '일시정지'
                    : '재개'
              "
            >
              <i v-if="recordingState !== 'recording'" class="bi bi-play-fill"></i>
              <i v-else class="bi bi-pause-fill"></i>
            </button>

            <span class="rec-live" :class="{ paused: recordingState !== 'recording' }">
              <span class="rec-wave">
                <span
                  v-for="(lv, i) in waveLevels"
                  :key="i"
                  :style="{ height: (2 + lv * 16).toFixed(1) + 'px' }"
                ></span>
              </span>
              <span class="rec-timer">{{ formatTimer(recordingSecs) }}</span>
            </span>

            <button class="ctrl-end" @click.stop="endMeeting">기록 종료</button>
          </div>
          <span
            v-if="['archived', 'ended'].includes(activeSession?.status)"
            class="ctrl-ended-msg"
          >
            <i class="bi bi-check-circle"></i> 종료된 회의입니다. 회의록을 생성할 수 있습니다.
          </span>
          <div class="ctrl-group-right">
            <span v-if="micError" class="mic-error-msg">⚠ {{ micError }}</span>
          </div>
        </div>

        <!-- Minutes bar (회의록 탭) -->
        <div v-if="activeTab === 'minutes'" class="sp-minutes-bar" @click.stop>
          <div class="minutes-bar-left">
            <button
              class="mbar-btn"
              :disabled="!generatedMinutes || generatingMinutes"
              @click="downloadPDF"
            >
              <i class="bi bi-file-earmark-pdf"></i> PDF
            </button>
          </div>
          <div class="minutes-bar-right">
            <span v-if="showOngoingWarning" class="mbar-warning-label">
              발화 탭에 가서 회의를 먼저 종료해주세요
            </span>
            <span v-else-if="minutesSavedAt" class="mbar-saved-label">
              <i class="bi bi-check-circle-fill"></i> {{ minutesSavedAt }} 저장됨
            </span>
            <button
              class="mbar-btn primary"
              :disabled="savingMinutes || generatingMinutes"
              @click="saveMinutesToDB"
            >
              <i v-if="savingMinutes" class="bi bi-arrow-repeat spin"></i>
              <i v-else class="bi bi-cloud-upload"></i>
              {{ savingMinutes ? '저장 중...' : '아카이브 저장' }}
            </button>
            <button
              class="mbar-btn primary"
              :disabled="generatingMinutes"
              @click.stop="generateMinutes"
            >
              <i v-if="generatingMinutes" class="bi bi-arrow-repeat spin"></i>
              <i v-else class="bi bi-stars"></i>
              {{ generatingMinutes ? '생성 중...' : '회의록 생성' }}
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- Right: 워크메이트 AI (Supervisor) -->
    <div class="sp-agent-right-sidebar" :style="{ width: agentSidebarW + 'px' }">
      <div class="sp-agent-resize-handle" @mousedown="onAgentResizeStart"></div>
      <div class="agent-supervisor-header">
        <div class="supervisor-brand">
          <img :src="hyeanAvatar" class="supervisor-logo" alt="워크메이트 AI" />
          <div class="supervisor-brand-text">
            <span class="supervisor-title">워크메이트 AI</span>
          </div>
        </div>
        <div class="supervisor-header-actions">
          <button class="agent-new-chat-btn" @click="wmClearHistory">새 채팅</button>
        </div>
      </div>
      <div ref="messagesEl" class="agent-messages">
        <div
          v-for="(msg, i) in wmMessages"
          :key="i"
          class="agent-msg-row"
          :class="msg.role === 'thinking' ? 'planning' : msg.role"
        >
          <!-- 사고 과정 블록 -->
          <template v-if="msg.role === 'thinking'">
            <div class="agent-planning-block" :class="{ done: msg.done, open: msg.open }">
              <button class="agent-planning-toggle" @click="msg.open = !msg.open">
                <svg
                  v-if="!msg.done"
                  class="agent-planning-spinner"
                  width="12"
                  height="12"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="#00ab36"
                  stroke-width="2.5"
                >
                  <path
                    d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83"
                  />
                </svg>
                <svg
                  v-else
                  width="12"
                  height="12"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="#00ab36"
                  stroke-width="2.5"
                >
                  <path d="M9 12l2 2 4-4" />
                  <circle cx="12" cy="12" r="10" />
                </svg>
                <span class="agent-planning-label">{{
                  msg.done ? 'Knowledge Graph 조회 완료' : 'Knowledge Graph 분석 중...'
                }}</span>
                <span class="agent-planning-count">{{ msg.steps.length }} queries</span>
                <svg
                  class="agent-planning-chev"
                  :class="{ rotated: msg.open }"
                  width="11"
                  height="11"
                  fill="none"
                  stroke="currentColor"
                  stroke-width="2"
                  viewBox="0 0 24 24"
                >
                  <path d="M19 9l-7 7-7-7" />
                </svg>
              </button>
              <div v-if="msg.open" class="agent-planning-steps">
                <div
                  v-for="(step, si) in msg.steps"
                  :key="si"
                  class="agent-planning-step fade-in"
                  :class="{
                    'agent-step-cypher': step.includes('MATCH') || step.includes('RETURN'),
                    'agent-step-data':
                      !step.includes('MATCH') &&
                      (step.includes('→') ||
                        step.includes('수신') ||
                        step.includes('수집') ||
                        step.includes('발견')),
                    'agent-step-route': step.includes('위임') || step.includes('라우팅'),
                  }"
                >
                  <span
                    v-if="step.includes('MATCH') || step.includes('RETURN')"
                    class="agent-step-icon-cypher"
                  >
                    <svg
                      width="10"
                      height="10"
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      stroke-width="2"
                    >
                      <ellipse cx="12" cy="5" rx="9" ry="3" />
                      <path d="M3 5v14c0 1.66 4.03 3 9 3s9-1.34 9-3V5" />
                      <path d="M3 12c0 1.66 4.03 3 9 3s9-1.34 9-3" />
                    </svg>
                  </span>
                  <span
                    v-else-if="
                      step.includes('→') ||
                      step.includes('수신') ||
                      step.includes('수집') ||
                      step.includes('발견')
                    "
                    class="agent-step-icon-data"
                  >
                    <svg
                      width="10"
                      height="10"
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      stroke-width="2.5"
                    >
                      <circle cx="8" cy="12" r="3" />
                      <circle cx="18" cy="7" r="2" />
                      <circle cx="18" cy="17" r="2" />
                      <line x1="11" y1="11" x2="16" y2="8" />
                      <line x1="11" y1="13" x2="16" y2="16" />
                    </svg>
                  </span>
                  <span v-else class="agent-step-num">{{ si + 1 }}</span>
                  <span class="agent-step-text">{{ step }}</span>
                </div>
                <div v-if="!msg.done" class="agent-planning-step agent-step-pending">
                  <span class="agent-step-dots"><span></span><span></span><span></span></span>
                </div>
              </div>
            </div>
          </template>

          <!-- AI 응답 -->
          <template v-else-if="msg.role === 'agent' && msg.content">
            <div class="agent-msg-label">
              <img :src="hyeanAvatar" class="agent-msg-avatar" />워크메이트 AI
            </div>
            <div class="agent-bubble agent theme-supervisor" v-html="renderMd(msg.content)"></div>
            <div v-if="!(wmLoading && i === wmMessages.length - 1)" class="wm-feedback">
              <button
                class="fb-btn"
                :style="fbBtnStyle(msg._fb === 1, '#3b82f6')"
                title="도움이 됐어요"
                @click="sendWmFeedback(msg, 1)"
              >
                <svg
                  width="12"
                  height="12"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  stroke-width="2"
                  stroke-linecap="round"
                  stroke-linejoin="round"
                >
                  <path
                    d="M14 9V5a3 3 0 0 0-3-3l-4 9v11h11.28a2 2 0 0 0 2-1.7l1.38-9a2 2 0 0 0-2-2.3H14z"
                  />
                  <path d="M7 22H4a2 2 0 0 1-2-2v-7a2 2 0 0 1 2-2h3" />
                </svg>
              </button>
              <button
                class="fb-btn"
                :style="fbBtnStyle(msg._fb === -1, '#ef4444')"
                title="아쉬워요"
                @click="sendWmFeedback(msg, -1)"
              >
                <svg
                  width="12"
                  height="12"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  stroke-width="2"
                  stroke-linecap="round"
                  stroke-linejoin="round"
                >
                  <path
                    d="M10 15v4a3 3 0 0 0 3 3l4-9V5H6.72a2 2 0 0 0-2 1.7l-1.38 9a2 2 0 0 0 2 2.3H10z"
                  />
                  <path d="M17 2h3a2 2 0 0 1 2 2v7a2 2 0 0 1-2 2h-3" />
                </svg>
              </button>
            </div>
            <div v-if="i === 0 && WM_SUGGESTIONS.length" class="wm-suggested">
              <!-- prettier-ignore -->
              <button
                v-for="s in WM_SUGGESTIONS"
                :key="s"
                class="wm-suggested-btn"
                :disabled="wmLoading"
                @click="wmInput = s; sendSessionChat()"
              >
                {{ s }}
              </button>
            </div>
          </template>

          <!-- 사용자 메시지 -->
          <div v-else-if="msg.role === 'user'" class="agent-bubble user">
            <span>{{ msg.content }}</span>
            <div v-if="msg.contexts?.length" class="user-ctx-chips">
              <span v-for="c in msg.contexts" :key="c.id" class="user-ctx-chip"
                >{{ c.icon }} {{ c.label }}</span
              >
            </div>
            <button
              v-if="msg.filePath"
              class="sp-file-dl-btn"
              @click="downloadChatFile(msg.filePath)"
              title="파일 다운로드"
            >
              <svg
                width="11"
                height="11"
                fill="none"
                stroke="currentColor"
                stroke-width="2"
                viewBox="0 0 24 24"
              >
                <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4" />
                <polyline points="7 10 12 15 17 10" />
                <line x1="12" y1="15" x2="12" y2="3" />
              </svg>
            </button>
          </div>
        </div>
        <div
          v-if="
            wmLoading &&
            wmMessages[wmMessages.length - 1]?.role === 'agent' &&
            wmMessages[wmMessages.length - 1]?.content === ''
          "
          class="agent-msg-row agent"
        >
          <div class="agent-bubble agent typing"><span></span><span></span><span></span></div>
        </div>
      </div>
      <AgentComposer
        ref="wmComposerRef"
        v-model="wmInput"
        :mentioned-contexts="mentionedContexts"
        :at-menu-open="atMenuOpen"
        :at-menu-items="atMenuItems"
        v-model:at-highlight="atHighlight"
        :at-type-labels="AT_TYPE_LABELS"
        :loading="wmLoading"
        :can-send="!!wmInput.trim()"
        :attach-disabled="chatFileUploading"
        :multiple-files="false"
        @input="onWmInput"
        @keydown="onWmKeydown"
        @send="sendSessionChat"
        @select-at-item="selectWmAtItem"
        @remove-ctx="removeWmCtx"
        @pin-ctx="setWmCtxPinned"
        @file-change="e => sendChatFile(e.target.files[0])"
        @ready="onWmComposerReady"
      />
    </div>
  </div>

  <SessionEditModal
    :show="showEditSession"
    :session="currentEditSession"
    @close="showEditSession = false"
    @saved="onSessionEditSaved"
    @deleted="onSessionDeleted"
  />

  <CreateSessionModal
    :show="showCreateSession"
    :meetings="meetings"
    :lockedUserId="authStore.user?.id"
    @close="showCreateSession = false"
    @saved="onSessionCreated"
  />

  <!-- 맥락 입력 모달 -->
  <Teleport to="body">
    <div v-if="showContextModal" class="app-modal-backdrop" @click.self="showContextModal = false">
      <div class="app-modal context-modal">
        <div class="app-modal-header">
          <span class="app-modal-title">맥락 입력</span>
          <button class="app-modal-close" @click="showContextModal = false">
            <svg
              width="14"
              height="14"
              fill="none"
              stroke="currentColor"
              stroke-width="2.5"
              viewBox="0 0 24 24"
            >
              <path d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>
        <div class="app-modal-body">
          <p class="context-modal-desc">
            대화 상황, 주제, 고유명사 등 회의와 관련된 맥락을 입력하면 요약 정확도가 크게 높아져요.
          </p>
          <textarea
            v-model="contextDraft"
            id="context_modal"
            name="context_modal"
            class="context-modal-textarea"
            placeholder="예시:&#10;- 대화 상황: ABC 프로젝트 킥오프 미팅&#10;- 주제: Q3 마케팅 전략, 예산 논의&#10;- 고유명사: 김매니저, 이팀장, 네트워크 인프라"
            rows="7"
          />
        </div>
        <div class="app-modal-footer">
          <button class="app-modal-cancel" @click="showContextModal = false">취소</button>
          <button class="app-modal-confirm" @click="saveContext">저장</button>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
/* ── Layout ── */
.sp-layout {
  display: flex;
  flex-direction: row !important;
  gap: 0;
}

/* ── Left sidebar (session selector) ── */
.sp-sidebar {
  position: relative;
  width: 220px;
  flex-shrink: 0;
  border-right: 1px solid var(--border);
  background: var(--bg-card);
  height: 100%;
}
.sp-sidebar.collapsed {
  width: 0;
  border-right: none;
}
.sp-sidebar-inner {
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow: hidden;
}
.sp-sidebar.collapsed .sp-sidebar-inner {
  opacity: 0;
  pointer-events: none;
}
.sp-toggle-handle {
  position: absolute;
  top: 50%;
  left: 100%;
  transform: translateY(-50%);
  width: 16px;
  height: 48px;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 0;
  border: 1px solid var(--border);
  border-left: none;
  border-radius: 0 8px 8px 0;
  background: var(--bg-card);
  color: var(--text-muted);
  cursor: pointer;
  z-index: 25;
}
.sp-toggle-handle:hover {
  background: var(--surface-2);
  color: var(--primary);
}
.sp-resize-handle {
  position: absolute;
  top: 0;
  right: -3px;
  width: 6px;
  height: 100%;
  cursor: col-resize;
  z-index: 20;
  background: transparent;
}
.sp-resize-handle:hover {
  background: rgba(59, 130, 246, 0.25);
}
.sp-sidebar-header {
  padding: 6px 16px;
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
}
.sp-header-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 0;
  font-size: 16px;
  height: 32px;
}
/* ── Session create modal ── */
.sp-mi:focus {
  border-color: var(--primary);
}
.sp-ms-wrap {
  display: flex;
  align-items: center;
  gap: 6px;
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 5px 8px;
}
.sp-ms-input {
  flex: 1;
  border: none;
  outline: none;
  font-size: 12px;
  color: var(--dark-card);
}
.sp-ms-results {
  border: 1px solid var(--border);
  border-radius: 8px;
  overflow: hidden;
  margin-top: 4px;
}
.sp-ms-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 7px 10px;
  border-bottom: 1px solid var(--border);
  font-size: 12px;
}
.sp-ms-item:last-child {
  border-bottom: none;
}
.sp-ms-info {
  flex: 1;
  min-width: 0;
}
.sp-ms-name {
  font-weight: 600;
  color: var(--dark-card);
  display: block;
}
.sp-ms-email {
  color: var(--dark-muted);
  font-size: 12px;
  display: block;
}
.sp-ms-role {
  padding: 3px 8px;
  border-radius: 5px;
  border: 1px solid var(--border);
  background: var(--surface);
  color: var(--text-muted);
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
}
.sp-ms-role.admin {
  border-color: var(--accent);
  background: rgba(59, 130, 246, 0.1);
  color: var(--accent);
}
.stt-type-btn {
  flex: 1;
  padding: 8px;
  border-radius: 8px;
  border: 1px solid var(--border);
  background: var(--surface);
  color: var(--text);
  font-size: 12px;
  cursor: pointer;
}
.stt-type-btn.active {
  border-color: var(--accent);
  background: rgba(59, 130, 246, 0.1);
  color: var(--accent);
  font-weight: 600;
}
.sp-sm-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 5px 8px;
  background: var(--surface);
  border-radius: 7px;
  font-size: 12px;
}
.sp-sm-name {
  flex: 1;
  font-weight: 600;
  color: var(--dark-card);
}
.sp-sm-role-tag {
  padding: 2px 7px;
  border-radius: 5px;
  font-size: 12px;
  font-weight: 600;
}
.sp-sm-role-tag.admin {
  background: rgba(59, 130, 246, 0.1);
  color: var(--accent);
}
.sp-sm-role-tag.member {
  background: rgba(34, 197, 94, 0.1);
  color: #16a34a;
}
.sp-sm-rm {
  background: none;
  border: none;
  cursor: pointer;
  color: var(--dark-muted);
  font-size: 16px;
  line-height: 1;
}
.sp-sm-rm:hover {
  color: var(--danger);
}
.sp-sidebar-title {
  font-size: 16px;
  font-weight: 700;
  color: var(--dark-text);
  margin: 0;
}
.day-mode .sp-sidebar-title {
  color: var(--dark-card);
}
.sp-sidebar-body {
  flex: 1;
  overflow-y: auto;
  padding: 0;
}

.sp-mtg-group {
  border-bottom: 1px solid var(--surface-2);
}
.sp-mtg-header {
  font-size: 12px;
  display: flex;
  align-items: center;
  gap: 7px;
  padding: 10px 14px;
  cursor: pointer;
  user-select: none;
}
.sp-mtg-dot {
  width: 6px;
  height: 6px;
  background: var(--primary);
  border-radius: 50%;
  flex-shrink: 0;
}
.sp-mtg-title {
  flex: 1;
  font-size: 12px;
  font-weight: 600;
  color: var(--text);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.sp-mtg-chev {
  color: var(--text-muted);
  transition: transform 0.2s;
  flex-shrink: 0;
}
.sp-mtg-chev.open {
  transform: rotate(180deg);
}

.sp-session-list {
  background: var(--surface);
  border-top: 1px solid var(--surface-2);
}
.sp-session-item {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 14px;
  cursor: pointer;
}
.sp-session-item:hover {
  background: rgba(59, 130, 246, 0.1);
}
.sp-session-item.active {
  background: rgba(59, 130, 246, 0.1);
}
.sp-session-info {
  flex: 1;
  min-width: 0;
}
.sp-session-name {
  font-size: 12px;
  font-weight: 600;
  color: var(--text);
  display: flex;
  align-items: center;
  gap: 5px;
  overflow: hidden;
}
.sp-session-title-text {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  flex-shrink: 1;
  min-width: 0;  
  color: var(--dark-text) !important;
}
html.day-mode-global .sp-session-title-text {
  color: var(--dark-card) !important;
}
.sp-session-status {
  font-size: 10px;
  font-weight: 600;
  flex-shrink: 0;
  color: var(--text-muted);
  background: var(--surface-2);
  border-radius: 10px;
  padding: 1px 6px;
  white-space: nowrap;
}
.sp-session-meta {
  display: flex;
  flex-direction: column;
  gap: 2px;
  margin-top: 3px;
  overflow: hidden;
}
.sp-session-date {
  font-size: 10px;
  color: var(--text-muted);
}
.sp-session-location {
  font-size: 10px;
  color: var(--text-muted);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.sp-status-badge {
  font-size: 10px;
  font-weight: 700;
  padding: 2px 6px;
  border-radius: 910px;
  flex-shrink: 0;
}
.sp-edit-btn {
  background: none;
  border: none;
  cursor: pointer;
  color: var(--text-muted);
  padding: 2px;
  display: flex;
  align-items: center;
  flex-shrink: 0;
  border-radius: 4px;
}
.sp-edit-btn:hover {
  color: var(--primary);
  background: var(--surface-2);
}

/* ── Center panel ── */
.sp-main {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: stretch;
  justify-content: center;
  padding: 0 10px;
  overflow: visible;
  min-width: 0;
}

.sp-no-session {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  gap: 10px;
  color: var(--text-muted);
}
.sp-no-session-text {
  font-size: 14px;
  font-weight: 600;
  margin: 0;
}
.sp-no-session-sub {
  font-size: 12px;
  margin: 0;
  opacity: 0.7;
}

.sp-panel {
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow: visible;
  border-radius: 0 !important;
}
.sp-panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 6px 8px;
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
  gap: 12px;
}
.sp-panel-title-row {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}
.sp-panel-title-group {
  display: flex;
  flex-direction: column;
  min-width: 0;
  flex: 1;
}
.sp-panel-title-line {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}
.sp-panel-title {
  font-size: 14px;
  font-weight: 700;
  color: var(--dark-card);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.sp-participant-count {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  flex-shrink: 0;
  font-size: 12px;
  font-weight: 600;
  color: var(--text-muted);
  padding: 1px 7px;
  border-radius: 910px;
  background: var(--surface-2, rgba(120, 120, 120, 0.1));
}
.sp-participant-count .bi {
  font-size: 12px;
}
.sp-panel-location {
  font-size: 12px;
  color: var(--text-muted);
  margin-top: 1px;
}
.rec-live {
  display: flex;
  align-items: center;
  flex-shrink: 0;
}
.rec-live.paused .rec-timer {
  color: var(--text-muted);
}

.sp-tab-body {
  flex: 1;
  overflow-y: auto;
  padding: 18px 23px;
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-height: 0;
}
.sp-tab-body::-webkit-scrollbar {
  width: 4px;
}
.sp-tab-body::-webkit-scrollbar-thumb {
  background: var(--border);
}
.minutes-scroll-area {
  flex: 1;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-height: 0;
  padding-bottom: 8px;
}
.minutes-scroll-area::-webkit-scrollbar {
  width: 4px;
}
.minutes-scroll-area::-webkit-scrollbar-thumb {
  background: var(--border);
}
.conv-block {
  padding: 0px 0px 6px;
}
.conv-block-header {
  display: flex;
  align-items: baseline;
  gap: 8px;
  margin-bottom: 8px;
}
.conv-block-title {
  font-size: 12px;
  font-weight: 700;
  color: var(--text);
}
.conv-block-time {
  font-size: 12px;
  color: var(--text-muted);
  font-family: 'Pretendard', inherit;
  white-space: nowrap;
}
.conv-block-bullet {
  font-size: 12px;
  color: var(--text);
  line-height: 2;
}
.conv-block-original {
  margin-top: 10px;
  padding-top: 10px;
  border-top: 1px solid var(--border);
  font-size: 12px;
  color: var(--text-muted);
  line-height: 1.8;
  white-space: pre-line;
}
.conv-raw {
  position: relative;
  padding: 16px 18px;
  border: 1px solid var(--border);
  border-radius: 10px;
  margin-bottom: 16px;
}
.conv-raw-loading-wrapper {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  height: 2px;
  overflow: hidden;
  border-radius: 10px 10px 0 0;
}
.conv-raw-loading-bar {
  height: 2px;
  width: 100%;
  background: linear-gradient(90deg, transparent, var(--primary), transparent);
  animation: conv-scan 1.4s ease-in-out infinite;
}
@keyframes conv-scan {
  0% {
    transform: translateX(-100%);
  }
  100% {
    transform: translateX(100%);
  }
}
.conv-raw-line {
  font-size: 12px;
  color: var(--text-muted);
  line-height: 2;
}
.context-modal {
  width: 480px;
  max-width: 90vw;
}
.context-modal-desc {
  font-size: 12px;
  color: var(--text-muted);
  margin-bottom: 12px;
  line-height: 1.6;
}
.context-modal-textarea {
  width: 100%;
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 12px 14px;
  font-size: 12px;
  background: var(--surface);
  color: var(--text);
  outline: none;
  resize: none;
  font-family: inherit;
  line-height: 1.7;
}
.context-modal-textarea:focus {
  border-color: var(--primary);
}
.app-modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  padding: 12px 20px;
  border-top: 1px solid var(--border);
}
.app-modal-cancel {
  padding: 7px 16px;
  border-radius: 7px;
  border: 1px solid var(--border);
  background: none;
  color: var(--text-muted);
  font-size: 12px;
  cursor: pointer;
}
.app-modal-confirm {
  padding: 7px 18px;
  border-radius: 7px;
  border: none;
  background: var(--primary);
  color: #fff;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
}

.sp-tab-body.minutes-mode {
  overflow: hidden;
  padding: 0;
  display: flex;
  flex-direction: column;
}
.sp-tab-body.minutes-mode .minutes-scroll-area {
  padding: 12px 16px 0;
}
.sp-tab-body.minutes-mode .minutes-scroll-area.has-nab {
  flex: 1;
  min-height: 0;
}
.nab-resize-handle {
  flex-shrink: 0;
  height: 5px;
  cursor: row-resize;
  background: transparent;
  border-top: 1px solid var(--border);
  transition: background 0.15s;
}
.nab-resize-handle:hover {
  background: var(--primary-light, rgba(99, 102, 241, 0.12));
}
.sp-tab-body.minutes-mode .minutes-action-row {
  padding: 10px 16px 8px;
  margin: 0;
}
.sp-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  gap: 8px;
  color: var(--text-muted);
}
/* Transcript lines */
.tline {
  display: flex;
  flex-direction: column;
  gap: 1px;
  align-items: flex-start;
  padding: 4px 0;
  position: relative;
}

/* ── AI 전문용어 교정 표시 — 교정된 줄을 잠깐 무지개색으로 빛나게(1회성) ── */
.tline-corrected {
  border-radius: 8px;
  padding: 4px 8px;
  margin: 0 -8px;
  animation: ai-glow 2.4s ease-out 1;
}
.tline-corrected .tline-text {
  background: linear-gradient(
    90deg,
    #f43f5e,
    #f59e0b,
    #22c55e,
    #38bdf8,
    #a855f7,
    #f43f5e
  );
  background-size: 300% 100%;
  -webkit-background-clip: text;
  background-clip: text;
  -webkit-text-fill-color: transparent;
  color: transparent;
  animation: ai-text-rainbow 2.4s linear 1;
}
@keyframes ai-glow {
  0% {
    box-shadow: 0 0 0 0 rgba(244, 63, 94, 0);
    background: transparent;
  }
  18% {
    box-shadow: 0 0 14px 2px rgba(244, 63, 94, 0.5);
    background: rgba(244, 63, 94, 0.07);
  }
  45% {
    box-shadow: 0 0 16px 3px rgba(56, 189, 248, 0.5);
    background: rgba(56, 189, 248, 0.07);
  }
  70% {
    box-shadow: 0 0 16px 3px rgba(34, 197, 94, 0.45);
    background: rgba(34, 197, 94, 0.07);
  }
  88% {
    box-shadow: 0 0 12px 2px rgba(168, 85, 247, 0.45);
    background: rgba(168, 85, 247, 0.06);
  }
  100% {
    box-shadow: 0 0 0 0 rgba(168, 85, 247, 0);
    background: transparent;
  }
}
@keyframes ai-text-rainbow {
  0% {
    background-position: 0% 50%;
  }
  100% {
    background-position: 200% 50%;
  }
}
@media (prefers-reduced-motion: reduce) {
  .tline-corrected,
  .tline-corrected .tline-text {
    animation: none;
  }
}
.tline-head {
  display: flex;
  align-items: center;
  gap: 8px;
}
.tline:hover .tline-edit-btn {
  opacity: 1;
}
.tline-time {
  font-size: 10px;
  color: var(--text-muted);
  flex-shrink: 0;
  font-family: 'Pretendard', inherit;
}
.tline-body {
  width: 100%;
  min-width: 0;
  font-size: 12px;
  line-height: 1.5;
}
.tline-text {
  font-size: 12px;
  color: var(--dark-card);
  line-height: 1.5;
}
/* 야간모드: 텍스트색에 --dark-card(어두운 색)를 쓰는 요소들은 다크 배경에 묻힌다.
   야간모드에선 --dark-card가 재정의되지 않으므로 명시적으로 밝은 텍스트색으로 덮는다.
   (.sp-sidebar-title처럼 base=--dark-text + .day-mode 오버라이드로 된 건 제외) */
html.night-mode .tline-text,
html.night-mode .tline-edit-text,
html.night-mode .tline-edit-speaker,
html.night-mode .sp-panel-title,
html.night-mode .sp-ms-name,
html.night-mode .sp-sm-name,
html.night-mode .sp-ms-input,
html.night-mode .ts-summary-body,
html.night-mode .minutes-md,
html.night-mode .tiptap-content :deep(.ProseMirror h1) {
  color: var(--dark-text);
}
/* 야간모드: 헤딩 — 너무 어두운 네이비(#1e40af)/다크값은 밝은 강조색으로 */
html.night-mode .minutes-md :deep(h2),
html.night-mode .tiptap-content :deep(.ProseMirror h2) {
  color: var(--accent-soft);
}
/* 야간모드: 밝은 배경면/hover 글레어 — 다크 표면으로 치환 */
html.night-mode .ctrl-end {
  background: rgba(239, 68, 68, 0.12);
}
html.night-mode .ctrl-stop:hover,
html.night-mode .tt-delete:hover {
  background: rgba(239, 68, 68, 0.16) !important;
}
html.night-mode .mbar-btn.regen:hover {
  background: var(--white-08);
}
html.night-mode .wm-suggested-btn:hover {
  background: var(--surface-2);
}
html.night-mode .sp-filter-drop-item:hover {
  background: var(--surface-2);
}
/* 야간모드: 어두운 배경의 초록(green-600) 역할 태그는 더 밝은 초록으로 */
html.night-mode .sp-sm-role-tag.member {
  color: #4ade80;
}
.tline-edit-btn {
  opacity: 0;
  transition: opacity 0.15s;
  background: none;
  border: none;
  cursor: pointer;
  color: var(--text-muted);
  font-size: 12px;
  padding: 1px 4px;
  border-radius: 4px;
  display: inline-flex;
  vertical-align: middle;
  margin-left: 4px;
}
.tline-edit-btn:hover {
  color: var(--accent);
  background: rgba(96, 165, 250, 0.1);
}

/* 편집 모드 — 일반 줄(.tline)과 동일한 세로 구조: head(time+화자입력) / body(textarea+버튼) */
.tline-editing {
  gap: 4px;
  background: var(--surface);
  border-radius: 8px;
  padding: 6px 8px;
  margin: 2px 0;
}
/* 편집 body: 일반 줄의 [텍스트][편집버튼]처럼 [textarea][저장/취소]를 가로 배치 */
.tline-editing .tline-body {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  align-items: flex-start;
}
.tline-edit-text {
  flex: 1;
  font-size: 12px;
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 4px 8px;
  resize: vertical;
  outline: none;
  background: var(--bg-card);
  color: var(--dark-card);
  min-width: 200px;
  line-height: 1.5;
}
/* 임원 체크박스 */
.tline-clevel-label {
  display: flex;
  align-items: center;
  gap: 4px;
  cursor: pointer;
  user-select: none;
  margin-left: 4px;
}
.tline-clevel-check {
  width: 13px;
  height: 13px;
  cursor: pointer;
  accent-color: #b45309;
}
.tline-clevel-text {
  font-size: 11px;
  font-weight: 600;
  color: #b45309;
}
/* 임원 발화 뱃지 */
.tline-clevel-badge {
  font-size: 10px;
  font-weight: 700;
  padding: 1px 5px;
  border-radius: 3px;
  background: rgba(234, 179, 8, 0.15);
  color: #b45309;
  margin-left: 4px;
  vertical-align: middle;
}
/* 임원 발화 줄 강조 */
.tline-clevel {
  border-left: 3px solid rgba(234, 179, 8, 0.6);
  padding-left: 8px;
}

/* 화자 라벨 (P6) */
.tline-speaker {
  font-size: 12px;
  font-weight: 600;
  color: var(--accent);
  background: rgba(96, 165, 250, 0.12);
  padding: 1px 7px;
  border-radius: 910px;
  flex-shrink: 0;
  margin-right: 6px;
  align-self: center;
  white-space: nowrap;
}
.tline-edit-speaker {
  width: 96px;
  flex-shrink: 0;
  font-size: 12px;
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 4px 8px;
  outline: none;
  background: var(--bg-card);
  color: var(--dark-card);
}
.tline-edit-btns {
  display: flex;
  gap: 4px;
  flex-shrink: 0;
  align-items: center;
}
.tline-save-btn {
  font-size: 12px;
  font-weight: 700;
  padding: 3px 10px;
  border-radius: 5px;
  border: none;
  background: var(--accent);
  color: #fff;
  cursor: pointer;
}
.tline-save-btn:hover {
  background: #2563eb;
}
.tline-cancel-btn {
  font-size: 12px;
  padding: 3px 8px;
  border-radius: 5px;
  border: 1px solid var(--border);
  background: none;
  color: var(--text-muted);
  cursor: pointer;
}

/* REC 타이머 */
.rec-timer {
  font-family: 'Pretendard', inherit;
  font-size: 12px;
  font-weight: 600;
  color: var(--danger);
  letter-spacing: 0.02em;
}
.rec-live.paused .rec-timer {
  color: var(--text-muted);
}
.rec-wave {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  height: 20px;
  margin-right: 6px;
}
.rec-wave span {
  display: inline-block;
  width: 2px;
  min-height: 2px;
  border-radius: 2px;
  background: #e53e3e;
  /* 높이는 실제 오디오 스펙트럼(getWaveLevels)으로 인라인 지정 — 프레임 간 부드럽게 */
  transition: height 0.05s linear;
}
/* 녹음 중이 아닐 땐(조회/일시정지) 평평한 막대 + 음소거 색상으로 차분하게 표시 */
.rec-live.paused .rec-wave span {
  background: var(--text-muted);
}
.mic-error-msg {
  font-size: 12px;
  color: var(--danger-soft);
  display: flex;
  align-items: center;
  gap: 4px;
}
.ctrl-ended-msg {
  display: flex;
  align-items: center;
  gap: 5px;
  font-size: 12px;
  font-weight: 600;
  color: var(--text-muted);
}

/* AI summary box */
.ts-summary-box {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 8px;
  margin-bottom: 12px;
  overflow: hidden;
}
.ts-summary-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 12px;
  background: var(--surface-2);
  border-bottom: 1px solid var(--border);
  font-size: 12px;
  font-weight: 600;
  color: var(--text-muted);
}
.ts-summary-close {
  background: none;
  border: none;
  cursor: pointer;
  color: var(--dark-muted);
  font-size: 12px;
  line-height: 1;
}
.ts-summary-body {
  padding: 10px 12px;
  font-size: 12px;
  color: var(--dark-border);
  line-height: 1.6;
}

/* Minutes – Tiptap editor */
.tiptap-toolbar {
  display: flex;
  align-items: center;
  gap: 2px;
  padding: 6px 4px;
  border-bottom: 1px solid var(--border);
  background: transparent;
  flex-wrap: wrap;
  margin-bottom: 8px;
}
.tt-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 28px;
  height: 26px;
  padding: 0 5px;
  border: 1px solid transparent;
  border-radius: 4px;
  background: none;
  color: var(--text-muted);
  font-size: 12px;
  cursor: pointer;
  transition: all 0.1s;
  user-select: none;
}
.tt-btn:hover {
  background: var(--border);
}
.tt-btn.active {
  background: var(--accent-bg-2);
  color: var(--accent-strong);
  border-color: #bfdbfe;
}
.tt-delete {
  color: var(--danger) !important;
}
.tt-delete:hover {
  background: #fef2f2 !important;
}
.tt-delete:disabled {
  opacity: 0.4;
  cursor: not-allowed;
  pointer-events: none;
}
.tt-sep {
  width: 1px;
  height: 18px;
  background: var(--border);
  margin: 0 3px;
}

.tiptap-content {
  border: none;
  padding: 4px 0;
  min-height: 400px;
  background: transparent;
  outline: none;
}
.tiptap-content :deep(.ProseMirror) {
  outline: none;
  min-height: 380px;
  color: var(--text);
}
.tiptap-content :deep(.ProseMirror p) {
  margin: 0 0 6px;
  font-size: 12px;
  line-height: 1.7;
  color: var(--text);
}
.tiptap-content :deep(.ProseMirror h1) {
  font-size: 20px;
  font-weight: 800;
  margin: 0 0 12px;
  padding-bottom: 8px;
  border-bottom: 2px solid var(--border);
  color: var(--dark-bg);
}
.tiptap-content :deep(.ProseMirror h2) {
  font-size: 16px;
  font-weight: 700;
  margin: 16px 0 6px;
  color: #1e40af;
}
.tiptap-content :deep(.ProseMirror h3) {
  font-size: 12px;
  font-weight: 700;
  margin: 10px 0 4px;
  color: var(--text-muted);
}
.tiptap-content :deep(.ProseMirror strong) {
  font-weight: 700;
}
.tiptap-content :deep(.ProseMirror em) {
  font-style: italic;
}
.tiptap-content :deep(.ProseMirror u) {
  text-decoration: underline;
}
.tiptap-content :deep(.ProseMirror ul),
.tiptap-content :deep(.ProseMirror ol) {
  padding-left: 20px;
  margin: 4px 0;
}
.tiptap-content :deep(.ProseMirror li) {
  margin-bottom: 2px;
  font-size: 12px;
  line-height: 1.6;
}
.tiptap-content :deep(.ProseMirror li > p) {
  margin: 0;
}
.tiptap-content :deep(.ProseMirror table) {
  width: auto;
  border-collapse: collapse;
  margin: 8px 0;
  font-size: 12px;
  table-layout: auto;
}
.tiptap-content :deep(.ProseMirror th),
.tiptap-content :deep(.ProseMirror td) {
  border: 1px solid var(--border);
  padding: 4px 10px;
  text-align: left;
  vertical-align: middle;
  white-space: nowrap;
}
.tiptap-content :deep(.ProseMirror th) {
  background: var(--surface-2);
  font-weight: 600;
  font-size: 12px;
}
.tiptap-content :deep(.ProseMirror td > p),
.tiptap-content :deep(.ProseMirror th > p) {
  margin: 0;
}
.tiptap-content :deep(.ProseMirror hr) {
  border: none;
  border-top: 2px solid var(--text-muted);
  margin: 16px 0;
}
.tiptap-content :deep(.ProseMirror blockquote) {
  border-left: 3px solid var(--border);
  padding-left: 12px;
  color: var(--text-muted);
  margin: 6px 0;
}

/* Streaming preview uses same styles */
.minutes-md {
  font-size: 12px;
  line-height: 1.7;
  color: var(--dark-card);
}
.minutes-md :deep(h1) {
  font-size: 20px;
  font-weight: 800;
  margin: 0 0 12px;
  padding-bottom: 8px;
  border-bottom: 2px solid var(--border);
}
.minutes-md :deep(h2) {
  font-size: 16px;
  font-weight: 700;
  margin: 16px 0 6px;
  color: #1e40af;
}
.minutes-md :deep(h3) {
  font-size: 12px;
  font-weight: 700;
  margin: 10px 0 4px;
  color: var(--text-muted);
}
.minutes-md :deep(strong) {
  font-weight: 700;
}
.minutes-md :deep(ul),
.minutes-md :deep(ol) {
  padding-left: 18px;
  margin: 4px 0;
}
.minutes-md :deep(li) {
  margin-bottom: 2px;
}
.minutes-md :deep(table) {
  width: 100%;
  border-collapse: collapse;
  margin: 8px 0;
  font-size: 12px;
}
.minutes-md :deep(th),
.minutes-md :deep(td) {
  border: 1px solid var(--border);
  padding: 5px 8px;
  text-align: left;
}
.minutes-md :deep(th) {
  background: var(--surface);
  font-weight: 600;
}
.minutes-md :deep(hr) {
  border: none;
  border-top: 2px solid var(--text-muted);
  margin: 16px 0;
}

.tt-source-info {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  font-size: 12px;
  color: var(--dark-muted);
  padding: 0 4px;
  white-space: nowrap;
  cursor: default;
}

/* Control bar */
.sp-ctrl-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 16px;
  border-top: 1px solid var(--border);
  flex-shrink: 0;
  background: var(--bg-card);
  overflow: visible;
  border-radius: 0;
}
.ctrl-group-left,
.ctrl-group-right {
  display: flex;
  align-items: center;
  gap: 12px;
}
.ctrl-group-right {
  margin-left: auto;
}
.ctrl-pop-wrap {
  position: relative;
}
.ctrl-btn {
  display: flex;
  align-items: center;
  gap: 3px;
  padding: 6px 10px;
  border-radius: 8px;
  border: 1px solid var(--border);
  background: var(--bg-card);
  color: var(--text-muted);
  font-size: 12px;
  cursor: pointer;
}
.ctrl-btn:hover,
.ctrl-active {
  background: var(--surface-2);
  border-color: var(--primary);
  color: var(--primary);
}
.ctrl-lang {
  font-size: 12px;
  gap: 4px;
}
.ctrl-chev {
  font-size: 10px;
  opacity: 0.6;
}
.ctrl-popover {
  position: absolute;
  bottom: calc(100% + 6px);
  left: 0;
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 10px;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.12);
  padding: 10px 12px;
  min-width: 160px;
  z-index: 200;
}
.cpop-title {
  font-size: 12px;
  font-weight: 700;
  color: var(--text-muted);
  text-transform: uppercase;
  margin-bottom: 8px;
}
.cpop-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
  font-size: 12px;
  color: var(--text-muted);
}
.cpop-label {
  flex: 1;
}
.cpop-range {
  flex: 1;
  accent-color: var(--primary);
}
.cpop-val {
  font-size: 12px;
  font-weight: 600;
  min-width: 28px;
  text-align: right;
}
.cpop-opt {
  display: block;
  width: 100%;
  text-align: left;
  padding: 7px 10px;
  border-radius: 6px;
  border: none;
  background: none;
  font-size: 12px;
  cursor: pointer;
  color: var(--text-muted);
}
.cpop-opt:hover {
  background: var(--surface-2);
}
.cpop-opt.selected {
  background: rgba(59, 130, 246, 0.1);
  color: var(--accent);
  font-weight: 600;
}
.ctrl-rec-btn {
  width: 34px;
  height: 34px;
  border-radius: 50%;
  border: none;
  background: var(--primary);
  color: #fff;
  font-size: 16px;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  box-shadow: 0 2px 8px rgba(59, 130, 246, 0.3);
  line-height: 1;
}
.ctrl-rec-btn.recording {
  background: var(--danger);
  box-shadow: 0 2px 8px rgba(239, 68, 68, 0.35);
}
.ctrl-rec-btn:hover {
  opacity: 0.85;
}
.ctrl-rec-btn i {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 100%;
  height: 100%;
}
.ctrl-stop {
  color: var(--danger);
  border-color: #fca5a5;
}
.ctrl-stop:hover {
  background: #fef2f2;
  border-color: var(--danger);
}
.ctrl-end {
  height: 34px;
  padding: 0 14px;
  border-radius: 17px;
  border: none;
  background: #fef2f2;
  color: var(--danger);
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  display: flex;
  align-items: center;
}
.ctrl-end:hover {
  background: var(--danger);
  color: #fff;
  border-color: var(--danger);
}
.ctrl-minutes {
  display: flex;
  align-items: center;
  gap: 5px;
  padding: 7px 14px;
  border-radius: 8px;
  border: none;
  background: var(--warning);
  color: #fff;
  font-size: 12px;
  font-weight: 700;
  cursor: pointer;
}
.ctrl-minutes:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* ── Left sidebar search ── */
.sp-search-wrap {
  position: relative;
  display: flex;
  align-items: center;
  margin-top: 10px;
}
.sp-filter-icon-btn-wrap { position: relative; margin-left: 4px; }
.sp-filter-icon-btn {
  width: 30px;
  height: 30px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--bg-card);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--dark-muted);
  flex-shrink: 0;
}
.sp-filter-icon-btn.active { border-color: var(--accent); color: var(--accent); }
.sp-filter-drop {
  position: absolute;
  top: 34px;
  right: 0;
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 8px;
  box-shadow: 0 4px 12px rgba(0,0,0,0.12);
  z-index: 100;
  min-width: 90px;
  overflow: hidden;
}
.sp-filter-drop-item {
  display: block;
  width: 100%;
  padding: 7px 14px;
  text-align: left;
  font-size: 12px;
  border: none;
  background: none;
  cursor: pointer;
  color: var(--text);
}
.sp-filter-drop-item:hover { background: var(--bg-hover, #f5f5f5); }
.sp-filter-drop-item.active { color: var(--accent); font-weight: 600; }
.sp-search-icon {
  position: absolute;
  left: 10px;
  top: 50%;
  transform: translateY(-50%);
  color: var(--dark-muted);
  pointer-events: none;
}
.sp-search-input {
  width: 100%;
  padding: 7px 28px;
  border: 1px solid var(--border);
  border-radius: 8px;
  font-size: 12px;
  color: var(--text);
  background: var(--bg-card);
  outline: none;
  box-sizing: border-box;
}
.sp-search-input:focus {
  border-color: var(--accent);
}
.sp-search-input::placeholder {
  color: var(--dark-muted);
}
.sp-search-clear {
  position: absolute;
  right: 6px;
  background: none;
  border: none;
  cursor: pointer;
  color: var(--dark-muted);
  font-size: 14px;
  line-height: 1;
  padding: 0;
}
.sp-search-clear:hover {
  color: var(--text-muted);
}
.sp-search-empty {
  padding: 20px 14px;
  text-align: center;
  font-size: 12px;
  color: var(--dark-muted);
}

/* ── Right: 워크메이트 AI ── */
.sp-agent-right-sidebar {
  position: relative;
  width: 290px;
  flex-shrink: 0;
  border-left: 1px solid var(--border);
  display: flex;
  flex-direction: column;
  background: var(--bg-card);
  overflow: hidden;
  height: 100%;
}
.sp-agent-resize-handle {
  position: absolute;
  top: 0;
  left: -3px;
  width: 6px;
  height: 100%;
  cursor: col-resize;
  z-index: 20;
  background: transparent;
}
.sp-agent-resize-handle:hover {
  background: rgba(59, 130, 246, 0.25);
}

/* ── Minutes action row ── */
.minutes-action-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 10px 0 2px;
  border-top: 1px solid var(--border);
  flex-shrink: 0;
}
.minutes-action-left,
.minutes-action-right {
  display: flex;
  align-items: center;
  gap: 6px;
}
.minutes-download-group {
  display: flex;
  gap: 4px;
}
.minutes-action-btn {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 6px 12px;
  border-radius: 7px;
  border: 1px solid var(--border);
  background: var(--bg-card);
  color: var(--text-muted);
  font-size: 12px;
  font-weight: 500;
  cursor: pointer;
  white-space: nowrap;
}
.minutes-action-btn:hover {
  background: var(--surface-2);
}
.minutes-action-btn.primary {
  background: var(--primary);
  color: #fff;
  border-color: var(--primary);
}
.minutes-action-btn.primary:hover {
  opacity: 0.88;
}
.minutes-action-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.minutes-saved-label {
  font-size: 12px;
  color: #22c55e;
  display: flex;
  align-items: center;
  gap: 4px;
}
@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}
.spin {
  display: inline-block;
  animation: spin 0.7s linear infinite;
}

/* Minutes bottom bar */
.sp-minutes-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 16px;
  border-top: 1px solid var(--border);
  flex-shrink: 0;
  background: var(--bg-card);
  border-radius: 0;
  flex-wrap: wrap;
  gap: 8px;
}
.minutes-bar-left,
.minutes-bar-right {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}
.mbar-btn {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 6px 14px;
  border-radius: 7px;
  border: 1px solid var(--border);
  background: var(--bg-card);
  color: var(--text-muted);
  font-size: 12px;
  font-weight: 500;
  cursor: pointer;
  white-space: nowrap;
}
.mbar-btn:hover {
  background: var(--surface-2);
}
.mbar-btn.primary {
  background: var(--primary);
  color: #fff;
  border-color: var(--primary);
}
.mbar-btn.primary:hover {
  opacity: 0.88;
}

.mbar-btn.regen:hover {
  background: #eef2ff;
}
.mbar-btn:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}
.mbar-saved-label {
  font-size: 12px;
  color: #22c55e;
  display: flex;
  align-items: center;
  gap: 4px;
}
.mbar-warning-label {
  font-size: 13px;
  color: #ef4444;
  display: flex;
  align-items: center;
  gap: 4px;
  margin-right: 10px;
  animation: fadeIn 0.2s ease;
}
@keyframes fadeIn {
  from { opacity: 0; transform: translateY(2px); }
  to   { opacity: 1; transform: translateY(0); }
}
.sp-attach-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border-radius: 7px;
  border: 1px solid var(--border);
  background: transparent;
  color: var(--text-muted);
  cursor: pointer;
  flex-shrink: 0;
}
.sp-attach-btn:hover {
  background: var(--surface-2);
  color: var(--primary);
}
.sp-attach-btn:disabled {
  opacity: 0.35;
  cursor: not-allowed;
}
.sp-file-dl-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 20px;
  margin-left: 4px;
  border-radius: 4px;
  border: none;
  background: rgba(255, 255, 255, 0.25);
  color: inherit;
  cursor: pointer;
  vertical-align: middle;
}
.sp-file-dl-btn:hover {
  background: rgba(255, 255, 255, 0.4);
}

/* ── 다음 회의 과제 블록 ── */
.next-agenda-block {
  border: 1px solid rgba(99, 102, 241, 0.25);
  border-radius: 10px;
  background: rgba(99, 102, 241, 0.04);
  overflow-y: auto;
  flex-shrink: 0;
}
.sp-tab-body.minutes-mode .next-agenda-block {
  flex: 1;
  min-height: 0;
  border-radius: 0;
  border-left: none;
  border-right: none;
  border-bottom: none;
  margin: 0;
}
.sp-tab-body.minutes-mode .next-agenda-block.nab-collapsed {
  flex: 0 0 auto;
  overflow: hidden;
}
.nab-collapse-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  border-radius: 5px;
  border: 1px solid rgba(99, 102, 241, 0.2);
  background: none;
  color: rgba(99, 102, 241, 0.6);
  cursor: pointer;
  flex-shrink: 0;
  margin-left: auto;
  transition:
    background 0.15s,
    color 0.15s;
}
.nab-collapse-btn:hover {
  background: rgba(99, 102, 241, 0.1);
  color: rgba(99, 102, 241, 1);
}
.nab-header {
  padding: 10px 14px;
  border-bottom: 1px solid rgba(99, 102, 241, 0.12);
  position: sticky;
  top: 0;
  z-index: 2;
  background: var(--bg-card, #fff);
}
.day-mode .nab-header {
  background: #fff;
}
.nab-title-row {
  display: flex;
  align-items: center;
  gap: 7px;
  font-size: 12px;
  font-weight: 700;
  color: #818cf8;
  margin-bottom: 4px;
}
.nab-badge {
  font-size: 10px;
  font-weight: 600;
  padding: 1px 6px;
  border-radius: 10px;
  background: rgba(99, 102, 241, 0.15);
  color: #818cf8;
}
.nab-desc {
  font-size: 12px;
  color: var(--text-muted);
  margin: 0;
}
.nab-loading {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 14px;
  font-size: 12px;
  color: var(--text-muted);
}
.nab-spinner {
  width: 14px;
  height: 14px;
  border: 2px solid rgba(99, 102, 241, 0.2);
  border-top-color: #818cf8;
  border-radius: 50%;
  animation: spin 0.7s linear infinite;
}
@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}
.nab-list {
  padding: 8px;
}
.nab-direct-add-btn {
  width: 100%;
  display: flex;
  align-items: center;
  gap: 5px;
  padding: 5px 10px;
  border-radius: 6px;
  border: 1px dashed var(--border);
  background: none;
  color: var(--text-muted);
  font-size: 11.5px;
  cursor: pointer;
  transition: all 0.12s;
  margin-bottom: 6px;
}
.nab-direct-add-btn:hover {
  border-color: var(--text-muted);
  color: var(--text);
}
.wm-suggested {
  display: flex;
  flex-direction: column;
  gap: 3px;
  margin: 5px 0 4px 2px;
}
.wm-suggested-btn {
  text-align: left;
  background: none;
  border: 1px solid #c7d2fe;
  border-radius: 6px;
  padding: 4px 10px;
  font-size: 12px;
  color: var(--text);
  cursor: pointer;
  font-weight: 500;
  width: 100%;
}
.wm-suggested-btn:hover:not(:disabled) {
  background: #fff;
}
.wm-suggested-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}
</style>
