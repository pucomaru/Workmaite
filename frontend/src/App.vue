<script setup>
import { useThemeStore } from './stores/theme'
import { useActivityRefresh } from './composables/useActivityRefresh'

// 앱 전체 JWT 자동 갱신: 사용자 인터랙션 감지 시 만료 임박 토큰 갱신
useActivityRefresh()
// Initialize theme store to apply class on startup
useThemeStore()
</script>

<template>
  <RouterView />
</template>
