import { ref, watch } from 'vue'
import { apiAI } from '../api'

/**
 * LLM 모델 선택 상태 (모듈 스코프 공유).
 * AgentComposer의 드롭다운에서 선택하고, useAgentChat이 채팅 요청에 실어 보낸다.
 * 목록은 백엔드 pricing.yaml(단가 등록 모델)에서 가져온다.
 */
export const availableModels = ref([])
export const defaultModel = ref('')
// null = 서버 기본 모델 사용. 새로고침 후에도 헤더와 표시가 일치하도록 sessionStorage에서 복원.
export const selectedModel = ref(sessionStorage.getItem('llm_model') || null)

// 선택 모델을 sessionStorage에 동기화 — api 인터셉터/streamPost가 모든 요청에
// X-LLM-Model 헤더로 실어 보낸다(순환 import 회피). null이면 헤더 미부착(서버 기본).
watch(selectedModel, v => {
  if (v) sessionStorage.setItem('llm_model', v)
  else sessionStorage.removeItem('llm_model')
})

let _loaded = false

export async function fetchModels() {
  if (_loaded) return
  try {
    const { data } = await apiAI.get('/api/agent/models')
    availableModels.value = data?.models || []
    defaultModel.value = data?.default || ''
    _loaded = true
  } catch {
    /* 다음 마운트에서 재시도 */
  }
}
