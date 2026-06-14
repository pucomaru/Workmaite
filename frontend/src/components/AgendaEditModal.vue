<script setup>
import { computed } from 'vue'
import DateInput from './DateInput.vue'
import DeptSelect from './DeptSelect.vue'

const props = defineProps({
  modal: Object, // { form: { title, department(배열), due_date, priority }, saving }
  nightMode: Boolean,
  saving: Boolean,
  deptOptions: { type: Array, default: () => [] }, // 검색 가능한 부서명 목록
})
const emit = defineEmits(['close', 'save', 'delete'])

// 부모 소유 편집 draft를 로컬 별칭으로 in-place 편집 (동일 참조)
const form = computed(() => props.modal?.form || {})

const PRIORITY_OPTIONS = [
  { value: 'critical', label: '최상', color: '#ef4444' },
  { value: 'high', label: '상', color: '#f97316' },
  { value: 'medium', label: '중', color: '#f59e0b' },
  { value: 'low', label: '하', color: '#10b981' },
  { value: 'minimal', label: '최하', color: '#6b7280' },
]

const STATUS_OPTIONS = [
  { value: 'pending', label: '대기' },
  { value: 'ongoing', label: '진행중' },
  { value: 'done', label: '완료' },
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

        <!-- Body -->
        <div class="app-modal-body">
          <!-- 제목 -->
          <div class="app-modal-field">
            <label>아젠다 제목 <span class="req">*</span></label>
            <input
              v-model="form.title"
              class="app-modal-input"
              placeholder="아젠다 제목을 입력하세요"
            />
          </div>



          <!-- 우선순위 + 상태 한 행 -->
          <div class="app-modal-field-row">
            <div class="app-modal-field">
              <label>우선순위</label>
              <select
                v-model="form.priority"
                class="app-modal-input priority-select"
                :style="{ borderLeftColor: priorityColor(form.priority), borderLeftWidth: '3px' }"
              >
                <option v-for="p in PRIORITY_OPTIONS" :key="p.value" :value="p.value">
                  {{ p.label }}
                </option>
              </select>
            </div>
            <div class="app-modal-field">
              <label>상태</label>
              <select v-model="form.status" class="app-modal-input">
                <option v-for="s in STATUS_OPTIONS" :key="s.value" :value="s.value">
                  {{ s.label }}
                </option>
              </select>
            </div>

            <!-- 마감일 -->
            <div class="app-modal-field">
              <label>마감일</label>
              <DateInput v-model="form.due_date" class="app-modal-input" />
            </div>
          </div>
            <!-- 참여 부서 (검색 다중선택) — 회의체 편집의 참여자 mi-section과 동일 UX -->
            <div class="app-modal-field">
              <DeptSelect
                v-model="form.department"
                :options="deptOptions"
                :night-mode="nightMode"
              />
            </div>
            
          </div>

        <!-- Footer -->
        <div class="app-modal-footer agenda-footer">
          <button class="app-btn-danger" @click="emit('delete')">삭제</button>
          <div class="footer-right">
            <button class="app-btn-cancel" @click="emit('close')">취소</button>
            <button
              class="app-btn-primary"
              :disabled="!form.title?.trim() || saving"
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
.agenda-edit-modal {
  max-width: 480px;
  width: 100%;
}

.priority-select {
  padding-left: 10px;
}

.agenda-footer {
  justify-content: space-between !important;
}
.footer-right {
  display: flex;
  gap: 8px;
}
</style>
