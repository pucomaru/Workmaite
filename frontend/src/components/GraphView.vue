<script setup>
import { ref, watch, onBeforeUnmount, onMounted } from 'vue'
import * as PIXI from 'pixi.js'
import {
  forceSimulation, forceLink, forceManyBody, forceCenter, forceCollide,
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
  selfNodeId:     { type: String,   default: null },
})
const emit = defineEmits(['nodeClick', 'nodeDblClick', 'bgClick'])

// ─── Constants ────────────────────────────────────────────────
const NODE_COLORS = {
  'Meetings':      0x3b82f6,
  'agenda':        0xf59e0b,
  'session':       0xf97316,
  'minutes':       0x60a5fa,
  'report':        0x34d399,
  'dept':          0x8b5cf6,
  'person':        0xf472b6,
  'company':       0x0d9488,
  'human_judgment': 0x22d3ee,
}
const NODE_RADIUS = {
  'Meetings':      11,
  'agenda':        10,
  'session':       10,
  'minutes':       10,
  'report':        10,
  'dept':          10,
  'person':        10,
  'company':       10,
  'human_judgment':  9,
}
// inbound 기반 노드 크기
const BACKLINK_STEP = 2.4   // 백링크 1개당 가중치
const BACKLINK_MAX  = 28    // 최대 추가 반경
const SELF_RADIUS   = 11    // "나" 노드 고정 반경

// ─── Refs ─────────────────────────────────────────────────────
const containerRef = ref(null)
const panOnly = ref(false)   // 이동 전용 모드 (노드 클릭/드래그 비활성, 배경 팬만)
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

// 노드 idx → inbound(백링크) 개수
let inboundCount = new Map()

// pan/zoom state
let vpX = 0, vpY = 0, vpScale = 1
let isPanning = false, panStartX = 0, panStartY = 0, panOrigX = 0, panOrigY = 0

// dirty flag — sim이 움직이거나 인터랙션이 발생했을 때만 리드로우
let _simDirty = true

// highlight blink state
let _hlBlinkVisible = false
let _blinkTimer = null
function _startBlink() {
  clearInterval(_blinkTimer)
  _hlBlinkVisible = true
  _simDirty = true
  let count = 0
  _blinkTimer = setInterval(() => {
    count++
    _hlBlinkVisible = !_hlBlinkVisible
    _simDirty = true
    if (count >= 6) { clearInterval(_blinkTimer); _hlBlinkVisible = true; _simDirty = true }
  }, 200)
}

// node drag state
let _draggingIdx = null
let _didNodeDrag = false

// smooth lerp target for search focus animation
let _targetVpX = null, _targetVpY = null, _targetVpScale = null

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
function buildSimulation(nodes, edges) {
  if (!app) return
  const w = app.screen.width, h = app.screen.height
  const ns = nodes ?? props.gNodes
  const es = edges ?? props.gEdges

  // Build sim nodes (preserve positions if possible)
  const prevPos = new Map(simNodes.map(n => [n._idx, { x: n.x, y: n.y }]))
  simNodes = ns.map((n, i) => {
    const prev = prevPos.get(i)
    return {
      _idx:  i,
      id:    n.id,
      type:  n.type,
      ended: n.ended ?? false,
      x:    prev ? prev.x : w / 2 + (Math.random() - 0.5) * 200,
      y:    prev ? prev.y : h / 2 + (Math.random() - 0.5) * 200,
      vx: 0, vy: 0,
    }
  })

  simEdges = es.map(e => ({
    source: e.from,
    target: e.to,
    rel:    e.rel,
  }))

  // inbound(백링크) 개수 집계 — target으로 들어오는 엣지 수
  inboundCount = new Map()
  for (const e of es) {
    inboundCount.set(e.to, (inboundCount.get(e.to) || 0) + 1)
  }

  if (sim) sim.stop()

  sim = forceSimulation(simNodes)
    .force('link', forceLink(simEdges)
      .id(d => d._idx)
      .distance(110)
      .strength(0.4)
    )
    .force('charge',  forceManyBody().strength(-220))
    .force('center',  forceCenter(w / 2, h / 2).strength(0.06))
    .force('collide', forceCollide(d => nodeRadiusForIdx(d._idx, d.type, d.id) + 14).strength(0.85))
    .alphaDecay(0.025)
    .on('tick', () => { _simDirty = true })

  rebuildNodeObjects()
}

function getRadius(type) {
  return NODE_RADIUS[type] ?? 16
}

// 백링크(inbound) 개수에 따른 추가 반경 — sqrt 스케일로 완만하게 증가
function backlinkBonus(idx) {
  const c = inboundCount.get(idx) || 0
  if (c <= 0) return 0
  return Math.min(BACKLINK_MAX, Math.sqrt(c) * BACKLINK_STEP)
}

