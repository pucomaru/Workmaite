<script setup>
import { ref, computed, onMounted } from 'vue'
import { apiAI } from '../api'
import DateInput from './DateInput.vue'

const emit = defineEmits(['close'])

function toDateStr(d) { return d.toISOString().slice(0, 10) }
const today         = toDateStr(new Date())
const thirtyDaysAgo = toDateStr(new Date(Date.now() - 29 * 864e5))

const loading   = ref(false)
const error     = ref('')
const startDate = ref(thirtyDaysAgo)
const endDate   = ref(today)
const dateError = ref('')
const data      = ref(null)

function validate() {
  if (!startDate.value || !endDate.value) { dateError.value = '시작일과 종료일을 모두 입력해 주세요.'; return false }
  if (startDate.value > endDate.value)    { dateError.value = '시작일은 종료일보다 이전이어야 합니다.'; return false }
  dateError.value = ''
  return true
}

async function fetchUsage() {
  if (!validate()) return
  loading.value = true
  error.value   = ''
  try {
    const res = await apiAI.get(`/api/usage/tokens?start_date=${startDate.value}&end_date=${endDate.value}`)
    data.value = res.data
  } catch (e) {
    error.value = e.response?.data?.detail || '사용량을 불러오지 못했습니다.'
  } finally {
    loading.value = false
  }
}
onMounted(fetchUsage)

function fmtNum(n) {
  if (n == null) return '0'
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(2) + 'M'
  if (n >= 1_000)     return (n / 1_000).toFixed(1) + 'K'
  return String(n)
}
function fmtCost(c) {
  if (c == null || c === 0) return '$0.000000'
  return '$' + Number(c).toFixed(6)
}
function fmtMin(s) {
  if (!s) return '0분'
  const m = Math.floor(s / 60), sec = Math.round(s % 60)
  return m ? `${m}분 ${sec}초` : `${sec}초`
}

const MODEL_COLORS = {
  'gpt-4o':        '#10a37f',
  'gpt-4o-mini':   '#6366f1',
  'gpt-4.1':       '#0ea5e9',
  'gpt-4.1-mini':  '#f59e0b',
  'gpt-4.1-nano':  '#8b5cf6',
  'gpt-4-turbo':   '#ef4444',
  'o1':            '#ec4899',
  'o1-mini':       '#14b8a6',
  'o3-mini':       '#f97316',
}
function modelColor(name) {
  const key = Object.keys(MODEL_COLORS).find(k => (name || '').toLowerCase().startsWith(k))
  return key ? MODEL_COLORS[key] : '#64748b'
}

const sections = computed(() => data.value?.sections || null)

const maxModelTokens = computed(() => {
  const list = sections.value?.ai_model?.by_model || []
  return Math.max(...list.map(r => r.total_tokens), 1)
})
</script>

