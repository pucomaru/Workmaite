import { describe, it, expect } from 'vitest'
import { NODE_ICON_PATHS, DEFAULT_ICON, nodeIconSvg } from '../src/graph/nodeIcons'

const NODE_TYPES = [
  'dept',
  'company',
  'agenda',
  'session',
  'minutes',
  'report',
  'person',
  'Meetings',
]

describe('NODE_ICON_PATHS', () => {
  it('그래프에서 쓰는 8개 노드 타입을 모두 정의한다', () => {
    for (const t of NODE_TYPES) {
      expect(NODE_ICON_PATHS[t], `${t} 아이콘 누락`).toBeTruthy()
      expect(typeof NODE_ICON_PATHS[t]).toBe('string')
    }
  })

  it('DEFAULT_ICON(person)은 정의된 타입을 가리킨다', () => {
    expect(NODE_ICON_PATHS[DEFAULT_ICON]).toBeTruthy()
  })

  it('Meetings 허브 아이콘의 연결선은 원 중심(12,12)을 통과하지 않는다', () => {
    // 회귀 방지: 과거 연결선이 원 내부를 가로질러 보이던 버그
    expect(NODE_ICON_PATHS.Meetings).not.toContain('M12 12')
  })
})

describe('nodeIconSvg', () => {
  it('알 수 없는 타입은 null을 반환한다', () => {
    expect(nodeIconSvg('unknown')).toBeNull()
    expect(nodeIconSvg('')).toBeNull()
  })

  it('브라우저 래스터화에 필요한 xmlns·viewBox를 포함한다', () => {
    const svg = nodeIconSvg('person')
    expect(svg).toContain('xmlns="http://www.w3.org/2000/svg"')
    expect(svg).toContain('viewBox="0 0 24 24"')
    expect(svg).toContain('fill="none"')
  })

  it('기본 stroke는 흰색·두께 2', () => {
    const svg = nodeIconSvg('agenda')
    expect(svg).toContain('stroke="#ffffff"')
    expect(svg).toContain('stroke-width="2"')
  })

  it('stroke 색·두께를 인자로 덮어쓸 수 있다 (currentColor 등)', () => {
    const svg = nodeIconSvg('dept', 'currentColor', 1.5)
    expect(svg).toContain('stroke="currentColor"')
    expect(svg).toContain('stroke-width="1.5"')
  })

  it('해당 타입의 inner 마크업을 그대로 감싼다', () => {
    const svg = nodeIconSvg('company')
    expect(svg).toContain(NODE_ICON_PATHS.company)
    expect(svg.startsWith('<svg')).toBe(true)
    expect(svg.endsWith('</svg>')).toBe(true)
  })
})
