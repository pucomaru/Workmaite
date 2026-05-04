<script setup>
import { ref, onMounted, computed } from 'vue'
import { useRouter } from 'vue-router'
import api from '../api'
import { renderMd } from '../composables/useMarkdown'

const router = useRouter()
const minutes = ref([])
const loading = ref(true)
const search = ref('')
const selectedMeeting = ref('')
const expandedId = ref(null)

onMounted(async () => {
  try {
    const { data } = await api.get('/api/all-minutes')
    minutes.value = data
  } finally {
    loading.value = false
  }
})

const meetingOptions = computed(() => {
  const seen = new Set()
  return minutes.value
    .map(m => ({ id: m.meeting_id, title: m.meeting_title }))
    .filter(m => { if (seen.has(m.id)) return false; seen.add(m.id); return true })
})

const filtered = computed(() =>
  minutes.value.filter(m => {
    const matchSearch = !search.value ||
      m.meeting_title.toLowerCase().includes(search.value.toLowerCase()) ||
      (m.session_title || '').toLowerCase().includes(search.value.toLowerCase()) ||
      (m.content_summary || '').toLowerCase().includes(search.value.toLowerCase())
    const matchMeeting = !selectedMeeting.value || m.meeting_id == selectedMeeting.value
    return matchSearch && matchMeeting
  })
)

function formatDate(d) {
  if (!d) return '-'
  return new Date(d).toLocaleDateString('ko-KR', { year: 'numeric', month: 'short', day: 'numeric' })
}

function toggleExpand(id) {
  expandedId.value = expandedId.value === id ? null : id
}

async function deleteMinutes(m) {
  if (!confirm(`${m.session_number}싰 회의 "${m.session_title || m.meeting_title}" 회의록을 삭제하시겠습니까?\n회의 세션과 연관된 정보가 모두 삭제됩니다.`)) return
  try {
    await api.delete(`/api/sessions/${m.session_id}`)
    minutes.value = minutes.value.filter(x => x.session_id !== m.session_id)
  } catch (e) {
    alert(e?.response?.data?.detail || '삭제 중 오류가 발생했습니다.')
  }
}
</script>

