<script setup>
import { inject, ref, computed, watch, onUnmounted } from 'vue'
import ProcessStepBar from './ProcessStepBar.vue'
import FileUploadArea from './FileUploadArea.vue'

const {
  showUploadModal,
  nightMode,
  uploadStep,
  uploadForm,
  gNodes,
  deptConnectableNodes,
  업로드회의체과제,
  prefilledCtx,
  REL_COLORS,
  autoRel,
  runAiAnalysis,
  aiAnalyzing,
  aiResult,
  aiStreamText,
  aiStreamStage,
  submitReview,
  isResubmit,
  rejectedReports,
  selectedParentId,
  fetchRejectedReports,
  isResultReadOnly,
} = inject('archiveModals')

function onResubmitToggle() {
  selectedParentId.value = null
  if (isResubmit.value) fetchRejectedReports()
}

function onParentSelect() {
  const parent = rejectedReports.value.find(r => r.id === selectedParentId.value)
  if (!parent) return
  uploadForm.value.meetingId = `mg-${parent.meeting_id}`
  const deptNode = deptConnectableNodes.value.find(n => n.label === parent.submitter_department)
  if (deptNode) uploadForm.value.connectNodeId = deptNode.id
}

// ── 레이더 차트 상수 ───────────────────────────────────────────
const CX = 100,
  CY = 105,
  R = 72
const CRITERIA_DEF = [
  { key: '목적및배경', label: '목적/배경', max: 15 },
  { key: '현황분석', label: '현황분석', max: 20 },
  { key: '핵심내용', label: '핵심내용', max: 20 },
  { key: '실행계획', label: '실행계획', max: 20 },
  { key: '기대효과', label: '기대효과', max: 15 },
  { key: '리스크및대안', label: '리스크/대안', max: 10 },
]

function ptArr(angleDeg, r) {
  const a = (angleDeg * Math.PI) / 180
  return [CX + r * Math.cos(a), CY + r * Math.sin(a)]
}
function pt(angleDeg, r) {
  const [x, y] = ptArr(angleDeg, r)
  return `${x.toFixed(1)},${y.toFixed(1)}`
}

// 그리드 다각형 (33%, 66%, 100%)
const gridPoly = CRITERIA_DEF.map((_, i) => pt(i * 60 - 90, R)).join(' ')
const gridPoly2 = CRITERIA_DEF.map((_, i) => pt(i * 60 - 90, R * 0.66)).join(' ')
const gridPoly3 = CRITERIA_DEF.map((_, i) => pt(i * 60 - 90, R * 0.33)).join(' ')

// 축 선
const axisLines = CRITERIA_DEF.map((_, i) => {
  const [x2, y2] = ptArr(i * 60 - 90, R)
  return { x2: x2.toFixed(1), y2: y2.toFixed(1) }
})

// 라벨 위치
const labelPos = CRITERIA_DEF.map((c, i) => {
  const [x, y] = ptArr(i * 60 - 90, R + 20)
  return { x: x.toFixed(1), y: y.toFixed(1), label: c.label }
})

// ── 애니메이션 ─────────────────────────────────────────────────
const animProgress = ref(0)
let animTimer = null

watch(aiResult, val => {
  if (val) {
    animProgress.value = 0
    const start = Date.now()
    const duration = 900
    animTimer = setInterval(() => {
      const t = Math.min((Date.now() - start) / duration, 1)
      animProgress.value = t < 0.5 ? 2 * t * t : -1 + (4 - 2 * t) * t
      if (animProgress.value >= 1) {
        animProgress.value = 1
        clearInterval(animTimer)
      }
    }, 16)
  }
})
onUnmounted(() => {
  clearInterval(animTimer)
})

