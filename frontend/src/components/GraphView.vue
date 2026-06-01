<script setup>
import { ref, watch, onBeforeUnmount, onMounted } from 'vue'
import * as PIXI from 'pixi.js'
import {
  forceSimulation, forceLink, forceManyBody, forceCenter,
  forceCollide, forceX, forceY,
} from 'd3-force'

// ─── Props / Emits ────────────────────────────────────────────
const props = defineProps({
  gNodes:         { type: Array,    default: () => [] },
  gEdges:         { type: Array,    default: () => [] },
  nightMode:      { type: Boolean,  default: true },
  hiddenNodeTypes:{ type: Array,    default: () => [] },
  queryHlIdxs:    { type: Object,   default: () => new Set() },  // Set<number>
  queryHlEdgeIdxs:{ type: Object,   default: () => new Set() },
  searchHitMgIdxs:{ type: Array,    default: () => [] },
  getHubFill:     { type: Function, required: true },
  computeUrgency: { type: Function, required: true },
  relColors:      { type: Object,   default: () => ({}) },
  groupTodoRatio: { type: Object,   default: () => new Map() },  // Map<id, ratio>
})
const emit = defineEmits(['nodeClick', 'nodeDblClick', 'bgClick'])

// ─── Constants ────────────────────────────────────────────────
const NODE_COLORS = {
  'org-root':      0x1f2937,
  'meeting_group': 0x3b82f6,
  'agenda':        0xf59e0b,
  'session':       0xf97316,
  'file':          0x64748b,
  'dept':          0x8b5cf6,
  'person':        0xf472b6,
  'org':           0x0d9488,
}
const NODE_RADIUS = {
  'org-root':      20,
  'meeting_group': 26,
  'agenda':        18,
  'session':       18,
  'file':          14,
  'dept':          18,
  'person':        14,
  'org':           17,
}

// ─── Refs ─────────────────────────────────────────────────────
const containerRef = ref(null)
let app = null          // PIXI.Application
let edgeLayer   = null  // PIXI.Graphics (all edges)
let nodeContainer = null  // PIXI.Container (node sprites)
let labelContainer = null // PIXI.Container (text labels)
let hlLayer = null      // PIXI.Graphics (highlight rings)

// node display objects: Map<nodeIdx, { gfx: PIXI.Graphics, label: PIXI.Text, data: node }>
let nodeObjs = new Map()

// d3-force simulation
let sim = null
let simNodes = []   // { index, x, y, vx, vy, id, type, ... }
let simEdges = []   // { source, target, rel }

// pan/zoom state
let vpX = 0, vpY = 0, vpScale = 1
let isPanning = false, panStartX = 0, panStartY = 0, panOrigX = 0, panOrigY = 0

// focused node
let focusedIdx = null

// resize observer
let ro = null

// ─── PIXI init ───────────────────────────────────────────────
async function initPixi() {
  if (app) destroyPixi()
  const el = containerRef.value; if (!el) return

  // 컨테이너 크기가 아직 0이면 다음 프레임까지 대기 (v-if 렌더 직후 레이아웃 미계산 방지)
  if (el.offsetWidth === 0 || el.offsetHeight === 0) {
    await new Promise(r => requestAnimationFrame(r))
    if (!containerRef.value) return  // unmounted 방지
  }

  app = new PIXI.Application()
  await app.init({
    width:  el.offsetWidth  || 800,
    height: el.offsetHeight || 600,
    backgroundAlpha: 0,
    antialias: true,
    resolution: window.devicePixelRatio || 1,
    autoDensity: true,
  })
  el.appendChild(app.canvas)
  app.canvas.style.width  = '100%'
  app.canvas.style.height = '100%'

  // Layers
  hlLayer        = new PIXI.Graphics();  app.stage.addChild(hlLayer)
  edgeLayer      = new PIXI.Graphics();  app.stage.addChild(edgeLayer)
  nodeContainer  = new PIXI.Container(); app.stage.addChild(nodeContainer)
  labelContainer = new PIXI.Container(); app.stage.addChild(labelContainer)

  // Interaction
  app.stage.eventMode = 'static'
  app.stage.hitArea   = new PIXI.Rectangle(0, 0, app.screen.width, app.screen.height)
  app.stage.on('pointerdown', onBgDown)
  app.stage.on('pointermove', onBgMove)
  app.stage.on('pointerup',   onBgUp)
  app.stage.on('pointerupoutside', onBgUp)
  app.canvas.addEventListener('wheel', onWheel, { passive: false })

  // Resize observer
  ro = new ResizeObserver(() => resizePixi())
  ro.observe(el)

  // Ticker
  app.ticker.add(tick)

  buildSimulation()
}

