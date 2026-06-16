import { describe, it, expect } from 'vitest'
import { ref } from 'vue'
import { useGraphBuilder } from '../src/composables/useGraphBuilder'

function makeBuilder(meetings, extra = {}) {
  return useGraphBuilder({
    meetings: ref(meetings),
    currentCompany: ref(extra.company ?? { name: 'Acme' }),
    currentPerson: ref(extra.person ?? { id: 1, name: 'Kim', department: 'Dev', company: 'Acme' }),
    neo4jDepts: ref(extra.depts ?? []),
    relatedAgendas: ref(extra.related ?? []),
    manualRelations: ref(extra.manual ?? []),
  })
}

const oneMeeting = [
  {
    id: 'mg-1',
    title: '반도체 위원회',
    status: 'active',
    members: [{ userId: 1, userName: 'Kim', department: 'Dev', role: 'admin', company: 'Acme' }],
    tasks: [{ id: 10, content: '패키징 도입', assignee_dept: 'Dev', status: 'todo' }],
    minutes: [],
    reports: [],
  },
]

describe('useGraphBuilder.buildGraphNodes', () => {
  it('회의체·부서·사람·아젠다·회사 노드를 생성한다', () => {
    const { buildGraphNodes } = makeBuilder(oneMeeting)
    const { nodes } = buildGraphNodes()
    const types = nodes.map(n => n.type)
    expect(types).toContain('Meetings')
    expect(types).toContain('dept')
    expect(types).toContain('person')
    expect(types).toContain('agenda')
    expect(types).toContain('company')
  })

  it('회의체 노드는 제목을 라벨로 갖는다', () => {
    const { buildGraphNodes } = makeBuilder(oneMeeting)
    const mg = buildGraphNodes().nodes.find(n => n.type === 'Meetings')
    expect(mg.label).toBe('반도체 위원회')
  })

  it('아젠다는 담당부서·추출 엣지로 연결된다 (관할 폐지, 담당 엣지는 만들지 않음)', () => {
    const { buildGraphNodes } = makeBuilder(oneMeeting)
    const { edges } = buildGraphNodes()
    // 안건→담당부서 (Dev 부서가 있으므로), 회의체→안건 추출
    expect(edges.some(e => e.rel === '담당부서')).toBe(true)
    expect(edges.some(e => e.rel === '추출')).toBe(true)
    // 폐지된 '관할', 만들지 않는 '담당'
    expect(edges.some(e => e.rel === '관할')).toBe(false)
    expect(edges.some(e => e.rel === '담당')).toBe(false)
  })

  it('session_agendas로 agenda-[:논의]->session 엣지를 그린다 (논의 아젠다 반영)', () => {
    const m = [
      {
        id: 'mg-1',
        title: 'M',
        status: 'active',
        members: [
          { userId: 1, userName: 'Kim', department: 'Dev', role: 'admin', company: 'Acme' },
        ],
        tasks: [{ id: 'agenda-5', content: '안건A', assignee_dept: 'Dev', status: 'ongoing' }],
        minutes: [{ id: 'session-9', session_title: '1차', date: '2025-01-01' }],
        reports: [],
        session_agendas: [{ session_id: 'session-9', agenda_id: 'agenda-5' }],
      },
    ]
    const { buildGraphNodes } = makeBuilder(m)
    const { nodes, edges } = buildGraphNodes()
    const agIdx = nodes.findIndex(n => n.type === 'agenda' && n.neo4jId === 'agenda-5')
    const sIdx = nodes.findIndex(n => n.type === 'session' && n.neo4jId === 'session-9')
    expect(agIdx).toBeGreaterThanOrEqual(0)
    expect(sIdx).toBeGreaterThanOrEqual(0)
    expect(edges.some(e => e.rel === '논의' && e.from === agIdx && e.to === sIdx)).toBe(true)
  })

  it('session→Meetings(소속) 엣지는 시각화하지 않는다 (DB에는 보존)', () => {
    const withSession = [
      {
        id: 'mg-2',
        title: 'S',
        status: 'active',
        members: [
          { userId: 1, userName: 'Kim', department: 'Dev', role: 'admin', company: 'Acme' },
        ],
        tasks: [],
        minutes: [{ id: 's1', session_title: '1차', date: '2025-01-01' }],
        reports: [],
      },
    ]
    const { buildGraphNodes } = makeBuilder(withSession)
    const { nodes, edges } = buildGraphNodes()
    const sIdx = nodes.findIndex(n => n.type === 'session')
    const mgIdx = nodes.findIndex(n => n.type === 'Meetings')
    expect(sIdx).toBeGreaterThanOrEqual(0)
    // 세션↔회의체 직접 엣지가 없어야 함 (양방향 모두)
    expect(
      edges.some(e => (e.from === sIdx && e.to === mgIdx) || (e.from === mgIdx && e.to === sIdx)),
    ).toBe(false)
  })

  it('같은 부서명이라도 회사가 다르면 부서 노드가 분리되고 각자 자기 회사에 연결된다 (사람→부서→회사)', () => {
    const meetingMixedCo = [
      {
        id: 'mg-9',
        title: 'M',
        status: 'active',
        members: [
          { userId: 1, userName: 'A', department: 'Dev', role: 'admin', company: 'Acme' },
          { userId: 2, userName: 'B', department: 'Dev', role: 'member', company: 'Other Co' },
        ],
        tasks: [],
        minutes: [],
        reports: [],
      },
    ]
    const { buildGraphNodes } = makeBuilder(meetingMixedCo)
    const { nodes, edges } = buildGraphNodes()
    // 두 회사 노드 모두 생성
    const acme = nodes.findIndex(n => n.type === 'company' && n.label === 'Acme')
    const otherCo = nodes.findIndex(n => n.type === 'company' && n.label === 'Other Co')
    expect(acme).toBeGreaterThanOrEqual(0)
    expect(otherCo).toBeGreaterThanOrEqual(0)
    // 'Dev' 부서 노드가 회사별로 2개 분리됨
    const devDepts = nodes.filter(n => n.type === 'dept' && n.label === 'Dev')
    expect(devDepts.length).toBe(2)
    // 직접 person→company(소속회사) 엣지는 만들지 않는다 (부서 경유)
    expect(edges.some(e => e.rel === '소속회사')).toBe(false)
    // 각 부서 노드가 자기 회사로 소속 연결됨
    expect(edges.some(e => e.rel === '소속' && e.to === acme)).toBe(true)
    expect(edges.some(e => e.rel === '소속' && e.to === otherCo)).toBe(true)
  })

  it('사람은 부서를 거쳐 회사에 연결된다 (사람→부서, 부서→회사). 직접 소속회사 엣지는 없음', () => {
    const { buildGraphNodes } = makeBuilder(oneMeeting) // 멤버 1명(Kim/Dev/Acme)
    const { nodes, edges } = buildGraphNodes()
    const personIdx = nodes.findIndex(n => n.type === 'person')
    const deptIdx = nodes.findIndex(n => n.type === 'dept')
    const acmeIdx = nodes.findIndex(n => n.type === 'company' && n.label === 'Acme')
    // 사람 → 부서 (소속)
    expect(edges.some(e => e.rel === '소속' && e.from === personIdx && e.to === deptIdx)).toBe(true)
    // 부서 → 회사 (소속)
    expect(edges.some(e => e.rel === '소속' && e.from === deptIdx && e.to === acmeIdx)).toBe(true)
    // 사람→회사 직접 엣지(소속회사)는 없음
    expect(edges.some(e => e.rel === '소속회사')).toBe(false)
  })

  it('빈 회의체 목록도 회사·본인 노드는 그린다 (빈 화면 방지)', () => {
    const { buildGraphNodes } = makeBuilder([])
    const { nodes } = buildGraphNodes()
    const types = nodes.map(n => n.type)
    expect(types).toContain('company')
    expect(types).toContain('person')
  })

  it('회의체 없는 본인은 ambient currentCompany가 아니라 자기 company에 연결된다', () => {
    // person.company(S1112) ≠ currentCompany(SK AX) — 본인 회사가 우선돼야 한다.
    const { buildGraphNodes } = makeBuilder([], {
      company: { name: 'SK AX' },
      person: { id: 4, name: '김도', department: '개발팀331', company: 'S1112' },
    })
    const { nodes, edges } = buildGraphNodes()
    // 회사 노드는 본인 회사(S1112)로 그려진다 (SK AX 아님)
    const co = nodes.find(n => n.type === 'company')
    expect(co.label).toBe('S1112')
    expect(nodes.some(n => n.type === 'company' && n.label === 'SK AX')).toBe(false)
    // 본인 → 부서 → 회사 경로로 S1112에 도달 (SK AX와 직접 연결 없음)
    const personIdx = nodes.findIndex(n => n.type === 'person')
    const deptIdx = nodes.findIndex(n => n.type === 'dept')
    const coIdx = nodes.findIndex(n => n.type === 'company')
    expect(edges.some(e => e.from === personIdx && e.to === deptIdx && e.rel === '소속')).toBe(true)
    expect(edges.some(e => e.from === deptIdx && e.to === coIdx && e.rel === '소속')).toBe(true)
  })

  it('노드와 엣지를 중복 제거한다 (같은 id 노드 / 같은 쌍·관계 엣지)', () => {
    const { buildGraphNodes } = makeBuilder(oneMeeting)
    const { nodes, edges } = buildGraphNodes()
    const nodeIds = nodes.map(n => n.id)
    expect(new Set(nodeIds).size).toBe(nodeIds.length)
    const edgeKeys = edges.map(e => `${e.from}-${e.to}-${e.rel}`)
    expect(new Set(edgeKeys).size).toBe(edgeKeys.length)
    // 엣지의 from/to 인덱스는 유효 범위
    for (const e of edges) {
      expect(e.from).toBeGreaterThanOrEqual(0)
      expect(e.from).toBeLessThan(nodes.length)
      expect(e.to).toBeLessThan(nodes.length)
    }
  })
})

