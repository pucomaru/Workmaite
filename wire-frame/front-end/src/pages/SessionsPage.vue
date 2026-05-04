<script setup>
import { ref, onMounted, computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import api from '../api'
import { streamPost } from '../api'
import MeetingNav from '../components/MeetingNav.vue'
import AgentPanel from '../components/AgentPanel.vue'
import BaseModal from '../components/BaseModal.vue'
import { useMeetingsStore } from '../stores/meetings'
import { useChatHistory } from '../composables/useChatHistory'
import araAvatar from '../assets/agents/ara.png'
import { marked } from 'marked'

const renderMd = (text) => marked.parse(text || '', { breaks: true })

const route = useRoute()
const router = useRouter()
const meetingsStore = useMeetingsStore()
const meetingId = computed(() => Number(route.params.meetingId))
const role = computed(() => meetingsStore.myRole)

const sessions = ref([])
const agendas = ref([])

const AGENDA_TYPE_LABEL = { report: '보고', discussion: '토의', decision: '결정', info: '정보공유' }
const AGENDA_TYPE_COLOR = { report: '#3b82f6', discussion: '#8b5cf6', decision: '#ef4444', info: '#6b7280' }

const showMinutesModal = ref(false)
const selectedSession = ref(null)
const minutes = ref(null)

const editingId = ref(null)
const editForm = ref({ title: '', scheduled_at: '', location: '', agenda_ids: [] })
const saving = ref(false)
const deleting = ref(null)
const ending = ref(null)

const showCreateModal = ref(false)
const createForm = ref({ title: '', scheduled_at: '', location: '', agenda_ids: [] })
const creating = ref(false)

// ── 아라 ──────────────────────────────────────
const araInput = ref('')
const araLoading = ref(false)
const messagesEl = ref(null)
const { messages: araMessages, loadMessages, saveMessage, clearHistory } = useChatHistory('sessions', meetingId.value)

// 빠른 질문 목록
const quickQuestions = [
  '전체 회의를 요약해줘',
  '가장 최근 회의 내용 알려줘',
  '회의에서 결정된 사항 정리해줘',
  '아직 해결 안 된 과제가 있어?',
]

onMounted(async () => {
  await meetingsStore.fetchMeeting(meetingId.value)
  await meetingsStore.fetchRole(meetingId.value)
  await Promise.all([
    loadSessions(),
    loadMessages(),
    api.get(`/api/meetings/${meetingId.value}/agendas`).then(({ data }) => {
      agendas.value = data.filter(a => a.agenda_type === 'scheduled')
    }).catch(() => {}),
  ])
})

async function loadSessions() {
  const { data } = await api.get(`/api/meetings/${meetingId.value}/sessions`)
  sessions.value = data
}

async function createSession() {
  if (!createForm.value.title.trim() || creating.value) return
  creating.value = true
  try {
    await api.post(`/api/meetings/${meetingId.value}/sessions`, {
      title: createForm.value.title.trim(),
      scheduled_at: createForm.value.scheduled_at || null,
      location: createForm.value.location.trim() || null,
      agenda_ids: createForm.value.agenda_ids,
    })
    showCreateModal.value = false
    createForm.value = { title: '', scheduled_at: '', location: '', agenda_ids: [] }
    await loadSessions()
  } finally {
    creating.value = false
  }
}

function startEdit(s) {
  editingId.value = s.id
  editForm.value = {
    title: s.title,
    scheduled_at: s.scheduled_at ? s.scheduled_at.slice(0, 16) : '',
    agenda_ids: s.agenda_ids ? [...s.agenda_ids] : [],
  }
}

function cancelEdit() { editingId.value = null }

async function saveEdit(s) {
  if (!editForm.value.title.trim() || saving.value) return
  saving.value = true
  try {
    await api.patch(`/api/sessions/${s.id}`, {
      title: editForm.value.title.trim(),
      scheduled_at: editForm.value.scheduled_at || null,
      agenda_ids: editForm.value.agenda_ids,
    })
    editingId.value = null
    await loadSessions()
  } finally {
    saving.value = false
  }
}

async function endSession(s) {
  if (!confirm(`"${s.title}" 회의를 종료하시겠습니까?`)) return
  ending.value = s.id
  try {
    await api.patch(`/api/sessions/${s.id}`, { status: 'ended' })
    // 연결된 아젠다 종료 처리
    const ids = s.agenda_ids || []
    if (ids.length) {
      await Promise.all(ids.map(id =>
        api.patch(`/api/meetings/${meetingId.value}/agendas/${id}`, { status: 'ended' }).catch(() => {})
      ))
    }
    await loadSessions()
  } finally {
    ending.value = null
  }
}

async function deleteSession(s) {
  if (!confirm(`"${s.title}" 회의를 삭제하시겠습니까?\n삭제하면 회의록도 함께 삭제됩니다.`)) return
  deleting.value = s.id
  try {
    await api.delete(`/api/sessions/${s.id}`)
    await loadSessions()
  } finally {
    deleting.value = null
  }
}

async function viewMinutes(s) {
  selectedSession.value = s
  minutes.value = null
  showMinutesModal.value = true
  try {
    const { data } = await api.get(`/api/sessions/${s.id}/minutes`)
    minutes.value = data
  } catch {
    minutes.value = null
  }
}

async function joinRoom(s) {
  try {
    const { data } = await api.get(`/api/livekit/token/${meetingId.value}/${s.id}`)
    const url = router.resolve(`/meetings/${meetingId.value}/sessions/${s.id}/room`).href
    const params = new URLSearchParams({ lkToken: data.token, lkUrl: data.url })
    const win = window.open(`${url}?${params.toString()}`, '_blank', 'noopener,noreferrer')
    if (win) win.opener = null
  } catch (e) {
    alert(e.response?.data?.detail || 'LiveKit 토큰 발급 실패')
  }
}

// ── 아라 전송 ─────────────────────────────────
async function sendAra() {
  if (!araInput.value.trim() || araLoading.value) return
  const text = araInput.value.trim()
  araMessages.value.push({ role: 'user', content: text })
  saveMessage('user', text)
  araInput.value = ''
  const agentMsg = { role: 'agent', content: '' }
  araMessages.value.push(agentMsg)
  araLoading.value = true
  await nextTick()
  scrollMessages()

  const history = araMessages.value.slice(0, -1).map(m => ({
    role: m.role === 'user' ? 'user' : 'assistant',
    content: m.content,
  }))
  await streamPost(
    '/api/agent/ara/sessions-chat',
    { meeting_id: meetingId.value, message: text, chat_history: history },
    (chunk) => {
      agentMsg.content += chunk
      scrollMessages()
    },
    () => {
      araLoading.value = false
      saveMessage('agent', agentMsg.content)
    },
  )
}

async function sendQuick(q) {
  araInput.value = q
  await sendAra()
}

function scrollMessages() {
  if (messagesEl.value) {
    messagesEl.value.scrollTop = messagesEl.value.scrollHeight
  }
}

import { nextTick } from 'vue'

function formatDate(d) {
  if (!d) return '일정 미정'
  return new Date(d).toLocaleString('ko-KR', {
    month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit',
  })
}
function statusLabel(s) {
  return { scheduled: '예정', ongoing: '진행중', ended: '종료' }[s] || s
}
function statusCls(s) {
  return { scheduled: 'badge-primary', ongoing: 'badge-warning', ended: 'badge-muted' }[s] || 'badge-muted'
}
</script>

<template>
  <div class="sessions-layout">
    <MeetingNav />

    <div class="sessions-body">
      <!-- 왼쪽: 아라 AgentPanel -->
      <AgentPanel
        :avatar="araAvatar"
        name="아라"
        name-en="Ara"
        subtitle="회의 요약 · 질의응답"
        :messages="araMessages"
        :loading="araLoading"
        :quick-questions="quickQuestions"
        greeting="안녕하세요, 아라입니다! 🎤
회의 전체 또는 특정 회의에 대해 자연어로 질문해보세요.
예: &quot;가장 최근 회의 요약해줘&quot;, &quot;전체 회의에서 결정된 사항 정리해줘&quot;"
        placeholder="회의에 대해 자유롭게 질문하세요..."
        accent-color="#f59e0b"
        accent-border="#fbbf24"
        accent-bg="#fffbeb"
        bubble-gradient="linear-gradient(135deg,#fef3c7,#fed7aa)"
        bubble-color="#92400e"
        @send="sendQuick"
        @clear="clearHistory"
      />

      <!-- 오른쪽: 회의 목록 -->
      <div class="card sessions-panel">
        <div class="right-panel-header">
          <span class="panel-tab active" style="cursor:default">회의 목록</span>
          <button class="btn btn-outline btn-sm" style="margin-left:auto;margin-right:6px" @click="showCreateModal = true">+ 회의 등록</button>
          <button v-if="role === 'admin'" class="btn btn-outline btn-sm" @click="router.push(`/meetings/${meetingId}/card-news`)">📰 카드뉴스</button>
        </div>

        <div class="tab-body">
          <div v-if="!sessions.length" class="empty-state">
            <p>등록된 회의가 없습니다.</p>
            <button class="btn btn-outline btn-sm" style="margin-top:12px" @click="showCreateModal = true">+ 회의 등록</button>
          </div>

          <div v-for="s in sessions" :key="s.id" class="session-card fade-in">
            <!-- 수정 모드 -->
            <div v-if="editingId === s.id" class="session-edit">
              <div class="form-group" style="margin-bottom:8px">
                <label class="form-label" style="font-size:11px">회의명</label>
                <input v-model="editForm.title" class="form-input"
                  @keydown.enter="saveEdit(s)" @keydown.esc="cancelEdit" autofocus />
              </div>
              <div class="form-group" style="margin-bottom:8px">
                <label class="form-label" style="font-size:11px">일정</label>
                <input type="datetime-local" v-model="editForm.scheduled_at" class="form-input" />
              </div>
              <div class="form-group" style="margin-bottom:12px">
                <label class="form-label" style="font-size:11px">아젠다 연결</label>
                <div class="agenda-check-list">
                  <label v-if="!agendas.length" style="font-size:12px;color:var(--text-muted)">등록된 아젠다가 없습니다</label>
                  <label v-for="a in agendas" :key="a.id" class="agenda-check-item">
                    <input type="checkbox" :value="a.id" v-model="editForm.agenda_ids" />
                    <span class="agenda-type-dot" :style="{ background: AGENDA_TYPE_COLOR[a.agenda_type] || '#6366f1' }"></span>
                    <span>{{ a.content }}</span>
                  </label>
                </div>
              </div>
              <div style="display:flex;gap:6px">
                <button class="btn btn-primary btn-sm" :disabled="!editForm.title.trim() || saving" @click="saveEdit(s)">
                  {{ saving ? '저장 중...' : '저장' }}
                </button>
                <button class="btn btn-ghost btn-sm" @click="cancelEdit">취소</button>
              </div>
            </div>

            <!-- 보기 모드 -->
            <div v-else>
              <div class="session-header">
                <div>
                  <div style="font-weight:600;font-size:14px">{{ s.title }}</div>
                  <div style="font-size:12px;color:var(--text-muted);margin-top:2px">{{ formatDate(s.scheduled_at) }}</div>
                  <!-- 연결된 아젠다 칩 -->
                  <div v-if="s.agenda_ids?.length" class="session-agenda-chips">
                    <span
                      v-for="id in s.agenda_ids"
                      :key="id"
                      class="session-agenda-chip"
                      :style="{ background: AGENDA_TYPE_COLOR[agendas.find(a=>a.id===id)?.agenda_type] || '#6366f1' }"
                    >
                      {{ (agendas.find(a=>a.id===id)?.content || '아젠다').slice(0,14) }}
                    </span>
                  </div>
                </div>
                <span class="badge" :class="statusCls(s.status)">{{ statusLabel(s.status) }}</span>
              </div>
              <div class="session-actions">
                <button class="btn btn-primary btn-sm" @click="joinRoom(s)">
                  {{ s.status === 'ended' ? '다시 보기' : '참여하기' }}
                </button>
                <button class="btn btn-outline btn-sm" :disabled="s.status !== 'ended'" @click="viewMinutes(s)">회의록</button>
                <template v-if="role === 'admin'">
                  <!-- 미종료 세션: 수정 + 종료 -->
                  <template v-if="s.status !== 'ended'">
                    <button v-if="s.status !== 'ongoing'" class="btn btn-ghost btn-sm" @click="startEdit(s)">수정</button>
                    <button class="btn-end-session" :disabled="ending === s.id" @click="endSession(s)">
                      {{ ending === s.id ? '종료 중...' : '종료' }}
                    </button>
                  </template>
                  <!-- 종료된 세션: 삭제만 -->
                  <template v-else>
                    <button class="btn btn-ghost btn-sm" style="color:var(--danger)" :disabled="deleting === s.id" @click="deleteSession(s)">
                      {{ deleting === s.id ? '삭제 중...' : '삭제' }}
                    </button>
                  </template>
                </template>
              </div>
            </div>
          </div>
        </div>

      </div>

    </div>
  </div>

  <!-- 회의 만들기 모달 -->
  <BaseModal v-model="showCreateModal">
    <template #title>회의 일정 추가</template>
    <div class="modal-inner">
      <div class="form-group">
        <label class="form-label">회의 제목 <span style="color:var(--danger)">*</span></label>
        <input v-model="createForm.title" class="form-input" placeholder="예: 1차 회의" @keydown.enter="createSession" autofocus />
      </div>
      <div class="form-group">
        <label class="form-label">일정</label>
        <input type="datetime-local" v-model="createForm.scheduled_at" class="form-input" />
      </div>
      <div class="form-group">
        <label class="form-label">장소 <span style="font-size:11px;color:var(--text-muted);font-weight:400">(TPO)</span></label>
        <input v-model="createForm.location" class="form-input" placeholder="예: 3층 회의실 A / 비대면 회의 등" />
      </div>
      <div class="form-group">
        <label class="form-label">아젠다 연결 <span style="font-size:11px;color:var(--text-muted);font-weight:400">(이 회의에서 다룰 아젠다)</span></label>
        <div class="agenda-check-list">
          <label v-if="!agendas.length" style="font-size:12px;color:var(--text-muted)">등록된 아젠다가 없습니다</label>
          <label v-for="a in agendas" :key="a.id" class="agenda-check-item">
            <input type="checkbox" :value="a.id" v-model="createForm.agenda_ids" />
            <span class="agenda-type-dot" :style="{ background: AGENDA_TYPE_COLOR[a.agenda_type] || '#6366f1' }"></span>
            <span style="font-size:13px">
              <strong style="font-size:11px;margin-right:4px;opacity:.7">{{ AGENDA_TYPE_LABEL[a.agenda_type] }}</strong>{{ a.content }}
            </span>
          </label>
        </div>
      </div>
    </div>
    <template #footer>
      <button class="btn btn-outline" @click="showCreateModal = false">취소</button>
      <button class="btn btn-primary" :disabled="!createForm.title.trim() || creating" @click="createSession">
        {{ creating ? '추가 중...' : '일정 추가' }}
      </button>
    </template>
  </BaseModal>

  <!-- 회의록 모달 -->
  <BaseModal v-model="showMinutesModal" width="min(680px, 95vw)">
    <template #title>{{ selectedSession?.title }} 회의록</template>
    <div class="modal-inner">
        <div v-if="!minutes" class="empty-state"><p>회의록을 불러오는 중...</p></div>
        <div v-else class="minutes-structured">
          <!-- 회의록 마크다운 요약 -->
          <div v-if="minutes.content_summary" class="minutes-md" v-html="renderMd(minutes.content_summary)"></div>

          <!-- 5대 필수요소 구조적 표시 (AI가 생성한 JSON 기반) -->
          <template v-if="!minutes.content_summary && (minutes.attendees_json?.length || minutes.decisions_json?.length || minutes.action_items_json?.length)">
            <!-- Joiner -->
            <section v-if="minutes.attendees_json?.length" class="ms-section">
              <div class="ms-section-title">👥 참석자 (Joiner)</div>
              <div class="ms-attendee-list">
                <div v-for="a in minutes.attendees_json" :key="a.name" class="ms-attendee" :class="{absent: !a.present}">
                  <span class="ms-att-name">{{ a.name }}</span>
                  <span class="ms-att-dept">{{ a.dept }}</span>
                  <span class="ms-att-role">{{ a.role === 'admin' ? '관리자' : '발제자' }}</span>
                  <span class="ms-att-status" :class="a.present ? 'present' : 'absent'">{{ a.present ? '참석' : '불참' }}</span>
                  <span v-if="a.note" class="ms-att-note">({{ a.note }})</span>
                </div>
              </div>
            </section>

            <!-- Done -->
            <section v-if="minutes.decisions_json?.length" class="ms-section">
              <div class="ms-section-title">✅ 결정 사항 (Done)</div>
              <div v-for="(d, i) in minutes.decisions_json" :key="i" class="ms-decision">
                <span class="ms-dec-num">{{ i+1 }}</span>
                <span class="ms-dec-content">{{ d.content }}</span>
                <span v-if="d.decided_by" class="ms-dec-by">— {{ d.decided_by }}</span>
              </div>
            </section>

            <!-- WILL DO -->
            <section v-if="minutes.action_items_json?.length" class="ms-section">
              <div class="ms-section-title">📌 실행 계획 (WILL DO)</div>
              <table class="ms-action-table">
                <thead><tr><th>업무</th><th>담당자</th><th>기한</th><th>상태</th></tr></thead>
                <tbody>
                  <tr v-for="(a, i) in minutes.action_items_json" :key="i">
                    <td>{{ a.content }}</td>
                    <td>{{ a.assignee || '-' }}</td>
                    <td>{{ a.due_date || '-' }}</td>
                    <td><span class="ms-status-chip" :class="'status-' + (a.status || 'pending')">{{ {'pending':'대기','done':'완료','delayed':'지연'}[a.status] || a.status }}</span></td>
                  </tr>
                </tbody>
              </table>
            </section>

            <!-- TBD -->
            <section v-if="minutes.tbd_items_json?.length" class="ms-section">
              <div class="ms-section-title">⚠️ 미결 안건 (TBD)</div>
              <div v-for="(t, i) in minutes.tbd_items_json" :key="i" class="ms-tbd-item">
                <span class="ms-tbd-dot">●</span>
                <span>{{ t.content }}</span>
                <span v-if="t.reason" class="ms-tbd-reason">— {{ t.reason }}</span>
              </div>
            </section>

            <!-- Next -->
            <section v-if="minutes.next_meeting_note" class="ms-section">
              <div class="ms-section-title">📅 차기 회의</div>
              <p class="ms-next">{{ minutes.next_meeting_note }}</p>
            </section>
          </template>
        </div>
    </div>
  </BaseModal>
</template>

<style scoped>
.modal-inner { padding: 20px 24px; display: flex; flex-direction: column; gap: 16px; }
.sessions-layout {
  display: flex;
  flex-direction: column;
  height: calc(100vh - var(--header-h) - 40px);
}

.sessions-body {
  flex: 1;
  min-height: 0;
  display: flex;
  gap: 16px;
  overflow: hidden;
}

/* ── 회의 목록 패널 ── */
.sessions-panel {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  min-height: 0;
}

.session-card {
  background: #f8fafc;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 14px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.session-header { display: flex; justify-content: space-between; align-items: flex-start; }
.session-actions { display: flex; gap: 6px; flex-wrap: wrap; }
.session-edit { display: flex; flex-direction: column; }

/* 아젠다 연결 칩 */
.session-agenda-chips { display: flex; flex-wrap: wrap; gap: 4px; margin-top: 6px; }
.session-agenda-chip {
  padding: 2px 8px; border-radius: 99px;
  font-size: 11px; font-weight: 600; color: #fff;
  white-space: nowrap; max-width: 120px;
  overflow: hidden; text-overflow: ellipsis;
}

/* 아젠다 체크리스트 */
.agenda-check-list { display: flex; flex-direction: column; gap: 6px; }
.agenda-check-item {
  display: flex; align-items: center; gap: 8px;
  padding: 6px 10px; border: 1px solid var(--border);
  border-radius: var(--radius); cursor: pointer; font-size: 13px;
  transition: background .12s;
}
.agenda-check-item:hover { background: #f1f5f9; }
.agenda-check-item input[type="checkbox"] { width: 15px; height: 15px; cursor: pointer; flex-shrink: 0; }
.agenda-type-dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
.btn-end-session {
  padding: 4px 10px;
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
.btn-end-session:hover:not(:disabled) { background: var(--danger); color: #fff; }
.btn-end-session:disabled { opacity: .45; cursor: not-allowed; }
.minutes-content { white-space: pre-wrap; font-size: 13px; line-height: 1.7; }

/* ── 회의록 구조적 표시 ── */
.minutes-structured { display: flex; flex-direction: column; gap: 18px; }
.minutes-md :deep(h2), .minutes-md :deep(h3) {
  font-size: 14px; font-weight: 700; margin: 16px 0 8px; color: var(--text);
  padding-bottom: 4px; border-bottom: 1px solid var(--border);
}
.minutes-md :deep(p) { font-size: 13px; line-height: 1.7; margin: 4px 0; }
.minutes-md :deep(ul), .minutes-md :deep(ol) { padding-left: 20px; font-size: 13px; line-height: 1.7; }
.minutes-md :deep(table) { width: 100%; border-collapse: collapse; font-size: 13px; }
.minutes-md :deep(th), .minutes-md :deep(td) { padding: 6px 10px; border: 1px solid var(--border); }
.minutes-md :deep(th) { background: #f9fafb; font-weight: 600; }

.ms-section { border: 1px solid var(--border); border-radius: 8px; overflow: hidden; }
.ms-section-title {
  padding: 10px 14px; background: #f8fafc; font-size: 13px; font-weight: 700;
  color: var(--text); border-bottom: 1px solid var(--border);
}
.ms-attendee-list { padding: 10px 14px; display: flex; flex-direction: column; gap: 6px; }
.ms-attendee { display: flex; align-items: center; gap: 8px; font-size: 13px; }
.ms-att-name { font-weight: 600; }
.ms-att-dept { color: var(--text-muted); font-size: 12px; }
.ms-att-role { background: #f1f5f9; padding: 1px 7px; border-radius: 99px; font-size: 11px; }
.ms-att-status { padding: 1px 8px; border-radius: 99px; font-size: 11px; font-weight: 600; }
.ms-att-status.present { background: #dcfce7; color: #166534; }
.ms-att-status.absent { background: #fef2f2; color: #dc2626; }
.ms-att-note { font-size: 11px; color: var(--text-muted); }

.ms-decision { display: flex; align-items: flex-start; gap: 8px; padding: 8px 14px; font-size: 13px; border-bottom: 1px solid var(--border); }
.ms-decision:last-child { border-bottom: none; }
.ms-dec-num { width: 20px; height: 20px; background: var(--primary); color: #fff; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 11px; font-weight: 700; flex-shrink: 0; }
.ms-dec-content { flex: 1; font-weight: 500; }
.ms-dec-by { color: var(--text-muted); font-size: 12px; white-space: nowrap; }

.ms-action-table { width: 100%; border-collapse: collapse; font-size: 13px; }
.ms-action-table th { padding: 8px 12px; background: #f9fafb; text-align: left; font-size: 12px; color: var(--text-muted); font-weight: 600; border-bottom: 1px solid var(--border); }
.ms-action-table td { padding: 8px 12px; border-bottom: 1px solid var(--border); vertical-align: middle; }
.ms-action-table tr:last-child td { border-bottom: none; }
.ms-status-chip { padding: 2px 8px; border-radius: 99px; font-size: 11px; font-weight: 600; }
.status-pending { background: #fef9c3; color: #a16207; }
.status-done { background: #dcfce7; color: #166534; }
.status-delayed { background: #fef2f2; color: #dc2626; }

.ms-tbd-item { display: flex; align-items: flex-start; gap: 8px; padding: 8px 14px; font-size: 13px; border-bottom: 1px solid var(--border); }
.ms-tbd-item:last-child { border-bottom: none; }
.ms-tbd-dot { color: #f59e0b; font-size: 8px; margin-top: 4px; flex-shrink: 0; }
.ms-tbd-reason { color: var(--text-muted); font-size: 12px; }
.ms-next { padding: 8px 14px; font-size: 13px; color: var(--text); margin: 0; }

/* ── 아라 패널 ── */
.ara-panel {
  display: flex;
  flex-direction: column;
  min-height: 0;
  overflow: hidden;
}

.ara-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 16px 10px;
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
}
.ara-title { display: flex; align-items: center; gap: 10px; }
.ara-avatar {
  width: 38px; height: 38px; border-radius: 50%; object-fit: cover;
  border: 2px solid #fbbf24;
  box-shadow: 0 0 0 3px #fef3c7;
}

/* 빠른 질문 */
.quick-questions {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  padding: 10px 14px;
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
}
.quick-btn {
  font-size: 11px;
  padding: 4px 10px;
  border-radius: 99px;
  border: 1px solid #fbbf24;
  background: #fffbeb;
  color: #92400e;
  cursor: pointer;
  transition: background .15s;
  white-space: nowrap;
}
.quick-btn:hover:not(:disabled) { background: #fef3c7; }
.quick-btn:disabled { opacity: .5; cursor: not-allowed; }

/* 메시지 */
.ara-messages {
  flex: 1;
  overflow-y: auto;
  padding: 14px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.msg-row { display: flex; flex-direction: column; gap: 3px; }
.msg-row.user { align-items: flex-end; }
.msg-row.agent { align-items: flex-start; }

.agent-label {
  display: flex;
  align-items: center;
  gap: 5px;
  font-size: 11px;
  font-weight: 600;
  color: #f59e0b;
  margin-bottom: 2px;
}
.ara-mini { width: 16px; height: 16px; border-radius: 50%; object-fit: cover; }

.bubble {
  padding: 8px 12px;
  border-radius: 12px;
  font-size: 13px;
  line-height: 1.65;
  max-width: 92%;
  word-break: break-word;
}
.ara-bubble {
  background: linear-gradient(135deg, #fef3c7, #fed7aa);
  border: 1px solid #fbbf24;
  color: #92400e;
  border-radius: 2px 12px 12px 12px;
}
.user-bubble {
  background: var(--primary);
  color: #fff;
  border-radius: 12px 12px 2px 12px;
}

/* 타이핑 애니메이션 */
.typing {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 10px 14px;
}
.typing span {
  width: 7px; height: 7px;
  background: #d97706;
  border-radius: 50%;
  animation: bounce 1.2s infinite;
}
.typing span:nth-child(2) { animation-delay: .2s; }
.typing span:nth-child(3) { animation-delay: .4s; }
@keyframes bounce { 0%,80%,100%{transform:translateY(0)} 40%{transform:translateY(-6px)} }

/* 입력창 */
.ara-input-area {
  display: flex;
  gap: 8px;
  padding: 10px 12px;
  border-top: 1px solid var(--border);
  flex-shrink: 0;
}
.ara-input {
  flex: 1;
  resize: none;
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 7px 10px;
  font-size: 13px;
  outline: none;
  font-family: inherit;
  line-height: 1.5;
}
.ara-input:focus { border-color: #fbbf24; box-shadow: 0 0 0 2px #fef3c7; }

.btn-ara {
  background: linear-gradient(135deg, #f59e0b, #ea580c);
  color: #fff;
  border: none;
  border-radius: 8px;
  padding: 6px 14px;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  transition: opacity .15s;
  align-self: flex-end;
}
.btn-ara:disabled { opacity: .45; cursor: not-allowed; }
.btn-ara:not(:disabled):hover { opacity: .88; }
</style>
