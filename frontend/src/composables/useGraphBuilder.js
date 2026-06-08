export function useGraphBuilder({ meetingGroups, currentPerson, authStore, currentOrg, neo4jDepts, meetingsStore }) {
  function buildGraphNodes() {
    const nodes = [], edges = []
    const data = meetingGroups.value

    // ── 반경 정의 (Neo4j 그래프 온톨로지 계층 반영) ─────────────
    // Organization(중심) → MeetingGroup → Department/Person → Agenda/Session → Minutes(file)
    const R = { meeting_group: 240, dept: 400, person: 340, agenda: 580, session: 750, file: 920 }
    const Y = { org: 0, meeting_group: 0, dept: -15, person: -50, agenda: 20, session: 30, file: 12 }
    const TWO_PI = Math.PI * 2

    // ── Organization 노드 (그래프 중심) ────────────────────────────
    const orgNodeIdx = nodes.length
    nodes.push({ id: 'org-node', label: currentOrg.value?.name || '조직', type: 'org', x: 0, y: Y.org, z: 0, data: currentOrg.value })

    // 소속 회의체 없으면 조직 노드만 표시
    if (!data.length) return { nodes, edges }

    const mgCount = data.length
    const sectorWidth = TWO_PI / Math.max(mgCount, 1)

    // dept name → neo4j id 룩업 맵
    const deptIdByName = new Map(neo4jDepts.value.map(d => [d.name, d.id]))

    data.forEach((g, gi) => {
      const ang = (gi / Math.max(mgCount, 1)) * TWO_PI
      // g.id가 Neo4j 전체 ID("mg-001" 등)이면 그대로 사용, 정수이면 prefix 추가
      const rawId = g.id || gi
      const mgNodeId = (typeof rawId === 'string' && rawId.includes('-')) ? rawId : `mg-${rawId}`
      const neo4jId = (typeof rawId === 'string' && rawId.includes('-')) ? rawId : `mg-${rawId}`

      // ── MeetingGroup 노드 ─────────────────────────────────────
      const mgIdx = nodes.length
      nodes.push({
        id: mgNodeId, label: g.title || `회의체${gi + 1}`, type: 'meeting_group',
        x: Math.cos(ang) * R.meeting_group, y: Y.meeting_group, z: Math.sin(ang) * R.meeting_group,
        data: g, groupIdx: gi, neo4jId,
      })
      // meetingGroup -[포함]→ org-node (조직 소속)
      edges.push({ from: mgIdx, to: orgNodeIdx, rel: '포함' })

      // ── Department 노드: 회의에 PARTICIPATES_IN ───────────────
      const membersByDept = new Map()
      // personKey(id) → node push 시점 index (O(1) 담당자 탐색용)
      const personIdxByKey = new Map()
      ;(g.members || []).forEach(mb => {
        const d = mb.department || mb.dept || '미지정'
        if (!membersByDept.has(d)) membersByDept.set(d, [])
        membersByDept.get(d).push(mb)
      })
      const depts = [...membersByDept.keys()]
      const dCount = depts.length
      const deptFan = dCount > 1 ? Math.min(sectorWidth * 0.42, 0.55) / (dCount - 1) : 0
      const deptIdxMap = new Map()

      depts.forEach((deptName, di) => {
        const dAng = ang + (di - (dCount - 1) / 2) * deptFan
        const deptIdx = nodes.length
        deptIdxMap.set(deptName, deptIdx)
        nodes.push({
          id: `dept-${deptIdByName.get(deptName) || deptName}`, label: deptName, type: 'dept',
          x: Math.cos(dAng) * R.dept, y: Y.dept, z: Math.sin(dAng) * R.dept,
          members: membersByDept.get(deptName), groupIdx: gi, meetingGroupId: mgNodeId,
          neo4jId: deptIdByName.get(deptName) || null,
        })
        // dept -[참여]→ meetingGroup
        edges.push({ from: deptIdx, to: mgIdx, rel: '참여' })
        // dept -[소속]→ org-node
        edges.push({ from: deptIdx, to: orgNodeIdx, rel: '소속' })

        // ── Person 노드 (로그인 사용자 포함, 모든 구성원 표시) ─
        const deptMembers = membersByDept.get(deptName) || []
        const pCount = deptMembers.length
        deptMembers.forEach((mb, pi) => {
          const pFan = pCount > 1 ? Math.min(0.3, sectorWidth * 0.15) / (pCount - 1) : 0
          const pAng = dAng + (pi - (pCount - 1) / 2) * pFan
          const pIdx = nodes.length
          const pName = mb.userName || mb.name || '?'
          const pKey = mb.userId || mb.email || pName
          personIdxByKey.set(pKey, pIdx)
          personIdxByKey.set(pName, pIdx)  // 이름으로도 탐색 가능하도록
          nodes.push({
            id: `person-${mb.userId || mb.email || pName}`, label: pName, type: 'person',
            x: Math.cos(pAng) * R.person, y: Y.person, z: Math.sin(pAng) * R.person,
            groupIdx: gi, meetingGroupId: mgNodeId, data: mb,
            neo4jId: mb.userId || null,
          })
          // person -[BELONGS_TO]→ dept
          edges.push({ from: pIdx, to: deptIdx, rel: '소속' })
          // person -[ADMIN_OF or MEMBER_OF]→ meetingGroup
          const memberRel = mb.role === 'admin' ? '간사' : '구성원'
          edges.push({ from: pIdx, to: mgIdx, rel: memberRel })
        })
      })

      // ── Agenda 노드: OWNED_BY meetingGroup ───────────────────
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

      const agendaIdxByTodoId = new Map()
      const sessionIdxByNeoId = new Map()
      const minutesFileIdxBySessionNeoId = new Map()
      const allAgendaIdxList = []

      depts.forEach(deptName => {
        const deptIdx = deptIdxMap.get(deptName)
        const deptNode = nodes[deptIdx]
        const dAng = deptNode ? Math.atan2(deptNode.z, deptNode.x) : ang
        const deptTasks = tasksByDept.get(deptName) || []
        const tCount = deptTasks.length
        const tFan = tCount > 1 ? Math.min(0.22, 0.14) : 0
        deptTasks.forEach((task, ti) => {
          const tAng = dAng + (ti - (tCount - 1) / 2) * tFan
          const agIdx = nodes.length
          allAgendaIdxList.push(agIdx)
          const agLabel = (task.content || `아젠다 ${ti + 1}`).slice(0, 12) + ((task.content || '').length > 12 ? '…' : '')
          nodes.push({
            id: `agenda-${g.id || gi}-${task.id || ti}`, label: agLabel, type: 'agenda',
            x: Math.cos(tAng) * R.agenda, y: Y.agenda, z: Math.sin(tAng) * R.agenda,
            groupIdx: gi, data: task, meetingGroupId: mgNodeId,
            neo4jId: task.id || null,
          })
          // agenda -[OWNED_BY]→ meetingGroup
          edges.push({ from: agIdx, to: mgIdx, rel: '관할' })
          // person -[담당]→ agenda: Neo4j assignee_names 우선, 없으면 부서 첫 구성원
          const assigneeNames = task.assignee_names?.length ? task.assignee_names : (task.assignee_name ? [task.assignee_name] : [])
          const assigneeDept = task.assignee_dept || deptName
          if (assigneeNames.length > 0) {
            for (const aName of assigneeNames) {
              const pIdx = personIdxByKey.get(aName) ?? -1
              if (pIdx >= 0) edges.push({ from: pIdx, to: agIdx, rel: '담당' })
            }
          } else {
            const fallbackMembers = membersByDept.get(assigneeDept) || []
            if (fallbackMembers.length > 0) {
              const fb = fallbackMembers[0]
              const fbKey = fb.userId || fb.email || fb.userName || fb.name || 0
              const personIdx = personIdxByKey.get(String(fbKey)) ?? personIdxByKey.get(fb.userName || fb.name) ?? -1
              if (personIdx >= 0) edges.push({ from: personIdx, to: agIdx, rel: '담당' })
            }
          }
          agendaIdxByTodoId.set(String(task.id), agIdx)
        })
      })

      // 부서 없을 때 아젠다를 회의체에 직접 연결
      if (depts.length === 0 && taskList.length > 0) {
        taskList.forEach((task, ti) => {
          const tAng = ang + (ti - (taskList.length - 1) / 2) * 0.2
          const agIdx = nodes.length
          allAgendaIdxList.push(agIdx)
          const agLabel = (task.content || `아젠다 ${ti + 1}`).slice(0, 12) + ((task.content || '').length > 12 ? '…' : '')
          nodes.push({
            id: `agenda-${g.id || gi}-${task.id || ti}`, label: agLabel, type: 'agenda',
            x: Math.cos(tAng) * R.agenda, y: Y.agenda, z: Math.sin(tAng) * R.agenda,
            groupIdx: gi, data: task, meetingGroupId: mgNodeId
          })
          edges.push({ from: mgIdx, to: agIdx, rel: '관할' })
          agendaIdxByTodoId.set(String(task.id), agIdx)
        })
      }

      // ── Session 노드: HELD_BY meetingGroup ────────────────────
      // 같은 회의체의 세션은 시간순(1차→2차→3차)으로 정렬해 '후속' 체인으로 연결
      const sessions = [...(g.minutes || [])].sort((a, b) => {
        const da = a.date || a.scheduled_at || '', db = b.date || b.scheduled_at || ''
        if (da && db && da !== db) return da < db ? -1 : 1
        if (da && !db) return -1
        if (!da && db) return 1
        return String(a.id ?? '').localeCompare(String(b.id ?? ''), undefined, { numeric: true })
      })
      const sTotal = sessions.length
      let prevSessionIdx = -1
      sessions.forEach((m, mi) => {
        // 회의체 각도 기준으로 세션을 부채꼴 배치 (과제와 무관)
        const sFan = sTotal > 1 ? Math.min(sectorWidth * 0.4, 0.5) / (sTotal - 1) : 0
        const sAng = ang + (mi - (sTotal - 1) / 2) * sFan
        const sIdx = nodes.length
        nodes.push({
          id: `session-${g.id || gi}-${mi}`,
          label: m.session_title || `${m.session_number || mi + 1}차 회의`, type: 'session',
          x: Math.cos(sAng) * R.session, y: Y.session, z: Math.sin(sAng) * R.session,
          groupIdx: gi, data: { ...m, participants: g.members || [] },
          neo4jId: m.id || null,
        })
        // session -[개최]→ meetingGroup (실제 Neo4j 관계)
        edges.push({ from: sIdx, to: mgIdx, rel: '개최' })
        // 직전 회차 → 이번 회차: 시간순 '후속' 체인 (1차→2차→3차)
        if (prevSessionIdx >= 0) edges.push({ from: prevSessionIdx, to: sIdx, rel: '후속' })
        prevSessionIdx = sIdx
        if (m.id != null) sessionIdxByNeoId.set(String(m.id), sIdx)
        // 세션→과제 연결은 Neo4j에 실제 관계가 없으므로 생성하지 않음

        // ── Document 노드 (회의록): session -[PRODUCED]→ document
        const dIdx = nodes.length
        nodes.push({
          id: `file-min-${g.id || gi}-${mi}`,
          label: m.session_title || `${m.session_number || mi + 1}차 회의록`, type: 'file', fileType: '회의록',
          x: Math.cos(sAng) * R.file, y: Y.file, z: Math.sin(sAng) * R.file, groupIdx: gi,
          data: {
            title: m.doc_title || (m.session_title ? m.session_title + ' 회의록' : null),
            doc_type: m.doc_type || '회의록',
            author: m.doc_author,
            created_at: m.doc_created_at || m.ended_at || m.date,
            file_name: m.file_name,
          }
        })
        edges.push({ from: sIdx, to: dIdx, rel: '산출' })
        if (m.id != null) minutesFileIdxBySessionNeoId.set(String(m.id), dIdx)
      })

      // ── Document 노드 (보고자료): ATTACHED_TO meetingGroup ───
      ;(g.reports || []).forEach((rp, ri) => {
        const relTodoId = String(rp.related_todo_id || '')
        let fromIdx = allAgendaIdxList.length > 0 ? allAgendaIdxList[0] : mgIdx
        if (relTodoId && agendaIdxByTodoId.has(relTodoId)) fromIdx = agendaIdxByTodoId.get(relTodoId)
        const fromNode = nodes[fromIdx]
        const bAng = fromNode ? Math.atan2(fromNode.z, fromNode.x) : ang
        const rAng = bAng + (ri - ((g.reports || []).length - 1) / 2) * 0.12
        const rIdx = nodes.length
        nodes.push({
          id: `file-rep-${g.id || gi}-${ri}`, label: rp.file_name || '보고자료', type: 'file', fileType: '보고자료',
          x: Math.cos(rAng) * R.file, y: Y.file - 15, z: Math.sin(rAng) * R.file, groupIdx: gi,
          data: { ...rp, created_at: rp.submitted_at },
          neo4jId: rp.id || null,
        })
        // document → agenda 연결 (과제 지정 시 해당 agenda, 아니면 첫 agenda, 없으면 meetingGroup)
        const docToIdx = (relTodoId && agendaIdxByTodoId.has(relTodoId))
          ? agendaIdxByTodoId.get(relTodoId)
          : (allAgendaIdxList.length > 0 ? allAgendaIdxList[0] : mgIdx)
        edges.push({ from: rIdx, to: docToIdx, rel: '첨부' })
      })

      // ── Minutes→Agenda 도출 연결 (회의→회의록→안건 생명주기) ──
      ;(g.minutes_agendas || []).forEach(ma => {
        const srcIdx = ma.session_id != null ? minutesFileIdxBySessionNeoId.get(String(ma.session_id)) : undefined
        const dstIdx = ma.agenda_id  != null ? agendaIdxByTodoId.get(String(ma.agenda_id)) : undefined
        if (srcIdx != null && dstIdx != null) edges.push({ from: srcIdx, to: dstIdx, rel: '도출' })
      })

      // ── Session→Agenda 다룸 연결 (회의가 직접 담당하는 안건) ──
      ;(g.session_agendas || []).forEach(sa => {
        const sIdx  = sa.session_id != null ? sessionIdxByNeoId.get(String(sa.session_id)) : undefined
        const agIdx = sa.agenda_id  != null ? agendaIdxByTodoId.get(String(sa.agenda_id)) : undefined
        if (sIdx != null && agIdx != null) edges.push({ from: sIdx, to: agIdx, rel: '다룸' })
      })

      // ── 이월(carry-forward): 다음 회차 -[도출]→ 미해결 안건 (안건→회의 폐곡선) ──
      ;(g.derivations || []).forEach(d => {
        const sIdx  = d.session_id != null ? sessionIdxByNeoId.get(String(d.session_id)) : undefined
        const agIdx = d.agenda_id  != null ? agendaIdxByTodoId.get(String(d.agenda_id)) : undefined
        if (sIdx != null && agIdx != null) edges.push({ from: sIdx, to: agIdx, rel: '도출' })
      })
    })

    // ── 소위원회 (MeetingGroup -[PARTICIPATES_IN]→ MeetingGroup) ─
    data.forEach(g => {
      if (!g.parent_id) return
      const rawId = g.id, rawPid = g.parent_id
      const subId = (typeof rawId === 'string' && rawId.includes('-')) ? rawId : `mg-${rawId}`
      const parId = (typeof rawPid === 'string' && rawPid.includes('-')) ? rawPid : `mg-${rawPid}`
      const subIdx = nodes.findIndex(n => n.id === subId)
      const parentIdx = nodes.findIndex(n => n.id === parId)
      if (subIdx >= 0 && parentIdx >= 0)
        edges.push({ from: subIdx, to: parentIdx, rel: '참여' })
    })

    // ── 중복 노드 제거 (같은 id가 여러 번 push된 경우) ─────────
    const nodeIdMap = new Map()   // id → dedupedNodes 인덱스
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

    // 엣지 인덱스 재매핑 + 중복 엣지 / 자기참조 제거
    const edgeKeySet = new Set()
    const dedupedEdges = []
    edges.forEach(e => {
      const from = idxRemap[e.from]
      const to   = idxRemap[e.to]
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
    const now = new Date(); now.setHours(0,0,0,0)
    let minDays = Infinity
    tasks.forEach(t => {
      if (t.status === 'done') return
      if (!t.due_date) return
      const due = new Date(t.due_date); due.setHours(0,0,0,0)
      const days = Math.ceil((due - now) / 86400000)
      if (days >= 0 && days < minDays) minDays = days
    })
    if (minDays <= 1) return 'critical'   // 하루 이하: 빨간색
    if (minDays <= 3) return 'warning'    // 3일 이하: 노란색
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
