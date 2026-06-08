<script setup>
import { inject, ref, onUnmounted } from 'vue'
import AppTable from './AppTable.vue'
const {
  viewMode, selectedMeetingType, meetingTypeOptions,
  selectedHistoryType, HISTORY_TYPE_OPTIONS,
  search, filteredGroups, sortedGroups,
  loading, meetingGroups, nightMode,
  lvColumns, lvSortKey, lvSortDir, handleLvSort,
  expandedMeeting, meetingsStore, filteredGroupHistoryMap,
  formatDate, downloadDummy, deleteReport,
} = inject('archiveList')

// ── 내부 테이블 컬럼 리사이즈 ──────────────────────────────────
const MIN_W = 60
const histColWidths = ref([null, 120, 160, 70]) // null = flex

let resizing = null
function startHistResize(e, colIndex) {
  e.preventDefault()
  resizing = {
    colIndex,
    startX: e.clientX,
    startWidth: histColWidths.value[colIndex],
    nextStartWidth: histColWidths.value[colIndex + 1],
  }
  window.addEventListener('mousemove', onHistMouseMove)
  window.addEventListener('mouseup', onHistMouseUp)
}
function onHistMouseMove(e) {
  if (!resizing) return
  const dx = e.clientX - resizing.startX
  const newW = Math.max(MIN_W, (resizing.startWidth || MIN_W) + dx)
  const newNext = resizing.nextStartWidth !== null
    ? Math.max(MIN_W, resizing.nextStartWidth - dx)
    : null
  const cols = [...histColWidths.value]
  cols[resizing.colIndex] = newW
  if (newNext !== null) cols[resizing.colIndex + 1] = newNext
  histColWidths.value = cols
}
function onHistMouseUp() {
  resizing = null
  window.removeEventListener('mousemove', onHistMouseMove)
  window.removeEventListener('mouseup', onHistMouseUp)
}
onUnmounted(() => {
  window.removeEventListener('mousemove', onHistMouseMove)
  window.removeEventListener('mouseup', onHistMouseUp)
})
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
          <tr v-if="expandedMeeting===g.id" class="lv-expanded-row">
            <td colspan="5" class="lv-expanded-td">
              <table class="app-table lv-hist-table">
                <thead>
                  <tr>
                    <th :style="histColWidths[0] ? { width: histColWidths[0] + 'px' } : {}">
                      설명
                      <span class="hist-col-resize" @mousedown.stop="startHistResize($event, 0)"/>
                    </th>
                    <th :style="{ width: histColWidths[1] + 'px' }">
                      담당자
                      <span class="hist-col-resize" @mousedown.stop="startHistResize($event, 1)"/>
                    </th>
                    <th :style="{ width: histColWidths[2] + 'px' }">
                      진행일시
                      <span class="hist-col-resize" @mousedown.stop="startHistResize($event, 2)"/>
                    </th>
                    <th :style="{ width: histColWidths[3] + 'px' }">자료</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-if="!(filteredGroupHistoryMap.get(g.id) || []).length">
                    <td colspan="4" class="lv-hist-empty">{{ selectedHistoryType ? '해당 유형의 이력이 없습니다.' : '이력이 없습니다.' }}</td>
                  </tr>
                  <tr v-for="(item, i) in (filteredGroupHistoryMap.get(g.id) || [])" :key="i"
                    class="lv-hist-row" :class="{ 'lv-hist-rejected': item.rejected }">
                    <td class="lv-hist-desc">
                      <div class="lv-hist-desc-inner">
                        <span class="lv-hist-type-dot" :class="'ht-' + item.type"></span>
                        {{ item.desc }}
                        <span v-if="item.rejected && item.type === 'report'" class="lv-rejected-badge">반려</span>
                      </div>
                    </td>
                    <td class="lv-hist-manager">{{ item.manager }}</td>
                    <td class="lv-hist-date">{{ formatDate(item.date) }}</td>
                    <td class="lv-hist-file">
                      <button v-if="item.hasFile" class="lv-dl-btn" @click.stop="downloadDummy(item)" title="다운로드">
                        <svg width="11" height="11" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"/></svg>
                      </button>
                      <button v-if="item.reportId" class="lv-dl-btn lv-del-btn" @click.stop="deleteReport(item.reportId)" title="삭제">
                        <svg width="11" height="11" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14a2 2 0 01-2 2H8a2 2 0 01-2-2L5 6"/><path d="M10 11v6M14 11v6"/><path d="M9 6V4a1 1 0 011-1h4a1 1 0 011 1v2"/></svg>
                      </button>
                      <span v-if="!item.hasFile && !item.reportId" class="lv-no-file">-</span>
                    </td>
                  </tr>
                </tbody>
              </table>
            </td>
          </tr>
        </template>
      </AppTable>
    </div>
  </div>
</template>
