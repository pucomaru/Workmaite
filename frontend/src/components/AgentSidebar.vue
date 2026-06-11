<script setup>
import { inject, ref, onMounted } from 'vue'
import { renderMd } from '../composables/useMarkdown'
import AgentComposer from './AgentComposer.vue'

const {
  SUPERVISOR, agentInfo, agentSidebarOpen, clearAgentChat,
  agentMessagesEl, currentMessages, agentLoading,
  atMenuOpen, atMenuItems, atHighlight, AT_TYPE_LABELS, selectAtItem,
  agentPendingFiles, mentionedContexts, removeMentionCtx,
  agentTextareaEl, agentInput, onAgentInput, onAgentKeydown,
  sendAgentMsg, onAgentFileSelected, triggerAtSuggest, loadChatHistory,
} = inject('agentSidebar')

// 사이드바가 열릴 때마다(v-if로 mount) 채팅 히스토리를 즉시 로드 후 맨 아래로 스크롤
onMounted(async () => {
  await loadChatHistory()
  requestAnimationFrame(() => {
    if (agentMessagesEl.value) agentMessagesEl.value.scrollTop = agentMessagesEl.value.scrollHeight
  })
})

const composerRef = ref(null)
// 공통 컴포저가 마운트되면 내부 textarea를 컴포저블 ref에 연결 (@멘션 커서/포커스용)
function onComposerReady({ textareaEl }) { agentTextareaEl.value = textareaEl }

// ─── 사이드바 리사이즈 ────────────────────────────────────────
const sidebarW = ref(320)
let resizing = false, startX = 0, startW = 0
function onResizeStart(e) {
  resizing = true; startX = e.clientX; startW = sidebarW.value
  document.addEventListener('mousemove', onResizeMove)
  document.addEventListener('mouseup', onResizeEnd)
  e.preventDefault()
}
function onResizeMove(e) {
  if (!resizing) return
  sidebarW.value = Math.max(260, Math.min(520, startW - (e.clientX - startX)))
}
function onResizeEnd() {
  resizing = false
  document.removeEventListener('mousemove', onResizeMove)
  document.removeEventListener('mouseup', onResizeEnd)
}
</script>

