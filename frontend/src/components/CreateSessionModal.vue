<script setup>
import { ref, computed, watch } from 'vue'
import { toast } from '../composables/useToast'
import api from '../api'
import DateInput from './DateInput.vue'
import MemberInvite from './MemberInvite.vue'
import { useAuthStore } from '../stores/auth'

const props = defineProps({
  show: { type: Boolean, default: false },
  meetings: { type: Array, default: () => [] },
  lockedUserId: { type: Number, default: null },
  initialMeetingId: { type: [Number, String], default: null },
  initialAgendaId: { type: [Number, String], default: null },
})
const emit = defineEmits(['close', 'saved'])

const authStore = useAuthStore()

const form = ref({
  title: '',
  location: '',
  dateOnly: '',
  timeOnly: '',
  meeting_id: null,
  context: '',
})
const members = ref([])
const creating = ref(false)
const showPastDateAlert = ref(false)
const showTimePicker = ref(false)
const timePickerListEl = ref(null)
const agendas = ref([])
const selectedAgendaIds = ref([])
const showAgendaDropdown = ref(false)

// 종료된 회의체는 회의 생성 불가 — 템플릿/검증/초기화 공통 소스 (누락 시 ReferenceError였음)
const availableMeetings = computed(() => (props.meetings || []).filter(m => m.status !== 'ended'))

function selectTime(t) {
  form.value.timeOnly = t
  showTimePicker.value = false
  showPastDateAlert.value = false
}

watch(showTimePicker, v => {
  if (!v) return
  setTimeout(() => {
    if (!timePickerListEl.value) return
    const idx = timeOptions.value.indexOf(form.value.timeOnly)
    if (idx < 0) return
    const itemHeight = timePickerListEl.value.scrollHeight / timeOptions.value.length
    timePickerListEl.value.scrollTop = Math.max(0, idx * itemHeight - 85)
  }, 0)
})

function toNumericId(id) {
  if (!id && id !== 0) return 0
  if (typeof id === 'number') return id
  const m = String(id).match(/(\d+)$/)
  return m ? parseInt(m[1], 10) : 0
}

// 회의체에서 현재 사용자의 역할(간사=admin / 참여자=member)을 자동 판별 — 회의 생성 시 role 수동선택 불필요
function resolveMyRole(meetingId) {
  if (!meetingId) return 'member'
  const mg = (props.meetings || []).find(m => toNumericId(m.id) === toNumericId(meetingId))
  return mg?.my_role === 'admin' ? 'admin' : 'member'
}

watch(
  () => props.show,
  async v => {
    if (!v) return
    const now = new Date()
    const minutes = now.getMinutes() < 30 ? 30 : 0
    const hours = minutes === 0 ? now.getHours() + 1 : now.getHours()
    const safeHours = hours > 22 ? 22 : hours < 8 ? 8 : hours
    // 종료된 회의체가 initialMeetingId로 들어와도 선택되지 않게 한다(선택지에 없으므로).
    const initId = props.initialMeetingId ? toNumericId(props.initialMeetingId) : null
    const initSelectable = availableMeetings.value.some(m => toNumericId(m.id) === initId)
    form.value = {
      title: '',
      location: '',
      dateOnly: '',
      timeOnly: `${String(safeHours).padStart(2, '0')}:${String(minutes).padStart(2, '0')}`,
      meeting_id: initSelectable ? initId : null,
      context: '',
    }
    const me = authStore.user
    members.value = me
      ? [
          {
            userId: me.id,
            name: me.name,
            email: me.email,
            role: resolveMyRole(form.value.meeting_id),
          },
        ]
      : []
    showPastDateAlert.value = false
    agendas.value = []
    selectedAgendaIds.value = []
    showAgendaDropdown.value = false
    if (form.value.meeting_id) {
      await loadAgendas(form.value.meeting_id)
      // 드래그로 아젠다에서 시작한 경우 해당 아젠다를 '논의 아젠다'로 자동 선택
      if (props.initialAgendaId != null) {
        const match = agendas.value.find(a => String(a.id) === String(props.initialAgendaId))
        if (match) selectedAgendaIds.value = [match.id]
      }
    }
  },
)

watch(
  () => form.value.meeting_id,
  async id => {
    agendas.value = []
    selectedAgendaIds.value = []
    showAgendaDropdown.value = false
    // 회의체가 바뀌면 생성자(나)의 role을 해당 회의체에서의 역할(간사/참여자)로 자동 갱신
    const me = authStore.user
    if (me) {
      const myRole = resolveMyRole(id)
      members.value = members.value.map(m => (m.userId === me.id ? { ...m, role: myRole } : m))
    }
    if (id) await loadAgendas(id)
  },
)

