<script setup>
import { inject, ref, computed } from 'vue'
import ProcessStepBar from './ProcessStepBar.vue'
import FileUploadArea from './FileUploadArea.vue'
const {
  showUploadModal, nightMode, uploadStep, uploadForm,
  gNodes, deptConnectableNodes, 업로드회의체과제, prefilledCtx,
  addCustomAgenda,
  REL_COLORS, autoRel, runAiAnalysis,
  aiAnalyzing, aiResult, aiStreamText, aiStreamStage, PRESENTATION_CRITERIA, doAddFile,
} = inject('archiveModals')

// AI가 추천한 과제인지 판별하고 추천 이유를 반환
function aiMatchReason(t) {
  const id = String(t.agenda_id ?? t.id)
  const m = (aiResult.value?.matched_agendas || []).find(x => String(x.id) === id)
  return m ? (m.reason || 'AI가 관련 과제로 추천') : ''
}

// 스트리밍 중인 부분 JSON에서 점수를 추출
const streamScore = computed(() => {
  const m = (aiStreamText.value || '').match(/"score"\s*:\s*(\d+)/)
  return m ? parseInt(m[1]) : null
})

// 스트리밍 중인 부분 JSON에서 완성된 feedback 항목들을 추출
const streamFeedback = computed(() => {
  const text = aiStreamText.value || ''
  const start = text.search(/"feedback"\s*:\s*\[/)
  if (start < 0) return []
  const arrStart = text.indexOf('[', start)
  const region = text.slice(arrStart + 1)
  // 닫는 ']' 이전까지만
  const end = region.indexOf(']')
  const body = end >= 0 ? region.slice(0, end) : region
  // 완성된 "..." 문자열만 추출 (이스케이프 처리)
  const items = []
  const re = /"((?:[^"\\]|\\.)*)"/g
  let mm
  while ((mm = re.exec(body)) !== null) {
    items.push(mm[1].replace(/\\"/g, '"').replace(/\\n/g, ' '))
  }
  return items
})