<template>
  <Teleport to="body">
    <div class="app-modal-backdrop" @click.self="emit('close')">
      <div class="app-modal tum-modal">

        <!-- 헤더 -->
        <div class="app-modal-header">
          <div class="app-modal-title" style="display:flex;align-items:center;gap:8px">
            <span style="font-size:18px">📊</span>
            <span>AI 사용량</span>
          </div>
          <button class="app-modal-close" @click="emit('close')">
            <i class="bi bi-x-lg"></i>
          </button>
        </div>

        <!-- 기간 선택 -->
        <div class="tum-daterange">
          <div class="tum-daterange-inputs">
            <div class="app-modal-field">
              <label>시작일</label>
              <DateInput v-model="startDate" class="app-modal-input" style="min-width:130px" :max="endDate" @keydown.enter="fetchUsage"/>
            </div>
            <span class="tum-date-sep">—</span>
            <div class="app-modal-field">
              <label>종료일</label>
              <DateInput v-model="endDate" class="app-modal-input" style="min-width:130px" :min="startDate" @keydown.enter="fetchUsage"/>
            </div>
            <button class="app-btn-primary" :disabled="loading" @click="fetchUsage">
              <span v-if="loading" class="spinner-border spinner-border-sm"></span>
              <i v-else class="bi bi-search"></i>
              조회
            </button>
          </div>
          <div v-if="dateError" class="tum-date-error">{{ dateError }}</div>
        </div>

        <div v-if="loading && !data" class="tum-loading">
          <span class="spinner-border spinner-border-sm me-2" style="color:var(--primary)"></span>불러오는 중...
        </div>
        <div v-else-if="error" class="tum-error">
          <i class="bi bi-exclamation-triangle me-1"></i>{{ error }}
        </div>

        <template v-else-if="data && sections">
          <!-- 요약 카드 -->
          <div class="tum-summary">
            <div class="tum-stat-card">
              <div class="tum-stat-label">기간 중 토큰</div>
              <div class="tum-stat-value">{{ fmtNum(data.period_total_tokens) }}</div>
            </div>
            <div class="tum-stat-card">
              <div class="tum-stat-label">기간 중 비용</div>
              <div class="tum-stat-value cost">{{ fmtCost(data.period_total_cost) }}</div>
            </div>
            <div class="tum-stat-card accent">
              <div class="tum-stat-label">누적 토큰</div>
              <div class="tum-stat-value">{{ fmtNum(data.total_all_time.total_tokens) }}</div>
            </div>
            <div class="tum-stat-card accent">
              <div class="tum-stat-label">누적 비용</div>
              <div class="tum-stat-value cost">{{ fmtCost(data.total_all_time.cost) }}</div>
            </div>
          </div>

          <!-- 섹션 목록 -->
          <div class="tum-sections">

            <!-- ① AI 모델 -->
            <div class="tum-section">
              <div class="tum-section-header">
                <span class="tum-section-icon">🤖</span>
                <span class="tum-section-title">AI 모델</span>
                <span class="tum-section-total">{{ fmtNum(sections.ai_model.total_tokens) }} tokens</span>
                <span class="tum-section-cost">{{ fmtCost(sections.ai_model.cost) }}</span>
              </div>
              <div v-if="!sections.ai_model.by_model.length" class="tum-empty-small">사용 내역 없음</div>
              <div v-else class="tum-model-list">
                <div v-for="row in sections.ai_model.by_model" :key="row.model_name" class="tum-model-row">
                  <div class="tum-gauge-label-row">
                    <span class="tum-model-dot" :style="{ background: modelColor(row.model_name) }"></span>
                    <span class="tum-gauge-name">{{ row.model_name }}</span>
                    <span class="tum-gauge-tokens">{{ fmtNum(row.total_tokens) }}</span>
                    <span class="tum-gauge-cost">{{ fmtCost(row.cost) }}</span>
                  </div>
                  <div class="tum-bar-wrap">
                    <span class="tum-bar-tag">입력</span>
                    <div class="tum-bar-bg">
                      <div class="tum-bar-fill" :style="{ width: (row.prompt_tokens / maxModelTokens * 100) + '%', background: modelColor(row.model_name) }"></div>
                    </div>
                    <span class="tum-bar-num">{{ fmtNum(row.prompt_tokens) }}</span>
                  </div>
                  <div class="tum-bar-wrap">
                    <span class="tum-bar-tag">출력</span>
                    <div class="tum-bar-bg">
                      <div class="tum-bar-fill" :style="{ width: (row.completion_tokens / maxModelTokens * 100) + '%', background: modelColor(row.model_name) + '99' }"></div>
                    </div>
                    <span class="tum-bar-num">{{ fmtNum(row.completion_tokens) }}</span>
                  </div>
                </div>
              </div>
            </div>

            <!-- ② 과제 추출 -->
            <div class="tum-section">
              <div class="tum-section-header">
                <span class="tum-section-icon">✅</span>
                <span class="tum-section-title">과제 추출</span>
                <span class="tum-section-total">{{ fmtNum(sections.task_extraction.total_tokens) }} tokens</span>
                <span class="tum-section-cost">{{ fmtCost(sections.task_extraction.cost) }}</span>
              </div>
              <div class="tum-token-detail">
                <span class="tum-token-chip">입력 {{ fmtNum(sections.task_extraction.prompt_tokens) }}</span>
                <span class="tum-token-chip out">출력 {{ fmtNum(sections.task_extraction.completion_tokens) }}</span>
              </div>
            </div>

            <!-- ③ 보고서 분석 -->
            <div class="tum-section">
              <div class="tum-section-header">
                <span class="tum-section-icon">📄</span>
                <span class="tum-section-title">보고서 분석</span>
                <span class="tum-section-total">{{ fmtNum(sections.report_analysis.total_tokens) }} tokens</span>
                <span class="tum-section-cost">{{ fmtCost(sections.report_analysis.cost) }}</span>
              </div>
              <div class="tum-token-detail">
                <span class="tum-token-chip">입력 {{ fmtNum(sections.report_analysis.prompt_tokens) }}</span>
                <span class="tum-token-chip out">출력 {{ fmtNum(sections.report_analysis.completion_tokens) }}</span>
              </div>
            </div>

            <!-- ④ 회의 -->
            <div class="tum-section">
              <div class="tum-section-header">
                <span class="tum-section-icon">🎙️</span>
                <span class="tum-section-title">회의</span>
                <span class="tum-section-total">{{ fmtNum(sections.meeting.total_tokens) }} tokens</span>
                <span class="tum-section-cost">{{ fmtCost(sections.meeting.total_cost) }}</span>
              </div>
              <!-- STT -->
              <div class="tum-meeting-row">
                <div class="tum-meeting-label">
                  <span class="tum-meeting-icon">🔊</span>
                  <span>STT 처리</span>
                </div>
                <div class="tum-meeting-vals">
                  <span class="tum-meeting-val">{{ fmtMin(sections.meeting.stt_seconds) }}</span>
                  <span class="tum-meeting-meta">{{ sections.meeting.stt_minutes.toFixed(1) }}분 · $0.01/분</span>
                  <span class="tum-meeting-cost">{{ fmtCost(sections.meeting.stt_cost) }}</span>
                </div>
              </div>
              <!-- LLM (회의록·슈퍼바이저) -->
              <div class="tum-meeting-row">
                <div class="tum-meeting-label">
                  <span class="tum-meeting-icon">🤖</span>
                  <span>회의 AI (회의록·어시스턴트)</span>
                </div>
                <div class="tum-meeting-vals">
                  <span class="tum-meeting-val">{{ fmtNum(sections.meeting.total_tokens) }} tokens</span>
                  <div class="tum-token-detail" style="margin:0">
                    <span class="tum-token-chip">입력 {{ fmtNum(sections.meeting.prompt_tokens) }}</span>
                    <span class="tum-token-chip out">출력 {{ fmtNum(sections.meeting.completion_tokens) }}</span>
                  </div>
                  <span class="tum-meeting-cost">{{ fmtCost(sections.meeting.cost) }}</span>
                </div>
              </div>
            </div>

          </div>
        </template>

      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.tum-modal { width: 560px; max-height: 88vh; }

