<script setup>
import { ref, watch, onBeforeUnmount } from 'vue'

const props = defineProps({
  gNodes: { type: Array, default: () => [] },
  gEdges: { type: Array, default: () => [] },
  nightMode: { type: Boolean, default: true },
  getHubFill: { type: Function, required: true },
})

const emit = defineEmits(['selectMeeting'])  // 클릭 시 meeting 노드 data 전달

// ─── Canvas ref ───────────────────────────────────────────────
const canvasRef = ref(null)

// ─── State ───────────────────────────────────────────────────
const selMgIdx  = ref(null)
let ctx = null, animId = null, ro = null
let cPos = []
let scale = 1, targetScale = 1
let camX = 0, camY = 0, targetCamX = 0, targetCamY = 0
let dragging = false, lastMx = 0, lastMy = 0, dragMoved = false

// ─── Layout ──────────────────────────────────────────────────
function buildPositions() {
  const canvas = canvasRef.value
  const w = canvas ? canvas.offsetWidth : 900
  const h = canvas ? canvas.offsetHeight : 600
  const cx = w / 2, cy = h / 2
  if (!props.gNodes.length) { cPos = []; return }

  const mgByGroup = new Map()
  props.gNodes.forEach((n, i) => {
    if (n.type === 'meeting_group') mgByGroup.set(n.groupIdx ?? i, i)
  })
  const mgList = [...mgByGroup.values()]
  const radius = Math.min(w, h) * 0.30

  cPos = props.gNodes.map(() => ({ x: cx, y: cy }))
  mgList.forEach((idx, gi) => {
    const ang = (gi / Math.max(mgList.length, 1)) * Math.PI * 2 - Math.PI / 2
    cPos[idx] = { x: cx + Math.cos(ang) * radius, y: cy + Math.sin(ang) * radius }
  })

  const placed = new Map()
  props.gNodes.forEach((n, i) => {
    if (n.type === 'meeting_group' || n.id === 'org-root' || n.id === 'org-node') return
    const mgIdx = mgByGroup.get(n.groupIdx)
    if (mgIdx === undefined) return
    const cnt = placed.get(mgIdx) || 0
    placed.set(mgIdx, cnt + 1)
    const goldenAng = cnt * 2.399963
    const r = 22 + 9 * Math.sqrt(cnt)
    cPos[i] = {
      x: cPos[mgIdx].x + Math.cos(goldenAng) * r,
      y: cPos[mgIdx].y + Math.sin(goldenAng) * r,
    }
  })
}

// ─── Canvas setup ────────────────────────────────────────────
function resize() {
  const c = canvasRef.value; if (!c || !ctx) return
  const dpr = window.devicePixelRatio || 1
  c.width = c.offsetWidth * dpr; c.height = c.offsetHeight * dpr
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
}

function init() {
  const canvas = canvasRef.value; if (!canvas) return
  ctx = canvas.getContext('2d')
  resize()
  if (ro) ro.disconnect()
  ro = new ResizeObserver(() => { resize(); buildPositions() })
  ro.observe(canvas)
  scale = 1; targetScale = 1
  selMgIdx.value = null
  buildPositions()
  camX = 0; camY = 0; targetCamX = 0; targetCamY = 0
  if (animId) cancelAnimationFrame(animId)
  animId = requestAnimationFrame(animate)
}

function stop() {
  if (animId) { cancelAnimationFrame(animId); animId = null }
  if (ro) { ro.disconnect(); ro = null }
}

// ─── Render ──────────────────────────────────────────────────
function animate() {
  camX   += (targetCamX - camX)   * 0.09
  camY   += (targetCamY - camY)   * 0.09
  scale  += (targetScale - scale) * 0.09
  draw()
  animId = requestAnimationFrame(animate)
}

function toS(px, py) {
  const c = canvasRef.value
  const w = c?.offsetWidth || 0, h = c?.offsetHeight || 0
  return { sx: w/2 + (px - camX) * scale, sy: h/2 + (py - camY) * scale }
}

