// ============================================================
// Workmaite Neo4j Seed Data
// 그래프 구조: Knowledge Graph (정적 조직) + Context Graph (동적 회의/결정)
// Document 귀속: Department -[:SUBMITTED]-> Document 명시
// ============================================================

// ── 기존 데이터 초기화 ────────────────────────────────────────
MATCH (n) DETACH DELETE n;


// ============================================================
// [KNOWLEDGE GRAPH] 정적 조직 데이터
// ============================================================

// ── Organization ─────────────────────────────────────────────
CREATE (org:Organization {
  id: 'org-1',
  name: '주식회사 워크메이트',
  industry: '경영컨설팅',
  created_at: datetime('2023-01-01T00:00:00')
});

// ── Department ───────────────────────────────────────────────
CREATE (d1:Department { id: 'dept-1', name: '전략기획팀', code: 'STR' });
CREATE (d2:Department { id: 'dept-2', name: '사업개발팀', code: 'BIZ' });
CREATE (d3:Department { id: 'dept-3', name: '운영지원팀', code: 'OPS' });

// ── Person ────────────────────────────────────────────────────
CREATE (p1:Person { id: 'person-1', name: '김전략', email: 'strategy@workmaite.com', position: '팀장' });
CREATE (p2:Person { id: 'person-2', name: '이기획', email: 'planning@workmaite.com', position: '과장' });
CREATE (p3:Person { id: 'person-3', name: '박사업', email: 'biz@workmaite.com',      position: '팀장' });
CREATE (p4:Person { id: 'person-4', name: '최운영', email: 'ops@workmaite.com',       position: '팀장' });
CREATE (p5:Person { id: 'person-5', name: '정지원', email: 'support@workmaite.com',   position: '대리' });

// ── MeetingGroup ─────────────────────────────────────────────
CREATE (mg1:MeetingGroup {
  id: 'mg-1', title: '전략위원회',
  purpose: 'Q별 전략 목표 점검 및 의사결정',
  meeting_type: 'Monthly', status: 'active'
});
CREATE (mg2:MeetingGroup {
  id: 'mg-2', title: '사업개발위원회',
  purpose: '신규 사업 기회 발굴 및 파트너십 검토',
  meeting_type: 'Biweekly', status: 'active'
});
CREATE (mg3:MeetingGroup {
  id: 'mg-3', title: '운영효율화위원회',
  purpose: '내부 운영 프로세스 개선 및 자동화',
  meeting_type: 'Weekly', status: 'active'
});

// ── Agenda ───────────────────────────────────────────────────
CREATE (ag1:Agenda {
  id: 'agenda-1', title: 'Q2 전략 목표 점검',
  description: 'Q1 실적 대비 Q2 목표 달성 현황 점검 및 방향 재정비',
  priority: 'urgent_important', status: 'in_progress', due_date: date('2026-06-30')
});
CREATE (ag2:Agenda {
  id: 'agenda-2', title: '신규 파트너십 MOU 체결 검토',
  description: '해외 컨설팅사 3곳과의 파트너십 조건 검토 및 우선순위 결정',
  priority: 'important', status: 'pending', due_date: date('2026-07-15')
});
CREATE (ag3:Agenda {
  id: 'agenda-3', title: '운영 프로세스 자동화 도입',
  description: 'RPA 도입을 통한 반복 업무 자동화 범위 및 일정 확정',
  priority: 'urgent_important', status: 'in_progress', due_date: date('2026-06-20')
});

// ── Document (Knowledge Graph용 — 보고자료/발제자료) ──────────
CREATE (doc1:Document {
  id: 'doc-1', title: 'Q2 전략 보고서',
  file_name: 'Q2_전략보고서_v2.pdf',
  doc_type: '보고자료', version: 2,
  uploaded_at: datetime('2026-05-10T09:00:00')
});
CREATE (doc2:Document {
  id: 'doc-2', title: '파트너십 후보사 비교 발제자료',
  file_name: '파트너십_발제자료_최종.pptx',
  doc_type: '발제자료', version: 1,
  uploaded_at: datetime('2026-05-18T14:30:00')
});
CREATE (doc3:Document {
  id: 'doc-3', title: 'RPA 도입 타당성 검토 보고서',
  file_name: 'RPA_타당성검토.pdf',
  doc_type: '보고자료', version: 1,
  uploaded_at: datetime('2026-05-20T10:00:00')
});


