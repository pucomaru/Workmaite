import { defineStore } from 'pinia'
import { ref } from 'vue'
import api, { apiAI } from '../api'

export const useMeetingsStore = defineStore('meetings', () => {
  const meetings = ref([])
  const currentMeeting = ref(null)
  const myRole = ref(null)
  const currentMembers = ref([])
  const currentLoopIdx = ref(0) // MeetingNav ↔ SessionsPage 공유
  const meetingRoles = ref({}) // { [meetingId]: 'admin' | 'member' | null }
  const membersByMeeting = ref({}) // { [meetingId]: MemberResponse[] } — 페이지 로컬 캐시 대신 단일 캐시 (PLAN Phase 1)

  async function fetchMeetings() {
    const { data } = await api.get('/api/v1/meetings')
    meetings.value = data
    const roles = {}
    data.forEach(m => {
      roles[m.id] = m.my_role ?? null
    })
    meetingRoles.value = roles
  }

  async function fetchMeeting(id) {
    const { data } = await api.get(`/api/v1/meetings/${id}`)
    currentMeeting.value = data
    if (data.my_role !== undefined) {
      meetingRoles.value = { ...meetingRoles.value, [id]: data.my_role }
    }
    return data
  }

  async function fetchMembers(meetingId) {
    try {
      const { data } = await api.get(`/api/v1/meetings/${meetingId}/members`)
      currentMembers.value = data
      membersByMeeting.value[meetingId] = data
      return data
    } catch {
      currentMembers.value = []
      return []
    }
  }

  /** 캐시 우선 멤버 조회 — 이미 받아온 회의체는 재요청하지 않는다. force로 무효화 가능 */
  async function fetchMembersOnce(meetingId, { force = false } = {}) {
    if (!force && membersByMeeting.value[meetingId]) return membersByMeeting.value[meetingId]
    try {
      const { data } = await api.get(`/api/v1/meetings/${meetingId}/members`)
      membersByMeeting.value[meetingId] = data
      return data
    } catch {
      membersByMeeting.value[meetingId] = []
      return []
    }
  }

  function invalidateMembers(meetingId) {
    delete membersByMeeting.value[meetingId]
  }

  async function fetchRole(meetingId) {
    try {
      const { data } = await api.get(`/api/v1/meetings/${meetingId}/my-role`)
      myRole.value = data.role
      meetingRoles.value = { ...meetingRoles.value, [meetingId]: data.role }
      return data.role
    } catch {
      const cached = meetingRoles.value[meetingId] ?? null
      myRole.value = cached
      return cached
    }
  }

  async function createMeeting(payload) {
    const { data } = await api.post('/api/v1/meetings', payload)
    meetings.value.unshift(data)
    return data
  }

  async function updateTitle(meetingId, title) {
    const { data } = await api.patch(`/api/v1/meetings/${meetingId}`, { title })
    if (currentMeeting.value?.id === meetingId) currentMeeting.value = data
    const idx = meetings.value.findIndex(m => m.id === meetingId)
    if (idx !== -1) meetings.value[idx] = data
    return data
  }

  async function terminateMeeting(meetingId) {
    const { data } = await api.patch(`/api/v1/meetings/${meetingId}`, { status: 'ended' })
    if (currentMeeting.value?.id === meetingId) currentMeeting.value = data
    const idx = meetings.value.findIndex(m => m.id === meetingId)
    if (idx !== -1) meetings.value[idx] = data
    return data
  }

  async function deleteMeeting(meetingId) {
    // /api/ai → FastAPI (Ingress 규칙), /api/v1 → Spring Boot (DELETE 없음)
    await apiAI.delete(`/api/ai/meetings/${meetingId}`)
    meetings.value = meetings.value.filter(m => m.id !== meetingId)
    if (currentMeeting.value?.id === meetingId) currentMeeting.value = null
  }

  async function addMember(meetingId, userId, role = 'member') {
    const { data } = await api.post(`/api/v1/meetings/${meetingId}/members`, { userId, role })
    await fetchMembers(meetingId)
    return data
  }

  async function updateMemberRole(meetingId, memberId, role) {
    await api.patch(`/api/v1/meetings/${meetingId}/members/${memberId}`, { role })
    await fetchMembers(meetingId)
  }

  async function removeMember(meetingId, memberId) {
    await api.delete(`/api/v1/meetings/${meetingId}/members/${memberId}`)
    currentMembers.value = currentMembers.value.filter(m => m.id !== memberId)
    if (membersByMeeting.value[meetingId]) {
      membersByMeeting.value[meetingId] = membersByMeeting.value[meetingId].filter(
        m => m.id !== memberId,
      )
    }
  }

  async function leaveMeeting(meetingId, currentUserId) {
    let members = currentMembers.value
    if (!members.length) members = await fetchMembers(meetingId)
    const me = members.find(m => m.user?.id === currentUserId || m.userId === currentUserId)
    if (!me) throw new Error('membership not found')
    await removeMember(meetingId, me.id)
  }

  return {
    meetings,
    currentMeeting,
    myRole,
    currentMembers,
    currentLoopIdx,
    meetingRoles,
    membersByMeeting,
    fetchMeetings,
    fetchMeeting,
    fetchMembers,
    fetchMembersOnce,
    invalidateMembers,
    fetchRole,
    createMeeting,
    updateTitle,
    terminateMeeting,
    deleteMeeting,
    addMember,
    updateMemberRole,
    removeMember,
    leaveMeeting,
  }
})
