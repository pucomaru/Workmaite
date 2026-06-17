<script setup>
import { nextTick, computed } from 'vue'
import { apiAI } from '../api'
import DateInput from './DateInput.vue'

const props = defineProps({
  items: { type: Array, required: true },
  memberCompanies: { type: Array, default: () => [] },
  memberDepts: { type: Array, default: () => [] },
  removeOnApprove: { type: Boolean, default: true },
  showFooter: { type: Boolean, default: false },
  showFeedback: { type: Boolean, default: true },
  saving: { type: Boolean, default: false }, // 저장 처리중 — 버튼 비활성 + 무지개 글로우
})

const emit = defineEmits(['approved', 'rejected', 'remove', 'save'])

const approvedCount = computed(() => props.items.filter(a => a._state === 'approved').length)
const rejectedCount = computed(() => props.items.filter(a => a._state === 'rejected').length)

function startApprove(i) {
  const ag = props.items[i]
  if (!props.removeOnApprove) {
    ag._state = ag._state === 'approved' ? null : 'approved'
    ag._showReason = false
  } else {
    emit('approved', i)
  }
}

function startReject(i) {
  const ag = props.items[i]
  if (props.removeOnApprove) {
    emit('rejected', i)
    return
  }
  if (ag._state === 'rejected') {
    ag._state = null
    ag._showReason = false
    return
  }
  if (ag._directAdd) {
    emit('remove', i)
    return
  }
  ag._origTitle = ag.title
  ag._origCompany = ag.company
  ag._origDept = ag.dept
  ag._origStartDate = ag.start_date
  ag._origEndDate = ag.end_date
  ag._feedbackAction = 'rejected'
  ag._showReason = true
  ag._state = 'rejected'
  scrollReasonIntoView(i)
}

const reasonRefs = {}

function scrollReasonIntoView(i) {
  nextTick(() => {
    const el = reasonRefs[i]
    if (el) el.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
  })
}

function startEdit(i) {
  const ag = props.items[i]
  ag._origTitle = ag.title
  ag._origCompany = ag.company
  ag._origDept = ag.dept
  ag._origStartDate = ag.start_date
  ag._origEndDate = ag.end_date
  ag._editTitle = ag.title
  ag._editCompany = ag.company || ''
  ag._editDept = ag.dept || ''
  ag._editStartDate = ag.start_date
  ag._editEndDate = ag.end_date
  ag._editing = true
}

function saveEdit(i) {
  const ag = props.items[i]
  ag.title = ag._editTitle
  ag.company = ag._editCompany
  ag.dept = ag._editDept
  ag.start_date = ag._editStartDate
  ag.end_date = ag._editEndDate
  ag._editing = false
  if (props.showFeedback && !ag._directAdd) {
    ag._feedbackAction = 'edited'
    ag._showReason = true
  }
}

function cancelEdit(i) {
  const ag = props.items[i]
  ag._editing = false
  if (!ag.title || ag._directAdd) emit('remove', i)
}

async function saveFeedback(i) {
  const ag = props.items[i]
  if (ag.db_id) {
    try {
      await apiAI.post('/api/agent/hitl-reviews', {
        target_type: 'agenda',
        agenda_id: ag.db_id,
        agent_log_id: ag._agentLogId || null,
        status: ag._feedbackAction || 'edited',
        comment: ag._reason || null,
      })
    } catch (e) {
      console.warn('[hitl-reviews] 저장 실패 (계속 진행):', e)
    }
  }
  ag._showReason = false
  ag._reason = ''
  if (ag._feedbackAction === 'rejected') {
    emit('rejected', i)
  } else {
    if (!props.removeOnApprove) ag._state = 'approved'
    emit('approved', i)
  }
}

function fmtDate(d) {
  if (!d || d === 'null' || d === 'NULL') return ''
  return d.replace(/-/g, '.')
}

function validDate(d) {
  return !!d && d !== 'null' && d !== 'NULL'
}

function deptList(dept) {
  if (!dept) return []
  return Array.isArray(dept) ? dept : [dept]
}

