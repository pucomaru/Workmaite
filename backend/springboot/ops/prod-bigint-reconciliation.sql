-- ============================================================================
-- 운영 DB 일회성 정비: 모든 id/FK를 bigint로 표준화 + Flyway 이력 리셋(V1 baseline 통합)
-- ============================================================================
-- 배경: 운영 스키마가 int/bigint 혼재였고(원본 Python 테이블=integer, 이후 Java 추가=bigint),
--       FK 타입 미스매치 8건이 있었다. 코드(SpringBoot 엔티티=Long, FastAPI 모델=BigInteger)와
--       Flyway V1 baseline은 전부 bigint 기준으로 통일했다. 이 스크립트로 운영도 맞춘다.
--
-- ⚠️ 실행 전 필수:
--   (1) 백업:  pg_dump --no-owner --no-privileges -Fc -d sk-team-9 -f backup_$(date +%F).dump
--   (2) SpringBoot 앱 중지(배포 일시정지/replicas=0) — 정비 중 Flyway 재실행을 막아야 한다.
--       (FastAPI는 읽기 전용 매핑이라 중지 불필요하나, ALTER 동안 짧은 락이 걸릴 수 있음)
--   (3) 한산한 시간대(점검 창)에 수행.
--
-- 안전성: integer→bigint는 "확장(widening)"이라 데이터 손실이 없다. PG 시퀀스는 내부적으로
--         int8이라 별도 변경이 필요 없다. 전체를 트랜잭션으로 감싸 실패 시 전부 롤백된다.
-- ============================================================================

BEGIN;

-- 1) integer id/FK → bigint (42 columns)
ALTER TABLE agenda            ALTER COLUMN id              TYPE bigint;
ALTER TABLE agenda            ALTER COLUMN meeting_id      TYPE bigint;
ALTER TABLE agenda            ALTER COLUMN session_id      TYPE bigint;
ALTER TABLE agenda            ALTER COLUMN assignee_id     TYPE bigint;
ALTER TABLE agent_logs        ALTER COLUMN id              TYPE bigint;
ALTER TABLE agent_logs        ALTER COLUMN meeting_id      TYPE bigint;
ALTER TABLE agent_logs        ALTER COLUMN session_id      TYPE bigint;
ALTER TABLE agent_logs        ALTER COLUMN user_id         TYPE bigint;
ALTER TABLE chat_messages     ALTER COLUMN id              TYPE bigint;
ALTER TABLE chat_messages     ALTER COLUMN user_id         TYPE bigint;
ALTER TABLE chat_messages     ALTER COLUMN meeting_id      TYPE bigint;
ALTER TABLE chat_messages     ALTER COLUMN session_id      TYPE bigint;
ALTER TABLE hitl_reviews      ALTER COLUMN id              TYPE bigint;
ALTER TABLE hitl_reviews      ALTER COLUMN agent_log_id    TYPE bigint;
ALTER TABLE hitl_reviews      ALTER COLUMN reviewer_id     TYPE bigint;
ALTER TABLE hitl_reviews      ALTER COLUMN agenda_id       TYPE bigint;
ALTER TABLE hitl_reviews      ALTER COLUMN report_id       TYPE bigint;
ALTER TABLE meeting_members   ALTER COLUMN id              TYPE bigint;
ALTER TABLE meeting_members   ALTER COLUMN meeting_id      TYPE bigint;
ALTER TABLE meeting_members   ALTER COLUMN user_id         TYPE bigint;
ALTER TABLE meeting_sessions  ALTER COLUMN id              TYPE bigint;
ALTER TABLE meeting_sessions  ALTER COLUMN meeting_id      TYPE bigint;
ALTER TABLE meetings          ALTER COLUMN id              TYPE bigint;
ALTER TABLE meetings          ALTER COLUMN created_by      TYPE bigint;
ALTER TABLE minutes           ALTER COLUMN id              TYPE bigint;
ALTER TABLE minutes           ALTER COLUMN session_id      TYPE bigint;
ALTER TABLE minutes           ALTER COLUMN recorder_id     TYPE bigint;
ALTER TABLE report_scores     ALTER COLUMN id              TYPE bigint;
ALTER TABLE report_scores     ALTER COLUMN report_id       TYPE bigint;
ALTER TABLE reports           ALTER COLUMN id              TYPE bigint;
ALTER TABLE reports           ALTER COLUMN meeting_id      TYPE bigint;
ALTER TABLE reports           ALTER COLUMN parent_id       TYPE bigint;
ALTER TABLE reports           ALTER COLUMN upload_id       TYPE bigint;
ALTER TABLE session_members   ALTER COLUMN id              TYPE bigint;
ALTER TABLE session_members   ALTER COLUMN session_id      TYPE bigint;
ALTER TABLE session_members   ALTER COLUMN user_id         TYPE bigint;
ALTER TABLE stt_segments      ALTER COLUMN id              TYPE bigint;
ALTER TABLE stt_segments      ALTER COLUMN session_id      TYPE bigint;
ALTER TABLE stt_segments      ALTER COLUMN speaker_user_id TYPE bigint;
ALTER TABLE token_usage_logs  ALTER COLUMN id              TYPE bigint;
ALTER TABLE token_usage_logs  ALTER COLUMN agent_log_id    TYPE bigint;
ALTER TABLE users             ALTER COLUMN id              TYPE bigint;

-- 2) Flyway 이력 리셋 — V2~V11은 V1 baseline으로 통합·삭제됨.
--    이력 테이블을 비우면 새 코드 배포 시 baseline-on-migrate(baseline-version=1)가
--    "비어있지 않은 스키마 + 이력 없음"을 감지해 V1으로 baseline 처리한다(V1 SQL은 재실행하지 않음).
DROP TABLE IF EXISTS flyway_schema_history;

COMMIT;

-- 3) 검증: 아래 쿼리가 0행이어야 한다(남은 integer id/FK 없음)
-- SELECT table_name, column_name
--   FROM information_schema.columns
--  WHERE table_schema = 'public' AND data_type = 'integer'
--    AND (column_name = 'id' OR column_name LIKE '%\_id' ESCAPE '\');
