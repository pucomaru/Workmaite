<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useMeetingsStore } from '../stores/meetings'
import { useAuthStore } from '../stores/auth'

const route  = useRoute()
const router = useRouter()
const meetingsStore = useMeetingsStore()
const authStore     = useAuthStore()

const meetingId = computed(() => route.params.meetingId)
const ready = ref(false)
const role    = computed(() => meetingsStore.myRole)
const isEnded = computed(() => meetingsStore.currentMeeting?.status === 'ended')
const meetingTitle = computed(() => meetingsStore.currentMeeting?.title || '')

onMounted(async () => {
  try {
    await meetingsStore.fetchRole(Number(meetingId.value))
  } finally {
    ready.value = true
  }
})

async function terminateMeeting() {
  if (!confirm('회의체를 완전히 종료하시겠습니까?\n이후 회의를 진행할 수 없습니다.')) return
  await meetingsStore.terminateMeeting(Number(meetingId.value))
}

const deleting = ref(false)</script>

<template>
  <nav class="meeting-nav">
    <template v-if="ready">
      <span class="meeting-title-label">🗞 {{ meetingTitle }}</span>
      <div class="nav-actions">
        <button
          v-if="role === 'admin' && !isEnded"
          class="btn-nav-end"
          @click="terminateMeeting"
          title="회의체 종료"
        >종료</button>
        <button
          v-if="role === 'admin' && isEnded"
          class="btn btn-ghost btn-sm delete-btn"
          :disabled="deleting"
          @click="deleteMeeting"
          title="회의체 영구 삭제"
        >{{ deleting ? '삭제 중...' : '삭제' }}</button>
        <button
          v-if="role && role !== 'admin'"
          class="btn btn-ghost btn-sm leave-btn"
          :disabled="leaving"
          @click="leaveMeeting"
        >{{ leaving ? '처리 중...' : '탈퇴' }}</button>
      </div>
    </template>
  </nav>
</template>

<style scoped>
.meeting-nav {
  background: #fff;
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  padding: 0 14px;
  margin-bottom: 16px;
  box-shadow: var(--shadow);
  display: flex;
  align-items: center;
  gap: 8px;
  min-height: 48px;
  flex-shrink: 0;
}
.meeting-title-label {
  flex: 1;
  font-size: 14px;
  font-weight: 600;
  color: var(--text);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.nav-actions {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-shrink: 0;
}
.leave-btn {
  color: var(--danger, #ef4444);
  border: 1px solid var(--danger, #ef4444);
  border-radius: 99px;
  font-size: 12px;
  padding: 3px 10px;
}
.leave-btn:hover { background: #fef2f2; }
.delete-btn { color: var(--text-muted); }
.btn-nav-end {
  padding: 4px 12px;
  border-radius: var(--radius, 6px);
  border: 1px solid var(--danger, #ef4444);
  background: transparent;
  color: var(--danger, #ef4444);
  font-size: 12px;
  font-weight: 700;
  cursor: pointer;
  line-height: 1.5;
  white-space: nowrap;
}
.btn-nav-end:hover { background: var(--danger, #ef4444); color: #fff; }
</style>

