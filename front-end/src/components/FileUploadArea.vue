<script setup>
import { ref } from 'vue'

const props = defineProps({
  file: { type: Object, default: null },
  multiple: { type: Boolean, default: false },
  accept: { type: String, default: '.pdf,.docx,.pptx,.xlsx,.ppt,.doc' },
  hint: { type: String, default: 'PDF · DOCX · PPT · XLSX' },
  label: { type: String, default: '파일 드래그 또는 클릭' }
})
const emit = defineEmits(['change'])

const inputRef = ref(null)

function handleClick() { inputRef.value?.click() }

function handleDrop(e) {
  const files = Array.from(e.dataTransfer.files)
  if (files.length) emit('change', files)
}

function handleInput(e) {
  const files = Array.from(e.target.files)
  if (files.length) emit('change', files)
  e.target.value = ''
}
</script>

<template>
  <div class="fua-area"
    @click="handleClick"
    @dragover.prevent
    @drop.prevent="handleDrop">
    <svg width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.5" viewBox="0 0 24 24">
      <path d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12"/>
    </svg>
    <span>{{ file ? file.name : label }}</span>
    <span class="fua-hint">{{ hint }}</span>
  </div>
  <input ref="inputRef" type="file" style="display:none" :multiple="multiple" :accept="accept" @change="handleInput" />
</template>

<style scoped>
.fua-area { border:1.5px dashed rgba(255,255,255,.12);border-radius:8px;padding:12px;display:flex;flex-direction:column;align-items:center;gap:4px;cursor:pointer;transition:border-color .18s,background .18s;color:#475569; }
.fua-area:hover { border-color:rgba(59,130,246,.5);background:rgba(59,130,246,.04);color:#64748b; }
.fua-hint { font-size:10px;color:#334155; }
</style>
