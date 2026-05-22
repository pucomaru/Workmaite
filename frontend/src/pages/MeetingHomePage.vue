<script setup>
import { ref, onMounted, computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import api, { streamPost } from '../api'
import MeetingNav from '../components/MeetingNav.vue'
import BaseModal from '../components/BaseModal.vue'
import { useMeetingsStore } from '../stores/meetings'
import { useAuthStore } from '../stores/auth'
import hyeanAvatar from '../assets/agents/hyean.png'
import { renderMd } from '../composables/useMarkdown'

const route = useRoute()
const router = useRouter()
const meetingsStore = useMeetingsStore()
const auth = useAuthStore()

const meetingId = computed(() => Number(route.params.meetingId))
const role = computed(() => meetingsStore.myRole)
const isAdmin = computed(() => role.value === 'admin')

// ── 회의체 기본 정보 ───────────────────────────────────────────
const meeting = computed(() => meetingsStore.currentMeeting)
const members = ref([])

// ── 편집 상태 ─────────────────────────────────────────────────
const editingTitle  = ref(false)
const editingPurpose = ref(false)
const editingDates  = ref(false)
const editingMembers = ref(false)

const titleDraft   = ref('')
const purposeDraft = ref('')
const startDraft   = ref('')
const endDraft     = ref('')
const memberSearch = ref('')
const memberSearchResults = ref([])
const saving = ref(false)

// ── 활동 기록 팝업 (단일 문서) ───────────────────────────────
const showMemoryPopup = ref(false)
const memDoc = ref({ content: '', updated_at: null })
const memLoading = ref(false)
const memEditing = ref(false)
const memEditBuf = ref('')
const memSaving = ref(false)

// ── 현황 요약 (Hyean) ─────────────────────────────────────────
const statusSummary = ref('')
const summaryLoading = ref(false)
const summaryGeneratedAt = ref(null)

// ── 보고서 리스트 ──────────────────────────────────────────────
const reports = ref([])
const reportsLoading = ref(false)

// ── 회의록 리스트 ──────────────────────────────────────────────
const minutes = ref([])
const minutesLoading = ref(false)

// ── 상태 레이블 ────────────────────────────────────────────────
const reportStatusMap = {
  draft: '검토전',
  submitted: '검토중',
  approved: '승인',
  rejected: '반려',
}
const reportStatusCls = {
  draft: 'badge-muted',
  submitted: 'badge-warn',
  approved: 'badge-success',
  rejected: 'badge-danger',
}

// ── 기간 / 남은 기간 ───────────────────────────────────────────
const remainingDays = computed(() => {
  if (!meeting.value?.end_date) return null
  const diff = Math.ceil((new Date(meeting.value.end_date) - new Date()) / 86400000)
  return diff
})

function formatDate(d) {
  if (!d) return '-'
  return new Date(d).toLocaleDateString('ko-KR', { year: 'numeric', month: 'short', day: 'numeric' })
}

// ── Load ──────────────────────────────────────────────────────
onMounted(async () => {
  await Promise.all([
    meetingsStore.fetchMeeting(meetingId.value),
    meetingsStore.fetchRole(meetingId.value),
    meetingsStore.fetchMembers(meetingId.value),
  ])
  members.value = meetingsStore.currentMembers

  await Promise.all([
    loadReports(),
    loadMinutes(),
    loadCachedSummary(),
  ])
})

async function loadCachedSummary() {
  try {
    const { data } = await api.get(`/api/agent/hyean/status-cache/${meetingId.value}`)
    if (data.content) {
      statusSummary.value = data.content
      summaryGeneratedAt.value = data.generated_at
    }
  } catch {}
}

async function loadReports() {
  reportsLoading.value = true
  try {
    const { data } = await api.get(`/api/meetings/${meetingId.value}/reports`)
    // admin: all / others: only own
    reports.value = isAdmin.value
      ? data
      : data.filter(r => r.user_id === auth.user?.id)
  } catch { reports.value = [] } finally { reportsLoading.value = false }
}

async function loadMinutes() {
  minutesLoading.value = true
  try {
    const { data } = await api.get(`/api/meetings/${meetingId.value}/minutes`)
    // minutes: admin sees all, others see all (minutes are meeting-level)
    // But if there's a meeting-level filter need: filter by uploader
    minutes.value = data
  } catch { minutes.value = [] } finally { minutesLoading.value = false }
}

async function loadSummary() {
  summaryLoading.value = true
  statusSummary.value = ''
  try {
    await streamPost(
      '/api/agent/hyean/status',
      { meeting_id: meetingId.value, user_role: role.value || 'presenter' },
      (chunk) => { statusSummary.value += chunk },
      async () => {
        summaryLoading.value = false
        // 생성 완료 후 DB 저장
        if (statusSummary.value.trim()) {
          try {
            await api.post(`/api/agent/hyean/status-cache/${meetingId.value}`, { content: statusSummary.value })
            summaryGeneratedAt.value = new Date().toISOString()
          } catch {}
        }
      }
    )
  } catch { summaryLoading.value = false }
}

async function loadDoc() {
  memLoading.value = true
  try {
    const { data } = await api.get(`/api/tacit-knowledge/activity/${meetingId.value}`)
    memDoc.value = data
  } catch { /* silent */ } finally { memLoading.value = false }
}

async function openMemory() {
  showMemoryPopup.value = true
  await loadDoc()
}

function startMemEdit() {
  memEditBuf.value = memDoc.value.content
  memEditing.value = true
}
function cancelMemEdit() {
  memEditing.value = false
  memEditBuf.value = ''
}
async function saveMemEdit() {
  memSaving.value = true
  try {
    await api.patch(`/api/tacit-knowledge/activity/${meetingId.value}`, { content: memEditBuf.value })
    memDoc.value.content = memEditBuf.value
    memDoc.value.updated_at = new Date().toISOString()
    memEditing.value = false
  } finally { memSaving.value = false }
}

function exportMemMarkdown() {
  const title = meeting.value?.title || '회의체'
  const filename = `${title}_운영메모리.md`
  const header = `# ${title} — 회의체 운영 메모리\n> 마지막 수정: ${formatMemDate(memDoc.value.updated_at)}\n\n`
  const blob = new Blob([header + (memDoc.value.content || '')], { type: 'text/markdown;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url; a.download = filename; a.click()
  URL.revokeObjectURL(url)
}

function formatMemDate(d) {
  if (!d) return '—'
  return new Date(d).toLocaleString('ko-KR', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
}

// ── 편집 저장 ──────────────────────────────────────────────────
function startEditTitle() {
  titleDraft.value = meeting.value?.title || ''
  editingTitle.value = true
}
async function saveTitle() {
  saving.value = true
  try {
    await meetingsStore.updateTitle(meetingId.value, titleDraft.value.trim())
    editingTitle.value = false
  } finally { saving.value = false }
}

function startEditPurpose() {
  purposeDraft.value = meeting.value?.purpose || ''
  editingPurpose.value = true
}
async function savePurpose() {
  saving.value = true
  try {
    await api.patch(`/api/meetings/${meetingId.value}`, { purpose: purposeDraft.value.trim() })
    await meetingsStore.fetchMeeting(meetingId.value)
    editingPurpose.value = false
  } finally { saving.value = false }
}

function startEditDates() {
  startDraft.value = meeting.value?.start_date?.slice(0, 10) || ''
  endDraft.value = meeting.value?.end_date?.slice(0, 10) || ''
  editingDates.value = true
}
async function saveDates() {
  saving.value = true
  try {
    await api.patch(`/api/meetings/${meetingId.value}`, {
      start_date: startDraft.value || null,
      end_date: endDraft.value || null,
    })
    await meetingsStore.fetchMeeting(meetingId.value)
    editingDates.value = false
  } finally { saving.value = false }
}

async function searchMemberCandidates() {
  if (!memberSearch.value.trim()) { memberSearchResults.value = []; return }
  const { data } = await api.get(`/api/users/search?q=${memberSearch.value}`)
  memberSearchResults.value = data.filter(u =>
    u.id !== auth.user?.id && !members.value.find(m => m.user?.id === u.id)
  )
}
async function addMember(u) {
  await meetingsStore.addMember(meetingId.value, u.id, 'presenter')
  members.value = meetingsStore.currentMembers
  memberSearch.value = ''
  memberSearchResults.value = []
}
async function removeMember(memberId) {
  if (!confirm('이 구성원을 제거하시겠습니까?')) return
  await meetingsStore.removeMember(meetingId.value, memberId)
  members.value = meetingsStore.currentMembers
}
async function changeMemberRole(memberId, newRole) {
  await meetingsStore.updateMemberRole(meetingId.value, memberId, newRole)
  members.value = meetingsStore.currentMembers
}

function openUrl(url) {
  if (!url) return
  if (!/^https?:\/\//i.test(url)) return
  const a = document.createElement('a')
  a.href = url; a.target = '_blank'; a.rel = 'noopener noreferrer'; a.click()
}

function downloadReport(report) {
  openUrl(report.file_url)
}
function downloadMinutes(min) {
  openUrl(min.download_url || min.file_url)
}
</script>

<template>
  <div class="home-page">

    <MeetingNav />

    <!-- ══ 상단 정보 ══ -->
    <div class="card top-card">
      <!-- 1행: 회의체명 + 운영 메모리 + 기간 -->
      <div class="top-row">

        <!-- 회의체명 -->
        <div class="info-block title-block">
          <div v-if="!editingTitle" class="info-view">
            <span class="meeting-title-text">{{ meeting?.title || '(회의체명 없음)' }}</span>
            <button v-if="isAdmin" class="icon-btn" @click="startEditTitle" title="편집">✏️</button>
          </div>
          <div v-else class="info-edit">
            <input v-model="titleDraft" class="form-input inline-input" />
            <button class="btn btn-primary btn-xs" :disabled="saving" @click="saveTitle">저장</button>
            <button class="btn btn-ghost btn-xs" @click="editingTitle=false">취소</button>
          </div>
        </div>

        <!-- 운영 메모리 (관리자만) -->
        <div v-if="isAdmin" class="info-block memory-block">
          <button class="mem-trigger-btn" @click="openMemory">
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><ellipse cx="12" cy="5" rx="9" ry="3"/><path d="M3 5v6c0 1.66 4.03 3 9 3s9-1.34 9-3V5"/><path d="M3 11v6c0 1.66 4.03 3 9 3s9-1.34 9-3v-6"/></svg>
            메모리 관리
          </button>
        </div>

        <!-- 기간 & 남은 기간 -->
        <div class="info-block dates-block">
          <div v-if="!editingDates" class="info-view">
            <div class="dates-text">
              <span class="date-range">
                {{ formatDate(meeting?.start_date) }} ~ {{ formatDate(meeting?.end_date) }}
              </span>
              <span v-if="remainingDays !== null" class="remaining-chip" :class="remainingDays <= 7 ? 'urgent' : ''">
                {{ remainingDays > 0 ? `D-${remainingDays}` : remainingDays === 0 ? 'D-Day' : `D+${Math.abs(remainingDays)}` }}
              </span>
            </div>
            <button v-if="isAdmin" class="icon-btn" @click="startEditDates" title="편집">✏️</button>
          </div>
          <div v-else class="info-edit dates-edit">
            <input type="date" v-model="startDraft" class="form-input inline-input" style="width:140px" />
            <span>~</span>
            <input type="date" v-model="endDraft" class="form-input inline-input" style="width:140px" />
            <button class="btn btn-primary btn-xs" :disabled="saving" @click="saveDates">저장</button>
            <button class="btn btn-ghost btn-xs" @click="editingDates=false">취소</button>
          </div>
        </div>
      </div>

      <!-- 2행: 회의체 목적 + 구성원 리스트 -->
      <div class="mid-row">

        <!-- 회의체 목적 -->
        <div class="purpose-block">
          <div class="block-label">
            회의체 목적
            <button v-if="isAdmin && !editingPurpose" class="icon-btn" @click="startEditPurpose" title="편집">✏️</button>
          </div>
          <div v-if="!editingPurpose" class="purpose-text">
            {{ meeting?.purpose || '(목적이 설정되지 않았습니다)' }}
          </div>
          <div v-else>
            <textarea v-model="purposeDraft" class="form-input" rows="3" style="width:100%;resize:vertical"></textarea>
            <div style="display:flex;gap:6px;margin-top:6px">
              <button class="btn btn-primary btn-xs" :disabled="saving" @click="savePurpose">저장</button>
              <button class="btn btn-ghost btn-xs" @click="editingPurpose=false">취소</button>
            </div>
          </div>
        </div>

        <!-- 구성원 리스트 -->
        <div class="members-block">
          <div class="block-label">
            구성원 리스트
            <button v-if="isAdmin && !editingMembers" class="icon-btn" @click="editingMembers=true" title="편집">✏️</button>
            <button v-if="editingMembers" class="btn btn-ghost btn-xs" @click="editingMembers=false">완료</button>
          </div>
          <div v-if="editingMembers" class="member-search-bar">
            <input v-model="memberSearch" class="form-input inline-input" placeholder="구성원 검색..." @input="searchMemberCandidates" />
            <div v-if="memberSearchResults.length" class="member-dropdown">
              <div v-for="u in memberSearchResults" :key="u.id" class="member-drop-item" @click="addMember(u)">
                {{ u.name }} ({{ u.department }})
              </div>
            </div>
          </div>
          <div class="members-list">
            <div v-for="m in members" :key="m.id" class="member-row">
              <div class="member-avatar">{{ m.user?.name?.[0] || '?' }}</div>
              <div class="member-info">
                <div class="member-name">{{ m.user?.name }}</div>
                <div class="member-dept">{{ m.user?.department }}</div>
              </div>
              <div v-if="editingMembers && isAdmin" class="member-actions">
                <select :value="m.role" @change="changeMemberRole(m.id, $event.target.value)" class="role-select">
                  <option value="admin">관리자</option>
                  <option value="presenter">발제자</option>
                </select>
                <button class="icon-btn danger" @click="removeMember(m.id)" title="제거">✕</button>
              </div>
              <span v-else class="role-badge" :class="m.role === 'admin' ? 'badge-primary' : 'badge-muted'">
                {{ m.role === 'admin' ? '관리자' : '발제자' }}
              </span>
            </div>
            <div v-if="!members.length" class="empty-members">구성원이 없습니다.</div>
          </div>
        </div>
      </div>
    </div>

    <!-- ══ 현황 요약 (Hyean) ══ -->
    <div class="card summary-card">
      <div class="summary-header">
        <div class="summary-agent-info">
          <img :src="hyeanAvatar" class="summary-agent-avatar" alt="혜안" />
          <div>
            <div class="summary-agent-name">혜안 <span class="summary-agent-en">(Hyean)</span></div>
            <div class="summary-agent-sub">회의체 운영 AI 비서 · 현황 분석</div>
          </div>
        </div>
        <div class="summary-header-right">
          <span v-if="summaryGeneratedAt" class="summary-ts">
            {{ new Date(summaryGeneratedAt).toLocaleString('ko-KR', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }) }} 생성
          </span>
          <button class="btn btn-ghost btn-xs" @click="loadSummary" :disabled="summaryLoading">
            {{ summaryLoading ? '분석 중...' : summaryGeneratedAt ? '재생성' : '현황 분석하기' }}
          </button>
        </div>
      </div>
      <div v-if="summaryLoading && !statusSummary" class="summary-loading">
        <span class="dot-anim">●</span>
        <span class="dot-anim" style="animation-delay:.2s">●</span>
        <span class="dot-anim" style="animation-delay:.4s">●</span>
        혜안이 현황을 분석 중입니다...
      </div>
      <div v-else-if="statusSummary" class="summary-content" v-html="renderMd(statusSummary)"></div>
      <div v-else class="empty-state" style="padding:20px">
        <button class="btn btn-primary btn-sm" @click="loadSummary">현황 분석하기</button>
      </div>
    </div>

    <!-- ══ 하단 2열: 보고서 + 회의록 ══ -->
    <div class="bottom-grid">

      <!-- 보고서 리스트 -->
      <div class="card list-card">
        <div class="block-label" style="margin-bottom:12px">📊 보고서 리스트</div>
        <div v-if="reportsLoading" class="empty-state">불러오는 중...</div>
        <div v-else-if="!reports.length" class="empty-state">보고서가 없습니다.</div>
        <div v-else class="table-wrap">
          <table class="data-table">
            <thead>
              <tr>
                <th>보고서명</th>
                <th>작성자</th>
                <th>부서명</th>
                <th>회사명</th>
                <th>업로드일</th>
                <th>상태</th>
                <th>다운로드</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="r in reports" :key="r.id" class="table-row">
                <td class="td-name">{{ r.file_name || r.title || '-' }}</td>
                <td>{{ r.presenter_name || r.user_name || '-' }}</td>
                <td>{{ r.department || '-' }}</td>
                <td>{{ r.company || '-' }}</td>
                <td>{{ formatDate(r.uploaded_at || r.created_at) }}</td>
                <td>
                  <span class="badge" :class="reportStatusCls[r.status] || 'badge-muted'">
                    {{ reportStatusMap[r.status] || r.status }}
                  </span>
                </td>
                <td>
                  <button
                    v-if="r.file_url"
                    class="icon-btn download-btn"
                    @click="downloadReport(r)"
                    title="다운로드"
                  >⬇</button>
                  <span v-else class="text-muted">-</span>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <!-- 회의록 리스트 -->
      <div class="card list-card">
        <div class="block-label" style="margin-bottom:12px">📋 회의록 리스트</div>
        <div v-if="minutesLoading" class="empty-state">불러오는 중...</div>
        <div v-else-if="!minutes.length" class="empty-state">회의록이 없습니다.</div>
        <div v-else class="table-wrap">
          <table class="data-table">
            <thead>
              <tr>
                <th>회의명</th>
                <th>회의 날짜</th>
                <th>다운로드</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="m in minutes" :key="m.minutes_id || m.id" class="table-row">
                <td class="td-name">
                  {{ m.session_title || `${m.session_number}차 회의` }}
                </td>
                <td>{{ formatDate(m.ended_at || m.session_date) }}</td>
                <td>
                  <button
                    v-if="m.download_url || m.file_url"
                    class="icon-btn download-btn"
                    @click="downloadMinutes(m)"
                    title="다운로드"
                  >⬇</button>
                  <span v-else class="text-muted">-</span>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>

    <!-- ══ 운영 메모리 팝업 (관리자 전용) ══ -->
    <BaseModal v-model="showMemoryPopup" width="min(700px, 95vw)">
      <template #title>
        <span>회의체 운영 메모리</span>
        <span v-if="memDoc.updated_at" class="mem-date-label">{{ formatMemDate(memDoc.updated_at) }}</span>
      </template>
      <template #header-actions>
        <button v-if="isAdmin" class="mem-edit-btn" @click="startMemEdit" :disabled="memEditing">✏️ 수정</button>
        <button class="mem-export-btn" @click="exportMemMarkdown">⬇ 내보내기</button>
      </template>

      <div class="mem-popup-body">
        <div v-if="memLoading" class="mem-empty">불러오는 중...</div>

        <div v-else-if="memEditing" class="mem-editor-wrap">
          <textarea v-model="memEditBuf" class="mem-editor" placeholder="회의체 운영 메모리를 마크다운으로 작성하세요..." />
          <div class="mem-editor-actions">
            <button class="btn btn-primary btn-sm" :disabled="memSaving" @click="saveMemEdit">
              {{ memSaving ? '저장 중...' : '저장' }}
            </button>
            <button class="btn btn-ghost btn-sm" @click="cancelMemEdit">취소</button>
          </div>
        </div>

        <div v-else-if="!memDoc.content?.trim()" class="mem-empty">
          <div style="font-size:32px;margin-bottom:10px">📋</div>
          <div style="font-weight:600;margin-bottom:6px">아직 기록된 활동이 없습니다</div>
          <div style="font-size:12px;color:var(--text-muted);line-height:1.7">
            에이전트(가온·나루·아라·나온·혜안)를 사용하면<br>활동이 자동으로 기록됩니다.
          </div>
        </div>

        <div v-else class="mem-doc">
          <pre class="mem-pre">{{ memDoc.content }}</pre>
        </div>
      </div>
    </BaseModal>
  </div>
</template>

<style scoped>
.home-page {
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding: 0 0 24px;
}

/* ── 카드 공통 ── */
.card {
  background: #fff;
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  padding: 20px 24px;
  box-shadow: var(--shadow);
}

/* ── 상단 카드 ── */
.top-row {
  display: flex;
  align-items: flex-start;
  gap: 16px;
  flex-wrap: wrap;
  margin-bottom: 20px;
  padding-bottom: 20px;
  border-bottom: 1px solid var(--border);
}
.title-block { flex: 1; min-width: 200px; }
.memory-block { flex-shrink: 0; }
.dates-block { flex-shrink: 0; min-width: 260px; }

.info-view {
  display: flex;
  align-items: center;
  gap: 8px;
}
.info-edit {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}
.dates-edit { gap: 8px; }

.meeting-title-text {
  font-size: 22px;
  font-weight: 700;
  color: #111827;
  line-height: 1.3;
}
.dates-text {
  display: flex;
  align-items: center;
  gap: 8px;
}
.date-range {
  font-size: 14px;
  color: var(--text-muted);
}
.remaining-chip {
  font-size: 12px;
  font-weight: 700;
  padding: 2px 10px;
  border-radius: 99px;
  background: #dbeafe;
  color: #1d4ed8;
}
.remaining-chip.urgent {
  background: #fee2e2;
  color: #dc2626;
}

/* 운영 메모리 버튼 */
.mem-trigger-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  background: #fff;
  border: 1px solid #d1d5db;
  color: #374151;
  border-radius: 8px;
  padding: 6px 13px;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: background .15s, border-color .15s, color .15s, box-shadow .15s;
  box-shadow: 0 1px 2px rgba(0,0,0,.05);
}
.mem-trigger-btn:hover {
  background: #f5f3ff;
  border-color: #a78bfa;
  color: #6d28d9;
  box-shadow: 0 1px 4px rgba(109,40,217,.12);
}

/* ── 중간: 목적 + 구성원 ── */
.mid-row {
  display: flex;
  gap: 20px;
  align-items: flex-start;
}
.purpose-block {
  flex: 1;
  min-width: 0;
}
.members-block {
  width: 240px;
  flex-shrink: 0;
  border-left: 1px solid var(--border);
  padding-left: 20px;
}

.block-label {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  font-weight: 700;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: .04em;
  margin-bottom: 8px;
}
.purpose-text {
  font-size: 14px;
  color: #374151;
  line-height: 1.7;
  white-space: pre-wrap;
  min-height: 60px;
}

/* 구성원 */
.member-search-bar { position: relative; margin-bottom: 10px; }
.member-dropdown {
  position: absolute;
  top: 100%;
  left: 0;
  right: 0;
  background: #fff;
  border: 1px solid var(--border);
  border-radius: 6px;
  z-index: 10;
  box-shadow: var(--shadow);
  max-height: 160px;
  overflow-y: auto;
}
.member-drop-item {
  padding: 8px 12px;
  font-size: 13px;
  cursor: pointer;
}
.member-drop-item:hover { background: #f1f5f9; }
.members-list { display: flex; flex-direction: column; gap: 8px; }
.member-row {
  display: flex;
  align-items: center;
  gap: 8px;
}
.member-avatar {
  width: 30px;
  height: 30px;
  border-radius: 50%;
  background: var(--primary);
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 13px;
  font-weight: 700;
  flex-shrink: 0;
}
.member-info { flex: 1; min-width: 0; }
.member-name { font-size: 13px; font-weight: 600; color: #111827; }
.member-dept { font-size: 11px; color: var(--text-muted); }
.member-actions { display: flex; align-items: center; gap: 4px; }
.role-select {
  font-size: 11px;
  padding: 2px 6px;
  border: 1px solid var(--border);
  border-radius: 4px;
}
.role-badge {
  font-size: 10px;
  padding: 2px 6px;
  border-radius: 99px;
  font-weight: 600;
}
.empty-members { font-size: 12px; color: var(--text-muted); padding: 8px 0; }

/* ── 요약 카드 ── */
.summary-card { padding: 16px 24px; }
.summary-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 14px;
  padding-bottom: 12px;
  border-bottom: 1px solid var(--border);
  flex-wrap: wrap;
}
.summary-agent-info {
  display: flex;
  align-items: center;
  gap: 10px;
}
.summary-agent-avatar {
  width: 38px; height: 38px;
  border-radius: 50%;
  object-fit: cover;
  border: 2px solid #c4b5fd;
  box-shadow: 0 0 0 3px #f3e8ff;
  flex-shrink: 0;
}
.summary-agent-name {
  font-weight: 700;
  font-size: 14px;
  color: var(--text);
}
.summary-agent-en { font-weight: 400; font-size: 12px; color: var(--text-muted); }
.summary-agent-sub { font-size: 11px; color: var(--text-muted); margin-top: 1px; }
.summary-header-right {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-left: auto;
  flex-shrink: 0;
}
.summary-ts {
  font-size: 11px;
  color: var(--text-muted);
  font-weight: 400;
}
.summary-loading {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  color: #6d28d9;
  padding: 12px 0;
}
.summary-content {
  font-size: 14px;
  line-height: 1.8;
  color: #374151;
}
.summary-content :deep(p)            { margin: 0 0 8px; }
.summary-content :deep(p:last-child) { margin-bottom: 0; }
.summary-content :deep(ul),
.summary-content :deep(ol)           { margin: 0 0 8px; padding-left: 20px; }
.summary-content :deep(li)           { margin-bottom: 3px; }
.summary-content :deep(h1),
.summary-content :deep(h2),
.summary-content :deep(h3),
.summary-content :deep(h4)           { font-weight: 700; margin: 14px 0 6px; line-height: 1.3; color: #1e293b; }
.summary-content :deep(h1)           { font-size: 18px; }
.summary-content :deep(h2)           { font-size: 16px; border-bottom: 1px solid var(--border); padding-bottom: 4px; }
.summary-content :deep(h3)           { font-size: 14px; color: #6d28d9; }
.summary-content :deep(h4)           { font-size: 13px; }
.summary-content :deep(strong)       { font-weight: 700; color: #111827; }
.summary-content :deep(em)           { font-style: italic; color: #4b5563; }
.summary-content :deep(code)         { background: #f1f5f9; padding: 1px 5px; border-radius: 4px; font-size: 12px; font-family: monospace; }
.summary-content :deep(pre)          { background: #1e293b; color: #e2e8f0; padding: 12px 14px; border-radius: 8px; overflow-x: auto; margin: 8px 0; font-size: 12px; }
.summary-content :deep(pre code)     { background: none; padding: 0; }
.summary-content :deep(blockquote)   { border-left: 3px solid #a78bfa; padding-left: 12px; color: #6b7280; margin: 8px 0; font-style: italic; }
.summary-content :deep(hr)           { border: none; border-top: 1px solid var(--border); margin: 12px 0; }
.summary-content :deep(table)        { border-collapse: collapse; width: 100%; margin: 8px 0; font-size: 13px; }
.summary-content :deep(th),
.summary-content :deep(td)           { border: 1px solid var(--border); padding: 6px 10px; text-align: left; }
.summary-content :deep(th)           { background: #f8fafc; font-weight: 600; }

/* ── 하단 2열 ── */
.bottom-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
}
.list-card {}

.table-wrap { overflow-x: auto; }
.data-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}
.data-table th {
  text-align: left;
  padding: 8px 10px;
  font-size: 11px;
  font-weight: 700;
  color: var(--text-muted);
  border-bottom: 1px solid var(--border);
  white-space: nowrap;
}
.data-table td {
  padding: 9px 10px;
  border-bottom: 1px solid #f1f5f9;
  color: #374151;
  vertical-align: middle;
}
.table-row:hover td { background: #f8fafc; }
.td-name {
  max-width: 160px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-weight: 500;
  color: #111827;
}
.download-btn {
  font-size: 15px;
  color: var(--primary);
}
.text-muted { color: var(--text-muted); }

/* ── 공통 아이콘 버튼 ── */
.icon-btn {
  background: none;
  border: none;
  cursor: pointer;
  font-size: 13px;
  padding: 2px 5px;
  border-radius: 4px;
  opacity: .55;
  transition: opacity .15s;
  line-height: 1;
}
.icon-btn:hover { opacity: 1; }
.icon-btn.danger:hover { color: #dc2626; }

.inline-input { height: 32px; padding: 0 8px; }
.btn-xs { padding: 3px 8px; font-size: 12px; height: auto; }
.btn-danger {
  background: #dc2626;
  color: #fff;
  border: none;
  border-radius: 6px;
  padding: 4px 10px;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
}
.btn-danger:hover:not(:disabled) { background: #b91c1c; }
.btn-danger:disabled { opacity: .6; cursor: not-allowed; }

/* ── 활동 기록 팝업 ── */
/* ── 운영 메모리 팝업 전용 ── */
.mem-date-label { font-size: 11px; color: var(--text-muted); font-weight: 400; }

.mem-edit-btn {
  background: #f8fafc; color: var(--text); border: 1.5px solid var(--border);
  border-radius: 6px; padding: 5px 11px; font-size: 12px; font-weight: 500;
  cursor: pointer; transition: background .15s;
}
.mem-edit-btn:hover:not(:disabled) { background: #e2e8f0; }
.mem-edit-btn:disabled { opacity: .5; cursor: not-allowed; }

.mem-export-btn {
  background: #f8fafc; color: var(--text); border: 1.5px solid var(--border);
  border-radius: 6px; padding: 5px 11px; font-size: 12px; font-weight: 500;
  cursor: pointer; transition: background .15s;
}
.mem-export-btn:hover { background: #e2e8f0; }

.mem-popup-body {
  padding: 16px; display: flex; flex-direction: column; min-height: 0;
}
.mem-empty {
  text-align: center; padding: 40px 20px; color: var(--text-muted);
  font-size: 13px; flex: 1;
}
.mem-editor-wrap { display: flex; flex-direction: column; gap: 10px; flex: 1; }
.mem-editor {
  flex: 1; min-height: 320px; border: 1.5px solid var(--border); border-radius: 8px;
  padding: 12px; font-size: 13px; font-family: 'Pretendard', monospace; line-height: 1.7;
  resize: none; outline: none; color: var(--text);
}
.mem-editor:focus { border-color: #94a3b8; box-shadow: 0 0 0 3px #f1f5f9; }
.mem-editor-actions { display: flex; gap: 8px; }
.mem-doc { flex: 1; }
.mem-pre {
  white-space: pre-wrap; word-break: break-word;
  font-size: 13px; font-family: 'Pretendard', sans-serif; line-height: 1.8;
  color: var(--text); margin: 0;
}

/* 공통 애니메이션 */
.dot-anim { font-size: 8px; color: #7c3aed; animation: blink 1s infinite; }
@keyframes blink { 0%,80%,100%{opacity:.2} 40%{opacity:1} }
.spin { display: inline-block; animation: spin 1s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }

/* 배지 */
.badge { font-size: 11px; padding: 2px 8px; border-radius: 99px; font-weight: 600; }
.badge-muted { background: #f1f5f9; color: #64748b; }
.badge-warn { background: #fef9c3; color: #854d0e; }
.badge-success { background: #dcfce7; color: #166534; }
.badge-danger { background: #fee2e2; color: #dc2626; }
.badge-primary { background: #dbeafe; color: #1d4ed8; }
</style>
