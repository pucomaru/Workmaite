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

// Role
CREATE CONSTRAINT role_id IF NOT EXISTS
  FOR (n:Role) REQUIRE n.id IS UNIQUE;

// MeetingGroup
CREATE CONSTRAINT meetinggroup_id IF NOT EXISTS
  FOR (n:MeetingGroup) REQUIRE n.id IS UNIQUE;

// Agenda
CREATE CONSTRAINT agenda_id IF NOT EXISTS
  FOR (n:Agenda) REQUIRE n.id IS UNIQUE;

// Document
CREATE CONSTRAINT document_id IF NOT EXISTS
  FOR (n:Document) REQUIRE n.id IS UNIQUE;


// ── Context Graph ─────────────────────────────────────────────

// Session
CREATE CONSTRAINT session_id IF NOT EXISTS
  FOR (n:Session) REQUIRE n.id IS UNIQUE;

// AIJudgment
CREATE CONSTRAINT aijudgment_id IF NOT EXISTS
  FOR (n:AIJudgment) REQUIRE n.id IS UNIQUE;

// HumanJudgment
CREATE CONSTRAINT humanjudgment_id IF NOT EXISTS
  FOR (n:HumanJudgment) REQUIRE n.id IS UNIQUE;


// ── Indexes (lookup performance) ──────────────────────────────

CREATE INDEX person_name           IF NOT EXISTS FOR (n:Person)         ON (n.name);
CREATE INDEX person_status         IF NOT EXISTS FOR (n:Person)         ON (n.status);
CREATE INDEX department_name       IF NOT EXISTS FOR (n:Department)     ON (n.name);
CREATE INDEX organization_name     IF NOT EXISTS FOR (n:Organization)   ON (n.name);
CREATE INDEX meetinggroup_title    IF NOT EXISTS FOR (n:MeetingGroup)   ON (n.title);
CREATE INDEX session_date          IF NOT EXISTS FOR (n:Session)        ON (n.date);
CREATE INDEX session_status        IF NOT EXISTS FOR (n:Session)        ON (n.status);
CREATE INDEX agenda_status         IF NOT EXISTS FOR (n:Agenda)         ON (n.status);
CREATE INDEX agenda_priority       IF NOT EXISTS FOR (n:Agenda)         ON (n.priority);
CREATE INDEX agenda_due_date       IF NOT EXISTS FOR (n:Agenda)         ON (n.due_date);
CREATE INDEX document_doc_type     IF NOT EXISTS FOR (n:Document)       ON (n.doc_type);
CREATE INDEX aijudgment_created    IF NOT EXISTS FOR (n:AIJudgment)     ON (n.created_at);
CREATE INDEX humanjudgment_judged  IF NOT EXISTS FOR (n:HumanJudgment)  ON (n.judged_at);
