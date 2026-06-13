# Workma!te

AI Archive Link Platform — Team No.9

---

## 아키텍처

```
Frontend (Vue 3)
    ├── SpringBoot :8080  — 인증(JWT), CRUD
    └── FastAPI    :8000  — AI 에이전트, WebSocket, Neo4j
                               ├── PostgreSQL (k8s)
                               └── Neo4j
```

---

## 팀원

| 역할 | 이름 |
|------|------|
| PM | 안민혁 |
| Front-end & AI | 안상연 |
| Back-end & AI | 이한결 · 윤세준 |
| Infra & AI | 김세림 · 이다예 |

---

## 실행

### 0. 포트포워딩 (로컬 실행 시)

```bash
kubectl port-forward svc/postgres-1-postgresql 5432:5432 -n postgres

kubectl port-forward svc/workmaite-neo4j 7474:7474 7687:7687
```

### 1. SpringBoot

```bash
cd backend/springboot
./gradlew bootRun        # Windows: gradlew.bat bootRun
```

### 2. FastAPI

```bash
cd backend/ai
uv run uvicorn main:app --reload --port 8000
```

### 3. Frontend

```bash
cd frontend
npm install --os=linux --cpu=x64 --libc=musl --os=linux --cpu=x64 --libc=glibc --os=darwin --cpu=arm64 --os=win32 --cpu=x64
npm run dev
```

---

## 환경변수

`backend/ai/.env` 파일을 생성합니다 (`.env.example` 참고).

| 키 | 설명 |
|----|------|
| `OPENAI_API_KEY` | OpenAI API 키 |
| `JWT_SECRET` | SpringBoot `application.yaml`의 `jwt.secret`과 동일 |
| `DB_HOST` / `DB_PORT` / `DB_NAME` / `DB_USER` / `DB_PASSWORD` | PostgreSQL 접속 정보 |
| `NEO4J_URL` / `NEO4J_USER` / `NEO4J_PASSWORD` | Neo4j 접속 정보 |

---
