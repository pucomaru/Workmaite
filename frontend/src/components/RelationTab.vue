<script setup>
import { inject, computed, ref, watch } from 'vue'
import { apiAI } from '../api'
import { toast } from '../composables/useToast'
import NodeIcon from './NodeIcon.vue'

// 관계 탭은 '보기 전용'이다 — 사용자가 직접 관계를 편집(추가/삭제)하면 구조 엣지가 끊겨
// 그래프가 깨지는 문제가 있어 편집 UI를 제거했다. 관계는 PG 동기화 / AI '채우기'로만 변경된다.
// 단, '회의체↔회의체 연결(협의)'은 전용 테이블(meeting_relations)을 쓰는 안전한 수동 관계라 여기서 편집한다.
const { currentNodeEdges, REL_COLORS, detailMeeting, meetings, isDetailAdmin, refreshArchive } =
  inject('archiveSidebar')

const outEdges = computed(() => currentNodeEdges.value.filter(e => e.direction === 'out'))
const inEdges = computed(() => currentNodeEdges.value.filter(e => e.direction === 'in'))

// ── 회의체 연결(협의) — PG(meeting_relations) 진실 + Neo4j 동기화 ──
const mrSearch = ref('')
const mrConnections = ref([]) // [{ id, meeting_id:'mg-N', title, status, rel_type }]
const mrBusy = ref(false)

async function loadConnections() {
  const id = detailMeeting.value?.id
  if (!id) {
    mrConnections.value = []
    return
  }
  try {
    const { data } = await apiAI.get(`/api/neo4j/meeting-relations/${id}`)
    mrConnections.value = data.relations || []
  } catch {
    mrConnections.value = []
  }
}

// 선택된 회의체가 바뀌면 연결 목록 재조회
watch(() => detailMeeting.value?.id, loadConnections, { immediate: true })

// 검색 결과: 회의체 제목 매칭, 자기 자신·이미 연결된 회의체 제외
const mrResults = computed(() => {
  const q = mrSearch.value.trim().toLowerCase()
  if (!q) return []
  const selfId = detailMeeting.value?.id
  const connected = new Set(mrConnections.value.map(c => c.meeting_id))
  return (meetings.value || [])
    .filter(
      m => m.id !== selfId && !connected.has(m.id) && (m.title || '').toLowerCase().includes(q),
    )
    .slice(0, 8)
})

async function addConnection(target) {
  if (mrBusy.value || !detailMeeting.value?.id) return
  mrBusy.value = true
  try {
    await apiAI.post('/api/neo4j/meeting-relations', {
      from_meeting_id: detailMeeting.value.id,
      to_meeting_id: target.id,
    })
    mrSearch.value = ''
    await loadConnections()
    // 그래프의 manual_relations(PG 진실)를 다시 읽어 협의 엣지를 즉시 반영한다.
    refreshArchive?.()
    toast.success('회의체를 연결했습니다.')
  } catch (e) {
    toast.error(e.response?.data?.detail || '연결에 실패했습니다.')
  } finally {
    mrBusy.value = false
  }
}

async function removeConnection(conn) {
  if (mrBusy.value || !detailMeeting.value?.id) return
  mrBusy.value = true
  try {
    await apiAI.delete('/api/neo4j/meeting-relations', {
      data: { from_meeting_id: detailMeeting.value.id, to_meeting_id: conn.meeting_id },
    })
    await loadConnections()
    // 해제된 협의 엣지를 그래프에서도 즉시 제거
    refreshArchive?.()
  } catch (e) {
    toast.error(e.response?.data?.detail || '연결 해제에 실패했습니다.')
  } finally {
    mrBusy.value = false
  }
}
</script>

