-- P1-7②: 멀티테넌시 — 회사 정규화(MT-4) + 초대 기반 온보딩(MT-2)

-- 회사 정규화: 자유 텍스트 → 엔티티
CREATE TABLE IF NOT EXISTS companies (
    id         BIGSERIAL PRIMARY KEY,
    name       VARCHAR(100) NOT NULL UNIQUE,
    created_at TIMESTAMP NOT NULL DEFAULT now()
);
INSERT INTO companies (name)
  SELECT DISTINCT trim(company) FROM users
  WHERE company IS NOT NULL AND trim(company) <> ''
  ON CONFLICT (name) DO NOTHING;
ALTER TABLE users ADD COLUMN IF NOT EXISTS company_id BIGINT REFERENCES companies(id);
UPDATE users u SET company_id = c.id FROM companies c
  WHERE u.company_id IS NULL AND trim(coalesce(u.company, '')) = c.name;
-- users.company(varchar)는 전 코드 경로 전환 후 별도 마이그레이션에서 DROP

-- 초대 기반 온보딩 (MT-2/UX-25): 관리자가 비밀번호를 만드는 구조 폐기
CREATE TABLE IF NOT EXISTS invitations (
    id          BIGSERIAL PRIMARY KEY,
    email       VARCHAR(255) NOT NULL,
    company_id  BIGINT REFERENCES companies(id),
    invited_by  BIGINT NOT NULL REFERENCES users(id),
    token_hash  VARCHAR(64) NOT NULL UNIQUE,    -- 초대 토큰의 SHA-256 (평문 저장 금지)
    role        VARCHAR(20) NOT NULL DEFAULT 'USER',
    expires_at  TIMESTAMP NOT NULL,
    accepted_at TIMESTAMP,
    created_at  TIMESTAMP NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_invitations_email ON invitations(email);

-- 임시 비밀번호 과도기: 최초 로그인 시 변경 강제 / 계정 비활성화(삭제 대신)
ALTER TABLE users ADD COLUMN IF NOT EXISTS must_change_password BOOLEAN NOT NULL DEFAULT false;
ALTER TABLE users ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT true;
