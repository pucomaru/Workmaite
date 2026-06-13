<script setup>
import { computed } from 'vue'
import DateInput from './DateInput.vue'
import MemberInvite from './MemberInvite.vue'

const props = defineProps({
  settings: Object, // { form, members, removedIds, meeting }
  nightMode: Boolean,
  saving: Boolean,
})
const emit = defineEmits(['close', 'save', 'delete'])

// 부모가 소유한 편집용 draft 객체를 로컬 별칭으로 받아 in-place 편집한다.
// (저장 시 부모가 같은 객체를 되읽는 구조 — 동일 참조이므로 동작 동일)
const form = computed(() => props.settings?.form || {})

function onMembersUpdate(newList) {
  const s = props.settings
  if (!s) return
  const removed = s.members.find(old => !newList.find(n => n.userId === old.userId))
  if (removed?.id) s.removedIds.push(removed.id)
  s.members = newList
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
            <label>회의체명 <span class="req">*</span></label>
            <input v-model="form.title" class="app-modal-input" />
          </div>
          <div class="app-modal-field">
            <label>소개</label>
            <textarea
              v-model="form.purpose"
              class="app-modal-input"
              rows="2"
              placeholder="이 회의체의 목적이나 소개..."
            ></textarea>
          </div>
          <div class="app-modal-field">
            <label>유형</label>
            <select v-model="form.meeting_type" class="app-modal-input">
              <option value="Weekly">Weekly</option>
              <option value="Monthly">Monthly</option>
              <option value="Quarterly">Quarterly</option>
            </select>
          </div>
          <div class="app-modal-field-row">
            <div class="app-modal-field">
              <label>시작일</label>
              <DateInput v-model="form.start_date" class="app-modal-input" />
            </div>
            <div class="app-modal-field">
              <label>종료일</label>
              <DateInput v-model="form.end_date" class="app-modal-input" />
            </div>
          </div>
          <div class="app-modal-field">
            <label>회의체 지침</label>
            <textarea
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
          <button class="app-btn-danger" @click="emit('delete')">삭제</button>
          <div class="footer-right">
            <button class="app-btn-cancel" @click="emit('close')">취소</button>
            <button
              class="app-btn-primary"
              :disabled="!form.title.trim() || saving"
              @click="emit('save')"
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
