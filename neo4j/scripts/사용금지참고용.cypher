// =============================================================
// seed.cypher  —  Realistic Sample Data
// SK AX — AI 제품 조직 시나리오
//
// 구조:
//   Organization(1) → Department(5) → Person(8)
//   MeetingGroup(4) — 회의체 간 REPORTS_TO 연결
//     mg-001 주간개발스프린트  →  mg-002 기술아키텍처위원회
//     mg-002 기술아키텍처위원회 →  mg-004 전사전략회의
//     mg-003 제품로드맵회의   →  mg-004 전사전략회의
//   Session  : mg별 3~5회 (총 12회)
//   Agenda   : 7개, 여러 회의/회의체에 걸쳐 반복 등장
//   Document : 회의록(Session→PRODUCED), 참고자료(ATTACHED_TO)
//   AIJudgment / HumanJudgment : Agenda 단위 판단 이력
// =============================================================


// ── 1. Organization ──────────────────────────────────────────

CREATE (:Organization {
  id: 'org-001',
  name: 'SK AX',
  org_type: '회사',
  established_at: '2019-03-01'
});


// ── 2. Department ────────────────────────────────────────────

CREATE (:Department {id: 'dept-001', name: '전략기획팀',   established_at: '2019-03-01'});
CREATE (:Department {id: 'dept-002', name: '제품개발팀',   established_at: '2019-03-01'});
CREATE (:Department {id: 'dept-003', name: 'AI연구팀',     established_at: '2020-01-15'});
CREATE (:Department {id: 'dept-004', name: 'UX디자인팀',   established_at: '2021-06-01'});
CREATE (:Department {id: 'dept-005', name: '데이터플랫폼팀', established_at: '2022-01-01'});


// ── 3. Role ───────────────────────────────────────────────────

CREATE (:Role {id: 'role-001', name: '간사'});
CREATE (:Role {id: 'role-002', name: '참여자'});


// ── 4. Person ────────────────────────────────────────────────

CREATE (:Person {id: 'p-001', name: '안민혁', email: 'minhyuk.ahn@sk-ax.com',    status: '출근'});
CREATE (:Person {id: 'p-002', name: '안상연', email: 'sangyeon.ahn@sk-ax.com',   status: '출근'});
CREATE (:Person {id: 'p-003', name: '이다예', email: 'daye.lee@sk-ax.com',       status: '재택'});
CREATE (:Person {id: 'p-004', name: '김세림', email: 'serim.kim@sk-ax.com',      status: '출근'});
CREATE (:Person {id: 'p-005', name: '이한결', email: 'hangyeol.lee@sk-ax.com',   status: '휴가'});
CREATE (:Person {id: 'p-006', name: '윤세준', email: 'sejun.yoon@sk-ax.com',     status: '출근'});
CREATE (:Person {id: 'p-007', name: '박지수', email: 'jisu.park@sk-ax.com',      status: '퇴근'});
CREATE (:Person {id: 'p-008', name: '최도윤', email: 'doyun.choi@sk-ax.com',     status: '출근'});


// ── 5. MeetingGroup ──────────────────────────────────────────

// mg-001: 실무 레벨 (매주)
CREATE (:MeetingGroup {
  id: 'mg-001',
  title: '주간 개발 스프린트',
  meeting_type: 'Weekly',
  created_at: '2025-01-06',
  last_report_at: '2026-05-19'
});

// mg-002: 기술 의사결정 레벨 (격주)
CREATE (:MeetingGroup {
  id: 'mg-002',
  title: '기술 아키텍처 위원회',
  meeting_type: 'Bi-weekly',
  created_at: '2025-01-13',
  last_report_at: '2026-05-12'
});

// mg-003: 제품 전략 레벨 (월간)
CREATE (:MeetingGroup {
  id: 'mg-003',
  title: '제품 로드맵 회의',
  meeting_type: 'Monthly',
  created_at: '2025-01-10',
  last_report_at: '2026-05-08'
});

// mg-004: 경영진 레벨 (분기)
CREATE (:MeetingGroup {
  id: 'mg-004',
  title: '전사 전략 회의',
  meeting_type: 'Quarterly',
  created_at: '2025-01-02',
  last_report_at: '2026-04-01'
});


// ── 6. Agenda ────────────────────────────────────────────────

CREATE (:Agenda {
  id: 'ag-001',
  title: 'AI 추천 엔진 v2 개발',
  category: '기술개발',
  description: '사용자 행동 기반 개인화 추천 엔진 v2 설계 및 구현. GraphRAG 파이프라인 연동.',
  status: '진행',
  priority: '상',
  created_at: '2026-03-10',
  due_date: '2026-06-30'
});

CREATE (:Agenda {
  id: 'ag-002',
  title: '클라우드 인프라 전환 계획',
  category: '인프라',
  description: '온프레미스 서버를 AWS 기반 멀티클라우드 환경으로 단계적 전환. 비용 분석 포함.',
  status: '승인대기',
  priority: '상',
  created_at: '2026-03-20',
  due_date: '2026-07-31'
});

CREATE (:Agenda {
  id: 'ag-003',
  title: 'UI/UX 개선 프로젝트 완료 보고',
  category: '디자인',
  description: '디자인 시스템 v2 적용 완료 및 사용성 테스트 결과 보고.',
  status: '완료',
  priority: '중',
  created_at: '2026-02-01',
  due_date: '2026-05-01'
});

CREATE (:Agenda {
  id: 'ag-004',
  title: 'Q3 사업 전략 방향성 수립',
  category: '전략',
  description: '3분기 핵심 KPI 설정 및 제품 로드맵 우선순위 조정. 외부 투자 유치 일정 포함.',
  status: '대기',
  priority: '상',
  created_at: '2026-05-01',
  due_date: '2026-06-15'
});

CREATE (:Agenda {
  id: 'ag-005',
  title: '실시간 데이터 파이프라인 구축',
  category: '데이터',
  description: 'Kafka + Flink 기반 실시간 이벤트 스트리밍 파이프라인 설계 및 구축.',
  status: '진행',
  priority: '중',
  created_at: '2026-04-01',
  due_date: '2026-07-15'
});