function resizePixi() {
  const el = containerRef.value; if (!el || !app) return
  const w = el.offsetWidth, h = el.offsetHeight
  app.renderer.resize(w, h)
  app.stage.hitArea = new PIXI.Rectangle(0, 0, w, h)
}

function destroyPixi() {
  if (sim) { sim.stop(); sim = null }
  if (ro)  { ro.disconnect(); ro = null }
  if (app) {
    app.ticker.remove(tick)
    app.canvas?.removeEventListener('wheel', onWheel)
    app.destroy(true, { children: true })
    app = null
  }
  nodeObjs.clear()
  edgeLayer = nodeContainer = labelContainer = hlLayer = null
}

// ─── Simulation ───────────────────────────────────────────────
function buildSimulation() {
  if (!app) return
  const w = app.screen.width, h = app.screen.height

  // Build sim nodes (preserve positions if possible)
  const prevPos = new Map(simNodes.map(n => [n._idx, { x: n.x, y: n.y }]))
  simNodes = props.gNodes.map((n, i) => {
    const prev = prevPos.get(i)
    return {
      _idx: i,
      id:   n.id,
      type: n.id === 'org-root' ? 'org-root' : n.type,
      x:    prev ? prev.x : w / 2 + (Math.random() - 0.5) * 200,
      y:    prev ? prev.y : h / 2 + (Math.random() - 0.5) * 200,
      vx: 0, vy: 0,
    }
  })

  simEdges = props.gEdges.map(e => ({
    source: e.from,
    target: e.to,
    rel:    e.rel,
  }))

  if (sim) sim.stop()

  // Strength per node type
  const chargeStr = (d) => {
    if (d.type === 'meeting_group') return -600
    if (d.type === 'dept')         return -300
    if (d.type === 'org-root')     return -400
    return -180
  }

  sim = forceSimulation(simNodes)
    .force('link', forceLink(simEdges)
      .id(d => d._idx)
      .distance(d => {
        const src = simNodes[d.source._idx ?? d.source]
        const tgt = simNodes[d.target._idx ?? d.target]
        if (!src || !tgt) return 120
        if (src.type === 'meeting_group' || tgt.type === 'meeting_group') return 140
        return 90
      })
      .strength(0.4)
    )
    .force('charge',  forceManyBody().strength(chargeStr))
    .force('center',  forceCenter(w / 2, h / 2).strength(0.05))
    .force('collide', forceCollide(d => getRadius(d.type) + 12).strength(0.7))
    .force('x', forceX(w / 2).strength(0.04))
    .force('y', forceY(h / 2).strength(0.04))
    .alphaDecay(0.015)
    .on('tick', () => {}) // handled in PIXI ticker

  rebuildNodeObjects()
}

function getRadius(type) {
  return NODE_RADIUS[type] ?? 16
}

// ─── Node Objects ─────────────────────────────────────────────
function rebuildNodeObjects() {
  if (!nodeContainer) return
  nodeContainer.removeChildren()
  labelContainer.removeChildren()
  nodeObjs.clear()

  props.gNodes.forEach((n, i) => {
    const type = n.id === 'org-root' ? 'org-root' : n.type
    const r = getRadius(type)

    // Graphics
    const gfx = new PIXI.Graphics()
    gfx.eventMode = 'static'
    gfx.cursor = 'pointer'
    gfx._nodeIdx = i
    gfx.on('pointerdown', (e) => { e.stopPropagation(); onNodeDown(i) })
    gfx.on('pointerup',   (e) => { e.stopPropagation(); onNodeUp(i) })
    gfx.on('pointerover', ()  => { onNodeOver(i) })
    gfx.on('pointerout',  ()  => { onNodeOut(i) })
    nodeContainer.addChild(gfx)

    // Label
    const label = new PIXI.Text({
      text: (n.label || '').slice(0, 9),
      style: {
        fontSize:   type === 'meeting_group' ? 13 : 10,
        fontFamily: 'sans-serif',
        fontWeight: type === 'meeting_group' ? 'bold' : 'normal',
        fill:       props.nightMode ? 0xe2e8f0 : 0x0f172a,
        align:      'center',
      }
    })
    label.anchor.set(0.5, 0)
    labelContainer.addChild(label)

    nodeObjs.set(i, { gfx, label, node: n, type, r, hovered: false, focused: false })
  })
}

