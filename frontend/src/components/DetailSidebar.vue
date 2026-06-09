<script setup>
import { inject, computed } from 'vue'
import SidebarInfoRow from './SidebarInfoRow.vue'
import ProcessStepBar from './ProcessStepBar.vue'
import FileUploadArea from './FileUploadArea.vue'
import DateInput from './DateInput.vue'

const {
  detailOpen, sidebarW, onSidebarResizeStart,
  detailMeeting, isDetailAdmin, openGroupSetting,
  detailTab, showExtractFlow, nodeDetailTab,
  detailDday, detailEndDateFormatted, detailDeptStatus,
  groupHistoryMap, goToList, formatDate,
  detailTodos, groupedTodos, completeTodo, deleteTodo,
  extractPhase, extractLoading, extractResult,
  selectedFiles, uploadedCtxFiles, selectedSimilarDocs, onCtxFilesAdded,
  runExtract, setExtractState, addExtractItem, finishExtract,
  saveAgendaFeedback,
  detailMemberDepts,
  goToProcessStep,
  PRIORITY_LABEL, STATUS_LABEL,
  currentNodeEdges, relEditIdx, relEditRel, ALL_REL_TYPES, REL_COLORS,
  saveRelEdit, cancelRelEdit, startRelEdit, doDeleteEdge,
  relAddActive, openAddRel, allGraphNodeList, relAddForm, doAddRel,
  detailNode, downloadDummy, downloadFile, deleteReport, currentOrg, personMeetingGroups, personTasks,
  meetingGroups,
  viewMode,
  nodeReviewing, startNodeReview,
} = inject('archiveSidebar')

