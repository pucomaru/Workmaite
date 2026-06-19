<script setup>
// 노드 유형별 아이콘 — 범용 AppIcon 에 위임. 알 수 없는 타입은 person 으로 폴백한다.
// path 정의는 graph/nodeIcons.js SSOT, 렌더는 AppIcon(공용) 한 곳으로 일원화.
import { computed } from 'vue'
import { NODE_ICON_PATHS, DEFAULT_ICON } from '../graph/nodeIcons'
import AppIcon from './AppIcon.vue'

const props = defineProps({
  type: { type: String, default: DEFAULT_ICON },
  size: { type: [Number, String], default: 14 },
})

const name = computed(() => (NODE_ICON_PATHS[props.type] ? props.type : DEFAULT_ICON))
</script>

<template>
  <AppIcon :name="name" :size="size" />
</template>