async function loadAgendas(meetingId) {
  try {
    const { data } = await api.get(`/api/v1/meetings/${meetingId}/agendas`)
    const raw = data.data ?? data
    const seen = new Set()
    agendas.value = raw.filter(a => {
      if (seen.has(a.id)) return false
      seen.add(a.id)
      return true
    })
  } catch (e) {
    console.error('[agendas] 로드 실패:', e)
    agendas.value = []
  }
}

function clampDateYear(e) {
  const val = e.target.value
  if (!val) return
  const parts = val.split('-')
  if (parts[0] && parts[0].length > 4) {
    parts[0] = parts[0].slice(0, 4)
    form.value.dateOnly = parts.join('-')
  }
}

const timeOptions = computed(() => {
  const options = []
  for (let h = 8; h <= 22; h++) {
    for (let m of [0, 30]) {
      const hh = String(h).padStart(2, '0')
      const mm = String(m).padStart(2, '0')
      options.push(`${hh}:${mm}`)
    }
  }
  return options
})

const errors = ref({})

function validate() {
  const f = form.value
  const e = {}
  if (!f.meeting_id) e.meeting_id = '회의체를 선택해주세요'
  else if (!availableMeetings.value.some(m => toNumericId(m.id) === f.meeting_id))
    e.meeting_id = '종료된 회의체에는 회의를 생성할 수 없습니다'
  if (!f.title.trim()) e.title = '회의명을 입력해주세요'
  if (!f.location.trim()) e.location = '장소를 입력해주세요'
  if (!f.dateOnly) e.dateOnly = '날짜를 선택해주세요'
  if (!members.value.length) e.members = '참여자를 추가해주세요'
  errors.value = e
  return Object.keys(e).length === 0
}