<template>
  <div class="page-wrap">
    <div class="page-header">
      <div>
        <h1 class="page-title">📋 전체 회의록</h1>
        <p class="page-desc">참여 중인 모든 회의체의 회의록을 확인합니다.</p>
      </div>
    </div>

    <div class="filter-bar">
      <input v-model="search" class="form-input" placeholder="회의체명, 회의 제목, 내용 검색..." style="flex:1;max-width:320px" />
      <select v-model="selectedMeeting" class="form-input" style="max-width:200px">
        <option value="">전체 회의체</option>
        <option v-for="m in meetingOptions" :key="m.id" :value="m.id">{{ m.title }}</option>
      </select>
    </div>

    <div v-if="loading" class="empty-state">불러오는 중...</div>
    <div v-else-if="!filtered.length" class="empty-state">
      <p>{{ search || selectedMeeting ? '검색 결과가 없습니다.' : '회의록이 없습니다.' }}</p>
    </div>

    <div v-else class="minutes-list">
      <div
        v-for="m in filtered"
        :key="m.minutes_id"
        class="minutes-card fade-in"
      >
        <div class="minutes-card-header" @click="toggleExpand(m.minutes_id)">
          <div class="minutes-meta">
            <span class="badge badge-primary" style="font-size:11px">{{ m.meeting_title }}</span>
            <span class="minutes-session">{{ m.session_number }}차 회의</span>
            <span v-if="m.session_title" class="minutes-session-title">— {{ m.session_title }}</span>
            <span v-if="m.session_location" class="minutes-location">📍 {{ m.session_location }}</span>
          </div>
          <div style="display:flex;align-items:center;gap:12px">
            <span class="minutes-date">{{ formatDate(m.ended_at) }}</span>
            <svg
              width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"
              :style="{ transform: expandedId === m.minutes_id ? 'rotate(180deg)' : '', transition: 'transform .2s' }"
            ><path d="M19 9l-7 7-7-7"/></svg>
          </div>
        </div>

        <div v-if="expandedId === m.minutes_id" class="minutes-body fade-in">

          <!-- TPO 요약 헤더 -->
          <div class="minutes-tpo-bar">
            <span v-if="m.meeting_purpose">🎯 {{ m.meeting_purpose }}</span>
            <span v-if="m.started_at">🕒 {{ formatDate(m.started_at) }} ~ {{ formatDate(m.ended_at) }}</span>
            <span v-if="m.session_location">📍 {{ m.session_location }}</span>
          </div>

          <!-- AI 생성 마크다운 -->
          <div v-if="m.content_summary" class="minutes-md" v-html="renderMd(m.content_summary)"></div>

          <!-- 구조적 데이터 (요약문이 없어도 렌더링) -->
          <div class="minutes-structured">

            <!-- Joiner -->
            <section v-if="m.attendees_json?.length" class="ms-section">
              <div class="ms-section-title">👥 참석자 (Joiner)</div>
              <div class="ms-attendee-list">
                <div v-for="a in m.attendees_json" :key="a.name" class="ms-attendee">
                  <span class="ms-att-name">{{ a.name }}</span>
                  <span class="ms-att-dept">{{ a.dept }}</span>
                  <span class="ms-att-status" :class="a.present !== false ? 'present' : 'absent'">{{ a.present !== false ? '참석' : '불참' }}</span>
                  <span v-if="a.note" class="ms-att-note">({{ a.note }})</span>
                </div>
              </div>
            </section>

            <!-- Done -->
            <section v-if="m.decisions_json?.length" class="ms-section">
              <div class="ms-section-title">✅ 결정 사항 (Done)</div>
              <div v-for="(d, i) in m.decisions_json" :key="i" class="ms-decision">
                <span class="ms-dec-num">{{ i+1 }}</span>
                <span class="ms-dec-content">{{ d.content }}</span>
                <span v-if="d.decided_by" class="ms-dec-by">— {{ d.decided_by }}</span>
              </div>
            </section>

            <!-- WILL DO -->
            <section v-if="m.action_items_json?.length" class="ms-section">
              <div class="ms-section-title">📌 실행 계획 (WILL DO)</div>
              <table class="ms-action-table">
                <thead><tr><th>업무</th><th>담당자</th><th>기한</th><th>상태</th></tr></thead>
                <tbody>
                  <tr v-for="(a, i) in m.action_items_json" :key="i">
                    <td>{{ a.content }}</td>
                    <td>{{ a.assignee || '-' }}</td>
                    <td>{{ a.due_date || '-' }}</td>
                    <td><span class="ms-status-chip" :class="'status-' + (a.status || 'pending')">{{ {pending:'대기',done:'완료',delayed:'지연'}[a.status] || a.status }}</span></td>
                  </tr>
                </tbody>
              </table>
            </section>

            <!-- TBD -->
            <section v-if="m.tbd_items_json?.length" class="ms-section">
              <div class="ms-section-title">⚠️ 미결 안건 (TBD)</div>
              <div v-for="(t, i) in m.tbd_items_json" :key="i" class="ms-tbd-item">
                <span class="ms-tbd-dot">●</span>
                <span>{{ t.content }}</span>
                <span v-if="t.reason" class="ms-tbd-reason">— {{ t.reason }}</span>
              </div>
            </section>

            <!-- Next -->
            <section v-if="m.next_meeting_note" class="ms-section">
              <div class="ms-section-title">📅 차기 회의</div>
              <p class="ms-next">{{ m.next_meeting_note }}</p>
            </section>

            <!-- fallback: raw -->
            <div v-if="!m.content_summary && !m.attendees_json?.length && !m.decisions_json?.length" class="minutes-raw">
              <div class="summary-label">🎥 녹취 원문</div>
              <pre class="raw-content">{{ m.content_raw || '회의록 내용이 없습니다.' }}</pre>
            </div>
          </div>

          <div style="margin-top:12px;text-align:right;display:flex;justify-content:flex-end;gap:8px">
            <button class="btn btn-ghost btn-sm" style="color:var(--danger)" @click.stop="deleteMinutes(m)">
              회의록 삭제
            </button>
            <button class="btn btn-outline btn-sm" @click="router.push(`/meetings/${m.meeting_id}/sessions`)">
              해당 회의체로 이동 →
            </button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.page-wrap { padding: 28px 32px; max-width: 900px; margin: 0 auto; }
