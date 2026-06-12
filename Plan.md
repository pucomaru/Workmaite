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

- **AI 오케스트레이션**: `routers/supervisor.py`(2,593줄)가 LLM 구조화 출력으로 intent 분류(`classify_intent`) 후 if-분기로 4개 에이전트(`task_extractor`, `minutes_generator`, `report_reviewer`, `knowledge_manager`)에 위임. 각 에이전트는 `create_react_agent` + 도구 2개씩. **모든 그래프가 checkpointer 없이 compile**되며(HITL `interrupt()` 사용처 포함), 채팅 그래프 thread_id는 요청마다 `uuid4()`. LangSmith 트레이싱은 `main.py`에서 강제 비활성화. 대화 이력은 프론트가 `/api/chats`로 직접 저장하고 서버는 최근 20개를 raw replay.
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
| DATA-2 | 🔴 | `NeoSyncService.java`, `MeetingService` 등 | ~~`@EnableAsync` 부재~~(정정: `AppConfig.java:12`에 존재 — 초기 진단 오류). 실제 문제: `@Transactional` 메서드 **커밋 전**에 sync가 발사되어 FastAPI가 PG에서 옛 데이터를 읽는 race. 실패는 warn 로그 후 무시(재시도 없음). **→ 2026-06-12 afterCommit+TaskExecutor 구조로 race 해소(코드 반영). 재시도/유실 방지는 여전히 outbox 필요(P2-4).** |
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
| BE-2 | 🟡 | repositories | 목록 API 페이지네이션 없음(`findAllByMeetingId` 등 — 데이터 증가 시 성능 절벽). N+1: `supervisor.py:_get_meeting_context` 멤버별 개별 user 조회. → **§2.13(PG-1~10)으로 전수 상세화, Phase 8로 작업화.** |
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
- [ ] UX-24 검색 옆 자물쇠 아이콘 → "조직 데이터 조회 범위" 의미가 전달되도록 툴팁/라벨 (실제 범위 구현은 §2.12 MT-5/P1-7)
- [ ] UX-25 구성원 추가의 `비밀번호` 필드 의미 명확화, 구성원 정보 수정 권한 제한 → **근본 원인·해결 설계는 §2.12(MT-1·MT-2)/P1-7** — 초대 기반 온보딩으로 비밀번호 필드 자체를 제거하는 방향

**세션/녹음**
- [ ] UX-26 녹음 시작 없이 "기록 종료" 눌러도 화면 전환되는 상태 가드 추가

### 2.9 Agentic 하네스 / 챗봇 서비스 갭 분석 (H) — 실서비스 관점 추가 감사

> 최신 agentic workflow 원칙(단순 루프 + 잘 설계된 도구, context engineering, durable execution, eval-driven)과
> 챗봇 서비스 원칙(신뢰 가능한 출력, 피드백 루프, 스트림 제어, 비용 가드)에 비춘 갭.

| ID | 심각도 | 위치 | 문제 |
|----|------|------|------|
| H-1 | 🔴 | `report_reviewer.py:185-192,284-318`, `task_extractor.py:178,260-291` | **checkpointer 없이 `interrupt()`/`get_state()`/`Command(resume)` 사용** — `builder.compile()`에 체크포인터가 없어 HITL 일시정지·재개가 동작하지 않거나(런타임 오류) 동작해도 프로세스 메모리 한정. pod 재시작/스케일아웃 시 진행 중인 검토·추출 승인 흐름 전부 유실. **테스터 피드백 UX-1("검토 결과가 안 나오는 파일이 있음")의 유력한 근본 원인 — 최우선 검증 대상.** |
| H-2 | 🔴 | `report_reviewer.py:166-176, 268-281` | LLM 응답을 `re.search(r'\{.*\}')`로 긁어 JSON 파싱하고, **실패하면 score=50짜리 가짜 검토 결과를 조작 생성**해 사용자에게 AI 검토 결과인 것처럼 노출. 신뢰가 생명인 사내 검토 시스템에서 치명적. `with_structured_output`(이미 라우팅에선 사용 중)을 쓰지 않는 이유가 없음. 실패는 실패로 노출+재시도가 원칙. |
| H-3 | 🟠 | `main.py:14-16` | `LANGCHAIN_TRACING_V2=false` 강제 — **에이전트 실행 트레이스 0**. 어떤 도구가 왜 호출됐는지, 어디서 느려졌는지 재현 불가. agent_logs(요약)만으로는 하네스 디버깅·오프라인 평가 불가능. **→ 2026-06-12 부분 해소: env 제어화(키+`LANGSMITH_TRACING=true` 시 활성). 키 회전(P0-1) 후 활성화하고 trace_id 연계는 P3A-3.** |
| H-4 | 🟠 | `routers/chat_history.py`, `supervisor.py:619-633` | 대화 이력의 기록 주체가 **클라이언트**(`POST /api/chats`로 agent role 메시지도 저장 가능 → 위조·오염) + supervisor는 별도 thread_id 체계로 저장 — 이력 저장이 이원화. 서버가 권위 있는 대화 저장소여야 함. |
| H-5 | 🟠 | `report_reviewer.py:206,239` 등 chat_stream 전부 | 그래프 호출마다 `thread_id=uuid4()` — 체크포인터 기반 스레드 연속성을 포기하고 매 턴 클라이언트 이력 재주입. 멀티턴 도구 상태(이전 검색 결과 등) 유실, 토큰 중복 과금. |
| H-6 | 🟠 | `prompts.py`, `supervisor.py` 컨텍스트 조립부 | **컨텍스트 사전 주입(pre-stuffing) 패턴**: 회의체 정보·아젠다·이전 회의록을 전부 시스템 프롬프트에 욱여넣음 → ① 시스템 프롬프트가 매 요청 달라져 **프롬프트 캐시 적중 불가** ② 토큰 낭비·context rot ③ 에이전트가 필요한 것만 가져오는 just-in-time 도구 검색 불가. 정적 prefix(역할·규칙) + 동적 정보는 도구 결과로 분리해야 함. |
| H-7 | 🟠 | 전역 | **rate limit / 사용자별 비용 상한 없음** — 한 사용자가 LLM·STT 비용을 무한 발생 가능(SEC-2와 결합 시 비인증 비용 공격). 동시 실행 큐/세마포어 없음(무거운 archive 분석 다중 클릭 = pod 메모리 폭증). |
| H-8 | 🟡 | `supervisor.py` commit/confirm 엔드포인트 | 쓰기 작업에 **idempotency key 없음** — 더블클릭·네트워크 재시도 시 아젠다 중복 commit, HITL 중복 확정. (UX-7 "실패 팝업 후 저장됨"도 동일 계열) |
| H-9 | 🟡 | 전역 | **사용자 피드백 루프 부재**: 응답 👍/👎, 검토 결과 정정 사유가 수집되지 않음 → eval 데이터셋(P6)이 자라지 않고, 프롬프트 개선이 감으로 이뤄짐. hitl_reviews는 승인/반려만. |
| H-10 | 🟡 | `api.js:_readSseStream`, 라우터 SSE | 스트림 **중단 버튼 없음**, 클라이언트 abort 시 서버 LLM 호출 취소 전파 미보장, 끊긴 스트림 재개(run_id 기반) 불가 — 긴 회의록 생성 중 새로고침하면 결과 유실+비용만 발생. |
| H-11 | 🟡 | `make_llm` ×4, 각 agent | 모델 추상화 없음(OpenAI 벤더 락인, ChatOpenAI 직접 생성 4중복), max_tokens·timeout·재시도 미설정, 폴백 모델 없음. 작업별 모델 라우팅 불가 구조. |
| H-12 | ⚪ | `classify_intent` off_topic 분기 | 가드레일이 라우팅 LLM의 off_topic 한 갈래뿐 — 입력 모더레이션, 출력 검증(근거 없는 주장에 출처 요구, 개인정보 마스킹) 계층 없음. 답변에 근거(그래프 노드/회의록) 인용이 없어 환각 검증 불가. |
| H-13 | 🟡 | `supervisor.py` `[PLANNING]` 15곳, `_stream_plan`(:358), `classify_intent.steps` | **플래닝 연극(planning theater)**: 화면에 표시되는 "계획"이 실제 실행과 분리되어 있음. ① `classify_intent`의 steps와 `_stream_plan` narration은 **보여주기 전용 별도 LLM 호출**(매 대화 추가 과금)이고, 실제 실행은 하드코딩된 분기라 표시된 계획과 동작의 일치 보장이 없음 ② `"아젠다 N건 분석"` 류는 라우터 코드의 고정 템플릿 f-string. 올바른 방향: 진행 표시는 별도 생성이 아니라 **에이전트 루프의 실제 이벤트**(`astream_events`의 `on_tool_start` 등)에서 파생 — P3A-6(타입 SSE)+P3B(도구 루프) 완료 시 자연 해소되므로, 그때 narration LLM 호출 제거로 비용도 절감. |

### 2.10 GraphRAG 실효성 분석 (G) — "Neo4j가 실제로 답변 품질에 기여하는가"

> 4대 유스케이스(챗봇 질의·과제 추출·보고서 분석·회의 도움)별로 그래프가 실제 어떻게 쓰이는지 코드 경로를 추적한 결과.
> **결론: 현재 구조는 "GraphRAG"라기보다 '그래프 모양의 벡터 저장소 + 고정 1-hop 컨텍스트 템플릿'에 가깝고, 핵심 검색 경로 하나는 인덱스명 불일치로 죽어 있다.**

