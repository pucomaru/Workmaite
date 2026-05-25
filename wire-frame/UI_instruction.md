# 회의체 운영 AI Agent 개발 프롬프트

## 프로젝트 개요

회의체를 연중 연속적으로 운영하며 조직 내 전략적 의사결정을 돕는 Multi-agent 웹 서비스를 구축한다.
경영전략팀이 수기로 처리하던 low-level 업무(아젠다 추출, 보고서 검토, 회의록 작성, 카드뉴스 생성)를
AI Agent가 대신하도록 설계한다.

---

## 기술 스택

| 구분 | 기술 |
|------|------|
| Frontend | Vue 3 + Vite |
| Backend | FastAPI (Python) |
| AI Orchestration | LangGraph 1.0, LangSmith |
| Database | SQLite (PoC용) |
| AI Model | OpenAI API (GPT-4o) |
| 실시간 회의 | LiveKit |
| 실시간 통신 | WebSocket |

---

## 전체 아키텍처

### Agent 구성 (총 5개)

```
혜안 (Hyean) - Supervisor Agent + 조직 암묵지 관리자
  [역할 1] 개별 회의체 현황 파악 → 사용자가 다음 임무를 알 수 있도록 실시간 안내
  [역할 2] 조직의 암묵지(운영 기준) 학습 및 Asset화
           → 모든 회의체에서 발생하는 컨텍스트를 지속 수집·분석
           → 조직 고유의 회의체 운영 기준(글로벌 + 회의체별)을 자동 업데이트 제안
           → Admin이 제안을 수락/거절/편집 → 확정된 기준이 전체 Agent에 반영
  → 모든 회의체 페이지 우측 하단 플로팅 버튼으로 상시 노출

가온 (Gaon) - Agenda 추출 Agent
  보고자료 및 회의 내용 기반으로 To-do 과제 추출
  → Due date / 담당 조직 / 주관 회의체 자동 맵핑
  → Admin Agenda 페이지, Presenter Todo 페이지에서 사용

나루 (Naru) - 보고서 검토 Agent (Global)
  전체 보고서 총괄 검토 (Admin 회의준비 페이지)

(Presenter용 보고서 검토 Agent)
  개별 보고서 사전 검토, 점수/수정사항 대시보드 제공
  → Presenter 회의준비 페이지에서 사용

아라 (Ara) - 회의 진행 Agent
  회의 중 실시간 지원 (지난 회의 요약, Agenda 확인)
  → 회의 화면 좌측 사이드바

나온 (Naon) - 카드뉴스 생성 Agent
  회의 결과물을 카드뉴스 형태로 재가공
  → 카드뉴스 화면 좌측 채팅 UI
```

### 사용자 권한

- **Admin**: 회의체 생성/관리, Agenda 확정, 보고서 승인/반려, 카드뉴스 생성
- **Presenter**: To-do 확인, 보고서 작성/제출, 회의 참여

### 주요 Loop 구조

```
[Admin] Agenda 페이지 → 회의준비 페이지 → n차 회의 → (반복)
[Presenter] Todo 페이지 → 회의준비 페이지 → n차 회의 → (반복)
```

---

## 데이터 모델 (SQLite)

