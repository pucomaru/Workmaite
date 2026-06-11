<script setup>
import { ref, computed, watch } from 'vue'
import api from '../api'
import MemberInvite from './MemberInvite.vue'
import { useAuthStore } from '../stores/auth'

const props = defineProps({
  show:             { type: Boolean, default: false },
  meetings:         { type: Array,   default: () => [] },
  lockedUserId:     { type: Number,  default: null },
  initialMeetingId: { type: [Number, String], default: null },
})
const emit = defineEmits(['close', 'saved'])

const authStore = useAuthStore()

const form = ref({ title: '', location: '', dateOnly: '', timeOnly: '', meeting_id: null, context: '' })
const members = ref([])
const creating = ref(false)
const showPastDateAlert = ref(false)

function toNumericId(id) {
  if (!id && id !== 0) return 0
  if (typeof id === 'number') return id
  const m = String(id).match(/(\d+)$/)
  return m ? parseInt(m[1], 10) : 0
}

watch(() => props.show, (v) => {
  if (!v) return
  form.value = {
    title: '', location: '', dateOnly: '', timeOnly: '',
    meeting_id: props.initialMeetingId ? toNumericId(props.initialMeetingId) : null,
    context: '',
  }
  const me = authStore.user
  members.value = me ? [{ userId: me.id, name: me.name, email: me.email, role: 'admin' }] : []
  showPastDateAlert.value = false
})

const canSubmit = computed(() => {
  const f = form.value
  return !creating.value && f.title.trim() && f.location.trim() && f.dateOnly && f.meeting_id && members.value.length > 0
})

async function doCreate() {
  if (!canSubmit.value) return
  const f = form.value
  const scheduled = new Date(`${f.dateOnly}T${f.timeOnly || '00:00'}`)
  if (scheduled < new Date()) { showPastDateAlert.value = true; return }
  creating.value = true
  try {
    await api.post(`/api/v1/meetings/${f.meeting_id}/sessions`, {
      title:        f.title,
      location:     f.location || null,
      scheduled_at: `${f.dateOnly}T${f.timeOnly || '00:00'}:00`,
      type:         'localwhisper',
      context:      f.context || null,
      attendees:    members.value.map(m => ({ user_id: m.userId, role: m.role || 'member' })),
    })
    emit('saved', { meetingId: f.meeting_id })
    emit('close')
  } catch (e) {
    alert(e.response?.data?.message || '생성 실패')
  } finally {
    creating.value = false
  }
}
</script>

<template>
  <Teleport to="body">
    <div v-if="show" class="app-modal-backdrop">
      <div class="app-modal app-modal-sm">
        <div class="app-modal-header">
          <span class="app-modal-title">회의 생성</span>
          <button class="app-modal-close" @click="emit('close')">
            <svg width="14" height="14" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24"><path d="M6 18L18 6M6 6l12 12"/></svg>
          </button>
        </div>
        <div class="app-modal-body">
          <div class="app-modal-field">
            <label>회의체 <span class="req">*</span></label>
            <select v-model="form.meeting_id" class="app-modal-input">
              <option :value="null" disabled>회의체를 선택하세요</option>
              <option v-for="m in meetings" :key="toNumericId(m.id)" :value="toNumericId(m.id)">{{ m.title }}</option>
            </select>
          </div>
          <div class="app-modal-field">
            <label>회의명 <span class="req">*</span></label>
            <input v-model="form.title" class="app-modal-input" placeholder="예: 2026 전략 수립 1차" />
          </div>
          <div class="app-modal-field">
            <label>장소 <span class="req">*</span></label>
            <input v-model="form.location" class="app-modal-input" placeholder="예: SK U Tower 8층" />
          </div>
          <div class="app-modal-field">
            <label>회의 날짜 <span class="req">*</span></label>
            <div class="datetime-split-input">
              <input type="date" v-model="form.dateOnly" class="datetime-split-date" @change="showPastDateAlert=false" />
              <span class="datetime-split-sep"></span>
              <input type="text" v-model="form.timeOnly" class="datetime-split-time" placeholder="HH:MM" maxlength="5" @input="showPastDateAlert=false" />
            </div>
            <p v-if="showPastDateAlert" style="color:#ef4444;font-size:12px;margin-top:4px;margin-bottom:0">현재 시간 이후로 설정해주세요.</p>
          </div>
          <div class="app-modal-field">
            <label>회의 맥락</label>
            <textarea v-model="form.context" class="app-modal-input context-modal-textarea" rows="4"
              placeholder="대화 상황, 주제, 고유명사 등 회의와 관련된 맥락을 입력하면 AI 응답 정확도가 높아져요.&#10;예: 분기별 성과 검토 회의, 주요 KPI: 전환율·CAC, 팀: 마케팅/영업/기획"></textarea>
          </div>
          <div class="app-modal-field">
            <MemberInvite v-model="members" :lockedUserId="lockedUserId" />
          </div>
        </div>
        <div class="app-modal-footer">
          <button class="app-btn-cancel" @click="emit('close')">취소</button>
          <button class="app-btn-primary" :disabled="!canSubmit" @click="doCreate">
            {{ creating ? '생성 중...' : '생성' }}
          </button>
        </div>
      </div>
    </div>
  </Teleport>
</template>
