<script setup>
import { inject } from 'vue'
const {
  loading, viewMode, detailOpen, sidebarW, isHiddenType, toggleNodeType,
  similarEdgesOn, similarLoading, toggleSimilarEdges,
} = inject('archiveCanvas')
</script>

<template>
  <div v-if="!loading && viewMode==='graph'" class="graph-legend-onto"
    :style="{ left: (detailOpen ? sidebarW + 12 : 12) + 'px', transition: 'left 0.28s cubic-bezier(.22,.68,0,1.2)' }">
    <!-- <div v-if="viewMode==='graph'" class="legend-onto-item" style="cursor:default">
      <svg width="13" height="13" viewBox="0 0 13 13" style="flex-shrink:0">
        <circle cx="6.5" cy="6.5" r="6" fill="#1f2937" stroke="rgba(255,255,255,0.35)" stroke-width="0.8"/>
        <circle cx="6.5" cy="4.8" r="1.4" fill="rgba(255,255,255,0.88)"/>
        <path d="M3.5 10.5 C3.5 8.5 5 7.8 6.5 7.8 C8 7.8 9.5 8.5 9.5 10.5" fill="rgba(255,255,255,0.88)"/>
      </svg>
      나
    </div>
    <div class="legend-onto-item" style="cursor:default">
      <span class="legend-onto-icon" style="background:#0d9488">
        <svg width="9" height="9" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round">
          <rect x="4" y="2" width="16" height="20" rx="1"/><path d="M9 22v-4h6v4"/>
          <path d="M8 6h.01M12 6h.01M16 6h.01M8 10h.01M12 10h.01M16 10h.01M8 14h.01M12 14h.01M16 14h.01"/>
        </svg>
      </span>
      조직
    </div> -->
    <div class="legend-onto-item" :class="{ 'legend-item-hidden': isHiddenType('company') }" @click="toggleNodeType('company')">
      <div class="legend-onto-dot legend-dot-circle" style="background:#0d9488"></div>
      조직
      <svg class="legend-eye" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <template v-if="!isHiddenType('company')"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></template>
        <template v-else><path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19"/><line x1="1" y1="1" x2="23" y2="23"/></template>
      </svg>
    </div>
    <div class="legend-onto-item" style="cursor:default">
      <div class="legend-onto-dot legend-dot-circle" style="background:#3b82f6"></div>
      회의체
    </div>
    <div class="legend-onto-item" :class="{ 'legend-item-hidden': isHiddenType('dept') }" @click="toggleNodeType('dept')">
      <div class="legend-onto-dot legend-dot-circle" style="background:#8b5cf6"></div>
      부서
      <svg class="legend-eye" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <template v-if="!isHiddenType('dept')"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></template>
        <template v-else><path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19"/><line x1="1" y1="1" x2="23" y2="23"/></template>
      </svg>
    </div>
    <div class="legend-onto-item" :class="{ 'legend-item-hidden': isHiddenType('agenda') }" @click="toggleNodeType('agenda')">
      <div class="legend-onto-dot legend-dot-circle" style="background:#f59e0b"></div>
      과제
      <svg class="legend-eye" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <template v-if="!isHiddenType('agenda')"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></template>
        <template v-else><path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19"/><line x1="1" y1="1" x2="23" y2="23"/></template>
      </svg>
    </div>
    <div class="legend-onto-item" :class="{ 'legend-item-hidden': isHiddenType('session') }" @click="toggleNodeType('session')">
      <div class="legend-onto-dot legend-dot-circle" style="background:#f97316"></div>
      회의
      <svg class="legend-eye" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <template v-if="!isHiddenType('session')"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></template>
        <template v-else><path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19"/><line x1="1" y1="1" x2="23" y2="23"/></template>
      </svg>
    </div>
    <div class="legend-onto-item" :class="{ 'legend-item-hidden': isHiddenType('human_judgment') }" @click="toggleNodeType('human_judgment')">
      <div class="legend-onto-dot legend-dot-circle" style="background:#22d3ee"></div>
      의사결정
      <svg class="legend-eye" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <template v-if="!isHiddenType('human_judgment')"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></template>
        <template v-else><path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19"/><line x1="1" y1="1" x2="23" y2="23"/></template>
      </svg>
    </div>
    <div class="legend-onto-item" :class="{ 'legend-item-hidden': isHiddenType('minutes') }" @click="toggleNodeType('minutes')">
      <div class="legend-onto-dot legend-dot-circle" style="background:#60a5fa"></div>
      회의록
      <svg class="legend-eye" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <template v-if="!isHiddenType('minutes')"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></template>
        <template v-else><path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19"/><line x1="1" y1="1" x2="23" y2="23"/></template>
      </svg>
    </div>
    <div class="legend-onto-item" :class="{ 'legend-item-hidden': isHiddenType('report') }" @click="toggleNodeType('report')">
      <div class="legend-onto-dot legend-dot-circle" style="background:#34d399"></div>
      보고자료
      <svg class="legend-eye" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <template v-if="!isHiddenType('report')"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></template>
        <template v-else><path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19"/><line x1="1" y1="1" x2="23" y2="23"/></template>
      </svg>
    </div>
    <div class="legend-onto-item" :class="{ 'legend-item-hidden': isHiddenType('person') }" @click="toggleNodeType('person')">
      <div class="legend-onto-dot legend-dot-circle" style="background:#f472b6"></div>
      인원
      <svg class="legend-eye" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <template v-if="!isHiddenType('person')"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></template>
        <template v-else><path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19"/><line x1="1" y1="1" x2="23" y2="23"/></template>
      </svg>
    </div>
  </div>
</template>
