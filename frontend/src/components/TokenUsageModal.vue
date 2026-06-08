<script setup>
import { ref, computed, onMounted } from 'vue'
import { apiAI } from '../api'

const emit = defineEmits(['close'])

// ── 날짜 유틸 ──────────────────────────────────────────────────────────────
function toDateStr(d) { return d.toISOString().slice(0, 10) }
const today        = toDateStr(new Date())
const thirtyDaysAgo = toDateStr(new Date(Date.now() - 29 * 864e5))

// ── 상태 ───────────────────────────────────────────────────────────────────
const loading   = ref(false)
const error     = ref('')
const startDate = ref(thirtyDaysAgo)
const endDate   = ref(today)
const dateError = ref('')
const data      = ref(null)
const activeTab = ref('model') // 'model' | 'context'

// ── 유효성 ─────────────────────────────────────────────────────────────────
function validate() {
  if (!startDate.value || !endDate.value) { dateError.value = '시작일과 종료일을 모두 입력해 주세요.'; return false }
  if (startDate.value > endDate.value)    { dateError.value = '시작일은 종료일보다 이전이어야 합니다.'; return false }
  dateError.value = ''
  return true
}

// ── 조회 ───────────────────────────────────────────────────────────────────
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

// ── 숫자 포맷 ──────────────────────────────────────────────────────────────
function fmtNum(n) {
  if (n == null) return '0'
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(2) + 'M'
  if (n >= 1_000)     return (n / 1_000).toFixed(1) + 'K'
  return String(n)
}
function fmtCost(c) {
  if (c == null || c === 0) return '$0.000000'
  return '$' + c.toFixed(6)
}

// ── 게이지 계산 ───────────────────────────────────────────────────────────
const maxTokens = computed(() => {
  if (!data.value) return 1
  const list = activeTab.value === 'model' ? data.value.by_model : data.value.by_context
  return Math.max(...(list || []).map(r => r.total_tokens), 1)
})

function promptPct(row) {
  return maxTokens.value ? (row.prompt_tokens / maxTokens.value) * 100 : 0
}
function completionPct(row) {
  return maxTokens.value ? (row.completion_tokens / maxTokens.value) * 100 : 0
}

// ── context_type 한글 라벨 ──────────────────────────────────────────────
const CONTEXT_LABELS = {
  archive_analyze:   '자료 분석',
  minutes_stream:    '회의록 생성',
  task_extract:      '작업 추출',
  report_review:     '보고서 검토',
  knowledge_manager: '지식 관리',
  supervisor:        '슈퍼바이저',
  chat:              '채팅',
}
function contextLabel(type) {
  return CONTEXT_LABELS[type] || type
}

// ── 모델 색상 ──────────────────────────────────────────────────────────────
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

</script>

