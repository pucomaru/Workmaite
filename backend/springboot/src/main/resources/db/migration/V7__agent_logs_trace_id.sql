-- P3A-3: agent_logs ↔ 트레이스 연결 — "느린 요청 → 트레이스" 점프용
ALTER TABLE agent_logs ADD COLUMN IF NOT EXISTS trace_id VARCHAR(64);
