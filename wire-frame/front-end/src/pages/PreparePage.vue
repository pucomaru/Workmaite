<script setup>
import { ref, onMounted, computed, nextTick } from 'vue'
import { useRoute } from 'vue-router'
import api, { streamPost } from '../api'
import MeetingNav from '../components/MeetingNav.vue'
import AgentPanel from '../components/AgentPanel.vue'
import { useMeetingsStore } from '../stores/meetings'
import { useAuthStore } from '../stores/auth'
import { useChatHistory } from '../composables/useChatHistory'
import naruAvatar from '../assets/agents/naru.png'
import { renderMd } from '../composables/useMarkdown'
import BaseModal from '../components/BaseModal.vue'

const route = useRoute()
const meetingsStore = useMeetingsStore()
const authStore = useAuthStore()
const meetingId = computed(() => Number(route.params.meetingId))
const role = computed(() => meetingsStore.myRole)
const currentUser = computed(() => authStore.user)

// ─── 탭 상태 ───────────────────────────────────────────────
const activeTab = ref('review') // 'review' | 'status'

// ─── 채팅 ──────────────────────────────────────────────────
const { messages, loadMessages, saveMessage, clearHistory } = useChatHistory('prepare', meetingId.value)
const loading = ref(false)
const agentPanelRef = ref(null)
const pendingFiles = ref([]) // 쳊부된 파일들 (전송 전)

// ─── 검토 탭 ── 로컬 리뷰 파일 목록 (세션 내 업로드) ───────
const reviewFiles = ref([]) // { fileName, score, feedback, element_scores, reportId, submitting, submitted }
const uploadingFile = ref(false)

// ─── 아젠다 스코프 ───────────────────────────────────────
const agendas = ref([])
const selectedAgendaId = ref(null) // null = 전체

const AGENDA_TYPE_LABEL = { report: '보고', discussion: '토의', decision: '결정', info: '정보공유' }
const AGENDA_TYPE_COLOR = { report: '#3b82f6', discussion: '#f59e0b', decision: '#8b5cf6', info: '#10b981' }

const selectedAgenda = computed(() => agendas.value.find(a => a.id === selectedAgendaId.value) ?? null)

// ─── 제출현황 탭 ── 전체 보고서 목록 ────────────────────────
const allReports = ref([])
const loadingReports = ref(false)
const expandedReviewId = ref(null) // 요소별 점수 패널 열린 report id

// 상태 변경 모달
const showActionModal = ref(false)
const actionTarget = ref(null)  // { report, newStatus }
const actionComment = ref('')
const actionSubmitting = ref(false)
const notifyTeams = ref(false)

// ─── 역할별 빠른 질문 & 인사말 ─────────────────────────────
const quickQuestions = computed(() => {
  if (role.value === 'admin') {
    return [
      '전체 보고서 종합 평가해줘',
      '기준 미달 보고서 알려줘',
      '가장 우수한 발제자료는?',
      '개선 필요한 발제자료 요약해줘',
    ]
  }
  return [
    '내 보고서 검토 기준 알려줘',
    '점수를 높이려면 어떻게 해야 해?',
    '발제자료 작성 팁 알려줘',
    '운영 기준에 맞는 보고서 구성 알려줘',
  ]
})

// ─── onMounted ─────────────────────────────────────────────
onMounted(async () => {
  await meetingsStore.fetchMeeting(meetingId.value)
  await meetingsStore.fetchRole(meetingId.value)
  await loadMessages()
  await Promise.all([
    loadAllReports(),
    api.get(`/api/meetings/${meetingId.value}/agendas`).then(({ data }) => {
      const myId = currentUser.value?.id
      const myDept = currentUser.value?.department
      agendas.value = data.filter(a => {
        if (a.agenda_type !== 'scheduled') return false
        if (role.value === 'admin') return true
        if (!a.department) return true
        return a.presenter_id === myId || (myDept && a.department === myDept)
      })
    }).catch(() => {}),
  ])
})

// ─── 채팅 메시지 전송 ─────────────────────────────────────
async function handleSend(text) {
  // 파일이 첨부된 경우 → 파일 업로드 + AI 검토
  if (pendingFiles.value.length) {
    const files = [...pendingFiles.value]
    pendingFiles.value = []
    await uploadAndReview(files, text.trim())
    return
  }
  if (!text.trim() || loading.value) return
  messages.value.push({ role: 'user', content: text })
  saveMessage('user', text)
  loading.value = true

  const agentMsg = { role: 'agent', content: '' }
  messages.value.push(agentMsg)

  try {
    await streamPost(
      '/api/agent/naru/chat',
      {
        message: text,
        meeting_id: meetingId.value,
        agenda_id: selectedAgendaId.value ?? undefined,
        chat_history: messages.value
          .slice(-12)
          .filter(m => m.content)
          .map(m => ({
            role: m.role === 'agent' ? 'assistant' : 'user',
            content: m.content,
          })),
      },
      (chunk) => { agentMsg.content += chunk },
    )
    saveMessage('agent', agentMsg.content)
  } catch {
    agentMsg.content = '죄송합니다. 응답 중 오류가 발생했습니다.'
  } finally {
    loading.value = false
  }
}

