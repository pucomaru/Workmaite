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
                      "fulltext": {"index": "agendaFulltext", "props": ["title"]},
                      "fields": "node.title AS title, node.status AS status, node.department AS department"},
    # Minutes는 구형 노드에 meeting_id 프로퍼티가 없어(2-hop 관계만 존재) 결합 스코프 사용
    "Minutes":       {"index": "minutesEmbedding",       "legacy": ["minutes_embedding_index"],
                      "scope": "custom",
                      "scope_cypher": ("WHERE node.meeting_id IN $mids "
                                       "OR EXISTS { MATCH (node)-[:기록]->(:Session)--(mg:Meetings) "
                                       "WHERE mg.pg_id IN $mids } "),
                      "fulltext": {"index": "minutesFulltext", "props": ["title", "content_summary"]},
                      "fields": "node.title AS title, node.content_summary AS summary, node.content AS content"},
    "MinutesChunk":  {"index": "minutesChunkEmbedding",  "legacy": [], "scope": None,
                      "fields": "node.text AS content"},
    "Report":        {"index": "reportEmbedding",        "legacy": [], "scope": "prop",
                      "fulltext": {"index": "reportFulltext", "props": ["file_name"]},
                      "fields": "node.file_name AS title, node.human_status AS status"},
    "ReportChunk":   {"index": "reportChunkEmbedding",   "legacy": [], "scope": None,
                      "fulltext": {"index": "reportChunkFulltext", "props": ["text", "title"]},
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


async def ensure_fulltext_indexes() -> None:
    """풀텍스트 인덱스 생성 (P3B-6 2단계, 시작 시 1회) — 제목·고유명사 검색 보강."""
    from neo4j_client import run_cypher

    for label, e in REGISTRY.items():
        ft = e.get("fulltext") if "alias" not in e else None
        if not ft:
            continue
        props = ", ".join(f"n.{p}" for p in ft["props"])
        try:
            await run_cypher(
                f"CREATE FULLTEXT INDEX {ft['index']} IF NOT EXISTS "
                f"FOR (n:{label}) ON EACH [{props}]"
            )
        except Exception as ex:
            logger.warning(f"[Retrieval] 풀텍스트 인덱스 {ft['index']} 생성 실패 (무시): {ex}")


def _rrf(rank: int, k: int = 60) -> float:
    return 1.0 / (k + rank)


async def hybrid_search(
    label: str,
    query: str,
    k: int = 5,
    meeting_ids: list[int] | None = None,
) -> list[dict]:
    """벡터 + 풀텍스트 RRF 결합 검색 (P3B-6 2단계).

    벡터는 의미 유사, 풀텍스트는 제목·고유명사 정확 일치에 강하다.
    풀텍스트 미정의 라벨이면 벡터 단독으로 동작한다. 결과 행에 rrf 점수 포함.
    """
    from neo4j_client import run_cypher

    real_label, entry = _resolve(label)
    vec_rows = await vector_search(label, query, k=max(k * 2, 10), meeting_ids=meeting_ids)

    ft = entry.get("fulltext")
    ft_rows: list[dict] = []
    if ft and query.strip():
        # Lucene 특수문자 이스케이프 후 OR 검색
        import re as _re
        safe = _re.sub(r'[+\-&|!(){}\[\]^"~*?:\\/]', " ", query)[:100].strip()
        if safe:
            try:
                ft_rows = await run_cypher(
                    f"CALL db.index.fulltext.queryNodes('{ft['index']}', $q) "
                    f"YIELD node, score "
                    f"RETURN {entry['fields']}, score LIMIT $k2",
                    {"q": safe, "k2": max(k * 2, 10)},
                )
            except Exception as ex:
                logger.warning(f"[Retrieval] 풀텍스트 검색 실패 (벡터 단독 진행): {ex}")

    # RRF 결합 — title+content 기준으로 동일 문서 판별
    def _key(r: dict) -> str:
        return f"{r.get('title')}|{str(r.get('content') or r.get('summary') or '')[:80]}"

    scores: dict[str, float] = {}
    docs: dict[str, dict] = {}
    for rank, r in enumerate(vec_rows):
        kkey = _key(r)
        scores[kkey] = scores.get(kkey, 0.0) + _rrf(rank)
        docs.setdefault(kkey, r)
    for rank, r in enumerate(ft_rows):
        kkey = _key(r)
        scores[kkey] = scores.get(kkey, 0.0) + _rrf(rank)
        docs.setdefault(kkey, r)

    merged = sorted(scores.items(), key=lambda x: -x[1])[:k]
    out = []
    for kkey, s in merged:
        row = dict(docs[kkey])
        row["rrf"] = round(s, 5)
        out.append(row)
    if not out:
        RETRIEVAL_ZERO_RESULTS.labels(real_label).inc()
    return out


async def graph_expanded_search(
    query: str,
    meeting_ids: list[int] | None = None,
    k: int = 3,
) -> list[dict]:
    """시드 벡터 검색 → 1-hop 그래프 확장 → 경로 근거 반환 (P3B-7, G-2).

    아젠다를 시드로 찾고 연결된 세션·보고서·판단으로 확장해, 답변이 인용할 수 있는
    "아젠다 → 세션/보고서" 경로를 함께 돌려준다.
    """
    from neo4j_client import run_cypher

    seeds = await vector_search("Agenda", query, k=k, meeting_ids=meeting_ids)
    out: list[dict] = []
    for s in seeds:
        title = s.get("title")
        if not title:
            continue
        try:
            paths = await run_cypher(
                "MATCH (ag:Agenda {title: $title}) "
                "OPTIONAL MATCH (ag)--(s:Session) "
                "OPTIONAL MATCH (ag)<-[:첨부|관할]-(r:Report) "
                "RETURN ag.title AS agenda, ag.status AS status, "
                "collect(DISTINCT s.title)[..3] AS sessions, "
                "collect(DISTINCT r.file_name)[..3] AS reports LIMIT 1",
                {"title": title},
            )
            if paths:
                row = paths[0]
                parts = [f"아젠다 '{row['agenda']}' ({row.get('status') or '?'})"]
                if row.get("sessions"):
                    parts.append("세션: " + ", ".join(filter(None, row["sessions"])))
                if row.get("reports"):
                    parts.append("보고서: " + ", ".join(filter(None, row["reports"])))
                out.append({"title": title, "path": " → ".join(parts), "score": s.get("score")})
        except Exception as e:
            logger.warning(f"[Retrieval] 그래프 확장 실패({title}): {e}")
            out.append({"title": title, "path": f"아젠다 '{title}'", "score": s.get("score")})
    return out
