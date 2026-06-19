<script setup>
import { ref, watch, onBeforeUnmount, onMounted } from 'vue'
import * as PIXI from 'pixi.js'
import { forceSimulation, forceLink, forceManyBody, forceCenter, forceCollide } from 'd3-force'
import { nodeIconSvg, NODE_ICON_PATHS } from '../graph/nodeIcons'

// ─── Props / Emits ────────────────────────────────────────────
const props = defineProps({
  gNodes: { type: Array, default: () => [] },
  gEdges: { type: Array, default: () => [] },
  nightMode: { type: Boolean, default: true },
  hiddenNodeTypes: { type: Array, default: () => [] },
  queryHlIdxs: { type: Object, default: () => new Set() }, // Set<number>
  queryHlEdgeIdxs: { type: Object, default: () => new Set() },
  searchHitMgIdxs: { type: Array, default: () => [] },
  getHubFill: { type: Function, required: true },
  computeUrgency: { type: Function, required: true },
  relColors: { type: Object, default: () => ({}) },
  selfNodeId: { type: String, default: null },
})
const emit = defineEmits(['nodeClick', 'nodeDblClick', 'bgClick'])

// ─── Constants ────────────────────────────────────────────────
// 노드 타입별 [중심(밝음), 외곽(진함)] 라디얼 그라데이션 색.
// 중심은 너무 희지 않게(흰 배경서도 보이게), 외곽은 채도 높게(어두운 배경서도 또렷하게) — 주간/야간 공통.
const NODE_GRADIENTS = {
  Meetings: [0x60a5fa, 0x2563eb], // 파랑
  company: [0x5eead4, 0x0d9488], // 청록
  dept: [0xc4b5fd, 0x7c3aed], // 보라
  agenda: [0xfcd34d, 0xd97706], // 앰버
  session: [0xfdba74, 0xea580c], // 주황
  minutes: [0x67e8f9, 0x0891b2], // 시안
  report: [0x6ee7b7, 0x059669], // 에메랄드
  person: [0xf9a8d4, 0xdb2777], // 핑크
}
// 외곽(진한) 색 — 단색 fallback·기타 참조용
const NODE_COLORS = {
  Meetings: 0x2563eb,
  agenda: 0xd97706,
  session: 0xea580c,
  minutes: 0x0891b2,
  report: 0x059669,
  dept: 0x7c3aed,
  person: 0xdb2777,
  company: 0x0d9488,
}

// 라디얼 그라데이션 캐시 — textureSpace:'local'이라 같은 색 조합은 모든 노드가 재사용.
const _gradientCache = new Map()
function _lighten(hex, amt = 0.45) {
  const r = (hex >> 16) & 0xff,
    g = (hex >> 8) & 0xff,
    b = hex & 0xff
  return (
    (Math.round(r + (255 - r) * amt) << 16) |
    (Math.round(g + (255 - g) * amt) << 8) |
    Math.round(b + (255 - b) * amt)
  )
}
// 라디얼 그라데이션 생성(실패 시 null → 호출부가 단색 폴백). 살짝 위쪽 광원으로 입체감.
function getNodeGradient(centerHex, edgeHex) {
  const key = centerHex * 0x1000000 + edgeHex
  if (_gradientCache.has(key)) return _gradientCache.get(key)
  let grad
  try {
    grad = new PIXI.FillGradient({
      type: 'radial',
      center: { x: 0.5, y: 0.38 },
      innerRadius: 0,
      outerCenter: { x: 0.5, y: 0.5 },
      outerRadius: 0.55,
      colorStops: [
        { offset: 0, color: centerHex },
        { offset: 1, color: edgeHex },
      ],
      textureSpace: 'local',
    })
  } catch {
    grad = null
  }
  _gradientCache.set(key, grad)
  return grad
}
const NODE_RADIUS = {
  Meetings: 10,
  agenda: 10,
  session: 10,
  minutes: 10,
  report: 10,
  dept: 10,
  person: 10,
  company: 10,
}
const BACKLINK_STEP = 2.4 // 백링크 1개당 가중치
const BACKLINK_MAX = 50 // 최대 추가 반경
const SELF_RADIUS = 10 // "나" 노드 고정 반경
const BOUNDS_SCALE = 5

// ─── Refs ─────────────────────────────────────────────────────
const containerRef = ref(null)
const panOnly = ref(false) // 이동 전용 모드 (노드 클릭/드래그 비활성, 배경 팬만)
let app = null // PIXI.Application
let edgeLayer = null // PIXI.Graphics (all edges)
let nodeContainer = null // PIXI.Container (node sprites)
let labelContainer = null // PIXI.Container (text labels)
let hlLayer = null // PIXI.Graphics (highlight rings)
let boundsLayer = null // PIXI.Graphics (노드가 너무 멀리 못 가게 가두는 사각 경계 — 투명 테두리)