// ── AI 분석 단계별 메시지 ──────────────────────────────────────
const EVAL_STEPS = [
  { message: '관련 회의록·안건을 검색하고 있습니다…', category: null },
  { message: '보고서 내용을 파악하고 있습니다…', category: null },
  { message: '목적 및 배경을 검토하고 있습니다…', category: '목적및배경' },
  { message: '현황 분석 데이터를 확인하고 있습니다…', category: '현황분석' },
  { message: '핵심 내용의 논리 구조를 파악하고 있습니다…', category: '핵심내용' },
  { message: '실행 계획의 구체성을 평가하고 있습니다…', category: '실행계획' },
  { message: '기대효과와 목적 연결성을 검토하고 있습니다…', category: '기대효과' },
  { message: '리스크와 대안을 분석하고 있습니다…', category: '리스크및대안' },
  { message: '종합 점수를 산출하고 있습니다…', category: null },
]
const CATEGORY_ORDER = [
  '목적및배경',
  '현황분석',
  '핵심내용',
  '실행계획',
  '기대효과',
  '리스크및대안',
]
const currentEvalStep = ref(0)

watch(aiAnalyzing, val => {
  if (!val) currentEvalStep.value = 0
})

watch(aiStreamStage, msg => {
  if (!msg) return
  if (msg.includes('분석')) currentEvalStep.value = Math.max(currentEvalStep.value, 1)
})

watch(aiStreamText, text => {
  if (!aiAnalyzing.value || !text) return
  if (CATEGORY_ORDER.every(c => text.includes(c))) {
    currentEvalStep.value = 8
    return
  }
  for (let i = CATEGORY_ORDER.length - 1; i >= 0; i--) {
    if (text.includes(CATEGORY_ORDER[i])) {
      currentEvalStep.value = Math.max(currentEvalStep.value, i + 2)
      return
    }
  }
})

const activeCategory = computed(() =>
  aiAnalyzing.value ? EVAL_STEPS[currentEvalStep.value]?.category : null,
)

// 점수 다각형
const scorePoly = computed(() => {
  const scores = aiResult.value?.detail_scores || {}
  return CRITERIA_DEF.map((c, i) => {
    const s = scores[c.key]?.score ?? 0
    return pt(i * 60 - 90, (s / c.max) * R * animProgress.value)
  }).join(' ')
})

// 색상
const scoreColor = computed(() => {
  const s = aiResult.value?.score ?? 0
  return s >= 80 ? '#10b981' : s >= 60 ? '#f59e0b' : '#ef4444'
})

// ── 카테고리 펼치기/접기 ───────────────────────────────────────
const expandedCriteria = ref(new Set())
function toggleCriteria(key) {
  const s = new Set(expandedCriteria.value)
  s.has(key) ? s.delete(key) : s.add(key)
  expandedCriteria.value = s
}

// ── 피드백 단계 ───────────────────────────────────────────────
const showFeedback = ref(false)
const hitlAction = ref('') // 'approved' | 'rejected'
const hitlFeedback = ref('')
const submitting = ref(false)

watch(showUploadModal, v => {
  if (!v) {
    showFeedback.value = false
    hitlAction.value = ''
    hitlFeedback.value = ''
  }
})

function onApprove() {
  hitlAction.value = 'approved'
  showFeedback.value = true
}
function onReject() {
  hitlAction.value = 'rejected'
  showFeedback.value = true
}
async function onSubmitFeedback() {
  submitting.value = true
  await submitReview(hitlAction.value, hitlFeedback.value)
  submitting.value = false
  showFeedback.value = false
}

// ── 과제 선택 ─────────────────────────────────────────────────
function aiMatchReason(t) {
  const id = String(t.agenda_id ?? t.id)
  const m = (aiResult.value?.matched_agendas || []).find(x => String(x.id) === id)
  return m ? m.reason || 'AI가 관련 아젠다로 추천' : ''
}
const agendaSearch = ref('')
const agendaDropdownOpen = ref(false)
function toggleAgendaDropdown() {
  agendaDropdownOpen.value = !agendaDropdownOpen.value
  if (agendaDropdownOpen.value) agendaSearch.value = ''
}
</script>