// ── 보고자료 레이더 차트 ─────────────────────────────────────────
const SB_CX = 90, SB_CY = 95, SB_R = 60
const SB_CRITERIA = [
  { key: '목적및배경',   label: '목적/배경',  max: 15 },
  { key: '현황분석',     label: '현황분석',   max: 20 },
  { key: '핵심내용',     label: '핵심내용',   max: 20 },
  { key: '실행계획',     label: '실행계획',   max: 20 },
  { key: '기대효과',     label: '기대효과',   max: 15 },
  { key: '리스크및대안', label: '리스크/대안', max: 10 },
]
function sbPt(angleDeg, r) {
  const a = angleDeg * Math.PI / 180
  return `${(SB_CX + r * Math.cos(a)).toFixed(1)},${(SB_CY + r * Math.sin(a)).toFixed(1)}`
}
const sbGridPoly  = SB_CRITERIA.map((_, i) => sbPt(i * 60 - 90, SB_R)).join(' ')
const sbGridPoly2 = SB_CRITERIA.map((_, i) => sbPt(i * 60 - 90, SB_R * 0.66)).join(' ')
const sbGridPoly3 = SB_CRITERIA.map((_, i) => sbPt(i * 60 - 90, SB_R * 0.33)).join(' ')
const sbAxisLines = SB_CRITERIA.map((_, i) => {
  const a = (i * 60 - 90) * Math.PI / 180
  return { x2: (SB_CX + SB_R * Math.cos(a)).toFixed(1), y2: (SB_CY + SB_R * Math.sin(a)).toFixed(1) }
})
const sbLabelPos = SB_CRITERIA.map((c, i) => {
  const a = (i * 60 - 90) * Math.PI / 180
  return { x: (SB_CX + (SB_R + 22) * Math.cos(a)).toFixed(1), y: (SB_CY + (SB_R + 22) * Math.sin(a)).toFixed(1), label: c.label }
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
</script>

<template>
        <Transition name="sidebar-slide">
          <div v-if="detailOpen" class="detail-sidebar" :style="{ width: sidebarW+'px' }">
          <div class="sidebar-resize-handle" @mousedown="onSidebarResizeStart"></div>

          <!-- ── Header: meeting_group ── -->
          <template v-if="detailMeeting">
          <div class="detail-header">
            <div class="detail-header-icon">
              <svg width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M17 21v-2a4 4 0 00-4-4H5a4 4 0 00-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 00-3-3.87M16 3.13a4 4 0 010 7.75"/></svg>
            </div>
            <div class="detail-header-left">
              <div class="detail-name-badge-row">
                <div class="detail-meeting-name">{{ detailMeeting?.title }}</div>
                <div class="detail-role-badge" :class="isDetailAdmin ? 'role-admin' : 'role-member'">{{ isDetailAdmin ? '간사' : '참여자' }}</div>
              </div>
              <div class="detail-meta-row">
                <span class="detail-meta">{{ detailMeeting?.members?.length||0 }}명</span>
                <span class="detail-meta-dot">·</span>
                <span class="detail-meta">{{ (detailMeeting?.minutes?.length||0)+(detailMeeting?.reports?.length||0) }}건</span>
                <template v-if="detailMeeting?.meeting_type">
                  <span class="detail-meta-dot">·</span>
                  <span class="detail-meta">{{ detailMeeting.meeting_type }}</span>
                </template>
              </div>
            </div>
            <div class="detail-header-actions">
              <button v-if="isDetailAdmin" class="detail-icon-btn" @click="openGroupSetting" title="회의체 설정 (간사만 가능)">
                <svg width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M12 15a3 3 0 100-6 3 3 0 000 6z"/><path d="M19.4 15a1.65 1.65 0 00.33 1.82l.06.06a2 2 0 010 2.83 2 2 0 01-2.83 0l-.06-.06a1.65 1.65 0 00-1.82-.33 1.65 1.65 0 00-1 1.51V21a2 2 0 01-2 2 2 2 0 01-2-2v-.09A1.65 1.65 0 009 19.4a1.65 1.65 0 00-1.82.33l-.06.06a2 2 0 01-2.83 0 2 2 0 010-2.83l.06-.06A1.65 1.65 0 004.68 15a1.65 1.65 0 00-1.51-1H3a2 2 0 01-2-2 2 2 0 012-2h.09A1.65 1.65 0 004.6 9a1.65 1.65 0 00-.33-1.82l-.06-.06a2 2 0 010-2.83 2 2 0 012.83 0l.06.06A1.65 1.65 0 009 4.68a1.65 1.65 0 001-1.51V3a2 2 0 012-2 2 2 0 012 2v.09a1.65 1.65 0 001 1.51 1.65 1.65 0 001.82-.33l.06-.06a2 2 0 012.83 0 2 2 0 010 2.83l-.06.06A1.65 1.65 0 0019.4 9a1.65 1.65 0 001.51 1H21a2 2 0 012 2 2 2 0 01-2 2h-.09a1.65 1.65 0 00-1.51 1z"/></svg>
              </button>
            </div>
          </div>

          <!-- 탭 -->
          <div class="detail-tabs">
            <button class="detail-tab" :class="{ active: detailTab==='basic' }" @click="detailTab='basic'">기본</button>
            <button class="detail-tab" :class="{ active: detailTab==='task' }" @click="detailTab='task'">과제</button>
            <button class="detail-tab detail-tab-extract" :class="{ active: detailTab==='extract' }" @click="detailTab='extract'; if(!showExtractFlow) showExtractFlow=true">과제추출</button>
            <button class="detail-tab" :class="{ active: detailTab==='rel' }" @click="detailTab='rel'">관계</button>
          </div>

          <div class="detail-body">

            <!-- ── 기본 탭 ── -->
            <template v-if="detailTab==='basic'">

            <!-- 소개 -->
            <div v-if="detailMeeting?.purpose || detailMeeting?.description" class="detail-section">
              <div class="detail-section-label">소개</div>
              <div class="detail-purpose">{{ detailMeeting.purpose || detailMeeting.description }}</div>
            </div>

            <!-- 간사 + 참여부서 -->
            <div class="detail-section" style="gap:7px">
              <SidebarInfoRow label="간사" :value="detailMeeting?.members?.find(mb => mb.role === 'admin')?.userName || detailMeeting?.members?.find(mb => mb.role === 'admin')?.name || '-'" />
              <SidebarInfoRow label="참여부서" :value="[...new Set((detailMeeting?.members||[]).map(mb => mb.department||mb.dept||'').filter(Boolean))].join(' · ') || '-'" />
              <SidebarInfoRow label="최종 보고일">
                <div style="display:flex;align-items:center;gap:4px;flex-wrap:nowrap;overflow:hidden">
                  <template v-if="detailDday !== null">
                    <span class="dday-date" style="white-space:nowrap">{{ detailEndDateFormatted }}</span>
                    <span class="dday-badge" :class="detailDday <= 0 ? 'dday-over' : detailDday <= 1 ? 'dday-critical' : detailDday <= 3 ? 'dday-warning' : 'dday-normal'" style="white-space:nowrap">{{ detailDday <= 0 ? '마감 초과' : `D-${detailDday}` }}</span>
                  </template>
                  <span v-else class="dday-label" style="font-size:10px;white-space:nowrap">없음</span>
                </div>
              </SidebarInfoRow>
            </div>

            <!-- 팀 제출 현황 -->
            <div class="detail-section">
              <div class="detail-section-label-row">
                <span class="detail-section-label">팀 제출 현황</span>
                <span class="dept-submit-summary">
                  <span class="dss-done">{{ detailDeptStatus.filter(d=>d.submitted).length }}팀 완료</span>
                  <template v-if="detailDeptStatus.filter(d=>!d.submitted && !d.noTask).length">
                    <span class="dss-sep">·</span>
                    <span class="dss-pending">{{ detailDeptStatus.filter(d=>!d.submitted && !d.noTask).length }}팀 미제출</span>
                  </template>
                </span>
              </div>
              <template v-if="detailDeptStatus.length">
                <div class="dept-submit-list">
                  <div v-for="ds in detailDeptStatus" :key="ds.dept" class="dept-submit-item" :class="{ 'dsi-done': ds.submitted, 'dsi-pending': !ds.submitted, 'dsi-urgent': !ds.submitted && ds.minDays !== null && ds.minDays <= 3 }">
                    <div class="dsi-dot" :class="{ 'dsi-dot-done': ds.submitted, 'dsi-dot-pending': !ds.submitted, 'dsi-dot-urgent': !ds.submitted && ds.minDays !== null && ds.minDays <= 3 }"></div>
                    <span class="dsi-name">{{ ds.dept }}</span>
                    <template v-if="ds.noTask">
                      <span class="dsi-status" style="color:#94a3b8">과제 없음</span>
                    </template>
                    <template v-else-if="ds.submitted">
                      <span class="dsi-status dsi-status-done">제출 완료</span>
                    </template>
                    <template v-else>
                      <span class="dsi-status dsi-status-pending">미제출 {{ ds.pendingCount }}건</span>
                      <span v-if="ds.minDays !== null" class="dsi-deadline" :class="{ 'dsi-deadline-urgent': ds.minDays <= 3, 'dsi-deadline-critical': ds.minDays <= 1 }">
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
                <button v-if="(groupHistoryMap.get(detailMeeting?.id)||[]).length > 3" class="detail-more-btn" @click="goToList(detailMeeting?.id)">전체 {{ (groupHistoryMap.get(detailMeeting?.id)||[]).length }}건 →</button>
              </div>
              <div class="detail-log-list">
                <template v-if="(groupHistoryMap.get(detailMeeting?.id)||[]).length">
                  <div v-for="(item, i) in (groupHistoryMap.get(detailMeeting?.id)||[]).slice(0,3)" :key="i" class="detail-log-item">
                    <span class="detail-log-dot" :class="'ht-'+item.type"></span>
                    <div class="detail-log-content">
                      <div class="detail-log-desc">{{ item.desc }}</div>
                      <div class="detail-log-meta">{{ item.manager }} · {{ formatDate(item.date) }}</div>
                    </div>
                  </div>
                </template>
                <div v-else class="detail-log-empty">기록된 로그가 없습니다.</div>
              </div>
            </div>

            </template><!-- /기본 탭 -->

            <!-- ── 과제 탭 ── -->
            <template v-if="detailTab==='task'">

                <!-- 등록된 과제 목록 (맨 위) -->
                <div class="detail-section">
                  <div class="detail-section-label-row">
                    <span class="detail-section-label">등록된 과제</span>
                    <span class="detail-section-label" style="font-weight:400">{{ detailTodos.length }}건</span>
                  </div>
                  <div v-if="!detailTodos.length" class="detail-log-empty">등록된 과제가 없습니다.</div>
                  <template v-else>
                    <div v-for="(todos, dept) in groupedTodos" :key="dept" class="todo-dept-group">
                      <div class="todo-dept-header">
                        <span class="todo-dept-name">{{ dept || '미배정' }}</span>
                        <span class="todo-dept-count">{{ todos.length }}건</span>
                      </div>
                      <div class="detail-todo-list">
                        <div v-for="todo in todos" :key="todo.id||todo.content" class="detail-todo-item">
                          <div class="detail-todo-status" :class="{
                            'ts-done': todo.status==='done',
                            'ts-progress': todo.status==='in_progress'||todo.status==='ongoing',
                            'ts-risk': todo.status==='at_risk',
                            'ts-pending': !todo.status||todo.status==='pending'
                          }">
                            {{ todo.status==='done' ? '완료' : todo.status==='in_progress'||todo.status==='ongoing' ? '진행' : todo.status==='at_risk' ? '위험' : '대기' }}
                          </div>
                          <div class="detail-todo-info">
                            <div class="detail-todo-title">{{ todo.content || todo.title }}</div>
                            <div class="detail-todo-meta">
                              <span v-if="todo.dept||(Array.isArray(todo.department)?todo.department[0]:todo.department)">{{ todo.dept || (Array.isArray(todo.department)?todo.department[0]:todo.department) }}</span>
                              <span v-if="todo.due_date"> · {{ formatDate(todo.due_date) }}</span>
                            </div>
                          </div>
                          <div class="detail-todo-actions">
                            <button class="todo-action-btn todo-done-btn" :class="{'is-done': todo.status==='done'}" @click="completeTodo(todo)" title="완료/취소">✓</button>
                            <button class="todo-action-btn todo-del-btn" @click="deleteTodo(todo)" title="삭제">✕</button>
                          </div>
                        </div>
                      </div>
                    </div>
                  </template>
                </div>

                <!-- AI 과제 추출 실행 버튼 -->
                <button class="ctx-run-btn" @click="showExtractFlow=true; detailTab='extract'">
                  <svg width="12" height="12" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24"><path d="M4 4l16 8-16 8V4z"/></svg>
                  AI 과제 추출 실행
                </button>

            </template><!-- /과제 탭 -->

            <!-- ── 과제추출 탭 ── -->
            <template v-if="detailTab==='extract'">

                <!-- 프로세스 인디케이터: 초안이 없을 때만 표시 -->
                <div class="task-process-bar" v-if="!extractResult.length && !extractLoading">
                  <ProcessStepBar
                    :steps="['자료선정', '추출']"
                    :current-step="0"
                    @step-click="() => {}"
                  />
                </div>

                <!-- 자료선정 단계: 초안이 없을 때만 -->
                <template v-if="!extractResult.length && !extractLoading">
                  <div class="ctx-section">
                    <div class="detail-section-label ctx-section-title-flex">
                      <svg width="11" height="11" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M15.172 7l-6.586 6.586a2 2 0 102.828 2.828l6.414-6.586a4 4 0 00-5.656-5.656l-6.415 6.585a6 6 0 108.486 8.486L20.5 13"/></svg>
                      추가 자료 선택
                    </div>
                    <!-- 기존 자료 목록: 실제 파일이 있는 항목만 표시 -->
                    <div class="ctx-file-list">
                      <label v-for="r in (detailMeeting?.reports||[]).filter(r=>r.file_name||r.file_url)" :key="'r'+r.id" class="ctx-file-item">
                        <input type="checkbox" :value="r.id" v-model="selectedFiles" class="ctx-checkbox" />
                        <svg width="10" height="10" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M9 17v-2m3 2v-4m3 4v-6m2 10H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"/></svg>
                        <span class="ctx-file-name">{{ r.file_name }}</span>
                        <span class="ctx-file-date">{{ r.submitted_at ? formatDate(r.submitted_at) : '' }}</span>
                      </label>
                      <label v-for="f in (detailMeeting?.files||[]).filter(f=>f.file_name||f.name||f.file_url)" :key="'f'+f.id" class="ctx-file-item">
                        <input type="checkbox" :value="f.id" v-model="selectedFiles" class="ctx-checkbox" />
                        <svg width="10" height="10" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M15.172 7l-6.586 6.586a2 2 0 102.828 2.828l6.414-6.585a4 4 0 00-5.656-5.656l-6.415 6.585a6 6 0 108.486 8.486L20.5 13"/></svg>
                        <span class="ctx-file-name">{{ f.file_name || f.name }}</span>
                      </label>
                      <!-- 새로 업로드된 파일 -->
                      <div v-for="(uf, i) in uploadedCtxFiles" :key="'uf'+i" class="ctx-file-item ctx-file-uploaded">
                        <input type="checkbox" :value="'upload_'+i" v-model="selectedFiles" class="ctx-checkbox" checked />
                        <svg width="10" height="10" fill="none" stroke="#10b981" stroke-width="2" viewBox="0 0 24 24"><path d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"/></svg>
                        <span class="ctx-file-name">{{ uf.name }}</span>
                        <span class="ctx-file-date ctx-new-tag">새 파일</span>
                        <button class="ctx-file-remove" @click.prevent="uploadedCtxFiles.splice(i,1)">×</button>
                      </div>
                    </div>
                    <!-- 파일 업로드 영역 -->
                    <FileUploadArea multiple @change="onCtxFilesAdded" />
                  </div>

                  <div class="ctx-section">
                    <div class="detail-section-label ctx-section-title-flex">
                      <svg width="11" height="11" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M13 10V3L4 14h7v7l9-11h-7z"/></svg>
                      유사 문서 추천
                    </div>
                    <div class="ctx-file-list"></div>
                  </div>

                  <button class="ctx-run-btn" @click="runExtract">
                    <svg width="12" height="12" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24"><path d="M4 4l16 8-16 8V4z"/></svg>
                    과제 추출하기
                  </button>
                </template><!-- /자료선정 단계 -->

                <!-- 추출 결과: 로딩 중이거나 초안이 있을 때 -->
                <template v-if="extractLoading || extractResult.length">
                    <div v-if="extractLoading" class="detail-extract-loading"><div class="gm-spinner"></div><span>AI가 분석 중입니다...</span></div>
                    <template v-else>
                      <div class="detail-extract-meta">AI가 {{ extractResult.length }}개 과제를 추천했습니다.</div>
                      <div class="detail-extract-list">
                        <template v-for="(ag, i) in extractResult" :key="i">
                          <div class="detail-extract-item" :class="{ 'ei-approved': ag._state==='approved', 'ei-rejected': ag._state==='rejected' }">
                            <div class="dei-num">{{ i+1 }}</div>
                            <div class="dei-body">
                              <template v-if="!ag._editing">
                                <div class="dei-title dei-title-bold">{{ ag.title }}</div>
                                <div class="dei-meta" v-if="ag.department">{{ Array.isArray(ag.department) ? ag.department.join(', ') : ag.department }}</div>
                                <div class="dei-dates" v-if="ag.start_date || ag.due_date">
                                  <div v-if="ag.start_date">시작 {{ ag.start_date }}</div>
                                  <div v-if="ag.due_date">마감 {{ ag.due_date }}</div>
                                </div>
                              </template>
                              <template v-else>
                                <input class="dei-input" v-model="ag._editTitle" placeholder="과제 제목" />
                                <select class="app-select dei-app-select" v-model="ag._editDept" style="margin-top:4px;width:100%">
                                  <option value="">담당부서 선택</option>
                                  <option v-for="d in detailMemberDepts" :key="d" :value="d">{{ d }}</option>
                                </select>
                                <div class="dei-date-row">
                                  <DateInput class="dei-input dei-date-input" v-model="ag._editStartDate" />
                                  <DateInput class="dei-input dei-date-input" v-model="ag._editDueDate" />
                                </div>
                              </template>
                            </div>
                            <div class="dei-actions">
                              <template v-if="!ag._editing">
                                <button class="gm-ei-btn gm-ei-edit" @click="ag._origTitle=ag.title; ag._origDept=ag.department; ag._origStartDate=ag.start_date; ag._origEndDate=ag.due_date; ag._editing=true; ag._feedbackVisible=true; ag._feedbackAction='edited'; ag._feedbackText=''"><svg width="10" height="10" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M11 4H4a2 2 0 00-2 2v14a2 2 0 002 2h14a2 2 0 002-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 013 3L12 15l-4 1 1-4 9.5-9.5z"/></svg></button>
                                <button class="gm-ei-btn" :class="ag._state==='approved' ? 'gm-ei-approved-active' : 'gm-ei-approve'" @click="setExtractState(i,'approved')"><svg width="10" height="10" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24"><path d="M20 6L9 17l-5-5"/></svg></button>
                                <button class="gm-ei-btn" :class="ag._state==='rejected' ? 'gm-ei-rejected-active' : 'gm-ei-reject'" @click="setExtractState(i,'rejected'); if(extractResult[i]._state==='rejected') { ag._origTitle=ag.title; ag._origDept=ag.department; ag._origStartDate=ag.start_date; ag._origEndDate=ag.due_date; ag._feedbackVisible=true; ag._feedbackAction='rejected'; ag._feedbackText='' }"><svg width="10" height="10" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24"><path d="M18 6L6 18M6 6l12 12"/></svg></button>
                              </template>
                              <template v-else>
                                <button class="gm-ei-btn gm-ei-save" @click="ag.title=ag._editTitle; ag.department=ag._editDept; ag.start_date=ag._editStartDate; ag.due_date=ag._editDueDate; ag._editing=false; ag._state='approved'"><svg width="10" height="10" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24"><path d="M20 6L9 17l-5-5"/></svg></button>
                                <button class="gm-ei-btn gm-ei-cancel-edit" @click="ag._editing=false; ag._feedbackVisible=false"><svg width="10" height="10" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24"><path d="M18 6L6 18M6 6l12 12"/></svg></button>
                              </template>
                            </div>
                          </div>
                          <!-- 인라인 피드백: 수정/반려 시 해당 아이템 바로 아래 -->
                          <div v-if="ag._feedbackVisible && !ag._editing" class="dei-feedback-box">
                            <div class="dei-feedback-label">
                              <span class="dei-feedback-tag" :class="ag._feedbackAction==='rejected' ? 'tag-rejected' : 'tag-edited'">{{ ag._feedbackAction==='rejected' ? '반려' : '수정' }}</span>
                              사유 입력 (선택)
                            </div>
                            <textarea v-model="ag._feedbackText" class="dei-feedback-input" placeholder="이 과제를 수정/반려한 이유를 알려주세요" rows="2" />
                            <div class="dei-feedback-btns">
                              <button class="dei-fb-submit" @click="saveAgendaFeedback(ag)">저장</button>
                            </div>
                          </div>
                        </template>
                      </div>
                      <button class="gm-add-btn" style="margin-top:6px" @click="addExtractItem"><svg width="10" height="10" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24"><path d="M12 5v14M5 12h14"/></svg> 항목 직접 추가</button>

                      <div class="detail-extract-footer detail-extract-footer--col">
                        <span class="dei-count">승인 {{ extractResult.filter(a=>a._state==='approved').length }} / 반려 {{ extractResult.filter(a=>a._state==='rejected').length }} / 미검토 {{ extractResult.filter(a=>!a._state).length }}</span>
                        <button class="detail-action-btn btn-assign" :disabled="!extractResult.filter(a=>a._state!==null).length" @click="finishExtract">완료</button>
                      </div>
                    </template>

                </template><!-- /추출 결과 -->

            </template><!-- /과제추출 탭 -->

            <!-- ── 관계 탭 ── -->
            <template v-if="detailTab==='rel'">
              <div class="detail-section">
                <div class="detail-section-label-row">
                  <span class="detail-section-label">연결 관계</span>
                  <button class="detail-more-btn rel-add-trigger" @click="openAddRel">+ 추가</button>
                </div>

                <div v-if="currentNodeEdges.length" class="rel-list">
                  <div v-for="edge in currentNodeEdges" :key="edge._idx" class="rel-item">
                    <!-- 인라인 편집 -->
                    <template v-if="relEditIdx === edge._idx">
                      <div class="rel-edit-row">
                        <select v-model="relEditRel" class="rel-type-select">
                          <option v-for="rt in ALL_REL_TYPES" :key="rt" :value="rt">{{ rt }}</option>
                        </select>
                        <button class="rel-btn rel-btn-save" @click="saveRelEdit">저장</button>
                        <button class="rel-btn rel-btn-cancel" @click="cancelRelEdit">취소</button>
                      </div>
                    </template>
                    <!-- 표시 -->
                    <template v-else>
                      <div class="rel-item-main">
                        <span class="rel-dir">{{ edge.direction==='out' ? '→' : '←' }}</span>
                        <span class="rel-badge" :style="{ background: REL_COLORS[edge.rel] || '#6b7280' }">{{ edge.rel }}</span>
                        <span class="rel-target-name" :title="edge.direction==='out' ? edge.toNode?.label : edge.fromNode?.label">
                          {{ edge.direction==='out' ? edge.toNode?.label : edge.fromNode?.label }}
                        </span>
                      </div>
                      <div class="rel-item-actions">
                        <button class="rel-btn rel-btn-edit" @click="startRelEdit(edge._idx)" title="관계 유형 수정">
                          <svg width="10" height="10" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M11 4H4a2 2 0 00-2 2v14a2 2 0 002 2h14a2 2 0 002-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 013 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>
                        </button>
                        <button class="rel-btn rel-btn-delete" @click="doDeleteEdge(edge._idx)" title="관계 삭제">
                          <svg width="10" height="10" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24"><path d="M18 6L6 18M6 6l12 12"/></svg>
                        </button>
                      </div>
                    </template>
                  </div>
                </div>
                <div v-else class="detail-log-empty">연결된 관계가 없습니다.</div>
              </div>

              <!-- 관계 추가 폼 -->
              <div v-if="relAddActive" class="detail-section rel-add-panel">
                <div class="detail-section-label-row" style="margin-bottom:8px">
                  <span class="detail-section-label">새 관계 추가</span>
                  <button class="rel-btn rel-btn-cancel" @click="relAddActive=false">
                    <svg width="10" height="10" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24"><path d="M18 6L6 18M6 6l12 12"/></svg>
                  </button>
                </div>
                <div class="rel-add-form">
                  <div class="rel-add-field">
                    <label class="rel-add-label">출발 노드</label>
                    <select v-model="relAddForm.fromId" class="rel-type-select">
                      <option value="">선택...</option>
                      <option v-for="n in allGraphNodeList" :key="n.id" :value="n.id">{{ n.label }} ({{ n.type }})</option>
                    </select>
                  </div>
                  <div class="rel-add-field">
                    <label class="rel-add-label">관계 유형</label>
                    <select v-model="relAddForm.rel" class="rel-type-select">
                      <option v-for="rt in ALL_REL_TYPES" :key="rt" :value="rt">
                        {{ rt }}
                      </option>
                    </select>
                  </div>
                  <div class="rel-add-field">
                    <label class="rel-add-label">도착 노드</label>
                    <select v-model="relAddForm.toId" class="rel-type-select">
                      <option value="">선택...</option>
                      <option v-for="n in allGraphNodeList" :key="n.id" :value="n.id" :disabled="n.id===relAddForm.fromId">
                        {{ n.label }} ({{ n.type }})
                      </option>
                    </select>
                  </div>
                  <button
                    class="app-btn-primary"
                    style="width:100%;margin-top:6px;font-size:12px;padding:7px 0"
                    :disabled="!relAddForm.fromId || !relAddForm.toId || !relAddForm.rel"
                    @click="doAddRel">
                    관계 추가
                  </button>
                </div>
              </div>
            </template><!-- /관계 탭 -->

          </div>
          </template><!-- /detailMeeting -->

          <!-- ── Node detail (부서/과제/회의/파일/사람/아젠다) ── -->
          <template v-else-if="detailNode">
          <div class="detail-header">
            <!-- 노드 유형별 아이콘 -->
            <div class="detail-header-icon">
              <!-- 부서 -->
              <svg v-if="detailNode.type==='dept'" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/></svg>
              <!-- 조직 -->
              <svg v-else-if="detailNode.type==='company'" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><rect x="4" y="2" width="16" height="20" rx="1"/><path d="M9 22v-4h6v4"/><path d="M8 6h.01M12 6h.01M16 6h.01M8 10h.01M12 10h.01M16 10h.01M8 14h.01M12 14h.01M16 14h.01"/></svg>
              <!-- 아젠다 -->
              <svg v-else-if="detailNode.type==='agenda'" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M9 11l3 3L22 4"/><path d="M21 12v7a2 2 0 01-2 2H5a2 2 0 01-2-2V5a2 2 0 012-2h11"/></svg>
              <!-- 회의(session) -->
              <svg v-else-if="detailNode.type==='session'" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><rect x="3" y="4" width="18" height="18" rx="2"/><path d="M16 2v4M8 2v4M3 10h18"/></svg>
              <!-- 회의록 -->
              <svg v-else-if="detailNode.type==='minutes'" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
              <!-- 보고자료 -->
              <svg v-else-if="detailNode.type==='report'" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="8" y1="13" x2="16" y2="13"/><line x1="8" y1="17" x2="16" y2="17"/></svg>
              <!-- 파일(하위호환) -->
              <svg v-else-if="detailNode.type==='file'" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
              <!-- 사람 -->
              <svg v-else width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M20 21v-2a4 4 0 00-4-4H8a4 4 0 00-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>
            </div>
            <div class="detail-header-left">
              <div class="detail-meeting-name">{{ detailNode.label }}</div>
              <div class="detail-meta-row">
                <span class="detail-meta">{{ { dept:'부서', agenda:'아젠다', session: detailNode.subType==='안건'?'안건':'회의', file:'문서', minutes:'회의록', report:'보고자료', person:'구성원', company:'회사' }[detailNode.type] || detailNode.type }}</span>
              </div>
            </div>
            <div class="detail-header-actions">
              <button class="detail-icon-btn" @click="detailOpen=false" title="닫기">
                <svg width="11" height="11" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24"><path d="M18 6L6 18M6 6l12 12"/></svg>
              </button>
            </div>
          </div>

          <!-- 탭 -->
          <div class="detail-tabs">
            <button class="detail-tab" :class="{ active: nodeDetailTab==='basic' }" @click="nodeDetailTab='basic'">기본</button>
            <button class="detail-tab" :class="{ active: nodeDetailTab==='rel' }" @click="nodeDetailTab='rel'">관계</button>
          </div>

          <div class="detail-body">

            <!-- ── 기본 탭 ── -->
            <template v-if="nodeDetailTab==='basic'">

            <!-- 부서 -->
            <template v-if="detailNode.type==='dept'">
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
                  <div v-for="mb in detailNode.members" :key="mb.userId||mb.userName" class="detail-member-row">
                    <div class="detail-member-avatar" :style="{ background: mb.role==='admin' ? 'var(--accent)' : 'var(--text-dim)' }">{{ (mb.userName||mb.name||'?')[0] }}</div>
                    <div class="detail-member-info">
                      <span class="detail-member-name">{{ mb.userName || mb.name || '-' }}</span>
                      <span class="detail-member-dept">{{ mb.role==='admin' ? '간사' : '참여자' }}</span>
                    </div>
                  </div>
                </div>
                <div v-else class="detail-log-empty">구성원 정보 없음</div>
              </div>
            </template>

            <!-- 조직 -->
            <template v-else-if="detailNode.type==='company'">
              <div class="detail-section">
                <div class="detail-info-grid">
                  <div class="detail-info-item">
                    <span class="detail-info-key">회사명</span>
                    <span class="detail-info-val">{{ detailNode.data?.name || detailNode.label }}</span>
                  </div>
                </div>
              </div>
              <div v-if="meetingGroups.length" class="detail-section">
                <div class="detail-section-label">회의체 목록 ({{ meetingGroups.length }}개)</div>
                <div class="detail-info-grid">
                  <div v-for="mg in meetingGroups" :key="mg.id" class="detail-info-item">
                    <span class="detail-info-val">{{ mg.title }}</span>
                  </div>
                </div>
              </div>
            </template>

            <!-- 아젠다 -->
            <template v-else-if="detailNode.type==='agenda'">
              <div v-if="detailNode.data?.ai_evidence" class="detail-section">
                <div class="detail-section-label">AI 추천 아젠다</div>
                <div class="ai-evidence-box">{{ detailNode.data.ai_evidence }}</div>
              </div>
              <div class="detail-section">
                <div class="detail-info-grid">
                  <div class="detail-info-item">
                    <span class="detail-info-key">아젠다명</span>
                    <span class="detail-info-val">{{ detailNode.data?.content || detailNode.label }}</span>
                  </div>
                  <div class="detail-info-item">
                    <span class="detail-info-key">상태</span>
                    <span class="detail-info-val">
                      <span class="status-badge" :class="{
                        'sb-done': detailNode.data?.status==='완료' || detailNode.data?.status==='done',
                        'sb-progress': detailNode.data?.status==='진행' || detailNode.data?.status==='진행중' || detailNode.data?.status==='in_progress',
                        'sb-pending': detailNode.data?.status==='대기' || detailNode.data?.status==='pending' || !detailNode.data?.status
                      }">{{ detailNode.data?.status || '-' }}</span>
                    </span>
                  </div>
                  <div class="detail-info-item">
                    <span class="detail-info-key">우선순위</span>
                    <span class="detail-info-val">{{ { high:'상', medium:'중', low:'하', 상:'상', 중:'중', 하:'하' }[detailNode.data?.priority] || detailNode.data?.priority || '-' }}</span>
                  </div>
                  <div class="detail-info-item">
                    <span class="detail-info-key">발생일</span>
                    <span class="detail-info-val">{{ detailNode.data?.created_at ? formatDate(detailNode.data.created_at) : '-' }}</span>
                  </div>
                  <div class="detail-info-item">
                    <span class="detail-info-key">마감일</span>
                    <span class="detail-info-val">{{ detailNode.data?.due_date ? formatDate(detailNode.data.due_date) : '-' }}</span>
                  </div>
                </div>
              </div>
            </template>

            <!-- 회의(session) -->
            <template v-else-if="detailNode.type==='session'">
              <div class="detail-section">
                <div class="detail-info-grid">
                  <div class="detail-info-item">
                    <span class="detail-info-key">회의명</span>
                    <span class="detail-info-val">{{ detailNode.data?.session_title || detailNode.label }}</span>
                  </div>
                  <div class="detail-info-item">
                    <span class="detail-info-key">일시</span>
                    <span class="detail-info-val">{{ detailNode.data?.date ? formatDate(detailNode.data.date) : '-' }}</span>
                  </div>
                  <div class="detail-info-item">
                    <span class="detail-info-key">장소</span>
                    <span class="detail-info-val">{{ detailNode.data?.location || '-' }}</span>
                  </div>
                  <div class="detail-info-item">
                    <span class="detail-info-key">상태</span>
                    <span class="detail-info-val">{{ { scheduled:'예정', in_progress:'진행중', completed:'완료', cancelled:'취소' }[detailNode.data?.session_status] || detailNode.data?.session_status || '-' }}</span>
                  </div>
                  <div v-if="detailNode.data?.description" class="detail-info-item">
                    <span class="detail-info-key">설명</span>
                    <span class="detail-info-val detail-info-val--wrap">{{ detailNode.data.description }}</span>
                  </div>
                </div>
              </div>
              <div v-if="detailNode.data?.participants?.length" class="detail-section">
                <div class="detail-section-label">참여자</div>
                <div class="detail-member-list">
                  <div v-for="p in detailNode.data.participants" :key="p.userId||p.userName" class="detail-member-row">
                    <div class="detail-member-avatar" style="background:var(--text-dim)">{{ (p.userName||p.name||'?')[0] }}</div>
                    <div class="detail-member-info">
                      <span class="detail-member-name">{{ p.userName || p.name }}</span>
                      <span v-if="p.department" class="detail-member-dept">{{ p.department }}</span>
                    </div>
                  </div>
                </div>
              </div>
            </template>

            <!-- 회의록 (minutes) -->
            <template v-else-if="detailNode.type==='minutes'">
              <!-- 회의 정보 (meeting_sessions) -->
              <div class="detail-section">
                <div class="detail-section-label">회의 정보</div>
                <div class="detail-info-grid">
                  <div class="detail-info-item">
                    <span class="detail-info-key">회의명</span>
                    <span class="detail-info-val">{{ detailNode.data?.session_title || detailNode.label }}</span>
                  </div>
                  <div class="detail-info-item">
                    <span class="detail-info-key">회의일자</span>
                    <span class="detail-info-val">{{ detailNode.data?.date ? formatDate(detailNode.data.date) : '-' }}</span>
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
                    <span class="detail-info-val">{{ { scheduled:'예정', in_progress:'진행중', completed:'완료', cancelled:'취소' }[detailNode.data.session_status] || detailNode.data.session_status }}</span>
                  </div>
                  <div v-if="detailNode.data?.description" class="detail-info-item">
                    <span class="detail-info-key">설명</span>
                    <span class="detail-info-val detail-info-val--wrap">{{ detailNode.data.description }}</span>
                  </div>
                </div>
              </div>
              <!-- 회의록 정보 (minutes) -->
              <div class="detail-section">
                <div class="detail-section-label">회의록</div>
                <div class="detail-info-grid">
                  <div v-if="detailNode.data?.minutes_status" class="detail-info-item">
                    <span class="detail-info-key">작성상태</span>
                    <span class="detail-info-val">{{ { draft:'초안', completed:'완료', published:'배포' }[detailNode.data.minutes_status] || detailNode.data.minutes_status }}</span>
                  </div>
                  <div v-if="detailNode.data?.generated_at" class="detail-info-item">
                    <span class="detail-info-key">생성일</span>
                    <span class="detail-info-val">{{ formatDate(detailNode.data.generated_at) }}</span>
                  </div>
                  <div class="detail-info-item">
                    <span class="detail-info-key">파일</span>
                    <span class="detail-info-val">
                      <button class="dl-icon-btn" :title="detailNode.data?.file_name || '회의록 다운로드'" @click="downloadDummy(detailNode)">
                        <svg width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
                      </button>
                    </span>
                  </div>
                </div>
              </div>
              <!-- 내용 요약 -->
              <div v-if="detailNode.data?.content_summary" class="detail-section">
                <div class="detail-section-label">AI 요약</div>
                <div class="ai-evidence-box">{{ detailNode.data.content_summary }}</div>
              </div>
            </template>

            <!-- 파일(보고자료) -->
            <template v-else-if="detailNode.type==='report' || detailNode.type==='file'">
              <div class="detail-section">
                <div class="detail-info-grid">
                  <div class="detail-info-item">
                    <span class="detail-info-key">파일명</span>
                    <span class="detail-info-val">{{ detailNode.data?.file_name || detailNode.data?.title || detailNode.label }}</span>
                  </div>
                  <div class="detail-info-item">
                    <span class="detail-info-key">파일</span>
                    <span class="detail-info-val detail-btn-row">
                      <button class="dl-icon-btn" :title="detailNode.data?.title || detailNode.data?.file_name || '파일 다운로드'" @click="downloadDummy(detailNode)">
                        <svg width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
                      </button>
                      <button class="dl-icon-btn delete" title="삭제"
                        @click="deleteReport(detailNode.data?.id || detailNode.reportId)">
                        <svg width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14a2 2 0 01-2 2H8a2 2 0 01-2-2L5 6"/><path d="M10 11v6M14 11v6"/><path d="M9 6V4a1 1 0 011-1h4a1 1 0 011 1v2"/></svg>
                      </button>
                    </span>
                  </div>
                  <div class="detail-info-item">
                    <span class="detail-info-key">업로드일</span>
                    <span class="detail-info-val">{{ detailNode.data?.created_at ? formatDate(detailNode.data.created_at) : (detailNode.data?.submitted_at ? formatDate(detailNode.data.submitted_at) : '-') }}</span>
                  </div>
                  <div class="detail-info-item">
                    <span class="detail-info-key">작성부서</span>
                    <span class="detail-info-val">{{ detailNode.data?.submitter_department || detailNode.data?.department || '-' }}</span>
                  </div>
                  <div v-if="detailNode.type==='report'" class="detail-info-item">
                    <span class="detail-info-key">검토상태</span>
                    <span class="detail-info-val">{{ { pending:'검토중', approved:'승인', rejected:'반려' }[detailNode.data?.human_status] || detailNode.data?.human_status || '-' }}</span>
                  </div>
                </div>
              </div>

              <!-- AI 검토 결과 — 레이더 차트 (report 타입) -->
              <div v-if="detailNode.type==='report'" class="detail-section">
                <div class="detail-section-label">AI 검토 결과</div>
                <div class="radar-wrap">
                  <div class="radar-svg-pos">
                    <svg viewBox="0 0 180 190" class="radar-svg" style="overflow:visible">
                      <polygon :points="sbGridPoly"  fill="none" stroke="rgba(255,255,255,.12)" stroke-width="1"/>
                      <polygon :points="sbGridPoly2" fill="none" stroke="rgba(255,255,255,.07)" stroke-width="0.7"/>
                      <polygon :points="sbGridPoly3" fill="none" stroke="rgba(255,255,255,.07)" stroke-width="0.7"/>
                      <line v-for="(ax, i) in sbAxisLines" :key="'ax'+i"
                        :x1="SB_CX" :y1="SB_CY" :x2="ax.x2" :y2="ax.y2"
                        stroke="rgba(255,255,255,.09)" stroke-width="0.8"/>
                      <polygon v-if="detailNode.data?.total_score != null"
                        :points="sbScorePoly"
                        :fill="sbScoreColor + '2e'" :stroke="sbScoreColor" stroke-width="1.8"/>
                      <text v-for="(lp, i) in sbLabelPos" :key="'lb'+i"
                        :x="lp.x" :y="lp.y"
                        text-anchor="middle" dominant-baseline="middle"
                        font-size="10" fill="#aaa" font-family="sans-serif">{{ lp.label }}</text>
                      <circle :cx="SB_CX" :cy="SB_CY" r="26" class="radar-center-bg"/>
                      <text v-if="detailNode.data?.total_score != null"
                        :x="SB_CX" :y="SB_CY - 6" text-anchor="middle" dominant-baseline="middle"
                        font-size="22" font-weight="700" :fill="sbScoreColor">{{ detailNode.data.total_score }}</text>
                      <text v-if="detailNode.data?.total_score != null"
                        :x="SB_CX" :y="SB_CY + 13" text-anchor="middle" dominant-baseline="middle"
                        font-size="10" fill="#888">/ 100</text>
                    </svg>
                    <!-- 검토하기 버튼: SVG 중앙에 절대 위치 오버레이 -->
                    <button v-if="detailNode.data?.total_score == null"
                      class="sb-review-btn sb-review-btn--center"
                      :disabled="nodeReviewing"
                      @click="startNodeReview(detailNode.data?.id)">
                      <span v-if="nodeReviewing" class="sb-review-spinner"></span>
                      <svg v-else width="11" height="11" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24">
                        <path d="M4 4l16 8-16 8V4z"/>
                      </svg>
                      {{ nodeReviewing ? 'AI 검토 중...' : 'AI 검토' }}
                    </button>
                  </div>
                  <div v-if="detailNode.data?.total_score != null && detailNode.data?.detail_scores" class="criteria-scores">
                    <div v-for="c in SB_CRITERIA" :key="c.key" class="cs-row">
                      <span class="cs-label">{{ c.label }}</span>
                      <div class="cs-bar-wrap">
                        <div class="cs-bar"
                          :style="{ width: ((detailNode.data.detail_scores[c.key]?.score ?? 0) / c.max * 100) + '%', background: sbScoreColor }"/>
                      </div>
                      <span class="cs-num">{{ detailNode.data.detail_scores[c.key]?.score ?? 0 }}/{{ c.max }}</span>
                    </div>
                  </div>
                </div>
              </div>
              <div v-if="detailNode.type==='report' && detailNode.data?.feedback" class="detail-section">
                <div class="detail-section-label">AI 피드백</div>
                <div class="rs-feedback-box">{{ detailNode.data.feedback }}</div>
              </div>
            </template>

            <!-- 구성원 (person) -->
            <template v-else-if="detailNode.type==='person'">
              <div class="detail-section">
                <div class="detail-info-grid">
                  <div class="detail-info-item">
                    <span class="detail-info-key">회사</span>
                    <span class="detail-info-val">{{ detailNode.data?.company || currentOrg?.name || '-' }}</span>
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
                <div v-if="personMeetingGroups(detailNode).length" class="detail-info-grid">
                  <div v-for="mg in personMeetingGroups(detailNode)" :key="mg.id" class="detail-info-item">
                    <span class="detail-info-key">{{ mg.role==='admin' ? '간사' : '참여' }}</span>
                    <span class="detail-info-val">{{ mg.title }}</span>
                  </div>
                </div>
                <div v-else class="detail-log-empty">회의체 정보 없음</div>
              </div>
              <div class="detail-section">
                <div class="detail-section-label">할당된 과제</div>
                <div v-if="personTasks(detailNode).length" class="detail-info-grid">
                  <div v-for="t in personTasks(detailNode)" :key="t.id" class="detail-info-item">
                    <span class="detail-info-key">
                      <span class="status-badge" :class="{'sb-done':t.status==='done','sb-progress':t.status==='in_progress','sb-pending':!t.status||t.status==='pending'}">{{ {done:'완료',in_progress:'진행',pending:'대기'}[t.status]||t.status }}</span>
                    </span>
                    <span class="detail-info-val detail-info-val--wrap">{{ t.content }}</span>
                  </div>
                </div>
                <div v-else class="detail-log-empty">할당된 과제 없음</div>
              </div>
            </template>

            </template><!-- /기본 탭 -->

            <!-- ── 관계 탭 ── -->
            <template v-if="nodeDetailTab==='rel'">

            <div class="detail-section">
              <div class="detail-section-label-row">
                <span class="detail-section-label">연결 관계</span>
                <button class="detail-more-btn rel-add-trigger" @click="openAddRel">+ 추가</button>
              </div>

              <div v-if="currentNodeEdges.length" class="rel-list">
                <div v-for="edge in currentNodeEdges" :key="edge._idx" class="rel-item">
                  <template v-if="relEditIdx === edge._idx">
                    <div class="rel-edit-row">
                      <select v-model="relEditRel" class="rel-type-select">
                        <option v-for="rt in ALL_REL_TYPES" :key="rt" :value="rt">{{ rt }}</option>
                      </select>
                      <button class="rel-btn rel-btn-save" @click="saveRelEdit">저장</button>
                      <button class="rel-btn rel-btn-cancel" @click="cancelRelEdit">취소</button>
                    </div>
                  </template>
                  <template v-else>
                    <div class="rel-item-main">
                      <span class="rel-dir">{{ edge.direction==='out' ? '→' : '←' }}</span>
                      <span class="rel-badge" :style="{ background: REL_COLORS[edge.rel] || '#6b7280' }">{{ edge.rel }}</span>
                      <span class="rel-target-name" :title="edge.direction==='out' ? edge.toNode?.label : edge.fromNode?.label">
                        {{ edge.direction==='out' ? edge.toNode?.label : edge.fromNode?.label }}
                      </span>
                    </div>
                    <div class="rel-item-actions">
                      <button class="rel-btn rel-btn-edit" @click="startRelEdit(edge._idx)" title="관계 유형 수정">
                        <svg width="10" height="10" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M11 4H4a2 2 0 00-2 2v14a2 2 0 002 2h14a2 2 0 002-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 013 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>
                      </button>
                      <button class="rel-btn rel-btn-delete" @click="doDeleteEdge(edge._idx)" title="관계 삭제">
                        <svg width="10" height="10" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24"><path d="M18 6L6 18M6 6l12 12"/></svg>
                      </button>
                    </div>
                  </template>
                </div>
              </div>
              <div v-else class="detail-log-empty">연결된 관계가 없습니다.</div>
            </div>

            <!-- 관계 추가 폼 (노드 공통) -->
            <div v-if="relAddActive" class="detail-section rel-add-panel">
              <div class="detail-section-label-row" style="margin-bottom:8px">
                <span class="detail-section-label">새 관계 추가</span>
                <button class="rel-btn rel-btn-cancel" @click="relAddActive=false">
                  <svg width="10" height="10" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24"><path d="M18 6L6 18M6 6l12 12"/></svg>
                </button>
              </div>
              <div class="rel-add-form">
                <div class="rel-add-field">
                  <label class="rel-add-label">출발 노드</label>
                  <select v-model="relAddForm.fromId" class="rel-type-select">
                    <option value="">선택...</option>
                    <option v-for="n in allGraphNodeList" :key="n.id" :value="n.id">{{ n.label }} ({{ n.type }})</option>
                  </select>
                </div>
                <div class="rel-add-field">
                  <label class="rel-add-label">관계 유형</label>
                  <select v-model="relAddForm.rel" class="rel-type-select">
                    <option v-for="rt in ALL_REL_TYPES" :key="rt" :value="rt">{{ rt }}</option>
                  </select>
                </div>
                <div class="rel-add-field">
                  <label class="rel-add-label">도착 노드</label>
                  <select v-model="relAddForm.toId" class="rel-type-select">
                    <option value="">선택...</option>
                    <option v-for="n in allGraphNodeList" :key="n.id" :value="n.id" :disabled="n.id===relAddForm.fromId">
                      {{ n.label }} ({{ n.type }})
                    </option>
                  </select>
                </div>
                <button
                  class="app-btn-primary"
                  style="width:100%;margin-top:6px;font-size:12px;padding:7px 0"
                  :disabled="!relAddForm.fromId || !relAddForm.toId || !relAddForm.rel"
                  @click="doAddRel">
                  관계 추가
                </button>
              </div>
            </div>

            </template><!-- /관계 탭 -->

          </div>
          </template><!-- /detailNode -->

          </div>
        </Transition>

        <!-- Sidebar toggle handle — visible whenever a meeting or node is selected -->
        <button v-if="(detailMeeting || detailNode) && viewMode==='graph'"
          class="sidebar-toggle-handle"
          :style="{ left: (detailOpen ? sidebarW : 0) + 'px', transition: 'left 0.28s cubic-bezier(.22,.68,0,1.2)' }"
          @click="detailOpen = !detailOpen"
          :title="detailOpen ? '사이드바 접기' : '사이드바 펼치기'">
          <svg width="8" height="14" viewBox="0 0 8 14" fill="none" xmlns="http://www.w3.org/2000/svg">
            <path v-if="detailOpen" d="M6 1L1 7L6 13" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>
            <path v-else d="M2 1L7 7L2 13" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>
          </svg>
        </button>
</template>
