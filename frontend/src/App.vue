<script setup>
import { useThemeStore } from './stores/theme'
import { useActivityRefresh } from './composables/useActivityRefresh'
import AppToast from './components/AppToast.vue'
import AppConfirmModal from './components/AppConfirmModal.vue'
import AppNetworkBanner from './components/AppNetworkBanner.vue'

// 앱 전체 JWT 자동 갱신: 사용자 인터랙션 감지 시 만료 임박 토큰 갱신
useActivityRefresh()
// Initialize theme store to apply class on startup
useThemeStore()
</script>

<template>
  <RouterView />
  <!-- 전역 피드백 레이어 (PLAN Phase 2): 토스트 · 확인 다이얼로그 · 네트워크 단절 배너 -->
  <AppToast />
  <AppConfirmModal />
  <AppNetworkBanner />
</template>
