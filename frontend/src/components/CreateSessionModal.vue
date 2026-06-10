<script setup>
import { inject } from 'vue'
import MemberInvite from './MemberInvite.vue'

const {
  showSessionModal,
  nightMode,
  sessionForm,
  sessionMembers,
  creatingSession,
  doCreateSession,
  showPastDateAlert,
  meetingGroups,
} = inject('archiveModals')

function toNumericId(id) {
  if (!id && id !== 0) return 0
  if (typeof id === 'number') return id
  const m = String(id).match(/(\d+)$/)
  return m ? parseInt(m[1], 10) : 0
}
</script>

<template>
  <Teleport to="body">
    <div v-if="showSessionModal" class="app-modal-backdrop">
      <div class="app-modal app-modal-sm" :class="{ dark: nightMode }">
        <div class="app-modal-header">
          <span class="app-modal-title">회의 생성</span>
          <button class="app-modal-close" @click="showSessionModal=false">
            <svg width="14" height="14" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24"><path d="M6 18L18 6M6 6l12 12"/></svg>
          </button>
        </div>
        <div class="app-modal-body">
          <div class="app-modal-field">
            <label>회의체 <span style="color:#ef4444">*</span></label>
            <select v-model="sessionForm.meeting_id" class="app-modal-input">
              <option :value="null" disabled>회의체를 선택하세요</option>
              <option v-for="m in meetingGroups" :key="toNumericId(m.id)" :value="toNumericId(m.id)">{{ m.title }}</option>
            </select>
          </div>
          <div class="app-modal-field">
            <label>회의명 <span style="color:#ef4444">*</span></label>
            <input v-model="sessionForm.title" class="app-modal-input" placeholder="예: 2025 전략 수립 1차" />
          </div>
          <div class="app-modal-field">
            <label>회의 날짜</label>
            <div class="datetime-split-input">
              <input type="date" v-model="sessionForm.dateOnly" class="datetime-split-date" @change="showPastDateAlert=false" />
              <span class="datetime-split-sep"></span>
              <input type="text" v-model="sessionForm.timeOnly" class="datetime-split-time" placeholder="HH:MM" maxlength="5" @input="showPastDateAlert=false" />
            </div>
            <p v-if="showPastDateAlert" style="color:#ef4444;font-size:12px;margin-top:4px;margin-bottom:0">현재 시간 이후로 설정해주세요.</p>
          </div>
          <div class="app-modal-field">
            <label>STT 방식</label>
            <div style="display:flex;gap:8px;">
              <button
                :class="['stt-type-btn', sessionForm.type === 'whisper' ? 'active' : '']"
                @click="sessionForm.type = 'whisper'">
                Whisper 모델 (보안)
              </button>
              <button
                :class="['stt-type-btn', sessionForm.type === 'external' ? 'active' : '']"
                @click="sessionForm.type = 'external'">
                Whisper API (빠름)
              </button>
            </div>
          </div>
          <div class="app-modal-field">
            <label>참석자</label>
            <MemberInvite v-model="sessionMembers" />
          </div>
        </div>
        <div class="app-modal-footer">
          <button class="app-btn-cancel" @click="showSessionModal=false">취소</button>
          <button class="app-btn-primary" :disabled="creatingSession||!sessionForm.title.trim()||!sessionForm.meeting_id" @click="doCreateSession">
            {{ creatingSession ? '생성 중...' : '생성' }}
          </button>
        </div>
      </div>
    </div>
  </Teleport>
</template>