// 노드 이탈 방지용 사각 경계 (화면 배수, 화면 중앙 기준). buildSimulation/resize에서 갱신.
let _bounds = null
function _computeBounds() {
  const w = app.screen.width,
    h = app.screen.height
  const halfW = (w * BOUNDS_SCALE) / 2,
    halfH = (h * BOUNDS_SCALE) / 2
  return {
    cx: w / 2,
    cy: h / 2,
    minX: w / 2 - halfW,
    maxX: w / 2 + halfW,
    minY: h / 2 - halfH,
    maxY: h / 2 + halfH,
  }
}
// d3-force 커스텀 force: 매 tick마다 노드를 경계 안으로 클램프(벽에 부딪히면 속도 반사로 감속)
function boundsForce() {
  if (!_bounds) return
  const pad = 10
  for (const n of simNodes) {
    if (n.fx != null || n.fy != null) continue // 드래그 고정 노드는 건드리지 않음
    if (n.x < _bounds.minX + pad) {
      n.x = _bounds.minX + pad
      if (n.vx < 0) n.vx *= -0.4
    } else if (n.x > _bounds.maxX - pad) {
      n.x = _bounds.maxX - pad
      if (n.vx > 0) n.vx *= -0.4
    }
    if (n.y < _bounds.minY + pad) {
      n.y = _bounds.minY + pad
      if (n.vy < 0) n.vy *= -0.4
    } else if (n.y > _bounds.maxY - pad) {
      n.y = _bounds.maxY - pad
      if (n.vy > 0) n.vy *= -0.4
    }
  }
}
// 경계 박스를 월드좌표(시뮬레이션 좌표)로 그린다 — 채움은 투명, 은은한 테두리만.
function _drawBoundsBox() {
  if (!boundsLayer || !_bounds) return
  boundsLayer.clear()
  const { minX, minY, maxX, maxY } = _bounds
  boundsLayer.roundRect(minX, minY, maxX - minX, maxY - minY, 28).stroke({
    color: props.nightMode ? 0xffffff : 0x64748b,
    width: 2,
    alpha: props.nightMode ? 0.16 : 0.22,
  })
}

// node display objects: Map<nodeIdx, { gfx: PIXI.Graphics, label: PIXI.Text, data: node }>
let nodeObjs = new Map()

let sim = null
let simNodes = [] // { index, x, y, vx, vy, id, type, ... }
let simEdges = [] // { source, target, rel }

// 노드 idx → inbound(백링크) 개수
let inboundCount = new Map()

// pan/zoom state
let vpX = 0,
  vpY = 0,
  vpScale = 1
let isPanning = false,
  panStartX = 0,
  panStartY = 0,
  panOrigX = 0,
  panOrigY = 0

// dirty flag — sim이 움직이거나 인터랙션이 발생했을 때만 리드로우
let _simDirty = true

// rainbow highlight state
const _RAINBOW_STOPS = [
  [147, 197, 253],
  [167, 139, 250],
  [244, 114, 182],
  [251, 191, 36],
  [52, 211, 153],
  [96, 165, 250],
]
let _hlPhase = 0
let _hlActive = false

function _rainbowHex(phase) {
  const n = _RAINBOW_STOPS.length
  const pos = (((phase % 1) + 1) % 1) * n
  const i = Math.floor(pos) % n
  const f = pos - Math.floor(pos)
  const [r1, g1, b1] = _RAINBOW_STOPS[i]
  const [r2, g2, b2] = _RAINBOW_STOPS[(i + 1) % n]
  return (
    (Math.round(r1 + (r2 - r1) * f) << 16) |
    (Math.round(g1 + (g2 - g1) * f) << 8) |
    Math.round(b1 + (b2 - b1) * f)
  )
}

// node drag state
let _draggingIdx = null
let _didNodeDrag = false

// smooth lerp target for search focus animation
let _targetVpX = null,
  _targetVpY = null,
  _targetVpScale = null

let focusedIdx = null

let ro = null

// ─── PIXI init ───────────────────────────────────────────────
async function initPixi() {
  if (app) destroyPixi()
  const el = containerRef.value
  if (!el) return

  // 컨테이너 크기가 아직 0이면 다음 프레임까지 대기 (v-if 렌더 직후 레이아웃 미계산 방지)
  if (el.offsetWidth === 0 || el.offsetHeight === 0) {
    await new Promise(r => requestAnimationFrame(r))
    if (!containerRef.value) return // unmounted 방지
  }

  app = new PIXI.Application()
  await app.init({
    width: el.offsetWidth || 800,
    height: el.offsetHeight || 600,
    backgroundAlpha: 0,
    antialias: true,
    resolution: window.devicePixelRatio || 1,
    autoDensity: true,
  })
  el.appendChild(app.canvas)
  app.canvas.style.width = '100%'
  app.canvas.style.height = '100%'

  // Layers
  boundsLayer = new PIXI.Graphics() // 맨 아래 — 노드 경계 박스(투명 테두리)
  app.stage.addChild(boundsLayer)
  hlLayer = new PIXI.Graphics()
  app.stage.addChild(hlLayer)
  edgeLayer = new PIXI.Graphics()
  app.stage.addChild(edgeLayer)
  nodeContainer = new PIXI.Container()
  app.stage.addChild(nodeContainer)
  labelContainer = new PIXI.Container()
  app.stage.addChild(labelContainer)

  // Interaction
  app.stage.eventMode = 'static'
  app.stage.hitArea = new PIXI.Rectangle(0, 0, app.screen.width, app.screen.height)
  app.stage.on('pointerdown', onBgDown)
  app.stage.on('pointermove', onBgMove)
  app.stage.on('pointerup', onBgUp)
  app.stage.on('pointerupoutside', onBgUp)
  app.canvas.addEventListener('wheel', onWheel, { passive: false })

  ro = new ResizeObserver(() => resizePixi())
  ro.observe(el)

  app.ticker.add(tick)

  // 노드는 즉시 렌더하고, 아이콘 텍스처는 백그라운드로 로드해 준비되면 부착한다.
  // (아이콘 로드 실패/지연이 노드 렌더를 막지 않도록 분리 — await로 묶지 않는다.)
  buildSimulation()
  preloadIconTextures()
    .then(() => {
      if (containerRef.value) attachMissingIcons()
    })
    .catch(() => {})
}