// ─── 담당 회사/부서 자동완성 ────────────────────────────────────────────
// memberCompanies/memberDepts(부모가 회의체 멤버에서 모아 전달) 중 입력 문자와
// 일치하는 항목을 메뉴로 띄워 검색·선택할 수 있게 한다.
function acFilter(list, query) {
  const q = (query || '').trim().toLowerCase()
  const seen = new Set()
  const out = []
  for (const raw of list || []) {
    const v = (raw == null ? '' : String(raw)).trim()
    if (!v) continue
    const key = v.toLowerCase()
    if (seen.has(key) || key === q) continue // 중복·정확히 같은 입력은 제외
    seen.add(key)
    if (!q || key.includes(q)) out.push(v)
    if (out.length >= 8) break
  }
  return out
}
function acList(ag, field) {
  return field === 'company'
    ? acFilter(props.memberCompanies, ag._editCompany)
    : acFilter(props.memberDepts, ag._editDept)
}
function openAc(ag, field) {
  ag._acOpen = field
  ag._acHi = 0
}
function pickAc(ag, field, val) {
  if (field === 'company') ag._editCompany = val
  else ag._editDept = val
  ag._acOpen = null
}
function acBlur(ag) {
  // 옵션 클릭(mousedown.prevent)은 blur를 막으므로, 바깥 클릭 시에만 약간 늦게 닫는다.
  setTimeout(() => {
    ag._acOpen = null
  }, 120)
}
function onAcKeydown(ag, field, e) {
  const list = acList(ag, field)
  if (e.key === 'Escape') {
    ag._acOpen = null
    return
  }
  if (!list.length) return
  const hi = ag._acHi || 0
  if (e.key === 'ArrowDown') {
    e.preventDefault()
    ag._acOpen = field
    ag._acHi = (hi + 1) % list.length
  } else if (e.key === 'ArrowUp') {
    e.preventDefault()
    ag._acHi = (hi - 1 + list.length) % list.length
  } else if (e.key === 'Enter' && ag._acOpen === field) {
    e.preventDefault()
    pickAc(ag, field, list[Math.min(hi, list.length - 1)])
  }
}
</script>

