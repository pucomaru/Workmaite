"""neo4j-graphrag 기반 자연어→Cypher 그래프 질의 (추가 기능).

기존 async 검색층(retrieval_registry: 벡터/하이브리드/그래프확장)은 그대로 두고, 고정 쿼리·
벡터검색이 못 다루는 **임의 구조/집계 질문**("부서별 미완료 안건 수", "협의 관계 회의체들의 간사"
등)을 LLM이 Cypher로 생성해 답하도록 보강한다.

안전장치
- 읽기전용: Text2CypherRetriever가 생성 Cypher를 EXPLAIN해 read-only가 아니면 실행을 거부한다
  (neo4j-graphrag 1.17 내장). CREATE/MERGE/SET/DELETE 등은 애초에 실행되지 않는다.
- 테넌트 스코프: 비관리자는 접근 가능한 회의체 pg_id로 한정하도록 스키마/프롬프트에 강제 주입한다.
  ⚠️ 벡터 도구의 '하드 필터(Cypher 파라미터)'와 달리, 여기는 LLM 생성 쿼리라 **강한 권고** 수준이다.
  하드 보장이 필요하면 graph_query 도구를 관리자 전용으로 게이팅할 것(tools/meeting_tools.py).
- sync 제약: neo4j-graphrag 리트리버는 동기 드라이버 전용 → 별도 동기 드라이버 풀 + asyncio.to_thread로
  이벤트 루프를 막지 않는다(기존 async Bolt 클라이언트 graphdb.neo4j_client 와 별개 풀).
"""

import asyncio
import logging
import os
import threading

import neo4j
from neo4j import GraphDatabase
from neo4j_graphrag.llm import LLMInterface, LLMResponse
from neo4j_graphrag.retrievers import Text2CypherRetriever

from graphdb.rel_schema import ALLOWED_REL_TYPES

logger = logging.getLogger(__name__)


class _ReadOnlyText2Cypher(Text2CypherRetriever):
    # 생성 시 DB 버전 확인(왕복)을 생략 — 운영 Neo4j 5.x 고정이고, read-only 강제는 search()에 내장.
    # 덕분에 요청별(스코프별) 스키마로 매번 가볍게 생성할 수 있다(DB 접속은 search 시점에만).
    VERIFY_NEO4J_VERSION = False


class _FactoryLLM(LLMInterface):
    """neo4j-graphrag LLMInterface 어댑터 — OpenAILLM 대신 기존 llm_factory에 위임한다.

    이로써 두 가지가 기존 인프라로 자동 해결된다:
    - 모델 선택: llm_factory가 model_override_var(사용자 model-select-btn 선택)를 읽는다.
      → workflow 내 다른 LLM과 동일하게 사용자가 고른 모델로 Cypher를 생성한다.
    - 토큰 과금: ChatOpenAI 호출은 전역 콜백 훅(llm.agent_logging.TokenUsageCollector,
      register_configure_hook로 등록)에 on_llm_end로 자동 집계된다. 수동 record_token_usage 불필요.
    asyncio.to_thread가 contextvar(model_override_var·_token_collector_var)를 워커 스레드로
    복사하므로, Text2Cypher가 스레드에서 invoke해도 두 메커니즘이 그대로 유효하다.
    """

    def __init__(self, profile: str = "routing") -> None:
        # 결정적 Cypher 생성을 위해 temperature=0·non-streaming 프로파일(routing) 사용.
        super().__init__(model_name=f"factory:{profile}")
        self._profile = profile

    def _messages(self, text: str, system_instruction):
        from langchain_core.messages import HumanMessage, SystemMessage

        msgs = []
        if system_instruction:
            msgs.append(SystemMessage(content=system_instruction))
        msgs.append(HumanMessage(content=text))
        return msgs

    @staticmethod
    def _as_text(content) -> str:
        return content if isinstance(content, str) else str(content)

    def invoke(
        self, input, message_history=None, system_instruction=None
    ) -> LLMResponse:
        from llm.llm_factory import llm_factory

        resp = llm_factory(self._profile, streaming=False).invoke(
            self._messages(input, system_instruction)
        )
        return LLMResponse(content=self._as_text(resp.content))

    async def ainvoke(
        self, input, message_history=None, system_instruction=None
    ) -> LLMResponse:
        from llm.llm_factory import llm_factory

        resp = await llm_factory(self._profile, streaming=False).ainvoke(
            self._messages(input, system_instruction)
        )
        return LLMResponse(content=self._as_text(resp.content))


