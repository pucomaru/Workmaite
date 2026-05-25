<script setup>
import { useThemeStore } from './stores/theme'
// Initialize theme store to apply class on startup
useThemeStore()
</script>

<template>
  <RouterView />
</template>
