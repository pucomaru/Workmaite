import { defineStore } from 'pinia'
import { ref, watch } from 'vue'

export const useThemeStore = defineStore('theme', () => {
  const nightMode = ref(localStorage.getItem('nightMode') !== 'false')

  watch(nightMode, (val) => {
    localStorage.setItem('nightMode', val)
    document.documentElement.classList.toggle('night-mode', val)
    document.documentElement.classList.toggle('day-mode-global', !val)
  }, { immediate: true })

  function toggle() {
    nightMode.value = !nightMode.value
  }

  return { nightMode, toggle }
})