function resizePixi() {
  const el = containerRef.value
  if (!el || !app) return
  const w = el.offsetWidth,
    h = el.offsetHeight
  app.renderer.resize(w, h)
  app.stage.hitArea = new PIXI.Rectangle(0, 0, w, h)
  // 화면 크기 바뀌면 경계 박스도 재계산·재드로잉
  if (_bounds) {
    _bounds = _computeBounds()
    _drawBoundsBox()
  }
}

function destroyPixi() {
  if (sim) {
    sim.stop()
    sim = null
  }
  if (ro) {
    ro.disconnect()
    ro = null
  }
  if (app) {
    app.ticker.remove(tick)
    app.canvas?.removeEventListener('wheel', onWheel)
    app.destroy(true, { children: true })
    app = null
  }
  nodeObjs.clear()
  edgeLayer = nodeContainer = labelContainer = hlLayer = boundsLayer = null
  _bounds = null
}

// ─── Simulation ───────────────────────────────────────────────
function buildSimulation(nodes, edges) {
  if (!app) return
  const w = app.screen.width,
    h = app.screen.height
  const ns = nodes ?? props.gNodes
  const es = edges ?? props.gEdges

  // node.id 기준으로 위치 보존 — 인덱스가 바뀌어도 같은 노드는 제자리 유지
  const prevPosById = new Map(simNodes.map(n => [n.id, { x: n.x, y: n.y }]))
  const hasNewNodes = ns.some(n => !prevPosById.has(n.id))
  const isFirstLoad = prevPosById.size === 0

  simNodes = ns.map((n, i) => {
    const prev = prevPosById.get(n.id)
    return {
      _idx: i,
      id: n.id,
      type: n.type,
      ended: n.ended ?? false,
      x: prev?.x ?? w / 2 + (Math.random() - 0.5) * 200,
      y: prev?.y ?? h / 2 + (Math.random() - 0.5) * 200,
      vx: 0,
      vy: 0,
    }
  })

  simEdges = es.map(e => ({
    source: e.from,
    target: e.to,
    rel: e.rel,
  }))

  // inbound(백링크) 개수 집계 — target으로 들어오는 엣지 수
  inboundCount = new Map()
  for (const e of es) {
    inboundCount.set(e.to, (inboundCount.get(e.to) || 0) + 1)
  }

  if (sim) sim.stop()

  // alpha 전략:
  //   최초 로딩       → 1.0 (풀 레이아웃)
  //   새 노드 추가    → 0.3 (신규 노드만 자리 잡도록 살짝)
  //   단순 데이터 갱신 → 0   (노드 이동 없음)
  const startAlpha = isFirstLoad ? 1 : hasNewNodes ? 0.3 : 0.15

  _bounds = _computeBounds() // 화면 1.5배 사각 경계 (노드 이탈 방지)

  sim = forceSimulation(simNodes)
    .force(
      'link',
      forceLink(simEdges)
        .id(d => d._idx)
        .distance(5) // 연결된 노드 간 목표 거리 ↑ = 더 퍼짐
        .strength(0.125), // 링크가 거리를 당기는 강도
    )
    .force('charge', forceManyBody().strength(-160)) // 노드 간 반발력 (음수↑ = 더 멀어짐)
    .force('center', forceCenter(w / 2, h / 2).strength(0.16)) // 중앙으로 모으는 힘
    .force('collide', forceCollide(d => nodeRadiusForIdx(d._idx, d.type, d.id) + 7).strength(0.85)) // 충돌 반경(겹침 방지 여백 +14)
    .force('bounds', boundsForce) // 사각 경계 밖으로 못 나가게 클램프
    .alphaDecay(0.025) // 작을수록 천천히 안정(레이아웃 더 풀림)
    .alpha(startAlpha) // 초기 에너지 (최초 1.0 / 노드추가 0.3 / 갱신 0)
    .on('tick', () => {
      _simDirty = true
    })

  _drawBoundsBox()
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

  // node.id → 기존 obj 매핑 (재사용 판단용)
  const existingByNodeId = new Map()
  nodeObjs.forEach(obj => existingByNodeId.set(obj.node.id, obj))

  const newNodeObjs = new Map()
  const newNodeIdSet = new Set(props.gNodes.map(n => n.id))

  props.gNodes.forEach((n, i) => {
    const type = n.type
    const r = nodeRadiusForIdx(i, type, n.id)
    const existing = existingByNodeId.get(n.id)

    if (existing) {
      // 기존 PIXI 객체 재사용 — 인덱스·핸들러만 갱신
      existing.node = n
      // 타입이 바뀌었거나(드문 경우), 텍스처 프리로드 전 생성돼 아이콘이 빠졌으면 부착/교체
      if (existing.type !== type || (!existing.icon && ICON_TEX[type])) {
        if (existing.icon) {
          existing.gfx.removeChild(existing.icon)
          existing.icon.destroy()
        }
        existing.icon = createIcon(existing.gfx, type)
        if (existing.icon) existing.icon.width = existing.icon.height = r * ICON_FIT
      }
      existing.type = type
      existing.r = r
      existing._drawSig = null // 재빌드 시 데이터/색/반경 변경 반영 위해 다음 틱 재드로잉 강제
      existing.gfx._nodeIdx = i
      existing.gfx.hitArea = new PIXI.Circle(0, 0, r + 4)
      existing.gfx.removeAllListeners()
      existing.gfx.on('pointerdown', e => {
        e.stopPropagation()
        onNodeDown(i, e)
      })
      existing.gfx.on('pointerup', e => {
        e.stopPropagation()
        onNodeUp(i)
      })
      existing.gfx.on('pointerover', () => {
        onNodeOver(i)
      })
      existing.gfx.on('pointerout', () => {
        onNodeOut(i)
      })
      const newText = (n.label || '').slice(0, 9)
      if (existing.label.text !== newText) existing.label.text = newText
      newNodeObjs.set(i, existing)
    } else {
      // 새 노드 — PIXI 객체 신규 생성
      const gfx = new PIXI.Graphics()
      gfx.eventMode = 'static'
      gfx.cursor = 'pointer'
      gfx.hitArea = new PIXI.Circle(0, 0, r + 4)
      gfx._nodeIdx = i
      gfx.on('pointerdown', e => {
        e.stopPropagation()
        onNodeDown(i, e)
      })
      gfx.on('pointerup', e => {
        e.stopPropagation()
        onNodeUp(i)
      })
      gfx.on('pointerover', () => {
        onNodeOver(i)
      })
      gfx.on('pointerout', () => {
        onNodeOut(i)
      })
      nodeContainer.addChild(gfx)

      const label = new PIXI.Text({
        text: (n.label || '').length > 10 ? (n.label || '').slice(0, 10) + '…' : n.label || '',
        style: {
          fontSize: 10,
          fontFamily: 'sans-serif',
          fontWeight: 'normal',
          fill: props.nightMode ? 0xe2e8f0 : 0x0f172a,
          align: 'center',
        },
        resolution: (window.devicePixelRatio || 1) * 3,
      })
      label.anchor.set(0.5, 0)
      label.eventMode = 'none'
      labelContainer.addChild(label)

      const icon = createIcon(gfx, type)
      if (icon) icon.width = icon.height = r * ICON_FIT // 첫 드로잉 전 초기 크기

      newNodeObjs.set(i, { gfx, label, icon, node: n, type, r, hovered: false, focused: false })
    }
  })

  // 사라진 노드 정리
  existingByNodeId.forEach((obj, nodeId) => {
    if (!newNodeIdSet.has(nodeId)) {
      nodeContainer.removeChild(obj.gfx)
      labelContainer.removeChild(obj.label)
      // children:true 로 아이콘 Sprite 자식까지 파괴(공유 텍스처 ICON_TEX는 보존 — texture 옵션 false 기본)
      obj.gfx.destroy({ children: true })
      obj.label.destroy()
    }
  })

  nodeObjs = newNodeObjs
  _simDirty = true
}