// 노드 인덱스별 최종 반경 ("나" 노드는 고정 크기)
function nodeRadiusForIdx(idx, type, id) {
  if (props.selfNodeId != null && id === props.selfNodeId) return SELF_RADIUS
  return getRadius(type) + backlinkBonus(idx)
}

// ─── Node Objects ─────────────────────────────────────────────
function rebuildNodeObjects() {
  if (!nodeContainer) return
  nodeContainer.removeChildren()
  labelContainer.removeChildren()
  nodeObjs.clear()

  props.gNodes.forEach((n, i) => {
    const type = n.type
    const r = nodeRadiusForIdx(i, type, n.id)

    // Graphics
    const gfx = new PIXI.Graphics()
    gfx.eventMode = 'static'
    gfx.cursor = 'pointer'
    gfx.hitArea = new PIXI.Circle(0, 0, r + 4)
    gfx._nodeIdx = i
    gfx.on('pointerdown', (e) => { e.stopPropagation(); onNodeDown(i, e) })
    gfx.on('pointerup',   (e) => { e.stopPropagation(); onNodeUp(i) })
    gfx.on('pointerover', ()  => { onNodeOver(i) })
    gfx.on('pointerout',  ()  => { onNodeOut(i) })
    nodeContainer.addChild(gfx)

    // Label
    const label = new PIXI.Text({
      text: (n.label || '').slice(0, 9),
      style: {
        fontSize:   10,
        fontFamily: 'sans-serif',
        fontWeight: 'normal',
        fill:       props.nightMode ? 0xe2e8f0 : 0x0f172a,
        align:      'center',
      },
      resolution: (window.devicePixelRatio || 1) * 3,
    })
    label.anchor.set(0.5, 0)
    label.eventMode = 'none'  // labels must not intercept pointer events
    labelContainer.addChild(label)

    nodeObjs.set(i, { gfx, label, node: n, type, r, hovered: false, focused: false })
  })
}

function drawNode(obj, sn) {
  const { gfx, node, type } = obj
  const isDark  = props.nightMode
  const isFocus = focusedIdx === sn._idx
  const isHl    = props.queryHlIdxs?.has(sn._idx)
  const isSearch = props.searchHitMgIdxs?.includes(sn._idx)
  const isSelf  = props.selfNodeId != null && node.id === props.selfNodeId
  const r = isSelf ? obj.r + 3 : obj.r
  const urgency  = type === 'Meetings' ? props.computeUrgency(node.data) : null
  const hubColor = type === 'Meetings' ? hexToNum(props.getHubFill(node.data)) : (NODE_COLORS[type] ?? 0x3b82f6)

  gfx.clear()

  // Search hit — yellow ring
  if (isSearch) {
    gfx.circle(0, 0, r + 6)
    gfx.stroke({ color: 0xfbbf24, width: 3, alpha: 1 })
  }

  // Main circle
  gfx.circle(0, 0, r)
  if (type === 'Meetings') {
    gfx.fill({ color: hubColor, alpha: urgency === 'critical' ? 0.95 : 0.88 })
  } else {
    gfx.fill({ color: NODE_COLORS[type] ?? 0x60a5fa, alpha: 1 })
  }

  // 자신 노드 — 검정 테두리로 구분
  if (isSelf && !isFocus && !obj.focused && !obj.hovered) {
    gfx.circle(0, 0, r)
    gfx.stroke({ color: isDark ? 0x0f172a : 0x0f172a, width: 2.5, alpha: 0.9 })
  }

  // Focus / hover ring
  if (isFocus || obj.focused) {
    gfx.circle(0, 0, r)
    gfx.stroke({ color: isDark ? 0xffffff : 0x1e293b, width: 2.5, alpha: 1 })
  } else if (obj.hovered) {
    gfx.circle(0, 0, r)
    gfx.stroke({ color: isDark ? 0xffffff : 0x1e293b, width: 3, alpha: 0.85 })
  }

  // Todo progress arc (Meetings, 진행 중인 회의체만)
  const ratio = (type === 'Meetings' && !node.ended)
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
  if (type === 'Meetings') {
    // hub icon: center dot + 3 outer dots connected by lines
    const spoke = r * 0.42
    const angles = [Math.PI * 1.5, Math.PI * 1.5 + Math.PI * 2 / 3, Math.PI * 1.5 + Math.PI * 4 / 3]
    for (const a of angles) {
      const ox = Math.cos(a) * spoke, oy = Math.sin(a) * spoke
      gfx.moveTo(0, 0).lineTo(ox, oy)
      gfx.stroke({ color: ic, width: Math.max(1, r * 0.1), alpha: 0.7, cap: 'round' })
      gfx.circle(ox, oy, r * 0.14).fill({ color: ic, alpha: 0.9 })
    }
    gfx.circle(0, 0, r * 0.18).fill({ color: ic, alpha: 0.95 })
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
  } else if (type === 'minutes' || type === 'report') {
    // folded doc — minutes: plain, report: with line accent
    const fw = r * 0.44, fh = r * 0.56, fold = fw * 0.3
    const fx = -fw / 2, fy = -fh / 2
    gfx.moveTo(fx, fy).lineTo(fx + fw - fold, fy).lineTo(fx + fw, fy + fold)
      .lineTo(fx + fw, fy + fh).lineTo(fx, fy + fh).closePath()
    gfx.stroke({ color: ic, width: Math.max(1, r * 0.08), alpha: 0.9 })
    if (type === 'report') {
      // 가로선 2개로 보고서 느낌
      const lx1 = fx + fw * 0.18, lx2 = fx + fw * 0.82, ly1 = fy + fh * 0.52, ly2 = fy + fh * 0.7
      gfx.moveTo(lx1, ly1).lineTo(lx2, ly1).stroke({ color: ic, width: Math.max(1, r * 0.07), alpha: 0.7 })
      gfx.moveTo(lx1, ly2).lineTo(lx2, ly2).stroke({ color: ic, width: Math.max(1, r * 0.07), alpha: 0.7 })
    }
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
  } else if (type === 'company') {
    // building / company icon
    const bw = r * 0.62, bh = r * 0.66
    const bx = -bw / 2, by = -bh / 2 + r * 0.04
    gfx.rect(bx, by, bw, bh).stroke({ color: ic, width: Math.max(1, r * 0.08), alpha: 0.92 })
    // windows (2 columns x 3 rows)
    const wsz = r * 0.1
    const cols = [bx + bw * 0.28, bx + bw * 0.72]
    const rows = [by + bh * 0.22, by + bh * 0.5, by + bh * 0.78]
    for (const cx of cols) {
      for (const cy of rows) {
        gfx.rect(cx - wsz / 2, cy - wsz / 2, wsz, wsz).fill({ color: ic, alpha: 0.92 })
      }
    }
  }
}