describe('useGraphBuilder.computeUrgency', () => {
  const { computeUrgency } = makeBuilder([])

  it('명시적 urgency가 있으면 그대로 반환한다', () => {
    expect(computeUrgency({ urgency: 'critical' })).toBe('critical')
  })

  it('미완료 아젠다의 마감 임박도에 따라 등급을 매긴다', () => {
    const inDays = n => {
      const d = new Date()
      d.setDate(d.getDate() + n)
      return d.toISOString()
    }
    expect(computeUrgency({ tasks: [{ status: 'todo', due_date: inDays(0) }] })).toBe('critical')
    expect(computeUrgency({ tasks: [{ status: 'todo', due_date: inDays(2) }] })).toBe('warning')
    expect(computeUrgency({ tasks: [{ status: 'todo', due_date: inDays(10) }] })).toBe('normal')
  })

  it('완료된(done) 아젠다와 마감일 없는 항목은 무시한다', () => {
    expect(
      computeUrgency({
        tasks: [{ status: 'done', due_date: new Date().toISOString() }, { status: 'todo' }],
      }),
    ).toBe('normal')
  })
})

describe('useGraphBuilder.getHubFill', () => {
  const { getHubFill } = makeBuilder([])

  it('긴급도에 따라 색을 반환한다', () => {
    expect(getHubFill({ urgency: 'critical' })).toBe('#ef4444')
    expect(getHubFill({ urgency: 'warning' })).toBe('#f59e0b')
    expect(getHubFill({ urgency: 'normal' })).toBe('#3b82f6')
  })
})