// 직접 입력한 과제 추가
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
            @step-click="i => { if (i === 0) uploadStep = 1 }"
          />
        </div>

        <template v-if="uploadStep===1">
          <div class="app-modal-header">
            <span class="app-modal-title">자료 정보 입력</span>
            <button class="app-modal-close" @click="showUploadModal=false"><svg width="14" height="14" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24"><path d="M6 18L18 6M6 6l12 12"/></svg></button>
          </div>
          <div class="app-modal-body">
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
                <option v-for="n in gNodes.filter(n=>n.type==='meeting_group')" :key="n.id" :value="n.id">{{ n.label }}</option>
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
              <span class="conn-node">{{ deptConnectableNodes.find(n=>n.id===uploadForm.connectNodeId)?.label }}</span>
              <span class="conn-arrow">→</span>
              <span class="conn-rel" :style="{color:REL_COLORS[autoRel(uploadForm.connectNodeId,'file')]||'#a78bfa'}">{{ autoRel(uploadForm.connectNodeId,'file') }}</span>
              <span class="conn-arrow">→</span>
              <span class="conn-node file">{{ uploadForm.label }}</span>
            </div>
          </div>
          <div class="app-modal-footer">
            <button class="app-btn-cancel" @click="showUploadModal=false">취소</button>
            <button class="app-btn-primary"
              :disabled="!uploadForm.label.trim() || !uploadForm.connectNodeId"
              @click="runAiAnalysis">
              <svg width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24" style="margin-right:5px"><path d="M12 2a10 10 0 100 20A10 10 0 0012 2z"/><path d="M12 8v4l3 3"/></svg>
              AI 검토 시작
            </button>
          </div>
        </template>

        <template v-else-if="uploadStep===2">
          <div class="app-modal-header">
            <span class="app-modal-title">AI 검토 결과 <span style="font-size:11px;opacity:.6;font-weight:400">— {{ uploadForm.label }}</span></span>
            <button class="app-modal-close" @click="showUploadModal=false"><svg width="14" height="14" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24"><path d="M6 18L18 6M6 6l12 12"/></svg></button>
          </div>
          <div class="app-modal-body ai-result-body">

            <div v-if="aiAnalyzing" class="ai-loading-wrap">
              <div class="ai-loading-spinner"></div>
              <div class="ai-loading-text">
                AI가 자료를 검토하고 있습니다…
                <br><span style="font-size:11px;opacity:.6">{{ aiStreamStage || '아카이브 기반으로 자료 검토 중' }}</span>
              </div>
              <div v-if="streamScore !== null" class="ai-stream-score">
                적합성 점수 <strong :style="{color: streamScore>=80?'#10b981':streamScore>=60?'#f59e0b':'#ef4444'}">{{ streamScore }}</strong> / 100
              </div>
              <div v-if="streamFeedback.length" class="ai-stream-feedback">
                <div v-for="(fb,i) in streamFeedback" :key="i" class="ai-feedback-item ai-stream-item">
                  <span class="fb-dot">•</span> {{ fb }}
                </div>
                <span class="ai-stream-caret">▋</span>
              </div>
            </div>

            <template v-else-if="aiResult">
              <div class="ai-score-section">
                <div class="ai-score-label">자료 적합성 점수</div>
                <div class="ai-score-gauge-wrap">
                  <svg width="110" height="60" viewBox="0 0 110 60">
                    <path d="M10 55 A45 45 0 0 1 100 55" fill="none" stroke="#e2e8f0" stroke-width="10" stroke-linecap="round"/>
                    <path d="M10 55 A45 45 0 0 1 100 55" fill="none"
                      :stroke="aiResult.score>=80?'#10b981':aiResult.score>=60?'#f59e0b':'#ef4444'"
                      stroke-width="10" stroke-linecap="round"
                      :stroke-dasharray="`${(aiResult.score/100)*141.3} 141.3`"/>
                    <text x="55" y="53" text-anchor="middle" font-size="18" font-weight="700"
                      :fill="aiResult.score>=80?'#10b981':aiResult.score>=60?'#f59e0b':'#ef4444'">{{ aiResult.score }}</text>
                  </svg>
                  <div class="ai-score-desc" :style="{color:aiResult.score>=80?'#10b981':aiResult.score>=60?'#d97706':'#dc2626'}">
                    {{ aiResult.score>=80?'우수':'적합'}} / 100
                  </div>
                </div>
                <div class="ai-feedback-list">
                  <div v-for="(fb,i) in aiResult.feedback" :key="i" class="ai-feedback-item">
                    <span class="fb-dot">•</span> {{ fb }}
                  </div>
                </div>
              </div>

              <div class="ai-section">
                <div class="ai-section-title">
                  <svg width="13" height="13" fill="none" stroke="#8b5cf6" stroke-width="2" viewBox="0 0 24 24"><path d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>
                  연관 과제 연결
                  <span v-if="aiResult.matched_agendas?.length" class="ai-badge">AI 추천 {{ aiResult.matched_agendas.length }}건</span>
                </div>
                <p v-if="업로드회의체과제.length" class="agenda-auto-note" style="margin-bottom:8px">
                  AI가 추천한 과제가 자동 선택되어 있습니다. 직접 추가하거나 해제할 수 있습니다.
                </p>
                <div v-if="업로드회의체과제.length" class="agenda-check-list">
                  <label
                    v-for="t in 업로드회의체과제"
                    :key="t.id"
                    class="agenda-check-item"
                    :class="{ recommended: aiMatchReason(t) }"
                  >
                    <input
                      type="checkbox"
                      :value="String(t.agenda_id ?? t.id)"
                      v-model="uploadForm.relatedTodoIds"
                    />
                    <span class="agenda-check-body">
                      <span class="agenda-check-content">
                        {{ t.content }}
                        <span v-if="aiMatchReason(t)" class="ai-badge sm">AI 추천</span>
                        <span v-else-if="t.isCustom" class="ai-badge sm custom">직접 추가</span>
                      </span>
                      <span v-if="aiMatchReason(t)" class="matched-agenda-reason">{{ aiMatchReason(t) }}</span>
                    </span>
                  </label>
                </div>
                <p v-else class="agenda-auto-note" style="margin-top:6px">
                  AI가 이 회의체에 연결 가능한 과제를 찾지 못했습니다. 아래에서 직접 추가하세요.
                </p>
                <div class="agenda-add-row">
                  <input
                    v-model="newAgendaText"
                    class="app-modal-input"
                    type="text"
                    placeholder="연결할 과제를 직접 입력…"
                    @keydown.enter.prevent="submitCustomAgenda"
                  />
                  <button type="button" class="agenda-add-btn" :disabled="!newAgendaText.trim()" @click="submitCustomAgenda">추가</button>
                </div>
              </div>

              <div v-if="uploadForm.fileType==='발제자료'" class="ai-section">
                <div class="ai-section-title">
                  <svg width="13" height="13" fill="none" stroke="#f59e0b" stroke-width="2" viewBox="0 0 24 24"><path d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>
                  발제자료 검토 기준 (Why/What/How)
                </div>
                <div class="criteria-list">
                  <div v-for="c in PRESENTATION_CRITERIA" :key="c.key" class="criteria-row">
                    <span class="criteria-dot" :class="aiResult.criteria?.[c.key] ? 'pass' : 'fail'">
                      <svg v-if="aiResult.criteria?.[c.key]" width="9" height="9" fill="none" stroke="currentColor" stroke-width="3" viewBox="0 0 24 24"><path d="M5 13l4 4L19 7"/></svg>
                      <svg v-else width="9" height="9" fill="none" stroke="currentColor" stroke-width="3" viewBox="0 0 24 24"><path d="M6 18L18 6M6 6l12 12"/></svg>
                    </span>
                    <div class="criteria-text">
                      <div class="criteria-label">{{ c.label }}</div>
                      <div class="criteria-desc">{{ c.desc }}</div>
                    </div>
                  </div>
                </div>
              </div>
            </template>
          </div>
          <div class="app-modal-footer" style="justify-content:space-between">
            <button class="app-btn-cancel" @click="uploadStep=1; aiResult=null">← 다시 입력</button>
            <button class="app-btn-primary" :disabled="aiAnalyzing || !aiResult" @click="doAddFile">
              <svg width="12" height="12" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24" style="margin-right:4px"><path d="M5 13l4 4L19 7"/></svg>
              아카이브 등록 확정
            </button>
          </div>
        </template>

      </div>
    </div>
  </Teleport>
</template>