<template>
  <Teleport to="body">
    <div v-if="showUploadModal" class="app-modal-backdrop">
      <div
        class="app-modal"
        :class="[uploadStep === 2 ? 'app-modal-lg' : 'app-modal-md', { dark: nightMode }]"
      >
        <div class="upload-step-bar">
          <ProcessStepBar
            :steps="['자료 정보 입력', 'AI 검토 결과']"
            :current-step="uploadStep - 1"
            @step-click="
              i => {
                if (i === 0 && !aiAnalyzing) uploadStep = 1
              }
            "
          />
        </div>

        <!-- ── Step 1: 자료 정보 입력 ── -->
        <template v-if="uploadStep === 1">
          <div class="app-modal-header">
            <span class="app-modal-title">자료 정보 입력</span>
            <button class="app-modal-close" @click="showUploadModal = false">
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
            <!-- 재검토 토글 -->
            <label class="resubmit-toggle">
              <input type="checkbox" v-model="isResubmit" @change="onResubmitToggle" />
              <span class="resubmit-toggle-label">자료 재검토</span>
              <span class="resubmit-toggle-desc">반려된 보고서를 수정해서 재제출합니다</span>
            </label>

            <!-- 반려 보고서 선택 -->
            <div v-if="isResubmit" class="app-modal-field">
              <label>재검토할 보고서 선택 <span class="req">*</span></label>
              <select v-model="selectedParentId" class="app-modal-input" @change="onParentSelect">
                <option :value="null">반려된 보고서 선택...</option>
                <option v-for="r in rejectedReports" :key="r.id" :value="r.id">
                  {{ r.file_name }} (v{{ r.version
                  }}{{ r.total_score != null ? ` · ${r.total_score}점` : '' }})
                </option>
              </select>
              <p
                v-if="rejectedReports.length === 0"
                class="agenda-auto-note"
                style="margin-top: 4px"
              >
                반려된 보고서가 없습니다.
              </p>
            </div>

            <div class="app-modal-field">
              <label>파일 첨부 <span class="req">*</span></label>
              <FileUploadArea
                :file="uploadForm.file"
                accept=".pdf"
                hint="PDF"
                @change="
                  files => {
                    uploadForm.file = files[0]
                    uploadForm.label = files[0]?.name || ''
                  }
                "
              />
            </div>
            <div class="app-modal-field">
              <label>자료명 <span class="req">*</span></label>
              <input
                v-model="uploadForm.label"
                class="app-modal-input"
                placeholder="파일을 첨부하세요"
                readonly
              />
            </div>
            <div class="app-modal-field">
              <label>관련 회의체 <span class="req">*</span></label>
              <!-- prettier-ignore -->
              <select
                v-model="uploadForm.meetingId"
                class="app-modal-input"
                @change="prefilledCtx.meetingId = false; prefilledCtx.connectNodeId = false"
              >
                <option value="">회의체 선택...</option>
                <option
                  v-for="n in gNodes.filter(n => n.type === 'Meetings')"
                  :key="n.id"
                  :value="n.id"
                >
                  {{ n.label }}
                </option>
              </select>
            </div>
            <div class="app-modal-field">
              <label>업로드 부서 <span class="req">*</span></label>
              <select
                v-model="uploadForm.connectNodeId"
                class="app-modal-input"
                @change="prefilledCtx.connectNodeId = false"
              >
                <option value="">부서 선택...</option>
                <option v-for="n in deptConnectableNodes" :key="n.id" :value="n.id">
                  {{ n.label }}
                </option>
              </select>
            </div>
            <p class="agenda-auto-note">
              <svg
                width="13"
                height="13"
                fill="none"
                stroke="currentColor"
                stroke-width="2"
                viewBox="0 0 24 24"
              >
                <path d="M12 2a10 10 0 100 20A10 10 0 0012 2z" />
                <path d="M12 16v-4M12 8h.01" />
              </svg>
              연관 아젠다는 AI 검토 과정에서 자동으로 판별되어 연결됩니다.
            </p>
            <div v-if="uploadForm.connectNodeId && uploadForm.label" class="conn-preview-box">
              <span class="conn-node">{{
                deptConnectableNodes.find(n => n.id === uploadForm.connectNodeId)?.label
              }}</span>
              <span class="conn-arrow">→</span>
              <span
                class="conn-rel"
                :style="{
                  color: REL_COLORS[autoRel(uploadForm.connectNodeId, 'report')] || '#a78bfa',
                }"
                >{{ autoRel(uploadForm.connectNodeId, 'report') }}</span
              >
              <span class="conn-arrow">→</span>
              <span class="conn-node file">{{ uploadForm.label }}</span>
            </div>
          </div>
          <div class="app-modal-footer">
            <button class="app-btn-cancel" @click="showUploadModal = false">취소</button>
            <button
              class="app-btn-primary"
              :disabled="
                !uploadForm.label.trim() || !uploadForm.connectNodeId || !uploadForm.meetingId
              "
              @click="runAiAnalysis"
            >
              <svg
                width="13"
                height="13"
                fill="none"
                stroke="currentColor"
                stroke-width="2"
                viewBox="0 0 24 24"
                style="margin-right: 5px"
              >
                <circle cx="12" cy="12" r="10" />
                <path d="M12 8v4l3 3" />
              </svg>
              AI 검토 시작
            </button>
          </div>
        </template>

        <!-- ── Step 2: AI 검토 결과 ── -->
        <template v-else-if="uploadStep === 2">
          <div class="app-modal-header">
            <span class="app-modal-title"
              >AI 검토 결과
              <span style="font-size: 11px; opacity: 0.6; font-weight: 400">
                — {{ uploadForm.label }}</span
              >
            </span>
            <button class="app-modal-close" @click="showUploadModal = false">
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

          <div class="app-modal-body ai-result-body">
            <!-- 레이더 차트 (로딩 중 / 결과) -->
            <div class="radar-wrap">
              <svg viewBox="0 0 200 210" class="radar-svg">
                <!-- 그리드 -->
                <polygon :points="gridPoly" fill="none" stroke="#e2e8f0" stroke-width="1" />
                <polygon :points="gridPoly2" fill="none" stroke="#e2e8f0" stroke-width="0.7" />
                <polygon :points="gridPoly3" fill="none" stroke="#e2e8f0" stroke-width="0.7" />
                <!-- 축 -->
                <line
                  v-for="(ax, i) in axisLines"
                  :key="i"
                  :x1="CX"
                  :y1="CY"
                  :x2="ax.x2"
                  :y2="ax.y2"
                  :stroke="
                    activeCategory && CRITERIA_DEF[i].key === activeCategory ? '#a78bfa' : '#e2e8f0'
                  "
                  :stroke-width="activeCategory && CRITERIA_DEF[i].key === activeCategory ? 2 : 0.8"
                  style="
                    transition:
                      stroke 0.4s,
                      stroke-width 0.4s;
                  "
                />

                <!-- 로딩 중: 점선 애니메이션 -->
                <polygon
                  v-if="aiAnalyzing"
                  :points="gridPoly"
                  fill="none"
                  stroke="#a78bfa"
                  stroke-width="1.5"
                  stroke-dasharray="6 3"
                  class="radar-loading-dash"
                />

                <!-- 결과: 점수 다각형 -->
                <polygon
                  v-if="aiResult && !aiAnalyzing"
                  :points="scorePoly"
                  :fill="scoreColor + '33'"
                  :stroke="scoreColor"
                  stroke-width="2"
                  class="radar-score-poly"
                />

                <!-- 라벨 -->
                <text
                  v-for="(lp, i) in labelPos"
                  :key="i"
                  :x="lp.x"
                  :y="lp.y"
                  text-anchor="middle"
                  dominant-baseline="middle"
                  font-size="8.5"
                  :fill="
                    activeCategory && CRITERIA_DEF[i].key === activeCategory ? '#7c3aed' : '#64748b'
                  "
                  :font-weight="
                    activeCategory && CRITERIA_DEF[i].key === activeCategory ? '700' : '400'
                  "
                  font-family="sans-serif"
                  style="transition: fill 0.4s"
                >
                  {{ lp.label }}
                </text>

                <!-- 중앙 점수 (결과 확정 후만 표시) -->
                <text
                  v-if="aiResult && !aiAnalyzing"
                  :x="CX"
                  :y="CY - 6"
                  text-anchor="middle"
                  dominant-baseline="middle"
                  font-size="22"
                  font-weight="700"
                  :fill="scoreColor"
                >
                  {{ aiResult.score }}
                </text>
                <text
                  v-if="aiResult && !aiAnalyzing"
                  :x="CX"
                  :y="CY + 14"
                  text-anchor="middle"
                  dominant-baseline="middle"
                  font-size="9"
                  fill="#94a3b8"
                >
                  / 100
                </text>
              </svg>

              <!-- 로딩 상태 메시지 -->
              <div v-if="aiAnalyzing" class="radar-stage">
                <div class="radar-stage-dot"></div>
                {{ EVAL_STEPS[currentEvalStep]?.message }}
              </div>

              <!-- 항목별 점수 바 -->
              <div v-if="aiResult && !aiAnalyzing" class="criteria-scores">
                <div v-for="c in CRITERIA_DEF" :key="c.key" class="cs-block">
                  <!-- 카테고리 행 -->
                  <div class="cs-row" @click="toggleCriteria(c.key)" style="cursor: pointer">
                    <span class="cs-label">{{ c.label }}</span>
                    <div class="cs-bar-wrap">
                      <div
                        class="cs-bar"
                        :style="{
                          width:
                            ((aiResult.detail_scores?.[c.key]?.score ?? 0) / c.max) * 100 + '%',
                          background: scoreColor,
                          transition: 'width 0.8s ease',
                        }"
                      />
                    </div>
                    <span class="cs-num"
                      >{{ aiResult.detail_scores?.[c.key]?.score ?? 0 }}/{{ c.max }}</span
                    >
                    <svg
                      class="cs-toggle-icon"
                      :style="{ transform: expandedCriteria.has(c.key) ? 'rotate(90deg)' : '' }"
                      width="9"
                      height="9"
                      fill="none"
                      stroke="currentColor"
                      stroke-width="2.5"
                      viewBox="0 0 24 24"
                    >
                      <path d="M9 18l6-6-6-6" />
                    </svg>
                  </div>

                  <!-- 펼쳐진 세부 항목 -->
                  <div v-if="expandedCriteria.has(c.key)" class="cs-detail">
                    <!-- sub_scores -->
                    <div
                      v-for="(sub, subKey) in aiResult.detail_scores?.[c.key]?.sub_scores"
                      :key="subKey"
                      class="cs-sub-row"
                    >
                      <span class="cs-sub-label">{{ subKey }}</span>
                      <div class="cs-sub-bar-wrap">
                        <div
                          class="cs-sub-bar"
                          :style="{
                            width: (sub.score / sub.max) * 100 + '%',
                            background: scoreColor + 'aa',
                          }"
                        />
                      </div>
                      <span class="cs-sub-num">{{ sub.score }}/{{ sub.max }}</span>
                    </div>
                    <!-- 잘된 점 -->
                    <div
                      v-if="aiResult.detail_scores?.[c.key]?.strengths?.length"
                      class="cs-feedback-section"
                    >
                      <span class="cs-fb-label cs-fb-good">✅ 잘된 점</span>
                      <ul class="cs-fb-list">
                        <li
                          v-for="(s, i) in aiResult.detail_scores[c.key].strengths"
                          :key="i"
                          class="cs-fb-item"
                        >
                          {{ s }}
                        </li>
                      </ul>
                    </div>
                    <!-- 개선 방향 -->
                    <div
                      v-if="aiResult.detail_scores?.[c.key]?.improvements?.length"
                      class="cs-feedback-section"
                    >
                      <span class="cs-fb-label cs-fb-warn">⚠️ 개선 방향</span>
                      <ul class="cs-fb-list">
                        <li
                          v-for="(imp, i) in aiResult.detail_scores[c.key].improvements"
                          :key="i"
                          class="cs-fb-item cs-fb-item-warn"
                        >
                          {{ imp }}
                        </li>
                      </ul>
                    </div>
                  </div>
                </div>
              </div>
            </div>

            <!-- 우선 개선과제: 신규·읽기전용 공통 표시 -->
            <div
              v-if="aiResult && !aiAnalyzing && aiResult.top_improvements?.length"
              class="ai-top-improvements"
            >
              <div class="ai-section-title" style="margin-bottom: 8px">
                <svg
                  width="13"
                  height="13"
                  fill="none"
                  stroke="#f59e0b"
                  stroke-width="2"
                  viewBox="0 0 24 24"
                >
                  <path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z" />
                </svg>
                우선 개선 아젠다
              </div>
              <div v-for="(imp, i) in aiResult.top_improvements" :key="i" class="ai-top-item">
                <span class="ai-top-num">{{ i + 1 }}</span>
                <span class="ai-top-category">[{{ imp.category }}]</span>
                <span class="ai-top-action">{{ imp.action }}</span>
              </div>
            </div>

            <!-- Top 3 개선 과제 + 피드백 -->
            <template v-if="aiResult && !aiAnalyzing && !showFeedback">
              <!-- 연관 과제 -->
              <div class="ai-section">
                <div class="ai-section-title">
                  <svg
                    width="13"
                    height="13"
                    fill="none"
                    stroke="#8b5cf6"
                    stroke-width="2"
                    viewBox="0 0 24 24"
                  >
                    <path d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                  </svg>
                  연관 아젠다 연결
                  <span v-if="aiResult.matched_agendas?.length" class="ai-badge"
                    >AI 추천 {{ aiResult.matched_agendas.length }}건</span
                  >
                </div>

                <!-- 선택된 과제 태그 -->
                <div v-if="uploadForm.relatedAgendaIds.length" class="agenda-tags">
                  <span v-for="id in uploadForm.relatedAgendaIds" :key="id" class="agenda-tag">
                    {{
                      업로드회의체과제
                        .find(t => String(t.agenda_id ?? t.id) === id)
                        ?.content?.slice(0, 20) || id
                    }}
                    <button
                      class="agenda-tag-remove"
                      @click.stop="
                        uploadForm.relatedAgendaIds = uploadForm.relatedAgendaIds.filter(
                          x => x !== id,
                        )
                      "
                    >
                      ×
                    </button>
                  </span>
                </div>

                <!-- 드롭다운 트리거 버튼 -->
                <div class="agenda-dropdown-wrap">
                  <button class="agenda-dropdown-trigger" @click.stop="toggleAgendaDropdown">
                    <span>{{ agendaDropdownOpen ? '아젠다 선택 닫기' : '아젠다 선택하기' }}</span>
                    <svg
                      width="11"
                      height="11"
                      fill="none"
                      stroke="currentColor"
                      stroke-width="2.5"
                      viewBox="0 0 24 24"
                      :style="{
                        transform: agendaDropdownOpen ? 'rotate(180deg)' : '',
                        transition: 'transform .2s',
                      }"
                    >
                      <path d="M6 9l6 6 6-6" />
                    </svg>
                  </button>

                  <div v-if="agendaDropdownOpen" class="agenda-dropdown">
                    <!-- 검색 -->
                    <input
                      v-model="agendaSearch"
                      class="agenda-search-input"
                      type="text"
                      placeholder="아젠다 내용 검색…"
                      autofocus
                      @click.stop
                    />

                    <div class="agenda-dropdown-list">
                      <!-- AI 추천 -->
                      <template v-if="!agendaSearch.trim()">
                        <div
                          v-if="업로드회의체과제.filter(t => aiMatchReason(t)).length"
                          class="agenda-group-label"
                        >
                          AI 추천
                        </div>
                        <label
                          v-for="t in 업로드회의체과제.filter(t => aiMatchReason(t))"
                          :key="'ai-' + t.id"
                          class="agenda-dropdown-item recommended"
                          @click.stop
                        >
                          <input
                            type="checkbox"
                            :value="String(t.agenda_id ?? t.id)"
                            v-model="uploadForm.relatedAgendaIds"
                          />
                          <span>{{ t.content }}</span>
                          <span class="ai-badge sm" style="margin-left: auto">AI 추천</span>
                        </label>
                        <div
                          v-if="업로드회의체과제.filter(t => aiMatchReason(t)).length"
                          class="agenda-group-label"
                          style="margin-top: 6px"
                        >
                          전체 아젠다
                        </div>
                      </template>

                      <!-- 검색 결과 or 전체 -->
                      <template
                        v-for="t in 업로드회의체과제.filter(
                          t =>
                            !aiMatchReason(t) &&
                            (!agendaSearch.trim() ||
                              t.content.toLowerCase().includes(agendaSearch.trim().toLowerCase())),
                        )"
                        :key="t.id"
                      >
                        <label class="agenda-dropdown-item" @click.stop>
                          <input
                            type="checkbox"
                            :value="String(t.agenda_id ?? t.id)"
                            v-model="uploadForm.relatedAgendaIds"
                          />
                          <span>{{ t.content }}</span>
                        </label>
                      </template>

                      <p
                        v-if="
                          !업로드회의체과제.filter(t =>
                            agendaSearch.trim()
                              ? t.content.toLowerCase().includes(agendaSearch.trim().toLowerCase())
                              : true,
                          ).length
                        "
                        class="agenda-auto-note"
                        style="padding: 8px 4px"
                      >
                        아젠다가 없습니다.
                      </p>
                    </div>
                  </div>
                </div>
              </div>
            </template>

            <!-- 피드백 입력 단계 -->
            <div v-if="showFeedback" class="hitl-feedback-wrap">
              <div class="hitl-feedback-title">
                <svg
                  width="15"
                  height="15"
                  fill="none"
                  stroke="#a78bfa"
                  stroke-width="2"
                  viewBox="0 0 24 24"
                >
                  <path
                    d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z"
                  />
                </svg>
                AI 검토 결과 리뷰
              </div>
              <p class="hitl-feedback-desc">
                AI가 보고서를 잘 평가했나요? 개선이 필요한 부분이 있으면 알려주세요.
              </p>
              <textarea
                v-model="hitlFeedback"
                class="hitl-textarea"
                placeholder="예) 리스크 항목 평가가 너무 관대했습니다 / 연관 아젠다 추천이 정확했습니다 (선택)"
                rows="3"
              />
            </div>
          </div>

          <!-- 푸터 -->
          <div class="app-modal-footer" style="justify-content: space-between">
            <!-- 로딩 중 -->
            <template v-if="aiAnalyzing">
              <span style="font-size: 12px; color: #94a3b8">AI가 검토 중입니다…</span>
              <button class="app-btn-primary" disabled>검토 중…</button>
            </template>

            <!-- 결과 확인 중 (읽기 전용: 이미 결정된 보고서) -->
            <template v-else-if="aiResult && !showFeedback && isResultReadOnly">
              <span style="font-size: 12px; color: #94a3b8">검토가 완료된 보고서입니다.</span>
              <button class="app-btn-cancel" @click="showUploadModal = false">닫기</button>
            </template>

            <!-- 결과 확인 중 (신규 검토) -->
            <template v-else-if="aiResult && !showFeedback">
              <button class="app-btn-reject" @click="onReject">
                <svg
                  width="12"
                  height="12"
                  fill="none"
                  stroke="currentColor"
                  stroke-width="2.5"
                  viewBox="0 0 24 24"
                >
                  <path d="M6 18L18 6M6 6l12 12" />
                </svg>
                반려
              </button>
              <button class="app-btn-primary" @click="onApprove">
                <svg
                  width="12"
                  height="12"
                  fill="none"
                  stroke="currentColor"
                  stroke-width="2.5"
                  viewBox="0 0 24 24"
                >
                  <path d="M5 13l4 4L19 7" />
                </svg>
                아카이브 등록 확정
              </button>
            </template>

            <!-- 피드백 입력 중 -->
            <template v-else-if="showFeedback">
              <button class="app-btn-cancel" @click="showFeedback = false">← 취소</button>
              <button class="app-btn-primary" :disabled="submitting" @click="onSubmitFeedback">
                {{ submitting ? '저장 중…' : '완료' }}
              </button>
            </template>
          </div>
        </template>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
