<script setup>
import { ref, onMounted, computed } from 'vue'
import { useRouter } from 'vue-router'
import { useMeetingsStore } from '../stores/meetings'
import { useAuthStore } from '../stores/auth'
import api from '../api'
import HyeanAgent from '../components/HyeanAgent.vue'

const router = useRouter()
const auth = useAuthStore()
const meetingsStore = useMeetingsStore()

const todos = ref([])
const myTasks = ref([])
const calendarEvents = ref([])
const showCreateModal = ref(false)
const form = ref({ title: '', purpose: '', start_date: '', end_date: '' })
const memberSearch = ref('')
const searchResults = ref([])
const selectedMembers = ref([])
const creating = ref(false)

// ── Calendar state ──────────────────────────────────────────
const calView = ref('month')
const cursor = ref(new Date())
const today = new Date()
today.setHours(0, 0, 0, 0)

const views = [
  { key: 'day',   label: '일' },
  { key: 'week',  label: '주' },
  { key: 'month', label: '월' },
  { key: 'year',  label: '년' },
]

function navigate(dir) {
  const d = new Date(cursor.value)
  if (calView.value === 'day')   d.setDate(d.getDate() + dir)
  if (calView.value === 'week')  d.setDate(d.getDate() + dir * 7)
  if (calView.value === 'month') d.setMonth(d.getMonth() + dir)
  if (calView.value === 'year')  d.setFullYear(d.getFullYear() + dir)
  cursor.value = d
}
function goToday() { cursor.value = new Date() }

const WEEKDAYS_KO = ['일','월','화','수','목','금','토']

const calTitle = computed(() => {
  const d = cursor.value
  const y = d.getFullYear()
  const m = d.getMonth() + 1
  if (calView.value === 'day') return `${y}년 ${m}월 ${d.getDate()}일 (${WEEKDAYS_KO[d.getDay()]})`
  if (calView.value === 'week') {
    const { start, end } = weekRange(d)
    const sm = start.getMonth() + 1, em = end.getMonth() + 1
    if (sm === em) return `${y}년 ${sm}월 ${start.getDate()}일 – ${end.getDate()}일`
    return `${y}년 ${sm}월 ${start.getDate()}일 – ${em}월 ${end.getDate()}일`
  }
  if (calView.value === 'month') return `${y}년 ${m}월`
  return `${y}년`
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
    const firstWd = new Date(y, m, 1).getDay()
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
    const [todoRes, taskRes, calRes] = await Promise.all([
      api.get('/api/todos/urgent'),
      api.get('/api/todos/mine').catch(() => api.get('/api/todos/urgent')),
      api.get('/api/calendar/events'),
    ])
    todos.value = todoRes.data
    myTasks.value = taskRes.data
    calendarEvents.value = calRes.data
  } catch {}
})

async function toggleTodo(todo) {
  const newStatus = todo.status === 'done' ? 'pending' : 'done'
  try {
    await api.patch(`/api/todos/${todo.id}`, { status: newStatus })
    todo.status = newStatus
  } catch {}
}

// ── Modal ────────────────────────────────────────────────────
async function searchMembers() {
  if (!memberSearch.value.trim()) { searchResults.value = []; return }
  const { data } = await api.get(`/api/users/search?q=${memberSearch.value}`)
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
      await api.post(`/api/meetings/${meeting.id}/members`, { user_id: m.id, role: m.role })
    }
    showCreateModal.value = false
    form.value = { title: '', purpose: '', start_date: '', end_date: '' }
    selectedMembers.value = []
    router.push(`/meetings/${meeting.id}/agenda`)
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
</script>

