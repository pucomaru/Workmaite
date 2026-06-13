<script setup>
import { ref, computed, onMounted } from 'vue'
import { apiAI } from '../api'
import DateInput from './DateInput.vue'

const emit = defineEmits(['close'])

function toDateStr(d) {
  return d.toISOString().slice(0, 10)
}
const today = toDateStr(new Date())
const thirtyDaysAgo = toDateStr(new Date(Date.now() - 29 * 864e5))

const loading = ref(false)
const error = ref('')
const startDate = ref(thirtyDaysAgo)
const endDate = ref(today)
const dateError = ref('')
const data = ref(null)

function validate() {
  if (!startDate.value || !endDate.value) {
    dateError.value = '시작일과 종료일을 모두 입력해 주세요.'
    return false
  }
  if (startDate.value > endDate.value) {
    dateError.value = '시작일은 종료일보다 이전이어야 합니다.'
    return false
  }
  dateError.value = ''
  return true
}

async function fetchUsage() {
  if (!validate()) return
  loading.value = true
  error.value = ''
  try {
    const res = await apiAI.get(
      `/api/usage/tokens?start_date=${startDate.value}&end_date=${endDate.value}`,
    )
    data.value = res.data
  } catch (e) {
    error.value = e.response?.data?.detail || '사용량을 불러오지 못했습니다.'
  } finally {
    loading.value = false
  }
}
onMounted(fetchUsage)

function fmtNum(n) {
  if (!n) return '0'
  if (n >= 1_000_000) return (n / 1e6).toFixed(2) + 'M'
  if (n >= 1_000) return (n / 1e3).toFixed(1) + 'K'
  return String(n)
}
function fmtCost(c) {
  const n = Number(c) || 0
  if (n === 0) return '$0'
  if (n < 0.0001) return '$' + n.toFixed(6)
  if (n < 0.01) return '$' + n.toFixed(4)
  return '$' + n.toFixed(2)
}
function fmtMin(s) {
  if (!s) return '0분'
  const m = Math.floor(s / 60),
    sec = Math.round(s % 60)
  return m ? `${m}분 ${sec}초` : `${sec}초`
}

const MODEL_COLORS = {
  'gpt-4o': '#10a37f',
  'gpt-4o-mini': '#6366f1',
  'gpt-4.1': '#0ea5e9',
  'gpt-4.1-mini': '#f59e0b',
  'gpt-4.1-nano': '#8b5cf6',
  'gpt-4-turbo': '#ef4444',
  o1: '#ec4899',
  'o1-mini': '#14b8a6',
  'o3-mini': '#f97316',
}
function modelColor(name) {
  const k = Object.keys(MODEL_COLORS).find(k => (name || '').toLowerCase().startsWith(k))
  return k ? MODEL_COLORS[k] : '#64748b'
}

const sec = computed(() => data.value?.sections || null)
</script>

