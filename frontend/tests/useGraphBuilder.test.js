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

  it('아젠다는 관할 엣지로 연결된다 (담당 엣지는 만들지 않음)', () => {
    const { buildGraphNodes } = makeBuilder(oneMeeting)
    const { edges } = buildGraphNodes()
    expect(edges.some(e => e.rel === '관할')).toBe(true)
    expect(edges.some(e => e.rel === '담당')).toBe(false)
  })

  it('빈 회의체 목록도 회사·본인 노드는 그린다 (빈 화면 방지)', () => {
    const { buildGraphNodes } = makeBuilder([])
    const { nodes } = buildGraphNodes()
    const types = nodes.map(n => n.type)
    expect(types).toContain('company')
    expect(types).toContain('person')
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
        tasks: [
          { status: 'done', due_date: new Date().toISOString() },
          { status: 'todo' },
        ],
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
