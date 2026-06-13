import { ref } from 'vue'

/**
 * 전역 토스트 — 네이티브 alert() 대체.
 * 사용: toast.success('저장되었습니다') / toast.error('저장 실패') / toast.info('안내')
 * 표시는 App.vue에 마운트된 <AppToast />가 담당한다.
 */
let _id = 0
export const toasts = ref([]) // [{ id, message, type }]

export function toast(message, type = 'info', { duration = 3200 } = {}) {
  const id = ++_id
  toasts.value.push({ id, message, type })
  if (duration > 0) setTimeout(() => dismissToast(id), duration)
  return id
}

export function dismissToast(id) {
  toasts.value = toasts.value.filter(t => t.id !== id)
}

toast.success = (message, opts) => toast(message, 'success', opts)
toast.error = (message, opts) => toast(message, 'error', { duration: 4500, ...opts })
toast.info = (message, opts) => toast(message, 'info', opts)
