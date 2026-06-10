<script setup>
import DateInput from './DateInput.vue'
import MemberInvite from './MemberInvite.vue'

const props = defineProps({
  settings: Object,   // { form, members, removedIds, meeting }
  nightMode: Boolean,
  saving: Boolean,
})
const emit = defineEmits(['close', 'save'])

function onMembersUpdate(newList) {
  if (!props.settings) return
  const removed = props.settings.members.find(old => !newList.find(n => n.userId === old.userId))
  if (removed?.id) props.settings.removedIds.push(removed.id)
  props.settings.members = newList
}
</script>

<template>
  <Teleport to="body">
    <div v-if="settings" class="app-modal-backdrop">
      <div class="app-modal app-modal-lg" :class="{ dark: nightMode }">
        <div class="app-modal-header">
          <span class="app-modal-title">회의체 설정</span>
          <button class="app-modal-close" @click="emit('close')">
            <svg width="14" height="14" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24"><path d="M6 18L18 6M6 6l12 12"/></svg>
          </button>
        </div>
        <div class="app-modal-body settings-body">
          <!-- 기본 정보 -->
          <div class="settings-section">
            <div class="settings-section-title">기본 정보</div>
            <div class="app-modal-field">
              <label>회의체 이름 <span class="req">*</span></label>
              <input v-model="settings.form.title" class="app-modal-input" />
            </div>
            <div class="app-modal-field">
              <label>소개</label>
              <textarea v-model="settings.form.purpose" class="app-modal-input" rows="2" placeholder="이 회의체의 목적이나 소개..."></textarea>
            </div>
            <div class="app-modal-field">
              <label>유형</label>
              <select v-model="settings.form.meeting_type" class="app-modal-input">
                <option value="Weekly">Weekly</option>
                <option value="Monthly">Monthly</option>
                <option value="Quarterly">Quarterly</option>
              </select>
            </div>
            <div class="app-modal-field-row">
              <div class="app-modal-field">
                <label>시작일</label>
                <DateInput v-model="settings.form.start_date" class="app-modal-input" />
              </div>
              <div class="app-modal-field">
                <label>종료일</label>
                <DateInput v-model="settings.form.end_date" class="app-modal-input" />
              </div>
            </div>
            <div class="app-modal-field">
              <label>회의체 지침</label>
              <textarea v-model="settings.form.guidelines" class="app-modal-input" rows="4"
                placeholder="운영 지침, 규칙, 주의사항 등을 입력하세요...&#10;예: 매주 월요일 10시, 의장 승인 필수, 안건 72시간 전 제출 등"></textarea>
            </div>
          </div>

          <!-- 참여자 -->
          <MemberInvite
            :modelValue="settings.members"
            @update:modelValue="onMembersUpdate"
            :nightMode="nightMode"
          />
        </div>
        <div class="app-modal-footer">
          <button class="app-btn-cancel" @click="emit('close')">취소</button>
          <button class="app-btn-primary" :disabled="!settings.form.title.trim() || saving" @click="emit('save')">
            {{ saving ? '저장 중...' : '저장' }}
          </button>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.settings-body { gap: 0; }
.settings-section { padding: 14px 0; border-bottom: 1px solid var(--surface-2); display: flex; flex-direction: column; gap: 10px; }
.settings-section-title { font-size: 12px; font-weight: 700; color: var(--text-muted); text-transform: uppercase; letter-spacing: .05em; display: flex; align-items: center; gap: 8px; }
.req { color: var(--danger); }

/* Dark mode */
.app-modal.dark .settings-section { border-bottom-color: rgba(255,255,255,.07); }
.app-modal.dark .settings-section-title { color: var(--text-dim); }
</style>
