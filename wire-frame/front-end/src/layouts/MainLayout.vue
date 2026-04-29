<script setup>
import { ref, onMounted, watch } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useAuthStore } from '../stores/auth'
import { useNotificationsStore } from '../stores/notifications'
import { useMeetingsStore } from '../stores/meetings'
import AppHeader from '../components/AppHeader.vue'
import AppSidebar from '../components/AppSidebar.vue'
import HyeanAgent from '../components/HyeanAgent.vue'

const router = useRouter()
const route = useRoute()
const auth = useAuthStore()
const notifStore = useNotificationsStore()
const meetingsStore = useMeetingsStore()

const sidebarOpen = ref(true)
const ws = ref(null)

onMounted(async () => {
  await notifStore.fetch()
  await meetingsStore.fetchMeetings()
  connectNotifWs()
})

function connectNotifWs() {
  if (!auth.user) return
  ws.value = new WebSocket(`ws://localhost:8000/ws/notifications/${auth.user.id}`)
  ws.value.onmessage = (e) => {
    try {
      const msg = JSON.parse(e.data)
      notifStore.push(msg)
    } catch {}
  }
  ws.value.onclose = () => setTimeout(connectNotifWs, 3000)
}

const meetingId = ref(null)
watch(() => route.params.meetingId, (id) => {
  meetingId.value = id ? Number(id) : null
  if (id) meetingsStore.fetchRole(id)
}, { immediate: true })

const inMeetingPage = ref(false)
watch(() => route.path, (p) => {
  inMeetingPage.value = p.includes('/meetings/')
}, { immediate: true })
</script>

<template>
  <div class="layout">
    <AppHeader :sidebar-open="sidebarOpen" @toggle-sidebar="sidebarOpen = !sidebarOpen" />
    <div class="layout-body">
      <AppSidebar :open="sidebarOpen" />
      <main class="layout-main" :class="{ 'sidebar-closed': !sidebarOpen }">
        <RouterView />
      </main>
    </div>
    <HyeanAgent v-if="inMeetingPage && meetingId" :meeting-id="meetingId" />
  </div>
</template>

<style scoped>
.layout { display: flex; flex-direction: column; height: 100vh; overflow: hidden; }
.layout-body { display: flex; flex: 1; overflow: hidden; }
.layout-main {
  flex: 1;
  overflow-y: auto;
  padding: 20px;
  margin-left: var(--sidebar-w);
  transition: margin-left .2s;
}
.layout-main.sidebar-closed { margin-left: 0; }
</style>
