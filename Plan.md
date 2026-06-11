# WorkMaite 개선 계획 (Plan.md)

> 작성: 2026-06-12, Claude Code 코드 전수 감사 결과.
> DB 직접 접근 없이 코드만으로 분석함 (PostgreSQL 스키마는 JPA/SQLAlchemy 모델에서, Neo4j 온톨로지는 sync 코드의 Cypher에서 재구성).
> **사용법**: 각 Phase의 체크박스를 진행하며 갱신하고, §6의 후속 프롬프트를 복사해 새 세션에서 이어서 작업한다. 완료 항목은 `[x]`로 표시하고 발견사항을 해당 항목 아래에 추가한다.

---

## 1. 시스템 현황 요약 (코드에서 파악한 아키텍처)

```
Vue 3 (Vite, Pinia, vue-router) ──┐
                                  ├─ Ingress(workmaite.project.skala-ai.com, TLS)
Spring Boot 8080 (/api/**) ───────┤   /api/agent|ai|neo4j|sync|chats|stt|upload, /ws → FastAPI
FastAPI AI 8000 (/api/agent 등) ──┤   /api/** 나머지 → Spring, / → 프론트, /grafana → Grafana
WhisperX 9000 (자체 STT+pyannote) ┘
PostgreSQL(공유 postgres ns) ←─ JPA(Spring) + SQLAlchemy(FastAPI) 듀얼 ORM
Neo4j(자체 배포) ←─ FastAPI가 HTTP REST(tx/commit)로 동기화 (Spring → FastAPI webhook 경유)
LLM: OpenAI gpt-4o-mini 단일 + text-embedding-3-small / STT: WhisperLiveKit(WS) | Google STT v1 | OpenAI diarize
CI: GitHub Actions(develop push → Harbor 이미지 → k8s yaml tag 갱신 → ArgoCD)
관측: prometheus-fastapi-instrumentator(/metrics), Spring actuator/prometheus, Loki, Grafana
```

- **AI 오케스트레이션**: `routers/supervisor.py`(2,593줄)가 LLM 구조화 출력으로 intent 분류(`classify_intent`) 후 if-분기로 4개 에이전트(`task_extractor`, `minutes_generator`, `report_reviewer`, `knowledge_manager`)에 위임. 각 에이전트는 `create_react_agent` + 도구 2개씩.
- **PG→Neo4j 동기화**: Spring CUD → `NeoSyncService`(@Async, fire-and-forget) → FastAPI `/api/sync/*` → `neo4j_sync.py` upsert(+OpenAI 임베딩). 시작 시 전체 resync.
- **토큰/비용 추적**: `agent_logging.py`의 데코레이터 + ContextVar 콜백으로 `agent_logs`/`token_usage_logs` 기록(잘 만들어진 편). `usage.py`가 대시보드 제공.
- **PostgreSQL 테이블(코드 재구성)**: users, meetings, meeting_members, meeting_sessions, session_members, agenda, reports, report_scores, stt_segments, minutes, chat_messages, agent_logs, token_usage_logs, session_summary_blocks, hitl_reviews.
- **Neo4j 온톨로지(코드 재구성)**: 노드 `User, Company, Department, Meetings, Session, Agenda, Minutes, MinutesChunk, Report, ReportChunk, HumanJudgment` / 관계(한글) `간사, 구성원, 소속, 참석, 관할, 발제세션, 담당, 담당부서, 첨부` 등 / 벡터 인덱스 8종(1536d cosine). **유니크 제약 생성 코드 없음.**

---

## 2. 발견된 문제 전체 목록

심각도: 🔴 Critical / 🟠 High / 🟡 Medium / ⚪ Low

### 2.1 보안 (SEC)

| ID | 심각도 | 위치 | 문제 |
|----|------|------|------|
| SEC-1 | 🔴 | `k8s/backend.yaml`, `backend/springboot/.../application.yaml`, `k8s/postgres/deployment.yaml`, `neo4j/k8s/secret.yaml` | DB/Redis/Neo4j 비밀번호, JWT 시크릿이 **평문으로 git에 커밋**됨. 로컬 `.env`에는 실제 OpenAI/LangSmith 키 존재(미커밋이나 유출 시 전체 장악). |
| SEC-2 | 🔴 | `backend/ai/routers/stt.py` (172, 207) | `/api/stt/save`, `/api/stt/transcribe`에 **인증 없음** + 공개 Ingress 노출. 누구나 임의 session_id에 STT 세그먼트 주입/오디오 변환(GC STT 비용 발생) 가능. |
| SEC-3 | 🔴 | `backend/ai/routers/neo4j_graph.py` | 12개 라우트 중 11개(관계/노드 생성·수정·삭제, 회의체 생성·삭제 등)가 **인증 없음** + 공개 Ingress(`/api/neo4j`) 노출. 외부인이 온톨로지 전체를 변조·삭제 가능. |
| SEC-4 | 🔴 | `backend/ai/main.py:121-138`, `websocket_manager.py` | WebSocket(`/ws/meetings/{id}/agenda`, `/ws/sessions/{id}/minutes`) 무인증 — 아무나 회의 실시간 데이터 수신 가능. |
| SEC-5 | 🔴 | Spring 전 서비스 (`ReportService` 등) | **IDOR**: ID만 알면 타인 회의체의 보고서/회의록/아젠다 조회·수정·삭제 가능. 멤버십/소유권 검증은 `MeetingService.validateAdmin`(멤버 관리)에만 존재. |
| SEC-6 | 🔴 | `main.py:96-102`, `SecurityConfig.java:61-71` | CORS `*` + `allowCredentials=true` (양쪽 모두). |
| SEC-7 | 🟠 | `AuthService.java`, `JwtTokenProvider.java` | refresh token이 서버에 저장/회전/폐기되지 않음. **토큰에 type 클레임이 없어 14일짜리 refresh token을 access token으로 사용 가능**. `logout()`은 빈 메서드. |
| SEC-8 | 🟠 | `backend/ai/auth.py`, `routers/auth.py` | FastAPI에 **별도 로그인/가입 경로**: pbkdf2 해시(Spring은 BCrypt — 같은 users 테이블에 두 해시 포맷 혼재, 상호 로그인 불가), access token 유효기간 **7일**. |
| SEC-9 | 🟠 | `k8s/ingress.yaml`, `sync.py`, `NeoSyncService.java:26` | 내부 동기화 API `/api/sync`가 공개 Ingress에 노출, 보호는 정적 `X-Internal-Secret` 하나(기본값이 코드에 하드코딩: `workmaite-internal-secret-2024`). |
| SEC-10 | 🟠 | `supervisor.py:575` | 관리자 판별이 `position in ("대표","CEO","임원")` 문자열 비교. position은 가입 시 사용자가 임의 입력 → **자기 직급을 '대표'로 가입하면 전체 회의체 조회**. RBAC 부재. |
| SEC-11 | 🟠 | `SessionPage.vue:22`, `DetailSidebar.vue:881` | `useMarkdown.js`는 DOMPurify를 쓰지만 SessionPage는 **자체 `renderMd`(sanitize 없음)** 정의, DetailSidebar는 원문 `v-html` → LLM 출력/STT 텍스트 경유 XSS. |
| SEC-12 | 🟡 | `supervisor.py:583-586` | Neo4j 사용자 매칭이 `email OR name` — 동명이인이면 타인 권한으로 회의체 접근 판정. |
| SEC-13 | 🟡 | `SecurityConfig.java:47-48`, `main.py:104` | `/actuator/**`, swagger permitAll, FastAPI `/metrics` 공개, `/grafana` 공개 Ingress. |
| SEC-14 | 🟡 | `backend/ai/routers/upload.py` | 업로드 파일 확장자/콘텐츠 타입 화이트리스트 검증 미흡(파일명 공백치환만). 크기 제한은 Ingress 100m뿐. |

