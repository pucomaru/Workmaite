<script setup>
import { inject } from 'vue'
import AppTable from './AppTable.vue'
const {
  viewMode, selectedMeetingType, meetingTypeOptions,
  selectedHistoryType, HISTORY_TYPE_OPTIONS,
  search, filteredGroups, sortedGroups,
  loading, meetingGroups, nightMode,
  lvColumns, lvSortKey, lvSortDir, handleLvSort,
  expandedMeeting, meetingsStore, filteredGroupHistoryMap,
  formatDate, downloadDummy,
} = inject('archiveList')
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
          <td colspan="5" class="lv-hist-empty" style="padding:20px;text-align:center;color:#94a3b8">{{ search ? '검색 결과가 없습니다.' : '데이터가 없습니다.' }}</td>
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
              <span v-else class="lv-type-text" style="color:#94a3b8">-</span>
            </td>
            <td class="lv-td-role">
              <span class="lv-role-badge" :class="meetingsStore.meetingRoles[g.id]==='admin' ? 'role-admin' : 'role-member'">
                {{ meetingsStore.meetingRoles[g.id] === 'admin' ? '간사' : '참여자' }}
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
                    <th>설명</th>
                    <th style="width:110px">담당자</th>
                    <th style="width:100px">진행일</th>
                    <th style="width:60px">자료</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-if="!(filteredGroupHistoryMap.get(g.id) || []).length">
                    <td colspan="4" class="lv-hist-empty">{{ selectedHistoryType ? '해당 유형의 이력이 없습니다.' : '이력이 없습니다.' }}</td>
                  </tr>
                  <tr v-for="(item, i) in (filteredGroupHistoryMap.get(g.id) || [])" :key="i" class="lv-hist-row">
                    <td class="lv-hist-desc">
                      <div class="lv-hist-desc-inner">
                        <span class="lv-hist-type-dot" :class="'ht-' + item.type"></span>
                        {{ item.desc }}
                      </div>
                    </td>
                    <td class="lv-hist-manager">{{ item.manager }}</td>
                    <td class="lv-hist-date">{{ formatDate(item.date) }}</td>
                    <td class="lv-hist-file">
                      <button v-if="item.hasFile" class="lv-dl-btn" @click.stop="downloadDummy(item.fileName)" title="다운로드">
                        <svg width="11" height="11" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"/></svg>
                      </button>
                      <span v-else class="lv-no-file">-</span>
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