<template>
  <Teleport to="body">
    <div class="app-modal-backdrop" @click.self="emit('close')">
      <div class="app-modal tum-modal">

        <!-- 헤더 -->
        <div class="app-modal-header">
          <div class="app-modal-title" style="display:flex;align-items:center;gap:8px">
            <span style="font-size:18px">📊</span>
            <span>토큰 사용량</span>
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
              <input
                v-model="startDate"
                type="date"
                class="app-modal-input"
                style="min-width:130px"
                :max="endDate"
                @keydown.enter="fetchUsage"
              />
            </div>
            <span class="tum-date-sep">—</span>
            <div class="app-modal-field">
              <label>종료일</label>
              <input
                v-model="endDate"
                type="date"
                class="app-modal-input"
                style="min-width:130px"
                :min="startDate"
                @keydown.enter="fetchUsage"
              />
            </div>
            <button
              class="app-btn-primary"
              :disabled="loading"
              @click="fetchUsage"
            >
              <span v-if="loading" class="spinner-border spinner-border-sm"></span>
              <i v-else class="bi bi-search"></i>
              조회
            </button>
          </div>
          <div v-if="dateError" class="tum-date-error">{{ dateError }}</div>
        </div>

        <!-- 로딩 -->
        <div v-if="loading && !data" class="tum-loading">
          <span class="spinner-border spinner-border-sm me-2" style="color:var(--primary)"></span>
          불러오는 중...
        </div>

        <!-- 에러 -->
        <div v-else-if="error" class="tum-error">
          <i class="bi bi-exclamation-triangle me-1"></i>{{ error }}
        </div>

        <!-- 콘텐츠 -->
        <template v-else-if="data">

          <!-- 요약 카드 -->
          <div class="tum-summary">
            <div class="tum-stat-card">
              <div class="tum-stat-label">기간 중 사용 토큰</div>
              <div class="tum-stat-value">{{ fmtNum(data.period_total_tokens) }}</div>
            </div>
            <div class="tum-stat-card">
              <div class="tum-stat-label">기간 중 비용</div>
              <div class="tum-stat-value cost">{{ fmtCost(data.period_total_cost) }}</div>
            </div>
            <div class="tum-stat-card accent">
              <div class="tum-stat-label">누적 사용 토큰</div>
              <div class="tum-stat-value">{{ fmtNum(data.total_all_time.total_tokens) }}</div>
            </div>
            <div class="tum-stat-card accent">
              <div class="tum-stat-label">누적 비용</div>
              <div class="tum-stat-value cost">{{ fmtCost(data.total_all_time.cost) }}</div>
            </div>
          </div>

          <!-- 탭 -->
          <div class="tum-tabs">
            <button
              class="tum-tab"
              :class="{ active: activeTab === 'model' }"
              @click="activeTab = 'model'"
            >모델별</button>
            <button
              class="tum-tab"
              :class="{ active: activeTab === 'context' }"
              @click="activeTab = 'context'"
            >에이전트별</button>
          </div>

          <!-- 모델별 게이지 -->
          <div v-if="activeTab === 'model'" class="tum-gauge-list">
            <div v-if="!data.by_model.length" class="tum-empty">
              이 기간에 사용 내역이 없습니다.
            </div>
            <div
              v-for="row in data.by_model"
              :key="row.model_name"
              class="tum-gauge-row"
            >
              <div class="tum-gauge-label-row">
                <span class="tum-model-dot" :style="{ background: modelColor(row.model_name) }"></span>
                <span class="tum-gauge-name">{{ row.model_name }}</span>
                <span class="tum-gauge-tokens">{{ fmtNum(row.total_tokens) }} tokens</span>
                <span class="tum-gauge-cost">{{ fmtCost(row.cost) }}</span>
              </div>
              <!-- 프롬프트 게이지 -->
              <div class="tum-bar-wrap">
                <span class="tum-bar-tag">입력</span>
                <div class="tum-bar-bg">
                  <div
                    class="tum-bar-fill prompt"
                    :style="{
                      width: promptPct(row) + '%',
                      background: modelColor(row.model_name),
                    }"
                  ></div>
                </div>
                <span class="tum-bar-num">{{ fmtNum(row.prompt_tokens) }}</span>
              </div>
              <!-- 컴플리션 게이지 -->
              <div class="tum-bar-wrap">
                <span class="tum-bar-tag">출력</span>
                <div class="tum-bar-bg">
                  <div
                    class="tum-bar-fill completion"
                    :style="{
                      width: completionPct(row) + '%',
                      background: modelColor(row.model_name) + '99',
                    }"
                  ></div>
                </div>
                <span class="tum-bar-num">{{ fmtNum(row.completion_tokens) }}</span>
              </div>
            </div>
          </div>

          <!-- 에이전트별 게이지 -->
          <div v-if="activeTab === 'context'" class="tum-gauge-list">
            <div v-if="!data.by_context.length" class="tum-empty">
              이 기간에 사용 내역이 없습니다.
            </div>
            <div
              v-for="row in data.by_context"
              :key="row.context_type"
              class="tum-gauge-row"
            >
              <div class="tum-gauge-label-row">
                <span class="tum-model-dot" style="background:#6366f1"></span>
                <span class="tum-gauge-name">{{ contextLabel(row.context_type) }}</span>
                <span class="tum-gauge-tokens">{{ fmtNum(row.total_tokens) }} tokens</span>
                <span class="tum-gauge-cost">{{ fmtCost(row.cost) }}</span>
              </div>
              <div class="tum-bar-wrap">
                <span class="tum-bar-tag">입력</span>
                <div class="tum-bar-bg">
                  <div
                    class="tum-bar-fill prompt"
                    :style="{ width: promptPct(row) + '%' }"
                  ></div>
                </div>
                <span class="tum-bar-num">{{ fmtNum(row.prompt_tokens) }}</span>
              </div>
              <div class="tum-bar-wrap">
                <span class="tum-bar-tag">출력</span>
                <div class="tum-bar-bg">
                  <div
                    class="tum-bar-fill completion"
                    :style="{ width: completionPct(row) + '%', background: '#6366f199' }"
                  ></div>
                </div>
                <span class="tum-bar-num">{{ fmtNum(row.completion_tokens) }}</span>
              </div>
            </div>
          </div>

        </template>

      </div>
    </div>
  </Teleport>
</template>