// ─── 파일 업로드 및 AI 검토 ───────────────────────────────
async function onAddFiles(files) {
  pendingFiles.value.push(...files)
}

async function uploadAndReview(files, extraText = '') {
  uploadingFile.value = true

  const uploadingNames = files.map(f => f.name).join(', ')
  const userMsg = extraText
    ? `📎 ${uploadingNames}\n${extraText}`
    : `📎 파일 업로드: ${uploadingNames}`
  messages.value.push({ role: 'user', content: userMsg })
  saveMessage('user', userMsg)

  const agentMsg = { role: 'agent', content: '파일을 검토하고 있습니다...' }
  messages.value.push(agentMsg)

  try {
    const results = []
    for (const file of files) {
      const form = new FormData()
      form.append('file', file)
      const { data } = await api.post(`/api/meetings/${meetingId.value}/reports/review`, form, {
        headers: { 'Content-Type': 'multipart/form-data' },
      })
      results.push({ file, report: data })
    }

    const lines = results.map(r => {
      const score = r.report.score ?? '-'
      const feedbackList = (r.report.feedback || []).map(f => `  • ${f}`).join('\n')
      return `**${r.file.name}** — 점수: **${score}점**\n${feedbackList}`
    })
    agentMsg.content = `검토가 완료되었습니다!\n\n${lines.join('\n\n')}`
    saveMessage('agent', agentMsg.content)

    for (const r of results) {
      const exists = reviewFiles.value.find(f => f.reportId === r.report.id)
      if (!exists) {
        reviewFiles.value.push({
          fileName: r.file.name,
          score: r.report.score,
          feedback: r.report.feedback || [],
          element_scores: r.report.element_scores || [],
          missing_elements: r.report.missing_elements || [],
          principles: r.report.principles || {},
          reportId: r.report.id,
          agendaId: r.report.agenda_id ?? selectedAgendaId.value ?? null,
          submitting: false,
          submitted: r.report.status === 'submitted',
        })
      }
    }

    activeTab.value = 'review'
    await loadAllReports()
  } catch {
    agentMsg.content = '파일 검토 중 오류가 발생했습니다. 다시 시도해주세요.'
    saveMessage('agent', agentMsg.content)
  } finally {
    uploadingFile.value = false
  }
}

// ─── 검토 파일 취소(삭제) ──────────────────────────────
async function cancelReviewFile(item) {
  if (!confirm(`"${item.fileName}" 발제자료를 취소하시겠습니까?\n검토 내용이 삭제됩니다.`)) return
  try {
    await api.delete(`/api/reports/${item.reportId}`)
  } catch (e) {
    if (e?.response?.status !== 404) {
      alert('삭제 중 오류가 발생했습니다.')
      return
    }
  }
  reviewFiles.value = reviewFiles.value.filter(f => f.reportId !== item.reportId)
  await loadAllReports()
}

// ─── 검토 파일 Admin에 제출 ──────────────────────────────
async function submitReviewFile(item) {
  item.submitting = true
  try {
    await api.post(`/api/meetings/${meetingId.value}/reports/${item.reportId}/submit`, {
      agenda_id: item.agendaId ?? null,
    })
    item.submitted = true
    await loadAllReports()
    const msg = `"${item.fileName}"을 제출했습니다. 관리자 승인을 기다려주세요.`
    messages.value.push({ role: 'agent', content: msg })
    saveMessage('agent', msg)
  } catch {
    messages.value.push({ role: 'agent', content: '제출 중 오류가 발생했습니다.' })
  } finally {
    item.submitting = false
  }
}

// ─── 제출현황 보고서 삭제 ────────────────────────────────
async function deleteReport(rpt) {
  const label = rpt.file_name || '보고서'
  if (!confirm(`"${label}"을 삭제하시겠습니까?`)) return
  try {
    await api.delete(`/api/reports/${rpt.id}`)
  } catch (e) {
    if (e?.response?.status !== 404) {
      alert(e?.response?.data?.detail || '삭제 중 오류가 발생했습니다.')
      return
    }
  }
  await loadAllReports()
}

