/**
 * 날짜 포맷 유틸 — 단일 정의.
 * 페이지마다 비슷한 formatDate를 재정의하지 말고 여기서 용도별 함수를 가져다 쓸 것.
 */

/** 'YYYY-MM-DD' (로컬 기준) */
export function fmtISO(d) {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

/** 마감일까지 남은 일수 (올림). null 입력 시 null */
export function getDday(due) {
  if (!due) return null
  return Math.ceil((new Date(due) - new Date()) / 86400000)
}

/** '6월 12일' — 홈 탭 목록용 */
export function formatDateShort(ds) {
  if (!ds) return ''
  return new Date(ds).toLocaleDateString('ko-KR', { month: 'short', day: 'numeric' })
}

/** '2026. 6월 12. 오후 10:30' (연도 포함) — 아카이브 이력용 */
export function formatDateTimeFull(d) {
  if (!d) return '-'
  return new Date(d).toLocaleString('ko-KR', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

/** '6월 12일 오후 10:30' (연도 없음) — 세션 목록용 */
export function formatDateTimeShort(d, fallback = '-') {
  if (!d) return fallback
  return new Date(d).toLocaleString('ko-KR', {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

/** '2026년 6월 12일' — 날짜만. 'YYYY-MM-DD' 문자열은 KST 오전 9시로 해석해 UTC 밀림 방지 */
export function formatDateLong(d) {
  if (!d) return '-'
  const dt = new Date(typeof d === 'string' && d.length <= 10 ? d + 'T09:00:00' : d)
  return dt.toLocaleDateString('ko-KR', { year: 'numeric', month: 'long', day: 'numeric' })
}
