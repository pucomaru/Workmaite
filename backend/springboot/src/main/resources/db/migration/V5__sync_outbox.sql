-- P2-4: Neo4j 동기화 아웃박스 (DATA-1/2 — fire-and-forget 유실 해결)
-- Spring이 비즈니스 트랜잭션 안에서 행을 기록하고, 커밋 후 디스패처가 FastAPI를 호출한다.
-- 실패 행은 유지되어 폴러가 재시도한다.
CREATE TABLE IF NOT EXISTS neo4j_sync_outbox (
    id           BIGSERIAL PRIMARY KEY,
    entity_type  VARCHAR(30) NOT NULL,          -- meeting/session/agenda/user/member
    entity_id    BIGINT      NOT NULL,
    op           VARCHAR(10) NOT NULL,          -- upsert/delete
    payload      JSONB,                         -- member: {"user_id":N,"role":"admin"}
    status       VARCHAR(15) NOT NULL DEFAULT 'pending',  -- pending/done/failed
    retry_count  INT         NOT NULL DEFAULT 0,
    last_error   TEXT,
    created_at   TIMESTAMP NOT NULL DEFAULT now(),
    processed_at TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_sync_outbox_pending
    ON neo4j_sync_outbox(status, created_at) WHERE status <> 'done';