function draw() {
  const canvas = canvasRef.value; if (!canvas || !ctx) return
  const w = canvas.offsetWidth, h = canvas.offsetHeight
  if (!w || !h || !cPos.length) return
  ctx.clearRect(0, 0, w, h)

  const isDark = props.nightMode
  ctx.fillStyle = isDark ? '#080f1e' : '#e8eeff'
  ctx.fillRect(0, 0, w, h)

  // 배경 별점 (다크 모드)
  if (isDark) {
    ctx.fillStyle = 'rgba(255,255,255,0.25)'
    for (let i = 0; i < 120; i++) {
      ctx.beginPath(); ctx.arc((i*7919)%w, (i*6271)%h, 0.6, 0, Math.PI*2); ctx.fill()
    }
  }

  if (!props.gNodes.length) return
  const sel = selMgIdx.value
  const selGroup = sel !== null ? (props.gNodes[sel]?.groupIdx ?? null) : null

  // ── 엣지 ──────────────────────────────────────────────────
  props.gEdges.forEach(e => {
    const pA = cPos[e.from], pB = cPos[e.to]
    const nA = props.gNodes[e.from], nB = props.gNodes[e.to]
    if (!pA || !pB || !nA || !nB) return
    // org 노드와 연결된 엣지 숨김
    if (['org-node','org-root'].includes(nA.id) || ['org-node','org-root'].includes(nB.id)) return
    const a = toS(pA.x, pA.y), b = toS(pB.x, pB.y)
    let alpha = isDark ? 0.18 : 0.14
    if (sel !== null) {
      const aRel = nA.type === 'meeting_group' ? e.from === sel : nA.groupIdx === selGroup
      const bRel = nB.type === 'meeting_group' ? e.to === sel : nB.groupIdx === selGroup
      alpha = (aRel && bRel) ? (isDark ? 0.55 : 0.45) : (isDark ? 0.05 : 0.04)
    }
    ctx.save()
    ctx.strokeStyle = isDark ? `rgba(148,163,184,${alpha})` : `rgba(100,116,139,${alpha})`
    ctx.lineWidth = 0.7
    ctx.beginPath(); ctx.moveTo(a.sx, a.sy); ctx.lineTo(b.sx, b.sy); ctx.stroke()
    // 선택된 그룹과 연관된 엣지에만 라벨 표시
    if (sel !== null && e.rel) {
      const aRel = nA.type === 'meeting_group' ? e.from === sel : nA.groupIdx === selGroup
      const bRel = nB.type === 'meeting_group' ? e.to === sel : nB.groupIdx === selGroup
      if (aRel && bRel) {
        const mx2 = (a.sx + b.sx) / 2, my2 = (a.sy + b.sy) / 2
        ctx.font = '9px sans-serif'
        ctx.textAlign = 'center'; ctx.textBaseline = 'middle'
        ctx.globalAlpha = 0.75
        ctx.fillStyle = isDark ? 'rgba(148,163,184,0.9)' : 'rgba(71,85,105,0.9)'
        ctx.fillText(e.rel, mx2, my2 - 5)
      }
    }
    ctx.restore()
  })

  // ── 세부 노드 ────────────────────────────────────────────
  props.gNodes.forEach((n, i) => {
    if (n.type === 'meeting_group' || n.id === 'org-root' || n.id === 'org-node') return
    const pos = cPos[i]; if (!pos) return
    const s = toS(pos.x, pos.y)
    const isRelated = sel === null ? false : (n.groupIdx === selGroup)
    const showDetail = isRelated && scale > 0.8
    const alpha = sel === null ? 0.55 : (isRelated ? 1.0 : 0.18)
    const r = showDetail ? Math.min(14, 11 * scale) : 4
    const COLOR = { dept:'#8b5cf6', agenda:'#f59e0b', session:'#f97316', file:'#64748b', person:'#f472b6' }
    const color = COLOR[n.type] || '#60a5fa'
    ctx.save()
    ctx.globalAlpha = alpha
    ctx.beginPath(); ctx.arc(s.sx, s.sy, r, 0, Math.PI*2)
    ctx.fillStyle = color; ctx.fill()
    if (showDetail) {
      drawIcon(n, s.sx, s.sy, r)
      const fs = Math.max(9, Math.round(10 * Math.min(1.5, scale)))
      ctx.fillStyle = isDark ? 'rgba(226,232,240,0.9)' : 'rgba(15,23,42,0.85)'
      ctx.font = `${fs}px sans-serif`
      ctx.textAlign = 'center'; ctx.textBaseline = 'top'
      ctx.fillText((n.label||'').slice(0,9), s.sx, s.sy + r + 3)
    }
    ctx.restore()
  })

  // ── MG 노드 ────────────────────────────────────────────────
  props.gNodes.forEach((n, i) => {
    if (n.type !== 'meeting_group') return
    const pos = cPos[i]; if (!pos) return
    const s = toS(pos.x, pos.y)
    const isSel = sel === i
    const alpha = sel === null ? 1.0 : (isSel ? 1.0 : 0.3)
    const r = isSel ? 30 * Math.min(1.5, scale) : 22
    const hubColor = props.getHubFill(n.data)
    ctx.save()
    ctx.globalAlpha = alpha
    if (isSel) {
      const glow = ctx.createRadialGradient(s.sx, s.sy, r*0.4, s.sx, s.sy, r*3)
      glow.addColorStop(0, 'rgba(59,130,246,0.28)'); glow.addColorStop(1, 'rgba(59,130,246,0)')
      ctx.beginPath(); ctx.arc(s.sx, s.sy, r*3, 0, Math.PI*2)
      ctx.fillStyle = glow; ctx.fill()
    }
    const grad = ctx.createRadialGradient(s.sx, s.sy, 0, s.sx, s.sy, r)
    grad.addColorStop(0, hubColor + 'ee'); grad.addColorStop(1, hubColor + '66')
    ctx.beginPath(); ctx.arc(s.sx, s.sy, r, 0, Math.PI*2)
    ctx.fillStyle = grad; ctx.fill()
    if (isSel) { ctx.strokeStyle = isDark ? '#fff' : '#1e293b'; ctx.lineWidth = 2.5; ctx.stroke() }
    const fs = Math.max(10, Math.round(12 * Math.min(1.4, scale)))
    ctx.fillStyle = isDark ? 'rgba(255,255,255,0.95)' : 'rgba(30,58,138,0.95)'
    ctx.font = `bold ${fs}px sans-serif`
    ctx.textAlign = 'center'; ctx.textBaseline = 'middle'
    ctx.fillText((n.label||'').slice(0,7), s.sx, s.sy)
    ctx.restore()
  })
  // org-root 노드는 표시하지 않음 (검은 점 제거)
}