```sql
-- 사용자
users (id, name, employee_id, password_hash, created_at)

-- 회의체
meetings (id, title, purpose, start_date, end_date, status, created_by, created_at)

-- 회의체 멤버
meeting_members (id, meeting_id, user_id, role)  -- role: admin | presenter

-- Agenda
agendas (id, meeting_id, department, content, status, confirmed_at, confirmed_by)
-- status: draft | confirmed

-- To-do
todos (id, meeting_id, user_id, agenda_id, content, due_date, status, source_type)
-- source_type: report | meeting_minutes

-- 보고서
reports (id, meeting_id, presenter_id, file_path, status, score, feedback, submitted_at, approved_at)
-- status: draft | submitted | approved | rejected

-- 회의 세션
meeting_sessions (id, meeting_id, session_number, title, password, scheduled_at, started_at, ended_at, status)

-- 회의록
minutes (id, session_id, content_raw, content_summary, generated_at)

-- 카드뉴스
card_news (id, meeting_id, session_ids, file_path, created_at)

-- 알림
notifications (id, user_id, type, message, is_read, created_at, ref_id, ref_type)

-- ─────────────────────────────────────────────
-- 암묵지(조직 운영 기준) 관련 테이블
-- ─────────────────────────────────────────────

-- 암묵지 원천 이벤트 로그 (혜안이 학습할 raw 데이터)
-- 회의체 운영 중 발생하는 모든 의사결정 이벤트를 자동 수집
tacit_events (
  id,
  event_type,       -- report_approved | report_rejected | agenda_confirmed |
                    -- agenda_dropped | todo_completed | todo_delayed | meeting_feedback
  meeting_id,
  meeting_type,     -- 회의체 목적/유형 (생성 시 purpose 기반 자동 분류)
  payload,          -- JSON: 이벤트 상세 (보고서 내용, 피드백 텍스트, 아젠다 내용 등)
  actor_id,
  created_at
)

-- 글로벌 암묵지 기준 (조직 전체 공유)
tacit_knowledge_global (
  id,
  category,         -- report_standard | agenda_standard | todo_standard | meeting_standard
  title,
  content,          -- 기준 본문 (마크다운)
  version,
  status,           -- active | draft | archived
  source_event_ids, -- JSON: 이 기준 도출에 사용된 tacit_events.id 목록
  created_at,
  updated_at
)

-- 회의체별 커스텀 암묵지 기준
tacit_knowledge_meeting (
  id,
  meeting_id,
  category,
  title,
  content,
  version,
  status,
  source_event_ids,
  created_at,
  updated_at
)

-- 혜안의 암묵지 업데이트 제안 (AI 초안 → Admin 검토 대기)
tacit_proposals (
  id,
  scope,            -- global | meeting
  meeting_id,       -- scope=meeting일 때만 사용
  target_id,        -- 업데이트 대상 knowledge id (NULL이면 신규 기준 생성 제안)
  category,
  title,
  proposed_content,
  diff_summary,     -- 기존 대비 변경 요약
  evidence_summary, -- 제안 근거 (어떤 이벤트 패턴에서 도출됐는지)
  source_event_ids,
  status,           -- pending | accepted | rejected | edited_and_accepted
  reviewed_by,
  reviewed_at,
  final_content,    -- Admin이 편집한 최종 내용
  created_at
)
```

---

## 화면별 구현 명세

### 1. 공통 레이아웃

#### 1-1. 공통 헤더

```
컴포넌트: AppHeader.vue

[좌측] 로고 / 앱명
[중앙] 현재 조회 중인 회의체 제목 (홈 대시보드 제외한 모든 페이지에서 표시)
[우측] 내 이름 | 알림 아이콘 (미읽 알림 수 badge)
```

#### 1-2. 사이드바

```
컴포넌트: AppSidebar.vue
- 접기/펼치기 토글 가능
- 홈화면 이동 버튼
- 최신 업데이트된 회의체 리스트 (검색 포함)
- 제출한 보고서 리스트 (검색 포함)
- 생성된 카드뉴스 리스트 (검색 포함)
```

#### 1-3. 혜안 Agent 플로팅 버튼

```
컴포넌트: HyeanAgent.vue

[플로팅 버튼]
- 회의체 페이지 진입 시 우측 하단에 항상 노출 (z-index 최상단)
- 클릭 시 채팅 패널 슬라이드업
- 탭 2개: [현황 안내] | [운영 기준]

[탭1 - 현황 안내]
- 현재 회의체의 전체 현황 분석 후 자연어 안내
  예: "보고서 3건 중 1건이 미제출 상태입니다. 담당자에게 독촉 알림을 보낼까요?"
- 다음 액션 추천 + 원클릭 실행 버튼

[탭2 - 운영 기준] (Admin 전용)
- 현재 회의체에 적용 중인 암묵지 기준 요약
  - 글로벌 기준: 조직 전체 공유 기준 목록 (카테고리별)
  - 회의체 기준: 이 회의체에만 적용되는 커스텀 기준 목록
- [전체 기준 관리] 버튼 → 암묵지 관리 페이지로 이동
- 미검토 제안 건수 badge 표시

API:
POST /api/agent/hyean/status
  Input: {meeting_id, user_id, user_role}
  Output: {guidance, next_actions[]} (스트리밍)

GET /api/tacit-knowledge/summary?meeting_id=
  → 현재 회의체에 적용 중인 기준 요약
```

#### 1-4. 회의체 헤더 (회의체 페이지 내부)

