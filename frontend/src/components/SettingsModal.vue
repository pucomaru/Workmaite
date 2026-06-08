<script setup>
import { inject } from 'vue'
const {
  settingsModal, nightMode, closeSettings,
  settingsSearchQ, watchSettingsSearch, settingsSearchLoading,
  settingsSearchResults, addMemberToSettings, avatarColor, initials,
  removeMemberFromSettings, ROLE_MAP, savingSettings, saveSettings,
} = inject('archiveModals')
</script>

<template>
  <Teleport to="body">
    <div v-if="settingsModal" class="app-modal-backdrop">
      <div class="app-modal app-modal-lg" :class="{ dark: nightMode }">
        <div class="app-modal-header">
          <span class="app-modal-title">회의체 설정</span>
          <button class="app-modal-close" @click="closeSettings">
            <svg width="14" height="14" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24"><path d="M6 18L18 6M6 6l12 12"/></svg>
          </button>
        </div>
        <div class="app-modal-body settings-body">
          <div class="settings-section">
            <div class="settings-section-title">기본 정보</div>
            <div class="app-modal-field">
              <label>회의체 이름 <span class="req">*</span></label>
              <input v-model="settingsModal.form.title" class="app-modal-input" />
            </div>
            <div class="app-modal-field">
              <label>소개</label>
              <textarea v-model="settingsModal.form.purpose" class="app-modal-input" rows="2" placeholder="이 회의체의 목적이나 소개..."></textarea>
            </div>
            <div class="app-modal-field">
              <label>회의체 지침</label>
              <textarea v-model="settingsModal.form.guidelines" class="app-modal-input" rows="4" placeholder="이 회의체의 운영 지침, 규칙, 주의사항 등을 입력하세요...&#10;예: 매주 월요일 10시, 의장 승인 필수, 안건 72시간 전 제출 등"></textarea>
            </div>
          </div>
          <div class="settings-section">
            <div class="settings-section-title">
              참여자 <span class="member-cnt-badge">{{ settingsModal.members.length }}명</span>
            </div>
            <div class="member-search-wrap">
              <svg width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><circle cx="11" cy="11" r="8"/><path d="M21 21l-4.35-4.35"/></svg>
              <input :value="settingsSearchQ" @input="watchSettingsSearch($event.target.value)" class="member-search-input" placeholder="이름 또는 이메일로 검색 후 추가..." />
              <span v-if="settingsSearchLoading" class="search-spinner">↻</span>
            </div>
            <div v-if="settingsSearchResults.length" class="member-search-results">
              <div v-for="u in settingsSearchResults" :key="u.id" class="member-search-item" @click="addMemberToSettings(u)">
                <div class="ui-avatar ui-avatar-sm" :style="{ background: avatarColor(u.name) }">{{ initials(u.name || u.email) }}</div>
                <div class="ms-info">
                  <span class="ms-name">{{ u.name || '이름없음' }}</span>
                  <span class="ms-email">{{ u.email }}</span>
                </div>
                <span class="ms-add-hint">+ 추가</span>
              </div>
            </div>
            <div class="settings-member-list">
              <div v-if="!settingsModal.members.length" class="settings-empty-members">참여자가 없습니다.</div>
              <div v-for="(mb, idx) in settingsModal.members" :key="mb.userId" class="settings-member-row">
                <div class="ui-avatar ui-avatar-sm" :style="{ background: avatarColor(mb.name) }">{{ initials(mb.name) }}</div>
                <div class="sm-info">
                  <span class="sm-name">{{ mb.name }}</span>
                  <span class="sm-email">{{ mb.position || mb.department || mb.email }}</span>
                </div>
                <select v-model="mb.role" class="app-select">
                  <option v-for="(label, val) in ROLE_MAP" :key="val" :value="val">{{ label }}</option>
                </select>
                <button class="sm-remove" @click="removeMemberFromSettings(idx)" title="제거">
                  <svg width="12" height="12" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24"><path d="M18 6L6 18M6 6l12 12"/></svg>
                </button>
              </div>
            </div>
          </div>
        </div>
        <div class="app-modal-footer">
          <button class="app-btn-cancel" @click="closeSettings">취소</button>
          <button class="app-btn-primary" :disabled="!settingsModal.form.title.trim() || savingSettings" @click="saveSettings">{{ savingSettings ? '저장 중...' : '저장' }}</button>
        </div>
      </div>
    </div>
  </Teleport>
</template>
