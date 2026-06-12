"""검색 레지스트리 (P3B-6, G-1·G-3·HC-3).

라벨→벡터 인덱스명→반환 필드→스코프 경로가 3곳(neo4j_sync._VECTOR_INDEXES,
knowledge_manager.index_map, minutes_generator 폴백 튜플)에 중복 정의되어 있던 것을
단일 소스로 통합한다. 인덱스명 불일치는 "조용한 검색 0건"(G-1 장애)으로 나타나므로,
0건 발생을 Prometheus 카운터로 상시 집계한다.
"""
import logging

from prometheus_client import Counter

logger = logging.getLogger(__name__)

RETRIEVAL_ZERO_RESULTS = Counter(
    "workmaite_retrieval_zero_results_total",
    "벡터 검색 0건 발생 (G-1 전면 장애 탐지용)",
    ["label"],
)

# label → 인덱스명/레거시명/반환 필드/meeting 스코프 방식
# scope: "prop"  = node.meeting_id 프로퍼티 필터
#        "rel"   = (node)--(:Meetings) 관계로 mg.pg_id 필터
#        None    = 스코프 미지원 (청크 등 — 호출측에서 별도 처리)
REGISTRY: dict[str, dict] = {
    "Meetings":      {"index": "meetingsEmbedding",      "legacy": [], "scope": None,
                      "fields": "node.title AS title, node.description AS content"},
    "Session":       {"index": "sessionEmbedding",       "legacy": [], "scope": "rel",
                      "fields": "node.title AS title, node.description AS content"},
    "Agenda":        {"index": "agendaEmbedding",        "legacy": [], "scope": "rel",
                      "fields": "node.title AS title, node.status AS status, node.department AS department"},
    # Minutes는 구형 노드에 meeting_id 프로퍼티가 없어(2-hop 관계만 존재) 결합 스코프 사용
    "Minutes":       {"index": "minutesEmbedding",       "legacy": ["minutes_embedding_index"],
                      "scope": "custom",
                      "scope_cypher": ("WHERE node.meeting_id IN $mids "
                                       "OR EXISTS { MATCH (node)-[:기록]->(:Session)--(mg:Meetings) "
                                       "WHERE mg.pg_id IN $mids } "),
                      "fields": "node.title AS title, node.content_summary AS summary, node.content AS content"},
    "MinutesChunk":  {"index": "minutesChunkEmbedding",  "legacy": [], "scope": None,
                      "fields": "node.text AS content"},
    "Report":        {"index": "reportEmbedding",        "legacy": [], "scope": "prop",
                      "fields": "node.file_name AS title, node.human_status AS status"},
    "ReportChunk":   {"index": "reportChunkEmbedding",   "legacy": [], "scope": None,
                      "fields": "node.text AS content, node.title AS title"},
    "HumanJudgment": {"index": "humanJudgmentEmbedding", "legacy": [], "scope": None,
                      "fields": "node.judgment AS title, node.reason AS content"},
    # 업로드 지식 문서는 ReportChunk 라벨로 저장됨 (별칭)
    "KnowledgeChunk": {"alias": "ReportChunk"},
}


def _resolve(label: str) -> tuple[str, dict]:
    entry = REGISTRY.get(label)
    if entry is None:
        raise KeyError(f"등록되지 않은 검색 라벨: {label} — retrieval_registry.REGISTRY에 추가 필요")
    if "alias" in entry:
        return entry["alias"], REGISTRY[entry["alias"]]
    return label, entry


def index_for(label: str) -> str:
    """라벨의 벡터 인덱스명 (단일 소스 — 하드코딩 금지)."""
    return _resolve(label)[1]["index"]


def index_names_for_creation() -> list[tuple[str, str, str]]:
    """init_vector_index용 (label, index_name, property) 목록."""
    return [(label, e["index"], "embedding")
            for label, e in REGISTRY.items() if "alias" not in e]


async def vector_search(
    label: str,
    query: str,
    k: int = 5,
    meeting_ids: list[int] | None = None,
) -> list[dict]:
    """스코프드 벡터 검색 — 모든 검색 도구의 기본 진입점 (P3B-6).

    meeting_ids를 주면 해당 회의체 데이터만 반환한다(스코프 미지원 라벨은 무시·경고).
    0건이면 메트릭 집계 + warning (G-1 재발 탐지).
    """
    from file_embedder import embed_query
    from neo4j_client import run_cypher

    real_label, entry = _resolve(label)
    emb = await embed_query(query[:500])

    # queryNodes는 전역 top-N을 먼저 뽑으므로, 스코프 필터가 있으면 오버페치 후 잘라야
    # 해당 회의체 문서가 상위권 밖이어도 누락되지 않는다 (post-filter 함정)
    fetch_k = max(k * 10, 50) if meeting_ids is not None else k
    scope_clause = ""
    params: dict = {"k": k, "fetch_k": fetch_k, "embedding": emb}
    if meeting_ids is not None:
        if entry["scope"] == "prop":
            scope_clause = "WHERE node.meeting_id IN $mids "
            params["mids"] = list(meeting_ids)
        elif entry["scope"] == "rel":
            scope_clause = "MATCH (node)--(mg:Meetings) WHERE mg.pg_id IN $mids "
            params["mids"] = list(meeting_ids)
        elif entry["scope"] == "custom":
            scope_clause = entry["scope_cypher"]
            params["mids"] = list(meeting_ids)
        else:
            logger.warning(f"[Retrieval] {real_label}는 meeting 스코프 미지원 — 전체 검색")

    rows: list[dict] = []
    last_err: Exception | None = None
    for idx in [entry["index"], *entry.get("legacy", [])]:
        try:
            rows = await run_cypher(
                f"CALL db.index.vector.queryNodes('{idx}', $fetch_k, $embedding) "
                f"YIELD node, score "
                f"{scope_clause}"
                f"RETURN {entry['fields']}, score ORDER BY score DESC LIMIT $k",
                params,
            )
            last_err = None
            break
        except Exception as e:
            last_err = e
    if last_err:
        logger.error(f"[Retrieval] {real_label} 검색 실패: {last_err}")
        raise last_err
    if not rows:
        RETRIEVAL_ZERO_RESULTS.labels(real_label).inc()
        logger.warning(f"[Retrieval] {real_label} 검색 0건 (query={query[:40]!r})")
    return rows