function drawNode(obj, sn) {
  const { gfx, node, type, r } = obj
  const isDark  = props.nightMode
  const isFocus = focusedIdx === sn._idx
  const isHl    = props.queryHlIdxs?.has(sn._idx)
  const isSearch = props.searchHitMgIdxs?.includes(sn._idx)
  const urgency  = type === 'meeting_group' ? props.computeUrgency(node.data) : null
  const hubColor = type === 'meeting_group' ? hexToNum(props.getHubFill(node.data)) : (NODE_COLORS[type] ?? 0x3b82f6)

  gfx.clear()

  // Query highlight glow
  if (isHl) {
    gfx.circle(0, 0, r * 2.6)
    gfx.fill({ color: 0x6366f1, alpha: 0.18 })
    gfx.circle(0, 0, r + 6)
    gfx.stroke({ color: 0x818cf8, width: 2.5, alpha: 0.9 })
  }

  // Search hit pulse ring
  if (isSearch) {
    gfx.circle(0, 0, r + 9)
    gfx.stroke({ color: 0xfbbf24, width: 2.2, alpha: 0.85 })
  }

  // Main circle
  gfx.circle(0, 0, r)
  if (type === 'meeting_group') {
    gfx.fill({ color: hubColor, alpha: urgency === 'critical' ? 0.95 : 0.88 })
  } else {
    gfx.fill({ color: NODE_COLORS[type] ?? 0x60a5fa, alpha: 1 })
  }

  // Focus / hover ring
  if (isFocus || obj.focused) {
    gfx.circle(0, 0, r)
    gfx.stroke({ color: isDark ? 0xffffff : 0x1e293b, width: 2.5, alpha: 1 })
  } else if (obj.hovered) {
    gfx.circle(0, 0, r)
    gfx.stroke({ color: isDark ? 0xffffff : 0x1e293b, width: 3, alpha: 0.85 })
  }

  // Todo progress arc (meeting_group)
  const ratio = type === 'meeting_group'
    ? (props.groupTodoRatio?.get(node.data?.id ?? node.id) ?? null)
    : null
  if (ratio != null && ratio > 0) {
    gfx.arc(0, 0, r + 4, -Math.PI / 2, -Math.PI / 2 + ratio * Math.PI * 2)
    gfx.stroke({ color: 0x86efac, width: 2.5, alpha: 0.85 })
  }

  // Icon drawing (inline via Graphics)
  drawIcon(gfx, type, r)
}

