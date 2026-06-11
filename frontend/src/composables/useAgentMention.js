import { ref, computed, nextTick } from 'vue'

/**
 * @ 멘션 메뉴 공통 로직.
 * 아카이브 그래프의 모든 노드(회의체·구성원·과제·세션)를 @로 검색/참조한다.
 * 아카이브 AI 사이드바와 회의 AI 사이드바가 동일하게 재사용한다.
 *
 * @param {object}   opts
 * @param {Ref<Array>} opts.meetingGroups  회의체 목록 (members/agendas/purpose 포함)
 * @param {Ref<Array>} opts.membersData    전체 구성원
 * @param {Ref<Array>} opts.tasksData      전체 과제
 * @param {Ref<object>} [opts.detailMeeting] 현재 선택된 회의체(세션 검색용, 선택)
 * @param {Ref<string>} opts.agentInput    입력 textarea v-model ref
 * @param {Ref<HTMLElement>} opts.agentTextareaEl textarea DOM ref
 * @param {Function} [opts.autoResize]     입력 시 호출할 높이 재조정 함수
 */
export function useAgentMention({
  meetingGroups,
  membersData,
  tasksData,
  detailMeeting,
  agentInput,
  agentTextareaEl,
  autoResize,
}) {
  const atMenuOpen = ref(false)
  const atQuery = ref('')
  const atCursorPos = ref(0)
  const atHighlight = ref(0)
  const mentionedContexts = ref([]) // [{id, type, label, icon, summary}]

  const AT_TYPE_ICONS = { meeting: '🏢', person: '👤', task: '✅', department: '🏬', session: '📅', document: '📄' }
  const AT_TYPE_LABELS = { meeting: '회의체', person: '구성원', task: '아젠다', department: '부서', session: '회의', document: '문서' }

  function _fmtDate(d) {
    if (!d) return ''
    const m = String(d).match(/(\d{4})-(\d{2})-(\d{2})/)
    return m ? `${m[1]}.${m[2]}.${m[3]}` : String(d).slice(0, 10)
  }

  const atMenuItems = computed(() => {
    const q = atQuery.value.toLowerCase()
    const seen = new Set()
    const items = []
    // 회의체
    for (const mg of (meetingGroups?.value || [])) {
      const label = mg.title || mg.name || ''
      if (!label) continue
      if (!q || label.toLowerCase().includes(q)) {
        const id = `mg-${mg.id}`
        if (!seen.has(id)) {
          seen.add(id)
          const memberNames = (mg.members || []).map(m => m.name || m.userName).filter(Boolean).join(', ')
          const agendaList = (mg.tasks || mg.agendas || []).map(a => a.content || a.title).filter(Boolean).slice(0, 3).join(', ')
          items.push({
            id, type: 'meeting', label, icon: '🏢',
            summary: ['[회의체] ' + label, mg.purpose ? '목적: ' + mg.purpose : '', memberNames ? '구성원: ' + memberNames : '', agendaList ? '아젠다: ' + agendaList : ''].filter(Boolean).join('\n'),
          })
        }
      }
    }
    // 회의 (sessions) — 모든 회의체의 minutes 배열에서 수집
    for (const mg of (meetingGroups?.value || [])) {
      for (const s of (mg.minutes || [])) {
        const sessionTitle = s.session_title || s.title || ''
        if (!sessionTitle) continue
        const dateStr = _fmtDate(s.date || s.started_at)
        const label = dateStr ? `${sessionTitle} - ${dateStr}` : sessionTitle
        if (!q || sessionTitle.toLowerCase().includes(q) || dateStr.includes(q)) {
          const id = `session-${s.id}`
          if (!seen.has(id)) {
            seen.add(id)
            items.push({
              id, type: 'session', label, icon: '📅',
              summary: ['[회의] ' + sessionTitle, mg.title ? '회의체: ' + mg.title : '', dateStr ? '일시: ' + dateStr : ''].filter(Boolean).join('\n'),
            })
          }
        }
      }
    }
    // 아젠다
    for (const t of (tasksData?.value || [])) {
      const label = (t.content || t.title || '').slice(0, 40)
      if (!label) continue
      if (!q || label.toLowerCase().includes(q)) {
        const id = `task-${t.id}`
        if (!seen.has(id)) {
          seen.add(id)
          const statusLabel = { pending: '대기', done: '완료', ongoing: '진행 중', in_progress: '진행 중', at_risk: '위험', submitted: '제출완료', draft: '초안' }[t.status] || t.status || ''
          items.push({
            id, type: 'task', label, icon: '✅',
            summary: ['[아젠다] ' + label, statusLabel ? '상태: ' + statusLabel : '', t.due_date || t.deadline ? '마감: ' + (t.due_date || t.deadline) : ''].filter(Boolean).join('\n'),
          })
        }
      }
    }
    return items.slice(0, 12)
  })

  function onAgentInput(e) {
    autoResize?.()
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
    nextTick(() => { agentTextareaEl.value?.focus(); autoResize?.() })
  }

  function removeMentionCtx(id) {
    mentionedContexts.value = mentionedContexts.value.filter(c => c.id !== id)
  }

  /**
   * @멘션 메뉴가 열려 있을 때 키 입력을 처리한다.
   * @returns {boolean} 키 입력을 소비했으면 true (상위에서 send 등 동작 막기)
   */
  function handleMentionKeydown(e) {
    if (!atMenuOpen.value || !atMenuItems.value.length) return false
    if (e.key === 'ArrowDown') { e.preventDefault(); atHighlight.value = (atHighlight.value + 1) % atMenuItems.value.length; return true }
    if (e.key === 'ArrowUp') { e.preventDefault(); atHighlight.value = (atHighlight.value - 1 + atMenuItems.value.length) % atMenuItems.value.length; return true }
    if (e.key === 'Enter' || e.key === 'Tab') { e.preventDefault(); selectAtItem(atMenuItems.value[atHighlight.value]); return true }
    if (e.key === 'Escape') { atMenuOpen.value = false; return true }
    return false
  }

  /**
   * 전송 직전 호출. 참조된 컨텍스트를 API 메시지에 주입할 텍스트 블록과
   * 화면 표시용 스냅샷을 반환하고 멘션을 초기화한다.
   * @returns {{ block: string, contexts: Array }}
   */
  function consumeMentionContext() {
    const contexts = [...mentionedContexts.value]
    const block = contexts.length
      ? `\n\n[참조 컨텍스트]\n${contexts.map(c => c.summary).join('\n---\n')}`
      : ''
    mentionedContexts.value = []
    return { block, contexts }
  }

  return {
    atMenuOpen, atQuery, atCursorPos, atHighlight, mentionedContexts,
    AT_TYPE_ICONS, AT_TYPE_LABELS, atMenuItems,
    onAgentInput, selectAtItem, removeMentionCtx, handleMentionKeydown, consumeMentionContext,
  }
}
