<script setup>
import { computed, onMounted, ref } from 'vue'
import api, { apiAI } from '../api'
import AppTable from '../components/AppTable.vue'
import AppTableSection from '../components/AppTableSection.vue'
import MemberEditModal from '../components/MemberEditModal.vue'
import { confirmDialog, promptDialog } from '../composables/useConfirm'
import { usePagination } from '../composables/usePagination'
import { useTableSort } from '../composables/useTableSort'
import { toast } from '../composables/useToast'
import { useThemeStore } from '../stores/theme'
import { useAuthStore } from '../stores/auth'

const auth = useAuthStore()

const companyColumns = [
  { label: '이름', width: '100px', sortKey: 'name' },
  { label: '회사', width: '110px', sortKey: 'company' },
  { label: '부서', width: '110px', sortKey: 'department' },
  { label: '직책', width: '80px', sortKey: 'position' },
  { label: '권한', width: '90px', sortKey: 'role' },
  { label: '이메일', width: '180px', sortKey: 'email' },
  { label: '참여 회의체' },
  { label: '', width: '72px', noResize: true },
]

function roleLabel(role) {
  return (
    { SYSTEM_ADMIN: '시스템 관리자', COMPANY_ADMIN: '회사 관리자', USER: '일반 사용자' }[role] ||
    '일반 사용자'
  )
}

// 권한 정렬 순서: 시스템 관리자 → 회사 관리자 → 일반 사용자
const ROLE_RANK = { SYSTEM_ADMIN: 0, COMPANY_ADMIN: 1, USER: 2 }

const themeStore = useThemeStore()
const nightMode = computed(() => themeStore.nightMode)

const selectedMeetingId = ref('all')
const searchQuery = ref('')
const allMembers = ref([])
// 본인이 속한 회의체 목록 (PostgreSQL 기준 권한 범위)
const myMeetings = ref([])
const loadingMembers = ref(true) // 첫 페인트부터 로딩 표시 — onMounted 이전에 빈 상태가 노출되는 깜빡임 방지

const showAddModal = ref(false)
const addForm = ref({
  name: '',
  email: '',
  company: '',
  department: '',
  position: '',
  password: '',
})
const addError = ref('')

const editModal = ref(null) // { ...member }

// 본인이 속한 회의체의 구성원만 PostgreSQL 기준으로 조회 (서버에서 권한 범위 강제)
async function fetchAllMembers() {
  loadingMembers.value = true
  try {
    const res = await apiAI.get('/api/ai/company/members')
    myMeetings.value = res.data.meetings ?? []
    allMembers.value = (res.data.members ?? []).map(u => ({
      id: u.id,
      name: u.name,
      email: u.email,
      employee_id: u.email,
      department: u.department,
      company: u.company,
      position: u.position,
      role: u.role,
      meetings: u.meetings ?? [],
    }))
  } catch {
    myMeetings.value = []
    allMembers.value = []
  } finally {
    loadingMembers.value = false
  }
}

const filteredMembers = computed(() => {
  const sid = selectedMeetingId.value
  let list = allMembers.value
  if (sid !== 'all') list = list.filter(m => m.meetings.some(mg => String(mg.id) === String(sid)))
  const q = searchQuery.value.trim().toLowerCase()
  if (q)
    list = list.filter(m =>
      [
        m.name,
        m.company,
        m.department,
        m.position,
        roleLabel(m.role),
        m.email,
        ...(m.meetings || []).map(g => g.title),
      ].some(v => (v ?? '').toString().toLowerCase().includes(q)),
    )
  return list
})

const memberCount = computed(() => {
  const sid = selectedMeetingId.value
  if (sid === 'all') return allMembers.value.length
  return allMembers.value.filter(m => m.meetings.some(g => String(g.id) === String(sid))).length
})

onMounted(async () => {
  await fetchAllMembers()
})

function openAddModal() {
  addForm.value = { name: '', email: '', company: '', department: '', position: '', password: '' }
  addError.value = ''
  showAddModal.value = true
}

