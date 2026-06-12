<script setup>
import { ref, onMounted, computed, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useMeetingsStore } from '../stores/meetings'
import { useAuthStore } from '../stores/auth'
import api from '../api'

import AppTable from '../components/AppTable.vue'
import AppPagination from '../components/AppPagination.vue'

const router = useRouter()
const auth = useAuthStore()
const meetingsStore = useMeetingsStore()

const calendarEvents = ref([])
const upcomingSessionsList = ref([])

const meetingRoles = ref({})   // { [meetingId]: 'admin' | 'member' | null }
const endingMeeting = ref(null)
const deletingMeeting = ref(null)
const meetingMeta = ref({}) // { [meetingId]: { owner_name, due_date, priority } }

// ── Calendar state ──────────────────────────────────────────
const calView = ref('month')
const cursor = ref(new Date())
const today = new Date()
today.setHours(0, 0, 0, 0)

const views = [
  { key: 'day',   label: '일' },
  { key: 'week',  label: '주' },
  { key: 'month', label: '월' },
]

function navigate(dir) {
  const d = new Date(cursor.value)
  if (calView.value === 'day')   d.setDate(d.getDate() + dir)
  if (calView.value === 'week')  d.setDate(d.getDate() + dir * 7)
  if (calView.value === 'month') d.setMonth(d.getMonth() + dir)
  cursor.value = d
}
function goToday() { cursor.value = new Date() }

const WEEKDAYS_KO = ['일','월','화','수','목','금','토']

const calTitle = computed(() => {
  const d = cursor.value
  const y = d.getFullYear()
  const m = d.getMonth() + 1
  if (calView.value === 'day') return `${y}년 ${m}월 ${d.getDate()}일 (${WEEKDAYS_KO[d.getDay()] ?? ''})`
  if (calView.value === 'week') {
    const { start, end } = weekRange(d)
    const sm = start.getMonth() + 1, em = end.getMonth() + 1
    if (sm === em) return `${y}년 ${sm}월 ${start.getDate()}일 – ${end.getDate()}일`
    return `${y}년 ${sm}월 ${start.getDate()}일 – ${em}월 ${end.getDate()}일`
  }
  return `${y}년 ${m}월`
})