function drawNode(obj, sn) {
  const { gfx, node, type } = obj
  const isDark = props.nightMode
  const isFocus = focusedIdx === sn._idx
  const isHl = props.queryHlIdxs?.has(sn._idx)
  const isSearch = props.searchHitMgIdxs?.includes(sn._idx)
  const isSelf = props.selfNodeId != null && node.id === props.selfNodeId
  const r = isSelf ? obj.r + 3 : obj.r
  const urgency = type === 'Meetings' ? props.computeUrgency(node.data) : null
  const hubColor =
    type === 'Meetings' ? hexToNum(props.getHubFill(node.data)) : (NODE_COLORS[type] ?? 0x3b82f6)

  gfx.clear()

  if (isSearch) {
    gfx.circle(0, 0, r + 6)
    gfx.stroke({ color: 0xfbbf24, width: 3, alpha: 1 })
  }

  // Main circle — 라디얼 그라데이션(중심 밝음 → 외곽 진함). 실패 시 단색 폴백.
  gfx.circle(0, 0, r)
  if (type === 'Meetings') {
    // 회의체는 긴급도 색(hubColor) 유지 — 밝게 한 중심 → hubColor 그라데이션
    const grad = getNodeGradient(_lighten(hubColor, 0.5), hubColor)
    gfx.fill(grad || { color: hubColor, alpha: urgency === 'critical' ? 0.95 : 0.88 })
  } else {
    const g = NODE_GRADIENTS[type]
    const grad = g ? getNodeGradient(g[0], g[1]) : null
    gfx.fill(grad || { color: (g && g[1]) || NODE_COLORS[type] || 0x60a5fa, alpha: 1 })
  }

  // 자신 노드 — 검정 테두리로 구분
  if (isSelf && !isFocus && !obj.focused && !obj.hovered) {
    gfx.circle(0, 0, r)
    gfx.stroke({ color: isDark ? 0x0f172a : 0x0f172a, width: 2.5, alpha: 0.9 })
  }

  // Rainbow highlight border (takes priority over focus/hover)
  if (isHl && _hlActive) {
    gfx.circle(0, 0, r)
    gfx.stroke({ color: _rainbowHex(_hlPhase), width: 2.5, alpha: 0.95 })
  } else if (isFocus || obj.focused) {
    gfx.circle(0, 0, r)
    gfx.stroke({ color: isDark ? 0xffffff : 0x1e293b, width: 2.5, alpha: 1 })
  } else if (obj.hovered) {
    gfx.circle(0, 0, r)
    gfx.stroke({ color: isDark ? 0xffffff : 0x1e293b, width: 3, alpha: 0.85 })
  }

  // 아이콘은 노드 gfx의 자식(obj.icon) Sprite로 분리돼 있어 여기서 그리지 않는다.
  // 크기만 현재 반경에 맞춰 갱신한다. (정의: graph/nodeIcons.js SSOT)
  if (obj.icon) obj.icon.width = obj.icon.height = r * ICON_FIT
}

