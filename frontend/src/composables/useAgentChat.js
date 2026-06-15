import { ref, computed, reactive, nextTick, watch } from 'vue'
import hyeanAvatar from '../assets/agents/hyean.png'
import api, { apiAI, streamPost } from '../api'
import { useAgentMention } from './useAgentMention'
import { useAuthStore } from '../stores/auth'
import { selectedModel } from '../stores/llmModel'

export function useAgentChat({
  meetings,
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
  const SUPERVISOR = {
    name: '워크메이트 AI',
    nameEn: 'Workmate AI',
    avatar: hyeanAvatar,
    greeting: '안녕하세요! 저는 워크메이트 AI예요 😊\n무엇이든 물어보세요.',
    suggested: [
      '회의체 현황을 브리핑해줘',
      '회의체별 아젠다 현황 알려줘',
      '최근 보고서 제출 현황 알려줘',
    ],
    suggestedAt: ['@ 회의체 · 회의 범위 지정'],
    endpoint: '/api/agent/supervisor/chat',
  }

  const SUPERVISOR_EXTRACT = {
    name: '워크메이트 AI',
    nameEn: 'Workmate AI',
    avatar: hyeanAvatar,
    greeting:
      '회의록과 자료를 분석해서 아젠다를 추출했습니다.\n추출된 아젠다 목록을 검토해보시고, 수정이 필요한 항목이 있으면 말씀해주세요.\n\n예시: "3번 아젠다 담당자를 홍길동으로 바꿔줘", "2번과 4번 아젠다를 합쳐줘", "이 아젠다가 왜 추출됐는지 설명해줘"',
    suggested: [
      '각 아젠다가 추출된 이유를 설명해줘',
      '비슷한 아젠다들을 하나로 합쳐줘',
      '담당 부서 배정이 적절한지 검토해줘',
    ],
    endpoint: '/api/agent/supervisor/chat',
  }

  const authStore = useAuthStore()

  const agentSidebarOpen = ref(false)
  const currentAgent = ref('supervisor')
  const agentInfo = computed(() => {
    if (
      (detailTab.value === 'task' || detailTab.value === 'extract') &&
      showExtractFlow.value &&
      extractPhase.value !== 'context'
    ) {
      return SUPERVISOR_EXTRACT
    }
    return SUPERVISOR
  })
  const allMessages = ref({ supervisor: [] })
  const currentMessages = computed(() => allMessages.value['supervisor'])
  const agentInput = ref('')
  const agentLoading = ref(false)
  let _agentAbortCtrl = null

  /** 스트리밍 응답 중단 (P3A-6) — fetch abort가 서버 generator 취소까지 전파된다 */
  function stopAgentResponse() {
    try {
      _agentAbortCtrl?.abort()
    } catch {}
    agentLoading.value = false
  }
  const agentMessagesEl = ref(null)
  const agentFileInput = ref(null)
  const agentPendingFiles = ref([])
  const agentTextareaEl = ref(null)

  // ─── @ mention (공통 컴포저블) ────────────────────────────────
  const {
    atMenuOpen,
    atQuery,
    atCursorPos,
    atHighlight,
    mentionedContexts,
    AT_TYPE_ICONS,
    AT_TYPE_LABELS,
    atMenuItems,
    onAgentInput,
    selectAtItem,
    removeMentionCtx,
    handleMentionKeydown,
    consumeMentionContext,
  } = useAgentMention({
    meetings,
    membersData,
    tasksData,
    detailMeeting,
    agentInput,
    agentTextareaEl,
    autoResize: () => agentAutoResize(),
  })

  // ─── thread_id 계산 ──────────────────────────────────────────
  // 아카이브 탭은 회의체 선택과 무관하게 사용자별 단일 스레드로 유지
  function getThreadId() {
    const uid = authStore.user?.id
    return uid ? `archive_${uid}` : null
  }

  // ─── 채팅 히스토리 로드 (Spring Boot GET) ─────────────────────
  // 상단 스크롤 시 이전 페이지 로드 (P8-6, keyset beforeId)
  let _loadingOlder = false
  let _historyExhausted = false

  async function loadOlderMessages() {
    const list = allMessages.value['supervisor'] || []
    const first = list.find(m => m.id)
    if (!first || _loadingOlder || _historyExhausted) return
    _loadingOlder = true
    try {
      const threadId = getThreadId()
      const res = await api.get('/api/v1/chat/messages', {
        params: { threadId, limit: 100, beforeId: first.id },
      })
      const older = (Array.isArray(res.data) ? res.data : []).map(m => ({
        id: m.id,
        role: m.role === 'assistant' ? 'agent' : m.role,
        content: m.content,
      }))
      if (!older.length) {
        _historyExhausted = true
        return
      }
      const el = agentMessagesEl.value
      const prevHeight = el ? el.scrollHeight : 0
      list.unshift(...older)
      await nextTick()
      if (el) el.scrollTop = el.scrollHeight - prevHeight // 보던 위치 유지
    } catch {
      /* 다음 스크롤에서 재시도 */
    } finally {
      _loadingOlder = false
    }
  }

  async function loadChatHistory() {
    const threadId = getThreadId()
    if (!threadId) {
      allMessages.value['supervisor'] = [{ role: 'agent', content: SUPERVISOR.greeting }]
      return
    }
    try {
      const res = await api.get('/api/v1/chat/messages', { params: { threadId, limit: 100 } }) // P8-2: 초기 로드 상한 (과거 페이지는 P8-6)
      // 인터셉터가 ApiResponse를 언랩하므로 res.data 가 바로 List<ChatMessageResponse>
      const messages = Array.isArray(res.data) ? res.data : (res.data?.data ?? [])
      if (messages.length === 0) {
        allMessages.value['supervisor'] = [{ role: 'agent', content: SUPERVISOR.greeting }]
      } else {
        // DB의 role: 'user' | 'assistant' → UI: 'user' | 'agent'
        allMessages.value['supervisor'] = messages.map(m => ({
          id: m.id, // loadMore 커서용 (P8-6)
          role: m.role === 'assistant' ? 'agent' : m.role,
          content: m.content,
        }))
      }
    } catch (err) {
      console.error('[AgentChat] loadChatHistory error:', err?.response?.status, err?.message)
      allMessages.value['supervisor'] = [{ role: 'agent', content: SUPERVISOR.greeting }]
    }
    await nextTick()
    requestAnimationFrame(() => {
      if (agentMessagesEl.value)
        agentMessagesEl.value.scrollTop = agentMessagesEl.value.scrollHeight
    })
  }

  // ─── 사이드바가 열릴 때마다 히스토리 로드 ───────────────────────
  // archive 스레드는 회의체 변경과 무관하므로 열릴 때만 로드
  // _skipAutoHistoryLoad: 분석·추출·검토 등 '프로그램적 오픈'은 직후 자체 메시지를 push하므로,
  // 늦게 도착해 그 메시지를 덮어쓰는 자동 히스토리 로드를 1회 건너뛴다 (regression: 6af82fe).
  let _skipAutoHistoryLoad = false
  watch(agentSidebarOpen, open => {
    if (!open) return
    if (_skipAutoHistoryLoad) {
      _skipAutoHistoryLoad = false
      return
    }
    loadChatHistory()
  })

  // 사이드바를 프로그램적으로 연다(닫혀 있을 때만). watch의 자동 로드를 건너뛰게 해
  // 호출자가 직후 push하는 메시지가 보존된다. 실제로 열었으면 true 반환.
  function openSidebarManaged() {
    if (agentSidebarOpen.value) return false
    _skipAutoHistoryLoad = true
    agentSidebarOpen.value = true
    return true
  }

  function initAgentGreeting() {
    if (!allMessages.value['supervisor'].length)
      allMessages.value['supervisor'] = [{ role: 'agent', content: SUPERVISOR.greeting }]
  }

  function switchAgent(_key) {
    agentSidebarOpen.value = true
    loadChatHistory()
  }

  // 새 채팅: DB 삭제 + UI 초기화
  async function clearAgentChat() {
    const threadId = getThreadId()
    if (threadId) {
      try {
        await api.delete('/api/v1/chat/messages', { params: { threadId } })
      } catch {
        /* 무시 */
      }
    }
    allMessages.value['supervisor'] = [{ role: 'agent', content: SUPERVISOR.greeting }]
    agentInput.value = ''
    agentPendingFiles.value = []
  }

  async function sendAgentMsg() {
    const text = agentInput.value.trim()
    if (
      (!text && !agentPendingFiles.value.length && !mentionedContexts.value.length) ||
      agentLoading.value
    )
      return
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
    const { block: ctxBlock, contexts: ctxSnapshot } = consumeMentionContext()
    if (ctxBlock) {
      content = `${content}${ctxBlock}`
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
    const isExtractMode =
      (detailTab.value === 'extract' || detailTab.value === 'task') &&
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
            chat_history: [
              {
                agendas: extractResult.value.map(
                  ({ title, department, priority, start_date, due_date, db_id }) => ({
                    title,
                    department,
                    priority,
                    start_date,
                    due_date,
                    db_id,
                  }),
                ),
              },
            ],
          },
          () => {}, // 텍스트 청크 없음
          () => {
            planningMsg.done = true
            agentLoading.value = false
            setTimeout(() => {
              planningMsg.open = false
            }, 1500)
          },
          step => {
            planningMsg.steps.push(step)
            nextTick(() => {
              if (agentMessagesEl.value)
                agentMessagesEl.value.scrollTop = agentMessagesEl.value.scrollHeight
            })
          },
          undefined, // onHighlight
          result => {
            agentMsg.content = result.reply || '아젠다 목록을 업데이트했습니다.'
            if (result.agendas && result.agendas.length) {
              const oldList = extractResult.value
              extractResult.value = result.agendas.map((ag, i) => {
                const old = oldList[i]
                const unchanged =
                  old &&
                  old.title === ag.title &&
                  JSON.stringify(old.bullets) === JSON.stringify(ag.bullets) &&
                  old.department === ag.department &&
                  old.priority === ag.priority
                return unchanged
                  ? { ...old, db_id: ag.db_id ?? null }
                  : {
                      ...ag,
                      _state: null,
                      _editing: false,
                      _editTitle: ag.title,
                      _editBullets: (ag.bullets || []).join('\n'),
                    }
              })
            }
          },
        )
      } catch {
        agentMsg.content = '아젠다 업데이트 중 오류가 발생했습니다.'
        planningMsg.done = true
        planningMsg.open = false
        agentLoading.value = false
      }
      return
    }

    // 일반 모드: supervisor 채팅 — [PLANNING] 이벤트를 실시간으로 수신
    _agentAbortCtrl = new AbortController()
    const history = allMessages.value[key]
      .filter(m => m.role === 'user' || m.role === 'agent')
      .slice(0, -1)
      .map(m => ({ role: m.role === 'user' ? 'user' : 'assistant', content: m.content }))
    try {
      await streamPost(
        agentInfo.value.endpoint,
        {
          thread_id: getThreadId(),
          meeting_id: toNumericId(detailMeeting.value?.id) || 0,
          message: content,
          chat_history: history,
          model: selectedModel.value || undefined,
        },
        chunk => {
          agentMsg.content += chunk
          nextTick(() => {
            if (agentMessagesEl.value)
              agentMessagesEl.value.scrollTop = agentMessagesEl.value.scrollHeight
          })
        },
        () => {
          planningMsg.done = true
          agentLoading.value = false
          // PLANNING 중 임시 flash 소등 (AI HIGHLIGHT가 없을 경우 대비)
          onQueryClear()
          // 응답이 모두 도착한 뒤 1.5초 후 사고 과정 블록 접기
          setTimeout(() => {
            planningMsg.open = false
          }, 1500)
        },
        step => {
          planningMsg.steps.push(step)
          onQueryHighlight(step)
          nextTick(() => {
            if (agentMessagesEl.value)
              agentMessagesEl.value.scrollTop = agentMessagesEl.value.scrollHeight
          })
        },
        labels => {
          // AI 기반 하이라이팅: LLM 답변에 실제 언급된 노드
          onLabelsHighlight(labels)
        },
        undefined, // onResult
        {
          signal: _agentAbortCtrl.signal,
          onAction: spec => {
            // 에이전트 쓰기 제안 → 확인 카드 메시지 삽입 (실행은 사용자가 확인 버튼을 눌러야)
            allMessages.value[key].push(
              reactive({ role: 'action', spec, state: 'pending', error: '' }),
            )
            nextTick(() => {
              if (agentMessagesEl.value)
                agentMessagesEl.value.scrollTop = agentMessagesEl.value.scrollHeight
            })
          },
        },
      )
    } catch {
      agentMsg.content = '응답 중 오류가 발생했습니다.'
      planningMsg.done = true
      planningMsg.open = false
      agentLoading.value = false
    }
  }

  // ── 에이전트 쓰기 액션 확인/실행 (확인 카드) ────────────────────────────
  // 실행은 기존 CRUD 엔드포인트로 — 권한 재검증·감사(AuditLogMiddleware)·동기화가 그쪽에서 보장됨.
  async function confirmAgentAction(msg) {
    if (!msg?.spec?.exec || msg.state !== 'pending') return
    msg.state = 'running'
    const { method, url, body } = msg.spec.exec
    try {
      await apiAI[method](url, body)
      msg.state = 'done'
      allMessages.value['supervisor'].push(
        reactive({ role: 'agent', content: `✅ ${msg.spec.summary}을(를) 완료했습니다.` }),
      )
    } catch (e) {
      msg.state = 'error'
      msg.error = e?.response?.data?.detail || e?.message || '실행에 실패했습니다.'
    }
  }
  function cancelAgentAction(msg) {
    if (msg && msg.state === 'pending') msg.state = 'cancelled'
  }

  function isExtractModeActive() {
    return (
      (detailTab.value === 'extract' || detailTab.value === 'task') &&
      showExtractFlow.value &&
      extractPhase.value === 'result' &&
      !!detailMeeting.value
    )
  }

  // ─── @ 범위 지정 버튼 — "@" 입력 후 드롭다운 오픈 ──────────────
  function triggerAtSuggest() {
    agentInput.value = '@'
    atQuery.value = ''
    atCursorPos.value = 0
    atMenuOpen.value = true
    atHighlight.value = 0
    nextTick(() => {
      const el = agentTextareaEl.value
      if (el) {
        el.focus()
        el.setSelectionRange(1, 1)
      }
    })
  }

  function onAgentKeydown(e) {
    if (handleMentionKeydown(e)) return
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      sendAgentMsg()
    }
  }
  function onAgentFileSelected(e) {
    agentPendingFiles.value.push(...Array.from(e.target.files || []))
    e.target.value = ''
  }
  function agentAutoResize() {
    const el = agentTextareaEl.value
    if (!el) return
    el.style.height = '36px'
    el.style.height = Math.min(el.scrollHeight, 100) + 'px'
  }

  // ─── 사고 과정 helper ─────────────────────────────────────────
  async function _runPlanningSteps(planningMsg, steps, delayMs = 360) {
    for (const step of steps) {
      planningMsg.steps.push(step)
      await new Promise(r => setTimeout(r, delayMs))
      nextTick(() => {
        if (agentMessagesEl.value)
          agentMessagesEl.value.scrollTop = agentMessagesEl.value.scrollHeight
      })
    }
    planningMsg.done = true
    // extract/inject 모드는 응답 생성 후 바로 접기
    setTimeout(() => {
      planningMsg.open = false
    }, 1200)
  }

  // ─── 좌측 액션 → 우측 에이전트 채팅 주입 ─────────────────────
  async function injectActionToAgent(userText, planningSteps, agentReply) {
    if (openSidebarManaged()) await loadChatHistory()
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
        if (agentMessagesEl.value)
          agentMessagesEl.value.scrollTop = agentMessagesEl.value.scrollHeight
      }
    }
  }

  // ─── 관계도 분석·재구성 워크플로우 ────────────────────────────
  // Supervisor가 임베딩 기반으로 회의 간 잠재 연결·구조 공백을 '분석'하고,
  // Knowledge agent가 발굴된 지식 연결을 그래프에 '재구성'한 뒤 근거를 보고합니다.
  // 실시간 [PLANNING] 스텝을 수신하며, 완료 시 onComplete(그래프 새로고침)를 호출합니다.
  async function runRelationshipAnalysis(onComplete) {
    if (agentLoading.value) return
    if (openSidebarManaged()) await loadChatHistory()
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
        chunk => {
          agentMsg.content += chunk
          nextTick(() => {
            if (agentMessagesEl.value)
              agentMessagesEl.value.scrollTop = agentMessagesEl.value.scrollHeight
          })
        },
        () => {
          planningMsg.done = true
          agentLoading.value = false
          onQueryClear()
          setTimeout(() => {
            planningMsg.open = false
          }, 1500)
          // 재설정된 관계를 그래프에 반영
          onComplete?.()
        },
        step => {
          planningMsg.steps.push(step)
          onQueryHighlight(step)
          nextTick(() => {
            if (agentMessagesEl.value)
              agentMessagesEl.value.scrollTop = agentMessagesEl.value.scrollHeight
          })
        },
        labels => {
          onLabelsHighlight(labels)
        },
      )
    } catch {
      agentMsg.content = '관계도 분석 중 오류가 발생했습니다.'
      planningMsg.done = true
      planningMsg.open = false
      agentLoading.value = false
    }
  }

  return {
    SUPERVISOR,
    SUPERVISOR_EXTRACT,
    agentSidebarOpen,
    currentAgent,
    agentInfo,
    allMessages,
    currentMessages,
    agentInput,
    agentLoading,
    agentMessagesEl,
    agentFileInput,
    agentPendingFiles,
    agentTextareaEl,
    stopAgentResponse,
    getThreadId,
    loadOlderMessages,
    atMenuOpen,
    atQuery,
    atCursorPos,
    atHighlight,
    mentionedContexts,
    AT_TYPE_ICONS,
    AT_TYPE_LABELS,
    atMenuItems,
    onAgentInput,
    selectAtItem,
    removeMentionCtx,
    initAgentGreeting,
    loadChatHistory,
    openSidebarManaged,
    switchAgent,
    clearAgentChat,
    sendAgentMsg,
    confirmAgentAction,
    cancelAgentAction,
    isExtractModeActive,
    triggerAtSuggest,
    onAgentKeydown,
    onAgentFileSelected,
    agentAutoResize,
    _runPlanningSteps,
    injectActionToAgent,
    runRelationshipAnalysis,
  }
}
