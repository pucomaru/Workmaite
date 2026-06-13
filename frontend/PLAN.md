# Frontend 개선 계획 (2026-06-13 분석)

> 분석 범위: `frontend/src` 전체 (페이지 8, 컴포넌트 25, 컴포저블 7, 스토어 4).
> 빌드는 vite 8 + Vue 3.5, 현재 `npm run build` 정상 통과 상태 기준.

## 현황 요약

| 영역 | 평가 | 근거 |
|---|---|---|
| 보안 (XSS) | ✅ 양호 | 모든 `v-html`이 DOMPurify 경유 (useMarkdown.js) |
| 메모리 누수 | ✅ 양호 | addEventListener 전수 확인 — 모두 해제 처리됨 |
| 스타일 시스템 | ✅ 양호 | 색상 토큰·공통 레이아웃 단일화 완료 (2026-06 정리) |
| 데이터 계층 | 🔴 취약 | 스토어/로컬 fetch 혼재 4개 자원, N+1 호출 3곳, 중복 fetch 5패턴 |
| 에러·피드백 UX | 🔴 취약 | 침묵 catch 24곳, alert/confirm 22곳, 로딩 상태 누락 페이지 존재 |
| 컴포넌트 구조 | 🟡 부채 | ArchivePage 2,840줄 + provide 81키(46키 미사용), SessionPage 1,815줄 6개 책임 |
| 품질 인프라 | 🔴 부재 | ESLint/Prettier/테스트/TypeScript 전무, scripts에 dev/build/preview만 존재 |
| 접근성 | 🟡 미흡 | 아이콘 전용 버튼 aria-label 누락 다수 |
| 번들 크기 | 🟡 보통 | SessionPage 450KB(tiptap), ArchivePage 259KB(pixi.js ~120KB) — 라우트 분할은 되어 있음 |

---

## 발견된 문제 (심각도순)

### 🔴 P-1. 데이터 계층 — 스토어와 로컬 fetch 혼재
같은 자원이 여러 곳에서 서로 다른 방식으로 관리되어 캐시 불일치·중복 로드 발생.

| 자원 | 스토어 | 로컬 중복 |
|---|---|---|
| 회의체 목록 | `stores/meetings.js fetchMeetings()` | SessionPage.vue:97 로컬 `fetchMeetings()` 별도 구현 |
| 역할(my_role) | `fetchMeetings()`가 이미 `meetingRoles`에 채움 | HomePage.vue:157 회의체마다 `/my-role` **N+1 호출** (스토어 무시) |
| 멤버 | `fetchMembers()` | MeetingsPage.vue `membersCache` 로컬 캐시 |
| 세션 목록 | 스토어 없음 | SessionPage.vue `sessionsCache` 로컬 전용 |

### 🔴 P-2. N+1 / 순차 API 호출
- HomePage.vue:157-166 — 회의체 N개 → `/my-role` N회 (fetchMeetings 응답에 이미 포함된 데이터)
- MeetingsPage.vue:120-122 — 멤버 N명 생성 시 N회 순차 POST
- MeetingsPage.vue:207-211 — 설정 저장 시 멤버 변경 건수만큼 순차 DELETE/POST

### 🔴 P-3. 에러 피드백 부재
- 침묵 catch 24곳 (`catch {}` / `.catch(() => {})`) — 실패해도 화면 무반응. 백엔드 단절 시 **이전 데이터가 정상처럼 표시**되는 현상의 원인(스토어 메모리 캐시 + 침묵 실패 조합)
- `alert()` 17곳, `confirm()` 4곳, `prompt()` 2곳 — UX 불일치, 접근성 문제
- HomePage 초기 로딩 스피너 없음(빈 달력 노출), ArchivePage `loading` ref 미사용

