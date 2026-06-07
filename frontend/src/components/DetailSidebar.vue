<script setup>
import { inject } from 'vue'
import SidebarInfoRow from './SidebarInfoRow.vue'
import ProcessStepBar from './ProcessStepBar.vue'
import FileUploadArea from './FileUploadArea.vue'

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
  showFeedback, submitFeedback,
  detailMemberDepts,
  goToProcessStep,
  PRIORITY_LABEL, STATUS_LABEL,
  currentNodeEdges, relEditIdx, relEditRel, ALL_REL_TYPES, REL_COLORS,
  saveRelEdit, cancelRelEdit, startRelEdit, doDeleteEdge,
  relAddActive, openAddRel, allGraphNodeList, relAddForm, doAddRel,
  detailNode, downloadDummy, currentOrg, personMeetingGroups, personTasks,
  viewMode,
} = inject('archiveSidebar')
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
                  <span v-else class="dday-label" style="font-size:10px;white-space:nowrap">미지정</span>
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
                    <div class="ctx-file-list">
                      <label class="ctx-file-item">
                        <input type="checkbox" v-model="selectedSimilarDocs" value="sim_1" class="ctx-checkbox" />
                        <svg width="10" height="10" fill="none" stroke="#a78bfa" stroke-width="2" viewBox="0 0 24 24"><path d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"/></svg>
                        <span class="ctx-file-name">운영위원회 회의록 3월</span>
                        <span class="ctx-sim-score">유사도 87%</span>
                      </label>
                      <label class="ctx-file-item">
                        <input type="checkbox" v-model="selectedSimilarDocs" value="sim_2" class="ctx-checkbox" />
                        <svg width="10" height="10" fill="none" stroke="#a78bfa" stroke-width="2" viewBox="0 0 24 24"><path d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"/></svg>
                        <span class="ctx-file-name">2025_전략보고서.pdf</span>
                        <span class="ctx-sim-score">유사도 79%</span>
                      </label>
                    </div>
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
                                  <input class="dei-input dei-date-input" type="date" v-model="ag._editStartDate" />
                                  <input class="dei-input dei-date-input" type="date" v-model="ag._editDueDate" />
                                </div>
                              </template>
                            </div>
                            <div class="dei-actions">
                              <template v-if="!ag._editing">
                                <button class="gm-ei-btn gm-ei-edit" @click="ag._editing=true; showFeedback(ag, 'edited')"><svg width="10" height="10" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M11 4H4a2 2 0 00-2 2v14a2 2 0 002 2h14a2 2 0 002-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 013 3L12 15l-4 1 1-4 9.5-9.5z"/></svg></button>
                                <button class="gm-ei-btn" :class="ag._state==='approved' ? 'gm-ei-approved-active' : 'gm-ei-approve'" @click="setExtractState(i,'approved')"><svg width="10" height="10" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24"><path d="M20 6L9 17l-5-5"/></svg></button>
                                <button class="gm-ei-btn" :class="ag._state==='rejected' ? 'gm-ei-rejected-active' : 'gm-ei-reject'" @click="setExtractState(i,'rejected'); if(extractResult[i]._state==='rejected') showFeedback(ag,'rejected')"><svg width="10" height="10" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24"><path d="M18 6L6 18M6 6l12 12"/></svg></button>
                              </template>
                              <template v-else>
                                <button class="gm-ei-btn gm-ei-save" @click="ag.title=ag._editTitle; ag.department=ag._editDept; ag.start_date=ag._editStartDate; ag.due_date=ag._editDueDate; ag._editing=false; ag._state='approved'"><svg width="10" height="10" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24"><path d="M20 6L9 17l-5-5"/></svg></button>
                                <button class="gm-ei-btn gm-ei-cancel-edit" @click="ag._editing=false"><svg width="10" height="10" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24"><path d="M18 6L6 18M6 6l12 12"/></svg></button>
                              </template>
                            </div>
                          </div>
                          <!-- 인라인 피드백: 수정/반려 시 해당 아이템 바로 아래 -->
                          <div v-if="ag._feedbackVisible" class="dei-feedback-box">
                            <div class="dei-feedback-label">
                              <span class="dei-feedback-tag" :class="ag._feedbackAction==='rejected' ? 'tag-rejected' : 'tag-edited'">{{ ag._feedbackAction==='rejected' ? '반려' : '수정' }}</span>
                              AI에게 피드백 보내기 (선택)
                            </div>
                            <textarea v-model="ag._feedbackText" class="dei-feedback-input" placeholder="이 과제를 수정/반려한 이유를 알려주세요" rows="2" />
                            <div class="dei-feedback-btns">
                              <button class="dei-fb-submit" @click="submitFeedback(ag)">보내기</button>
                              <button class="dei-fb-skip" @click="ag._feedbackVisible=false">건너뛰기</button>
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
              <svg v-else-if="detailNode.type==='org'" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M3 9l9-7 9 7v11a2 2 0 01-2 2H5a2 2 0 01-2-2z"/><polyline points="9 22 9 12 15 12 15 22"/></svg>
              <!-- 아젠다 -->
              <svg v-else-if="detailNode.type==='agenda'" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M9 11l3 3L22 4"/><path d="M21 12v7a2 2 0 01-2 2H5a2 2 0 01-2-2V5a2 2 0 012-2h11"/></svg>
              <!-- 회의(session) -->
              <svg v-else-if="detailNode.type==='session'" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><rect x="3" y="4" width="18" height="18" rx="2"/><path d="M16 2v4M8 2v4M3 10h18"/></svg>
              <!-- 파일 -->
              <svg v-else-if="detailNode.type==='file'" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
              <!-- 사람 -->
              <svg v-else width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M20 21v-2a4 4 0 00-4-4H8a4 4 0 00-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>
            </div>
            <div class="detail-header-left">
              <div class="detail-meeting-name">{{ detailNode.label }}</div>
              <div class="detail-meta-row">
                <span class="detail-meta">{{ { dept:'부서', agenda:'아젠다', session: detailNode.subType==='안건'?'안건':'회의', file:'문서', person:'구성원', org:'조직' }[detailNode.type] || detailNode.type }}</span>
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
                <div v-if="detailNode.members?.length" class="node-member-list">
                  <div v-for="mb in detailNode.members" :key="mb.userId||mb.userName" class="node-member-row">
                    <div class="node-avatar" :style="{ background: mb.role==='admin' ? 'var(--accent)' : 'var(--text-dim)' }">{{ (mb.userName||mb.name||'?')[0] }}</div>
                    <div class="node-member-info">
                      <span class="node-member-name">{{ mb.userName || mb.name || '-' }}</span>
                      <span class="node-member-role">{{ mb.role==='admin' ? '간사' : '참여자' }}</span>
                    </div>
                  </div>
                </div>
                <div v-else class="node-empty">구성원 정보 없음</div>
              </div>
            </template>

            <!-- 조직 -->
            <template v-else-if="detailNode.type==='org'">
              <div class="detail-section">
                <div class="detail-info-grid">
                  <div class="detail-info-item" style="grid-column:span 2">
                    <span class="detail-info-key">조직명</span>
                    <span class="detail-info-val">{{ detailNode.data?.name || detailNode.label }}</span>
                  </div>
                  <div class="detail-info-item">
                    <span class="detail-info-key">타입</span>
                    <span class="detail-info-val">{{ detailNode.data?.org_type || '-' }}</span>
                  </div>
                </div>
              </div>
              <div v-if="meetingGroups.length" class="detail-section">
                <div class="detail-section-label">회의체 목록 ({{ meetingGroups.length }}개)</div>
                <div class="detail-info-grid">
                  <div v-for="mg in meetingGroups" :key="mg.id" class="detail-info-item" style="grid-column:span 2">
                    <span class="detail-info-val">{{ mg.title }}</span>
                  </div>
                </div>
              </div>
            </template>

            <!-- 아젠다 -->
            <template v-else-if="detailNode.type==='agenda'">
              <div class="detail-section">
                <div class="detail-info-grid">
                  <div class="detail-info-item" style="grid-column:span 2">
                    <span class="detail-info-key">아젠다명</span>
                    <span class="detail-info-val">{{ detailNode.data?.content || detailNode.label }}</span>
                  </div>
                  <div class="detail-info-item">
                    <span class="detail-info-key">카테고리</span>
                    <span class="detail-info-val">{{ detailNode.data?.category || '-' }}</span>
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
                  <div class="detail-info-item" style="grid-column:span 2">
                    <span class="detail-info-key">회의명</span>
                    <span class="detail-info-val">{{ detailNode.data?.session_title || detailNode.label }}</span>
                  </div>
                  <div class="detail-info-item">
                    <span class="detail-info-key">회의일자</span>
                    <span class="detail-info-val">{{ detailNode.data?.date ? formatDate(detailNode.data.date) : (detailNode.data?.ended_at ? formatDate(detailNode.data.ended_at) : '-') }}</span>
                  </div>
                  <div class="detail-info-item">
                    <span class="detail-info-key">타입</span>
                    <span class="detail-info-val">{{ detailNode.data?.session_type || '-' }}</span>
                  </div>
                  <div class="detail-info-item" style="grid-column:span 2">
                    <span class="detail-info-key">회의소개</span>
                    <span class="detail-info-val">{{ detailNode.data?.description || '-' }}</span>
                  </div>
                  <div class="detail-info-item" style="grid-column:span 2; display:flex; align-items:center; gap:8px">
                    <span class="detail-info-key">회의록</span>
                    <button class="dl-icon-btn" :title="detailNode.data?.doc_title || detailNode.data?.file_name || '회의록 다운로드'" @click="downloadDummy(detailNode.data?.doc_title || detailNode.data?.file_name || detailNode.data?.session_title || detailNode.label)">
                      <svg width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
                    </button>
                  </div>
                </div>
              </div>
              <div v-if="detailNode.data?.participants?.length" class="detail-section">
                <div class="detail-section-label">참여자</div>
                <div class="node-member-list">
                  <div v-for="p in detailNode.data.participants" :key="p.userId||p.userName" class="node-member-row">
                    <div class="node-avatar" style="background:var(--text-dim)">{{ (p.userName||p.name||'?')[0] }}</div>
                    <div class="node-member-info">
                      <span class="node-member-name">{{ p.userName || p.name }}</span>
                      <span v-if="p.department" class="node-member-role">{{ p.department }}</span>
                    </div>
                  </div>
                </div>
              </div>
            </template>

            <!-- 파일(문서/회의록) -->
            <template v-else-if="detailNode.type==='file'">
              <div class="detail-section">
                <div class="detail-info-grid">
                  <div class="detail-info-item" style="grid-column:span 2">
                    <span class="detail-info-key">파일명</span>
                    <span class="detail-info-val">{{ detailNode.data?.title || detailNode.data?.file_name || detailNode.label }}</span>
                  </div>
                  <div class="detail-info-item">
                    <span class="detail-info-key">종류</span>
                    <span class="detail-info-val">{{ detailNode.data?.doc_type || detailNode.fileType || '-' }}</span>
                  </div>
                  <div class="detail-info-item">
                    <span class="detail-info-key">작성일</span>
                    <span class="detail-info-val">{{ detailNode.data?.created_at ? formatDate(detailNode.data.created_at) : (detailNode.data?.submitted_at ? formatDate(detailNode.data.submitted_at) : '-') }}</span>
                  </div>
                  <div class="detail-info-item">
                    <span class="detail-info-key">작성자</span>
                    <span class="detail-info-val">{{ detailNode.data?.author || detailNode.data?.department || '-' }}</span>
                  </div>
                  <div class="detail-info-item" style="grid-column:span 2; display:flex; align-items:center; gap:8px">
                    <span class="detail-info-key">파일</span>
                    <button class="dl-icon-btn" :title="detailNode.data?.title || detailNode.data?.file_name || '파일 다운로드'" @click="downloadDummy(detailNode.data?.title || detailNode.data?.file_name || detailNode.label)">
                      <svg width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
                    </button>
                  </div>
                </div>
              </div>
            </template>

            <!-- 구성원 (person) -->
            <template v-else-if="detailNode.type==='person'">
              <div class="detail-section">
                <div class="detail-info-grid">
                  <SidebarInfoRow label="조직" :value="detailNode.data?.organization || currentOrg?.name || '-'" />
                  <SidebarInfoRow label="부서" :value="detailNode.data?.department || '-'" />
                  <SidebarInfoRow label="직책" :value="detailNode.data?.position || '-'" />
                </div>
              </div>
              <div class="detail-section">
                <div class="detail-section-label">참여 회의체</div>
                <div v-if="personMeetingGroups(detailNode).length" class="detail-info-grid">
                  <div v-for="mg in personMeetingGroups(detailNode)" :key="mg.id" class="detail-info-item" style="grid-column:span 2">
                    <span class="detail-info-key">{{ mg.role==='admin' ? '간사' : '참여' }}</span>
                    <span class="detail-info-val">{{ mg.title }}</span>
                  </div>
                </div>
                <div v-else class="node-empty">회의체 정보 없음</div>
              </div>
              <div class="detail-section">
                <div class="detail-section-label">할당된 과제</div>
                <div v-if="personTasks(detailNode).length" class="detail-info-grid">
                  <div v-for="t in personTasks(detailNode)" :key="t.id" class="detail-info-item" style="grid-column:span 2">
                    <span class="detail-info-key">
                      <span class="status-badge" :class="{'sb-done':t.status==='done','sb-progress':t.status==='in_progress','sb-pending':!t.status||t.status==='pending'}">{{ {done:'완료',in_progress:'진행',pending:'대기'}[t.status]||t.status }}</span>
                    </span>
                    <span class="detail-info-val" style="white-space:normal;line-height:1.4">{{ t.content }}</span>
                  </div>
                </div>
                <div v-else class="node-empty">할당된 과제 없음</div>
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
