<script setup>
import { inject, ref, computed, watch, onUnmounted } from 'vue'
import ProcessStepBar from './ProcessStepBar.vue'
import FileUploadArea from './FileUploadArea.vue'

const {
  showUploadModal, nightMode, uploadStep, uploadForm,
  gNodes, deptConnectableNodes, 업로드회의체과제, prefilledCtx,
  addCustomAgenda,
  REL_COLORS, autoRel, runAiAnalysis,
  aiAnalyzing, aiResult, aiStreamText, aiStreamStage,
  PRESENTATION_CRITERIA, doAddFile, submitReview,
  isResubmit, rejectedReports, selectedParentId, fetchRejectedReports,
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
const CX = 100, CY = 105, R = 72
const CRITERIA_DEF = [
  { key: '목적및배경',   label: '목적/배경',  max: 15 },
  { key: '현황분석',     label: '현황분석',   max: 20 },
  { key: '핵심내용',     label: '핵심내용',   max: 20 },
  { key: '실행계획',     label: '실행계획',   max: 20 },
  { key: '기대효과',     label: '기대효과',   max: 15 },
  { key: '리스크및대안', label: '리스크/대안', max: 10 },
]

function ptArr(angleDeg, r) {
  const a = angleDeg * Math.PI / 180
  return [CX + r * Math.cos(a), CY + r * Math.sin(a)]
}
function pt(angleDeg, r) {
  const [x, y] = ptArr(angleDeg, r)
  return `${x.toFixed(1)},${y.toFixed(1)}`
}

// 그리드 다각형 (33%, 66%, 100%)
const gridPoly  = CRITERIA_DEF.map((_, i) => pt(i * 60 - 90, R)).join(' ')
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

watch(aiResult, (val) => {
  if (val) {
    animProgress.value = 0
    const start = Date.now()
    const duration = 900
    animTimer = setInterval(() => {
      const t = Math.min((Date.now() - start) / duration, 1)
      animProgress.value = t < 0.5 ? 2 * t * t : -1 + (4 - 2 * t) * t // ease in-out
      if (animProgress.value >= 1) {
        animProgress.value = 1
        clearInterval(animTimer)
      }
    }, 16)
  }
})
onUnmounted(() => clearInterval(animTimer))

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

// ── 스트리밍 중 부분 파싱 ──────────────────────────────────────
const streamScore = computed(() => {
  const m = (aiStreamText.value || '').match(/"score"\s*:\s*(\d+)/)
  return m ? parseInt(m[1]) : null
})

// ── 피드백 단계 ───────────────────────────────────────────────
const showFeedback = ref(false)
const hitlAction = ref('')   // 'approved' | 'rejected'
const hitlFeedback = ref('')
const submitting = ref(false)

watch(showUploadModal, (v) => {
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

// ── 과제 추가 ─────────────────────────────────────────────────
function aiMatchReason(t) {
  const id = String(t.agenda_id ?? t.id)
  const m = (aiResult.value?.matched_agendas || []).find(x => String(x.id) === id)
  return m ? (m.reason || 'AI가 관련 과제로 추천') : ''
}
const newAgendaText = ref('')
function submitCustomAgenda() {
  const text = newAgendaText.value.trim()
  if (!text) return
  addCustomAgenda(text)
  newAgendaText.value = ''
}
</script>

<template>
  <Teleport to="body">
    <div v-if="showUploadModal" class="app-modal-backdrop">
      <div class="app-modal app-modal-md" :class="{ dark: nightMode }">

        <div class="upload-step-bar">
          <ProcessStepBar
            :steps="['자료 정보 입력', 'AI 검토 결과']"
            :current-step="uploadStep - 1"
            @step-click="i => { if (i === 0 && !aiAnalyzing) uploadStep = 1 }"
          />
        </div>

        <!-- ── Step 1: 자료 정보 입력 ── -->
        <template v-if="uploadStep === 1">
          <div class="app-modal-header">
            <span class="app-modal-title">자료 정보 입력</span>
            <button class="app-modal-close" @click="showUploadModal = false">
              <svg width="14" height="14" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24"><path d="M6 18L18 6M6 6l12 12"/></svg>
            </button>
          </div>
          <div class="app-modal-body">

            <!-- 재검토 토글 -->
            <label class="resubmit-toggle">
              <input type="checkbox" v-model="isResubmit" @change="onResubmitToggle"/>
              <span class="resubmit-toggle-label">자료 재검토</span>
              <span class="resubmit-toggle-desc">반려된 보고서를 수정해서 재제출합니다</span>
            </label>

            <!-- 반려 보고서 선택 -->
            <div v-if="isResubmit" class="app-modal-field">
              <label>재검토할 보고서 선택 <span class="req">*</span></label>
              <select v-model="selectedParentId" class="app-modal-input" @change="onParentSelect">
                <option :value="null">반려된 보고서 선택...</option>
                <option v-for="r in rejectedReports" :key="r.id" :value="r.id">
                  {{ r.file_name }} (v{{ r.version }}{{ r.total_score != null ? ` · ${r.total_score}점` : '' }})
                </option>
              </select>
              <p v-if="rejectedReports.length === 0" class="agenda-auto-note" style="margin-top:4px">반려된 보고서가 없습니다.</p>
            </div>

            <div class="app-modal-field">
              <label>파일 첨부 <span class="req">*</span></label>
              <FileUploadArea
                :file="uploadForm.file"
                accept=".pdf"
                hint="PDF"
                @change="files => { uploadForm.file = files[0]; uploadForm.label = files[0]?.name || '' }"
              />
            </div>
            <div class="app-modal-field">
              <label>자료명 <span class="req">*</span></label>
              <input v-model="uploadForm.label" class="app-modal-input" placeholder="파일을 첨부하세요" readonly />
            </div>
            <div class="app-modal-field">
              <label>관련 회의체 <span class="req">*</span></label>
              <select v-model="uploadForm.meetingId" class="app-modal-input"
                @change="prefilledCtx.meetingId = false; prefilledCtx.connectNodeId = false">
                <option value="">회의체 선택...</option>
                <option v-for="n in gNodes.filter(n => n.type === 'meeting_group')" :key="n.id" :value="n.id">{{ n.label }}</option>
              </select>
            </div>
            <div class="app-modal-field">
              <label>업로드 부서 <span class="req">*</span></label>
              <select v-model="uploadForm.connectNodeId" class="app-modal-input"
                @change="prefilledCtx.connectNodeId = false">
                <option value="">부서 선택...</option>
                <option v-for="n in deptConnectableNodes" :key="n.id" :value="n.id">{{ n.label }}</option>
              </select>
            </div>
            <p class="agenda-auto-note">
              <svg width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M12 2a10 10 0 100 20A10 10 0 0012 2z"/><path d="M12 16v-4M12 8h.01"/></svg>
              연관 과제는 AI 검토 과정에서 자동으로 판별되어 연결됩니다.
            </p>
            <div v-if="uploadForm.connectNodeId && uploadForm.label" class="conn-preview-box">
              <span class="conn-node">{{ deptConnectableNodes.find(n => n.id === uploadForm.connectNodeId)?.label }}</span>
              <span class="conn-arrow">→</span>
              <span class="conn-rel" :style="{ color: REL_COLORS[autoRel(uploadForm.connectNodeId, 'file')] || '#a78bfa' }">{{ autoRel(uploadForm.connectNodeId, 'file') }}</span>
              <span class="conn-arrow">→</span>
              <span class="conn-node file">{{ uploadForm.label }}</span>
            </div>
          </div>
          <div class="app-modal-footer">
            <button class="app-btn-cancel" @click="showUploadModal = false">취소</button>
            <button class="app-btn-primary"
              :disabled="!uploadForm.label.trim() || !uploadForm.connectNodeId || !uploadForm.meetingId"
              @click="runAiAnalysis">
              <svg width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24" style="margin-right:5px"><circle cx="12" cy="12" r="10"/><path d="M12 8v4l3 3"/></svg>
              AI 검토 시작
            </button>
          </div>
        </template>

        <!-- ── Step 2: AI 검토 결과 ── -->
        <template v-else-if="uploadStep === 2">
          <div class="app-modal-header">
            <span class="app-modal-title">AI 검토 결과
              <span style="font-size:11px;opacity:.6;font-weight:400"> — {{ uploadForm.label }}</span>
            </span>
            <button class="app-modal-close" @click="showUploadModal = false">
              <svg width="14" height="14" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24"><path d="M6 18L18 6M6 6l12 12"/></svg>
            </button>
          </div>

          <div class="app-modal-body ai-result-body">

            <!-- 레이더 차트 (로딩 중 / 결과) -->
            <div class="radar-wrap">
              <svg viewBox="0 0 200 210" class="radar-svg">
                <!-- 그리드 -->
                <polygon :points="gridPoly"  fill="none" stroke="#e2e8f0" stroke-width="1"/>
                <polygon :points="gridPoly2" fill="none" stroke="#e2e8f0" stroke-width="0.7"/>
                <polygon :points="gridPoly3" fill="none" stroke="#e2e8f0" stroke-width="0.7"/>
                <!-- 축 -->
                <line v-for="(ax, i) in axisLines" :key="i"
                  :x1="CX" :y1="CY" :x2="ax.x2" :y2="ax.y2"
                  stroke="#e2e8f0" stroke-width="0.8"/>

                <!-- 로딩 중: 점선 애니메이션 -->
                <polygon v-if="aiAnalyzing" :points="gridPoly"
                  fill="none" stroke="#a78bfa" stroke-width="1.5"
                  stroke-dasharray="6 3" class="radar-loading-dash"/>

                <!-- 결과: 점수 다각형 -->
                <polygon v-if="aiResult && !aiAnalyzing" :points="scorePoly"
                  :fill="scoreColor + '33'" :stroke="scoreColor" stroke-width="2"
                  class="radar-score-poly"/>

                <!-- 라벨 -->
                <text v-for="(lp, i) in labelPos" :key="i"
                  :x="lp.x" :y="lp.y"
                  text-anchor="middle" dominant-baseline="middle"
                  font-size="8.5" fill="#64748b" font-family="sans-serif">
                  {{ lp.label }}
                </text>

                <!-- 중앙 점수 (결과 확정 후만 표시) -->
                <text v-if="aiResult && !aiAnalyzing"
                  :x="CX" :y="CY - 6" text-anchor="middle" dominant-baseline="middle"
                  font-size="22" font-weight="700" :fill="scoreColor">
                  {{ aiResult.score }}
                </text>
                <text v-if="aiResult && !aiAnalyzing"
                  :x="CX" :y="CY + 14" text-anchor="middle" dominant-baseline="middle"
                  font-size="9" fill="#94a3b8">
                  / 100
                </text>
              </svg>

              <!-- 로딩 상태 메시지 -->
              <div v-if="aiAnalyzing" class="radar-stage">
                <div class="radar-stage-dot"></div>
                {{ aiStreamStage || '항목별로 평가하고 있습니다…' }}
              </div>

              <!-- 항목별 점수 바 -->
              <div v-if="aiResult && !aiAnalyzing" class="criteria-scores">
                <div v-for="c in CRITERIA_DEF" :key="c.key" class="cs-row">
                  <span class="cs-label">{{ c.label }}</span>
                  <div class="cs-bar-wrap">
                    <div class="cs-bar"
                      :style="{
                        width: ((aiResult.detail_scores?.[c.key]?.score ?? 0) / c.max * 100) + '%',
                        background: scoreColor,
                        transition: 'width 0.8s ease',
                      }"/>
                  </div>
                  <span class="cs-num">{{ aiResult.detail_scores?.[c.key]?.score ?? 0 }}/{{ c.max }}</span>
                </div>
              </div>
            </div>

            <!-- 피드백 목록 -->
            <template v-if="aiResult && !aiAnalyzing && !showFeedback">
              <div class="ai-feedback-list" style="margin-top:12px">
                <div v-for="(fb, i) in aiResult.feedback" :key="i" class="ai-feedback-item">
                  <span class="fb-dot">•</span> {{ fb }}
                </div>
              </div>

              <!-- 연관 과제 -->
              <div class="ai-section">
                <div class="ai-section-title">
                  <svg width="13" height="13" fill="none" stroke="#8b5cf6" stroke-width="2" viewBox="0 0 24 24"><path d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>
                  연관 과제 연결
                  <span v-if="aiResult.matched_agendas?.length" class="ai-badge">AI 추천 {{ aiResult.matched_agendas.length }}건</span>
                </div>
                <div v-if="업로드회의체과제.length" class="agenda-check-list">
                  <label v-for="t in 업로드회의체과제" :key="t.id"
                    class="agenda-check-item" :class="{ recommended: aiMatchReason(t) }">
                    <input type="checkbox" :value="String(t.agenda_id ?? t.id)" v-model="uploadForm.relatedTodoIds"/>
                    <span class="agenda-check-body">
                      <span class="agenda-check-content">
                        {{ t.content }}
                        <span v-if="aiMatchReason(t)" class="ai-badge sm">AI 추천</span>
                      </span>
                      <span v-if="aiMatchReason(t)" class="matched-agenda-reason">{{ aiMatchReason(t) }}</span>
                    </span>
                  </label>
                </div>
                <p v-else class="agenda-auto-note" style="margin-top:6px">연결 가능한 과제를 찾지 못했습니다.</p>
                <div class="agenda-add-row">
                  <input v-model="newAgendaText" class="app-modal-input" type="text"
                    placeholder="연결할 과제를 직접 입력…"
                    @keydown.enter.prevent="submitCustomAgenda"/>
                  <button type="button" class="agenda-add-btn" :disabled="!newAgendaText.trim()" @click="submitCustomAgenda">추가</button>
                </div>
              </div>
            </template>

            <!-- 피드백 입력 단계 -->
            <div v-if="showFeedback" class="hitl-feedback-wrap">
              <div class="hitl-feedback-title">
                <svg width="15" height="15" fill="none" stroke="#a78bfa" stroke-width="2" viewBox="0 0 24 24"><path d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z"/></svg>
                AI 검토 결과 리뷰
              </div>
              <p class="hitl-feedback-desc">AI가 보고서를 잘 평가했나요? 개선이 필요한 부분이 있으면 알려주세요.</p>
              <textarea v-model="hitlFeedback" class="hitl-textarea"
                placeholder="예) 리스크 항목 평가가 너무 관대했습니다 / 연관 과제 추천이 정확했습니다 (선택)"
                rows="3"/>
            </div>

          </div>

          <!-- 푸터 -->
          <div class="app-modal-footer" style="justify-content:space-between">
            <!-- 로딩 중 -->
            <template v-if="aiAnalyzing">
              <span style="font-size:12px;color:#94a3b8">AI가 검토 중입니다…</span>
              <button class="app-btn-primary" disabled>검토 중…</button>
            </template>

            <!-- 결과 확인 중 -->
            <template v-else-if="aiResult && !showFeedback">
              <button class="app-btn-reject" @click="onReject">
                <svg width="12" height="12" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24"><path d="M6 18L18 6M6 6l12 12"/></svg>
                반려
              </button>
              <button class="app-btn-primary" @click="onApprove">
                <svg width="12" height="12" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24"><path d="M5 13l4 4L19 7"/></svg>
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
/* ── 레이더 차트 ── */
.radar-wrap { display: flex; flex-direction: column; align-items: center; gap: 10px; }
.radar-svg  { width: 200px; height: 210px; }

@keyframes dashRotate {
  to { stroke-dashoffset: -30; }
}
.radar-loading-dash {
  animation: dashRotate 1.2s linear infinite;
}
.radar-score-poly { transition: all 0.1s; }

.radar-stage {
  display: flex; align-items: center; gap: 6px;
  font-size: 12px; color: #64748b;
}
.radar-stage-dot {
  width: 7px; height: 7px; border-radius: 50%;
  background: #a78bfa;
  animation: pulse 1s ease-in-out infinite;
}
@keyframes pulse { 0%,100%{opacity:1} 50%{opacity:.3} }

/* ── 항목별 점수 바 ── */
.criteria-scores { width: 100%; max-width: 260px; display: flex; flex-direction: column; gap: 5px; }
.cs-row { display: flex; align-items: center; gap: 6px; }
.cs-label { font-size: 10px; color: #64748b; width: 52px; flex-shrink: 0; text-align: right; }
.cs-bar-wrap { flex: 1; height: 6px; background: #f1f5f9; border-radius: 3px; overflow: hidden; }
.cs-bar { height: 100%; border-radius: 3px; }
.cs-num { font-size: 10px; color: #94a3b8; width: 28px; flex-shrink: 0; }

/* ── 피드백 입력 ── */
.hitl-feedback-wrap { margin-top: 12px; display: flex; flex-direction: column; gap: 8px; }
.hitl-feedback-title {
  display: flex; align-items: center; gap: 6px;
  font-size: 13px; font-weight: 600; color: #1e293b;
}
.hitl-feedback-desc {
  font-size: 12px; color: #64748b; margin: 0;
}
.hitl-textarea {
  width: 100%; border: 1px solid #e2e8f0; border-radius: 8px;
  padding: 10px 12px; font-size: 13px; resize: vertical;
  outline: none; transition: border-color .15s;
  font-family: inherit;
}
.hitl-textarea:focus { border-color: #a78bfa; }

/* ── 재검토 토글 ── */
.resubmit-toggle {
  display: flex; align-items: center; gap: 8px;
  padding: 8px 10px; border-radius: 8px;
  background: #f8f5ff; border: 1px solid #e9d5ff;
  cursor: pointer; margin-bottom: 4px;
}
.resubmit-toggle input[type="checkbox"] { width: 14px; height: 14px; accent-color: #8b5cf6; flex-shrink: 0; }
.resubmit-toggle-label { font-size: 13px; font-weight: 600; color: #6d28d9; }
.resubmit-toggle-desc  { font-size: 11px; color: #9ca3af; }

/* ── 반려 버튼 ── */
.app-btn-reject {
  display: flex; align-items: center; gap: 5px;
  padding: 8px 16px; border-radius: 8px; font-size: 13px; font-weight: 600;
  border: 1.5px solid #ef4444; color: #ef4444; background: transparent;
  cursor: pointer; transition: background .15s;
}
.app-btn-reject:hover { background: #fef2f2; }
</style>