<template>
  <div class="home">

    <!-- ① To-do 리스트 -->
    <div class="card todo-section">
      <div class="section-title-row">
        <span class="section-title">나의 To-do</span>
        <span class="badge badge-muted" style="font-size:11px">{{ todos.length }}건</span>
      </div>
      <div v-if="!todos.length" class="empty-inline">등록된 To-do가 없습니다.</div>
      <div v-else class="todo-list">
        <div v-for="t in todos" :key="t.id" class="todo-row" :class="{ done: t.status === 'done' }">
          <button class="todo-check" @click="toggleTodo(t)">
            <svg v-if="t.status === 'done'" width="16" height="16" viewBox="0 0 16 16" fill="none">
              <circle cx="8" cy="8" r="7" fill="var(--success)" stroke="var(--success)"/>
              <path d="M5 8.5l2 2 4-4" stroke="#fff" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
            </svg>
            <span v-else class="todo-circle" />
          </button>
          <span class="todo-content">{{ t.content }}</span>
          <span v-if="t.due_date" class="todo-dday" :class="getDday(t.due_date) < 0 ? 'overdue' : getDday(t.due_date) <= 3 ? 'urgent' : ''">
            {{ getDday(t.due_date) < 0 ? `D+${Math.abs(getDday(t.due_date))}` : getDday(t.due_date) === 0 ? 'D-day' : `D-${getDday(t.due_date)}` }}
          </span>
          <span v-if="t.meeting_title" class="todo-meeting">{{ t.meeting_title }}</span>
        </div>
      </div>
    </div>

    <!-- ② 진행중인 회의체 -->
    <div class="meetings-section">
      <div class="section-title-row">
        <span class="section-title">진행중인 회의체</span>
        <button class="btn btn-primary btn-sm" @click="showCreateModal = true">+ 회의체 만들기</button>
      </div>
      <div class="meeting-grid">
        <div
          v-for="m in activeMeetings"
          :key="m.id"
          class="meeting-card card"
          @click="router.push(`/meetings/${m.id}/agenda`)"
        >
          <div class="meeting-card-header">
            <span class="meeting-title">{{ m.title }}</span>
            <span class="badge badge-success">진행중</span>
          </div>
          <div v-if="m.purpose" class="meeting-meta">{{ m.purpose.slice(0, 60) }}{{ m.purpose.length > 60 ? '...' : '' }}</div>
          <div v-if="m.start_date" class="meeting-dates">{{ formatDate(m.start_date) }} ~ {{ formatDate(m.end_date) }}</div>
        </div>
        <div v-if="!activeMeetings.length" class="empty-state" style="grid-column:1/-1">
          <p>진행중인 회의체가 없습니다.</p>
          <button class="btn btn-primary btn-sm" @click="showCreateModal = true">회의체 만들기</button>
        </div>
      </div>
    </div>

    <!-- ③ 하단 2열: 달력 + 나의 작업 -->
    <div class="bottom-grid">

      <!-- 달력 -->
      <div class="card cal-card">
        <div class="cal-header">
          <div class="cal-nav">
            <button class="nav-btn" @click="navigate(-1)">‹</button>
            <button class="today-btn" @click="goToday">오늘</button>
            <button class="nav-btn" @click="navigate(1)">›</button>
          </div>
          <span class="cal-title">{{ calTitle }}</span>
          <div class="view-switch">
            <button v-for="v in views" :key="v.key" class="view-btn" :class="{ active: calView === v.key }" @click="calView = v.key">{{ v.label }}</button>
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
                <span class="week-wd">{{ WEEKDAYS_KO[d.getDay()] }}</span>
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
                <span class="badge" :class="e.type === 'session' ? 'badge-primary' : 'badge-warning'">
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

      <!-- 나의 작업 -->
      <div class="card my-tasks-card">
        <div class="section-title-row" style="padding:14px 16px;border-bottom:1px solid var(--border)">
          <span class="section-title">나의 작업</span>
          <span class="badge badge-muted" style="font-size:11px">{{ myTasks.length }}건</span>
        </div>
        <div style="flex:1;overflow-y:auto">
          <div v-if="!myTasks.length" class="empty-state" style="padding:32px 16px">
            <p>진행 중인 작업이 없습니다.</p>
          </div>
          <div v-for="t in myTasks" :key="t.id" class="task-row" :class="{ done: t.status === 'done' }">
            <button class="todo-check" @click="toggleTodo(t)">
              <svg v-if="t.status === 'done'" width="16" height="16" viewBox="0 0 16 16" fill="none">
                <circle cx="8" cy="8" r="7" fill="var(--success)" stroke="var(--success)"/>
                <path d="M5 8.5l2 2 4-4" stroke="#fff" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
              </svg>
              <span v-else class="todo-circle" />
            </button>
            <div class="task-info">
              <div class="task-content">{{ t.content }}</div>
              <div class="task-meta">
                <span v-if="t.meeting_title" class="task-meeting">{{ t.meeting_title }}</span>
                <span v-if="t.due_date" class="todo-dday" :class="getDday(t.due_date) < 0 ? 'overdue' : getDday(t.due_date) <= 3 ? 'urgent' : ''">
                  {{ getDday(t.due_date) < 0 ? `D+${Math.abs(getDday(t.due_date))}` : getDday(t.due_date) === 0 ? 'D-day' : `D-${getDday(t.due_date)}` }}
                </span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- ④ 혜안 floating -->
    <HyeanAgent />

    <!-- 회의체 생성 모달 -->
    <div v-if="showCreateModal" class="modal-overlay" @click.self="showCreateModal = false">
      <div class="modal slide-up">
        <div class="modal-header">
          <span class="modal-title">새 회의체 만들기</span>
          <button class="btn-ghost btn-icon" @click="showCreateModal = false">✕</button>
        </div>
        <div class="modal-body">
          <div class="form-group">
            <label class="form-label">회의체 제목 <span style="color:var(--danger)">*</span></label>
            <input v-model="form.title" class="form-input" placeholder="예: 2024 경영전략 위원회" />
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
          <div class="form-group">
            <label class="form-label">멤버 초대</label>
            <input v-model="memberSearch" class="form-input" placeholder="사번 또는 이름 검색" @input="searchMembers" />
            <div v-if="searchResults.length" class="search-dropdown">
              <div v-for="u in searchResults" :key="u.id" class="search-item">
                <span>{{ u.name }} ({{ u.employee_id }})</span>
                <div style="display:flex;gap:4px">
                  <button class="btn btn-sm btn-primary" @click="addMember(u, 'admin')">Admin</button>
                  <button class="btn btn-sm btn-outline" @click="addMember(u, 'presenter')">Presenter</button>
                </div>
              </div>
            </div>
            <div v-if="selectedMembers.length" class="selected-members">
              <div v-for="m in selectedMembers" :key="m.id" class="member-chip">
                {{ m.name }}
                <span class="badge badge-primary" style="font-size:10px">{{ m.role }}</span>
                <button @click="removeMember(m)" style="background:none;color:var(--text-muted)">✕</button>
              </div>
            </div>
          </div>
        </div>
        <div class="modal-footer">
          <button class="btn btn-outline" @click="showCreateModal = false">취소</button>
          <button class="btn btn-primary" :disabled="!form.title.trim() || creating" @click="createMeeting">
            {{ creating ? '생성 중...' : '회의체 생성' }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* ── 전체 레이아웃 ──────────────────────────────────────────── */
.home { display: flex; flex-direction: column; gap: 20px; padding-bottom: 80px; }

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

/* ── ② 회의체 섹션 ──────────────────────────────────────────── */
.meetings-section { display: flex; flex-direction: column; gap: 12px; }
.meeting-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 12px; }
.meeting-card { padding: 16px; cursor: pointer; transition: box-shadow .15s; }
.meeting-card:hover { box-shadow: var(--shadow-md); }
.meeting-card-header { display: flex; align-items: flex-start; justify-content: space-between; gap: 8px; margin-bottom: 6px; }
.meeting-title { font-size: 14px; font-weight: 600; flex: 1; }
.meeting-meta { font-size: 12px; color: var(--text-muted); line-height: 1.4; margin-bottom: 6px; }
.meeting-dates { font-size: 11px; color: var(--text-muted); }

