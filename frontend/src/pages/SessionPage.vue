<script setup>
import { ref, computed, onMounted, onUnmounted, nextTick } from 'vue'
import { marked } from 'marked'
import { useEditor, EditorContent } from '@tiptap/vue-3'
import StarterKit from '@tiptap/starter-kit'
import Underline from '@tiptap/extension-underline'
import { Table, TableRow, TableCell, TableHeader } from '@tiptap/extension-table'
import MemberInvite from '../components/MemberInvite.vue'
import api, { apiAI } from '../api'
import { streamPost } from '../api'
import { useSTT } from '../composables/useSTT'
import hyeanAvatar from '../assets/agents/hyean.png'

const renderMd = (t) => marked.parse(t || '', { breaks: true })

// ─── State ────────────────────────────────────────────────────
const meetings = ref([])          // [{ id, title, sessions: [] }]
const loadingMeetings = ref(false)
const sessionsCache = ref({})     // { [meetingId]: SessionResponse[] }

const selectedMeetingId = ref(null)
const expandedMeetingId = ref(null)
const activeSession = ref(null)
const sidebarSearch = ref('')

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
    // 백그라운드에서 각 회의체 세션 로드
    meetings.value.forEach(m => loadSessions(m.id))
  } catch (e) {
    console.error('meetings fetch error', e)
  } finally {
    loadingMeetings.value = false
  }
}

