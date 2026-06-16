import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import AppPagination from '../src/components/AppPagination.vue'

const make = props =>
  mount(AppPagination, { props: { modelValue: 1, totalItems: 0, pageSize: 10, ...props } })

describe('AppPagination', () => {
  it('totalItems/pageSize로 페이지 수만큼 번호 버튼을 그린다', () => {
    const w = make({ totalItems: 25, pageSize: 10 }) // 3페이지
    const nums = w.findAll('.page-num').map(b => b.text())
    expect(nums).toEqual(['1', '2', '3'])
  })

  it('항목이 없어도 최소 1페이지를 보장한다', () => {
    const w = make({ totalItems: 0 })
    expect(w.findAll('.page-num').map(b => b.text())).toEqual(['1'])
  })

  it('번호 클릭 시 update:modelValue를 emit한다', async () => {
    const w = make({ totalItems: 30, pageSize: 10, modelValue: 1 })
    await w.findAll('.page-num')[2].trigger('click') // 3페이지
    expect(w.emitted('update:modelValue')[0]).toEqual([3])
  })

  it('현재 페이지를 다시 클릭하면 emit하지 않는다', async () => {
    const w = make({ totalItems: 30, pageSize: 10, modelValue: 2 })
    await w.findAll('.page-num')[1].trigger('click') // 현재(2)
    expect(w.emitted('update:modelValue')).toBeUndefined()
  })

  it('첫 페이지에서 이전 버튼은 비활성, 마지막에서 다음 버튼은 비활성', () => {
    const first = make({ totalItems: 30, pageSize: 10, modelValue: 1 })
    const btns1 = first.findAll('.page-btn')
    expect(btns1[0].attributes('disabled')).toBeDefined() // prev
    expect(btns1[btns1.length - 1].attributes('disabled')).toBeUndefined() // next

    const last = make({ totalItems: 30, pageSize: 10, modelValue: 3 })
    const btns2 = last.findAll('.page-btn')
    expect(btns2[0].attributes('disabled')).toBeUndefined()
    expect(btns2[btns2.length - 1].attributes('disabled')).toBeDefined()
  })

  it('이전/다음 버튼은 인접 페이지로 이동을 emit한다', async () => {
    const w = make({ totalItems: 50, pageSize: 10, modelValue: 3 })
    const btns = w.findAll('.page-btn')
    await btns[0].trigger('click') // prev → 2
    await btns[btns.length - 1].trigger('click') // next → 4
    const events = w.emitted('update:modelValue')
    expect(events[0]).toEqual([2])
    expect(events[1]).toEqual([4])
  })

  it('maxVisible 윈도우만큼만 현재 페이지 주변 번호를 보여준다', () => {
    const w = make({ totalItems: 100, pageSize: 10, modelValue: 5, maxVisible: 5 })
    expect(w.findAll('.page-num').map(b => b.text())).toEqual(['3', '4', '5', '6', '7'])
  })
})