.tum-daterange { padding: 12px 20px 0; flex-shrink: 0; }
.tum-daterange-inputs { display: flex; align-items: flex-end; gap: 8px; flex-wrap: wrap; }
.tum-date-sep { font-size: 14px; color: var(--text-muted, #94a3b8); padding-bottom: 4px; align-self: flex-end; margin-bottom: 8px; }
.tum-date-error { margin-top: 5px; font-size: 11px; color: #ef4444; }

/* 요약 카드 */
.tum-summary { display: grid; grid-template-columns: 1fr 1fr 1fr 1fr; gap: 10px; padding: 14px 20px; flex-shrink: 0; }
.tum-stat-card { background: var(--surface, #f8fafc); border: 1px solid var(--border, #e2e8f0); border-radius: 10px; padding: 10px 12px; }
.tum-stat-card.accent { background: rgba(99,102,241,.06); border-color: rgba(99,102,241,.2); }
.tum-stat-label { font-size: 10px; color: var(--text-muted, #64748b); margin-bottom: 3px; }
.tum-stat-value { font-size: 17px; font-weight: 700; color: var(--text, #1e293b); line-height: 1.1; }
.tum-stat-value.cost { font-size: 13px; }

/* 섹션 */
.tum-sections { overflow-y: auto; flex: 1; padding: 6px 20px 16px; display: flex; flex-direction: column; gap: 10px; }
.tum-section { border: 1px solid var(--border, #e2e8f0); border-radius: 10px; overflow: hidden; }
.tum-section-header {
  display: flex; align-items: center; gap: 7px;
  padding: 9px 13px;
  background: var(--surface, #f8fafc);
  border-bottom: 1px solid var(--border, #e2e8f0);
}
.tum-section-icon { font-size: 14px; flex-shrink: 0; }
.tum-section-title { font-size: 13px; font-weight: 600; color: var(--text, #1e293b); flex: 1; }
.tum-section-total { font-size: 11px; color: var(--text-muted, #64748b); }
.tum-section-cost { font-size: 11px; color: var(--text-muted, #64748b); min-width: 74px; text-align: right; }

/* 모델 리스트 */
.tum-model-list { padding: 8px 13px 10px; display: flex; flex-direction: column; gap: 10px; }
.tum-model-row { display: flex; flex-direction: column; gap: 4px; }
.tum-gauge-label-row { display: flex; align-items: center; gap: 7px; font-size: 12px; }
.tum-model-dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
.tum-gauge-name { font-weight: 600; color: var(--text, #1e293b); flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.tum-gauge-tokens { font-size: 11px; color: var(--text-muted, #64748b); }
.tum-gauge-cost { font-size: 11px; color: var(--text-muted, #64748b); min-width: 72px; text-align: right; }
.tum-bar-wrap { display: flex; align-items: center; gap: 7px; }
.tum-bar-tag { font-size: 10px; color: var(--text-muted, #94a3b8); width: 22px; flex-shrink: 0; text-align: right; }
.tum-bar-bg { flex: 1; height: 7px; border-radius: 4px; background: var(--surface-2, #f1f5f9); overflow: hidden; }
.tum-bar-fill { height: 100%; border-radius: 4px; transition: width .5s cubic-bezier(.4,0,.2,1); }
.tum-bar-num { font-size: 10px; color: var(--text-muted, #64748b); min-width: 38px; text-align: right; }

/* 토큰 칩 */
.tum-token-detail { display: flex; gap: 6px; padding: 6px 13px 8px; flex-wrap: wrap; }
.tum-token-chip {
  font-size: 11px; padding: 2px 8px; border-radius: 20px;
  background: rgba(99,102,241,.1); color: #6366f1;
}
.tum-token-chip.out { background: rgba(99,102,241,.05); color: #94a3b8; }

/* 회의 섹션 행 */
.tum-meeting-row {
  display: flex; align-items: flex-start; justify-content: space-between;
  padding: 7px 13px;
  border-top: 1px solid var(--border, #f1f5f9);
  gap: 8px;
}
.tum-meeting-label { display: flex; align-items: center; gap: 5px; font-size: 12px; color: var(--text-muted, #64748b); min-width: 130px; flex-shrink: 0; }
.tum-meeting-icon { font-size: 12px; }
.tum-meeting-vals { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; justify-content: flex-end; flex: 1; }
.tum-meeting-val { font-size: 12px; font-weight: 600; color: var(--text, #1e293b); }
.tum-meeting-meta { font-size: 10px; color: var(--text-muted, #94a3b8); }
.tum-meeting-cost { font-size: 11px; color: var(--text-muted, #64748b); min-width: 74px; text-align: right; }

.tum-empty-small { padding: 8px 13px; font-size: 12px; color: var(--text-muted, #94a3b8); }
.tum-loading, .tum-error { text-align: center; padding: 36px 20px; font-size: 13px; color: var(--text-muted, #64748b); }
.tum-error { color: #ef4444; }
</style>