### 2.2 데이터 정합성 (DATA)

| ID | 심각도 | 위치 | 문제 |
|----|------|------|------|
| DATA-1 | 🔴 | `neo4j_sync.py:766` | `retry_failed_syncs()`가 **빈 스텁**(`{"retried":0,...}` 반환). `_log_failure`도 로그만 남김. 즉 **동기화 실패는 영구 유실**되고 주기 재시도 태스크는 아무것도 안 함. 재기동 전체 resync가 유일한 복구 수단. |
| DATA-2 | 🔴 | Spring 전역 (`@EnableAsync` 부재), `MeetingService` 등 | `NeoSyncService`의 `@Async`가 **무효** → 동기 실행. 게다가 `@Transactional` 메서드 **커밋 전**에 호출되어 FastAPI가 PG에서 옛 데이터를 읽는 race + 요청 지연. 실패는 warn 로그 후 무시. |
| DATA-3 | 🔴 | `models.py` vs JPA entity, `application.yaml:31` | **듀얼 ORM 스키마 드리프트**: ddl-auto=none + Flyway/Liquibase 부재 → 스키마의 단일 소스 없음. 예: `HitlReview.status` 기본값 `"검토중"`(Text), Minutes.status `"DRAFT"` vs 소문자 status 혼용(`"ended"/"ENDED"` in 비교), enum이 문자열 컨버터로 양쪽 별도 정의. |
| DATA-4 | 🟠 | `ReportService.deleteReport`, `MinutesService` 등 | 삭제 시 Neo4j 동기화 호출 없음 → **고아 노드**(Report/Minutes/HumanJudgment). `cleanup_deleted_from_pg`는 수동/재기동 시에만. |
| DATA-5 | 🟠 | `neo4j_sync.py` 전체 | Neo4j **유니크 제약 없음** — `MERGE (n {id:...})`가 동시 실행되면 중복 노드 생성 가능. 벡터 인덱스 외 인덱스/제약 생성 코드 없음. |
| DATA-6 | 🟠 | `main.py:38-60`, `sync_all_from_pg` | 매 pod 재시작마다 ① `DETACH DELETE`로 draft Agenda 일괄 삭제(사용자 작업 중 데이터 파괴 가능) ② 전체 테이블 순회 + **전 노드 OpenAI 재임베딩**(비용·기동시간 폭증, 행당 HTTP 1회 직렬). |
| DATA-7 | 🟠 | `models.py` | FK 컬럼 인덱스 전무(`stt_segments.session_id`, `agenda.meeting_id`, `chat_messages.thread_id` 등 — 조회 패턴상 필수). `reports.related_agenda_ids`가 JSON 배열(참조 무결성 없음, 테스터 피드백 "agenda-263으로 뜸"의 근원). `agenda.department`도 JSON. `updated_at`에 `onupdate` 없음. |
| DATA-8 | 🟡 | 전역 | `datetime.utcnow()`(naive, deprecated) + `LocalDateTime.now()`(서버 TZ) 혼용 — 타임존 불일치 위험. Neo4j에는 ISO 문자열로 저장(날짜 연산 불가). |
| DATA-9 | 🟡 | `neo4j_sync.py:416,419` | 관계 타입 오타 `다룸멌`(의도: `다룸`?) — 삭제 대상 매칭이 영구히 실패. |
| DATA-10 | 🟡 | `database.py` | FastAPI(async)에서 **동기 psycopg2** 세션 사용 — 이벤트 루프 블로킹. pool 설정 기본값. |

### 2.3 AI / Agent (AI)

| ID | 심각도 | 위치 | 문제 |
|----|------|------|------|
| AI-1 | 🟠 | `routers/supervisor.py` (2,593줄) | **LangGraph v1 Supervisor 패턴이 아님**: LLM 분류기(`classify_intent`) + 수동 if-분기. 멀티턴 핸드오프/재라우팅 불가, 상태 그래프 없음. 라우팅·컨텍스트 조립·비즈니스 로직·SSE 직렬화가 한 파일에 혼재한 god-file. |
| AI-2 | 🟠 | `agents/*.py` | 에이전트당 도구 2개뿐(검색 2종). 회의체 조회·아젠다 상태 변경·보고서 점수 기록 등이 도구가 아니라 라우터 코드로 박혀 있어 **Tool Calling 설계가 빈약** — supervisor가 데이터를 직접 긁어 프롬프트에 욱여넣는 구조. |
| AI-3 | 🟠 | `supervisor.py:573-598` | AI 데이터 조회 범위 제어가 **라우터별 수동 구현**(meeting_id 접근 체크 1곳). 도구 레벨에서 user/meeting 스코프가 강제되지 않음 — `search_knowledge_graph` 등은 전체 그래프 검색. 멀티테넌트 격리 불가. |
| AI-4 | 🟠 | `prompts.py`, 각 agent | 사용자 업로드 문서/STT 원문을 시스템 프롬프트에 직접 삽입 — **프롬프트 인젝션** 방어 없음(구분자/지시문 무력화 가능). |
| AI-5 | 🟡 | `prompts.py` | 프롬프트가 코드 상수 — 버전 관리/AB 테스트/핫픽스 불가. 라우팅 프롬프트에 키워드 하드코딩(★ 케이스). |
| AI-6 | 🔴(요구사항) | 부재 | **정확도 평가 체계 전무**: 아젠다 추출 정확도, 부서 매칭 유사도, 회의록 품질을 측정할 골든 데이터셋/eval 하네스/회귀 테스트 없음. |
| AI-7 | 🟡 | `make_llm` 류 | LLM 호출에 retry/timeout/max_tokens 미설정(기본값 의존). `neo4j_client.run_cypher` timeout 10s에 매 호출 새 httpx 클라이언트(커넥션 풀 없음). |
| AI-8 | 🟡 | `agent_logging.py:38-51` | 모델 단가 하드코딩(구버전 가격) — 드리프트. STT 비용은 추정 단가. `_finalize`가 동기 DB I/O를 이벤트 루프에서 실행. |
| AI-9 | 🟡 | `classify_intent` | 대화 이력 없이 마지막 메시지 500자만으로 라우팅 — "그거 다시 해줘" 류 후속 발화 오라우팅. |
| AI-10 | ⚪ | 전역 | gpt-4o-mini 단일 모델 — 작업 난이도별 모델 전략(라우팅=mini, 회의록 생성=상위 모델 등) 부재. |
| AI-11 | 🟡 | `supervisor.py` 등 | `print(f"DEBUG: ...")` 10곳, `except Exception` 131곳(상당수 silent pass) — 운영 디버깅 불가. |