| ID | 심각도 | 위치 | 문제 |
|----|------|------|------|
| G-1 | 🔴→✅ | `knowledge_manager.py:267`, `minutes_generator.py:46` | **죽은 벡터 검색**: Minutes 검색이 인덱스명 `minutes_embedding_index`를 호출하지만 실제 생성되는 인덱스는 `minutesEmbedding`(`neo4j_sync.py:45`) → **회의록 유사 검색이 항상 빈 결과**, `except: return []`가 삼켜 아무도 모름. `KnowledgeChunk` 타입도 index_map에 없어 엉뚱한 인덱스로 폴백. 인덱스명 3곳 중복 정의가 근본 원인. **→ 2026-06-12 핫픽스 완료(P0-8): 인덱스명 교정+0건/실패 warning 로그. 레지스트리 단일화(HC-3)와 상시 메트릭은 P3B-6에서.** |
| G-2 | 🟠 | `neo4j_client.py:52-123`, agents 전체 | **그래프 순회 부재**: 컨텍스트는 고정 1-hop 템플릿 쿼리(아젠다 20·세션 5·문서 10 LIMIT)뿐. "이 아젠다가 어느 세션들에서 논의됐고 어떤 보고서로 이어졌나" 같은 **멀티홉 경로 추적·관계 가중 랭킹·경로 기반 근거 제시가 없음** — 온톨로지를 만들어 놓고 추론에 쓰지 않는 상태. 유일한 그래프다운 활용은 `[*1..2]` 스코핑(`vector_search_node`)과 관계 정규화 기능(`analyze-relationships` — 이건 잘 만들어진 편). |
| G-3 | 🟠 | `knowledge_manager.py:292`, `minutes_generator.py:90-120`, `task_extractor.py:93-131` | **에이전트 검색 도구에 회의체 스코핑 없음**: meeting_id 필터가 가능한 `vector_search_node(meeting_id=...)`가 이미 있는데 **도구들은 전부 전역 검색** 사용 — 타 회의체 자료가 컨텍스트에 섞임(권한 AI-3 + 정확도 동시 훼손). |
| G-4 | 🟠 | `supervisor.py:1896-1916`, `task_extractor.extract_agendas_from_context` | **과제 추출이 그래프를 안 씀**: 컨텍스트가 전부 PG(회의체 정보·지침·이전 회의록 요약·미완료 과제·첨부 텍스트), 부서 후보도 PG 멤버 부서 목록뿐. 그래프의 `Department-[담당부서]-Agenda` 이력(과거 어떤 유형 안건을 어느 부서가 맡았나), 유사 과거 아젠다 검색이 추출·부서배정에 활용되지 않음 — "온톨로지 기반 아젠다 추출"이라는 핵심 가치 제안이 미구현. UX-11(아젠다가 전부 팀에만 연결)도 같은 뿌리. |
| G-5 | 🟡 | `report_reviewer.py:364-385` | 보고서 분석 retrieval이 **파일명+본문 앞 500자**를 쿼리로 사용(문서 주제 대표성 낮음), k=2/3에 150자 절단 — 게다가 Minutes 쪽은 G-1로 항상 0건. 검토 루브릭 대비 과거 우수/반려 보고서 사례(HumanJudgment) 검색 미활용. |
| G-6 | 🟡 | `neo4j_sync.py` 임베딩 소스 | **임베딩 텍스트 빈약/편향**: Meetings=guidelines만, Session=제목+장소, Minutes=전문 단일 벡터(긴 문서 평균화로 변별력 저하). 노드 임베딩 vs 청크 임베딩의 역할 구분·결합 전략 없음. **풀텍스트 인덱스 부재**로 고유명사·회의체명 정확 검색 불가(하이브리드 검색 없음). |
| G-7 | 🟡 | `supervisor.py:379-411` (sessions-chat) | 회의 도움 챗이 그래프 대신 **PG 전체 세션+전체 아젠다+전체 회의록 요약을 무제한 pre-stuff** — 회의체가 크면 토큰 폭증, 오래된 세션이 최신과 동일 가중치. (멤버십 검증도 없음 — SEC-5 계열) |
| G-8 | ⚪ | 종합 | 긍정 평가: 온톨로지 스키마 자체(회의체-세션-아젠다-문서-사람-부서)는 유스케이스에 적합하게 설계됨. 문제는 스키마가 아니라 **활용 계층**(검색·순회·근거 인용)과 **품질 측정 부재**(P6과 연결 — retrieval recall을 재는 장치가 없어 G-1 같은 전면 장애도 탐지 불가). |

### 2.11 하드코딩 인벤토리 (HC) — 설정·코드 분리 점검

> 운영 중 바뀔 수 있는 값이 코드에 박힌 곳. (H-13의 `[PLANNING]` 마커, AI-8 가격표 포함 — 중복 ID는 참조만)

| ID | 위치 | 내용 | 개선 방향 |
|----|------|------|----------|
| HC-1 | `supervisor.py:106-125` | 라우팅 프롬프트 안 키워드 분기("브리핑","현황","속해있어"… ★ 케이스) | Supervisor 그래프 전환(P3A-5) 시 제거 — 도구 설명이 라우팅을 대신 |
| HC-2 | `supervisor.py:575` | 관리자 직급 목록 `("대표","CEO","임원")` | RBAC(P1-3)로 제거 |
| HC-3 | `neo4j_sync.py:41-50` + `knowledge_manager.py:266-272` + `minutes_generator.py:46` | **벡터 인덱스명 3중 정의(불일치 사고 G-1의 원인)** | `ai/retrieval_registry.py` 단일 모듈로 통합 — 라벨→인덱스→반환필드 한 곳에서 관리 |
| HC-4 | `stt.py:69-73,80-81`, `useSTT.js:1-6` | STT 언어맵·sample_rate 48000·max_speakers 6·청크 12s/무음 0.9s 임계값 | 설정 파일/env로 외출, 서버-프론트 공유 상수는 API로 내려주기 |
| HC-5 | `stt.py:184`, `useSTT.js:119-124` | `화자_` 라벨 접두사·정규화 규칙이 서버/프론트에 각각 구현 | 한쪽(서버)으로 통일 |
| HC-6 | `report_reviewer.py:413-420` | 보고서 12대 요소 채점 루브릭(`_DETAIL_SCORE_SCHEMA`) | 회의체별 커스터마이즈 가능성 높음 → DB/설정으로 (가중치 변경에 배포 불필요하게) |
| HC-7 | `agent_logging.py:38-51`, `usage.py:31-36` | LLM 단가표·STT 분당 단가 | 설정 파일 + 주기 갱신 절차 (AI-8) |
| HC-8 | `chat_history.py:13`, `usage.py:16-28` | `VALID_CONTEXT_TYPES`·context_type→섹션 매핑이 두 파일에 산재 | enum/상수 모듈 단일화 |
| HC-9 | `neo4j_sync.py` 전반, `supervisor.py` | `mg-`/`agenda-`/`session-` ID 포맷 문자열이 수십 곳에 산재 | `neo4j_ids.py` 헬퍼(`mg_id(7)` 등)로 통일 — 포맷 변경·오타 방지 |
| HC-10 | `k8s/*.yaml` 전체 | 네임스페이스 `skala3-finalproj-class2-team9`, 레지스트리 경로, AI URL 기본값(`localhost:8000`) | kustomize overlay(base/dev/prod)로 환경값 분리 |
| HC-11 | `models.py:212` 등 | 상태값 한글 기본값(`"검토중"`), `"DRAFT"`/`"ended"`/`"ENDED"` 대소문자 혼용 | DATA-3 enum 표준화와 함께 코드化(영문 enum + 표시명 매핑) |
| HC-12 | `supervisor.py:645-652`, Vue 컴포넌트 | off_topic 안내문·greeting 등 사용자 노출 문구가 코드 내 | 문구 리소스 분리(최소한 constants 모듈) — 톤 수정에 배포 불필요 |

### 2.12 멀티테넌시·구성원 관리 (MT) — "여러 회사가 모이는 서비스"의 경계 부재

> 이 서비스는 **여러 회사의 인원이 모여 회의체를 구성**하는 구조인데, 코드에는 회사(테넌트) 경계가 사실상 존재하지 않는다.
> 테스터 피드백 UX-24(자물쇠 아이콘 = 조직 데이터 조회 범위 의도)·UX-25(구성원 추가의 비밀번호, 수정 권한)의 근본 원인.

| ID | 심각도 | 위치 | 문제 |
|----|------|------|------|
| MT-1 | 🔴 | `UserController.java` PATCH `/api/v1/users/{userId}`, `UserService.updateUser:92-98` | **계정 탈취 벡터**: 인증만 되면 누구나 타인의 이름·회사·부서·직위는 물론 **비밀번호까지 변경 가능**(권한 체크 전무, "관리자 기능"은 주석뿐). 비밀번호를 바꾸면 그 계정으로 로그인 가능. FastAPI 쪽에도 동일 계열 `PATCH /users/{user_id}`가 2개(`meetings.py:388,524`) 존재. |
| MT-2 | 🔴 | `OrganizationPage.vue:87-112,265,471-472`, `/api/v1/auth/signup` | **비밀번호 대행 생성**: 회사 탭의 "구성원 추가"가 공개 signup API로 타인 계정을 만들면서 **추가하는 사람이 초기 비밀번호를 직접 입력**(어떤 흐름은 `generateTempPassword()`로 임의 생성). → ① 비밀번호를 생성자가 알게 됨 ② 메신저 등으로 전달돼 노출 ③ 최초 로그인 시 변경 강제 없음 ④ 본인 동의 없이 계정 생성. UX-25의 "이게 무슨 비밀번호냐"는 혼란은 이 설계의 증상. |
| MT-3 | 🔴 | `GET /api/v1/users`, `GET /api/v1/users/search`, FastAPI `meetings.py:347,359` | **전사 디렉터리 공개**: 인증된 사용자라면 **모든 회사의 전체 구성원**(이름·이메일·회사·부서·직위·소속 회의체)을 조회/검색 가능. 타사 인원에게 자사 조직 구조가 그대로 노출 — B2B 멀티테넌트 서비스에서 계약·컴플라이언스 사고급. |
| MT-4 | 🟠 | `users.company` (varchar 자유 입력) | **테넌트 식별자가 자유 텍스트**: 회사가 정규화된 엔티티가 아니라 가입 시 입력하는 문자열 → "SK", "에스케이", 오타가 전부 다른 회사로 취급되거나, 반대로 같은 문자열만 쓰면 타사 사칭 가능. 회사 단위 관리자 역할도 없어 "우리 회사 구성원"의 권위 있는 정의가 불가능. |
| MT-5 | 🟡 | `supervisor.py` 조직 쿼리, `_get_member_org_depts`, Neo4j User/Company 노드 | **AI 조회 범위도 회사 경계 무시**: 조직 트리·구성원 질의가 회사 필터 없이 동작 — 챗봇에게 물으면 타사 조직 정보가 답변에 섞일 수 있음(AI-3·P3B-1 스코핑에 company 차원 누락). |
| MT-6 | 🟡 | `OrganizationPage.vue:114-123` | 구성원 "제거"가 실제로는 첫 번째 회의체에서의 멤버 제거(`meetings[0]`) — 계정 관리와 회의체 멤버십 관리가 UI에서 뒤섞여 사용자가 무엇이 지워지는지 알 수 없음. |