```
컴포넌트: MeetingNav.vue
- 공통 헤더 바로 아래 위치
- 가로 스크롤 네비게이션 (loop 3개 표시)
  - Admin: Agenda → 회의준비 → 회의 → Agenda (반복)
  - Presenter: Todo → 회의준비 → 회의 → Todo (반복)
- 현재 위치 강조 표시
- [팀 멤버 보기] 버튼: 회의체 참여 멤버 확인 + admin/presenter 권한 설정
- Admin 전용: [회의체 제목 편집] 인라인 편집
- [회의체 종료] 버튼: 확인 팝업 후 종료 처리
```

---

### 2. 로그인 / 회원가입

```
페이지: LoginPage.vue, RegisterPage.vue

로그인: 사번(employee_id) + 비밀번호
회원가입: 이름, 사번, 비밀번호

API:
POST /api/auth/login    → JWT 토큰 반환
POST /api/auth/register
GET  /api/auth/me
```

---

### 3. 홈 대시보드

```
페이지: HomePage.vue

[상단] 시급한 To-do 리스트 (due_date 임박 순 정렬)

[메인 - 투컬럼]
좌측: 달력 컴포넌트
  - 일/주/월 뷰 전환 버튼
  - 예약된 회의 일정 (색상 A)
  - To-do 마감일 (색상 B)
  
우측: To-do 리스트
  - Presenter 권한 보유 회의체에서 생성된 To-do만 표시
  - Admin only인 경우 빈 화면

[회의체 리스트 섹션]
  - 진행중인 회의체 리스트 (회의체 제목 / 날짜)
  - [회의체 만들기] 버튼

[회의체 만들기 모달]
  필드:
  - 회의체 제목 (필수)
  - 회의체 목적 (textarea)
  - 진행 기간 (시작일, 종료일)
  - 멤버 초대 (사번/이름 검색, 선택적)
  - 권한 설정 (admin / presenter)
  
  동작:
  - 멤버 없어도 생성 가능
  - 초대된 멤버는 알림 수신 + 사이드바/회의체 리스트에 자동 추가

API:
GET  /api/meetings              → 내가 속한 회의체 목록
POST /api/meetings              → 회의체 생성
GET  /api/todos/urgent          → 시급한 To-do (due 3일 이내)
GET  /api/calendar/events       → 달력 이벤트 (회의 일정 + to-do)
GET  /api/users/search?q=       → 멤버 검색
POST /api/meetings/{id}/members → 멤버 추가
```

---

### 4. Admin Agenda 페이지

```
페이지: AdminAgendaPage.vue
경로: /meetings/:meetingId/agenda

[loop 진입점 — 첫 진입 vs 이후 루프 분기]
첫 진입: "보고자료를 등록하세요" 안내 → 보고자료 업로드
이후 루프: 이전 회의록 + 보고자료 모두 참조 → 새 Agenda 추출

[레이아웃 - 투컬럼]

좌측: 가온(Gaon) Agent 채팅 UI
  - 채팅 인터페이스 (사용자 ↔ 가온)
  - 파일 업로드 버튼 (보고자료 PDF/문서 첨부)
  - 채팅 내용에 따라 우측 Agenda 리스트 실시간 업데이트 (WebSocket)

우측: Agenda 리스트
  - 형식: [담당 부서] | [아젠다 내용] | [확정 버튼]
  - 유저가 직접 편집 가능 (인라인 편집)
  - [확정] 버튼 클릭 시:
    - Agenda 상태 → confirmed 저장
    - 해당 담당 부서의 Presenter에게 알림 발송
    - Presenter Todo 페이지에 Agenda 자동 반영

Agent 동작 (FastAPI + LangGraph):
POST /api/agent/gaon/extract-agenda
  Input: {meeting_id, file_content, chat_history, previous_minutes}
  Output: [{department, content, due_date}] (스트리밍)

WebSocket: /ws/meetings/{meetingId}/agenda
  → Agenda 리스트 실시간 동기화
```

---

### 5. Presenter Todo 페이지

