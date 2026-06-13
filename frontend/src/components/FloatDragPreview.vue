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
