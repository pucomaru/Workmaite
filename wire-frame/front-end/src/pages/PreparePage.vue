<script setup>
import { ref, onMounted, computed } from 'vue'
import { useRoute } from 'vue-router'
import api from '../api'
import { streamPost } from '../api'
import MeetingNav from '../components/MeetingNav.vue'
import AgentPanel from '../components/AgentPanel.vue'
import { useMeetingsStore } from '../stores/meetings'
import { useChatHistory } from '../composables/useChatHistory'
import naruAvatar from '../assets/agents/naru.png'
import { marked } from 'marked'
const renderMd = (text) => marked.parse(text || '', { breaks: true })

const route = useRoute()
const meetingsStore = useMeetingsStore()
const meetingId = computed(() => Number(route.params.meetingId))
const role = computed(() => meetingsStore.myRole)

const reports = ref([])
const input = ref('')
const loading = ref(false)
const reviewResult = ref(null)
const fileInput = ref(null)
const uploading = ref(false)
const messagesEl = ref(null)
const reportContent = ref('')
const isDragging = ref(false)

// 업로드 후 제출 여부 선택 모달
const showSubmitModal = ref(false)
const pendingFile = ref(null)  // AI 검토가 완료된 파일
const submitting = ref(false)

// 관리자: 승인/반려 사유 입력 모달
const showReviewModal = ref(false)
const reviewTarget = ref(null)   // { id, action: 'approved'|'rejected' }
const reviewComment = ref('')
const reviewSubmitting = ref(false)

const { messages, loadMessages, saveMessage, clearHistory } = useChatHistory('prepare', meetingId.value)
const agentPanelRef = ref(null)

async function handleSend(text) {
  input.value = text
  await sendMessage()
}

onMounted(async () => {
  await meetingsStore.fetchMeeting(meetingId.value)
  await meetingsStore.fetchRole(meetingId.value)
  await loadMessages()
  if (role.value === 'admin') {
    await loadReports()
    if (messages.value.length === 0) {
      const greeting = '전체 보고서를 총괄 검토해드립니다. "전체 검토 시작"을 클릭하거나 질문하세요.'
      messages.value.push({ role: 'agent', content: greeting })
      saveMessage('agent', greeting)
    }
  } else {
    await loadReports()
    if (messages.value.length === 0) {
      const greeting = '발제자료 파일을 업로드하면 AI가 사전 검토를 진행합니다. 점수와 개선사항을 제공해드립니다.'
      messages.value.push({ role: 'agent', content: greeting })
      saveMessage('agent', greeting)
    }
  }
})

async function loadReports() {
  const { data } = await api.get(`/api/meetings/${meetingId.value}/reports`)
  reports.value = data
}

async function sendMessage() {
  if (!input.value.trim() || loading.value) return
  const text = input.value.trim()
  messages.value.push({ role: 'user', content: text })
  saveMessage('user', text)
  input.value = ''
  const agentMsg = { role: 'agent', content: '' }
  messages.value.push(agentMsg)
  loading.value = true

  const endpoint = role.value === 'admin' ? '/api/agent/naru/chat' : '/api/agent/naru/chat'
  const history = messages.value.slice(0,-1).map(m => ({ role: m.role === 'user' ? 'user' : 'assistant', content: m.content }))

  await streamPost(
    endpoint,
    { meeting_id: meetingId.value, message: text, chat_history: history },
    (chunk) => { agentMsg.content += chunk },
    () => { loading.value = false; saveMessage('agent', agentMsg.content) }
  )
}

async function globalReview() {
  messages.value.push({ role: 'user', content: '전체 보고서 검토를 시작해주세요.' })
  saveMessage('user', '전체 보고서 검토를 시작해주세요.')
  const agentMsg = { role: 'agent', content: '' }
  messages.value.push(agentMsg)
  loading.value = true

  const history = messages.value.slice(0,-1).map(m => ({ role: m.role === 'user' ? 'user' : 'assistant', content: m.content }))
  await streamPost(
    '/api/agent/naru/global-review',
    { meeting_id: meetingId.value, message: '전체 보고서를 검토해주세요.', chat_history: history },
    (chunk) => { agentMsg.content += chunk },
    () => { loading.value = false; saveMessage('agent', agentMsg.content) }
  )
}

