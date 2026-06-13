/**
 * 아바타 색상/이니셜 유틸 — 단일 정의.
 * 색상 배열이 파일마다 달라지면 같은 사람이 화면마다 다른 색으로 보이므로 여기서만 관리한다.
 */
export const AVATAR_COLORS = [
  '#6366f1',
  '#3b82f6',
  '#10b981',
  '#f59e0b',
  '#ef4444',
  '#8b5cf6',
  '#ec4899',
  '#14b8a6',
]

/** 이름 기반 안정 색상 (같은 이름 → 항상 같은 색) */
export function avatarColor(name) {
  let h = 0
  for (const c of name || '') h = (h * 31 + c.charCodeAt(0)) % AVATAR_COLORS.length
  return AVATAR_COLORS[h]
}

/** 첫 글자 이니셜 */
export function initials(name) {
  return (name || '?')[0]
}
