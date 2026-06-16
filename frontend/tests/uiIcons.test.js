import { describe, it, expect } from 'vitest'
import { UI_ICON_PATHS, ICON_IMAGES, ICON_PATHS } from '../src/icons/uiIcons'
import { NODE_ICON_PATHS } from '../src/graph/nodeIcons'

describe('ICON_PATHS (공용 레지스트리)', () => {
  it('노드 타입 아이콘을 모두 재사용해 포함한다', () => {
    for (const key of Object.keys(NODE_ICON_PATHS)) {
      expect(ICON_PATHS[key]).toBe(NODE_ICON_PATHS[key])
    }
  })

  it('UI 전용 아이콘(home)도 포함한다', () => {
    expect(ICON_PATHS.home).toBe(UI_ICON_PATHS.home)
    expect(ICON_PATHS.home).toBeTruthy()
  })

  it('이미지 아이콘(archive)은 path 레지스트리에 없다 (ICON_IMAGES로 분리)', () => {
    expect(ICON_PATHS.archive).toBeUndefined()
  })
})

describe('ICON_IMAGES', () => {
  it('archive는 favicon 정적 자산을 가리킨다', () => {
    expect(ICON_IMAGES.archive).toBe('/favicon.svg')
  })

  it('path 레지스트리와 이미지 레지스트리는 키가 겹치지 않는다', () => {
    const overlap = Object.keys(ICON_IMAGES).filter(k => k in ICON_PATHS)
    expect(overlap).toEqual([])
  })
})