<template>
  <div class="arl-list">
    <template v-for="(ag, i) in items" :key="ag.db_id || i">
      <div
        class="arl-item"
        :class="{
          'arl-approved': !removeOnApprove && ag._state === 'approved',
          'arl-rejected': !removeOnApprove && ag._state === 'rejected',
          'arl-saved': !removeOnApprove && ag._state === 'saved',
        }"
      >
        <div class="arl-accent"></div>

        <div class="dei-body">
          <template v-if="!ag._editing">
            <div class="arl-header">
              <span class="arl-index">#{{ String(i + 1).padStart(2, '0') }}</span>
              <div class="dei-actions">
                <button class="gm-ei-btn gm-ei-edit" @click="startEdit(i)" title="편집">
                  <svg
                    width="10"
                    height="10"
                    fill="none"
                    stroke="currentColor"
                    stroke-width="2"
                    viewBox="0 0 24 24"
                  >
                    <path d="M11 4H4a2 2 0 00-2 2v14a2 2 0 002 2h14a2 2 0 002-2v-7" />
                    <path d="M18.5 2.5a2.121 2.121 0 013 3L12 15l-4 1 1-4 9.5-9.5z" />
                  </svg>
                </button>
                <button
                  class="gm-ei-btn gm-ei-approve"
                  :class="{ 'gm-ei-approved-active': !removeOnApprove && ag._state === 'approved' }"
                  @click="startApprove(i)"
                  title="승인"
                >
                  <svg
                    width="10"
                    height="10"
                    fill="none"
                    stroke="currentColor"
                    stroke-width="2.5"
                    viewBox="0 0 24 24"
                  >
                    <path d="M20 6L9 17l-5-5" />
                  </svg>
                </button>
                <button
                  class="gm-ei-btn gm-ei-reject"
                  :class="{ 'gm-ei-rejected-active': !removeOnApprove && ag._state === 'rejected' }"
                  @click="startReject(i)"
                  title="반려"
                >
                  <svg
                    width="10"
                    height="10"
                    fill="none"
                    stroke="currentColor"
                    stroke-width="2.5"
                    viewBox="0 0 24 24"
                  >
                    <path d="M18 6L6 18M6 6l12 12" />
                  </svg>
                </button>
              </div>
            </div>
            <div class="arl-title">{{ ag.title }}</div>
            <div class="arl-meta" v-if="ag.company || ag.dept || ag.start_date || ag.end_date">
              <div class="arl-tags" v-if="ag.company || ag.dept">
                <span class="arl-tag arl-tag-company" v-if="ag.company">{{ ag.company }}</span>
                <span class="arl-tag arl-tag-dept" v-for="d in deptList(ag.dept)" :key="d">{{
                  d
                }}</span>
              </div>
              <div class="arl-date-range" v-if="validDate(ag.start_date) || validDate(ag.end_date)">
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
                  <rect x="3" y="4" width="18" height="18" rx="2" />
                  <line x1="16" y1="2" x2="16" y2="6" />
                  <line x1="8" y1="2" x2="8" y2="6" />
                  <line x1="3" y1="10" x2="21" y2="10" />
                </svg>
                <span v-if="validDate(ag.start_date) && validDate(ag.end_date)"
                  >{{ fmtDate(ag.start_date) }} → {{ fmtDate(ag.end_date) }}</span
                >
                <span v-else-if="validDate(ag.start_date)">{{ fmtDate(ag.start_date) }} 시작</span>
                <span v-else>{{ fmtDate(ag.end_date) }} 마감</span>
              </div>
            </div>
          </template>

          <template v-else>
            <div class="arl-header">
              <span class="arl-index">#{{ String(i + 1).padStart(2, '0') }}</span>
              <div class="dei-actions">
                <button class="gm-ei-btn gm-ei-save" @click="saveEdit(i)" title="저장">
                  <svg
                    width="10"
                    height="10"
                    fill="none"
                    stroke="currentColor"
                    stroke-width="2.5"
                    viewBox="0 0 24 24"
                  >
                    <path d="M20 6L9 17l-5-5" />
                  </svg>
                </button>
                <button class="gm-ei-btn gm-ei-cancel-edit" @click="cancelEdit(i)" title="취소">
                  <svg
                    width="10"
                    height="10"
                    fill="none"
                    stroke="currentColor"
                    stroke-width="2.5"
                    viewBox="0 0 24 24"
                  >
                    <path d="M18 6L6 18M6 6l12 12" />
                  </svg>
                </button>
              </div>
            </div>
            <input
              :id="`edit-agenda-title-${i}`"
              :name="`edit-agenda-title-${i}`"
              class="dei-input"
              v-model="ag._editTitle"
              placeholder="아젠다 제목"
              style="margin-top: 5px"
            />
            <div class="dei-ac-wrap" style="margin-top: 4px">
              <input
                :id="`edit-company-${i}`"
                :name="`edit-company-${i}`"
                class="dei-input"
                v-model="ag._editCompany"
                placeholder="담당 회사 (선택)"
                autocomplete="off"
                @focus="openAc(ag, 'company')"
                @input="openAc(ag, 'company')"
                @keydown="onAcKeydown(ag, 'company', $event)"
                @blur="acBlur(ag)"
              />
              <ul
                v-if="ag._acOpen === 'company' && acList(ag, 'company').length"
                class="dei-ac-menu"
              >
                <li
                  v-for="(opt, oi) in acList(ag, 'company')"
                  :key="opt"
                  :class="{ 'dei-ac-active': oi === (ag._acHi || 0) }"
                  @mousedown.prevent="pickAc(ag, 'company', opt)"
                  @mouseenter="ag._acHi = oi"
                >
                  {{ opt }}
                </li>
              </ul>
            </div>
            <div class="dei-ac-wrap" style="margin-top: 4px">
              <input
                :id="`edit-dept-${i}`"
                :name="`edit-dept-${i}`"
                class="dei-input"
                v-model="ag._editDept"
                placeholder="담당 부서 (선택)"
                autocomplete="off"
                @focus="openAc(ag, 'dept')"
                @input="openAc(ag, 'dept')"
                @keydown="onAcKeydown(ag, 'dept', $event)"
                @blur="acBlur(ag)"
              />
              <ul v-if="ag._acOpen === 'dept' && acList(ag, 'dept').length" class="dei-ac-menu">
                <li
                  v-for="(opt, oi) in acList(ag, 'dept')"
                  :key="opt"
                  :class="{ 'dei-ac-active': oi === (ag._acHi || 0) }"
                  @mousedown.prevent="pickAc(ag, 'dept', opt)"
                  @mouseenter="ag._acHi = oi"
                >
                  {{ opt }}
                </li>
              </ul>
            </div>
            <div class="dei-date-row">
              <DateInput class="dei-input dei-date-input" v-model="ag._editStartDate" />
              <DateInput class="dei-input dei-date-input" v-model="ag._editEndDate" />
            </div>
          </template>
        </div>
      </div>

      <div
        v-if="showFeedback && ag._showReason && !ag._editing"
        class="arl-reason-below"
        :ref="
          el => {
            if (el) reasonRefs[i] = el
            else delete reasonRefs[i]
          }
        "
        :class="ag._feedbackAction === 'rejected' ? 'arb-rejected' : 'arb-edited'"
      >
        <span class="arb-label"
          >{{ ag._feedbackAction === 'rejected' ? '✗ 반려 사유' : '✎ 수정 사유' }} (선택)</span
        >
        <textarea
          v-model="ag._reason"
          class="dei-feedback-input"
          :placeholder="
            ag._feedbackAction === 'rejected' ? '반려 사유를 남겨주세요' : '수정 사유를 남겨주세요'
          "
          rows="2"
        />
        <div class="dei-feedback-btns">
          <button class="dei-fb-submit" @click="saveFeedback(i)">저장</button>
        </div>
      </div>
    </template>

    <div v-if="showFooter && items.length" class="nab-footer">
      <slot name="footer-left" />
      <div class="nab-footer-right">
        <span class="nab-count">승인 {{ approvedCount }} / 반려 {{ rejectedCount }}</span>
        <button
          class="nab-save-btn"
          :class="{ saving }"
          :disabled="saving || (!approvedCount && !rejectedCount)"
          @click="emit('save')"
        >
          <span v-if="saving" class="nab-save-spinner" aria-hidden="true"></span>
          {{
            saving
              ? '저장 중…'
              : approvedCount
                ? `승인 ${approvedCount}건 저장`
                : rejectedCount
                  ? `반려 ${rejectedCount}건 처리`
                  : '승인 0건 처리'
          }}
        </button>
      </div>
    </div>
  </div>
