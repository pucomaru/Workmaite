-- P1-3 RBAC 부트스트랩: 기존에 부서 문자열('전략기획팀')로 관리자 권한을 받던 사용자에게
-- 명시적 role을 1회 부여한다. 이후 신규 가입자는 부서명과 무관하게 USER이며,
-- 관리자 부여는 DB(또는 추후 관리 UI)에서만 가능 — 자가신고 권한 상승(SEC-10) 차단.
UPDATE users
SET role = 'SYSTEM_ADMIN'
WHERE trim(coalesce(department, '')) = '전략기획팀'
  AND role = 'USER';