// 임시 비밀번호 방식 (P1-7② 개정): 관리자가 임시 비밀번호로 즉시 계정 생성,
// 해당 계정은 최초 로그인 시 비밀번호 변경이 강제된다(서버 필터로 차단)
async function submitAdd() {
  addError.value = ''
  if (!addForm.value.name.trim()) {
    addError.value = '이름을 입력해주세요.'
    return
  }
  if (!addForm.value.email.trim()) {
    addError.value = '이메일을 입력해주세요.'
    return
  }
  if ((addForm.value.password || '').length < 8) {
    addError.value = '임시 비밀번호(8자 이상)를 입력해주세요.'
    return
  }
  try {
    const { data } = await api.post('/api/v1/users/bulk', [
      {
        name: addForm.value.name,
        email: addForm.value.email,
        department: addForm.value.department || '',
        position: addForm.value.position || '',
        password: addForm.value.password,
      },
    ])
    const r = data?.[0]
    if (r && !r.ok) {
      addError.value = r.reason || '등록 실패'
      return
    }
    await fetchAllMembers()
    showAddModal.value = false
  } catch (e) {
    addError.value = e.response?.data?.message || '등록에 실패했습니다. (관리자 권한 필요)'
  }
}

async function _removeMember(member) {
  // (A) 본인 자기 삭제 금지 — 관리자라도 자신은 제거할 수 없다.
  if (member.id === auth.user?.id) {
    toast.error('자기 자신은 제거할 수 없습니다.')
    return
  }
  if (member.isCustom) {
    if (
      !(await confirmDialog(`${member.name || member.email}을(를) 제거하시겠습니까?`, {
        danger: true,
      }))
    )
      return
    allMembers.value = allMembers.value.filter(m => m.id !== member.id)
    return
  }

  const sid = selectedMeetingId.value
  if (sid !== 'all') {
    // (B) 특정 회의체 필터 중 — 그 회의체에서만 제외 (PG 원천: Spring)
    const mship = member.meetings.find(g => String(g.id) === String(sid))
    if (!mship?.member_id) {
      toast.error('해당 회의체의 멤버십을 찾을 수 없습니다.')
      return
    }
    if (
      !(await confirmDialog(`이 회의체에서 ${member.name || member.email}님을 제외하시겠습니까?`, {
        danger: true,
      }))
    )
      return
    try {
      await api.delete(`/api/v1/meetings/${sid}/members/${mship.member_id}`)
      await fetchAllMembers()
    } catch (e) {
      toast.error(e.response?.data?.message || '제외에 실패했습니다.')
    }
  } else {
    // (B) 전체 보기 — 계정 삭제(한 번에). 서버가 모든 회의체 멤버십·FK를 정리하고 소프트 삭제한다.
    if (
      !(await confirmDialog(
        `${member.name || member.email}님의 계정을 삭제하시겠습니까? 모든 회의체에서 제외됩니다.`,
        { danger: true },
      ))
    )
      return
    try {
      await apiAI.delete(`/api/ai/users/${member.id}`)
      await fetchAllMembers()
    } catch (e) {
      toast.error(e.response?.data?.detail || '계정 삭제에 실패했습니다.')
    }
  }
}

function openEdit(member) {
  // member는 /api/ai/company/members 응답 형태({ id, name, email, company, department, position, role, meetings })
  // 그대로 공용 모달이 받는 구성원 객체와 호환된다.
  editModal.value = { ...member }
}

const expandedRows = ref(new Set())
function toggleExpand(key) {
  const s = new Set(expandedRows.value)
  s.has(key) ? s.delete(key) : s.add(key)
  expandedRows.value = s
}

