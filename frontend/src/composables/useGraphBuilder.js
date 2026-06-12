export function useGraphBuilder({ meetingGroups, currentPerson, authStore, currentCompany, neo4jDepts, meetingsStore, relatedAgendas }) {
  function buildGraphNodes() {
    const nodes = [], edges = []
    const data = meetingGroups.value

    const deptIdByName = new Map(neo4jDepts.value.map(d => [d.name, d.id]))
    const globalAgendaIdxMap = new Map()

    // ── Organization node ──────────────────────────────────────
    const companyNodeIdx = nodes.length
    const _companyData = currentCompany?.value
    nodes.push({ id: 'company-node', label: _companyData?.name || '조직', type: 'company', data: _companyData })

    if (!data.length) return { nodes, edges }

    data.forEach((g, gi) => {
      const rawId = g.id || gi
      const mgNodeId = (typeof rawId === 'string' && rawId.includes('-')) ? rawId : `mg-${rawId}`

      // ── MeetingGroup node ────────────────────────────────────
      const mgIdx = nodes.length
      nodes.push({
        id: mgNodeId, label: g.title || `회의체${gi + 1}`, type: 'Meetings',
        data: g, groupIdx: gi, neo4jId: g.id || null,
        ended: g.status === 'ended',
      })
      // meetingGroup -[포함]→ company (작은→큰)
      edges.push({ from: mgIdx, to: companyNodeIdx, rel: '포함' })

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
          id: `dept-${deptIdByName.get(deptName) || deptName}`, label: deptName, type: 'dept',
          members: membersByDept.get(deptName), groupIdx: gi, meetingGroupId: mgNodeId,
          neo4jId: deptIdByName.get(deptName) || null,
        })
        edges.push({ from: deptIdx, to: mgIdx, rel: '참여' })
        edges.push({ from: deptIdx, to: companyNodeIdx, rel: '소속' })

        ;(membersByDept.get(deptName) || []).forEach(mb => {
          const pIdx = nodes.length
          const pName = mb.userName || mb.name || '?'
          const pKey = mb.userId || mb.email || pName
          personIdxByKey.set(pKey, pIdx)
          personIdxByKey.set(pName, pIdx)
          nodes.push({
            id: `person-${mb.userId || mb.email || pName}`, label: pName, type: 'person',
            groupIdx: gi, meetingGroupId: mgNodeId, data: mb, neo4jId: mb.userId || null,
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
        const agLabel = (task.content || '아젠다').length > 10 ? (task.content || '아젠다').slice(0, 10) + '…' : (task.content || '아젠다')
        nodes.push({
          id: `agenda-${g.id || gi}-${task.id || agIdx}`, label: agLabel, type: 'agenda',
          groupIdx: gi, data: task, meetingGroupId: mgNodeId, neo4jId: task.id || null,
        })
        edges.push({ from: agIdx, to: connIdx, rel: '관할' })
        if (connIdx !== mgIdx) edges.push({ from: agIdx, to: mgIdx, rel: '관할' })
        const assigneeNames = task.assignee_names?.length ? task.assignee_names : (task.assignee_name ? [task.assignee_name] : [])
        if (assigneeNames.length > 0) {
          for (const aName of assigneeNames) {
            const pIdx = personIdxByKey.get(aName) ?? -1
            if (pIdx >= 0) edges.push({ from: pIdx, to: agIdx, rel: '담당' })
          }
        } else {
          const assigneeDept = task.assignee_dept || depts[0]
          const fallbackMembers = membersByDept.get(assigneeDept) || []
          if (fallbackMembers.length > 0) {
            const fb = fallbackMembers[0]
            const fbKey = fb.userId || fb.email || fb.userName || fb.name || 0
            const pIdx = personIdxByKey.get(String(fbKey)) ?? personIdxByKey.get(fb.userName || fb.name) ?? -1
            if (pIdx >= 0) edges.push({ from: pIdx, to: agIdx, rel: '담당' })
          }
        }
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
        const da = a.date || a.scheduled_at || '', db = b.date || b.scheduled_at || ''
        if (da && db && da !== db) return da < db ? -1 : 1
        if (da && !db) return -1; if (!da && db) return 1
        return String(a.id ?? '').localeCompare(String(b.id ?? ''), undefined, { numeric: true })
      })
      const sessionIdxByNeoId = new Map()
      const minutesFileIdxBySessionNeoId = new Map()
      let prevSessionIdx = -1
      sessions.forEach((m, mi) => {
        const sIdx = nodes.length
        nodes.push({
          id: `session-${g.id || gi}-${mi}`,
          label: m.session_title || `${mi + 1}차 회의`, type: 'session',
          groupIdx: gi, data: { ...m, participants: m.participants?.filter(p => p.userId != null) || [] }, neo4jId: m.id || null,
        })
        edges.push({ from: sIdx, to: mgIdx, rel: '개최' })
        if (prevSessionIdx >= 0) edges.push({ from: prevSessionIdx, to: sIdx, rel: '후속' })
        prevSessionIdx = sIdx
        if (m.id != null) sessionIdxByNeoId.set(String(m.id), sIdx)

        const dIdx = nodes.length
        nodes.push({
          id: `minutes-${g.id || gi}-${mi}`,
          label: m.minutes_file_name || m.file_name || `${m.session_number || mi + 1}차 회의록`,
          type: 'minutes', groupIdx: gi,
          data: {
            title: m.doc_title || (m.session_title ? m.session_title + ' 회의록' : null),
            doc_type: '회의록', author: m.doc_author,
            created_at: m.doc_created_at || m.ended_at || m.date,
            file_name: m.minutes_file_name || m.file_name, session_neo_id: m.id,
            session_title: m.session_title, session_number: m.session_number,
            date: m.date, started_at: m.started_at, ended_at: m.ended_at,
            session_type: m.session_type, description: m.description, location: m.location,
            session_status: m.session_status, content_summary: m.content_summary,
            minutes_status: m.minutes_status, minutes_pg_id: m.minutes_pg_id, generated_at: m.generated_at,
          },
        })
        edges.push({ from: sIdx, to: dIdx, rel: '산출' })
        if (m.id != null) minutesFileIdxBySessionNeoId.set(String(m.id), dIdx)
      })

      // ── Report nodes ─────────────────────────────────────────
      const visibleReports = (g.reports || []).filter(rp => rp.human_status !== 'rejected')
      visibleReports.forEach((rp, ri) => {
        const agendaIds = (rp.related_agenda_ids || []).map(String).filter(Boolean)
        let primaryFromIdx = allAgendaIdxList.length > 0 ? allAgendaIdxList[0] : mgIdx
        for (const aid of agendaIds) {
          if (agendaIdxById.has(aid)) { primaryFromIdx = agendaIdxById.get(aid); break }
        }
        const rIdx = nodes.length
        nodes.push({
          id: `report-${g.id || gi}-${ri}`, label: rp.file_name || '보고자료', type: 'report',
          groupIdx: gi, data: { ...rp }, neo4jId: rp.id || null,
        })
        if (agendaIds.length > 0) {
          agendaIds.forEach(aid => {
            if (agendaIdxById.has(aid)) edges.push({ from: rIdx, to: agendaIdxById.get(aid), rel: '첨부' })
          })
        } else {
          edges.push({ from: rIdx, to: primaryFromIdx, rel: '첨부' })
        }
      })

      // ── Lifecycle edges (아젠다→세션/회의록) ────────────────────
      ;(g.minutes_agendas || []).forEach(ma => {
        const mIdx  = ma.session_id != null ? minutesFileIdxBySessionNeoId.get(String(ma.session_id)) : undefined
        const agIdx = ma.agenda_id  != null ? agendaIdxById.get(String(ma.agenda_id)) : undefined
        if (mIdx != null && agIdx != null) edges.push({ from: agIdx, to: mIdx, rel: '도출' })
      })
      ;(g.session_agendas || []).forEach(sa => {
        const sIdx  = sa.session_id != null ? sessionIdxByNeoId.get(String(sa.session_id)) : undefined
        const agIdx = sa.agenda_id  != null ? agendaIdxById.get(String(sa.agenda_id)) : undefined
        if (sIdx != null && agIdx != null) edges.push({ from: agIdx, to: sIdx, rel: '다룸' })
      })
      ;(g.derivations || []).forEach(d => {
        const sIdx  = d.session_id != null ? sessionIdxByNeoId.get(String(d.session_id)) : undefined
        const agIdx = d.agenda_id  != null ? agendaIdxById.get(String(d.agenda_id)) : undefined
        if (sIdx != null && agIdx != null) edges.push({ from: agIdx, to: sIdx, rel: '도출' })
      })
    })

    // ── Sub-meeting edges ─────────────────────────────────────
    data.forEach(g => {
      if (!g.parent_id) return
      const rawId = g.id, rawPid = g.parent_id
      const subId = (typeof rawId === 'string' && rawId.includes('-')) ? rawId : `mg-${rawId}`
      const parId = (typeof rawPid === 'string' && rawPid.includes('-')) ? rawPid : `mg-${rawPid}`
      const subIdx = nodes.findIndex(n => n.id === subId)
      const parentIdx = nodes.findIndex(n => n.id === parId)
      if (subIdx >= 0 && parentIdx >= 0) edges.push({ from: subIdx, to: parentIdx, rel: '참여' })
    })

    // ── Cross-meeting related agenda edges ────────────────────
    ;(relatedAgendas?.value || []).forEach(pair => {
      const fromIdx = globalAgendaIdxMap.get(String(pair.from_id))
      const toIdx   = globalAgendaIdxMap.get(String(pair.to_id))
      if (fromIdx != null && toIdx != null) edges.push({ from: fromIdx, to: toIdx, rel: '관련' })
    })

    // ── Dedup nodes + edges ───────────────────────────────────
    const nodeIdMap = new Map()
    const dedupedNodes = []
    const idxRemap = new Array(nodes.length)
    nodes.forEach((n, i) => {
      if (nodeIdMap.has(n.id)) { idxRemap[i] = nodeIdMap.get(n.id) }
      else {
        const newIdx = dedupedNodes.length
        nodeIdMap.set(n.id, newIdx)
        dedupedNodes.push(n)
        idxRemap[i] = newIdx
      }
    })
    const edgeKeySet = new Set()
    const dedupedEdges = []
    edges.forEach(e => {
      const from = idxRemap[e.from], to = idxRemap[e.to]
      if (from === undefined || to === undefined || from === to) return
      const key = `${from}-${to}-${e.rel}`
      if (!edgeKeySet.has(key)) { edgeKeySet.add(key); dedupedEdges.push({ ...e, from, to }) }
    })

    return { nodes: dedupedNodes, edges: dedupedEdges }
  }

  function computeUrgency(g) {
    if (g?.urgency) return g.urgency
    const tasks = g?.tasks || []
    const now = new Date(); now.setHours(0, 0, 0, 0)
    let minDays = Infinity
    tasks.forEach(t => {
      if (t.status === 'done' || !t.due_date) return
      const due = new Date(t.due_date); due.setHours(0, 0, 0, 0)
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
