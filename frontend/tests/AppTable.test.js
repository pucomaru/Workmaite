import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import AppTable from '../src/components/AppTable.vue'

const columns = [
  { label: '이름', sortKey: 'name' },
  { label: '메모' }, // 정렬 불가 컬럼 (sortKey 없음)
]

const mountTable = (extra = {}) => mount(AppTable, { props: { columns, ...extra } })

describe('AppTable', () => {
  it('컬럼 라벨을 헤더에 그린다', () => {
    const w = mountTable()
    const ths = w.findAll('th').map(t => t.text())
    expect(ths.join(' ')).toContain('이름')
    expect(ths.join(' ')).toContain('메모')
  })

  it('sortKey가 있는 컬럼만 sortable-th 클래스를 갖는다', () => {
    const w = mountTable()
    const ths = w.findAll('th')
    expect(ths[0].classes()).toContain('sortable-th')
    expect(ths[1].classes()).not.toContain('sortable-th')
  })

  it('정렬 안 된 컬럼 클릭 → asc emit', async () => {
    const w = mountTable()
    await w.findAll('th')[0].trigger('click')
    expect(w.emitted('sort')[0]).toEqual([{ key: 'name', dir: 'asc' }])
  })

  it('현재 asc인 컬럼 재클릭 → desc emit', async () => {
    const w = mountTable({ sortKey: 'name', sortDir: 'asc' })
    await w.findAll('th')[0].trigger('click')
    expect(w.emitted('sort')[0]).toEqual([{ key: 'name', dir: 'desc' }])
  })

  it('현재 desc인 컬럼 재클릭 → 정렬 해제(null) emit', async () => {
    const w = mountTable({ sortKey: 'name', sortDir: 'desc' })
    await w.findAll('th')[0].trigger('click')
    expect(w.emitted('sort')[0]).toEqual([{ key: null, dir: null }])
  })

  it('sortKey 없는 컬럼 클릭은 emit하지 않는다', async () => {
    const w = mountTable()
    await w.findAll('th')[1].trigger('click')
    expect(w.emitted('sort')).toBeUndefined()
  })

  it('tbody 슬롯 내용을 렌더한다', () => {
    const w = mount(AppTable, {
      props: { columns },
      slots: { default: '<tr class="row-x"><td>a</td><td>b</td></tr>' },
    })
    expect(w.find('tbody .row-x').exists()).toBe(true)
  })
})