// ─── 제출현황 로드 ────────────────────────────────────────
async function loadAllReports() {
  loadingReports.value = true
  try {
    const { data } = await api.get(`/api/meetings/${meetingId.value}/reports`)
    allReports.value = data
  } catch {
    // silent
  } finally {
    loadingReports.value = false
  }
}

// ─── 제출현황 탭: 역할별 + 아젠다 필터 ──────────────────
const filteredReports = computed(() => {
  let list = allReports.value
  if (role.value !== 'admin') {
    const myId = currentUser.value?.id
    const myDept = currentUser.value?.department
    list = list.filter(r => {
      const presenterDept = r.presenter?.department
      return r.presenter_id === myId || (myDept && presenterDept === myDept)
    })
  }
  if (selectedAgendaId.value) {
    list = list.filter(r => r.agenda_id === selectedAgendaId.value)
  }
  return list
})

// ─── 검토 탭: 아젠다 필터 ────────────────────────────────
const filteredReviewFiles = computed(() => {
  if (!selectedAgendaId.value) return reviewFiles.value
  return reviewFiles.value.filter(f => f.agendaId === selectedAgendaId.value)
})

// ─── AI 검토 점수 클릭 → 요소별 패널 토글 ──────────────────
function toggleReviewPanel(reportId) {
  expandedReviewId.value = expandedReviewId.value === reportId ? null : reportId
}

async function showAiReason(report) {
  toggleReviewPanel(report.id)
}

function elementScoreColor(score) {
  if (score >= 80) return '#16a34a'
  if (score >= 50) return '#d97706'
  return '#dc2626'
}
function principleLabel(key) {
  const map = {
    so_what: 'So What?',
    one_page_one_message: '1P 1Message',
    data_based: '데이터 기반',
    decision_focused: '의사결정 중심',
    concise: '간결함',
  }
  return map[key] || key
}

// ─── 상태 변경 모달 ──────────────────────────────────────
function openActionModal(report) {
  actionTarget.value = { report, newStatus: report.status }
  actionComment.value = report.review_comment || ''
  notifyTeams.value = false
  showActionModal.value = true
}

async function submitAction() {
  if (!actionTarget.value) return
  actionSubmitting.value = true
  try {
    await api.patch(`/api/reports/${actionTarget.value.report.id}/status`, {
      status: actionTarget.value.newStatus,
      comment: actionComment.value || null,
      notify_teams: notifyTeams.value,
    })
    showActionModal.value = false
    await loadAllReports()
  } catch {
    // silent
  } finally {
    actionSubmitting.value = false
  }
}

// ─── 아젠다 표시 헬퍼 ─────────────────────────────────────
function agendaLabel(agendaId) {
  if (!agendaId) return null
  const a = agendas.value.find(a => a.id === agendaId)
  if (!a) return null
  const text = a.content || a.title || ''
  return text.length > 20 ? text.slice(0, 20) + '…' : text
}

// ─── 상태 표시 헬퍼 ──────────────────────────────────────
const statusLabel = {
  draft: '검토전',
  submitted: '검토중',
  approved: '승인',
  rejected: '반려',
}
const statusClass = {
  draft: 'status-draft',
  submitted: 'status-submitted',
  approved: 'status-approved',
  rejected: 'status-rejected',
}
function formatDate(dt) {
  if (!dt) return '-'
  return new Date(dt).toLocaleDateString('ko-KR', { month: '2-digit', day: '2-digit', year: '2-digit' })
}
</script>