async function uploadReport(fileOrEvent) {
  const file = fileOrEvent instanceof File ? fileOrEvent : fileOrEvent.target.files[0]
  if (!file) return
  uploading.value = true
  messages.value.push({ role: 'user', content: `보고서 파일 업로드: ${file.name}` })
  const agentMsg = { role: 'agent', content: '파일을 분석하고 있습니다...' }
  messages.value.push(agentMsg)

  try {
    // Read file content for review
    const text = await file.text().catch(() => file.name)
    const reviewRes = await api.post('/api/agent/report-review', {
      report_content: text.slice(0, 3000),
      agenda: '',
    })
    reviewResult.value = reviewRes.data
    agentMsg.content = `검토 완료!\n\n📊 점수: ${reviewRes.data.score}/100\n\n📝 주요 피드백:\n${(reviewRes.data.feedback || []).map(f => `• ${f}`).join('\n')}\n\n점수가 만족스러우면 최종 제출하세요.`

    // Upload to server
    const formData = new FormData()
    formData.append('file', file)
    const token = localStorage.getItem('token')
    await fetch(`http://localhost:8000/api/meetings/${meetingId.value}/reports`, {
      method: 'POST',
      headers: { Authorization: `Bearer ${token}` },
      body: formData,
    })
    await loadReports()
  } catch (err) {
    agentMsg.content = '파일 처리 중 오류가 발생했습니다.'
  } finally {
    uploading.value = false
  }
}

function openReviewModal(reportId, action) {
  reviewTarget.value = { id: reportId, action }
  reviewComment.value = ''
  showReviewModal.value = true
}

async function submitReview() {
  if (!reviewTarget.value) return
  reviewSubmitting.value = true
  try {
    await api.patch(`/api/reports/${reviewTarget.value.id}/status`, {
      status: reviewTarget.value.action,
      comment: reviewComment.value.trim() || null,
    })
    await loadReports()
    showReviewModal.value = false
    reviewTarget.value = null
  } finally {
    reviewSubmitting.value = false
  }
}

async function updateReportStatus(reportId, status) {
  await api.patch(`/api/reports/${reportId}/status`, { status })
  await loadReports()
}

function onKeydown(e) {
  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage() }
}

function onDragover() {
  if (role.value !== 'admin') isDragging.value = true
}

function onDragleave(e) {
  if (!e.currentTarget.contains(e.relatedTarget)) {
    isDragging.value = false
  }
}

function onDrop(e) {
  isDragging.value = false
  if (role.value === 'admin') return
  const file = e.dataTransfer.files[0]
  if (file) uploadReport(file)
}

function formatDate(d) {
  if (!d) return '-'
  return new Date(d).toLocaleDateString('ko-KR')
}

function statusCls(s) {
  const m = { draft: 'badge-muted', submitted: 'badge-primary', approved: 'badge-success', rejected: 'badge-danger' }
  return m[s] || 'badge-muted'
}
function statusLabel(s) {
  const m = { draft: '미제출', submitted: '제출됨', approved: '승인', rejected: '반려' }
  return m[s] || s
}

function getToken() { return localStorage.getItem('token') }

async function downloadFile(reportId, fileName) {
  const res = await fetch(`http://localhost:8000/api/reports/${reportId}/download`, {
    headers: { Authorization: `Bearer ${getToken()}` }
  })
  if (!res.ok) { alert('파일을 불러올 수 없습니다.'); return }
  const blob = await res.blob()
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url; a.download = fileName; a.click()
  URL.revokeObjectURL(url)
}

async function previewFile(reportId) {
  const res = await fetch(`http://localhost:8000/api/reports/${reportId}/download`, {
    headers: { Authorization: `Bearer ${getToken()}` }
  })
  if (!res.ok) { alert('파일을 불러올 수 없습니다.'); return }
  const blob = await res.blob()
  const url = URL.createObjectURL(blob)
  window.open(url, '_blank')
}
</script>