**개선 설계 방향** (P1-7로 작업화):
1. **계정 생성 = 초대 기반으로 전환**: 관리자가 비밀번호를 만드는 구조 자체를 폐기. 초대(이메일+역할) → 초대 토큰 링크/코드 → **본인이 비밀번호 설정**. 이메일 발송이 어려운 환경이면 과도기로 "시스템이 임시 비밀번호 자동 생성(생성자에게도 1회만 표시) + 최초 로그인 시 변경 강제(`must_change_password`)".
2. **디렉터리 가시성 규칙**: 기본 = 내 회사 구성원 + "나와 같은 회의체에 속한" 타사 인원만. 전체 목록/검색 API에 이 스코프를 서버에서 강제. 타사 인원은 최소 필드(이름·회사·직위)만.
3. **회사 관리자 역할**: `users.role`에 `COMPANY_ADMIN` 추가 — 자기 회사 구성원의 추가/수정/비활성화만 가능. 회의체 간사는 회의체 멤버십만 관리(계정 정보는 불가). 본인 정보는 본인만(PATCH /users/me).
4. **회사 정규화**: `companies` 테이블 + `users.company_id` FK (기존 문자열은 마이그레이션으로 매핑). 가입/초대 시 회사는 선택만 가능(자유 입력 제거).
5. **AI 스코프에 company 차원 추가**: 조직/구성원 도구는 호출자의 company + 공유 회의체 멤버로 제한(P3B-1과 통합, UX-24 자물쇠 의미 실현).
6. 구성원 관련 모든 변경(생성·수정·비활성화·초대)을 audit_logs에 기록(P1-6).

### 2.13 페이지네이션 부재 인벤토리 (PG) — 목록 API 전수 점검 (2026-06-12)

> Spring 전체에 `Pageable`/`PageRequest` 사용처 **0건**, FastAPI 목록 라우트에 limit/offset 파라미터 **0건**, 프론트에 무한 스크롤/페이지 UI **0건**. 모든 목록이 "전체 조회 → 전체 직렬화 → 전체 렌더". BE-2에서 한 줄로 지적한 것을 전수 조사로 상세화.
> 다행히 §4.1 인덱스 초안이 keyset 컬럼(`chat_messages(thread_id, created_at)`, `stt_segments(session_id, start_sec)`)을 이미 커버 — 인덱스 선행 작업은 P2와 겹침.

| ID | 심각도 | 위치 | 문제 |
|----|------|------|------|
| PG-1 | 🟠 | `ChatMessageRepository.findByThreadIdOrderByCreatedAtAsc`, `ChatMessageController GET /chat/messages`, FastAPI `chat_history.py:50` | **채팅 이력 전체 로드**: 스레드당 메시지가 무한 누적되는데 매 진입 시 전부 내려줌. 사용량에 정비례로 느려지는 첫 번째 절벽. (supervisor의 replay는 최근 20개로 이미 제한 — 서버 측은 OK, API/프론트만 문제.) |
| PG-2 | 🟠 | `ScriptRepository.findBySessionIdOrderByStartSecAsc`, `ScriptController GET /sessions/{id}/scripts` | **STT 세그먼트 전체 로드**: 1–2시간 회의면 세그먼트 수천 행 — 진행 중 화면 재진입/아카이브 조회마다 전체 전송. |
| PG-3 | 🟡 | `MeetingController GET /meetings`(+keyword), `GET /me/meetings`, `MeetingRepository.findByTitleContaining...` | 회의체 목록·검색 무제한. 검색은 `ILIKE %kw%` full scan + 전체 반환. |
| PG-4 | 🟡 | `SessionRepository.findByMeetingId`, `ReportRepository.findAllByMeetingId`, `AgendaRepository.findByMeetingIdOrderByCreatedAt` | 회의체 하위 목록(세션/보고서/아젠다) 전체 반환 — 운영 1년 누적 시 회의체당 수백 건. |
| PG-5 | 🟡 | `UserController GET /users`(전체 사용자), `GET /users/search` | 사용자 디렉터리 무제한 — MT-3(전사 디렉터리 공개)과 같은 API. 스코프 축소(P1-7)와 페이지네이션을 한 작업으로. |
| PG-6 | 🟡 | FastAPI `meetings.py:43`(전체 회의), `meetings.py:364-370`(전체 사용자 + **사용자별 멤버십 개별 쿼리 N+1**), `upload.py:105` | 관리/조회용 목록 라우트들이 `.all()` — N+1까지 겹쳐 사용자 수에 제곱 비례 비용. |
| PG-7 | 🟡 | `neo4j_graph.py GET /archive` | 사용자 소속 그래프 **전체**를 한 응답으로(LIMIT 없는 Cypher 다수: Department 전체, 소속 회의체 전체와 하위 노드). 응답 크기가 데이터 증가에 정비례. |
| PG-8 | ~~🟡~~ | `PastMeetingsPage.vue` | ~~프론트 N+1 HTTP~~ **재확인 결과 오진(2026-06-12)**: 세션은 펼칠 때만 lazy-load — 수정 불필요. |
| PG-9 | ⚪ | `AgentPanel.vue:130`, SessionPage 스크립트 영역 | 메시지/세그먼트 배열 전체를 `v-for` 렌더 — 증분 로드·가상 스크롤 없음(PG-1·2 해결의 프론트 짝). |
| PG-10 | ⚪ | `ApiResponse.java`, FastAPI 응답 모델 | **페이지 응답 계약 자체가 부재**: envelope에 page/size/total/next_cursor 메타 필드 없음 — 개별 API를 고치기 전에 계약부터 정의해야 함. |

---

## 3. 단계별 개선 계획

### Phase 0 — 비상 보안 조치 (즉시, 1–2일) 🔴
목표: 외부에서 악용 가능한 구멍부터 차단. 코드 변경 최소.

- [x] P0-1 **유출 키 회전** — 완료 (2026-06-12, 수동 수행). 이로써 LangSmith 트레이싱 활성화 가능: ai-secret에 `LANGSMITH_TRACING=true`+새 키 설정 시 agent_logs.trace_id(P3A-3)로 트레이스 점프 동작.
- [x] P0-2 **시크릿을 k8s Secret으로 이전** (2026-06-12): `k8s/backend.yaml` DB 비번 → `backend-secret` secretKeyRef + JWT_SECRET 주입 추가, `application.yaml` 전 시크릿 `${ENV}` 참조화, `k8s/postgres/deployment.yaml` → `postgres-secret`, `neo4j/k8s/secret.yaml` placeholder화. 템플릿 `k8s/secrets.example.yaml` 생성, **시크릿 위치별 매뉴얼(`SECURITY_ROTATION.md` §0~2)** 작성. **⚠ develop 머지 전 클러스터에 `backend-secret` 생성 필수 + ai-secret의 JWT_SECRET 동일값 확인.**
- [x] (추가) **Redis 완전 제거** (2026-06-12): 코드에서 Redis 미사용 확인(주석의 "도입 예정"뿐) → `spring-boot-starter-data-redis` 의존성, `application.yaml` redis 블록, `k8s/backend.yaml` REDIS env 3종 제거. 의존성만 남겨두면 actuator health가 Redis 연결을 검사해 probe 실패를 유발하므로 의존성째 제거. 컴파일 검증 통과.
- [x] P0-3 **무인증 라우터 봉쇄** (2026-06-12): `stt.py` 2개, `neo4j_graph.py` 11개 라우트에 `get_current_user` 추가. `main.py` WebSocket 2개에 JWT 쿼리파라미터 검증(`_ws_user_id`, 실패 시 4401). `useSTT.js` fetch에 Authorization 헤더, `api.js toWsUrl`에 토큰 자동 부착. **잔여: WLK(`/wlk/asr`) WebSocket은 별도 서비스(whisperlivekit)라 미적용 — P4에서 프록시/게이트웨이로 처리.**
- [x] P0-4 **`/api/sync` 공개 Ingress 제거** (2026-06-12): `k8s/ingress.yaml`에서 경로 삭제(내부 Service 호출은 영향 없음). **잔여: `/grafana` 노출과 actuator permitAll은 운영 결정 필요(Grafana 자체 로그인 사용 중인지 확인) — P1으로 이월.**
- [x] P0-5 CORS 화이트리스트 교체 (2026-06-12): FastAPI(`main.py`, `CORS_ALLOWED_ORIGINS` env로 확장 가능) + Spring(`SecurityConfig.java`) 모두 `workmaite.project.skala-ai.com`+로컬 dev로 제한.
- [x] P0-6 XSS 차단 (2026-06-12): `SessionPage.vue` 자체 renderMd → `useMarkdown`(DOMPurify) 교체, `DetailSidebar.vue` content_summary v-html sanitize. 전 renderMd 사용처가 sanitize 버전으로 일원화 확인.
- [x] P0-7 시작 시 draft Agenda `DETACH DELETE` 제거 (2026-06-12): 레거시 Todo/todo-* 정리만 유지 — 사용자 검토 중 draft 유실 방지.
- [x] P0-8 **기능 핫픽스(G-1)** (2026-06-12): 인덱스명 `minutes_embedding_index` → `minutesEmbedding` 수정(`knowledge_manager.py`, `minutes_generator.py`), KnowledgeChunk → `reportChunkEmbedding` 매핑 교정, 검색 0건/실패 시 warning 로그 추가. **보강**: `ensure_vector_indexes`의 레거시 인덱스명 생성도 `minutesEmbedding`으로 통일하고, 구버전 DB(레거시 인덱스만 존재) 호환을 위해 Minutes 검색에 레거시명 폴백 추가 — 어떤 DB 상태에서도 동작. 검증: Python 전 파일 ast 파싱 OK.

> **추가 완료(Phase 0 범위 외 퀵윈, 2026-06-12)**
> - [x] BE-5: `show-sql` 기본 false(`${SHOW_SQL:false}`)로 변경.
> - [x] DATA-9(코드 측): `다룸멌` 오타 — 생성 쿼리를 정식 형태 `(Agenda)-[:다룸]->(Session)`으로 교정(`knowledge_manager.py:624`), 조회 패턴은 신구 양쪽 매칭 유지. DB 잔여 오타 관계는 기존 정규화 룰(`supervisor.py:1528`)이 점진 정리.
> - [x] DATA-2(부분): `NeoSyncService`를 **afterCommit + TaskExecutor** 구조로 재작성 — 커밋 전 발사 race 제거, 요청 스레드 비블로킹. (실패 재시도는 여전히 outbox 필요 → P2-4)
> - [x] H-3(부분): `main.py` 트레이싱 강제 off 제거 — `LANGSMITH_TRACING=true`+API 키 존재 시에만 활성화되도록 env 제어화. (trace_id↔agent_logs 연결은 P3A-3에서)
> - [x] AI-11(부분): `supervisor.py`의 `print()` 10곳 제거 — DEBUG 라인 삭제, 오류 출력은 logger로 전환.
> - 검증: Python ast 전체 통과, `gradlew compileJava` 성공, `npm run build` 성공.