```
페이지: PresenterTodoPage.vue
경로: /meetings/:meetingId/todo

[레이아웃 - 투컬럼]

좌측: 가온(Gaon) Agent 채팅 UI
  - Admin이 Agenda를 아직 확정하지 않은 경우:
    "아직 할당된 아젠다가 없습니다. Admin이 아젠다를 확정하면 알림을 드릴게요."
  - Agenda 확정 후: To-do 작성 보조, 보고서 방향 제시

우측: 할당된 Agenda + To-do 리스트
  - [상단 고정] 확정된 Agenda 리스트
  - [하단] To-do 리스트 또는 보고서 작성 방향
    - 유저가 직접 편집 가능
    - 채팅에 따라 실시간 업데이트

API:
GET  /api/meetings/{id}/agendas/assigned  → 나에게 할당된 Agenda
GET  /api/meetings/{id}/todos/mine        → 내 To-do 목록
POST /api/meetings/{id}/todos             → To-do 생성
PATCH /api/todos/{id}                     → To-do 수정
```

---

### 6. Admin 회의준비 페이지

```
페이지: AdminPreparePage.vue
경로: /meetings/:meetingId/prepare

[레이아웃 - 투컬럼]

좌측: 나루(Naru) Agent 채팅 UI
  - Global 보고서 검토 (전체 제출 보고서 총괄 분석)
  - "전체 보고서 품질 리포트", "누락된 내용", "공통 피드백" 등 제공

우측: 보고서 제출 현황 대시보드
  - 제출 현황 테이블: [Presenter 이름] | [부서] | [제출 상태] | [제출일] | [승인/반려]
  - [승인] / [반려] 버튼 → 클릭 시 해당 Presenter에게 알림 발송
  - 보고서 파일 미리보기/다운로드

API:
GET  /api/meetings/{id}/reports            → 제출된 보고서 목록
PATCH /api/reports/{id}/status             → 승인(approved) / 반려(rejected)
POST /api/agent/naru/global-review         → 전체 보고서 총괄 검토
```

---

### 7. Presenter 회의준비 페이지

```
페이지: PresenterPreparePage.vue
경로: /meetings/:meetingId/prepare/presenter

[레이아웃 - 투컬럼]

좌측: 보고서 검토 Agent 채팅 UI
  - 보고서 파일 업로드 → Agent가 사전 검토
  - 검토 결과: 점수(0-100) + 수정사항 대시보드 (우측에 표시)
  - 개선 제안 채팅 대화 지속 가능

우측: 보고서 제출 패널
  - 보고서 점수 카드 (Agent 검토 결과)
  - 수정사항 체크리스트
  - [최종 제출] 버튼 → 업로드 시 Admin에게 알림
  - 보고서 승인 알림 수신 시: [Teams 업로드] 버튼 활성화

API:
POST /api/agent/report-review              → 보고서 사전 검토 (score + feedback)
POST /api/meetings/{id}/reports            → 보고서 제출
POST /api/reports/{id}/upload-teams        → Teams 업로드 (MS Teams Webhook)
```

---

### 8. n차 회의 페이지 (회의록 생성 UI)

```
페이지: MeetingSessionPage.vue
경로: /meetings/:meetingId/sessions

[상단]
[회의 만들기] 버튼 (Admin 전용, 미생성 상태일 때만 표시)
  모달 입력: 회의명, 일정(datetime), 회의 멤버 선택, 비밀번호(선택)
  생성 후: 초대된 멤버들에게 알림 + 링크 전송
  [회의 만들기] 버튼 → [회의 참여] 버튼으로 전환

[메인 - 투컬럼]

좌측: 회의록 생성 Agent 대화창
  - 회의 종료 후 자동으로 회의록 생성 메시지 출력
  - "회의 내용 기반으로 회의록이 생성되었습니다."
  - [AI 회의록 다운로드] 버튼
  - [회의 원문 다운로드] 버튼
  - Admin 전용 버튼: [카드뉴스 생성 페이지로 이동] | [Agenda 추출 페이지로 이동]
  - Presenter 전용 버튼: [To-do 추출 페이지로 이동]

우측: n차 회의록 스택 리스트
  - 회차별 회의록 카드 (회의명, 날짜, 요약 미리보기)
  - 클릭 시 회의록 상세 모달
  - 회의 원문은 표시 안 함 (다운로드만 가능)

API:
POST /api/meetings/{id}/sessions            → 회의 세션 생성
GET  /api/meetings/{id}/sessions            → 세션 목록
GET  /api/sessions/{id}/minutes             → 회의록 조회
GET  /api/sessions/{id}/minutes/download    → 회의록 다운로드
GET  /api/sessions/{id}/raw/download        → 회의 원문 다운로드

WebSocket: /ws/sessions/{sessionId}/minutes
  → 회의 종료 후 회의록 생성 실시간 스트리밍
```

