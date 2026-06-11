<script setup>
import { ref, computed, onMounted, onUnmounted, nextTick } from 'vue'
import { marked } from 'marked'
import { useEditor, EditorContent } from '@tiptap/vue-3'
import StarterKit from '@tiptap/starter-kit'
import Underline from '@tiptap/extension-underline'
import { Table, TableRow, TableCell, TableHeader } from '@tiptap/extension-table'
import SessionEditModal from '../components/SessionEditModal.vue'
import CreateSessionModal from '../components/CreateSessionModal.vue'
import DateInput from '../components/DateInput.vue'
import AgentComposer from '../components/AgentComposer.vue'
import AgendaReviewList from '../components/AgendaReviewList.vue'
import api, { apiAI } from '../api'
import { streamPost } from '../api'
import { useSTT } from '../composables/useSTT'
import { useAgentMention } from '../composables/useAgentMention'
import hyeanAvatar from '../assets/agents/hyean.png'
import { useThemeStore } from '../stores/theme'
import { useAuthStore } from '../stores/auth'
const themeStore = useThemeStore()
const authStore = useAuthStore()

const renderMd = (t) => marked.parse(t || '', { breaks: true })

// ─── State ────────────────────────────────────────────────────
const meetings = ref([])          // [{ id, title, sessions: [] }]
const loadingMeetings = ref(false)
const sessionsCache = ref({})     // { [meetingId]: SessionResponse[] }

const selectedMeetingId = ref(null)
const expandedMeetingIds = ref(new Set())
const activeSession = ref(null)
const sidebarSearch = ref('')
const sidebarCollapsed = ref(false)
const sidebarW = ref(220)
let sidebarResizing = false, srStartX = 0, srStartW = 0
function onSidebarResizeStart(e) {
  if (sidebarCollapsed.value) return
  sidebarResizing = true; srStartX = e.clientX; srStartW = sidebarW.value
  document.addEventListener('mousemove', onSidebarResizeMove)
  document.addEventListener('mouseup', onSidebarResizeEnd)
  e.preventDefault()
}
function onSidebarResizeMove(e) {
  if (!sidebarResizing) return
  sidebarW.value = Math.max(180, Math.min(420, srStartW + (e.clientX - srStartX)))
}
function onSidebarResizeEnd() {
  sidebarResizing = false
  document.removeEventListener('mousemove', onSidebarResizeMove)
  document.removeEventListener('mouseup', onSidebarResizeEnd)
}

