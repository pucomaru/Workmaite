import { describe, it, expect } from 'vitest'
import { ref, nextTick } from 'vue'
import { usePagination } from '../src/composables/usePagination'

const items = n => Array.from({ length: n }, (_, i) => i + 1)

describe('usePagination', () => {
  it('페이지 크기만큼 슬라이스한다', () => {
    const list = ref(items(25))
    const { page, paged } = usePagination(list, 10)
    expect(paged.value).toHaveLength(10)
    page.value = 3
    expect(paged.value).toEqual([21, 22, 23, 24, 25])
  })

  it('빈 행 수: 마지막 페이지에서 부족분을 채운다', () => {
    const list = ref(items(25))
    const { page, fillerCount } = usePagination(list, 10)
    expect(fillerCount.value).toBe(0)
    page.value = 3
    expect(fillerCount.value).toBe(5)
  })

  it('기본값: 목록이 비면 빈 행을 만들지 않는다', () => {
    const { fillerCount } = usePagination(ref([]), 10)
    expect(fillerCount.value).toBe(0)
  })

  it('fillEmpty: 목록이 비어도 높이 유지를 위해 빈 행을 채운다', () => {
    const { fillerCount } = usePagination(ref([]), 10, { fillEmpty: true })
    expect(fillerCount.value).toBe(10)
  })

  it('목록이 줄어 현재 페이지가 범위를 벗어나면 마지막 페이지로 보정한다', async () => {
    const list = ref(items(30))
    const { page, paged } = usePagination(list, 10)
    page.value = 3
    list.value = items(11)
    await nextTick()
    expect(page.value).toBe(2)
    expect(paged.value).toEqual([11])
  })
})
