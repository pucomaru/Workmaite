-- graph_relations: 그래프에서 사용자가 수동 생성한 자유 관계 (구조 FK 외).
-- 소스 오브 트루스 = PostgreSQL. Neo4j에는 FastAPI가 동기화(MERGE)한다.
-- node id는 그래프 노드 id 문자열(예: mg-001, agenda-12, p-3).
-- 적용:  psql "$DATABASE_URL" -f ddl/graph_relations.sql

CREATE TABLE IF NOT EXISTS graph_relations (
  id           BIGSERIAL PRIMARY KEY,
  from_node_id TEXT   NOT NULL,
  rel_type     TEXT   NOT NULL,
  to_node_id   TEXT   NOT NULL,
  created_by   BIGINT REFERENCES users(id),
  created_at   TIMESTAMP NOT NULL DEFAULT now(),
  CONSTRAINT uq_graph_relations UNIQUE (from_node_id, rel_type, to_node_id)
);

CREATE INDEX IF NOT EXISTS idx_graph_relations_from ON graph_relations (from_node_id);
CREATE INDEX IF NOT EXISTS idx_graph_relations_to   ON graph_relations (to_node_id);
