import { ref, computed, watch } from 'vue'

/**
 * 테이블 페이지네이션 — 단일 정의.
 * (기존: HomePage×2 / CompanyPage / MeetingsPage에 page ref + slice + filler + clamp watch 중복)
 *
 * @param {import('vue').Ref<Array>|import('vue').ComputedRef<Array>} listRef 페이징할 목록
 * @param {number} pageSize 페이지당 행 수
 * @param {{ fillEmpty?: boolean }} opts fillEmpty: 목록이 비어도 빈 행으로 높이 유지 (홈 탭)
 * @returns {{ page, paged, fillerCount, pageSize }}
 *   page는 AppPagination의 v-model에, fillerCount는 filler-row v-for에 연결한다.
 */
export function usePagination(listRef, pageSize, { fillEmpty = false } = {}) {
  const page = ref(1)

  const paged = computed(() =>
    listRef.value.slice((page.value - 1) * pageSize, page.value * pageSize),
  )

  const fillerCount = computed(() =>
    paged.value.length || fillEmpty ? pageSize - paged.value.length : 0,
  )

  // 검색·필터로 목록이 줄어 현재 페이지가 범위를 벗어나면 마지막 페이지로 보정
  watch(
    () => listRef.value.length,
    len => {
      const tp = Math.max(1, Math.ceil(len / pageSize))
      if (page.value > tp) page.value = tp
    },
  )

  return { page, paged, fillerCount, pageSize }
}