### 2.4 STT / 화자분리 (STT)

| ID | 심각도 | 위치 | 문제 |
|----|------|------|------|
| STT-1 | 🔴(품질) | `useSTT.js:2`, `stt.py:_transcribe_cloud` | gcapi 모드: **12초 청크 단위로 독립 diarization** → 화자 태그가 청크마다 리셋(청크1의 화자_1 ≠ 청크2의 화자_1). 회의록의 화자 일관성 근본적으로 붕괴. |
| STT-2 | 🟠 | `stt.py:82` | `model="latest_short"` + 동기 `recognize`(60초/10MB 제한) — 회의 도메인에 부적합. v2 API(chirp_2, 스트리밍/배치) 미사용. 샘플레이트 48000 하드코딩. |
| STT-3 | 🟠 | `stt.py` 전체 | **원본 오디오를 어디에도 저장하지 않음** — STT 실패 시(`except → logger.error → 200 OK 빈 응답`) 발화 영구 유실, 재처리/모델 업그레이드 후 재변환 불가. |
| STT-4 | 🟡 | `app.py(whisperx):69` | align model을 **매 요청마다 로드** — GPU/CPU 낭비, 지연. `batch_size=1`. WhisperX 경로는 화자분리 결과를 버리고 텍스트만 반환(주석상 의도). |
| STT-5 | 🟡 | `stt_segments.speaker_user_id` | 화자 라벨 → 실제 참석자 매핑 자동화 없음(수동 편집 전제). 화자 등록(enrollment)/세션 멤버 음성 매칭 부재. |
| STT-6 | 🟡 | `usage.py` | STT 비용이 분당 추정 단가 — 실제 GC 청구 기반 검증 없음. WLK WebSocket(`/wlk/asr`)도 무인증. |

### 2.5 백엔드 구조 (BE)

| ID | 심각도 | 위치 | 문제 |
|----|------|------|------|
| BE-1 | 🟠 | 부재 | **감사 로그(audit log) 부재**: agent_logs는 AI 활동만. 회의체/보고서/아젠다/구성원 CRUD에 "누가-언제-무엇을" 기록 없음(회사 시스템 요건 미충족). HITL 승인/반려 이력은 hitl_reviews에 일부만. |
| BE-2 | 🟡 | repositories | 목록 API 페이지네이션 없음(`findAllByMeetingId` 등 — 데이터 증가 시 성능 절벽). N+1: `supervisor.py:_get_meeting_context` 멤버별 개별 user 조회. |
| BE-3 | 🟠 | `src/test` | **테스트 사실상 0개**(Spring 1개 컨텍스트 로드 테스트, AI/프론트 0). CI도 테스트 미실행. |
| BE-4 | ⚪ | `backend/workmaite-server/`, `backend/springboot/package-lock.json`, `backend/Dockerfile` | 빌드 잔재/혼동 파일. `reset_db.py` 위험 스크립트 방치. |
| BE-5 | 🟡 | `application.yaml:37` | `show-sql: true` 프로파일 구분 없이 활성(prod 로그 오염 + 데이터 노출). |
| BE-6 | 🟡 | MVC 관점 | Controller→Service는 준수하나, 인가가 Controller/Service 어디에도 일관 적용 안 됨. DTO 검증 `@Valid` 누락 다수. |

### 2.6 프론트엔드 (FE)