/* ── 레이더 차트 (모달 크기 고정 오버라이드) ── */
.radar-svg {
  width: 200px;
  height: 210px;
}
.radar-loading-dash {
  animation: dashRotate 1.2s linear infinite;
}
.radar-score-poly {
  transition: all 0.1s;
}

.radar-stage {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--text-muted);
}
.radar-stage-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--violet-soft);
  animation: pulse 1s ease-in-out infinite;
}
@keyframes pulse {
  0%,
  100% {
    opacity: 1;
  }
  50% {
    opacity: 0.3;
  }
}

/* ── 항목별 점수 바 ── */
.criteria-scores {
  width: 100%;
  max-width: 280px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.cs-block {
  display: flex;
  flex-direction: column;
}
.cs-row {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 3px 4px;
  border-radius: 6px;
}
.cs-row:hover {
  background: rgba(0, 0, 0, 0.04);
}
.cs-label {
  font-size: 10px;
  color: var(--text-muted);
  width: 52px;
  flex-shrink: 0;
  text-align: right;
}
.cs-bar-wrap {
  flex: 1;
  height: 6px;
  background: var(--surface-2);
  border-radius: 3px;
  overflow: hidden;
}
.cs-bar {
  height: 100%;
  border-radius: 3px;
}
.cs-num {
  font-size: 10px;
  color: var(--dark-muted);
  width: 28px;
  flex-shrink: 0;
}
.cs-toggle-icon {
  flex-shrink: 0;
  color: var(--dark-muted);
  transition: transform 0.2s;
}

/* 세부 항목 */
.cs-detail {
  margin: 3px 0 5px 58px;
  display: flex;
  flex-direction: column;
  gap: 3px;
  border-left: 2px solid #e2e8f0;
  padding-left: 10px;
}
.cs-sub-row {
  display: flex;
  align-items: center;
  gap: 5px;
}
.cs-sub-label {
  font-size: 9.5px;
  color: var(--dark-muted);
  width: 70px;
  flex-shrink: 0;
}
.cs-sub-bar-wrap {
  flex: 1;
  height: 4px;
  background: var(--surface-2);
  border-radius: 2px;
  overflow: hidden;
}
.cs-sub-bar {
  height: 100%;
  border-radius: 2px;
}
.cs-sub-num {
  font-size: 9px;
  color: var(--dark-text-2);
  width: 22px;
  flex-shrink: 0;
}
.cs-feedback-section {
  margin-top: 6px;
  display: flex;
  flex-direction: column;
  gap: 3px;
}
.cs-fb-label {
  font-size: 10px;
  font-weight: 600;
  margin-bottom: 3px;
}
.cs-fb-good {
  color: var(--success);
}
.cs-fb-warn {
  color: var(--warning);
}
.cs-fb-list {
  margin: 0;
  padding-left: 14px;
  display: flex;
  flex-direction: column;
  gap: 3px;
  list-style: disc;
}
.cs-fb-item {
  font-size: 11px;
  color: var(--text-muted);
  line-height: 1.55;
}
.cs-fb-item-warn {
  color: #92400e;
}

/* Top 3 개선 과제 */
.ai-top-improvements {
  margin-top: 10px;
  display: flex;
  flex-direction: column;
  gap: 5px;
}
.ai-top-item {
  display: flex;
  align-items: flex-start;
  gap: 6px;
  font-size: 11.5px;
}
.ai-top-num {
  width: 16px;
  height: 16px;
  border-radius: 50%;
  background: var(--warning-bg);
  color: var(--warning-text);
  font-size: 10px;
  font-weight: 700;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  margin-top: 1px;
}
.ai-top-category {
  color: #8b5cf6;
  font-weight: 600;
  flex-shrink: 0;
}
.ai-top-action {
  color: #374151;
  line-height: 1.5;
}

/* ── 피드백 입력 ── */
.hitl-feedback-wrap {
  margin-top: 12px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.hitl-feedback-title {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  font-weight: 600;
  color: var(--dark-card);
}
.hitl-feedback-desc {
  font-size: 12px;
  color: var(--text-muted);
  margin: 0;
}
.hitl-textarea {
  width: 100%;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  padding: 10px 12px;
  font-size: 13px;
  resize: vertical;
  outline: none;
  transition: border-color 0.15s;
  font-family: inherit;
}
.hitl-textarea:focus {
  border-color: var(--violet-soft);
}

/* ── 재검토 토글 ── */
.resubmit-toggle {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 10px;
  border-radius: 8px;
  background: #f8f5ff;
  border: 1px solid #e9d5ff;
  cursor: pointer;
  margin-bottom: 4px;
}
.resubmit-toggle input[type='checkbox'] {
  width: 14px;
  height: 14px;
  accent-color: #8b5cf6;
  flex-shrink: 0;
}
.resubmit-toggle-label {
  font-size: 13px;
  font-weight: 600;
  color: #6d28d9;
}
.resubmit-toggle-desc {
  font-size: 11px;
  color: #9ca3af;
}

/* ── 반려 버튼 ── */
.app-btn-reject {
  display: flex;
  align-items: center;
  gap: 5px;
  padding: 8px 16px;
  border-radius: 8px;
  font-size: 13px;
  font-weight: 600;
  border: 1.5px solid var(--danger);
  color: var(--danger);
  background: transparent;
  cursor: pointer;
}
.app-btn-reject:hover {
  background: #fef2f2;
}
</style>