CREATE (:Agenda {
  id: 'ag-006',
  title: '보안 취약점 정기 점검 결과',
  category: '보안',
  description: 'OWASP Top 10 기준 취약점 점검 결과 공유 및 패치 계획 수립.',
  status: '완료',
  priority: '상',
  created_at: '2026-03-01',
  due_date: '2026-04-30'
});

CREATE (:Agenda {
  id: 'ag-007',
  title: 'API 게이트웨이 도입',
  category: '기술개발',
  description: 'MSA 전환에 따른 API 게이트웨이 선정(Kong vs AWS API GW) 및 도입 계획.',
  status: '진행',
  priority: '중',
  created_at: '2026-04-15',
  due_date: '2026-06-30'
});


// ── 7. Document (참고자료 및 회의록) ──────────────────────────

// 사전 참고 자료
CREATE (:Document {
  id: 'doc-ref-001',
  title: 'AI 추천 엔진 기술 검토 보고서',
  file_name: 'ai_rec_engine_review_v1.pdf',
  doc_type: '보고서',
  author: '김세림',
  created_at: '2026-03-05',
  file_url: '/uploads/ai_rec_engine_review_v1.pdf'
});

CREATE (:Document {
  id: 'doc-ref-002',
  title: '클라우드 전환 비용 분석서',
  file_name: 'cloud_migration_cost.xlsx',
  doc_type: '보고서',
  author: '윤세준',
  created_at: '2026-03-18',
  file_url: '/uploads/cloud_migration_cost.xlsx'
});

CREATE (:Document {
  id: 'doc-ref-003',
  title: 'UX 사용성 테스트 결과 보고서',
  file_name: 'ux_usability_test_2026q1.pdf',
  doc_type: '보고서',
  author: '이한결',
  created_at: '2026-04-28',
  file_url: '/uploads/ux_usability_test_2026q1.pdf'
});

CREATE (:Document {
  id: 'doc-ref-004',
  title: 'Q2 제품 현황 보고서',
  file_name: 'product_status_2026q2.pdf',
  doc_type: '보고서',
  author: '안민혁',
  created_at: '2026-05-02',
  file_url: '/uploads/product_status_2026q2.pdf'
});

CREATE (:Document {
  id: 'doc-ref-005',
  title: 'Kafka 파이프라인 아키텍처 설계서',
  file_name: 'kafka_pipeline_arch.pdf',
  doc_type: '보고서',
  author: '윤세준',
  created_at: '2026-04-10',
  file_url: '/uploads/kafka_pipeline_arch.pdf'
});

// 회의록 (세션별 1:1 대응, 아래 Session 생성 후 PRODUCED로 연결)
CREATE (:Document {
  id: 'doc-min-001',
  title: '스프린트 #18 회의록',
  file_name: 'sprint18_minutes.md',
  doc_type: '회의록',
  author: '안상연',
  created_at: '2026-04-07',
  file_url: '/uploads/sprint18_minutes.md'
});

CREATE (:Document {
  id: 'doc-min-002',
  title: '스프린트 #19 회의록',
  file_name: 'sprint19_minutes.md',
  doc_type: '회의록',
  author: '안상연',
  created_at: '2026-04-14',
  file_url: '/uploads/sprint19_minutes.md'
});

CREATE (:Document {
  id: 'doc-min-003',
  title: '스프린트 #20 회의록',
  file_name: 'sprint20_minutes.md',
  doc_type: '회의록',
  author: '안상연',
  created_at: '2026-04-28',
  file_url: '/uploads/sprint20_minutes.md'
});

CREATE (:Document {
  id: 'doc-min-004',
  title: '스프린트 #21 회의록',
  file_name: 'sprint21_minutes.md',
  doc_type: '회의록',
  author: '안상연',
  created_at: '2026-05-12',
  file_url: '/uploads/sprint21_minutes.md'
});

CREATE (:Document {
  id: 'doc-min-005',
  title: '스프린트 #22 회의록',
  file_name: 'sprint22_minutes.md',
  doc_type: '회의록',
  author: '안상연',
  created_at: '2026-05-19',
  file_url: '/uploads/sprint22_minutes.md'
});

CREATE (:Document {
  id: 'doc-min-006',
  title: '기술 아키텍처 위원회 8차 회의록',
  file_name: 'arch_committee_008.md',
  doc_type: '회의록',
  author: '김세림',
  created_at: '2026-04-14',
  file_url: '/uploads/arch_committee_008.md'
});

CREATE (:Document {
  id: 'doc-min-007',
  title: '기술 아키텍처 위원회 9차 회의록',
  file_name: 'arch_committee_009.md',
  doc_type: '회의록',
  author: '김세림',
  created_at: '2026-04-28',
  file_url: '/uploads/arch_committee_009.md'
});

CREATE (:Document {
  id: 'doc-min-008',
  title: '기술 아키텍처 위원회 10차 회의록',
  file_name: 'arch_committee_010.md',
  doc_type: '회의록',
  author: '김세림',
  created_at: '2026-05-12',
  file_url: '/uploads/arch_committee_010.md'
});

CREATE (:Document {
  id: 'doc-min-009',
  title: '제품 로드맵 회의 4월 회의록',
  file_name: 'roadmap_meeting_2026apr.md',
  doc_type: '회의록',
  author: '안민혁',
  created_at: '2026-04-08',
  file_url: '/uploads/roadmap_meeting_2026apr.md'
});

CREATE (:Document {
  id: 'doc-min-010',
  title: '제품 로드맵 회의 5월 회의록',
  file_name: 'roadmap_meeting_2026may.md',
  doc_type: '회의록',
  author: '안민혁',
  created_at: '2026-05-08',
  file_url: '/uploads/roadmap_meeting_2026may.md'
});

