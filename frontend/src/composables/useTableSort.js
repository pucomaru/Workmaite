import { ref, computed } from 'vue'

/**
 * AppTable 정렬 상태 + 정렬된 목록 — 단일 정의.
 * (기존: HomePage applySortStr / CompanyPage sortedMembers / MeetingsPage·ArchivePage 인라인 comparator 중복)
 *
 * @param {import('vue').Ref<Array>|import('vue').ComputedRef<Array>} listRef 정렬할 목록
 * @param {{ sortValues?: Record<string, (item:any)=>any> }} [options]
 *   sortValues: 특정 컬럼(key)의 비교값을 커스텀 추출한다. 예) 권한을 시스템>회사>일반 순으로
 *   정렬하려면 { role: m => RANK[m.role] }처럼 숫자 랭크를 반환한다.
 * @returns {{ sortKey, sortDir, handleSort, sorted }}
 *   handleSort는 AppTable의 @sort="handleSort"에 그대로 연결한다.
 *   양쪽 모두 숫자로 해석되는 값은 숫자 비교, 그 외는 대소문자 무시 문자열 비교.
 */
export function useTableSort(listRef, options = {}) {
  const sortValues = options.sortValues || {}
  const sortKey = ref(null)
  const sortDir = ref(null) // 'asc' | 'desc' | null

  function handleSort({ key, dir }) {
    sortKey.value = key
    sortDir.value = dir
  }

  const sorted = computed(() => {
    const list = [...listRef.value]
    if (!sortKey.value || !sortDir.value) return list
    const k = sortKey.value
    const d = sortDir.value === 'asc' ? 1 : -1
    const valueOf = sortValues[k]
    return list.sort((a, b) => {
      const av = ((valueOf ? valueOf(a) : a[k]) ?? '').toString().toLowerCase()
      const bv = ((valueOf ? valueOf(b) : b[k]) ?? '').toString().toLowerCase()
      if (av !== '' && bv !== '' && !isNaN(Number(av)) && !isNaN(Number(bv))) {
        return (Number(av) - Number(bv)) * d
      }
      return av < bv ? -d : av > bv ? d : 0
    })
  })

  return { sortKey, sortDir, handleSort, sorted }
}