// 아이콘은 graph/nodeIcons.js(SSOT)의 SVG를 "브라우저로 래스터화한 텍스처"로 노드별 Sprite에 붙인다.
// ★ PIXI v8의 GraphicsContext.svg() 파서는 타원 arc(a/A) 커맨드에서 깨진 geometry를 만들어
//   렌더 시점에 throw → 렌더 루프 전체가 죽는다. 따라서 파서를 쓰지 않고 브라우저 래스터화를 쓴다.
const ICON_FIT = 1 // 아이콘 지름 = 노드 반경 r 의 배수(튜닝 값)
const ICON_TEX = {} // type → PIXI.Texture | null
let _iconsReady = false

/** 8개 타입 아이콘 SVG를 data URL → 텍스처로 1회 프리로드(브라우저 래스터화). */
async function preloadIconTextures() {
  if (_iconsReady) return
  await Promise.all(
    Object.keys(NODE_ICON_PATHS).map(async type => {
      // 64px로 래스터화(고해상) — Sprite에서 r 크기에 맞춰 축소
      const svg = nodeIconSvg(type, '#ffffff', 2).replace('<svg ', '<svg width="64" height="64" ')
      const url = 'data:image/svg+xml;charset=utf8,' + encodeURIComponent(svg)
      try {
        ICON_TEX[type] = await PIXI.Assets.load({
          src: url,
          data: { parseAsGraphicsContext: false }, // GraphicsContext 파서 금지 → 텍스처로 래스터화
        })
      } catch {
        ICON_TEX[type] = null
      }
    }),
  )
  _iconsReady = true
}

/** 노드 gfx에 타입별 아이콘 Sprite 자식을 부착하고 반환(텍스처 없으면 null). */
function createIcon(gfx, type) {
  const tex = ICON_TEX[type]
  if (!tex) return null
  const icon = new PIXI.Sprite(tex)
  icon.eventMode = 'none' // 클릭/호버는 부모 gfx가 처리
  icon.anchor.set(0.5) // 노드 원점 중심 정렬

  gfx.addChild(icon) // gfx.clear()는 자식을 지우지 않음 → 원 재드로잉에도 보존
  return icon
}

/** 텍스처 로드 완료 후, 아이콘이 빠진 기존 노드에 부착(시뮬레이션 재빌드 없이). */
function attachMissingIcons() {
  nodeObjs.forEach(obj => {
    if (!obj.icon && ICON_TEX[obj.type]) {
      obj.icon = createIcon(obj.gfx, obj.type)
      if (obj.icon) obj.icon.width = obj.icon.height = obj.r * ICON_FIT
    }
  })
  _simDirty = true // 다음 틱에 리드로우
}