CREATE (:Document {
  id: 'doc-min-011',
  title: '2026 Q2 전사 전략 회의록',
  file_name: 'strategy_2026q2.md',
  doc_type: '회의록',
  author: '박지수',
  created_at: '2026-04-01',
  file_url: '/uploads/strategy_2026q2.md'
});

CREATE (:Document {
  id: 'doc-min-012',
  title: '보안 취약점 점검 최종 보고 회의록',
  file_name: 'security_review_final.md',
  doc_type: '회의록',
  author: '안민혁',
  created_at: '2026-04-21',
  file_url: '/uploads/security_review_final.md'
});

// 보도자료
CREATE (:Document {
  id: 'doc-pr-001',
  title: 'SK AX AI 추천 엔진 고도화 착수 보도자료',
  file_name: 'pr_ai_engine_v2_launch.pdf',
  doc_type: '보도자료',
  author: '안민혁',
  created_at: '2026-04-01',
  file_url: '/uploads/pr_ai_engine_v2_launch.pdf'
});


// ── 8. Session ───────────────────────────────────────────────
//  mg-001 주간 개발 스프린트 (s-001 ~ s-005)

CREATE (:Session {
  id: 's-001',
  title: '스프린트 #18 킥오프',
  date: '2026-04-07',
  session_type: '대면',
  description: '스프린트 18 목표 설정 및 AI 추천 엔진 v2 설계 착수 논의.',
  status: 'closed',
  session_number: 18
});

CREATE (:Session {
  id: 's-002',
  title: '스프린트 #19 주간 회의',
  date: '2026-04-14',
  session_type: '대면',
  description: 'AI 추천 엔진 v2 데이터 수집 모듈 개발 현황 점검, 보안 취약점 패치 완료 확인.',
  status: 'closed',
  session_number: 19
});

CREATE (:Session {
  id: 's-003',
  title: '스프린트 #20 주간 회의',
  date: '2026-04-28',
  session_type: '비대면',
  description: '데이터 파이프라인 구축 1단계 완료 보고, UX 개선 QA 통과 확인.',
  status: 'closed',
  session_number: 20
});

CREATE (:Session {
  id: 's-004',
  title: '스프린트 #21 주간 회의',
  date: '2026-05-12',
  session_type: '대면',
  description: 'AI 추천 엔진 v2 모델 학습 결과 발표, API 게이트웨이 POC 착수 논의.',
  status: 'closed',
  session_number: 21
});

CREATE (:Session {
  id: 's-005',
  title: '스프린트 #22 주간 회의',
  date: '2026-05-19',
  session_type: '대면',
  description: 'API 게이트웨이 Kong vs AWS 비교 결과 공유, 데이터 파이프라인 2단계 계획 수립.',
  status: 'open',
  session_number: 22
});

// mg-002 기술 아키텍처 위원회 (s-006 ~ s-008)

CREATE (:Session {
  id: 's-006',
  title: '기술 아키텍처 위원회 8차',
  date: '2026-04-14',
  session_type: '대면',
  description: '클라우드 전환 1단계 계획 검토, 보안 취약점 점검 결과 확인.',
  status: 'closed',
  session_number: 8
});

CREATE (:Session {
  id: 's-007',
  title: '기술 아키텍처 위원회 9차',
  date: '2026-04-28',
  session_type: '대면',
  description: '데이터 파이프라인 아키텍처 심의, AI 추천 엔진 v2 기술 스택 승인.',
  status: 'closed',
  session_number: 9
});

CREATE (:Session {
  id: 's-008',
  title: '기술 아키텍처 위원회 10차',
  date: '2026-05-12',
  session_type: '비대면',
  description: 'API 게이트웨이 도입 방안 심의, 클라우드 전환 비용 분석 최종 검토.',
  status: 'closed',
  session_number: 10
});

// mg-003 제품 로드맵 회의 (s-009 ~ s-010)

CREATE (:Session {
  id: 's-009',
  title: '제품 로드맵 4월 정기 회의',
  date: '2026-04-08',
  session_type: '대면',
  description: 'UX/UI 개선 완료 보고, AI 추천 엔진 v2 로드맵 확정.',
  status: 'closed',
  session_number: 4
});

CREATE (:Session {
  id: 's-010',
  title: '제품 로드맵 5월 정기 회의',
  date: '2026-05-08',
  session_type: '대면',
  description: 'Q3 제품 방향성 논의, 클라우드 전환 영향도 분석 공유.',
  status: 'closed',
  session_number: 5
});

// mg-003 보안 특별 세션
CREATE (:Session {
  id: 's-011',
  title: '보안 취약점 최종 보고',
  date: '2026-04-21',
  session_type: '대면',
  description: 'OWASP 기준 취약점 패치 완료 확인 및 재발 방지 대책 수립.',
  status: 'closed',
  session_number: 6
});

// mg-004 전사 전략 회의 (s-012)

CREATE (:Session {
  id: 's-012',
  title: '2026 Q2 전사 전략 회의',
  date: '2026-04-01',
  session_type: '대면',
  description: 'Q1 성과 리뷰 및 Q2 전략 방향 확정. AI 추천 엔진 v2 투자 계획 승인.',
  status: 'closed',
  session_number: 2
});


// ── 9. AIJudgment & HumanJudgment ────────────────────────────

CREATE (:AIJudgment {
  id: 'aj-001',
  created_at: '2026-04-07T18:00:00',
  score: 91,
  version: 1,
  rationale: 'AI 추천 엔진 v2 착수 타당. 현재 데이터 인프라 성숙도 충분, Q2 내 PoC 완료 가능성 높음.'
});

CREATE (:AIJudgment {
  id: 'aj-002',
  created_at: '2026-04-14T19:00:00',
  score: 74,
  version: 1,
  rationale: '클라우드 전환은 비용 절감 효과 명확하나 마이그레이션 리스크 존재. 단계적 접근 권장.'
});

CREATE (:AIJudgment {
  id: 'aj-003',
  created_at: '2026-04-28T17:30:00',
  score: 85,
  version: 1,
  rationale: '데이터 파이프라인 설계 타당. Kafka + Flink 선택은 현재 처리량 요구사항 대비 적합.'
});

