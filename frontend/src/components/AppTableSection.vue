<template>
  <div class="lv-inner lv-inner-fill">
    <div class="lv-header">
      <div class="lv-filter-wrap"><slot name="filters" /></div>
      <div class="lv-header-right"><slot name="header-right" /></div>
    </div>
    <div class="table-wrap">
      <slot />
    </div>
    <AppPagination
      v-if="showPagination"
      :modelValue="page"
      :totalItems="totalItems"
      :pageSize="pageSize"
      :dark="dark"
      @update:modelValue="emit('update:page', $event)"
    />
  </div>
</template>

<script setup>
import AppPagination from './AppPagination.vue'

/**
 * 목록 페이지 공통 본문 레이아웃 (회사·회의체 탭).
 * lv-header(좌: 필터 슬롯 / 중앙: 페이지네이션 / 우: 제목·건수 슬롯) + table-wrap(내부 스크롤).
 * 레이아웃 클래스(lv-inner/lv-header/table-wrap)는 style.css 전역 단일 정의를 사용한다.
 *
 * 슬롯: #filters(좌측 필터), #header-right(제목·건수), 기본 슬롯(로딩/빈 상태/AppTable)
 */
defineProps({
  page: { type: Number, default: 1 },
  totalItems: { type: Number, default: 0 },
  pageSize: { type: Number, default: 30 },
  dark: { type: Boolean, default: false },
  showPagination: { type: Boolean, default: true },
})

const emit = defineEmits(['update:page'])
</script>
