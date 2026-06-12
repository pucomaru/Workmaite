# 시크릿 관리 매뉴얼 + 자격증명 회전 가이드

> "시크릿을 어디에 두고 어떻게 만드는가"에 대한 실무 매뉴얼.
> git 히스토리에 한 번이라도 커밋된 값은 유출된 것으로 간주하고 교체한다.

---

## 0. 개념 정리 — 시크릿이 사는 곳은 딱 3군데

| 보관 위치 | 용도 | 누가 읽나 | 만드는 방법 |
|---|---|---|---|
| **① k8s Secret** (클러스터 안) | **런타임 비밀**: DB 비번, JWT 시크릿, OpenAI 키, R2 키, Neo4j 비번 | 실행 중인 pod (deployment yaml의 `secretKeyRef`/`secretRef`가 참조) | `kubectl create secret ...` (아래 §1) |
| **② GitHub Actions Secrets** (레포 설정) | **CI 전용 비밀**: Harbor 로그인, git push 토큰 | GitHub Actions 워크플로(`.github/workflows/*.yml`의 `${{ secrets.XXX }}`) | GitHub 웹 UI (아래 §2) |
| **③ 로컬 `.env`** (각자 PC) | 로컬 개발 시 환경변수 | 내 PC의 FastAPI/Spring 프로세스 | 직접 작성, **절대 커밋 금지**(.gitignore 등록됨) |

**Harbor는 시크릿 저장소가 아니다.** Harbor는 도커 이미지 레지스트리일 뿐이고, Harbor와 관련된 시크릿은 두 개다:
- CI가 이미지를 **push**할 때 쓰는 로그인 정보 → ② GitHub Secrets의 `HARBOR_USERNAME`/`HARBOR_PASSWORD`
- 클러스터가 이미지를 **pull**할 때 쓰는 인증 → ① k8s의 `harbor-secret`(docker-registry 타입, 이미 존재)

흐름: `git push` → GitHub Actions(②로 Harbor 로그인) → 이미지 push → ArgoCD가 yaml 변경 감지 → pod 기동 시 ①의 harbor-secret으로 pull, ①의 backend-secret/ai-secret으로 환경변수 주입.

---

## 1. ① k8s Secret — 이번에 새로 만들어야 하는 것

배포 yaml이 이제 `backend-secret`을 참조하므로 **develop 머지/배포 전에 반드시 생성**해야 한다.
(클러스터 접근: 평소 `kubectl`을 쓰던 그 환경에서 실행. 네임스페이스는 `skala3-finalproj-class2-team9`)

```bash
# 1) backend-secret 생성 (Spring Boot용)
kubectl create secret generic backend-secret \
  -n skala3-finalproj-class2-team9 \
  --from-literal=DB_PASSWORD='<PostgreSQL 비밀번호>' \
  --from-literal=JWT_SECRET='<랜덤 48자 이상>'   # 생성: openssl rand -base64 48

# 2) ai-secret에 JWT_SECRET이 같은 값으로 들어있는지 확인 (FastAPI와 공유 검증)
kubectl get secret ai-secret -n skala3-finalproj-class2-team9 \
  -o jsonpath='{.data.JWT_SECRET}' | base64 -d

#    없거나 다르면 갱신:
kubectl patch secret ai-secret -n skala3-finalproj-class2-team9 \
  -p "{\"stringData\":{\"JWT_SECRET\":\"<backend-secret과 동일한 값>\"}}"

# 3) (해당 인스턴스를 실제로 쓸 때만) postgres-secret
kubectl create secret generic postgres-secret \
  -n skala3-finalproj-class2-team9 \
  --from-literal=POSTGRES_PASSWORD='<비밀번호>'

# 4) 확인
kubectl get secrets -n skala3-finalproj-class2-team9
kubectl rollout restart deploy/workmaite-backend -n skala3-finalproj-class2-team9   # 적용
```