---

### 9. 회의 화면

```
페이지: MeetingRoomPage.vue
경로: /meetings/:meetingId/sessions/:sessionId/room

[기반 라이브러리]: LiveKit SDK

[레이아웃]
메인 영역: 참여자 비디오 그리드 (Zoom UI 참고)
  - 참여자 리스트 패널 (이름, 마이크/카메라 상태)

좌측 사이드바: 아라(Ara) Agent
  - 채팅 인터페이스
  - [지난 회의 요약] 탭
  - [현재 Agenda] 탭

하단 컨트롤 바:
  - [회의 시작] 버튼 (누르면 녹음 시작 + Agent 기능 활성화)
  - 마이크 on/off, 카메라 on/off
  - [나가기] 버튼
  - Admin 전용: [회의 종료] 버튼

회의 종료 조건:
  1. Admin이 [회의 종료] 버튼 클릭
  2. 모든 참여자가 나가기를 눌러 참여자 수 = 0
  → 자동으로 회의록 생성 프로세스 시작
  → 완료 후 n차 회의 화면으로 리디렉션

녹음 처리:
  - LiveKit Audio Track → 청크 단위 STT (OpenAI Whisper API)
  - 발화자 구분 (speaker diarization)
  - 실시간 스크립트 저장 → DB(minutes.content_raw)
  - 회의 종료 시 LangGraph로 요약 생성 → DB(minutes.content_summary)

API:
POST /api/sessions/{id}/start               → 녹음 시작
POST /api/sessions/{id}/end                 → 회의 종료 + 회의록 생성 트리거
POST /api/sessions/{id}/transcript-chunk    → STT 결과 청크 저장
```

---

### 10. 카드뉴스 화면

```
페이지: CardNewsPage.vue
경로: /meetings/:meetingId/card-news

활성화 조건: 회의가 정상 종료된 경우에만

[레이아웃 - 투컬럼]

좌측: 나온(Naon) Agent 채팅 UI
  - 카드뉴스에 포함할 회의 차수 선택 (멀티 선택 가능, Claude 대화창 스타일)
  - "어떤 내용을 강조할까요?" 등 커스터마이즈 대화
  - [카드뉴스 생성] 버튼

우측: 카드뉴스 스택
  - 생성된 카드뉴스 카드 리스트 (스택 형태)
  - 각 카드: 제목, 생성일, 미리보기 썸네일
  - [다운로드] 버튼 (이미지/PDF)

가로 스크롤 네비게이션: Agenda 페이지 연결

API:
POST /api/agent/naon/generate-card-news     → 카드뉴스 생성
  Input: {meeting_id, session_ids, emphasis_points}
  Output: card_news_id + 이미지 파일
GET  /api/meetings/{id}/card-news           → 카드뉴스 목록
GET  /api/card-news/{id}/download           → 다운로드
```

---


### 11. 암묵지 관리 페이지 (Admin 전용)