</template>

<style>
/* ── item list ── */
.arl-list {
  display: flex;
  flex-direction: column;
  gap: 5px;
}
.arl-item {
  display: flex;
  align-items: stretch;
  gap: 0;
  background: rgba(255, 255, 255, 0.035);
  border-radius: 8px;
  border: 1px solid var(--white-07);
  overflow: hidden;
}
.arl-item.arl-approved {
  border-color: rgba(16, 185, 129, 0.35);
  background: rgba(16, 185, 129, 0.06);
}
.arl-item.arl-rejected {
  border-color: rgba(239, 68, 68, 0.2);
  background: rgba(239, 68, 68, 0.03);
  opacity: 0.6;
}
.arl-item.arl-saved {
  border-color: rgba(16, 185, 129, 0.5);
  background: rgba(16, 185, 129, 0.09);
}
.arl-item:has(+ .arl-reason-below) {
  border-radius: 8px 8px 0 0;
  border-bottom-color: transparent;
}

/* left accent bar */
.arl-accent {
  width: 3px;
  flex-shrink: 0;
  background: rgba(99, 102, 241, 0.45);
}
.arl-item.arl-approved .arl-accent {
  background: rgba(16, 185, 129, 0.6);
}
.arl-item.arl-rejected .arl-accent {
  background: rgba(239, 68, 68, 0.4);
}
.arl-item.arl-saved .arl-accent {
  background: rgba(16, 185, 129, 0.75);
}

.dei-body {
  flex: 1;
  min-width: 0;
  padding: 7px 10px 8px;
}