// ============================================================
// [CONTEXT GRAPH] 동적 회의/결정 데이터
// ============================================================

// ── Session ──────────────────────────────────────────────────
CREATE (s1:Session {
  id: 'session-1', title: '전략위원회 4차 회의',
  session_number: 4,
  scheduled_at: datetime('2026-05-22T14:00:00'),
  ended_at:     datetime('2026-05-22T16:00:00'),
  status: 'ended'
});
CREATE (s2:Session {
  id: 'session-2', title: '사업개발위원회 7차 회의',
  session_number: 7,
  scheduled_at: datetime('2026-05-20T10:00:00'),
  ended_at:     datetime('2026-05-20T11:30:00'),
  status: 'ended'
});
CREATE (s3:Session {
  id: 'session-3', title: '운영효율화위원회 12차 회의',
  session_number: 12,
  scheduled_at: datetime('2026-05-21T09:00:00'),
  ended_at:     datetime('2026-05-21T10:00:00'),
  status: 'ended'
});

// ── Decision ─────────────────────────────────────────────────
CREATE (dec1:Decision {
  id: 'decision-1',
  content: 'Q2 매출 목표 15% 상향 조정 및 핵심 KPI 재설정',
  decided_at: datetime('2026-05-22T15:30:00'),
  status: 'confirmed'
});
CREATE (dec2:Decision {
  id: 'decision-2',
  content: 'A사와 우선 파트너십 협상 진행, 9월 MOU 체결 목표',
  decided_at: datetime('2026-05-20T11:00:00'),
  status: 'confirmed'
});
CREATE (dec3:Decision {
  id: 'decision-3',
  content: 'RPA 1단계 범위 확정: 정산 업무 자동화, 7월 파일럿 시작',
  decided_at: datetime('2026-05-21T09:50:00'),
  status: 'confirmed'
});

// ── Evidence ─────────────────────────────────────────────────
CREATE (ev1:Evidence {
  id: 'evidence-1',
  content: 'Q1 실적: 매출 목표 대비 108% 달성, 영업이익률 12.3%',
  source: 'Q1 경영실적 보고서'
});
CREATE (ev2:Evidence {
  id: 'evidence-2',
  content: 'A사 레퍼런스 체크 결과 동종업계 3개사 협업 경험 확인',
  source: '외부 시장조사 보고서'
});
CREATE (ev3:Evidence {
  id: 'evidence-3',
  content: '현업 인터뷰: 정산 업무 월평균 40시간 소요, 오류율 3.2%',
  source: '현업 부서 인터뷰 결과'
});

// ── AIJudgment ────────────────────────────────────────────────
CREATE (ai1:AIJudgment {
  id: 'ai-1',
  summary: 'Q1 실적 기반 Q2 상향 목표 달성 가능성 78% 예측',
  recommendation: 'Q2 목표 상향은 타당하나 채용 리소스 확보 병행 필요',
  confidence: 0.78,
  generated_at: datetime('2026-05-22T15:00:00')
});
CREATE (ai2:AIJudgment {
  id: 'ai-2',
  summary: '3개 파트너 후보사 정량 비교: A사 종합점수 1위',
  recommendation: 'A사 우선협상 적정, 계약조건 IP 귀속 조항 검토 필요',
  confidence: 0.85,
  generated_at: datetime('2026-05-20T09:30:00')
});