.page-header { display: flex; align-items: flex-start; justify-content: space-between; margin-bottom: 20px; }
.page-title { font-size: 22px; font-weight: 700; margin: 0 0 4px; }
.page-desc { font-size: 13px; color: var(--text-muted); margin: 0; }
.filter-bar { display: flex; gap: 10px; margin-bottom: 18px; flex-wrap: wrap; }
.minutes-list { display: flex; flex-direction: column; gap: 10px; }
.minutes-card { background: #fff; border: 1px solid var(--border); border-radius: var(--radius); overflow: hidden; }
.minutes-card-header { display: flex; align-items: center; justify-content: space-between; padding: 14px 16px; cursor: pointer; transition: background .15s; }
.minutes-card-header:hover { background: #f8fafc; }
.minutes-meta { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.minutes-session { font-weight: 600; font-size: 13px; }
.minutes-session-title { font-size: 13px; color: var(--text-muted); }
.minutes-date { font-size: 12px; color: var(--text-muted); white-space: nowrap; }
.minutes-body { padding: 0 16px 16px; border-top: 1px solid var(--border); background: #fafbfc; }
.summary-label { font-size: 11px; font-weight: 600; color: var(--text-muted); text-transform: uppercase; letter-spacing: .05em; margin: 14px 0 8px; }
.summary-content { font-size: 13px; line-height: 1.7; color: var(--text); white-space: pre-wrap; }
.raw-content { font-size: 12px; line-height: 1.6; color: var(--text-muted); background: #f1f5f9; border-radius: 6px; padding: 12px; white-space: pre-wrap; word-break: break-all; max-height: 300px; overflow-y: auto; }

/* ── TPO 바 ── */
.minutes-tpo-bar {
  display: flex; gap: 12px; flex-wrap: wrap;
  padding: 10px 0; margin-bottom: 4px;
  font-size: 12px; color: var(--text-muted);
  border-bottom: 1px solid var(--border);
}
.minutes-location { font-size: 12px; color: var(--text-muted); }

/* ── 마크다운 요약 ── */
.minutes-md :deep(h2), .minutes-md :deep(h3) {
  font-size: 13px; font-weight: 700; margin: 16px 0 6px; color: var(--text);
  padding-bottom: 3px; border-bottom: 1px solid var(--border);
}
.minutes-md :deep(p) { font-size: 13px; line-height: 1.7; margin: 4px 0; }
.minutes-md :deep(ul), .minutes-md :deep(ol) { padding-left: 18px; font-size: 13px; line-height: 1.7; }
.minutes-md :deep(table) { width: 100%; border-collapse: collapse; font-size: 12px; margin: 8px 0; }
.minutes-md :deep(th), .minutes-md :deep(td) { padding: 5px 8px; border: 1px solid var(--border); }
.minutes-md :deep(th) { background: #f9fafb; font-weight: 600; }

/* ── 구조적 섹션 ── */
.minutes-structured { display: flex; flex-direction: column; gap: 12px; margin-top: 12px; }
.ms-section { border: 1px solid var(--border); border-radius: 8px; overflow: hidden; }
.ms-section-title { padding: 8px 12px; background: #f8fafc; font-size: 12px; font-weight: 700; color: var(--text); border-bottom: 1px solid var(--border); }
.ms-attendee-list { padding: 8px 12px; display: flex; flex-direction: column; gap: 5px; }
.ms-attendee { display: flex; align-items: center; gap: 8px; font-size: 12px; }
.ms-att-name { font-weight: 600; }
.ms-att-dept { color: var(--text-muted); font-size: 11px; }
.ms-att-status { padding: 1px 7px; border-radius: 99px; font-size: 11px; font-weight: 600; }
.ms-att-status.present { background: #dcfce7; color: #166534; }
.ms-att-status.absent { background: #fef2f2; color: #dc2626; }
.ms-att-note { font-size: 11px; color: var(--text-muted); }
.ms-decision { display: flex; align-items: flex-start; gap: 8px; padding: 7px 12px; font-size: 12px; border-bottom: 1px solid var(--border); }
.ms-decision:last-child { border-bottom: none; }
.ms-dec-num { width: 18px; height: 18px; background: var(--primary); color: #fff; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 10px; font-weight: 700; flex-shrink: 0; }
.ms-dec-content { flex: 1; }
.ms-dec-by { color: var(--text-muted); font-size: 11px; white-space: nowrap; }
.ms-action-table { width: 100%; border-collapse: collapse; font-size: 12px; }
.ms-action-table th { padding: 6px 10px; background: #f9fafb; text-align: left; font-size: 11px; color: var(--text-muted); font-weight: 600; border-bottom: 1px solid var(--border); }
.ms-action-table td { padding: 6px 10px; border-bottom: 1px solid var(--border); vertical-align: middle; }
.ms-action-table tr:last-child td { border-bottom: none; }
.ms-status-chip { padding: 1px 7px; border-radius: 99px; font-size: 11px; font-weight: 600; }
.status-pending { background: #fef9c3; color: #a16207; }
.status-done { background: #dcfce7; color: #166534; }
.status-delayed { background: #fef2f2; color: #dc2626; }
.ms-tbd-item { display: flex; align-items: flex-start; gap: 8px; padding: 7px 12px; font-size: 12px; border-bottom: 1px solid var(--border); }
.ms-tbd-item:last-child { border-bottom: none; }
.ms-tbd-dot { color: #f59e0b; font-size: 8px; margin-top: 3px; flex-shrink: 0; }
.ms-tbd-reason { color: var(--text-muted); font-size: 11px; }
.ms-next { padding: 8px 12px; font-size: 12px; color: var(--text); margin: 0; }
</style>
