# Cloud Architecture

> Workmaite의 실제 배포 구성(`k8s/`, `argocd/`, `.github/workflows/`)을 근거로 도출한 종합 클라우드 아키텍처.
> 핵심 설계 원칙: **GitOps 기반 지속적 배포(ArgoCD) · Kubernetes 위의 3-tier 마이크로서비스 분리 · 관측성(Observability)과 보안(TLS·Secret·IDOR)을 일급(first-class)으로 통합.**

---

## 1. 종합 클라우드 아키텍처 (Comprehensive Cloud Architecture)

```mermaid
flowchart TB
    User([End User · Browser]):::ext
    Dev([Developer]):::ext

    %% ===== CI/CD · GitOps =====
    subgraph CICD["⓪ CI/CD · GitOps Pipeline"]
        direction LR
        GH["GitHub Repo<br/><i>als7928/Workmaite</i>"]
        GHA["GitHub Actions<br/><i>ci/quality · {fastapi, springboot, frontend}</i>"]
        Harbor["Harbor Registry<br/><i>amdp-registry.skala-ai.com</i>"]
        Argo["ArgoCD<br/><i>ns: skala-argocd</i><br/>watch: develop / path=k8s"]
        GH --> GHA --> Harbor
        GH -.->|manifest 변경 감시| Argo
        Harbor -.->|image pull| Argo
    end

    %% ===== Edge =====
    subgraph EDGE["① Edge / Ingress Layer"]
        direction TB
        DNS["DNS<br/>workmaite.project.skala-ai.com"]
        Nginx["Nginx Ingress Controller<br/><i>class: public-nginx</i><br/>proxy-body=100m · timeout=3600s<br/>(WebSocket · SSE · STT 지원)"]
        Cert["cert-manager<br/><i>letsencrypt-prod → TLS</i>"]
        DNS --> Nginx
        Cert -.->|workmaite-tls| Nginx
    end

    %% ===== Kubernetes Cluster =====
    subgraph EKS["② Managed Kubernetes Cluster (SKALA Cloud) — ns: skala3-finalproj-class2-team9"]
        direction TB

        subgraph APP["Application Tier (3-tier Microservices)"]
            direction TB
            FE["workmaite-frontend · :80<br/><b>Vue SPA (Nginx)</b>"]
            BE["workmaite-backend · :8080<br/><b>Spring Boot (prod)</b><br/>인증 · JWT · 비즈니스 API"]
            AI["workmaite-ai · :8000<br/><b>FastAPI · LangGraph Agent</b><br/>/ws · /api/ai · /api/agent · /api/stt"]
            BE -->|"AI_URL · internal /api/sync"| AI
        end

        subgraph DATA["Stateful / Data Tier"]
            direction LR
            Neo[("Neo4j 5.19-community<br/>:7687 bolt · :7474<br/>Vector+Fulltext Index<br/><i>PVC</i>")]
        end

        subgraph OBS["Observability Stack"]
            direction LR
            Prom["Prometheus v2.55.1<br/><i>metrics + rules</i>"]
            Loki["Loki 3.4.1<br/><i>logs</i>"]
            Graf["Grafana 11.5.2 · :3000<br/><i>/grafana</i>"]
            Prom --> Graf
            Loki --> Graf
        end

        Sec[["Secrets<br/>ai-secret · r2-secret<br/>backend-secret · *-tls"]]:::sec
        PDB[["PodDisruptionBudget<br/>(가용성 보장)"]]:::sec
    end

    %% ===== Shared / External Data =====
    subgraph EXT["③ Shared & External Services"]
        direction TB
        PG[("PostgreSQL 15<br/>ns: postgres<br/>postgres-1-postgresql…:5432<br/><b>Source of Truth</b>")]
        R2{{"Cloudflare R2<br/>Object Storage<br/><i>file upload (S3 호환)</i>"}}
        OAI{{"OpenAI API<br/>gpt-4o · text-embedding-3-small<br/>Realtime API (STT)"}}
        LS{{"LangSmith<br/>LLM Tracing"}}
    end

    %% ===== Flows =====
    User -->|HTTPS| DNS
    Dev ==>|git push| GH
    Argo ==>|kubectl apply| EKS

    Nginx -->|"/"| FE
    Nginx -->|"/api"| BE
    Nginx -->|"/api/ai · /ws · /ai …"| AI
    Nginx -->|"/grafana"| Graf

    BE -->|JDBC| PG
    AI -->|bolt| Neo
    AI -->|asyncpg| PG
    AI -.->|"S3 API"| R2
    BE -.->|"S3 API"| R2
    AI -.->|"LLM · Embedding · STT"| OAI
    AI -.->|trace| LS

    AI -.->|/metrics| Prom
    BE -.->|/metrics| Prom
    APP -.->|stdout logs| Loki

    classDef ext fill:#1f2933,stroke:#0b0c0e,color:#fff;
    classDef sec fill:#fef2f2,stroke:#dc2626,color:#7f1d1d;
    classDef default fill:#f5f7fa,stroke:#52606d,color:#1f2933;
    style CICD fill:#f8fafc,stroke:#64748b
    style EDGE fill:#eef2ff,stroke:#4f46e5
    style EKS fill:#ecfdf5,stroke:#059669
    style APP fill:#f0f9ff,stroke:#0284c7
    style DATA fill:#fff7ed,stroke:#ea580c
    style OBS fill:#fdf4ff,stroke:#a21caf
    style EXT fill:#fffbeb,stroke:#d97706
```

