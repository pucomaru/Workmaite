import { describe, it, expect } from 'vitest'
import { AVATAR_COLORS, avatarColor, initials } from '../src/utils/avatar'

describe('avatarColor', () => {
  it('같은 이름은 항상 같은 색', () => {
    expect(avatarColor('홍길동')).toBe(avatarColor('홍길동'))
  })
  it('팔레트 안의 색만 반환한다', () => {
    for (const name of ['홍길동', 'Alice', '김민혁', '', null]) {
      expect(AVATAR_COLORS).toContain(avatarColor(name))
    }
  })
})

describe('initials', () => {
  it('첫 글자를 반환한다', () => {
    expect(initials('홍길동')).toBe('홍')
    expect(initials('Alice')).toBe('A')
  })
  it('빈 값이면 ?를 반환한다', () => {
    expect(initials('')).toBe('?')
    expect(initials(null)).toBe('?')
  })
})
