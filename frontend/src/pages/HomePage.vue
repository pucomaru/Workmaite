<script setup>
import { ref, onMounted, computed } from 'vue'
import { useRouter } from 'vue-router'
import { useMeetingsStore } from '../stores/meetings'
import { useAuthStore } from '../stores/auth'
import api, { apiAI } from '../api'

import BaseModal from '../components/BaseModal.vue'
import AppTable from '../components/AppTable.vue'

const router = useRouter()
const auth = useAuthStore()
const meetingsStore = useMeetingsStore()

const calendarEvents = ref([])
const showCreateModal = ref(false)
const form = ref({ title: '', purpose: '', start_date: '', end_date: '' })
const memberSearch = ref('')
const searchResults = ref([])
const selectedMembers = ref([])
const creating = ref(false)

const meetingRoles = ref({})   // { [meetingId]: 'admin' | 'presenter' | null }
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
  return type === 'session' ? 'evt-session' : 'evt-todo'
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
  try {
    const calRes = await api.get('/api/v1/home/calendar', { params: { view: 'month', date: new Date().toISOString().slice(0, 10) } })
    calendarEvents.value = calRes.data
  } catch {}

  await hydrateMeetingMeta()

  // 각 회의체에 대한 내 권한 병렬 조회
  await Promise.all(
    meetingsStore.meetings.map(async (m) => {
      try {
        const { data } = await api.get(`/api/v1/meetings/${m.id}/my-role`)
        meetingRoles.value[m.id] = data.role
      } catch {
        meetingRoles.value[m.id] = null
      }
    })
  )
})

async function hydrateMeetingMeta() {
  const active = meetingsStore.meetings.filter(m => m.status === 'active')
  const entries = await Promise.all(
    active.map(async (m) => {
      try {
        const [membersRes, todosRes] = await Promise.all([
          api.get(`/api/v1/meetings/${m.id}/members`),
          apiAI.get(`/api/meetings/${m.id}/todos`),
        ])

        const members = membersRes.data || []
        const todos = todosRes.data || []

        const admin = members.find(mm => mm.role === 'admin')
        const owner_name = admin?.user?.name || admin?.user_name || '-'

        const openTodos = todos
          .filter(t => t.status !== 'done')
          .sort((a, b) => {
            const da = a.due_date ? new Date(a.due_date).getTime() : Number.MAX_SAFE_INTEGER
            const db = b.due_date ? new Date(b.due_date).getTime() : Number.MAX_SAFE_INTEGER
            return da - db
          })

        const topTodo = openTodos[0]
        return [m.id, {
          owner_name,
          due_date: topTodo?.due_date || null,
          priority: topTodo?.priority || 'normal',
        }]
      } catch {
        return [m.id, { owner_name: '-', due_date: null, priority: 'normal' }]
      }
    })
  )
  meetingMeta.value = Object.fromEntries(entries)
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

// ── Modal ────────────────────────────────────────────────────
async function searchMembers() {
  if (!memberSearch.value.trim()) { searchResults.value = []; return }
  const { data } = await api.get(`/api/v1/users/search?q=${memberSearch.value}`)
  searchResults.value = data.filter(u => u.id !== auth.user?.id && !selectedMembers.value.find(m => m.id === u.id))
}
function addMember(u, role = 'presenter') {
  selectedMembers.value.push({ ...u, role })
  searchResults.value = []
  memberSearch.value = ''
}
function removeMember(u) {
  selectedMembers.value = selectedMembers.value.filter(m => m.id !== u.id)
}
async function createMeeting() {
  if (!form.value.title.trim()) return
  creating.value = true
  try {
    const meeting = await meetingsStore.createMeeting({
      title: form.value.title,
      purpose: form.value.purpose,
      start_date: form.value.start_date || null,
      end_date: form.value.end_date || null,
    })
    for (const m of selectedMembers.value) {
      await api.post(`/api/v1/meetings/${meeting.id}/members`, { userId: m.id, role: m.role })
    }
    showCreateModal.value = false
    form.value = { title: '', purpose: '', start_date: '', end_date: '' }
    selectedMembers.value = []
    router.push('/meeting-groups')
  } finally {
    creating.value = false
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
    due_date: meetingMeta.value[m.id]?.due_date ?? null,
    priority: meetingMeta.value[m.id]?.priority ?? m.priority ?? 'normal',
  }))
)