### Phase 1 — 인증/인가 통합 (1주) 🔴
목표: "누가 무엇을 볼 수 있는가"의 단일 모델 확립. AI 데이터 범위 정의의 토대.

- [x] P1-1 인증 발급 주체를 **Spring으로 일원화** (2026-06-12): FastAPI `routers/auth.py` 제거, FastAPI는 검증만. pbkdf2 혼재는 Spring 로그인에 레거시 검증+성공 시 BCrypt 재해시(점진 마이그레이션, `LegacyPbkdf2Verifier`)로 해소.
- [x] P1-2 JWT `type` 클레임 + **`refresh_tokens` 테이블 회전/폐기** (2026-06-12): Flyway 도입(V2), 회전된 토큰 재사용 탐지 시 전체 폐기(noRollbackFor로 커밋 보장), jti 추가(같은 초 발급 토큰 byte-identical 버그 — E2E로 발견·수정), logout 실제 폐기 + 프론트 연동. FastAPI/WS도 type=refresh 거부.
- [x] P1-3 **RBAC 도입** (2026-06-12): users.role(V2) + V3 부트스트랩(기존 전략기획팀→SYSTEM_ADMIN 1회 부여). supervisor.py position 판별 2곳, meetings.py `_is_strategic` 부서 판별, 프론트 isStrategicTeam 모두 role 기준으로 교체.
- [x] P1-4 **멤버십 가드 공통화** (2026-06-12): Spring `MeetingAccessGuard`+`CurrentUser` — 각 서비스의 단일 진입점(findXxxById)과 meetingId 경로에 적용. FastAPI `access_guard.py` — meetings/sessions/upload/stt/supervisor 라우트 적용. 비멤버 403 E2E 검증. (supervisor의 나머지 도구 스코프는 P3B-1에서)
- [x] P1-5 Neo4j 사용자 매칭 `pg_id` 단일 키 통일 (2026-06-12): /archive·supervisor 본인 매칭, meeting-groups 멤버 추가/삭제(user_id 필수화), 간사 연결(호출자 본인) — email/name OR 매칭 전부 제거.
- [x] P1-6 **감사 로그 도입** (2026-06-12): audit_logs(V2) + Spring @AuditLogged AOP(6개 서비스 CUD·승인·할당) + AuthService LOGIN/SIGNUP/LOGOUT + FastAPI AuditLogMiddleware(변경성 요청). TransactionTemplate(REQUIRES_NEW)로 본 처리와 분리, signup은 afterCommit(FK). 4종 이벤트 DB 기록 검증.
- [x] P1-7① **멀티테넌시 즉시 조치** (2026-06-12): PATCH /users/{id} 비밀번호 변경 제거+권한 가드(MT-1), GET /users·search 디렉터리 스코프(본인+내 회사+공유 회의체, MT-3) — Spring/FastAPI 양쪽. E2E 검증.
- [ ] P1-7② **마이그레이션 동반(§4.3 V4)**: companies 정규화, COMPANY_ADMIN 부여 UI, 초대 기반 온보딩(invitations, `must_change_password`), 회사 탭 UI 초대 흐름 교체(MT-2/UX-25). ③ AI 조직 쿼리 company 스코프(P3B-1과 통합).

### Phase 2 — DB 스키마/정합성 (1주) 🟠
목표: 스키마 단일 소스 + PG↔Neo4j 동기화를 신뢰 가능하게.

- [x] P2-1 **Flyway 도입** (2026-06-12, P1-2와 동시): baseline-on-migrate(V1), models.py 읽기 전용 선언. ※ 마이그레이션 번호가 §4 초안과 달라짐 — 실적용: V2(auth/rbac/audit), V3(role 부트스트랩), V4(인덱스/제약), V5(sync outbox), V6(report_agendas).
- [x] P2-2 인덱스/제약 — **V4** 적용 (2026-06-12): FK/조회 인덱스 17종 + 멤버십 유니크 2종 + human_status CHECK. 운영 스키마 대조·위반 데이터 0건 확인, EXPLAIN으로 인덱스 사용 검증. **agenda.status CHECK 보류**: Spring enum(ON_HOLD/CONFIRMED/DONE) vs 실데이터(draft/ongoing/done) 불일치 발견 → HC-11에서 정리.
- [x] P2-3 audit_logs(V2)·neo4j_sync_outbox(V5)·report_agendas(V6) 테이블 (2026-06-12). chat_feedback은 P3C-3에서.
- [x] P2-4 **아웃박스 동기화** (2026-06-12): NeoSyncService가 트랜잭션 내 outbox 기록 → 커밋 후 SyncOutboxDispatcher kick + 30초 폴러 재시도(최대 10회, 404 skip). 삭제 전파(DATA-4): session/agenda 삭제 라우트 신설 + delete 함수 예외 전파화. E2E 검증.
- [x] P2-5 Neo4j 유니크 제약 9종 (2026-06-12): ensure_constraints()가 시작 시 중복 정리(차수 보존) 후 생성 — dev Neo4j 적용 확인. (`다룸멌` 오타는 Phase 0에서 기처리)
- [x] P2-6 임베딩 content_hash 게이팅 (2026-06-12): 6개 sync 함수 적용, 동일 내용 재sync 시 OpenAI 호출 생략(실측 0.18s→0.05s). STARTUP_FULL_RESYNC(기본 false)로 전체 resync 옵션화.
- [x] P2-7(부분) Neo4j행 타임스탬프 ISO-8601+TZ(UTC) 통일 (2026-06-12). **잔여: PG TIMESTAMPTZ 컬럼 전환+JPA Instant화는 시프트 위험 때문에 별도 패스로 분리** — 현재는 naive-UTC로 일관.
- [x] P2-8 report_agendas 정규화 (2026-06-12): V6 테이블+백필(11개 보고서→13연결), FastAPI dual-write. **잔여: 프론트 읽기 경로 전환(P7/P8) 후 JSONB DROP.**

### Phase 3 — AI 하네스 & 에이전트 재설계 (2–3주) 🟠
목표: LangGraph v1 Supervisor 패턴 + **내구성 있는 실행(durable execution)** + 도구 중심 설계 + 데이터 범위 강제.
설계 원칙은 §8 참조. 작업은 3A(하네스 기반) → 3B(도구/컨텍스트) → 3C(서비스 가드) 순.

**3A. 하네스 기반 공사 — 신뢰 가능한 실행부터**
- [x] P3A-1 **체크포인터 도입** (2026-06-12): 재현 결과 **HITL이 애초에 동작 불가였음** — 체크포인터 없는 compile에서 get_state가 'No checkpointer set' 실패(UX-1 원인 확정). `graph_runtime.py`(AsyncPostgresSaver+psycopg pool, lifespan 관리) + HITL 그래프 lazy-compile + aget_state. run_id 서버 발급(start 라우트 thread_id optional). **서버 재시작 후 pending resume까지 E2E 검증.** (체크포인터는 HITL 그래프에 적용 — 채팅 그래프 메모리는 P3B-3에서)
- [x] P3A-2 **structured output** (2026-06-12): 검토 경로(HITL propose·직접 검토)를 pydantic 스키마(12요소 ElementScore 포함)로 전환 — **가짜 score=50 fabrication 제거**, 실패는 명시적 에러(502/status:error). 추출 경로는 분석텍스트+JSON 프롬프트 설계 유지(P6 eval 전 프롬프트 변경 금지) + 파싱 실패 1회 재시도 후 명시적 실패. 공통 헬퍼 `ainvoke_structured`. 잔여: archive 분석(_parse_archive_result)의 루브릭 스키마는 HC-6과 함께. 실패율 메트릭은 P5-1에서.
- [x] P3A-3 **trace_id 연결** (2026-06-12): V7 + log_agent_run이 collect_runs()로 루트 run id 기록(트레이싱 off여도 동작). LangSmith env 제어화는 Phase 0에서 기완료 — 키 회전(P0-1) 후 LANGSMITH_TRACING=true로 활성화하면 trace_id로 점프 가능.
- [x] P3A-4 `supervisor.py` 해체 (2026-06-12): 2,966줄 → 1,024줄. services/supervisor_helpers.py(공용 DB 컨텍스트·로그) + 라우터 4분리(graph_analysis 608/archive 838/hitl_reviews 289/knowledge 184). OpenAPI 80경로 누락 0·스모크 통과. **잔여: supervisor chat 핸들러(~600줄)는 P3A-5 재작성과 함께, archive.py 추가 분해는 P7-1과 함께. graphs/·tools/ 레이어는 P3A-5·P3B-1에서 생성.**
- [~] P3A-5 **Supervisor 전환 — 1단계 완료 (2026-06-12)**: 라우팅 계층 개선 — off_topic Literal 복구(죽은 분기 살림), 인사 예외, classify_intent에 대화이력 6턴 반영(AI-9). **eval 93.75%→100%(18/18)**, off_topic SSE 조기종료 라이브 검증. 2단계: 도구 5종+JIT 에이전트. **3단계(2026-06-12): react 기본 전환**(롤백 SUPERVISOR_TOOLS_MODE=legacy, 플래그 없이 도구 경로 동작 검증). 잔여: 사전조립 경로 제거(1사이클 후), classify_intent→handoff 통합.
- [~] P3A-6 **스트리밍 프로토콜 v2 — 1단계 완료 (2026-06-12)**: sse.py 포매터 + supervisor 전 스트림 16곳 event: 기반 전환(payload JSON화 — FE-2 해소), api.js v2 파서+v1 폴백, 라이브 검증. 2단계 완료(2026-06-12): 타 라우터 19곳 v2 전환·v1 마커 전면 제거(예외: analyze-file/stream은 streamPostForm 파서와 함께). 3단계 완료(2026-06-12): run_id 이벤트, 중단 버튼(AbortSignal→서버 generator 취소 전파). **잔여**: narration 제거(astream_events 기반 진행표시 — P3A-5 2단계 그래프 전환과 함께). 원계획: **스트리밍 프로토콜 v2(FE-2·H-10·H-13 통합)**: SSE `event:` 필드 기반 타입 이벤트(`planning|token|tool_call|result|usage|error`) + 응답에 `run_id`. 클라이언트 abort 시 `asyncio.CancelledError`를 LLM 호출까지 전파(취소된 만큼만 과금), 프론트에 중단 버튼. 체크포인터 덕에 끊긴 run 상태 조회/이어보기 가능. **진행 표시는 `astream_events`의 실제 도구/노드 이벤트에서 파생** — `_stream_plan`·`classify_intent.steps` 같은 보여주기 전용 narration LLM 호출 제거(플래닝 연극 해소 + 대화당 LLM 1회 절감).
- [x] P3A-7 LLM 클라이언트 공통화 (2026-06-12): `llm_factory(profile)` — _make_llm 4중복+직접 생성 12곳 통합, timeout(60s)/retry(2) 일관, OPENAI_MODEL_{PROFILE} env로 프로파일별 모델 분리 가능. 잔여: 폴백 체인, run_cypher 공유 풀.

