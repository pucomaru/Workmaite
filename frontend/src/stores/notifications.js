import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { apiAI } from '../api'

export const useNotificationsStore = defineStore('notifications', () => {
  const notifications = ref([])
  const unreadCount = computed(() => notifications.value.filter(n => !n.is_read).length)

  async function fetch() {
    const { data } = await apiAI.get('/api/notifications')
    notifications.value = data
  }

  async function markRead(id) {
    await apiAI.patch(`/api/notifications/${id}/read`)
    const n = notifications.value.find(n => n.id === id)
    if (n) n.is_read = true
  }

  async function markAllRead() {
    await apiAI.patch('/api/notifications/read-all')
    notifications.value.forEach(n => n.is_read = true)
  }

  function push(notif) {
    notifications.value.unshift(notif)
  }

  return { notifications, unreadCount, fetch, markRead, markAllRead, push }
})