// 예정된 회의: calendarEvents 중 type='session' 이고 오늘 이후 항목
const sessionColumns = [
  { label: '회의명', sortKey: 'title' },
  { label: '회의체', sortKey: 'meeting_title' },
  { label: '날짜', width: '110px', sortKey: 'date' },
  { label: 'D-day', width: '80px', sortKey: 'date' },
]

const meetingColumns = [
  { label: '회의체명', sortKey: 'title' },
  { label: '유형', width: '90px', sortKey: 'meeting_type' },
  { label: '담당자', width: '90px', sortKey: 'owner_name' },
  { label: '마감일', width: '110px', sortKey: 'due_date' },
  { label: '우선순위', width: '80px', sortKey: 'priority' },
]

const upcomingSessions = computed(() => {
  const todayStr = fmtISO(new Date())
  return calendarEvents.value
    .filter(e => e.type === 'session' && e.date >= todayStr)
    .sort((a, b) => new Date(a.date) - new Date(b.date))
})

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
</script>

<template>
  <div class="home page-wrap">

    <!-- ① 예정된 회의 -->
    <div class="d-flex align-items-center justify-content-between mb-3">
      <h6 class="mb-0 fw-bold" style="color:var(--primary)"><i class="bi bi-calendar-event me-2"></i>예정된 회의 <span class="section-count">({{ upcomingSessions.length }}건)</span></h6>
    </div>
    <AppTable :columns="sessionColumns" :sortKey="sessionSortKey" :sortDir="sessionSortDir" @sort="handleSessionSort">
      <tr v-for="s in sortedSessions" :key="s.id" style="cursor:pointer">
        <td><div class="fw-semibold">{{ s.title }}</div></td>
        <td class="text-muted">{{ s.meeting_title || '-' }}</td>
        <td>{{ formatDate(s.date) }}</td>
        <td>
          <span class="upcoming-dday"
            :class="getDday(s.date) <= 3 ? 'dday-urgent' : 'dday-normal'">
            {{ getDday(s.date) === 0 ? 'D-day' : `D-${getDday(s.date)}` }}
          </span>
        </td>
      </tr>
    </AppTable>

    <!-- ②③ 하단 2열: 진행중인 회의체 + 달력 -->
    <div class="main-grid">

    <!-- ② 회의체 섹션 -->
    <div class="meetings-section">
      <div class="d-flex align-items-center justify-content-between mb-3">
        <h6 class="mb-0 fw-bold" style="color:var(--primary)"><i class="bi bi-people me-2"></i>진행중인 회의체 <span class="section-count">({{ displayActiveMeetings.length }}건)</span></h6>
      </div>

      <!-- 회의체 테이블 -->
      <AppTable :columns="meetingColumns" :sortKey="meetingSortKey" :sortDir="meetingSortDir" @sort="handleMeetingSort">
        <tr v-for="m in sortedMeetings" :key="m.id"
          style="cursor:pointer" @click="router.push('/meeting-groups')">
          <td>
            <div class="fw-semibold">{{ m.title }}</div>
          </td>
          <td>
            <span class="type-badge">{{ m.meeting_type || 'Weekly' }}</span>
          </td>
          <td class="text-muted">{{ m.owner_name || '-' }}</td>
          <td>
            <span v-if="(m.due_date || m.end_date)" style="color:#1e293b">
              {{ formatDate(m.due_date || m.end_date) }}
            </span>
            <span v-else class="text-muted">-</span>
          </td>
          <td>
            <span v-if="m.priority === 'high'" class="priority-indicator high">▲ 상</span>
            <span v-else-if="m.priority === 'low'" class="priority-indicator low">▼ 하</span>
            <span v-else class="priority-indicator mid">— 중</span>
          </td>
        </tr>
      </AppTable>
    </div>

    <!-- ③ 달력 -->
    <div class="card cal-card">
        <div class="cal-header">
          <div class="d-flex align-items-center gap-1">
            <button class="btn btn-sm btn-outline-secondary px-2" @click="navigate(-1)">‹</button>
            <button class="btn btn-sm btn-outline-secondary px-2" @click="goToday">오늘</button>
            <button class="btn btn-sm btn-outline-secondary px-2" @click="navigate(1)">›</button>
          </div>
          <span class="cal-title">{{ calTitle }}</span>
          <div class="btn-group btn-group-sm">
            <button v-for="v in views" :key="v.key"
              class="btn"
              :class="calView === v.key ? 'btn-primary' : 'btn-outline-secondary'"
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
          <span><i class="dot-todo"></i> To-do 마감</span>
        </div>
      </div>
    </div><!-- /main-grid -->

    <!-- 회의체 생성 모달 -->
    <BaseModal v-model="showCreateModal">
      <template #title>새 회의체 만들기</template>
      <div class="modal-inner">
        <div class="form-group">
          <label class="form-label">회의체 제목 <span style="color:var(--danger)">*</span></label>
          <input v-model="form.title" class="form-input" placeholder="예: 경영전략 위원회" />
        </div>
        <div class="form-group">
          <label class="form-label">회의체 목적</label>
          <textarea v-model="form.purpose" class="form-input form-textarea" placeholder="회의체의 목적을 입력하세요" />
        </div>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px">
          <div class="form-group">
            <label class="form-label">시작일</label>
            <input type="date" v-model="form.start_date" class="form-input" />
          </div>
          <div class="form-group">
            <label class="form-label">종료일</label>
            <input type="date" v-model="form.end_date" class="form-input" />
          </div>
        </div>

      </div>
      <template #footer>
        <button class="btn btn-outline-secondary" @click="showCreateModal = false">취소</button>
        <button class="btn btn-primary" :disabled="!form.title.trim() || creating" @click="createMeeting">
          {{ creating ? '생성 중...' : '회의체 생성' }}
        </button>
      </template>
    </BaseModal>
  </div>