**3B. 도구 & 컨텍스트 엔지니어링**
- [ ] P3B-1 **도구 확충 + 스코프 강제(AI-2·AI-3)**: 회의체 현황·아젠다 목록/상태·보고서 제출 현황·그래프 검색·이전 회의록 검색을 `@tool`로. 모든 도구가 `RunnableConfig`의 `user_id`/허용 `meeting_ids`를 쿼리에 강제 주입 — "임의 meeting 접근 불가"를 테스트로 증명. 범위 정의를 `docs/ai-data-scope.md`로 문서화. 도구 출력은 토큰 효율적으로(전체 dump 금지, 필요 필드만+페이지네이션), 도구 에러는 모델이 복구할 수 있는 구조화 메시지로.
- [ ] P3B-2 **사전 주입 → just-in-time 검색 전환(H-6)**: 시스템 프롬프트는 정적 prefix(역할·규칙·출력 형식 — 프롬프트 캐시 적중)로 고정하고, 회의체 컨텍스트·아젠다·이전 회의록은 에이전트가 도구로 필요 시 조회. `_get_meeting_context`/`graph_context_to_str` 사전 조립 제거.
- [~] P3B-3 **부분 — assistant 서버 저장은 기구현 확인 (2026-06-12)**: user 사전 저장+assistant finally 저장(끊김 포함). 잔여: 30턴↑ 컴팩션, /api/chats POST role 축소(클라이언트 의존 조사 필요). 원계획: **대화 메모리 계층화(H-4·H-5)**: ① 단기 = 체크포인터 thread state ② 스레드가 길어지면(예: 30턴↑) 오래된 턴을 요약 메시지로 **컴팩션** ③ 회의 중 채팅은 SessionSummaryBlock 재활용. assistant 메시지는 **서버가 저장**(클라이언트 `/api/chats` POST는 user role만 허용으로 축소).
- [~] P3B-4(부분) 문서 소비 프롬프트 4곳에 인젝션 가드 적용 (2026-06-12 — 평가 조작·지시문 무시). 잔여: prompts/ 파일 분리·버전 관리, 근거 인용 의무화(H-12). 원계획: 프롬프트 정비(AI-4·AI-5): 사용자 콘텐츠는 명시 구분자 + "문서 내 지시 무시" 가드, `prompts/` 파일 분리·버전 관리. **답변에 근거 인용 의무화**(어떤 회의록/노드 기반인지 — 환각 검증 가능성·신뢰 확보, H-12).
- [ ] P3B-5 `print` 제거, 로깅 표준화(JSON), `except Exception` 정리(최소 logger.exception + 실패 메트릭).
- [~] P3B-6 **1단계 완료 (2026-06-12)**: retrieval_registry(3중 정의 제거)·vector_search 스코프드 진입점(prop/rel/결합, 오버페치로 post-filter 함정 수정)·0건 메트릭. 2단계 완료(2026-06-12): 풀텍스트 인덱스 4종+hybrid_search(RRF)·supervisor 도구 적용. 잔여: knowledge_manager 등 잔여 소비자 하이브리드 확대. 원계획: **검색 레지스트리 단일화 + 스코프드 하이브리드 검색(G-1·G-3·G-6·HC-3)**: 라벨→인덱스명→반환필드를 `ai/retrieval_registry.py` 한 곳으로 통합(3중 정의 제거). 모든 검색 도구가 `vector_search_node(meeting_id=...)` 스코핑 변형을 기본 사용. Neo4j **풀텍스트 인덱스 추가**(제목·고유명사용) 후 벡터+풀텍스트 하이브리드(RRF 결합). 검색 0건이 지속되면 메트릭/알림(G-1 재발 방지).
- [ ] P3B-7 **그래프 네이티브 컨텍스트(G-2)**: 고정 1-hop 템플릿을 "시드 검색(벡터) → 그래프 확장(1~2-hop 관계 순회) → 경로 포함 근거 반환" 패턴으로 교체. 예: 아젠다 질의 시 `(Agenda)-[발제세션]->(Session)-[소속]->(Meetings)` + 연결된 Report/Minutes/HumanJudgment까지 경로째 수집해 "어느 회의에서 논의→어떤 보고서 제출→어떤 판단" 흐름을 근거로 인용(P3B-4 인용 의무와 결합). 회의록 임베딩은 청크 중심으로 재편(노드 전문 임베딩은 보조, G-6).
- [ ] P3B-8 **과제 추출의 그래프 활용(G-4)**: 추출 시 ① 유사 과거 아젠다 top-k(중복 제안 방지·이월 과제 연결) ② `Department-[담당부서]->Agenda` 이력 기반 부서 추천(현 PG 멤버 부서 목록 단독 사용 대체) ③ 추출 결과를 세션 노드에 연결(UX-11의 "회의에서 나온 아젠다는 회의에 연결" 구조 반영). 부서 추천 정확도는 P6 eval로 측정.

**3C. 서비스 가드 (챗봇 운영 안전망)**
- [~] P3C-1 **비용 상한 — 완료 (2026-06-12)**: 일일 토큰 예산을 PG 집계(token_usage_logs)로 판정. 분당 rate limit은 **사용자 결정으로 제외**. 동시 1개 세마포어는 잔여. 원계획: **rate limit & 비용 상한(H-7)**: 사용자별 분당 요청 제한 + 일일 토큰 예산(초과 시 안내 메시지). 구현: 현재 단일 replica이므로 **인메모리 카운터(slowapi 등)로 충분**, 일일 토큰 예산은 `token_usage_logs` 집계로 판정(Redis 불필요 — 2026-06-12 제거됨). 무거운 분석 엔드포인트는 사용자당 동시 1개 세마포어. 멀티 replica 확장 시 PG 기반 카운터로 전환.
- [~] P3C-2 **idempotency — 백엔드 완료 (2026-06-12)**: HITL confirm 2종+아젠다 commit 중복 차단(409, 실패 시 키 해제 — E2E 검증). 잔여: 프론트 버튼 더블클릭 가드. 원계획: **idempotency(H-8)**: commit/confirm 엔드포인트에 `Idempotency-Key` 헤더(또는 proposal_id 기반 중복 차단), 프론트 버튼 더블클릭 가드.
- [~] P3C-3 **피드백 루프 — 수집부 완료 (2026-06-12)**: V8 chat_feedback + POST /api/agent/feedback + 👍/👎 UI(👎 사유 수집). E2E 검증. 잔여: eval 데이터셋 환류 자동화(P6-4), HITL 반려 사유 통합.
- [ ] P3C-4 출력 가드레일(H-12): 쓰기 도구는 HITL interrupt 필수 유지, 근거 없는 단정 답변 방지 지침, (선택) 입력 모더레이션.

### Phase 4 — STT/화자분리 품질 (1주) 🟠
- [ ] P4-1 **청크 diarization 폐기**: gcapi를 v2 `StreamingRecognize`(또는 긴 녹음은 GCS 업로드 + batch `latest_long`/chirp) 로 전환해 세션 전체에 일관된 화자 태그 확보. 불가하면 WhisperX(전구간 pyannote) 경로를 기본으로.
- [ ] P4-2 **원본 오디오 보존**: 청크를 R2에 append 저장(`sessions/{id}/audio/...`), 실패 시 재처리 큐. 보존 기간 정책(예: 회의록 확정 후 30일) 문서화 — 개인정보 관점 필수.
- [ ] P4-3 STT 실패를 사용자에게 노출(에러 응답 + 프론트 재시도 UI), 5xx 시 provider 폴백 체인(gcapi→whisperx).
- [ ] P4-4 whisperx: align model 시작 시 1회 로드, batch_size 조정, 요청 큐(동시 1) 보호.
- [ ] P4-5 화자→사용자 매핑 보조: 세션 멤버 목록 기반 라벨 지정 UI 개선 + (선택) 화자 임베딩 기반 자동 제안.
- [ ] P4-6 STT 정확도 측정: 테스트 음성(대본 있는 회의 녹음) WER/화자 DER 측정 스크립트 작성, provider별 비교 리포트.

### Phase 5 — 관측성/비용/알림 (3–4일) 🟡
- [~] P5-1(부분) TTFT·스트림 총시간 히스토그램 — 채팅/minutes 3개 스트림 계측 (2026-06-12). 잔여: 에이전트/도구별 duration, Grafana 대시보드. 원계획: 기능별 시간 측정: agent_logs에 `duration_ms`(ended_at-created_at) 활용 + Prometheus 히스토그램(에이전트별/도구별). **TTFT(첫 토큰까지 시간)·스트림 총 시간을 SSE 핸들러에서 측정** — 챗봇 체감 품질의 핵심 지표. Grafana 대시보드(라우팅 분포, 에이전트 지연, TTFT p50/p95, 토큰/비용 일별, structured output 실패율).
- [ ] P5-2 Alertmanager 룰: sync outbox 적체, STT 실패율, LLM 에러율, 5xx, pod 재시작.
- [~] P5-3(부분) 가격표 pricing.yaml 외출 + prefix 매칭 버그 수정 (2026-06-12). 잔여: 월별 비용 리포트 API, STT 분 단위 실측. 원계획: 비용: 가격표를 설정 파일로 외출 + 월별 비용 리포트 API(이미 usage.py 토대 있음), STT 분 단위 실측 로그.
- [~] P5-4 **PG 백업 — 완료 (2026-06-12)**: postgres-backup CronJob(매일 KST 03시, pg_dump→R2) — 1회성 잡으로 덤프·업로드 실검증(212KB). 잔여: Neo4j 백업, 복구 리허설 문서.