### 🟡 P-4. 거대 컴포넌트와 결합도
- ArchivePage.vue **2,840줄**, `provide('archiveSidebar')` **81키** 중 소비자가 실제 사용하는 키는 35개 — 46키(57%)는 잉여 결합
- SessionPage.vue **1,815줄**에 6개 독립 책임(세션 관리/녹음·STT/대화기록/회의록 에디터/아젠다 추출/채팅)
- 채팅 UI 3곳 중복(AgentSidebar, SessionPage, ArchivePage 경유) — 마크업·로직 약 40~60줄씩
- 수동 모달 10개(총 1,646줄), 공통 래퍼 없음

### 🔴 P-5. 품질 인프라 부재
- ESLint/Prettier 없음 → 스타일 드리프트가 사람 손에 의존 (이번 정리에서 드러난 중복·사본 문제의 근본 원인)
- 테스트 0개 — utils/composables(순수 로직)조차 미검증
- TypeScript 미사용 — 81키 provide 같은 대형 계약이 무검증

### 🟡 P-6. 접근성
- 아이콘 전용 버튼 aria-label/title 누락: AppHeader.vue:291,353, TokenUsageModal.vue:82, LandingPage.vue:341,352 외 다수

### 🟢 P-7. 번들 (낮은 우선순위)
- pixi.js(~120KB)·tiptap(~80KB)이 각 페이지 진입 시 일괄 로드 — 라우트 분할은 이미 적용되어 있어 체감 영향 제한적

---

## 단계별 개선 계획

### Phase 0 — 품질 인프라 구축 (0.5~1일, 저위험·즉시) ✅ 2026-06-13 완료
재발 방지 장치부터. 이후 단계의 안전망이 된다.
- [x] ESLint(flat config) + `eslint-plugin-vue` 도입, `npm run lint` 추가 — 0 errors / 90 warnings (기존 코드 경고는 점진 해소)
- [x] `.editorconfig` 추가 (Prettier는 전체 리포맷 디프를 피하기 위해 보류 — 필요 시 후속 도입)
- [x] Vitest 설치 + 순수 로직 테스트 20개: `tests/date.test.js`, `avatar.test.js`, `useTableSort.test.js`, `usePagination.test.js`
- [x] CI 게이트: `.github/workflows/quality-frontend.yml` (PR·develop push 시 lint+test+build, 기존 배포 워크플로와 분리)
- 비고: 기존 편집 모달들의 `vue/no-mutating-props` 19건은 warn으로 강등 — Phase 3 모달 재설계에서 해소.

### Phase 1 — 데이터 계층 단일화 (1~2일, 효과 최대) ✅ 2026-06-13 완료 (배치 API 제외)
- [x] **HomePage N+1 제거**: `/my-role` 루프 삭제, `meetingsStore.meetingRoles` 사용 — 회의체 N개 기준 API 호출 N+3 → 3
- [x] 세션 목록을 `stores/sessions.js`로 승격 — `sessionsByMeeting` 캐시 + `loadSessions(force)` + `invalidate`
- [x] 멤버 캐시를 `stores/meetings.js`로 통합 — `membersByMeeting` + `fetchMembersOnce()` + `invalidateMembers()`, MeetingsPage 로컬 캐시 제거
- [x] SessionPage의 로컬 `fetchMeetings()` HTTP 호출 제거 → 스토어 fetch 후 사이드바 트리 형태로 매핑
- [ ] (백엔드 협업) 멤버 일괄 추가/변경 배치 엔드포인트 — `POST /api/v1/meetings/{id}/members/batch` ← 별도 이슈로 분리
- 완료 기준 달성: 같은 자원을 fetch하는 HTTP 경로가 자원당 1개 (회의체·역할·멤버·세션 모두 스토어 경유).

