<script setup>
import { inject, computed } from 'vue'

// 관계 탭은 '보기 전용'이다 — 사용자가 직접 관계를 편집(추가/삭제)하면 구조 엣지가 끊겨
// 그래프가 깨지는 문제가 있어 편집 UI를 제거했다. 관계는 PG 동기화 / AI '채우기'로만 변경된다.
const { currentNodeEdges, REL_COLORS } = inject('archiveSidebar')

const outEdges = computed(() => currentNodeEdges.value.filter(e => e.direction === 'out'))
const inEdges = computed(() => currentNodeEdges.value.filter(e => e.direction === 'in'))
</script>

<template>
  <!-- 나가는 관계 (보기 전용) -->
  <div class="detail-section">
    <div class="detail-section-label-row">
      <span class="detail-section-label">나가는 관계</span>
    </div>
    <div v-if="outEdges.length" class="rel-list">
      <div v-for="edge in outEdges" :key="edge._idx" class="rel-item rel-item-readonly">
        <div class="rel-item-main">
          <span class="rel-dir">→</span>
          <span class="rel-badge" :style="{ background: REL_COLORS[edge.rel] || '#6b7280' }">{{
            edge.rel
          }}</span>
          <span class="rel-target-name" :title="edge.toNode?.label">{{ edge.toNode?.label }}</span>
        </div>
      </div>
    </div>
    <div v-else class="detail-log-empty">나가는 관계가 없습니다.</div>
  </div>

  <!-- 들어오는 관계 (보기 전용) -->
  <div class="detail-section">
    <div class="detail-section-label-row">
      <span class="detail-section-label">들어오는 관계</span>
    </div>
    <div v-if="inEdges.length" class="rel-list">
      <div v-for="edge in inEdges" :key="'in-' + edge._idx" class="rel-item rel-item-readonly">
        <div class="rel-item-main">
          <span class="rel-dir">←</span>
          <span class="rel-badge" :style="{ background: REL_COLORS[edge.rel] || '#6b7280' }">{{
            edge.rel
          }}</span>
          <span class="rel-target-name" :title="edge.fromNode?.label">{{
            edge.fromNode?.label
          }}</span>
        </div>
      </div>
    </div>
    <div v-else class="detail-log-empty">들어오는 관계가 없습니다.</div>
  </div>
</template>