### Phase 6 — 정확도 평가 체계 (병행, 1주) 🟠
- [~] P6-1 골든 데이터셋 — **스모크 셋 구축 (2026-06-12)**: 라우팅 16케이스 + 추출 3건(`backend/ai/eval/dataset/`). 잔여: 실제 회의록/보고서 기반 10–20건 확장, 회의록 요약 라벨.
- [~] P6-2 eval 하네스 — **스모크판 구축 (2026-06-12)**: `eval/run_eval.py`(라우팅 정확도 + 추출 P/R/F1·부서 정확도, JSON 기록). **베이스라인: 라우팅 93.75%(15/16), 추출 F1=1.00.** 발견: off_topic이 라우팅 Literal에 없어 반환 불가(죽은 지시) — 코딩 요청이 task_extractor로 오분류, P3A-5에서 처리. 잔여: 제목 임베딩 매칭(현 difflib), 회의록 LLM-judge.
- [ ] P6-3 CI에 스모크 eval(소형 5건) 추가 — 프롬프트 변경 PR에서 자동 실행.
- [ ] P6-4 **트레이스 기반 평가 환류**: P3A-3 트레이싱 + P3C-3 피드백(👍/👎, HITL 반려 사유)에서 실패 사례를 주기적으로 골든 데이터셋에 추가 — eval이 운영 데이터로 계속 자라는 구조(eval-driven development). 라우팅 정확도(classify→handoff 결정)도 평가 항목에 포함.
- [~] P6-5 **스모크 구축 (2026-06-12)**: eval/retrieval_eval.py self-retrieval recall@5 — 15/15 베이스라인. 잔여: 질의→정답 노드 골든셋 20건, recall@k·MRR 정식 측정. 원계획: **retrieval 평가(G-8)**: "질의 → 반드시 찾아야 할 노드" 쌍 20건으로 recall@k·MRR 측정(`eval/retrieval_eval.py`). 검색 0건 비율 메트릭 상시 수집 — G-1 같은 전면 검색 장애를 즉시 탐지. 부서 추천(P3B-8)의 정확도(테스트 데이터 대비 추출 아젠다·부서 유사도)도 여기서 측정.

### Phase 7 — 코드 품질/구조/UX (지속)
- [ ] P7-1 프론트 분해: ArchivePage → `archive/` 하위 15개 내외 컴포넌트+composable(목록/검토패널/모달별), SessionPage → 녹음/스크립트/회의록/채팅 4분할. Pinia store로 서버 상태 정리.
- [ ] P7-2 SSE 프로토콜을 `event:` 필드 기반으로 재설계(FE-2), 스트림 파서 공통화.
- [ ] P7-3 §2.8 UX 백로그 26건 처리(우선: UX-3/5/6/7 — 데이터 신뢰 관련).
- [ ] P7-4 테스트: Spring 서비스 단위테스트(인가 가드 포함), FastAPI 라우터 테스트(httpx), 프론트 핵심 composable 테스트. CI에 테스트+린트 게이트 추가.
- [x] P7-5 잔재 정리 (2026-06-12): workmaite-server/·springboot/package-lock.json 삭제, reset_db.py 안전장치. **정정: backend/Dockerfile은 잔재가 아니라 backend CI의 실사용 빌드 파일 — 오삭제로 CI 1회 실패 후 복구** (BE-4 항목에서 제외). 미사용 코드 정리는 상시.
- [ ] P7-6 k8s: 리소스 requests/limits 전 deployment, PDB, NetworkPolicy, postgres StatefulSet 전환.
- [ ] P7-7 **하드코딩 정리(§2.11 HC-1~12)**: 각 항목의 "개선 방향" 열대로 설정/레지스트리/enum 모듈로 외출. 우선순위: HC-3(검색 레지스트리 — P3B-6과 동일 작업), HC-2(RBAC — P1-3과 동일), HC-9(ID 헬퍼), HC-6(채점 루브릭 설정화), HC-10(kustomize overlay). 나머지는 해당 영역을 건드리는 PR에 동반 처리.

### Phase 8 — 페이지네이션 도입 (§2.13 PG, 3–5일, 독립 진행 가능) 🟡
목표: 데이터 누적에 정비례로 느려지는 목록 경로 제거. 계약 정의 → 절벽이 빠른 순(채팅·STT)부터 적용 → 프론트 전환 → 기본값 강제 순서로, **배포 중간 단계에서도 기존 프론트가 깨지지 않게** 진행.

- [ ] P8-1 **공통 페이지 계약 정의(PG-10)**: 응답 envelope 표준화 — `items` + `pageInfo { nextCursor }`(keyset) 또는 `{ page, size, totalElements }`(offset). 기본 size 30, 최대 100을 **서버에서 강제**. 시간순 무한 누적 데이터(채팅·STT 세그먼트)는 keyset 커서(`(created_at,id)` / `(start_sec,id)`), 관리·검색 목록은 offset(`Pageable`). Spring은 `ApiResponse`에 pageInfo 추가, FastAPI는 제네릭 `Page[T]` Pydantic 모델. `docs/api-pagination.md`에 규약 기록.
- [~] P8-2 **채팅 이력(PG-1) — 백엔드+초기로드 완료 (2026-06-12)**: beforeId/limit keyset(Spring+FastAPI 동일 계약, 호환 모드), 프론트 초기 로드 100건 제한. E2E 검증. 잔여: 상단 스크롤 loadMore UI(P8-6). 원계획: **채팅 이력(PG-1)**: `GET /chat/messages?threadId&before=<cursor>&limit=` — 최초 로드는 최신 N개(역순 조회 후 클라이언트 정렬), `before` 커서로 과거 페이지. Spring 리포지토리 keyset 쿼리 + FastAPI `chat_history.py` 동일 계약. AgentPanel은 상단 스크롤 도달 시 loadMore. supervisor의 최근 20개 replay 로직은 무변경 확인.
- [~] P8-3 **STT 스크립트(PG-2) — 백엔드 완료 (2026-06-12)**: afterSec/limit keyset(상한 500, 호환 모드). 잔여: SessionPage 증분 로드 적용(P8-6). 원계획: **STT 스크립트(PG-2)**: `GET /sessions/{id}/scripts?after_sec=&limit=` keyset. SessionPage는 증분 로드, 진행 중 세션의 실시간 세그먼트 추가(WS)는 기존 경로 유지 — 페이지 로드와 실시간 append가 겹치지 않게 커서 기준 명확히. 세그먼트 수가 큰 화면은 가상 스크롤 검토(PG-9).
- [ ] P8-4 **Spring 목록 API(PG-3/4/5)**: `MeetingRepository`/`SessionRepository`/`ReportRepository`/`AgendaRepository`/`UserRepository` 목록 메서드에 `Pageable` 도입, 컨트롤러는 `page,size,sort` 수용 + size 상한 검증. **호환 전략**: 1단계는 파라미터 미지정 시 기존 전체 반환 유지(기존 프론트 보호), 프론트 전환(P8-6) 후 2단계에서 기본 size 강제. `/users`·`/users/search`는 P1-7(MT-3 스코프 축소)과 같은 PR로.
- [ ] P8-5 **FastAPI/Neo4j(PG-6/7)**: 목록 라우트에 `limit/offset` Query 파라미터(FastAPI `Query(le=100)`), Cypher에 `SKIP/LIMIT`. `meetings.py:364` 사용자별 멤버십 N+1을 단일 join 쿼리로 교체. `/archive`는 회의체 목록을 페이지 단위로, 그래프 시각화 응답은 노드 수 상한 + "더 보기" 확장 쿼리로 분리.
- [ ] P8-6 **프론트 공통화(PG-8/9)**: `composables/usePagination.js`(offset)·`useInfiniteScroll.js`(cursor) 작성 후 AgentPanel·SessionPage 스크립트·회의체/아카이브 목록에 적용. PastMeetingsPage의 회의별 sessions N+1 HTTP는 서버에 집계 엔드포인트(회의+세션 요약 한 번에) 또는 배치 조회로 교체.
- [ ] P8-7 **검증/회귀 방지**: 시드 스크립트(채팅 5천 건, 세그먼트 1만 건)로 전후 응답시간·페이로드 크기 측정해 본 문서에 기록. keyset 쿼리 `EXPLAIN`으로 §4.1 인덱스(`idx_chat_messages_thread`, `idx_stt_segments_session`) 사용 확인 — 인덱스 미적용 환경이면 P2-2(V2 마이그레이션)를 선행. 페이지네이션 파라미터 검증(음수/초과 size) 테스트 추가(P7-4와 연계).

**의존 관계**: P0 → P1 → (P2 ∥ P3A) → P3B → P3C, P4는 독립 진행 가능, P5/P6은 P3A(트레이싱·메트릭) 이후 병행, P7은 상시. **P8은 독립 진행 가능하나 P8-7의 인덱스 확인 때문에 P2-2(V2 인덱스)와 같이 가면 효율적**, `/users` 계열(P8-4)은 P1-7과 같은 PR 권장.
**Phase 3 내부 순서가 중요**: 3A(체크포인터·structured output·트레이싱)가 깔려야 3B(Supervisor 전환)를 안전하게 검증할 수 있다 — 측정 수단 없이 아키텍처를 갈아엎지 말 것.

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