// ── 회의록 Document (Context Graph용 — session PRODUCED) ─────
CREATE (min1:Document {
  id: 'doc-min-1', title: '전략위원회 4차 회의록',
  file_name: '전략위원회_4차_회의록.pdf',
  doc_type: '회의록', version: 1,
  uploaded_at: datetime('2026-05-22T17:00:00')
});
CREATE (min2:Document {
  id: 'doc-min-2', title: '사업개발위원회 7차 회의록',
  file_name: '사업개발위원회_7차_회의록.pdf',
  doc_type: '회의록', version: 1,
  uploaded_at: datetime('2026-05-20T12:00:00')
});
CREATE (min3:Document {
  id: 'doc-min-3', title: '운영효율화위원회 12차 회의록',
  file_name: '운영효율화위원회_12차_회의록.pdf',
  doc_type: '회의록', version: 1,
  uploaded_at: datetime('2026-05-21T10:30:00')
});


// ============================================================
// [RELATIONSHIPS] 관계 설정
// ============================================================

// ── 조직 소속 ─────────────────────────────────────────────────
MATCH (org:Organization {id:'org-1'}),
      (d1:Department {id:'dept-1'}), (d2:Department {id:'dept-2'}), (d3:Department {id:'dept-3'})
CREATE (d1)-[:BELONGS_TO]->(org)
CREATE (d2)-[:BELONGS_TO]->(org)
CREATE (d3)-[:BELONGS_TO]->(org);

// ── Person → Department (BELONGS_TO) ──────────────────────────
MATCH (p1:Person {id:'person-1'}), (d1:Department {id:'dept-1'}) CREATE (p1)-[:BELONGS_TO]->(d1);
MATCH (p2:Person {id:'person-2'}), (d1:Department {id:'dept-1'}) CREATE (p2)-[:BELONGS_TO]->(d1);
MATCH (p3:Person {id:'person-3'}), (d2:Department {id:'dept-2'}) CREATE (p3)-[:BELONGS_TO]->(d2);
MATCH (p4:Person {id:'person-4'}), (d3:Department {id:'dept-3'}) CREATE (p4)-[:BELONGS_TO]->(d3);
MATCH (p5:Person {id:'person-5'}), (d3:Department {id:'dept-3'}) CREATE (p5)-[:BELONGS_TO]->(d3);

// ── Person → MeetingGroup (ADMIN_OF / MEMBER_OF) ──────────────
MATCH (p1:Person {id:'person-1'}), (mg1:MeetingGroup {id:'mg-1'}) CREATE (p1)-[:ADMIN_OF]->(mg1);
MATCH (p2:Person {id:'person-2'}), (mg1:MeetingGroup {id:'mg-1'}) CREATE (p2)-[:MEMBER_OF]->(mg1);
MATCH (p3:Person {id:'person-3'}), (mg1:MeetingGroup {id:'mg-1'}) CREATE (p3)-[:MEMBER_OF]->(mg1);
MATCH (p3:Person {id:'person-3'}), (mg2:MeetingGroup {id:'mg-2'}) CREATE (p3)-[:ADMIN_OF]->(mg2);
MATCH (p1:Person {id:'person-1'}), (mg2:MeetingGroup {id:'mg-2'}) CREATE (p1)-[:MEMBER_OF]->(mg2);
MATCH (p4:Person {id:'person-4'}), (mg3:MeetingGroup {id:'mg-3'}) CREATE (p4)-[:ADMIN_OF]->(mg3);
MATCH (p5:Person {id:'person-5'}), (mg3:MeetingGroup {id:'mg-3'}) CREATE (p5)-[:MEMBER_OF]->(mg3);
MATCH (p1:Person {id:'person-1'}), (mg3:MeetingGroup {id:'mg-3'}) CREATE (p1)-[:MEMBER_OF]->(mg3);

// ── Department → MeetingGroup (PARTICIPATES_IN) ───────────────
MATCH (d1:Department {id:'dept-1'}), (mg1:MeetingGroup {id:'mg-1'}) CREATE (d1)-[:PARTICIPATES_IN]->(mg1);
MATCH (d2:Department {id:'dept-2'}), (mg1:MeetingGroup {id:'mg-1'}) CREATE (d2)-[:PARTICIPATES_IN]->(mg1);
MATCH (d2:Department {id:'dept-2'}), (mg2:MeetingGroup {id:'mg-2'}) CREATE (d2)-[:PARTICIPATES_IN]->(mg2);
MATCH (d1:Department {id:'dept-1'}), (mg2:MeetingGroup {id:'mg-2'}) CREATE (d1)-[:PARTICIPATES_IN]->(mg2);
MATCH (d3:Department {id:'dept-3'}), (mg3:MeetingGroup {id:'mg-3'}) CREATE (d3)-[:PARTICIPATES_IN]->(mg3);
MATCH (d1:Department {id:'dept-1'}), (mg3:MeetingGroup {id:'mg-3'}) CREATE (d1)-[:PARTICIPATES_IN]->(mg3);