<template>
  <div class="prepare-page">
    <MeetingNav />

    <div class="agent-body">
      <!-- 왼쪽: 나루 Agent 패널 -->
      <AgentPanel
        ref="agentPanelRef"
        :messages="messages"
        :loading="loading"
        :avatar="naruAvatar"
        name="나루"
        name-en="Naru"
        subtitle="발제자료 검토 AI"
        :quickQuestions="quickQuestions"
        :greeting="role === 'admin' ? '안녕하세요! 저는 회의준비 검토를 도와드리는 나루입니다. 발제자료를 업로드하거나 제출된 보고서를 함께 검토해봐요.' : '안녕하세요! 저는 발제자료 검토 AI 나루입니다. 자료를 업로드하면 회의체 운영 기준을 바탕으로 점수와 피드백을 드립니다.'"
        accent-color="#3b82f6"
        accent-border="#60a5fa"
        accent-bg="#eff6ff"
        bubble-gradient="linear-gradient(135deg,#eff6ff,#dbeafe)"
        bubble-color="#1e40af"
        @send="handleSend"
        @clear="clearHistory"
        :pending-files="pendingFiles.map(f => ({ name: f.name }))"
        @remove-file="(i) => pendingFiles.splice(i, 1)"
        @add-files="onAddFiles"
      >
        <template #overlay>
          <div v-if="uploadingFile" class="drag-overlay">
            <div class="drag-hint"><span class="spinner-sm spinner-dark"></span> 파일 검토 중...</div>
          </div>
        </template>
      </AgentPanel>

      <!-- 오른쪽 패널 -->
      <div class="prepare-right card">
        <!-- 탭 헤더 -->
        <div class="right-panel-header">
          <button
            class="panel-tab"
            :class="{ active: activeTab === 'review' }"
            @click="activeTab = 'review'"
          >검토</button>
          <button
            class="panel-tab"
            :class="{ active: activeTab === 'status' }"
            @click="activeTab = 'status'"
          >제출현황</button>
          <select class="scope-select" v-model="selectedAgendaId" style="margin-left:auto">
            <option :value="null">전체 아젠다</option>
            <option v-for="a in agendas" :key="a.id" :value="a.id">
              {{ (a.content || a.title || '').slice(0, 28) }}{{ (a.content || a.title || '').length > 28 ? '…' : '' }}
            </option>
          </select>
        </div>

        <div v-if="activeTab === 'review'" class="tab-body">
          <div v-if="filteredReviewFiles.length === 0" class="empty-state">
            <p>아직 검토한 파일이 없어요</p>
            <p class="text-muted">
              {{ selectedAgenda ? `'${(selectedAgenda.content || '').slice(0,15)}' 아젠다의 ` : '' }}발제자료를 왼쪽 채팅창에서 업로드해주세요
            </p>
          </div>
          <div v-else class="review-file-list">
            <div
              v-for="item in filteredReviewFiles"
              :key="item.reportId"
              class="review-file-card"
            >
              <div class="rfc-top">
                <span class="rfc-name">{{ item.fileName }}</span>
                <span class="score-badge" :style="{ background: elementScoreColor(item.score) }">{{ item.score ?? '-' }}점</span>
              </div>
              <div class="rfc-agenda-row">
                <span class="rfc-agenda-label">아젠다</span>
                <select class="rfc-agenda-select" v-model="item.agendaId" :disabled="item.submitted">
                  <option :value="null">-- 선택 안함 --</option>
                  <option v-for="a in agendas" :key="a.id" :value="a.id">
                    {{ a.content || a.title || `아젠다 #${a.id}` }}
                  </option>
                </select>
              </div>

              <!-- 누락 요소 경고 -->
              <div v-if="item.missing_elements?.length" class="missing-alert" style="margin:8px 0 4px">
                ⚠️ 누락: {{ item.missing_elements.join(', ') }}
              </div>

              <!-- 5대 원칙 -->
              <div v-if="item.principles && Object.keys(item.principles).length" class="principles-row" style="margin:6px 0">
                <span
                  v-for="(val, key) in item.principles" :key="key"
                  class="principle-chip"
                  :class="val ? 'principle-ok' : 'principle-fail'"
                >{{ principleLabel(key) }} {{ val ? '✓' : '✗' }}</span>
              </div>

              <!-- 12대 요소 미니 바 -->
              <div v-if="item.element_scores?.length" class="element-mini-bars">
                <div v-for="el in item.element_scores" :key="el.id" class="element-mini-bar" :title="el.name + ': ' + el.comment">
                  <span class="emb-label">{{ el.id }}. {{ el.name.split(' ')[0] }}</span>
                  <div class="emb-track">
                    <div class="emb-fill" :style="{ width: el.score + '%', background: elementScoreColor(el.score) }"></div>
                  </div>
                  <span class="emb-score">{{ el.present ? el.score : 0 }}</span>
                </div>
              </div>

              <ul class="feedback-list" v-if="item.feedback?.length">
                <li v-for="(fb, i) in item.feedback" :key="i">{{ fb }}</li>
              </ul>
              <div class="rfc-actions">
                <span v-if="item.submitted" class="status-chip status-submitted">제출됨</span>
                <template v-else>
                  <button
                    class="btn-submit-to-admin"
                    :disabled="item.submitting"
                    @click="submitReviewFile(item)"
                  >
                    <span v-if="item.submitting" class="spinner-sm"></span>
                    {{ item.submitting ? '제출 중...' : 'Admin에 제출' }}
                  </button>
                  <button
                    class="btn btn-ghost btn-sm"
                    style="color:var(--danger);font-size:12px"
                    :disabled="item.submitting"
                    @click="cancelReviewFile(item)"
                  >취소</button>
                </template>
              </div>
            </div>
          </div>
        </div>

        <!-- ────── 제출현황 탭 ────── -->
        <div v-if="activeTab === 'status'" class="tab-body">
          <div v-if="loadingReports" class="empty-state">
            <span class="spinner-sm spinner-dark"></span> 불러오는 중...
          </div>
          <div v-else-if="filteredReports.length === 0" class="empty-state">
            <p>아직 제출된 보고서가 없어요</p>
          </div>
          <table v-else class="reports-table">
            <thead>
              <tr>
                <th>보고서명</th>
                <th>아젠다</th>
                <th>작성자</th>
                <th>업로드일</th>
                <th>AI검토</th>
                <th>상태</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              <template v-for="rpt in filteredReports" :key="rpt.id">
                <tr :class="{ 'row-expanded': expandedReviewId === rpt.id }">
                  <td class="name-cell">{{ rpt.file_name || '-' }}</td>
                  <td>
                    <span v-if="agendaLabel(rpt.agenda_id)" class="agenda-chip">{{ agendaLabel(rpt.agenda_id) }}</span>
                    <span v-else class="text-muted">-</span>
                  </td>
                  <td>{{ rpt.presenter?.name || '-' }}</td>
                  <td>{{ formatDate(rpt.submitted_at || rpt.created_at) }}</td>
                  <td>
                    <button
                      v-if="rpt.score != null"
                      class="score-btn"
                      :class="{ 'score-btn-active': expandedReviewId === rpt.id }"
                      @click="toggleReviewPanel(rpt.id)"
                      title="클릭하여 12대 필수요소 검토 결과 보기"
                    >{{ rpt.score }}점 ▾</button>
                    <span v-else class="text-muted">-</span>
                  </td>
                  <td>
                    <button
                      v-if="role === 'admin'"
                      :class="['status-chip', 'status-clickable', statusClass[rpt.status]]"
                      @click="openActionModal(rpt)"
                      title="클릭하여 상태 변경"
                    >{{ statusLabel[rpt.status] || rpt.status }}</button>
                    <span v-else :class="['status-chip', statusClass[rpt.status]]">
                      {{ statusLabel[rpt.status] || rpt.status }}
                    </span>
                  </td>
                  <td>
                    <button
                      v-if="role === 'admin' || rpt.status === 'draft'"
                      class="btn btn-ghost btn-sm"
                      style="color:var(--danger);font-size:12px"
                      @click="deleteReport(rpt)"
                    >삭제</button>
                  </td>
                </tr>
                <!-- 요소별 검토 확장 패널 -->
                <tr v-if="expandedReviewId === rpt.id" class="review-expand-row">
                  <td colspan="7">
                    <div class="review-panel">
                      <!-- 헤더: 종합 점수 + 5대 원칙 -->
                      <div class="review-panel-header">
                        <span class="review-total-score" :style="{ color: elementScoreColor(rpt.score) }">
                          종합 {{ rpt.score }}점
                        </span>
                        <div v-if="rpt.principles" class="principles-row">
                          <span
                            v-for="(val, key) in rpt.principles" :key="key"
                            class="principle-chip"
                            :class="val ? 'principle-ok' : 'principle-fail'"
                          >{{ principleLabel(key) }} {{ val ? '✓' : '✗' }}</span>
                        </div>
                      </div>

                      <!-- 누락 요소 경고 -->
                      <div v-if="rpt.missing_elements?.length" class="missing-alert">
                        ⚠️ 누락 요소: {{ rpt.missing_elements.join(', ') }}
                      </div>

                      <!-- 종합 피드백 -->
                      <div v-if="rpt.feedback?.length" class="review-feedback-list">
                        <div v-for="(f, i) in rpt.feedback" :key="i" class="review-feedback-item">• {{ f }}</div>
                      </div>

                      <!-- 12대 필수요소 그리드 -->
                      <div v-if="rpt.element_scores?.length" class="element-grid">
                        <div
                          v-for="el in rpt.element_scores" :key="el.id"
                          class="element-card"
                          :class="el.present ? 'element-present' : 'element-missing'"
                        >
                          <div class="element-card-top">
                            <span class="element-num">{{ el.id }}</span>
                            <span class="element-name">{{ el.name }}</span>
                            <span class="element-score-badge" :style="{ background: el.present ? elementScoreColor(el.score) : '#dc2626' }">
                              {{ el.present ? el.score + '점' : '없음' }}
                            </span>
                          </div>
                          <p class="element-comment">{{ el.comment }}</p>
                        </div>
                      </div>
                    </div>
                  </td>
                </tr>
              </template>
            </tbody>
          </table>
        </div>
      </div>
    </div>

    <!-- 상태 변경 모달 -->
    <BaseModal v-model="showActionModal" width="420px">
      <template #title>
        <span class="modal-title-file">{{ actionTarget?.report?.file_name }}</span>
        <span> 상태 변경</span>
      </template>
      <div class="modal-inner">
        <!-- 상태 선택 -->
        <div class="modal-section-label">새 상태 선택</div>
        <div class="status-options">
          <button
            v-for="s in ['draft','submitted','approved','rejected']"
            :key="s"
            :class="['status-option-btn', statusClass[s], { 'status-option-active': actionTarget?.newStatus === s }]"
            @click="actionTarget.newStatus = s"
          >{{ statusLabel[s] }}</button>
        </div>

        <!-- 코멘트 -->
        <div class="modal-section-label" style="margin-top:14px">코멘트</div>
        <textarea
          v-model="actionComment"
          class="comment-input"
          :placeholder="actionTarget?.newStatus === 'rejected' ? '반려 사유를 입력하세요' : '코멘트 (선택)'"
          rows="3"
        ></textarea>

        <!-- Teams 알림 -->
        <label class="teams-notify-check">
          <input type="checkbox" v-model="notifyTeams" />
          <span>Teams로 알림 전송</span>
        </label>
      </div>
      <template #footer>
        <button class="btn-cancel" @click="showActionModal = false">취소</button>
        <button
          :class="actionTarget?.newStatus === 'approved' ? 'btn-approve' : actionTarget?.newStatus === 'rejected' ? 'btn-reject' : 'btn-status-change'"
          :disabled="actionSubmitting"
          @click="submitAction"
        >
          {{ actionSubmitting ? '처리 중...' : '변경' }}
        </button>
      </template>
    </BaseModal>
  </div>