CREATE (:AIJudgment {
  id: 'aj-004',
  created_at: '2026-05-08T20:00:00',
  score: 68,
  version: 1,
  rationale: 'Q3 전략 방향 논의 시기 적절하나 외부 투자 유치 일정과 제품 로드맵 간 리소스 충돌 가능성 있음.'
});

CREATE (:AIJudgment {
  id: 'aj-005',
  created_at: '2026-05-12T18:00:00',
  score: 82,
  version: 1,
  rationale: 'API 게이트웨이 도입 타당. Kong이 AWS API GW 대비 운영 유연성 우위. MSA 전환 속도에 긍정적.'
});

CREATE (:HumanJudgment {
  id: 'hj-001',
  judged_at: '2026-04-08T09:00:00',
  judgment: '승인',
  version: 1,
  rationale: 'AI 추천 엔진 v2 착수 승인. Q2 마일스톤 연동하여 진행.'
});

CREATE (:HumanJudgment {
  id: 'hj-002',
  judged_at: '2026-04-29T10:00:00',
  judgment: '승인',
  version: 1,
  rationale: 'Kafka 파이프라인 아키텍처 검토 완료. 1단계 구축 진행 승인.'
});

CREATE (:HumanJudgment {
  id: 'hj-003',
  judged_at: '2026-05-09T14:00:00',
  judgment: '반려',
  version: 1,
  rationale: 'Q3 전략 수립 전 투자 유치 일정 재조정 필요. 로드맵 우선순위 재검토 후 재상정.'
});

CREATE (:HumanJudgment {
  id: 'hj-004',
  judged_at: '2026-05-13T10:00:00',
  judgment: '승인',
  version: 1,
  rationale: 'Kong API 게이트웨이 도입 승인. 6월 말까지 PoC 환경 구성 완료 목표.'
});

CREATE (:HumanJudgment {
  id: 'hj-005',
  judged_at: '2026-04-28T15:00:00',
  judgment: '승인',
  version: 1,
  rationale: '클라우드 전환 1단계(개발 환경) 승인. 2단계는 비용 분석 보완 후 재심의.'
});


// =============================================================
// 관계 정의
// =============================================================

// ── 10. Department → Organization ────────────────────────────

MATCH (d:Department), (o:Organization {id: 'org-001'})
CREATE (d)-[:PART_OF]->(o);


// ── 11. Person → Department ──────────────────────────────────

MATCH (p:Person {id: 'p-001'}), (d:Department {id: 'dept-001'}) CREATE (p)-[:BELONGS_TO]->(d);
MATCH (p:Person {id: 'p-002'}), (d:Department {id: 'dept-002'}) CREATE (p)-[:BELONGS_TO]->(d);
MATCH (p:Person {id: 'p-003'}), (d:Department {id: 'dept-002'}) CREATE (p)-[:BELONGS_TO]->(d);
MATCH (p:Person {id: 'p-004'}), (d:Department {id: 'dept-003'}) CREATE (p)-[:BELONGS_TO]->(d);
MATCH (p:Person {id: 'p-005'}), (d:Department {id: 'dept-004'}) CREATE (p)-[:BELONGS_TO]->(d);
MATCH (p:Person {id: 'p-006'}), (d:Department {id: 'dept-005'}) CREATE (p)-[:BELONGS_TO]->(d);
MATCH (p:Person {id: 'p-007'}), (d:Department {id: 'dept-001'}) CREATE (p)-[:BELONGS_TO]->(d);
MATCH (p:Person {id: 'p-008'}), (d:Department {id: 'dept-003'}) CREATE (p)-[:BELONGS_TO]->(d);


// ── 12. Person → Role ────────────────────────────────────────

MATCH (p:Person {id: 'p-001'}), (r:Role {id: 'role-001'}) CREATE (p)-[:HAS_ROLE]->(r);
MATCH (p:Person {id: 'p-002'}), (r:Role {id: 'role-002'}) CREATE (p)-[:HAS_ROLE]->(r);
MATCH (p:Person {id: 'p-003'}), (r:Role {id: 'role-002'}) CREATE (p)-[:HAS_ROLE]->(r);
MATCH (p:Person {id: 'p-004'}), (r:Role {id: 'role-001'}) CREATE (p)-[:HAS_ROLE]->(r);
MATCH (p:Person {id: 'p-005'}), (r:Role {id: 'role-002'}) CREATE (p)-[:HAS_ROLE]->(r);
MATCH (p:Person {id: 'p-006'}), (r:Role {id: 'role-001'}) CREATE (p)-[:HAS_ROLE]->(r);
MATCH (p:Person {id: 'p-007'}), (r:Role {id: 'role-002'}) CREATE (p)-[:HAS_ROLE]->(r);
MATCH (p:Person {id: 'p-008'}), (r:Role {id: 'role-002'}) CREATE (p)-[:HAS_ROLE]->(r);


// ── 13. Department → MeetingGroup ────────────────────────────

MATCH (d:Department {id: 'dept-002'}), (mg:MeetingGroup {id: 'mg-001'}) CREATE (d)-[:PARTICIPATES_IN]->(mg);
MATCH (d:Department {id: 'dept-003'}), (mg:MeetingGroup {id: 'mg-001'}) CREATE (d)-[:PARTICIPATES_IN]->(mg);
MATCH (d:Department {id: 'dept-005'}), (mg:MeetingGroup {id: 'mg-001'}) CREATE (d)-[:PARTICIPATES_IN]->(mg);

MATCH (d:Department {id: 'dept-002'}), (mg:MeetingGroup {id: 'mg-002'}) CREATE (d)-[:PARTICIPATES_IN]->(mg);
MATCH (d:Department {id: 'dept-003'}), (mg:MeetingGroup {id: 'mg-002'}) CREATE (d)-[:PARTICIPATES_IN]->(mg);
MATCH (d:Department {id: 'dept-005'}), (mg:MeetingGroup {id: 'mg-002'}) CREATE (d)-[:PARTICIPATES_IN]->(mg);

