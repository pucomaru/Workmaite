import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import NodeIcon from '../src/components/NodeIcon.vue'

describe('NodeIcon', () => {
  it('노드 타입(dept)의 아이콘을 렌더한다', () => {
    const w = mount(NodeIcon, { props: { type: 'dept' } })
    expect(w.find('svg').exists()).toBe(true)
    expect(w.find('svg').html()).toContain('M17 21v-2a4 4 0 00-4-4H5')
  })

  it('회의체(Meetings) 노드 아이콘도 렌더한다', () => {
    const w = mount(NodeIcon, { props: { type: 'Meetings' } })
    // 허브 아이콘은 원(circle)들을 포함한다
    expect(w.find('svg').findAll('circle').length).toBeGreaterThan(0)
  })

  it('알 수 없는 타입은 person으로 폴백한다', () => {
    const w = mount(NodeIcon, { props: { type: '존재하지않는타입' } })
    expect(w.find('svg').html()).toContain('M20 21v-2') // person path
  })

  it('type 미지정 시 기본값(person)으로 렌더한다', () => {
    const w = mount(NodeIcon)
    expect(w.find('svg').html()).toContain('M20 21v-2')
  })

  it('size prop을 하위 AppIcon에 전달한다', () => {
    const w = mount(NodeIcon, { props: { type: 'agenda', size: 22 } })
    expect(w.find('svg').attributes('width')).toBe('22')
  })
})
