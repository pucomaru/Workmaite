<script setup>
import { inject } from 'vue'
const {
  loading,
  viewMode,
  openCreateModal,
  onFloatBtnMouseDown,
  openSessionModal,
  openUploadModal,
} = inject('archiveCanvas')
</script>

<template>
  <div v-if="!loading && viewMode === 'graph'" class="graph-float-btns">
    <div
      class="float-btn-item"
      @click="openCreateModal"
      @mousedown.prevent="onFloatBtnMouseDown('meeting', $event)"
      title="클릭 또는 드래그해서 회의체 생성"
    >
      <div class="float-node-preview meeting-preview">
        <svg
          width="24"
          height="24"
          fill="none"
          stroke="currentColor"
          stroke-width="1.5"
          viewBox="0 0 24 24"
        >
          <circle cx="12" cy="5" r="2" />
          <circle cx="19" cy="17" r="2" />
          <circle cx="5" cy="17" r="2" />
          <circle cx="12" cy="12" r="2" />
          <line x1="12" y1="7" x2="12" y2="10" />
          <line x1="12" y1="14" x2="17.4" y2="15.6" />
          <line x1="12" y1="14" x2="6.6" y2="15.6" />
        </svg>
      </div>
      <span class="float-btn-label">회의체 생성</span>
    </div>
    <div
      class="float-btn-item"
      @click="openUploadModal()"
      @mousedown.prevent="onFloatBtnMouseDown('doc', $event)"
      title="클릭 또는 드래그해서 자료 업로드"
    >
      <div class="float-node-preview doc-preview">
        <svg
          width="21"
          height="21"
          fill="none"
          stroke="currentColor"
          stroke-width="1.5"
          viewBox="0 0 24 24"
        >
          <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z" />
          <polyline points="14 2 14 8 20 8" />
          <line x1="8" y1="13" x2="16" y2="13" />
          <line x1="8" y1="17" x2="16" y2="17" />
        </svg>
      </div>
      <span class="float-btn-label">보고서 검토</span>
    </div>

    <div
      class="float-btn-item"
      @click="openSessionModal()"
      @mousedown.prevent="onFloatBtnMouseDown('session', $event)"
      title="클릭 또는 드래그해서 회의 생성"
    >
      <div class="float-node-preview session-preview">
        <svg
          width="22"
          height="22"
          fill="none"
          stroke="currentColor"
          stroke-width="1.5"
          viewBox="0 0 24 24"
        >
          <path d="M12 1a3 3 0 00-3 3v8a3 3 0 006 0V4a3 3 0 00-3-3z" />
          <path d="M19 10v2a7 7 0 01-14 0v-2M12 19v4M8 23h8" />
        </svg>
      </div>
      <span class="float-btn-label">회의 생성</span>
    </div>
  </div>
</template>