| ID | 심각도 | 위치 | 문제 |
|----|------|------|------|
| FE-1 | 🟠 | `ArchivePage.vue`(2,679줄), `SessionPage.vue`(1,658줄), `DetailSidebar.vue`(1,171줄) | 페이지가 상태·API·뷰·모달을 전부 보유한 god-component — Vue 설계 원칙(컴포넌트 분해, composable 추출) 위반. 유지보수 불가 지경. |
| FE-2 | 🟡 | `api.js:134-161` | SSE 프로토콜이 `[PLANNING]`/`[RESULT]`/`[HIGHLIGHT]` 문자열 프리픽스 — LLM 출력에 `data:`/`[DONE]` 포함 시 오동작. SSE `event:` 필드 기반으로 재설계 필요. |
| FE-3 | 🟡 | `auth.js` | 토큰 sessionStorage 보관(XSS 시 탈취 — SEC-11과 결합 시 치명) + 탭마다 재로그인. httpOnly 쿠키 또는 BFF 패턴 검토. |
| FE-4 | ⚪ | `useSTT.js:26,187` | STT fetch에 Authorization 헤더 없음(현재는 서버도 안 받으므로 동작 — SEC-2 수정 시 함께). |
| FE-5 | ⚪ | 전역 | 일부 컴포넌트만 `useMarkdown` 사용(중복 renderMd 구현), CSS가 페이지별 거대 파일(style.css 419줄 + archive/* 1,000줄+), 디자인 토큰 부재. |

### 2.7 인프라/운영 (INFRA)

| ID | 심각도 | 위치 | 문제 |
|----|------|------|------|
| INFRA-1 | 🔴 | `k8s/*.yaml` | 시크릿 평문(SEC-1과 동일 작업으로 처리). |
| INFRA-2 | 🟠 | `k8s/postgres/deployment.yaml` | PostgreSQL이 **Deployment**(StatefulSet 아님), replicas=1, 리소스 limits 없음, **백업/PITR 전무**, PodDisruptionBudget 없음. Neo4j도 동일 계열 리스크. |
| INFRA-3 | 🟠 | `.github/workflows/*` | CI에 **테스트/린트/이미지 스캔 0** — 빌드&푸시만. develop 푸시 즉시 배포(승인 게이트 없음). main 브랜치 미사용. |
| INFRA-4 | 🟡 | 부재 | 알림 룰(Prometheus Alertmanager) 없음 — sync 실패·STT 실패·LLM 오류가 조용히 묻힘(DATA-1과 결합해 치명). |
| INFRA-5 | 🟡 | 부재 | NetworkPolicy 없음(같은 클러스터 교육생 누구나 pod 직접 접근 가능), `/grafana` 공개. |
| INFRA-6 | ⚪ | Dockerfiles | 루트 실행, 헬스체크 없음 (k8s probe는 있음). |

### 2.8 사용자 테스트 피드백 백로그 (UX) — 제3자 테스트 코멘트 정리

> 원 코멘트를 기능 영역별로 분류. (이미 해결된 항목은 확인 후 ✅ 처리할 것)

**아카이브/보고서 검토 흐름**
- [ ] UX-1 `진행중` 클릭 시 AI 검토 결과가 있는 파일/없는 파일 동작 불일치 — 검토 결과 없으면 안내 문구 표시
- [ ] UX-2 검토 결과 없는 파일이 `참고자료`로 바뀌는 동작의 의도 명확화
- [ ] UX-3 보고서 승인 후 "연관 아젠다 연결"이 `agenda-263` 같은 내부 ID로 노출 → 아젠다 제목 표시 (근본 원인: DATA-7 related_agenda_ids JSON)
- [ ] UX-4 "아카이브 등록 완료" 클릭 시 AI 검토 결과 없이 결과 리뷰가 바로 뜨는 흐름 정리
- [ ] UX-5 연관 과제 연결 정보 미표시 — 데이터 없으면 "연관 과제 없음" 표기
- [ ] UX-6 일부 회의록 파일 다운로드 실패 (file_path R2 URL 만료/presign 문제 추정 — `upload.py`/`r2_storage.py` 확인)
- [ ] UX-7 회의록 생성 전 아카이브 저장 → 실패 팝업 후 "저장됨" 메시지 (에러 핸들링 순서 버그)
- [ ] UX-8 Word 다운로드 버튼 제거(PDF만 사용하기로 결정됨)
- [ ] UX-9 `회의록` 탭의 파일 업로드 존재 이유 정리
- [ ] UX-10 회의록 자동 생성 상태에서 "생성" 버튼 역할 불명확

**아젠다/과제**
- [ ] UX-11 아젠다가 전부 팀에 연결됨 — 회의에서 나온 아젠다는 회의(세션)에 연결되는 온톨로지 구조 재검토 (AI-2/온톨로지 설계와 연동)
- [ ] UX-12 실행 완료된 아젠다의 아카이브 노출/과거 아젠다 조회 경로 정의
- [ ] UX-13 팀별 과제 묶음 보기, 마감일/중요도 정렬 추가
- [ ] UX-14 과제 수정 → 확인 → 수정 사유 입력 순서 어색 (사유 입력을 확인 전에)
- [ ] UX-15 승인 버튼 과다 노출 정리, 아젠다 편집의 우선순위 명칭 수정
- [ ] UX-16 과제 선정 사유(ai_evidence) 함께 표시

**그래프 뷰**
- [ ] UX-17 관계가 너무 많아 전체 구조 파악 어려움 — 관계 타입 필터/그룹핑
- [ ] UX-18 연결관계 목록·관계 추가 목록 단순화
- [ ] UX-19 노드 선택 후 관계 추가 시 선택 노드를 출발 노드로 자동 지정
- [ ] UX-20 회의 순서(세션 타임라인) 시각화

**회의체/목록**
- [ ] UX-21 회의체명/유형 클릭 시 정렬 여부 명확화 (정렬 아이콘)
- [ ] UX-22 "이력"이 파일 개수인지 변경 이력인지 라벨 명확화
- [ ] UX-23 `내 회의체 전체` 클릭 동작, 참여 회의체 1개인데 `+2개 더보기` 표시 버그
- [ ] UX-24 검색 옆 자물쇠 아이콘 → "조직 데이터 조회 범위" 의미가 전달되도록 툴팁/라벨
- [ ] UX-25 구성원 추가의 `비밀번호` 필드 의미 명확화(임시 비밀번호?), 구성원 정보 수정 권한 제한(SEC-5와 연동)

**세션/녹음**
- [ ] UX-26 녹음 시작 없이 "기록 종료" 눌러도 화면 전환되는 상태 가드 추가

---

## 3. 단계별 개선 계획

### Phase 0 — 비상 보안 조치 (즉시, 1–2일) 🔴
목표: 외부에서 악용 가능한 구멍부터 차단. 코드 변경 최소.

- [ ] P0-1 **유출 키 회전**: OpenAI/LangSmith 키, JWT_SECRET, INTERNAL_SECRET, DB/Redis/Neo4j 비밀번호 전부 재발급. (git 히스토리에 .env는 없지만 k8s yaml/application.yaml의 비번은 히스토리에 있음)
- [ ] P0-2 **시크릿을 k8s Secret으로 이전**: `k8s/backend.yaml`의 env 평문 → `secretKeyRef`. `application.yaml`은 `${ENV}` 참조로 변경, `neo4j/k8s/secret.yaml` git 제거(또는 SealedSecrets/SOPS).
- [ ] P0-3 **무인증 라우터 봉쇄**: `stt.py` 2개, `neo4j_graph.py` 11개 라우트에 `Depends(get_current_user)` 추가. WebSocket 2개 + WLK에 토큰 검증(쿼리파라미터/서브프로토콜) 추가. `useSTT.js`에 Authorization 헤더 추가.
- [ ] P0-4 **`/api/sync`를 공개 Ingress에서 제거** (클러스터 내부 Service 호출만 허용). `/grafana`, `/metrics`, actuator 접근 제한.
- [ ] P0-5 CORS 화이트리스트로 교체 (`https://workmaite.project.skala-ai.com` + 로컬 dev).
- [ ] P0-6 XSS 차단: `SessionPage.vue` renderMd를 `useMarkdown`으로 교체, `DetailSidebar.vue:881` v-html sanitize.
- [ ] P0-7 시작 시 `_cleanup_stale_neo4j_nodes`의 `DETACH DELETE` 제거 또는 안전 조건으로 축소.

### Phase 1 — 인증/인가 통합 (1주) 🔴
목표: "누가 무엇을 볼 수 있는가"의 단일 모델 확립. AI 데이터 범위 정의의 토대.

- [ ] P1-1 인증 발급 주체를 **Spring으로 일원화**: FastAPI `routers/auth.py`(signup/login) 제거, FastAPI는 검증만. pbkdf2/BCrypt 혼재 해소(기존 pbkdf2 사용자 마이그레이션 또는 재설정).
- [ ] P1-2 JWT에 `type`(access/refresh) 클레임 추가, refresh는 Redis 저장+회전+로그아웃 시 폐기(이미 Redis 인프라 있음 — AuthService 주석의 계획 실행).
- [ ] P1-3 **RBAC 도입**: users에 `role`(SYSTEM_ADMIN 등) 컬럼 추가, position 문자열 판별(`supervisor.py:575`) 제거. 회의체 수준 권한은 meeting_members.role 사용.
- [ ] P1-4 **멤버십 가드 공통화**: Spring에 `@PreAuthorize` 또는 AOP `MeetingAccessGuard`(meetingId/reportId/sessionId → 멤버십 검증) 도입, 전 컨트롤러 적용. FastAPI에 동일한 `require_meeting_member(meeting_id)` dependency 작성 후 meetings/sessions/upload/supervisor 전 라우트 적용.
- [ ] P1-5 Neo4j 사용자 매칭을 email/name → `pg_id` 단일 키로 통일 (SEC-12).
- [ ] P1-6 **감사 로그 도입**(BE-1): `audit_logs` 테이블 (§4 마이그레이션) + Spring AOP(@AuditLogged) / FastAPI 미들웨어로 CRUD·승인·로그인 기록.

### Phase 2 — DB 스키마/정합성 (1주) 🟠
목표: 스키마 단일 소스 + PG↔Neo4j 동기화를 신뢰 가능하게.

- [ ] P2-1 **Flyway 도입**: 현재 운영 스키마를 `V1__baseline.sql`로 베이스라인, 이후 모든 변경은 마이그레이션으로. SQLAlchemy `models.py`는 읽기 전용 매핑으로 선언(스키마 생성 금지 — 주인은 Flyway).
- [ ] P2-2 `V2__indexes_constraints.sql` 적용 (§4.1 초안) — FK 인덱스, NOT NULL, status CHECK.
- [ ] P2-3 `V3__audit_and_sync.sql` (§4.2) — `audit_logs`, `neo4j_sync_failures`(아웃박스) 테이블.
- [ ] P2-4 **동기화 재설계(아웃박스 패턴)**: Spring은 트랜잭션 안에서 `neo4j_sync_outbox`에 행만 기록 → 커밋 후 폴러(또는 `@TransactionalEventListener(AFTER_COMMIT)` + `@EnableAsync`)가 FastAPI 호출 → 실패 시 행 유지, `retry_failed_syncs`를 **실제 구현**(아웃박스 재처리). 삭제 전파(DATA-4) 포함.
- [ ] P2-5 Neo4j 유니크 제약 생성 (§4.3 Cypher) + `다룸멌` 오타 수정 + 기존 중복 노드 정리 쿼리.
- [ ] P2-6 임베딩 재계산 방지: 노드에 `content_hash` 저장, 변경 시에만 임베딩 호출. 시작 시 전체 resync는 옵션 플래그로(기본 off), 변경분만 동기화.
- [ ] P2-7 datetime을 timezone-aware(UTC)로 통일 (`datetime.now(timezone.utc)` / `Instant`), Neo4j에는 epoch 또는 ISO-8601+TZ.
- [ ] P2-8 related_agenda_ids JSON → `report_agendas` 조인 테이블 (§4.2) — UX-3/5의 근본 해결.

### Phase 3 — AI 아키텍처 재설계 (2주) 🟠
목표: LangGraph v1 Supervisor 패턴 + 도구 중심 설계 + 데이터 범위 강제.

- [ ] P3-1 `supervisor.py` 해체: `routers/`(HTTP/SSE만) / `graphs/`(LangGraph 정의) / `tools/`(도구) / `services/`(DB 접근) 레이어 분리. 파일당 500줄 이하 목표.
- [ ] P3-2 **Supervisor 그래프 전환**: `langgraph-supervisor`(또는 StateGraph + handoff tool) 기반 — supervisor가 도구 호출로 sub-agent에 위임, 결과 보고 후 재라우팅 가능. `classify_intent` 제거. 대화 이력은 그래프 state(checkpointer)로(AI-9 해결).
- [ ] P3-3 **도구 확충 + 스코프 강제**: 각 도구가 `RunnableConfig`로 `user_id`/허용 `meeting_ids`를 받아 쿼리에 강제 주입(WHERE meeting_id IN ...). 읽기 도구(회의체 현황, 아젠다 목록, 보고서 현황, 그래프 검색)와 쓰기 도구(아젠다 상태 변경 등 — HITL interrupt 필수) 분리. AI가 접근 가능한 데이터 범위를 `docs/ai-data-scope.md`로 문서화.
- [ ] P3-4 프롬프트 정비: 사용자 콘텐츠는 명시적 구분자+"문서 내 지시 무시" 가드, 출력 스키마는 전부 structured output으로. 프롬프트를 `prompts/` 디렉토리 파일(또는 DB)로 분리해 버전 관리.
- [ ] P3-5 LLM 클라이언트 공통화: `_make_llm` 4중복 제거 → `llm_factory(task_profile)` (retry=2, timeout, max_tokens, 작업별 모델 선택). `run_cypher`에 공유 httpx 클라이언트 풀.
- [ ] P3-6 `print` 제거, 로깅 표준화(structlog/JSON), `except Exception` 정리(삼킨 곳에 최소 logger.exception + 메트릭).

### Phase 4 — STT/화자분리 품질 (1주) 🟠
- [ ] P4-1 **청크 diarization 폐기**: gcapi를 v2 `StreamingRecognize`(또는 긴 녹음은 GCS 업로드 + batch `latest_long`/chirp) 로 전환해 세션 전체에 일관된 화자 태그 확보. 불가하면 WhisperX(전구간 pyannote) 경로를 기본으로.
- [ ] P4-2 **원본 오디오 보존**: 청크를 R2에 append 저장(`sessions/{id}/audio/...`), 실패 시 재처리 큐. 보존 기간 정책(예: 회의록 확정 후 30일) 문서화 — 개인정보 관점 필수.
- [ ] P4-3 STT 실패를 사용자에게 노출(에러 응답 + 프론트 재시도 UI), 5xx 시 provider 폴백 체인(gcapi→whisperx).
- [ ] P4-4 whisperx: align model 시작 시 1회 로드, batch_size 조정, 요청 큐(동시 1) 보호.
- [ ] P4-5 화자→사용자 매핑 보조: 세션 멤버 목록 기반 라벨 지정 UI 개선 + (선택) 화자 임베딩 기반 자동 제안.
- [ ] P4-6 STT 정확도 측정: 테스트 음성(대본 있는 회의 녹음) WER/화자 DER 측정 스크립트 작성, provider별 비교 리포트.

### Phase 5 — 관측성/비용/알림 (3–4일) 🟡
- [ ] P5-1 기능별 시간 측정: agent_logs에 `duration_ms`(ended_at-created_at) 활용 + Prometheus 히스토그램(에이전트별/도구별). Grafana 대시보드(라우팅 분포, 에이전트 지연, 토큰/비용 일별).
- [ ] P5-2 Alertmanager 룰: sync outbox 적체, STT 실패율, LLM 에러율, 5xx, pod 재시작.
- [ ] P5-3 비용: 가격표를 설정 파일로 외출 + 월별 비용 리포트 API(이미 usage.py 토대 있음), STT 분 단위 실측 로그.
- [ ] P5-4 PostgreSQL/Neo4j 백업 CronJob(pg_dump → R2, neo4j-admin dump), 복구 리허설 문서.

### Phase 6 — 정확도 평가 체계 (병행, 1주) 🟠
- [ ] P6-1 골든 데이터셋: 회의록/보고서 샘플 10–20건에 대해 기대 아젠다·부서·요약 라벨링(`eval/dataset/`).
- [ ] P6-2 eval 하네스(`eval/run_eval.py`): 아젠다 추출 P/R/F1(제목 임베딩 유사도 ≥0.85 매칭), 부서 매칭 정확도, 회의록 LLM-judge 루브릭 점수. 결과를 JSON으로 저장해 프롬프트/모델 변경 시 회귀 비교.
- [ ] P6-3 CI에 스모크 eval(소형 5건) 추가 — 프롬프트 변경 PR에서 자동 실행.

### Phase 7 — 코드 품질/구조/UX (지속)
- [ ] P7-1 프론트 분해: ArchivePage → `archive/` 하위 15개 내외 컴포넌트+composable(목록/검토패널/모달별), SessionPage → 녹음/스크립트/회의록/채팅 4분할. Pinia store로 서버 상태 정리.
- [ ] P7-2 SSE 프로토콜을 `event:` 필드 기반으로 재설계(FE-2), 스트림 파서 공통화.
- [ ] P7-3 §2.8 UX 백로그 26건 처리(우선: UX-3/5/6/7 — 데이터 신뢰 관련).
- [ ] P7-4 테스트: Spring 서비스 단위테스트(인가 가드 포함), FastAPI 라우터 테스트(httpx), 프론트 핵심 composable 테스트. CI에 테스트+린트 게이트 추가.
- [ ] P7-5 잔재 정리: `backend/workmaite-server/`, `backend/Dockerfile`(루트), `springboot/package-lock.json`, `reset_db.py` 안전장치, 미사용 코드.
- [ ] P7-6 k8s: 리소스 requests/limits 전 deployment, PDB, NetworkPolicy, postgres StatefulSet 전환.

**의존 관계**: P0 → P1 → (P2 ∥ P3) → P4, P5/P6은 P2 이후 병행 가능, P7은 상시.

---

## 4. DB 마이그레이션 초안

> Flyway 도입(P2-1) 후 적용. 실제 운영 스키마와 대조(`\d` 출력) 후 컬럼명/타입 확정 필요 — 아래는 코드 기준 재구성본.

### 4.1 `V2__indexes_constraints.sql`
```sql
-- FK/조회 패턴 기반 인덱스 (코드의 WHERE/ORDER BY에서 도출)
CREATE INDEX IF NOT EXISTS idx_meeting_members_meeting   ON meeting_members(meeting_id);
CREATE INDEX IF NOT EXISTS idx_meeting_members_user      ON meeting_members(user_id);
CREATE INDEX IF NOT EXISTS idx_meeting_sessions_meeting  ON meeting_sessions(meeting_id, status);
CREATE INDEX IF NOT EXISTS idx_agenda_meeting_status     ON agenda(meeting_id, status);
CREATE INDEX IF NOT EXISTS idx_agenda_session             ON agenda(session_id);
CREATE INDEX IF NOT EXISTS idx_reports_meeting           ON reports(meeting_id);
CREATE INDEX IF NOT EXISTS idx_reports_parent            ON reports(parent_id);
CREATE INDEX IF NOT EXISTS idx_report_scores_report      ON report_scores(report_id);
CREATE INDEX IF NOT EXISTS idx_stt_segments_session      ON stt_segments(session_id, start_sec);
CREATE INDEX IF NOT EXISTS idx_minutes_session           ON minutes(session_id);
CREATE INDEX IF NOT EXISTS idx_chat_messages_thread      ON chat_messages(thread_id, created_at);
CREATE INDEX IF NOT EXISTS idx_agent_logs_meeting        ON agent_logs(meeting_id, created_at);
CREATE INDEX IF NOT EXISTS idx_agent_logs_context        ON agent_logs(context_type, created_at);
CREATE INDEX IF NOT EXISTS idx_token_usage_agent_log     ON token_usage_logs(agent_log_id);
CREATE INDEX IF NOT EXISTS idx_session_members_session   ON session_members(session_id);
CREATE INDEX IF NOT EXISTS idx_hitl_reviews_report       ON hitl_reviews(report_id);
CREATE INDEX IF NOT EXISTS idx_hitl_reviews_agenda       ON hitl_reviews(agenda_id);

-- 정합성 제약 (운영 데이터 위반 여부 먼저 점검 후 적용)
ALTER TABLE session_members ADD CONSTRAINT uq_session_members UNIQUE (session_id, user_id);
ALTER TABLE agenda    ADD CONSTRAINT ck_agenda_status   CHECK (status IN ('draft','todo','in_progress','done','archived'));  -- 실제 사용값 확인 후 확정
ALTER TABLE reports   ADD CONSTRAINT ck_reports_human_status CHECK (human_status IN ('pending','approved','rejected','reference'));
-- status 값 표준화 선행 필요: meeting_sessions.status 'ended'/'ENDED' 혼용 → UPDATE 후 CHECK
```

### 4.2 `V3__audit_and_sync.sql`
```sql
-- 감사 로그 (P1-6)
CREATE TABLE IF NOT EXISTS audit_logs (
    id          BIGSERIAL PRIMARY KEY,
    actor_id    BIGINT REFERENCES users(id),
    action      VARCHAR(40)  NOT NULL,          -- CREATE/UPDATE/DELETE/APPROVE/LOGIN/...
    entity_type VARCHAR(40)  NOT NULL,          -- meeting/report/agenda/minutes/member/...
    entity_id   BIGINT,
    meeting_id  BIGINT,
    detail      JSONB,                          -- 변경 전후 diff 요약
    ip_addr     VARCHAR(45),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_audit_logs_actor  ON audit_logs(actor_id, created_at);
CREATE INDEX idx_audit_logs_entity ON audit_logs(entity_type, entity_id);

-- Neo4j 동기화 아웃박스 (P2-4, DATA-1/2 해결)
CREATE TABLE IF NOT EXISTS neo4j_sync_outbox (
    id           BIGSERIAL PRIMARY KEY,
    entity_type  VARCHAR(30) NOT NULL,          -- user/meeting/session/agenda/minutes/report/member/...
    entity_id    BIGINT      NOT NULL,
    op           VARCHAR(10) NOT NULL,          -- upsert/delete
    payload      JSONB,
    status       VARCHAR(15) NOT NULL DEFAULT 'pending',  -- pending/done/failed
    retry_count  INT         NOT NULL DEFAULT 0,
    last_error   TEXT,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    processed_at TIMESTAMPTZ
);
CREATE INDEX idx_sync_outbox_pending ON neo4j_sync_outbox(status, created_at) WHERE status <> 'done';

-- 보고서-아젠다 연결 정규화 (P2-8, UX-3/5)
CREATE TABLE IF NOT EXISTS report_agendas (
    report_id BIGINT NOT NULL REFERENCES reports(id) ON DELETE CASCADE,
    agenda_id BIGINT NOT NULL REFERENCES agenda(id)  ON DELETE CASCADE,
    PRIMARY KEY (report_id, agenda_id)
);
-- 데이터 이행: INSERT INTO report_agendas SELECT id, jsonb_array_elements_text(related_agenda_ids)::bigint FROM reports WHERE related_agenda_ids IS NOT NULL; (값 형식 'agenda-263' 여부 확인 후 파싱)

-- RBAC (P1-3)
ALTER TABLE users ADD COLUMN IF NOT EXISTS role VARCHAR(20) NOT NULL DEFAULT 'USER';  -- USER/ADMIN
```

### 4.3 Neo4j 제약 (P2-5) — `neo4j/migrations/001_constraints.cypher`
```cypher
CREATE CONSTRAINT user_pg_id    IF NOT EXISTS FOR (u:User)          REQUIRE u.pg_id IS UNIQUE;
CREATE CONSTRAINT meetings_id   IF NOT EXISTS FOR (m:Meetings)      REQUIRE m.id    IS UNIQUE;
CREATE CONSTRAINT session_id    IF NOT EXISTS FOR (s:Session)       REQUIRE s.id    IS UNIQUE;
CREATE CONSTRAINT agenda_id     IF NOT EXISTS FOR (a:Agenda)        REQUIRE a.id    IS UNIQUE;
CREATE CONSTRAINT minutes_id    IF NOT EXISTS FOR (m:Minutes)       REQUIRE m.id    IS UNIQUE;
CREATE CONSTRAINT report_id     IF NOT EXISTS FOR (r:Report)        REQUIRE r.id    IS UNIQUE;
CREATE CONSTRAINT hj_id         IF NOT EXISTS FOR (h:HumanJudgment) REQUIRE h.id    IS UNIQUE;
CREATE CONSTRAINT dept_name     IF NOT EXISTS FOR (d:Department)    REQUIRE d.name  IS UNIQUE;
CREATE CONSTRAINT company_name  IF NOT EXISTS FOR (c:Company)       REQUIRE c.name  IS UNIQUE;
// 적용 전 중복 노드 점검: MATCH (n:Agenda) WITH n.id AS id, count(*) AS c WHERE c > 1 RETURN id, c;
// 오타 관계 정리: MATCH ()-[r:`다룸멌`]->() DELETE r;  (의도된 타입 확인 후)
```

---

## 5. 핵심 리스크 Top 5 (경영 요약)

1. **외부 공격 표면**(SEC-2/3/4 + SEC-1): 무인증 공개 API로 온톨로지 변조·회의 데이터 절취·비용 발생 공격이 지금 가능. → Phase 0.
2. **권한 모델 부재**(SEC-5/10): 사내 사용자 간 데이터 격리가 사실상 없음 — "AI 조회 범위" 이전에 API 조회 범위부터 뚫려 있음. → Phase 1.
3. **동기화 신뢰성**(DATA-1/2/4): GraphRAG의 근간인 그래프가 조용히 어긋나며, 복구 수단이 재기동뿐(그마저 비용 폭탄 DATA-6). → Phase 2.
4. **화자분리 구조 결함**(STT-1/3): 12초 청크 diarization으로는 "누가 말했나"가 원리적으로 부정확하고, 원음 미보존으로 복구 불가. → Phase 4.
5. **품질 측정 불가**(AI-6, BE-3): 정확도 지표·테스트·알림이 없어 개선/회귀를 알 수 없음. → Phase 5/6.

---

## 6. 후속 작업용 프롬프트 모음

각 프롬프트를 새 Claude Code 세션에 붙여 사용. 공통 머리말: **"Plan.md를 읽고 아래 작업을 수행해. 완료 후 Plan.md의 해당 체크박스를 갱신하고 변경 요약을 항목 아래 추가해."**

### 6.1 Phase 0 (보안 응급조치)
```
Plan.md §3 Phase 0을 수행해줘. 순서:
1. k8s/backend.yaml·ai.yaml의 평문 자격증명을 k8s Secret(secretKeyRef) 참조로 바꾸고, secret 생성용 템플릿(k8s/secrets.example.yaml)을 만들어 실값은 placeholder로 둬. application.yaml의 비밀번호/JWT 시크릿은 환경변수 참조(${DB_PASSWORD} 등)로 교체.
2. backend/ai/routers/stt.py 전체 라우트와 neo4j_graph.py의 무인증 라우트 11개에 get_current_user 의존성을 추가하고, 프론트(useSTT.js 등) 호출부에 Authorization 헤더를 추가해.
3. main.py의 WebSocket 2개에 토큰 검증(query param token → auth.get_current_user 로직 재사용)을 추가해.
4. k8s/ingress.yaml에서 /api/sync 경로를 제거하고, FastAPI CORS와 SecurityConfig CORS를 도메인 화이트리스트로 교체해.
5. SessionPage.vue의 자체 renderMd를 composables/useMarkdown.js로 교체하고 DetailSidebar.vue:881의 v-html을 sanitize해.
6. main.py의 _cleanup_stale_neo4j_nodes에서 draft Agenda DETACH DELETE를 제거해.
주의: 기존 동작(로컬 개발 port-forward 흐름) 깨지지 않게 .env.example도 갱신. 키 회전(P0-1)은 사람이 해야 하니 회전 대상 목록만 SECURITY_ROTATION.md로 정리해줘.
```

### 6.2 Phase 1 (인증/인가 통합)
```
Plan.md §3 Phase 1을 수행해줘. 핵심:
- FastAPI routers/auth.py의 signup/login 제거(검증 전용으로 축소), Spring AuthService에 JWT type 클레임(access/refresh) 추가 + JwtAuthenticationFilter에서 access만 허용, refresh는 Redis 저장·회전·logout 폐기 구현.
- users.role 컬럼 추가(마이그레이션은 Plan.md §4.2 참조), supervisor.py:575의 position 문자열 admin 판별을 role 기반으로 교체.
- Spring에 meetingId 기반 멤버십 검증 AOP/유틸을 만들어 Report/Minutes/Agenda/Script/Session 컨트롤러 전체에 적용(IDOR 차단). FastAPI에는 require_meeting_member dependency를 만들어 meetings/sessions/upload/supervisor 라우트에 적용.
- audit_logs 테이블(§4.2)과 Spring AOP 기반 감사 로깅(@AuditLogged), FastAPI 미들웨어 감사 로깅을 추가.
완료 후 침투 시나리오(타인 reportId 조회, refresh로 API 호출, position='대표' 가입)가 차단되는지 테스트 코드로 증명해줘.
```

### 6.3 Phase 2 (스키마/동기화)
```
Plan.md §3 Phase 2와 §4 마이그레이션을 수행해줘.
- Spring에 Flyway 추가(baseline-on-migrate), V1은 현 스키마 베이스라인(JPA 엔티티에서 생성하되 운영 DB와 대조 필요 항목은 주석으로 표시), V2/V3는 Plan.md §4.1·4.2 초안 기반.
- neo4j_sync_outbox 기반 아웃박스 패턴 구현: Spring @TransactionalEventListener(AFTER_COMMIT)+@EnableAsync로 outbox 기록·발송, FastAPI retry_failed_syncs(neo4j_sync.py:766 스텁)를 outbox 재처리로 실구현, 삭제 전파(Report/Minutes 삭제 → Neo4j) 추가.
- Neo4j 유니크 제약(§4.3) 적용 코드를 init_vector_index 옆에 추가하고, `다룸멌` 오타를 수정해.
- 임베딩 content_hash 캐싱으로 시작 시 전체 재임베딩을 제거(변경분만), startup 전체 resync는 env 플래그 기본 off.
```

### 6.4 Phase 3 (LangGraph Supervisor 재설계)
```
Plan.md §3 Phase 3을 수행해줘. routers/supervisor.py(2,593줄)를 해체해서:
- ai/graphs/supervisor_graph.py: LangGraph v1 Supervisor 패턴(supervisor가 handoff tool로 task_extractor/minutes_generator/report_reviewer/knowledge_manager에 위임, MessagesState+checkpointer로 멀티턴 유지). 기존 classify_intent 제거.
- ai/tools/: 회의체 현황 조회, 아젠다 목록/상태, 보고서 제출 현황, 그래프 검색, 이전 회의록 검색 등을 @tool로 추출하되 모든 도구가 config의 user_id·allowed_meeting_ids로 쿼리를 강제 스코핑하게 해(임의 meeting 접근 불가 증명 테스트 포함).
- routers/는 SSE 변환만 담당하게 축소. 기존 SSE 이벤트 포맷([PLANNING] 등)은 프론트 호환을 위해 어댑터로 유지.
- prompts.py를 ai/prompts/ 파일들로 분리, 사용자 콘텐츠 삽입부에 인젝션 가드 구분자 적용, make_llm 4중복을 llm_factory로 통합(retry/timeout/작업별 모델).
기존 기능(아카이브 분석, 회의록 생성, HITL 검토)의 동작 동등성을 유지하고, 토큰 로깅(agent_logging)이 계속 작동하는지 확인해.
```

### 6.5 Phase 4 (STT 품질)
```
Plan.md §3 Phase 4를 수행해줘.
- stt.py의 gcapi 경로를 세션 단위 일관 화자분리로 재설계: 녹음 청크를 R2에 누적 저장하고, (a) Google STT v2 스트리밍 또는 (b) 세션 종료 시 전체 오디오 배치 diarization(latest_long) 중 가능한 쪽으로 구현. 12초 청크별 독립 diarization은 제거.
- STT 실패 시 5xx와 에러 메시지를 반환하고 프론트(useSTT.js)에 재시도/알림 UI를 추가. provider 폴백 체인(gcapi 실패→localwhisper) 구현.
- whisperx app.py의 align model을 시작 시 1회 로드로 변경.
- STT 사용량(provider, 오디오 초)을 DB에 실측 기록해 usage.py 비용 추정을 실측 기반으로 교체.
- eval: 테스트 오디오에 대한 WER/화자 정확도 측정 스크립트(eval/stt_eval.py)를 작성해.
```

### 6.6 Phase 6 (정확도 평가)
```
Plan.md §3 Phase 6을 수행해줘. eval/ 디렉토리에:
- dataset/: 회의록·보고서 샘플과 기대 결과(아젠다 목록, 담당 부서, 요약) JSON 스키마 정의 + 샘플 3건 작성(내용은 가상의 회의).
- run_eval.py: archive_extract_agendas와 동일 경로를 호출해 추출 결과를 기대값과 비교 — 아젠다 P/R/F1(임베딩 유사도 매칭), 부서 정확도, (회의록은 LLM-judge 루브릭 1-5점). 결과를 eval/results/{date}.json으로 저장하고 직전 결과와 회귀 비교 리포트 출력.
- .github/workflows에 프롬프트 파일 변경 시 스모크 eval을 실행하는 잡 추가(OPENAI_API_KEY는 secrets).
```

### 6.7 Phase 7 (프론트 분해 + UX 백로그)
```
Plan.md §2.8 UX 백로그와 §3 P7-1~3을 수행해줘. 우선순위:
1. UX-3/5: related_agenda_ids의 'agenda-N' ID 노출을 아젠다 제목 표시로 교체, 데이터 없으면 '연관 과제 없음' 표기.
2. UX-6/7: 회의록 다운로드 실패 원인(R2 presigned URL 흐름) 추적·수정, 아카이브 저장의 실패 팝업→성공 메시지 순서 버그 수정.
3. ArchivePage.vue(2,679줄)를 archive/ 하위 컴포넌트와 composable로 분해(목록/필터/검토패널/모달/그래프 연동), SessionPage.vue(1,658줄)를 녹음·스크립트·회의록·채팅 4영역으로 분해. 동작 동등성 유지, 단계별 커밋.
4. 나머지 UX 항목을 작은 PR 단위로 처리하고 Plan.md 체크박스 갱신.
```

---

## 7. 진행 현황

- [x] 전수 감사 완료 (2026-06-12) — 본 문서 작성
- [ ] Phase 0 보안 응급조치
- [ ] Phase 1 인증/인가 통합
- [ ] Phase 2 스키마/동기화
- [ ] Phase 3 AI 재설계
- [ ] Phase 4 STT 품질
- [ ] Phase 5 관측성/비용
- [ ] Phase 6 평가 체계
- [ ] Phase 7 코드 품질/UX