function drawIcon(gfx, type, r) {
  const ic = 0xffffff
  if (type === 'org-root') {
    // person silhouette
    gfx.circle(0, -r * 0.22, r * 0.22).fill({ color: ic, alpha: 0.9 })
    gfx.arc(0, r * 0.08 + r * 0.29 * 0.7, r * 0.29, Math.PI, Math.PI * 2)
    gfx.fill({ color: ic, alpha: 0.9 })
  } else if (type === 'meeting_group') {
    // no extra icon — label centered inside
  } else if (type === 'agenda') {
    // checkmark
    const cs = r * 0.45
    gfx.moveTo(-cs, cs * 0.1).lineTo(-cs * 0.18, cs * 0.78).lineTo(cs, -cs * 0.62)
    gfx.stroke({ color: ic, width: Math.max(1.5, r * 0.13), alpha: 0.92, cap: 'round', join: 'round' })
  } else if (type === 'session') {
    // calendar
    const cw = r * 0.6, ch = r * 0.52
    const fx = -cw / 2, fy = -ch / 2 + r * 0.05
    gfx.rect(fx, fy, cw, ch).stroke({ color: ic, width: Math.max(1, r * 0.09), alpha: 0.92 })
    gfx.moveTo(fx, fy + ch * 0.33).lineTo(fx + cw, fy + ch * 0.33)
    gfx.stroke({ color: ic, width: Math.max(1, r * 0.09), alpha: 0.92 })
    const cr = r * 0.09
    gfx.circle(fx + cw * 0.28, fy - cr * 0.3, cr).fill({ color: ic, alpha: 0.92 })
    gfx.circle(fx + cw * 0.72, fy - cr * 0.3, cr).fill({ color: ic, alpha: 0.92 })
  } else if (type === 'file') {
    // folded doc
    const fw = r * 0.44, fh = r * 0.56, fold = fw * 0.3
    const fx = -fw / 2, fy = -fh / 2
    gfx.moveTo(fx, fy).lineTo(fx + fw - fold, fy).lineTo(fx + fw, fy + fold)
      .lineTo(fx + fw, fy + fh).lineTo(fx, fy + fh).closePath()
    gfx.stroke({ color: ic, width: Math.max(1, r * 0.08), alpha: 0.9 })
  } else if (type === 'dept') {
    // two-people icon
    const shr = r * 0.13, sbr = r * 0.16, shx = -r * 0.24, shy = -r * 0.14
    gfx.circle(shx, shy, shr).fill({ color: ic, alpha: 0.92 })
    gfx.arc(shx, shy + shr + sbr * 1.1, sbr, Math.PI, Math.PI * 2).fill({ color: ic, alpha: 0.92 })
    const bhr = r * 0.18, bbr = r * 0.22, bhx = r * 0.2, bhy = -r * 0.17
    gfx.circle(bhx, bhy, bhr).fill({ color: ic, alpha: 0.92 })
    gfx.arc(bhx, bhy + bhr + bbr * 1.1, bbr, Math.PI, Math.PI * 2).fill({ color: ic, alpha: 0.92 })
  } else if (type === 'person') {
    const hr = r * 0.22, br = r * 0.28
    gfx.circle(0, -r * 0.18, hr).fill({ color: ic, alpha: 0.88 })
    gfx.arc(0, -r * 0.18 + hr + br * 1.1, br, Math.PI, Math.PI * 2).fill({ color: ic, alpha: 0.88 })
  }
}