---

## 2. 슬라이드 추천 문구 (Slide Copy)

### 제목 / 부제
- **제목:** Cloud Architecture
- **부제:** *GitOps-Driven Microservices on Kubernetes with Integrated Observability*
- **한 줄 요약:** "선언적 GitOps(ArgoCD)로 배포되는 EKS 기반 3-tier 마이크로서비스 — TLS·Secret·관측성을 플랫폼 차원에서 일급으로 통합한다."

### 핵심 메시지 (Bullet Points)
- **선언적 GitOps 배포 (Declarative GitOps):** GitHub Actions가 서비스별로 빌드·품질검사 후 이미지를 **Harbor 레지스트리**에 푸시하고, **ArgoCD**가 `k8s/` 매니페스트를 단일 진실원천(Single Source of Truth)으로 삼아 EKS에 지속 동기화한다.
- **3-tier 마이크로서비스 분리:** **Vue SPA** · **Spring Boot**(인증·JWT·비즈니스) · **FastAPI**(LangGraph 에이전트·STT) 를 독립 배포 단위로 분리하고, Ingress가 경로 기반(path-based)으로 트래픽을 라우팅한다.
- **단일 진실원천 + 하이브리드 데이터 (Polyglot Persistence):** **PostgreSQL**(Source of Truth)과 **Neo4j**(Vector+Fulltext 프로퍼티 그래프)를 역할 분리하고, 파일은 **Cloudflare R2** 객체 스토리지에 저장한다.
- **엣지 보안 & 장기 연결 지원:** **cert-manager + Let's Encrypt**로 자동 TLS를 발급하고, Nginx Ingress의 타임아웃·바디 크기 튜닝으로 **WebSocket·SSE 스트리밍·STT 업로드**를 안정적으로 지원한다.
- **내장 관측성 (Built-in Observability):** **Prometheus·Loki·Grafana** 스택으로 메트릭·로그·대시보드를 클러스터 내부에서 통합 수집하며, PrometheusRule로 경보를 선언한다.
- **운영 안정성 (Operational Resilience):** Readiness/Liveness 프로브, 리소스 requests/limits, **PodDisruptionBudget**, Secret 분리(ai/r2/backend/tls), 내부 전용 `/api/sync` 비노출로 가용성과 보안을 동시에 확보한다.

### 학술적 정의 (Caption / Speaker Note)
> *We deploy a cloud-native, three-tier microservice system on a managed Kubernetes substrate, governed by a declarative GitOps control loop (ArgoCD) that continuously reconciles cluster state against a version-controlled manifest repository. A path-routing ingress with automated TLS provisioning fronts a polyglot persistence layer—relational source-of-truth (PostgreSQL), a hybrid vector/graph store (Neo4j), and S3-compatible object storage (Cloudflare R2)—while a co-located Prometheus/Loki/Grafana stack provides first-class observability across metrics and logs.*

---

## 3. 표기 범례 (Legend)