<template>
  <Transition name="agent-sidebar-slide">
    <div v-if="agentSidebarOpen" class="agent-right-sidebar" :style="{ width: sidebarW + 'px' }">
        <div class="agent-resize-handle" @mousedown="onResizeStart"></div>
        <!-- Supervisor header -->
        <div class="agent-supervisor-header">
          <div class="supervisor-brand">
            <img :src="SUPERVISOR.avatar" class="supervisor-logo" />
            <div class="supervisor-brand-text">
              <span class="supervisor-title">{{ SUPERVISOR.name }}</span>
              <span class="supervisor-sub">{{ SUPERVISOR.subtitle }}</span>
            </div>

          </div>
          <div class="supervisor-header-actions">
            <button class="agent-new-chat-btn" @click="clearAgentChat">새 채팅</button>
            <button class="agent-sidebar-close" @click="agentSidebarOpen=false">✕</button>
          </div>
        </div>
        <!-- Messages -->
        <div ref="agentMessagesEl" class="agent-messages">
          <div v-for="(msg,i) in currentMessages" :key="i" class="agent-msg-row" :class="msg.role === 'planning' ? 'planning' : msg.role">

            <!-- 사고 과정 블록 -->
            <template v-if="msg.role==='planning'">
              <div class="agent-msg-label">
                <img :src="agentInfo.avatar" class="agent-msg-avatar" />
                {{ agentInfo.name }}
              </div>
              <div class="agent-planning-block" :class="{ done: msg.done, open: msg.open }">
                <button class="agent-planning-toggle" @click="msg.open = !msg.open">
                  <svg v-if="!msg.done" class="agent-planning-spinner" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="#00ab36" stroke-width="2.5"><path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83"/></svg>
                  <svg v-else width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="#00ab36" stroke-width="2.5"><path d="M9 12l2 2 4-4"/><circle cx="12" cy="12" r="10"/></svg>
                  <span class="agent-planning-label">
                    <template v-if="!msg.steps.length">{{ msg.done ? '완료' : '분석 중...' }}</template>
                    <template v-else>{{ msg.steps[msg.steps.length - 1].length > 58 ? msg.steps[msg.steps.length - 1].slice(0, 57) + '…' : msg.steps[msg.steps.length - 1] }}</template>
                  </span>
                  <span class="agent-planning-count">{{ msg.steps.length }} steps</span>
                  <svg class="agent-planning-chev" :class="{ rotated: msg.open }" width="11" height="11" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M19 9l-7 7-7-7"/></svg>
                </button>
                <div v-if="msg.open" class="agent-planning-steps">
                  <div v-for="(step, si) in msg.steps" :key="si"
                       class="agent-planning-step fade-in"
                       :class="{
                         'agent-step-data':  step.includes('→') || step.includes('확인') || step.includes('수집') || step.includes('분석'),
                         'agent-step-route': step.includes('위임') || step.includes('라우팅'),
                       }">
                    <span v-if="step.includes('위임') || step.includes('라우팅')" class="agent-step-icon-data">
                      <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M5 12h14M12 5l7 7-7 7"/></svg>
                    </span>
                    <span v-else-if="step.includes('확인') || step.includes('분석') || step.includes('수집') || step.includes('탐색')" class="agent-step-icon-data">
                      <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><circle cx="8" cy="12" r="3"/><circle cx="18" cy="7" r="2"/><circle cx="18" cy="17" r="2"/><line x1="11" y1="11" x2="16" y2="8"/><line x1="11" y1="13" x2="16" y2="16"/></svg>
                    </span>
                    <span v-else class="agent-step-num">{{ si + 1 }}</span>
                    <span class="agent-step-text">{{ step }}</span>
                  </div>
                  <div v-if="!msg.done" class="agent-planning-step agent-step-pending">
                    <span class="agent-step-dots"><span></span><span></span><span></span></span>
                  </div>
                </div>
              </div>
            </template>

            <!-- AI 응답 -->
            <template v-else-if="msg.role==='agent'&&msg.content">
              <div v-if="currentMessages[i-1]?.role !== 'planning'" class="agent-msg-label">
                <img :src="agentInfo.avatar" class="agent-msg-avatar" />
                {{ agentInfo.name }}
              </div>
              <div class="agent-bubble agent theme-supervisor"
                   :class="{ 'is-streaming': agentLoading && i === currentMessages.length - 2 }"
                   v-html="renderMd(msg.content)"></div>
              <div v-if="i===0&&(agentInfo.suggested?.length||agentInfo.suggestedAt?.length)" class="agent-suggested">
                <button
                  v-for="s in agentInfo.suggested" :key="s"
                  class="suggested-btn" :disabled="agentLoading"
                  @click="agentInput=s;sendAgentMsg()"
                >{{ s }}</button>
                <template v-if="agentInfo.suggestedAt?.length">
                  <div class="suggested-section-label">@ 붙여서 범위 지정</div>
                  <button
                    v-for="s in agentInfo.suggestedAt" :key="'at-'+s"
                    class="suggested-btn suggested-btn--at" :disabled="agentLoading"
                    :title="'클릭하면 회의체·회의 목록에서 선택할 수 있어요'"
                    @click="triggerAtSuggest()"
                  >{{ s }}</button>
                </template>
              </div>
            </template>

            <!-- 사용자 메시지 -->
            <div v-else-if="msg.role==='user'" class="agent-bubble user">
              <div>{{ msg.content }}</div>
              <div v-if="msg.contexts?.length" class="user-ctx-chips">
                <span v-for="c in msg.contexts" :key="c.id" class="user-ctx-chip">{{ c.icon }} {{ c.label }}</span>
              </div>
            </div>
          </div>
          <div v-if="agentLoading&&currentMessages[currentMessages.length-1]?.role==='agent'&&currentMessages[currentMessages.length-1]?.content===''" class="agent-msg-row agent">
            <div class="agent-bubble agent typing"><span></span><span></span><span></span></div>
          </div>
        </div>
        <!-- Input -->
        <AgentComposer
          ref="composerRef"
          v-model="agentInput"
          :pending-files="agentPendingFiles"
          :mentioned-contexts="mentionedContexts"
          :at-menu-open="atMenuOpen"
          :at-menu-items="atMenuItems"
          v-model:at-highlight="atHighlight"
          :at-type-labels="AT_TYPE_LABELS"
          :loading="agentLoading"
          :can-send="!!(agentInput.trim() || agentPendingFiles.length || mentionedContexts.length)"
          @input="onAgentInput"
          @keydown="onAgentKeydown"
          @send="sendAgentMsg"
          @select-at-item="selectAtItem"
          @remove-ctx="removeMentionCtx"
          @file-change="onAgentFileSelected"
          @ready="onComposerReady"
        />
      </div>
    </Transition>
</template>