### Phase 2 — 에러·피드백 UX (1~2일) ✅ 2026-06-13 완료
- [x] `useToast` + `AppToast.vue` 전역 토스트 (success/error/info, App.vue 마운트)
- [x] 네이티브 다이얼로그 전량 치환 — `alert()` 23곳 → 토스트, `confirm()` 8곳 → `confirmDialog()`(Promise), `window.prompt()` 3곳 → `promptDialog()` (입력 지원 `AppConfirmModal`)
- [x] 네트워크 단절 전역 처리 — `stores/network.js` + api/apiAI 인터셉터 연동 + `AppNetworkBanner.vue` 상단 배너 ("서버에 연결할 수 없습니다 — 표시 중인 데이터는 최신이 아닐 수 있습니다")
- [x] HomePage 초기 로딩 상태 추가 (`table-loading` 패턴 재사용). ArchivePage 목록 뷰는 기존 `loading` 표시가 이미 동작 — 그래프 뷰는 자체 UX 유지
- [x] 침묵 catch 정책: 사용자 행동 실패는 토스트로 전환 완료. 데이터 로드 폴백 catch는 네트워크 배너가 시스템 차원에서 인지시키므로 의도적 유지 (개별 토스트는 소음)
- 완료 기준 달성: `alert(`/`confirm(`/`window.prompt` 검색 결과 0건 (새 컴포저블 주석 제외).

### Phase 3 — 거대 컴포넌트 분해 (3~5일, 점진)
위험도가 있으므로 Phase 0의 테스트/lint 안전망 위에서 진행. 한 PR에 한 덩어리씩.
- [ ] **3-1. archiveSidebar provide 다이어트**: 미사용 46키 제거(즉시, 저위험) → 이후 도메인별 3분할 (`archiveDetail` / `archiveExtract` / `archiveGraphRel`)
- [ ] **3-2. 채팅 공통화**: `ChatMessages.vue`(역할별 버블 + planning 블록 + typing 인디케이터) 추출 — AgentSidebar·SessionPage 양쪽 적용 (AgentComposer 공통화와 동일 패턴)
- [ ] **3-3. SessionPage 분해**: ① `MinutesEditor.vue`(tiptap 에디터+다음 아젠다 블록, ~500줄) ② `useRecording`(녹음·타이머·STT 연동) ③ `SessionChat.vue` — 추출 순서는 결합도 낮은 것부터
- [ ] **3-4. BaseModal 재설계**: header/body/footer 슬롯 + size prop. 신규 모달부터 적용, 기존 10개는 수정 기회가 있을 때 점진 마이그레이션 (빅뱅 금지)
- 완료 기준: ArchivePage < 1,800줄, SessionPage < 1,000줄, provide 키 모두 실사용.

### Phase 4 — 성능·장기 과제 (선택, 여유 시)
- [ ] pixi.js 동적 import (`() => import('pixi.js')`) — 아카이브 목록만 쓰는 사용자는 그래프 미로드
- [ ] tiptap 청크 분리 (회의록 에디터 진입 시 로드)
- [ ] TypeScript 점진 도입 — `utils/`·`composables/`·`stores/`부터 `.ts` 전환 (`allowJs`로 혼용), 컴포넌트는 마지막
- [ ] 접근성 일괄 정비: 아이콘 버튼 aria-label, 모달 focus trap, ESC 닫기 표준화
- [ ] HomePage 달력 year-view 데드 분기 정리 (views에 'year' 없음 — 템플릿/스타일 잔존)

---

## 진행 원칙
1. **한 PR = 한 주제** — 이번 분석에서 자동 정리 스크립트(`scripts/find-dead-css.mjs` 등)가 검증된 것처럼, 기계적 변경은 스크립트화하고 결과를 빌드로 검증한다.
2. **Phase 0 없이 Phase 3 금지** — 거대 컴포넌트 분해는 테스트·lint 안전망이 생긴 뒤에.
3. 스타일/레이아웃 공통 클래스는 `style.css` 단일 정의 원칙 유지 (페이지 scoped 사본 금지).
4. 백엔드 변경이 필요한 항목(배치 API)은 별도 이슈로 분리해 프런트 단독 항목과 섞지 않는다.
