<script setup>
import { inject, computed, ref, watch } from 'vue'
import DOMPurify from 'dompurify'
import SidebarInfoRow from './SidebarInfoRow.vue'
import ProcessStepBar from './ProcessStepBar.vue'
import FileUploadArea from './FileUploadArea.vue'
import AgendaReviewList from './AgendaReviewList.vue'
import RelationTab from './RelationTab.vue'

const {
  detailOpen,
  sidebarW,
  onSidebarResizeStart,
  detailMeeting,
  isDetailAdmin,
  isAnyAdmin,
  canEditCompany,
  canEditDept,
  openGroupSetting,
  openNodeGroupSetting,
  detailTab,
  showExtractFlow,
  nodeDetailTab,
  detailDday,
  detailEndDateFormatted,
  detailDeptStatus,
  groupHistoryMap,
  formatDate,
  formatDateOnly,
  detailAgendas,
  groupedAgendas,
  doneAgendasWithReport,
  completeAgenda,
  deleteAgenda,
  extractLoading,
  extractResult,
  selectedFiles,
  uploadedCtxFiles,
  onCtxFilesAdded,
  removeCtxFile,
  runExtract,
  goToProcessStep,
  finishExtract,
  addDirectAgenda,
  detailMemberDepts,
  detailMemberCompanies,
  NODE_TYPE_COLORS,
  detailNode,
  downloadDummy,
  deleteReport,
  currentCompany,
  personMeetings,
  reportRelatedAgendas,
  meetings,
  viewMode,
  nodeReviewing,
  startNodeReview,
} = inject('archiveSidebar')

// ── 아젠다 직접 추가 ─────────────────────────────────────────────
const directAddItems = ref([])

function pushDirectAddItem() {
  directAddItems.value.push({
    title: '',
    company: '',
    dept: '',
    start_date: '',
    end_date: '',
    db_id: null,
    _state: null,
    _editing: true,
    _directAdd: true,
    _editTitle: '',
    _editCompany: '',
    _editDept: '',
    _editStartDate: '',
    _editEndDate: '',
    _agentLogId: null,
    _showReason: false,
    _feedbackAction: '',
    _reason: '',
  })
}

async function approveDirectAdd(i) {
  const ag = directAddItems.value[i]
  try {
    await addDirectAgenda({
      title: ag.title,
      company: ag.company || '',
      dept: ag.dept || '',
      start_date: ag.start_date || '',
      end_date: ag.end_date || '',
    })
    directAddItems.value.splice(i, 1)
  } catch (e) {
    console.error('[approveDirectAdd] 실패:', e)
  }
}

function removeDirectAdd(i) {
  directAddItems.value.splice(i, 1)
}

// ── 완료 과제 더보기 / 팀 필터 ─────────────────────────────────────
const doneExpanded = ref(false)
const doneDeptFilter = ref('')
watch(
  () => detailMeeting?.value?.id,
  () => {
    doneExpanded.value = false
    doneDeptFilter.value = ''
  },
)
const doneDepts = computed(() => [
  ...new Set(
    (doneAgendasWithReport || { value: [] }).value?.map(t => t.dept).filter(Boolean) || [],
  ),
])
const doneFiltered = computed(() => {
  const items = doneAgendasWithReport?.value || []
  return doneDeptFilter.value ? items.filter(t => t.dept === doneDeptFilter.value) : items
})
const doneDisplayItems = computed(() =>
  doneExpanded.value ? doneFiltered.value : doneFiltered.value.slice(0, 5),
)

// ── 최근 로그 더보기 / 필터 ──────────────────────────────────────
const logExpanded = ref(false)
const logTypeFilter = ref('')
const expandedLogIndexes = ref(new Set())
watch(
  () => detailMeeting?.value?.id,
  () => {
    logExpanded.value = false
    logTypeFilter.value = ''
    expandedLogIndexes.value = new Set()
  },
)
function toggleLogItem(index) {
  const next = new Set(expandedLogIndexes.value)
  if (next.has(index)) next.delete(index)
  else next.add(index)
  expandedLogIndexes.value = next
}
const logAllItems = computed(() => groupHistoryMap.value.get(detailMeeting.value?.id) || [])
const logFilteredItems = computed(() =>
  logTypeFilter.value
    ? logAllItems.value.filter(i => i.type === logTypeFilter.value)
    : logAllItems.value,
)
const logDisplayItems = computed(() =>
  logExpanded.value ? logFilteredItems.value : logFilteredItems.value.slice(0, 7),
)

// ── 보고자료 레이더 차트 ─────────────────────────────────────────
const SB_CX = 90,
  SB_CY = 95,
  SB_R = 60
const SB_CRITERIA = [
  { key: '목적및배경', label: '목적/배경', max: 15 },
  { key: '현황분석', label: '현황분석', max: 20 },
  { key: '핵심내용', label: '핵심내용', max: 20 },
  { key: '실행계획', label: '실행계획', max: 20 },
  { key: '기대효과', label: '기대효과', max: 15 },
  { key: '리스크및대안', label: '리스크/대안', max: 10 },
]
function sbPt(angleDeg, r) {
  const a = (angleDeg * Math.PI) / 180
  return `${(SB_CX + r * Math.cos(a)).toFixed(1)},${(SB_CY + r * Math.sin(a)).toFixed(1)}`
}
const sbGridPoly = SB_CRITERIA.map((_, i) => sbPt(i * 60 - 90, SB_R)).join(' ')
const sbGridPoly2 = SB_CRITERIA.map((_, i) => sbPt(i * 60 - 90, SB_R * 0.66)).join(' ')
const sbGridPoly3 = SB_CRITERIA.map((_, i) => sbPt(i * 60 - 90, SB_R * 0.33)).join(' ')
const sbAxisLines = SB_CRITERIA.map((_, i) => {
  const a = ((i * 60 - 90) * Math.PI) / 180
  return {
    x2: (SB_CX + SB_R * Math.cos(a)).toFixed(1),
    y2: (SB_CY + SB_R * Math.sin(a)).toFixed(1),
  }
})
const sbLabelPos = SB_CRITERIA.map((c, i) => {
  const a = ((i * 60 - 90) * Math.PI) / 180
  return {
    x: (SB_CX + (SB_R + 22) * Math.cos(a)).toFixed(1),
    y: (SB_CY + (SB_R + 22) * Math.sin(a)).toFixed(1),
    label: c.label,
  }
})
const sbScorePoly = computed(() => {
  const scores = detailNode.value?.data?.detail_scores || {}
  return SB_CRITERIA.map((c, i) => {
    const s = scores[c.key]?.score ?? 0
    return sbPt(i * 60 - 90, (s / c.max) * SB_R)
  }).join(' ')
})
const sbScoreColor = computed(() => {
  const s = detailNode.value?.data?.total_score ?? 0
  return s >= 80 ? '#10b981' : s >= 60 ? '#f59e0b' : '#ef4444'
})

// 우선 개선 과제: 실시간 검토 결과(top_improvements) 또는 그래프 로드 데이터(detail_scores._top_improvements)
const sbTopImprovements = computed(() => {
  const d = detailNode.value?.data
  return d?.detail_scores?._top_improvements || d?.top_improvements || []
})

function parseAiEvidence(val) {
  if (!val) return ''
  try {
    const p = JSON.parse(val)
    return p?.reasoning || ''
  } catch {
    return val
  }
}

// 관계 탭은 RelationTab.vue로 분리 (회의체·노드 상세에서 동일하게 재사용)
</script>

