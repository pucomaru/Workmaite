<script setup>
import { inject } from 'vue'
const { floatDragging, floatDragPos, floatDragPreviewLine } = inject('archiveCanvas')
</script>

<template>
  <Teleport to="body">
    <div
      v-if="floatDragging"
      class="float-drag-ghost"
      :style="{ left: floatDragPos.x - 22 + 'px', top: floatDragPos.y - 22 + 'px' }"
    >
      <div
        class="ghost-node"
        :class="
          floatDragging === 'meeting'
            ? 'ghost-meeting'
            : floatDragging === 'session'
              ? 'ghost-session'
              : 'ghost-doc'
        "
      >
        <template v-if="floatDragging === 'meeting'">
          <!-- meeting-preview와 동일 아이콘 (드래그 ghost = 생성될 노드 모양) -->
          <svg
            width="18"
            height="18"
            fill="none"
            stroke="currentColor"
            stroke-width="1.6"
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
        </template>
        <template v-else-if="floatDragging === 'session'">
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
        </template>
        <template v-else>
          <!-- doc-preview와 동일 아이콘 (드래그 ghost = 생성될 노드 모양) -->
          <svg
            width="16"
            height="16"
            fill="none"
            stroke="currentColor"
            stroke-width="1.8"
            viewBox="0 0 24 24"
          >
            <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z" />
            <polyline points="14 2 14 8 20 8" />
            <line x1="8" y1="13" x2="16" y2="13" />
            <line x1="8" y1="17" x2="16" y2="17" />
          </svg>
        </template>
      </div>
      <span class="ghost-label">{{
        floatDragging === 'meeting'
          ? '회의체 생성'
          : floatDragging === 'session'
            ? '회의 생성'
            : '자료 업로드'
      }}</span>
      <span v-if="floatDragPreviewLine" class="ghost-connect-hint">✓ 연결 가능</span>
    </div>
  </Teleport>

  <Teleport to="body">
    <svg
      v-if="floatDragging && floatDragPreviewLine"
      style="
        position: fixed;
        inset: 0;
        width: 100vw;
        height: 100vh;
        pointer-events: none;
        z-index: 9998;
      "
    >
      <defs>
        <marker id="drag-arrow" markerWidth="6" markerHeight="6" refX="3" refY="3" orient="auto">
          <circle cx="3" cy="3" r="2.5" fill="rgba(52,211,153,0.9)" />
        </marker>
      </defs>
      <line
        :x1="floatDragPreviewLine.x1"
        :y1="floatDragPreviewLine.y1"
        :x2="floatDragPreviewLine.x2"
        :y2="floatDragPreviewLine.y2"
        stroke="rgba(52,211,153,0.75)"
        stroke-width="2.5"
        stroke-dasharray="9,5"
        stroke-linecap="round"
        marker-end="url(#drag-arrow)"
      />
      <circle
        :cx="floatDragPreviewLine.x1"
        :cy="floatDragPreviewLine.y1"
        r="10"
        fill="rgba(52,211,153,0.2)"
        stroke="rgba(52,211,153,0.6)"
        stroke-width="2"
        stroke-dasharray="4,2"
      />
    </svg>
  </Teleport>
</template>
