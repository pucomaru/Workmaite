<script setup>
import { computed } from 'vue'
import { toast } from '../composables/useToast'
import MemberInvite from './MemberInvite.vue'

const props = defineProps({
  settings: Object, // { form, members, removedIds, meeting }
  nightMode: Boolean,
  saving: Boolean,
})
const emit = defineEmits(['close', 'save', 'delete'])

const form = computed(() => props.settings?.form || {})

function onMembersUpdate(newList) {
  const s = props.settings
  if (!s) return
  const removed = s.members.find(old => !newList.find(n => n.userId === old.userId))
  if (removed?.id) s.removedIds.push(removed.id)
  s.members = newList
}

function handleSave() {
  if (
    form.value.start_date &&
    form.value.end_date &&
    form.value.end_date <= form.value.start_date
  ) {
    toast.error('종료일은 시작일보다 늦어야 합니다.')
    return
  }
  emit('save')
}
</script>

<template>
  <Teleport to="body">
    <div v-if="settings" class="app-modal-backdrop">
      <div class="app-modal app-modal-lg" :class="{ dark: nightMode }">
        <div class="app-modal-header">
          <span class="app-modal-title">회의체 설정</span>
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
            <label for="meeting-title">회의체명 <span class="req">*</span></label>
            <input id="meeting-title" name="title" v-model="form.title" class="app-modal-input" />
          </div>
          <div class="app-modal-field">
            <label for="meeting-purpose">소개</label>
            <textarea
              id="meeting-purpose"
              name="purpose"
              v-model="form.purpose"
              class="app-modal-input"
              rows="2"
              placeholder="이 회의체의 목적이나 소개..."
            ></textarea>
          </div>
          <div class="app-modal-field">
            <label for="meeting-type">유형</label>
            <select
              id="meeting-type"
              name="meeting_type"
              v-model="form.meeting_type"
              class="app-modal-input"
            >
              <option value="Weekly">Weekly</option>
              <option value="Monthly">Monthly</option>
              <option value="Quarterly">Quarterly</option>
            </select>
          </div>
          <div class="app-modal-field-row">
            <div class="app-modal-field">
              <label for="meeting-start-date">시작일</label>
              <input
                id="meeting-start-date"
                v-model="form.start_date"
                type="date"
                min="1000-01-01"
                max="9999-12-31"
                class="app-modal-input"
              />
            </div>
            <div class="app-modal-field">
              <label for="meeting-end-date">종료일</label>
              <input
                id="meeting-end-date"
                v-model="form.end_date"
                type="date"
                min="1000-01-01"
                max="9999-12-31"
                class="app-modal-input"
              />
            </div>
          </div>
          <div class="app-modal-field">
            <label for="meeting-guidelines">회의체 지침</label>
            <textarea
              id="meeting-guidelines"
              name="guidelines"
              v-model="form.guidelines"
              class="app-modal-input"
              rows="4"
              placeholder="운영 지침, 규칙, 주의사항 등을 입력하세요...&#10;예: 매주 월요일 10시, 의장 승인 필수, 안건 72시간 전 제출 등"
            ></textarea>
          </div>
          <MemberInvite
            :modelValue="settings.members"
            @update:modelValue="onMembersUpdate"
            :nightMode="nightMode"
          />
        </div>
        <div class="app-modal-footer modal-footer-split">
          <button class="app-btn-danger" :disabled="saving" @click="emit('delete')">삭제</button>
          <div class="footer-right">
            <button class="app-btn-cancel" @click="emit('close')">취소</button>
            <button
              class="app-btn-primary"
              :disabled="!form.title.trim() || saving"
              @click="handleSave"
            >
              {{ saving ? '저장 중...' : '저장' }}
            </button>
          </div>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.modal-footer-split {
  justify-content: space-between !important;
}
.footer-right {
  display: flex;
  gap: 8px;
}
</style>