function drawIcon(n, sx, sy, r) {
  ctx.save()
  ctx.strokeStyle = 'rgba(255,255,255,0.92)'; ctx.fillStyle = 'rgba(255,255,255,0.92)'
  ctx.lineWidth = Math.max(1, r*0.12); ctx.lineCap = 'round'; ctx.lineJoin = 'round'
  if (n.type === 'agenda') {
    const cs = r*0.5
    ctx.beginPath(); ctx.moveTo(sx-cs,sy+cs*0.1); ctx.lineTo(sx-cs*0.18,sy+cs*0.78); ctx.lineTo(sx+cs,sy-cs*0.62); ctx.stroke()
  } else if (n.type === 'session') {
    const cw=r*0.68,ch=r*0.6,cx2=sx-cw/2,cy2=sy-ch/2+r*0.06,fold=cw*0.22
    ctx.strokeRect(cx2,cy2,cw,ch)
    ctx.beginPath(); ctx.moveTo(cx2,cy2+ch*0.33); ctx.lineTo(cx2+cw,cy2+ch*0.33); ctx.stroke()
    ctx.beginPath(); ctx.arc(cx2+cw*0.28,cy2-fold*0.3,fold*0.4,0,Math.PI*2); ctx.fill()
    ctx.beginPath(); ctx.arc(cx2+cw*0.72,cy2-fold*0.3,fold*0.4,0,Math.PI*2); ctx.fill()
  } else if (n.type === 'file') {
    const fw=r*0.5,fh=r*0.62,fx=sx-fw/2,fy=sy-fh/2,fold=fw*0.3
    ctx.beginPath(); ctx.moveTo(fx,fy); ctx.lineTo(fx+fw-fold,fy); ctx.lineTo(fx+fw,fy+fold); ctx.lineTo(fx+fw,fy+fh); ctx.lineTo(fx,fy+fh); ctx.closePath(); ctx.stroke()
  } else if (n.type === 'dept') {
    const shx=sx-r*0.24,shy=sy-r*0.14,shr=r*0.13,sbr=r*0.16
    ctx.beginPath(); ctx.arc(shx,shy,shr,0,Math.PI*2); ctx.fill()
    ctx.beginPath(); ctx.arc(shx,shy+shr+sbr*1.1,sbr,Math.PI,Math.PI*2); ctx.fill()
    const bhx=sx+r*0.2,bhy=sy-r*0.17,bhr=r*0.18,bbr=r*0.22
    ctx.beginPath(); ctx.arc(bhx,bhy,bhr,0,Math.PI*2); ctx.fill()
    ctx.beginPath(); ctx.arc(bhx,bhy+bhr+bbr*1.1,bbr,Math.PI,Math.PI*2); ctx.fill()
  }
  ctx.restore()
}

