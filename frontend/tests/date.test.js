import { describe, it, expect } from 'vitest'
import { fmtISO, getDday, formatDateShort, formatDateTimeFull, formatDateTimeShort, formatDateLong } from '../src/utils/date'

describe('fmtISO', () => {
  it('로컬 기준 YYYY-MM-DD로 포맷한다', () => {
    expect(fmtISO(new Date(2026, 5, 13))).toBe('2026-06-13')
    expect(fmtISO(new Date(2026, 0, 1))).toBe('2026-01-01')
  })
})

describe('getDday', () => {
  it('null/빈 값이면 null', () => {
    expect(getDday(null)).toBeNull()
    expect(getDday('')).toBeNull()
  })
  it('미래 날짜는 양수, 과거 날짜는 음수', () => {
    const future = new Date(Date.now() + 3 * 86400000)
    const past = new Date(Date.now() - 3 * 86400000)
    expect(getDday(future)).toBeGreaterThan(0)
    expect(getDday(past)).toBeLessThan(0)
  })
})

describe('formatDate*', () => {
  it('빈 값 폴백을 지킨다', () => {
    expect(formatDateShort('')).toBe('')
    expect(formatDateTimeFull(null)).toBe('-')
    expect(formatDateTimeShort(null)).toBe('-')
    expect(formatDateTimeShort(null, '일정 미정')).toBe('일정 미정')
    expect(formatDateLong(null)).toBe('-')
  })
  it('ko-KR 포맷으로 날짜를 표시한다', () => {
    expect(formatDateShort('2026-06-13')).toContain('월')
    expect(formatDateLong('2026-06-13')).toContain('2026년')
  })
  it('formatDateLong은 YYYY-MM-DD 문자열을 UTC 밀림 없이 그 날짜로 해석한다', () => {
    expect(formatDateLong('2026-06-13')).toContain('13일')
  })
})
