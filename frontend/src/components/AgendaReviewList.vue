<script setup>
import { nextTick, computed } from 'vue'
import { apiAI } from '../api'
import DateInput from './DateInput.vue'

const props = defineProps({
  items: { type: Array, required: true },
  memberCompanies:  { type: Array, default: () => [] },
  memberDepts: { type: Array, default: () => [] },
  removeOnApprove: { type: Boolean, default: true },
  showFooter: { type: Boolean, default: false },
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
  if (!props.removeOnApprove && ag._state === 'rejected') {
    ag._state = null
    ag._showReason = false
    return
  }
  ag._origTitle = ag.title
  ag._origCompany = ag.company
  ag._origDept = ag.dept
  ag._origStartDate = ag.start_date
  ag._origEndDate = ag.end_date
  ag._feedbackAction = 'rejected'
  ag._showReason = true
  if (!props.removeOnApprove) ag._state = 'rejected'
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
  ag._feedbackAction = 'edited'
  ag._showReason = true
}

function cancelEdit(i) {
  const ag = props.items[i]
  ag._editing = false
  if (!ag.title) emit('remove', i)
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
    } catch (e) { console.warn('[hitl-reviews] 저장 실패 (계속 진행):', e) }
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
  if (!d) return ''
  return d.replace(/-/g, '.')
}

function deptList(dept) {
  if (!dept) return []
  return Array.isArray(dept) ? dept : [dept]
}
</script>