// ─── 이벤트 ──────────────────────────────────────────────────
function onMouseDown(e) { dragging=true; dragMoved=false; lastMx=e.clientX; lastMy=e.clientY }
function onMouseMove(e) {
  if (!dragging) return
  const dx=e.clientX-lastMx, dy=e.clientY-lastMy
  if (Math.abs(dx)+Math.abs(dy) > 3) dragMoved = true
  targetCamX -= dx/scale; camX -= dx/scale
  targetCamY -= dy/scale; camY -= dy/scale
  lastMx=e.clientX; lastMy=e.clientY
}
function onMouseUp() { dragging=false }
function onWheel(e) {
  e.preventDefault()
  targetScale = Math.max(0.3, Math.min(6, targetScale * (e.deltaY < 0 ? 1.12 : 0.88)))
}
function resetView() {
  selMgIdx.value = null; targetScale=1; targetCamX=0; targetCamY=0
}

function onClick(e) {
  if (dragMoved) return
  const canvas = canvasRef.value; if (!canvas) return
  const rect = canvas.getBoundingClientRect()
  const mx = e.clientX - rect.left, my = e.clientY - rect.top
  const w = canvas.offsetWidth, h = canvas.offsetHeight

  let hitIdx = null, minDist = Infinity
  props.gNodes.forEach((n, i) => {
    if (n.type !== 'meeting_group') return
    const pos = cPos[i]; if (!pos) return
    const sx = w/2 + (pos.x - camX) * scale
    const sy = h/2 + (pos.y - camY) * scale
    const r = (selMgIdx.value === i ? 30 * Math.min(1.5, scale) : 22) + 8
    const d = Math.hypot(sx - mx, sy - my)
    if (d <= r && d < minDist) { minDist = d; hitIdx = i }
  })

  if (hitIdx !== null) {
    if (selMgIdx.value === hitIdx) {
      selMgIdx.value = null
      targetScale = 1; targetCamX = 0; targetCamY = 0
      emit('selectMeeting', null)
    } else {
      selMgIdx.value = hitIdx
      targetCamX = cPos[hitIdx].x; targetCamY = cPos[hitIdx].y
      targetScale = 2.4
      // 사이드바 열기 위해 meeting data emit
      emit('selectMeeting', props.gNodes[hitIdx])
    }
  } else {
    selMgIdx.value = null
    targetScale = 1; targetCamX = 0; targetCamY = 0
    emit('selectMeeting', null)
  }
}

// ─── Watch ────────────────────────────────────────────────────
watch(() => props.gNodes.length, () => {
  if (animId) buildPositions()
})

// ─── Expose ──────────────────────────────────────────────────
defineExpose({
  init,
  stop,
  zoomIn()  { targetScale = Math.min(6, targetScale * 1.25) },
  zoomOut() { targetScale = Math.max(0.3, targetScale / 1.25) },
  resetView,
})
onBeforeUnmount(stop)
</script>

<template>
  <div class="const-wrap">
    <canvas
      ref="canvasRef"
      class="const-canvas"
      @mousedown="onMouseDown"
      @mousemove="onMouseMove"
      @mouseup="onMouseUp"
      @mouseleave="onMouseUp"
      @click="onClick"
      @wheel.prevent="onWheel"
    />

  </div>
</template>

<style scoped>
.const-wrap {
  position: relative;
  width: 100%;
  height: 100%;
}
.const-canvas {
  width: 100%;
  height: 100%;
  display: block;
}
</style>