</template>

<style scoped>
/* ── 전체 레이아웃 ──────────────────────────────────────────── */
.home { display: flex; flex-direction: column; gap: 20px; padding-bottom: 40px; }

.section-title-row { display: flex; align-items: center; justify-content: space-between; }
.section-title { font-size: 15px; font-weight: 700; }

/* ── ① To-do 섹션 ───────────────────────────────────────────── */
.todo-section { padding: 14px 16px; }
.todo-section .section-title-row { margin-bottom: 12px; }
.empty-inline { font-size: 13px; color: var(--text-muted); padding: 4px 0; }
.todo-list { display: flex; flex-direction: column; gap: 6px; }
.todo-row {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 10px;
  border-radius: var(--radius);
  background: #f8fafc;
  border: 1px solid var(--border);
  transition: background .1s;
}
.todo-row:hover { background: #f1f5f9; }
.todo-row.done .todo-content { text-decoration: line-through; color: var(--text-muted); }
.todo-check { background: none; border: none; cursor: pointer; padding: 0; display: flex; align-items: center; flex-shrink: 0; }
.todo-circle { display: inline-block; width: 16px; height: 16px; border-radius: 50%; border: 2px solid var(--border); }
.todo-content { flex: 1; font-size: 13px; }
.todo-dday { font-size: 11px; font-weight: 600; padding: 2px 7px; border-radius: 99px; background: #f1f5f9; color: var(--text-muted); white-space: nowrap; flex-shrink: 0; }
.todo-dday.urgent { background: #fef3c7; color: #d97706; }
.todo-dday.overdue { background: #fee2e2; color: var(--danger); }
.todo-meeting { font-size: 11px; color: var(--text-muted); background: #eff6ff; border-radius: 99px; padding: 2px 7px; flex-shrink: 0; }
.todo-row.pinned { background: #fffbeb; border-color: #fde68a; }
.todo-row.pinned:hover { background: #fef3c7; }
.pin-fixed-icon { font-size: 13px; flex-shrink: 0; opacity: 0.8; }
.pin-btn { background: none; border: none; cursor: pointer; padding: 0 2px; font-size: 13px; opacity: 0.3; transition: opacity .15s, transform .15s; flex-shrink: 0; }
.pin-btn:hover { opacity: 0.8; }
.pin-btn.active { opacity: 1; transform: rotate(-30deg); }


/* ── ②③ 메인 2열 그리드 ─────────────────────────────────────── */
.main-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; align-items: start; }

/* ── ② 회의체 섹션 ──────────────────────────────────────────── */
.meetings-section { display: flex; flex-direction: column; gap: 12px; }
.meeting-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 12px; }
.meeting-card { padding: 16px; cursor: pointer; transition: box-shadow .15s; display: flex; flex-direction: column; gap: 4px; }
.meeting-card:hover { box-shadow: var(--shadow-md); }
.meeting-card-ended { opacity: 0.7; background: #f8fafc; }
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
  transition: background .15s, color .15s;
  line-height: 1.5;
}
.btn-meeting-end:hover:not(:disabled) { background: var(--danger); color: #fff; }
.btn-meeting-end:disabled { opacity: .45; cursor: not-allowed; }

/* ── 달력 ──────────────────────────────────────────────────── */
.cal-card { display: flex; flex-direction: column; }
.cal-header { display: flex; align-items: center; justify-content: space-between; padding: 12px 16px; border-bottom: 1px solid var(--border); gap: 8px; flex-wrap: wrap; }
.cal-title { font-size: 13px; font-weight: 600; flex: 1; text-align: center; white-space: nowrap; }
.cal-nav { display: flex; align-items: center; gap: 4px; }
.nav-btn { width: 28px; height: 28px; display: flex; align-items: center; justify-content: center; border-radius: 6px; background: none; border: 1px solid var(--border); font-size: 16px; color: var(--text-muted); cursor: pointer; transition: all .15s; line-height: 1; }
.nav-btn:hover { background: var(--bg); color: var(--text); }
.today-btn { padding: 4px 10px; border-radius: 6px; background: none; border: 1px solid var(--border); font-size: 12px; font-weight: 500; color: var(--text-muted); cursor: pointer; transition: all .15s; }
.today-btn:hover { background: var(--primary); color: #fff; border-color: var(--primary); }
.view-switch { display: flex; border: 1px solid var(--border); border-radius: 6px; overflow: hidden; }
.view-btn { padding: 4px 8px; font-size: 12px; font-weight: 500; background: none; border: none; color: var(--text-muted); cursor: pointer; transition: all .15s; }
.view-btn:hover { background: var(--bg); color: var(--text); }
.view-btn.active { background: var(--primary); color: #fff; }
.cal-body { padding: 12px; }
.cal-weekrow { display: grid; grid-template-columns: repeat(7,1fr); margin-bottom: 4px; }
.wd-cell { text-align: center; font-size: 11px; font-weight: 600; color: var(--text-muted); padding: 4px 0; }
.month-grid { display: grid; grid-template-columns: repeat(7,1fr); gap: 1px; }
.month-cell { min-height: 52px; border-radius: 6px; padding: 4px 3px 3px; cursor: pointer; display: flex; flex-direction: column; gap: 2px; transition: background .1s; min-width: 0; overflow: hidden; }
.month-cell:not(.empty):hover { background: #f1f5f9; }
.month-cell.empty { cursor: default; }
.month-cell.today .day-num { background: var(--primary); color: #fff; border-radius: 50%; width: 22px; height: 22px; display: flex; align-items: center; justify-content: center; font-weight: 700; }
.day-num { font-size: 12px; width: 22px; height: 22px; display: flex; align-items: center; justify-content: center; }
.month-evts { display: flex; flex-direction: column; gap: 1px; min-width: 0; width: 100%; }
.week-grid { display: grid; grid-template-columns: repeat(7,1fr); gap: 4px; min-height: 160px; }
.week-col { border-radius: 6px; border: 1px solid var(--border); display: flex; flex-direction: column; cursor: pointer; transition: background .1s; overflow: hidden; min-width: 0; }
.week-col:hover { background: #f8fafc; }
.week-col.today { border-color: var(--primary); }
.week-col-header { padding: 6px 6px 4px; border-bottom: 1px solid var(--border); display: flex; flex-direction: column; align-items: center; gap: 2px; background: #f8fafc; flex-shrink: 0; }
.week-wd { font-size: 10px; font-weight: 600; color: var(--text-muted); text-transform: uppercase; }
.week-daynum { font-size: 13px; font-weight: 600; width: 24px; height: 24px; display: flex; align-items: center; justify-content: center; border-radius: 50%; }
.week-daynum.today { background: var(--primary); color: #fff; }
.week-evts { flex: 1; padding: 4px; display: flex; flex-direction: column; gap: 2px; }
.week-empty-slot { flex: 1; }
.day-view { display: flex; flex-direction: column; gap: 8px; min-height: 140px; }
.day-evt-row { display: flex; align-items: flex-start; gap: 10px; padding: 10px 12px; background: #f8fafc; border-radius: 8px; border: 1px solid var(--border); }
.day-evt-bar { width: 3px; min-height: 36px; border-radius: 2px; flex-shrink: 0; }
.day-evt-bar.evt-session { background: var(--accent); }
.day-evt-bar.evt-todo { background: var(--warning); }
.day-evt-info { flex: 1; display: flex; flex-direction: column; gap: 4px; }
.day-evt-title { font-size: 13px; font-weight: 500; }
.year-grid { display: grid; grid-template-columns: repeat(3,1fr); gap: 10px; }
.mini-month { border: 1px solid var(--border); border-radius: 8px; padding: 8px; cursor: pointer; transition: box-shadow .15s; }
.mini-month:hover { box-shadow: var(--shadow-md); }
.mini-month-title { font-size: 12px; font-weight: 700; color: var(--primary); margin-bottom: 4px; text-align: center; }
.mini-weekrow { display: grid; grid-template-columns: repeat(7,1fr); margin-bottom: 2px; }
.mini-weekrow span { font-size: 8px; font-weight: 600; color: var(--text-muted); text-align: center; }
.mini-grid { display: grid; grid-template-columns: repeat(7,1fr); gap: 1px; }
.mini-cell { font-size: 9px; text-align: center; border-radius: 3px; padding: 1px 0; cursor: pointer; line-height: 1.6; }
.mini-cell:not(:empty):hover { background: #e2e8f0; }
.mini-cell.today { background: var(--primary); color: #fff; border-radius: 50%; }
.mini-cell.has-evt { font-weight: 700; color: var(--accent); }
.evt-pill { font-size: 10px; font-weight: 500; border-radius: 3px; padding: 1px 4px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; cursor: pointer; }
.evt-pill.evt-session { background: #dbeafe; color: #1d4ed8; }

/* 우선순위 배지 */
.section-count { font-size: 13px; font-weight: 500; color: var(--text-muted); }
.upcoming-dday { font-size: 12px; font-weight: 700; }
.upcoming-dday.dday-urgent { color: #d97706; }
.upcoming-dday.dday-normal { color: #64748b; }
.priority-indicator { font-size: 12px; font-weight: 700; display: inline-flex; align-items: center; gap: 2px; }
.priority-indicator.high { color: #dc2626; }
.priority-indicator.mid  { color: #d97706; }
.priority-indicator.low  { color: #2563eb; }
/* 유형 텍스트 (배지 없음) */
.type-badge { font-size: 12px; font-weight: 600; color: #64748b; }
.evt-pill.evt-todo   { background: #fef3c7; color: #92400e; }
.evt-more { font-size: 10px; color: var(--text-muted); padding-left: 2px; }
.cal-legend { display: flex; gap: 14px; padding: 8px 16px; border-top: 1px solid var(--border); font-size: 11px; color: var(--text-muted); }
.cal-legend span { display: flex; align-items: center; gap: 5px; }
.dot-session, .dot-todo { display: inline-block; width: 8px; height: 8px; border-radius: 2px; }
.dot-session { background: #3b82f6; }
.dot-todo { background: #f59e0b; }

/* ── 모달 ───────────────────────────────────────────────────── */
.modal-inner { padding: 20px 24px; display: flex; flex-direction: column; gap: 16px; }
.search-dropdown { border: 1px solid var(--border); border-radius: 6px; background: #fff; box-shadow: var(--shadow-md); margin-top: 4px; }
.search-item { padding: 8px 12px; display: flex; align-items: center; justify-content: space-between; border-bottom: 1px solid var(--border); font-size: 13px; }
.search-item:last-child { border-bottom: none; }
.selected-members { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 8px; }
.member-chip { display: inline-flex; align-items: center; gap: 6px; background: #eff6ff; border: 1px solid #bfdbfe; border-radius: 99px; padding: 4px 10px; font-size: 12px; }
</style>
