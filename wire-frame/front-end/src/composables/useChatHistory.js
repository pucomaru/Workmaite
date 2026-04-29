import { ref } from 'vue'
import api from '../api'

/**
 * AI 에이전트 대화 기록을 DB에 영속 저장/복원합니다.
 *
 * @param {string} contextType - 페이지 타입: agenda | prepare | todo | cardnews | room
 * @param {number|null} contextId - meetingId 또는 sessionId (null이면 비활성화)
 */
export function useChatHistory(contextType, contextId) {
  const messages = ref([])
  const historyLoading = ref(false)

  /** 서버에서 대화 기록 로드 */
  async function loadMessages() {
    if (!contextId) return
    historyLoading.value = true
    try {
      const res = await api.get(`/api/chats/${contextType}/${contextId}`)
      messages.value = res.data.map(m => ({ role: m.role, content: m.content }))
    } catch (e) {
      console.error('[useChatHistory] 로드 실패', e)
    } finally {
      historyLoading.value = false
    }
  }

  /**
   * 완성된 메시지 1건을 DB에 저장합니다.
   * 스트리밍 중에는 호출하지 말고, 스트리밍 완료 후 한 번만 호출하세요.
   */
  async function saveMessage(role, content) {
    if (!contextId) return
    try {
      await api.post(`/api/chats/${contextType}/${contextId}`, { role, content })
    } catch (e) {
      console.error('[useChatHistory] 저장 실패', e)
    }
  }

  /** 해당 컨텍스트의 대화 기록 전체 삭제 */
  async function clearHistory() {
    if (!contextId) return
    try {
      await api.delete(`/api/chats/${contextType}/${contextId}`)
      messages.value = []
    } catch (e) {
      console.error('[useChatHistory] 삭제 실패', e)
    }
  }

  return { messages, historyLoading, loadMessages, saveMessage, clearHistory }
}
