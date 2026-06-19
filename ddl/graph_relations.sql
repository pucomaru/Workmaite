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