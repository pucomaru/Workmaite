// =============================================================
// init.cypher  —  Schema Constraints & Indexes
// Knowledge Graph (정적) + Context Graph (동적)
// =============================================================

// ── Knowledge Graph ──────────────────────────────────────────

// Organization
CREATE CONSTRAINT organization_id IF NOT EXISTS
  FOR (n:Organization) REQUIRE n.id IS UNIQUE;

// Department
CREATE CONSTRAINT department_id IF NOT EXISTS
  FOR (n:Department) REQUIRE n.id IS UNIQUE;

// Person
CREATE CONSTRAINT person_id IF NOT EXISTS
  FOR (n:Person) REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT person_email IF NOT EXISTS
  FOR (n:Person) REQUIRE n.email IS UNIQUE;

// MeetingGroup
CREATE CONSTRAINT meetinggroup_id IF NOT EXISTS
  FOR (n:MeetingGroup) REQUIRE n.id IS UNIQUE;

// Role
CREATE CONSTRAINT role_id IF NOT EXISTS
  FOR (n:Role) REQUIRE n.id IS UNIQUE;

// Document
CREATE CONSTRAINT document_id IF NOT EXISTS
  FOR (n:Document) REQUIRE n.id IS UNIQUE;

// Agenda
CREATE CONSTRAINT agenda_id IF NOT EXISTS
  FOR (n:Agenda) REQUIRE n.id IS UNIQUE;


// ── Context Graph ─────────────────────────────────────────────

// Session
CREATE CONSTRAINT session_id IF NOT EXISTS
  FOR (n:Session) REQUIRE n.id IS UNIQUE;

// Decision
CREATE CONSTRAINT decision_id IF NOT EXISTS
  FOR (n:Decision) REQUIRE n.id IS UNIQUE;

// AIJudgment
CREATE CONSTRAINT aijudgment_id IF NOT EXISTS
  FOR (n:AIJudgment) REQUIRE n.id IS UNIQUE;

// ── Indexes (lookup performance) ──────────────────────────────

CREATE INDEX person_name        IF NOT EXISTS FOR (n:Person)       ON (n.name);
CREATE INDEX department_name    IF NOT EXISTS FOR (n:Department)   ON (n.name);
CREATE INDEX session_date       IF NOT EXISTS FOR (n:Session)      ON (n.date);
CREATE INDEX session_status     IF NOT EXISTS FOR (n:Session)      ON (n.status);
CREATE INDEX agenda_status      IF NOT EXISTS FOR (n:Agenda)       ON (n.status);
CREATE INDEX decision_made_at   IF NOT EXISTS FOR (n:Decision)     ON (n.made_at);
CREATE INDEX aijudgment_created IF NOT EXISTS FOR (n:AIJudgment)   ON (n.created_at);
