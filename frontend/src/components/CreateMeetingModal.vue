<script setup>
import { inject } from 'vue'
import MemberInvite from './MemberInvite.vue'
import { useAuthStore } from '../stores/auth'
const { showCreateModal, nightMode, createForm, creating, doCreateMeeting, createMembers } =
  inject('archiveModals')
const authStore = useAuthStore()
</script>

<template>
  <Teleport to="body">
    <div v-if="showCreateModal" class="app-modal-backdrop">
      <div class="app-modal app-modal-md" :class="{ dark: nightMode }">
        <div class="app-modal-header">
          <span class="app-modal-title">회의체 생성</span>
          <button class="app-modal-close" @click="showCreateModal = false">
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
            <label for="create-title">회의체명 <span class="req">*</span></label>
            <input
              id="create-title"
              name="title"
              v-model="createForm.title"
              class="app-modal-input"
              placeholder="예: 전략기획위원회"
            />
          </div>
          <div class="app-modal-field">
            <label for="create-purpose">소개</label>
            <textarea
              id="create-purpose"
              name="purpose"
              v-model="createForm.purpose"
              class="app-modal-input"
              placeholder="이 회의체의 목적이나 소개..."
              rows="2"
            ></textarea>
          </div>
          <div class="app-modal-field">
            <label for="create-meeting-type">유형</label>
            <select
              id="create-meeting-type"
              name="meeting_type"
              v-model="createForm.meeting_type"
              class="app-modal-input"
            >
              <option value="Weekly">Weekly</option>
              <option value="Monthly">Monthly</option>
              <option value="Quarterly">Quarterly</option>
            </select>
          </div>
          <div class="app-modal-field-row">
            <div class="app-modal-field">
              <label for="create-start-date">시작일</label>
              <input
                id="create-start-date"
                name="start_date"
                type="date"
                v-model="createForm.start_date"
                min="1000-01-01"
                max="9999-12-31"
                class="app-modal-input"
              />
            </div>
            <div class="app-modal-field">
              <label for="create-end-date">종료일</label>
              <input
                id="create-end-date"
                name="end_date"
                type="date"
                v-model="createForm.end_date"
                min="1000-01-01"
                max="9999-12-31"
                class="app-modal-input"
              />
            </div>
          </div>
          <div class="app-modal-field">
            <label for="create-guidelines">운영 지침</label>
            <textarea
              id="create-guidelines"
              name="guidelines"
              v-model="createForm.guidelines"
              class="app-modal-input"
              rows="3"
              placeholder="운영 지침, 규칙, 주의사항 등을 입력하세요...
예: 매주 월요일 10시, 의장 승인 필수, 안건 72시간 전 제출 등"
            ></textarea>
          </div>
          <div class="app-modal-field">
            <MemberInvite v-model="createMembers" :lockedUserId="authStore.user?.id" />
          </div>
        </div>
        <div class="app-modal-footer">
          <button class="app-btn-cancel" @click="showCreateModal = false">취소</button>
          <button
            class="app-btn-primary"
            :disabled="creating || !createForm.title.trim()"
            @click="doCreateMeeting"
          >
            {{ creating ? '생성 중...' : '생성' }}
          </button>
        </div>
      </div>
    </div>
  </Teleport>
</template>
