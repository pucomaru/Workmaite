<script setup>
import { ref, onMounted } from 'vue'
import { availableModels, defaultModel, selectedModel, fetchModels } from '../stores/llmModel'
import { atTypeDot } from '../composables/useAgentMention'

/**
 * 공통 AI 입력 컴포저 (textarea + @멘션 드롭다운 + 파일/컨텍스트 칩 + 툴바).
 * 아카이브 AI 사이드바와 회의 AI 사이드바가 동일하게 재사용한다.
 */
defineProps({
  modelValue: { type: String, default: '' },
  pendingFiles: { type: Array, default: () => [] },
  mentionedContexts: { type: Array, default: () => [] },
  atMenuOpen: { type: Boolean, default: false },
  atMenuItems: { type: Array, default: () => [] },
  atHighlight: { type: Number, default: 0 },
  atTypeLabels: { type: Object, default: () => ({}) },
  loading: { type: Boolean, default: false },
  canSend: { type: Boolean, default: false },
  attachDisabled: { type: Boolean, default: false },
  placeholder: { type: String, default: '질문하세요... (@ 컨텍스트 추가)' },
  multipleFiles: { type: Boolean, default: true },
})

const emit = defineEmits([
  'update:modelValue',
  'update:atHighlight',
  'input',
  'keydown',
  'send',
  'stop',
  'selectAtItem',
  'removeCtx',
  'pinCtx',
  'fileChange',
  'ready',
])

const textareaEl = ref(null)
const fileInput = ref(null)

defineExpose({ textareaEl, fileInput, focus: () => textareaEl.value?.focus() })

onMounted(() => {
  emit('ready', { textareaEl: textareaEl.value, fileInput: fileInput.value })
  fetchModels()
})

function onInput(e) {
  emit('update:modelValue', e.target.value)
  emit('input', e)
}
function onFileChange(e) {
  emit('fileChange', e)
}

// ── 모델 선택 드롭업 ──────────────────────────────────
const modelMenuOpen = ref(false)

function selectModel(m) {
  selectedModel.value = m
  modelMenuOpen.value = false
}
</script>

<template>
  <div class="agent-composer" :class="{ responding: loading }">
    <!-- @ 드롭다운 -->
    <Transition name="at-menu">
      <div v-if="atMenuOpen && atMenuItems.length" class="at-menu">
        <div
          v-for="(item, i) in atMenuItems"
          :key="item.id"
          class="at-menu-item"
          :class="{ active: i === atHighlight }"
          @mousedown.prevent="emit('selectAtItem', item)"
          @mouseover="emit('update:atHighlight', i)"
        >
          <span class="at-dot" :style="{ background: atTypeDot(item.type) }"></span>
          <span class="at-type">{{ atTypeLabels[item.type] }}</span>
          <span class="at-label">{{ item.label }}</span>
        </div>
        <div class="at-menu-hint">↑↓ 이동 · Enter 선택 · Esc 닫기</div>
      </div>
    </Transition>
    <!-- 파일 chips -->
    <div v-if="pendingFiles.length" class="agent-file-chips">
      <span v-for="f in pendingFiles" :key="f.name" class="agent-file-chip">📎 {{ f.name }}</span>
    </div>
    <!-- @ 컨텍스트 chips — 좌측 X(미포함/제외)·핀(포함 고정) -->
    <div v-if="mentionedContexts.length" class="agent-ctx-chips">
      <span
        v-for="c in mentionedContexts"
        :key="c.id"
        class="agent-ctx-chip"
        :class="{ pinned: c.pinned }"
      >
        <!-- 토글: 선택(pinned)=X(제거) / 미고정=핀(고정) — 한 번에 하나만 표시 -->
        <button
          v-if="c.pinned"
          class="ctx-chip-act"
          title="컨텍스트에서 제거"
          @click="emit('removeCtx', c.id)"
        >
          <svg
            width="9"
            height="9"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="3"
            stroke-linecap="round"
          >
            <path d="M6 6l12 12M18 6L6 18" />
          </svg>
        </button>
        <button v-else class="ctx-chip-act" title="컨텍스트 고정" @click="emit('pinCtx', c.id)">
          <svg
            width="10"
            height="10"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
            stroke-linecap="round"
            stroke-linejoin="round"
          >
            <path d="M12 17v5" />
            <path d="M9 10.8V5a2 2 0 0 1 2-2h2a2 2 0 0 1 2 2v5.8l1.5 2.2h-9z" />
          </svg>
        </button>
        <span class="at-dot" :style="{ background: atTypeDot(c.type) }"></span>
        <span class="ctx-chip-text">{{ c.label }}</span>
      </span>
    </div>
    <textarea
      ref="textareaEl"
      name="agent-input"
      :value="modelValue"
      class="agent-textarea"
      :placeholder="placeholder"
      rows="1"
      @input="onInput"
      @keydown="emit('keydown', $event)"
    />
    <div class="agent-composer-toolbar">
      <div class="composer-toolbar-left">
        <button
          class="agent-attach-btn"
          :disabled="attachDisabled"
          @click="fileInput?.click()"
          title="파일 첨부"
        >
          ＋
        </button>
        <!-- 모델 선택 드롭업 -->
        <div v-if="availableModels.length" class="model-select-wrap">
          <button
            class="model-select-btn"
            :class="{ open: modelMenuOpen }"
            title="모델 선택"
            @click="modelMenuOpen = !modelMenuOpen"
            @blur="modelMenuOpen = false"
          >
            <span class="model-select-label">{{ selectedModel || defaultModel || '모델' }}</span>
            <svg
              width="9"
              height="9"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2.5"
              stroke-linecap="round"
            >
              <path d="M18 15l-6-6-6 6" />
            </svg>
          </button>
          <Transition name="model-menu">
            <div v-if="modelMenuOpen" class="model-menu">
              <div
                class="model-menu-item"
                :class="{ active: !selectedModel }"
                @mousedown.prevent="selectModel(null)"
              >
                기본
                <span v-if="defaultModel" class="model-menu-default">({{ defaultModel }})</span>
              </div>
              <div
                v-for="m in availableModels"
                :key="m"
                class="model-menu-item"
                :class="{ active: selectedModel === m }"
                @mousedown.prevent="selectModel(m)"
              >
                {{ m }}
              </div>
            </div>
          </Transition>
        </div>
      </div>
      <button v-if="loading" class="agent-send-btn" @click="emit('stop')" title="응답 중단">
        ■
      </button>
      <button v-else class="agent-send-btn" :disabled="!canSend" @click="emit('send')" title="전송">
        <svg
          width="15"
          height="15"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          stroke-width="2.4"
          stroke-linecap="round"
          stroke-linejoin="round"
        >
          <line x1="12" y1="19" x2="12" y2="5" />
          <polyline points="5 12 12 5 19 12" />
        </svg>
      </button>
    </div>
    <input
      name="file"
      ref="fileInput"
      type="file"
      :multiple="multipleFiles"
      style="display: none"
      @change="onFileChange"
    />
  </div>
</template>