```
페이지: TacitKnowledgePage.vue
경로: /tacit-knowledge
접근 권한: Admin만 접근 가능 (글로벌 기준 관리 권한)
사이드바에서 직접 접근 가능하도록 링크 추가

─────────────────────────────────────────────
[개념 설명]
암묵지(Tacit Knowledge) = 조직이 회의체를 운영하면서
쌓아온 의사결정 패턴을 AI가 정제한 "살아있는 운영 기준"

혜안 Agent가 자동 학습한 패턴을 Admin이 검토·확정하면
이후 모든 Agent(가온, 나루, 아라 등)의 판단 기준으로 반영됨
─────────────────────────────────────────────

[레이아웃]
상단 탭: [검토 대기 중] | [글로벌 기준] | [회의체별 기준] | [학습 로그]

────────────────────────────────────────────
[탭1 - 검토 대기 중] (기본 진입 탭)
────────────────────────────────────────────
혜안이 새로 제안한 암묵지 업데이트 목록
미검토 건수 badge 표시

제안 카드 형식:
┌─────────────────────────────────────────────────┐
│ [NEW | UPDATE] 카테고리 뱃지          날짜       │
│ 제목: "보고서 핵심 요건 업데이트"                 │
│                                                   │
│ 📊 제안 근거                                      │
│ "최근 3건의 반려 보고서 분석 결과, 경영진이       │
│  공통으로 요구한 항목이 누락된 패턴 발견"         │
│ → 근거 이벤트 [3건] 보기 (클릭 시 상세 팝업)     │
│                                                   │
│ 📝 변경 내용 (diff 형식)                          │
│ - 기존: "...내용..."                              │
│ + 제안: "...새 내용..."                           │
│                                                   │
│ [수락] [거절] [편집 후 수락]                      │
└─────────────────────────────────────────────────┘

[편집 후 수락] 클릭 시:
- 제안 내용을 인라인 마크다운 에디터로 편집 가능
- [최종 확정] 버튼으로 저장

────────────────────────────────────────────
[탭2 - 글로벌 기준]
────────────────────────────────────────────
조직 전체에 공유되는 운영 기준 목록
카테고리별 섹션:
  📋 보고서 기준 (report_standard)
  📌 아젠다 기준 (agenda_standard)
  ✅ 과제 기준 (todo_standard)
  🎙 회의 기준 (meeting_standard)

각 기준 카드:
- 제목 / 버전 / 최종 업데이트일
- 내용 미리보기 (접기/펼치기)
- [편집] 버튼 (Admin이 직접 수동 수정 가능)
- [버전 히스토리] 버튼 → 이전 버전 목록 + 롤백 가능

[+ 기준 직접 추가] 버튼
  → 카테고리 선택 + 제목 + 내용 작성 → 즉시 active 등록

────────────────────────────────────────────
[탭3 - 회의체별 기준]
────────────────────────────────────────────
회의체 드롭다운으로 선택 → 해당 회의체 커스텀 기준 표시
글로벌 기준과 동일한 편집 UI
"글로벌 기준 상속 중" vs "커스텀 기준 적용 중" 상태 표시

────────────────────────────────────────────
[탭4 - 학습 로그]
────────────────────────────────────────────
혜안이 수집한 원천 이벤트 로그 열람
필터: 이벤트 유형 / 회의체 / 날짜 범위
각 이벤트 클릭 시 상세 내용 확인
"이 이벤트로 새 기준 제안 요청" 버튼 (수동 트리거)
```

API:
GET  /api/tacit-knowledge/proposals              → 검토 대기 중 제안 목록
PATCH /api/tacit-knowledge/proposals/{id}        → 수락/거절/편집 후 수락
  Body: {action: "accept"|"reject"|"edit_accept", final_content?}

GET  /api/tacit-knowledge/global                 → 글로벌 기준 목록
POST /api/tacit-knowledge/global                 → 글로벌 기준 직접 추가
PATCH /api/tacit-knowledge/global/{id}           → 글로벌 기준 수동 편집
GET  /api/tacit-knowledge/global/{id}/versions   → 버전 히스토리
POST /api/tacit-knowledge/global/{id}/rollback   → 이전 버전 롤백

GET  /api/tacit-knowledge/meeting/{meetingId}    → 회의체별 커스텀 기준
POST /api/tacit-knowledge/meeting/{meetingId}    → 회의체 기준 추가
PATCH /api/tacit-knowledge/meeting/{id}          → 회의체 기준 수동 편집

GET  /api/tacit-knowledge/events                 → 학습 로그 목록 (필터 지원)
POST /api/agent/hyean/propose-from-event         → 특정 이벤트로 제안 수동 트리거

---

## 알림 시스템

```
WebSocket: /ws/notifications/{userId}
→ 실시간 알림 수신

알림 발생 시점:
1. Admin이 Agenda 확정 → 해당 Presenter에게 알림
2. Presenter가 보고서 제출 → Admin에게 알림
3. Admin이 보고서 승인 → 해당 Presenter에게 알림
4. Teams에 보고서 업로드 완료 → 관련자 알림
5. 회의 생성 → 초대된 멤버에게 알림 + 링크
6. 회의록 생성 완료 → 회의 참여자 전원에게 알림
7. 혜안이 새 암묵지 업데이트 제안 생성 → Admin에게 알림
   예: "회의 패턴 분석 결과, 보고서 기준 업데이트가 제안되었습니다. [검토하기]"
8. Admin이 암묵지 기준 확정 → 전체 구성원에게 알림 (선택적)
   예: "보고서 작성 기준이 업데이트되었습니다. [확인하기]" 

알림 컴포넌트: NotificationPanel.vue
- 헤더 알림 아이콘 클릭 시 드롭다운
- 미읽 알림 badge 수
- 클릭 시 해당 페이지로 이동

API:
GET   /api/notifications           → 알림 목록
PATCH /api/notifications/{id}/read → 읽음 처리
PATCH /api/notifications/read-all  → 전체 읽음
```