function isSameDay(a, b) {
  return a.getFullYear() === b.getFullYear() &&
         a.getMonth()    === b.getMonth()    &&
         a.getDate()     === b.getDate()
}
function isToday(d) { return isSameDay(d, today) }
function eventsOn(date) {
  const ds = fmtISO(date)
  return calendarEvents.value.filter(e => e.date?.startsWith(ds))
}
function fmtISO(d) {
  return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`
}

const monthCells = computed(() => {
  const y = cursor.value.getFullYear()
  const m = cursor.value.getMonth()
  const firstWd = new Date(y, m, 1).getDay()
  const lastDay = new Date(y, m + 1, 0).getDate()
  const cells = []
  for (let i = 0; i < firstWd; i++) cells.push(null)
  for (let d = 1; d <= lastDay; d++) cells.push(new Date(y, m, d))
  while (cells.length % 7 !== 0) cells.push(null)
  return cells
})

function weekRange(d) {
  const start = new Date(d)
  start.setDate(d.getDate() - d.getDay())
  start.setHours(0, 0, 0, 0)
  const end = new Date(start)
  end.setDate(start.getDate() + 6)
  return { start, end }
}
const weekDays = computed(() => {
  const { start } = weekRange(cursor.value)
  return Array.from({ length: 7 }, (_, i) => {
    const d = new Date(start)
    d.setDate(start.getDate() + i)
    return d
  })
})

const yearMonths = computed(() => {
  const y = cursor.value.getFullYear()
  return Array.from({ length: 12 }, (_, m) => {
    const firstWd = (new Date(y, m, 1).getDay() + 6) % 7
    const lastDay = new Date(y, m + 1, 0).getDate()
    const cells = []
    for (let i = 0; i < firstWd; i++) cells.push(null)
    for (let d = 1; d <= lastDay; d++) cells.push(new Date(y, m, d))
    return { month: m + 1, cells }
  })
})

const dayEvents = computed(() => eventsOn(cursor.value))

function evtCls(type) {
  return type === 'session' ? 'evt-session' : 'evt-agenda'
}

function clickDay(d) {
  if (!d) return
  cursor.value = new Date(d)
  calView.value = 'day'
}
function clickMiniDay(d) {
  if (!d) return
  cursor.value = new Date(d)
  calView.value = 'month'
}

// ── Data loading ─────────────────────────────────────────────
onMounted(async () => {
  await meetingsStore.fetchMeetings()

  // 캘린더·담당자 메타·역할을 모두 병렬 실행
  await Promise.all([
    api.get('/api/v1/home/calendar', { params: { view: 'month', date: new Date().toISOString().slice(0, 10) } })
      .then(calRes => {
        calendarEvents.value = (calRes.data?.sessions ?? []).map(s => ({
          ...s,
          id: s.sessionId,
          type: 'session',
          date: s.scheduledAt?.slice(0, 10),
          meeting_title: s.meetingTitle,
        }))
      }).catch(() => {}),

    api.get('/api/v1/me/sessions')
      .then(res => {
        upcomingSessionsList.value = (res.data ?? []).map(s => ({
          ...s,
          id: s.sessionId,
          date: s.scheduledAt?.slice(0, 10),
          meeting_title: s.meetingTitle,
        }))
      }).catch(() => {}),

    hydrateMeetingMeta(),

    Promise.all(
      meetingsStore.meetings.map(async (m) => {
        try {
          const { data } = await api.get(`/api/v1/meetings/${m.id}/my-role`)
          meetingRoles.value[m.id] = data.role
        } catch {
          meetingRoles.value[m.id] = null
        }
      })
    ),
  ])
})

async function hydrateMeetingMeta() {
  const active = meetingsStore.meetings.filter(m => m.status === 'active')
  if (active.length === 0) return

  // 담당자: 단일 요청으로 모든 active 회의체의 admin 이름을 일괄 조회
  const adminMap = {}
  try {
    const { data: activeMeetingsData } = await api.get('/api/v1/me/meetings')
    ;(activeMeetingsData ?? []).forEach(r => {
      adminMap[r.meetingId] = { adminName: r.adminName || '-', memberCount: r.memberCount ?? 0 }
    })
  } catch {}

  // 담당자를 즉시 반영 (아젠다 로드를 기다리지 않음)
  const initial = {}
  active.forEach(m => {
    initial[m.id] = { owner_name: adminMap[m.id]?.adminName ?? '-', member_count: adminMap[m.id]?.memberCount ?? 0, due_date: null }
  })
  meetingMeta.value = initial

}

// ── 회의체 종료 / 삭제 ─────────────────────────────────────────
async function endMeeting(m, e) {
  e.stopPropagation()
  if (!confirm(`"${m.title}" 회의체를 종료하시겠습니까?\n종료 후에는 새 회의를 추가할 수 없습니다.`)) return
  endingMeeting.value = m.id
  try {
    await meetingsStore.terminateMeeting(m.id)
  } finally {
    endingMeeting.value = null
  }
}

async function deleteMeeting(m, e) {
  e.stopPropagation()
  if (!confirm(`"${m.title}" 회의체를 삭제하시겠습니까?\n모든 회의록과 데이터가 함께 삭제됩니다.`)) return
  deletingMeeting.value = m.id
  try {
    await meetingsStore.deleteMeeting(m.id)
  } finally {
    deletingMeeting.value = null
  }
}


// ── Utils ────────────────────────────────────────────────────
function getDday(due) {
  if (!due) return null
  const diff = Math.ceil((new Date(due) - new Date()) / 86400000)
  return diff
}
function formatDate(ds) {
  if (!ds) return ''
  return new Date(ds).toLocaleDateString('ko-KR', { month: 'short', day: 'numeric' })
}
function statusLabel(s) {
  return { active: '진행중', ended: '종료' }[s] || s
}

const activeMeetings = computed(() =>
  meetingsStore.meetings.filter(m => m.status === 'active')
)
const endedMeetings = computed(() =>
  meetingsStore.meetings.filter(m => m.status === 'ended')
)

const displayActiveMeetings = computed(() =>
  activeMeetings.value.map(m => ({
    ...m,
    owner_name: meetingMeta.value[m.id]?.owner_name ?? m.owner_name ?? '-',
    member_count: meetingMeta.value[m.id]?.member_count ?? 0,
    role: meetingRoles.value[m.id] ?? null,
  }))
)

// 예정된 회의: calendarEvents 중 type='session' 이고 오늘 이후 항목
const sessionColumns = [
  { label: '회의명', sortKey: 'title' },
  { label: '회의체', sortKey: 'meeting_title' },
  { label: '장소', width: '110px', sortKey: 'location' },
  { label: '날짜', width: '110px', sortKey: 'date' },
  { label: 'D-day', width: '80px', sortKey: 'date' },
]

const meetingColumns = [
  { label: '회의체명', sortKey: 'title' },
  { label: '유형', width: '80px', sortKey: 'meeting_type' },
  { label: '역할', width: '70px' },
  { label: '간사', width: '90px', sortKey: 'owner_name' },
  { label: '참여자', width: '70px', sortKey: 'member_count' },
]

const upcomingSessions = computed(() =>
  [...upcomingSessionsList.value].sort((a, b) => new Date(a.date) - new Date(b.date))
)

// ── 정렬 ──────────────────────────────────────────
const sessionSortKey = ref(null)
const sessionSortDir = ref(null)
const meetingSortKey = ref(null)
const meetingSortDir = ref(null)

function applySortStr(list, key, dir) {
  if (!key || !dir) return list
  const d = dir === 'asc' ? 1 : -1
  return [...list].sort((a, b) => {
    const av = (a[key] ?? '').toString().toLowerCase()
    const bv = (b[key] ?? '').toString().toLowerCase()
    return av < bv ? -d : av > bv ? d : 0
  })
}

const sortedSessions = computed(() => applySortStr(upcomingSessions.value, sessionSortKey.value, sessionSortDir.value))
const sortedMeetings = computed(() => applySortStr(displayActiveMeetings.value, meetingSortKey.value, meetingSortDir.value))

function handleSessionSort({ key, dir }) { sessionSortKey.value = key; sessionSortDir.value = dir }
function handleMeetingSort({ key, dir }) { meetingSortKey.value = key; meetingSortDir.value = dir }

// ── 페이지네이션 ──────────────────────────────────
const SESSION_PAGE_SIZE = 7
const MEETING_PAGE_SIZE = 15
const sessionPage = ref(1)
const meetingPage = ref(1)

const pagedSessions = computed(() =>
  sortedSessions.value.slice((sessionPage.value - 1) * SESSION_PAGE_SIZE, sessionPage.value * SESSION_PAGE_SIZE)
)
const pagedMeetings = computed(() =>
  sortedMeetings.value.slice((meetingPage.value - 1) * MEETING_PAGE_SIZE, meetingPage.value * MEETING_PAGE_SIZE)
)

const sessionFillerCount = computed(() => SESSION_PAGE_SIZE - pagedSessions.value.length)
const meetingFillerCount = computed(() => MEETING_PAGE_SIZE - pagedMeetings.value.length)

watch(() => sortedSessions.value.length, (len) => {
  const tp = Math.max(1, Math.ceil(len / SESSION_PAGE_SIZE))
  if (sessionPage.value > tp) sessionPage.value = tp
})
watch(() => sortedMeetings.value.length, (len) => {
  const tp = Math.max(1, Math.ceil(len / MEETING_PAGE_SIZE))
  if (meetingPage.value > tp) meetingPage.value = tp
})
</script>

<template>
  <div class="home-page page-full-height">
    <div class="home-body">
    <div class="home">

    <!-- ① 예정된 회의 -->
    <div class="sessions-section">
      <div class="section-title-row">
        
        <h6 class="section-title mb-0" style="color:var(--primary)"><svg class="me-2" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24" style="vertical-align:-2px"><path d="M12 1a3 3 0 00-3 3v8a3 3 0 006 0V4a3 3 0 00-3-3z"/><path d="M19 10v2a7 7 0 01-14 0v-2M12 19v4M8 23h8"/></svg>예정된 회의 <span class="section-count">({{ upcomingSessions.length }}건)</span></h6>
      </div>
      <AppTable :columns="sessionColumns" :sortKey="sessionSortKey" :sortDir="sessionSortDir" @sort="handleSessionSort">
        <tr v-for="s in pagedSessions" :key="s.id" style="cursor:pointer">
          <td><div class="fw-semibold">{{ s.title }}</div></td>
          <td class="text-muted">{{ s.meeting_title || '-' }}</td>
          <td class="text-muted">{{ s.location || '-' }}</td>
          <td>{{ formatDate(s.date) }}</td>
          <td>
            <span class="upcoming-dday"
              :class="getDday(s.date) <= 3 ? 'dday-urgent' : 'dday-normal'">
              {{ getDday(s.date) === 0 ? 'D-day' : `D-${getDday(s.date)}` }}
            </span>
          </td>
        </tr>
        <tr v-for="i in sessionFillerCount" :key="`filler-${i}`" class="filler-row">
          <td v-for="(c, ci) in sessionColumns" :key="ci">&nbsp;</td>
        </tr>
      </AppTable>
      <AppPagination v-model="sessionPage" :totalItems="sortedSessions.length" :pageSize="SESSION_PAGE_SIZE" />
    </div>

    <!-- ②③ 하단 2열: 진행중인 회의체 + 달력 -->
    <div class="main-grid">

    <!-- ② 회의체 섹션 -->
    <div class="meetings-section">
      <div class="section-title-row">
        <h6 class="section-title mb-0" style="color:var(--primary)"><svg width="15" height="15" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><circle cx="12" cy="5" r="2"/><circle cx="19" cy="17" r="2"/><circle cx="5" cy="17" r="2"/><circle cx="12" cy="12" r="2"/><line x1="12" y1="7" x2="12" y2="10"/><line x1="12" y1="14" x2="17.4" y2="15.6"/><line x1="12" y1="14" x2="6.6" y2="15.6"/></svg>
       진행중인 회의체 <span class="section-count">({{ displayActiveMeetings.length }}건)</span></h6>
      </div>

      <!-- 회의체 테이블 -->
      <AppTable :columns="meetingColumns" :sortKey="meetingSortKey" :sortDir="meetingSortDir" @sort="handleMeetingSort">
        <tr v-for="m in pagedMeetings" :key="m.id"
          style="cursor:pointer" @click="router.push('/meetings')">
          <td>
            <div class="fw-semibold">{{ m.title }}</div>
          </td>
          <td>
            <span class="text-muted" style="font-size:12px;">{{ m.meeting_type || '-' }}</span>
          </td>
          <td>
            <span class="text-muted" style="font-size:12px;">{{ m.role === 'admin' ? '간사' : '참여자' }}</span>
          </td>
          <td class="text-muted">{{ m.owner_name || '-' }}</td>
          <td class="text-muted">{{ m.member_count }}명</td>
        </tr>
        <tr v-for="i in meetingFillerCount" :key="`filler-${i}`" class="filler-row">
          <td v-for="(c, ci) in meetingColumns" :key="ci">&nbsp;</td>
        </tr>
      </AppTable>
      <AppPagination v-model="meetingPage" :totalItems="sortedMeetings.length" :pageSize="MEETING_PAGE_SIZE" />
    </div>

    <!-- ③ 달력 -->
    <div class="calendar-section">
      <div class="section-title-row">
        <h6 class="section-title mb-0" style="color:var(--primary)"><i class="bi bi-calendar3 me-2"></i>캘린더</h6>
      </div>
      <div class="card cal-card">
        <div class="cal-header">
          <div class="d-flex align-items-center gap-1">
            <button class="btn btn-sm px-1" @click="navigate(-1)">‹</button>
            <button class="btn btn-sm px-1" @click="goToday">오늘</button>
            <button class="btn btn-sm px-1" @click="navigate(1)">›</button>
          </div>
          <span class="cal-title">{{ calTitle }}</span>
          <div class="view-switch">
            <button v-for="v in views" :key="v.key"
              class="view-btn"
              :class="{ active: calView === v.key }"
              @click="calView = v.key">{{ v.label }}</button>
          </div>
        </div>

        <!-- Month -->
        <div v-if="calView === 'month'" class="cal-body">
          <div class="cal-weekrow">
            <div v-for="wd in WEEKDAYS_KO" :key="wd" class="wd-cell">{{ wd }}</div>
          </div>
          <div class="month-grid">
            <div
              v-for="(cell, i) in monthCells" :key="i"
              class="month-cell"
              :class="{ empty: !cell, today: cell && isToday(cell), 'has-events': cell && eventsOn(cell).length > 0 }"
              @click="cell && clickDay(cell)"
            >
              <span v-if="cell" class="day-num">{{ cell.getDate() }}</span>
              <div v-if="cell" class="month-evts">
                <div v-for="e in eventsOn(cell).slice(0,2)" :key="e.id" class="evt-pill" :class="evtCls(e.type)" :title="e.title">{{ e.title }}</div>
                <div v-if="eventsOn(cell).length > 2" class="evt-more">+{{ eventsOn(cell).length - 2 }}</div>
              </div>
            </div>
          </div>
        </div>

        <!-- Week -->
        <div v-else-if="calView === 'week'" class="cal-body">
          <div class="week-grid">
            <div v-for="d in weekDays" :key="d.toISOString()" class="week-col" :class="{ today: isToday(d) }" @click="clickDay(d)">
              <div class="week-col-header">
                <span class="week-wd">{{ WEEKDAYS_KO[(d.getDay() + 6) % 7] }}</span>
                <span class="week-daynum" :class="{ today: isToday(d) }">{{ d.getDate() }}</span>
              </div>
              <div class="week-evts">
                <div v-for="e in eventsOn(d)" :key="e.id" class="evt-pill" :class="evtCls(e.type)" :title="e.title">{{ e.title }}</div>
                <div v-if="!eventsOn(d).length" class="week-empty-slot" />
              </div>
            </div>
          </div>
        </div>

        <!-- Day -->
        <div v-else-if="calView === 'day'" class="cal-body">
          <div class="day-view">
            <div v-if="!dayEvents.length" class="empty-state" style="padding:32px 16px"><p>이 날에 등록된 일정이 없습니다.</p></div>
            <div v-for="e in dayEvents" :key="e.id" class="day-evt-row">
              <div class="day-evt-bar" :class="evtCls(e.type)" />
              <div class="day-evt-info">
                <div class="day-evt-title">{{ e.title }}</div>
                <span class="badge" :class="e.type === 'session' ? 'badge-app-primary' : 'badge-app-warning'">
                  {{ e.type === 'session' ? '회의' : 'To-do 마감' }}
                </span>
              </div>
            </div>
          </div>
        </div>

        <!-- Year -->
        <div v-else-if="calView === 'year'" class="cal-body">
          <div class="year-grid">
            <div v-for="ym in yearMonths" :key="ym.month" class="mini-month"
              @click="cursor = new Date(cursor.value.getFullYear(), ym.month-1, 1); calView = 'month'"
            >
              <div class="mini-month-title">{{ ym.month }}월</div>
              <div class="mini-weekrow"><span v-for="wd in WEEKDAYS_KO" :key="wd">{{ wd }}</span></div>
              <div class="mini-grid">
                <div v-for="(cell, i) in ym.cells" :key="i" class="mini-cell"
                  :class="{ today: cell && isToday(cell), 'has-evt': cell && eventsOn(cell).length > 0 }"
                  @click.stop="cell && clickMiniDay(cell)"
                >
                  <span v-if="cell">{{ cell.getDate() }}</span>
                </div>
              </div>
            </div>
          </div>
        </div>

        <div class="cal-legend">
          <span><i class="dot-session"></i> 회의</span>
          <span><i class="dot-agenda"></i> 아젠다 마감</span>
        </div>
      </div>
    </div>
    </div><!-- /main-grid -->

    </div><!-- /home -->
    </div><!-- /home-body -->

  </div>
</template>

<style scoped>
/* ── 전체 레이아웃 (아카이브·회사·회의체 탭과 동일: 다크 헤더 바 + 스크롤 본문) ── */
.home-page { display: flex; flex-direction: column; height: 100%; }
.home-body { flex: 1; overflow-y: auto; min-height: 0; padding: 6px 16px; }
.home { display: flex; flex-direction: column; gap: 20px; padding-bottom: 40px; }

.section-title-row { display: flex; align-items: center; justify-content: space-between; height: 32px;}
.section-title { font-size: 16px; font-weight: 700; }

/* ── ① To-do 섹션 ───────────────────────────────────────────── */
.agenda-section { padding: 14px 16px; }
.agenda-section .section-title-row { margin-bottom: 12px; }
.empty-inline { font-size: 13px; color: var(--text-muted); padding: 4px 0; }
.agenda-list { display: flex; flex-direction: column; gap: 6px; }
.agenda-row {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 10px;
  border-radius: var(--radius);
  background: var(--surface);
  border: 1px solid var(--border);
 
}
.agenda-row:hover { background: var(--surface-2); }
.agenda-row.done .agenda-content { text-decoration: line-through; color: var(--text-muted); }
.agenda-check { background: none; border: none; cursor: pointer; padding: 0; display: flex; align-items: center; flex-shrink: 0; }
.agenda-circle { display: inline-block; width: 16px; height: 16px; border-radius: 50%; border: 2px solid var(--border); }
.agenda-content { flex: 1; font-size: 13px; }
.agenda-dday { font-size: 11px; font-weight: 600; padding: 2px 7px; border-radius: 99px; background: var(--surface-2); color: var(--text-muted); white-space: nowrap; flex-shrink: 0; }
.agenda-dday.urgent { background: #fef3c7; color: #d97706; }
.agenda-dday.overdue { background: #fee2e2; color: var(--danger); }
.agenda-meeting { font-size: 11px; color: var(--text-muted); background: #eff6ff; border-radius: 99px; padding: 2px 7px; flex-shrink: 0; }
.agenda-row.pinned { background: #fffbeb; border-color: #fde68a; }
.agenda-row.pinned:hover { background: #fef3c7; }
.pin-fixed-icon { font-size: 13px; flex-shrink: 0; opacity: 0.8; }
.pin-btn { background: none; border: none; cursor: pointer; padding: 0 2px; font-size: 13px; opacity: 0.3; flex-shrink: 0; }
.pin-btn:hover { opacity: 0.8; }
.pin-btn.active { opacity: 1; transform: rotate(-30deg); }


/* ── ②③ 메인 2열 그리드 ─────────────────────────────────────── */
.main-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; align-items: start; }

/* ── ① 예정된 회의 섹션 ─────────────────────────────────────── */
.sessions-section { display: flex; flex-direction: column; gap: 12px; }

/* app-table 행 hover — 회사·회의체 탭(.member-row/.mg-row)과 동일한 색상 변화 */
.sessions-section :deep(tbody tr:not(.filler-row):hover),
.meetings-section :deep(tbody tr:not(.filler-row):hover) { background: var(--surface); }

/* ── ② 회의체 섹션 ──────────────────────────────────────────── */
.meetings-section { display: flex; flex-direction: column; gap: 12px; }

/* ── ③ 달력 섹션 ────────────────────────────────────────────── */
.calendar-section { display: flex; flex-direction: column; gap: 12px; }
.meeting-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 12px; }
.meeting-card { padding: 16px; cursor: pointer;  display: flex; flex-direction: column; gap: 4px; }
.meeting-card:hover { box-shadow: var(--shadow-md); }
.meeting-card-ended { opacity: 0.7; background: var(--surface); }
.meeting-card-ended:hover { opacity: 0.9; }
.meeting-card-header { display: flex; align-items: flex-start; justify-content: space-between; gap: 8px; margin-bottom: 2px; }
.meeting-title { font-size: 14px; font-weight: 600; flex: 1; }
.meeting-meta { font-size: 12px; color: var(--text-muted); line-height: 1.4; }
.meeting-dates { font-size: 11px; color: var(--text-muted); }
.meeting-card-actions { margin-top: 8px; padding-top: 8px; border-top: 1px solid var(--border); display: flex; justify-content: flex-end; }
.btn-meeting-end {
  padding: 3px 10px;
  border-radius: var(--radius);
  border: 1px solid var(--danger);
  background: transparent;
  color: var(--danger);
  font-size: 12px;
  font-weight: 700;
  cursor: pointer;
  line-height: 1.5;
}
.btn-meeting-end:hover:not(:disabled) { background: var(--danger); color: #fff; }
.btn-meeting-end:disabled { opacity: .45; cursor: not-allowed; }

/* ── 달력 ──────────────────────────────────────────────────── */
.cal-card { display: flex; flex-direction: column; height: 448.5px; }
.cal-header { display: flex; align-items: center; justify-content: space-between; padding: 4px 8px; border-bottom: 1px solid var(--border); gap: 8px; flex-wrap: wrap; font-size: 13px; height: 33.5px; flex-shrink: 0; }
.cal-header .btn.btn-sm { width: 18px; height: 18px; padding: 0; display: inline-flex; align-items: center; justify-content: center; font-size: 13px; line-height: 1; white-space: nowrap; }
.cal-title { font-size: 13px; font-weight: 600; flex: 1; text-align: center; white-space: nowrap; }
.cal-nav { display: flex; align-items: center; gap: 4px; }
.nav-btn { width: 28px; height: 28px; display: flex; align-items: center; justify-content: center; border-radius: 6px; background: none; border: 1px solid var(--border); font-size: 13px; color: var(--text-muted); cursor: pointer;  line-height: 1; }
.nav-btn:hover { background: var(--bg); color: var(--text); }
.today-btn { padding: 4px 10px; border-radius: 6px; background: none; border: 1px solid var(--border); font-size: 13px; font-weight: 500; color: var(--text-muted); cursor: pointer;  }
.today-btn:hover { background: var(--primary); color: #fff; border-color: var(--primary); }
.view-switch { display: flex; border: 1px solid var(--border); border-radius: 6px; overflow: hidden; }
.view-btn { padding: 0px; font-size: 13px; font-weight: 500; background: none; border: none; color: var(--text-muted); cursor: pointer; width: 18px; height: 18px; }
.view-btn:hover { background: var(--bg); color: var(--text); width: 18px; height: 18px;}
.view-btn.active { background: var(--primary); color: #fff; width: 18px; height: 18px;}
.cal-body { padding: 12px; flex: 1; min-height: 0; overflow-y: auto; }
.cal-weekrow { display: grid; grid-template-columns: repeat(7,1fr); margin-bottom: 4px; }
.wd-cell { text-align: center; font-size: 13px; font-weight: 600; color: var(--text-muted); padding: 4px 0; }
.month-grid { display: grid; grid-template-columns: repeat(7,1fr); gap: 1px; }
.month-cell { min-height: 52px; border-radius: 6px; padding: 4px 3px 3px; cursor: pointer; display: flex; flex-direction: column; gap: 2px; min-width: 0; overflow: hidden; }
.month-cell:not(.empty):hover { background: var(--surface-2); }
.month-cell.empty { cursor: default; }
.month-cell.today .day-num { background: var(--primary); color: #fff; border-radius: 50%; width: 22px; height: 22px; display: flex; align-items: center; justify-content: center; font-weight: 700; }
.day-num { font-size: 13px; width: 22px; height: 22px; display: flex; align-items: center; justify-content: center; }
.month-evts { display: flex; flex-direction: column; gap: 1px; min-width: 0; width: 100%; }
.week-grid { display: grid; grid-template-columns: repeat(7,1fr); gap: 4px; min-height: 160px; }
.week-col { border-radius: 6px; border: 1px solid var(--border); display: flex; flex-direction: column; cursor: pointer; overflow: hidden; min-width: 0; }
.week-col:hover { background: var(--surface); }
.week-col.today { border-color: var(--primary); }
.week-col-header { padding: 6px 6px 4px; border-bottom: 1px solid var(--border); display: flex; flex-direction: column; align-items: center; gap: 2px; background: var(--surface); flex-shrink: 0; }
.week-wd { font-size: 13px; font-weight: 600; color: var(--text-muted); text-transform: uppercase; }
.week-daynum { font-size: 13px; font-weight: 600; width: 24px; height: 24px; display: flex; align-items: center; justify-content: center; border-radius: 50%; }
.week-daynum.today { background: var(--primary); color: #fff; }
.week-evts { flex: 1; padding: 4px; display: flex; flex-direction: column; gap: 2px; }
.week-empty-slot { flex: 1; }
.day-view { display: flex; flex-direction: column; gap: 8px; min-height: 140px; }
.day-evt-row { display: flex; align-items: flex-start; gap: 10px; padding: 10px 12px; background: var(--surface); border-radius: 8px; border: 1px solid var(--border); }
.day-evt-bar { width: 3px; min-height: 36px; border-radius: 2px; flex-shrink: 0; }
.day-evt-bar.evt-session { background: var(--accent); }
.day-evt-bar.evt-agenda { background: var(--warning); }
.day-evt-info { flex: 1; display: flex; flex-direction: column; gap: 4px; }
.day-evt-title { font-size: 13px; font-weight: 500; }
.year-grid { display: grid; grid-template-columns: repeat(3,1fr); gap: 10px; }
.mini-month { border: 1px solid var(--border); border-radius: 8px; padding: 8px; cursor: pointer;}
.mini-month:hover { box-shadow: var(--shadow-md); }
.mini-month-title { font-size: 13px; font-weight: 700; color: var(--primary); margin-bottom: 4px; text-align: center; }
.mini-weekrow { display: grid; grid-template-columns: repeat(7,1fr); margin-bottom: 2px; }
.mini-weekrow span { font-size: 13px; font-weight: 600; color: var(--text-muted); text-align: center; }
.mini-grid { display: grid; grid-template-columns: repeat(7,1fr); gap: 1px; }
.mini-cell { font-size: 13px; text-align: center; border-radius: 3px; padding: 1px 0; cursor: pointer; line-height: 1.6; }
.mini-cell:not(:empty):hover { background: var(--border); }
.mini-cell.today { background: var(--primary); color: #fff; border-radius: 50%; }
.mini-cell.has-evt { font-weight: 700; color: var(--accent); }
.evt-pill { font-size: 13px; font-weight: 500; border-radius: 3px; padding: 1px 4px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; cursor: pointer; }
.evt-pill.evt-session { background: #dbeafe; color: #1d4ed8; }

/* 우선순위 배지 */
.section-count { font-size: 13px; font-weight: 500; color: var(--text-muted); }
.upcoming-dday { font-size: 12px; font-weight: 700; }
.upcoming-dday.dday-urgent { color: #d97706; }
.upcoming-dday.dday-normal { color: var(--text-muted); }
/* 유형 텍스트 (배지 없음) */
.type-badge { font-size: 11px; font-weight: 600; }
.type-badge-weekly    { color: #3b82f6; }
.type-badge-monthly   { color: #8b5cf6; }
.type-badge-quarterly { color: #f59e0b; }
.type-badge-default   { color: var(--accent); }
.role-badge { font-size: 11px; font-weight: 700; padding: 2px 7px; border-radius: 6px; }
.role-admin  { background: rgba(59,130,246,.15); color: #3b82f6; }
.role-member { background: rgba(100,116,139,.12); color: var(--text-muted); }
.evt-pill.evt-agenda   { background: #fef3c7; color: #92400e; }
.evt-more { font-size: 13px; color: var(--text-muted); padding-left: 2px; }
.cal-legend { display: flex; gap: 14px; padding: 8px 16px; border-top: 1px solid var(--border); font-size: 13px; color: var(--text-muted); }
.cal-legend span { display: flex; align-items: center; gap: 5px; }
.dot-session, .dot-agenda { display: inline-block; width: 8px; height: 8px; border-radius: 2px; }
.dot-session { background: var(--accent); }
.dot-agenda { background: var(--warning); }


</style>