이미 클러스터에 존재하는 Secret (참고): `ai-secret`(OpenAI 키, Neo4j 비번 등 FastAPI 환경변수), `r2-secret`(Cloudflare R2 키), `harbor-secret`(이미지 pull), `neo4j-secret`(Neo4j 초기 비번).
값 확인은 `kubectl get secret <이름> -n <ns> -o jsonpath='{.data}'` 후 base64 디코드.

> 주의: `kubectl create secret` 명령은 셸 히스토리에 남는다. 민감하면 `--from-file=DB_PASSWORD=./pw.txt`로 만들고 파일은 삭제.

---

## 2. ② GitHub Actions Secrets — 이미 있고, 회전할 때만 손대면 됨

위치: **GitHub 레포 → Settings → Secrets and variables → Actions → Repository secrets**

| 이름 | 용도 | 회전 방법 |
|---|---|---|
| `HARBOR_USERNAME` / `HARBOR_PASSWORD` | CI가 Harbor에 이미지 push + 오래된 이미지 삭제 | Harbor 웹(amdp-registry.skala-ai.com) 로그인 → 사용자 프로필에서 비밀번호 변경(또는 로봇 계정 재발급) → GitHub 웹에서 값 업데이트 |
| `GIT_TOKEN` | CI가 이미지 태그 갱신 커밋을 push | GitHub → Settings(개인) → Developer settings → Personal access tokens에서 재발급 → 레포 시크릿 업데이트 |

런타임 비밀(DB 비번, OpenAI 키 등)은 **GitHub Secrets에 넣지 않는다** — CI는 그 값들이 필요 없고, 필요한 곳은 클러스터(①)다.

---

## 3. 회전 대상 체크리스트 (git 히스토리에 노출된 것)

| 자격증명 | 노출 위치였던 곳 | 회전 절차 |
|---|---|---|
| PostgreSQL 비번 (`team9postgres1234`) | `k8s/backend.yaml`, `application.yaml` | DB에서 `ALTER USER team9 WITH PASSWORD '...'` → ①의 backend-secret·ai-secret 갱신 → rollout restart |
| JWT 시크릿 | `application.yaml` | 새 값 생성(`openssl rand -base64 48`) → backend-secret과 ai-secret에 **동일 값** 반영 → 전 사용자 재로그인 발생하므로 공지 후 점검 시간대에 |
| INTERNAL_SECRET | `NeoSyncService.java` 기본값, `.env` | 새 랜덤값 → ai-secret 갱신 + backend 환경변수(INTERNAL_SECRET) 추가 → 코드 기본값 제거(P1) |
| Neo4j 비번 (`skala-2-team9`) | `neo4j/k8s/secret.yaml` | Neo4j에서 `ALTER USER neo4j SET PASSWORD '...'` → neo4j-secret·ai-secret 갱신 |
| ~~Redis 비번~~ | `k8s/backend.yaml`(과거 커밋) | **서비스에서 Redis 미사용 확정 — 의존성·설정 제거됨(2026-06-12).** 다만 노출된 비번은 팀 공유 인프라(redis-1-master)의 것이므로 **인프라 관리자에게 노출 사실 통지** |
| OpenAI / LangSmith 키 | 로컬 `.env` (미커밋) | 각 콘솔에서 재발급 → ai-secret(OPENAI_API_KEY 등) 갱신, 로컬 .env 교체 |

회전 후 확인: 로그인 → AI 챗 → 회의체 생성(Neo4j 동기화 로그) → STT 1회.

---

## 4. 재발 방지 규칙

1. **시크릿 값이 들어간 yaml/properties는 커밋 금지** — placeholder 템플릿(`k8s/secrets.example.yaml`)만 커밋.
2. 새 시크릿이 필요하면: 런타임이면 ① k8s Secret + deployment에 `secretKeyRef`, CI면 ② GitHub Secrets. 그 외 선택지는 없다고 생각하면 된다.
3. (권장) CI에 gitleaks 스캔 잡 추가, 로컬에 pre-commit hook (Plan.md INFRA-3).