_sync_driver: neo4j.Driver | None = None
_llm: LLMInterface | None = None
_lock = threading.Lock()


def _get_sync_driver() -> neo4j.Driver:
    """neo4j-graphrag 전용 동기 드라이버(소형 풀). 기존 async 드라이버와 별개."""
    global _sync_driver
    if _sync_driver is None:
        with _lock:
            if _sync_driver is None:
                # Bolt URI 정규화/자격증명은 기존 async 클라이언트와 동일 소스 재사용
                from graphdb.neo4j_client import (
                    _bolt_uri,
                    NEO4J_USER,
                    NEO4J_PASSWORD,
                )

                _sync_driver = GraphDatabase.driver(
                    _bolt_uri(),
                    auth=(NEO4J_USER, NEO4J_PASSWORD),
                    max_connection_pool_size=5,
                )
    return _sync_driver


def _get_llm() -> LLMInterface:
    """Cypher 생성용 LLM 어댑터(싱글톤). 모델·토큰은 invoke 시점에 llm_factory가 동적 해석한다."""
    global _llm
    if _llm is None:
        with _lock:
            if _llm is None:
                _llm = _FactoryLLM(profile="routing")
    return _llm


def close_sync_driver() -> None:
    """앱 종료 시 동기 드라이버 풀 종료 (lifespan에서 호출)."""
    global _sync_driver
    if _sync_driver is not None:
        try:
            _sync_driver.close()
        except Exception:
            pass
        _sync_driver = None


# ─── 스키마(프롬프트 주입) ────────────────────────────────────────────────────
# 실제 Neo4j 라벨/프로퍼티는 graphdb/neo4j_client.py·file_embedder.py의 Cypher에서 확인된 것을,
# 관계 어휘는 graphdb/rel_schema.py(SSOT)를 따른다.
_NODE_SCHEMA = """노드 라벨과 주요 프로퍼티:
- (:Meetings) 회의체   : id('mg-<pg_id>' 형식), pg_id(정수), title, description, status, meeting_type
- (:Session)  회의(세션): pg_id, title, scheduled_at, status, meeting_id(정수)
- (:Agenda)   안건/아젠다: title, status, department, meeting_id(정수)
- (:Minutes)  회의록    : pg_id, title, content_summary, meeting_id(정수)
- (:Report)   보고자료  : file_name, human_status, meeting_id(정수)
- (:User)     사용자    : id, pg_id, name, department, company
- (:Company)  회사/조직 : name"""

_REL_PATTERNS = """관계 패턴 (관계 타입은 전부 한글 — Cypher에서 반드시 백틱으로 감쌀 것. 예: -[:`관할`]->):
- (:Agenda)-[:`관할`]->(:Meetings)     안건이 속한 회의체
- (:User)-[:`참여`]->(:Meetings)       참여자
- (:User)-[:`운영`]->(:Meetings)       간사/운영자
- (:User)-[:`담당`]->(:Agenda)         안건 담당자
- (:Agenda)-[:`논의`]->(:Session)      안건이 논의된 회의
- (:Session)-[:`소속`]->(:Meetings)    회의가 속한 회의체
- (:Session)-[:`기록`]->(:Minutes)     회의의 회의록
- (:Minutes)-[:`도출`]->(:Agenda)      회의록에서 도출된 안건
- (:Report)-[:`발제`]->(:Meetings)     보고자료-회의체
- (:Report)-[:`도출`]->(:Agenda)       보고자료에서 도출된 안건
- (:Agenda)-[:`관련`]-(:Agenda)        안건 간 연관(방향 무관)
- (:Meetings)-[:`협의`]-(:Meetings)    회의체 간 협의(방향 무관)
- (:User)-[:`참석`]->(:Session)
- (:Session)-[:`후속`]->(:Session)
- (:User)-[:`소속`]->(:Company)"""