/* header row: index + actions */
.arl-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 3px;
}
.arl-index {
  font-size: 9.5px;
  font-weight: 700;
  font-family: ui-monospace, monospace;
  color: rgba(99, 102, 241, 0.7);
  letter-spacing: 0.05em;
  background: rgba(99, 102, 241, 0.1);
  padding: 1px 5px;
  border-radius: 3px;
}
.arl-item.arl-approved .arl-index {
  color: rgba(16, 185, 129, 0.8);
  background: rgba(16, 185, 129, 0.1);
}
.arl-item.arl-rejected .arl-index {
  color: rgba(239, 68, 68, 0.7);
  background: rgba(239, 68, 68, 0.08);
}

/* title */
.arl-title {
  font-size: 12px;
  font-weight: 600;
  color: var(--dark-text, #e8e8e8);
  line-height: 1.45;
  word-break: keep-all;
}

/* meta row */
.arl-meta {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
  margin-top: 6px;
}
.arl-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 3px;
}
.arl-tag {
  font-size: 10px;
  font-weight: 500;
  color: rgba(148, 163, 184, 0.85);
  background: var(--white-06);
  border: 1px solid var(--white-09);
  border-radius: 3px;
  padding: 1px 6px;
  line-height: 1.5;
}
.arl-tag-company {
  color: rgba(45, 212, 191, 0.85);
  background: rgba(13, 148, 136, 0.12);
  border-color: rgba(13, 148, 136, 0.25);
}
.arl-tag-dept {
  color: rgba(167, 139, 250, 0.85);
  background: rgba(139, 92, 246, 0.1);
  border-color: rgba(139, 92, 246, 0.2);
}
.arl-date-range {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 10px;
  color: rgba(148, 163, 184, 0.65);
  font-variant-numeric: tabular-nums;
}
.arl-date-range svg {
  opacity: 0.5;
  flex-shrink: 0;
}

/* reason below */
.arl-reason-below {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 6px 9px 7px;
  margin-top: -4px;
  border: 1px solid var(--white-06);
  border-top: none;
  border-radius: 0 0 8px 8px;
  background: rgba(255, 255, 255, 0.02);
}
.arb-rejected {
  border-color: rgba(239, 68, 68, 0.18) !important;
  background: rgba(239, 68, 68, 0.03) !important;
}
.arb-edited {
  border-color: rgba(99, 102, 241, 0.2) !important;
  background: rgba(99, 102, 241, 0.03) !important;
}
.arb-label {
  font-size: 10px;
  font-weight: 600;
  color: var(--text-muted);
  letter-spacing: 0.03em;
}
.arb-rejected .arb-label {
  color: rgba(248, 113, 113, 0.7);
}
.arb-edited .arb-label {
  color: rgba(129, 140, 248, 0.8);
}

/* day-mode */
.day-mode .arl-item {
  background: var(--surface);
  border-color: var(--border);
}
.day-mode .arl-item.arl-approved {
  border-color: rgba(22, 163, 74, 0.2);
  background: rgba(22, 163, 74, 0.04);
}
.day-mode .arl-item.arl-rejected {
  border-color: rgba(239, 68, 68, 0.15);
  background: transparent;
}
.day-mode .arl-item.arl-saved {
  border-color: rgba(22, 163, 74, 0.35);
  background: rgba(22, 163, 74, 0.07);
}
.day-mode .arl-accent {
  background: rgba(99, 102, 241, 0.3);
}
.day-mode .arl-item.arl-approved .arl-accent {
  background: rgba(22, 163, 74, 0.45);
}
.day-mode .arl-item.arl-rejected .arl-accent {
  background: rgba(239, 68, 68, 0.3);
}
.day-mode .arl-index {
  color: rgba(99, 102, 241, 0.8);
  background: rgba(99, 102, 241, 0.08);
}
.day-mode .arl-tag {
  color: var(--text-muted);
  background: var(--surface-2);
  border-color: #e2e8f0;
}
.day-mode .arl-tag-company {
  color: #0d9488;
  background: #f0fdfa;
  border-color: #99f6e4;
}
.day-mode .arl-tag-dept {
  color: #7c3aed;
  background: #f5f3ff;
  border-color: #ddd6fe;
}
.day-mode .arl-date-range {
  color: var(--dark-muted);
}
.day-mode .arl-title {
  color: var(--dark-card);
}
.day-mode .arl-reason-below {
  background: rgba(0, 0, 0, 0.02);
  border-color: #e2e8f0;
}
.day-mode .arb-rejected {
  border-color: rgba(239, 68, 68, 0.2) !important;
  background: rgba(239, 68, 68, 0.03) !important;
}
.day-mode .arb-edited {
  border-color: rgba(99, 102, 241, 0.15) !important;
  background: rgba(99, 102, 241, 0.04) !important;
}
.day-mode .arb-rejected .arb-label {
  color: var(--danger);
}
.day-mode .arb-edited .arb-label {
  color: var(--indigo);
}