<template>
  <!-- ── 회의체 연결(협의) — 도착 회의체를 검색해 연결 ── -->
  <div v-if="detailMeeting" class="detail-section">
    <div class="detail-section-label-row">
      <span class="detail-section-label">회의체 연결</span>
      <span v-if="mrConnections.length" class="mr-cnt-badge">{{ mrConnections.length }}</span>
    </div>

    <!-- 검색 → 연결 (간사/관리자만) -->
    <template v-if="isDetailAdmin">
      <div class="mr-search-wrap">
        <svg
          width="13"
          height="13"
          fill="none"
          stroke="currentColor"
          stroke-width="2"
          viewBox="0 0 24 24"
        >
          <circle cx="11" cy="11" r="8" />
          <path d="M21 21l-4.35-4.35" />
        </svg>
        <input
          v-model="mrSearch"
          class="mr-search-input"
          placeholder="연결할 회의체를 제목으로 검색"
        />
      </div>
      <div v-if="mrResults.length" class="mr-search-results">
        <div v-for="m in mrResults" :key="m.id" class="mr-search-item" @click="addConnection(m)">
          <span class="mr-ic"><NodeIcon type="Meetings" :size="13" /></span>
          <span class="mr-name">{{ m.title }}</span>
          <span class="mr-add-hint">+ 연결</span>
        </div>
      </div>
      <div v-else-if="mrSearch.trim()" class="mr-no-result">검색 결과가 없습니다.</div>
    </template>

    <!-- 연결된 회의체 목록 -->
    <div class="mr-list">
      <div v-if="!mrConnections.length" class="detail-log-empty">연결된 회의체가 없습니다.</div>
      <div v-for="c in mrConnections" :key="c.id" class="mr-row">
        <span class="mr-badge" :style="{ background: REL_COLORS[c.rel_type] || '#60a5fa' }">{{
          c.rel_type
        }}</span>
        <span class="mr-ic"><NodeIcon type="Meetings" :size="13" /></span>
        <span class="mr-name" :title="c.title">{{ c.title }}</span>
        <button
          v-if="isDetailAdmin"
          class="mr-remove"
          :disabled="mrBusy"
          @click="removeConnection(c)"
          title="연결 해제"
        >
          <svg
            width="12"
            height="12"
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

<style scoped>
.mr-cnt-badge {
  font-size: 11px;
  font-weight: 700;
  background: rgba(96, 165, 250, 0.15);
  color: var(--accent-soft);
  border-radius: 99px;
  padding: 1px 7px;
  line-height: 1.6;
}
.mr-search-wrap {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 7px 10px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--surface);
  margin-bottom: 6px;
}
.mr-search-wrap svg {
  color: var(--text-muted);
  flex-shrink: 0;
}
.mr-search-input {
  flex: 1;
  border: none;
  background: none;
  color: var(--text);
  font-size: 12px;
  outline: none;
}
.mr-search-input::placeholder {
  color: var(--text-muted);
}
.mr-search-results {
  border: 1px solid var(--border);
  border-radius: 8px;
  overflow: hidden;
  background: var(--bg-card);
  margin-bottom: 6px;
}
.mr-search-item {
  display: flex;
  align-items: center;
  gap: 9px;
  padding: 8px 11px;
  cursor: pointer;
  transition: background 0.1s;
}
.mr-search-item:hover {
  background: var(--surface);
}
.mr-add-hint {
  font-size: 12px;
  font-weight: 700;
  color: var(--accent);
  flex-shrink: 0;
}
.mr-no-result {
  font-size: 12px;
  color: var(--text-muted);
  padding: 2px 2px 6px;
}
.mr-list {
  display: flex;
  flex-direction: column;
  gap: 3px;
}
.mr-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 5px 6px;
  border-radius: 7px;
}
.mr-row:hover {
  background: var(--surface);
}
.mr-ic {
  display: inline-flex;
  color: var(--accent-soft);
  flex-shrink: 0;
}
.mr-badge {
  font-size: 10px;
  font-weight: 700;
  color: #fff;
  border-radius: 4px;
  padding: 1px 6px;
  flex-shrink: 0;
}
.mr-name {
  flex: 1;
  font-size: 12px;
  font-weight: 500;
  color: var(--text);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.mr-remove {
  width: 22px;
  height: 22px;
  border-radius: 5px;
  border: none;
  background: rgba(239, 68, 68, 0.08);
  color: var(--danger-soft);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  transition: background 0.15s;
}
.mr-remove:hover:not(:disabled) {
  background: rgba(239, 68, 68, 0.2);
}
.mr-remove:disabled {
  opacity: 0.5;
  cursor: default;
}
</style>