_EXAMPLES = [
    "질문: 'IT 인프라' 회의체의 미완료 안건 수\n"
    "MATCH (a:Agenda)-[:`관할`]->(m:Meetings) "
    "WHERE m.title CONTAINS 'IT 인프라' AND a.status <> 'done' "
    "RETURN count(a) AS 미완료안건수",
    "질문: pg_id가 12인 회의체의 보고자료별 검토 상태\n"
    "MATCH (r:Report) WHERE r.meeting_id = 12 "
    "RETURN r.file_name AS 파일, r.human_status AS 상태 LIMIT 25",
]


def _build_schema(allowed_ids: list[int] | None, is_admin: bool) -> str:
    parts = [
        _NODE_SCHEMA,
        _REL_PATTERNS,
        "유효한 관계 타입(이 목록 밖은 사용 금지): "
        + ", ".join(f"`{r}`" for r in sorted(ALLOWED_REL_TYPES)),
        "규칙: 읽기 전용(MATCH/OPTIONAL MATCH/WHERE/WITH/RETURN/ORDER BY/LIMIT)만 사용한다. "
        "CREATE/MERGE/SET/DELETE/REMOVE 등 변경 구문은 절대 쓰지 않는다. RETURN에는 적절한 LIMIT을 둔다.",
    ]
    if not is_admin:
        ids = ", ".join(str(i) for i in (allowed_ids or []))
        parts.append(
            "★ 보안 제약(반드시 준수): 이 사용자는 pg_id ∈ ["
            + ids
            + "] 회의체에만 접근 가능하다. "
            "모든 쿼리를 이 범위로 제한할 것 — 회의체는 (m:Meetings) WHERE m.pg_id IN ["
            + ids
            + "], "
            "그 외 노드는 가능한 한 meeting_id IN [" + ids + "] 로 필터링한다. "
            "허용 범위 밖의 회의체·사용자·회사 데이터는 어떤 경우에도 조회하지 않는다."
        )
    return "\n\n".join(parts)


async def graph_nl_query(
    question: str,
    allowed_meeting_ids: list[int] | None,
    is_admin: bool,
    k: int = 25,
) -> dict:
    """자연어 질문 → Cypher 생성·실행(읽기전용) → 결과.

    반환: {"rows": [...], "cypher": "..."} 또는 {"rows": [], "message": "..."}.
    """
    if not is_admin and not allowed_meeting_ids:
        return {
            "rows": [],
            "message": "접근 가능한 회의체가 없어 그래프 질의를 수행할 수 없습니다.",
        }

    schema = _build_schema(allowed_meeting_ids, is_admin)
    database = os.environ.get("NEO4J_DATABASE", "neo4j")

    def _run() -> dict:
        retr = _ReadOnlyText2Cypher(
            driver=_get_sync_driver(),
            llm=_get_llm(),
            neo4j_schema=schema,
            examples=_EXAMPLES,
            neo4j_database=database,
        )
        res = retr.search(query_text=question)
        cypher = (res.metadata or {}).get("cypher", "")
        rows = [item.content for item in res.items]
        return {"cypher": cypher, "rows": rows[:k]}

    try:
        out = await asyncio.to_thread(_run)
        logger.info(
            "[Text2Cypher] q=%r rows=%d cypher=%r",
            question[:60],
            len(out["rows"]),
            out.get("cypher", "")[:200],
        )
        return out
    except Exception as e:
        # read-only 거부·문법 오류·생성 실패 등은 모델이 복구 가능한 메시지로 변환
        logger.warning(f"[Text2Cypher] 실패: {e}")
        return {"rows": [], "message": f"그래프 질의 생성/실행에 실패했습니다 ({e})."}
