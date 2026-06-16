import { describe, it, expect, beforeEach, vi } from 'vitest'
import { toast, toasts, dismissToast } from '../src/composables/useToast'

beforeEach(() => {
  toasts.value = [] // 모듈 전역 상태 초기화
  vi.useRealTimers()
})

describe('useToast', () => {
  it('메시지를 큐에 추가한다 (기본 type=info)', () => {
    toast('안녕')
    expect(toasts.value).toHaveLength(1)
    expect(toasts.value[0]).toMatchObject({ message: '안녕', type: 'info' })
  })

  it('같은 메시지는 중복 추가하지 않는다', () => {
    toast('같은 메시지')
    toast('같은 메시지')
    expect(toasts.value).toHaveLength(1)
  })

  it('success/error/info 헬퍼가 type을 지정한다', () => {
    toast.success('성공')
    toast.error('실패')
    toast.info('안내')
    const types = toasts.value.map(t => t.type)
    expect(types).toEqual(['success', 'error', 'info'])
  })

  it('dismissToast(id)는 해당 토스트만 제거한다', () => {
    const id1 = toast('하나')
    toast('둘')
    dismissToast(id1)
    expect(toasts.value.map(t => t.message)).toEqual(['둘'])
  })

  it('duration 경과 후 자동으로 사라진다', () => {
    vi.useFakeTimers()
    toast('자동소멸', 'info', { duration: 1000 })
    expect(toasts.value).toHaveLength(1)
    vi.advanceTimersByTime(1000)
    expect(toasts.value).toHaveLength(0)
  })

  it('duration=0이면 자동 소멸 타이머를 걸지 않는다', () => {
    vi.useFakeTimers()
    toast('영구', 'info', { duration: 0 })
    vi.advanceTimersByTime(100000)
    expect(toasts.value).toHaveLength(1)
  })

  it('각 토스트는 고유 id를 받는다', () => {
    const id1 = toast('a')
    const id2 = toast('b')
    expect(id1).not.toBe(id2)
  })
})
