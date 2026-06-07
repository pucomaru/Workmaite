<script setup>
import { inject } from 'vue'
import MemberInvite from './MemberInvite.vue'
const { showSessionModal, nightMode, sessionForm, sessionMembers, creatingSession, doCreateSession } = inject('archiveModals')
</script>

<template>
  <Teleport to="body">
    <div v-if="showSessionModal" class="app-modal-backdrop">
      <div class="app-modal app-modal-md" :class="{ dark: nightMode }">
        <div class="app-modal-header">
          <span class="app-modal-title">회의 생성</span>
          <button class="app-modal-close" @click="showSessionModal=false">
            <svg width="14" height="14" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24"><path d="M6 18L18 6M6 6l12 12"/></svg>
          </button>
        </div>
        <div class="app-modal-body">
          <div class="app-modal-field">
            <label>회의명 <span class="req">*</span></label>
            <input v-model="sessionForm.title" class="app-modal-input" placeholder="예: 2025 전략 수립 1차" />
          </div>
          <div class="app-modal-field">
            <label>회의 소개</label>
            <textarea v-model="sessionForm.purpose" class="app-modal-input" placeholder="이번 회의의 목적이나 주요 내용..." rows="2"></textarea>
          </div>
          <div class="app-modal-field">
            <label>회의 날짜</label>
            <input type="datetime-local" v-model="sessionForm.date" class="app-modal-input" />
          </div>
          <div v-if="sessionForm.meeting_id" class="app-modal-field">
            <label>연결된 회의체</label>
            <div class="app-modal-input" style="background:var(--bg2);color:var(--text2);cursor:default">
              {{ sessionForm.meeting_id }}
            </div>
          </div>
          <div class="app-modal-field">
            <label>구성원</label>
            <MemberInvite v-model="sessionMembers" />
          </div>
        </div>
        <div class="app-modal-footer">
          <button class="app-btn-cancel" @click="showSessionModal=false">취소</button>
          <button class="app-btn-primary" :disabled="creatingSession||!sessionForm.title.trim()" @click="doCreateSession">{{ creatingSession ? '생성 중...' : '생성' }}</button>
        </div>
      </div>
    </div>
  </Teleport>
</template>
