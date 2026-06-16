// UI/내비게이션 아이콘 단일 정의(SSOT). viewBox 0 0 24 24, stroke 기반(fill=none).
// 노드 타입 아이콘(graph/nodeIcons.js)과 합쳐 공용 레지스트리 ICON_PATHS 를 만든다.
// - 컴포넌트: AppIcon.vue 가 ICON_PATHS[name] 을 currentColor 로 그린다.
// - 노드 타입(Meetings/company/session/dept/agenda/minutes/report/person)은 nodeIcons 에서 재사용한다.

import { NODE_ICON_PATHS } from '../graph/nodeIcons'

export const UI_ICON_PATHS = {
  // 홈
  home: '<path d="M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6"/>',
}

// 자체 색/그라데이션을 가진 이미지 아이콘 — currentColor 라인 아이콘과 달리 <img>로 렌더(틴트 불가).
// public/ 정적 자산은 빌드 시 루트(/)로 서빙된다.
export const ICON_IMAGES = {
  archive: '/favicon.svg', // 브랜드 로고(레인보우 허브)
}

// 공용 아이콘 레지스트리 — 노드 타입 + UI 병합(이름 충돌 시 UI 우선).
export const ICON_PATHS = { ...NODE_ICON_PATHS, ...UI_ICON_PATHS }
