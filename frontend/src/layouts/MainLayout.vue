<script setup>
import { ref, onMounted, watch } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useAuthStore } from '../stores/auth'
import { useMeetingsStore } from '../stores/meetings'
import AppHeader from '../components/AppHeader.vue'

const router = useRouter()
const route = useRoute()
const auth = useAuthStore()
const meetingsStore = useMeetingsStore()

onMounted(async () => {
  await meetingsStore.fetchMeetings()
})

const meetingId = ref(null)
watch(() => route.params.meetingId, (id) => {
  meetingId.value = id ? Number(id) : null
  meetingsStore.currentLoopIdx = 0
  if (id) meetingsStore.fetchRole(id)
}, { immediate: true })

const inMeetingPage = ref(false)
watch(() => route.path, (p) => {
  inMeetingPage.value = p.includes('/meetings/')
}, { immediate: true })
</script>

<template>
  <div class="layout">
    <AppHeader />
    <div class="layout-body">
      <main class="layout-main">
        <RouterView :key="route.params.meetingId ?? route.path" />
      </main>
    </div>
    <HyeanAgent v-if="inMeetingPage && meetingId" :meeting-id="meetingId" />
    <div class="ai-disclaimer">Workma!te의 AI는 실수할 수 있으니 반드시 결과를 검토해주세요.</div>
  </div>
</template>

<style scoped>
.layout { display: flex; flex-direction: column; height: 100vh; overflow: hidden; }
.layout-body { display: flex; flex: 1; overflow: hidden; min-height: 0; }
.layout-main { flex: 1; overflow-y: auto; padding: 24px 28px; }
.ai-disclaimer {
  text-align: center;
  font-size: 11px;
  color: var(--text-muted);
  background: var(--bg);
  padding: 4px 12px;
  flex-shrink: 0;
  letter-spacing: 0.01em;
}
</style>
