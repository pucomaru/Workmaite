# Workmaite CI/CD 초기 배포 파이프라인

## 1. 목적

Workmaite 서비스의 기능 구현 전, 배포 자동화 기반을 먼저 구축한다.

현재 단계에서는 완성된 서비스 코드를 배포하는 것이 아니라, Backend와 AI Agent의 최소 실행 애플리케이션을 기준으로 Docker 이미지 빌드, Amazon ECR Push, Kubernetes 배포, ArgoCD Sync 흐름을 검증한다.

이를 통해 이후 실제 기능 코드가 구현되었을 때 동일한 CI/CD 파이프라인을 통해 자동 배포할 수 있는 기반을 마련한다.

## 2. 초기 배포 대상

Workmaite 프로젝트는 서비스 영역을 다음 구조로 분리한다.

| 구분 | 기술 스택 | 초기 배포 범위 |
|---|---|---|
| Backend | Spring Boot | Docker 이미지 빌드 후 EKS 배포 |
| AI Agent | FastAPI | Docker 이미지 빌드 후 EKS 배포 |
| Frontend | Vue.js | 기본 폴더 구조 생성 후 S3 + CloudFront 배포는 후속 작업으로 진행 |

초기 CI/CD 구현 범위는 Backend와 AI Agent의 배포 자동화에 우선 집중한다. Backend와 AI Agent는 최소 Health Check API를 포함한 실행 가능한 애플리케이션을 기준으로 Docker 이미지 빌드, ECR Push, EKS 배포 흐름을 검증한다.

Frontend는 `frontend/` 폴더를 기준으로 관리하되, 정적 파일 빌드 및 S3 + CloudFront 배포 자동화는 후속 작업에서 구성한다.

## 3. CI/CD 파이프라인 흐름

초기 CI/CD 파이프라인은 다음 흐름을 따른다.

```text
Developer
  ↓
GitHub Push
  ↓
GitHub Actions
  ↓
Docker Image Build
  ↓
Amazon ECR Push
  ↓
Kubernetes Manifest Image Tag Update
  ↓
ArgoCD Sync
  ↓
Amazon EKS Deploy
```

## 4. 구성 요소별 역할

| 구성 요소 | 역할 |
|---|---|
| GitHub | 소스 코드 및 Kubernetes Manifest 저장소 |
| GitHub Actions | Docker 이미지 빌드 및 ECR Push 자동화 |
| Amazon ECR | Backend, AI Agent Docker 이미지 저장소 |
| ArgoCD | Git 기준 Kubernetes 배포 상태 동기화 |
| Amazon EKS | Backend, AI Agent 실행 환경 |
| Kubernetes Manifest | Deployment, Service, Ingress 등 배포 리소스 정의 |

## 5. 이미지 저장소 및 태그 규칙

Amazon ECR Repository는 다음 기준으로 생성한다.

| 서비스 | ECR Repository |
|---|---|
| Backend | `workmaite-backend` |
| AI Agent | `workmaite-ai-agent` |

Docker 이미지 태그는 다음 기준을 사용한다.

| 태그 | 설명 |
|---|---|
| `latest` | 가장 최근 빌드 이미지 |
| `dev-{github-sha}` | develop 또는 작업 브랜치 기준 빌드 이미지 |
| `{version}` | 운영 배포 시 사용하는 버전 태그 |

초기 단계에서는 `latest`와 `dev-{github-sha}`를 우선 사용한다.

## 6. 프로젝트 및 Kubernetes 배포 구조

초기 프로젝트 구조는 다음과 같이 구성한다.

```text
Workmaite/
├── backend/
├── ai-agent/
├── frontend/
├── k8s/
├── docs/
└── .github/

초기 Kubernetes Manifest 구조는 다음과 같다.
k8s/
├── backend/
│   ├── deployment.yml
│   └── service.yml
├── ai-agent/
│   ├── deployment.yml
│   └── service.yml
└── namespace.yml

## 7. Health Check 기준

초기 배포 검증을 위해 각 서비스는 Health Check API를 제공한다.

| 서비스 | Health Check URI |
|---|---|
| Backend | `/api/v1/health` |
| AI Agent | `/health` |

배포 후 각 Pod의 readinessProbe와 livenessProbe는 Health Check API를 기준으로 설정한다.

## 8. 완료 기준

CI/CD 초기 배포 파이프라인의 완료 기준은 다음과 같다.

1. Backend 샘플 애플리케이션이 Docker 이미지로 빌드된다.
2. AI Agent 샘플 애플리케이션이 Docker 이미지로 빌드된다.
3. GitHub Actions에서 이미지 빌드가 자동 실행된다.
4. 빌드된 이미지가 Amazon ECR에 Push된다.
5. Kubernetes Manifest가 작성된다.
6. ArgoCD가 Manifest를 기준으로 EKS에 배포를 수행한다.
7. EKS에서 Backend, AI Agent Pod가 정상 기동된다.
8. Health Check API로 배포 성공 여부를 확인할 수 있다.

## 9. 후속 작업

초기 파이프라인 구축 이후 다음 작업을 진행한다.

- Frontend S3 + CloudFront 배포 자동화
- Nginx Ingress 라우팅 설정
- NLB 외부 진입점 구성
- PostgreSQL, Redis, Neo4j 연결 설정
- Prometheus, Grafana, Loki 기반 모니터링 구성
- 운영 환경 Secret 및 ConfigMap 분리