<template>
  <Transition name="sidebar-slide">
    <div v-if="detailOpen" class="detail-sidebar" :style="{ width: sidebarW + 'px' }">
      <div class="sidebar-resize-handle" @mousedown="onSidebarResizeStart"></div>

      <!-- ── Header: Meetings ── -->
      <template v-if="detailMeeting">
        <div class="detail-header">
          <div class="detail-header-icon">
            <svg
              width="15"
              height="15"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
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
          <div class="detail-header-left">
            <div class="detail-name-badge-row">
              <div class="detail-meeting-name">{{ detailMeeting?.title }}</div>
              <div class="detail-role-badge" :class="isDetailAdmin ? 'role-admin' : 'role-member'">
                {{ isDetailAdmin ? '간사' : '참여자' }}
              </div>
            </div>
            <div class="detail-meta-row">
              <span class="detail-meta">{{ detailMeeting?.members?.length || 0 }}명</span>
              <span class="detail-meta-dot">·</span>
              <span class="detail-meta"
                >{{
                  (detailMeeting?.minutes?.length || 0) + (detailMeeting?.reports?.length || 0)
                }}건</span
              >
              <template v-if="detailMeeting?.meeting_type">
                <span class="detail-meta-dot">·</span>
                <span class="detail-meta">{{ detailMeeting.meeting_type }}</span>
              </template>
            </div>
          </div>
          <div class="detail-header-actions">
            <button v-if="isDetailAdmin" class="detail-icon-btn" @click="openGroupSetting">
              <svg
                width="13"
                height="13"
                fill="none"
                stroke="currentColor"
                stroke-width="2"
                viewBox="0 0 24 24"
              >
                <path d="M12 15a3 3 0 100-6 3 3 0 000 6z" />
                <path
                  d="M19.4 15a1.65 1.65 0 00.33 1.82l.06.06a2 2 0 010 2.83 2 2 0 01-2.83 0l-.06-.06a1.65 1.65 0 00-1.82-.33 1.65 1.65 0 00-1 1.51V21a2 2 0 01-2 2 2 2 0 01-2-2v-.09A1.65 1.65 0 009 19.4a1.65 1.65 0 00-1.82.33l-.06.06a2 2 0 01-2.83 0 2 2 0 010-2.83l.06-.06A1.65 1.65 0 004.68 15a1.65 1.65 0 00-1.51-1H3a2 2 0 01-2-2 2 2 0 012-2h.09A1.65 1.65 0 004.6 9a1.65 1.65 0 00-.33-1.82l-.06-.06a2 2 0 010-2.83 2 2 0 012.83 0l.06.06A1.65 1.65 0 009 4.68a1.65 1.65 0 001-1.51V3a2 2 0 012-2 2 2 0 012 2v.09a1.65 1.65 0 001 1.51 1.65 1.65 0 001.82-.33l.06-.06a2 2 0 012.83 0 2 2 0 010 2.83l-.06.06A1.65 1.65 0 0019.4 9a1.65 1.65 0 001.51 1H21a2 2 0 012 2 2 2 0 01-2 2h-.09a1.65 1.65 0 00-1.51 1z"
                />
              </svg>
            </button>
          </div>
        </div>

        <!-- 탭 -->
        <div class="detail-tabs">
          <button
            class="detail-tab"
            :class="{ active: detailTab === 'basic' }"
            @click="detailTab = 'basic'"
          >
            기본
          </button>
          <button
            class="detail-tab"
            :class="{ active: detailTab === 'task' }"
            @click="detailTab = 'task'"
          >
            아젠다
          </button>
          <!-- prettier-ignore -->
          <button
            class="detail-tab detail-tab-extract"
            :class="{ active: detailTab === 'extract' }"
            @click="detailTab = 'extract'; if (!showExtractFlow) showExtractFlow = true"
          >
            아젠다 추출
          </button>
          <button
            class="detail-tab"
            :class="{ active: detailTab === 'rel' }"
            @click="detailTab = 'rel'"
          >
            관계
          </button>
        </div>

        <div class="detail-body">
          <!-- ── 기본 탭 ── -->
          <template v-if="detailTab === 'basic'">
            <!-- 소개 -->
            <div v-if="detailMeeting?.purpose || detailMeeting?.description" class="detail-section">
              <div class="detail-section-label">소개</div>
              <div class="detail-purpose">
                {{ detailMeeting.purpose || detailMeeting.description }}
              </div>
            </div>

            <!-- 맥락 -->
            <div v-if="detailMeeting?.context" class="detail-section">
              <div class="detail-section-label">회의 맥락</div>
              <div class="detail-purpose detail-context">{{ detailMeeting.context }}</div>
            </div>

            <!-- 간사 + 참여부서 -->
            <div class="detail-section" style="gap: 7px">
              <SidebarInfoRow
                label="간사"
                :value="
                  detailMeeting?.members?.find(mb => mb.role === 'admin')?.userName ||
                  detailMeeting?.members?.find(mb => mb.role === 'admin')?.name ||
                  '-'
                "
              />
              <SidebarInfoRow
                label="참여부서"
                :value="
                  [
                    ...new Set(
                      (detailMeeting?.members || [])
                        .map(mb => mb.department || mb.dept || '')
                        .filter(Boolean),
                    ),
                  ].join(' · ') || '-'
                "
              />
              <SidebarInfoRow
                label="시작일"
                :value="detailMeeting?.start_date ? detailMeeting.start_date.slice(0, 10) : '-'"
              />
              <SidebarInfoRow label="종료일">
                <div
                  style="
                    display: flex;
                    align-items: center;
                    gap: 4px;
                    flex-wrap: nowrap;
                    overflow: hidden;
                  "
                >
                  <template v-if="detailDday !== null">
                    <span class="dday-date" style="white-space: nowrap">{{
                      detailEndDateFormatted
                    }}</span>
                    <span
                      class="dday-badge"
                      :class="
                        detailDday <= 0
                          ? 'dday-over'
                          : detailDday <= 1
                            ? 'dday-critical'
                            : detailDday <= 3
                              ? 'dday-warning'
                              : 'dday-normal'
                      "
                      style="white-space: nowrap"
                      >{{ detailDday <= 0 ? '마감 초과' : `D-${detailDday}` }}</span
                    >
                  </template>
                  <span v-else class="dday-label" style="white-space: nowrap">없음</span>
                </div>
              </SidebarInfoRow>
            </div>

            <!-- 팀 제출 현황 -->
            <div class="detail-section">
              <div class="detail-section-label-row">
                <span class="detail-section-label">팀 제출 현황</span>
                <span class="dept-submit-summary">
                  <span class="dss-done"
                    >{{ detailDeptStatus.filter(d => d.submitted).length }}팀 완료</span
                  >
                  <template v-if="detailDeptStatus.filter(d => !d.submitted && !d.noTask).length">
                    <span class="dss-sep">·</span>
                    <span class="dss-pending"
                      >{{ detailDeptStatus.filter(d => !d.submitted && !d.noTask).length }}팀
                      미제출</span
                    >
                  </template>
                </span>
              </div>
              <template v-if="detailDeptStatus.length">
                <div class="dept-submit-list">
                  <div
                    v-for="ds in detailDeptStatus"
                    :key="ds.dept"
                    class="dept-submit-item"
                    :class="{
                      'dsi-done': ds.submitted,
                      'dsi-pending': !ds.submitted,
                      'dsi-urgent': !ds.submitted && ds.minDays !== null && ds.minDays <= 3,
                    }"
                  >
                    <div
                      class="dsi-dot"
                      :class="{
                        'dsi-dot-done': ds.submitted,
                        'dsi-dot-pending': !ds.submitted,
                        'dsi-dot-urgent': !ds.submitted && ds.minDays !== null && ds.minDays <= 3,
                      }"
                    ></div>
                    <span class="dsi-name">{{ ds.dept }}</span>
                    <template v-if="ds.noTask">
                      <span class="dsi-status" style="color: #94a3b8">아젠다 없음</span>
                    </template>
                    <template v-else-if="ds.submitted">
                      <span class="dsi-status dsi-status-done">제출 완료</span>
                    </template>
                    <template v-else>
                      <span class="dsi-status dsi-status-pending"
                        >미제출 {{ ds.pendingCount }}건</span
                      >
                      <span
                        v-if="ds.minDays !== null"
                        class="dsi-deadline"
                        :class="{
                          'dsi-deadline-urgent': ds.minDays <= 3,
                          'dsi-deadline-critical': ds.minDays <= 1,
                        }"
                      >
                        {{ ds.minDays <= 0 ? '마감초과' : `D-${ds.minDays}` }}
                      </span>
                    </template>
                  </div>
                </div>
              </template>
              <div v-else class="detail-log-empty">참여 부서 정보가 없습니다.</div>
            </div>

            <!-- 최근 로그 -->
            <div class="detail-section">
              <div class="detail-section-label-row">
                <span class="detail-section-label">최근 로그</span>
                <span v-if="logAllItems.length" class="detail-log-total"
                  >전체 {{ logAllItems.length }}건</span
                >
              </div>
              <div class="detail-log-filters">
                <button
                  class="log-chip"
                  :class="{ active: logTypeFilter === '' }"
                  @click="logTypeFilter = ''"
                >
                  전체
                </button>
                <button
                  class="log-chip"
                  :class="{ active: logTypeFilter === 'minutes' }"
                  @click="logTypeFilter = 'minutes'"
                >
                  회의록
                </button>
                <button
                  class="log-chip"
                  :class="{ active: logTypeFilter === 'report' }"
                  @click="logTypeFilter = 'report'"
                >
                  보고서
                </button>
                <button
                  class="log-chip"
                  :class="{ active: logTypeFilter === 'agenda' }"
                  @click="logTypeFilter = 'agenda'"
                >
                  아젠다
                </button>
              </div>
              <div class="detail-log-list">
                <template v-if="logFilteredItems.length">
                  <div v-for="(item, i) in logDisplayItems" :key="i" class="detail-log-item">
                    <span
                      class="detail-log-dot"
                      :style="{ background: NODE_TYPE_COLORS[item.type] || '#555' }"
                    ></span>
                    <div class="detail-log-content">
                      <div
                        class="detail-log-desc"
                        :class="{ 'log-expandable': item.agendas?.length }"
                        @click="item.agendas?.length && toggleLogItem(i)"
                      >
                        <span class="detail-log-desc-text">{{ item.desc }}</span>
                        <svg
                          v-if="item.agendas?.length"
                          class="log-expand-chevron"
                          :class="{ open: expandedLogIndexes.has(i) }"
                          width="10"
                          height="10"
                          viewBox="0 0 10 10"
                          fill="none"
                        >
                          <path
                            d="M2 3.5L5 6.5L8 3.5"
                            stroke="currentColor"
                            stroke-width="1.5"
                            stroke-linecap="round"
                            stroke-linejoin="round"
                          />
                        </svg>
                      </div>
                      <div class="detail-log-meta">
                        <template v-if="item.manager && item.date"
                          >{{ item.manager }} · {{ formatDate(item.date) }}</template
                        >
                        <template v-else-if="item.date">{{ formatDate(item.date) }}</template>
                        <template v-else-if="item.manager">{{ item.manager }}</template>
                      </div>
                      <ul
                        v-if="item.agendas?.length && expandedLogIndexes.has(i)"
                        class="log-agenda-list"
                      >
                        <li v-for="(ag, ai) in item.agendas" :key="ai" class="log-agenda-item">
                          {{ ag }}
                        </li>
                      </ul>
                    </div>
                  </div>
                  <button
                    v-if="!logExpanded && logFilteredItems.length > 7"
                    class="detail-log-more"
                    @click="logExpanded = true"
                  >
                    더보기 {{ logFilteredItems.length - 7 }}건 ↓
                  </button>
                  <!-- prettier-ignore -->
                  <button
                    v-if="logExpanded"
                    class="detail-log-more"
                    @click="logExpanded = false; logTypeFilter = ''"
                  >
                    접기 ↑
                  </button>
                </template>
                <div v-else class="detail-log-empty">기록된 로그가 없습니다.</div>
              </div>
            </div> </template
          ><!-- /기본 탭 -->

          <!-- ── 과제 탭 ── -->
          <template v-if="detailTab === 'task'">
            <!-- 아젠다 직접 추가 버튼 (항상 표시) -->
            <!-- prettier-ignore -->
            <button class="gm-add-btn" style="margin-bottom: 8px" @click="pushDirectAddItem">
              <svg width="10" height="10" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24">
                <path d="M12 5v14M5 12h14" />
              </svg>
              아젠다 직접 추가
            </button>

            <!-- 직접 추가 인라인 (AI 추출 탭과 동일한 AgendaReviewList) -->
            <AgendaReviewList
              v-if="directAddItems.length"
              :items="directAddItems"
              :memberCompanies="detailMemberCompanies"
              :memberDepts="detailMemberDepts"
              :removeOnApprove="true"
              :showFooter="false"
              :showFeedback="false"
              style="margin-bottom: 10px"
              @approved="approveDirectAdd"
              @rejected="removeDirectAdd"
              @remove="removeDirectAdd"
              @save="() => {}"
            />

            <!-- 진행중 아젠다 목록 -->
            <div class="detail-section" style="margin-top: 4px">
              <div class="detail-section-label-row">
                <span class="detail-section-label">진행중 아젠다</span>
                <span class="detail-section-label" style="font-weight: 400"
                  >{{ detailAgendas.filter(t => t.status !== 'done').length }}건</span
                >
              </div>
              <div v-if="!detailAgendas.length" class="detail-log-empty">
                등록된 아젠다가 없습니다.
              </div>
              <template v-else>
                <div
                  v-for="(agendas, dept) in groupedAgendas"
                  :key="dept"
                  class="agenda-dept-group"
                >
                  <div class="agenda-dept-header">
                    <span class="agenda-dept-name">{{ dept || '미배정' }}</span>
                    <span class="agenda-dept-count">{{ agendas.length }}건</span>
                  </div>
                  <div class="detail-agenda-list">
                    <div
                      v-for="agenda in agendas"
                      :key="agenda.id || agenda.content"
                      class="detail-agenda-item"
                    >
                      <div
                        class="detail-agenda-status"
                        :class="{
                          'ts-done': agenda.status === 'done',
                          'ts-progress':
                            agenda.status === 'in_progress' || agenda.status === 'ongoing',
                          'ts-risk': agenda.status === 'at_risk',
                          'ts-pending': !agenda.status || agenda.status === 'pending',
                        }"
                      >
                        {{
                          agenda.status === 'done'
                            ? '완료'
                            : agenda.status === 'in_progress' || agenda.status === 'ongoing'
                              ? '진행'
                              : agenda.status === 'at_risk'
                                ? '위험'
                                : '대기'
                        }}
                      </div>
                      <div class="detail-agenda-info">
                        <div class="detail-agenda-title">{{ agenda.content || agenda.title }}</div>
                        <div class="detail-agenda-meta">
                          <div
                            v-if="
                              agenda.dept ||
                              (Array.isArray(agenda.department)
                                ? agenda.department[0]
                                : agenda.department)
                            "
                          >
                            담당부서 -
                            {{
                              agenda.dept ||
                              (Array.isArray(agenda.department)
                                ? agenda.department[0]
                                : agenda.department)
                            }}
                          </div>
                          <div v-if="agenda.due_date">
                            마감기한 - {{ formatDateOnly(agenda.due_date) }}
                          </div>
                        </div>
                      </div>
                      <div class="detail-agenda-actions">
                        <button
                          class="agenda-action-btn agenda-done-btn"
                          :class="{ 'is-done': agenda.status === 'done' }"
                          @click="completeAgenda(agenda)"
                          title="완료/취소"
                        >
                          ✓
                        </button>
                        <button
                          class="agenda-action-btn agenda-del-btn"
                          @click="deleteAgenda(agenda)"
                          title="삭제"
                        >
                          ✕
                        </button>
                      </div>
                    </div>
                  </div>
                </div>
              </template>
            </div>

            <!-- 완료된 아젠다 -->
            <div
              v-if="doneAgendasWithReport.length"
              class="detail-section"
              style="margin-top: 12px"
            >
              <div class="detail-section-label-row">
                <span class="detail-section-label">완료된 아젠다</span>
                <span class="detail-log-total">{{ doneAgendasWithReport.length }}건</span>
              </div>
              <div v-if="doneExpanded && doneDepts.length > 1" class="detail-log-filters">
                <button
                  class="log-chip"
                  :class="{ active: doneDeptFilter === '' }"
                  @click="doneDeptFilter = ''"
                >
                  전체
                </button>
                <button
                  v-for="dept in doneDepts"
                  :key="dept"
                  class="log-chip"
                  :class="{ active: doneDeptFilter === dept }"
                  @click="doneDeptFilter = dept"
                >
                  {{ dept }}
                </button>
              </div>
              <div class="done-agenda-list">
                <div v-for="agenda in doneDisplayItems" :key="agenda.id" class="done-agenda-item">
                  <div class="done-agenda-check">
                    <svg
                      width="10"
                      height="10"
                      fill="none"
                      stroke="#10b981"
                      stroke-width="2.5"
                      viewBox="0 0 24 24"
                    >
                      <polyline points="20 6 9 17 4 12" />
                    </svg>
                  </div>
                  <div class="done-agenda-body">
                    <div class="done-agenda-title">{{ agenda.title || agenda.content }}</div>
                    <div class="done-agenda-meta">
                      <span>{{ agenda.dept }}</span>
                    </div>
                    <div v-if="agenda.reportFileName" class="done-agenda-report">
                      <svg
                        width="9"
                        height="9"
                        fill="none"
                        stroke="currentColor"
                        stroke-width="2"
                        viewBox="0 0 24 24"
                      >
                        <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z" />
                        <polyline points="14 2 14 8 20 8" />
                      </svg>
                      <span class="done-agenda-filename">{{ agenda.reportFileName }}</span>
                    </div>
                    <div class="done-agenda-dates">
                      <span v-if="agenda.reportDate">제출 {{ formatDate(agenda.reportDate) }}</span>
                      <span v-if="agenda.due_date">마감 {{ formatDateOnly(agenda.due_date) }}</span>
                    </div>
                  </div>
                </div>
                <button
                  v-if="!doneExpanded && doneFiltered.length > 5"
                  class="detail-log-more"
                  @click="doneExpanded = true"
                >
                  더보기 {{ doneFiltered.length - 5 }}건 ↓
                </button>
                <!-- prettier-ignore -->
                <button
                  v-if="doneExpanded"
                  class="detail-log-more"
                  @click="doneExpanded = false; doneDeptFilter = ''"
                >
                  접기 ↑
                </button>
              </div>
            </div> </template
          ><!-- /과제 탭 -->

          <!-- ── 과제추출 탭 ── -->
          <template v-if="detailTab === 'extract'">
            <!-- 프로세스 인디케이터: 항상 표시 -->
            <div class="task-process-bar">
              <ProcessStepBar
                :steps="['자료선정', '추출']"
                :current-step="extractResult.length || extractLoading ? 1 : 0"
                @step-click="() => {}"
              />
            </div>

            <!-- 자료선정 단계: 초안이 없을 때만 -->
            <template v-if="!extractResult.length && !extractLoading">
              <div class="ctx-section">
                <div class="detail-section-label ctx-section-title-flex">
                  <svg
                    width="11"
                    height="11"
                    fill="none"
                    stroke="currentColor"
                    stroke-width="2"
                    viewBox="0 0 24 24"
                  >
                    <path
                      d="M15.172 7l-6.586 6.586a2 2 0 102.828 2.828l6.414-6.586a4 4 0 00-5.656-5.656l-6.415 6.585a6 6 0 108.486 8.486L20.5 13"
                    />
                  </svg>
                  추가 자료 선택
                </div>
                <!-- 기존 자료 목록: 실제 파일이 있는 항목만 표시 -->
                <div class="ctx-file-list">
                  <label
                    v-for="r in (detailMeeting?.reports || []).filter(
                      r =>
                        (r.file_name || r.file_url) &&
                        (r.human_status === 'approved' || r.status === 'approved'),
                    )"
                    :key="'r' + r.id"
                    class="ctx-file-item"
                  >
                    <input
                      type="checkbox"
                      :value="r.id"
                      v-model="selectedFiles"
                      class="ctx-checkbox"
                    />
                    <svg
                      width="10"
                      height="10"
                      fill="none"
                      stroke="currentColor"
                      stroke-width="2"
                      viewBox="0 0 24 24"
                    >
                      <path
                        d="M9 17v-2m3 2v-4m3 4v-6m2 10H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
                      />
                    </svg>
                    <span class="ctx-file-name">{{ r.file_name }}</span>
                    <span class="ctx-file-date">{{
                      r.submitted_at ? formatDate(r.submitted_at) : ''
                    }}</span>
                  </label>
                  <label
                    v-for="f in (detailMeeting?.files || []).filter(
                      f => f.file_name || f.name || f.file_url,
                    )"
                    :key="'f' + f.id"
                    class="ctx-file-item"
                  >
                    <input
                      type="checkbox"
                      :value="f.id"
                      v-model="selectedFiles"
                      class="ctx-checkbox"
                    />
                    <svg
                      width="10"
                      height="10"
                      fill="none"
                      stroke="currentColor"
                      stroke-width="2"
                      viewBox="0 0 24 24"
                    >
                      <path
                        d="M15.172 7l-6.586 6.586a2 2 0 102.828 2.828l6.414-6.585a4 4 0 00-5.656-5.656l-6.415 6.585a6 6 0 108.486 8.486L20.5 13"
                      />
                    </svg>
                    <span class="ctx-file-name">{{ f.file_name || f.name }}</span>
                  </label>
                  <!-- 새로 업로드된 파일 -->
                  <div
                    v-for="(uf, i) in uploadedCtxFiles"
                    :key="'uf' + i"
                    class="ctx-file-item ctx-file-uploaded"
                  >
                    <input
                      v-if="uf.id"
                      type="checkbox"
                      :value="uf.id"
                      v-model="selectedFiles"
                      class="ctx-checkbox"
                    />
                    <svg
                      v-else-if="uf.uploading"
                      class="ctx-uploading-spin"
                      width="10"
                      height="10"
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="#a78bfa"
                      stroke-width="2.5"
                    >
                      <path
                        d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4"
                      />
                    </svg>
                    <svg
                      v-else-if="uf.error"
                      width="10"
                      height="10"
                      fill="none"
                      stroke="#f87171"
                      stroke-width="2"
                      viewBox="0 0 24 24"
                    >
                      <circle cx="12" cy="12" r="10" />
                      <path d="M12 8v4M12 16h.01" />
                    </svg>
                    <svg
                      v-else
                      width="10"
                      height="10"
                      fill="none"
                      stroke="#10b981"
                      stroke-width="2"
                      viewBox="0 0 24 24"
                    >
                      <path
                        d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
                      />
                    </svg>
                    <span class="ctx-file-name">{{ uf.file_name }}</span>
                    <span class="ctx-file-date ctx-new-tag">{{
                      uf.uploading ? '업로드 중…' : uf.error ? '오류' : '대기중'
                    }}</span>
                    <button class="ctx-file-remove" @click.prevent="removeCtxFile(i)">×</button>
                  </div>
                </div>
                <!-- 파일 업로드 영역 -->
                <FileUploadArea multiple @change="onCtxFilesAdded" />
              </div>

              <div class="ctx-section">
                <div class="detail-section-label ctx-section-title-flex">
                  <svg
                    width="11"
                    height="11"
                    fill="none"
                    stroke="currentColor"
                    stroke-width="2"
                    viewBox="0 0 24 24"
                  >
                    <path d="M13 10V3L4 14h7v7l9-11h-7z" />
                  </svg>
                  유사 문서 추천
                </div>
                <div class="ctx-file-list"></div>
              </div>

              <button class="ctx-run-btn" @click="runExtract">
                <svg
                  width="12"
                  height="12"
                  fill="none"
                  stroke="currentColor"
                  stroke-width="2.5"
                  viewBox="0 0 24 24"
                >
                  <path d="M4 4l16 8-16 8V4z" />
                </svg>
                아젠다 추출하기
              </button> </template
            ><!-- /자료선정 단계 -->

            <!-- 추출 결과: 로딩 중이거나 초안이 있을 때 -->
            <template v-if="extractLoading || extractResult.length">
              <div v-if="extractLoading" class="detail-extract-loading">
                <div class="gm-spinner"></div>
                <span>AI가 분석 중입니다...</span>
              </div>
              <template v-else>
                <div class="detail-extract-meta">
                  AI가 {{ extractResult.length }}개 아젠다를 추천했습니다.
                </div>
                <!-- prettier-ignore -->
                <button class="ctx-run-btn" style="margin-top:6px;margin-bottom:6px" @click="goToProcessStep('context')">
                  <svg width="12" height="12" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24"><path d="M4 4l16 8-16 8V4z" /></svg>
                  아젠다 재추출하기
                </button>
                <AgendaReviewList
                  :items="extractResult"
                  :memberCompanies="detailMemberCompanies"
                  :memberDepts="detailMemberDepts"
                  :removeOnApprove="false"
                  :showFooter="true"
                  @approved="() => {}"
                  @rejected="() => {}"
                  @remove="i => extractResult.splice(i, 1)"
                  @save="finishExtract"
                />
              </template> </template
            ><!-- /추출 결과 --> </template
          ><!-- /과제추출 탭 -->

          <!-- ── 관계 탭 ── -->
          <template v-if="detailTab === 'rel'"> <RelationTab /> </template
          ><!-- /관계 탭 -->
        </div> </template
      ><!-- /detailMeeting -->

      <!-- ── Node detail (부서/과제/회의/파일/사람/아젠다) ── -->
      <template v-else-if="detailNode">
        <div class="detail-header">
          <!-- 노드 유형별 아이콘 -->
          <div class="detail-header-icon">
            <!-- 부서 -->
            <svg
              v-if="detailNode.type === 'dept'"
              width="14"
              height="14"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
              viewBox="0 0 24 24"
            >
              <path d="M17 21v-2a4 4 0 00-4-4H5a4 4 0 00-4 4v2" />
              <circle cx="9" cy="7" r="4" />
              <path d="M23 21v-2a4 4 0 00-3-3.87M16 3.13a4 4 0 010 7.75" />
            </svg>
            <!-- 회사 -->
            <svg
              v-else-if="detailNode.type === 'company'"
              width="14"
              height="14"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
              viewBox="0 0 24 24"
            >
              <rect x="4" y="2" width="16" height="20" rx="1" />
              <path d="M9 22v-4h6v4" />
              <path
                d="M8 6h.01M12 6h.01M16 6h.01M8 10h.01M12 10h.01M16 10h.01M8 14h.01M12 14h.01M16 14h.01"
              />
            </svg>
            <!-- 아젠다 -->
            <svg
              v-else-if="detailNode.type === 'agenda'"
              width="14"
              height="14"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
              viewBox="0 0 24 24"
            >
              <path d="M9 11l3 3L22 4" />
              <path d="M21 12v7a2 2 0 01-2 2H5a2 2 0 01-2-2V5a2 2 0 012-2h11" />
            </svg>
            <!-- 회의(session) -->
            <svg
              v-else-if="detailNode.type === 'session'"
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
            <!-- 회의록 -->
            <svg
              v-else-if="detailNode.type === 'minutes'"
              width="14"
              height="14"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
              viewBox="0 0 24 24"
            >
              <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z" />
              <polyline points="14 2 14 8 20 8" />
            </svg>
            <!-- 보고자료 -->
            <svg
              v-else-if="detailNode.type === 'report'"
              width="14"
              height="14"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
              viewBox="0 0 24 24"
            >
              <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z" />
              <polyline points="14 2 14 8 20 8" />
              <line x1="8" y1="13" x2="16" y2="13" />
              <line x1="8" y1="17" x2="16" y2="17" />
            </svg>
            <!-- 사람 -->
            <svg
              v-else
              width="14"
              height="14"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
              viewBox="0 0 24 24"
            >
              <path d="M20 21v-2a4 4 0 00-4-4H8a4 4 0 00-4 4v2" />
              <circle cx="12" cy="7" r="4" />
            </svg>
          </div>
          <div class="detail-header-left">
            <div class="detail-meeting-name">
              {{
                detailNode.type === 'agenda'
                  ? detailNode.data?.content || detailNode.data?.title || detailNode.label
                  : detailNode.label
              }}
            </div>
            <div class="detail-meta-row">
              <span class="detail-meta">{{
                {
                  dept: '부서',
                  agenda: '아젠다',
                  session: detailNode.subType === '안건' ? '안건' : '회의',
                  minutes: '회의록',
                  report: '보고자료',
                  person: '구성원',
                  company: '회사',
                }[detailNode.type] || detailNode.type
              }}</span>
            </div>
          </div>
          <div class="detail-header-actions">
            <button
              v-if="
                detailNode.type === 'dept'
                  ? canEditDept
                  : detailNode.type === 'company'
                    ? canEditCompany
                    : isAnyAdmin
              "
              class="detail-icon-btn"
              @click="openNodeGroupSetting"
            >
              <svg
                width="13"
                height="13"
                fill="none"
                stroke="currentColor"
                stroke-width="2"
                viewBox="0 0 24 24"
              >
                <path d="M12 15a3 3 0 100-6 3 3 0 000 6z" />
                <path
                  d="M19.4 15a1.65 1.65 0 00.33 1.82l.06.06a2 2 0 010 2.83 2 2 0 01-2.83 0l-.06-.06a1.65 1.65 0 00-1.82-.33 1.65 1.65 0 00-1 1.51V21a2 2 0 01-2 2 2 2 0 01-2-2v-.09A1.65 1.65 0 009 19.4a1.65 1.65 0 00-1.82.33l-.06.06a2 2 0 01-2.83 0 2 2 0 010-2.83l.06-.06A1.65 1.65 0 004.68 15a1.65 1.65 0 00-1.51-1H3a2 2 0 01-2-2 2 2 0 012-2h.09A1.65 1.65 0 004.6 9a1.65 1.65 0 00-.33-1.82l-.06-.06a2 2 0 010-2.83 2 2 0 012.83 0l.06.06A1.65 1.65 0 009 4.68a1.65 1.65 0 001-1.51V3a2 2 0 012-2 2 2 0 012 2v.09a1.65 1.65 0 001 1.51 1.65 1.65 0 001.82-.33l.06-.06a2 2 0 012.83 0 2 2 0 010 2.83l-.06.06A1.65 1.65 0 0019.4 9a1.65 1.65 0 001.51 1H21a2 2 0 012 2 2 2 0 01-2 2h-.09a1.65 1.65 0 00-1.51 1z"
                />
              </svg>
            </button>
          </div>
        </div>

        <!-- 탭 -->
        <div class="detail-tabs">
          <button
            class="detail-tab"
            :class="{ active: nodeDetailTab === 'basic' }"
            @click="nodeDetailTab = 'basic'"
          >
            기본
          </button>
          <button
            class="detail-tab"
            :class="{ active: nodeDetailTab === 'rel' }"
            @click="nodeDetailTab = 'rel'"
          >
            관계
          </button>
        </div>

        <div class="detail-body">
          <!-- ── 기본 탭 ── -->
          <template v-if="nodeDetailTab === 'basic'">
            <!-- 부서 -->
            <template v-if="detailNode.type === 'dept'">
              <div class="detail-section">
                <div class="detail-info-grid">
                  <div class="detail-info-item">
                    <span class="detail-info-key">부서명</span>
                    <span class="detail-info-val">{{ detailNode.label }}</span>
                  </div>
                </div>
              </div>
              <div class="detail-section">
                <div class="detail-section-label">부서 구성원</div>
                <div v-if="detailNode.members?.length" class="detail-member-list">
                  <div
                    v-for="mb in detailNode.members"
                    :key="mb.userId || mb.userName"
                    class="detail-member-row"
                  >
                    <div
                      class="detail-member-avatar"
                      :style="{
                        background: mb.role === 'admin' ? 'var(--accent)' : 'var(--text-muted)',
                      }"
                    >
                      {{ (mb.userName || mb.name || '?')[0] }}
                    </div>
                    <div class="detail-member-info">
                      <span class="detail-member-name">{{ mb.userName || mb.name || '-' }}</span>
                      <span class="detail-member-dept">{{
                        mb.role === 'admin' ? '간사' : '참여자'
                      }}</span>
                    </div>
                  </div>
                </div>
                <div v-else class="detail-log-empty">구성원 정보 없음</div>
              </div>
            </template>

            <!-- 조직 -->
            <template v-else-if="detailNode.type === 'company'">
              <div class="detail-section">
                <div class="detail-info-grid">
                  <div class="detail-info-item">
                    <span class="detail-info-key">회사명</span>
                    <span class="detail-info-val">{{
                      detailNode.data?.name || detailNode.label
                    }}</span>
                  </div>
                </div>
              </div>
              <div v-if="meetings.length" class="detail-section">
                <div class="detail-section-label">회의체 목록 ({{ meetings.length }}개)</div>
                <div class="detail-info-grid">
                  <div v-for="mg in meetings" :key="mg.id" class="detail-info-item">
                    <span class="detail-info-val">{{ mg.title }}</span>
                  </div>
                </div>
              </div>
            </template>

            <!-- 아젠다 -->
            <template v-else-if="detailNode.type === 'agenda'">
              <div v-if="parseAiEvidence(detailNode.data?.ai_evidence)" class="detail-section">
                <div class="detail-section-label">AI 추천 아젠다</div>
                <div class="ai-evidence-box">
                  {{ parseAiEvidence(detailNode.data.ai_evidence) }}
                </div>
              </div>
              <div class="detail-section">
                <div class="detail-info-grid">
                  <div class="detail-info-item">
                    <span class="detail-info-key">아젠다명</span>
                    <span class="detail-info-val">{{
                      detailNode.data?.content || detailNode.label
                    }}</span>
                  </div>
                  <div class="detail-info-item">
                    <span class="detail-info-key">상태</span>
                    <span class="detail-info-val">
                      <span
                        class="status-badge"
                        :class="{
                          'sb-done':
                            detailNode.data?.status === '완료' ||
                            detailNode.data?.status === 'done',
                          'sb-progress':
                            detailNode.data?.status === '진행' ||
                            detailNode.data?.status === '진행중' ||
                            detailNode.data?.status === 'in_progress' ||
                            detailNode.data?.status === 'ongoing',
                          'sb-pending':
                            detailNode.data?.status === '대기' ||
                            detailNode.data?.status === 'pending' ||
                            !detailNode.data?.status,
                        }"
                        >{{
                          {
                            done: '완료',
                            ongoing: '진행중',
                            in_progress: '진행중',
                            pending: '대기',
                            완료: '완료',
                            진행중: '진행중',
                            진행: '진행중',
                            대기: '대기',
                          }[detailNode.data?.status] ||
                          detailNode.data?.status ||
                          '-'
                        }}</span
                      >
                    </span>
                  </div>
                  <div class="detail-info-item">
                    <span class="detail-info-key">우선순위</span>
                    <span class="detail-info-val">
                      <span
                        class="status-badge"
                        :class="{
                          'sb-critical': detailNode.data?.priority === 'critical',
                          'sb-high':
                            detailNode.data?.priority === 'high' ||
                            detailNode.data?.priority === '상',
                          'sb-medium':
                            detailNode.data?.priority === 'medium' ||
                            detailNode.data?.priority === '중',
                          'sb-low':
                            detailNode.data?.priority === 'low' ||
                            detailNode.data?.priority === '하',
                          'sb-minimal': detailNode.data?.priority === 'minimal',
                          'sb-pending': !detailNode.data?.priority,
                        }"
                        >{{
                          {
                            critical: '최상',
                            high: '상',
                            medium: '중',
                            low: '하',
                            minimal: '최하',
                            상: '상',
                            중: '중',
                            하: 'v   하',
                          }[detailNode.data?.priority] ||
                          detailNode.data?.priority ||
                          '-'
                        }}</span
                      >
                    </span>
                  </div>
                  <div class="detail-info-item">
                    <span class="detail-info-key">등록일</span>
                    <span class="detail-info-val">{{
                      detailNode.data?.created_at ? formatDate(detailNode.data.created_at) : '-'
                    }}</span>
                  </div>
                  <div class="detail-info-item">
                    <span class="detail-info-key">마감일</span>
                    <span class="detail-info-val">{{
                      detailNode.data?.due_date ? formatDate(detailNode.data.due_date) : '-'
                    }}</span>
                  </div>
                </div>
              </div>
            </template>

            <!-- 회의(session) -->
            <template v-else-if="detailNode.type === 'session'">
              <div class="detail-section">
                <div class="detail-info-grid">
                  <div class="detail-info-item">
                    <span class="detail-info-key">회의명</span>
                    <span class="detail-info-val">{{
                      detailNode.data?.session_title || detailNode.label
                    }}</span>
                  </div>
                  <div class="detail-info-item">
                    <span class="detail-info-key">일시</span>
                    <span class="detail-info-val">{{
                      detailNode.data?.date ? formatDate(detailNode.data.date) : '-'
                    }}</span>
                  </div>
                  <div class="detail-info-item">
                    <span class="detail-info-key">장소</span>
                    <span class="detail-info-val">{{ detailNode.data?.location || '-' }}</span>
                  </div>
                  <div class="detail-info-item">
                    <span class="detail-info-key">상태</span>
                    <span class="detail-info-val">{{
                      {
                        scheduled: '예정',
                        in_progress: '진행중',
                        completed: '완료',
                        cancelled: '취소',
                      }[detailNode.data?.session_status] ||
                      detailNode.data?.session_status ||
                      '-'
                    }}</span>
                  </div>
                  <div v-if="detailNode.data?.description" class="detail-info-item">
                    <span class="detail-info-key">설명</span>
                    <span class="detail-info-val detail-info-val--wrap">{{
                      detailNode.data.description
                    }}</span>
                  </div>
                </div>
              </div>
              <div v-if="detailNode.data?.participants?.length" class="detail-section">
                <div class="detail-section-label">참여자</div>
                <div class="detail-member-list">
                  <div
                    v-for="p in detailNode.data.participants"
                    :key="p.userId || p.userName"
                    class="detail-member-row"
                  >
                    <div class="detail-member-avatar" style="background: var(--text-muted)">
                      {{ (p.userName || p.name || '?')[0] }}
                    </div>
                    <div class="detail-member-info">
                      <span class="detail-member-name">{{ p.userName || p.name }}</span>
                      <span v-if="p.department" class="detail-member-dept">{{ p.department }}</span>
                    </div>
                  </div>
                </div>
              </div>
            </template>

            <!-- 회의록 (minutes) -->
            <template v-else-if="detailNode.type === 'minutes'">
              <!-- 회의 정보 (meeting_sessions) -->
              <div class="detail-section">
                <div class="detail-section-label">회의 정보</div>
                <div class="detail-info-grid">
                  <div class="detail-info-item">
                    <span class="detail-info-key">회의명</span>
                    <span class="detail-info-val">{{
                      detailNode.data?.session_title || detailNode.label
                    }}</span>
                  </div>
                  <div class="detail-info-item">
                    <span class="detail-info-key">회의일자</span>
                    <span class="detail-info-val">{{
                      detailNode.data?.date ? formatDate(detailNode.data.date) : '-'
                    }}</span>
                  </div>
                  <div v-if="detailNode.data?.ended_at" class="detail-info-item">
                    <span class="detail-info-key">종료</span>
                    <span class="detail-info-val">{{ formatDate(detailNode.data.ended_at) }}</span>
                  </div>
                  <div v-if="detailNode.data?.location" class="detail-info-item">
                    <span class="detail-info-key">장소</span>
                    <span class="detail-info-val">{{ detailNode.data.location }}</span>
                  </div>
                  <div v-if="detailNode.data?.session_status" class="detail-info-item">
                    <span class="detail-info-key">상태</span>
                    <span class="detail-info-val">{{
                      {
                        scheduled: '예정',
                        in_progress: '진행중',
                        completed: '완료',
                        cancelled: '취소',
                      }[detailNode.data.session_status] || detailNode.data.session_status
                    }}</span>
                  </div>
                  <div v-if="detailNode.data?.description" class="detail-info-item">
                    <span class="detail-info-key">설명</span>
                    <span class="detail-info-val detail-info-val--wrap">{{
                      detailNode.data.description
                    }}</span>
                  </div>
                </div>
              </div>
              <!-- 회의록 정보 (minutes) -->
              <div class="detail-section">
                <div class="detail-section-label">회의록</div>
                <div class="detail-info-grid">
                  <div v-if="detailNode.data?.minutes_status" class="detail-info-item">
                    <span class="detail-info-key">작성상태</span>
                    <span class="detail-info-val">{{
                      { draft: '초안', completed: '완료', published: '배포' }[
                        detailNode.data.minutes_status
                      ] || detailNode.data.minutes_status
                    }}</span>
                  </div>
                  <div v-if="detailNode.data?.generated_at" class="detail-info-item">
                    <span class="detail-info-key">생성일</span>
                    <span class="detail-info-val">{{
                      formatDate(detailNode.data.generated_at)
                    }}</span>
                  </div>
                  <div class="detail-info-item">
                    <span class="detail-info-key">파일</span>
                    <span class="detail-info-val">
                      <button
                        class="dl-icon-btn"
                        :title="detailNode.data?.file_name || '회의록 다운로드'"
                        @click="downloadDummy(detailNode)"
                      >
                        <svg
                          width="14"
                          height="14"
                          fill="none"
                          stroke="currentColor"
                          stroke-width="2"
                          viewBox="0 0 24 24"
                        >
                          <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4" />
                          <polyline points="7 10 12 15 17 10" />
                          <line x1="12" y1="15" x2="12" y2="3" />
                        </svg>
                      </button>
                    </span>
                  </div>
                </div>
              </div>
              <!-- 내용 요약 -->
              <div v-if="detailNode.data?.content_summary" class="detail-section">
                <div class="detail-section-label">AI 요약</div>
                <div
                  class="ai-evidence-box"
                  style="max-height: 300px; overflow-y: auto; font-size: 12px"
                  v-html="DOMPurify.sanitize(detailNode.data.content_summary)"
                ></div>
              </div>
            </template>

            <!-- 파일(보고자료) -->
            <template v-else-if="detailNode.type === 'report'">
              <div class="detail-section">
                <div class="detail-info-grid">
                  <div class="detail-info-item">
                    <span class="detail-info-key">파일명</span>
                    <span class="detail-info-val">{{
                      detailNode.data?.file_name || detailNode.data?.title || detailNode.label
                    }}</span>
                  </div>
                  <div class="detail-info-item">
                    <span class="detail-info-key">파일</span>
                    <span class="detail-info-val detail-btn-row">
                      <button
                        class="dl-icon-btn"
                        :title="
                          detailNode.data?.title || detailNode.data?.file_name || '파일 다운로드'
                        "
                        @click="downloadDummy(detailNode)"
                      >
                        <svg
                          width="14"
                          height="14"
                          fill="none"
                          stroke="currentColor"
                          stroke-width="2"
                          viewBox="0 0 24 24"
                        >
                          <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4" />
                          <polyline points="7 10 12 15 17 10" />
                          <line x1="12" y1="15" x2="12" y2="3" />
                        </svg>
                      </button>
                      <button
                        class="dl-icon-btn delete"
                        title="삭제"
                        @click="deleteReport(detailNode.data?.id || detailNode.reportId)"
                      >
                        <svg
                          width="14"
                          height="14"
                          fill="none"
                          stroke="currentColor"
                          stroke-width="2"
                          viewBox="0 0 24 24"
                        >
                          <polyline points="3 6 5 6 21 6" />
                          <path d="M19 6l-1 14a2 2 0 01-2 2H8a2 2 0 01-2-2L5 6" />
                          <path d="M10 11v6M14 11v6" />
                          <path d="M9 6V4a1 1 0 011-1h4a1 1 0 011 1v2" />
                        </svg>
                      </button>
                    </span>
                  </div>
                  <div class="detail-info-item">
                    <span class="detail-info-key">업로드일</span>
                    <span class="detail-info-val">{{
                      detailNode.data?.created_at
                        ? formatDate(detailNode.data.created_at)
                        : detailNode.data?.submitted_at
                          ? formatDate(detailNode.data.submitted_at)
                          : '-'
                    }}</span>
                  </div>
                  <div class="detail-info-item">
                    <span class="detail-info-key">작성부서</span>
                    <span class="detail-info-val">{{
                      detailNode.data?.submitter_department || detailNode.data?.department || '-'
                    }}</span>
                  </div>
                  <div
                    v-if="detailNode.type === 'report' && !(detailNode.data?.version === 1 && !detailNode.data?.parent_id)"
                    class="detail-info-item"
                  >
                    <span class="detail-info-key">검토상태</span>
                    <span class="detail-info-val">{{
                      { pending: '검토중', approved: '승인', rejected: '반려' }[
                        detailNode.data?.human_status
                      ] ||
                      detailNode.data?.human_status ||
                      '-'
                    }}</span>
                  </div>
                </div>
              </div>

              <!-- AI 검토 결과 — 레이더 차트 (report 타입, 첫 번째 자료 제외) -->
              <div v-if="detailNode.type === 'report' && !(detailNode.data?.version === 1 && !detailNode.data?.parent_id)" class="detail-section">
                <div class="detail-section-label">AI 검토 결과</div>
                <div class="radar-wrap">
                  <div class="radar-svg-pos">
                    <svg viewBox="0 0 180 190" class="radar-svg" style="overflow: visible">
                      <polygon
                        :points="sbGridPoly"
                        fill="none"
                        stroke="rgba(255,255,255,.12)"
                        stroke-width="1"
                      />
                      <polygon
                        :points="sbGridPoly2"
                        fill="none"
                        stroke="rgba(255,255,255,.07)"
                        stroke-width="0.7"
                      />
                      <polygon
                        :points="sbGridPoly3"
                        fill="none"
                        stroke="rgba(255,255,255,.07)"
                        stroke-width="0.7"
                      />
                      <line
                        v-for="(ax, i) in sbAxisLines"
                        :key="'ax' + i"
                        :x1="SB_CX"
                        :y1="SB_CY"
                        :x2="ax.x2"
                        :y2="ax.y2"
                        stroke="rgba(255,255,255,.09)"
                        stroke-width="0.8"
                      />
                      <polygon
                        v-if="detailNode.data?.total_score != null"
                        :points="sbScorePoly"
                        :fill="sbScoreColor + '2e'"
                        :stroke="sbScoreColor"
                        stroke-width="1.8"
                      />
                      <text
                        v-for="(lp, i) in sbLabelPos"
                        :key="'lb' + i"
                        :x="lp.x"
                        :y="lp.y"
                        text-anchor="middle"
                        dominant-baseline="middle"
                        font-size="10"
                        fill="#aaa"
                        font-family="sans-serif"
                      >
                        {{ lp.label }}
                      </text>
                      <circle :cx="SB_CX" :cy="SB_CY" r="26" class="radar-center-bg" />
                      <text
                        v-if="detailNode.data?.total_score != null"
                        :x="SB_CX"
                        :y="SB_CY - 6"
                        text-anchor="middle"
                        dominant-baseline="middle"
                        font-size="22"
                        font-weight="700"
                        :fill="sbScoreColor"
                      >
                        {{ detailNode.data.total_score }}
                      </text>
                      <text
                        v-if="detailNode.data?.total_score != null"
                        :x="SB_CX"
                        :y="SB_CY + 13"
                        text-anchor="middle"
                        dominant-baseline="middle"
                        font-size="10"
                        fill="#888"
                      >
                        / 100
                      </text>
                    </svg>
                    <!-- 검토하기 버튼: SVG 중앙에 절대 위치 오버레이 -->
                    <button
                      v-if="detailNode.data?.total_score == null"
                      class="sb-review-btn sb-review-btn--center"
                      :disabled="nodeReviewing"
                      @click="startNodeReview(detailNode.data?.id)"
                    >
                      <span v-if="nodeReviewing" class="sb-review-spinner"></span>
                      <svg
                        v-else
                        width="11"
                        height="11"
                        fill="none"
                        stroke="currentColor"
                        stroke-width="2.5"
                        viewBox="0 0 24 24"
                      >
                        <path d="M4 4l16 8-16 8V4z" />
                      </svg>
                      {{ nodeReviewing ? 'AI 검토 중...' : 'AI 검토' }}
                    </button>
                  </div>
                  <div
                    v-if="detailNode.data?.total_score != null && detailNode.data?.detail_scores"
                    class="criteria-scores"
                  >
                    <div v-for="c in SB_CRITERIA" :key="c.key" class="cs-row">
                      <span class="cs-label">{{ c.label }}</span>
                      <div class="cs-bar-wrap">
                        <div
                          class="cs-bar"
                          :style="{
                            width:
                              ((detailNode.data.detail_scores[c.key]?.score ?? 0) / c.max) * 100 +
                              '%',
                            background: sbScoreColor,
                          }"
                        />
                      </div>
                      <span class="cs-num"
                        >{{ detailNode.data.detail_scores[c.key]?.score ?? 0 }}/{{ c.max }}</span
                      >
                    </div>
                  </div>
                </div>
              </div>
              <div
                v-if="detailNode.type === 'report' && detailNode.data?.feedback && !(detailNode.data?.version === 1 && !detailNode.data?.parent_id)"
                class="detail-section"
              >
                <div class="detail-section-label">AI 피드백</div>
                <div class="rs-feedback-box" style="white-space: pre-line">
                  {{
                    Array.isArray(detailNode.data.feedback)
                      ? detailNode.data.feedback.join('\n')
                      : detailNode.data.feedback
                  }}
                </div>
              </div>

              <!-- 우선 개선사항 -->
              <div
                v-if="detailNode.type === 'report' && sbTopImprovements.length && !(detailNode.data?.version === 1 && !detailNode.data?.parent_id)"
                class="detail-section"
              >
                <div class="detail-section-label">
                  <svg
                    width="11"
                    height="11"
                    fill="none"
                    stroke="#f59e0b"
                    stroke-width="2"
                    viewBox="0 0 24 24"
                    style="vertical-align: -1px; margin-right: 3px"
                  >
                    <path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z" />
                  </svg>
                  우선 개선사항
                </div>
                <div class="sb-top-improvements">
                  <div v-for="(imp, i) in sbTopImprovements" :key="i" class="sb-top-item">
                    <span class="sb-top-num">{{ i + 1 }}</span>
                    <span class="sb-top-cat">[{{ imp.category }}]</span>
                    <span class="sb-top-action">{{ imp.action }}</span>
                  </div>
                </div>
              </div>

              <!-- 연관 아젠다 -->
              <div v-if="detailNode.type === 'report'" class="detail-section">
                <div class="detail-section-label">연관 아젠다</div>
                <template v-if="reportRelatedAgendas(detailNode).length">
                  <div class="detail-info-grid">
                    <div
                      v-for="ag in reportRelatedAgendas(detailNode)"
                      :key="ag.data?.id"
                      class="detail-info-item"
                    >
                      <span class="detail-info-key">
                        <span
                          class="status-badge"
                          :class="{
                            'sb-done': ag.data?.status === 'done' || ag.data?.status === '완료',
                            'sb-progress':
                              ag.data?.status === 'in_progress' ||
                              ag.data?.status === 'ongoing' ||
                              ag.data?.status === '진행',
                            'sb-pending':
                              !ag.data?.status ||
                              ag.data?.status === 'pending' ||
                              ag.data?.status === '대기',
                          }"
                        >
                          {{
                            {
                              done: '완료',
                              in_progress: '진행',
                              ongoing: '진행',
                              pending: '대기',
                              진행: '진행',
                              완료: '완료',
                              대기: '대기',
                            }[ag.data?.status] || '대기'
                          }}
                        </span>
                      </span>
                      <span class="detail-info-val detail-info-val--wrap">{{
                        ag.data?.content || ag.label
                      }}</span>
                    </div>
                  </div>
                </template>
                <div v-else class="detail-log-empty">연관된 아젠다가 없습니다.</div>
              </div>
            </template>

            <!-- 구성원 (person) -->
            <template v-else-if="detailNode.type === 'person'">
              <div class="detail-section">
                <div class="detail-info-grid">
                  <div class="detail-info-item">
                    <span class="detail-info-key">회사</span>
                    <span class="detail-info-val">{{
                      detailNode.data?.company || currentCompany?.name || '-'
                    }}</span>
                  </div>
                  <div class="detail-info-item">
                    <span class="detail-info-key">부서</span>
                    <span class="detail-info-val">{{ detailNode.data?.department || '-' }}</span>
                  </div>
                  <div class="detail-info-item">
                    <span class="detail-info-key">직책</span>
                    <span class="detail-info-val">{{ detailNode.data?.position || '-' }}</span>
                  </div>
                </div>
              </div>
              <div class="detail-section">
                <div class="detail-section-label">참여 회의체</div>
                <div v-if="personMeetings(detailNode).length" class="person-mg-list">
                  <div v-for="mg in personMeetings(detailNode)" :key="mg.id" class="person-mg-item">
                    <span
                      class="detail-role-badge"
                      :class="mg.role === 'admin' ? 'role-admin' : 'role-member'"
                      >{{ mg.role === 'admin' ? '간사' : '참여' }}</span
                    >
                    <span class="person-mg-title">{{ mg.title }}</span>
                  </div>
                </div>
                <div v-else class="detail-log-empty">회의체 정보 없음</div>
              </div>
            </template> </template
          ><!-- /기본 탭 -->

          <!-- ── 관계 탭 ── -->
          <template v-if="nodeDetailTab === 'rel'"> <RelationTab /> </template
          ><!-- /관계 탭 -->
        </div> </template
      ><!-- /detailNode -->
    </div>
  </Transition>

  <!-- Sidebar toggle handle — visible whenever a meeting or node is selected -->
  <button
    v-if="(detailMeeting || detailNode) && viewMode === 'graph'"
    class="sidebar-toggle-handle"
    :style="{
      left: (detailOpen ? sidebarW : 0) + 'px',
      transition: 'left 0.28s cubic-bezier(.22,.68,0,1.2)',
    }"
    @click="detailOpen = !detailOpen"
    :title="detailOpen ? '사이드바 접기' : '사이드바 펼치기'"
  >
    <svg width="8" height="14" viewBox="0 0 8 14" fill="none" xmlns="http://www.w3.org/2000/svg">
      <path
        v-if="detailOpen"
        d="M6 1L1 7L6 13"
        stroke="currentColor"
        stroke-width="1.8"
        stroke-linecap="round"
        stroke-linejoin="round"
      />
      <path
        v-else
        d="M2 1L7 7L2 13"
        stroke="currentColor"
        stroke-width="1.8"
        stroke-linecap="round"
        stroke-linejoin="round"
      />
    </svg>
  </button>
</template>

<style scoped>
.ai-evidence-box :deep(h1),
.ai-evidence-box :deep(h2),
.ai-evidence-box :deep(h3) {
  font-size: 1em;
  font-weight: 600;
  margin: 4px 0;
}
.ai-evidence-box :deep(table) {
  width: 100%;
  max-width: 100%;
  table-layout: fixed;
  border-collapse: collapse;
  font-size: 12px;
}
.ai-evidence-box :deep(th),
.ai-evidence-box :deep(td) {
  word-break: break-word;
  white-space: normal;
  padding: 4px 6px;
}
.ai-evidence-box :deep(th):nth-child(1),
.ai-evidence-box :deep(td):nth-child(1) {
  width: 20%;
}
.ai-evidence-box :deep(th):nth-child(2),
.ai-evidence-box :deep(td):nth-child(2) {
  width: 50%;
}
.ai-evidence-box :deep(th):nth-child(3),
.ai-evidence-box :deep(td):nth-child(3) {
  width: 30%;
}
</style>