// ─── Tick / Render ───────────────────────────────────────────
let _hlPulse = 0
function tick() {
  if (!app || !sim) return
  _hlPulse += 0.05

  // Advance simulation one step
  sim.tick()

  const w = app.screen.width, h = app.screen.height

  // Apply viewport transform to all layers
  for (const layer of [edgeLayer, nodeContainer, labelContainer, hlLayer]) {
    layer.x = vpX; layer.y = vpY
    layer.scale.set(vpScale)
  }
  app.stage.hitArea = new PIXI.Rectangle(-vpX / vpScale, -vpY / vpScale, w / vpScale, h / vpScale)

  // ── Draw edges ────────────────────────────────────────────
  edgeLayer.clear()
  hlLayer.clear()

  const hidSet = new Set(props.hiddenNodeTypes)
  const isHidden = (i) => {
    const n = props.gNodes[i]; if (!n) return false
    return hidSet.has(n.id === 'org-root' ? 'org-root' : n.type)
  }

  simEdges.forEach((e, ei) => {
    const si = typeof e.source === 'object' ? e.source._idx : e.source
    const ti = typeof e.target === 'object' ? e.target._idx : e.target
    if (isHidden(si) || isHidden(ti)) return
    const sn = simNodes[si], tn = simNodes[ti]
    if (!sn || !tn) return

    const relColor = hexToNum(props.relColors[e.rel] || '#60a5fa')
    const isHlEdge = props.queryHlEdgeIdxs?.has(ei)
    const isFocEdge = focusedIdx !== null && (si === focusedIdx || ti === focusedIdx)

    const alpha = focusedIdx !== null
      ? (isFocEdge ? 0.85 : 0.12)
      : 0.35

    // dx/dy for arrow
    const dx = tn.x - sn.x, dy = tn.y - sn.y
    const len = Math.sqrt(dx * dx + dy * dy); if (len < 4) return
    const ux = dx / len, uy = dy / len
    const tr = getRadius(tn.type) + 4
    const ex = tn.x - ux * tr, ey = tn.y - uy * tr

    // Highlight glow
    if (isHlEdge) {
      const pulse = 0.4 + 0.4 * Math.sin(_hlPulse * 4)
      hlLayer.moveTo(sn.x, sn.y).lineTo(tn.x, tn.y)
      hlLayer.stroke({ color: 0x8b5cf6, width: 7, alpha: 0.55 * pulse, cap: 'round' })
    }

    // Edge line (slight curve)
    const bow = Math.min(len * 0.15, 30)
    const cpx = (sn.x + tn.x) / 2 - uy * bow
    const cpy = (sn.y + tn.y) / 2 + ux * bow
    const sr = getRadius(typeof e.source === 'object' ? e.source.type : (props.gNodes[si]?.type ?? 'file')) + 3
    const sx2 = sn.x + ux * sr, sy2 = sn.y + uy * sr

    edgeLayer.moveTo(sx2, sy2).quadraticCurveTo(cpx, cpy, ex, ey)
    edgeLayer.stroke({ color: relColor, width: isFocEdge ? 1.8 : 0.9, alpha })

    // Arrowhead
    const as = 7
    const px2 = -uy * as * 0.44, py2 = ux * as * 0.44
    edgeLayer.poly([ex, ey, ex - ux * as + px2, ey - uy * as + py2, ex - ux * as - px2, ey - uy * as - py2])
    edgeLayer.fill({ color: relColor, alpha })

    // Edge label (only when focused or zoomed in)
    if (e.rel && (isFocEdge || vpScale > 1.4) && len > 40) {
      const lx = (sn.x + tn.x) / 2 - uy * 8
      const ly = (sn.y + tn.y) / 2 + ux * 8
      edgeLayer.moveTo(lx - 1, ly)  // placeholder — text drawn in DOM
      // We'll draw rel label as Text below using a separate pass
    }
  })

  // ── Draw nodes ───────────────────────────────────────────
  simNodes.forEach((sn, i) => {
    const obj = nodeObjs.get(i)
    if (!obj) return
    const hidden = hidSet.has(sn.type)
    obj.gfx.visible   = !hidden
    obj.label.visible = !hidden

    if (hidden) return

    // Position
    obj.gfx.x  = sn.x;  obj.gfx.y  = sn.y
    obj.label.x = sn.x; obj.label.y = sn.y + obj.r + 3

    // Fade non-focused
    const alphaVal = focusedIdx !== null
      ? (i === focusedIdx || isNeighbor(i, focusedIdx) ? 1.0 : 0.2)
      : 1.0
    obj.gfx.alpha   = alphaVal
    obj.label.alpha = alphaVal * (sn.type === 'meeting_group' ? 0 : 0.9)  // MG label inside node

    // Redraw
    obj.focused = (i === focusedIdx)
    drawNode(obj, sn)

    // MG label — draw inside node via PIXI.Text offset
    if (sn.type === 'meeting_group') {
      obj.label.y = sn.y   // center vertically
      obj.label.anchor.set(0.5, 0.5)
      obj.label.alpha = alphaVal * 0.95
      obj.label.style.fill = props.nightMode ? 0xffffff : 0x1e3a8a
    } else {
      obj.label.anchor.set(0.5, 0)
    }
  })
}

function isNeighbor(a, b) {
  for (const e of simEdges) {
    const si = typeof e.source === 'object' ? e.source._idx : e.source
    const ti = typeof e.target === 'object' ? e.target._idx : e.target
    if ((si === a && ti === b) || (si === b && ti === a)) return true
  }
  return false
}

// ─── Interaction ─────────────────────────────────────────────
let _downX = 0, _downY = 0, _didMove = false
function onBgDown(e) {
  const p = e.global
  isPanning  = true
  panStartX  = p.x; panStartY  = p.y
  panOrigX   = vpX; panOrigY   = vpY
  _downX     = p.x; _downY     = p.y
  _didMove   = false
}
function onBgMove(e) {
  if (!isPanning) return
  const p = e.global
  if (Math.abs(p.x - _downX) + Math.abs(p.y - _downY) > 4) _didMove = true
  vpX = panOrigX + (p.x - panStartX)
  vpY = panOrigY + (p.y - panStartY)
}
function onBgUp() {
  isPanning = false
  if (!_didMove) {
    focusedIdx = null
    emit('bgClick')
  }
}

