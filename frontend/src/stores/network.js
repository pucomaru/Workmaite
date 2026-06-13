import { ref } from 'vue'

/**
 * 네트워크 연결 상태 (PLAN Phase 2).
 * api.js 인터셉터가 ERR_NETWORK 시 true, 성공 응답 시 false로 갱신한다.
 * 백엔드 단절 시 스토어의 이전 데이터가 정상처럼 보이는 문제를 배너로 인지시킨다.
 */
export const networkDown = ref(false)

export function markNetworkDown() { networkDown.value = true }
export function markNetworkUp() { if (networkDown.value) networkDown.value = false }
