# Workma!te

> **Team No.9** | AI 기반 회의 관리 플랫폼

---

## 목차

1. [프로젝트 소개](#프로젝트-소개)
2. [서비스 아키텍처](#서비스-아키텍처)
3. [팀원 소개](#팀원-소개)
4. [사전 준비](#사전-준비)
5. [실행 방법](#실행-방법)
   - [1. PostgreSQL 접속 (포트포워딩)](#1-postgresql-포트포워딩)
   - [2. SpringBoot 백엔드 실행](#2-springboot-백엔드-실행)
   - [3. FastAPI AI 서버 실행](#3-fastapi-ai-서버-실행)
   - [4. Frontend 실행](#4-frontend-실행)
6. [환경변수 설정](#환경변수-설정)
7. [GitHub 기본 개념](#github-기본-개념)
8. [Git 설치 및 초기 설정](#git-설치-및-초기-설정)
9. [작업 흐름 (워크플로우)](#작업-흐름-워크플로우)
10. [자주 쓰는 명령어 모음](#자주-쓰는-명령어-모음)
11. [주의사항](#주의사항)

---

## 프로젝트 소개

**Workma!te**는 AI 에이전트 기반 회의 관리 플랫폼입니다.  
회의 안건 정리, 회의록 생성, Todo 추출, 보고서 검토 등을 AI가 지원합니다.

---

## 서비스 아키텍처

```
Frontend (Vue 3 / Vite)
        │
        ├──▶ SpringBoot  :8080   ← 인증, 회의체/세션/안건/Todo/보고서 CRUD
        │
        └──▶ FastAPI     :8000   ← AI 에이전트 (가온/나루/아라/나온/혜안), 챗 히스토리, WebSocket
                │
                └──▶ PostgreSQL (k8s) ←── 공유 DB
                └──▶ Neo4j           ←── 지식 그래프
```

| 서버 | 역할 | 포트 |
|------|------|------|
| **SpringBoot** | 회원가입·로그인(JWT 발급), 회의체/세션/안건/Todo/보고서 CRUD | `8080` |
| **FastAPI** | AI 에이전트, 챗 히스토리, WebSocket 알림, Neo4j 연동 | `8000` |
| **Vue 3** | 프론트엔드 | `5173` |

> **JWT 공유**: SpringBoot에서 발급된 토큰을 FastAPI가 동일한 시크릿으로 검증합니다.

---

## 팀원 소개

| 역할 | 이름 | GitHub |
|------|------|--------|
| PM  | 안민혁 | [als7928](https://github.com/als7928) |
| Infra | 김세림 | [serim0906](https://github.com/serim0906) |
| Back-end | 이한결 | [hg020121](https://github.com/hg020121) |
| Back-end | 윤세준 | [SejunYOON-ai](https://github.com/SejunYOON-ai) |
| Front-end | 안상연 | [ahnup](https://github.com/ahnup) |
| Infra | 이다예 | [pucomaru](https://github.com/pucomaru)|

---

## 사전 준비

| 항목 | 버전 |
|------|------|
| Java | 21 |
| Python | 3.11+ |
| Node.js | 18+ |
| kubectl | - |
| k9s (선택) | - |

### kubectl 클러스터 접근 확인

```bash
kubectl get nodes
kubectl get svc -n postgres
```

---

## 실행 방법

### 1. PostgreSQL 포트포워딩

> **모든 서버 실행 전에 먼저 포트포워딩을 켜야 합니다.**  
> 터미널 하나를 전용으로 열어두세요.

```bash
kubectl port-forward svc/postgres-1-postgresql 5432:5432 -n postgres
```

| 항목 | 값 |
|------|----|
| Host | `localhost:5432` |
| DB | `sk-team-9` |
| User | `team9` |
| Password | `team9postgres1234` |

psql로 직접 접속하려면:

```bash
PGPASSWORD='team9postgres1234' psql -h localhost -p 5432 -U team9 -d "sk-team-9"
```

---

### 2. SpringBoot 백엔드 실행

```bash
cd backend/springboot
./gradlew bootRun
```

Windows:

```bat
cd backend\springboot
gradlew.bat bootRun
```

서버가 뜨면 `http://localhost:8080` 에서 API가 응답합니다.

> DB 연결 정보는 `backend/springboot/src/main/resources/application.yaml` 에 있습니다.  
> k8s 클러스터 내부 배포 시에는 `url`을 `postgres-1-postgresql.postgres.svc.cluster.local:5432` 로 변경하세요.

---

### 3. FastAPI AI 서버 실행

#### 가상환경 생성 및 패키지 설치 (최초 1회)

```bash
cd backend/ai
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

#### `.env` 파일 생성 (최초 1회)

`backend/ai/.env` 파일을 만들고 아래 내용을 채웁니다:

```env
LANGSMITH_TRACING=true
LANGSMITH_API_KEY=
LANGSMITH_ENDPOINT=https://api.smith.langchain.com
LANGSMITH_PROJECT=

OPENAI_MODEL=
OPENAI_EMBEDDING_MODEL=
OPENAI_TEMPERATURE=0.1
OPENAI_API_KEY=

# Neo4j (kubectl port-forward svc/workmaite-neo4j 7474:7474 7687:7687)
NEO4J_URL=http://localhost:7474
NEO4J_USER=
NEO4J_PASSWORD=
NEO4J_DATABASE=


JWT_SECRET=

# PostgreSQL (kubectl port-forward svc/postgres-1-postgresql 5432:5432 -n postgres)
DB_HOST=localhost
DB_PORT=5432
DB_NAME=
DB_USER=
DB_PASSWORD=
```

#### 서버 실행

```bash
cd backend/ai
source .venv/bin/activate
uvicorn main:app --reload --port 8000
```

서버가 뜨면 `http://localhost:8000/docs` 에서 Swagger UI를 확인할 수 있습니다.

---

### 4. Frontend 실행

#### 패키지 설치 (최초 1회)

```bash
cd frontend
npm install
```

#### 개발 서버 실행

```bash
npm run dev
```

브라우저에서 `http://localhost:5173` 으로 접속합니다.

---

## 환경변수 설정

### FastAPI — `backend/ai/.env`

| 키 | 설명 | 예시 |
|----|------|------|
| `OPENAI_API_KEY` | OpenAI API 키 | `sk-...` |
| `JWT_SECRET` | SpringBoot와 동일한 JWT 시크릿 | `workmaite-shared-secret-...` |
| `DB_HOST` | PostgreSQL 호스트 | `localhost` (포트포워딩 시) |
| `DB_PORT` | PostgreSQL 포트 | `5432` |
| `DB_NAME` | DB 이름 | `sk-team-9` |
| `DB_USER` | DB 사용자 | `team9` |
| `DB_PASSWORD` | DB 비밀번호 | `team9postgres1234` |
| `NEO4J_URL` | Neo4j HTTP URL | `http://localhost:7474` |
| `NEO4J_USER` | Neo4j 사용자 | `neo4j` |
| `NEO4J_PASSWORD` | Neo4j 비밀번호 | `neo4j` |

### SpringBoot — `backend/springboot/src/main/resources/application.yaml`

| 키 | 설명 |
|----|------|
| `spring.datasource.url` | JDBC URL |
| `spring.datasource.username` | DB 사용자 |
| `spring.datasource.password` | DB 비밀번호 |
| `jwt.secret` | JWT 시크릿 (FastAPI `.env`의 `JWT_SECRET`과 동일) |

---

## GitHub 기본 개념

GitHub를 처음 쓰는 분들을 위해 핵심 개념만 간단히 정리했습니다.

### Repository (저장소)
코드와 파일이 저장되는 공간입니다. 지금 보고 있는 이 페이지가 저장소입니다.

### Branch (브랜치)
작업을 분리하는 가지입니다.
- `main` — 완성된 코드만 올라오는 메인 브랜치 (함부로 직접 수정 금지)
- 각자의 작업 브랜치 — 내 작업용으로 따로 만들어 사용

### Commit (커밋)
변경 내용을 저장하는 단위입니다. "저장 + 메모" 라고 생각하면 됩니다.

### Push / Pull
- **Push** — 내 컴퓨터의 변경 내용을 GitHub에 올리기
- **Pull** — GitHub의 최신 내용을 내 컴퓨터로 가져오기

### Pull Request (PR)
내 브랜치의 작업을 `main`에 합치자고 요청하는 것입니다. 팀장이 검토 후 승인합니다.

---

## Git 설치 및 초기 설정

### 1. 이름 & 이메일 등록 (최초 1회)

```bash
git config --global user.name "홍길동"
git config --global user.email "your@email.com"
```

> GitHub 계정 이메일과 동일하게 설정하세요.

### 2. 저장소 복사 (최초 1회)

```bash
git clone https://github.com/als7928/Workmaite.git
cd meetmaite
```

---

## 작업 흐름 (워크플로우)

매번 작업할 때 아래 순서를 따라주세요.

### 1단계 — 최신 코드 받아오기

작업 시작 전에 항상 먼저 실행하세요.

```bash
git pull origin main
```

### 2단계 — 내 작업 브랜치 만들기

```bash
git checkout -b feature/내작업이름
# 예시: git checkout -b feature/login-page
```

> 브랜치 이름은 `feature/기능명` 형식으로 통일합니다.

### 3단계 — 코드 작성

평소처럼 파일을 수정하세요.

### 4단계 — 변경 내용 저장 (커밋)

```bash
git add .
git commit -m "작업 내용을 간단히 설명"
# 예시: git commit -m "로그인 페이지 UI 구현"
```

### 5단계 — GitHub에 올리기 (푸시)

```bash
git push origin feature/내작업이름
```

### 6단계 — Pull Request 생성

1. GitHub 저장소 페이지로 이동
2. 상단에 표시되는 **"Compare & pull request"** 버튼 클릭
3. 제목과 설명 작성 후 **"Create pull request"** 클릭
4. 팀장의 리뷰 및 승인 대기

### 7단계 — 머지 후 정리

PR이 승인되어 `main`에 합쳐지면:

```bash
git checkout main
git pull origin main
```

---

## 자주 쓰는 명령어 모음

```bash
# 현재 상태 확인
git status

# 변경된 내용 확인
git diff

# 브랜치 목록 확인
git branch

# 브랜치 이동
git checkout 브랜치이름

# 커밋 내역 확인
git log --oneline
```

---

## 주의사항

- `main` 브랜치에 직접 Push하지 마세요. 반드시 PR을 통해 합칩니다.
- 작업 시작 전 `git pull`로 최신 코드를 먼저 받아오세요.
- 커밋 메시지는 알아보기 쉽게 한국어로 작성해도 됩니다.
- 충돌(Conflict)이 발생하면 혼자 해결하려 하지 말고 PM에게 먼저 알려주세요.

---

> 궁금한 점은 팀 슬랙에 언제든지 물어보세요!
