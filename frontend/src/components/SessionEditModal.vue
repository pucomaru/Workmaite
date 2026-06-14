<script setup>
import { ref, computed, watch } from 'vue'
import { toast } from '../composables/useToast'
import { confirmDialog } from '../composables/useConfirm'
import api from '../api'
import MemberInvite from './MemberInvite.vue'

const props = defineProps({
  show: { type: Boolean, default: false },
  session: { type: Object, default: null },
})
const emit = defineEmits(['close', 'saved', 'deleted'])

const form = ref({
  id: null,
  meetingId: null,
  title: '',
  location: '',
  dateOnly: '',
  timeOnly: '',
  type: 'gpt-realtime-whisper',
  context: '',
})
const members = ref([])
const saving = ref(false)

watch(
  () => props.session,
  async s => {
    if (!s) return
    form.value = {
      id: s.id,
      meetingId: s.meetingId ?? s.meeting_id ?? null,
      title: s.title || '',
      location: s.location || '',
      dateOnly: s.scheduled_at ? s.scheduled_at.slice(0, 10) : '',
      timeOnly: s.scheduled_at ? s.scheduled_at.slice(11, 16) : '',
      type: s.type || 'gpt-realtime-whisper',
      context: s.context || '',
    }
    // members가 직접 주어진 경우 (archive 등) 바로 사용, 아니면 attendee_ids로 API 조회
    if (s.members?.length) {
      members.value = s.members
    } else {
      members.value = []
      if (s.attendee_ids?.length) {
        try {
          const { data } = await api.get(`/api/v1/users/by-ids?ids=${s.attendee_ids.join(',')}`)
          const roleMap = Object.fromEntries((s.attendees || []).map(a => [a.userId, a.role]))
          members.value = (data.data ?? data).map(u => ({
            userId: u.id,
            name: u.name,
            email: u.email,
            role: roleMap[u.id] || 'member',
          }))
        } catch {}
      }
    }
  },
  { immediate: true },
)

const canSubmit = computed(() => {
  const f = form.value
  return (
    !saving.value && f.title.trim() && f.location.trim() && f.dateOnly && members.value.length > 0
  )
})

async function doDelete() {
  if (
    !(await confirmDialog('회의를 삭제하시겠습니까? 이 작업은 되돌릴 수 없습니다.', {
      danger: true,
    }))
  )
    return
  saving.value = true
  try {
    await api.delete(`/api/v1/sessions/${form.value.id}`)
    emit('deleted', { meetingId: form.value.meetingId })
    emit('close')
  } catch (e) {
    toast.error(e.response?.data?.message || '삭제 실패')
  } finally {
    saving.value = false
  }
}

async function doSave() {
  if (!canSubmit.value) return
  saving.value = true
  try {
    await api.patch(`/api/v1/sessions/${form.value.id}`, {
      title: form.value.title,
      location: form.value.location || null,
      scheduled_at: form.value.dateOnly
        ? `${form.value.dateOnly}T${form.value.timeOnly || '00:00'}:00`
        : null,
      type: form.value.type,
      context: form.value.context || null,
      attendees: members.value.map(m => ({ user_id: m.userId, role: m.role || 'member' })),
    })
    emit('saved', { meetingId: form.value.meetingId })
    emit('close')
  } catch (e) {
    toast.error(e.response?.data?.message || '수정 실패')
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <Teleport to="body">
    <div v-if="show" class="app-modal-backdrop">
      <div class="app-modal app-modal-sm">
        <div class="app-modal-header">
          <span class="app-modal-title">회의 편집</span>
          <button class="app-modal-close" @click="emit('close')">
            <svg
              width="14"
              height="14"
              fill="none"
              stroke="currentColor"
              stroke-width="2.5"
              viewBox="0 0 24 24"
            >
              <path d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>
        <div class="app-modal-body">
          <div class="app-modal-field">
            <label>회의명 <span class="req">*</span></label>
            <input
              v-model="form.title"
              class="app-modal-input"
              placeholder="예: 2026 전략 수립 1차"
            />
          </div>
          <div class="app-modal-field">
            <label>장소 <span class="req">*</span></label>
            <input
              v-model="form.location"
              class="app-modal-input"
              placeholder="예: SK U Tower 8층"
            />
          </div>
          <div class="app-modal-field">
            <label>회의 날짜 <span class="req">*</span></label>
            <div class="datetime-split-input">
              <input type="date" v-model="form.dateOnly" class="datetime-split-date" />
              <span class="datetime-split-sep"></span>
              <input
                type="text"
                v-model="form.timeOnly"
                class="datetime-split-time"
                placeholder="HH:MM"
                maxlength="5"
              />
            </div>
          </div>
          <div class="app-modal-field">
            <label>회의 맥락</label>
            <textarea
              v-model="form.context"
              class="app-modal-input context-modal-textarea"
              rows="4"
              placeholder="대화 상황, 주제, 고유명사 등 회의와 관련된 맥락을 입력하면 AI 응답 정확도가 높아져요.&#10;예: 분기별 성과 검토 회의, 주요 KPI: 전환율·CAC, 팀: 마케팅/영업/기획"
            ></textarea>
          </div>
          <div class="app-modal-field">
            <MemberInvite v-model="members" />
          </div>
        </div>
        <div class="app-modal-footer">
          <button class="app-btn-danger" :disabled="saving" @click="doDelete">삭제</button>
          <div class="app-modal-footer-right">
            <button class="app-btn-cancel" @click="emit('close')">취소</button>
            <button class="app-btn-primary" :disabled="!canSubmit" @click="doSave">
              {{ saving ? '수정 중...' : '수정' }}
            </button>
          </div>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.app-modal-footer {
  justify-content: space-between;
}
</style>