| 기호 | 의미 |
|------|------|
| `──▶` (실선) | 동기 요청 흐름 (HTTP/JDBC/bolt request) |
| `══▶` (굵은선) | 배포 파이프라인 (git push → ArgoCD apply) |
| `┄┄▶` (점선) | 보조 호출 (외부 API · 메트릭/로그 · TLS 주입) |
| ⓪ CI/CD | GitHub Actions → Harbor → ArgoCD GitOps |
| ① Edge | DNS · Nginx Ingress · cert-manager TLS |
| ② EKS Cluster | App(3-tier) · Data(Neo4j) · Observability · Secret |
| ③ External | PostgreSQL(공용 ns) · Cloudflare R2 · OpenAI(LLM·Embedding·Realtime STT) · LangSmith |

---

### 부록 — 인프라 구성 매핑 (Infra Provenance)

| 구성요소 | 매니페스트 · 출처 |
|----------|-------------------|
| Ingress · TLS · 경로 라우팅 | `k8s/ingress.yaml` — `public-nginx`, `letsencrypt-prod`, host `workmaite.project.skala-ai.com` |
| GitOps 배포 | `argocd/workmaite-app.yaml` — repo/branch=`develop`, path=`k8s`, ns=`skala3-finalproj-class2-team9` |
| CI/품질 파이프라인 | `.github/workflows/ci-{fastapi,springboot,frontend}.yml`, `quality-*.yml` |
| Frontend (Vue) | `k8s/frontend.yaml` — `workmaite-frontend:80`, image `…/workmaite-frontend` |
| Backend (Spring Boot) | `k8s/springboot.yaml` — `workmaite-backend:8080`, `SPRING_PROFILES_ACTIVE=prod`, `AI_URL`, JWT |
| AI (FastAPI · LangGraph) | `k8s/fastapi.yaml` — `workmaite-ai:8000`, probes `/health`, `ai-secret`·`r2-secret` |
| Neo4j (Graph + Vector) | `k8s/neo4j/{deployment,service,pvc,configmap}.yaml` — `neo4j:5.19-community`, bolt `7687` |
| PostgreSQL (Source of Truth) | `postgres-1-postgresql.postgres.svc.cluster.local:5432` (공용 `postgres` ns) |
| 관측성 스택 | `k8s/workmaite-{prometheus,loki,grafana}.yaml`, `k8s/prometheus-rules.yaml` |
| 가용성 · 보안 | `k8s/pdb.yaml`, `k8s/secrets.yaml`, `harbor-secret`(imagePullSecret) |
| 객체 스토리지 | `r2-secret` (Cloudflare R2 · S3 호환 API) |
| LLM / Embedding / STT | OpenAI `gpt-4o` · `text-embedding-3-small` · Realtime API STT (`ai-secret`) |
| LLM 트레이싱 | LangSmith (`LANGSMITH_*`) |