// ─── Tick / Render ───────────────────────────────────────────
function tick() {
  if (!app || !sim) return

  // viewport lerp 진행 중이면 dirty
  if (_targetVpX !== null) _simDirty = true

  // 리드로우가 필요 없으면 skip
  if (!_simDirty) return
  _simDirty = false

  // Lerp viewport toward search focus target
  if (_targetVpX !== null) {
    vpX     += (_targetVpX     - vpX)     * 0.1
    vpY     += (_targetVpY     - vpY)     * 0.1
    vpScale += (_targetVpScale - vpScale) * 0.1
    if (Math.abs(vpX - _targetVpX) < 0.5 && Math.abs(vpY - _targetVpY) < 0.5 && Math.abs(vpScale - _targetVpScale) < 0.001) {
      vpX = _targetVpX; vpY = _targetVpY; vpScale = _targetVpScale
      _targetVpX = null; _targetVpY = null; _targetVpScale = null
    }
  }

  const w = app.screen.width, h = app.screen.height

  // Apply viewport transform to all layers
  for (const layer of [edgeLayer, nodeContainer, labelContainer, hlLayer]) {
    layer.x = vpX; layer.y = vpY
    layer.scale.set(vpScale)
  }
  // stage hitArea는 항상 스크린 좌표 — 월드 좌표로 변환하면 고배율 시 클릭 무효 버그 발생
  app.stage.hitArea = new PIXI.Rectangle(0, 0, w, h)

  // ── Draw edges ────────────────────────────────────────────
  edgeLayer.clear()
  hlLayer.clear()

  const hidSet = new Set(props.hiddenNodeTypes)
  const isHidden = (i) => {
    const n = props.gNodes[i]; if (!n) return false
    return hidSet.has(n.type)
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
    const endedEdge = props.gNodes[si]?.ended || props.gNodes[ti]?.ended

    const alpha = (focusedIdx !== null
      ? (isFocEdge ? 0.85 : 0.12)
      : 0.35) * (endedEdge ? 0.45 : 1.0)

    // dx/dy for arrow
    const dx = tn.x - sn.x, dy = tn.y - sn.y
    const len = Math.sqrt(dx * dx + dy * dy); if (len < 4) return
    const ux = dx / len, uy = dy / len
    const tr = nodeRadiusForIdx(ti, tn.type, props.gNodes[ti]?.id) + 4
    const ex = tn.x - ux * tr, ey = tn.y - uy * tr

    // Edge line (straight)
    const sr = nodeRadiusForIdx(si, props.gNodes[si]?.type ?? 'minutes', props.gNodes[si]?.id) + 3
    const sx2 = sn.x + ux * sr, sy2 = sn.y + uy * sr

    const hlOn = isHlEdge && _hlBlinkVisible
    const finalAlpha = hlOn && focusedIdx === null ? 0.75 : alpha
    edgeLayer.moveTo(sx2, sy2).lineTo(ex, ey)
    edgeLayer.stroke({ color: relColor, width: (isFocEdge || hlOn) ? 1.8 : 0.9, alpha: finalAlpha })

    // Arrowhead
    const as = 7
    const px2 = -uy * as * 0.44, py2 = ux * as * 0.44
    edgeLayer.poly([ex, ey, ex - ux * as + px2, ey - uy * as + py2, ex - ux * as - px2, ey - uy * as - py2])
    edgeLayer.fill({ color: relColor, alpha: finalAlpha })
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

    // Fade non-focused / non-search-hit
    const hasSearchHits = props.searchHitMgIdxs?.length > 0
    const alphaVal = focusedIdx !== null
      ? (i === focusedIdx || isNeighbor(i, focusedIdx) ? 1.0 : 0.2)
      : hasSearchHits
        ? (props.searchHitMgIdxs.includes(i) ? 1.0 : 0.15)
        : 1.0
    const endedDim = sn.ended ? 0.45 : 1.0
    obj.gfx.alpha   = alphaVal * endedDim
    obj.label.alpha = alphaVal * endedDim * 0.9

    // Redraw
    obj.focused = (i === focusedIdx)
    drawNode(obj, sn)

    obj.label.anchor.set(0.5, 0)
    // Update text resolution to match zoom for crisp text at any scale
    const targetRes = (window.devicePixelRatio || 1) * Math.max(2, Math.ceil(vpScale * 1.5))
    if (obj.label.resolution !== targetRes) obj.label.resolution = targetRes
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
// PIXI v8 registers a global pointerup listener on globalThis for drag tracking.
// Without this flag, any DOM element click (e.g. sidebar tabs) fires onBgUp and
// emits 'bgClick', closing the sidebar unintentionally.
let _downX = 0, _downY = 0, _didMove = false
let _pointerDownOnCanvas = false
function onBgDown(e) {
  _pointerDownOnCanvas = true
  const p = e.global
  isPanning  = true
  panStartX  = p.x; panStartY  = p.y
  panOrigX   = vpX; panOrigY   = vpY
  _downX     = p.x; _downY     = p.y
  _didMove   = false
}
function onBgMove(e) {
  const p = e.global
  if (_draggingIdx !== null) {
    if (Math.abs(p.x - _downX) + Math.abs(p.y - _downY) > 4) {
      _didNodeDrag = true
      _targetVpX = null; _targetVpY = null; _targetVpScale = null
    }
    const wx = (p.x - vpX) / vpScale
    const wy = (p.y - vpY) / vpScale
    const sn = simNodes[_draggingIdx]
    if (sn) { sn.fx = wx; sn.fy = wy; sn.x = wx; sn.y = wy; _simDirty = true }
    return
  }
  if (!isPanning) return
  if (Math.abs(p.x - _downX) + Math.abs(p.y - _downY) > 4) {
    _didMove = true
    _targetVpX = null; _targetVpY = null; _targetVpScale = null
  }
  vpX = panOrigX + (p.x - panStartX)
  vpY = panOrigY + (p.y - panStartY)
  _simDirty = true
}
function onBgUp() {
  if (_draggingIdx !== null) {
    const sn = simNodes[_draggingIdx]
    if (sn) { sn.fx = null; sn.fy = null }
    sim?.alphaTarget(0)
    _draggingIdx = null
    _didNodeDrag = false
    return
  }
  if (!_pointerDownOnCanvas) return
  _pointerDownOnCanvas = false
  isPanning = false
  if (!_didMove) {
    focusedIdx = null
    emit('bgClick')
  }
}

let _nodeDownTime = 0
function onNodeDown(idx, e) {
  // 이동 전용 모드: 노드 클릭/드래그 무시하고 배경 팬으로 동작
  if (panOnly.value) { onBgDown(e); return }
  _nodeDownTime = Date.now()
  isPanning = false
  _draggingIdx = idx
  _didNodeDrag = false
  if (e?.global) { _downX = e.global.x; _downY = e.global.y }
  const sn = simNodes[idx]
  if (sn) { sn.fx = sn.x; sn.fy = sn.y; sim?.alphaTarget(0.3).restart() }
}
function onNodeUp(idx) {
  if (panOnly.value) { onBgUp(); return }
  const sn = simNodes[idx]
  if (_didNodeDrag) {
    if (sn) { sn.fx = null; sn.fy = null }
    sim?.alphaTarget(0)
  } else if (Date.now() - _nodeDownTime < 300) {
    if (focusedIdx === idx) {
      focusedIdx = null
    } else {
      focusedIdx = idx
      if (sn) { sn.fx = sn.x; sn.fy = sn.y; setTimeout(() => { if(sn){ sn.fx=null; sn.fy=null } }, 1200) }
    }
    _simDirty = true
    emit('nodeClick', props.gNodes[idx], idx)
  }
  _draggingIdx = null
  _didNodeDrag = false
}
function onNodeOver(idx) {
  const obj = nodeObjs.get(idx); if (obj) { obj.hovered = true; _simDirty = true }
}
function onNodeOut(idx) {
  const obj = nodeObjs.get(idx); if (obj) { obj.hovered = false; _simDirty = true }
}

function onWheel(e) {
  e.preventDefault()
  _targetVpX = null; _targetVpY = null; _targetVpScale = null
  const rect = app.canvas.getBoundingClientRect()
  const mx = e.clientX - rect.left
  const my = e.clientY - rect.top
  const factor = e.deltaY < 0 ? 1.12 : 0.89
  const newScale = Math.max(0.2, Math.min(3, vpScale * factor))
  vpX = mx - (mx - vpX) * (newScale / vpScale)
  vpY = my - (my - vpY) * (newScale / vpScale)
  vpScale = newScale
  _simDirty = true
}

// ─── Exposed controls ─────────────────────────────────────────
function zoomIn()  { vpScale = Math.min(3,   vpScale * 1.25); _simDirty = true }
function zoomOut() { vpScale = Math.max(0.2,  vpScale / 1.25); _simDirty = true }
function resetView() {
  vpX = 0; vpY = 0; vpScale = 1; focusedIdx = null; _simDirty = true
}
/** 이동 전용 모드 토글 — 켜면 노드 클릭/드래그 없이 배경 팬만 가능 */
function togglePanOnly() {
  panOnly.value = !panOnly.value
  return panOnly.value
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

/** 검색 히트 노드들이 중앙으로 부드럽게 이동하도록 뷰포트 애니메이션 설정 */
function focusSearchHits(hitIdxs) {
  if (!hitIdxs || hitIdxs.length === 0) {
    _targetVpX = null; _targetVpY = null; _targetVpScale = null
    return
  }
  if (!app) return
  const hitNodes = hitIdxs.map(i => simNodes[i]).filter(Boolean)
  if (!hitNodes.length) return

  const w = app.screen.width, h = app.screen.height

  if (hitNodes.length === 1) {
    const sn = hitNodes[0]
    const s = Math.min(2.0, Math.max(1.2, vpScale))
    _targetVpX     = w / 2 - sn.x * s
    _targetVpY     = h / 2 - sn.y * s
    _targetVpScale = s
  } else {
    let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity
    for (const sn of hitNodes) {
      minX = Math.min(minX, sn.x); maxX = Math.max(maxX, sn.x)
      minY = Math.min(minY, sn.y); maxY = Math.max(maxY, sn.y)
    }
    const cx = (minX + maxX) / 2, cy = (minY + maxY) / 2
    const pad = 160
    const s = Math.max(0.3, Math.min(2.2, Math.min(w / (maxX - minX + pad), h / (maxY - minY + pad))))
    _targetVpX     = w / 2 - cx * s
    _targetVpY     = h / 2 - cy * s
    _targetVpScale = s
  }
}

defineExpose({ zoomIn, zoomOut, resetView, togglePanOnly, panOnly, reloadGraph: buildSimulation, getNodeAtScreen, getNodeScreenPos, focusSearchHits })

// ─── Helpers ─────────────────────────────────────────────────
function hexToNum(hex) {
  if (!hex) return 0x60a5fa
  return parseInt(hex.replace('#', ''), 16)
}

// ─── Watchers ─────────────────────────────────────────────────
watch(() => props.gNodes.length, () => buildSimulation())
watch(() => props.queryHlIdxs, (val) => {
  if (val?.size > 0) _startBlink()
  else { clearInterval(_blinkTimer); _hlBlinkVisible = false; _simDirty = true }
})
watch(() => props.queryHlEdgeIdxs, () => { _simDirty = true })
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
