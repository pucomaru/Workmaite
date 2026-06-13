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
          width="16"
          height="16"
          fill="none"
          stroke="currentColor"
          stroke-width="2.5"
          viewBox="0 0 24 24"
        >
          <path d="M12 4v16m8-8H4" />
        </svg>
      </div>
      <span class="float-btn-label">회의체 생성</span>
    </div>
    <div
      class="float-btn-item"
      @click="openSessionModal()"
      @mousedown.prevent="onFloatBtnMouseDown('session', $event)"
      title="클릭 또는 드래그해서 회의 생성"
    >
      <div class="float-node-preview session-preview">
        <svg
          width="14"
          height="14"
          fill="none"
          stroke="currentColor"
          stroke-width="2"
          viewBox="0 0 24 24"
        >
          <path d="M12 1a3 3 0 00-3 3v8a3 3 0 006 0V4a3 3 0 00-3-3z" />
          <path d="M19 10v2a7 7 0 01-14 0v-2M12 19v4M8 23h8" />
        </svg>
      </div>
      <span class="float-btn-label">회의 생성</span>
    </div>
    <div
      class="float-btn-item"
      @click="openUploadModal()"
      @mousedown.prevent="onFloatBtnMouseDown('doc', $event)"
      title="클릭 또는 드래그해서 자료 업로드"
    >
      <div class="float-node-preview doc-preview">
        <svg
          width="16"
          height="16"
          fill="none"
          stroke="currentColor"
          stroke-width="2"
          viewBox="0 0 24 24"
        >
          <path d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12" />
        </svg>
      </div>
      <span class="float-btn-label">자료 업로드</span>
    </div>
  </div>
</template>
