// =============================================================
// seed.cypher  —  Sample Data
// Knowledge Graph (정적) + Context Graph (동적)
// =============================================================


// ── 1. Knowledge Graph ───────────────────────────────────────

// Organization
CREATE (:Organization {id: 'org-001', name: 'Workmaite Inc.', type: 'company'});

// Departments
CREATE (:Department {id: 'dept-001', name: '제품팀',     org_id: 'org-001'});
CREATE (:Department {id: 'dept-002', name: '개발팀',     org_id: 'org-001'});
CREATE (:Department {id: 'dept-003', name: '디자인팀',   org_id: 'org-001'});

// Roles
CREATE (:Role {id: 'role-001', name: 'PM',       level: 'senior'});
CREATE (:Role {id: 'role-002', name: 'Engineer', level: 'mid'});
CREATE (:Role {id: 'role-003', name: 'Designer', level: 'mid'});
CREATE (:Role {id: 'role-004', name: 'CTO',      level: 'executive'});

// Persons
CREATE (:Person {id: 'p-001', name: '안민혁', email: 'als7928@daum.net',  title: 'Product Manager'});
CREATE (:Person {id: 'p-002', name: '안상연', email: 'seoyeon@workmaite.io', title: 'Frontend Engineer'});
CREATE (:Person {id: 'p-003', name: '김세림', email: 'dohyun@workmaite.io',  title: 'Backend Engineer'});
CREATE (:Person {id: 'p-004', name: '이다예', email: 'yujin@workmaite.io',   title: 'UX Designer'});
CREATE (:Person {id: 'p-005', name: '윤세준', email: 'haeun@workmaite.io',   title: 'CTO'});
CREATE (:Person {id: 'p-006', name: '이한결', email: 'han@workmaite.io',   title: 'CTO'});

// MeetingGroups
CREATE (:MeetingGroup {id: 'mg-001', title: '주간 제품 스프린트',   type: 'recurring'});
CREATE (:MeetingGroup {id: 'mg-002', title: '기술 아키텍처 리뷰',   type: 'recurring'});
CREATE (:MeetingGroup {id: 'mg-003', title: '전사 전략 회의',       type: 'quarterly'});

// Documents
CREATE (:Document {id: 'doc-001', title: 'Q2 제품 로드맵',         file_type: 'pdf',  created_at: '2026-04-01'});
CREATE (:Document {id: 'doc-002', title: 'Neo4j 아키텍처 설계서',   file_type: 'pdf',  created_at: '2026-04-15'});
CREATE (:Document {id: 'doc-003', title: '스프린트 14 회의록',      file_type: 'md',   created_at: '2026-05-10'});

// Agendas
CREATE (:Agenda {id: 'ag-001', title: 'GraphRAG 파이프라인 PoC',   description: 'Neo4j 기반 GraphRAG 프로토타입 구현',    status: 'in-progress'});
CREATE (:Agenda {id: 'ag-002', title: 'UI 컴포넌트 리팩토링',       description: '디자인 시스템 v2 적용',                  status: 'todo'});
CREATE (:Agenda {id: 'ag-003', title: 'API 인증 방식 전환',         description: 'JWT → OAuth2.0 마이그레이션',            status: 'done'});


// ── 2. Knowledge Graph 관계 ───────────────────────────────────

// Person → Department
MATCH (p:Person {id: 'p-001'}), (d:Department {id: 'dept-001'}) CREATE (p)-[:BELONGS_TO]->(d);
MATCH (p:Person {id: 'p-002'}), (d:Department {id: 'dept-002'}) CREATE (p)-[:BELONGS_TO]->(d);
MATCH (p:Person {id: 'p-003'}), (d:Department {id: 'dept-002'}) CREATE (p)-[:BELONGS_TO]->(d);
MATCH (p:Person {id: 'p-004'}), (d:Department {id: 'dept-003'}) CREATE (p)-[:BELONGS_TO]->(d);
MATCH (p:Person {id: 'p-005'}), (d:Department {id: 'dept-002'}) CREATE (p)-[:BELONGS_TO]->(d);

