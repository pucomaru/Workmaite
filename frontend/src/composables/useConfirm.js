import { ref } from 'vue'

/**
 * Promise 기반 확인/입력 다이얼로그 (PLAN Phase 2) — 네이티브 confirm()/prompt() 대체.
 * 사용:
 *   if (!(await confirmDialog('삭제하시겠습니까?', { danger: true }))) return
 *   const reason = await promptDialog('사유를 입력하세요 (선택)')  // 취소 시 null
 * 표시는 App.vue에 마운트된 <AppConfirmModal />이 담당한다.
 */
export const confirmState = ref(null)
// { mode: 'confirm'|'prompt', message, okText, cancelText, danger, placeholder, resolve }

export function confirmDialog(message, { okText = '확인', cancelText = '취소', danger = false } = {}) {
  return new Promise(resolve => {
    confirmState.value = { mode: 'confirm', message, okText, cancelText, danger, resolve }
  })
}

export function promptDialog(message, { okText = '확인', cancelText = '취소', placeholder = '' } = {}) {
  return new Promise(resolve => {
    confirmState.value = { mode: 'prompt', message, okText, cancelText, placeholder, danger: false, resolve }
  })
}

/** 내부용 — AppConfirmModal이 호출. confirm은 boolean, prompt는 string|null로 settle */
export function settleConfirm(result) {
  const s = confirmState.value
  confirmState.value = null
  s?.resolve(result)
}