```mermaid
flowchart TB
    User([End User · Browser]):::ext
    Dev([Developer]):::ext
    %% ===== CI/CD · GitOps =====
    subgraph CICD["⓪ CI/CD · GitOps Pipeline"]
        direction LR
        GH["GitHub Repo<br/><i>als7928/Workmaite</i>"]
        GHA["GitHub Actions<br/><i>ci/quality · {fastapi, springboot, frontend}</i>"]
        Harbor["Harbor Registry<br/><i>amdp-registry.skala-ai.com</i>"]
        Argo["ArgoCD<br/><i>ns: skala-argocd</i><br/>watch: develop / path=k8s"]
        GH --> GHA --> Harbor
        GH -.->|manifest 변경 감시| Argo
        Harbor -.->|image pull| Argo
    end
    %% ===== Edge =====
    subgraph EDGE["① Edge / Ingress Layer"]
        direction TB
        DNS["DNS<br/>workmaite.project.skala-ai.com"]
        Nginx["Nginx Ingress Controller<br/><i>class: public-nginx</i><br/>proxy-body=100m · timeout=3600s<br/>(WebSocket · SSE · STT 지원)"]
        Cert["cert-manager<br/><i>letsencrypt-prod → TLS</i>"]
        DNS --> Nginx
        Cert -.->|workmaite-tls| Nginx
    end
    %% ===== Kubernetes Cluster =====
    subgraph EKS["② Managed Kubernetes Cluster (SKALA Cloud) — ns: skala3-finalproj-class2-team9"]
        direction TB
        subgraph APP["Application Tier (3-tier Microservices)"]
            direction TB
            FE["workmaite-frontend · :80<br/><b>Vue SPA (Nginx)</b>"]
            BE["workmaite-backend · :8080<br/><b>Spring Boot (prod)</b><br/>인증 · JWT · 비즈니스 API"]
            AI["workmaite-ai · :8000<br/><b>FastAPI · LangGraph Agent</b><br/>/ws · /api/ai · /api/agent · /api/stt"]
            BE -->|"AI_URL · internal /api/sync"| AI
        end
        subgraph DATA["Stateful / Data Tier"]
            direction LR
            Neo[("Neo4j 5.19-community<br/>:7687 bolt · :7474<br/>Vector+Fulltext Index<br/><i>PVC</i>")]
        end
        subgraph OBS["Observability Stack"]
            direction LR
            Prom["Prometheus v2.55.1<br/><i>metrics + rules</i>"]
            Loki["Loki 3.4.1<br/><i>logs</i>"]
            Graf["Grafana 11.5.2 · :3000<br/><i>/grafana</i>"]
            Prom --> Graf
            Loki --> Graf
        end
        Sec[["Secrets<br/>ai-secret · r2-secret<br/>backend-secret · *-tls"]]:::sec
        PDB[["PodDisruptionBudget<br/>(가용성 보장)"]]:::sec
    end
    %% ===== Shared / External Data =====
    subgraph EXT["③ Shared & External Services"]
        direction TB
        PG[("PostgreSQL 15<br/>ns: postgres<br/>postgres-1-postgresql…:5432<br/><b>Source of Truth</b>")]
        R2{{"Cloudflare R2<br/>Object Storage<br/><i>file upload (S3 호환)</i>"}}
        OAI{{"OpenAI API<br/>gpt-4o · text-embedding-3-small<br/>Realtime API (STT)"}}
        LS{{"LangSmith<br/>LLM Tracing"}}
    end
    %% ===== Flows =====
    User -->|HTTPS req| DNS
    Nginx -.->|"HTTPS resp · SPA · API · WS/SSE"| User
    Dev ==>|git push| GH
    Argo ==>|kubectl apply| EKS
    Nginx -->|"/"| FE
    Nginx -->|"/api"| BE
    Nginx -->|"/api/ai · /ws · /ai …"| AI
    Nginx -->|"/grafana"| Graf
    BE -->|JDBC| PG
    AI -->|bolt| Neo
    AI -->|asyncpg| PG
    AI -.->|"S3 API"| R2
    BE -.->|"S3 API"| R2
    AI -.->|"LLM · Embedding · STT"| OAI
    AI -.->|trace| LS
    AI -.->|/metrics| Prom
    BE -.->|/metrics| Prom
    APP -.->|stdout logs| Loki
    classDef ext fill:#1f2933,stroke:#0b0c0e,color:#fff;
    classDef sec fill:#fef2f2,stroke:#dc2626,color:#7f1d1d;
    classDef default fill:#f5f7fa,stroke:#52606d,color:#1f2933;
    style CICD fill:#f8fafc,stroke:#64748b
    style EDGE fill:#eef2ff,stroke:#4f46e5
    style EKS fill:#ecfdf5,stroke:#059669
    style APP fill:#f0f9ff,stroke:#0284c7
    style DATA fill:#fff7ed,stroke:#ea580c
    style OBS fill:#fdf4ff,stroke:#a21caf
    style EXT fill:#fffbeb,stroke:#d97706
```

