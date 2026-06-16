// 노드 유형별 아이콘 단일 정의(SSOT).
// - 템플릿: NodeIcon.vue 가 NODE_ICON_PATHS 를 currentColor 로 그린다.
// - PIXI(GraphView): nodeIconSvg(type) 문자열을 GraphicsContext().svg() 로 그린다.
// 색은 소비자가 입힌다(템플릿=currentColor, PIXI=명시 색) → 여기엔 path 마크업만 둔다.
// 모든 아이콘 viewBox 0 0 24 24, stroke 기반(fill=none).

export const NODE_ICON_PATHS = {
  // 부서 — 두 사람
  dept:
    '<path d="M17 21v-2a4 4 0 00-4-4H5a4 4 0 00-4 4v2"/><circle cx="9" cy="7" r="4"/>' +
    '<path d="M23 21v-2a4 4 0 00-3-3.87M16 3.13a4 4 0 010 7.75"/>',
  // 회사 — 빌딩
  company:
    '<rect x="4" y="2" width="16" height="20" rx="1"/><path d="M9 22v-4h6v4"/>' +
    '<path d="M8 6h.01M12 6h.01M16 6h.01M8 10h.01M12 10h.01M16 10h.01M8 14h.01M12 14h.01M16 14h.01"/>',
  // 아젠다 — 체크 클립보드
  agenda:
    '<path d="M9 11l3 3L22 4"/>' +
    '<path d="M21 12v7a2 2 0 01-2 2H5a2 2 0 01-2-2V5a2 2 0 012-2h11"/>',
  // 세션(회의) — 마이크
  session:
    '<path d="M12 1a3 3 0 00-3 3v8a3 3 0 006 0V4a3 3 0 00-3-3z"/>' +
    '<path d="M19 10v2a7 7 0 01-14 0v-2M12 19v4M8 23h8"/>',
  // 회의록 — 문서
  minutes: '<path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/><polyline points="14 2 14 8 20 8"/>',
  // 보고자료 — 줄 있는 문서
  report:
    '<path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/><polyline points="14 2 14 8 20 8"/>' +
    '<line x1="8" y1="13" x2="16" y2="13"/><line x1="8" y1="17" x2="16" y2="17"/>',
  // 사람
  person: '<path d="M20 21v-2a4 4 0 00-4-4H8a4 4 0 00-4 4v2"/><circle cx="12" cy="7" r="4"/>',
  // 회의체 — 허브(중앙 + 3노드)
  Meetings:
    // 허브: 중심 + 바깥 3노드. 연결선은 원 '가장자리'에서 끝나 원 내부를 통과하지 않음.
    '<circle cx="12" cy="5" r="2"/><circle cx="12" cy="12" r="2"/><circle cx="5" cy="17" r="2"/><circle cx="19" cy="17" r="2"/>' +
    '<line x1="12" y1="7" x2="12" y2="10"/><line x1="12" y1="14" x2="17.4" y2="15.6"/><line x1="12" y1="14" x2="6.6" y2="15.6"/>',
}

// 알 수 없는 타입의 폴백 아이콘 키
export const DEFAULT_ICON = 'person'

/** PIXI GraphicsContext().svg() 용 완전한 SVG 문자열 (stroke 색 명시 — PIXI는 currentColor 못 풂). */
export function nodeIconSvg(type, stroke = '#ffffff', strokeWidth = 2) {
  const inner = NODE_ICON_PATHS[type]
  if (!inner) return null
  // xmlns 필수 — data URL 이미지로 래스터화하려면 SVG 네임스페이스가 있어야 브라우저가 디코드한다.
  return (
    `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" ` +
    `stroke="${stroke}" stroke-width="${strokeWidth}" ` +
    `stroke-linecap="round" stroke-linejoin="round">${inner}</svg>`
  )
}
