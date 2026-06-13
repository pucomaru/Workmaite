import { ref, computed } from 'vue'

/**
 * AppTable 정렬 상태 + 정렬된 목록 — 단일 정의.
 * (기존: HomePage applySortStr / CompanyPage sortedMembers / MeetingsPage·ArchivePage 인라인 comparator 중복)
 *
 * @param {import('vue').Ref<Array>|import('vue').ComputedRef<Array>} listRef 정렬할 목록
 * @returns {{ sortKey, sortDir, handleSort, sorted }}
 *   handleSort는 AppTable의 @sort="handleSort"에 그대로 연결한다.
 *   양쪽 모두 숫자로 해석되는 값은 숫자 비교, 그 외는 대소문자 무시 문자열 비교.
 */
export function useTableSort(listRef) {
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
    return list.sort((a, b) => {
      const av = (a[k] ?? '').toString().toLowerCase()
      const bv = (b[k] ?? '').toString().toLowerCase()
      if (av !== '' && bv !== '' && !isNaN(Number(av)) && !isNaN(Number(bv))) {
        return (Number(av) - Number(bv)) * d
      }
      return av < bv ? -d : av > bv ? d : 0
    })
  })

  return { sortKey, sortDir, handleSort, sorted }
}