// ─── 우측 AI 사이드바 리사이즈 ────────────────────────────────
const agentSidebarW = ref(290)
let agentResizing = false, arStartX = 0, arStartW = 0
function onAgentResizeStart(e) {
  agentResizing = true; arStartX = e.clientX; arStartW = agentSidebarW.value
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

const filteredMeetings = computed(() => {
  const q = sidebarSearch.value.trim().toLowerCase()
  if (!q) return meetings.value
  return meetings.value.filter(m =>
    m.title.toLowerCase().includes(q) ||
    (m.sessions || []).some(s => (s.title || '').toLowerCase().includes(q))
  )
})

const selectedMeeting = computed(() => meetings.value.find(m => m.id === selectedMeetingId.value))

async function loadSessions(meetingId) {
  if (sessionsCache.value[meetingId]) return sessionsCache.value[meetingId]
  try {
    const res = await api.get(`/api/v1/meetings/${meetingId}/sessions`)
    sessionsCache.value[meetingId] = res.data ?? []
  } catch {
    sessionsCache.value[meetingId] = []
  }
  const m = meetings.value.find(m => m.id === meetingId)
  if (m) m.sessions = sessionsCache.value[meetingId]
  return sessionsCache.value[meetingId]
}

async function fetchMeetings() {
  loadingMeetings.value = true
  try {
    const res = await api.get('/api/v1/meetings')
    meetings.value = (res.data ?? []).map(m => ({ ...m, sessions: null }))
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
  showSummary.value = false
  transcriptSummary.value = ''
  const rec = getOrCreateRecord(s.id)
  transcriptLines.value = rec.transcriptLines
  generatedMinutes.value = rec.generatedMinutes
  showMinutesTab.value = rec.showMinutesTab
  await nextTick()
  loadMinutesToEditor(rec.generatedMinutes?.content_summary || '')

  if (!rec.transcriptLines.length) {
    try {
      const { data } = await api.get(`/api/v1/sessions/${s.id}/scripts`)
      if (data && data.length) {
        const lines = data.map(seg => ({
          id: seg.id,
          time: utcToKst(seg.createdAt),
          speaker: seg.speakerLabel,
          text: seg.content,
        }))
        rec.transcriptLines.push(...lines)
        transcriptLines.value = rec.transcriptLines
      }
    } catch (e) {
      console.error('STT 세그먼트 로드 실패', e)
    }
  }

  // DB에서 저장된 회의록 불러오기 (in-memory에 없을 때만)
  if (!rec.generatedMinutes) {
    try {
      const { data } = await api.get(`/api/v1/sessions/${s.id}/minutes`)
      if (data?.contentSummary) {
        generatedMinutes.value = { content_summary: data.contentSummary }
        showMinutesTab.value = true
        rec.generatedMinutes = generatedMinutes.value
        rec.showMinutesTab = true
        await nextTick()
        loadMinutesToEditor(data.contentSummary)
      }
    } catch { /* 404 = 저장된 회의록 없음, 정상 */ }
  }
}

// ─── Recording ────────────────────────────────────────────────
const recordingState = ref('idle')
const activeTab = ref('transcript')
const transcriptLines = ref([])
const generatedMinutes = ref(null)
const showMinutesTab = ref(false)
const generatingMinutes = ref(false)
const transcriptSummary = ref('')
const summarizingTranscript = ref(false)
const showSummary = ref(false)
const transcriptAreaRef = ref(null)

const editor = useEditor({
  extensions: [
    StarterKit,
    Underline,
    Table.configure({ resizable: false }),
    TableRow,
    TableHeader,
    TableCell,
  ],
  content: '',
  editable: true,
  onUpdate: ({ editor }) => {
    if (!generatingMinutes.value && generatedMinutes.value) {
      generatedMinutes.value = { ...generatedMinutes.value, content_summary: editor.getHTML() }
      if (activeSession.value) {
        getOrCreateRecord(activeSession.value.id).generatedMinutes = generatedMinutes.value
      }
    }
  }
})

function loadMinutesToEditor(content) {
  if (!editor.value) return
  if (!content) { editor.value.commands.clearContent(); return }
  const html = content.startsWith('<') ? content : renderMd(content)
  editor.value.commands.setContent(html, false)
}

onUnmounted(() => editor.value?.destroy())
const showPopover = ref(null)
const micSensitivity = ref(70)
const noiseReduction = ref(true)
const transcriptLang = ref('ko')
const sttMode = ref('gcapi')   // 'localwhisper' | 'whisperapi' | 'gcapi'
const micError = ref('')

const STT_MODE_LABELS = { localwhisper: 'Local', whisperapi: 'Whisper API', gcapi: 'Google Cloud API' }

const sessionRecords = ref(new Map())
function getOrCreateRecord(id) {
  if (!sessionRecords.value.has(id))
    sessionRecords.value.set(id, { transcriptLines: [], generatedMinutes: null, showMinutesTab: false })
  return sessionRecords.value.get(id)
}

// 스피커 레이블 — 발화 등장 순서 기반으로 A/B/C... 동적 할당
const SPEAKER_COLORS = ['#60a5fa','#f59e0b','#34d399','#f472b6','#a78bfa','#fb923c']

const speakerMap = computed(() => {
  const map = new Map()
  for (const line of transcriptLines.value) {
    if (line.speaker && !map.has(line.speaker)) map.set(line.speaker, map.size)
  }
  return map
})

function speakerIdx(raw) { return speakerMap.value.get(raw) ?? 0 }
function speakerColor(raw) { return raw ? SPEAKER_COLORS[speakerIdx(raw) % SPEAKER_COLORS.length] : '#94a3b8' }

const KST = { hour: '2-digit', minute: '2-digit', second: '2-digit', timeZone: 'Asia/Seoul' }
function nowTime() { return new Date().toLocaleTimeString('ko-KR', KST) }
function utcToKst(str) {
  if (!str) return '--:--:--'
  // Spring Boot LocalDateTime은 Z 없이 오므로 UTC임을 명시
  const iso = str.endsWith('Z') || str.includes('+') ? str : str + 'Z'
  return new Date(iso).toLocaleTimeString('ko-KR', KST)
}

function _pushLine(time, text, speaker = null, id = null) {
  const entry = { time, text, speaker, id }
  transcriptLines.value.push(entry)
  if (activeSession.value) getOrCreateRecord(activeSession.value.id).transcriptLines = transcriptLines.value
  nextTick(() => { if (transcriptAreaRef.value) transcriptAreaRef.value.scrollTop = transcriptAreaRef.value.scrollHeight })
}

const stt = useSTT({
  onResult: (text, id = null) => { _pushLine(nowTime(), text, null, id) },
  onSegments: (segments) => {
    const t = nowTime()
    segments.forEach(seg => { if (seg.text?.trim()) _pushLine(t, seg.text.trim(), seg.speaker ?? null, seg.id ?? null) })
  },
  getLang: () => transcriptLang.value,
  getSessionId: () => activeSession.value?.id ?? null,
  getSttMode: () => sttMode.value,
})

// ─── 녹음 타이머 ──────────────────────────────────────────────
const recordingSecs = ref(0)
let _timerInterval = null

function _startTimer() {
  _timerInterval = setInterval(() => { recordingSecs.value++ }, 1000)
}
function _pauseTimer() { clearInterval(_timerInterval); _timerInterval = null }
function _resetTimer() { _pauseTimer(); recordingSecs.value = 0 }
function formatTimer(s) {
  return `${String(Math.floor(s / 60)).padStart(2, '0')}:${String(s % 60).padStart(2, '0')}`
}

// ─── 발화 편집 ────────────────────────────────────────────────
const editingIdx = ref(null)
const editDraft = ref({ speaker: '', text: '' })

function startEdit(idx) {
  const line = transcriptLines.value[idx]
  editingIdx.value = idx
  editDraft.value = { speaker: line.speaker || '', text: line.text }
}
function cancelEdit() { editingIdx.value = null }
async function saveEdit(idx) {
  const line = transcriptLines.value[idx]
  if (!line.id) return
  await api.patch(`/api/v1/sessions/${activeSession.value.id}/scripts`, {
    segments: [{ id: line.id, speakerLabel: editDraft.value.speaker, content: editDraft.value.text }]
  })
  line.speaker = editDraft.value.speaker
  line.text = editDraft.value.text
  editingIdx.value = null
}

function toggleRecording() {
  micError.value = ''
  if (recordingState.value === 'idle') {
    stt.start()
      .then(() => {
        recordingState.value = 'recording'
        _resetTimer(); _startTimer()
        if (activeSession.value?.id) {
          api.post(`/api/v1/sessions/${activeSession.value.id}/start`).catch(() => {})
        }
      })
      .catch(() => { micError.value = '마이크 권한이 필요합니다. 브라우저 설정을 확인해 주세요.' })
  } else if (recordingState.value === 'recording') {
    recordingState.value = 'paused'; stt.stop(); _pauseTimer(); fetchTranscriptSummary()
  } else {
    stt.start()
      .then(() => { recordingState.value = 'recording'; _startTimer() })
      .catch(() => { micError.value = '마이크 권한이 필요합니다.' })
  }
}

function stopRecording() {
  const was = recordingState.value === 'recording'
  recordingState.value = 'idle'; stt.stop(); _resetTimer()
  if (was) fetchTranscriptSummary()
}

async function fetchTranscriptSummary() {
  if (!transcriptLines.value.length) return
  summarizingTranscript.value = true; showSummary.value = true; transcriptSummary.value = ''
  const text = transcriptLines.value.map(l => `[${l.time}] ${l.text}`).join('\n')
  const sessionTitle = activeSession.value?.title || '회의'

  // ── 우측 채팅에 AI 사고 과정 표시 ──────────────────────────
  const userMsg = `"${sessionTitle}" 대화 내용을 요약해줘`
  const thinkingSteps = [
    `대화 텍스트 분석 중 (${transcriptLines.value.length}개 발화)...`,
    `핵심 발언 및 반복 주제 추출`,
    `Neo4j Context Graph: Evidence 노드 연결 준비`,
    `요약 생성 중...`,
  ]
  injectAction(userMsg, thinkingSteps, '').then(() => {/* noop */})
  // 실제 summary는 스트리밍으로 별도 표시 (중앙 패널)
  try {
    await streamPost('/api/agent/supervisor/chat',
      { meeting_id: activeSession.value?.meeting_id || 0, message: `다음 대화 내용을 간결하게 요약해줘:\n${text}`, chat_history: [] },
      (chunk) => { transcriptSummary.value += chunk },
      () => { summarizingTranscript.value = false }
    )
  } catch { transcriptSummary.value = '요약 중 오류가 발생했습니다.'; summarizingTranscript.value = false }
}

async function generateMinutes() {
  if (generatingMinutes.value) return
  generatingMinutes.value = true; showMinutesTab.value = true; activeTab.value = 'minutes'

  const sessionTitle = activeSession.value?.title || '회의'
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
  const agentMsg = { role: 'agent', content: '회의록을 생성하고 있습니다...' }
  wmMessages.value.push(agentMsg)
  await nextTick()

  let minutesContent = ''
  generatedMinutes.value = { content_summary: '' }

  try {
    await streamPost(
      '/api/agent/minutes/generate-minutes',
      { meeting_id: activeSession.value?.meeting_id || 0, message: transcriptText, chat_history: [] },
      (chunk) => {
        minutesContent += chunk
        generatedMinutes.value = { ...generatedMinutes.value, content_summary: minutesContent }
      },
      async () => {
        const html = renderMd(minutesContent)
        generatedMinutes.value = {
          content_summary: html,
          sources: {
            stt_count: sttCount,
            session_title: sessionTitle,
            transcript: [...transcriptLines.value]
          }
        }
        if (activeSession.value) {
          const rec = getOrCreateRecord(activeSession.value.id)
          rec.generatedMinutes = generatedMinutes.value
          rec.showMinutesTab = true
        }
        await nextTick()
        loadMinutesToEditor(html)
        agentMsg.content = `회의록 생성이 완료되었습니다.\n\n📄 **${sessionTitle}** 회의록이 회의록 탭에 저장되었습니다.\n\n결정 사항이나 액션 아이템에 대해 더 궁금한 점이 있으면 질문해 주세요.`
        wmLoading.value = false
        generatingMinutes.value = false
        // 다음 회의 과제 자동 추출
        extractNextAgendas()
      }
    )
  } catch {
    agentMsg.content = '회의록 생성 중 오류가 발생했습니다.'
    generatedMinutes.value = { content_summary: '회의록 생성 중 오류가 발생했습니다. 다시 시도해주세요.' }
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
      body{font-family:'Malgun Gothic',Arial,sans-serif;font-size:13px;line-height:1.7;color:#1e293b;padding:40px;max-width:820px;margin:0 auto}
      h1{font-size:20px;font-weight:800;border-bottom:2px solid #e2e8f0;padding-bottom:10px;margin-bottom:16px}
      h2{font-size:16px;font-weight:700;color:#1e40af;margin-top:20px;margin-bottom:6px}
      h3{font-size:14px;font-weight:700;color:#475569;margin-top:12px;margin-bottom:4px}
      p{margin:0 0 6px}ul,ol{padding-left:20px;margin:4px 0}li{margin-bottom:2px}
      table{width:100%;border-collapse:collapse;margin:8px 0;font-size:12px}
      th,td{border:1px solid #e2e8f0;padding:6px 10px;text-align:left}th{background:#f1f5f9;font-weight:600}
      hr{border:none;border-top:1px solid #e2e8f0;margin:14px 0}
      @media print{body{padding:20px}}
    </style>
  </head><body>${html}</body></html>`)
  w.document.close()
  setTimeout(() => { w.focus(); w.print() }, 400)
}

function downloadWord() {
  const html = editor.value?.getHTML() || generatedMinutes.value?.content_summary || ''
  const title = activeSession.value?.title || '회의록'
  const full = `<html xmlns:o="urn:schemas-microsoft-com:office:office" xmlns:w="urn:schemas-microsoft-com:office:word">
    <head><meta charset="utf-8">
    <style>
      body{font-family:'Malgun Gothic',Arial,sans-serif;font-size:11pt;line-height:1.6}
      h1{font-size:16pt;font-weight:bold;border-bottom:1pt solid #ccc;padding-bottom:6pt}
      h2{font-size:13pt;font-weight:bold;color:#1e40af}
      h3{font-size:11pt;font-weight:bold;color:#475569}
      table{border-collapse:collapse;width:100%}th,td{border:1pt solid #ccc;padding:4pt 8pt}th{background:#f1f5f9}
    </style>
    </head><body>${html}</body></html>`
  const blob = new Blob([full], { type: 'application/msword;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url; a.download = `${title}.doc`; a.click()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}

const savingMinutes = ref(false)
const minutesSavedAt = ref(null)

// ── 다음 회의 과제 승인/반려 블록 ─────────────────────────────
const nextAgendaItems = ref([])
const showNextAgendaBlock = ref(false)
const nextAgendaExtracting = ref(false)

async function extractNextAgendas() {
  const meetingId = activeSession.value?.meeting_id || selectedMeeting.value?.id || 0
  if (!meetingId) return

  nextAgendaExtracting.value = true
  showNextAgendaBlock.value = true
  try {
    const formData = new FormData()
    formData.append('meeting_id', String(meetingId))

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
    const toNounTitle = (t) => (t || '')
      .replace(/\s*(검토\s*)?결과\s*보고\s*$/, '').replace(/\s*보고\s*$/, '')
      .replace(/\s*논의\s*$/, '').replace(/\s*수립\s*$/, '')
      .replace(/\s*확인\s*$/, '').replace(/\s*예정\s*$/, '').replace(/\s*완료\s*$/, '').trim()
    nextAgendaItems.value = items.map(a => {
      const title = toNounTitle(a.title || a.content || '')
      const dept  = a.department || a.dept || a.assignee_dept || ''
      return {
        title, dept,
        db_id: a.db_id || null,
        start_date: a.start_date || null,
        end_date: a.due_date || null,
        _agentLogId: agentLogId,
        _state: null, _reason: '', _showReason: false, _editing: false,
        _editTitle: title, _editDept: dept,
        _editStartDate: a.start_date || null,
        _editEndDate: a.due_date || null,
      }
    })
    if (!nextAgendaItems.value.length) {
      nextAgendaItems.value = [{ title: '다음 회의 과제를 입력해주세요', dept: '', db_id: null, start_date: null, end_date: null, _agentLogId: null, _state: null, _reason: '', _showReason: false, _editing: false, _editTitle: '', _editDept: '', _editStartDate: null, _editEndDate: null }]
    }
  } catch {
    nextAgendaItems.value = [{ title: '다음 회의 과제를 입력해주세요', dept: '', db_id: null, start_date: null, end_date: null, _agentLogId: null, _state: null, _reason: '', _showReason: false, _editing: false, _editTitle: '', _editDept: '', _editStartDate: null, _editEndDate: null }]
  } finally {
    nextAgendaExtracting.value = false
  }
}

function addNextAgendaItem() {
  nextAgendaItems.value.push({ title: '', dept: '', db_id: null, start_date: null, end_date: null, _agentLogId: null, _state: null, _reason: '', _showReason: false, _editing: true, _editTitle: '', _editDept: '', _editStartDate: null, _editEndDate: null })
}

function removeNextAgendaItem(i) {
  nextAgendaItems.value.splice(i, 1)
}

async function saveApprovedNextAgendas() {
  const approved = nextAgendaItems.value.filter(a => a._state === 'approved')
  if (!approved.length) return
  try {
    const meetingId = activeSession.value?.meeting_id || selectedMeeting.value?.id || 0
    for (const a of approved) {
      await api.post(`/api/v1/meetings/${meetingId}/agendas`, { title: a.title, priority: 'medium' })
    }
    nextAgendaItems.value.forEach(a => { if (a._state === 'approved') a._state = 'saved' })
  } catch (e) {
    alert('저장에 실패했습니다.')
  }
}

async function saveMinutesToDB() {
  if (!activeSession.value || !generatedMinutes.value?.content_summary) return
  savingMinutes.value = true
  try {
    const html = editor.value?.getHTML() || generatedMinutes.value.content_summary
    const fd = new FormData()
    fd.append('content', html)
    const { data } = await apiAI.post(`/api/upload/minutes/${activeSession.value.id}`, fd, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    minutesFileUrl.value = data.file_path
    minutesSavedAt.value = new Date().toLocaleTimeString('ko-KR', { hour: '2-digit', minute: '2-digit' })
    // 회의록 저장 완료 → 세션 archived 처리
    await api.post(`/api/v1/sessions/${activeSession.value.id}/archive`)
    if (activeSession.value) activeSession.value.status = 'archived'
  } catch (e) {
    alert('저장에 실패했습니다.')
  } finally {
    savingMinutes.value = false
  }
}

function deleteMinutes() {
  if (!confirm('작성된 회의록을 삭제하시겠습니까?')) return
  generatedMinutes.value = null
  showMinutesTab.value = false
  editor.value?.commands.clearContent()
  if (activeSession.value) {
    const rec = getOrCreateRecord(activeSession.value.id)
    rec.generatedMinutes = null
    rec.showMinutesTab = false
  }
}

async function endMeeting() {
  if (!confirm('기록을 종료하시겠습니까?')) return
  const sessionId = activeSession.value?.id
  const meetingId = activeSession.value?.meeting_id
  stopRecording()
  if (sessionId) {
    await api.post(`/api/v1/sessions/${sessionId}/end`).catch(() => {})
    if (meetingId && sessionsCache.value[meetingId]) {
      const s = sessionsCache.value[meetingId].find(s => s.id === sessionId)
      if (s) s.status = 'ended'
    }
  }
  activeSession.value = null
}

function togglePopover(name) { showPopover.value = showPopover.value === name ? null : name }

// ─── Agent (워크메이트 AI / Supervisor) ─────────────────────────────────────
const wmMessages = ref([{
  role: 'agent',
  content: '안녕하세요! 워크메이트 AI입니다 😊\n회의 내용에 대해 무엇이든 질문하세요.\n예: "오늘 회의를 요약해줘", "결정 사항 정리해줘"',
}])
const wmInput = ref('')
const wmLoading = ref(false)
const messagesEl = ref(null)

// ─── @ 멘션 (아카이브 그래프 전체 노드 검색, 공통 컴포저블) ─────
const wmTextareaEl = ref(null)
const wmComposerRef = ref(null)
const mentionMeetingGroups = ref([])
const mentionMembers = ref([])
const mentionTasks = ref([])

async function loadMentionGraph() {
  try {
    const { data } = await apiAI.get('/api/neo4j/archive')
    mentionMeetingGroups.value = data?.meetings || []
    mentionMembers.value = (data?.meetings || []).flatMap(m => m.members || [])
    mentionTasks.value = (data?.meetings || []).flatMap(m => m.tasks || [])
  } catch { /* 그래프 미연결 시 @멘션은 비활성 */ }
}

function wmAutoResize() {
  const el = wmTextareaEl.value; if (!el) return
  el.style.height = '36px'; el.style.height = Math.min(el.scrollHeight, 100) + 'px'
}

const {
  atMenuOpen, atHighlight, mentionedContexts,
  AT_TYPE_LABELS, atMenuItems,
  onAgentInput: onWmInput, selectAtItem: selectWmAtItem,
  removeMentionCtx: removeWmCtx, handleMentionKeydown: handleWmMentionKeydown,
  consumeMentionContext: consumeWmMention,
} = useAgentMention({
  meetingGroups: mentionMeetingGroups,
  membersData: mentionMembers,
  tasksData: mentionTasks,
  agentInput: wmInput,
  agentTextareaEl: wmTextareaEl,
  autoResize: wmAutoResize,
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

// ─── 좌측 액션 → 우측 채팅 주입 ──────────────────────────────
async function injectAction(userText, thinkingSteps, agentReply) {
  if (wmLoading.value) return
  wmMessages.value.push({ role: 'user', content: userText })
  const thinkingMsg = { role: 'thinking', steps: [], open: true, done: false }
  wmMessages.value.push(thinkingMsg)
  wmLoading.value = true
  await nextTick()
  if (messagesEl.value) messagesEl.value.scrollTop = messagesEl.value.scrollHeight
  await _runThinkingSteps(thinkingMsg, thinkingSteps)
  const agentMsg = { role: 'agent', content: '' }
  wmMessages.value.push(agentMsg)
  await nextTick()
  // 타입라이터 효과로 응답 표시
  for (let i = 0; i < agentReply.length; i++) {
    agentMsg.content += agentReply[i]
    if (i % 4 === 0) {
      await new Promise(r => setTimeout(r, 12))
      if (messagesEl.value) messagesEl.value.scrollTop = messagesEl.value.scrollHeight
    }
  }
  wmLoading.value = false
}

async function sendAra() {
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
    await streamPost('/api/agent/supervisor/chat',
      { meeting_id: selectedMeeting.value?.id || 0, message: content, chat_history: history },
      (chunk) => { agentMsg.content += chunk; if (messagesEl.value) messagesEl.value.scrollTop = messagesEl.value.scrollHeight },
      () => { thinkingMsg.done = true; thinkingMsg.open = false; wmLoading.value = false },
      (step) => { thinkingMsg.steps.push(step); nextTick(() => { if (messagesEl.value) messagesEl.value.scrollTop = messagesEl.value.scrollHeight }) }
    )
  } catch { agentMsg.content = '응답 중 오류가 발생했습니다.'; thinkingMsg.done = true; thinkingMsg.open = false; wmLoading.value = false }
}

function onWmKeydown(e) {
  if (handleWmMentionKeydown(e)) return
  if (e.key==='Enter'&&!e.shiftKey) { e.preventDefault(); sendAra() }
}

function formatDate(d) {
  if (!d) return '일정 미정'
  return new Date(d).toLocaleString('ko-KR', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
}

const STATUS_LABEL = { scheduled: '예정', ongoing: '진행중', ended: '회의록 미생성', archived: '완료' }
const STATUS_CLS = { scheduled: '#3b82f6', ongoing: '#f59e0b', ended: '#ef4444', archived: '#94a3b8' }

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
    delete sessionsCache.value[meetingId]
    await loadSessions(meetingId)
  }
}

// ─── Session create modal (sidebar) ──────────────────────────
const showCreateSession = ref(false)

function openCreateSession() { showCreateSession.value = true }
async function onSessionCreated({ meetingId }) {
  delete sessionsCache.value[meetingId]
  await loadSessions(meetingId)
}

onMounted(() => {
  fetchMeetings()
  loadMentionGraph()
})

// 공통 컴포저가 마운트되면 내부 textarea를 @멘션 ref에 연결
function onWmComposerReady({ textareaEl }) { wmTextareaEl.value = textareaEl }

// ─── 채팅 파일 첨부 ──────────────────────────────────────────
const chatFileUploading = ref(false)

async function sendChatFile(file) {
  if (!file || chatFileUploading.value || !activeSession.value) return
  chatFileUploading.value = true
  const fd = new FormData()
  fd.append('file', file)
  fd.append('thread_id', `session-${activeSession.value.id}`)
  fd.append('context_type', 'session')
  fd.append('session_id', String(activeSession.value.id))
  if (activeSession.value.meeting_id) fd.append('meeting_id', String(activeSession.value.meeting_id))
  try {
    const { data } = await apiAI.post('/api/upload/chat', fd, { headers: { 'Content-Type': 'multipart/form-data' } })
    wmMessages.value.push({ role: 'user', content: `[파일 첨부] ${data.file_name}`, filePath: data.file_path, fileName: data.file_name })
    await nextTick()
    if (messagesEl.value) messagesEl.value.scrollTop = messagesEl.value.scrollHeight
  } catch {
    alert('파일 업로드에 실패했습니다.')
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
    alert('다운로드 링크 생성에 실패했습니다.')
  }
}

// ─── 회의록 관련 파일 업로드 ─────────────────────────────────
const minutesFileRef = ref(null)
const minutesFileUrl = ref(null)
const minutesFileUploading = ref(false)

async function uploadMinutesFile(event) {
  const file = event.target.files?.[0]
  if (!file || !activeSession.value) return
  minutesFileUploading.value = true
  const fd = new FormData()
  fd.append('file', file)
  try {
    const { data } = await apiAI.post(`/api/upload/minutes/${activeSession.value.id}/file`, fd, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    minutesFileUrl.value = data.file_path
    minutesSavedAt.value = new Date().toLocaleTimeString('ko-KR', { hour: '2-digit', minute: '2-digit' })
  } catch {
    alert('파일 업로드에 실패했습니다.')
  } finally {
    minutesFileUploading.value = false
    if (minutesFileRef.value) minutesFileRef.value.value = ''
  }
}

async function downloadMinutesFile() {
  if (!minutesFileUrl.value) return
  try {
    const { data } = await apiAI.get('/api/upload/presigned', { params: { file_path: minutesFileUrl.value } })
    window.open(data.url, '_blank')
  } catch {
    alert('다운로드 링크 생성에 실패했습니다.')
  }
}
</script>

<template>
  <div class="sp-layout page-full-height" :class="{ 'day-mode': !themeStore.nightMode }" @click="showPopover=null">

    <!-- Left: Meeting / session selector -->
    <div class="sp-sidebar" :class="{ collapsed: sidebarCollapsed }" :style="{ width: sidebarCollapsed ? '0px' : sidebarW + 'px' }">
      <button class="sidebar-toggle-handle sp-toggle-handle"
        @click.stop="sidebarCollapsed = !sidebarCollapsed"
        :title="sidebarCollapsed ? '사이드바 펼치기' : '사이드바 접기'">
        <svg width="8" height="14" viewBox="0 0 8 14" fill="none" xmlns="http://www.w3.org/2000/svg">
          <path v-if="!sidebarCollapsed" d="M6 1L1 7L6 13" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>
          <path v-else d="M2 1L7 7L2 13" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>
        </svg>
      </button>
      <div class="sp-sidebar-inner">
      <div class="sp-sidebar-header">
        <div class="sp-header-top">
          <span class="sp-sidebar-title">회의</span>
          <button class="create-btn sm" @click.stop="openCreateSession()" title="회의 생성">
            <svg width="11" height="11" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24"><path d="M12 4v16m8-8H4"/></svg>
            회의 생성
          </button>
        </div>
        <div class="sp-search-wrap">
          <svg class="sp-search-icon" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><circle cx="11" cy="11" r="8"/><path d="M21 21l-4.35-4.35"/></svg>
          <input v-model="sidebarSearch" class="sp-search-input" placeholder="회의 검색" />
          <button v-if="sidebarSearch" class="sp-search-clear" @click="sidebarSearch=''">&times;</button>
        </div>
      </div>
      <div class="sp-sidebar-body">
        <div v-if="loadingMeetings" class="sp-search-empty">불러오는 중...</div>
        <div v-else-if="!filteredMeetings.length" class="sp-search-empty">{{ sidebarSearch ? '검색 결과 없음' : '참여 중인 회의체가 없습니다' }}</div>
        <div v-for="mtg in filteredMeetings" :key="mtg.id" class="sp-mtg-group">
          <div class="sp-mtg-header" @click="selectMeeting(mtg)" :class="{ expanded: expandedMeetingIds.has(mtg.id) }">
            <span class="sp-mtg-title">{{ mtg.title }}</span>
            <svg class="sp-mtg-chev" :class="{ open: expandedMeetingIds.has(mtg.id) }" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M19 9l-7 7-7-7"/></svg>
          </div>
          <div v-if="expandedMeetingIds.has(mtg.id)" class="sp-session-list">
            <div v-if="!mtg.sessions" class="sp-session-item" style="justify-content:center;color:var(--dark-muted);font-size:11px">불러오는 중...</div>
            <div v-else-if="!mtg.sessions.filter(s => s.status !== 'archived').length" class="sp-session-item" style="justify-content:center;color:var(--dark-muted);font-size:11px">등록된 회의가 없습니다</div>
            <div v-for="s in mtg.sessions.filter(s => s.status !== 'archived')" :key="s.id"
              class="sp-session-item"
              :class="{ active: activeSession?.id === s.id }"
              @click="enterSession(s)">
              <div class="sp-session-info">
                <div class="sp-session-name">{{ s.title }}</div>
                <div class="sp-session-meta">
                  <span v-if="s.location" class="sp-session-location"><i class="bi bi-geo-alt"></i> {{ s.location }}</span>
                  <span class="sp-session-date">{{ formatDate(s.scheduled_at) }}</span>
                </div>
              </div>
              <button class="sp-edit-btn" @click="openEditSession(s, $event)" title="편집">
                <svg width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>
              </button>
            </div>
          </div>
        </div>
      </div>
      </div>
      <div v-if="!sidebarCollapsed" class="sidebar-resize-handle sp-resize-handle" @mousedown="onSidebarResizeStart"></div>
    </div>

    <!-- Center: Recording panel -->
    <div class="sp-main" @click.stop>

      <!-- No session selected -->
      <div v-if="!activeSession" class="sp-no-session">
        <svg width="48" height="48" fill="none" stroke="currentColor" stroke-width="1.5" viewBox="0 0 24 24" style="color:#cbd5e1"><path d="M12 14c1.66 0 3-1.34 3-3V5c0-1.66-1.34-3-3-3S9 3.34 9 5v6c0 1.66 1.34 3 3 3z"/><path d="M17 11c0 2.76-2.24 5-5 5s-5-2.24-5-5H5c0 3.53 2.61 6.43 6 6.92V21h2v-3.08c3.39-.49 6-3.39 6-6.92h-2z"/></svg>
        <p class="sp-no-session-text">좌측에서 회의를 선택하세요</p>
        <p class="sp-no-session-sub">회의를 클릭하면 녹음하고 회의록을 생성할 수 있습니다.</p>
      </div>

      <!-- Active session recording view -->
      <div v-else class="sp-panel card">
        <!-- Panel header: title + tabs -->
        <div class="sp-panel-header">
          <div class="sp-panel-title-row">
            <div class="sp-panel-title-group">
              <div class="sp-panel-title">{{ activeSession.title }}</div>
              <div v-if="activeSession.location" class="sp-panel-location">
                <i class="bi bi-geo-alt"></i> {{ activeSession.location }}
              </div>
            </div>
            <span v-if="recordingState !== 'idle'" class="rec-live" :class="{ paused: recordingState === 'paused' }">
              <i class="bi bi-record-fill"></i>
              {{ recordingState === 'recording' ? 'REC' : 'PAUSE' }}
              <span class="rec-timer">{{ formatTimer(recordingSecs) }}</span>
            </span>
          </div>
          <div class="app-tabs">
            <button class="app-tab" :class="{ active: activeTab === 'transcript' }" @click="activeTab='transcript'">대화 기록</button>
            <button class="app-tab" :class="{ active: activeTab === 'script' }" @click="activeTab='script'">스크립트</button>
            <button class="app-tab" :class="{ active: activeTab === 'minutes' }" @click="activeTab='minutes'">회의록</button>
          </div>
        </div>

        <!-- Tab content -->
        <div ref="transcriptAreaRef" class="sp-tab-body" :class="{ 'minutes-mode': activeTab==='minutes' }">
          <template v-if="activeTab === 'transcript'">
            <div v-if="showSummary" class="ts-summary-box">
              <div class="ts-summary-header">
                <span><i class="bi bi-stars"></i> AI 요약</span>
                <button class="ts-summary-close" @click="showSummary=false">✕</button>
              </div>
              <div v-if="summarizingTranscript" class="ts-summary-body">
                <span class="spinner-border spinner-border-sm text-primary"></span>
                <span style="font-size:12px;color:var(--text-muted);margin-left:6px">요약 중...</span>
              </div>
              <div v-else class="ts-summary-body minutes-md" v-html="renderMd(transcriptSummary)"></div>
            </div>
            <div v-if="!transcriptLines.length" class="sp-empty">
              <i class="bi bi-mic" style="font-size:28px;opacity:.25"></i>
              <p class="text-muted small mb-0">녹음을 시작하면 대화가 실시간으로 기록됩니다.</p>
            </div>
            <template v-for="(line, idx) in transcriptLines" :key="idx">
              <!-- 편집 모드 -->
              <div v-if="editingIdx === idx" class="tline tline-editing">
                <span class="tline-time">{{ line.time }}</span>
                <input v-model="editDraft.speaker" class="tline-edit-speaker" placeholder="발화자" />
                <textarea v-model="editDraft.text" class="tline-edit-text" rows="2" />
                <div class="tline-edit-btns">
                  <button class="tline-save-btn" @click="saveEdit(idx)">저장</button>
                  <button class="tline-cancel-btn" @click="cancelEdit">취소</button>
                </div>
              </div>
              <!-- 일반 모드 -->
              <div v-else class="tline">
                <span class="tline-time">{{ line.time }}</span>
                <span v-if="line.speaker" class="tline-speaker" :style="{ color: speakerColor(line.speaker), borderColor: speakerColor(line.speaker) }">{{ line.speaker }}</span>
                <span class="tline-body">
                  <span class="tline-text">{{ line.text }}</span>
                  <button v-if="line.id" class="tline-edit-btn" @click="startEdit(idx)" title="편집">
                    <i class="bi bi-pencil"></i>
                  </button>
                </span>
              </div>
            </template>
          </template>

          <template v-else-if="activeTab === 'script'">
            <div v-if="!transcriptLines.length" class="sp-empty">
              <i class="bi bi-file-earmark-text" style="font-size:28px;opacity:.25"></i>
              <p class="text-muted small mb-0">스크립트가 여기에 표시됩니다.</p>
            </div>
            <template v-for="(line, idx) in transcriptLines" :key="idx">
              <div v-if="editingIdx === idx" class="tline tline-editing">
                <span class="tline-time">{{ line.time }}</span>
                <input v-model="editDraft.speaker" class="tline-edit-speaker" placeholder="발화자" />
                <textarea v-model="editDraft.text" class="tline-edit-text" rows="2" />
                <div class="tline-edit-btns">
                  <button class="tline-save-btn" @click="saveEdit(idx)">저장</button>
                  <button class="tline-cancel-btn" @click="cancelEdit">취소</button>
                </div>
              </div>
              <div v-else class="tline">
                <span class="tline-time">{{ line.time }}</span>
                <span v-if="line.speaker" class="tline-speaker" :style="{ color: speakerColor(line.speaker), borderColor: speakerColor(line.speaker) }">{{ line.speaker }}</span>
                <span class="tline-body">
                  <span class="tline-text">{{ line.text }}</span>
                  <button v-if="line.id" class="tline-edit-btn" @click="startEdit(idx)" title="편집">
                    <i class="bi bi-pencil"></i>
                  </button>
                </span>
              </div>
            </template>
          </template>

          <template v-else-if="activeTab === 'minutes'">
            <div class="minutes-scroll-area" :class="{ 'has-nab': showNextAgendaBlock && generatedMinutes }">
              <div v-if="generatingMinutes && !generatedMinutes?.content_summary" class="sp-empty">
                <span class="spinner-border spinner-border-sm text-primary mb-2"></span>
                <p class="text-muted small">AI가 회의록을 생성 중입니다...</p>
              </div>
              <template v-else-if="generatedMinutes">
                <!-- Tiptap Toolbar -->
                <div class="tiptap-toolbar">
                  <button class="tt-btn" :class="{active: editor?.isActive('bold')}" @click="editor?.chain().focus().toggleBold().run()" title="굵게"><b>B</b></button>
                  <button class="tt-btn" :class="{active: editor?.isActive('italic')}" @click="editor?.chain().focus().toggleItalic().run()" title="기울임"><i>I</i></button>
                  <button class="tt-btn" :class="{active: editor?.isActive('underline')}" @click="editor?.chain().focus().toggleUnderline().run()" title="밑줄"><u>U</u></button>
                  <div class="tt-sep"></div>
                  <button class="tt-btn" :class="{active: editor?.isActive('heading', {level:1})}" @click="editor?.chain().focus().toggleHeading({level:1}).run()">H1</button>
                  <button class="tt-btn" :class="{active: editor?.isActive('heading', {level:2})}" @click="editor?.chain().focus().toggleHeading({level:2}).run()">H2</button>
                  <button class="tt-btn" :class="{active: editor?.isActive('heading', {level:3})}" @click="editor?.chain().focus().toggleHeading({level:3}).run()">H3</button>
                  <div class="tt-sep"></div>
                  <button class="tt-btn" :class="{active: editor?.isActive('bulletList')}" @click="editor?.chain().focus().toggleBulletList().run()" title="글머리">•≡</button>
                  <button class="tt-btn" :class="{active: editor?.isActive('orderedList')}" @click="editor?.chain().focus().toggleOrderedList().run()" title="번호목록">1≡</button>
                  <div class="tt-sep"></div>
                  <button class="tt-btn" @click="editor?.chain().focus().setHorizontalRule().run()" title="구분선">—</button>
                  <div class="tt-sep"></div>
                  <button class="tt-btn" @click="editor?.chain().focus().undo().run()" title="실행취소">↩</button>
                  <button class="tt-btn" @click="editor?.chain().focus().redo().run()" title="다시실행">↪</button>
                  <div style="flex:1"></div>
                  <span v-if="generatedMinutes.sources" class="tt-source-info" :title="`기반 자료: 발화 ${generatedMinutes.sources.stt_count}개 · ${generatedMinutes.sources.session_title}`">
                    <i class="bi bi-mic-fill"></i> {{ generatedMinutes.sources.stt_count }}개
                  </span>
                  <div class="tt-sep" v-if="generatedMinutes.sources"></div>
                  <button class="tt-btn tt-delete" :disabled="generatingMinutes" @click="deleteMinutes" title="삭제"><i class="bi bi-trash"></i></button>
                </div>

                <!-- Streaming preview (Markdown rendered) -->
                <div v-if="generatingMinutes" class="tiptap-content minutes-md" v-html="renderMd(generatedMinutes.content_summary||'')"></div>
                <!-- Tiptap Editor -->
                <editor-content v-else :editor="editor" class="tiptap-content" />

              </template>
              <div v-else class="sp-empty"><p class="text-muted small">회의록이 없습니다.</p></div>
            </div>

            <!-- ── 다음 회의 과제 승인/반려 블록 (에디터 영역 밖) ── -->
            <div v-if="generatedMinutes && showNextAgendaBlock" class="next-agenda-block">
              <div class="nab-header">
                <div class="nab-title-row">
                  <svg width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2"/><rect x="9" y="3" width="6" height="4" rx="1" ry="1"/><path d="M9 12h6M9 16h4"/></svg>
                  <span>다음 회의 과제</span>
                  <span class="nab-badge">회의록 기반 AI 추출</span>
                </div>
                <p class="nab-desc">회의록에서 추출한 과제를 검토하고 승인/반려해 주세요.</p>
              </div>

              <div v-if="nextAgendaExtracting" class="nab-loading">
                <div class="nab-spinner"></div><span>과제 추출 중...</span>
              </div>
              <template v-else-if="nextAgendaItems.length">
                <div class="nab-list">
                  <AgendaReviewList
                    :items="nextAgendaItems"
                    :removeOnApprove="false"
                    @approved="() => {}"
                    @rejected="removeNextAgendaItem"
                    @remove="removeNextAgendaItem"
                  />
                </div>

                <div class="nab-footer">
                  <button class="nab-add-btn" @click="addNextAgendaItem">
                    <svg width="10" height="10" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24"><path d="M12 5v14M5 12h14"/></svg> 과제 직접 추가
                  </button>
                  <div class="nab-footer-right">
                    <span class="nab-count">승인 {{ nextAgendaItems.filter(a=>a._state==='approved'||a._state==='saved').length }} / 반려 {{ nextAgendaItems.filter(a=>a._state==='rejected').length }}</span>
                    <button class="nab-save-btn" :disabled="!nextAgendaItems.filter(a=>a._state==='approved').length" @click="saveApprovedNextAgendas">
                      승인 {{ nextAgendaItems.filter(a=>a._state==='approved').length }}건 저장
                    </button>
                  </div>
                </div>
              </template>
            </div>

          </template>
        </div>

        <!-- Control bar (대화기록/스크립트 탭) -->
        <div v-if="activeTab !== 'minutes'" class="sp-ctrl-bar" @click.stop>
          <div v-show="activeSession?.status !== 'archived'" class="ctrl-group-left">
            <!-- Language selector -->
            <div class="ctrl-pop-wrap">
              <button class="ctrl-btn ctrl-lang" :class="{ 'ctrl-active': showPopover==='lang' }"
                @click.stop="togglePopover('lang')" title="언어">
                <i class="bi bi-headphones"></i>
                <span>{{ transcriptLang==='ko'?'한국어':'English' }}</span>
                <i class="bi bi-chevron-down ctrl-chev"></i>
              </button>
              <div v-if="showPopover==='lang'" class="ctrl-popover" @click.stop>
                <div class="cpop-title">대화기록 언어</div>
                <button class="cpop-opt" :class="{ selected: transcriptLang==='ko' }" @click="transcriptLang='ko';showPopover=null">🇰🇷 한국어</button>
                <button class="cpop-opt" :class="{ selected: transcriptLang==='en' }" @click="transcriptLang='en';showPopover=null">🇺🇸 English</button>
              </div>
            </div>

            <!-- STT mode selector -->
            <div class="ctrl-pop-wrap">
              <button class="ctrl-btn ctrl-lang" :class="{ 'ctrl-active': showPopover==='stt' }"
                @click.stop="togglePopover('stt')" title="STT 방식">
                <i class="bi bi-soundwave"></i>
                <span>{{ STT_MODE_LABELS[sttMode] }}</span>
                <i class="bi bi-chevron-down ctrl-chev"></i>
              </button>
              <div v-if="showPopover==='stt'" class="ctrl-popover" @click.stop>
                <div class="cpop-title">STT 설정</div>
                <button class="cpop-opt" :class="{ selected: sttMode==='gcapi' }"
                  @click="sttMode='gcapi';showPopover=null">
                  <i class="bi bi-people" style="margin-right:5px"></i>Google Cloud API
                </button>
                <button class="cpop-opt" :class="{ selected: sttMode==='whisperapi' }"
                  @click="sttMode='whisperapi';showPopover=null">
                  <i class="bi bi-lightning-charge" style="margin-right:5px"></i>Whisper API
                </button>
                <button class="cpop-opt" :class="{ selected: sttMode==='localwhisper' }"
                  @click="sttMode='localwhisper';showPopover=null">
                  <i class="bi bi-shield-lock" style="margin-right:5px"></i>Local
                </button>
              </div>
            </div>

            <!-- Record / pause -->
            <button class="ctrl-rec-btn" :class="{ recording: recordingState==='recording' }"
              @click.stop="toggleRecording"
              :title="recordingState==='idle'?'녹음 시작':recordingState==='recording'?'일시정지':'재개'">
              <i v-if="recordingState!=='recording'" class="bi bi-play-fill"></i>
              <i v-else class="bi bi-pause-fill"></i>
            </button>

            <button class="ctrl-end" @click.stop="endMeeting">기록 종료</button>
          </div>
          <div class="ctrl-group-right">
            <span v-if="micError" class="mic-error-msg">⚠ {{ micError }}</span>
          </div>
        </div>

        <!-- Minutes bar (회의록 탭) -->
        <div v-if="activeTab === 'minutes'" class="sp-minutes-bar" @click.stop>
          <div class="minutes-bar-left">
            <button class="mbar-btn" :disabled="!generatedMinutes || generatingMinutes" @click="downloadPDF">
              <i class="bi bi-file-earmark-pdf"></i> PDF
            </button>
            <button class="mbar-btn" :disabled="!generatedMinutes || generatingMinutes" @click="downloadWord">
              <i class="bi bi-file-earmark-word"></i> Word
            </button>
            <button class="mbar-btn" :disabled="minutesFileUploading" @click="minutesFileRef?.click()" title="회의록 관련 파일 업로드">
              <i v-if="minutesFileUploading" class="bi bi-arrow-repeat spin"></i>
              <i v-else class="bi bi-file-earmark-arrow-up"></i>
              {{ minutesFileUploading ? '업로드 중...' : '파일 업로드' }}
            </button>
            <button v-if="minutesFileUrl" class="mbar-btn" @click="downloadMinutesFile" title="R2에 저장된 PDF 다운로드">
              <i class="bi bi-cloud-download"></i> PDF 다운로드
            </button>
            <input ref="minutesFileRef" type="file" accept=".pdf,.doc,.docx,.hwp" style="display:none" @change="uploadMinutesFile" />
          </div>
          <div class="minutes-bar-right">
            <span v-if="minutesSavedAt" class="mbar-saved-label">
              <i class="bi bi-check-circle-fill"></i> {{ minutesSavedAt }} 저장됨
            </span>
            <button class="mbar-btn primary" :disabled="savingMinutes || generatingMinutes" @click="saveMinutesToDB">
              <i v-if="savingMinutes" class="bi bi-arrow-repeat spin"></i>
              <i v-else class="bi bi-cloud-upload"></i>
              {{ savingMinutes ? '저장 중...' : '아카이브 저장' }}
            </button>
            <button class="mbar-btn regen" :disabled="generatingMinutes" @click.stop="generateMinutes">
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
          <button class="agent-new-chat-btn" @click="wmMessages=[{role:'agent',content:'안녕하세요! 워크메이트 AI입니다 😊\n무엇이든 질문하세요.'}]">새 채팅</button>
        </div>
      </div>
      <div ref="messagesEl" class="agent-messages">
        <div v-for="(msg, i) in wmMessages" :key="i" class="agent-msg-row" :class="msg.role === 'thinking' ? 'planning' : msg.role">

          <!-- 사고 과정 블록 -->
          <template v-if="msg.role==='thinking'">
            <div class="agent-planning-block" :class="{ done: msg.done, open: msg.open }">
              <button class="agent-planning-toggle" @click="msg.open = !msg.open">
                <svg v-if="!msg.done" class="agent-planning-spinner" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="#00ab36" stroke-width="2.5"><path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83"/></svg>
                <svg v-else width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="#00ab36" stroke-width="2.5"><path d="M9 12l2 2 4-4"/><circle cx="12" cy="12" r="10"/></svg>
                <span class="agent-planning-label">{{ msg.done ? 'Knowledge Graph 조회 완료' : 'Knowledge Graph 분석 중...' }}</span>
                <span class="agent-planning-count">{{ msg.steps.length }} queries</span>
                <svg class="agent-planning-chev" :class="{ rotated: msg.open }" width="11" height="11" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M19 9l-7 7-7-7"/></svg>
              </button>
              <div v-if="msg.open" class="agent-planning-steps">
                <div v-for="(step, si) in msg.steps" :key="si"
                     class="agent-planning-step fade-in"
                     :class="{
                       'agent-step-cypher': step.includes('MATCH') || step.includes('RETURN'),
                       'agent-step-data':   !step.includes('MATCH') && (step.includes('→') || step.includes('수신') || step.includes('수집') || step.includes('발견')),
                       'agent-step-route':  step.includes('위임') || step.includes('라우팅'),
                     }">
                  <span v-if="step.includes('MATCH') || step.includes('RETURN')" class="agent-step-icon-cypher">
                    <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><ellipse cx="12" cy="5" rx="9" ry="3"/><path d="M3 5v14c0 1.66 4.03 3 9 3s9-1.34 9-3V5"/><path d="M3 12c0 1.66 4.03 3 9 3s9-1.34 9-3"/></svg>
                  </span>
                  <span v-else-if="step.includes('→') || step.includes('수신') || step.includes('수집') || step.includes('발견')" class="agent-step-icon-data">
                    <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><circle cx="8" cy="12" r="3"/><circle cx="18" cy="7" r="2"/><circle cx="18" cy="17" r="2"/><line x1="11" y1="11" x2="16" y2="8"/><line x1="11" y1="13" x2="16" y2="16"/></svg>
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
          <template v-else-if="msg.role==='agent'&&msg.content">
            <div class="agent-msg-label">
              <img :src="hyeanAvatar" class="agent-msg-avatar" />워크메이트 AI
            </div>
            <div class="agent-bubble agent theme-supervisor" v-html="renderMd(msg.content)"></div>
          </template>

          <!-- 사용자 메시지 -->
          <div v-else-if="msg.role==='user'" class="agent-bubble user">
            <span>{{ msg.content }}</span>
            <div v-if="msg.contexts?.length" class="user-ctx-chips">
              <span v-for="c in msg.contexts" :key="c.id" class="user-ctx-chip">{{ c.icon }} {{ c.label }}</span>
            </div>
            <button v-if="msg.filePath" class="sp-file-dl-btn" @click="downloadChatFile(msg.filePath)" title="파일 다운로드">
              <svg width="11" height="11" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
            </button>
          </div>
        </div>
        <div v-if="wmLoading&&wmMessages[wmMessages.length-1]?.role==='agent'&&wmMessages[wmMessages.length-1]?.content===''" class="agent-msg-row agent">
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
        :attach-disabled="chatFileUploading || !activeSession"
        :multiple-files="false"
        @input="onWmInput"
        @keydown="onWmKeydown"
        @send="sendAra"
        @select-at-item="selectWmAtItem"
        @remove-ctx="removeWmCtx"
        @file-change="e => sendChatFile(e.target.files[0])"
        @ready="onWmComposerReady"
      />
    </div>

  </div>


  <SessionEditModal
    :show="showEditSession"
    :session="currentEditSession"
    @close="showEditSession=false"
    @saved="onSessionEditSaved"
  />

  <CreateSessionModal
    :show="showCreateSession"
    :meetings="meetings"
    :lockedUserId="authStore.user?.id"
    @close="showCreateSession=false"
    @saved="onSessionCreated"
  />
</template>

<style scoped>
/* ── Layout ── */
.sp-layout { display:flex;flex-direction:row !important;gap:0; }

/* ── Left sidebar (session selector) ── */
.sp-sidebar { position:relative;width:220px;flex-shrink:0;border-right:1px solid var(--border);background:var(--bg-card);height:100%; }
.sp-sidebar.collapsed { width:0;border-right:none; }
.sp-sidebar-inner { display:flex;flex-direction:column;height:100%;overflow:hidden; }
.sp-sidebar.collapsed .sp-sidebar-inner { opacity:0;pointer-events:none; }
.sp-toggle-handle { position:absolute;top:50%;left:100%;transform:translateY(-50%);width:16px;height:48px;display:flex;align-items:center;justify-content:center;padding:0;border:1px solid var(--border);border-left:none;border-radius:0 8px 8px 0;background:var(--bg-card);color:var(--text-muted);cursor:pointer;z-index:25; }
.sp-toggle-handle:hover { background:var(--surface-2);color:var(--primary); }
.sp-resize-handle { position:absolute;top:0;right:-3px;width:6px;height:100%;cursor:col-resize;z-index:20;background:transparent; }
.sp-resize-handle:hover { background:rgba(59,130,246,.25); }
.sp-sidebar-header { padding:14px 16px;border-bottom:1px solid var(--border);flex-shrink:0; }
.sp-header-top { display:flex;align-items:center;justify-content:space-between;margin-bottom:0; }
/* ── Session create modal ── */
.sp-mi:focus { border-color:var(--primary); }
.sp-ms-wrap { display:flex;align-items:center;gap:6px;border:1px solid var(--border);border-radius:8px;padding:5px 8px; }
.sp-ms-input { flex:1;border:none;outline:none;font-size:12px;color:var(--dark-card); }
.sp-ms-results { border:1px solid var(--border);border-radius:8px;overflow:hidden;margin-top:4px; }
.sp-ms-item { display:flex;align-items:center;gap:8px;padding:7px 10px;border-bottom:1px solid var(--border);font-size:12px; }
.sp-ms-item:last-child { border-bottom:none; }
.sp-ms-info { flex:1;min-width:0; }
.sp-ms-name { font-weight:600;color:var(--dark-card);display:block; }
.sp-ms-email { color:var(--dark-muted);font-size:11px;display:block; }
.sp-ms-role { padding:3px 8px;border-radius:5px;border:1px solid var(--border);background:var(--surface);color:var(--text-dim);font-size:11px;font-weight:600;cursor:pointer; }
.sp-ms-role.admin { border-color:var(--accent);background:rgba(59,130,246,.1);color:var(--accent); }
.stt-type-btn { flex:1;padding:8px;border-radius:8px;border:1px solid var(--border);background:var(--surface);color:var(--text);font-size:12px;cursor:pointer; }
.stt-type-btn.active { border-color:var(--accent);background:rgba(59,130,246,.1);color:var(--accent);font-weight:600; }
.sp-sm-row { display:flex;align-items:center;gap:8px;padding:5px 8px;background:var(--surface);border-radius:7px;font-size:12px; }
.sp-sm-name { flex:1;font-weight:600;color:var(--dark-card); }
.sp-sm-role-tag { padding:2px 7px;border-radius:5px;font-size:11px;font-weight:600; }
.sp-sm-role-tag.admin { background:rgba(59,130,246,.1);color:var(--accent); }
.sp-sm-role-tag.member { background:rgba(34,197,94,.1);color:#16a34a; }
.sp-sm-rm { background:none;border:none;cursor:pointer;color:var(--dark-muted);font-size:15px;line-height:1; }
.sp-sm-rm:hover { color:var(--danger); }
.sp-sidebar-title { font-size:16px;font-weight:700;color:var(--dark-text);margin:0; }
.day-mode .sp-sidebar-title { color:var(--dark-card); }
.sp-sidebar-body { flex:1;overflow-y:auto;padding:0; }

.sp-mtg-group { border-bottom:1px solid var(--surface-2); }
.sp-mtg-header { display:flex;align-items:center;gap:7px;padding:10px 14px;cursor:pointer;user-select:none; }
.sp-mtg-header.expanded { background:var(--surface); }
.sp-mtg-dot { width:6px;height:6px;background:var(--primary);border-radius:50%;flex-shrink:0; }
.sp-mtg-title { flex:1;font-size:12px;font-weight:600;color:var(--text);overflow:hidden;text-overflow:ellipsis;white-space:nowrap; }
.sp-mtg-chev { color:var(--text-muted);transition:transform .2s;flex-shrink:0; }
.sp-mtg-chev.open { transform:rotate(180deg); }

.sp-session-list { background:var(--surface);border-top:1px solid var(--surface-2); }
.sp-session-item { display:flex;align-items:center;gap:6px;padding:8px 14px;cursor:pointer; }
.sp-session-item:hover { background:rgba(59,130,246,.1); }
.sp-session-item.active { background:rgba(59,130,246,.1); }
.sp-session-info { flex:1;min-width:0; }
.sp-session-name { font-size:11px;font-weight:600;color:var(--text);overflow:hidden;text-overflow:ellipsis;white-space:nowrap; }
.sp-session-meta { display:flex;align-items:center;gap:6px;margin-top:4px;overflow:hidden; }
.sp-session-date { font-size:10px;color:var(--text-muted);flex-shrink:0;margin-left:auto; }
.sp-session-location { font-size:10px;color:var(--text-dim);overflow:hidden;text-overflow:ellipsis;white-space:nowrap; }
.sp-status-badge { font-size:9px;font-weight:700;padding:2px 6px;border-radius:99px;flex-shrink:0; }
.sp-edit-btn { background:none;border:none;cursor:pointer;color:var(--text-muted);padding:2px;display:flex;align-items:center;flex-shrink:0;border-radius:4px; }
.sp-edit-btn:hover { color:var(--primary);background:var(--surface-2); }

/* ── Center panel ── */
.sp-main { flex:1;display:flex;flex-direction:column;align-items:stretch;justify-content:center;padding:0 3px;overflow:visible;min-width:0; }

.sp-no-session { display:flex;flex-direction:column;align-items:center;justify-content:center;height:100%;gap:10px;color:var(--text-muted); }
.sp-no-session-text { font-size:14px;font-weight:600;margin:0; }
.sp-no-session-sub { font-size:12px;margin:0;opacity:.7; }

.sp-panel { display:flex;flex-direction:column;height:100%;overflow:visible;border-radius:0 !important; }
.sp-panel-header { display:flex;align-items:center;justify-content:space-between;padding:6px 8px;border-bottom:1px solid var(--border);flex-shrink:0;gap:12px; }
.sp-panel-title-row { display:flex;align-items:center;gap:8px;min-width:0; }
.sp-panel-title-group { display:flex;flex-direction:column;min-width:0;flex:1; }
.sp-panel-title { font-size:14px;font-weight:700;color:var(--dark-card);overflow:hidden;text-overflow:ellipsis;white-space:nowrap; }
.sp-panel-location { font-size:11px;color:var(--text-muted);margin-top:1px; }
.rec-live { font-size:11px;font-weight:700;color:var(--danger);display:flex;align-items:center;gap:3px;flex-shrink:0;animation:pulse 1.2s infinite; }
@keyframes pulse { 0%,100%{opacity:1}50%{opacity:.4} }


.sp-tab-body { flex:1;overflow-y:auto;padding:12px 16px;display:flex;flex-direction:column;gap:4px;min-height:0; }
.sp-tab-body::-webkit-scrollbar { width:4px; }
.sp-tab-body::-webkit-scrollbar-thumb { background:var(--border); }
.minutes-scroll-area { flex:1;overflow-y:auto;display:flex;flex-direction:column;gap:4px;min-height:0;padding-bottom:8px; }
.minutes-scroll-area::-webkit-scrollbar { width:4px; }
.minutes-scroll-area::-webkit-scrollbar-thumb { background:var(--border); }
.sp-tab-body.minutes-mode { overflow:hidden;padding:0;display:flex;flex-direction:column; }
.sp-tab-body.minutes-mode .minutes-scroll-area { padding:12px 16px 0; }
.sp-tab-body.minutes-mode .minutes-scroll-area.has-nab { flex:0 1 50%;min-height:0; }
.sp-tab-body.minutes-mode .minutes-action-row { padding:10px 16px 8px;margin:0; }
.sp-empty { display:flex;flex-direction:column;align-items:center;justify-content:center;height:100%;gap:8px;color:var(--text-muted); }

/* Transcript lines */
.tline { display:flex;gap:8px;align-items:baseline;padding:3px 0;position:relative; }
.tline:hover .tline-edit-btn { opacity:1; }
.tline-time { font-size:10px;color:var(--text-muted);flex-shrink:0;font-family:monospace; }
.tline-speaker {
  font-size:10px;font-weight:700;flex-shrink:0;
  padding:1px 6px;border-radius:99px;border:1px solid;
  letter-spacing:.04em;
}
.tline-body { display:flex;align-items:baseline;flex:1;min-width:0; }
.tline-text { font-size:13px;color:var(--dark-card);line-height:1.5;flex:1; }
.tline-edit-btn { opacity:0;transition:opacity .15s;background:none;border:none;cursor:pointer;color:var(--text-muted);font-size:11px;padding:1px 4px;border-radius:4px;flex-shrink:0;margin-left:2px; }
.tline-edit-btn:hover { color:var(--accent);background:rgba(96,165,250,.1); }

/* 편집 모드 */
.tline-editing { flex-wrap:wrap;align-items:flex-start;gap:6px;background:var(--surface);border-radius:8px;padding:6px 8px;margin:2px 0; }
.tline-edit-speaker { font-size:11px;font-weight:700;border:1px solid var(--border);border-radius:6px;padding:2px 8px;width:72px;outline:none;background:var(--bg-card);color:var(--dark-card); }
.tline-edit-text { flex:1;font-size:13px;border:1px solid var(--border);border-radius:6px;padding:4px 8px;resize:vertical;outline:none;background:var(--bg-card);color:var(--dark-card);min-width:200px;line-height:1.5; }
.tline-edit-btns { display:flex;gap:4px;flex-shrink:0;align-items:center; }
.tline-save-btn { font-size:11px;font-weight:700;padding:3px 10px;border-radius:5px;border:none;background:var(--accent);color:#fff;cursor:pointer; }
.tline-save-btn:hover { background:#2563eb; }
.tline-cancel-btn { font-size:11px;padding:3px 8px;border-radius:5px;border:1px solid var(--border);background:none;color:var(--text-muted);cursor:pointer; }

/* REC 타이머 */
.rec-live.paused { background:rgba(100,116,139,.15);color:var(--text-muted); }
.rec-timer { font-family:monospace;font-size:11px;margin-left:4px;letter-spacing:.05em; }
.mic-error-msg { font-size:11px;color:#f87171;display:flex;align-items:center;gap:4px; }

/* AI summary box */
.ts-summary-box { background:var(--surface);border:1px solid var(--border);border-radius:8px;margin-bottom:12px;overflow:hidden; }
.ts-summary-header { display:flex;align-items:center;justify-content:space-between;padding:8px 12px;background:var(--surface-2);border-bottom:1px solid var(--border);font-size:12px;font-weight:600;color:var(--text-dim); }
.ts-summary-close { background:none;border:none;cursor:pointer;color:var(--dark-muted);font-size:13px;line-height:1; }
.ts-summary-body { padding:10px 12px;font-size:13px;color:var(--dark-border);line-height:1.6; }

/* Minutes – Tiptap editor */
.tiptap-toolbar { display:flex;align-items:center;gap:2px;padding:6px 4px;border-bottom:1px solid var(--border);background:transparent;flex-wrap:wrap;margin-bottom:8px; }
.tt-btn { display:inline-flex;align-items:center;justify-content:center;min-width:28px;height:26px;padding:0 5px;border:1px solid transparent;border-radius:4px;background:none;color:var(--text-dim);font-size:12px;cursor:pointer;transition:all .1s;user-select:none; }
.tt-btn:hover { background:var(--border); }
.tt-btn.active { background:#dbeafe;color:#1d4ed8;border-color:#bfdbfe; }
.tt-delete { color:var(--danger) !important; }
.tt-delete:hover { background:#fef2f2 !important; }
.tt-delete:disabled { opacity:.4;cursor:not-allowed;pointer-events:none; }
.tt-sep { width:1px;height:18px;background:var(--border);margin:0 3px; }

.tiptap-content { border:none;padding:4px 0;min-height:400px;background:transparent;outline:none; }
.tiptap-content :deep(.ProseMirror) { outline:none;min-height:380px; }
.tiptap-content :deep(.ProseMirror p) { margin:0 0 6px;font-size:13px;line-height:1.7;color:var(--dark-card); }
.tiptap-content :deep(.ProseMirror h1) { font-size:17px;font-weight:800;margin:0 0 12px;padding-bottom:8px;border-bottom:2px solid var(--border);color:var(--dark-bg); }
.tiptap-content :deep(.ProseMirror h2) { font-size:15px;font-weight:700;margin:16px 0 6px;color:#1e40af; }
.tiptap-content :deep(.ProseMirror h3) { font-size:13px;font-weight:700;margin:10px 0 4px;color:var(--text-dim); }
.tiptap-content :deep(.ProseMirror strong) { font-weight:700; }
.tiptap-content :deep(.ProseMirror em) { font-style:italic; }
.tiptap-content :deep(.ProseMirror u) { text-decoration:underline; }
.tiptap-content :deep(.ProseMirror ul),.tiptap-content :deep(.ProseMirror ol) { padding-left:20px;margin:4px 0; }
.tiptap-content :deep(.ProseMirror li) { margin-bottom:2px;font-size:13px;line-height:1.6; }
.tiptap-content :deep(.ProseMirror li > p) { margin:0; }
.tiptap-content :deep(.ProseMirror table) { width:100%;border-collapse:collapse;margin:8px 0;font-size:12px;table-layout:fixed; }
.tiptap-content :deep(.ProseMirror th),.tiptap-content :deep(.ProseMirror td) { border:1px solid var(--border);padding:6px 10px;text-align:left;vertical-align:top;word-break:break-word; }
.tiptap-content :deep(.ProseMirror th) { background:var(--surface-2);font-weight:600;font-size:12px; }
.tiptap-content :deep(.ProseMirror td > p),.tiptap-content :deep(.ProseMirror th > p) { margin:0; }
.tiptap-content :deep(.ProseMirror hr) { border:none;border-top:1px solid var(--border);margin:12px 0; }
.tiptap-content :deep(.ProseMirror blockquote) { border-left:3px solid var(--border);padding-left:12px;color:var(--text-muted);margin:6px 0; }

/* Streaming preview uses same styles */
.minutes-md { font-size:13px;line-height:1.7;color:var(--dark-card); }
.minutes-md :deep(h1) { font-size:17px;font-weight:800;margin:0 0 12px;padding-bottom:8px;border-bottom:2px solid var(--border); }
.minutes-md :deep(h2) { font-size:15px;font-weight:700;margin:16px 0 6px;color:#1e40af; }
.minutes-md :deep(h3) { font-size:13px;font-weight:700;margin:10px 0 4px;color:var(--text-dim); }
.minutes-md :deep(strong) { font-weight:700; }
.minutes-md :deep(ul),.minutes-md :deep(ol) { padding-left:18px;margin:4px 0; }
.minutes-md :deep(li) { margin-bottom:2px; }
.minutes-md :deep(table) { width:100%;border-collapse:collapse;margin:8px 0;font-size:12px; }
.minutes-md :deep(th),.minutes-md :deep(td) { border:1px solid var(--border);padding:5px 8px;text-align:left; }
.minutes-md :deep(th) { background:var(--surface);font-weight:600; }
.minutes-md :deep(hr) { border:none;border-top:1px solid var(--border);margin:12px 0; }

.tt-source-info { display:inline-flex;align-items:center;gap:3px;font-size:11px;color:var(--dark-muted);padding:0 4px;white-space:nowrap;cursor:default; }


/* Control bar */
.sp-ctrl-bar { display:flex;align-items:center;justify-content:space-between;padding:10px 16px;border-top:1px solid var(--border);flex-shrink:0;background:var(--bg-card);overflow:visible;border-radius:0; }
.ctrl-group-left,.ctrl-group-right { display:flex;align-items:center;gap:12px; }
.ctrl-group-right { margin-left:auto; }
.ctrl-pop-wrap { position:relative; }
.ctrl-btn { display:flex;align-items:center;gap:3px;padding:6px 10px;border-radius:8px;border:1px solid var(--border);background:var(--bg-card);color:var(--text-dim);font-size:13px;cursor:pointer; }
.ctrl-btn:hover,.ctrl-active { background:var(--surface-2);border-color:var(--primary);color:var(--primary); }
.ctrl-lang { font-size:12px;gap:4px; }
.ctrl-chev { font-size:9px;opacity:.6; }
.ctrl-popover { position:absolute;bottom:calc(100% + 6px);left:0;background:var(--bg-card);border:1px solid var(--border);border-radius:10px;box-shadow:0 8px 24px rgba(0,0,0,.12);padding:10px 12px;min-width:160px;z-index:200; }
.cpop-title { font-size:11px;font-weight:700;color:var(--text-muted);text-transform:uppercase;margin-bottom:8px; }
.cpop-row { display:flex;align-items:center;gap:8px;margin-bottom:6px;font-size:12px;color:var(--text-dim); }
.cpop-label { flex:1; }
.cpop-range { flex:1;accent-color:var(--primary); }
.cpop-val { font-size:11px;font-weight:600;min-width:28px;text-align:right; }
.cpop-opt { display:block;width:100%;text-align:left;padding:7px 10px;border-radius:6px;border:none;background:none;font-size:13px;cursor:pointer;color:var(--text-dim);transition:background .1s; }
.cpop-opt:hover { background:var(--surface-2); }
.cpop-opt.selected { background:rgba(59,130,246,.1);color:var(--accent);font-weight:600; }
.ctrl-rec-btn { width:34px;height:34px;border-radius:50%;border:none;background:var(--primary);color:#fff;font-size:15px;display:flex;align-items:center;justify-content:center;cursor:pointer;box-shadow:0 2px 8px rgba(59,130,246,.3);line-height:1; }
.ctrl-rec-btn.recording { background:var(--danger);box-shadow:0 2px 8px rgba(239,68,68,.35); }
.ctrl-rec-btn:hover { opacity:.85; }
.ctrl-rec-btn i { display:flex;align-items:center;justify-content:center;width:100%;height:100%; }
.ctrl-stop { color:var(--danger);border-color:#fca5a5; }
.ctrl-stop:hover { background:#fef2f2;border-color:var(--danger); }
.ctrl-end { height:34px;padding:0 14px;border-radius:17px;border:none;background:#fef2f2;color:var(--danger);font-size:12px;font-weight:600;cursor:pointer;display:flex;align-items:center; }
.ctrl-end:hover { background:var(--danger);color:#fff;border-color:var(--danger); }
.ctrl-minutes { display:flex;align-items:center;gap:5px;padding:7px 14px;border-radius:8px;border:none;background:var(--warning);color:#fff;font-size:12px;font-weight:700;cursor:pointer; }
.ctrl-minutes:disabled { opacity:.5;cursor:not-allowed; }

/* ── Left sidebar search ── */
.sp-search-wrap { position:relative;display:flex;align-items:center;margin-top:10px; }
.sp-search-icon { position:absolute;left:9px;top:50%;transform:translateY(-50%);color:var(--dark-muted);pointer-events:none; }
.sp-search-input { width:100%;padding:7px 28px;border:1px solid var(--border);border-radius:8px;font-size:12px;color:var(--text);background:var(--bg-card);outline:none;box-sizing:border-box; }
.sp-search-input:focus { border-color:var(--accent); }
.sp-search-input::placeholder { color:var(--dark-muted); }
.sp-search-clear { position:absolute;right:6px;background:none;border:none;cursor:pointer;color:var(--dark-muted);font-size:14px;line-height:1;padding:0; }
.sp-search-clear:hover { color:var(--text-dim); }
.sp-search-empty { padding:20px 14px;text-align:center;font-size:12px;color:var(--dark-muted); }

/* ── Right: 워크메이트 AI ── */
.sp-agent-right-sidebar { position:relative;width:290px;flex-shrink:0;border-left:1px solid var(--border);display:flex;flex-direction:column;background:var(--bg-card);overflow:hidden;height:100%; }
.sp-agent-resize-handle { position:absolute;top:0;left:-3px;width:6px;height:100%;cursor:col-resize;z-index:20;background:transparent; }
.sp-agent-resize-handle:hover { background:rgba(59,130,246,.25); }

/* ── Minutes action row ── */
.minutes-action-row { display:flex;align-items:center;justify-content:space-between;gap:8px;padding:10px 0 2px;border-top:1px solid var(--border);flex-shrink:0; }
.minutes-action-left,.minutes-action-right { display:flex;align-items:center;gap:6px; }
.minutes-download-group { display:flex;gap:4px; }
.minutes-action-btn { display:inline-flex;align-items:center;gap:5px;padding:6px 12px;border-radius:7px;border:1px solid var(--border);background:var(--bg-card);color:var(--text-dim);font-size:12px;font-weight:500;cursor:pointer;white-space:nowrap; }
.minutes-action-btn:hover { background:var(--surface-2); }
.minutes-action-btn.primary { background:var(--primary);color:#fff;border-color:var(--primary); }
.minutes-action-btn.primary:hover { opacity:.88; }
.minutes-action-btn:disabled { opacity:.5;cursor:not-allowed; }
.minutes-saved-label { font-size:11px;color:#22c55e;display:flex;align-items:center;gap:4px; }
@keyframes spin { to { transform:rotate(360deg); } }
.spin { display:inline-block;animation:spin .7s linear infinite; }

/* Minutes bottom bar */
.sp-minutes-bar { display:flex;align-items:center;justify-content:space-between;padding:10px 16px;border-top:1px solid var(--border);flex-shrink:0;background:var(--bg-card);border-radius:0;flex-wrap:wrap;gap:8px; }
.minutes-bar-left,.minutes-bar-right { display:flex;align-items:center;gap:6px;flex-wrap:wrap; }
.mbar-btn { display:inline-flex;align-items:center;gap:5px;padding:6px 14px;border-radius:7px;border:1px solid var(--border);background:var(--bg-card);color:var(--text-dim);font-size:12px;font-weight:500;cursor:pointer;white-space:nowrap; }
.mbar-btn:hover { background:var(--surface-2); }
.mbar-btn.primary { background:var(--primary);color:#fff;border-color:var(--primary); }
.mbar-btn.primary:hover { opacity:.88; }
.mbar-btn.regen { background:var(--surface);border-color:#c7d2fe;color:#4f46e5; }
.mbar-btn.regen:hover { background:#eef2ff; }
.mbar-btn:disabled { opacity:.45;cursor:not-allowed; }
.mbar-saved-label { font-size:11px;color:#22c55e;display:flex;align-items:center;gap:4px; }
.sp-attach-btn { display:flex;align-items:center;justify-content:center;width:28px;height:28px;border-radius:7px;border:1px solid var(--border);background:transparent;color:var(--text-muted);cursor:pointer;flex-shrink:0; }
.sp-attach-btn:hover { background:var(--surface-2);color:var(--primary); }
.sp-attach-btn:disabled { opacity:.35;cursor:not-allowed; }
.sp-file-dl-btn { display:inline-flex;align-items:center;justify-content:center;width:20px;height:20px;margin-left:4px;border-radius:4px;border:none;background:rgba(255,255,255,.25);color:inherit;cursor:pointer;vertical-align:middle; }
.sp-file-dl-btn:hover { background:rgba(255,255,255,.4); }

/* ── 다음 회의 과제 블록 ── */
.next-agenda-block { border:1px solid rgba(99,102,241,.25);border-radius:10px;background:rgba(99,102,241,.04);overflow-y:auto;flex-shrink:0; }
.sp-tab-body.minutes-mode .next-agenda-block { flex:1;min-height:0;border-radius:0;border-left:none;border-right:none;border-bottom:none;margin:0; }
.nab-header { padding:12px 14px 8px;border-bottom:1px solid rgba(99,102,241,.12); }
.nab-title-row { display:flex;align-items:center;gap:7px;font-size:12px;font-weight:700;color:#818cf8;margin-bottom:4px; }
.nab-badge { font-size:10px;font-weight:600;padding:1px 6px;border-radius:10px;background:rgba(99,102,241,.15);color:#818cf8; }
.nab-desc { font-size:11px;color:var(--text-muted);margin:0; }
.nab-loading { display:flex;align-items:center;gap:8px;padding:14px;font-size:12px;color:var(--text-muted); }
.nab-spinner { width:14px;height:14px;border:2px solid rgba(99,102,241,.2);border-top-color:#818cf8;border-radius:50%;animation:spin .7s linear infinite; }
@keyframes spin { to { transform:rotate(360deg); } }
.nab-list { padding:8px; }
.nab-footer { display:flex;align-items:center;justify-content:space-between;padding:8px 10px;border-top:1px solid var(--border); }
.nab-footer-right { display:flex;align-items:center;gap:8px; }
.nab-count { font-size:11px;color:var(--text-muted); }
.nab-add-btn { font-size:11px;color:#818cf8;background:none;border:none;cursor:pointer;display:flex;align-items:center;gap:4px;padding:0; }
.nab-save-btn { font-size:11px;font-weight:600;padding:5px 12px;border-radius:6px;border:none;background:linear-gradient(135deg,#6366f1,#818cf8);color:#fff;cursor:pointer; }
.nab-save-btn:disabled { opacity:.35;cursor:not-allowed; }
</style>
