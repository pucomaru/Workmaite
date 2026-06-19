# WorkMaite

> AI 기반 회의체 운영 플랫폼 — 회의 녹취부터 안건 추출, 회의록 작성, 보고서 검토까지 하나의 워크플로우로.

WorkMaite는 여러 회사·부서의 인원이 모여 구성하는 **회의체(meeting group)** 를 중심으로, 회의 진행 과정에서 발생하는 음성·문서·의사결정을 AI 에이전트와 지식 그래프(GraphRAG)로 연결해 관리하는 B2B 협업 서비스입니다.

## 주요 기능

- **실시간 STT & 화자 분리** — WebSocket으로 회의 음성을 실시간 전사하고, 회의체 구성원·용어 사전을 프롬프트에 주입해 정확도를 높입니다(`SttSegment` 단위 화자/구간 저장).
- **AI 안건 추출** — 회의 맥락과 조직 지식 그래프를 바탕으로 실행 과제(아젠다)를 도출하고 담당 부서를 제안합니다.
- **회의록 자동 생성** — 녹취·안건·첨부 문서를 종합해 구조화된 회의록을 작성합니다.
- **보고서 AI 검토** — 12대 평가 요소 루브릭으로 보고서를 채점하고 개선점을 제시합니다.
- **지식 그래프 & 챗봇** — 회의체·세션·안건·문서·구성원을 온톨로지로 연결하고, 자연어 질의에 Text2Cypher / 벡터 검색 기반으로 답변합니다.
- **에이전트 직접 액션(HITL)** — 챗봇에서 아젠다·회의록·보고서·회의를 생성/수정/삭제하며, 휴먼인더루프 검토를 거칩니다.
- **운영 거버넌스** — RBAC(접근 가드), 감사 로그 미들웨어, 토큰·비용 추적(usage) 대시보드를 제공합니다.

## 아키텍처

```
Vue 3 SPA ──┐
            ├─ Ingress (TLS) ─┬─ Spring Boot : 인증/인가, 회의체·세션·안건·회의록·보고서 도메인 (/api/**)
            │                 ├─ FastAPI      : AI 오케스트레이션, STT, GraphRAG, 동기화 수신 (/api/agent, /api/stt, /api/sync ...)
            │                 └─ (FastAPI 내부) OpenAI STT/LLM 호출
            │
   PostgreSQL (도메인 데이터, 단일 소스) ──┐
                                          ├─ Outbox 디스패처 → FastAPI /api/sync → Neo4j (지식 그래프 + 벡터 인덱스)
   Cloudflare R2 (음성·첨부 파일 저장) ────┘
```

- **AI 오케스트레이션**: LangGraph 1.x 기반 supervisor가 사용자 의도를 분류한 뒤 4개 전문 에이전트(`task_extractor`, `minutes_generator`, `report_reviewer`, `knowledge_manager`)에 위임하거나, 도구(tool) 기반으로 직접 액션을 수행합니다. 대화 상태는 `langgraph-checkpoint-postgres`로 영속화합니다.
- **데이터 정합성**: PostgreSQL을 단일 소스로 두고, 트랜잭션 아웃박스 패턴(`NeoSyncService` → `neo4j_sync_outbox` → `SyncOutboxDispatcher` 폴러)으로 Neo4j에 안정적으로 동기화합니다(커밋 후 전달, 실패 시 재시도·삭제 전파).
- **GraphRAG**: 노드/문서 청크 임베딩과 Neo4j 벡터 인덱스, Text2Cypher, 한국어 형태소 분석(kiwipiepy)을 결합해 회의록·보고서·지식 검색을 수행합니다.
- **관측성**: 두 백엔드 모두 Prometheus 메트릭(`/metrics`)을 노출하고, LLM 토큰·비용은 `usage` 라우터와 `pricing.yaml`로 추적합니다.

## 기술 스택

| 영역 | 스택 |
|------|------|
| Frontend | Vue 3.5, Vite 8, Pinia 3, Vue Router 5, TipTap 3(표/리치텍스트), PixiJS 8 + d3-force/d3-zoom(그래프 뷰), Bootstrap 5, marked, DOMPurify, axios |
| Backend (도메인) | Spring Boot 4.1, Java 21, Gradle(Kotlin DSL), Spring Data JPA, Spring Security + JWT(jjwt), springdoc-openapi, Actuator + Micrometer(Prometheus), Lombok |
| Backend (AI) | FastAPI 0.136, Python 3.11, SQLAlchemy 2.0, LangGraph 1.x, LangChain 1.x, langgraph-checkpoint-postgres, OpenAI(gpt-4o 계열) |
| 문서/리포트 처리 | pypdf · pdfplumber · python-docx · openpyxl(파싱), markdown + WeasyPrint(PDF 생성), tiktoken |
| STT | OpenAI 전사 모델(`gpt-realtime-whisper` 실시간 / `gpt-4o-transcribe` 배치), WebSocket 실시간 스트리밍 |
| Data | PostgreSQL(단일 소스), Neo4j 6 + neo4j-graphrag(GraphRAG·벡터), kiwipiepy(한국어 형태소) |
| Storage | Cloudflare R2(S3 호환, boto3) |
| Infra | Docker, Kubernetes, ArgoCD(GitOps), Harbor, GitHub Actions |
| 관측 | Prometheus, Loki, Grafana |
| 품질 도구 | (FE) ESLint 10 · Prettier · Vitest 4 · (AI) ruff · mypy · deptry · pip-audit · (도메인) Spotless · Checkstyle · PMD · SpotBugs |