</template>

<style scoped>
.prepare-page {
  display: flex;
  flex-direction: column;
  height: calc(100vh - var(--header-h) - 40px);
  overflow: hidden;
}

/* ─── 아젠다 범위 드롭다운 ─── */
.scope-select {
  padding: 4px 8px;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  font-size: 12px;
  color: var(--text);
  background: #f9fafb;
  cursor: pointer;
  max-width: 220px;
}
.scope-select:focus { outline: 2px solid var(--primary); border-color: transparent; }
.agent-body {
  flex: 1;
  min-height: 0;
  display: flex;
  gap: 16px;
  overflow: hidden;
}
.prepare-right {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

/* ─── 드래그 오버레이 ─── */
.drag-overlay {
  position: absolute; inset: 0; z-index: 10;
  background: rgba(99,102,241,.08);
  border: 2px dashed var(--primary, #6366f1);
  border-radius: var(--radius, 10px);
  display: flex; align-items: center; justify-content: center;
  pointer-events: none;
}
.drag-hint {
  background: white;
  border: 1px solid var(--primary, #6366f1);
  border-radius: var(--radius, 10px);
  padding: 12px 24px;
  font-size: 14px;
  font-weight: 600;
  color: var(--primary, #6366f1);
  box-shadow: 0 2px 8px rgba(0,0,0,.08);
  display: flex; align-items: center; gap: 8px;
}

/* ─── 빈 상태 ─── */
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 6px;
  height: 160px;
  color: var(--text-muted, #6b7280);
  font-size: 14px;
  text-align: center;
}
.text-muted { color: var(--text-muted, #9ca3af); font-size: 12px; }

/* ─── 검토 파일 카드 ─── */
.review-file-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.review-file-card {
  border: 1px solid var(--border, #e5e7eb);
  border-radius: 8px;
  padding: 14px 16px;
  display: flex;
  flex-direction: column;
  gap: 10px;
  background: #fafafa;
}
.rfc-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}
.rfc-name {
  font-size: 14px;
  font-weight: 600;
  color: var(--text, #111827);
  word-break: break-all;
}
.score-badge {
  flex-shrink: 0;
  padding: 2px 10px;
  background: var(--primary, #6366f1);
  color: #fff;
  border-radius: 999px;
  font-size: 13px;
  font-weight: 700;
}
.feedback-list {
  margin: 0;
  padding-left: 18px;
  font-size: 13px;
  color: var(--text, #374151);
  line-height: 1.6;
}
.rfc-actions {
  display: flex;
  justify-content: flex-end;
}
.btn-submit-to-admin {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 16px;
  background: var(--primary, #6366f1);
  color: #fff;
  border: none;
  border-radius: 6px;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: opacity .15s;
}
.btn-submit-to-admin:disabled { opacity: .6; cursor: default; }
.btn-submit-to-admin:not(:disabled):hover { opacity: .85; }

/* ─── 제출현황 테이블 ─── */
.reports-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}
.reports-table th {
  text-align: left;
  padding: 8px 12px;
  background: #f9fafb;
  font-weight: 600;
  font-size: 12px;
  color: var(--text-muted, #6b7280);
  border-bottom: 1px solid var(--border, #e5e7eb);
  white-space: nowrap;
}
.reports-table td {
  padding: 10px 12px;
  border-bottom: 1px solid var(--border, #f3f4f6);
  vertical-align: middle;
}
.reports-table tr:last-child td { border-bottom: none; }
.name-cell {
  max-width: 200px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  font-weight: 500;
}

/* ─── 상태 칩 ─── */
.status-chip {
  display: inline-block;
  padding: 2px 10px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 600;
  white-space: nowrap;
}
.status-draft { background: #f3f4f6; color: #6b7280; }
.status-submitted { background: #eff6ff; color: #3b82f6; }
.status-approved { background: #f0fdf4; color: #16a34a; }
.status-rejected { background: #fef2f2; color: #dc2626; }

/* ─── 점수 버튼 ─── */
.score-btn {
  padding: 2px 10px;
  background: #f0f0ff;
  color: var(--primary, #6366f1);
  border: 1px solid #c7d2fe;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 700;
  cursor: pointer;
  transition: background .15s;
}
.score-btn:hover { background: #e0e7ff; }
.score-btn-active { background: #e0e7ff; border-color: var(--primary); }
.row-expanded td { background: #fafbff; }

/* ─── 요소별 검토 확장 패널 ─── */
.review-expand-row td { padding: 0 !important; }
.review-panel {
  padding: 16px 20px;
  background: #fafbff;
  border-top: 1px solid #e0e7ff;
  border-bottom: 2px solid #e0e7ff;
}
.review-panel-header {
  display: flex; align-items: center; gap: 16px; margin-bottom: 10px; flex-wrap: wrap;
}
.review-total-score { font-size: 20px; font-weight: 800; }
.principles-row { display: flex; gap: 6px; flex-wrap: wrap; }
.principle-chip {
  padding: 2px 8px; border-radius: 99px; font-size: 11px; font-weight: 600;
}
.principle-ok { background: #dcfce7; color: #166534; }
.principle-fail { background: #fef2f2; color: #dc2626; }
.missing-alert {
  background: #fef9c3; color: #92400e; border: 1px solid #fcd34d;
  border-radius: 6px; padding: 6px 10px; font-size: 12px; margin-bottom: 8px;
}
.review-feedback-list { margin-bottom: 12px; }
.review-feedback-item { font-size: 12px; color: var(--text-muted); padding: 2px 0; }
.element-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 8px; margin-top: 10px;
}
.element-card {
  border-radius: 8px; padding: 8px 10px;
  border: 1px solid var(--border);
  background: #fff;
}
.element-present { border-left: 3px solid #16a34a; }
.element-missing { border-left: 3px solid #dc2626; background: #fff8f8; }
.element-card-top { display: flex; align-items: center; gap: 6px; margin-bottom: 4px; }
.element-num {
  width: 18px; height: 18px; border-radius: 50%;
  background: #6366f1; color: #fff;
  display: flex; align-items: center; justify-content: center;
  font-size: 10px; font-weight: 700; flex-shrink: 0;
}
.element-name { font-size: 12px; font-weight: 600; flex: 1; }
.element-score-badge {
  padding: 1px 7px; border-radius: 99px;
  color: #fff; font-size: 11px; font-weight: 700;
}
.element-comment { font-size: 11px; color: var(--text-muted); margin: 0; line-height: 1.5; }

/* ─── 아젠다 선택 (검토탭 카드) ─── */
.rfc-agenda-row {
  display: flex;
  align-items: center;
  gap: 8px;
}
.rfc-agenda-label {
  font-size: 11px;
  font-weight: 600;
  color: var(--text-muted, #6b7280);
  white-space: nowrap;
  flex-shrink: 0;
}
.rfc-agenda-select {
  flex: 1;
  padding: 4px 8px;
  border: 1px solid var(--border, #e5e7eb);
  border-radius: 6px;
  font-size: 12px;
  color: var(--text, #374151);
  background: #fff;
  cursor: pointer;
}
.rfc-agenda-select:disabled { background: #f9fafb; cursor: default; }
.rfc-agenda-select:focus { outline: 2px solid var(--primary, #6366f1); border-color: transparent; }

/* ─── 아젠다 칩 (제출현황 테이블) ─── */
.agenda-chip {
  display: inline-block;
  padding: 2px 8px;
  background: #f0f4ff;
  color: var(--primary, #6366f1);
  border-radius: 999px;
  font-size: 11px;
  font-weight: 500;
  white-space: nowrap;
  max-width: 120px;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* ─── 미니 바 (검토탭 카드) ─── */
.element-mini-bars { display: flex; flex-direction: column; gap: 4px; margin: 8px 0; }
.element-mini-bar { display: flex; align-items: center; gap: 6px; font-size: 11px; }
.emb-label { width: 80px; color: var(--text-muted); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.emb-track { flex: 1; height: 6px; background: #e5e7eb; border-radius: 99px; overflow: hidden; }
.emb-fill { height: 100%; border-radius: 99px; transition: width .3s; }
.emb-score { width: 24px; text-align: right; color: var(--text-muted); }

/* ─── 승인/반려 버튼 ─── */
.action-btns { display: flex; gap: 6px; }
.btn-approve {
  padding: 4px 12px;
  background: #16a34a;
  color: #fff;
  border: none;
  border-radius: 6px;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  transition: opacity .15s;
}
.btn-approve:hover { opacity: .85; }
.btn-reject {
  padding: 4px 12px;
  background: #dc2626;
  color: #fff;
  border: none;
  border-radius: 6px;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  transition: opacity .15s;
}
.btn-reject:hover { opacity: .85; }
.btn-status-change {
  padding: 6px 16px;
  background: var(--primary, #6366f1);
  color: #fff;
  border: none;
  border-radius: 6px;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  transition: opacity .15s;
}
.btn-status-change:disabled, .btn-approve:disabled, .btn-reject:disabled { opacity: .6; cursor: default; }

/* ─── 상태 칩 클릭 (admin) ─── */
.status-clickable {
  cursor: pointer;
  border: none;
  transition: opacity .15s, transform .1s;
}
.status-clickable:hover { opacity: .75; transform: scale(1.05); }

/* ─── 모달 상태 선택 ─── */
.modal-section-label {
  font-size: 11px;
  font-weight: 700;
  color: var(--text-muted, #6b7280);
  text-transform: uppercase;
  letter-spacing: .4px;
  margin-bottom: 8px;
}
.modal-title-file {
  font-weight: 700;
  color: var(--primary, #6366f1);
  font-size: 14px;
}
.status-options {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}
.status-option-btn {
  padding: 5px 14px;
  border: 2px solid transparent;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  opacity: .55;
  transition: opacity .15s, transform .1s, box-shadow .15s;
}
.status-option-btn:hover { opacity: .8; }
.status-option-active {
  opacity: 1 !important;
  border-color: currentColor;
  box-shadow: 0 0 0 3px rgba(0,0,0,.08);
  transform: scale(1.06);
}

/* ─── Teams 알림 ─── */
.teams-notify-check {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 14px;
  font-size: 13px;
  color: var(--text, #374151);
  cursor: pointer;
  padding: 10px 14px;
  background: #f0f4ff;
  border: 1px solid #c7d2fe;
  border-radius: 8px;
  user-select: none;
}
.teams-notify-check input[type="checkbox"] {
  width: 15px; height: 15px;
  cursor: pointer;
  accent-color: var(--primary, #6366f1);
  flex-shrink: 0;
}

/* ─── 모달 ─── */
.modal-inner { padding: 16px 20px; display: flex; flex-direction: column; gap: 12px; }
.comment-input {
  width: 100%;
  padding: 8px 10px;
  border: 1px solid var(--border, #d1d5db);
  border-radius: 6px;
  font-size: 13px;
  resize: vertical;
  font-family: inherit;
  box-sizing: border-box;
}
.comment-input:focus { outline: 2px solid var(--primary, #6366f1); border-color: transparent; }
.btn-cancel {
  padding: 6px 16px;
  background: #f3f4f6;
  color: var(--text, #374151);
  border: none;
  border-radius: 6px;
  font-size: 13px;
  cursor: pointer;
}
.btn-cancel:hover { background: #e5e7eb; }

/* ─── 스피너 ─── */
.spinner-sm {
  display: inline-block;
  width: 12px; height: 12px;
  border: 2px solid rgba(255,255,255,.4);
  border-top-color: #fff;
  border-radius: 50%;
  animation: spin .6s linear infinite;
}
.spinner-dark {
  border-color: rgba(99,102,241,.2);
  border-top-color: var(--primary, #6366f1);
}
@keyframes spin { to { transform: rotate(360deg); } }
</style>
