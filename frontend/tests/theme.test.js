import { describe, it, expect, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useThemeStore } from '../src/stores/theme'

const html = () => document.documentElement

beforeEach(() => {
  setActivePinia(createPinia())
  localStorage.clear()
  html().className = ''
})

describe('useThemeStore', () => {
  it('localStorage가 없으면 야간 모드가 기본값', () => {
    const store = useThemeStore()
    expect(store.nightMode).toBe(true)
    // 생성 시 watch(immediate)로 html 클래스가 설정된다
    expect(html().classList.contains('night-mode')).toBe(true)
    expect(html().classList.contains('day-mode-global')).toBe(false)
  })

  it("localStorage 'false'면 주간 모드로 시작한다", () => {
    localStorage.setItem('nightMode', 'false')
    const store = useThemeStore()
    expect(store.nightMode).toBe(false)
    expect(html().classList.contains('day-mode-global')).toBe(true)
    expect(html().classList.contains('night-mode')).toBe(false)
  })

  it('toggle은 모드를 뒤집고 html 클래스를 교체한다', async () => {
    const store = useThemeStore()
    store.toggle() // 야간 → 주간
    await Promise.resolve()
    expect(store.nightMode).toBe(false)
    expect(html().classList.contains('day-mode-global')).toBe(true)
    expect(html().classList.contains('night-mode')).toBe(false)

    store.toggle() // 주간 → 야간
    await Promise.resolve()
    expect(store.nightMode).toBe(true)
    expect(html().classList.contains('night-mode')).toBe(true)
    expect(html().classList.contains('day-mode-global')).toBe(false)
  })

  it('toggle은 localStorage에 선택을 저장한다', async () => {
    const store = useThemeStore()
    store.toggle()
    await Promise.resolve()
    expect(localStorage.getItem('nightMode')).toBe('false')
    store.toggle()
    await Promise.resolve()
    expect(localStorage.getItem('nightMode')).toBe('true')
  })
})