/* ── ③ 하단 2열 ─────────────────────────────────────────────── */
.bottom-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; align-items: start; }

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
.month-cell { min-height: 52px; border-radius: 6px; padding: 4px 3px 3px; cursor: pointer; display: flex; flex-direction: column; gap: 2px; transition: background .1s; }
.month-cell:not(.empty):hover { background: #f1f5f9; }
.month-cell.empty { cursor: default; }
.month-cell.today .day-num { background: var(--primary); color: #fff; border-radius: 50%; width: 22px; height: 22px; display: flex; align-items: center; justify-content: center; font-weight: 700; }
.day-num { font-size: 12px; width: 22px; height: 22px; display: flex; align-items: center; justify-content: center; }
.month-evts { display: flex; flex-direction: column; gap: 1px; }
.week-grid { display: grid; grid-template-columns: repeat(7,1fr); gap: 4px; min-height: 160px; }
.week-col { border-radius: 6px; border: 1px solid var(--border); display: flex; flex-direction: column; cursor: pointer; transition: background .1s; overflow: hidden; }
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
.evt-pill.evt-todo   { background: #fef3c7; color: #92400e; }
.evt-more { font-size: 10px; color: var(--text-muted); padding-left: 2px; }
.cal-legend { display: flex; gap: 14px; padding: 8px 16px; border-top: 1px solid var(--border); font-size: 11px; color: var(--text-muted); }
.cal-legend span { display: flex; align-items: center; gap: 5px; }
.dot-session, .dot-todo { display: inline-block; width: 8px; height: 8px; border-radius: 2px; }
.dot-session { background: #3b82f6; }
.dot-todo { background: #f59e0b; }

/* ── 나의 작업 ──────────────────────────────────────────────── */
.my-tasks-card { display: flex; flex-direction: column; max-height: 520px; }
.task-row {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 12px 16px;
  border-bottom: 1px solid var(--border);
  transition: background .1s;
}
.task-row:hover { background: #f8fafc; }
.task-row:last-child { border-bottom: none; }
.task-row.done .task-content { text-decoration: line-through; color: var(--text-muted); }
.task-info { flex: 1; display: flex; flex-direction: column; gap: 4px; }
.task-content { font-size: 13px; line-height: 1.4; }
.task-meta { display: flex; align-items: center; gap: 6px; }
.task-meeting { font-size: 11px; color: var(--primary); background: #eff6ff; border-radius: 99px; padding: 2px 7px; }

/* ── 모달 ───────────────────────────────────────────────────── */
.search-dropdown { border: 1px solid var(--border); border-radius: 6px; background: #fff; box-shadow: var(--shadow-md); margin-top: 4px; }
.search-item { padding: 8px 12px; display: flex; align-items: center; justify-content: space-between; border-bottom: 1px solid var(--border); font-size: 13px; }
.search-item:last-child { border-bottom: none; }
.selected-members { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 8px; }
.member-chip { display: inline-flex; align-items: center; gap: 6px; background: #eff6ff; border: 1px solid #bfdbfe; border-radius: 99px; padding: 4px 10px; font-size: 12px; }
</style>