<template>
  <Teleport to="body">
    <div class="app-modal-backdrop" @click.self="emit('close')">
      <div class="app-modal tum-modal">
        <div class="app-modal-header">
          <div class="app-modal-title">📊 AI 사용량</div>
          <button class="app-modal-close" @click="emit('close')"><i class="bi bi-x-lg" /></button>
        </div>

        <!-- 기간 선택 -->
        <div class="tum-date-bar">
          <div class="app-modal-field" style="flex: 1; min-width: 0">
            <label>시작일</label>
            <DateInput
              v-model="startDate"
              class="app-modal-input"
              :max="endDate"
              @keydown.enter="fetchUsage"
            />
          </div>
          <span class="tum-sep">—</span>
          <div class="app-modal-field" style="flex: 1; min-width: 0">
            <label>종료일</label>
            <DateInput
              v-model="endDate"
              class="app-modal-input"
              :min="startDate"
              @keydown.enter="fetchUsage"
            />
          </div>
          <button
            class="app-btn-primary"
            style="align-self: flex-end"
            :disabled="loading"
            @click="fetchUsage"
          >
            <span v-if="loading" class="spinner-border spinner-border-sm" />
            <i v-else class="bi bi-search" /> 조회
          </button>
        </div>
        <p v-if="dateError" class="tum-date-err">{{ dateError }}</p>

        <div v-if="loading && !data" class="tum-placeholder">
          <span class="spinner-border spinner-border-sm me-2" />불러오는 중...
        </div>
        <div v-else-if="error" class="tum-placeholder" style="color: #ef4444">
          <i class="bi bi-exclamation-triangle me-1" />{{ error }}
        </div>

        <template v-else-if="data && sec">
          <!-- 요약 통계 바 -->
          <div class="tum-stats-bar">
            <div class="tum-stat">
              <span class="tum-stat-val">{{ fmtNum(data.period_total_tokens) }}</span>
              <span class="tum-stat-lbl">기간 토큰</span>
            </div>
            <div class="tum-stat-sep" />
            <div class="tum-stat">
              <span class="tum-stat-val tum-accent">{{ fmtCost(data.period_grand_cost) }}</span>
              <span class="tum-stat-lbl">기간 비용</span>
            </div>
            <div class="tum-stat-sep" />
            <div class="tum-stat">
              <span class="tum-stat-val">{{ fmtNum(data.total_all_time.total_tokens) }}</span>
              <span class="tum-stat-lbl">누적 토큰</span>
            </div>
            <div class="tum-stat-sep" />
            <div class="tum-stat">
              <span class="tum-stat-val tum-accent">{{ fmtCost(data.total_all_time.cost) }}</span>
              <span class="tum-stat-lbl">누적 비용</span>
            </div>
          </div>

          <div class="app-modal-body">
            <div class="app-modal-field">
              <label>🤖 AI 사용</label>
              <div v-if="!sec.ai_model.by_model.length" class="tum-m-row">
                <span style="font-size: 12px; color: var(--text-muted, #94a3b8)"
                  >사용 내역 없음</span
                >
              </div>
              <template v-for="model in sec.ai_model.by_model" :key="model.model_name">
                <!-- 모델 행 -->
                <div class="tum-m-row tum-model-row">
                  <span
                    class="tum-model-dot"
                    :style="{ background: modelColor(model.model_name) }"
                  />
                  <span class="tum-m-desc" style="font-weight: 600">{{ model.model_name }}</span>
                  <span class="tum-m-note">{{ fmtNum(model.total_tokens) }} tokens</span>
                  <span class="tum-m-cost">{{ fmtCost(model.cost) }}</span>
                </div>
                <!-- 컨텍스트 하위 행 -->
                <div
                  v-for="ctx in model.by_context"
                  :key="ctx.section"
                  class="tum-m-row tum-ctx-row"
                >
                  <span class="tum-ctx-indent" />
                  <span class="tum-chip" :class="`ctx-${ctx.section}`">{{ ctx.label }}</span>
                  <span class="tum-m-desc">{{ fmtNum(ctx.total_tokens) }} tokens</span>
                  <span class="tum-m-cost">{{ fmtCost(ctx.cost) }}</span>
                </div>
              </template>
              <div v-if="sec.ai_model.by_model.length" class="tum-m-total">
                <span>AI 비용 합계</span>
                <span class="tum-accent">{{ fmtCost(sec.ai_model.cost) }}</span>
              </div>
            </div>

            <!-- ② STT (제공자별) -->
            <div class="app-modal-field">
              <label>🎙️ STT</label>
              <div v-if="!sec.stt.by_provider.length" class="tum-m-row">
                <span style="font-size: 12px; color: var(--text-muted, #94a3b8)"
                  >사용 내역 없음</span
                >
              </div>
              <div v-for="p in sec.stt.by_provider" :key="p.provider" class="tum-m-row">
                <span class="tum-chip" :class="`stt-${p.provider}`">{{ p.label }}</span>
                <span class="tum-m-desc">{{ fmtMin(p.seconds) }}</span>
                <span class="tum-m-note">
                  {{ p.minutes.toFixed(1) }}분 ·
                  {{ p.cost_per_min > 0 ? `$${p.cost_per_min}/분` : '무료' }}
                </span>
                <span class="tum-m-cost">{{ fmtCost(p.cost) }}</span>
              </div>
              <div v-if="sec.stt.by_provider.length" class="tum-m-total">
                <span>STT 비용 합계</span>
                <span class="tum-accent">{{ fmtCost(sec.stt.total_cost) }}</span>
              </div>
            </div>
          </div>
        </template>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.tum-modal {
  width: 520px;
}