MATCH (d:Department {id: 'dept-001'}), (mg:MeetingGroup {id: 'mg-003'}) CREATE (d)-[:PARTICIPATES_IN]->(mg);
MATCH (d:Department {id: 'dept-002'}), (mg:MeetingGroup {id: 'mg-003'}) CREATE (d)-[:PARTICIPATES_IN]->(mg);
MATCH (d:Department {id: 'dept-004'}), (mg:MeetingGroup {id: 'mg-003'}) CREATE (d)-[:PARTICIPATES_IN]->(mg);

MATCH (d:Department {id: 'dept-001'}), (mg:MeetingGroup {id: 'mg-004'}) CREATE (d)-[:PARTICIPATES_IN]->(mg);
MATCH (d:Department {id: 'dept-002'}), (mg:MeetingGroup {id: 'mg-004'}) CREATE (d)-[:PARTICIPATES_IN]->(mg);
MATCH (d:Department {id: 'dept-003'}), (mg:MeetingGroup {id: 'mg-004'}) CREATE (d)-[:PARTICIPATES_IN]->(mg);


// ── 14. Person → MeetingGroup (ADMIN_OF / MEMBER_OF) ─────────

// mg-001 주간 개발 스프린트
MATCH (p:Person {id: 'p-002'}), (mg:MeetingGroup {id: 'mg-001'}) CREATE (p)-[:ADMIN_OF]->(mg);
MATCH (p:Person {id: 'p-003'}), (mg:MeetingGroup {id: 'mg-001'}) CREATE (p)-[:MEMBER_OF]->(mg);
MATCH (p:Person {id: 'p-004'}), (mg:MeetingGroup {id: 'mg-001'}) CREATE (p)-[:MEMBER_OF]->(mg);
MATCH (p:Person {id: 'p-006'}), (mg:MeetingGroup {id: 'mg-001'}) CREATE (p)-[:MEMBER_OF]->(mg);
MATCH (p:Person {id: 'p-008'}), (mg:MeetingGroup {id: 'mg-001'}) CREATE (p)-[:MEMBER_OF]->(mg);

// mg-002 기술 아키텍처 위원회
MATCH (p:Person {id: 'p-004'}), (mg:MeetingGroup {id: 'mg-002'}) CREATE (p)-[:ADMIN_OF]->(mg);
MATCH (p:Person {id: 'p-002'}), (mg:MeetingGroup {id: 'mg-002'}) CREATE (p)-[:MEMBER_OF]->(mg);
MATCH (p:Person {id: 'p-003'}), (mg:MeetingGroup {id: 'mg-002'}) CREATE (p)-[:MEMBER_OF]->(mg);
MATCH (p:Person {id: 'p-006'}), (mg:MeetingGroup {id: 'mg-002'}) CREATE (p)-[:MEMBER_OF]->(mg);

// mg-003 제품 로드맵 회의
MATCH (p:Person {id: 'p-001'}), (mg:MeetingGroup {id: 'mg-003'}) CREATE (p)-[:ADMIN_OF]->(mg);
MATCH (p:Person {id: 'p-002'}), (mg:MeetingGroup {id: 'mg-003'}) CREATE (p)-[:MEMBER_OF]->(mg);
MATCH (p:Person {id: 'p-004'}), (mg:MeetingGroup {id: 'mg-003'}) CREATE (p)-[:MEMBER_OF]->(mg);
MATCH (p:Person {id: 'p-005'}), (mg:MeetingGroup {id: 'mg-003'}) CREATE (p)-[:MEMBER_OF]->(mg);

// mg-004 전사 전략 회의
MATCH (p:Person {id: 'p-007'}), (mg:MeetingGroup {id: 'mg-004'}) CREATE (p)-[:ADMIN_OF]->(mg);
MATCH (p:Person {id: 'p-001'}), (mg:MeetingGroup {id: 'mg-004'}) CREATE (p)-[:MEMBER_OF]->(mg);
MATCH (p:Person {id: 'p-004'}), (mg:MeetingGroup {id: 'mg-004'}) CREATE (p)-[:MEMBER_OF]->(mg);


// ── 15. MeetingGroup 간 계층 연결 ────────────────────────────
// 실무 → 기술심의 → 경영진 보고 구조

MATCH (mg1:MeetingGroup {id: 'mg-001'}), (mg2:MeetingGroup {id: 'mg-002'})
CREATE (mg1)-[:REPORTS_TO]->(mg2);

MATCH (mg2:MeetingGroup {id: 'mg-002'}), (mg4:MeetingGroup {id: 'mg-004'})
CREATE (mg2)-[:REPORTS_TO]->(mg4);

MATCH (mg3:MeetingGroup {id: 'mg-003'}), (mg4:MeetingGroup {id: 'mg-004'})
CREATE (mg3)-[:REPORTS_TO]->(mg4);


// ── 16. Agenda → MeetingGroup ────────────────────────────────

MATCH (a:Agenda {id: 'ag-001'}), (mg:MeetingGroup {id: 'mg-001'}) CREATE (a)-[:OWNED_BY]->(mg);
MATCH (a:Agenda {id: 'ag-002'}), (mg:MeetingGroup {id: 'mg-002'}) CREATE (a)-[:OWNED_BY]->(mg);
MATCH (a:Agenda {id: 'ag-003'}), (mg:MeetingGroup {id: 'mg-003'}) CREATE (a)-[:OWNED_BY]->(mg);
MATCH (a:Agenda {id: 'ag-004'}), (mg:MeetingGroup {id: 'mg-004'}) CREATE (a)-[:OWNED_BY]->(mg);
MATCH (a:Agenda {id: 'ag-005'}), (mg:MeetingGroup {id: 'mg-001'}) CREATE (a)-[:OWNED_BY]->(mg);
MATCH (a:Agenda {id: 'ag-006'}), (mg:MeetingGroup {id: 'mg-003'}) CREATE (a)-[:OWNED_BY]->(mg);
MATCH (a:Agenda {id: 'ag-007'}), (mg:MeetingGroup {id: 'mg-002'}) CREATE (a)-[:OWNED_BY]->(mg);