// ── Agenda → MeetingGroup (OWNED_BY) ──────────────────────────
MATCH (ag1:Agenda {id:'agenda-1'}), (mg1:MeetingGroup {id:'mg-1'}) CREATE (ag1)-[:OWNED_BY]->(mg1);
MATCH (ag2:Agenda {id:'agenda-2'}), (mg2:MeetingGroup {id:'mg-2'}) CREATE (ag2)-[:OWNED_BY]->(mg2);
MATCH (ag3:Agenda {id:'agenda-3'}), (mg3:MeetingGroup {id:'mg-3'}) CREATE (ag3)-[:OWNED_BY]->(mg3);

// ── Person → Agenda (ASSIGNED_TO) ─────────────────────────────
MATCH (p1:Person {id:'person-1'}), (ag1:Agenda {id:'agenda-1'}) CREATE (p1)-[:ASSIGNED_TO]->(ag1);
MATCH (p3:Person {id:'person-3'}), (ag2:Agenda {id:'agenda-2'}) CREATE (p3)-[:ASSIGNED_TO]->(ag2);
MATCH (p4:Person {id:'person-4'}), (ag3:Agenda {id:'agenda-3'}) CREATE (p4)-[:ASSIGNED_TO]->(ag3);

// ── Department → Document (SUBMITTED) — Document 귀속 명시 ────
MATCH (d1:Department {id:'dept-1'}), (doc1:Document {id:'doc-1'}) CREATE (d1)-[:SUBMITTED]->(doc1);
MATCH (d2:Department {id:'dept-2'}), (doc2:Document {id:'doc-2'}) CREATE (d2)-[:SUBMITTED]->(doc2);
MATCH (d3:Department {id:'dept-3'}), (doc3:Document {id:'doc-3'}) CREATE (d3)-[:SUBMITTED]->(doc3);

// ── Document → MeetingGroup (ATTACHED_TO) ─────────────────────
MATCH (doc1:Document {id:'doc-1'}), (mg1:MeetingGroup {id:'mg-1'}) CREATE (doc1)-[:ATTACHED_TO]->(mg1);
MATCH (doc2:Document {id:'doc-2'}), (mg2:MeetingGroup {id:'mg-2'}) CREATE (doc2)-[:ATTACHED_TO]->(mg2);
MATCH (doc3:Document {id:'doc-3'}), (mg3:MeetingGroup {id:'mg-3'}) CREATE (doc3)-[:ATTACHED_TO]->(mg3);

// ── Session → MeetingGroup (HELD_BY) ──────────────────────────
MATCH (s1:Session {id:'session-1'}), (mg1:MeetingGroup {id:'mg-1'}) CREATE (s1)-[:HELD_BY]->(mg1);
MATCH (s2:Session {id:'session-2'}), (mg2:MeetingGroup {id:'mg-2'}) CREATE (s2)-[:HELD_BY]->(mg2);
MATCH (s3:Session {id:'session-3'}), (mg3:MeetingGroup {id:'mg-3'}) CREATE (s3)-[:HELD_BY]->(mg3);

// ── Session → Agenda (COVERS) ─────────────────────────────────
MATCH (s1:Session {id:'session-1'}), (ag1:Agenda {id:'agenda-1'}) CREATE (s1)-[:COVERS]->(ag1);
MATCH (s2:Session {id:'session-2'}), (ag2:Agenda {id:'agenda-2'}) CREATE (s2)-[:COVERS]->(ag2);
MATCH (s3:Session {id:'session-3'}), (ag3:Agenda {id:'agenda-3'}) CREATE (s3)-[:COVERS]->(ag3);