// ─── Tick / Render ───────────────────────────────────────────
function tick() {
  if (!app || !sim) return

  // viewport lerp 진행 중이면 dirty
  if (_targetVpX !== null) _simDirty = true

  // rainbow highlight 진행 중이면 phase 업데이트 + dirty 유지
  if (_hlActive) {
    _hlPhase = (_hlPhase + 0.005) % 1
    _simDirty = true
  }

  // 리드로우가 필요 없으면 skip
  if (!_simDirty) return
  _simDirty = false

  // Lerp viewport toward search focus target
  if (_targetVpX !== null) {
    vpX += (_targetVpX - vpX) * 0.1
    vpY += (_targetVpY - vpY) * 0.1
    vpScale += (_targetVpScale - vpScale) * 0.1
    if (
      Math.abs(vpX - _targetVpX) < 0.5 &&
      Math.abs(vpY - _targetVpY) < 0.5 &&
      Math.abs(vpScale - _targetVpScale) < 0.001
    ) {
      vpX = _targetVpX
      vpY = _targetVpY
      vpScale = _targetVpScale
      _targetVpX = null
      _targetVpY = null
      _targetVpScale = null
    }
  }

  const w = app.screen.width,
    h = app.screen.height

  for (const layer of [boundsLayer, edgeLayer, nodeContainer, labelContainer, hlLayer]) {
    layer.x = vpX
    layer.y = vpY
    layer.scale.set(vpScale)
  }
  // stage hitArea는 항상 스크린 좌표 — 월드 좌표로 변환하면 고배율 시 클릭 무효 버그 발생
  app.stage.hitArea = new PIXI.Rectangle(0, 0, w, h)

  // ── Draw edges ────────────────────────────────────────────
  edgeLayer.clear()
  hlLayer.clear()

  const hidSet = new Set(props.hiddenNodeTypes)
  const isHidden = i => {
    const n = props.gNodes[i]
    if (!n) return false
    return hidSet.has(n.type)
  }

  simEdges.forEach((e, ei) => {
    const si = typeof e.source === 'object' ? e.source._idx : e.source
    const ti = typeof e.target === 'object' ? e.target._idx : e.target
    if (isHidden(si) || isHidden(ti)) return
    const sn = simNodes[si],
      tn = simNodes[ti]
    if (!sn || !tn) return

    // 뷰포트 컬링 — 양 끝 노드가 모두 화면(여백 100px) 밖이면 그리지 않는다(줌인 시 큰 절감).
    const ssx = sn.x * vpScale + vpX,
      ssy = sn.y * vpScale + vpY
    const tsx = tn.x * vpScale + vpX,
      tsy = tn.y * vpScale + vpY
    const M = 100
    const sOff = ssx < -M || ssx > w + M || ssy < -M || ssy > h + M
    const tOff = tsx < -M || tsx > w + M || tsy < -M || tsy > h + M
    if (sOff && tOff) return

    const relColor = hexToNum(props.relColors[e.rel] || '#60a5fa')
    const isHlEdge = props.queryHlEdgeIdxs?.has(ei)
    const isFocEdge = focusedIdx !== null && (si === focusedIdx || ti === focusedIdx)
    const endedEdge = props.gNodes[si]?.ended || props.gNodes[ti]?.ended

    const alpha =
      (focusedIdx !== null ? (isFocEdge ? 0.85 : 0.12) : 0.35) * (endedEdge ? 0.45 : 1.0)

    const dx = tn.x - sn.x,
      dy = tn.y - sn.y
    const len = Math.sqrt(dx * dx + dy * dy)
    if (len < 4) return
    const ux = dx / len,
      uy = dy / len
    // 노드 반경은 동기화 시 계산된 obj.r를 재사용(프레임마다 nodeRadiusForIdx 재계산 회피)
    const tr = (nodeObjs.get(ti)?.r ?? nodeRadiusForIdx(ti, tn.type, props.gNodes[ti]?.id)) + 4
    const ex = tn.x - ux * tr,
      ey = tn.y - uy * tr

    const sr =
      (nodeObjs.get(si)?.r ??
        nodeRadiusForIdx(si, props.gNodes[si]?.type ?? 'minutes', props.gNodes[si]?.id)) + 3
    const sx2 = sn.x + ux * sr,
      sy2 = sn.y + uy * sr

    const isHlOn = isHlEdge && _hlActive
    const edgeColor = isHlOn ? _rainbowHex(_hlPhase) : relColor
    const finalAlpha = isHlOn && focusedIdx === null ? 0.9 : alpha
    edgeLayer.moveTo(sx2, sy2).lineTo(ex, ey)
    edgeLayer.stroke({
      color: edgeColor,
      width: isFocEdge || isHlOn ? 2.2 : 0.9,
      alpha: finalAlpha,
    })

    const as = 7
    const px2 = -uy * as * 0.44,
      py2 = ux * as * 0.44
    edgeLayer.poly([
      ex,
      ey,
      ex - ux * as + px2,
      ey - uy * as + py2,
      ex - ux * as - px2,
      ey - uy * as - py2,
    ])
    edgeLayer.fill({ color: edgeColor, alpha: finalAlpha })
  })

  // ── Draw nodes ───────────────────────────────────────────
  // focus 시 이웃 집합을 프레임당 1회만 계산한다. (기존: 노드마다 isNeighbor가 전체 엣지를
  // 스캔해 O(노드수 × 엣지수) — 포커스/검색 중 viewport 애니메이션이 도는 동안 매 프레임
  // 발생해 rAF 핸들러가 100ms+ 걸리는 원인이었다.)
  let _neighborSet = null
  if (focusedIdx !== null) {
    _neighborSet = new Set()
    for (const e of simEdges) {
      const si = typeof e.source === 'object' ? e.source._idx : e.source
      const ti = typeof e.target === 'object' ? e.target._idx : e.target
      if (si === focusedIdx) _neighborSet.add(ti)
      else if (ti === focusedIdx) _neighborSet.add(si)
    }
  }

  simNodes.forEach((sn, i) => {
    const obj = nodeObjs.get(i)
    if (!obj) return
    const hidden = hidSet.has(sn.type)
    obj.gfx.visible = !hidden
    obj.label.visible = !hidden

    if (hidden) return

    // 뷰포트 컬링 — 화면(여백 60px) 밖 노드는 숨기고 재드로잉/페이드 계산을 건너뛴다.
    const nsx = sn.x * vpScale + vpX,
      nsy = sn.y * vpScale + vpY
    const Mn = 60
    if (nsx < -Mn || nsx > w + Mn || nsy < -Mn || nsy > h + Mn) {
      obj.gfx.visible = false
      obj.label.visible = false
      return
    }

    obj.gfx.x = sn.x
    obj.gfx.y = sn.y
    obj.label.x = sn.x
    obj.label.y = sn.y + obj.r + 3

    const hasSearchHits = props.searchHitMgIdxs?.length > 0
    const alphaVal =
      focusedIdx !== null
        ? i === focusedIdx || _neighborSet.has(i)
          ? 1.0
          : 0.2
        : hasSearchHits
          ? props.searchHitMgIdxs.includes(i)
            ? 1.0
            : 0.15
          : 1.0
    const endedDim = sn.ended ? 0.45 : 1.0
    obj.gfx.alpha = alphaVal * endedDim
    obj.label.alpha = alphaVal * endedDim * 0.9

    // Redraw — 모양에 영향을 주는 상태가 바뀐 노드만 다시 그린다. (위치는 gfx.x/y, 페이드는
    // gfx.alpha로 처리되므로 force 레이아웃 중에는 대부분 재드로잉이 불필요하다. 대형 그래프
    // 초기 로딩 시 매 프레임 전체 노드 재드로잉이 rAF 100ms+의 주원인이었다.)
    obj.focused = i === focusedIdx
    const hlAnim = _hlActive && props.queryHlIdxs?.has(i) ? _hlPhase.toFixed(2) : '0'
    const drawSig = `${obj.focused ? 1 : 0}|${obj.hovered ? 1 : 0}|${hlAnim}|${
      props.searchHitMgIdxs?.includes(i) ? 1 : 0
    }|${props.nightMode ? 1 : 0}`
    if (obj._drawSig !== drawSig) {
      obj._drawSig = drawSig
      drawNode(obj, sn)
    }

    obj.label.anchor.set(0.5, 0)
    // Update text resolution to match zoom for crisp text at any scale
    const targetRes = (window.devicePixelRatio || 1) * Math.max(2, Math.ceil(vpScale * 1.5))
    if (obj.label.resolution !== targetRes) obj.label.resolution = targetRes
  })
}

