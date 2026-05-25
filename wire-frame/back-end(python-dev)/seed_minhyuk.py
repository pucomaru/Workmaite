"""
안민혁(p-006) 기준 Neo4j 더미데이터 시딩 스크립트
기존 노드들을 MATCH로 활용하여 풍부한 관계 구성
"""
import asyncio, httpx, base64, os, sys
from dotenv import load_dotenv

load_dotenv("../.env")
NEO4J_URL  = os.getenv("NEO4J_URL")
NEO4J_USER = os.getenv("NEO4J_USER")
NEO4J_PASS = os.getenv("NEO4J_PASSWORD")
NEO4J_DB   = os.getenv("NEO4J_DATABASE", "neo4j")

creds    = base64.b64encode(f"{NEO4J_USER}:{NEO4J_PASS}".encode()).decode()
HEADERS  = {"Authorization": f"Basic {creds}", "Content-Type": "application/json", "Accept": "application/json"}
ENDPOINT = f"{NEO4J_URL}/db/{NEO4J_DB}/tx/commit"


async def run(cypher: str, params: dict = None) -> list:
    payload = {"statements": [{"statement": cypher, "parameters": params or {}}]}
    async with httpx.AsyncClient(timeout=10) as c:
        r = await c.post(ENDPOINT, json=payload, headers=HEADERS)
        body = r.json()
        if body.get("errors"):
            print(f"  [ERROR] {body['errors']}")
            return []
        res = body["results"][0] if body.get("results") else {}
        cols = res.get("columns", [])
        return [dict(zip(cols, row["row"])) for row in res.get("data", [])]


# ─────────────────────────────────────────────────────────────────────────────
# 각 단계별 Cypher 구문 (MERGE → 중복 안전, MATCH → 기존 노드 활용)
# ─────────────────────────────────────────────────────────────────────────────

