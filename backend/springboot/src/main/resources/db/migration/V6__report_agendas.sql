-- P2-8: 보고서-아젠다 연결 정규화 (UX-3/5의 근본 해결 기반)
-- reports.related_agenda_ids JSONB(["agenda-174", ...])를 조인 테이블로 정규화.
-- 과도기에는 dual-write(FastAPI upload.py) — 읽기 경로 전환 완료 후 JSONB 컬럼 DROP 예정.
CREATE TABLE IF NOT EXISTS report_agendas (
    report_id BIGINT NOT NULL REFERENCES reports(id) ON DELETE CASCADE,
    agenda_id BIGINT NOT NULL REFERENCES agenda(id)  ON DELETE CASCADE,
    PRIMARY KEY (report_id, agenda_id)
);
CREATE INDEX IF NOT EXISTS idx_report_agendas_agenda ON report_agendas(agenda_id);

-- 기존 데이터 백필: 'agenda-N' 형식에서 N 추출, 삭제된 아젠다는 제외(FK 보호)
INSERT INTO report_agendas (report_id, agenda_id)
SELECT DISTINCT r.id, a.id
FROM reports r
CROSS JOIN LATERAL jsonb_array_elements_text(r.related_agenda_ids) AS v
JOIN agenda a ON a.id = NULLIF((regexp_match(v, '\d+$'))[1], '')::bigint
WHERE r.related_agenda_ids IS NOT NULL
ON CONFLICT DO NOTHING;