// ── 17. Agenda → Person (담당자) ──────────────────────────────

MATCH (a:Agenda {id: 'ag-001'}), (p:Person {id: 'p-004'}) CREATE (a)-[:ASSIGNED_TO]->(p);
MATCH (a:Agenda {id: 'ag-002'}), (p:Person {id: 'p-006'}) CREATE (a)-[:ASSIGNED_TO]->(p);
MATCH (a:Agenda {id: 'ag-003'}), (p:Person {id: 'p-005'}) CREATE (a)-[:ASSIGNED_TO]->(p);
MATCH (a:Agenda {id: 'ag-004'}), (p:Person {id: 'p-001'}) CREATE (a)-[:ASSIGNED_TO]->(p);
MATCH (a:Agenda {id: 'ag-005'}), (p:Person {id: 'p-006'}) CREATE (a)-[:ASSIGNED_TO]->(p);
MATCH (a:Agenda {id: 'ag-006'}), (p:Person {id: 'p-003'}) CREATE (a)-[:ASSIGNED_TO]->(p);
MATCH (a:Agenda {id: 'ag-007'}), (p:Person {id: 'p-003'}) CREATE (a)-[:ASSIGNED_TO]->(p);


// ── 18. Document (참고자료) → MeetingGroup ────────────────────

MATCH (doc:Document {id: 'doc-ref-001'}), (mg:MeetingGroup {id: 'mg-001'}) CREATE (doc)-[:ATTACHED_TO]->(mg);
MATCH (doc:Document {id: 'doc-ref-002'}), (mg:MeetingGroup {id: 'mg-002'}) CREATE (doc)-[:ATTACHED_TO]->(mg);
MATCH (doc:Document {id: 'doc-ref-003'}), (mg:MeetingGroup {id: 'mg-003'}) CREATE (doc)-[:ATTACHED_TO]->(mg);
MATCH (doc:Document {id: 'doc-ref-004'}), (mg:MeetingGroup {id: 'mg-004'}) CREATE (doc)-[:ATTACHED_TO]->(mg);
MATCH (doc:Document {id: 'doc-ref-005'}), (mg:MeetingGroup {id: 'mg-001'}) CREATE (doc)-[:ATTACHED_TO]->(mg);
MATCH (doc:Document {id: 'doc-pr-001'}),  (mg:MeetingGroup {id: 'mg-004'}) CREATE (doc)-[:ATTACHED_TO]->(mg);


// ── 19. Session → MeetingGroup ───────────────────────────────

MATCH (s:Session {id: 's-001'}), (mg:MeetingGroup {id: 'mg-001'}) CREATE (s)-[:HELD_BY]->(mg);
MATCH (s:Session {id: 's-002'}), (mg:MeetingGroup {id: 'mg-001'}) CREATE (s)-[:HELD_BY]->(mg);
MATCH (s:Session {id: 's-003'}), (mg:MeetingGroup {id: 'mg-001'}) CREATE (s)-[:HELD_BY]->(mg);
MATCH (s:Session {id: 's-004'}), (mg:MeetingGroup {id: 'mg-001'}) CREATE (s)-[:HELD_BY]->(mg);
MATCH (s:Session {id: 's-005'}), (mg:MeetingGroup {id: 'mg-001'}) CREATE (s)-[:HELD_BY]->(mg);

MATCH (s:Session {id: 's-006'}), (mg:MeetingGroup {id: 'mg-002'}) CREATE (s)-[:HELD_BY]->(mg);
MATCH (s:Session {id: 's-007'}), (mg:MeetingGroup {id: 'mg-002'}) CREATE (s)-[:HELD_BY]->(mg);
MATCH (s:Session {id: 's-008'}), (mg:MeetingGroup {id: 'mg-002'}) CREATE (s)-[:HELD_BY]->(mg);

MATCH (s:Session {id: 's-009'}), (mg:MeetingGroup {id: 'mg-003'}) CREATE (s)-[:HELD_BY]->(mg);
MATCH (s:Session {id: 's-010'}), (mg:MeetingGroup {id: 'mg-003'}) CREATE (s)-[:HELD_BY]->(mg);
MATCH (s:Session {id: 's-011'}), (mg:MeetingGroup {id: 'mg-003'}) CREATE (s)-[:HELD_BY]->(mg);

MATCH (s:Session {id: 's-012'}), (mg:MeetingGroup {id: 'mg-004'}) CREATE (s)-[:HELD_BY]->(mg);


// ── 20. Session → Agenda (COVERS) ────────────────────────────
// 동일 아젠다가 여러 회차에 걸쳐 반복 등장

// ag-001 AI 추천 엔진 v2: 스프린트 18~22, 아키텍처위 7~9, 로드맵 4월, 전략 Q2
MATCH (s:Session {id: 's-001'}), (a:Agenda {id: 'ag-001'}) CREATE (s)-[:COVERS]->(a);
MATCH (s:Session {id: 's-002'}), (a:Agenda {id: 'ag-001'}) CREATE (s)-[:COVERS]->(a);
MATCH (s:Session {id: 's-003'}), (a:Agenda {id: 'ag-001'}) CREATE (s)-[:COVERS]->(a);
MATCH (s:Session {id: 's-004'}), (a:Agenda {id: 'ag-001'}) CREATE (s)-[:COVERS]->(a);
MATCH (s:Session {id: 's-007'}), (a:Agenda {id: 'ag-001'}) CREATE (s)-[:COVERS]->(a);
MATCH (s:Session {id: 's-009'}), (a:Agenda {id: 'ag-001'}) CREATE (s)-[:COVERS]->(a);
MATCH (s:Session {id: 's-012'}), (a:Agenda {id: 'ag-001'}) CREATE (s)-[:COVERS]->(a);

