// P2-5: Neo4j 유니크 제약 (Plan.md §4.3)
// 런타임에는 backend/ai/neo4j_sync.py:ensure_constraints()가 시작 시 동일 내용을 보장한다.
// 이 파일은 수동 적용/문서화용 사본.
CREATE CONSTRAINT user_pg_id    IF NOT EXISTS FOR (u:User)          REQUIRE u.pg_id IS UNIQUE;
CREATE CONSTRAINT meetings_id   IF NOT EXISTS FOR (m:Meetings)      REQUIRE m.id    IS UNIQUE;
CREATE CONSTRAINT session_id    IF NOT EXISTS FOR (s:Session)       REQUIRE s.id    IS UNIQUE;
CREATE CONSTRAINT agenda_id     IF NOT EXISTS FOR (a:Agenda)        REQUIRE a.id    IS UNIQUE;
CREATE CONSTRAINT minutes_id    IF NOT EXISTS FOR (m:Minutes)       REQUIRE m.id    IS UNIQUE;
CREATE CONSTRAINT report_id     IF NOT EXISTS FOR (r:Report)        REQUIRE r.id    IS UNIQUE;
CREATE CONSTRAINT hj_id         IF NOT EXISTS FOR (h:HumanJudgment) REQUIRE h.id    IS UNIQUE;
CREATE CONSTRAINT dept_name     IF NOT EXISTS FOR (d:Department)    REQUIRE d.name  IS UNIQUE;
CREATE CONSTRAINT company_name  IF NOT EXISTS FOR (c:Company)       REQUIRE c.name  IS UNIQUE;
// 적용 전 중복 점검 예: MATCH (n:Agenda) WITH n.id AS id, count(*) AS c WHERE c > 1 RETURN id, c;
