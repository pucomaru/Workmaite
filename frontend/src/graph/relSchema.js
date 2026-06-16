import { reactive } from 'vue'
import { apiAI } from '../api'

/**
 * 그래프 관계 스키마 — 백엔드 rel_schema.py(SSOT)의 프런트 사본.
 * 번들 기본값은 백엔드 canonical과 동일하게 유지하고, 마운트 시 GET /api/neo4j/rel-schema로 병합한다.
 * (번들 기본값이 있어 첫 페인트·오프라인에서도 색상/추론이 동작한다.)
 *
 * 관계명 추가·변경은 반드시 backend/fastapi/rel_schema.py에서 시작할 것.
 */

// 관계명 → 색상 (그래프 엣지·배지 공용)
export const REL_COLORS = reactive({
  포함: '#0d9488',
  소속: '#a78bfa',
  소속회사: '#a78bfa',
  운영: '#1e3a5f',
  참여: '#60a5fa',
  참석: '#93c5fd',
  협의: '#60a5fa',
  담당: '#34d399',
  담당부서: '#a78bfa', // agenda→dept (안건 담당 부서)
  추출: '#fbbf24', // Meetings→agenda (회의체가 추출한 안건)
  관련: '#fcd34d',
  논의: '#ea580c',
  도출: '#d97706', // minutes→agenda
  기록: '#0891b2',
  작성: '#c4b5fd', // dept→report (부서가 작성한 보고자료)
  후속: '#ea580c',
  첨부: '#60a5fa', // report→Meetings (보고자료 첨부)
  취급: '#f472b6', // report→agenda (보고자료가 다루는 안건)
  참조: '#7a8090',
  // 폐지(레거시): 관할(→추출), 발제(→첨부/취급) — 미마이그레이션 잔존 엣지는 회색 폴백.
})

// 노드 타입쌍("from→to") → canonical 관계명 (rel_schema.py / neo4j_sync.py와 일치)
export const REL_MATRIX = reactive({
  'Meetings→company': '포함',
  'dept→company': '소속',
  'person→dept': '소속',
  'dept→Meetings': '참여', // 부서가 구성원을 통해 참여하는 회의체 (neo4j_sync가 (Department)-[:참여]->(Meetings) 실제 생성)
  'dept→dept': '포함',
  'Meetings→Meetings': '협의',
  'agenda→agenda': '관련',
  'Meetings→agenda': '추출', // 회의체가 추출한 안건 (← 과거 'agenda→Meetings 관할' 폐지)
  'agenda→dept': '담당부서', // 안건의 담당 부서
  'person→Meetings': '참여',
  'person→agenda': '담당',
  'agenda→session': '논의',
  'session→Meetings': '소속', // DB 보존(질의용) — 시각화에서는 그리지 않음
  'session→minutes': '기록',
  'person→minutes': '작성',
  'person→session': '참석',
  'session→session': '후속',
  'minutes→agenda': '도출',
  'report→Meetings': '첨부', // 보고자료 첨부 (← 과거 '발제' 폐지)
  'report→agenda': '취급', // 보고자료가 다루는 안건 (← 과거 '발제'/'도출' 폐지)
  'dept→report': '작성',
})

/** 타입쌍 → 관계명 (정/역 양방향 시도, 폴백 '참조') */
export function autoRelByType(fromType, toType) {
  return REL_MATRIX[`${fromType}→${toType}`] || REL_MATRIX[`${toType}→${fromType}`] || '참조'
}

/**
 * canonical 방향 보정 — 사용자가 그린 방향(from→to)에 대해,
 * 매트릭스가 역방향(to→from)만 정의하면 저장 방향을 뒤집는다.
 * (단방향 저장 원칙: 같은 의미 엣지가 출처에 따라 방향이 달라지지 않게)
 * @returns {{ rel, reversed }} reversed=true면 저장 시 from/to를 교환해야 함
 */
export function resolveCanonical(fromType, toType) {
  if (REL_MATRIX[`${fromType}→${toType}`])
    return { rel: REL_MATRIX[`${fromType}→${toType}`], reversed: false }
  if (REL_MATRIX[`${toType}→${fromType}`])
    return { rel: REL_MATRIX[`${toType}→${fromType}`], reversed: true }
  return { rel: '참조', reversed: false }
}

/** 관계명 → 색상 (미정의 시 회색 폴백) */
export function relColor(rel) {
  return REL_COLORS[rel] || '#6b7280'
}

let _loaded = false
/** 백엔드 SSOT로 번들 기본값을 덮어쓴다 (1회). 실패 시 기본값 유지. */
export async function fetchRelSchema() {
  if (_loaded) return
  try {
    const { data } = await apiAI.get('/api/neo4j/rel-schema')
    if (data?.colors) Object.assign(REL_COLORS, data.colors)
    if (data?.matrix) Object.assign(REL_MATRIX, data.matrix)
    _loaded = true
  } catch {
    /* 번들 기본값 유지 */
  }
}