STEPS = [

# ── 1. 안민혁 Person 노드 ─────────────────────────────────────────────────────
("""
MERGE (p:Person {id: 'p-006'})
SET   p.name     = '안민혁',
      p.email    = 'minhyuk@workmaite.io',
      p.title    = '기획조정실장',
      p.position = '임원'
RETURN p.name AS created
""", None, "Person: 안민혁"),

# ── 2. 신규 Department 노드 3개 ──────────────────────────────────────────────
("""
MERGE (d:Department {id: 'dept-004'}) SET d.name='기획조정실', d.code='PLAN'
MERGE (d2:Department {id: 'dept-005'}) SET d2.name='디지털혁신팀', d2.code='DX'
MERGE (d3:Department {id: 'dept-006'}) SET d3.name='리스크관리팀', d3.code='RISK'
RETURN 'departments created' AS r
""", None, "Departments: 기획조정실·디지털혁신팀·리스크관리팀"),

# ── 3. 안민혁 → 기획조정실 소속 ─────────────────────────────────────────────
("""
MATCH (p:Person {id:'p-006'}), (d:Department {id:'dept-004'})
MERGE (p)-[:BELONGS_TO]->(d)
RETURN p.name + ' BELONGS_TO ' + d.name AS r
""", None, "안민혁 → 기획조정실 BELONGS_TO"),

# ── 4. 신규 MeetingGroup 3개 ─────────────────────────────────────────────────
("""
MERGE (mg:MeetingGroup {id:'mg-004'})
SET   mg.title        = '경영전략위원회',
      mg.type         = 'quarterly',
      mg.status       = 'active',
      mg.purpose      = '중장기 사업 방향성 수립 및 경영 의사결정',
      mg.meeting_type = 'committee'

MERGE (mg2:MeetingGroup {id:'mg-005'})
SET   mg2.title        = '디지털혁신 태스크포스',
      mg2.type         = 'recurring',
      mg2.status       = 'active',
      mg2.purpose      = '디지털 전환 과제 발굴 및 추진 로드맵 관리',
      mg2.meeting_type = 'taskforce'

MERGE (mg3:MeetingGroup {id:'mg-006'})
SET   mg3.title        = '리스크관리위원회',
      mg3.type         = 'monthly',
      mg3.status       = 'active',
      mg3.purpose      = '운영·재무·법률 리스크 식별 및 대응 체계 점검',
      mg3.meeting_type = 'committee'

RETURN 'meeting groups created' AS r
""", None, "MeetingGroups: mg-004, mg-005, mg-006"),

# ── 5. 안민혁 — 회의체 관계 (ADMIN 2, MEMBER 1) ──────────────────────────────
("""
MATCH (p:Person {id:'p-006'}), (mg4:MeetingGroup {id:'mg-004'}), (mg5:MeetingGroup {id:'mg-005'}), (mg6:MeetingGroup {id:'mg-006'})
MERGE (p)-[:ADMIN_OF]->(mg4)
MERGE (p)-[:ADMIN_OF]->(mg5)
MERGE (p)-[:MEMBER_OF]->(mg6)
RETURN 'memberships created' AS r
""", None, "안민혁 ADMIN_OF mg-004·mg-005, MEMBER_OF mg-006"),

# ── 6. 기존 구성원들을 안민혁 회의체에 연결 ─────────────────────────────────
("""
// 정하은(CTO) → 경영전략위원회·리스크관리위원회 멤버
MATCH (haeun:Person {id:'p-005'}), (mg4:MeetingGroup {id:'mg-004'}), (mg6:MeetingGroup {id:'mg-006'})
MERGE (haeun)-[:MEMBER_OF]->(mg4)
MERGE (haeun)-[:MEMBER_OF]->(mg6)

// 김민준(PM) → 경영전략위원회·디지털혁신TF 멤버
WITH 1 AS dummy
MATCH (minjun:Person {id:'p-001'}), (mg4:MeetingGroup {id:'mg-004'}), (mg5:MeetingGroup {id:'mg-005'})
MERGE (minjun)-[:MEMBER_OF]->(mg4)
MERGE (minjun)-[:MEMBER_OF]->(mg5)

// 이서연·박도현·최유진 → 디지털혁신TF 멤버
WITH 1 AS dummy2
MATCH (seoyeon:Person {id:'p-002'}), (dohyun:Person {id:'p-003'}), (yujin:Person {id:'p-004'}), (mg5:MeetingGroup {id:'mg-005'})
MERGE (seoyeon)-[:MEMBER_OF]->(mg5)
MERGE (dohyun)-[:MEMBER_OF]->(mg5)
MERGE (yujin)-[:MEMBER_OF]->(mg5)

RETURN 'cross memberships done' AS r
""", None, "기존 구성원 → 안민혁 회의체 연결"),

# ── 7. 부서 — 회의체 PARTICIPATES_IN ─────────────────────────────────────────
("""
MATCH (d4:Department {id:'dept-004'}), (d5:Department {id:'dept-005'}), (d6:Department {id:'dept-006'}),
      (mg4:MeetingGroup {id:'mg-004'}), (mg5:MeetingGroup {id:'mg-005'}), (mg6:MeetingGroup {id:'mg-006'})
MERGE (d4)-[:PARTICIPATES_IN]->(mg4)
MERGE (d4)-[:PARTICIPATES_IN]->(mg6)
MERGE (d5)-[:PARTICIPATES_IN]->(mg5)
MERGE (d6)-[:PARTICIPATES_IN]->(mg6)
RETURN 'dept participates done' AS r
""", None, "부서 → 회의체 PARTICIPATES_IN"),

# ── 8. 역할(Role) 노드 ──────────────────────────────────────────────────────
("""
MERGE (r1:Role {id:'role-005'}) SET r1.name='위원장', r1.level='executive'
MERGE (r2:Role {id:'role-006'}) SET r2.name='TF장', r2.level='lead'
MERGE (r3:Role {id:'role-007'}) SET r3.name='위원', r3.level='member'
RETURN 'roles created' AS r
""", None, "Roles: 위원장·TF장·위원"),

# ── 9. 안민혁 역할 부여 ──────────────────────────────────────────────────────
("""
MATCH (p:Person {id:'p-006'}), (r1:Role {id:'role-005'}), (r2:Role {id:'role-006'})
MERGE (p)-[:HAS_ROLE {meeting_group:'mg-004'}]->(r1)
MERGE (p)-[:HAS_ROLE {meeting_group:'mg-005'}]->(r2)
RETURN 'roles assigned' AS r
""", None, "안민혁 역할 부여"),

# ── 10. 아젠다(Agenda) 9개 — 회의체별 3개 ────────────────────────────────────
("""
// ─ mg-004 경영전략위원회 아젠다
MERGE (a1:Agenda {id:'ag-004'})
SET   a1.title='2026 하반기 사업계획 검토', a1.priority='high', a1.status='in_progress', a1.due_date='2026-06-30', a1.description='연간 목표 대비 상반기 달성률 분석 및 하반기 전략 재조정'
MERGE (a2:Agenda {id:'ag-005'})
SET   a2.title='M&A 후보 기업 심층 평가', a2.priority='high', a2.status='pending', a2.due_date='2026-07-15', a2.description='전략적 인수 후보 3개사 재무·기술·문화 적합성 평가'
MERGE (a3:Agenda {id:'ag-006'})
SET   a3.title='ESG 경영 지표 설정', a3.priority='medium', a3.status='completed', a3.due_date='2026-05-01', a3.description='탄소중립 목표 및 사회 책임 지표 KPI 확정'

// ─ mg-005 디지털혁신TF 아젠다
MERGE (a4:Agenda {id:'ag-007'})
SET   a4.title='AI 플랫폼 도입 로드맵', a4.priority='high', a4.status='in_progress', a4.due_date='2026-06-15', a4.description='내부 업무 자동화 및 AI 어시스턴트 전사 배포 계획'
MERGE (a5:Agenda {id:'ag-008'})
SET   a5.title='레거시 시스템 마이그레이션', a5.priority='high', a5.status='in_progress', a5.due_date='2026-08-31', a5.description='온프레미스 ERP → 클라우드 전환 단계별 계획'
MERGE (a6:Agenda {id:'ag-009'})
SET   a6.title='데이터 거버넌스 체계 수립', a6.priority='medium', a6.status='pending', a6.due_date='2026-07-31', a6.description='데이터 오너십 정의, 품질 관리 프로세스 표준화'

// ─ mg-006 리스크관리위원회 아젠다
MERGE (a7:Agenda {id:'ag-010'})
SET   a7.title='사이버보안 취약점 정기 점검', a7.priority='critical', a7.status='in_progress', a7.due_date='2026-05-31', a7.description='외부 침투 테스트 결과 분석 및 조치 계획 수립'
MERGE (a8:Agenda {id:'ag-011'})
SET   a8.title='공급망 리스크 대응 방안', a8.priority='high', a8.status='pending', a8.due_date='2026-06-20', a8.description='핵심 공급업체 집중도 분석 및 대체 공급처 발굴'
MERGE (a9:Agenda {id:'ag-012'})
SET   a9.title='컴플라이언스 교육 이수율 관리', a9.priority='medium', a9.status='completed', a9.due_date='2026-04-30', a9.description='개인정보보호·내부거래 교육 전 임직원 이수 확인'

RETURN 'agendas created' AS r
""", None, "Agendas: ag-004 ~ ag-012 (9개)"),

# ── 11. 아젠다 → 회의체 OWNED_BY ─────────────────────────────────────────────
("""
MATCH (a4:Agenda {id:'ag-004'}), (a5:Agenda {id:'ag-005'}), (a6:Agenda {id:'ag-006'}), (mg4:MeetingGroup {id:'mg-004'})
MERGE (a4)-[:OWNED_BY]->(mg4)
MERGE (a5)-[:OWNED_BY]->(mg4)
MERGE (a6)-[:OWNED_BY]->(mg4)

WITH 1 AS d
MATCH (a7:Agenda {id:'ag-007'}), (a8:Agenda {id:'ag-008'}), (a9:Agenda {id:'ag-009'}), (mg5:MeetingGroup {id:'mg-005'})
MERGE (a7)-[:OWNED_BY]->(mg5)
MERGE (a8)-[:OWNED_BY]->(mg5)
MERGE (a9)-[:OWNED_BY]->(mg5)

WITH 1 AS d2
MATCH (a10:Agenda {id:'ag-010'}), (a11:Agenda {id:'ag-011'}), (a12:Agenda {id:'ag-012'}), (mg6:MeetingGroup {id:'mg-006'})
MERGE (a10)-[:OWNED_BY]->(mg6)
MERGE (a11)-[:OWNED_BY]->(mg6)
MERGE (a12)-[:OWNED_BY]->(mg6)

RETURN 'agenda owned_by done' AS r
""", None, "아젠다 → 회의체 OWNED_BY"),

# ── 12. 아젠다 담당자 ASSIGNED_TO ────────────────────────────────────────────
("""
// 안민혁 담당 아젠다
MATCH (p:Person {id:'p-006'}), (a4:Agenda {id:'ag-004'}), (a5:Agenda {id:'ag-005'})
MERGE (p)-[:ASSIGNED_TO]->(a4)
MERGE (p)-[:ASSIGNED_TO]->(a5)

// 김민준이 하반기 사업계획·AI플랫폼 담당
WITH 1 AS d
MATCH (minjun:Person {id:'p-001'}), (a4:Agenda {id:'ag-004'}), (a7:Agenda {id:'ag-007'})
MERGE (minjun)-[:ASSIGNED_TO]->(a4)
MERGE (minjun)-[:ASSIGNED_TO]->(a7)

// 이서연·박도현이 레거시 마이그레이션·데이터거버넌스 담당
WITH 1 AS d2
MATCH (seoyeon:Person {id:'p-002'}), (dohyun:Person {id:'p-003'}),
      (a8:Agenda {id:'ag-008'}), (a9:Agenda {id:'ag-009'})
MERGE (seoyeon)-[:ASSIGNED_TO]->(a8)
MERGE (dohyun)-[:ASSIGNED_TO]->(a9)

// 정하은(CTO) → 사이버보안 점검 담당
WITH 1 AS d3
MATCH (haeun:Person {id:'p-005'}), (a10:Agenda {id:'ag-010'})
MERGE (haeun)-[:ASSIGNED_TO]->(a10)

RETURN 'assignments done' AS r
""", None, "아젠다 담당자 ASSIGNED_TO"),

# ── 13. 세션(Session) 9개 ────────────────────────────────────────────────────
("""
MERGE (s:Session {id:'s-004'})
SET   s.title='경영전략위원회 2026년 1차', s.session_number=1, s.ended_at='2026-03-10T15:00:00', s.status='completed', s.attendees_count=7

MERGE (s2:Session {id:'s-005'})
SET   s2.title='경영전략위원회 2026년 2차', s2.session_number=2, s2.ended_at='2026-05-08T15:00:00', s2.status='completed', s2.attendees_count=6

MERGE (s3:Session {id:'s-006'})
SET   s3.title='경영전략위원회 2026년 3차', s3.session_number=3, s3.ended_at=null, s3.status='scheduled', s3.attendees_count=0

MERGE (s4:Session {id:'s-007'})
SET   s4.title='디지털혁신TF 킥오프', s4.session_number=1, s4.ended_at='2026-02-20T10:00:00', s4.status='completed', s4.attendees_count=12

MERGE (s5:Session {id:'s-008'})
SET   s5.title='디지털혁신TF 2차 — AI 파일럿 보고', s5.session_number=2, s5.ended_at='2026-04-03T10:00:00', s5.status='completed', s5.attendees_count=10

MERGE (s6:Session {id:'s-009'})
SET   s6.title='디지털혁신TF 3차 — 마이그레이션 중간 점검', s6.session_number=3, s6.ended_at='2026-05-15T10:00:00', s6.status='completed', s6.attendees_count=11

MERGE (s7:Session {id:'s-010'})
SET   s7.title='리스크관리위원회 2026년 3월', s7.session_number=3, s7.ended_at='2026-03-28T14:00:00', s7.status='completed', s7.attendees_count=5

MERGE (s8:Session {id:'s-011'})
SET   s8.title='리스크관리위원회 2026년 4월', s8.session_number=4, s8.ended_at='2026-04-25T14:00:00', s8.status='completed', s8.attendees_count=5

MERGE (s9:Session {id:'s-012'})
SET   s9.title='리스크관리위원회 2026년 5월', s9.session_number=5, s9.ended_at='2026-05-23T14:00:00', s9.status='completed', s9.attendees_count=6

RETURN 'sessions created' AS r
""", None, "Sessions: s-004 ~ s-012 (9개)"),

# ── 14. 세션 → 회의체 HELD_BY ────────────────────────────────────────────────
("""
MATCH (s4:Session  {id:'s-004'}), (s5:Session {id:'s-005'}), (s6:Session {id:'s-006'}), (mg4:MeetingGroup {id:'mg-004'})
MERGE (s4)-[:HELD_BY]->(mg4)
MERGE (s5)-[:HELD_BY]->(mg4)
MERGE (s6)-[:HELD_BY]->(mg4)

WITH 1 AS d
MATCH (s7:Session {id:'s-007'}), (s8:Session {id:'s-008'}), (s9:Session {id:'s-009'}), (mg5:MeetingGroup {id:'mg-005'})
MERGE (s7)-[:HELD_BY]->(mg5)
MERGE (s8)-[:HELD_BY]->(mg5)
MERGE (s9)-[:HELD_BY]->(mg5)

WITH 1 AS d2
MATCH (s10:Session {id:'s-010'}), (s11:Session {id:'s-011'}), (s12:Session {id:'s-012'}), (mg6:MeetingGroup {id:'mg-006'})
MERGE (s10)-[:HELD_BY]->(mg6)
MERGE (s11)-[:HELD_BY]->(mg6)
MERGE (s12)-[:HELD_BY]->(mg6)

RETURN 'session held_by done' AS r
""", None, "세션 → 회의체 HELD_BY"),

# ── 15. 세션 연속성 FOLLOWED_BY ──────────────────────────────────────────────
("""
MATCH (s4:Session {id:'s-004'}), (s5:Session {id:'s-005'})
MERGE (s4)-[:FOLLOWED_BY]->(s5)

WITH 1 AS d
MATCH (s7:Session {id:'s-007'}), (s8:Session {id:'s-008'})
MERGE (s7)-[:FOLLOWED_BY]->(s8)

WITH 1 AS d2
MATCH (s8:Session {id:'s-008'}), (s9:Session {id:'s-009'})
MERGE (s8)-[:FOLLOWED_BY]->(s9)

WITH 1 AS d3
MATCH (s10:Session {id:'s-010'}), (s11:Session {id:'s-011'})
MERGE (s10)-[:FOLLOWED_BY]->(s11)

WITH 1 AS d4
MATCH (s11:Session {id:'s-011'}), (s12:Session {id:'s-012'})
MERGE (s11)-[:FOLLOWED_BY]->(s12)

RETURN 'session follow chains done' AS r
""", None, "세션 FOLLOWED_BY 체인"),

# ── 16. 문서(Document) 9개 ───────────────────────────────────────────────────
("""
MERGE (doc1:Document {id:'doc-004'})
SET   doc1.title='2026 하반기 사업계획 검토 보고서', doc1.file_name='2026H2_business_plan_review.pdf', doc1.doc_type='report', doc1.uploaded_at='2026-05-08'

MERGE (doc2:Document {id:'doc-005'})
SET   doc2.title='M&A 후보 평가 분석서', doc2.file_name='ma_candidate_analysis.pdf', doc2.doc_type='analysis', doc2.uploaded_at='2026-05-08'

MERGE (doc3:Document {id:'doc-006'})
SET   doc3.title='ESG KPI 확정안', doc3.file_name='esg_kpi_final.xlsx', doc3.doc_type='minutes', doc3.uploaded_at='2026-04-30'

MERGE (doc4:Document {id:'doc-007'})
SET   doc4.title='AI 플랫폼 파일럿 결과 보고', doc4.file_name='ai_platform_pilot_report.pdf', doc4.doc_type='report', doc4.uploaded_at='2026-04-03'

MERGE (doc5:Document {id:'doc-008'})
SET   doc5.title='클라우드 전환 아키텍처 설계서', doc5.file_name='cloud_migration_architecture.pdf', doc5.doc_type='analysis', doc5.uploaded_at='2026-05-15'

MERGE (doc6:Document {id:'doc-009'})
SET   doc6.title='디지털혁신TF 회의록 (2026-05-15)', doc6.file_name='dx_tf_minutes_20260515.md', doc6.doc_type='minutes', doc6.uploaded_at='2026-05-15'

MERGE (doc7:Document {id:'doc-010'})
SET   doc7.title='사이버보안 침투테스트 결과 요약', doc7.file_name='pentest_summary_2026Q1.pdf', doc7.doc_type='report', doc7.uploaded_at='2026-03-28'

MERGE (doc8:Document {id:'doc-011'})
SET   doc8.title='공급망 집중도 분석 보고서', doc8.file_name='supply_chain_concentration.pdf', doc8.doc_type='analysis', doc8.uploaded_at='2026-04-25'

MERGE (doc9:Document {id:'doc-012'})
SET   doc9.title='컴플라이언스 교육 이수 현황', doc9.file_name='compliance_training_status.xlsx', doc9.doc_type='minutes', doc9.uploaded_at='2026-05-23'

RETURN 'documents created' AS r
""", None, "Documents: doc-004 ~ doc-012 (9개)"),

# ── 17. 세션 → 문서 PRODUCED ─────────────────────────────────────────────────
("""
MATCH (s5:Session {id:'s-005'}), (doc4:Document {id:'doc-004'}), (doc5:Document {id:'doc-005'})
MERGE (s5)-[:PRODUCED]->(doc4)
MERGE (s5)-[:PRODUCED]->(doc5)

WITH 1 AS d
MATCH (s4:Session {id:'s-004'}), (doc6:Document {id:'doc-006'})
MERGE (s4)-[:PRODUCED]->(doc6)

WITH 1 AS d2
MATCH (s8:Session {id:'s-008'}), (doc7:Document {id:'doc-007'})
MATCH (s9:Session {id:'s-009'}), (doc8:Document {id:'doc-008'}), (doc9:Document {id:'doc-009'})
MERGE (s8)-[:PRODUCED]->(doc7)
MERGE (s9)-[:PRODUCED]->(doc8)
MERGE (s9)-[:PRODUCED]->(doc9)

WITH 1 AS d3
MATCH (s10:Session {id:'s-010'}), (doc10:Document {id:'doc-010'})
MATCH (s11:Session {id:'s-011'}), (doc11:Document {id:'doc-011'})
MATCH (s12:Session {id:'s-012'}), (doc12:Document {id:'doc-012'})
MERGE (s10)-[:PRODUCED]->(doc10)
MERGE (s11)-[:PRODUCED]->(doc11)
MERGE (s12)-[:PRODUCED]->(doc12)

RETURN 'produced done' AS r
""", None, "세션 → 문서 PRODUCED"),

# ── 18. 문서 → 회의체 ATTACHED_TO ────────────────────────────────────────────
("""
MATCH (doc4:Document {id:'doc-004'}), (doc5:Document {id:'doc-005'}), (doc6:Document {id:'doc-006'}), (mg4:MeetingGroup {id:'mg-004'})
MERGE (doc4)-[:ATTACHED_TO]->(mg4)
MERGE (doc5)-[:ATTACHED_TO]->(mg4)
MERGE (doc6)-[:ATTACHED_TO]->(mg4)

WITH 1 AS d
MATCH (doc7:Document {id:'doc-007'}), (doc8:Document {id:'doc-008'}), (doc9:Document {id:'doc-009'}), (mg5:MeetingGroup {id:'mg-005'})
MERGE (doc7)-[:ATTACHED_TO]->(mg5)
MERGE (doc8)-[:ATTACHED_TO]->(mg5)
MERGE (doc9)-[:ATTACHED_TO]->(mg5)

WITH 1 AS d2
MATCH (doc10:Document {id:'doc-010'}), (doc11:Document {id:'doc-011'}), (doc12:Document {id:'doc-012'}), (mg6:MeetingGroup {id:'mg-006'})
MERGE (doc10)-[:ATTACHED_TO]->(mg6)
MERGE (doc11)-[:ATTACHED_TO]->(mg6)
MERGE (doc12)-[:ATTACHED_TO]->(mg6)

RETURN 'attached_to done' AS r
""", None, "문서 → 회의체 ATTACHED_TO"),

# ── 19. 의사결정(Decision) 9개 ───────────────────────────────────────────────
("""
MERGE (dec1:Decision {id:'d-004'})
SET   dec1.title='하반기 핵심 사업 3개 집중 투자 확정', dec1.status='approved', dec1.decided_at='2026-05-08', dec1.impact='high'

MERGE (dec2:Decision {id:'d-005'})
SET   dec2.title='A사 M&A 타당성 검토 착수 승인', dec2.status='approved', dec2.decided_at='2026-05-08', dec2.impact='critical'

MERGE (dec3:Decision {id:'d-006'})
SET   dec3.title='ESG KPI 탄소배출 30% 감축 목표 확정', dec3.status='approved', dec3.decided_at='2026-04-30', dec3.impact='medium'

MERGE (dec4:Decision {id:'d-007'})
SET   dec4.title='사내 AI 어시스턴트 전사 파일럿 승인', dec4.status='approved', dec4.decided_at='2026-04-03', dec4.impact='high'

MERGE (dec5:Decision {id:'d-008'})
SET   dec5.title='ERP 클라우드 전환 1단계 예산 확정', dec5.status='approved', dec5.decided_at='2026-05-15', dec5.impact='high'

MERGE (dec6:Decision {id:'d-009'})
SET   dec6.title='데이터 거버넌스 TF 구성 의결', dec6.status='pending', dec6.decided_at=null, dec6.impact='medium'

MERGE (dec7:Decision {id:'d-010'})
SET   dec7.title='외부 침투테스트 업체 교체 결정', dec7.status='approved', dec7.decided_at='2026-03-28', dec7.impact='medium'

MERGE (dec8:Decision {id:'d-011'})
SET   dec8.title='2차 공급업체 긴급 발굴 예산 승인', dec8.status='approved', dec8.decided_at='2026-04-25', dec8.impact='high'

MERGE (dec9:Decision {id:'d-012'})
SET   dec9.title='컴플라이언스 미이수자 징계 절차 개시', dec9.status='approved', dec9.decided_at='2026-05-23', dec9.impact='medium'

RETURN 'decisions created' AS r
""", None, "Decisions: d-004 ~ d-012 (9개)"),

# ── 20. 의사결정 관계 MADE_BY·APPROVED_BY·CAUSED_BY ─────────────────────────
("""
// 경영전략위원회 결정 → 세션에서 산출
MATCH (dec1:Decision {id:'d-004'}), (dec2:Decision {id:'d-005'}), (s5:Session {id:'s-005'})
MERGE (dec1)-[:MADE_BY]->(s5)
MERGE (dec2)-[:MADE_BY]->(s5)

WITH 1 AS d
MATCH (dec3:Decision {id:'d-006'}), (s4:Session {id:'s-004'})
MERGE (dec3)-[:MADE_BY]->(s4)

// 디지털혁신TF 결정
WITH 1 AS d2
MATCH (dec4:Decision {id:'d-007'}), (s8:Session {id:'s-008'})
MATCH (dec5:Decision {id:'d-008'}), (s9:Session {id:'s-009'})
MERGE (dec4)-[:MADE_BY]->(s8)
MERGE (dec5)-[:MADE_BY]->(s9)

// 리스크관리위원회 결정
WITH 1 AS d3
MATCH (dec7:Decision {id:'d-010'}), (s10:Session {id:'s-010'})
MATCH (dec8:Decision {id:'d-011'}), (s11:Session {id:'s-011'})
MATCH (dec9:Decision {id:'d-012'}), (s12:Session {id:'s-012'})
MERGE (dec7)-[:MADE_BY]->(s10)
MERGE (dec8)-[:MADE_BY]->(s11)
MERGE (dec9)-[:MADE_BY]->(s12)

RETURN 'decision made_by done' AS r
""", None, "의사결정 MADE_BY 세션"),

# ── 21. 안민혁이 결정 승인 APPROVED_BY ──────────────────────────────────────
("""
MATCH (p:Person {id:'p-006'}),
      (dec1:Decision {id:'d-004'}), (dec2:Decision {id:'d-005'}),
      (dec4:Decision {id:'d-007'}), (dec5:Decision {id:'d-008'}),
      (dec7:Decision {id:'d-010'}), (dec8:Decision {id:'d-011'})
MERGE (dec1)-[:APPROVED_BY]->(p)
MERGE (dec2)-[:APPROVED_BY]->(p)
MERGE (dec4)-[:APPROVED_BY]->(p)
MERGE (dec5)-[:APPROVED_BY]->(p)
MERGE (dec7)-[:APPROVED_BY]->(p)
MERGE (dec8)-[:APPROVED_BY]->(p)

RETURN 'approved_by done' AS r
""", None, "의사결정 APPROVED_BY 안민혁"),

# ── 22. 의사결정 → 아젠다 CAUSED_BY ─────────────────────────────────────────
("""
MATCH (dec1:Decision {id:'d-004'}), (a4:Agenda {id:'ag-004'})
MERGE (dec1)-[:CAUSED_BY]->(a4)

WITH 1 AS d
MATCH (dec2:Decision {id:'d-005'}), (a5:Agenda {id:'ag-005'})
MERGE (dec2)-[:CAUSED_BY]->(a5)

WITH 1 AS d2
MATCH (dec4:Decision {id:'d-007'}), (a7:Agenda {id:'ag-007'})
MATCH (dec5:Decision {id:'d-008'}), (a8:Agenda {id:'ag-008'})
MERGE (dec4)-[:CAUSED_BY]->(a7)
MERGE (dec5)-[:CAUSED_BY]->(a8)

WITH 1 AS d3
MATCH (dec7:Decision {id:'d-010'}), (a10:Agenda {id:'ag-010'})
MATCH (dec8:Decision {id:'d-011'}), (a11:Agenda {id:'ag-011'})
MERGE (dec7)-[:CAUSED_BY]->(a10)
MERGE (dec8)-[:CAUSED_BY]->(a11)

RETURN 'caused_by done' AS r
""", None, "의사결정 → 아젠다 CAUSED_BY"),

# ── 23. 최종 집계 ────────────────────────────────────────────────────────────
("""
MATCH (p:Person {id:'p-006'})
OPTIONAL MATCH (p)-[r1:ADMIN_OF]->(mg_admin)
OPTIONAL MATCH (p)-[r2:MEMBER_OF]->(mg_member)
OPTIONAL MATCH (p)-[r3:ASSIGNED_TO]->(a)
OPTIONAL MATCH (p)-[r4:APPROVED_BY]-(dec)
RETURN p.name AS name,
       count(DISTINCT mg_admin) AS admin_groups,
       count(DISTINCT mg_member) AS member_groups,
       count(DISTINCT a) AS assigned_agendas,
       count(DISTINCT dec) AS approved_decisions
""", None, "안민혁 최종 집계"),
]


async def main():
    print(f"\n{'='*60}")
    print(f"  Neo4j 더미데이터 시딩 — 안민혁(p-006)")
    print(f"{'='*60}\n")

    for i, (cypher, params, label) in enumerate(STEPS, 1):
        print(f"[{i:02d}/{len(STEPS)}] {label} ...", end=" ")
        rows = await run(cypher, params)
        if rows:
            print(f"OK → {rows[0]}")
        else:
            print("OK")

    print(f"\n{'='*60}")
    print("  완료!")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    asyncio.run(main())
