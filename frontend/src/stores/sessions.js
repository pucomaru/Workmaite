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
    } catch {
      sessionsByMeeting.value[meetingId] = []
    }
    return sessionsByMeeting.value[meetingId]
  }

  function invalidate(meetingId) {
    delete sessionsByMeeting.value[meetingId]
  }

  return { sessionsByMeeting, loadSessions, invalidate }
})
