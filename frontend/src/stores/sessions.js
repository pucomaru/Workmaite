import { defineStore } from 'pinia'
import { ref } from 'vue'
import api from '../api'

/**
 * 세션 목록 단일 캐시 (PLAN Phase 1).
 * 기존에는 SessionPage 로컬 sessionsCache로만 존재해 다른 페이지에서 재사용이 불가능했다.
 */
export const useSessionsStore = defineStore('sessions', () => {
  const sessionsByMeeting = ref({}) // { [meetingId]: SessionResponse[] }

  /** 캐시 우선 조회 — force로 무효화 후 재조회 */
  async function loadSessions(meetingId, { force = false } = {}) {
    if (!force && sessionsByMeeting.value[meetingId]) return sessionsByMeeting.value[meetingId]
    try {
      const res = await api.get(`/api/v1/meetings/${meetingId}/sessions`)
      sessionsByMeeting.value[meetingId] = res.data ?? []
    } catch (e) {
      // 조용히 빈 목록으로 두면 500/403을 못 보게 된다 — 디버깅용 로그 (UX는 그대로 빈 목록)
      console.error(`[sessions] 회의 ${meetingId} 세션 조회 실패`, e?.response?.status, e)
      sessionsByMeeting.value[meetingId] = []
    }
    return sessionsByMeeting.value[meetingId]
  }

  function invalidate(meetingId) {
    delete sessionsByMeeting.value[meetingId]
  }

  return { sessionsByMeeting, loadSessions, invalidate }
})
