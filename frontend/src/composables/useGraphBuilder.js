export function useGraphBuilder({
  meetings,
  currentCompany,
  currentPerson,
  neo4jDepts,
  relatedAgendas,
  manualRelations,
}) {
  function buildGraphNodes() {
    const nodes = [],
      edges = []
    const data = meetings.value

    const deptIdByName = new Map(neo4jDepts.value.map(d => [d.name, d.id]))
    const globalAgendaIdxMap = new Map()

    // ── Company nodes ──────────────────────────────────────
    // 멤버의 company에서 회사 노드를 파생한다 — 여러 회사가 참여하면 회사 노드도 여러 개.
    // (기존: currentCompany 하나로 단일 'company-node'를 만들어 모든 회의체를 묶어버려 '조직' 1개만 표시됐음)
    const companyIdxByName = new Map()
    const memberCompany = mb => mb.company || mb.user?.company || ''
    function getCompanyIdx(name) {
      const key = (name || '').trim()
      if (!key) return -1
      if (companyIdxByName.has(key)) return companyIdxByName.get(key)
      const idx = nodes.length
      companyIdxByName.set(key, idx)
      nodes.push({ id: `company-${key}`, label: key, type: 'company', data: { name: key } })
      return idx
    }

    if (!data.length) {
      // 신규 유저(소속 회의체 없음)도 회사·부서·본인만은 시각화한다(빈 화면 방지).
      const person = currentPerson?.value
      const coName = currentCompany?.value?.name || person?.company || ''
      let coIdx = -1
      if (coName) {
        coIdx = nodes.length
        nodes.push({
          id: `company-${coName}`,
          label: coName,
          type: 'company',
          data: { name: coName },
        })
      }
      let fbDeptIdx = -1
      if (person?.department) {
        fbDeptIdx = nodes.length
        nodes.push({ id: `dept-${person.department}`, label: person.department, type: 'dept' })
        if (coIdx >= 0) edges.push({ from: fbDeptIdx, to: coIdx, rel: '소속' })
      }
      if (person?.name) {
        const pIdx = nodes.length
        nodes.push({
          id: `person-${person.id || person.email || person.name}`,
          label: person.name,
          type: 'person',
          data: person,
        })
        if (fbDeptIdx >= 0) edges.push({ from: pIdx, to: fbDeptIdx, rel: '소속' })
        else if (coIdx >= 0) edges.push({ from: pIdx, to: coIdx, rel: '소속' })
      }
      return { nodes, edges }
    }

    data.forEach((g, gi) => {
      const rawId = g.id || gi
      const mgNodeId = typeof rawId === 'string' && rawId.includes('-') ? rawId : `mg-${rawId}`

      // ── Meeting node ────────────────────────────────────
      const mgIdx = nodes.length
      nodes.push({
        id: mgNodeId,
        label: g.title || `회의체${gi + 1}`,
        type: 'Meetings',
        data: g,
        groupIdx: gi,
        neo4jId: g.id || null,
        ended: g.status === 'ended',
      })
      // meeting -[포함]→ host company (간사 소속 회사, 없으면 첫 멤버 회사)
      const _adminMb = (g.members || []).find(mb => mb.role === 'admin')
      const _hostCompany =
        memberCompany(_adminMb || {}) || memberCompany((g.members || [])[0] || {})
      const _hostCoIdx = getCompanyIdx(_hostCompany)
      if (_hostCoIdx >= 0) edges.push({ from: mgIdx, to: _hostCoIdx, rel: '포함' })

      // ── Department + Person nodes ────────────────────────────
      const membersByDept = new Map()
      const personIdxByKey = new Map()
      ;(g.members || []).forEach(mb => {
        const d = mb.department || mb.dept || '미지정'
        if (!membersByDept.has(d)) membersByDept.set(d, [])
        membersByDept.get(d).push(mb)
      })
      const depts = [...membersByDept.keys()]
      const deptIdxMap = new Map()

      depts.forEach(deptName => {
        const deptIdx = nodes.length
        deptIdxMap.set(deptName, deptIdx)
        nodes.push({
          id: `dept-${deptIdByName.get(deptName) || deptName}`,
          label: deptName,
          type: 'dept',
          members: membersByDept.get(deptName),
          groupIdx: gi,
          meetingId: mgNodeId,
          neo4jId: deptIdByName.get(deptName) || null,
        })
        edges.push({ from: deptIdx, to: mgIdx, rel: '참여' })
        // dept -[소속]→ 그 부서 멤버의 회사
        const _deptCompany = (membersByDept.get(deptName) || []).map(memberCompany).find(Boolean)
        const _deptCoIdx = getCompanyIdx(_deptCompany)
        if (_deptCoIdx >= 0) edges.push({ from: deptIdx, to: _deptCoIdx, rel: '소속' })
        ;(membersByDept.get(deptName) || []).forEach(mb => {
          const pIdx = nodes.length
          const pName = mb.userName || mb.name || '?'
          const pKey = mb.userId || mb.email || pName
          personIdxByKey.set(pKey, pIdx)
          personIdxByKey.set(pName, pIdx)
          nodes.push({
            id: `person-${mb.userId || mb.email || pName}`,
            label: pName,
            type: 'person',
            groupIdx: gi,
            meetingId: mgNodeId,
            data: mb,
            neo4jId: mb.userId || null,
          })
          edges.push({ from: pIdx, to: deptIdx, rel: '소속' })
          edges.push({ from: pIdx, to: mgIdx, rel: mb.role === 'admin' ? '간사' : '구성원' })
        })
      })

      // ── Agenda nodes ─────────────────────────────────────────
      const taskList = g.tasks || []
      const tasksByDept = new Map()
      depts.forEach(d => tasksByDept.set(d, []))
      const unassigned = []
      taskList.forEach(task => {
        const d = task.assignee_dept || task.dept || ''
        if (d && tasksByDept.has(d)) tasksByDept.get(d).push(task)
        else unassigned.push(task)
      })
      unassigned.forEach((task, ti) => {
        if (depts.length > 0) tasksByDept.get(depts[ti % depts.length]).push(task)
      })

      const agendaIdxById = new Map()
      const allAgendaIdxList = []

      function pushAgenda(task, connIdx) {
        const agIdx = nodes.length
        allAgendaIdxList.push(agIdx)
        const agLabel =
          (task.content || '아젠다').length > 10
            ? (task.content || '아젠다').slice(0, 10) + '…'
            : task.content || '아젠다'
        nodes.push({
          id: `agenda-${g.id || gi}-${task.id || agIdx}`,
          label: agLabel,
          type: 'agenda',
          groupIdx: gi,
          data: task,
          meetingId: mgNodeId,
          neo4jId: task.id || null,
        })
        // 아젠다는 '부서(관할)'에 연결한다. depts가 있으면 connIdx=부서 노드라 agenda→부서 관할이 그려진다.
        // (이전에 그리던 사람→아젠다 '담당' 엣지는 제거 — 담당자 정보는 노드 상세에서 확인)
        edges.push({ from: agIdx, to: connIdx, rel: '관할' })
        if (connIdx !== mgIdx) edges.push({ from: agIdx, to: mgIdx, rel: '관할' })
        agendaIdxById.set(String(task.id), agIdx)
        if (task.id != null) globalAgendaIdxMap.set(String(task.id), agIdx)
      }

      if (depts.length > 0) {
        depts.forEach(deptName => {
          const deptIdx = deptIdxMap.get(deptName)
          ;(tasksByDept.get(deptName) || []).forEach(task => pushAgenda(task, deptIdx))
        })
      } else {
        taskList.forEach(task => pushAgenda(task, mgIdx))
      }

      // ── Session + Minutes nodes ──────────────────────────────
      const sessions = [...(g.minutes || [])].sort((a, b) => {
        const da = a.date || a.scheduled_at || '',
          db = b.date || b.scheduled_at || ''
        if (da && db && da !== db) return da < db ? -1 : 1
        if (da && !db) return -1
        if (!da && db) return 1
        return String(a.id ?? '').localeCompare(String(b.id ?? ''), undefined, { numeric: true })
      })
      const sessionIdxByNeoId = new Map()
      const minutesFileIdxBySessionNeoId = new Map()
      let prevSessionIdx = -1
      sessions.forEach((m, mi) => {
        const sIdx = nodes.length
        nodes.push({
          id: `session-${g.id || gi}-${mi}`,
          label: m.session_title || `${mi + 1}차 회의`,
          type: 'session',
          groupIdx: gi,
          data: { ...m, participants: m.participants?.filter(p => p.userId != null) || [] },
          neo4jId: m.id || null,
        })
        edges.push({ from: sIdx, to: mgIdx, rel: '소속' })
        if (prevSessionIdx >= 0) edges.push({ from: prevSessionIdx, to: sIdx, rel: '후속' })
        prevSessionIdx = sIdx
        if (m.id != null) sessionIdxByNeoId.set(String(m.id), sIdx)

        // 회의록 노드는 '실제 저장된 회의록(minutes_pg_id 존재)'이 있을 때만 생성한다.
        // archive 쿼리가 OPTIONAL MATCH라 회의록 없는 세션도 한 행씩(minutes_pg_id=null) 반환하는데,
        // 이전엔 세션마다 무조건 minutes 노드를 만들어 회의록 없는 세션에도 'N차 회의록' 유령 노드가 떴다.
        if (m.minutes_pg_id != null) {
          const dIdx = nodes.length
          nodes.push({
            id: `minutes-${g.id || gi}-${mi}`,
            label: m.minutes_file_name || m.file_name || `${m.session_number || mi + 1}차 회의록`,
            type: 'minutes',
            groupIdx: gi,
            data: {
              title: m.doc_title || (m.session_title ? m.session_title + ' 회의록' : null),
              doc_type: '회의록',
              author: m.doc_author,
              created_at: m.doc_created_at || m.ended_at || m.date,
              file_name: m.minutes_file_name || m.file_name,
              session_neo_id: m.id,
              session_title: m.session_title,
              session_number: m.session_number,
              date: m.date,
              started_at: m.started_at,
              ended_at: m.ended_at,
              session_type: m.session_type,
              description: m.description,
              location: m.location,
              session_status: m.session_status,
              content_summary: m.content_summary,
              minutes_status: m.minutes_status,
              minutes_pg_id: m.minutes_pg_id,
              generated_at: m.generated_at,
            },
          })
          edges.push({ from: sIdx, to: dIdx, rel: '산출' })
          if (m.id != null) minutesFileIdxBySessionNeoId.set(String(m.id), dIdx)
        }
      })

      // ── Report nodes ─────────────────────────────────────────
      const visibleReports = (g.reports || []).filter(rp => rp.human_status !== 'rejected')
      visibleReports.forEach((rp, ri) => {
        const agendaIds = (rp.related_agenda_ids || []).map(String).filter(Boolean)
        let primaryFromIdx = mgIdx
        for (const aid of agendaIds) {
          if (agendaIdxById.has(aid)) {
            primaryFromIdx = agendaIdxById.get(aid)
            break
          }
        }
        const rIdx = nodes.length
        nodes.push({
          id: `report-${g.id || gi}-${ri}`,
          label: rp.file_name || '보고자료',
          type: 'report',
          groupIdx: gi,
          data: { ...rp },
          neo4jId: rp.id || null,
        })
        if (agendaIds.length > 0) {
          agendaIds.forEach(aid => {
            if (agendaIdxById.has(aid))
              edges.push({ from: rIdx, to: agendaIdxById.get(aid), rel: '도출' })
          })
        } else {
          edges.push({ from: rIdx, to: primaryFromIdx, rel: '첨부' })
        }
        // dept → report '첨부' (제출 부서가 그래프에 있으면 연결) — REL_MATRIX "dept→report": 첨부
        const _subDept = rp.submitter_department || rp.department || rp.dept || ''
        if (_subDept && deptIdxMap.has(_subDept)) {
          edges.push({ from: deptIdxMap.get(_subDept), to: rIdx, rel: '첨부' })
        }
      })

      // ── Lifecycle edges (아젠다→세션/회의록) ────────────────────
      ;(g.minutes_agendas || []).forEach(ma => {
        const mIdx =
          ma.session_id != null
            ? minutesFileIdxBySessionNeoId.get(String(ma.session_id))
            : undefined
        const agIdx = ma.agenda_id != null ? agendaIdxById.get(String(ma.agenda_id)) : undefined
        // 회의록 → 아젠다 방향 (canonical: minutes-[도출]->agenda)
        if (mIdx != null && agIdx != null) edges.push({ from: mIdx, to: agIdx, rel: '도출' })
      })
      ;(g.session_agendas || []).forEach(sa => {
        const sIdx =
          sa.session_id != null ? sessionIdxByNeoId.get(String(sa.session_id)) : undefined
        const agIdx = sa.agenda_id != null ? agendaIdxById.get(String(sa.agenda_id)) : undefined
        // 회의 생성 시 선택한 '논의 아젠다' → canonical: agenda-[논의]->session
        // (기존 '다룸'은 폐지된 관계명이라 그래프에 안 떴음)
        if (sIdx != null && agIdx != null) edges.push({ from: agIdx, to: sIdx, rel: '논의' })
      })
      ;(g.derivations || []).forEach(d => {
        const sIdx = d.session_id != null ? sessionIdxByNeoId.get(String(d.session_id)) : undefined
        const agIdx = d.agenda_id != null ? agendaIdxById.get(String(d.agenda_id)) : undefined
        if (sIdx != null && agIdx != null) edges.push({ from: agIdx, to: sIdx, rel: '도출' })
      })
    })

    // 멤버에 회사 정보가 전혀 없으면 단일 폴백 회사 노드로 모든 회의체를 묶는다
    if (companyIdxByName.size === 0) {
      const fallbackName = currentCompany?.value?.name || '조직'
      const coIdx = getCompanyIdx(fallbackName)
      nodes.forEach((n, i) => {
        if (n.type === 'Meetings') edges.push({ from: i, to: coIdx, rel: '포함' })
      })
    }

    // ── Sub-meeting edges ─────────────────────────────────────
    data.forEach(g => {
      if (!g.parent_id) return
      const rawId = g.id,
        rawPid = g.parent_id
      const subId = typeof rawId === 'string' && rawId.includes('-') ? rawId : `mg-${rawId}`
      const parId = typeof rawPid === 'string' && rawPid.includes('-') ? rawPid : `mg-${rawPid}`
      const subIdx = nodes.findIndex(n => n.id === subId)
      const parentIdx = nodes.findIndex(n => n.id === parId)
      if (subIdx >= 0 && parentIdx >= 0) edges.push({ from: subIdx, to: parentIdx, rel: '참여' })
    })

    // ── Cross-meeting related agenda edges ────────────────────
    ;(relatedAgendas?.value || []).forEach(pair => {
      const fromIdx = globalAgendaIdxMap.get(String(pair.from_id))
      const toIdx = globalAgendaIdxMap.get(String(pair.to_id))
      if (fromIdx != null && toIdx != null) edges.push({ from: fromIdx, to: toIdx, rel: '관련' })
    })

    // ── 수동 생성 관계 복원 (Neo4j에서 읽어온 자유 관계) ──────────
    // 구조 파생 엣지가 이미 같은 노드쌍을 연결했으면 건너뛴다(방향 무관 1쌍 1엣지).
    ;(manualRelations?.value || []).forEach(mr => {
      const fi = nodes.findIndex(n => n.id === mr.from_id || n.neo4jId === mr.from_id)
      const ti = nodes.findIndex(n => n.id === mr.to_id || n.neo4jId === mr.to_id)
      if (fi < 0 || ti < 0 || fi === ti) return
      const dup = edges.some(e => (e.from === fi && e.to === ti) || (e.from === ti && e.to === fi))
      if (!dup) edges.push({ from: fi, to: ti, rel: mr.rel, manual: true })
    })

    // ── Dedup nodes + edges ───────────────────────────────────
    const nodeIdMap = new Map()
    const dedupedNodes = []
    const idxRemap = new Array(nodes.length)
    nodes.forEach((n, i) => {
      if (nodeIdMap.has(n.id)) {
        idxRemap[i] = nodeIdMap.get(n.id)
      } else {
        const newIdx = dedupedNodes.length
        nodeIdMap.set(n.id, newIdx)
        dedupedNodes.push(n)
        idxRemap[i] = newIdx
      }
    })
    const edgeKeySet = new Set()
    const dedupedEdges = []
    edges.forEach(e => {
      const from = idxRemap[e.from],
        to = idxRemap[e.to]
      if (from === undefined || to === undefined || from === to) return
      const key = `${from}-${to}-${e.rel}`
      if (!edgeKeySet.has(key)) {
        edgeKeySet.add(key)
        dedupedEdges.push({ ...e, from, to })
      }
    })

    return { nodes: dedupedNodes, edges: dedupedEdges }
  }

  function computeUrgency(g) {
    if (g?.urgency) return g.urgency
    const tasks = g?.tasks || []
    const now = new Date()
    now.setHours(0, 0, 0, 0)
    let minDays = Infinity
    tasks.forEach(t => {
      if (t.status === 'done' || !t.due_date) return
      const due = new Date(t.due_date)
      due.setHours(0, 0, 0, 0)
      const days = Math.ceil((due - now) / 86400000)
      if (days >= 0 && days < minDays) minDays = days
    })
    if (minDays <= 1) return 'critical'
    if (minDays <= 3) return 'warning'
    return 'normal'
  }

  function getHubFill(g) {
    const u = computeUrgency(g)
    if (u === 'critical') return '#ef4444'
    if (u === 'warning') return '#f59e0b'
    return '#3b82f6'
  }

  return { buildGraphNodes, computeUrgency, getHubFill }
}