// Person → Role
MATCH (p:Person {id: 'p-001'}), (r:Role {id: 'role-001'}) CREATE (p)-[:HAS_ROLE]->(r);
MATCH (p:Person {id: 'p-002'}), (r:Role {id: 'role-002'}) CREATE (p)-[:HAS_ROLE]->(r);
MATCH (p:Person {id: 'p-003'}), (r:Role {id: 'role-002'}) CREATE (p)-[:HAS_ROLE]->(r);
MATCH (p:Person {id: 'p-004'}), (r:Role {id: 'role-003'}) CREATE (p)-[:HAS_ROLE]->(r);
MATCH (p:Person {id: 'p-005'}), (r:Role {id: 'role-004'}) CREATE (p)-[:HAS_ROLE]->(r);

// Department → Organization
MATCH (d:Department), (o:Organization {id: 'org-001'}) CREATE (d)-[:PART_OF]->(o);

// Department → MeetingGroup
MATCH (d:Department {id: 'dept-001'}), (mg:MeetingGroup {id: 'mg-001'}) CREATE (d)-[:PARTICIPATES_IN]->(mg);
MATCH (d:Department {id: 'dept-002'}), (mg:MeetingGroup {id: 'mg-001'}) CREATE (d)-[:PARTICIPATES_IN]->(mg);
MATCH (d:Department {id: 'dept-002'}), (mg:MeetingGroup {id: 'mg-002'}) CREATE (d)-[:PARTICIPATES_IN]->(mg);
MATCH (d:Department {id: 'dept-001'}), (mg:MeetingGroup {id: 'mg-003'}) CREATE (d)-[:PARTICIPATES_IN]->(mg);
MATCH (d:Department {id: 'dept-002'}), (mg:MeetingGroup {id: 'mg-003'}) CREATE (d)-[:PARTICIPATES_IN]->(mg);
MATCH (d:Department {id: 'dept-003'}), (mg:MeetingGroup {id: 'mg-003'}) CREATE (d)-[:PARTICIPATES_IN]->(mg);

// Person → MeetingGroup
MATCH (p:Person {id: 'p-001'}), (mg:MeetingGroup {id: 'mg-001'}) CREATE (p)-[:ADMIN_OF]->(mg);
MATCH (p:Person {id: 'p-002'}), (mg:MeetingGroup {id: 'mg-001'}) CREATE (p)-[:MEMBER_OF]->(mg);
MATCH (p:Person {id: 'p-003'}), (mg:MeetingGroup {id: 'mg-001'}) CREATE (p)-[:MEMBER_OF]->(mg);
MATCH (p:Person {id: 'p-005'}), (mg:MeetingGroup {id: 'mg-002'}) CREATE (p)-[:ADMIN_OF]->(mg);
MATCH (p:Person {id: 'p-003'}), (mg:MeetingGroup {id: 'mg-002'}) CREATE (p)-[:MEMBER_OF]->(mg);
MATCH (p:Person {id: 'p-005'}), (mg:MeetingGroup {id: 'mg-003'}) CREATE (p)-[:ADMIN_OF]->(mg);

// Document → MeetingGroup
MATCH (doc:Document {id: 'doc-001'}), (mg:MeetingGroup {id: 'mg-001'}) CREATE (doc)-[:ATTACHED_TO]->(mg);
MATCH (doc:Document {id: 'doc-002'}), (mg:MeetingGroup {id: 'mg-002'}) CREATE (doc)-[:ATTACHED_TO]->(mg);
MATCH (doc:Document {id: 'doc-003'}), (mg:MeetingGroup {id: 'mg-001'}) CREATE (doc)-[:ATTACHED_TO]->(mg);