/* ── shared dei-* / gm-ei-* ── */
.dei-num {
  font-size: 10px;
  font-weight: 700;
  color: var(--text-muted);
  min-width: 16px;
  margin-top: 2px;
}
.dei-input {
  width: 100%;
  background: var(--white-06);
  border: 1px solid var(--white-10);
  border-radius: 5px;
  padding: 4px 7px;
  font-size: 12px;
  color: var(--dark-text, #e8e8e8);
  outline: none;
  box-sizing: border-box;
}
.dei-app-select {
  font-size: 12px;
  padding: 3px 6px;
  border-radius: 5px;
}
.dei-date-row {
  display: flex;
  gap: 6px;
  margin-top: 4px;
}

/* ── 담당 회사/부서 자동완성 ── */
.dei-ac-wrap {
  position: relative;
}
.dei-ac-menu {
  position: absolute;
  left: 0;
  right: 0;
  top: calc(100% + 2px);
  margin: 0;
  padding: 3px;
  list-style: none;
  background: var(--surface-raised, #1e1e24);
  border: 1px solid var(--white-12, rgba(255, 255, 255, 0.14));
  border-radius: 6px;
  max-height: 144px;
  overflow-y: auto;
  z-index: 40;
  box-shadow: 0 8px 22px rgba(0, 0, 0, 0.4);
}
.dei-ac-menu li {
  padding: 4px 8px;
  font-size: 12px;
  color: var(--dark-text, #e8e8e8);
  border-radius: 4px;
  cursor: pointer;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.dei-ac-menu li.dei-ac-active {
  background: rgba(99, 102, 241, 0.18);
  color: #c7d2fe;
}
.day-mode .dei-ac-menu {
  background: #fff;
  border-color: #e2e8f0;
}
.day-mode .dei-ac-menu li {
  color: var(--dark-card);
}
.day-mode .dei-ac-menu li.dei-ac-active {
  background: #eef2ff;
  color: #4338ca;
}
.dei-date-input {
  flex: 1;
  min-width: 0;
}
.dei-actions {
  display: flex;
  flex-direction: row;
  gap: 3px;
}
.dei-feedback-input {
  width: 100%;
  background: var(--white-04);
  border: 1px solid var(--white-08);
  border-radius: 5px;
  padding: 5px 7px;
  font-size: 12px;
  color: var(--dark-muted, #aaa);
  outline: none;
  resize: none;
  font-family: inherit;
  box-sizing: border-box;
}
.dei-feedback-input:focus {
  border-color: rgba(99, 102, 241, 0.35);
}
.dei-feedback-input::placeholder {
  color: rgba(148, 163, 184, 0.4);
  font-style: italic;
}
.dei-feedback-btns {
  display: flex;
  justify-content: flex-end;
  margin-top: 5px;
}
.dei-fb-submit {
  font-size: 12px;
  padding: 3px 12px;
  background: var(--indigo);
  color: #fff;
  border: none;
  border-radius: 5px;
  cursor: pointer;
}
.gm-ei-btn {
  width: 22px;
  height: 22px;
  border-radius: 4px;
  border: 1px solid var(--border, var(--white-10));
  background: none;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--text-muted, #666);
}
.gm-ei-btn:hover {
  background: var(--surface-raised, var(--white-06));
}
.gm-ei-edit:hover {
  color: var(--text, #e8e8e8);
}
.gm-ei-approve {
  color: var(--text-muted, #666);
}
.gm-ei-approve:hover {
  color: rgba(100, 160, 100, 1);
  border-color: rgba(100, 160, 100, 0.4);
  background: rgba(100, 160, 100, 0.08);
}
.gm-ei-approved-active {
  color: rgba(80, 150, 80, 1) !important;
  border-color: rgba(80, 150, 80, 0.45) !important;
  background: rgba(80, 150, 80, 0.1) !important;
}
.gm-ei-reject {
  color: var(--text-muted, #666);
}
.gm-ei-reject:hover {
  color: rgba(180, 80, 80, 1);
  border-color: rgba(180, 80, 80, 0.4);
  background: rgba(180, 80, 80, 0.08);
}
.gm-ei-rejected-active {
  color: rgba(180, 80, 80, 1) !important;
  border-color: rgba(180, 80, 80, 0.45) !important;
  background: rgba(180, 80, 80, 0.1) !important;
}
.gm-ei-save {
  color: rgba(80, 150, 80, 0.9);
  border-color: rgba(80, 150, 80, 0.3);
}
.gm-ei-save:hover {
  background: rgba(80, 150, 80, 0.12);
}
.gm-ei-cancel-edit {
  color: var(--text-muted, #666);
}

/* day-mode for dei/gm-ei */
.day-mode .dei-input {
  background: var(--surface);
  border-color: #e2e8f0;
  color: var(--dark-card);
}
.day-mode .dei-feedback-input {
  background: var(--surface);
  border-color: var(--dark-text-2);
  color: var(--dark-card);
}
.day-mode .dei-feedback-input::placeholder {
  color: var(--dark-muted);
}

/* ── shared footer ── */
.nab-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 10px;
  border-top: 1px solid var(--border);
}
.nab-footer-right {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-left: auto;
}
.nab-count {
  font-size: 12px;
  color: var(--text-muted);
}
.nab-add-btn {
  font-size: 12px;
  color: #818cf8;
  background: none;
  border: none;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 0;
}
.nab-save-btn {
  font-size: 12px;
  font-weight: 600;
  padding: 5px 12px;
  border-radius: 6px;
  border: none;
  background: linear-gradient(135deg, var(--indigo), #818cf8);
  color: #fff;
  cursor: pointer;
}
.nab-save-btn:disabled {
  opacity: 0.35;
  cursor: not-allowed;
}
/* 저장 처리중 — 비활성(중복 클릭 차단)이지만 밝게 유지하고 무지개빛 테두리가 빙글빙글 빛난다 */
.nab-save-btn.saving,
.nab-save-btn.saving:disabled {
  opacity: 1;
  cursor: wait;
  animation: nab-rainbow-glow 1.6s linear infinite;
}
@keyframes nab-rainbow-glow {
  0% {
    box-shadow:
      0 0 0 1.5px #f43f5e,
      0 0 10px 1px rgba(244, 63, 94, 0.6);
  }
  25% {
    box-shadow:
      0 0 0 1.5px #f59e0b,
      0 0 10px 1px rgba(245, 158, 11, 0.6);
  }
  50% {
    box-shadow:
      0 0 0 1.5px #22c55e,
      0 0 10px 1px rgba(34, 197, 94, 0.6);
  }
  75% {
    box-shadow:
      0 0 0 1.5px #38bdf8,
      0 0 10px 1px rgba(56, 189, 248, 0.6);
  }
  100% {
    box-shadow:
      0 0 0 1.5px #a855f7,
      0 0 10px 1px rgba(168, 85, 247, 0.6);
  }
}
.nab-save-spinner {
  display: inline-block;
  width: 11px;
  height: 11px;
  margin-right: 5px;
  vertical-align: -1px;
  border: 2px solid rgba(255, 255, 255, 0.4);
  border-top-color: #fff;
  border-radius: 50%;
  animation: nab-spin 0.6s linear infinite;
}
@keyframes nab-spin {
  to {
    transform: rotate(360deg);
  }
}
</style>