<style scoped>
/* ── 컨테이너 크기 오버라이드 ───────────────────────────────────────────── */
.tum-modal { width: 560px; max-height: 88vh; }

/* ── 기간 선택 ─────────────────────────────────────────────────*/
.tum-daterange {
  padding: 12px 20px 0;
  flex-shrink: 0;
}
.tum-daterange-inputs {
  display: flex; align-items: flex-end; gap: 8px; flex-wrap: wrap;
}
.tum-date-sep {
  font-size: 14px; color: var(--text-muted, #94a3b8);
  padding-bottom: 4px; align-self: flex-end; margin-bottom: 8px;
}
.tum-date-error {
  margin-top: 5px;
  font-size: 11px; color: #ef4444;
}

/* ── 요약 카드 ─────────────────────────────────────────────────────────────*/
.tum-summary {
  display: grid; grid-template-columns: 1fr 1fr 1fr 1fr;
  gap: 10px; padding: 14px 20px;
  flex-shrink: 0;
}
.tum-stat-card {
  background: var(--surface, #f8fafc);
  border: 1px solid var(--border, #e2e8f0);
  border-radius: 10px; padding: 10px 12px;
}
.tum-stat-card.accent {
  background: rgba(99,102,241,.06);
  border-color: rgba(99,102,241,.2);
}
.tum-stat-label { font-size: 10px; color: var(--text-muted, #64748b); margin-bottom: 3px; }
.tum-stat-value {
  font-size: 17px; font-weight: 700; color: var(--text, #1e293b);
  line-height: 1.1;
}
.tum-stat-value.cost { font-size: 13px; }
.tum-stat-sub { font-size: 10px; color: var(--text-muted, #94a3b8); margin-top: 2px; }

/* ── 탭 ──────────────────────────────────────────────────────────────────*/
.tum-tabs {
  display: flex; gap: 0; padding: 0 20px;
  border-bottom: 1px solid var(--border, #e2e8f0);
  flex-shrink: 0;
}
.tum-tab {
  padding: 8px 18px; font-size: 13px; font-weight: 500;
  border: none; background: transparent;
  color: var(--text-muted, #64748b); cursor: pointer;
  border-bottom: 2px solid transparent; margin-bottom: -1px;
  transition: all .15s;
}
.tum-tab.active {
  color: var(--primary, #2563eb);
  border-bottom-color: var(--primary, #2563eb);
}
.tum-tab:hover:not(.active) { color: var(--text, #1e293b); }

/* ── 게이지 목록 ───────────────────────────────────────────────────────────*/
.tum-gauge-list {
  overflow-y: auto; flex: 1;
  padding: 10px 20px 16px;
  display: flex; flex-direction: column; gap: 14px;
}
.tum-gauge-row {
  display: flex; flex-direction: column; gap: 5px;
}
.tum-gauge-label-row {
  display: flex; align-items: center; gap: 7px;
  font-size: 13px;
}
.tum-model-dot {
  width: 9px; height: 9px; border-radius: 50%; flex-shrink: 0;
}
.tum-gauge-name {
  font-weight: 600; color: var(--text, #1e293b); flex: 1;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.tum-gauge-tokens {
  font-size: 11px; color: var(--text-muted, #64748b);
}
.tum-gauge-cost {
  font-size: 11px; color: var(--text-muted, #64748b);
  min-width: 72px; text-align: right;
}

/* ── 개별 바 ──────────────────────────────────────────────────────────────*/
.tum-bar-wrap {
  display: flex; align-items: center; gap: 8px;
}
.tum-bar-tag {
  font-size: 10px; color: var(--text-muted, #94a3b8);
  width: 22px; flex-shrink: 0; text-align: right;
}
.tum-bar-bg {
  flex: 1; height: 8px; border-radius: 4px;
  background: var(--surface-2, #f1f5f9);
  overflow: hidden;
}
.tum-bar-fill {
  height: 100%; border-radius: 4px;
  transition: width .5s cubic-bezier(.4,0,.2,1);
}
.tum-bar-fill.prompt  { background: #6366f1; }
.tum-bar-fill.completion { background: #6366f180; }
.tum-bar-num {
  font-size: 10px; color: var(--text-muted, #64748b);
  min-width: 40px; text-align: right;
}

/* ── 로딩 / 에러 / 비어있음 ─────────────────────────────────────────────*/
.tum-loading, .tum-error, .tum-empty {
  text-align: center; padding: 36px 20px;
  font-size: 13px; color: var(--text-muted, #64748b);
}
.tum-error { color: #ef4444; }
</style>