---

## LangGraph Agent 구조

```python
# 각 Agent는 독립적인 LangGraph StateGraph로 구현

# ─────────────────────────────────────────────
# 암묵지 주입 원칙
# 모든 Agent는 실행 시 해당 회의체의 활성 암묵지 기준을
# system prompt에 동적으로 주입받아 판단 기준으로 활용함
#
# 주입 예시 (가온 Agent system prompt 일부):
# "다음은 이 조직의 아젠다 선정 기준입니다:
#  [글로벌 기준] 전략적 우선순위가 명확하고 의사결정 필요성이 있는 항목을 우선 선정
#  [이 회의체 기준] 분기 KPI와 직접 연관된 항목만 아젠다화
#  위 기준을 참고하여 아젠다를 추출하고 우선순위를 판단하세요."
# ─────────────────────────────────────────────

# 1. Gaon Agent (Agenda/Todo 추출)
class GaonState(TypedDict):
    meeting_id: str
    uploaded_files: list[str]
    chat_history: list[dict]
    previous_minutes: list[str]
    active_knowledge: list[dict]  # 주입된 암묵지 기준
    agendas: list[dict]           # output
    todos: list[dict]             # output

# 2. Naru Agent (보고서 전체 검토)
class NaruState(TypedDict):
    meeting_id: str
    reports: list[dict]
    chat_history: list[dict]
    global_review: str          # output

# 3. Report Review Agent (개별 보고서)
class ReportReviewState(TypedDict):
    report_content: str
    agenda: str
    chat_history: list[dict]
    score: int                  # output (0-100)
    feedback: list[str]         # output

# 4. Ara Agent (회의 중 지원)
class AraState(TypedDict):
    session_id: str
    transcript_so_far: str
    previous_minutes: list[str]
    current_agendas: list[dict]
    chat_history: list[dict]
    response: str               # output

# 5. Naon Agent (카드뉴스)
class NaonState(TypedDict):
    meeting_id: str
    selected_sessions: list[str]
    minutes_list: list[str]
    emphasis_points: str
    chat_history: list[dict]
    card_news_content: dict     # output

# 6. Hyean Agent (Supervisor + 암묵지 관리자)
# 역할 A: 개별 회의체 현황 안내
class HyeanStatusState(TypedDict):
    meeting_id: str
    user_id: str
    user_role: str
    meeting_status: dict          # agenda/report/todo 현황 snapshot
    active_knowledge: list[dict]  # 현재 적용 중인 암묵지 기준
    chat_history: list[dict]
    guidance: str                 # output
    next_actions: list[dict]      # output: [{label, api_endpoint, payload}]

# 역할 B: 암묵지 학습 및 제안 생성 (백그라운드 배치 실행)
# 트리거: 보고서 승인/반려, Agenda 확정/폐기, To-do 완료/지연, 회의 종료
class HyeanLearningState(TypedDict):
    trigger_event: dict           # 새로 발생한 tacit_event
    recent_events: list[dict]     # 최근 N건의 동일 유형 이벤트
    current_knowledge: list[dict] # 현재 활성 기준
    scope: str                    # "global" | "meeting"
    meeting_id: str | None
    proposal: dict | None         # output: tacit_proposals에 저장할 제안 (None이면 제안 없음)

# HyeanLearningState 노드 구성 (LangGraph)
# collect_events → analyze_pattern → compare_with_current → generate_proposal → save_proposal
#   ↑ 패턴이 유의미하지 않으면 propose 없이 종료
```

---

## 실시간성 요구사항

모든 핵심 기능은 실시간으로 동작해야 한다.

| 기능 | 구현 방식 |
|------|-----------|
| Agenda 리스트 실시간 업데이트 | WebSocket |
| To-do 리스트 실시간 업데이트 | WebSocket |
| 보고서 제출 현황 | WebSocket |
| 알림 수신 | WebSocket |
| 회의록 생성 스트리밍 | WebSocket (Server-Sent Events도 가능) |
| Agent 응답 스트리밍 | LangGraph streaming + WebSocket |
| 회의 음성/영상 | LiveKit WebRTC |

---

## 파일 구조 (권장)

