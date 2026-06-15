<script setup>
import { inject, ref, computed, watch } from 'vue'

// DetailSidebar의 회의체 상세·노드 상세 양쪽 '관계 탭'이 동일해 단일 컴포넌트로 추출.
// 상태는 부모와 같은 provide(archiveSidebar)에서 inject한다.
const {
  currentNodeEdges,
  REL_COLORS,
  doDeleteEdge,
  relAddActive,
  openAddRel,
  allGraphNodeList,
  relAddForm,
  doAddRel,
} = inject('archiveSidebar')

const NODE_TYPE_KO = {
  Meetings: '회의체',
  session: '회의',
  agenda: '아젠다',
  minutes: '회의록',
  report: '보고자료',
  dept: '부서',
  person: '구성원',
  company: '회사',
}

// outlink만 편집, inlink는 읽기 전용 (GraphRAG 단방향 저장 원칙)
const outEdges = computed(() => currentNodeEdges.value.filter(e => e.direction === 'out'))
const inEdges = computed(() => currentNodeEdges.value.filter(e => e.direction === 'in'))

// 도착 노드 검색
const toSearch = ref('')
const showToList = ref(false)
const toNodeData = computed(() => allGraphNodeList.value.find(n => n.id === relAddForm.value.toId))
const filteredToNodes = computed(() => {
  const q = toSearch.value.trim().toLowerCase()
  const list = allGraphNodeList.value.filter(n => n.id !== relAddForm.value.fromId)
  if (!q) return list.slice(0, 30)
  return list
    .filter(n => n.label?.toLowerCase().includes(q) || NODE_TYPE_KO[n.type]?.includes(q))
    .slice(0, 30)
})
function selectToNode(n) {
  relAddForm.value.toId = n.id
  toSearch.value = ''
  showToList.value = false
}
function clearToNode() {
  relAddForm.value.toId = ''
  toSearch.value = ''
}
function hideTo() {
  setTimeout(() => {
    showToList.value = false
  }, 160)
}

watch(relAddActive, v => {
  if (!v) {
    toSearch.value = ''
    showToList.value = false
  }
})
</script>

<template>
  <!-- 나가는 관계 (편집 가능) -->
  <div class="detail-section">
    <div class="detail-section-label-row">
      <span class="detail-section-label">나가는 관계</span>
      <button class="detail-more-btn rel-add-trigger" @click="openAddRel">+ 추가</button>
    </div>

    <!-- 새 관계 추가 폼 (헤더 바로 아래) -->
    <div v-if="relAddActive" class="detail-section rel-add-panel">
      <div class="detail-section-label-row" style="margin-bottom: 10px">
        <span class="detail-section-label">새 관계 추가</span>
        <button class="rel-btn rel-btn-cancel" @click="relAddActive = false">
          <svg
            width="10"
            height="10"
            fill="none"
            stroke="currentColor"
            stroke-width="2.5"
            viewBox="0 0 24 24"
          >
            <path d="M18 6L6 18M6 6l12 12" />
          </svg>
        </button>
      </div>
      <div class="rel-add-form">
        <div class="rel-add-field">
          <label class="rel-add-label">도착 노드</label>
          <div class="rel-node-search-wrap">
            <div v-if="toNodeData" class="rel-node-selected" @click="clearToNode">
              <span class="rel-node-sel-label">{{ toNodeData.label }}</span>
              <span class="rel-node-sel-type">{{
                NODE_TYPE_KO[toNodeData.type] || toNodeData.type
              }}</span>
              <span class="rel-node-sel-clear">×</span>
            </div>
            <input
              v-else
              v-model="toSearch"
              class="rel-search-input"
              placeholder="노드 이름 검색..."
              @focus="showToList = true"
              @blur="hideTo"
            />
            <div v-if="showToList && !toNodeData" class="rel-node-list">
              <div v-if="!filteredToNodes.length" class="rel-node-empty">결과 없음</div>
              <div
                v-for="n in filteredToNodes"
                :key="n.id"
                class="rel-node-item"
                @mousedown.prevent="selectToNode(n)"
              >
                <span class="rel-node-item-label">{{ n.label }}</span>
                <span class="rel-node-item-type">{{ NODE_TYPE_KO[n.type] || n.type }}</span>
              </div>
            </div>
          </div>
        </div>
        <button
          class="app-btn-primary"
          style="width: 100%; margin-top: 8px; font-size: 12px; padding: 7px 0"
          :disabled="!relAddForm.fromId || !relAddForm.toId || !relAddForm.rel?.trim()"
          @click="doAddRel"
        >
          관계 추가
        </button>
      </div>
    </div>

    <div v-if="outEdges.length" class="rel-list">
      <div v-for="edge in outEdges" :key="edge._idx" class="rel-item">
        <div class="rel-item-main">
          <span class="rel-dir">→</span>
          <span class="rel-badge" :style="{ background: REL_COLORS[edge.rel] || '#6b7280' }">{{
            edge.rel
          }}</span>
          <span class="rel-target-name" :title="edge.toNode?.label">{{ edge.toNode?.label }}</span>
        </div>
        <div class="rel-item-actions">
          <button class="rel-btn rel-btn-delete" @click="doDeleteEdge(edge._idx)" title="관계 삭제">
            <svg
              width="10"
              height="10"
              fill="none"
              stroke="currentColor"
              stroke-width="2.5"
              viewBox="0 0 24 24"
            >
              <path d="M18 6L6 18M6 6l12 12" />
            </svg>
          </button>
        </div>
      </div>
    </div>
    <div v-else class="detail-log-empty">나가는 관계가 없습니다.</div>
  </div>

  <!-- 들어오는 관계 (읽기 전용 — 단방향 저장 원칙상 상대 노드에서 편집) -->
  <div class="detail-section">
    <div class="detail-section-label-row">
      <span class="detail-section-label">들어오는 관계</span>
      <span class="rel-in-hint">상대 노드에서 편집</span>
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
