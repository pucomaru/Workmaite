-- P3C-3: 응답 피드백 (H-9) — 👍/👎+사유 수집, P6 eval 데이터셋 환류용
CREATE TABLE IF NOT EXISTS chat_feedback (
    id           BIGSERIAL PRIMARY KEY,
    user_id      BIGINT NOT NULL REFERENCES users(id),
    thread_id    VARCHAR(100) NOT NULL,
    message_id   BIGINT REFERENCES chat_messages(id),
    agent_log_id BIGINT REFERENCES agent_logs(id),
    rating       SMALLINT NOT NULL,               -- 1=up / -1=down
    reason       TEXT,
    content_snippet TEXT,                          -- 평가 대상 응답 앞부분 (메시지 미저장 응답 대비)
    created_at   TIMESTAMP NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_chat_feedback_thread ON chat_feedback(thread_id, created_at);