// ─── Interaction ─────────────────────────────────────────────
// PIXI v8 registers a global pointerup listener on globalThis for drag tracking.
// Without this flag, any DOM element click (e.g. sidebar tabs) fires onBgUp and
// emits 'bgClick', closing the sidebar unintentionally.
let _downX = 0,
  _downY = 0,
  _didMove = false
let _pointerDownOnCanvas = false
function onBgDown(e) {
  _pointerDownOnCanvas = true
  const p = e.global
  isPanning = true
  panStartX = p.x
  panStartY = p.y
  panOrigX = vpX
  panOrigY = vpY
  _downX = p.x
  _downY = p.y
  _didMove = false
}
function onBgMove(e) {
  const p = e.global
  if (_draggingIdx !== null) {
    if (Math.abs(p.x - _downX) + Math.abs(p.y - _downY) > 4) {
      if (!_didNodeDrag) sim?.alphaTarget(0.3).restart() // 실제 드래그 시작 시점에만 re-heat
      _didNodeDrag = true
      _targetVpX = null
      _targetVpY = null
      _targetVpScale = null
    }
    const wx = (p.x - vpX) / vpScale
    const wy = (p.y - vpY) / vpScale
    const sn = simNodes[_draggingIdx]
    if (sn) {
      sn.fx = wx
      sn.fy = wy
      sn.x = wx
      sn.y = wy
      _simDirty = true
    }
    return
  }
  if (!isPanning) return
  if (Math.abs(p.x - _downX) + Math.abs(p.y - _downY) > 4) {
    _didMove = true
    _targetVpX = null
    _targetVpY = null
    _targetVpScale = null
  }
  vpX = panOrigX + (p.x - panStartX)
  vpY = panOrigY + (p.y - panStartY)
  _simDirty = true
}
function onBgUp() {
  if (_draggingIdx !== null) {
    const sn = simNodes[_draggingIdx]
    if (sn) {
      sn.fx = null
      sn.fy = null
    }
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
  if (panOnly.value) {
    onBgDown(e)
    return
  }
  _nodeDownTime = Date.now()
  isPanning = false
  _draggingIdx = idx
  _didNodeDrag = false
  if (e?.global) {
    _downX = e.global.x
    _downY = e.global.y
  }
  const sn = simNodes[idx]
  if (sn) {
    sn.fx = sn.x
    sn.fy = sn.y
    // 클릭만으로 sim을 re-heat하지 않는다 — 실제 드래그가 시작될 때만 re-heat(onBgMove)한다.
    // (기존엔 pointerdown마다 alphaTarget(0.3)+restart라 단순 클릭에도 전체 노드가 움직였다.)
  }
}
function onNodeUp(idx) {
  if (panOnly.value) {
    onBgUp()
    return
  }
  const sn = simNodes[idx]
  if (_didNodeDrag) {
    if (sn) {
      sn.fx = null
      sn.fy = null
    }
    sim?.alphaTarget(0)
  } else if (Date.now() - _nodeDownTime < 300) {
    if (focusedIdx === idx) {
      focusedIdx = null
    } else {
      focusedIdx = idx
      if (sn) {
        sn.fx = sn.x
        sn.fy = sn.y
        setTimeout(() => {
          if (sn) {
            sn.fx = null
            sn.fy = null
          }
        }, 1200)
      }
    }
    _simDirty = true
    emit('nodeClick', props.gNodes[idx], idx)
  }
  _draggingIdx = null
  _didNodeDrag = false
}
function onNodeOver(idx) {
  const obj = nodeObjs.get(idx)
  if (obj) {
    obj.hovered = true
    _simDirty = true
  }
}
function onNodeOut(idx) {
  const obj = nodeObjs.get(idx)
  if (obj) {
    obj.hovered = false
    _simDirty = true
  }
}

function onWheel(e) {
  e.preventDefault()
  _targetVpX = null
  _targetVpY = null
  _targetVpScale = null
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
function zoomIn() {
  vpScale = Math.min(3, vpScale * 1.25)
  _simDirty = true
}
function zoomOut() {
  vpScale = Math.max(0.2, vpScale / 1.25)
  _simDirty = true
}
function resetView() {
  vpX = 0
  vpY = 0
  vpScale = 1
  focusedIdx = null
  _simDirty = true
}
/** 노드 선택(포커스) 해제 — 뷰포트는 유지. (예: 선택 노드 삭제 후) */
function clearFocus() {
  focusedIdx = null
  _simDirty = true
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
  const wx = (sx - rect.left - vpX) / vpScale
  const wy = (sy - rect.top - vpY) / vpScale
  let best = null,
    bestDist = Infinity
  for (const sn of simNodes) {
    const r = getRadius(sn.type) + 24
    const dx = sn.x - wx,
      dy = sn.y - wy
    const dist = Math.sqrt(dx * dx + dy * dy)
    if (dist < r && dist < bestDist) {
      best = sn
      bestDist = dist
    }
  }
  return best ? (props.gNodes[best._idx] ?? null) : null
}

/** gNode id → 뷰포트 기준 화면 좌표 {x, y} 반환 */
function getNodeScreenPos(nodeId) {
  if (!app || !containerRef.value) return null
  const sn = simNodes.find(n => props.gNodes[n._idx]?.id === nodeId)
  if (!sn) return null
  const rect = containerRef.value.getBoundingClientRect()
  return {
    x: rect.left + sn.x * vpScale + vpX,
    y: rect.top + sn.y * vpScale + vpY,
  }
}

/** 검색 히트 노드들이 중앙으로 부드럽게 이동하도록 뷰포트 애니메이션 설정 */
function focusSearchHits(hitIdxs) {
  if (!hitIdxs || hitIdxs.length === 0) {
    _targetVpX = null
    _targetVpY = null
    _targetVpScale = null
    return
  }
  if (!app) return
  const hitNodes = hitIdxs.map(i => simNodes[i]).filter(Boolean)
  if (!hitNodes.length) return

  const w = app.screen.width,
    h = app.screen.height

  if (hitNodes.length === 1) {
    const sn = hitNodes[0]
    const s = Math.min(2.0, Math.max(1.2, vpScale))
    _targetVpX = w / 2 - sn.x * s
    _targetVpY = h / 2 - sn.y * s
    _targetVpScale = s
  } else {
    let minX = Infinity,
      maxX = -Infinity,
      minY = Infinity,
      maxY = -Infinity
    for (const sn of hitNodes) {
      minX = Math.min(minX, sn.x)
      maxX = Math.max(maxX, sn.x)
      minY = Math.min(minY, sn.y)
      maxY = Math.max(maxY, sn.y)
    }
    const cx = (minX + maxX) / 2,
      cy = (minY + maxY) / 2
    const pad = 160
    const s = Math.max(
      0.3,
      Math.min(2.2, Math.min(w / (maxX - minX + pad), h / (maxY - minY + pad))),
    )
    _targetVpX = w / 2 - cx * s
    _targetVpY = h / 2 - cy * s
    _targetVpScale = s
  }
}

defineExpose({
  zoomIn,
  zoomOut,
  resetView,
  clearFocus,
  togglePanOnly,
  panOnly,
  reloadGraph: buildSimulation,
  getNodeAtScreen,
  getNodeScreenPos,
  focusSearchHits,
})

// ─── Helpers ─────────────────────────────────────────────────
function hexToNum(color) {
  if (!color) return 0x60a5fa
  const s = String(color).trim()
  // rgb()/rgba() 문자열도 허용 (rel-schema에 섞여 들어와도 캔버스가 죽지 않도록)
  const m = s.match(/rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)/i)
  if (m) return (+m[1] << 16) | (+m[2] << 8) | +m[3]
  const n = parseInt(s.replace('#', ''), 16)
  // 파싱 실패(NaN)는 PIXI stroke가 throw → 렌더 루프 전체 중단. 반드시 폴백.
  return Number.isNaN(n) ? 0x60a5fa : n
}

// ─── Watchers ─────────────────────────────────────────────────
watch([() => props.gNodes, () => props.gEdges], () => buildSimulation())
watch(
  () => props.queryHlIdxs,
  val => {
    _hlActive = val?.size > 0 || props.queryHlEdgeIdxs?.size > 0
    if (!_hlActive) _hlPhase = 0
    _simDirty = true
  },
)
watch(
  () => props.queryHlEdgeIdxs,
  val => {
    _hlActive = val?.size > 0 || props.queryHlIdxs?.size > 0
    if (!_hlActive) _hlPhase = 0
    _simDirty = true
  },
)
watch(
  () => props.nightMode,
  () => {
    // update label colors
    nodeObjs.forEach(obj => {
      obj.label.style.fill = props.nightMode ? 0xe2e8f0 : 0x0f172a
    })
    _drawBoundsBox() // 경계 박스 테두리 색도 모드에 맞게 갱신
    _simDirty = true // 야간/주간 전환 시 노드 색도 다시 그린다
  },
)
// 범례에서 노드 타입 표시/숨김 토글 시 그래프를 다시 그린다 — 시뮬레이션 안정 후
// tick이 _simDirty=false면 조기 반환해 재렌더가 멈추므로, 토글을 반영하려면 dirty 표시 필요.
watch(
  () => props.hiddenNodeTypes,
  () => {
    _simDirty = true
  },
  { deep: true },
)

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