<template>
  <div class="prepare-layout">
    <MeetingNav />
    <div class="agent-body">
      <!-- 왼쪽: 나루 패널 -->
      <AgentPanel
        ref="agentPanelRef"
        :avatar="naruAvatar"
        name="나루"
        name-en="Naru"
        :subtitle="role === 'admin' ? '전체 보고서 종합 검토' : '발제자료 검토 어시스턴트'"
        :messages="messages"
        :loading="loading"
        placeholder="나루에게 질문하세요..."
        accent-color="#0ea5e9"
        accent-border="#38bdf8"
        accent-bg="#f0f9ff"
        bubble-gradient="linear-gradient(135deg,#f0f9ff,#e0f2fe)"
        bubble-color="#0c4a6e"
        @send="handleSend"
        @clear="clearHistory"
        style="position:relative"
        @dragover.prevent="onDragover"
        @dragleave="onDragleave"
        @drop.prevent="onDrop"
      >
        <template #actions>
          <button v-if="role === 'admin'" class="btn btn-primary btn-sm" :disabled="loading" @click="globalReview">
            전체 검토 시작
          </button>
          <button v-else class="btn btn-outline btn-sm" :disabled="uploading" @click="fileInput.click()">
            {{ uploading ? '분석 중...' : '📎 발제자료 업로드' }}
          </button>
          <input ref="fileInput" type="file" accept=".pdf,.docx,.txt" style="display:none" @change="uploadReport" />
        </template>
        <template #overlay>
          <div v-if="isDragging" class="drag-overlay">
            <div class="drag-hint">📎 파일을 여기에 놓으세요</div>
          </div>
        </template>
      </AgentPanel>

      <!-- 오른쪽: 발제자료 문서 -->
      <div class="prepare-right">
        <!-- Admin: Report table -->
        <div v-if="role === 'admin'" class="card">
          <div class="card-header">
            <span style="font-weight:600">발제자료 제출 현황</span>
            <button class="btn btn-ghost btn-sm" @click="loadReports">새로고침</button>
          </div>
          <div style="overflow-x:auto">
            <table class="table">
              <thead>
                <tr>
                  <th>발제자</th>
                  <th>파일명</th>
                  <th>제출일</th>
                  <th>상태</th>
                  <th>사유</th>
                  <th>액션</th>
                </tr>
              </thead>
              <tbody>
                <tr v-if="!reports.length">
                  <td colspan="6" style="text-align:center;color:var(--text-muted);padding:24px">제출된 발제자료가 없습니다.</td>
                </tr>
                <tr v-for="r in reports" :key="r.id" class="fade-in">
                  <td>{{ r.presenter?.name || '-' }}</td>
                  <td style="font-size:12px">
                    <div v-if="r.file_name" class="file-name-cell">
                      <span class="file-name-text">{{ r.file_name }}</span>
                      <span class="file-actions">
                        <button class="file-act-btn" @click.stop="previewFile(r.id)" title="미리보기">👁 미리보기</button>
                        <button class="file-act-btn" @click.stop="downloadFile(r.id, r.file_name)" title="다운로드">⬇ 다운로드</button>
                      </span>
                    </div>
                    <span v-else style="color:var(--text-muted)">-</span>
                  </td>
                  <td style="font-size:12px">{{ formatDate(r.submitted_at) }}</td>
                  <td><span class="badge" :class="statusCls(r.status)">{{ statusLabel(r.status) }}</span></td>
                  <td style="font-size:12px;max-width:160px">
                    <span v-if="r.review_comment" class="review-comment-cell" :title="r.review_comment">{{ r.review_comment }}</span>
                    <span v-else style="color:var(--text-muted)">-</span>
                  </td>
                  <td>
                    <div v-if="r.status === 'submitted'" style="display:flex;gap:4px">
                      <button class="btn btn-success btn-sm" @click="openReviewModal(r.id, 'approved')">승인</button>
                      <button class="btn btn-danger btn-sm" @click="openReviewModal(r.id, 'rejected')">반려</button>
                    </div>
                    <span v-else style="font-size:12px;color:var(--text-muted)">-</span>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>

        <!-- Presenter: Review result -->
        <div v-else class="card">
          <div class="card-header"><span style="font-weight:600">검토 결과</span></div>
          <div class="card-body">
            <div v-if="!reviewResult" class="empty-state">
              <p>발제자료를 업로드하면 AI 검토 결과가 표시됩니다.</p>
            </div>
            <div v-else class="review-result">
              <div class="score-card">
                <div class="score-num">{{ reviewResult.score }}</div>
                <div class="score-label">/ 100점</div>
              </div>
              <div class="feedback-list">
                <div style="font-weight:600;margin-bottom:8px">개선 사항</div>
                <div v-for="(f, i) in reviewResult.feedback" :key="i" class="feedback-item">
                  <span>📌</span><span>{{ f }}</span>
                </div>
              </div>
              <!-- 제출 파일 다운로드 -->
              <div v-if="reports.length" style="margin-top:8px;padding-top:12px;border-top:1px solid var(--border)">
                <div style="font-weight:600;margin-bottom:10px;font-size:13px">제출한 파일</div>
                <div v-for="r in reports" :key="r.id" class="submitted-file-row">
                  <div class="file-name-cell">
                    <span class="file-name-text">📄 {{ r.file_name }}</span>
                    <span class="file-actions">
                      <button class="file-act-btn" @click="previewFile(r.id)">👁 미리보기</button>
                      <button class="file-act-btn" @click="downloadFile(r.id, r.file_name)">⬇ 다운로드</button>
                    </span>
                  </div>
                  <!-- 제출 상태 표시 -->
                  <div class="file-status-row">
                    <span class="badge" :class="statusCls(r.status)">{{ statusLabel(r.status) }}</span>
                    <button
                      v-if="r.status === 'draft'"
                      class="btn btn-primary btn-sm"
                      style="font-size:11px;padding:2px 10px"
                      @click="showSubmitModal = true"
                    >📤 제출하기</button>
                  </div>
                  <!-- 승인/반려 사유 -->
                  <div v-if="r.review_comment && (r.status === 'approved' || r.status === 'rejected')" class="review-reason-box" :class="r.status">
                    <span class="review-reason-label">{{ r.status === 'approved' ? '✅ 승인 사유' : '❌ 반려 사유' }}</span>
                    <span class="review-reason-text">{{ r.review_comment }}</span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- ─── 제출 확인 모달 ────────────────────────────────── -->
    <Teleport to="body">
      <div v-if="showSubmitModal" class="modal-backdrop" @click.self="showSubmitModal = false">
        <div class="modal-box">
          <div class="modal-header">
            <span style="font-size:20px">📤 관리자에게 제출할까요?</span>
          </div>
          <div class="modal-body">
            <p style="font-size:14px;color:var(--text-muted);line-height:1.7">
              관리자에게 제출하면 승인/반려 피드백을 수신할 수 있습니다.<br/>
              아직 수정이 필요하다면 임시저장 상태로 둘 수 있습니다.
            </p>
            <div v-if="reports.find(r => r.status === 'draft')" class="draft-file-preview">
              📄 {{ reports.find(r => r.status === 'draft')?.file_name }}
            </div>
          </div>
          <div class="modal-footer">
            <button class="btn btn-ghost" @click="showSubmitModal = false">임시저장 유지</button>
            <button class="btn btn-primary" :disabled="submitting" @click="confirmSubmit">
              {{ submitting ? '제출 중...' : '✔ 제출하기' }}
            </button>
          </div>
        </div>
      </div>
    </Teleport>

    <!-- ─── 승인/반려 사유 모달 ────────────────────────────── -->
    <Teleport to="body">
      <div v-if="showReviewModal" class="modal-backdrop" @click.self="showReviewModal = false">
        <div class="modal-box">
          <div class="modal-header">
            <span v-if="reviewTarget?.action === 'approved'" style="font-size:18px">✅ 발제자료 승인</span>
            <span v-else style="font-size:18px">❌ 발제자료 반려</span>
          </div>
          <div class="modal-body">
            <label class="form-label">사유 입력 <span style="color:var(--text-muted);font-size:12px">(선택사항)</span></label>
            <textarea
              v-model="reviewComment"
              class="form-input form-textarea"
              :placeholder="reviewTarget?.action === 'approved' ? '승인 사유를 입력하세요 (ex. 자료가 완성도가 높고 다양한 시각 자료가 포함됨)' : '반려 사유를 입력하세요 (ex. 협의사항 누락, 근거 자료 부족)'"
              rows="3"
              style="resize:vertical"
              autofocus
            />
          </div>
          <div class="modal-footer">
            <button class="btn btn-ghost" @click="showReviewModal = false">취소</button>
            <button
              class="btn"
              :class="reviewTarget?.action === 'approved' ? 'btn-success' : 'btn-danger'"
              :disabled="reviewSubmitting"
              @click="submitReview"
            >
              {{ reviewSubmitting ? '저장 중...' : (reviewTarget?.action === 'approved' ? '승인' : '반려') }}
            </button>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<style scoped>