async function doCreate() {
  if (!validate()) return
  const f = form.value
  const scheduled = new Date(`${f.dateOnly}T${f.timeOnly || '00:00'}`)
  if (scheduled < new Date()) {
    showPastDateAlert.value = true
    return
  }
  creating.value = true
  try {
    const { data } = await api.post(`/api/v1/meetings/${f.meeting_id}/sessions`, {
      title: f.title,
      location: f.location || null,
      scheduled_at: `${f.dateOnly}T${f.timeOnly || '00:00'}:00`,
      type: 'gpt-realtime-whisper',
      context: f.context || null,
      attendees: members.value.map(m => ({ user_id: m.userId, role: m.role || 'member' })),
      agenda_ids: selectedAgendaIds.value.length ? selectedAgendaIds.value : null,
    })
    // 생성된 세션 id를 함께 전달 — 호출부가 해당 세션으로 바로 이동/선택할 수 있게.
    const created = data?.data ?? data
    emit('saved', { meetingId: f.meeting_id, sessionId: created?.id ?? null })
    emit('close')
  } catch (e) {
    toast.error(e.response?.data?.message || '생성 실패')
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
            <label for="create-meeting">주관 회의체 <span class="req">*</span></label>
            <select
              id="create-meeting"
              name="meeting_id"
              v-model="form.meeting_id"
              class="app-modal-input"
              @change="errors.meeting_id = null"
            >
              <option :value="null" disabled>회의체를 선택하세요</option>
              <option
                v-for="m in availableMeetings"
                :key="toNumericId(m.id)"
                :value="toNumericId(m.id)"
              >
                {{ m.title }}
              </option>
            </select>
            <p v-if="errors.meeting_id" class="field-error">{{ errors.meeting_id }}</p>
          </div>
          <div class="app-modal-field">
            <label for="session-create-title">회의명 <span class="req">*</span></label>
            <input
              id="session-create-title"
              name="title"
              v-model="form.title"
              class="app-modal-input"
              placeholder="예: 2026 전략 수립 1차"
              @input="errors.title = null"
            />
            <p v-if="errors.title" class="field-error">{{ errors.title }}</p>
          </div>
          <div class="app-modal-field">
            <label for="create-location">장소 <span class="req">*</span></label>
            <input
              id="create-location"
              name="location"
              v-model="form.location"
              class="app-modal-input"
              placeholder="예: SK U Tower 8층"
              @input="errors.location = null"
            />
            <p v-if="errors.location" class="field-error">{{ errors.location }}</p>
          </div>
          <div class="app-modal-field">
            <label for="create-date">회의 날짜 <span class="req">*</span></label>
            <div style="display: flex; gap: 8px; align-items: center">
              <DateInput
                id="create-date"
                name="date"
                v-model="form.dateOnly"
                class="app-modal-input"
                style="flex: 1"
                @update:modelValue="showPastDateAlert = false; errors.dateOnly = null"
              />
              <div style="position: relative; width: 110px">
                <div
                  v-if="showTimePicker"
                  style="position: fixed; inset: 0; z-index: 1001"
                  @click="showTimePicker = false"
                ></div>
                <div
                  class="app-modal-input"
                  style="
                    cursor: pointer;
                    display: flex;
                    align-items: center;
                    justify-content: space-between;
                    user-select: none;
                  "
                  @click.stop="showTimePicker = !showTimePicker"
                >
                  <span>{{ form.timeOnly || '시간 선택' }}</span>
                  <svg
                    width="10"
                    height="10"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    stroke-width="2.5"
                  >
                    <path d="M6 9l6 6 6-6" />
                  </svg>
                </div>
                <div
                  v-if="showTimePicker"
                  ref="timePickerListEl"
                  style="
                    position: absolute;
                    top: calc(100% + 4px);
                    left: 0;
                    z-index: 1002;
                    background: var(--bg-card, #fff);
                    border: 1px solid var(--border, #e5e7eb);
                    border-radius: 6px;
                    max-height: 140px;
                    overflow-y: auto;
                    width: 100%;
                    box-shadow: 0 4px 16px rgba(0, 0, 0, 0.12);
                  "
                >
                  <div
                    v-for="t in timeOptions"
                    :key="t"
                    @click.stop="selectTime(t)"
                    :style="{
                      padding: '6px 12px',
                      cursor: 'pointer',
                      fontSize: '12px',
                      background: form.timeOnly === t ? 'var(--primary, #6366f1)' : 'transparent',
                      color: form.timeOnly === t ? '#fff' : 'inherit',
                    }"
                  >
                    {{ t }}
                  </div>
                </div>
              </div>
            </div>
            <p v-if="errors.dateOnly" class="field-error">{{ errors.dateOnly }}</p>
            <p v-else-if="showPastDateAlert" class="field-error">현재 시간 이후로 설정해주세요.</p>
          </div>
          <div class="app-modal-field">
            <label for="create-context">회의 맥락</label>
            <textarea
              id="create-context"
              name="context"
              v-model="form.context"
              class="app-modal-input context-modal-textarea"
              rows="4"
              placeholder="대화 상황, 주제, 고유명사 등 회의와 관련된 맥락을 입력하면 AI 응답 정확도가 높아져요.&#10;예: 분기별 성과 검토 회의, 주요 KPI: 전환율·CAC, 팀: 마케팅/영업/기획"
            ></textarea>
          </div>
          <div class="app-modal-field">
            <span class="app-modal-label">논의 아젠다</span>
            <div style="position: relative">
              <div
                class="app-modal-input"
                role="button"
                tabindex="0"
                :style="{ cursor: agendas.length ? 'pointer' : 'default' }"
                style="
                  display: flex;
                  align-items: center;
                  justify-content: space-between;
                  user-select: none;
                "
                @click="agendas.length && (showAgendaDropdown = !showAgendaDropdown)"
              >
                <span style="color: #9ca3af">
                  {{
                    !form.meeting_id
                      ? '회의체를 먼저 선택하세요'
                      : !agendas.length
                        ? '등록된 안건이 없습니다'
                        : selectedAgendaIds.length
                          ? `${selectedAgendaIds.length}개 선택됨`
                          : '안건을 선택하세요'
                  }}
                </span>
                <svg
                  v-if="agendas.length"
                  width="10"
                  height="10"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  stroke-width="2.5"
                >
                  <path d="M6 9l6 6 6-6" />
                </svg>
              </div>
              <div
                v-if="showAgendaDropdown && agendas.length"
                style="position: fixed; inset: 0; z-index: 1001"
                @click="showAgendaDropdown = false"
              ></div>
              <div
                v-if="showAgendaDropdown && agendas.length"
                style="
                  position: absolute;
                  top: calc(100% + 4px);
                  left: 0;
                  right: 0;
                  z-index: 1002;
                  background: var(--bg-card, #fff);
                  border: 1px solid var(--border, #e5e7eb);
                  border-radius: 6px;
                  max-height: 160px;
                  overflow-y: auto;
                  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.12);
                "
              >
                <label
                  v-for="agenda in agendas.filter(
                    a => a.status === 'ongoing' || a.status === 'done',
                  )"
                  :key="agenda.id"
                  style="
                    display: flex;
                    align-items: center;
                    gap: 8px;
                    padding: 8px 12px;
                    cursor: pointer;
                    font-size: 12px;
                  "
                >
                  <input
                    type="checkbox"
                    :value="agenda.id"
                    v-model="selectedAgendaIds"
                    style="width: 14px; height: 14px; cursor: pointer"
                  />
                  <span>{{ agenda.title }}</span>
                </label>
              </div>
            </div>
          </div>
          <div class="app-modal-field">
            <MemberInvite v-model="members" :lockedUserId="lockedUserId" :hideRole="true" />
          </div>
        </div>
        <div class="app-modal-footer">
          <button class="app-btn-cancel" @click="emit('close')">취소</button>
          <button class="app-btn-primary" :disabled="creating" @click="doCreate">
            {{ creating ? '생성 중...' : '생성' }}
          </button>
        </div>
      </div>
    </div>
  </Teleport>
</template>
