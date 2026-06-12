import { ref } from 'vue'
import { apiAI } from '../api'

/**
 * LLM 모델 선택 상태 (모듈 스코프 공유).
 * AgentComposer의 드롭다운에서 선택하고, useAgentChat이 채팅 요청에 실어 보낸다.
 * 목록은 백엔드 pricing.yaml(단가 등록 모델)에서 가져온다.
 */
export const availableModels = ref([])
export const defaultModel = ref('')
export const selectedModel = ref(null) // null = 서버 기본 모델 사용

let _loaded = false

export async function fetchModels() {
  if (_loaded) return
  try {
    const { data } = await apiAI.get('/api/agent/models')
    availableModels.value = data?.models || []
    defaultModel.value = data?.default || ''
    _loaded = true
  } catch { /* 다음 마운트에서 재시도 */ }
}