// ag-002 클라우드 전환: 아키텍처위 8~10, 로드맵 5월, 전략 Q2
MATCH (s:Session {id: 's-006'}), (a:Agenda {id: 'ag-002'}) CREATE (s)-[:COVERS]->(a);
MATCH (s:Session {id: 's-007'}), (a:Agenda {id: 'ag-002'}) CREATE (s)-[:COVERS]->(a);
MATCH (s:Session {id: 's-008'}), (a:Agenda {id: 'ag-002'}) CREATE (s)-[:COVERS]->(a);
MATCH (s:Session {id: 's-010'}), (a:Agenda {id: 'ag-002'}) CREATE (s)-[:COVERS]->(a);
MATCH (s:Session {id: 's-012'}), (a:Agenda {id: 'ag-002'}) CREATE (s)-[:COVERS]->(a);

// ag-003 UX 개선 완료 보고: 스프린트 20, 로드맵 4월
MATCH (s:Session {id: 's-003'}), (a:Agenda {id: 'ag-003'}) CREATE (s)-[:COVERS]->(a);
MATCH (s:Session {id: 's-009'}), (a:Agenda {id: 'ag-003'}) CREATE (s)-[:COVERS]->(a);

// ag-004 Q3 전략: 로드맵 5월, 전략 Q2
MATCH (s:Session {id: 's-010'}), (a:Agenda {id: 'ag-004'}) CREATE (s)-[:COVERS]->(a);
MATCH (s:Session {id: 's-012'}), (a:Agenda {id: 'ag-004'}) CREATE (s)-[:COVERS]->(a);

// ag-005 데이터 파이프라인: 스프린트 19~22, 아키텍처위 9차
MATCH (s:Session {id: 's-002'}), (a:Agenda {id: 'ag-005'}) CREATE (s)-[:COVERS]->(a);
MATCH (s:Session {id: 's-003'}), (a:Agenda {id: 'ag-005'}) CREATE (s)-[:COVERS]->(a);
MATCH (s:Session {id: 's-005'}), (a:Agenda {id: 'ag-005'}) CREATE (s)-[:COVERS]->(a);
MATCH (s:Session {id: 's-007'}), (a:Agenda {id: 'ag-005'}) CREATE (s)-[:COVERS]->(a);

// ag-006 보안 취약점: 스프린트 19, 아키텍처위 8, 로드맵 보안특별
MATCH (s:Session {id: 's-002'}), (a:Agenda {id: 'ag-006'}) CREATE (s)-[:COVERS]->(a);
MATCH (s:Session {id: 's-006'}), (a:Agenda {id: 'ag-006'}) CREATE (s)-[:COVERS]->(a);
MATCH (s:Session {id: 's-011'}), (a:Agenda {id: 'ag-006'}) CREATE (s)-[:COVERS]->(a);

// ag-007 API 게이트웨이: 스프린트 21~22, 아키텍처위 10
MATCH (s:Session {id: 's-004'}), (a:Agenda {id: 'ag-007'}) CREATE (s)-[:COVERS]->(a);
MATCH (s:Session {id: 's-005'}), (a:Agenda {id: 'ag-007'}) CREATE (s)-[:COVERS]->(a);
MATCH (s:Session {id: 's-008'}), (a:Agenda {id: 'ag-007'}) CREATE (s)-[:COVERS]->(a);


// ── 21. Session → Document (PRODUCED: 회의록 생성) ───────────

MATCH (s:Session {id: 's-001'}), (doc:Document {id: 'doc-min-001'}) CREATE (s)-[:PRODUCED]->(doc);
MATCH (s:Session {id: 's-002'}), (doc:Document {id: 'doc-min-002'}) CREATE (s)-[:PRODUCED]->(doc);
MATCH (s:Session {id: 's-003'}), (doc:Document {id: 'doc-min-003'}) CREATE (s)-[:PRODUCED]->(doc);
MATCH (s:Session {id: 's-004'}), (doc:Document {id: 'doc-min-004'}) CREATE (s)-[:PRODUCED]->(doc);
MATCH (s:Session {id: 's-005'}), (doc:Document {id: 'doc-min-005'}) CREATE (s)-[:PRODUCED]->(doc);
MATCH (s:Session {id: 's-006'}), (doc:Document {id: 'doc-min-006'}) CREATE (s)-[:PRODUCED]->(doc);
MATCH (s:Session {id: 's-007'}), (doc:Document {id: 'doc-min-007'}) CREATE (s)-[:PRODUCED]->(doc);
MATCH (s:Session {id: 's-008'}), (doc:Document {id: 'doc-min-008'}) CREATE (s)-[:PRODUCED]->(doc);
MATCH (s:Session {id: 's-009'}), (doc:Document {id: 'doc-min-009'}) CREATE (s)-[:PRODUCED]->(doc);
MATCH (s:Session {id: 's-010'}), (doc:Document {id: 'doc-min-010'}) CREATE (s)-[:PRODUCED]->(doc);
MATCH (s:Session {id: 's-011'}), (doc:Document {id: 'doc-min-012'}) CREATE (s)-[:PRODUCED]->(doc);
MATCH (s:Session {id: 's-012'}), (doc:Document {id: 'doc-min-011'}) CREATE (s)-[:PRODUCED]->(doc);


// ── 22. Session → Session (REFERENCES: 이전 회의 참조) ────────
// 각 회의체 내 연속 회차

// mg-001 스프린트 연속 참조
MATCH (s1:Session {id: 's-002'}), (s2:Session {id: 's-001'}) CREATE (s1)-[:REFERENCES]->(s2);
MATCH (s1:Session {id: 's-003'}), (s2:Session {id: 's-002'}) CREATE (s1)-[:REFERENCES]->(s2);
MATCH (s1:Session {id: 's-004'}), (s2:Session {id: 's-003'}) CREATE (s1)-[:REFERENCES]->(s2);
MATCH (s1:Session {id: 's-005'}), (s2:Session {id: 's-004'}) CREATE (s1)-[:REFERENCES]->(s2);

