<script setup>
import { inject, ref } from 'vue'
import AppTable from './AppTable.vue'
const {
  viewMode, selectedMeetingType, meetingTypeOptions,
  selectedHistoryType, HISTORY_TYPE_OPTIONS,
  search, filteredGroups, sortedGroups,
  loading, meetingGroups, nightMode,
  lvColumns, lvSortKey, lvSortDir, handleLvSort,
  expandedMeeting, filteredGroupHistoryMap,
  formatDate, downloadDummy, deleteReport,
} = inject('archiveList')

// ── 이전 버전 토글 ─────────────────────────────────────────────
const expandedVersionKeys = ref(new Set())
function toggleVersions(key) {
  const s = new Set(expandedVersionKeys.value)
  s.has(key) ? s.delete(key) : s.add(key)
  expandedVersionKeys.value = s
}
function versionKey(groupId, itemIdx) {
  return `${groupId}-${itemIdx}`
}
</script>

<template>
  <div v-show="viewMode==='list'" class="list-view">
    <div class="lv-inner">
      <div class="lv-header">
        <div class="lv-filter-wrap">
          <select v-model="selectedMeetingType" class="lv-type-filter">
            <option v-for="opt in meetingTypeOptions" :key="opt.value" :value="opt.value">{{ opt.label }}</option>
          </select>
          <select v-model="selectedHistoryType" class="lv-type-filter">
            <option v-for="opt in HISTORY_TYPE_OPTIONS" :key="opt.value" :value="opt.value">{{ opt.label }}</option>
          </select>
        </div>
        <div class="lv-header-right">
          <span class="lv-title">{{ search ? `"${search}" 검색 결과` : '전체 목록' }}</span>
          <span class="lv-count">{{ filteredGroups.length }}개 회의체</span>
        </div>
      </div>
      <div v-if="loading" class="lv-empty">불러오는 중...</div>
      <div v-else-if="!meetingGroups.length" class="lv-empty">소속된 회의체가 없습니다.</div>
      <AppTable v-else :columns="lvColumns" :dark="nightMode" :sortKey="lvSortKey" :sortDir="lvSortDir" @sort="handleLvSort">
        <tr v-if="!filteredGroups.length">
          <td colspan="5" class="lv-hist-empty" style="padding:20px;text-align:center;color:var(--dark-muted)">{{ search ? '검색 결과가 없습니다.' : '데이터가 없습니다.' }}</td>
        </tr>
        <template v-for="g in sortedGroups" :key="g.id">
          <!-- 회의체 행 -->
          <tr class="lv-group-row" @click="expandedMeeting = expandedMeeting===g.id ? null : g.id">
            <td class="lv-td-name">
              <div class="lv-name-cell">
                <svg class="lv-expand-icon" :style="{ transform: expandedMeeting===g.id ? 'rotate(90deg)' : '' }" width="11" height="11" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24"><path d="M9 18l6-6-6-6"/></svg>
                <div class="lv-group-name">{{ g.title }}</div>
              </div>
            </td>
            <td class="lv-td-type">
              <span v-if="g.meeting_type" class="lv-type-text">{{ g.meeting_type }}</span>
              <span v-else class="lv-type-text" style="color:var(--dark-muted)">-</span>
            </td>
            <td class="lv-td-role">
              <span class="lv-role-badge" :class="g._role === '간사' ? 'role-admin' : 'role-member'">
                {{ g._role || '참여자' }}
              </span>
            </td>
            <td class="lv-td-secretary">
              <span class="lv-secretary-text">{{ g.members.find(m => m.role === 'admin')?.userName || g.members.find(m => m.role === 'admin')?.name || '-' }}</span>
            </td>
            <td class="lv-td-cnt">{{ (filteredGroupHistoryMap.get(g.id) || []).length }}건</td>
          </tr>

          <!-- 서브헤더 행 -->
          <tr v-if="expandedMeeting===g.id" class="lv-sub-header-row">
            <td colspan="2" class="lv-sub-th">파일명</td>
            <td class="lv-sub-th">점수</td>
            <td class="lv-sub-th">담당부서</td>
            <td class="lv-sub-th">진행일시 / 기타</td>
          </tr>

          <!-- 이력 없을 때 -->
          <tr v-if="expandedMeeting===g.id && !(filteredGroupHistoryMap.get(g.id) || []).length">
            <td colspan="5" class="lv-hist-empty">{{ selectedHistoryType ? '해당 유형의 이력이 없습니다.' : '이력이 없습니다.' }}</td>
          </tr>

          <!-- 데이터 행들 -->
          <template v-if="expandedMeeting===g.id">
            <template v-for="(item, i) in (filteredGroupHistoryMap.get(g.id) || [])" :key="i">
              <!-- 메인 행 -->
              <tr class="lv-sub-row" :class="{ 'lv-hist-rejected': item.rejected }">
                <td colspan="2" class="lv-sub-td-name">
                  <div class="lv-hist-desc-inner">
                    <button
                      v-if="item.olderVersions?.length"
                      class="lv-ver-toggle"
                      :class="{ expanded: expandedVersionKeys.has(versionKey(g.id, i)) }"
                      @click.stop="toggleVersions(versionKey(g.id, i))"
                      :title="`이전 버전 ${item.olderVersions.length}개`"
                    >
                      <svg width="9" height="9" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24"><path d="M9 18l6-6-6-6"/></svg>
                    </button>
                    <span v-else class="lv-ver-toggle-placeholder"/>
                    <span class="lv-hist-type-dot" :class="'ht-' + item.type"></span>
                    <span
                      :class="{ 'lv-desc-clickable': item.olderVersions?.length }"
                      @click.stop="item.olderVersions?.length && toggleVersions(versionKey(g.id, i))"
                    >{{ item.fileName }}</span>
                    <span v-if="item.rejected" class="lv-status-badge lv-badge-rejected">반려</span>
                    <span v-else-if="item.approved" class="lv-status-badge lv-badge-approved">승인</span>
                  </div>
                </td>
                <td class="lv-sub-td">{{ item.score != null ? item.score + '점' : '-' }}</td>
                <td class="lv-sub-td">{{ item.dept || '-' }}</td>
                <td class="lv-sub-td lv-sub-td-etc">
                  <span class="lv-sub-date">{{ formatDate(item.date) }}</span>
                  <div class="lv-hist-file">
                    <button v-if="item.hasFile" class="lv-dl-btn" @click.stop="downloadDummy(item)" title="다운로드">
                      <svg width="11" height="11" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"/></svg>
                    </button>
                    <button v-if="item.reportId" class="lv-dl-btn lv-del-btn" @click.stop="deleteReport(item.reportId)" title="삭제">
                      <svg width="11" height="11" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14a2 2 0 01-2 2H8a2 2 0 01-2-2L5 6"/><path d="M10 11v6M14 11v6"/><path d="M9 6V4a1 1 0 011-1h4a1 1 0 011 1v2"/></svg>
                    </button>
                  </div>
                </td>
              </tr>
              <!-- 이전 버전 행들 -->
              <template v-if="item.olderVersions?.length && expandedVersionKeys.has(versionKey(g.id, i))">
                <tr v-for="(ver, vi) in item.olderVersions" :key="`ver-${vi}`"
                  class="lv-sub-row lv-ver-row" :class="{ 'lv-hist-rejected': ver.rejected }">
                  <td colspan="2" class="lv-sub-td-name" style="padding-left:36px">
                    <div class="lv-hist-desc-inner">
                      <span class="lv-hist-type-dot ht-report"></span>
                      {{ ver.fileName }}
                      <span v-if="ver.rejected" class="lv-status-badge lv-badge-rejected">반려</span>
                      <span v-else-if="ver.approved" class="lv-status-badge lv-badge-approved">승인</span>
                    </div>
                  </td>
                  <td class="lv-sub-td">{{ ver.score != null ? ver.score + '점' : '-' }}</td>
                  <td class="lv-sub-td">{{ ver.dept || '-' }}</td>
                  <td class="lv-sub-td lv-sub-td-etc">
                    <span class="lv-sub-date">{{ formatDate(ver.date) }}</span>
                    <div class="lv-hist-file">
                      <button v-if="ver.hasFile" class="lv-dl-btn" @click.stop="downloadDummy(ver)" title="다운로드">
                        <svg width="11" height="11" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"/></svg>
                      </button>
                      <button v-if="ver.reportId" class="lv-dl-btn lv-del-btn" @click.stop="deleteReport(ver.reportId)" title="삭제">
                        <svg width="11" height="11" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14a2 2 0 01-2 2H8a2 2 0 01-2-2L5 6"/><path d="M10 11v6M14 11v6"/><path d="M9 6V4a1 1 0 011-1h4a1 1 0 011 1v2"/></svg>
                      </button>
                    </div>
                  </td>
                </tr>
              </template>
            </template>
          </template>
        </template>
      </AppTable>
    </div>
  </div>
</template>