<template>
  <div class="arl-list">
    <template v-for="(ag, i) in items" :key="ag.db_id || i">
      <div class="arl-item"
        :class="{
          'arl-approved': !removeOnApprove && ag._state === 'approved',
          'arl-rejected': !removeOnApprove && ag._state === 'rejected',
          'arl-saved':    !removeOnApprove && ag._state === 'saved',
        }">

        <div class="arl-accent"></div>

        <div class="dei-body">
          <template v-if="!ag._editing">
            <div class="arl-header">
              <span class="arl-index">#{{ String(i + 1).padStart(2, '0') }}</span>
              <div class="dei-actions">
                <button class="gm-ei-btn gm-ei-edit" @click="startEdit(i)" title="편집">
                  <svg width="10" height="10" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M11 4H4a2 2 0 00-2 2v14a2 2 0 002 2h14a2 2 0 002-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 013 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>
                </button>
                <button class="gm-ei-btn gm-ei-approve"
                  :class="{ 'gm-ei-approved-active': !removeOnApprove && ag._state === 'approved' }"
                  @click="startApprove(i)" title="승인">
                  <svg width="10" height="10" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24"><path d="M20 6L9 17l-5-5"/></svg>
                </button>
                <button class="gm-ei-btn gm-ei-reject"
                  :class="{ 'gm-ei-rejected-active': !removeOnApprove && ag._state === 'rejected' }"
                  @click="startReject(i)" title="반려">
                  <svg width="10" height="10" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24"><path d="M18 6L6 18M6 6l12 12"/></svg>
                </button>
              </div>
            </div>
            <div class="arl-title">{{ ag.title }}</div>
            <div class="arl-meta" v-if="ag.company || ag.dept || ag.start_date || ag.end_date">
              <div class="arl-tags" v-if="ag.company">
                <span class="arl-tag arl-tag-company" v-for="o in deptList(ag.company)" :key="o">{{ o }}</span>
              </div>
              <div class="arl-tags" v-if="ag.dept">
                <span class="arl-tag arl-tag-dept" v-for="d in deptList(ag.dept)" :key="d">{{ d }}</span>
              </div>
              <div class="arl-date-range" v-if="ag.start_date || ag.end_date">
                <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                  <rect x="3" y="4" width="18" height="18" rx="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/>
                </svg>
                <span v-if="ag.start_date && ag.end_date">{{ fmtDate(ag.start_date) }} → {{ fmtDate(ag.end_date) }}</span>
                <span v-else-if="ag.start_date">{{ fmtDate(ag.start_date) }} 시작</span>
                <span v-else>{{ fmtDate(ag.end_date) }} 마감</span>
              </div>
            </div>
          </template>

          <template v-else>
            <div class="arl-header">
              <span class="arl-index">#{{ String(i + 1).padStart(2, '0') }}</span>
              <div class="dei-actions">
                <button class="gm-ei-btn gm-ei-save" @click="saveEdit(i)" title="저장">
                  <svg width="10" height="10" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24"><path d="M20 6L9 17l-5-5"/></svg>
                </button>
                <button class="gm-ei-btn gm-ei-cancel-edit" @click="cancelEdit(i)" title="취소">
                  <svg width="10" height="10" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24"><path d="M18 6L6 18M6 6l12 12"/></svg>
                </button>
              </div>
            </div>
            <input class="dei-input" v-model="ag._editTitle" placeholder="아젠다 제목" style="margin-top:5px" />
            <select v-if="memberCompanies.length" class="app-select dei-app-select" v-model="ag._editCompany" style="margin-top:4px;width:100%">
              <option value="">회사 선택</option>
              <option v-for="o in memberCompanies" :key="o" :value="o">{{ o }}</option>
            </select>
            <input v-else class="dei-input" v-model="ag._editCompany" placeholder="회사 (선택)" style="margin-top:4px" />
            <select v-if="memberDepts.length" class="app-select dei-app-select" v-model="ag._editDept" style="margin-top:4px;width:100%">
              <option value="">담당부서 선택</option>
              <option v-for="d in memberDepts" :key="d" :value="d">{{ d }}</option>
            </select>
            <input v-else class="dei-input" v-model="ag._editDept" placeholder="담당 팀 (선택)" style="margin-top:4px" />
            <div class="dei-date-row">
              <DateInput class="dei-input dei-date-input" v-model="ag._editStartDate" />
              <DateInput class="dei-input dei-date-input" v-model="ag._editEndDate" />
            </div>
          </template>
        </div>
      </div>

      <div v-if="ag._showReason && !ag._editing" class="arl-reason-below"
        :ref="el => { if (el) reasonRefs[i] = el; else delete reasonRefs[i] }"
        :class="ag._feedbackAction === 'rejected' ? 'arb-rejected' : 'arb-edited'">
        <span class="arb-label">{{ ag._feedbackAction === 'rejected' ? '✗ 반려 사유' : '✎ 수정 사유' }} (선택)</span>
        <textarea v-model="ag._reason" class="dei-feedback-input"
          :placeholder="ag._feedbackAction === 'rejected' ? '반려 사유를 남겨주세요' : '수정 사유를 남겨주세요'"
          rows="2" />
        <div class="dei-feedback-btns">
          <button class="dei-fb-submit" @click="saveFeedback(i)">저장</button>
        </div>
      </div>
    </template>

    <div v-if="showFooter && items.length" class="nab-footer">
      <slot name="footer-left" />
      <div class="nab-footer-right">
        <span class="nab-count">승인 {{ approvedCount }} / 반려 {{ rejectedCount }}</span>
        <button class="nab-save-btn" :disabled="!approvedCount" @click="emit('save')">
          승인 {{ approvedCount }}건 저장
        </button>
      </div>
    </div>
  </div>
</template>

<style>
/* ── item list ── */
.arl-list { display:flex;flex-direction:column;gap:5px; }
.arl-item { display:flex;align-items:stretch;gap:0;background:rgba(255,255,255,.035);border-radius:8px;border:1px solid rgba(255,255,255,.07);transition:border-color .18s,background .18s;overflow:hidden; }
.arl-item.arl-approved { border-color:rgba(16,185,129,.35);background:rgba(16,185,129,.06); }
.arl-item.arl-rejected { border-color:rgba(239,68,68,.2);background:rgba(239,68,68,.03);opacity:.6; }
.arl-item.arl-saved    { border-color:rgba(16,185,129,.5);background:rgba(16,185,129,.09); }
.arl-item:has(+ .arl-reason-below) { border-radius:8px 8px 0 0;border-bottom-color:transparent; }

/* left accent bar */
.arl-accent { width:3px;flex-shrink:0;background:rgba(99,102,241,.45);transition:background .18s; }
.arl-item.arl-approved .arl-accent { background:rgba(16,185,129,.6); }
.arl-item.arl-rejected .arl-accent { background:rgba(239,68,68,.4); }
.arl-item.arl-saved    .arl-accent { background:rgba(16,185,129,.75); }