-- 응답 피드백 (P3C-3, H-9)
CREATE TABLE IF NOT EXISTS chat_feedback (
    id           BIGSERIAL PRIMARY KEY,
    user_id      BIGINT NOT NULL REFERENCES users(id),
    thread_id    VARCHAR(100) NOT NULL,
    message_id   BIGINT REFERENCES chat_messages(id),
    agent_log_id BIGINT REFERENCES agent_logs(id),
    rating       SMALLINT NOT NULL,               -- 1=👍 / -1=👎
    reason       TEXT,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_chat_feedback_thread ON chat_feedback(thread_id, created_at);
```

> 참고: LangGraph `AsyncPostgresSaver`(P3A-1)는 자체 테이블(`checkpoints` 등)을 `setup()`으로 생성한다 — Flyway 관리 대상 외 스키마(`langgraph`)로 분리 권장.

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

### 4.4 `V4__multitenancy.sql` (P1-7 — §2.12 멀티테넌시)
```sql
-- 회사 정규화 (MT-4): 자유 텍스트 → 엔티티
CREATE TABLE IF NOT EXISTS companies (
    id         BIGSERIAL PRIMARY KEY,
    name       VARCHAR(100) NOT NULL UNIQUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
-- 기존 users.company 문자열에서 회사 생성 후 FK 연결 (오타/동의어는 수동 정리 필요)
INSERT INTO companies (name)
  SELECT DISTINCT trim(company) FROM users
  WHERE company IS NOT NULL AND trim(company) <> ''
  ON CONFLICT (name) DO NOTHING;
ALTER TABLE users ADD COLUMN IF NOT EXISTS company_id BIGINT REFERENCES companies(id);
UPDATE users u SET company_id = c.id FROM companies c WHERE trim(u.company) = c.name;
-- users.company(varchar)는 전환 완료 후 별도 마이그레이션에서 DROP

-- 역할 확장 (MT-1/MT-2): USER / COMPANY_ADMIN / SYSTEM_ADMIN  (V3의 role 컬럼 전제)
-- 초대 기반 온보딩 (MT-2)
CREATE TABLE IF NOT EXISTS invitations (
    id          BIGSERIAL PRIMARY KEY,
    email       VARCHAR(255) NOT NULL,
    company_id  BIGINT REFERENCES companies(id),
    invited_by  BIGINT NOT NULL REFERENCES users(id),
    token_hash  VARCHAR(255) NOT NULL UNIQUE,   -- 초대 링크 토큰의 해시(평문 저장 금지)
    role        VARCHAR(20) NOT NULL DEFAULT 'USER',
    expires_at  TIMESTAMPTZ NOT NULL,
    accepted_at TIMESTAMPTZ,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_invitations_email ON invitations(email);

-- 임시 비밀번호 과도기 지원: 최초 로그인 시 변경 강제
ALTER TABLE users ADD COLUMN IF NOT EXISTS must_change_password BOOLEAN NOT NULL DEFAULT false;
-- 계정 비활성화(퇴사/탈퇴 처리 — 삭제 대신)
ALTER TABLE users ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT true;
```

---

## 5. 핵심 리스크 Top 5 (경영 요약)

1. **외부 공격 표면**(SEC-2/3/4 + SEC-1): 무인증 공개 API로 온톨로지 변조·회의 데이터 절취·비용 발생 공격이 지금 가능. → Phase 0.
2. **권한 모델 부재**(SEC-5/10 + §2.12 MT-1~3): 사용자 간 데이터 격리가 사실상 없음 — 타인 비밀번호 변경(계정 탈취), 전사 디렉터리 노출, 회사(테넌트) 경계 부재. 여러 회사가 모이는 서비스 특성상 컴플라이언스 사고로 직결. → Phase 1 (P1-4·P1-7).
3. **동기화 신뢰성**(DATA-1/2/4): GraphRAG의 근간인 그래프가 조용히 어긋나며, 복구 수단이 재기동뿐(그마저 비용 폭탄 DATA-6). → Phase 2.
4. **화자분리 구조 결함**(STT-1/3): 12초 청크 diarization으로는 "누가 말했나"가 원리적으로 부정확하고, 원음 미보존으로 복구 불가. → Phase 4.
5. **AI 결과 신뢰 불가**(H-1/H-2 + AI-6): HITL 검토가 checkpointer 부재로 동작 불가 의심(테스터가 이미 증상 보고), 파싱 실패 시 50점 가짜 검토가 노출되는데, 이를 탐지할 정확도 지표·테스트·알림이 전무. → Phase 3A/5/6.

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

### 6.4-a Phase 3A (하네스 기반 공사 — Supervisor 전환 전에 먼저)
```
Plan.md §3 Phase 3A를 수행해줘. 순서 중요:
1. 검증: backend/ai/agents/report_reviewer.py와 task_extractor.py의 HITL 그래프(builder.compile() — checkpointer 없음)에서 interrupt()/get_state()/Command(resume)가 실제로 동작하는지 재현 테스트를 먼저 작성해 실행해(동작 안 하면 Plan.md UX-1의 근본 원인). 결과를 Plan.md H-1에 기록.
2. langgraph AsyncPostgresSaver를 도입해 전 그래프를 checkpointer와 함께 compile하고(전용 스키마 langgraph), thread_id를 서버 발급 run_id로 통일해(요청마다 uuid4 생성 제거). HITL 승인 대기가 프로세스 재시작 후에도 살아있는지 테스트로 증명.
3. report_reviewer/task_extractor의 re.search 기반 JSON 파싱을 전부 with_structured_output(pydantic 모델)으로 교체. 파싱 실패 시 1회 재시도, 그래도 실패면 score=50 가짜 결과 대신 명시적 오류 응답을 반환하고 프론트에 "검토 실패 — 재시도" UI를 추가해.
4. main.py의 LANGCHAIN_TRACING_V2 강제 비활성화를 제거하고 env로 제어, trace_id를 agent_logs에 저장.
5. SSE 프로토콜 v2: [PLANNING] 문자열 프리픽스 대신 event: 필드 기반 타입 이벤트(planning|token|tool_call|result|usage|error)+run_id로 교체하고, api.js 파서와 프론트 중단 버튼(AbortController→서버 CancelledError 전파)을 구현해.
6. _make_llm 4중복을 ai/llm_factory.py로 통합(retry/timeout/max_tokens/작업별 모델 테이블/폴백).
각 단계는 기존 기능 동작 동등성 테스트와 함께 별도 커밋으로.
```

### 6.4-b Phase 3B (Supervisor 그래프 + 도구/컨텍스트 엔지니어링)
```
Plan.md §3 Phase 3B와 P3A-4·P3A-5를 수행해줘(3A 완료 전제). routers/supervisor.py(2,593줄)를 해체해서:
- ai/graphs/supervisor_graph.py: LangGraph v1 Supervisor 패턴(supervisor가 handoff tool로 4개 에이전트에 위임, MessagesState+PostgresSaver로 멀티턴 유지). classify_intent 제거. 단순 현황 조회는 다단 그래프 대신 single-loop+도구로 처리.
- ai/tools/: 회의체 현황·아젠다 목록/상태·보고서 제출 현황·그래프 검색·이전 회의록 검색을 @tool로 추출. 모든 도구는 RunnableConfig의 user_id·allowed_meeting_ids로 쿼리를 강제 스코핑(임의 meeting 접근 불가 증명 테스트 포함). 도구 출력은 필요 필드만+상한, 도구 에러는 모델이 복구 가능한 구조화 메시지로.
- 컨텍스트 사전 주입 제거: _get_meeting_context/graph_context_to_str로 시스템 프롬프트에 욱여넣던 것을 도구 JIT 조회로 전환. 시스템 프롬프트는 정적 prefix로 고정(프롬프트 캐시 적중).
- 대화 메모리: 30턴 초과 시 오래된 턴 요약 컴팩션. assistant 메시지는 서버가 저장하고 /api/chats POST는 user role만 허용.
- prompts.py를 ai/prompts/로 분리, 사용자 콘텐츠 구분자+인젝션 가드, 답변에 근거(회의록/노드 ID) 인용 의무화.
AI 데이터 접근 범위를 docs/ai-data-scope.md로 문서화하고, 토큰 로깅(agent_logging)이 계속 작동하는지 확인해.
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

### 6.7 Phase 3C (챗봇 서비스 가드)
```
Plan.md §3 Phase 3C를 수행해줘.
- Redis 기반 rate limiter(사용자별 분당 N회, 일일 토큰 예산 — token_usage_logs 합산)를 FastAPI dependency로 만들어 LLM 호출 라우트에 적용. 초과 시 429+친절한 안내 메시지. 무거운 분석 엔드포인트는 사용자당 동시 1개 세마포어.
- commit/confirm 엔드포인트에 Idempotency-Key(또는 proposal_id 유니크 제약) 중복 차단, 프론트 버튼 더블클릭 가드.
- chat_feedback 테이블(Plan.md §4.2)과 응답별 👍/👎+사유 UI(AgentPanel/AgentSidebar), 수집 데이터를 eval/dataset으로 내보내는 스크립트.
- UX-7(아카이브 저장 실패 팝업 후 성공 메시지) 에러 핸들링 순서 버그를 이 작업에서 함께 수정해.
```

### 6.7-b Phase 1-7 (멀티테넌시 구성원 관리)
```
Plan.md §2.12(MT-1~6)와 §3 P1-7을 수행해줘. 순서:
1. [긴급, 마이그레이션 불필요] UserService.updateUser에서 비밀번호 변경 로직 제거(비밀번호는 본인 PATCH /users/me로만), PATCH /api/v1/users/{id}에 권한 가드(자기 자신 또는 SYSTEM_ADMIN), FastAPI meetings.py:388·524의 user patch 2종에도 동일 가드. 침투 테스트: 일반 사용자 A가 B의 비밀번호/정보를 바꿀 수 없음을 증명.
2. [긴급] GET /api/v1/users·/search·FastAPI users/all·users/search에 가시성 스코프 적용: 내 회사(company) 구성원 + 나와 같은 회의체에 속한 타사 인원만, 타사 인원은 이름·회사·직위만 반환.
3. [마이그레이션] Plan.md §4.4 V4__multitenancy.sql 적용: companies 정규화, invitations, must_change_password, is_active.
4. 초대 기반 온보딩 구현: COMPANY_ADMIN/간사가 이메일+역할로 초대 생성 → 토큰 링크로 본인이 비밀번호 설정. 과도기 모드: 임시 비밀번호 자동 생성(1회 표시) + 최초 로그인 시 변경 강제. OrganizationPage.vue의 비밀번호 입력 필드 제거(UX-25), 구성원 '제거'를 회의체 멤버 제거와 계정 비활성화로 분리(MT-6).
5. 구성원 변경 전부 audit_logs 기록(P1-6 연계), AI 조직 쿼리에 company 스코프(P3B-1 연계).
완료 후 Plan.md §2.12와 P1-7 체크박스를 갱신해줘.
```

### 6.8 GraphRAG 강화 (P0-8 핫픽스 + P3B-6~8)
```
Plan.md §2.10(G-1~G-8)과 §3 P3B-6·P3B-7·P3B-8을 수행해줘. 순서:
1. 핫픽스(P0-8): knowledge_manager.py:267과 minutes_generator.py:46의 'minutes_embedding_index'를 neo4j_sync._VECTOR_INDEXES의 실제 이름 'minutesEmbedding'으로 수정하고, 검색 결과 0건이 반복되면 warning 로그+메트릭을 남기게 해.
2. ai/retrieval_registry.py 생성: 노드 라벨→벡터 인덱스명→반환 필드→풀텍스트 인덱스명을 단일 정의(HC-3 3중 정의 제거). neo4j_sync, knowledge_manager, minutes_generator, task_extractor, report_reviewer가 전부 이 레지스트리를 쓰도록 교체.
3. 모든 에이전트 검색 도구를 vector_search_node(meeting_id=...) 스코핑 변형으로 교체(전역 검색 제거)하고, Neo4j 풀텍스트 인덱스(제목·내용)를 추가해 벡터+풀텍스트 RRF 하이브리드 검색을 구현해.
4. 그래프 네이티브 컨텍스트(P3B-7): "시드 벡터 검색 → 1~2hop 관계 확장 → 경로 포함 근거 반환" 헬퍼를 만들어 supervisor 챗·보고서 분석의 retrieval을 교체하고, 답변에 근거 경로(예: 아젠다→세션→보고서)를 인용하게 해.
5. 과제 추출(P3B-8): extract_agendas_from_context에 유사 과거 아젠다 top-k와 Department-담당부서 이력 기반 부서 추천을 추가하고, 추출된 아젠다를 세션 노드에 연결해(UX-11).
각 단계 후 eval/retrieval_eval.py(질의→기대 노드 20쌍, recall@k·MRR)로 개선 전후를 수치 비교해 Plan.md에 기록해줘.
```

### 6.9 하드코딩 정리 (P7-7)
```
Plan.md §2.11 하드코딩 인벤토리(HC-1~12)를 처리해줘. P1/P3 작업과 겹치는 HC-1·HC-2·HC-3은 제외하고:
- HC-9: backend/ai/neo4j_ids.py 헬퍼(mg_id/agenda_id/session_id/parse_pg_id)를 만들어 'mg-'/'agenda-'/'session-' f-string 산재를 전부 교체.
- HC-4/5: STT 상수(언어맵, sample_rate, 청크/무음 임계값, 화자 라벨 규칙)를 ai/stt_config.py + env로 외출하고 프론트 정규화 중복(useSTT.js normalizeSpeaker)을 서버 응답 기준으로 단일화.
- HC-6: _DETAIL_SCORE_SCHEMA 루브릭을 설정 파일(또는 DB 테이블)로 분리해 가중치 수정에 배포가 필요 없게.
- HC-7: 모델 단가표·STT 단가를 ai/pricing.yaml로 분리.
- HC-8: context_type 정의를 단일 enum 모듈로 통합.
- HC-10: k8s/를 kustomize base+overlay 구조로 재편(네임스페이스·레지스트리·URL 환경별 분리).
- HC-11/12: 상태값 영문 enum화(+표시명 매핑)와 사용자 노출 문구 constants 분리.
각 항목은 동작 동등성 확인 후 별도 커밋으로.
```

### 6.10 Phase 7 (프론트 분해 + UX 백로그)
```
Plan.md §2.8 UX 백로그와 §3 P7-1~3을 수행해줘. 우선순위:
1. UX-3/5: related_agenda_ids의 'agenda-N' ID 노출을 아젠다 제목 표시로 교체, 데이터 없으면 '연관 과제 없음' 표기.
2. UX-6/7: 회의록 다운로드 실패 원인(R2 presigned URL 흐름) 추적·수정, 아카이브 저장의 실패 팝업→성공 메시지 순서 버그 수정.
3. ArchivePage.vue(2,679줄)를 archive/ 하위 컴포넌트와 composable로 분해(목록/필터/검토패널/모달/그래프 연동), SessionPage.vue(1,658줄)를 녹음·스크립트·회의록·채팅 4영역으로 분해. 동작 동등성 유지, 단계별 커밋.
4. 나머지 UX 항목을 작은 PR 단위로 처리하고 Plan.md 체크박스 갱신.
```

### 6.11 Phase 8 (페이지네이션)
```
Plan.md §2.13 페이지네이션 인벤토리(PG-1~10)와 §3 Phase 8(P8-1~7)을 수행해줘. 순서:
1. P8-1: 페이지 응답 계약부터 — Spring ApiResponse에 pageInfo, FastAPI Page[T] 모델, docs/api-pagination.md.
2. P8-2/3: 절벽이 빠른 채팅 이력(keyset before 커서)과 STT 스크립트(after_sec 커서)를 백엔드+프론트(무한 스크롤) 세트로.
3. P8-4/5: 나머지 Spring 목록에 Pageable(파라미터 미지정 시 기존 동작 유지), FastAPI limit/offset + Cypher SKIP/LIMIT, meetings.py:364 N+1 join 교체, /archive 노드 상한.
4. P8-6: usePagination/useInfiniteScroll composable 공통화, PastMeetingsPage N+1 HTTP 제거.
5. P8-7: 시드 데이터로 전후 측정해 Plan.md에 기록, EXPLAIN으로 인덱스 사용 확인.
주의: 기존 프론트가 깨지지 않게 백엔드는 호환 모드(파라미터 옵션) → 프론트 전환 → 기본 size 강제 순. /users 계열은 MT-3 스코프 작업(P1-7)과 같은 PR로.
```

---

## 7. 진행 현황

> ⚠️ **운영 사고 기록 (2026-06-12)**: `k8s/secrets.example.yaml`(placeholder)이 ArgoCD 감시 경로(path: k8s)에 있어 실제 backend-secret(DB_PASSWORD·JWT_SECRET)·postgres-secret(POSTGRES_PASSWORD)을 **빈 값으로 덮어씀** — 다음 pod 재시작 시 기동 불가 상태였음. kubectl로 실값 복구 + 예시 파일을 docs/로 이동(재발 차단) + backend 재시작으로 정상 기동 검증 완료. 교훈: ArgoCD 경로에는 적용 가능한 manifest만 둘 것.

- [x] 전수 감사 완료 (2026-06-12) — 본 문서 작성
- [x] Agentic 하네스/챗봇 서비스 관점 보강 (2026-06-12) — §2.9, Phase 3 재구성(3A/3B/3C), §8 추가
- [x] GraphRAG 실효성·하드코딩 점검 (2026-06-12) — §2.10(G-1~8: 죽은 인덱스명, 그래프 순회 부재 등), §2.11(HC-1~12), H-13 플래닝 연극, P0-8 핫픽스·P3B-6~8·P6-5·P7-7 추가
- [x] 페이지네이션 전수 점검 (2026-06-12) — §2.13(PG-1~10), Phase 8(P8-1~7)·§6.11 추가
- [x] **Phase 0 보안 응급조치 — 코드 측 완료 (2026-06-12)**: P0-2~P0-8 적용 + 퀵윈(BE-5, DATA-2 race, DATA-9, H-3 env화, print 정리). 빌드 검증(Python ast/gradle compileJava/vite build) 통과. **잔여: P0-1 키 회전(사람, SECURITY_ROTATION.md), 클러스터 Secret 생성, WLK WS 인증, /grafana·actuator 정책 결정**
- [x] **Phase 1 인증/인가 통합 — 코드 측 완료 (2026-06-12)**: P1-1~P1-7① 적용·E2E 검증(자세한 내용은 §3 Phase 1 체크박스). Flyway 도입 + V2(refresh_tokens/users.role/audit_logs)·V3(role 부트스트랩) 마이그레이션이 dev DB에 적용됨. **잔여: P1-7②(초대 온보딩·companies 정규화·V4), k8s 배포 시 ai-secret JWT_SECRET 동일값 확인**
- [x] **Phase 2 스키마/동기화 — 완료 (2026-06-12)**: P2-1~P2-8 적용 (V4~V6 마이그레이션 dev DB 적용, Neo4j 제약 적용). 잔여: P2-7 TIMESTAMPTZ 전면 전환(별도 패스), P2-8 프론트 읽기 전환. Phase 1 코드리뷰(7앵글) 반영 커밋 포함.
- [~] **Phase 3A — 사실상 완료 (2026-06-12)**: P3A-1~4·7 완료 + P3A-5 2단계(라우팅 개선 eval 100%, 도구 기반 에이전트 react opt-in) + P3A-6 3단계(SSE v2 전면·중단 버튼·run_id). **잔여: react 모드 dev 평가 후 기본 전환+사전조립 경로 제거, narration 제거**
- [ ] Phase 3B Supervisor 그래프 + 도구/컨텍스트 엔지니어링
- [~] **Phase 3C — 대부분 완료 (2026-06-12)**: 일일 토큰 예산(PG)·idempotency(실패 시 해제)·chat_feedback 수집부+👍/👎 UI. 잔여: P3C-4 출력 가드레일, 동시 1 세마포어, 프론트 더블클릭 가드. ※분당 rate limit은 사용자 결정으로 제외
- [ ] Phase 4 STT 품질
- [ ] Phase 5 관측성/비용
- [ ] Phase 6 평가 체계
- [ ] Phase 7 코드 품질/UX
- [~] Phase 8 페이지네이션 — P8-1 규약 문서·P8-2/3 keyset·P8-4(meetings page/size)·P8-5(/users/all N+1 제거+limit) 완료, PG-8 오진 정정 (2026-06-12). 잔여: users/검색 목록 Pageable, P8-6 loadMore UI, P8-7 시드 측정

---

## 8. 적용한 설계 원칙 레퍼런스 (개선 작업 시 판단 기준)

**Agentic workflow 원칙**
1. **필요한 만큼만 에이전트답게**: 결정 경로가 고정된 작업(회의록 생성, 파일 분석)은 워크플로(체인)로, 동적 판단이 필요한 것(자유 대화, 지식 탐색)만 에이전트 루프로. 멀티 에이전트는 비용·디버깅 난이도가 크므로 supervisor+소수 전문 에이전트 구조를 유지하되 단계 수를 늘리지 않는다.
2. **도구는 계약(contract)**: 이름·설명·입출력 스키마가 명확하고, 출력은 토큰 효율적(필요 필드만), 에러는 모델이 복구할 수 있는 문장으로. 권한 스코프는 도구 내부에서 강제(모델의 선의에 의존 금지).
3. **컨텍스트 엔지니어링**: 시스템 프롬프트는 정적(캐시 적중), 데이터는 just-in-time 도구 조회. 긴 스레드는 컴팩션. "모델에게 다 보여주기"가 아니라 "지금 필요한 것만 보여주기".
4. **내구성 있는 실행**: HITL·장기 작업은 반드시 영속 체크포인터 위에서. 재시작·스케일아웃·네트워크 단절을 기본 전제로 설계(idempotency 포함).
5. **구조화 출력 의무**: 모델 출력을 코드가 소비하면 structured output. regex JSON 파싱과 fabricated fallback은 금지 — 실패는 실패로 노출하고 재시도.

**챗봇 서비스 원칙**
6. **신뢰 우선**: 모르는 것/실패한 것을 꾸미지 않는다. 답변에 근거(출처) 인용. AI 생성물과 확정 데이터(승인된 회의록)를 UI에서 구분.
7. **체감 속도**: TTFT를 측정·관리, 스트리밍 기본, 진행 단계 노출(이미 [PLANNING] 개념 있음 — 타입 이벤트로 정식화), 중단 가능.
8. **운영 가드**: rate limit·예산 상한·동시성 제한은 출시 전 필수. 피드백 수집은 출시 첫날부터(나중에 붙이면 데이터가 없다).

**하네스 엔지니어링**
9. **관측 가능해야 개선 가능**: 트레이스(도구 호출 단위) + 메트릭(TTFT·토큰·실패율) + 평가(골든셋 회귀)가 삼각대. 이 셋 없이 프롬프트/모델 변경 금지.
10. **평가 주도 개발**: 운영 실패 사례(👎, HITL 반려)가 자동으로 eval 데이터셋이 되는 환류 구조. 프롬프트 변경은 eval 점수로 검증 후 배포.
