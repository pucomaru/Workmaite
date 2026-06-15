<template>
  <div class="cdate-wrap" ref="wrapRef">
    <input
      :id="fieldId"
      :name="fieldName"
      ref="textRef"
      type="text"
      inputmode="numeric"
      autocomplete="off"
      v-bind="textAttrs"
      :placeholder="placeholder"
      :value="display"
      @input="onInput"
      @blur="onBlur"
      @keydown="onKeydown"
    />
    <button
      type="button"
      class="cdate-btn"
      tabindex="-1"
      aria-label="달력 열기"
      @click="openPicker"
    >
      <svg
        width="16"
        height="16"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        stroke-width="2"
        stroke-linecap="round"
        stroke-linejoin="round"
      >
        <rect x="3" y="4" width="18" height="18" rx="2" />
        <line x1="16" y1="2" x2="16" y2="6" />
        <line x1="8" y1="2" x2="8" y2="6" />
        <line x1="3" y1="10" x2="21" y2="10" />
      </svg>
    </button>
    <input
      :id="`${fieldId}-native`"
      :name="`${fieldName}-native`"
      ref="nativeRef"
      type="date"
      class="cdate-native"
      tabindex="-1"
      aria-hidden="true"
      :min="min"
      :max="max"
      :value="modelValue"
      @input="onNative"
      @blur="pickerOpen = false"
    />
    <div v-if="pickerOpen" class="cdate-overlay" @mousedown.prevent="closePicker" />
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, onUnmounted, useAttrs, useId } from 'vue'

defineOptions({ inheritAttrs: false })

// 폼 필드 id/name — 호출자가 넘긴 id를 우선 사용하고, 없으면 인스턴스 고유 id를 생성한다.
// (정적 id를 쓰면 한 폼에 여러 DateInput이 들어갈 때 id가 중복된다.)
const attrs = useAttrs()
const _uid = useId()
const fieldId = computed(() => attrs.id ?? `cdate-${_uid}`)
const fieldName = computed(() => attrs.name ?? fieldId.value)
// id/name은 위에서 직접 바인딩하므로 $attrs 스프레드에서는 제외(이중 바인딩 방지)
const textAttrs = computed(() => {
  // eslint-disable-next-line no-unused-vars
  const { id, name, ...rest } = attrs
  return rest
})

const props = defineProps({
  modelValue: { type: String, default: '' },
  min: { type: String, default: '1900-01-01' },
  max: { type: String, default: '9999-12-31' },
  placeholder: { type: String, default: 'YYYY-MM-DD' },
})
const emit = defineEmits(['update:modelValue'])

const textRef = ref(null)
const nativeRef = ref(null)
const wrapRef = ref(null)
const pickerOpen = ref(false)

function onDocMousedown(e) {
  if (wrapRef.value && !wrapRef.value.contains(e.target)) {
    nativeRef.value?.blur()
  }
}

onMounted(() => document.addEventListener('mousedown', onDocMousedown))
onUnmounted(() => document.removeEventListener('mousedown', onDocMousedown))
const display = ref(formatFromValue(props.modelValue))

watch(
  () => props.modelValue,
  v => {
    display.value = formatFromValue(v)
  },
)

function formatFromValue(v) {
  if (!v) return ''
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(v)
  return m ? `${m[1]}-${m[2]}-${m[3]}` : ''
}

function formatDigits(digits) {
  const y = digits.slice(0, 4)
  const mo = digits.slice(4, 6)
  const d = digits.slice(6, 8)
  let out = y
  if (digits.length >= 4) out += '-' + mo
  if (digits.length >= 6) out += '-' + d
  return out
}

function onInput(e) {
  const digits = e.target.value.replace(/\D/g, '').slice(0, 8)
  display.value = formatDigits(digits)
  if (digits.length === 8) commit(display.value)
}

function onKeydown(e) {
  if (e.key === 'Enter') commit(display.value)
}

function onBlur() {
  commit(display.value)
}

function clamp(val) {
  if (props.min && val < props.min) return props.min
  if (props.max && val > props.max) return props.max
  return val
}

function isValid(y, mo, d) {
  if (mo < 1 || mo > 12) return false
  const dim = new Date(y, mo, 0).getDate()
  return d >= 1 && d <= dim
}

function commit(str) {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(str)
  if (!m) {
    // incomplete/invalid -> revert to current model value
    display.value = formatFromValue(props.modelValue)
    return
  }
  const y = +m[1],
    mo = +m[2],
    d = +m[3]
  if (!isValid(y, mo, d)) {
    display.value = formatFromValue(props.modelValue)
    return
  }
  const next = clamp(str)
  display.value = next
  if (next !== props.modelValue) emit('update:modelValue', next)
}

function openPicker() {
  const el = nativeRef.value
  if (!el) return
  pickerOpen.value = true
  if (typeof el.showPicker === 'function') {
    try {
      el.showPicker()
      return
    } catch {
      /* fall through */
    }
  }
  el.focus()
  el.click()
}

function closePicker() {
  pickerOpen.value = false
  textRef.value?.focus()
}

function onNative(e) {
  const v = e.target.value
  if (v) emit('update:modelValue', v)
  pickerOpen.value = false
}
</script>

<style scoped>
.cdate-wrap {
  position: relative;
  display: inline-flex;
  align-items: center;
  width: 100%;
}
.cdate-wrap > input[type='text'] {
  width: 100%;
  padding-right: 30px;
}
.cdate-btn {
  position: absolute;
  right: 6px;
  top: 50%;
  transform: translateY(-50%);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 2px;
  border: none;
  background: transparent;
  color: var(--text-secondary, #888);
  cursor: pointer;
  border-radius: 4px;
}
.cdate-btn:hover {
  color: var(--text-primary, #333);
}
.cdate-native {
  position: absolute;
  right: 6px;
  bottom: 0;
  width: 1px;
  height: 1px;
  opacity: 0;
  pointer-events: none;
}
.cdate-overlay {
  position: fixed;
  inset: 0;
  z-index: 9999;
}
</style>
