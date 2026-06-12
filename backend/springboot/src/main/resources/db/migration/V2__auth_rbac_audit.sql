-- Phase 1 인증/인가 통합에 필요한 스키마 (전부 additive — 기존 데이터 무영향)
-- V1은 기존 운영 스키마 baseline (flyway baseline-on-migrate)

-- P1-2: refresh token 서버 저장/회전/폐기
CREATE TABLE IF NOT EXISTS refresh_tokens (
    id          BIGSERIAL PRIMARY KEY,
    user_id     BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash  VARCHAR(64) NOT NULL UNIQUE,   -- SHA-256 hex (원문 토큰은 저장하지 않음)
    expires_at  TIMESTAMP NOT NULL,
    created_at  TIMESTAMP NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_refresh_tokens_user ON refresh_tokens(user_id);

-- P1-3: RBAC — 시스템 수준 역할 (회의체 수준 권한은 meeting_members.role 사용)
ALTER TABLE users ADD COLUMN IF NOT EXISTS role VARCHAR(30) NOT NULL DEFAULT 'USER';

-- P1-6: 감사 로그 (Plan.md §4.2 초안 기준)
CREATE TABLE IF NOT EXISTS audit_logs (
    id          BIGSERIAL PRIMARY KEY,
    actor_id    BIGINT REFERENCES users(id),
    action      VARCHAR(40)  NOT NULL,          -- CREATE/UPDATE/DELETE/APPROVE/LOGIN/...
    entity_type VARCHAR(40)  NOT NULL,          -- meeting/report/agenda/minutes/member/...
    entity_id   BIGINT,
    meeting_id  BIGINT,
    detail      JSONB,
    ip_addr     VARCHAR(45),
    created_at  TIMESTAMP NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_audit_logs_actor  ON audit_logs(actor_id, created_at);
CREATE INDEX IF NOT EXISTS idx_audit_logs_entity ON audit_logs(entity_type, entity_id);
