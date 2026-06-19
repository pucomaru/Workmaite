<script setup>
// 범용 아이콘 — UI/노드 공용. 정의는 icons/uiIcons.js SSOT.
// - ICON_IMAGES[name] 이 있으면 <img>(자체 색/그라데이션 로고 등) 로 렌더.
// - 아니면 ICON_PATHS[name] 을 currentColor stroke 라인 아이콘으로 렌더.
import { computed } from 'vue'
import { ICON_IMAGES, ICON_PATHS } from '../icons/uiIcons'

const props = defineProps({
  name: { type: String, required: true },
  size: { type: [Number, String], default: 14 },
  color: { type: String, default: 'currentColor' },
})

const imgSrc = computed(() => ICON_IMAGES[props.name] || null)
const inner = computed(() => ICON_PATHS[props.name] || '')
</script>

<template>
  <img
    v-if="imgSrc"
    :src="imgSrc"
    :width="size"
    :height="size"
    :alt="name"
    class="app-icon-img"
    draggable="false"
  />
  <svg
    v-else
    :width="size"
    :height="size"
    fill="none"
    :stroke="color"
    stroke-width="2"
    stroke-linecap="round"
    stroke-linejoin="round"
    viewBox="0 0 24 24"
    v-html="inner"
  />
</template>

<style scoped>
.app-icon-img {
  display: inline-block;
  vertical-align: middle;
  object-fit: contain;
  /* 박스 border 대신 모양을 따라가는 살짝 외곽선(드롭섀도) — 라이트/다크 헤더 양쪽에서 입체감 */
  filter: drop-shadow(0 0 0.1px rgba(255, 255, 255, 0.5));
  width: 18px;
  height: 18px;
}
</style>