.dei-body { flex:1;min-width:0;padding:7px 10px 8px; }

/* header row: index + actions */
.arl-header { display:flex;align-items:center;justify-content:space-between;margin-bottom:3px; }
.arl-index { font-size:9.5px;font-weight:700;font-family:ui-monospace,monospace;color:rgba(99,102,241,.7);letter-spacing:.05em;background:rgba(99,102,241,.1);padding:1px 5px;border-radius:3px; }
.arl-item.arl-approved .arl-index { color:rgba(16,185,129,.8);background:rgba(16,185,129,.1); }
.arl-item.arl-rejected .arl-index { color:rgba(239,68,68,.7);background:rgba(239,68,68,.08); }

/* title */
.arl-title { font-size:12px;font-weight:600;color:var(--dark-text,#e8e8e8);line-height:1.45;word-break:keep-all; }

/* meta row */
.arl-meta { display:flex;flex-wrap:wrap;align-items:center;gap:6px;margin-top:6px; }
.arl-tags { display:flex;flex-wrap:wrap;gap:3px; }
.arl-tag { font-size:10px;font-weight:500;color:rgba(148,163,184,.85);background:rgba(255,255,255,.06);border:1px solid rgba(255,255,255,.09);border-radius:3px;padding:1px 6px;line-height:1.5; }
.arl-tag-company  { color:rgba(45,212,191,.85);background:rgba(13,148,136,.12);border-color:rgba(13,148,136,.25); }
.arl-tag-dept { color:rgba(167,139,250,.85);background:rgba(139,92,246,.1);border-color:rgba(139,92,246,.2); }
.arl-date-range { display:flex;align-items:center;gap:4px;font-size:10px;color:rgba(148,163,184,.65);font-variant-numeric:tabular-nums; }
.arl-date-range svg { opacity:.5;flex-shrink:0; }

/* reason below */
.arl-reason-below { display:flex;flex-direction:column;gap:4px;padding:6px 9px 7px;margin-top:-4px;border:1px solid rgba(255,255,255,.06);border-top:none;border-radius:0 0 8px 8px;background:rgba(255,255,255,.02); }
.arb-rejected { border-color:rgba(239,68,68,.18) !important;background:rgba(239,68,68,.03) !important; }
.arb-edited   { border-color:rgba(99,102,241,.2)  !important;background:rgba(99,102,241,.03) !important; }
.arb-label { font-size:10px;font-weight:600;color:var(--text-dim);letter-spacing:.03em; }
.arb-rejected .arb-label { color:rgba(248,113,113,.7); }
.arb-edited   .arb-label { color:rgba(129,140,248,.8); }

/* day-mode */
.day-mode .arl-item { background:var(--surface);border-color:var(--border); }
.day-mode .arl-item.arl-approved { border-color:rgba(22,163,74,.2);background:rgba(22,163,74,.04); }
.day-mode .arl-item.arl-rejected { border-color:rgba(239,68,68,.15);background:transparent; }
.day-mode .arl-item.arl-saved    { border-color:rgba(22,163,74,.35);background:rgba(22,163,74,.07); }
.day-mode .arl-accent { background:rgba(99,102,241,.3); }
.day-mode .arl-item.arl-approved .arl-accent { background:rgba(22,163,74,.45); }
.day-mode .arl-item.arl-rejected .arl-accent { background:rgba(239,68,68,.3); }
.day-mode .arl-index { color:rgba(99,102,241,.8);background:rgba(99,102,241,.08); }
.day-mode .arl-tag { color:#64748b;background:#f1f5f9;border-color:#e2e8f0; }
.day-mode .arl-tag-company  { color:#0d9488;background:#f0fdfa;border-color:#99f6e4; }
.day-mode .arl-tag-dept { color:#7c3aed;background:#f5f3ff;border-color:#ddd6fe; }
.day-mode .arl-date-range { color:#94a3b8; }
.day-mode .arl-title { color:#1e293b; }
.day-mode .arl-reason-below { background:rgba(0,0,0,.02);border-color:#e2e8f0; }
.day-mode .arb-rejected { border-color:rgba(239,68,68,.2) !important;background:rgba(239,68,68,.03) !important; }
.day-mode .arb-edited   { border-color:rgba(99,102,241,.15) !important;background:rgba(99,102,241,.04) !important; }
.day-mode .arb-rejected .arb-label { color:#ef4444; }
.day-mode .arb-edited   .arb-label { color:#6366f1; }

/* ── shared dei-* / gm-ei-* ── */
.dei-num { font-size:10px;font-weight:700;color:var(--text-dim);min-width:16px;margin-top:2px; }
.dei-input { width:100%;background:rgba(255,255,255,.06);border:1px solid rgba(255,255,255,.1);border-radius:5px;padding:4px 7px;font-size:12px;color:var(--dark-text,#e8e8e8);outline:none;box-sizing:border-box; }
.dei-app-select { font-size:11px;padding:3px 6px;border-radius:5px; }
.dei-date-row { display:flex;gap:6px;margin-top:4px; }
.dei-date-input { flex:1;min-width:0; }
.dei-actions { display:flex;flex-direction:row;gap:3px; }
.dei-feedback-input { width:100%;background:rgba(255,255,255,.04);border:1px solid rgba(255,255,255,.08);border-radius:5px;padding:5px 7px;font-size:11px;color:var(--dark-muted,#aaa);outline:none;resize:none;font-family:inherit;transition:border-color .15s;box-sizing:border-box; }
.dei-feedback-input:focus { border-color:rgba(99,102,241,.35); }
.dei-feedback-input::placeholder { color:rgba(148,163,184,.4);font-style:italic; }
.dei-feedback-btns { display:flex;justify-content:flex-end;margin-top:5px; }
.dei-fb-submit { font-size:11px;padding:3px 12px;background:#6366f1;color:#fff;border:none;border-radius:5px;cursor:pointer; }
.gm-ei-btn { width:22px;height:22px;border-radius:4px;border:1px solid var(--border,rgba(255,255,255,.1));background:none;cursor:pointer;display:flex;align-items:center;justify-content:center;color:var(--text-muted,#666);transition:all .12s; }
.gm-ei-btn:hover { background:var(--surface-raised,rgba(255,255,255,.06)); }
.gm-ei-edit:hover { color:var(--text,#e8e8e8); }
.gm-ei-approve { color:var(--text-muted,#666); }
.gm-ei-approve:hover { color:rgba(100,160,100,1);border-color:rgba(100,160,100,.4);background:rgba(100,160,100,.08); }
.gm-ei-approved-active { color:rgba(80,150,80,1)!important;border-color:rgba(80,150,80,.45)!important;background:rgba(80,150,80,.1)!important; }
.gm-ei-reject { color:var(--text-muted,#666); }
.gm-ei-reject:hover { color:rgba(180,80,80,1);border-color:rgba(180,80,80,.4);background:rgba(180,80,80,.08); }
.gm-ei-rejected-active { color:rgba(180,80,80,1)!important;border-color:rgba(180,80,80,.45)!important;background:rgba(180,80,80,.1)!important; }
.gm-ei-save { color:rgba(80,150,80,.9);border-color:rgba(80,150,80,.3); }
.gm-ei-save:hover { background:rgba(80,150,80,.12); }
.gm-ei-cancel-edit { color:var(--text-muted,#666); }

/* day-mode for dei/gm-ei */
.day-mode .dei-input { background:#f8fafc;border-color:#e2e8f0;color:#1e293b; }
.day-mode .dei-feedback-input { background:#f8fafc;border-color:#cbd5e1;color:#1e293b; }
.day-mode .dei-feedback-input::placeholder { color:#94a3b8; }

/* ── shared footer ── */
.nab-footer { display:flex;align-items:center;justify-content:space-between;padding:8px 10px;border-top:1px solid var(--border); }
.nab-footer-right { display:flex;align-items:center;gap:8px;margin-left:auto; }
.nab-count { font-size:11px;color:var(--text-muted); }
.nab-add-btn { font-size:11px;color:#818cf8;background:none;border:none;cursor:pointer;display:flex;align-items:center;gap:4px;padding:0; }
.nab-save-btn { font-size:11px;font-weight:600;padding:5px 12px;border-radius:6px;border:none;background:linear-gradient(135deg,#6366f1,#818cf8);color:#fff;cursor:pointer; }
.nab-save-btn:disabled { opacity:.35;cursor:not-allowed; }
</style>