let _nodeDownTime = 0
function onNodeDown(idx) {
  _nodeDownTime = Date.now()
  isPanning = false  // don't pan when clicking node
}
function onNodeUp(idx) {
  if (Date.now() - _nodeDownTime < 300) {
    if (focusedIdx === idx) {
      focusedIdx = null
    } else {
      focusedIdx = idx
      // Pin node
      const sn = simNodes[idx]
      if (sn) { sn.fx = sn.x; sn.fy = sn.y; setTimeout(() => { if(sn){ sn.fx=null; sn.fy=null } }, 1200) }
    }
    emit('nodeClick', props.gNodes[idx], idx)
  }
}
function onNodeOver(idx) {
  const obj = nodeObjs.get(idx); if (obj) obj.hovered = true
}
function onNodeOut(idx) {
  const obj = nodeObjs.get(idx); if (obj) obj.hovered = false
}

function onWheel(e) {
  e.preventDefault()
  const rect = app.canvas.getBoundingClientRect()
  const mx = e.clientX - rect.left
  const my = e.clientY - rect.top
  const factor = e.deltaY < 0 ? 1.12 : 0.89
  const newScale = Math.max(0.2, Math.min(6, vpScale * factor))
  vpX = mx - (mx - vpX) * (newScale / vpScale)
  vpY = my - (my - vpY) * (newScale / vpScale)
  vpScale = newScale
}

// ─── Exposed controls ─────────────────────────────────────────
function zoomIn()  { vpScale = Math.min(6,   vpScale * 1.25) }
function zoomOut() { vpScale = Math.max(0.2,  vpScale / 1.25) }
function resetView() {
  vpX = 0; vpY = 0; vpScale = 1; focusedIdx = null
}
/** 뷰포트 좌표(px) → 가장 가까운 gNode 반환, 없으면 null */
function getNodeAtScreen(sx, sy) {
  if (!app) return null
  const el = containerRef.value
  const rect = el ? el.getBoundingClientRect() : { left: 0, top: 0 }
  const wx = ((sx - rect.left) - vpX) / vpScale
  const wy = ((sy - rect.top)  - vpY) / vpScale
  let best = null, bestDist = Infinity
  for (const sn of simNodes) {
    const r = getRadius(sn.type) + 24
    const dx = sn.x - wx, dy = sn.y - wy
    const dist = Math.sqrt(dx * dx + dy * dy)
    if (dist < r && dist < bestDist) { best = sn; bestDist = dist }
  }
  return best ? props.gNodes[best._idx] ?? null : null
}

/** gNode id → 뷰포트 기준 화면 좌표 {x, y} 반환 */
function getNodeScreenPos(nodeId) {
  if (!app || !containerRef.value) return null
  const sn = simNodes.find(n => props.gNodes[n._idx]?.id === nodeId)
  if (!sn) return null
  const rect = containerRef.value.getBoundingClientRect()
  return {
    x: rect.left + sn.x * vpScale + vpX,
    y: rect.top  + sn.y * vpScale + vpY,
  }
}

defineExpose({ zoomIn, zoomOut, resetView, reloadGraph: buildSimulation, getNodeAtScreen, getNodeScreenPos })

// ─── Helpers ─────────────────────────────────────────────────
function hexToNum(hex) {
  if (!hex) return 0x60a5fa
  return parseInt(hex.replace('#', ''), 16)
}

// ─── Watchers ─────────────────────────────────────────────────
watch(() => props.gNodes.length, () => buildSimulation())
watch(() => props.nightMode, () => {
  // update label colors
  nodeObjs.forEach(obj => {
    obj.label.style.fill = props.nightMode ? 0xe2e8f0 : 0x0f172a
  })
})

// ─── Lifecycle ────────────────────────────────────────────────
onMounted(() => initPixi())
onBeforeUnmount(() => destroyPixi())
</script>

<template>
  <div ref="containerRef" class="gv-wrap" />
</template>

<style scoped>
.gv-wrap {
  width: 100%;
  height: 100%;
  position: relative;
  overflow: hidden;
}
</style>
