-- P1-7②: users.company 문자열 컬럼 폐기 (정규화 완료 — companies + users.company_id)
-- 안전장치: DROP 전에 미백필 사용자(company 문자열은 있으나 company_id NULL)를 마지막으로 백필.
INSERT INTO companies (name)
  SELECT DISTINCT trim(company) FROM users
  WHERE company IS NOT NULL AND trim(company) <> '' AND company_id IS NULL
  ON CONFLICT (name) DO NOTHING;

UPDATE users u SET company_id = c.id FROM companies c
  WHERE u.company_id IS NULL AND trim(coalesce(u.company, '')) = c.name;

-- 문자열 컬럼 제거 — 이제 진실은 companies(name) + users.company_id
ALTER TABLE users DROP COLUMN IF EXISTS company;