async function selectMeeting(m) {
  if (expandedMeetingId.value === m.id) {
    expandedMeetingId.value = null
    return
  }
  expandedMeetingId.value = m.id
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

  if (s.status?.toLowerCase() === 'ended' && !rec.transcriptLines.length) {
    try {
      const { data } = await apiAI.get(`/api/sessions/${s.id}/stt-segments`)
      if (data && data.length) {
        const lines = data.map(seg => ({
          time: new Date(seg.start_sec * 1000).toISOString().slice(11, 19),
          text: `${seg.speaker_name || seg.speaker_label}: ${seg.content}`,
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
      const { data } = await apiAI.get(`/api/sessions/${s.id}/minutes`)
      if (data?.content_summary) {
        generatedMinutes.value = { content_summary: data.content_summary }
        showMinutesTab.value = true
        rec.generatedMinutes = generatedMinutes.value
        rec.showMinutesTab = true
        await nextTick()
        loadMinutesToEditor(data.content_summary)
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

const sessionRecords = ref(new Map())
function getOrCreateRecord(id) {
  if (!sessionRecords.value.has(id))
    sessionRecords.value.set(id, { transcriptLines: [], generatedMinutes: null, showMinutesTab: false })
  return sessionRecords.value.get(id)
}

const stt = useSTT({
  onResult: (text) => {
    const time = new Date().toLocaleTimeString('ko-KR', { hour: '2-digit', minute: '2-digit', second: '2-digit' })
    const entry = { time, text }
    transcriptLines.value.push(entry)
    if (activeSession.value) {
      const rec = getOrCreateRecord(activeSession.value.id)
      rec.transcriptLines.push(entry)
    }
    nextTick(() => { if (transcriptAreaRef.value) transcriptAreaRef.value.scrollTop = transcriptAreaRef.value.scrollHeight })
  },
  getLang: () => transcriptLang.value === 'ko' ? 'ko-KR' : 'en-US',
})

function toggleRecording() {
  if (recordingState.value === 'idle') {
    recordingState.value = 'recording'; stt.start()
  } else if (recordingState.value === 'recording') {
    recordingState.value = 'paused'; stt.stop(); fetchTranscriptSummary()
  } else {
    recordingState.value = 'recording'; stt.start()
  }
}

function stopRecording() {
  const was = recordingState.value === 'recording'
  recordingState.value = 'idle'; stt.stop()
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
      '/api/agent/ara/generate-minutes',
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

async function saveMinutesToDB() {
  if (!activeSession.value || !generatedMinutes.value?.content_summary) return
  savingMinutes.value = true
  try {
    const html = editor.value?.getHTML() || generatedMinutes.value.content_summary
    await apiAI.post(`/api/sessions/${activeSession.value.id}/minutes`, { content_summary: html })
    minutesSavedAt.value = new Date().toLocaleTimeString('ko-KR', { hour: '2-digit', minute: '2-digit' })
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

function endMeeting() {
  if (!confirm('기록을 종료하시겠습니까?')) return
  stopRecording(); activeSession.value = null
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

  wmMessages.value.push({ role: 'user', content: text })

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
      { meeting_id: selectedMeeting.value?.id || 0, message: text, chat_history: history },
      (chunk) => { agentMsg.content += chunk; if (messagesEl.value) messagesEl.value.scrollTop = messagesEl.value.scrollHeight },
      () => { thinkingMsg.done = true; thinkingMsg.open = false; wmLoading.value = false },
      (step) => { thinkingMsg.steps.push(step); nextTick(() => { if (messagesEl.value) messagesEl.value.scrollTop = messagesEl.value.scrollHeight }) }
    )
  } catch { agentMsg.content = '응답 중 오류가 발생했습니다.'; thinkingMsg.done = true; thinkingMsg.open = false; wmLoading.value = false }
}

function onWmKeydown(e) { if (e.key==='Enter'&&!e.shiftKey) { e.preventDefault(); sendAra() } }

function formatDate(d) {
  if (!d) return '일정 미정'
  return new Date(d).toLocaleString('ko-KR', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
}

const STATUS_LABEL = { scheduled: '예정', ongoing: '진행중', ended: '종료' }
const STATUS_CLS = { scheduled: '#3b82f6', ongoing: '#f59e0b', ended: '#94a3b8' }

// ─── Session create modal (sidebar) ──────────────────────────
const showCreateSession = ref(false)
const createSessionForm = ref({ title: '', purpose: '', date: '', meetingId: null })
const createSessionMembers = ref([])
const creatingSessionForm = ref(false)

async function doCreateSessionForm() {
  if (!createSessionForm.value.title.trim() || !createSessionForm.value.meetingId) return
  creatingSessionForm.value = true
  try {
    const meetingId = createSessionForm.value.meetingId
    await apiAI.post(`/api/v1/meetings/${meetingId}/sessions`, {
      title: createSessionForm.value.title,
      scheduled_at: createSessionForm.value.date ? createSessionForm.value.date + ':00' : null,
    })
    // 캐시 무효화 후 재로드
    delete sessionsCache.value[meetingId]
    await loadSessions(meetingId)
    showCreateSession.value = false
    createSessionForm.value = { title: '', purpose: '', date: '', meetingId: null }
    createSessionMembers.value = []
  } catch(e) {
    alert(e.response?.data?.message || '생성 실패')
  } finally {
    creatingSessionForm.value = false
  }
}

onMounted(() => {
  fetchMeetings()
})
</script>

<template>
  <div class="sp-layout page-full-height" @click="showPopover=null">

    <!-- Left: Meeting / session selector -->
    <div class="sp-sidebar">
      <div class="sp-sidebar-header">
        <div class="sp-header-top">
          <span class="sp-sidebar-title">회의체 선택</span>
          <button class="sp-create-btn" @click.stop="showCreateSession=true" title="회의 생성">
            <svg width="11" height="11" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24"><path d="M12 4v16m8-8H4"/></svg>
            회의 생성
          </button>
        </div>
        <div class="sp-search-wrap">
          <svg class="sp-search-icon" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><circle cx="11" cy="11" r="8"/><path d="M21 21l-4.35-4.35"/></svg>
          <input v-model="sidebarSearch" class="sp-search-input" placeholder="회의체 검색..." />
          <button v-if="sidebarSearch" class="sp-search-clear" @click="sidebarSearch=''">&times;</button>
        </div>
      </div>
      <div class="sp-sidebar-body">
        <div v-if="loadingMeetings" class="sp-search-empty">불러오는 중...</div>
        <div v-else-if="!filteredMeetings.length" class="sp-search-empty">{{ sidebarSearch ? '검색 결과 없음' : '참여 중인 회의체가 없습니다' }}</div>
        <div v-for="mtg in filteredMeetings" :key="mtg.id" class="sp-mtg-group">
          <div class="sp-mtg-header" @click="selectMeeting(mtg)" :class="{ expanded: expandedMeetingId === mtg.id }">
            <div class="sp-mtg-dot"></div>
            <span class="sp-mtg-title">{{ mtg.title }}</span>
            <svg class="sp-mtg-chev" :class="{ open: expandedMeetingId === mtg.id }" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M19 9l-7 7-7-7"/></svg>
          </div>
          <div v-if="expandedMeetingId === mtg.id" class="sp-session-list">
            <div v-if="!mtg.sessions" class="sp-session-item" style="justify-content:center;color:#94a3b8;font-size:11px">불러오는 중...</div>
            <div v-else-if="!mtg.sessions.length" class="sp-session-item" style="justify-content:center;color:#94a3b8;font-size:11px">등록된 회의가 없습니다</div>
            <div v-for="s in mtg.sessions" :key="s.id"
              class="sp-session-item"
              :class="{ active: activeSession?.id === s.id }"
              @click="enterSession(s)">
              <div class="sp-session-dot" :style="{ background: STATUS_CLS[s.status] }"></div>
              <div class="sp-session-info">
                <div class="sp-session-name">{{ s.title }}</div>
                <div class="sp-session-date">{{ formatDate(s.scheduled_at) }}</div>
              </div>
              <span class="sp-status-badge" :style="{ background: STATUS_CLS[s.status]+'22', color: STATUS_CLS[s.status] }">{{ STATUS_LABEL[s.status] }}</span>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Center: Recording panel -->
    <div class="sp-main" @click.stop>

      <!-- No session selected -->
      <div v-if="!activeSession" class="sp-no-session">
        <svg width="48" height="48" fill="none" stroke="currentColor" stroke-width="1.5" viewBox="0 0 24 24" style="color:#cbd5e1"><path d="M12 14c1.66 0 3-1.34 3-3V5c0-1.66-1.34-3-3-3S9 3.34 9 5v6c0 1.66 1.34 3 3 3z"/><path d="M17 11c0 2.76-2.24 5-5 5s-5-2.24-5-5H5c0 3.53 2.61 6.43 6 6.92V21h2v-3.08c3.39-.49 6-3.39 6-6.92h-2z"/></svg>
        <p class="sp-no-session-text">왼쪽에서 회의를 선택하세요</p>
        <p class="sp-no-session-sub">회의체를 클릭하면 세션 목록이 펼쳐집니다</p>
      </div>

      <!-- Active session recording view -->
      <div v-else class="sp-panel card">
        <!-- Panel header: title + tabs -->
        <div class="sp-panel-header">
          <div class="sp-panel-title-row">
            <div class="sp-panel-title">{{ activeSession.title }}</div>
            <span v-if="recordingState === 'recording'" class="rec-live">
              <i class="bi bi-record-fill"></i> REC
            </span>
          </div>
          <div class="app-tabs">
            <button class="app-tab" :class="{ active: activeTab === 'transcript' }" @click="activeTab='transcript'">대화 기록</button>
            <button class="app-tab" :class="{ active: activeTab === 'script' }" @click="activeTab='script'">스크립트</button>
            <button v-if="showMinutesTab" class="app-tab" :class="{ active: activeTab === 'minutes' }" @click="activeTab='minutes'">회의록</button>
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
            <div v-for="(line, idx) in transcriptLines" :key="idx" class="tline">
              <span class="tline-time">{{ line.time }}</span>
              <span class="tline-text">{{ line.text }}</span>
            </div>
          </template>

          <template v-else-if="activeTab === 'script'">
            <div v-if="!transcriptLines.length" class="sp-empty">
              <i class="bi bi-file-earmark-text" style="font-size:28px;opacity:.25"></i>
              <p class="text-muted small mb-0">스크립트가 여기에 표시됩니다.</p>
            </div>
            <div v-for="(line, idx) in transcriptLines" :key="idx" class="tline">
              <span class="tline-time">{{ line.time }}</span>
              <span class="tline-text">{{ line.text }}</span>
            </div>
          </template>

          <template v-else-if="activeTab === 'minutes'">
            <div class="minutes-scroll-area">
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

          </template>
        </div>

        <!-- Control bar (대화기록/스크립트 탭) -->
        <div v-if="activeTab !== 'minutes'" class="sp-ctrl-bar" @click.stop>
          <div class="ctrl-group-left">
            <!-- Mic settings -->
            <div class="ctrl-pop-wrap">
              <button class="ctrl-btn" :class="{ 'ctrl-active': showPopover==='mic' }"
                @click.stop="togglePopover('mic')" title="녹음 설정">
                <i class="bi bi-mic"></i><i class="bi bi-chevron-down ctrl-chev"></i>
              </button>
              <div v-if="showPopover==='mic'" class="ctrl-popover" @click.stop>
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

            <!-- Record / pause -->
            <button class="ctrl-rec-btn" :class="{ recording: recordingState==='recording' }"
              @click.stop="toggleRecording"
              :title="recordingState==='idle'?'녹음 시작':recordingState==='recording'?'일시정지':'재개'">
              <i v-if="recordingState!=='recording'" class="bi bi-play-fill"></i>
              <i v-else class="bi bi-pause-fill"></i>
            </button>

            <!-- Stop -->
            <button v-if="recordingState!=='idle'" class="ctrl-btn ctrl-stop" @click.stop="stopRecording" title="중지">
              <i class="bi bi-stop-fill"></i>
            </button>

            <button class="ctrl-end" @click.stop="endMeeting">기록 종료</button>
          </div>
          <div class="ctrl-group-right">
            <button class="ctrl-minutes" :disabled="generatingMinutes" @click.stop="generateMinutes">
              <i class="bi bi-stars"></i> 회의록 생성
            </button>
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
              {{ generatingMinutes ? '생성 중...' : '회의록 재생성' }}
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- Right: 워크메이트 AI (Supervisor) -->
    <div class="sp-agent-panel">
      <div class="sp-agent-header">
        <div class="sp-agent-header-brand">
          <img :src="hyeanAvatar" class="sp-agent-avatar" alt="워크메이트 AI" />
          <div class="sp-agent-header-text">
            <div class="sp-agent-name">워크메이트 AI</div>
            <div class="sp-agent-sub">회의 AI 어시스턴트</div>
          </div>
        </div>
        <div class="sp-agent-header-actions">
          <button class="sp-agent-new-chat" @click="wmMessages=[{role:'agent',content:'안녕하세요! 워크메이트 AI입니다 😊\n무엇이든 질문하세요.'}]">새 채팅</button>
        </div>
      </div>
      <div ref="messagesEl" class="sp-agent-messages">
        <div v-for="(msg, i) in wmMessages" :key="i" class="sp-msg-row" :class="msg.role === 'thinking' ? 'thinking' : msg.role">

          <!-- 사고 과정 블록 -->
          <template v-if="msg.role==='thinking'">
            <div class="sp-thinking-block" :class="{ done: msg.done, open: msg.open }">
              <button class="sp-thinking-toggle" @click="msg.open = !msg.open">
                <svg v-if="!msg.done" class="sp-thinking-spinner" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="#00ab36" stroke-width="2.5"><path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83"/></svg>
                <svg v-else width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="#00ab36" stroke-width="2.5"><path d="M9 12l2 2 4-4"/><circle cx="12" cy="12" r="10"/></svg>
                <span class="sp-thinking-label">{{ msg.done ? 'Knowledge Graph 조회 완료' : 'Knowledge Graph 분석 중...' }}</span>
                <span class="sp-thinking-count">{{ msg.steps.length }} queries</span>
                <svg class="sp-thinking-chev" :class="{ rotated: msg.open }" width="11" height="11" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M19 9l-7 7-7-7"/></svg>
              </button>
              <div v-if="msg.open" class="sp-thinking-steps">
                <div v-for="(step, si) in msg.steps" :key="si"
                     class="sp-thinking-step fade-in"
                     :class="{
                       'sp-step-cypher': step.includes('MATCH') || step.includes('RETURN'),
                       'sp-step-data':   !step.includes('MATCH') && (step.includes('→') || step.includes('수신') || step.includes('수집') || step.includes('발견')),
                       'sp-step-route':  step.includes('위임') || step.includes('라우팅'),
                     }">
                  <span v-if="step.includes('MATCH') || step.includes('RETURN')" class="sp-step-icon-cypher">
                    <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><ellipse cx="12" cy="5" rx="9" ry="3"/><path d="M3 5v14c0 1.66 4.03 3 9 3s9-1.34 9-3V5"/><path d="M3 12c0 1.66 4.03 3 9 3s9-1.34 9-3"/></svg>
                  </span>
                  <span v-else-if="step.includes('→') || step.includes('수신') || step.includes('수집') || step.includes('발견')" class="sp-step-icon-data">
                    <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><circle cx="8" cy="12" r="3"/><circle cx="18" cy="7" r="2"/><circle cx="18" cy="17" r="2"/><line x1="11" y1="11" x2="16" y2="8"/><line x1="11" y1="13" x2="16" y2="16"/></svg>
                  </span>
                  <span v-else class="sp-step-num">{{ si + 1 }}</span>
                  <span class="sp-step-text">{{ step }}</span>
                </div>
                <div v-if="!msg.done" class="sp-thinking-step sp-step-pending">
                  <span class="sp-step-dots"><span></span><span></span><span></span></span>
                </div>
              </div>
            </div>
          </template>

          <!-- AI 응답 -->
          <template v-else-if="msg.role==='agent'&&msg.content">
            <div class="sp-agent-label">
              <img :src="hyeanAvatar" class="sp-msg-avatar" />워크메이트 AI
            </div>
            <div class="sp-bubble agent" v-html="renderMd(msg.content)"></div>
          </template>

          <!-- 사용자 메시지 -->
          <div v-else-if="msg.role==='user'" class="sp-bubble user">{{ msg.content }}</div>
        </div>
        <div v-if="wmLoading&&wmMessages[wmMessages.length-1]?.role==='agent'&&wmMessages[wmMessages.length-1]?.content===''" class="sp-msg-row agent">
          <div class="sp-bubble agent typing"><span></span><span></span><span></span></div>
        </div>
      </div>
      <div class="sp-agent-input">
        <div class="sp-agent-input-row">
          <textarea v-model="wmInput" class="sp-ara-textarea" rows="1" placeholder="질문하세요..." @keydown="onWmKeydown"></textarea>
          <button class="sp-ara-send" :disabled="wmLoading||!wmInput.trim()" @click="sendAra">전송</button>
        </div>
      </div>
    </div>

  </div>

  <!-- 회의 생성 모달 -->
  <Teleport to="body">
    <div v-if="showCreateSession" class="app-modal-backdrop" @click.self="showCreateSession=false">
      <div class="app-modal app-modal-sm">
        <div class="app-modal-header">
          <span class="app-modal-title">회의 생성</span>
          <button class="app-modal-close" @click="showCreateSession=false">
            <svg width="14" height="14" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24"><path d="M6 18L18 6M6 6l12 12"/></svg>
          </button>
        </div>
        <div class="app-modal-body">
          <div class="app-modal-field">
            <label>회의체 <span style="color:#ef4444">*</span></label>
            <select v-model="createSessionForm.meetingId" class="app-modal-input">
              <option :value="null" disabled>회의체를 선택하세요</option>
              <option v-for="m in meetings" :key="m.id" :value="m.id">{{ m.title }}</option>
            </select>
          </div>
          <div class="app-modal-field">
            <label>회의명 <span style="color:#ef4444">*</span></label>
            <input v-model="createSessionForm.title" class="app-modal-input" placeholder="예: 2025 전략 수립 1차" />
          </div>
          <div class="app-modal-field">
            <label>회의 날짜</label>
            <input type="datetime-local" v-model="createSessionForm.date" class="app-modal-input" />
          </div>
        </div>
        <div class="app-modal-footer">
          <button class="app-btn-cancel" @click="showCreateSession=false">취소</button>
          <button class="app-btn-primary" :disabled="creatingSessionForm||!createSessionForm.title.trim()||!createSessionForm.meetingId" @click="doCreateSessionForm">
            {{ creatingSessionForm ? '생성 중...' : '생성' }}
          </button>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
/* ── Layout ── */
.sp-layout { display:flex;flex-direction:row !important;gap:0; }

/* ── Left sidebar (session selector) ── */
.sp-sidebar { width:220px;flex-shrink:0;border-right:1px solid var(--border);display:flex;flex-direction:column;overflow:hidden;background:#fff;height:100%; }
.sp-sidebar-header { padding:12px 14px;border-bottom:1px solid var(--border);flex-shrink:0; }
.sp-header-top { display:flex;align-items:center;justify-content:space-between;margin-bottom:0; }
.sp-create-btn { display:flex;align-items:center;gap:4px;padding:4px 9px;border-radius:7px;border:1px solid var(--primary);background:#eff6ff;color:var(--primary);font-size:11px;font-weight:600;cursor:pointer;transition:all .15s;white-space:nowrap; }
.sp-create-btn:hover { background:var(--primary);color:#fff; }
/* ── Session create modal ── */
.sp-mi:focus { border-color:var(--primary); }
.sp-ms-wrap { display:flex;align-items:center;gap:6px;border:1px solid var(--border);border-radius:8px;padding:5px 8px; }
.sp-ms-input { flex:1;border:none;outline:none;font-size:12px;color:#1e293b; }
.sp-ms-results { border:1px solid var(--border);border-radius:8px;overflow:hidden;margin-top:4px; }
.sp-ms-item { display:flex;align-items:center;gap:8px;padding:7px 10px;border-bottom:1px solid var(--border);font-size:12px; }
.sp-ms-item:last-child { border-bottom:none; }
.sp-ms-info { flex:1;min-width:0; }
.sp-ms-name { font-weight:600;color:#1e293b;display:block; }
.sp-ms-email { color:#94a3b8;font-size:11px;display:block; }
.sp-ms-role { padding:3px 8px;border-radius:5px;border:1px solid var(--border);background:#f8fafc;color:#475569;font-size:11px;font-weight:600;cursor:pointer; }
.sp-ms-role.admin { border-color:var(--primary);background:#eff6ff;color:var(--primary); }
.sp-sm-row { display:flex;align-items:center;gap:8px;padding:5px 8px;background:#f8fafc;border-radius:7px;font-size:12px; }
.sp-sm-name { flex:1;font-weight:600;color:#1e293b; }
.sp-sm-role-tag { padding:2px 7px;border-radius:5px;font-size:11px;font-weight:600; }
.sp-sm-role-tag.admin { background:#eff6ff;color:var(--primary); }
.sp-sm-role-tag.member { background:#f0fdf4;color:#16a34a; }
.sp-sm-rm { background:none;border:none;cursor:pointer;color:#94a3b8;font-size:15px;line-height:1; }
.sp-sm-rm:hover { color:#ef4444; }
.sp-sidebar-title { font-size:12px;font-weight:700;color:var(--text-muted);text-transform:uppercase;letter-spacing:.05em; }
.sp-sidebar-body { flex:1;overflow-y:auto;padding:8px 0; }

.sp-mtg-group { border-bottom:1px solid #f1f5f9; }
.sp-mtg-header { display:flex;align-items:center;gap:7px;padding:10px 14px;cursor:pointer;transition:background .15s;user-select:none; }
.sp-mtg-header:hover,.sp-mtg-header.expanded { background:#f8fafc; }
.sp-mtg-dot { width:6px;height:6px;background:var(--primary);border-radius:50%;flex-shrink:0; }
.sp-mtg-title { flex:1;font-size:12px;font-weight:600;color:#334155;overflow:hidden;text-overflow:ellipsis;white-space:nowrap; }
.sp-mtg-chev { color:var(--text-muted);transition:transform .2s;flex-shrink:0; }
.sp-mtg-chev.open { transform:rotate(180deg); }

.sp-session-list { background:#f8fafc;border-top:1px solid #f1f5f9; }
.sp-session-item { display:flex;align-items:center;gap:6px;padding:8px 14px 8px 22px;cursor:pointer;transition:background .15s; }
.sp-session-item:hover { background:#eff6ff; }
.sp-session-item.active { background:#eff6ff; }
.sp-session-dot { width:5px;height:5px;border-radius:50%;flex-shrink:0; }
.sp-session-info { flex:1;min-width:0; }
.sp-session-name { font-size:11px;font-weight:600;color:#334155;overflow:hidden;text-overflow:ellipsis;white-space:nowrap; }
.sp-session-date { font-size:10px;color:var(--text-muted); }
.sp-status-badge { font-size:9px;font-weight:700;padding:2px 6px;border-radius:99px;flex-shrink:0; }

/* ── Center panel ── */
.sp-main { flex:1;display:flex;flex-direction:column;align-items:stretch;justify-content:center;padding:16px;overflow:visible;min-width:0; }

.sp-no-session { display:flex;flex-direction:column;align-items:center;justify-content:center;height:100%;gap:10px;color:var(--text-muted); }
.sp-no-session-text { font-size:14px;font-weight:600;margin:0; }
.sp-no-session-sub { font-size:12px;margin:0;opacity:.7; }

.sp-panel { display:flex;flex-direction:column;height:100%;overflow:visible; }
.sp-panel-header { display:flex;align-items:center;justify-content:space-between;padding:12px 16px;border-bottom:1px solid var(--border);flex-shrink:0;gap:12px; }
.sp-panel-title-row { display:flex;align-items:center;gap:8px;min-width:0; }
.sp-panel-title { font-size:14px;font-weight:700;color:#1e293b;overflow:hidden;text-overflow:ellipsis;white-space:nowrap; }
.rec-live { font-size:11px;font-weight:700;color:#ef4444;display:flex;align-items:center;gap:3px;flex-shrink:0;animation:pulse 1.2s infinite; }
@keyframes pulse { 0%,100%{opacity:1}50%{opacity:.4} }


.sp-tab-body { flex:1;overflow-y:auto;padding:12px 16px;display:flex;flex-direction:column;gap:4px;min-height:0; }
.sp-tab-body::-webkit-scrollbar { width:4px; }
.sp-tab-body::-webkit-scrollbar-thumb { background:#e2e8f0; }
.minutes-scroll-area { flex:1;overflow-y:auto;display:flex;flex-direction:column;gap:4px;min-height:0;padding-bottom:8px; }
.minutes-scroll-area::-webkit-scrollbar { width:4px; }
.minutes-scroll-area::-webkit-scrollbar-thumb { background:#e2e8f0; }
.sp-tab-body.minutes-mode { overflow:hidden;padding:0; }
.sp-tab-body.minutes-mode .minutes-scroll-area { padding:12px 16px 0; }
.sp-tab-body.minutes-mode .minutes-action-row { padding:10px 16px 8px;margin:0; }
.sp-empty { display:flex;flex-direction:column;align-items:center;justify-content:center;height:100%;gap:8px;color:var(--text-muted); }

/* Transcript lines */
.tline { display:flex;gap:10px;align-items:baseline;padding:3px 0; }
.tline-time { font-size:10px;color:var(--text-muted);flex-shrink:0;font-family:monospace; }
.tline-text { font-size:13px;color:#1e293b;line-height:1.5; }

/* AI summary box */
.ts-summary-box { background:#fafafa;border:1px solid #e2e8f0;border-radius:8px;margin-bottom:12px;overflow:hidden; }
.ts-summary-header { display:flex;align-items:center;justify-content:space-between;padding:8px 12px;background:#f1f5f9;border-bottom:1px solid #e2e8f0;font-size:12px;font-weight:600;color:#475569; }
.ts-summary-close { background:none;border:none;cursor:pointer;color:#94a3b8;font-size:13px;line-height:1; }
.ts-summary-body { padding:10px 12px;font-size:13px;color:#334155;line-height:1.6; }

/* Minutes – Tiptap editor */
.tiptap-toolbar { display:flex;align-items:center;gap:2px;padding:6px 4px;border-bottom:1px solid var(--border);background:transparent;flex-wrap:wrap;margin-bottom:8px; }
.tt-btn { display:inline-flex;align-items:center;justify-content:center;min-width:28px;height:26px;padding:0 5px;border:1px solid transparent;border-radius:4px;background:none;color:#475569;font-size:12px;cursor:pointer;transition:all .1s;user-select:none; }
.tt-btn:hover { background:#e2e8f0; }
.tt-btn.active { background:#dbeafe;color:#1d4ed8;border-color:#bfdbfe; }
.tt-delete { color:#ef4444 !important; }
.tt-delete:hover { background:#fef2f2 !important; }
.tt-delete:disabled { opacity:.4;cursor:not-allowed;pointer-events:none; }
.tt-sep { width:1px;height:18px;background:var(--border);margin:0 3px; }

.tiptap-content { border:none;padding:4px 0;min-height:400px;background:transparent;outline:none; }
.tiptap-content :deep(.ProseMirror) { outline:none;min-height:380px; }
.tiptap-content :deep(.ProseMirror p) { margin:0 0 6px;font-size:13px;line-height:1.7;color:#1e293b; }
.tiptap-content :deep(.ProseMirror h1) { font-size:17px;font-weight:800;margin:0 0 12px;padding-bottom:8px;border-bottom:2px solid var(--border);color:#0f172a; }
.tiptap-content :deep(.ProseMirror h2) { font-size:15px;font-weight:700;margin:16px 0 6px;color:#1e40af; }
.tiptap-content :deep(.ProseMirror h3) { font-size:13px;font-weight:700;margin:10px 0 4px;color:#475569; }
.tiptap-content :deep(.ProseMirror strong) { font-weight:700; }
.tiptap-content :deep(.ProseMirror em) { font-style:italic; }
.tiptap-content :deep(.ProseMirror u) { text-decoration:underline; }
.tiptap-content :deep(.ProseMirror ul),.tiptap-content :deep(.ProseMirror ol) { padding-left:20px;margin:4px 0; }
.tiptap-content :deep(.ProseMirror li) { margin-bottom:2px;font-size:13px;line-height:1.6; }
.tiptap-content :deep(.ProseMirror li > p) { margin:0; }
.tiptap-content :deep(.ProseMirror table) { width:100%;border-collapse:collapse;margin:8px 0;font-size:12px;table-layout:fixed; }
.tiptap-content :deep(.ProseMirror th),.tiptap-content :deep(.ProseMirror td) { border:1px solid var(--border);padding:6px 10px;text-align:left;vertical-align:top;word-break:break-word; }
.tiptap-content :deep(.ProseMirror th) { background:#f1f5f9;font-weight:600;font-size:12px; }
.tiptap-content :deep(.ProseMirror td > p),.tiptap-content :deep(.ProseMirror th > p) { margin:0; }
.tiptap-content :deep(.ProseMirror hr) { border:none;border-top:1px solid var(--border);margin:12px 0; }
.tiptap-content :deep(.ProseMirror blockquote) { border-left:3px solid #e2e8f0;padding-left:12px;color:#64748b;margin:6px 0; }

/* Streaming preview uses same styles */
.minutes-md { font-size:13px;line-height:1.7;color:#1e293b; }
.minutes-md :deep(h1) { font-size:17px;font-weight:800;margin:0 0 12px;padding-bottom:8px;border-bottom:2px solid var(--border); }
.minutes-md :deep(h2) { font-size:15px;font-weight:700;margin:16px 0 6px;color:#1e40af; }
.minutes-md :deep(h3) { font-size:13px;font-weight:700;margin:10px 0 4px;color:#475569; }
.minutes-md :deep(strong) { font-weight:700; }
.minutes-md :deep(ul),.minutes-md :deep(ol) { padding-left:18px;margin:4px 0; }
.minutes-md :deep(li) { margin-bottom:2px; }
.minutes-md :deep(table) { width:100%;border-collapse:collapse;margin:8px 0;font-size:12px; }
.minutes-md :deep(th),.minutes-md :deep(td) { border:1px solid var(--border);padding:5px 8px;text-align:left; }
.minutes-md :deep(th) { background:#f8fafc;font-weight:600; }
.minutes-md :deep(hr) { border:none;border-top:1px solid var(--border);margin:12px 0; }

.tt-source-info { display:inline-flex;align-items:center;gap:3px;font-size:11px;color:#94a3b8;padding:0 4px;white-space:nowrap;cursor:default; }


/* Control bar */
.sp-ctrl-bar { display:flex;align-items:center;justify-content:space-between;padding:10px 16px;border-top:1px solid var(--border);flex-shrink:0;background:#fff;overflow:visible;border-radius:0 0 12px 12px; }
.ctrl-group-left,.ctrl-group-right { display:flex;align-items:center;gap:6px; }
.ctrl-pop-wrap { position:relative; }
.ctrl-btn { display:flex;align-items:center;gap:3px;padding:6px 10px;border-radius:8px;border:1px solid var(--border);background:#fff;color:#475569;font-size:13px;cursor:pointer;transition:all .15s; }
.ctrl-btn:hover,.ctrl-active { background:#f1f5f9;border-color:var(--primary);color:var(--primary); }
.ctrl-lang { font-size:12px;gap:4px; }
.ctrl-chev { font-size:9px;opacity:.6; }
.ctrl-popover { position:absolute;bottom:calc(100% + 6px);left:0;background:#fff;border:1px solid var(--border);border-radius:10px;box-shadow:0 8px 24px rgba(0,0,0,.12);padding:10px 12px;min-width:160px;z-index:200; }
.cpop-title { font-size:11px;font-weight:700;color:var(--text-muted);text-transform:uppercase;margin-bottom:8px; }
.cpop-row { display:flex;align-items:center;gap:8px;margin-bottom:6px;font-size:12px;color:#475569; }
.cpop-label { flex:1; }
.cpop-range { flex:1;accent-color:var(--primary); }
.cpop-val { font-size:11px;font-weight:600;min-width:28px;text-align:right; }
.cpop-opt { display:block;width:100%;text-align:left;padding:7px 10px;border-radius:6px;border:none;background:none;font-size:13px;cursor:pointer;color:#475569;transition:background .1s; }
.cpop-opt:hover { background:#f1f5f9; }
.cpop-opt.selected { background:#eff6ff;color:var(--primary);font-weight:600; }
.ctrl-rec-btn { width:38px;height:38px;border-radius:50%;border:none;background:var(--primary);color:#fff;font-size:16px;display:flex;align-items:center;justify-content:center;cursor:pointer;transition:all .15s;box-shadow:0 2px 8px rgba(59,130,246,.3); }
.ctrl-rec-btn.recording { background:#ef4444;box-shadow:0 2px 8px rgba(239,68,68,.35); }
.ctrl-rec-btn:hover { opacity:.85; }
.ctrl-stop { color:#ef4444;border-color:#fca5a5; }
.ctrl-stop:hover { background:#fef2f2;border-color:#ef4444; }
.ctrl-end { padding:6px 14px;border-radius:8px;border:1px solid #fca5a5;background:#fef2f2;color:#ef4444;font-size:12px;font-weight:600;cursor:pointer;transition:all .15s; }
.ctrl-end:hover { background:#ef4444;color:#fff;border-color:#ef4444; }
.ctrl-minutes { display:flex;align-items:center;gap:5px;padding:7px 14px;border-radius:8px;border:none;background:#f59e0b;color:#fff;font-size:12px;font-weight:700;cursor:pointer;transition:opacity .15s; }
.ctrl-minutes:disabled { opacity:.5;cursor:not-allowed; }

/* ── Left sidebar search ── */
.sp-search-wrap { position:relative;display:flex;align-items:center;margin-top:7px; }
.sp-search-icon { position:absolute;left:8px;color:#94a3b8;pointer-events:none; }
.sp-search-input { width:100%;padding:5px 26px 5px 26px;border:1px solid var(--border);border-radius:7px;font-size:11px;color:#334155;background:#f8fafc;outline:none;box-sizing:border-box; }
.sp-search-input:focus { border-color:var(--primary);background:#fff; }
.sp-search-input::placeholder { color:#94a3b8; }
.sp-search-clear { position:absolute;right:6px;background:none;border:none;cursor:pointer;color:#94a3b8;font-size:14px;line-height:1;padding:0; }
.sp-search-clear:hover { color:#475569; }
.sp-search-empty { padding:20px 14px;text-align:center;font-size:12px;color:#94a3b8; }

/* ── Right: 워크메이트 AI ── */
.sp-agent-panel { width:290px;flex-shrink:0;border-left:1px solid var(--border);display:flex;flex-direction:column;background:#fff;overflow:hidden;height:100%; }
.sp-agent-header { display:flex;align-items:center;justify-content:space-between;padding:10px 12px;border-bottom:1px solid var(--border);flex-shrink:0;background:linear-gradient(135deg,#eff6ff 0%,#f0fdf4 100%); }
.sp-agent-header-brand { display:flex;align-items:center;gap:8px;flex:1;min-width:0; }
.sp-agent-avatar { width:30px;height:30px;border-radius:50%;object-fit:cover;flex-shrink:0;border:2px solid #93c5fd; }
.sp-agent-header-text { display:flex;flex-direction:column;min-width:0;flex:1; }
.sp-agent-name { font-size:13px;font-weight:700;color:#1e293b;white-space:nowrap;overflow:hidden;text-overflow:ellipsis; }
.sp-agent-sub { font-size:10px;color:#64748b;white-space:nowrap;overflow:hidden;text-overflow:ellipsis; }
.sp-agent-header-actions { display:flex;align-items:center;gap:5px;flex-shrink:0; }
.sp-agent-new-chat { background:none;border:1px solid var(--border);border-radius:6px;padding:3px 9px;font-size:11px;color:var(--text-muted);cursor:pointer;transition:all .15s;white-space:nowrap; }
.sp-agent-new-chat:hover { background:#eff6ff;border-color:#93c5fd;color:var(--primary); }
.sp-agent-messages { flex:1;overflow-y:auto;padding:8px;display:flex;flex-direction:column;gap:7px; }
.sp-agent-messages::-webkit-scrollbar { width:3px; }
.sp-agent-messages::-webkit-scrollbar-thumb { background:#e2e8f0; }
.sp-msg-row { display:flex;flex-direction:column;gap:3px; }
.sp-msg-row.user { align-items:flex-end; }
.sp-agent-label { display:flex;align-items:center;gap:4px;font-size:11px;font-weight:600;color:var(--text-muted); }
.sp-msg-avatar { width:15px;height:15px;border-radius:50%;object-fit:cover; }
.sp-bubble { padding:8px 11px;border-radius:10px;font-size:13px;line-height:1.55;max-width:90%;word-break:break-word;border:1px solid transparent; }
.sp-bubble.user { background:var(--primary);color:#fff;border-radius:10px 10px 2px 10px; }
.sp-bubble.agent { background:linear-gradient(135deg,#eff6ff,#f0fdf4);border-color:#93c5fd;color:#1e3a5f;border-radius:2px 10px 10px 10px; }
.sp-bubble.agent :deep(p) { margin:0 0 6px; }
.sp-bubble.agent :deep(p:last-child) { margin:0; }
.typing { display:flex;gap:4px;align-items:center; }
.typing span { width:5px;height:5px;background:#94a3b8;border-radius:50%;animation:bounce .8s infinite; }
.typing span:nth-child(2) { animation-delay:.15s; }
.typing span:nth-child(3) { animation-delay:.3s; }
@keyframes bounce { 0%,80%,100%{transform:scale(.8);opacity:.5}40%{transform:scale(1.2);opacity:1} }
.sp-agent-input { padding:7px 9px;border-top:1px solid var(--border);flex-shrink:0; }
.sp-agent-input-row { display:flex;align-items:flex-end;gap:4px; }
.sp-ara-textarea { flex:1;resize:none;overflow:hidden;min-height:34px;max-height:80px;border:1px solid var(--border);border-radius:7px;padding:6px 8px;font-size:12px;outline:none;font-family:inherit;line-height:1.5;box-sizing:border-box; }
.sp-ara-textarea:focus { border-color:var(--primary); }
.sp-ara-send { padding:6px 12px;border-radius:7px;border:none;background:var(--primary);color:#fff;font-size:12px;font-weight:600;cursor:pointer;flex-shrink:0; }
.sp-ara-send:disabled { opacity:.4;cursor:not-allowed; }

/* ── Neo4j Knowledge Graph 사고 과정 블록 ──────────────────── */
.sp-thinking-block { width:100%;border:1px solid rgba(0,171,54,.3);border-radius:10px;background:rgba(0,171,54,.03);overflow:hidden; }
.sp-thinking-block.done { border-color:rgba(0,171,54,.5);background:rgba(0,171,54,.04); }
.sp-thinking-toggle { display:flex;align-items:center;gap:6px;width:100%;padding:7px 10px;background:none;border:none;cursor:pointer;color:#374151;font-size:11.5px;font-weight:600;text-align:left; }
.sp-thinking-label { flex:1;color:#374151;font-size:11px; }
.sp-thinking-count { font-size:10px;font-weight:600;color:#00ab36;background:rgba(0,171,54,.1);padding:1px 7px;border-radius:20px;border:1px solid rgba(0,171,54,.2); }
.sp-thinking-chev { transition:transform .2s;flex-shrink:0;color:#9ca3af; }
.sp-thinking-chev.rotated { transform:rotate(180deg); }

.sp-thinking-steps { padding:4px 10px 10px;display:flex;flex-direction:column;gap:5px;border-top:1px solid rgba(0,171,54,.12); }

/* 일반 단계 */
.sp-thinking-step { display:flex;align-items:flex-start;gap:7px;font-size:11.5px;line-height:1.5; }
.sp-step-num { flex-shrink:0;width:16px;height:16px;background:rgba(0,0,0,.08);color:#6b7280;border-radius:50%;font-size:8.5px;font-weight:700;display:flex;align-items:center;justify-content:center;margin-top:1.5px; }
.sp-step-text { color:#4b5563;word-break:break-all; }

/* Cypher 쿼리 단계 */
.sp-step-cypher { background:#0d1117;border:1px solid rgba(0,171,54,.35);border-left:3px solid #00ab36;border-radius:6px;padding:5px 8px; }
.sp-step-cypher .sp-step-text { font-family:'Courier New',monospace;font-size:10.5px;color:#79c0ff;word-break:break-all; }
.sp-step-icon-cypher { flex-shrink:0;color:#00ab36;margin-top:2px; }

/* 데이터 수신 단계 */
.sp-step-data { background:rgba(0,171,54,.06);border:1px solid rgba(0,171,54,.2);border-radius:6px;padding:4px 8px; }
.sp-step-data .sp-step-text { color:#15803d;font-weight:500; }
.sp-step-icon-data { flex-shrink:0;color:#00ab36;margin-top:2px; }

/* 라우팅 단계 */
.sp-step-route .sp-step-text { color:#7c3aed;font-style:italic; }

.sp-step-pending { padding-left:2px; }
.sp-step-dots { display:flex;gap:3px;align-items:center; }
.sp-step-dots span { width:4px;height:4px;background:#00ab36;border-radius:50%;animation:bounce .8s infinite; }
.sp-step-dots span:nth-child(2) { animation-delay:.15s; }
.sp-step-dots span:nth-child(3) { animation-delay:.3s; }
@keyframes sp-spin { to { transform:rotate(360deg); } }
.sp-thinking-spinner { animation:sp-spin 1s linear infinite;flex-shrink:0; }
.sp-msg-row.thinking { padding:0; }

/* ── Minutes action row ── */
.minutes-action-row { display:flex;align-items:center;justify-content:space-between;gap:8px;padding:10px 0 2px;border-top:1px solid var(--border);flex-shrink:0; }
.minutes-action-left,.minutes-action-right { display:flex;align-items:center;gap:6px; }
.minutes-download-group { display:flex;gap:4px; }
.minutes-action-btn { display:inline-flex;align-items:center;gap:5px;padding:6px 12px;border-radius:7px;border:1px solid var(--border);background:#fff;color:#475569;font-size:12px;font-weight:500;cursor:pointer;transition:all .15s;white-space:nowrap; }
.minutes-action-btn:hover { background:#f1f5f9; }
.minutes-action-btn.primary { background:var(--primary);color:#fff;border-color:var(--primary); }
.minutes-action-btn.primary:hover { opacity:.88; }
.minutes-action-btn:disabled { opacity:.5;cursor:not-allowed; }
.minutes-saved-label { font-size:11px;color:#22c55e;display:flex;align-items:center;gap:4px; }
@keyframes spin { to { transform:rotate(360deg); } }
.spin { display:inline-block;animation:spin .7s linear infinite; }

/* Minutes bottom bar */
.sp-minutes-bar { display:flex;align-items:center;justify-content:space-between;padding:10px 16px;border-top:1px solid var(--border);flex-shrink:0;background:#fff;border-radius:0 0 12px 12px; }
.minutes-bar-left,.minutes-bar-right { display:flex;align-items:center;gap:6px; }
.mbar-btn { display:inline-flex;align-items:center;gap:5px;padding:6px 14px;border-radius:7px;border:1px solid var(--border);background:#fff;color:#475569;font-size:12px;font-weight:500;cursor:pointer;transition:all .15s;white-space:nowrap; }
.mbar-btn:hover { background:#f1f5f9; }
.mbar-btn.primary { background:var(--primary);color:#fff;border-color:var(--primary); }
.mbar-btn.primary:hover { opacity:.88; }
.mbar-btn.regen { background:#f8fafc;border-color:#c7d2fe;color:#4f46e5; }
.mbar-btn.regen:hover { background:#eef2ff; }
.mbar-btn:disabled { opacity:.45;cursor:not-allowed; }
.mbar-saved-label { font-size:11px;color:#22c55e;display:flex;align-items:center;gap:4px; }
</style>