/* ── 기간 입력 ── */
.tum-date-bar {
  display: flex;
  align-items: flex-end;
  gap: 8px;
  padding: 12px 20px 10px;
  flex-shrink: 0;
  border-bottom: 1px solid var(--border, #e2e8f0);
}
.tum-sep {
  padding-bottom: 10px;
  color: var(--text-muted, var(--dark-muted));
}
.tum-date-err {
  margin: 4px 20px 0;
  font-size: 11px;
  color: var(--danger);
}
.tum-placeholder {
  text-align: center;
  padding: 40px 20px;
  font-size: 13px;
  color: var(--text-muted, var(--text-muted));
}

/* ── 요약 바 ── */
.tum-stats-bar {
  display: flex;
  align-items: center;
  justify-content: space-around;
  padding: 12px 20px;
  background: var(--surface, var(--surface));
  border-bottom: 1px solid var(--border, #e2e8f0);
  flex-shrink: 0;
}
.tum-stat {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 3px;
}
.tum-stat-val {
  font-size: 16px;
  font-weight: 700;
  color: var(--text, var(--dark-card));
  line-height: 1;
}
.tum-stat-lbl {
  font-size: 10px;
  color: var(--text-muted, var(--text-muted));
  text-transform: uppercase;
  letter-spacing: 0.04em;
}
.tum-stat-sep {
  width: 1px;
  height: 32px;
  background: var(--border, #e2e8f0);
}
.tum-accent {
  color: var(--accent, var(--accent)) !important;
}

/* ── 공통 행 ── */
.tum-m-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 7px 0;
  border-bottom: 1px solid var(--border, #e2e8f0);
  font-size: 12px;
}
.tum-model-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}

/* ── 컨텍스트 하위 행 ── */
.tum-ctx-row {
  background: var(--surface, var(--surface));
}
.tum-ctx-indent {
  width: 16px;
  flex-shrink: 0;
}

/* ── 칩 ── */
.tum-chip {
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.03em;
  padding: 2px 7px;
  border-radius: 99px;
  flex-shrink: 0;
  white-space: nowrap;
}
/* 컨텍스트 칩 */
.tum-chip.ctx-task_extraction {
  background: #d1fae5;
  color: #065f46;
}
.tum-chip.ctx-report_analysis {
  background: #ede9fe;
  color: #5b21b6;
}
.tum-chip.ctx-meeting {
  background: var(--warning-bg);
  color: #92400e;
}
.tum-chip.ctx-other {
  background: var(--surface-2);
  color: var(--text-muted);
}
/* STT 칩 */
.tum-chip.stt-gcapi {
  background: var(--accent-bg-2);
  color: var(--accent-strong);
}
.tum-chip.stt-whisperapi {
  background: var(--warning-bg);
  color: #92400e;
}
.tum-chip.stt-localwhisper {
  background: #d1fae5;
  color: #065f46;
}

/* ── 행 내 텍스트 ── */
.tum-m-desc {
  flex: 1;
  font-weight: 500;
  color: var(--text, var(--dark-card));
}
.tum-m-note {
  font-size: 11px;
  color: var(--text-muted, var(--text-muted));
  white-space: nowrap;
}
.tum-m-cost {
  width: 64px;
  text-align: right;
  font-weight: 600;
  color: var(--text, var(--dark-card));
  flex-shrink: 0;
}

/* ── 합계 행 ── */
.tum-m-total {
  display: flex;
  justify-content: space-between;
  padding: 8px 0 2px;
  font-size: 12px;
  font-weight: 700;
  color: var(--text, var(--dark-card));
}
</style>

<style>
/* ── 나이트 모드 ── */
html.night-mode .tum-stats-bar {
  background: var(--white-03) !important;
}
html.night-mode .tum-ctx-row {
  background: rgba(255, 255, 255, 0.02) !important;
}
html.night-mode .tum-chip.ctx-task_extraction {
  background: rgba(16, 185, 129, 0.15) !important;
  color: #6ee7b7 !important;
}
html.night-mode .tum-chip.ctx-report_analysis {
  background: rgba(139, 92, 246, 0.15) !important;
  color: #c4b5fd !important;
}
html.night-mode .tum-chip.ctx-meeting {
  background: rgba(245, 158, 11, 0.15) !important;
  color: #fcd34d !important;
}
html.night-mode .tum-chip.stt-gcapi {
  background: rgba(147, 197, 253, 0.15) !important;
  color: var(--accent-soft) !important;
}
html.night-mode .tum-chip.stt-whisperapi {
  background: rgba(251, 191, 36, 0.15) !important;
  color: #fcd34d !important;
}
html.night-mode .tum-chip.stt-localwhisper {
  background: rgba(16, 185, 129, 0.15) !important;
  color: #6ee7b7 !important;
}
</style>