.prepare-layout {
  display: flex;
  flex-direction: column;
  height: calc(100vh - var(--header-h) - 40px);
}
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
  overflow-y: auto;
}
.review-result { display: flex; flex-direction: column; gap: 16px; }
.score-card { display: flex; align-items: baseline; gap: 4px; padding: 20px; background: linear-gradient(135deg, var(--primary) 0%, var(--primary-light) 100%); border-radius: var(--radius); color: #fff; width: fit-content; }
.score-num { font-size: 48px; font-weight: 700; line-height: 1; }
.score-label { font-size: 20px; opacity: .8; }
.feedback-list { display: flex; flex-direction: column; gap: 8px; }
.feedback-item { display: flex; gap: 8px; padding: 8px 12px; background: #f8fafc; border-radius: 6px; font-size: 13px; line-height: 1.5; }
.file-name-cell { display: flex; align-items: center; gap: 8px; }
.file-name-text { font-size: 12px; color: var(--text-muted); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 160px; }
.file-actions { display: flex; gap: 4px; opacity: 0; transition: opacity .15s; flex-shrink: 0; }
.file-name-cell:hover .file-actions { opacity: 1; }
.file-act-btn {
  font-size: 11px; color: var(--primary); background: none; border: 1px solid var(--primary);
  border-radius: 4px; padding: 1px 6px; cursor: pointer; white-space: nowrap;
}
.file-act-btn:hover { background: #eff6ff; }
.submitted-files-section { margin-bottom: 16px; padding-bottom: 16px; border-bottom: 1px solid var(--border); }
.review-result.has-divider { padding-top: 4px; }
.submitted-file-row { display: flex; flex-direction: column; gap: 6px; padding: 10px 0; border-bottom: 1px solid var(--border); }
.submitted-file-row:last-child { border-bottom: none; }
.file-status-row { display: flex; align-items: center; gap: 8px; }
.review-reason-box {
  display: flex; flex-direction: column; gap: 4px;
  padding: 8px 12px; border-radius: 6px; font-size: 12px;
}
.review-reason-box.approved { background: #f0fdf4; border: 1px solid #bbf7d0; }
.review-reason-box.rejected { background: #fef2f2; border: 1px solid #fecaca; }
.review-reason-label { font-weight: 600; font-size: 11px; }
.review-reason-text { color: var(--text); line-height: 1.5; }
.review-comment-cell { display: -webkit-box; -webkit-line-clamp: 2; line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; font-size: 12px; color: var(--text-muted); cursor: default; }

/* 모달 */
.modal-backdrop {
  position: fixed; inset: 0; z-index: 200;
  background: rgba(0,0,0,.45);
  display: flex; align-items: center; justify-content: center;
}
.modal-box {
  background: #fff;
  border-radius: var(--radius);
  box-shadow: 0 8px 32px rgba(0,0,0,.18);
  width: 420px; max-width: 96vw;
  display: flex; flex-direction: column;
  overflow: hidden;
}
.modal-header { padding: 18px 20px 14px; font-weight: 700; font-size: 15px; border-bottom: 1px solid var(--border); }
.modal-body { padding: 16px 20px; display: flex; flex-direction: column; gap: 12px; }
.modal-footer { padding: 12px 20px; border-top: 1px solid var(--border); display: flex; justify-content: flex-end; gap: 8px; }
.draft-file-preview { padding: 8px 12px; background: #f8fafc; border: 1px solid var(--border); border-radius: 6px; font-size: 13px; color: var(--text-muted); }
.drag-overlay {
  position: absolute; inset: 0; z-index: 10;
  background: rgba(99, 102, 241, 0.08);
  border: 2px dashed var(--primary, #6366f1);
  border-radius: var(--radius);
  display: flex; align-items: center; justify-content: center;
  pointer-events: none;
}
.drag-hint {
  background: white;
  border: 1px solid var(--primary, #6366f1);
  border-radius: var(--radius);
  padding: 12px 24px;
  font-size: 14px;
  font-weight: 600;
  color: var(--primary, #6366f1);
  box-shadow: 0 2px 8px rgba(0,0,0,0.08);
}
</style>
