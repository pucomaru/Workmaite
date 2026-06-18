# WorkMaite

> AI 기반 회의체 운영 플랫폼 — 회의 녹취부터 안건 추출, 회의록 작성, 보고서 검토까지 하나의 워크플로우로.

WorkMaite는 여러 회사·부서의 인원이 모여 구성하는 **회의체(meeting group)** 를 중심으로, 회의 진행 과정에서 발생하는 음성·문서·의사결정을 AI 에이전트와 지식 그래프(GraphRAG)로 연결해 관리하는 B2B 협업 서비스입니다.

## 주요 기능

- **실시간 STT & 화자 분리** — 회의 음성을 텍스트로 변환하고 화자별로 정리합니다.
- **AI 안건 추출** — 회의 맥락과 조직 지식 그래프를 바탕으로 실행 과제(아젠다)를 도출하고 담당 부서를 제안합니다.
- **회의록 자동 생성** — 녹취·안건·첨부 문서를 종합해 구조화된 회의록을 작성합니다.
- **보고서 AI 검토** — 12대 평가 요소 루브릭으로 보고서를 채점하고 개선점을 제시합니다.
- **지식 그래프 & 챗봇** — 회의체·세션·안건·문서·구성원을 온톨로지로 연결하고, 자연어 질의에 그래프 기반으로 답변합니다.
- **운영 거버넌스** — RBAC, 감사 로그, 토큰·비용 추적 대시보드를 제공합니다.

## 아키텍처

```
Vue 3 SPA ──┐
            ├─ Ingress (TLS) ─┬─ Spring Boot  : 인증/인가, 회의체·보고서·회의록 도메인 (/api/**)
            │                 ├─ FastAPI       : AI 오케스트레이션, STT, 동기화 (/api/agent, /api/ai ...)
            │                 └─ WhisperX       : STT + 화자 분리
            │
   PostgreSQL (도메인 데이터, 단일 소스) ──┐
                                          └─ Outbox 동기화 → Neo4j (지식 그래프 + 벡터 인덱스)
```

- **AI 오케스트레이션**: LangGraph 기반으로 사용자 의도를 분류한 뒤 4개 전문 에이전트(`task_extractor`, `minutes_generator`, `report_reviewer`, `knowledge_manager`)에 위임합니다.
- **데이터 정합성**: PostgreSQL을 단일 소스로 두고, 트랜잭션 아웃박스 패턴으로 Neo4j에 안정적으로 동기화합니다(재시도·삭제 전파 포함).
- **GraphRAG**: 노드/청크 임베딩(`text-embedding-3-small`, 1536d)과 벡터 인덱스로 회의록·보고서·지식 검색을 수행합니다.

## 기술 스택

| 영역 | 스택 |
|------|------|
| Frontend | Vue 3, Vite, Pinia, Vue Router, TipTap, PixiJS(그래프 뷰), DOMPurify |
| Backend (도메인) | Spring Boot 3.3.5, Java 17, Spring Security(JWT), Flyway |
| Backend (AI) | FastAPI, Python 3.11, LangGraph, LangChain, OpenAI(gpt-4o-mini) |
| Data | PostgreSQL, Neo4j(GraphRAG) |
| STT | WhisperX(+pyannote), Google Cloud Speech |
| Infra | Docker, Kubernetes, ArgoCD, Harbor, GitHub Actions |
| 관측 | Prometheus, Loki, Grafana |

## 로컬 개발

### 사전 요구사항
- Node.js 20+, Java 17+, Python 3.11+ ([uv](https://github.com/astral-sh/uv) 권장)
- Docker (PostgreSQL / Neo4j)

### 실행

```bash
# 0. 환경 변수
cp .env.example .env   # OpenAI 키 등 채우기

# 1. 데이터베이스 실행 및 포트포워딩
docker compose -f postgres/docker-compose.yml up -d
kubectl port-forward svc/postgres-1-postgresql 5432:5432 -n postgres

docker compose -f neo4j/docker-compose.yml up -d
kubectl port-forward svc/workmaite-neo4j 7687:7687


# 2. Spring Boot (도메인 API, :8080)
cd backend && ./mvnw spring-boot:run

# 3. FastAPI (AI 서버, :8000)
cd backend/fastapi && uv sync && uv run uvicorn main:app --reload --port 8000

# 4. Frontend (:5173)
cd frontend && npm install && npm run dev
```

## 품질 / 테스트

```bash
# Frontend
cd frontend && npm run lint && npm run test

# FastAPI
cd backend/fastapi && uv run ruff check . && uv run mypy .

# AI 평가 하네스 (정확도/근거성/지연/보고서 회귀)
cd backend/fastapi && uv run python eval/run_eval.py
```

## 배포

`develop` 브랜치에 푸시하면 GitHub Actions가 컨테이너 이미지를 빌드해 Harbor에 푸시하고, k8s 매니페스트의 이미지 태그를 갱신합니다. ArgoCD가 이를 감지해 클러스터에 GitOps 방식으로 배포합니다. 모든 시크릿은 Kubernetes Secret으로 관리됩니다.

## 디렉터리 구조

```
backend/
  ├─ src/, pom.xml      # Spring Boot 도메인 서버
  └─ fastapi/           # FastAPI AI 서버 (agents/, graphs/, routers/, eval/)
frontend/               # Vue.js 3
k8s/                    # Kubernetes 매니페스트
neo4j/, postgres/       # 로컬 개발용 Docker (docker-compose)
docs/                   # 문서
```
