-- P2-2: FK/조회 패턴 기반 인덱스 + 정합성 제약 (Plan.md §4.1)
-- 2026-06-12 운영 스키마 대조 완료: 대상 컬럼 전부 존재, 유니크 위반 데이터 0건 확인.
-- agenda.status CHECK는 보류 — Spring enum(ON_HOLD/CONFIRMED/DONE)과 실데이터(draft/ongoing/done)
-- 불일치가 먼저 정리되어야 함 (HC-11 상태값 표준화에서 처리).

CREATE INDEX IF NOT EXISTS idx_meeting_members_meeting   ON meeting_members(meeting_id);
CREATE INDEX IF NOT EXISTS idx_meeting_members_user      ON meeting_members(user_id);
CREATE INDEX IF NOT EXISTS idx_meeting_sessions_meeting  ON meeting_sessions(meeting_id, status);
CREATE INDEX IF NOT EXISTS idx_agenda_meeting_status     ON agenda(meeting_id, status);
CREATE INDEX IF NOT EXISTS idx_agenda_session            ON agenda(session_id);
CREATE INDEX IF NOT EXISTS idx_reports_meeting           ON reports(meeting_id);
CREATE INDEX IF NOT EXISTS idx_reports_parent            ON reports(parent_id);
CREATE INDEX IF NOT EXISTS idx_report_scores_report      ON report_scores(report_id);
CREATE INDEX IF NOT EXISTS idx_stt_segments_session      ON stt_segments(session_id, start_sec);
CREATE INDEX IF NOT EXISTS idx_minutes_session           ON minutes(session_id);
CREATE INDEX IF NOT EXISTS idx_chat_messages_thread      ON chat_messages(thread_id, created_at);
CREATE INDEX IF NOT EXISTS idx_agent_logs_meeting        ON agent_logs(meeting_id, created_at);
CREATE INDEX IF NOT EXISTS idx_agent_logs_context        ON agent_logs(context_type, created_at);
CREATE INDEX IF NOT EXISTS idx_token_usage_agent_log     ON token_usage_logs(agent_log_id);
CREATE INDEX IF NOT EXISTS idx_session_members_session   ON session_members(session_id);
CREATE INDEX IF NOT EXISTS idx_hitl_reviews_report       ON hitl_reviews(report_id);
CREATE INDEX IF NOT EXISTS idx_hitl_reviews_agenda       ON hitl_reviews(agenda_id);

-- 멤버십 중복 방지 (2026-06-12 기준 위반 데이터 0건 확인)
ALTER TABLE session_members ADD CONSTRAINT uq_session_members UNIQUE (session_id, user_id);
ALTER TABLE meeting_members ADD CONSTRAINT uq_meeting_members UNIQUE (meeting_id, user_id);

-- 보고서 검토 상태 표준화 (실사용 값: pending/approved/rejected — 코드 전수 확인)
ALTER TABLE reports ADD CONSTRAINT ck_reports_human_status
    CHECK (human_status IN ('pending', 'approved', 'rejected'));