// Agenda → Person, MeetingGroup
MATCH (a:Agenda {id: 'ag-001'}), (p:Person {id: 'p-003'})         CREATE (a)-[:ASSIGNED_TO]->(p);
MATCH (a:Agenda {id: 'ag-001'}), (mg:MeetingGroup {id: 'mg-002'}) CREATE (a)-[:OWNED_BY]->(mg);
MATCH (a:Agenda {id: 'ag-002'}), (p:Person {id: 'p-004'})         CREATE (a)-[:ASSIGNED_TO]->(p);
MATCH (a:Agenda {id: 'ag-002'}), (mg:MeetingGroup {id: 'mg-001'}) CREATE (a)-[:OWNED_BY]->(mg);
MATCH (a:Agenda {id: 'ag-003'}), (p:Person {id: 'p-002'})         CREATE (a)-[:ASSIGNED_TO]->(p);
MATCH (a:Agenda {id: 'ag-003'}), (mg:MeetingGroup {id: 'mg-001'}) CREATE (a)-[:OWNED_BY]->(mg);


// ── 3. Context Graph ─────────────────────────────────────────

// Sessions
CREATE (:Session {id: 's-001', title: '스프린트 14 킥오프',     date: '2026-05-06', status: 'closed'});
CREATE (:Session {id: 's-002', title: '아키텍처 리뷰 #7',       date: '2026-05-13', status: 'closed'});
CREATE (:Session {id: 's-003', title: '스프린트 15 킥오프',     date: '2026-05-20', status: 'open'});

// Decisions
CREATE (:Decision {id: 'd-001', content: 'GraphRAG PoC를 스프린트 14 내 완료', made_at: '2026-05-06', rationale: 'Q2 로드맵 목표 달성을 위한 빠른 검증 필요', confidence: 0.85});
CREATE (:Decision {id: 'd-002', content: 'Neo4j Community Edition 채택',       made_at: '2026-05-13', rationale: '비용 최소화 및 오픈소스 활용',                confidence: 0.90});
CREATE (:Decision {id: 'd-003', content: 'UI 리팩토링을 스프린트 15로 이관',   made_at: '2026-05-20', rationale: '개발 리소스 우선순위 조정',                  confidence: 0.75});

// AIJudgments
CREATE (:AIJudgment {id: 'aj-001', model: 'gpt-4o',      prompt_hash: 'abc123', result: 'approved', reasoning: 'GraphRAG PoC 완료 가능성 높음, 리소스 충분',    created_at: '2026-05-06T11:00:00'});
CREATE (:AIJudgment {id: 'aj-002', model: 'gpt-4o-mini', prompt_hash: 'def456', result: 'suggested', reasoning: 'UI 리팩토링 병행은 리소스 과부하 위험',        created_at: '2026-05-20T09:30:00'});


// ── 4. Context Graph 관계 ─────────────────────────────────────

// Session → Decision
MATCH (s:Session {id: 's-001'}), (d:Decision {id: 'd-001'}) CREATE (s)-[:PRODUCED]->(d);
MATCH (s:Session {id: 's-002'}), (d:Decision {id: 'd-002'}) CREATE (s)-[:PRODUCED]->(d);
MATCH (s:Session {id: 's-003'}), (d:Decision {id: 'd-003'}) CREATE (s)-[:PRODUCED]->(d);

// Decision → Evidence (근거)
MATCH (d:Decision {id: 'd-001'}), (ev:Evidence {id: 'ev-001'}) CREATE (d)-[:BASED_ON]->(ev);
MATCH (d:Decision {id: 'd-002'}), (ev:Evidence {id: 'ev-002'}) CREATE (d)-[:BASED_ON]->(ev);
MATCH (d:Decision {id: 'd-002'}), (doc:Document {id: 'doc-002'}) CREATE (d)-[:BASED_ON]->(doc);
MATCH (d:Decision {id: 'd-003'}), (ev:Evidence {id: 'ev-003'}) CREATE (d)-[:BASED_ON]->(ev);

// AIJudgment → Agenda (추천)
MATCH (aj:AIJudgment {id: 'aj-001'}), (a:Agenda {id: 'ag-001'}) CREATE (aj)-[:RECOMMENDED]->(a);
MATCH (aj:AIJudgment {id: 'aj-002'}), (a:Agenda {id: 'ag-002'}) CREATE (aj)-[:RECOMMENDED]->(a);

