<script setup>
import { ref, watch } from 'vue'
import DateInput from './DateInput.vue'

const props = defineProps({
  modal: Object,   // { form: { title, department, due_date, priority }, saving }
  nightMode: Boolean,
  saving: Boolean,
})
const emit = defineEmits(['close', 'save'])

const PRIORITY_OPTIONS = [
  { value: 'critical', label: '^^  최상 (Critical)', color: '#ef4444' },
  { value: 'high',     label: '^   상 (High)',       color: '#f97316' },
  { value: 'medium',   label: '-   중 (Medium)',     color: '#f59e0b' },
  { value: 'low',      label: 'v   하 (Low)',        color: '#10b981' },
  { value: 'minimal',  label: 'vv  최하 (Minimal)',  color: '#6b7280' },
]

const STATUS_OPTIONS = [
  { value: 'pending', label: '대기' },
  { value: 'ongoing', label: '진행중' },
  { value: 'done',    label: '완료' },
]

function priorityColor(val) {
  return PRIORITY_OPTIONS.find(p => p.value === val)?.color ?? '#6b7280'
}
</script>

<template>
  <Teleport to="body">
    <div v-if="modal" class="app-modal-backdrop" @click.self="emit('close')">
      <div class="app-modal agenda-edit-modal" :class="{ dark: nightMode }">
        <!-- Header -->
        <div class="app-modal-header">
          <span class="app-modal-title">아젠다 편집</span>
          <button class="app-modal-close" @click="emit('close')">
            <svg width="14" height="14" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24"><path d="M6 18L18 6M6 6l12 12"/></svg>
          </button>
        </div>

        <!-- Body -->
        <div class="app-modal-body">
          <!-- 제목 -->
          <div class="app-modal-field">
            <label>아젠다 제목 <span class="req">*</span></label>
            <input v-model="modal.form.title" class="app-modal-input" placeholder="아젠다 제목을 입력하세요" />
          </div>

          <!-- 담당부서 + 우선순위 한 행 -->
          <div class="app-modal-field-row">
            <div class="app-modal-field">
              <label>담당 부서</label>
              <input v-model="modal.form.department" class="app-modal-input" placeholder="예: 전략기획팀" />
            </div>
            <div class="app-modal-field">
              <label>우선순위</label>
              <select v-model="modal.form.priority" class="app-modal-input priority-select"
                :style="{ borderLeftColor: priorityColor(modal.form.priority), borderLeftWidth: '3px' }">
                <option v-for="p in PRIORITY_OPTIONS" :key="p.value" :value="p.value">{{ p.label }}</option>
              </select>
            </div>
          </div>

          <!-- 마감 + 상태 한 행 -->
          <div class="app-modal-field-row">
            <div class="app-modal-field">
              <label>마감일</label>
              <DateInput v-model="modal.form.due_date" class="app-modal-input" />
            </div>
            <div class="app-modal-field">
              <label>상태</label>
              <select v-model="modal.form.status" class="app-modal-input">
                <option v-for="s in STATUS_OPTIONS" :key="s.value" :value="s.value">{{ s.label }}</option>
              </select>
            </div>
          </div>
        </div>

        <!-- Footer -->
        <div class="app-modal-footer">
          <button class="app-btn-cancel" @click="emit('close')">취소</button>
          <button class="app-btn-primary"
            :disabled="!modal.form.title?.trim() || saving"
            @click="emit('save')">
            {{ saving ? '저장 중...' : '저장' }}
          </button>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.agenda-edit-modal { max-width: 480px; width: 100%; }

/* 우선순위 select 색상 힌트 */
.priority-select { padding-left: 10px; }

/* Dark mode */
</style>
