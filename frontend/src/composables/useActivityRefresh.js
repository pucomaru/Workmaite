import { onMounted, onUnmounted } from 'vue'
import { ensureFreshToken } from '../api'

/**
 * 사용자 인터랙션(마우스·클릭·키입력·터치·스크롤) 감지 시 JWT를 자동 갱신합니다.
 *
 * - 만료 5분 전 이내일 때만 실제 갱신 요청을 발송합니다.
 * - 60초 쓰로틀: 60초 안에 아무리 많은 이벤트가 와도 토큰 체크는 한 번만 합니다.
 * - App.vue 최상단에서 한 번만 등록하면 앱 전체에 적용됩니다.
 */
export function useActivityRefresh() {
  let _throttleTimer = null

  const onActivity = () => {
    if (_throttleTimer) return // 60초 내 중복 체크 방지
    _throttleTimer = setTimeout(() => { _throttleTimer = null }, 60_000)
    ensureFreshToken().catch(() => {}) // 실패는 무시 — 실제 요청 시 인터셉터가 처리
  }

  const EVENTS = ['mousemove', 'mousedown', 'keydown', 'touchstart', 'scroll']

  onMounted(() => {
    EVENTS.forEach(e => window.addEventListener(e, onActivity, { passive: true }))
  })

  onUnmounted(() => {
    EVENTS.forEach(e => window.removeEventListener(e, onActivity))
    clearTimeout(_throttleTimer)
  })
}
