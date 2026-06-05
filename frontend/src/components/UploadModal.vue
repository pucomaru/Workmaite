<script setup>
import { inject } from 'vue'
import ProcessStepBar from './ProcessStepBar.vue'
import FileUploadArea from './FileUploadArea.vue'
const {
  showUploadModal, nightMode, uploadStep, uploadForm,
  gNodes, deptConnectableNodes, 업로드회의체과제, prefilledCtx,
  REL_COLORS, autoRel, runAiAnalysis,
  aiAnalyzing, aiResult, PRESENTATION_CRITERIA, doAddFile,
} = inject('archiveModals')
</script>

<template>
  <Teleport to="body">
    <div v-if="showUploadModal" class="app-modal-backdrop" @click.self="showUploadModal=false">
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
                @change="files => { uploadForm.file = files[0]; uploadForm.label = uploadForm.label || files[0]?.name }"
              />
            </div>
            <div class="app-modal-field">
              <label>자료명 <span class="req">*</span></label>
              <input v-model="uploadForm.label" class="app-modal-input" placeholder="예: 2025년 1분기 전략보고서.pdf" />
            </div>

            <div class="app-modal-field">
              <label>관련 회의체 <span class="req">*</span><span v-if="prefilledCtx.meetingId" class="prefill-label">자동 입력됨</span></label>
              <select v-model="uploadForm.meetingId" class="app-modal-input" :class="{ 'prefilled': uploadForm.meetingId }"
                @change="prefilledCtx.meetingId = false; prefilledCtx.connectNodeId = false">
                <option value="">회의체 선택...</option>
                <option v-for="n in gNodes.filter(n=>n.type==='meeting_group')" :key="n.id" :value="n.id">{{ n.label }}</option>
              </select>
            </div>

            <div class="app-modal-field">
              <label>업로드 부서 <span class="req">*</span><span v-if="prefilledCtx.connectNodeId" class="prefill-label">자동 입력됨</span></label>
              <select v-model="uploadForm.connectNodeId" class="app-modal-input" :class="{ 'prefilled': uploadForm.connectNodeId }"
                @change="prefilledCtx.connectNodeId = false">
                <option value="">부서 선택...</option>
                <option v-for="n in deptConnectableNodes" :key="n.id" :value="n.id">{{ n.label }}</option>
              </select>
            </div>

            <div class="app-modal-field">
              <label>연관 과제 <span class="req">*</span><span v-if="prefilledCtx.relatedTodoId" class="prefill-label">자동 입력됨</span></label>
              <select v-model="uploadForm.relatedTodoId" class="app-modal-input" :class="{ 'prefilled': uploadForm.relatedTodoId }"
                :disabled="!uploadForm.meetingId" @change="prefilledCtx.relatedTodoId = false">
                <option value="">{{ uploadForm.meetingId ? (업로드회의체과제.length ? '과제 선택...' : '연결된 과제가 없습니다') : '회의체를 먼저 선택하세요' }}</option>
                <option v-for="t in 업로드회의체과제" :key="t.id" :value="String(t.agenda_id ?? t.id)">{{ t.content }}</option>
              </select>
            </div>

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
              <div class="ai-loading-text">AI가 자료를 검토하고 있습니다…<br><span style="font-size:11px;opacity:.6">GraphDB 맥락 + 조직 암묵지 분석 중</span></div>
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
