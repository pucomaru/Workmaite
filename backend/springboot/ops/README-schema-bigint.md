# 스키마 bigint 표준화 — 통합/리셋(A) 가이드

운영 스키마의 id 타입 혼재(int/bigint)와 FK 타입 미스매치를 없애고, Flyway 마이그레이션을
단일 `V1__baseline.sql`로 통합한다. 코드·DB·마이그레이션을 모두 **bigint** 기준으로 정렬한다.

## 무엇이 바뀌었나 (이 PR)

- **`db/migration/V1__baseline.sql`** — 운영 스키마 전체를 통합한 baseline. 모든 id PK = `bigserial`,
  모든 FK = `bigint`. 카운터(`loop_count`, `version`, `block_index`, `prompt_tokens`,
  `completion_tokens`)는 의미상 `integer` 유지.
- **V2~V11 삭제** — 스키마 변경은 V1에 흡수, DML(백필·일회성 권한부여)은 신규 DB엔 불필요하여 제외.
- **SpringBoot 엔티티** — 전부 `Long`(=bigint). 드리프트 정리: `HitlReview`(존재하지 않던
  `target_id`/`review_prompt`/`review_comment` 제거, `comment`/`agenda_id`/`report_id` 정렬),
  `TokenUsageLog.cost`→`estimated_cost_usd(Double)`, `ReportScore.total_score` `Float`→`Double`.
- **FastAPI 모델(`models.py`)** — id/FK·`recording_seconds`=`BigInteger`, `rating`=`SmallInteger`.
- **CI `schema-validate.yml`** — 빈 postgres에 Flyway V1을 적용한 뒤 SpringBoot(Hibernate validate)와
  FastAPI(SQLAlchemy reflect)가 그 스키마와 일치하는지 검증. 양쪽 코드가 스키마에서 드리프트하면 실패.

## 운영 DB 적용 절차 (일회성, `ops/prod-bigint-reconciliation.sql`)

> 운영 스키마를 실제로 bigint로 바꾸는 단계. **이 PR 머지와 별개로, 점검 창에서 수동 수행**한다.
> 코드(엔티티=Long)는 현재 integer 운영 스키마에서도 동작하므로(Long이 integer를 읽는 건 안전),
> 코드 배포와 DB 정비의 선후는 유연하지만 아래 순서를 권장한다.

1. **백업**
   ```bash
   kubectl exec -n postgres <postgres-pod> -- \
     pg_dump --no-owner --no-privileges -Fc -U team9 -d sk-team-9 > backup_$(date +%F).dump
   ```
2. **SpringBoot 앱 중지** (replicas=0 또는 배포 일시정지) — 정비 중 Flyway 재실행 방지.
3. **정비 SQL 실행** (`ops/prod-bigint-reconciliation.sql`) — id/FK 42개를 bigint로 ALTER +
   `flyway_schema_history` DROP. 전체가 한 트랜잭션이라 실패 시 롤백.
   ```bash
   kubectl exec -i -n postgres <postgres-pod> -- \
     psql -U team9 -d sk-team-9 < backend/springboot/ops/prod-bigint-reconciliation.sql
   ```
4. **새 SpringBoot 배포·기동** — Flyway가 "비어있지 않은 스키마 + 이력 없음"을 보고 `baseline-version=1`로
   baseline 처리(V1 SQL 미실행). 이후 스키마 = bigint, 이력 = `[baseline v1]`.
5. **새 FastAPI 배포** — `BigInteger` 모델. (읽기 전용이라 마이그레이션 동작 없음)
6. **검증** — 정비 SQL 하단의 쿼리가 0행인지 확인(남은 integer id/FK 없음).

### 주의: 중간 재기동 금지
3단계(이력 DROP)와 4단계(새 코드 배포) 사이에 **구버전 코드가 재기동되면 안 된다**. 구버전은 V2~V11 파일을
갖고 있어, 빈 이력 + 기존 스키마에서 baseline 후 V2부터 재적용을 시도하다 실패한다. 앱을 내린 상태에서
SQL→새 배포를 연달아 수행하면 이 창이 사라진다.

## 신규 환경(빈 DB)

Flyway가 V1 하나로 전체 스키마를 생성한다(`baseline-on-migrate`는 빈 스키마에선 트리거되지 않아 V1이 실행됨).
별도 조치 불필요.
