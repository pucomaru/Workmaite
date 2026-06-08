import { ref, computed, reactive, nextTick } from 'vue'
import hyeanAvatar from '../assets/agents/hyean.png'
import { apiAI, streamPost } from '../api'

export function useAgentChat({
  meetingGroups,
  membersData,
  tasksData,
  detailMeeting,
  detailTab,
  showExtractFlow,
  extractPhase,
  extractResult,
  toNumericId,
  onQueryHighlight,
  onLabelsHighlight,
  onQueryClear,
}) {
  // ─── Agents ───────────────────────────────────────────────────
  // 내부적으로는 5개 서브에이전트가 존재하지만 사용자에게는 단일 워크메이트 AI로 표시됨
  const SUPERVISOR = {
    name: '워크메이트 AI', nameEn: 'Workmate AI',
    avatar: hyeanAvatar,
    greeting: '안녕하세요! 저는 워크메이트 AI예요 😊\n무엇이든 물어보세요.',
    suggested: ['회의체 현황을 브리핑해줘', '이번 회의 아젠다를 정리해줘', '보고서를 검토해줘'],
    endpoint: '/api/agent/supervisor/chat',
  }

  const SUPERVISOR_EXTRACT = {
    name: '워크메이트 AI', nameEn: 'Workmate AI',
    avatar: hyeanAvatar,
    greeting: '회의록과 자료를 분석해서 과제를 추출했습니다.\n추출된 과제 목록을 검토해보시고, 수정이 필요한 항목이 있으면 말씀해주세요.\n\n예시: "3번 과제 담당자를 홍길동으로 바꿔줘", "2번과 4번 과제를 합쳐줘", "이 과제가 왜 추출됐는지 설명해줘"',
    suggested: ['각 과제가 추출된 이유를 설명해줘', '비슷한 과제들을 하나로 합쳐줘', '담당 부서 배정이 적절한지 검토해줘'],
    endpoint: '/api/agent/supervisor/chat',
  }

  const agentSidebarOpen = ref(false)
  const currentAgent = ref('supervisor')
  const agentInfo = computed(() => {
    if ((detailTab.value === 'task' || detailTab.value === 'extract') && showExtractFlow.value && extractPhase.value !== 'context') {
      return SUPERVISOR_EXTRACT
    }
    return SUPERVISOR
  })
  const allMessages = ref({ supervisor: [] })
  const currentMessages = computed(() => allMessages.value['supervisor'])
  const agentInput = ref('')
  const agentLoading = ref(false)
  const agentMessagesEl = ref(null)
  const agentFileInput = ref(null)
  const agentPendingFiles = ref([])
  const agentTextareaEl = ref(null)

  // ─── @ mention ────────────────────────────────────────────────
  const atMenuOpen = ref(false)
  const atQuery = ref('')
  const atCursorPos = ref(0)
  const atHighlight = ref(0)
  const mentionedContexts = ref([]) // [{id, type, label, icon, summary}]

  const AT_TYPE_ICONS = { meeting: '🏢', person: '👤', task: '✅', department: '🏬', session: '📅', document: '📄' }
  const AT_TYPE_LABELS = { meeting: '회의체', person: '구성원', task: '과제', department: '부서', session: '회의', document: '문서' }

  const atMenuItems = computed(() => {
    const q = atQuery.value.toLowerCase()
    const seen = new Set()
    const items = []
    // 회의체
    for (const mg of meetingGroups.value) {
      const label = mg.title || mg.name || ''
      if (!label) continue
      if (!q || label.toLowerCase().includes(q)) {
        const id = `mg-${mg.id}`
        if (!seen.has(id)) {
          seen.add(id)
          const memberNames = (mg.members || []).map(m => m.name).filter(Boolean).join(', ')
          const agendaList = (mg.agendas || []).map(a => a.content || a.title).filter(Boolean).slice(0, 3).join(', ')
          items.push({
            id, type: 'meeting', label, icon: '🏢',
            summary: ['[회의체] ' + label, mg.purpose ? '목적: ' + mg.purpose : '', memberNames ? '구성원: ' + memberNames : '', agendaList ? '아젠다: ' + agendaList : ''].filter(Boolean).join('\n'),
          })
        }
      }
    }
    // 구성원
    for (const m of membersData.value) {
      const label = m.name || ''
      if (!label) continue
      if (!q || label.toLowerCase().includes(q)) {
        const id = `person-${m.id || m.employee_id || m.name}`
        if (!seen.has(id)) {
          seen.add(id)
          items.push({
            id, type: 'person', label, icon: '👤',
            summary: ['[구성원] ' + label, m.department ? '부서: ' + m.department : '', m.position ? '직책: ' + m.position : ''].filter(Boolean).join('\n'),
          })
        }
      }
    }
    // 과제
    for (const t of tasksData.value) {
      const label = (t.content || t.title || '').slice(0, 40)
      if (!label) continue
      if (!q || label.toLowerCase().includes(q)) {
        const id = `task-${t.id}`
        if (!seen.has(id)) {
          seen.add(id)
          const statusLabel = { pending: '대기', done: '완료', in_progress: '진행중', at_risk: '위험' }[t.status] || t.status || ''
          items.push({
            id, type: 'task', label, icon: '✅',
            summary: ['[과제] ' + label, statusLabel ? '상태: ' + statusLabel : '', t.deadline ? '마감: ' + t.deadline : ''].filter(Boolean).join('\n'),
          })
        }
      }
    }
    // 현재 선택된 회의체의 세션
    if (detailMeeting.value?.sessions?.length) {
      for (const s of detailMeeting.value.sessions) {
        const label = s.title || s.name || ''
        if (!label) continue
        if (!q || label.toLowerCase().includes(q)) {
          const id = `session-${s.id}`
          if (!seen.has(id)) {
            seen.add(id)
            items.push({ id, type: 'session', label, icon: '📅', summary: ['[회의] ' + label, s.date ? '일시: ' + s.date : ''].filter(Boolean).join('\n') })
          }
        }
      }
    }
    return items.slice(0, 8)
  })

  function onAgentInput(e) {
    agentAutoResize()
    const val = agentInput.value
    const cursor = e.target.selectionStart
    const before = val.slice(0, cursor)
    const atIdx = before.lastIndexOf('@')
    if (atIdx !== -1) {
      const query = before.slice(atIdx + 1)
      if (!query.includes(' ') && !query.includes('\n')) {
        atQuery.value = query
        atCursorPos.value = atIdx
        atMenuOpen.value = true
        atHighlight.value = 0
        return
      }
    }
    atMenuOpen.value = false
  }

  function selectAtItem(item) {
    const el = agentTextareaEl.value
    const cursor = el ? el.selectionStart : agentInput.value.length
    const val = agentInput.value
    agentInput.value = val.slice(0, atCursorPos.value) + val.slice(cursor)
    if (!mentionedContexts.value.find(c => c.id === item.id)) {
      mentionedContexts.value.push(item)
    }
    atMenuOpen.value = false
    atQuery.value = ''
    nextTick(() => { agentTextareaEl.value?.focus(); agentAutoResize() })
  }

  function removeMentionCtx(id) {
    mentionedContexts.value = mentionedContexts.value.filter(c => c.id !== id)
  }

  function initAgentGreeting() {
    if (!allMessages.value['supervisor'].length)
      allMessages.value['supervisor'] = [{ role: 'agent', content: SUPERVISOR.greeting }]
  }

  function switchAgent(_key) {
    // 사용자에게는 단일 워크메이트 AI로 표시 — 내부 라우팅은 supervisor 엔드포인트가 처리
    agentSidebarOpen.value = true
    initAgentGreeting()
  }

  function clearAgentChat() {
    allMessages.value['supervisor'] = [{ role: 'agent', content: SUPERVISOR.greeting }]
    agentInput.value = ''; agentPendingFiles.value = []
  }

  async function sendAgentMsg() {
    const text = agentInput.value.trim()
    if ((!text && !agentPendingFiles.value.length && !mentionedContexts.value.length) || agentLoading.value) return
    agentInput.value = ''
    atMenuOpen.value = false
    if (agentTextareaEl.value) agentTextareaEl.value.style.height = '36px'
    let content = text
    if (agentPendingFiles.value.length) {
      const names = agentPendingFiles.value.map(f => f.name).join(', ')
      content = text ? `📎 ${names}\n${text}` : `📎 ${names}`
      agentPendingFiles.value = []
    }
    // @ 컨텍스트를 API 메시지에 주입 (화면에는 chips로만 표시)
    const ctxSnapshot = [...mentionedContexts.value]
    if (ctxSnapshot.length) {
      const ctxBlock = ctxSnapshot.map(c => c.summary).join('\n---\n')
      content = `${content}\n\n[참조 컨텍스트]\n${ctxBlock}`
      mentionedContexts.value = []
    }
    const key = 'supervisor'
    // 화면에는 원본 텍스트만 + 참조된 컨텍스트 칩 표시 (API엔 full content 전달)
    const displayText = text || (agentPendingFiles.value.length ? `📎 파일` : '')
    allMessages.value[key].push({ role: 'user', content: displayText, contexts: ctxSnapshot })

    // ── 사고 과정 블록 (실시간 백엔드 이벤트로 채움) ──────────────────
    // reactive()로 감싸야 로컬 변수 변경이 Vue 반응성 시스템에 즉시 반영됨
    const planningMsg = reactive({ role: 'planning', steps: [], open: true, done: false })
    allMessages.value[key].push(planningMsg)
    const agentMsg = reactive({ role: 'agent', content: '' })
    allMessages.value[key].push(agentMsg)
    agentLoading.value = true
    await nextTick()
    if (agentMessagesEl.value) agentMessagesEl.value.scrollTop = agentMessagesEl.value.scrollHeight

    // 과제 탭 추출 결과 단계 → chat-extract 엔드포인트로 과제 목록 업데이트
    // 'extract' 탭(runExtract 실행 후)과 'task' 탭(extractPhase=result) 모두 포함
    const isExtractMode = (detailTab.value === 'extract' || detailTab.value === 'task') &&
      showExtractFlow.value &&
      extractPhase.value === 'result' &&
      detailMeeting.value

    if (isExtractMode) {
      try {
        await streamPost(
          '/api/agent/archive/chat-extract',
          {
            meeting_id: toNumericId(detailMeeting.value.id),
            message: content,
            chat_history: [{ agendas: extractResult.value.map(({ title, department, priority, start_date, due_date }) => ({ title, department, priority, start_date, due_date })) }],
          },
          () => {},  // 텍스트 청크 없음
          () => {
            planningMsg.done = true
            agentLoading.value = false
            setTimeout(() => { planningMsg.open = false }, 1500)
          },
          (step) => {
            planningMsg.steps.push(step)
            nextTick(() => { if (agentMessagesEl.value) agentMessagesEl.value.scrollTop = agentMessagesEl.value.scrollHeight })
          },
          undefined,  // onHighlight
          (result) => {
            agentMsg.content = result.reply || '과제 목록을 업데이트했습니다.'
            if (result.agendas && result.agendas.length) {
              const oldList = extractResult.value
              extractResult.value = result.agendas.map((ag, i) => {
                const old = oldList[i]
                const unchanged = old &&
                  old.title === ag.title &&
                  JSON.stringify(old.bullets) === JSON.stringify(ag.bullets) &&
                  old.department === ag.department &&
                  old.priority === ag.priority
                return unchanged
                  ? old
                  : { ...ag, _state: null, _editing: false, _editTitle: ag.title, _editBullets: (ag.bullets || []).join('\n') }
              })
            }
          },
        )
      } catch {
        agentMsg.content = '과제 업데이트 중 오류가 발생했습니다.'
        planningMsg.done = true; planningMsg.open = false
        agentLoading.value = false
      }
      return
    }

    // 일반 모드: supervisor 채팅 — [PLANNING] 이벤트를 실시간으로 수신
    const history = allMessages.value[key]
      .filter(m => m.role === 'user' || m.role === 'agent')
      .slice(0, -1)
      .map(m => ({ role: m.role === 'user' ? 'user' : 'assistant', content: m.content }))
    try {
      await streamPost(
        agentInfo.value.endpoint,
        { meeting_id: toNumericId(detailMeeting.value?.id), message: content, chat_history: history },
        (chunk) => {
          agentMsg.content += chunk
          nextTick(() => { if (agentMessagesEl.value) agentMessagesEl.value.scrollTop = agentMessagesEl.value.scrollHeight })
        },
        () => {
          planningMsg.done = true
          agentLoading.value = false
          // PLANNING 중 임시 flash 소등 (AI HIGHLIGHT가 없을 경우 대비)
          onQueryClear()
          // 응답이 모두 도착한 뒤 1.5초 후 사고 과정 블록 접기
          setTimeout(() => { planningMsg.open = false }, 1500)
        },
        (step) => {
          planningMsg.steps.push(step)
          onQueryHighlight(step)
          nextTick(() => { if (agentMessagesEl.value) agentMessagesEl.value.scrollTop = agentMessagesEl.value.scrollHeight })
        },
        (labels) => {
          // AI 기반 하이라이팅: LLM 답변에 실제 언급된 노드
          onLabelsHighlight(labels)
        }
      )
    } catch {
      agentMsg.content = '응답 중 오류가 발생했습니다.'
      planningMsg.done = true; planningMsg.open = false
      agentLoading.value = false
    }
  }

  function isExtractModeActive() {
    return (detailTab.value === 'extract' || detailTab.value === 'task') &&
      showExtractFlow.value &&
      extractPhase.value === 'result' &&
      !!detailMeeting.value
  }

  function onAgentKeydown(e) {
    if (atMenuOpen.value && atMenuItems.value.length) {
      if (e.key === 'ArrowDown') { e.preventDefault(); atHighlight.value = (atHighlight.value + 1) % atMenuItems.value.length; return }
      if (e.key === 'ArrowUp') { e.preventDefault(); atHighlight.value = (atHighlight.value - 1 + atMenuItems.value.length) % atMenuItems.value.length; return }
      if (e.key === 'Enter' || e.key === 'Tab') { e.preventDefault(); selectAtItem(atMenuItems.value[atHighlight.value]); return }
      if (e.key === 'Escape') { atMenuOpen.value = false; return }
    }
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendAgentMsg() }
  }
  function onAgentFileSelected(e) { agentPendingFiles.value.push(...Array.from(e.target.files || [])); e.target.value = '' }
  function agentAutoResize() {
    const el = agentTextareaEl.value; if (!el) return
    el.style.height = '36px'; el.style.height = Math.min(el.scrollHeight, 100) + 'px'
  }

  // ─── 사고 과정 helper ─────────────────────────────────────────
  async function _runPlanningSteps(planningMsg, steps, delayMs = 360) {
    for (const step of steps) {
      planningMsg.steps.push(step)
      await new Promise(r => setTimeout(r, delayMs))
      nextTick(() => { if (agentMessagesEl.value) agentMessagesEl.value.scrollTop = agentMessagesEl.value.scrollHeight })
    }
    planningMsg.done = true
    // extract/inject 모드는 응답 생성 후 바로 접기
    setTimeout(() => { planningMsg.open = false }, 1200)
  }

  // ─── 좌측 액션 → 우측 에이전트 채팅 주입 ─────────────────────
  async function injectActionToAgent(userText, planningSteps, agentReply) {
    if (!agentSidebarOpen.value) { agentSidebarOpen.value = true; initAgentGreeting() }
    await nextTick()
    allMessages.value['supervisor'].push({ role: 'user', content: userText })
    const planningMsg = reactive({ role: 'planning', steps: [], open: true, done: false })
    allMessages.value['supervisor'].push(planningMsg)
    if (agentMessagesEl.value) agentMessagesEl.value.scrollTop = agentMessagesEl.value.scrollHeight
    await _runPlanningSteps(planningMsg, planningSteps)
    const agentMsg = { role: 'agent', content: '' }
    allMessages.value['supervisor'].push(agentMsg)
    for (let i = 0; i < agentReply.length; i++) {
      agentMsg.content += agentReply[i]
      if (i % 4 === 0) {
        await new Promise(r => setTimeout(r, 10))
        if (agentMessagesEl.value) agentMessagesEl.value.scrollTop = agentMessagesEl.value.scrollHeight
      }
    }
  }

  // ─── 관계도 분석·재구성 워크플로우 ────────────────────────────
  // Supervisor가 임베딩 기반으로 회의 간 잠재 연결·구조 공백을 '분석'하고,
  // Knowledge agent가 발굴된 지식 연결을 그래프에 '재구성'한 뒤 근거를 보고합니다.
  // 실시간 [PLANNING] 스텝을 수신하며, 완료 시 onComplete(그래프 새로고침)를 호출합니다.
  async function runRelationshipAnalysis(onComplete) {
    if (agentLoading.value) return
    if (!agentSidebarOpen.value) { agentSidebarOpen.value = true; initAgentGreeting() }
    await nextTick()

    allMessages.value['supervisor'].push({
      role: 'user',
      content: '회의별로 흩어진 지식을 분석해서 연관된 안건·문서를 서로 연결해줘',
    })
    const planningMsg = reactive({ role: 'planning', steps: [], open: true, done: false })
    allMessages.value['supervisor'].push(planningMsg)
    const agentMsg = reactive({ role: 'agent', content: '' })
    allMessages.value['supervisor'].push(agentMsg)
    agentLoading.value = true
    await nextTick()
    if (agentMessagesEl.value) agentMessagesEl.value.scrollTop = agentMessagesEl.value.scrollHeight

    try {
      await streamPost(
        '/api/agent/knowledge/analyze-relationships',
        {},
        (chunk) => {
          agentMsg.content += chunk
          nextTick(() => { if (agentMessagesEl.value) agentMessagesEl.value.scrollTop = agentMessagesEl.value.scrollHeight })
        },
        () => {
          planningMsg.done = true
          agentLoading.value = false
          onQueryClear()
          setTimeout(() => { planningMsg.open = false }, 1500)
          // 재설정된 관계를 그래프에 반영
          onComplete?.()
        },
        (step) => {
          planningMsg.steps.push(step)
          onQueryHighlight(step)
          nextTick(() => { if (agentMessagesEl.value) agentMessagesEl.value.scrollTop = agentMessagesEl.value.scrollHeight })
        },
        (labels) => { onLabelsHighlight(labels) },
      )
    } catch {
      agentMsg.content = '관계도 분석 중 오류가 발생했습니다.'
      planningMsg.done = true; planningMsg.open = false
      agentLoading.value = false
    }
  }

  return {
    SUPERVISOR, SUPERVISOR_EXTRACT,
    agentSidebarOpen, currentAgent, agentInfo,
    allMessages, currentMessages,
    agentInput, agentLoading, agentMessagesEl, agentFileInput, agentPendingFiles, agentTextareaEl,
    atMenuOpen, atQuery, atCursorPos, atHighlight, mentionedContexts,
    AT_TYPE_ICONS, AT_TYPE_LABELS, atMenuItems,
    onAgentInput, selectAtItem, removeMentionCtx, initAgentGreeting,
    switchAgent, clearAgentChat, sendAgentMsg, isExtractModeActive,
    onAgentKeydown, onAgentFileSelected, agentAutoResize,
    _runPlanningSteps, injectActionToAgent, runRelationshipAnalysis,
  }
}
