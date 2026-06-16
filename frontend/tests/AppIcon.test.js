import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import AppIcon from '../src/components/AppIcon.vue'
import { NODE_ICON_PATHS } from '../src/graph/nodeIcons'

describe('AppIcon', () => {
  it('라인 아이콘(name=person)은 <svg>로 렌더하고 <img>는 없다', () => {
    const w = mount(AppIcon, { props: { name: 'person' } })
    expect(w.find('svg').exists()).toBe(true)
    expect(w.find('img').exists()).toBe(false)
  })

  it('해당 이름의 path 마크업을 svg 안에 그린다', () => {
    const w = mount(AppIcon, { props: { name: 'person' } })
    // person path 시작부 — v-html로 삽입된 내용 확인
    expect(w.find('svg').html()).toContain('M20 21v-2')
  })

  it('이미지 아이콘(name=archive)은 <img>로 렌더하고 src는 favicon', () => {
    const w = mount(AppIcon, { props: { name: 'archive' } })
    const img = w.find('img')
    expect(img.exists()).toBe(true)
    expect(img.attributes('src')).toBe('/favicon.svg')
    expect(img.attributes('alt')).toBe('archive')
    expect(w.find('svg').exists()).toBe(false)
  })

  it('UI 전용 아이콘(home)도 svg로 렌더된다', () => {
    const w = mount(AppIcon, { props: { name: 'home' } })
    expect(w.find('svg').exists()).toBe(true)
    expect(w.find('svg').html()).toContain('M3 12l2-2')
  })

  it('알 수 없는 이름은 빈 svg(내용 없음)로 렌더한다 — 깨지지 않음', () => {
    const w = mount(AppIcon, { props: { name: 'nope-not-real' } })
    expect(w.find('svg').exists()).toBe(true)
    expect(w.find('svg').findAll('path').length).toBe(0)
  })

  it('size prop이 width/height에 반영된다', () => {
    const w = mount(AppIcon, { props: { name: 'agenda', size: 20 } })
    const svg = w.find('svg')
    expect(svg.attributes('width')).toBe('20')
    expect(svg.attributes('height')).toBe('20')
  })

  it('svg는 currentColor stroke·viewBox 24를 갖는다 (테마 색 상속)', () => {
    const w = mount(AppIcon, { props: { name: 'company' } })
    const svg = w.find('svg')
    expect(svg.attributes('stroke')).toBe('currentColor')
    expect(svg.attributes('fill')).toBe('none')
    expect(svg.attributes('viewBox')).toBe('0 0 24 24')
    // path 정의는 SSOT와 동일해야 한다
    expect(svg.html()).toContain('M9 22v-4h6v4')
    expect(NODE_ICON_PATHS.company).toContain('M9 22v-4h6v4')
  })
})
