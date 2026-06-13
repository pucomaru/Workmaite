-- ============================================================================
-- 운영 DB 일회성 정비: 모든 id/FK를 bigint로 표준화
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

COMMIT;