// ── CSV 내보내기 ──────────────────────────────────────────
function exportCSV() {
  // 임시비밀번호 컬럼은 보안상 값을 비워 내보낸다 (가져오기 시 채워 일괄 등록용 템플릿 겸용)
  const headers = ['이름', '이메일', '회사', '부서', '직책', '임시비밀번호']
  const rows = filteredMembers.value.map(m => [
    m.name || '',
    m.email || '',
    m.company || '',
    m.department || '',
    m.position || '',
    '',
  ])
  const csvContent = [headers, ...rows]
    .map(row => row.map(cell => `"${String(cell).replace(/"/g, '""')}"`).join(','))
    .join('\n')
  const blob = new Blob(['\uFEFF' + csvContent], { type: 'text/csv;charset=utf-8;' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `구성원_${new Date().toISOString().slice(0, 10)}.csv`
  a.click()
  URL.revokeObjectURL(url)
}

// ── CSV 가져오기 ──────────────────────────────────────────
const csvImportInput = ref(null)

function triggerCSVImport() {
  csvImportInput.value?.click()
}

function handleCSVFile(e) {
  const file = e.target.files?.[0]
  if (!file) return
  const reader = new FileReader()
  reader.onload = ev => {
    parseAndImportCSV(ev.target.result)
  }
  reader.readAsText(file, 'utf-8')
  e.target.value = ''
}

const csvImportResult = ref(null)

function parseCSVLine(line) {
  const result = []
  let cur = '',
    inQuote = false
  for (let i = 0; i < line.length; i++) {
    const ch = line[i]
    if (ch === '"') {
      if (inQuote && line[i + 1] === '"') {
        cur += '"'
        i++
      } else inQuote = !inQuote
    } else if (ch === ',' && !inQuote) {
      result.push(cur.trim())
      cur = ''
    } else {
      cur += ch
    }
  }
  result.push(cur.trim())
  return result
}

const CSV_HEADER_MAP = {
  이름: 'name',
  name: 'name',
  이메일: 'email',
  email: 'email',
  회사: 'company',
  회사명: 'company',
  company: 'company',
  부서: 'department',
  부서명: 'department',
  department: 'department',
  직책: 'position',
  position: 'position',
  임시비밀번호: 'password',
  비밀번호: 'password',
  password: 'password',
}

async function parseAndImportCSV(text) {
  // BOM 제거
  const content = text.replace(/^\uFEFF/, '')
  const lines = content.split(/\r?\n/).filter(l => l.trim())
  if (lines.length < 2) {
    toast.info('CSV 파일에 데이터가 없습니다.')
    return
  }

  const headerLine = parseCSVLine(lines[0])
  const fieldKeys = headerLine.map(
    h => CSV_HEADER_MAP[h.toLowerCase()] || CSV_HEADER_MAP[h] || null,
  )

  if (!fieldKeys.includes('name')) {
    toast.info('CSV에 "이름" 열이 필요합니다.\n헤더 예시: 이름,이메일,조직,부서,직책,임시비밀번호')
    return
  }

  // 일괄 임시 비밀번호: CSV에 개별 비밀번호가 없거나 비어있는 행에 공통 적용 (각자 최초 로그인 시 변경 강제)
  const bulkPassword = (
    (await promptDialog(
      '가져올 구성원의 임시 비밀번호를 입력하세요 (8자 이상)\nCSV 비밀번호가 있으면 우선 적용됩니다',
      { placeholder: '임시 비밀번호 입력', inputType: 'password', minLength: 8 },
    )) || ''
  ).trim()

  const existingEmails = new Set(allMembers.value.map(m => (m.email || '').toLowerCase()))
  const skippedNoEmail = []
  const skippedDuplicate = []
  const succeeded = []
  const failed = []

  for (let i = 1; i < lines.length; i++) {
    const cols = parseCSVLine(lines[i])
    const obj = {}
    fieldKeys.forEach((key, idx) => {
      if (key) obj[key] = cols[idx] || ''
    })
    if (!obj.name) continue

    if (!obj.email) {
      skippedNoEmail.push(obj.name)
      continue
    }

    const emailLower = obj.email.toLowerCase()
    if (existingEmails.has(emailLower)) {
      skippedDuplicate.push(obj.name)
      continue
    }

    const rowPassword = obj.password || bulkPassword
    if (!rowPassword || rowPassword.length < 8) {
      failed.push(`${obj.name} (임시 비밀번호 없음/8자 미만)`)
      continue
    }
    try {
      // 임시 비밀번호 방식 (P1-7② 개정): 행별 비밀번호 또는 일괄 비밀번호로 즉시 생성, 로그인 시 변경 강제
      const { data } = await api.post('/api/v1/users/bulk', [
        {
          name: obj.name,
          email: obj.email,
          department: obj.department || '',
          position: obj.position || '',
          password: rowPassword,
        },
      ])
      const r = data?.[0]
      if (r && !r.ok) {
        failed.push(`${obj.name} (${r.reason})`)
        continue
      }
      existingEmails.add(emailLower)
      succeeded.push(obj.name)
    } catch {
      failed.push(obj.name)
    }
  }

  await fetchAllMembers()

  const pwNote = bulkPassword
    ? '임시 비밀번호로 로그인 → 최초 로그인 시 변경 강제'
    : '각자 CSV의 임시 비밀번호로 로그인 → 변경 강제'
  const resultLines = [`${succeeded.length}명 등록 완료 (${pwNote})`]
  if (skippedNoEmail.length)
    resultLines.push(`이메일 없음 (${skippedNoEmail.length}명): ${skippedNoEmail.join(', ')}`)
  if (skippedDuplicate.length)
    resultLines.push(`이미 존재 (${skippedDuplicate.length}명): ${skippedDuplicate.join(', ')}`)
  if (failed.length) resultLines.push(`등록 실패 (${failed.length}명): ${failed.join(', ')}`)
  csvImportResult.value = resultLines.join('\n')
}

const groupedFilteredMembers = computed(() => filteredMembers.value)

// ── 정렬·페이지네이션 (공통 컴포저블) ────────────────
const {
  sortKey,
  sortDir,
  handleSort,
  sorted: sortedMembers,
} = useTableSort(groupedFilteredMembers, { sortValues: { role: m => ROLE_RANK[m.role] ?? 99 } })

const MEMBER_PAGE_SIZE = 15
const {
  page: memberPage,
  paged: pagedMembers,
  fillerCount: memberFillerCount,
} = usePagination(sortedMembers, MEMBER_PAGE_SIZE)
</script>

<template>
  <div class="company-page page-full-height" :class="{ 'day-mode': !nightMode }">
    <!-- Archive-style header -->
    <div class="archive-header">
      <div class="header-title-wrap">
        <h1 class="archive-title">구성원 관리</h1>
      </div>

      <div class="search-wrap">
        <svg
          class="search-icon"
          width="14"
          height="14"
          fill="none"
          stroke="currentColor"
          stroke-width="2"
          viewBox="0 0 24 24"
        >
          <circle cx="11" cy="11" r="8" />
          <path d="M21 21l-4.35-4.35" />
        </svg>
        <input
          v-model="searchQuery"
          class="search-input"
          name="search"
          placeholder="이름, 직책, 이메일 검색..."
        />
      </div>

      <div class="plus-wrap">
        <input
          ref="csvImportInput"
          id="csv-import-input"
          type="file"
          accept=".csv"
          style="display: none"
          @change="handleCSVFile"
        />
        <button class="create-btn secondary" @click="exportCSV" title="현재 목록을 CSV로 내보내기">
          <svg
            width="13"
            height="13"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
            viewBox="0 0 24 24"
          >
            <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4" />
            <polyline points="17 8 12 3 7 8" />
            <line x1="12" y1="3" x2="12" y2="15" />
          </svg>
          CSV 내보내기
        </button>
        <button
          class="create-btn secondary"
          @click="triggerCSVImport"
          title="CSV 파일로 구성원 일괄 등록"
        >
          <svg
            width="13"
            height="13"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
            viewBox="0 0 24 24"
          >
            <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4" />
            <polyline points="7 10 12 15 17 10" />
            <line x1="12" y1="15" x2="12" y2="3" />
          </svg>
          CSV 가져오기
        </button>
        <button class="create-btn" @click="openAddModal">
          <svg
            width="13"
            height="13"
            fill="none"
            stroke="currentColor"
            stroke-width="2.5"
            viewBox="0 0 24 24"
          >
            <path d="M16 21v-2a4 4 0 00-4-4H6a4 4 0 00-4 4v2" />
            <circle cx="9" cy="7" r="4" />
            <path d="M19 8v6M22 11h-6" />
          </svg>
          구성원 추가
        </button>
      </div>
    </div>

    <!-- 목록 본문 (공통 레이아웃: lv-header + table-wrap) -->
    <AppTableSection
      v-model:page="memberPage"
      :total-items="sortedMembers.length"
      :page-size="MEMBER_PAGE_SIZE"
      :dark="nightMode"
      :show-pagination="!loadingMembers"
    >
      <template #filters>
        <select v-model="selectedMeetingId" name="meeting" class="lv-type-filter">
          <option value="all">내 회의체 전체</option>
          <option v-for="m in myMeetings" :key="m.id" :value="String(m.id)">{{ m.title }}</option>
        </select>
      </template>
      <template #header-right>
        <span class="lv-title">{{
          searchQuery ? `"${searchQuery}" 검색 결과` : '조회된 구성원'
        }}</span>
        <span class="lv-count">{{ memberCount }}명</span>
      </template>

      <div v-if="loadingMembers" class="table-loading">
        <span class="spinner-border spinner-border-sm text-primary"></span>
        <span style="margin-left: 10px; color: var(--text-muted); font-size: 12px"
          >불러오는 중...</span
        >
      </div>
      <template v-else>
        <AppTable
          :columns="companyColumns"
          :dark="nightMode"
          :sortKey="sortKey"
          :sortDir="sortDir"
          @sort="handleSort"
        >
          <tr v-for="member in pagedMembers" :key="member.email || member.name" class="member-row">
            <td>
              <div class="name-cell">
                <span class="member-name-text">{{ member.name || '이름없음' }}</span>
              </div>
            </td>
            <td class="text-muted">{{ member.company || '-' }}</td>
            <td class="text-muted">{{ member.department || '-' }}</td>
            <td class="text-muted">{{ member.position || '-' }}</td>
            <td class="text-muted">{{ roleLabel(member.role) }}</td>
            <td class="text-muted">{{ member.email || '-' }}</td>
            <td>
              <div class="cell-meetings">
                <template v-if="selectedMeetingId !== 'all'">
                  <span class="meeting-tag">{{
                    member.meetings.find(g => String(g.id) === String(selectedMeetingId))?.title ||
                    '-'
                  }}</span>
                </template>
                <template v-else>
                  <span v-if="!member.meetings.length"></span>
                  <span
                    v-for="mg in member.meetings.slice(0, 5)"
                    :key="mg.id"
                    class="meeting-tag"
                    >{{ mg.title }}</span
                  >
                  <template v-if="member.meetings.length > 5">
                    <template v-if="expandedRows.has(member.email || member.name)">
                      <span
                        v-for="mg in member.meetings.slice(5)"
                        :key="mg.id"
                        class="meeting-tag"
                        >{{ mg.title }}</span
                      >
                      <button
                        class="meeting-more-btn"
                        @click.stop="toggleExpand(member.email || member.name)"
                      >
                        접기
                      </button>
                    </template>
                    <button
                      v-else
                      class="meeting-more-btn"
                      @click.stop="toggleExpand(member.email || member.name)"
                    >
                      +{{ member.meetings.length - 5 }}개 더보기
                    </button>
                  </template>
                </template>
              </div>
            </td>
            <td>
              <div class="action-btns">
                <button class="act-btn" @click="openEdit(member)" title="수정">
                  <svg
                    width="13"
                    height="13"
                    fill="none"
                    stroke="currentColor"
                    stroke-width="2"
                    viewBox="0 0 24 24"
                  >
                    <path d="M11 4H4a2 2 0 00-2 2v14a2 2 0 002 2h14a2 2 0 002-2v-7" />
                    <path d="M18.5 2.5a2.121 2.121 0 013 3L12 15l-4 1 1-4 9.5-9.5z" />
                  </svg>
                </button>
              </div>
            </td>
          </tr>
          <!-- filler 행 — 마지막 페이지에서 테이블 높이를 유지해 페이지네이션 위치가 튀지 않게 한다 -->
          <tr
            v-for="n in memberFillerCount"
            :key="`filler-${n}`"
            class="filler-row"
            aria-hidden="true"
          >
            <td :colspan="companyColumns.length"></td>
          </tr>
          <tr v-if="!groupedFilteredMembers.length">
            <td colspan="7" class="empty-row">
              <div class="empty-state">
                <p>
                  {{ myMeetings.length ? '조회할 구성원이 없습니다' : '조회할 구성원이 없습니다' }}
                </p>
              </div>
            </td>
          </tr>
        </AppTable>
      </template>
    </AppTableSection>

    <!-- Add member modal -->
    <Teleport to="body">
      <div v-if="showAddModal" class="app-modal-backdrop">
        <div class="app-modal app-modal-sm">
          <div class="app-modal-header">
            <span class="app-modal-title">구성원 추가</span>
            <button class="app-modal-close" @click="showAddModal = false">
              <svg
                width="14"
                height="14"
                fill="none"
                stroke="currentColor"
                stroke-width="2.5"
                viewBox="0 0 24 24"
              >
                <path d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
          <div class="app-modal-body">
            <div class="app-modal-field-row">
              <div class="app-modal-field">
                <label for="add-member-name">이름 <span class="req">*</span></label>
                <input
                  id="add-member-name"
                  v-model="addForm.name"
                  autocomplete="off"
                  class="app-modal-input"
                  placeholder="홍길동"
                />
              </div>
              <div class="app-modal-field">
                <label for="add-member-email">이메일</label>
                <input
                  id="add-member-email"
                  v-model="addForm.email"
                  autocomplete="off"
                  class="app-modal-input"
                  placeholder="example@company.com"
                />
              </div>
            </div>
            <div class="app-modal-field-row">
              <div class="app-modal-field">
                <label for="add-member-company">회사명</label>
                <input
                  id="add-member-company"
                  v-model="addForm.company"
                  autocomplete="off"
                  class="app-modal-input"
                  placeholder="예: SK AX"
                />
              </div>
              <div class="app-modal-field">
                <label for="add-member-department">부서명</label>
                <input
                  id="add-member-department"
                  v-model="addForm.department"
                  autocomplete="off"
                  class="app-modal-input"
                  placeholder="예: 전략기획팀"
                />
              </div>
            </div>
            <div class="app-modal-field-row">
              <div class="app-modal-field">
                <label for="add-member-position">직책</label>
                <input
                  id="add-member-position"
                  v-model="addForm.position"
                  autocomplete="off"
                  class="app-modal-input"
                  placeholder="예: 팀장"
                />
              </div>
              <div class="app-modal-field">
                <label for="add-member-password">비밀번호 <span class="req">*</span></label>
                <input
                  id="add-member-password"
                  v-model="addForm.password"
                  type="password"
                  autocomplete="new-password"
                  class="app-modal-input"
                  placeholder="임시 비밀번호 (8자 이상 — 최초 로그인 시 변경 강제)"
                />
              </div>
            </div>
            <div v-if="addError" style="color: #ef4444; font-size: 12px; margin-top: 8px">
              {{ addError }}
            </div>
          </div>
          <div class="app-modal-footer">
            <button class="app-btn-cancel" @click="showAddModal = false">취소</button>
            <button class="app-btn-primary" :disabled="!addForm.name.trim()" @click="submitAdd">
              추가
            </button>
          </div>
        </div>
      </div>

      <!-- CSV 가져오기 결과 모달 -->
      <div v-if="csvImportResult" class="app-modal-backdrop">
        <div class="app-modal app-modal-sm">
          <div class="app-modal-header">
            <span class="app-modal-title">CSV 가져오기 결과</span>
            <button class="app-modal-close" @click="csvImportResult = null">
              <svg
                width="14"
                height="14"
                fill="none"
                stroke="currentColor"
                stroke-width="2.5"
                viewBox="0 0 24 24"
              >
                <path d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
          <div
            class="app-modal-body"
            style="white-space: pre-line; font-size: 14px; line-height: 1.8"
          >
            {{ csvImportResult }}
          </div>
          <div class="app-modal-footer">
            <button class="app-btn-primary" @click="csvImportResult = null">확인</button>
          </div>
        </div>
      </div>

      <!-- Edit member modal (공용 컴포넌트 — ArchivePage와 동일 동작/권한 로직) -->
      <MemberEditModal
        :member="editModal"
        :night-mode="nightMode"
        @close="editModal = null"
        @saved="fetchAllMembers"
        @deleted="fetchAllMembers"
      />
    </Teleport>
  </div>
</template>

<style scoped>
.company-page {
  display: flex;
  flex-direction: column;
  margin: -24px -28px 0 -28px;
  height: calc(100% + 24px);
  overflow: hidden;
}

/* filler 행 — 마지막 페이지 높이 유지용. 상호작용·테두리 없음 */
.filler-row td {
  height: 41px;
  border-bottom: none !important;
}
.filler-row:hover {
  background: transparent !important;
}

.member-count-text {
  font-size: 12px;
  color: #c8d1dd;
  white-space: nowrap;
  flex-shrink: 0;
}
.day-mode .member-count-text {
  color: #5a5f66;
}
.company-scope-badge {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  font-weight: 600;
  color: #7dd3fc;
  background: rgba(56, 189, 248, 0.12);
  border: 1px solid rgba(56, 189, 248, 0.3);
  border-radius: 6px;
  padding: 3px 8px;
  white-space: nowrap;
  flex-shrink: 0;
}
.company-scope-badge svg {
  flex-shrink: 0;
}
.day-mode .company-scope-badge {
  color: #0369a1;
  background: rgba(2, 132, 199, 0.08);
  border-color: rgba(2, 132, 199, 0.25);
}
.company-meeting-select {
  min-width: 120px;
  font-size: 12px;
  font-weight: 500;
  height: 32px;
  padding-top: 0;
  padding-bottom: 0;
}

/* 목록 레이아웃(lv-*, table-wrap, table-loading)은 style.css 전역 단일 정의 + AppTableSection 사용 */
.member-row {
  border-bottom: 1px solid var(--white-06);
}
.member-row:last-child {
  border-bottom: none;
}
.member-row:hover {
  background: var(--white-04);
}
.member-row:hover td:last-child {
  background: var(--white-04);
}
.day-mode .member-row {
  border-bottom-color: var(--surface-2);
}
.day-mode .member-row:hover {
  background: #fafbff;
}
.day-mode .member-row:hover td:last-child {
  background: #fafbff;
}

.name-cell {
  display: flex;
  align-items: center;
  gap: 10px;
}
.member-name-text {
  font-weight: 600;
  color: var(--dark-text);
}
.day-mode .member-name-text {
  color: var(--dark-card);
}
.cell-muted {
  color: var(--text-muted);
  padding: 4px;
}
.day-mode .cell-muted {
  color: var(--text-muted);
}
.cell-meetings {
  display: flex;
  flex-wrap: nowrap;
  align-items: center;
  gap: 4px;
  overflow: hidden;
  width: 100%;
}
.meeting-tag {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 4px;
  background: var(--surface-2);
  color: var(--text-muted);
  font-size: 12px;
  white-space: nowrap;
}
.meeting-more-btn {
  border: none;
  background: none;
  color: var(--dark-muted);
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  padding: 2px 4px;
  border-radius: 4px;
  white-space: nowrap;
  flex-shrink: 0;
}
.meeting-more-btn:hover {
  color: var(--accent);
}

.action-btns {
  display: flex;
  gap: 4px;
  width: fit-content;
  margin-left: auto;
}
:deep(td:last-child) {
  padding-left: 6px;
  padding-right: 6px;
}
.act-btn {
  width: 28px;
  height: 28px;
  border-radius: 7px;
  border: 1px solid var(--white-10);
  background: var(--white-05);
  color: var(--text-muted);
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
}
.act-btn:hover {
  border-color: rgba(96, 165, 250, 0.5);
  color: var(--accent-soft);
  background: rgba(96, 165, 250, 0.1);
}
.act-btn.danger:hover {
  border-color: #fca5a5;
  color: #dc2626;
  background: rgba(96, 165, 250, 0.1);
}

.empty-row {
  padding: 0 !important;
}
.req {
  color: var(--danger);
}
.dropdown-results {
  position: absolute;
  top: calc(100% + 4px);
  left: 0;
  right: 0;
  background: #fff;
  border: 1px solid var(--border);
  border-radius: 10px;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.12);
  z-index: 10;
  overflow: hidden;
  max-height: 200px;
  overflow-y: auto;
}
.dropdown-item-result {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
  cursor: pointer;
}
.dropdown-item-result:hover {
  background: var(--surface-2);
}
</style>