// AIJudgment → Evidence
MATCH (aj:AIJudgment {id: 'aj-001'}), (ev:Evidence {id: 'ev-001'}) CREATE (aj)-[:BASED_ON]->(ev);
MATCH (aj:AIJudgment {id: 'aj-002'}), (ev:Evidence {id: 'ev-003'}) CREATE (aj)-[:BASED_ON]->(ev);

// AIJudgment → Person (승인/반려)
MATCH (aj:AIJudgment {id: 'aj-001'}), (p:Person {id: 'p-001'}) CREATE (aj)-[:APPROVED_BY]->(p);
MATCH (aj:AIJudgment {id: 'aj-002'}), (p:Person {id: 'p-005'}) CREATE (aj)-[:APPROVED_BY]->(p);

// Agenda → Decision (인과)
MATCH (a:Agenda {id: 'ag-001'}), (d:Decision {id: 'd-001'}) CREATE (a)-[:CAUSED_BY]->(d);
MATCH (a:Agenda {id: 'ag-002'}), (d:Decision {id: 'd-003'}) CREATE (a)-[:CAUSED_BY]->(d);

// Agenda → Agenda (연속성)
MATCH (a1:Agenda {id: 'ag-003'}), (a2:Agenda {id: 'ag-001'}) CREATE (a1)-[:FOLLOWED_BY]->(a2);

// Session → Session (지난 회의 Recap)
MATCH (s1:Session {id: 's-003'}), (s2:Session {id: 's-001'}) CREATE (s1)-[:REFERENCES]->(s2);


// ── 5. 정적 ↔ 동적 브릿지 관계 ──────────────────────────────

// Session → MeetingGroup
MATCH (s:Session {id: 's-001'}), (mg:MeetingGroup {id: 'mg-001'}) CREATE (s)-[:HELD_BY]->(mg);
MATCH (s:Session {id: 's-002'}), (mg:MeetingGroup {id: 'mg-002'}) CREATE (s)-[:HELD_BY]->(mg);
MATCH (s:Session {id: 's-003'}), (mg:MeetingGroup {id: 'mg-001'}) CREATE (s)-[:HELD_BY]->(mg);

// Decision → Person (의사결정자)
MATCH (d:Decision {id: 'd-001'}), (p:Person {id: 'p-001'}) CREATE (d)-[:MADE_BY]->(p);
MATCH (d:Decision {id: 'd-002'}), (p:Person {id: 'p-005'}) CREATE (d)-[:MADE_BY]->(p);
MATCH (d:Decision {id: 'd-003'}), (p:Person {id: 'p-001'}) CREATE (d)-[:MADE_BY]->(p);

// Session → Agenda (세션에서 다루는 아젠다)
MATCH (s:Session {id: 's-001'}), (a:Agenda {id: 'ag-001'}) CREATE (s)-[:COVERS]->(a);
MATCH (s:Session {id: 's-001'}), (a:Agenda {id: 'ag-003'}) CREATE (s)-[:COVERS]->(a);
MATCH (s:Session {id: 's-002'}), (a:Agenda {id: 'ag-001'}) CREATE (s)-[:COVERS]->(a);
MATCH (s:Session {id: 's-003'}), (a:Agenda {id: 'ag-002'}) CREATE (s)-[:COVERS]->(a);
MATCH (s:Session {id: 's-003'}), (a:Agenda {id: 'ag-001'}) CREATE (s)-[:COVERS]->(a);

// Agenda → Person (담당자, 브릿지)
MATCH (a:Agenda {id: 'ag-001'}), (p:Person {id: 'p-003'}) MERGE (a)-[:ASSIGNED_TO]->(p);
MATCH (a:Agenda {id: 'ag-002'}), (p:Person {id: 'p-004'}) MERGE (a)-[:ASSIGNED_TO]->(p);