```mermaid
flowchart TB
    User([사용자 · 웹브라우저]):::ext
    Dev([개발자]):::ext
    %% ===== CI/CD · GitOps =====
    subgraph CICD["⓪ 자동 배포 파이프라인 (CI/CD · GitOps)"]
        direction LR
        GH["소스코드 저장소<br/>(GitHub · als7928/Workmaite)"]
        GHA["빌드·검사 자동화<br/>(GitHub Actions)"]
        Harbor["컨테이너 이미지 보관소<br/>(Harbor Registry)"]
        Argo["자동 배포 관리자<br/>(ArgoCD)"]
        GH --> GHA --> Harbor
        GH -.->|변경 감시| Argo
        Harbor -.->|이미지 가져오기| Argo
    end
    %% ===== Edge =====
    subgraph EDGE["① 외부 진입 관문 (Edge / Ingress)"]
        direction TB
        DNS["주소 안내<br/>(DNS · workmaite.project.skala-ai.com)"]
        Nginx["관문·트래픽 분배기<br/>(Nginx Ingress)<br/>실시간 통신·음성 지원"]
        Cert["보안 인증서 관리<br/>(cert-manager · TLS)"]
        DNS --> Nginx
        Cert -.->|인증서 적용| Nginx
    end
    %% ===== Kubernetes Cluster =====
    subgraph EKS["② 서비스 운영 클러스터 (Kubernetes · SKALA Cloud)<br/><i>Pod egress는 플랫폼이 NAT 처리 (별도 선언 없음)</i>"]
        direction TB
        subgraph APP["서비스 본체 (3계층 구조)"]
            direction TB
            FE["화면·사용자 인터페이스<br/>(Vue · Nginx)"]
            BE["핵심 업무 처리·로그인<br/>(Spring Boot · JWT)"]
            AI["AI 비서·음성 처리<br/>(FastAPI · LangGraph)"]
            BE -->|내부 연동| AI
        end
        subgraph DATA["AI 전용 데이터 (그래프)"]
            direction LR
            Neo[("지식 그래프 저장소<br/>(Neo4j · 벡터 검색)")]
        end
        subgraph OBS["모니터링 (관측)"]
            direction LR
            Prom["지표 수집<br/>(Prometheus)"]
            Loki["로그 수집<br/>(Loki)"]
            Graf["대시보드<br/>(Grafana)"]
            Prom --> Graf
            Loki --> Graf
        end
        Sec[["비밀 정보 보관<br/>(Secrets · 인증키·인증서)"]]:::sec
        PDB[["서비스 중단 방지<br/>(PodDisruptionBudget)"]]:::sec
    end
    %% ===== Shared / External Data =====
    subgraph EXT["③ 공용·외부 서비스 (Pod egress → 플랫폼 NAT 경유)"]
        direction TB
        PG[("핵심 데이터베이스<br/>(PostgreSQL · 원본 데이터)")]
        R2["파일 저장소<br/>(Cloudflare R2 · S3 호환)"]
        OAI["AI 모델 서비스<br/>(OpenAI · GPT·음성인식)"]
        LS["AI 동작 추적<br/>(LangSmith)"]
    end
    %% ===== Flows =====
    User -->|"요청 (HTTPS)"| DNS
    Nginx -.->|"응답 (화면·데이터·실시간)"| User
    Dev ==>|코드 업로드| GH
    Argo ==>|배포 실행| EKS
    Nginx -->|화면 요청| FE
    Nginx -->|업무 요청| BE
    Nginx -->|AI·실시간 요청| AI
    Nginx -->|모니터링 화면| Graf
    BE -->|데이터 조회·저장| PG
    AI -->|그래프 조회| Neo
    AI -->|데이터 조회·저장| PG
    AI -.->|파일 저장·조회| R2
    BE -.->|파일 저장·조회| R2
    AI -.->|AI 호출·음성인식| OAI
    AI -.->|동작 기록| LS
    AI -.->|지표 전송| Prom
    BE -.->|지표 전송| Prom
    APP -.->|로그 전송| Loki
    classDef ext fill:#1f2933,stroke:#0b0c0e,color:#fff;
    classDef sec fill:#fef2f2,stroke:#dc2626,color:#7f1d1d;
    classDef default fill:#f5f7fa,stroke:#52606d,color:#1f2933;
    style CICD fill:#f8fafc,stroke:#64748b
    style EDGE fill:#eef2ff,stroke:#4f46e5
    style EKS fill:#ecfdf5,stroke:#059669
    style APP fill:#f0f9ff,stroke:#0284c7
    style DATA fill:#fff7ed,stroke:#ea580c
    style OBS fill:#fdf4ff,stroke:#a21caf
    style EXT fill:#fffbeb,stroke:#d97706
```