// ── Session → Document (PRODUCED) — 회의록 생성 ───────────────
MATCH (s1:Session {id:'session-1'}), (min1:Document {id:'doc-min-1'}) CREATE (s1)-[:PRODUCED]->(min1);
MATCH (s2:Session {id:'session-2'}), (min2:Document {id:'doc-min-2'}) CREATE (s2)-[:PRODUCED]->(min2);
MATCH (s3:Session {id:'session-3'}), (min3:Document {id:'doc-min-3'}) CREATE (s3)-[:PRODUCED]->(min3);

// ── Decision → Session (BASED_ON) ────────────────────────────
MATCH (dec1:Decision {id:'decision-1'}), (s1:Session {id:'session-1'}) CREATE (dec1)-[:BASED_ON]->(s1);
MATCH (dec2:Decision {id:'decision-2'}), (s2:Session {id:'session-2'}) CREATE (dec2)-[:BASED_ON]->(s2);
MATCH (dec3:Decision {id:'decision-3'}), (s3:Session {id:'session-3'}) CREATE (dec3)-[:BASED_ON]->(s3);

// ── Decision → Agenda (CAUSED_BY) ────────────────────────────
MATCH (dec1:Decision {id:'decision-1'}), (ag1:Agenda {id:'agenda-1'}) CREATE (dec1)-[:CAUSED_BY]->(ag1);
MATCH (dec2:Decision {id:'decision-2'}), (ag2:Agenda {id:'agenda-2'}) CREATE (dec2)-[:CAUSED_BY]->(ag2);
MATCH (dec3:Decision {id:'decision-3'}), (ag3:Agenda {id:'agenda-3'}) CREATE (dec3)-[:CAUSED_BY]->(ag3);

// ── Evidence → Decision (REFERENCES) ─────────────────────────
MATCH (ev1:Evidence {id:'evidence-1'}), (dec1:Decision {id:'decision-1'}) CREATE (ev1)-[:REFERENCES]->(dec1);
MATCH (ev2:Evidence {id:'evidence-2'}), (dec2:Decision {id:'decision-2'}) CREATE (ev2)-[:REFERENCES]->(dec2);
MATCH (ev3:Evidence {id:'evidence-3'}), (dec3:Decision {id:'decision-3'}) CREATE (ev3)-[:REFERENCES]->(dec3);

// ── AIJudgment → Decision (RECOMMENDED) ──────────────────────
MATCH (ai1:AIJudgment {id:'ai-1'}), (dec1:Decision {id:'decision-1'}) CREATE (ai1)-[:RECOMMENDED]->(dec1);
MATCH (ai2:AIJudgment {id:'ai-2'}), (dec2:Decision {id:'decision-2'}) CREATE (ai2)-[:RECOMMENDED]->(dec2);

// ── Decision 연속성 (FOLLOWED_BY) ────────────────────────────
// 이전 결정이 다음 회의 아젠다로 이어지는 연속 고리
MATCH (dec1:Decision {id:'decision-1'}), (ag1:Agenda {id:'agenda-1'}) CREATE (dec1)-[:FOLLOWED_BY]->(ag1);


// ============================================================
// [INDEXES & CONSTRAINTS]
// ============================================================
CREATE CONSTRAINT IF NOT EXISTS FOR (n:Organization)  REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT IF NOT EXISTS FOR (n:Department)    REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT IF NOT EXISTS FOR (n:Person)        REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT IF NOT EXISTS FOR (n:MeetingGroup)  REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT IF NOT EXISTS FOR (n:Agenda)        REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT IF NOT EXISTS FOR (n:Document)      REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT IF NOT EXISTS FOR (n:Session)       REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT IF NOT EXISTS FOR (n:Decision)      REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT IF NOT EXISTS FOR (n:Evidence)      REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT IF NOT EXISTS FOR (n:AIJudgment)    REQUIRE n.id IS UNIQUE;
