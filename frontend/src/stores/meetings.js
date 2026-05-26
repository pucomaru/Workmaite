import { defineStore } from 'pinia'
import { ref } from 'vue'
import api from '../api'

export const useMeetingsStore = defineStore('meetings', () => {
  const meetings = ref([])
  const currentMeeting = ref(null)
  const myRole = ref(null)
  const currentMembers = ref([])
  const currentLoopIdx = ref(0)   // MeetingNav ↔ SessionsPage 공유

  async function fetchMeetings() {
    const { data } = await api.get('/api/v1/meetings')
    meetings.value = data
  }

  async function fetchMyMeetings() {
    const { data } = await api.get('/api/v1/me/meetings')
    meetings.value = data
  }

  async function fetchMeeting(id) {
    const { data } = await api.get(`/api/v1/meetings/${id}`)
    currentMeeting.value = data
    return data
  }

  async function fetchMembers(meetingId) {
    try {
      const { data } = await api.get(`/api/meetings/${meetingId}/members`)
      currentMembers.value = data
      return data
    } catch {
      currentMembers.value = []
      return []
    }
  }

  async function fetchRole(meetingId) {
    try {
      const { data } = await api.get(`/api/meetings/${meetingId}/my-role`)
      myRole.value = data.role
      return data.role
    } catch {
      myRole.value = null
      return null
    }
  }

  async function createMeeting(payload) {
    const { data } = await api.post('/api/meetings', payload)
    meetings.value.unshift(data)
    return data
  }

  async function updateTitle(meetingId, title) {
    const { data } = await api.patch(`/api/meetings/${meetingId}`, { title })
    if (currentMeeting.value?.id === meetingId) currentMeeting.value = data
    const idx = meetings.value.findIndex(m => m.id === meetingId)
    if (idx !== -1) meetings.value[idx] = data
    return data
  }

  async function terminateMeeting(meetingId) {
    const { data } = await api.patch(`/api/meetings/${meetingId}`, { status: 'ended' })
    if (currentMeeting.value?.id === meetingId) currentMeeting.value = data
    const idx = meetings.value.findIndex(m => m.id === meetingId)
    if (idx !== -1) meetings.value[idx] = data
    return data
  }

  async function deleteMeeting(meetingId) {
    await api.delete(`/api/meetings/${meetingId}`)
    meetings.value = meetings.value.filter(m => m.id !== meetingId)
    if (currentMeeting.value?.id === meetingId) currentMeeting.value = null
  }

  async function addMember(meetingId, userId, role = 'presenter') {
    const { data } = await api.post(`/api/meetings/${meetingId}/members`, { user_id: userId, role })
    await fetchMembers(meetingId)
    return data
  }

  async function updateMemberRole(meetingId, memberId, role) {
    await api.patch(`/api/meetings/${meetingId}/members/${memberId}`, { role })
    await fetchMembers(meetingId)
  }

  async function removeMember(meetingId, memberId) {
    await api.delete(`/api/meetings/${meetingId}/members/${memberId}`)
    currentMembers.value = currentMembers.value.filter(m => m.id !== memberId)
  }

  async function leaveMeeting(meetingId, currentUserId) {
    let members = currentMembers.value
    if (!members.length) members = await fetchMembers(meetingId)
    const me = members.find(m => m.user?.id === currentUserId)
    if (!me) throw new Error('membership not found')
    await removeMember(meetingId, me.id)
  }

  return {
    meetings, currentMeeting, myRole, currentMembers, currentLoopIdx,
    fetchMeetings, fetchMyMeetings, fetchMeeting, fetchMembers, fetchRole,
    createMeeting, updateTitle, terminateMeeting, deleteMeeting,
    addMember, updateMemberRole, removeMember, leaveMeeting,
  }
})