## 로컬 개발

### 사전 요구사항
- Node.js 20+, Java 21+, Python 3.11+ ([uv](https://github.com/astral-sh/uv) 권장)
- Docker (PostgreSQL / Neo4j), kubectl (포트포워딩용)

### 실행

```bash
# 0. 환경 변수 (OpenAI 키, R2 자격증명, DB/Neo4j 접속정보 등)
cp .env.example .env

# 1. 데이터베이스 실행 및 포트포워딩
docker compose -f postgres/docker-compose.yml up -d
kubectl port-forward svc/postgres-1-postgresql 5432:5432 -n postgres

docker compose -f neo4j/docker-compose.yml up -d
kubectl port-forward svc/workmaite-neo4j 7687:7687

# (최초 1회) 스키마/인덱스 적용
psql "$DATABASE_URL" -f ddl/schema.sql -f ddl/relation.sql -f ddl/index.sql

# 2. Spring Boot (도메인 API, :8080)
cd backend/springboot && ./gradlew bootRun     # 리포 루트 .env를 자동 주입

# 3. FastAPI (AI 서버, :8000)
cd backend/fastapi && uv sync && uv run uvicorn main:app --reload --port 8000

# 4. Frontend (:5173)
cd frontend && npm install && npm run dev
```

## 품질 / 테스트

```bash
# Frontend — 린트 + 단위 테스트(Vitest)
cd frontend && npm run lint && npm run test

# Spring Boot — 포맷/정적분석/테스트 (Spotless·Checkstyle·PMD·SpotBugs 포함)
cd backend/springboot && ./gradlew check

# FastAPI — 린트·타입·의존성 검사
cd backend/fastapi && uv run ruff check . && uv run mypy . && uv run deptry .

# AI 평가 하네스 (라우팅/추출/근거성/지연/보고서 회귀)
cd backend/fastapi && uv run python eval/run_eval.py
```

## 배포

`develop` 브랜치에 푸시하면 GitHub Actions가 서비스별 CI(`ci-frontend`·`ci-springboot`·`ci-fastapi`)로 컨테이너 이미지를 빌드해 Harbor에 푸시하고, k8s 매니페스트의 이미지 태그를 갱신합니다. ArgoCD가 이를 감지해 클러스터에 GitOps 방식으로 배포합니다. 별도의 `quality-*` 워크플로우가 정적분석·테스트를 수행하며, 모든 시크릿은 Kubernetes Secret으로 관리됩니다.

## 디렉터리 구조

```
backend/
  ├─ springboot/          # Spring Boot 도메인 서버 (Gradle, Java 21)
  │   └─ src/main/java/com/workmaite/
  │       ├─ domain/      # auth · user · company · meetings · sessions · agendas
  │       │               #  minutes · reports · scripts · chat · home · logs · audit
  │       └─ global/      # config · auth(JWT) · sync(Outbox→Neo4j) · audit · exception · common
  └─ fastapi/             # FastAPI AI 서버 (Python 3.11)
      ├─ agents/          # task_extractor · minutes_generator · report_reviewer · knowledge_manager
      ├─ graphs/          # LangGraph supervisor / agent 워크플로우
      ├─ routers/         # supervisor · stt · sessions · meetings · knowledge · sync · usage · upload ...
      ├─ graphdb/         # Neo4j 클라이언트 · GraphRAG · Text2Cypher · 임베딩 · 동기화
      ├─ realtime/        # 실시간 전사 WebSocket · SSE
      ├─ llm/             # LLM 팩토리 · 토큰/비용 메트릭 · pricing.yaml
      ├─ core/            # 인증 · 접근 가드 · 감사 미들웨어 · STT 프롬프트
      ├─ db/              # SQLAlchemy 모델 · 스키마 · 세션
      ├─ services/ tools/ storage/   # 헬퍼 · 에이전트 도구 · R2 스토리지
      └─ eval/            # AI 평가 하네스(dataset/ · results/)

frontend/                 # Vue 3 SPA (Vite)
  └─ src/
      ├─ pages/ components/ layouts/   # 화면 · UI 컴포넌트 · 레이아웃
      ├─ stores/          # Pinia 스토어 (auth · meetings · sessions · network · theme · llmModel)
      ├─ composables/     # useRealtimeSTT · useAgentChat · useGraphBuilder ...
      ├─ graph/ icons/ utils/ assets/  # 그래프 스키마 · 아이콘 · 유틸 · 정적 자원
      └─ api.js router.js
  └─ tests/               # Vitest 단위 테스트

ddl/                      # PostgreSQL DDL (schema · relation · index · graph_relations)
k8s/                      # Kubernetes 매니페스트 (서비스 · ingress · 관측 스택 · secrets)
argocd/                   # ArgoCD Application 정의
neo4j/, postgres/         # 로컬 개발용 Docker (docker-compose)
.github/workflows/        # CI(ci-*) · 품질(quality-*) 파이프라인
docs/                     # 아키텍처·파이프라인·데이터 스코프 문서
```