```
/frontend (Vue 3 + Vite)
  /src
    /components
      /common       AppHeader, AppSidebar, NotificationPanel
      /agents       HyeanAgent, GaonChat, NaruChat, AraChat, NaonChat
      /tacit        ProposalCard, KnowledgeCard, KnowledgeEditor, VersionHistory, EventLog
      /meeting      MeetingNav, MeetingCard, MeetingCreateModal
      /agenda       AgendaList, AgendaItem
      /todo         TodoList, TodoItem
      /report       ReportTable, ReportUpload, ReviewDashboard
      /session      SessionCard, MinutesStack
      /cardnews     CardNewsStack, CardNewsCard
    /pages
      LoginPage, RegisterPage, HomePage
      AdminAgendaPage, PresenterTodoPage
      AdminPreparePage, PresenterPreparePage
      MeetingSessionPage, MeetingRoomPage, CardNewsPage
      TacitKnowledgePage
    /stores         (Pinia)
      auth, meetings, notifications, todos, tacitKnowledge
    /composables
      useWebSocket, useAgent, useMeeting

/backend (FastAPI)
  /routers
    auth, meetings, agendas, todos, reports, sessions, minutes, card_news, notifications
    tacit_knowledge       # 암묵지 기준 CRUD + 제안 관리
  /agents
    gaon, naru, report_review, ara, naon
    hyean_status          # 현황 안내 Agent
    hyean_learning        # 암묵지 학습·제안 Agent (백그라운드)
    knowledge_injector    # Agent 실행 시 암묵지 기준 동적 주입 유틸리티
  /models         SQLAlchemy models
  /schemas        Pydantic schemas
  /services
    livekit, openai_stt, teams_webhook
  /websocket
    manager, handlers
  main.py
```

---

## 구현 우선순위

### Phase 1 (핵심 루프)
1. 로그인/회원가입 + JWT 인증
2. 홈 대시보드 + 회의체 생성 모달
3. Admin Agenda 페이지 + 가온 Agent (파일 업로드 → Agenda 추출)
4. Presenter Todo 페이지 + Agenda 확정 → 알림 연동

### Phase 2 (회의 준비)
5. Admin 회의준비 페이지 + 나루 Agent
6. Presenter 회의준비 페이지 + 보고서 검토 Agent
7. 보고서 승인/반려 + 알림 시스템

### Phase 3 (회의 진행)
8. n차 회의 페이지 + 회의 세션 생성
9. 회의 화면 (LiveKit) + 아라 Agent
10. 회의 종료 → 회의록 자동 생성

### Phase 4 (암묵지 시스템)
11. 카드뉴스 화면 + 나온 Agent
12. 혜안 Agent 기본 기능 (현황 안내 플로팅 버튼)
13. tacit_events 자동 수집 로직 구현
    - 보고서 승인/반려 시 이벤트 저장 훅
    - Agenda 확정/폐기 시 이벤트 저장 훅
    - To-do 완료/지연 시 이벤트 저장 훅
    - 회의 종료(회의록 생성) 시 이벤트 저장 훅
14. 혜안 Learning Agent (HyeanLearningState) + 제안 생성 파이프라인
15. 암묵지 관리 페이지 (TacitKnowledgePage) 구현
    - 검토 대기 탭 (제안 카드 + 수락/거절/편집)
    - 글로벌 기준 탭 (CRUD + 버전 히스토리)
    - 회의체별 기준 탭
    - 학습 로그 탭
16. knowledge_injector 구현 → 전체 Agent system prompt에 암묵지 동적 주입
17. 사이드바에 [암묵지 관리] 메뉴 추가 (Admin 전용)

---

## 디자인 가이드라인

- **톤**: 기업용 전략기획 도구. 신뢰감 있고 정돈된 느낌. 과하게 화려하지 않되, 단조롭지 않게.
- **컬러**: 네이비 계열 Primary + 포인트 컬러 1가지. 다크/라이트 모드 중 하나 선택.
- **Agent 캐릭터 구분**: 각 Agent(가온, 나루, 아라, 나온, 혜안)는 채팅 UI 내 아이콘/이름으로 명확히 구분.
- **루프 네비게이션**: 가로 스크롤 3개 loop 표시는 현재 위치를 강조(굵게, 색상)하고 이전/다음 단계를 흐리게.
- **실시간 업데이트**: 리스트 갱신 시 애니메이션(fade-in) 적용으로 변경 인지 가능하게.