<script setup>
import { ref, onMounted, computed, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import api from '../api'
import MeetingNav from '../components/MeetingNav.vue'
import { useMeetingsStore } from '../stores/meetings'

const route = useRoute()
const router = useRouter()
const meetingsStore = useMeetingsStore()
const meetingId = computed(() => Number(route.params.meetingId))
const role = computed(() => meetingsStore.myRole)

const loops = ref([])
const currentLoopIdx = computed(() => meetingsStore.currentLoopIdx)
const currentLoop = computed(() => loops.value[currentLoopIdx.value] ?? null)
const currentSessions = computed(() => currentLoop.value?.sessions ?? [])

const showMinutesModal = ref(false)
const selectedSession = ref(null)
const minutes = ref(null)

const editingId = ref(null)
const editForm = ref({ title: '', scheduled_at: '' })
const saving = ref(false)
const deleting = ref(null)

// 회의 만들기 모달
const showCreateModal = ref(false)
const createForm = ref({ title: '', scheduled_at: '' })
const creating = ref(false)

onMounted(async () => {
  await meetingsStore.fetchMeeting(meetingId.value)
  await meetingsStore.fetchRole(meetingId.value)
  await loadLoops()
})

async function loadLoops() {
  const { data } = await api.get(`/api/meetings/${meetingId.value}/loops`)
  loops.value = data
  if (data.length > 0 && currentLoopIdx.value >= data.length) {
    meetingsStore.currentLoopIdx = data.length - 1
  }
}

// 회의 생성
async function createSession() {
  if (!createForm.value.title.trim() || creating.value || !currentLoop.value) return
  creating.value = true
  try {
    await api.post(`/api/meetings/${meetingId.value}/sessions`, {
      title: createForm.value.title.trim(),
      loop_id: currentLoop.value.id,
      scheduled_at: createForm.value.scheduled_at || null,
    })
    showCreateModal.value = false
    createForm.value = { title: '', scheduled_at: '' }
    await loadLoops()
  } finally {
    creating.value = false
  }
}

function startEdit(s) {
  editingId.value = s.id
  editForm.value = {
    title: s.title,
    scheduled_at: s.scheduled_at ? s.scheduled_at.slice(0, 16) : '',
  }
}

function cancelEdit() { editingId.value = null }

async function saveEdit(s) {
  if (!editForm.value.title.trim() || saving.value) return
  saving.value = true
  try {
    await api.patch(`/api/sessions/${s.id}`, {
      title: editForm.value.title.trim(),
      scheduled_at: editForm.value.scheduled_at || null,
    })
    editingId.value = null
    await loadLoops()
  } finally {
    saving.value = false
  }
}

async function deleteSession(s) {
  if (!confirm(`"${s.title}" 회의를 삭제하시겠습니까?\n삭제하면 회의록도 함께 삭제됩니다.`)) return
  deleting.value = s.id
  try {
    await api.delete(`/api/sessions/${s.id}`)
    await loadLoops()
  } finally {
    deleting.value = null
  }
}

async function viewMinutes(s) {
  selectedSession.value = s
  minutes.value = null
  showMinutesModal.value = true
  try {
    const { data } = await api.get(`/api/sessions/${s.id}/minutes`)
    minutes.value = data
  } catch {
    minutes.value = null
  }
}

async function joinRoom(s) {
  try {
    const { data } = await api.get(`/api/livekit/token/${meetingId.value}/${s.id}`)
    const url = router.resolve(`/meetings/${meetingId.value}/sessions/${s.id}/room`).href
    const params = new URLSearchParams({ lkToken: data.token, lkUrl: data.url })
    window.open(`${url}?${params.toString()}`, '_blank')
  } catch (e) {
    alert(e.response?.data?.detail || 'LiveKit 토큰 발급 실패')
  }
}

function goCardNews() {
  router.push(`/meetings/${meetingId.value}/card-news`)
}

function formatDate(d) {
  if (!d) return '일정 미정'
  return new Date(d).toLocaleString('ko-KR', {
    month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit',
  })
}

function statusLabel(s) {
  return { scheduled: '예정', ongoing: '진행중', ended: '종료' }[s] || s
}
function statusCls(s) {
  return { scheduled: 'badge-primary', ongoing: 'badge-warning', ended: 'badge-muted' }[s] || 'badge-muted'
}
</script>

<template>
  <div style="display:flex;flex-direction:column;height:calc(100vh - var(--header-h) - 40px)">
    <MeetingNav />

    <div class="card" style="flex:1;min-height:0;display:flex;flex-direction:column">
      <div class="card-header">
        <span style="font-weight:600">
          {{ currentLoop ? `${currentLoop.loop_number}차 회의 목록` : '회의 목록' }}
        </span>
        <div style="display:flex;gap:8px;align-items:center">
          <button
            v-if="role === 'admin' && currentLoop"
            class="btn btn-primary btn-sm"
            @click="showCreateModal = true"
          >
            + 회의 만들기
          </button>
          <button v-if="role === 'admin'" class="btn btn-outline btn-sm" @click="goCardNews">
            📰 카드뉴스
          </button>
        </div>
      </div>

      <div style="flex:1;overflow-y:auto;padding:16px;display:flex;flex-direction:column;gap:12px">
        <!-- 이 차수에 회의 없음 -->
        <div v-if="!currentSessions.length" class="empty-state">
          <p>이 차수에 등록된 회의가 없습니다.</p>
          <button
            v-if="role === 'admin'"
            class="btn btn-primary btn-sm"
            style="margin-top:12px"
            @click="showCreateModal = true"
          >
            + 회의 만들기
          </button>
        </div>

        <div v-for="s in currentSessions" :key="s.id" class="session-card fade-in">

          <!-- 수정 모드 -->
          <div v-if="editingId === s.id" class="session-edit">
            <div class="form-group" style="margin-bottom:8px">
              <label class="form-label" style="font-size:11px">회의명</label>
              <input v-model="editForm.title" class="form-input"
                @keydown.enter="saveEdit(s)" @keydown.esc="cancelEdit" autofocus />
            </div>
            <div class="form-group" style="margin-bottom:12px">
              <label class="form-label" style="font-size:11px">일정</label>
              <input type="datetime-local" v-model="editForm.scheduled_at" class="form-input" />
            </div>
            <div style="display:flex;gap:6px">
              <button class="btn btn-primary btn-sm"
                :disabled="!editForm.title.trim() || saving" @click="saveEdit(s)">
                {{ saving ? '저장 중...' : '저장' }}
              </button>
              <button class="btn btn-ghost btn-sm" @click="cancelEdit">취소</button>
            </div>
          </div>

          <!-- 보기 모드 -->
          <div v-else>
            <div class="session-header">
              <div>
                <div style="font-weight:600;font-size:14px">{{ s.title }}</div>
                <div style="font-size:12px;color:var(--text-muted);margin-top:2px">
                  {{ formatDate(s.scheduled_at) }}
                </div>
              </div>
              <span class="badge" :class="statusCls(s.status)">{{ statusLabel(s.status) }}</span>
            </div>
            <div class="session-actions">
              <button class="btn btn-primary btn-sm" @click="joinRoom(s)">
                {{ s.status === 'ended' ? '다시 보기' : '참여하기' }}
              </button>
              <button class="btn btn-outline btn-sm"
                :disabled="s.status !== 'ended'" @click="viewMinutes(s)">
                회의록
              </button>
              <template v-if="role === 'admin' && s.status !== 'ongoing'">
                <button class="btn btn-ghost btn-sm" @click="startEdit(s)">수정</button>
                <button class="btn btn-ghost btn-sm" style="color:var(--danger)"
                  :disabled="deleting === s.id" @click="deleteSession(s)">
                  {{ deleting === s.id ? '삭제 중...' : '삭제' }}
                </button>
              </template>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>

  <!-- 회의 만들기 모달 -->
  <div v-if="showCreateModal" class="modal-overlay" @click.self="showCreateModal = false">
    <div class="modal slide-up">
      <div class="modal-header">
        <span class="modal-title">
          {{ currentLoop?.loop_number }}차 회의 만들기
        </span>
        <button class="btn-ghost btn-icon" @click="showCreateModal = false">✕</button>
      </div>
      <div class="modal-body">
        <div class="form-group">
          <label class="form-label">회의 제목 <span style="color:var(--danger)">*</span></label>
          <input
            v-model="createForm.title"
            class="form-input"
            placeholder="예: 1차 회의"
            @keydown.enter="createSession"
            autofocus
          />
        </div>
        <div class="form-group">
          <label class="form-label">일정</label>
          <input type="datetime-local" v-model="createForm.scheduled_at" class="form-input" />
        </div>
      </div>
      <div class="modal-footer">
        <button class="btn btn-outline" @click="showCreateModal = false">취소</button>
        <button
          class="btn btn-primary"
          :disabled="!createForm.title.trim() || creating"
          @click="createSession"
        >
          {{ creating ? '생성 중...' : '회의 만들기' }}
        </button>
      </div>
    </div>
  </div>

  <!-- 회의록 모달 -->
  <div v-if="showMinutesModal" class="modal-overlay" @click.self="showMinutesModal = false">
    <div class="modal" style="max-width:680px">
      <div class="modal-header">
        <span class="modal-title">{{ selectedSession?.title }} 회의록</span>
        <button class="btn-ghost btn-icon" @click="showMinutesModal = false">✕</button>
      </div>
      <div class="modal-body">
        <div v-if="!minutes" class="empty-state"><p>회의록을 불러오는 중...</p></div>
        <div v-else class="minutes-content">{{ minutes.content_summary }}</div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.session-card {
  background: #f8fafc;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 14px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.session-header { display: flex; justify-content: space-between; align-items: flex-start; }
.session-actions { display: flex; gap: 6px; flex-wrap: wrap; }
.session-edit { display: flex; flex-direction: column; }
.minutes-content { white-space: pre-wrap; font-size: 13px; line-height: 1.7; }
</style>
