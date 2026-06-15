import { describe, it, expect } from 'vitest'
import { ref } from 'vue'
import { useTableSort } from '../src/composables/useTableSort'

const rows = () =>
  ref([
    { name: '나', count: 10 },
    { name: '가', count: 2 },
    { name: '다', count: 1 },
  ])

describe('useTableSort', () => {
  it('정렬 키가 없으면 원본 순서를 유지한다', () => {
    const { sorted } = useTableSort(rows())
    expect(sorted.value.map(r => r.name)).toEqual(['나', '가', '다'])
  })

  it('문자열 오름차순/내림차순 정렬', () => {
    const list = rows()
    const { handleSort, sorted } = useTableSort(list)
    handleSort({ key: 'name', dir: 'asc' })
    expect(sorted.value.map(r => r.name)).toEqual(['가', '나', '다'])
    handleSort({ key: 'name', dir: 'desc' })
    expect(sorted.value.map(r => r.name)).toEqual(['다', '나', '가'])
  })

  it('숫자 값은 숫자로 비교한다 (10이 2보다 뒤)', () => {
    const { handleSort, sorted } = useTableSort(rows())
    handleSort({ key: 'count', dir: 'asc' })
    expect(sorted.value.map(r => r.count)).toEqual([1, 2, 10])
  })

  it('정렬 해제(null) 시 원본 순서로 복귀한다', () => {
    const { handleSort, sorted } = useTableSort(rows())
    handleSort({ key: 'name', dir: 'asc' })
    handleSort({ key: null, dir: null })
    expect(sorted.value.map(r => r.name)).toEqual(['나', '가', '다'])
  })

  it('원본 배열을 변형하지 않는다', () => {
    const list = rows()
    const { handleSort, sorted } = useTableSort(list)
    handleSort({ key: 'name', dir: 'asc' })
    void sorted.value
    expect(list.value.map(r => r.name)).toEqual(['나', '가', '다'])
  })
})