// mg-002 아키텍처 위원회 연속 참조
MATCH (s1:Session {id: 's-007'}), (s2:Session {id: 's-006'}) CREATE (s1)-[:REFERENCES]->(s2);
MATCH (s1:Session {id: 's-008'}), (s2:Session {id: 's-007'}) CREATE (s1)-[:REFERENCES]->(s2);

// mg-003 로드맵 회의 연속 참조
MATCH (s1:Session {id: 's-010'}), (s2:Session {id: 's-009'}) CREATE (s1)-[:REFERENCES]->(s2);

// 회의체 간 참조: 스프린트 회의 → 아키텍처 위원회 (실무 결과 보고)
MATCH (s1:Session {id: 's-007'}), (s2:Session {id: 's-003'}) CREATE (s1)-[:REFERENCES]->(s2);
MATCH (s1:Session {id: 's-008'}), (s2:Session {id: 's-004'}) CREATE (s1)-[:REFERENCES]->(s2);

// 회의체 간 참조: 로드맵 회의 → 전략 회의
MATCH (s1:Session {id: 's-012'}), (s2:Session {id: 's-009'}) CREATE (s1)-[:REFERENCES]->(s2);


// ── 23. AIJudgment → Agenda ───────────────────────────────────

MATCH (aj:AIJudgment {id: 'aj-001'}), (a:Agenda {id: 'ag-001'}) CREATE (aj)-[:ABOUT]->(a);
MATCH (aj:AIJudgment {id: 'aj-002'}), (a:Agenda {id: 'ag-002'}) CREATE (aj)-[:ABOUT]->(a);
MATCH (aj:AIJudgment {id: 'aj-003'}), (a:Agenda {id: 'ag-005'}) CREATE (aj)-[:ABOUT]->(a);
MATCH (aj:AIJudgment {id: 'aj-004'}), (a:Agenda {id: 'ag-004'}) CREATE (aj)-[:ABOUT]->(a);
MATCH (aj:AIJudgment {id: 'aj-005'}), (a:Agenda {id: 'ag-007'}) CREATE (aj)-[:ABOUT]->(a);


// ── 24. AIJudgment → Document (판단 근거) ────────────────────

MATCH (aj:AIJudgment {id: 'aj-001'}), (doc:Document {id: 'doc-ref-001'}) CREATE (aj)-[:BASED_ON]->(doc);
MATCH (aj:AIJudgment {id: 'aj-002'}), (doc:Document {id: 'doc-ref-002'}) CREATE (aj)-[:BASED_ON]->(doc);
MATCH (aj:AIJudgment {id: 'aj-003'}), (doc:Document {id: 'doc-ref-005'}) CREATE (aj)-[:BASED_ON]->(doc);
MATCH (aj:AIJudgment {id: 'aj-004'}), (doc:Document {id: 'doc-ref-004'}) CREATE (aj)-[:BASED_ON]->(doc);
MATCH (aj:AIJudgment {id: 'aj-005'}), (doc:Document {id: 'doc-min-004'}) CREATE (aj)-[:BASED_ON]->(doc);


// ── 25. HumanJudgment → Agenda ────────────────────────────────

MATCH (hj:HumanJudgment {id: 'hj-001'}), (a:Agenda {id: 'ag-001'}) CREATE (hj)-[:ABOUT]->(a);
MATCH (hj:HumanJudgment {id: 'hj-002'}), (a:Agenda {id: 'ag-005'}) CREATE (hj)-[:ABOUT]->(a);
MATCH (hj:HumanJudgment {id: 'hj-003'}), (a:Agenda {id: 'ag-004'}) CREATE (hj)-[:ABOUT]->(a);
MATCH (hj:HumanJudgment {id: 'hj-004'}), (a:Agenda {id: 'ag-007'}) CREATE (hj)-[:ABOUT]->(a);
MATCH (hj:HumanJudgment {id: 'hj-005'}), (a:Agenda {id: 'ag-002'}) CREATE (hj)-[:ABOUT]->(a);


// ── 26. HumanJudgment → AIJudgment (검토) ────────────────────

MATCH (hj:HumanJudgment {id: 'hj-001'}), (aj:AIJudgment {id: 'aj-001'}) CREATE (hj)-[:REVIEWED]->(aj);
MATCH (hj:HumanJudgment {id: 'hj-002'}), (aj:AIJudgment {id: 'aj-003'}) CREATE (hj)-[:REVIEWED]->(aj);
MATCH (hj:HumanJudgment {id: 'hj-003'}), (aj:AIJudgment {id: 'aj-004'}) CREATE (hj)-[:REVIEWED]->(aj);
MATCH (hj:HumanJudgment {id: 'hj-004'}), (aj:AIJudgment {id: 'aj-005'}) CREATE (hj)-[:REVIEWED]->(aj);
MATCH (hj:HumanJudgment {id: 'hj-005'}), (aj:AIJudgment {id: 'aj-002'}) CREATE (hj)-[:REVIEWED]->(aj);


// ── 27. HumanJudgment → Person (판단자) ──────────────────────

MATCH (hj:HumanJudgment {id: 'hj-001'}), (p:Person {id: 'p-001'}) CREATE (hj)-[:JUDGED_BY]->(p);
MATCH (hj:HumanJudgment {id: 'hj-002'}), (p:Person {id: 'p-004'}) CREATE (hj)-[:JUDGED_BY]->(p);
MATCH (hj:HumanJudgment {id: 'hj-003'}), (p:Person {id: 'p-001'}) CREATE (hj)-[:JUDGED_BY]->(p);
MATCH (hj:HumanJudgment {id: 'hj-004'}), (p:Person {id: 'p-004'}) CREATE (hj)-[:JUDGED_BY]->(p);
MATCH (hj:HumanJudgment {id: 'hj-005'}), (p:Person {id: 'p-007'}) CREATE (hj)-[:JUDGED_BY]->(p);
