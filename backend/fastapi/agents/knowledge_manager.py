import logging
import os
import json
import uuid
from datetime import datetime, timezone
from typing import AsyncGenerator, List, Optional, Annotated, cast
from typing_extensions import TypedDict

from llm.llm_factory import llm_factory
from langchain_openai import ChatOpenAI
from langchain_core.messages import BaseMessage, SystemMessage, HumanMessage, AIMessage
from langchain_core.tools import tool
from langgraph.graph.message import add_messages
from langgraph.managed import RemainingSteps
from langgraph.prebuilt import create_react_agent
from pydantic import BaseModel, Field
from graphdb.neo4j_ids import to_agenda_id, to_mg_id, to_minutes_id

from routers.prompts import (
    KNOWLEDGE_SYSTEM,
    RELATIONSHIP_SUMMARY_SYSTEM,
    relationship_summary_human,
)

logger = logging.getLogger(__name__)
MODEL = os.environ["OPENAI_MODEL"]


# ── State ─────────────────────────────────────────────────────────────────
class KnowledgeState(TypedDict):
    messages: Annotated[List[BaseMessage], add_messages]
    remaining_steps: RemainingSteps
    knowledge: List[dict]
    meeting_context: str


# ── Pydantic schemas ──────────────────────────────────────────────────────
class KnowledgeEntry(BaseModel):
    node_type: str = Field(..., description="저장 노드 타입: Minutes | Task | Report")
    title: str = Field(..., description="문서 제목")
    content: str = Field(..., description="문서 내용")
    meeting_id: Optional[int] = Field(None, description="연관 회의체 ID")


# ── LLM ───────────────────────────────────────────────────────────────────
def _make_llm(temperature: float = 0.2) -> ChatOpenAI:
    return llm_factory("knowledge", temperature=temperature)


# ── Neo4j 벡터 인덱스 관리 ─────────────────────────────────────────────────
async def ensure_vector_indexes() -> None:
    """Neo4j 5.19 내장 벡터 인덱스가 없으면 Cypher로 생성합니다."""
    from graphdb.neo4j_client import run_cypher

    index_queries = [
        # 인덱스명은 neo4j_sync._VECTOR_INDEXES와 동일해야 한다.
        # (같은 라벨·속성에 다른 이름의 인덱스를 만들면 한쪽 생성이 조용히 실패해
        #  검색이 0건이 되는 사고가 있었음 — Plan.md G-1)
        """CREATE VECTOR INDEX minutesEmbedding IF NOT EXISTS
           FOR (m:Minutes) ON (m.embedding)
           OPTIONS {indexConfig: {
             `vector.dimensions`: 1536,
             `vector.similarity_function`: 'cosine'
           }}""",
        """CREATE VECTOR INDEX agendaEmbedding IF NOT EXISTS
           FOR (t:Agenda) ON (t.embedding)
           OPTIONS {indexConfig: {
             `vector.dimensions`: 1536,
             `vector.similarity_function`: 'cosine'
           }}""",
        """CREATE VECTOR INDEX reportChunkEmbedding IF NOT EXISTS
           FOR (c:ReportChunk) ON (c.embedding)
           OPTIONS {indexConfig: {
             `vector.dimensions`: 1536,
             `vector.similarity_function`: 'cosine'
           }}""",
        """CREATE VECTOR INDEX minutesChunkEmbedding IF NOT EXISTS
           FOR (c:MinutesChunk) ON (c.embedding)
           OPTIONS {indexConfig: {
             `vector.dimensions`: 1536,
             `vector.similarity_function`: 'cosine'
           }}""",
    ]
    for q in index_queries:
        try:
            await run_cypher(q)
        except Exception:
            pass


# ── 임베딩 생성 ────────────────────────────────────────────────────────────
async def _embed(text: str) -> List[float]:
    # EMBED_MODEL(text-embedding-3-small)·EMBED_DIM(1536)·사용량 기록을 일원화한 공용
    # 임베더 사용. 직접 OpenAIEmbeddings()는 모델 미지정 시 ada-002로 떨어져 EMBED_MODEL을
    # 무시하므로 사용하지 않는다(벡터 차원이 인덱스와 어긋나 검색이 실패할 수 있다).
    from graphdb.file_embedder import embed_query

    return await embed_query(text[:2000])


# ── Neo4j 저장 함수 ────────────────────────────────────────────────────────
async def store_minutes(
    title: str,
    content: str,
    meeting_id: int,
    session_id: int = None,
) -> dict:
    from graphdb.neo4j_client import run_cypher

    await ensure_vector_indexes()
    node_id = to_minutes_id(uuid.uuid4().hex[:8])
    embedding = await _embed(content)
    created_at = datetime.now(timezone.utc).isoformat()

    await run_cypher(
        """MERGE (m:Minutes {id: $id})
           SET m.title = $title,
               m.content = $content,
               m.meeting_id = $meeting_id,
               m.session_id = $session_id,
               m.created_at = $created_at
           WITH m
           CALL db.create.setNodeVectorProperty(m, 'embedding', $embedding)
           RETURN m.id AS id""",
        {
            "id": node_id,
            "title": title,
            "content": content[:8000],
            "meeting_id": meeting_id,
            "session_id": session_id,
            "created_at": created_at,
            "embedding": embedding,
        },
    )

    if meeting_id:
        try:
            await run_cypher(
                """MATCH (m:Minutes {id: $mid})
                   MATCH (mg:Meeting_session {pg_id: $pg_id})
                   MERGE (m)-[:`청크`]->(mg)""",
                {"mid": node_id, "pg_id": meeting_id},
            )
        except Exception:
            pass

    return {"id": node_id, "status": "stored", "node_type": "Minutes"}


async def store_task(
    content: str,
    department: str = None,
    due_date: str = None,
    meeting_id: int = None,
) -> dict:
    from graphdb.neo4j_client import run_cypher

    await ensure_vector_indexes()
    node_id = to_agenda_id(uuid.uuid4().hex[:8])
    embedding = await _embed(content)
    created_at = datetime.now(timezone.utc).isoformat()

    await run_cypher(
        """MERGE (t:Agenda {id: $id})
           SET t.content = $content,
               t.department = $department,
               t.due_date = $due_date,
               t.meeting_id = $meeting_id,
               t.status = 'pending',
               t.created_at = $created_at
           WITH t
           CALL db.create.setNodeVectorProperty(t, 'embedding', $embedding)
           RETURN t.id AS id""",
        {
            "id": node_id,
            "content": content,
            "department": department,
            "due_date": due_date,
            "meeting_id": meeting_id,
            "created_at": created_at,
            "embedding": embedding,
        },
    )

    if department:
        try:
            await run_cypher(
                """MATCH (t:Agenda {id: $tid})
                   MERGE (d:Department {name: $dept})
                   MERGE (t)-[:ASSIGNED_TO_DEPT]->(d)""",
                {"tid": node_id, "dept": department},
            )
        except Exception:
            pass

    if meeting_id:
        try:
            await run_cypher(
                """MATCH (t:Agenda {id: $tid})
                   MATCH (mg:Meeting {pg_id: $pg_id})
                   MERGE (t)-[:`청크`]->(mg)""",
                {"tid": node_id, "pg_id": meeting_id},
            )
        except Exception:
            pass

    return {"id": node_id, "status": "stored", "node_type": "Agenda"}


async def store_report(
    title: str,
    content: str,
    meeting_id: int = None,
    score: int = None,
) -> dict:
    from graphdb.neo4j_client import run_cypher

    await ensure_vector_indexes()
    node_id = f"reportchunk-{uuid.uuid4().hex[:8]}"
    embedding = await _embed(content)
    created_at = datetime.now(timezone.utc).isoformat()

    await run_cypher(
        """MERGE (c:ReportChunk {id: $id})
           SET c.title = $title,
               c.content = $content,
               c.meeting_id = $meeting_id,
               c.score = $score,
               c.created_at = $created_at,
               c.source = 'ai_review'
           WITH c
           CALL db.create.setNodeVectorProperty(c, 'embedding', $embedding)
           RETURN c.id AS id""",
        {
            "id": node_id,
            "title": title,
            "content": content[:8000],
            "meeting_id": meeting_id,
            "score": score,
            "created_at": created_at,
            "embedding": embedding,
        },
    )

    if meeting_id:
        try:
            await run_cypher(
                """MATCH (c:ReportChunk {id: $cid})
                   MATCH (mg:Meetings {id: $mg_id})
                   MERGE (c)-[:`청크`]->(mg)""",
                {"cid": node_id, "mg_id": to_mg_id(meeting_id)},
            )
        except Exception:
            pass

    return {"id": node_id, "status": "stored", "node_type": "ReportChunk"}


async def search_knowledge(
    query: str,
    node_type: str = "Minutes",
    k: int = 5,
    meeting_ids: list[int] | None = None,
) -> List[dict]:
    """스코프드 의미검색. meeting_ids 미지정 시 현재 요청의 접근 스코프(agent_scope contextvar)를
    자동 적용해 비소속·타사 회의체 데이터 누수(IDOR)를 차단한다. 관리자/스코프 미설정이면 전체 검색.
    라벨별 스코프 규칙은 retrieval_registry와 동일(prop/rel/custom)."""
    from graphdb.neo4j_client import run_cypher
    from graphdb.retrieval_registry import index_for, _resolve, RETRIEVAL_ZERO_RESULTS
    from core.agent_scope import current_scope_meeting_ids

    try:
        index_for(node_type)  # 미등록 라벨 조기 발견
    except KeyError as e:
        logger.warning(f"[search_knowledge] {e}")
        return []

    scope = meeting_ids if meeting_ids is not None else current_scope_meeting_ids()
    embedding = await _embed(query)
    entry_label, entry = _resolve(node_type)

    # queryNodes는 전역 top-N을 먼저 뽑으므로, 스코프가 있으면 오버페치 후 잘라 누락을 막는다.
    fetch_k = max(k * 10, 50) if scope is not None else k
    scope_clause = ""
    params: dict = {"k": k, "fetch_k": fetch_k, "embedding": embedding}
    if scope is not None:
        _sc = entry.get("scope")
        if _sc == "prop":
            scope_clause = "WHERE node.meeting_id IN $mids "
            params["mids"] = list(scope)
        elif _sc == "rel":
            scope_clause = "MATCH (node)--(mg:Meetings) WHERE mg.pg_id IN $mids "
            params["mids"] = list(scope)
        elif _sc == "custom":
            scope_clause = entry["scope_cypher"]
            params["mids"] = list(scope)
        # scope None(청크 등): 미지원 라벨은 전체 — 호출측이 별도 처리

    last_err: Exception | None = None
    for idx in [entry["index"], *entry.get("legacy", [])]:
        try:
            rows = await run_cypher(
                f"CALL db.index.vector.queryNodes('{idx}', $fetch_k, $embedding) "
                f"YIELD node, score {scope_clause}"
                f"RETURN node.title AS title, node.content AS content, "
                f"node.meeting_id AS meeting_id, score ORDER BY score DESC LIMIT $k",
                params,
            )
            if not rows:
                RETRIEVAL_ZERO_RESULTS.labels(entry_label).inc()
                logger.warning(
                    f"[search_knowledge] 검색 결과 0건: node_type={node_type} index={idx} query={query[:50]!r}"
                )
            return rows
        except Exception as e:
            last_err = e
    logger.warning(f"[search_knowledge] 검색 실패 ({node_type}): {last_err}")
    return []


# ── 공개 Tool 함수 (Agent가 직접 호출 가능) ──────────────────────────────────
@tool
async def search_knowledge_graph(query: str, node_type: str = "Minutes") -> str:
    """지식 그래프에서 의미 기반으로 문서를 검색합니다.

    Args:
        query: 검색할 키워드 또는 자연어 쿼리
        node_type: 검색 대상 노드 타입 (Minutes / Agenda / Report)
    """
    results = await search_knowledge(query, node_type=node_type, k=5)

    # KnowledgeChunk를 항상 보조 검색 (업로드된 지식 문서)
    extra: List[dict] = []
    if node_type != "KnowledgeChunk":
        extra = await search_knowledge(query, node_type="KnowledgeChunk", k=2)

    parts = []
    for r in results[:4]:
        title = r.get("title") or ""
        content = r.get("content", "")[:250]
        score = float(r.get("score") or 0)
        parts.append(f"[{node_type}] {title}\n{content}\n(유사도 {score * 100:.0f}%)")
    for r in extra[:2]:
        title = r.get("title") or ""
        content = r.get("content", "")[:250]
        score = float(r.get("score") or 0)
        parts.append(
            f"[KnowledgeChunk] {title}\n{content}\n(유사도 {score * 100:.0f}%)"
        )

    if not parts:
        return "관련 자료를 찾지 못했습니다."
    return "\n\n---\n\n".join(parts)


@tool
async def fetch_meeting_graph_context(meeting_id: int) -> str:
    """특정 회의체의 Neo4j 그래프 컨텍스트(안건·세션·구성원 등)를 조회합니다.

    Args:
        meeting_id: 조회할 회의체 ID (PostgreSQL PK)
    """
    from core.agent_scope import current_scope_meeting_ids
    from graphdb.neo4j_client import get_meeting_graph_context, graph_context_to_str

    # 현재 사용자가 볼 수 없는 회의체면 차단 (IDOR 방지)
    _scope = current_scope_meeting_ids()
    if _scope is not None and meeting_id not in _scope:
        return "[접근 거부] 해당 회의체에 대한 접근 권한이 없습니다."

    ctx = await get_meeting_graph_context(meeting_id)
    return graph_context_to_str(ctx) or "(회의체 정보 없음)"


KNOWLEDGE_TOOLS: list = [search_knowledge_graph, fetch_meeting_graph_context]


# ── HITL: 관계 제안 / 승인·반려 ──────────────────────────────────────────────
_proposals: dict = {}  # proposal_id → {meeting_id, relationships, created_at} (인메모리 임시 저장)


async def propose_relationships(
    meeting_id: int,
    node_types: List[str] = None,
) -> dict:
    """Neo4j에서 같은 meeting_id 노드를 조회하고, LLM이 연결 가능한 관계를 분석해 제안합니다.
    반환: {proposal_id, relationships: [{from_id, from_type, to_id, to_type, rel_type, reason}]}
    """
    from graphdb.neo4j_client import run_cypher

    if node_types is None:
        node_types = ["Agenda", "Minutes"]

    nodes: List[dict] = []
    queries = {
        "Agenda": "MATCH (n:Agenda {meeting_id: $mid}) RETURN n.id AS id, n.content AS content, 'Agenda' AS type",
        "Minutes": "MATCH (n:Minutes {meeting_id: $mid}) RETURN n.id AS id, n.title AS content, 'Minutes' AS type",
    }
    for ntype in node_types:
        if ntype in queries:
            try:
                rows = await run_cypher(queries[ntype], {"mid": meeting_id})
                nodes.extend(rows)
            except Exception:
                pass

    if not nodes:
        return {
            "proposal_id": None,
            "relationships": [],
            "message": "분석할 노드가 없습니다.",
        }

    node_list_text = "\n".join(
        [
            f"- [{r['type']}] id={r['id']}: {str(r.get('content', ''))[:100]}"
            for r in nodes
        ]
    )
    llm = llm_factory("knowledge", temperature=0.1, streaming=False)
    response = await llm.ainvoke(
        [
            SystemMessage(
                content="""회의체 온톨로지 분석 전문가입니다.
제공된 Neo4j 노드 목록을 보고 연결해야 할 관계를 제안하세요.
반드시 아래 JSON 형식으로만 응답하세요:
{
  "relationships": [
    {
      "from_id": "노드 id",
      "from_type": "노드 타입",
      "to_id": "연결 대상 id",
      "to_type": "연결 대상 타입",
      "rel_type": "관계 타입 (예: RELATED_TO, DERIVED_FROM, REFERENCES)",
      "reason": "연결 이유 한 줄"
    }
  ]
}"""
            ),
            HumanMessage(
                content=f"회의체 ID: {meeting_id}\n\n노드 목록:\n{node_list_text}\n\n위 노드들 간에 연결해야 할 관계를 분석해 주세요."
            ),
        ]
    )

    try:
        import re as _re2

        _m = _re2.search(r"\{[\s\S]*\}", cast(str, response.content))
        parsed = json.loads(_m.group(0)) if _m else {"relationships": []}
    except Exception:
        parsed = {"relationships": []}

    relationships = parsed.get("relationships", [])

    proposal_id = f"proposal-{uuid.uuid4().hex[:8]}"
    _proposals[proposal_id] = {
        "meeting_id": meeting_id,
        "relationships": relationships,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    return {"proposal_id": proposal_id, "relationships": relationships}


async def confirm_relationships(
    proposal_id: str,
    approved: bool,
    reject_reason: str = None,
) -> dict:
    """제안된 관계를 승인하면 Neo4j에 MERGE, 반려하면 제안을 폐기합니다.
    승인 반환: {status:"confirmed", relationships:[...]}
    반려 반환: {status:"rejected"}
    """
    from graphdb.neo4j_client import run_cypher

    proposal = _proposals.get(proposal_id)
    if not proposal:
        return {"status": "error", "message": "존재하지 않는 proposal_id입니다."}

    relationships = proposal["relationships"]

    if approved:
        merged = []
        for rel in relationships:
            try:
                await run_cypher(
                    f"""MATCH (a {{id: $from_id}})
                        MATCH (b {{id: $to_id}})
                        MERGE (a)-[:{rel["rel_type"]}]->(b)""",
                    {"from_id": rel["from_id"], "to_id": rel["to_id"]},
                )
                merged.append(rel)
            except Exception:
                pass
        _proposals.pop(proposal_id, None)
        return {"status": "confirmed", "relationships": merged}

    else:
        _proposals.pop(proposal_id, None)
        return {"status": "rejected"}


# ── Helpers ────────────────────────────────────────────────────────────────
def _to_base_messages(messages: List[dict]) -> List[BaseMessage]:
    result: List[BaseMessage] = []
    for m in messages:
        role, content = m.get("role", ""), m.get("content", "")
        if role == "user":
            result.append(HumanMessage(content=content))
        elif role in ("assistant", "agent"):
            result.append(AIMessage(content=content))
    return result


# ── Graph ─────────────────────────────────────────────────────────────────
def _knowledge_state_modifier(state: KnowledgeState) -> List[BaseMessage]:
    knowledge = state.get("knowledge", [])
    meeting_context = state.get("meeting_context", "")
    system = KNOWLEDGE_SYSTEM
    if meeting_context:
        system += f"\n\n[회의체 맥락]\n{meeting_context}"
    if knowledge:
        kb_text = "\n".join(
            [
                f"- [{k.get('category', '')}] {k.get('title', '')}: {k.get('content', '')[:100]}"
                for k in knowledge[:10]
            ]
        )
        system += f"\n\n[Knowledge Base 현황]\n{kb_text}"
    return [SystemMessage(content=system)] + list(state.get("messages", []))


def _build_graph():
    return create_react_agent(
        model=_make_llm(),
        tools=KNOWLEDGE_TOOLS,
        state_schema=KnowledgeState,
        prompt=_knowledge_state_modifier,
    )


_graph = _build_graph()


# ── Public API ─────────────────────────────────────────────────────────────
async def chat_stream(
    message: str,
    chat_history: List[dict],
    knowledge: List[dict] = None,
    meeting_id: int = 0,
    meeting_context: str = "",
) -> AsyncGenerator[str, None]:
    history = _to_base_messages(chat_history[-10:])
    input_msgs = history + [HumanMessage(content=message)]
    config = {"configurable": {"thread_id": str(uuid.uuid4())}}

    async for event in _graph.astream_events(
        {
            "messages": input_msgs,
            "knowledge": knowledge or [],
            "meeting_context": meeting_context,
        },
        config,
        version="v2",
    ):
        if event["event"] == "on_chat_model_stream":
            chunk = event["data"]["chunk"]
            if chunk.content:
                yield chunk.content


# ── 지식 그래프 관리(재구성) ──────────────────────────────────────────────────
# 유사도 임계값은 core.ai_config로 집약(env로 튜닝 가능, 하드코딩 금지)
from core.ai_config import (  # noqa: E402
    ORPHAN_ATTACH_THRESHOLD as _ORPHAN_ATTACH_THRESHOLD,
    LIFECYCLE_LINK_THRESHOLD as _LIFECYCLE_LINK_THRESHOLD,
)


class _AgendaFillItem(BaseModel):
    agenda_id: int = Field(..., description="대상 안건 id")
    department: Optional[List[str]] = Field(
        None, description="채울 담당 부서명 목록 (추론 불가/불필요하면 null)"
    )
    due_date: Optional[str] = Field(
        None,
        description="채울 마감일 YYYY-MM-DD (비어있고 맥락상 추론 가능할 때만, 아니면 null)",
    )
    priority: Optional[str] = Field(
        None, description="low|medium|high (보정 없으면 null)"
    )
    status: Optional[str] = Field(None, description="ongoing|done (변경 없으면 null)")
    reason: str = Field("", description="변경 근거 한 문장")


class _AgendaFillResult(BaseModel):
    items: List[_AgendaFillItem] = Field(default_factory=list)


async def fill_agenda_fields(meeting_ids: List[int]) -> dict:
    """'채우기' — 접근 가능한 회의체의 안건에서 빈 필드(부서)·우선순위·완료 상태를 맥락에 맞게 보정한다.

    reconcile_graph가 '관계를 재설정'하던 것과 달리, 사용자가 비워둔 노드 메타데이터를 채우고
    우선순위·상태를 현실에 맞게 조정하는 데 집중한다. PG(Agenda)를 수정한 뒤 Neo4j에 동기화한다.
    부서는 비어있을 때만 채워(사용자 입력 보존), 우선순위·상태는 근거 기반으로만 보정한다.
    """
    from db.database import SessionLocal
    from db import models as _m
    from graphdb import neo4j_sync
    from routers.prompts import FIELD_FILL_SYSTEM, field_fill_human

    actions: list[dict] = []
    stats = {"department": 0, "due_date": 0, "priority": 0, "status": 0}
    if not meeting_ids:
        return {"actions": actions, "stats": stats}

    changed_for_sync: list[dict] = []
    db = SessionLocal()
    try:
        rows = (
            db.query(_m.Agenda)
            .filter(_m.Agenda.meeting_id.in_(list(meeting_ids)))
            .filter(_m.Agenda.status.notin_(["done", "closed", "completed", "draft"]))
            .order_by(_m.Agenda.created_at.desc())
            .limit(60)
            .all()
        )
        if not rows:
            return {"actions": actions, "stats": stats}
        mids = list({r.meeting_id for r in rows})
        mtitle = {
            m.id: m.title
            for m in db.query(_m.Meeting).filter(_m.Meeting.id.in_(mids)).all()
        }
        payload = [
            {
                "id": r.id,
                "title": r.title,
                "status": r.status,
                "priority": r.priority,
                "department": r.department,
                "due_date": r.due_date.isoformat() if r.due_date else None,
                "evidence": r.ai_evidence,
                "meeting": mtitle.get(r.meeting_id, ""),
            }
            for r in rows
        ]
        try:
            llm = llm_factory(
                "knowledge", temperature=0.1, streaming=False
            ).with_structured_output(_AgendaFillResult)
            result = cast(
                _AgendaFillResult,
                await llm.ainvoke(
                    [
                        SystemMessage(content=FIELD_FILL_SYSTEM),
                        HumanMessage(
                            content=field_fill_human(
                                payload, datetime.now().date().isoformat()
                            )
                        ),
                    ]
                ),
            )
        except Exception as e:
            logger.warning(f"[fill] LLM 보정 실패: {e}")
            return {"actions": actions, "stats": stats}

        by_id = {r.id: r for r in rows}
        for item in result.items:
            ag = by_id.get(item.agenda_id)
            if not ag:
                continue
            changed: list[str] = []
            # 부서: 비어있을 때만 채움(사용자 설정 보존)
            if item.department and not ag.department:
                ag.department = item.department
                changed.append(f"부서 {', '.join(item.department)}")
                stats["department"] += 1
            # 마감일: 비어있을 때만 맥락 기반으로 채움
            if item.due_date and not ag.due_date:
                try:
                    ag.due_date = datetime.fromisoformat(item.due_date.strip()[:19])
                    changed.append(f"마감일 {item.due_date.strip()[:10]}")
                    stats["due_date"] += 1
                except Exception:
                    pass
            # 우선순위: 유효값이고 다를 때 보정
            if (
                item.priority in ("low", "medium", "high")
                and item.priority != ag.priority
            ):
                ag.priority = item.priority
                changed.append(f"우선순위 {item.priority}")
                stats["priority"] += 1
            # 상태: ongoing/done만, 근거 기반(임의 완료는 프롬프트로 차단)
            if item.status in ("ongoing", "done") and item.status != ag.status:
                ag.status = item.status
                changed.append(f"상태 {item.status}")
                stats["status"] += 1
            if changed:
                actions.append(
                    {
                        "kind": "fill",
                        "detail": f"[{ag.title}]",
                        "changed": changed,
                        "evidence": item.reason or "맥락에 맞게 보정",
                        "highlight": ag.title,
                    }
                )
                changed_for_sync.append(
                    {
                        "agenda_id": ag.id,
                        "meeting_id": ag.meeting_id,
                        "title": ag.title,
                        "status": ag.status,
                        "assignee_id": ag.assignee_id,
                        "priority": ag.priority,
                        "due_date": ag.due_date.isoformat() if ag.due_date else None,
                        "session_id": ag.session_id,
                        "department": json.dumps(ag.department, ensure_ascii=False)
                        if ag.department
                        else None,
                        "ai_evidence": ag.ai_evidence,
                    }
                )
        db.commit()
    finally:
        db.close()

    # PG 커밋 후 Neo4j 동기화(변경분만) — draft가 아니므로 노드 upsert됨
    for c in changed_for_sync:
        try:
            await neo4j_sync.sync_agenda(**c)
        except Exception as e:
            logger.warning(f"[fill] Neo4j 동기화 실패(agenda {c['agenda_id']}): {e}")

    return {"actions": actions, "stats": stats}


async def reconcile_graph(analysis: dict) -> dict:
    from graphdb.neo4j_client import run_cypher

    sem = analysis.get("semantic", {})
    struct = analysis.get("structural", {})
    member = analysis.get("membership", {})

    actions: List[dict] = []
    stats = {
        "session_links": 0,
        "lifecycle_links": 0,
        "carry_links": 0,
        "session_agenda_links": 0,
        "related_agendas": 0,
        "doc_refs": 0,
        "doc_attached": 0,
        "membership_fixed": 0,
        "pruned_links": 0,
    }
    ts = datetime.now(timezone.utc).isoformat()

    # ⓪ 세션 시간순 '후속' 체인
    for chain in struct.get("session_chains", []):
        mg_title = chain.get("mg", "")
        for pair in chain.get("missing", []):
            a_id, b_id = pair.get("a_id"), pair.get("b_id")
            if not a_id or not b_id:
                continue
            try:
                await run_cypher(
                    "MATCH (a:Session {id:$a}), (b:Session {id:$b}) "
                    "MERGE (a)-[r:`후속`]->(b) "
                    "SET r.kind='session_sequence', r.discovered_by='knowledge_agent', r.discovered_at=$ts",
                    {"a": a_id, "b": b_id, "ts": ts},
                )
                a_t = pair.get("a_title") or "이전 회차"
                b_t = pair.get("b_title") or "다음 회차"
                actions.append(
                    {
                        "kind": "session_chain",
                        "detail": f"[{a_t}] → [{b_t}]"
                        + (f" · {mg_title}" if mg_title else ""),
                        "evidence": "같은 회의체의 연속된 회차를 시간순으로 이어 회의의 흐름(맥락)을 복원했습니다.",
                        "highlight": pair.get("b_title") or None,
                    }
                )
                stats["session_links"] += 1
            except Exception:
                pass

    # ① 회의 생명주기 — Minutes → Agenda 브릿지
    for gap in struct.get("lifecycle_gaps", []):
        mid = gap.get("minutes_pg_id")
        sid = gap.get("session_id")
        content = gap.get("content", "")
        session_title = gap.get("session_title", "세션")
        if not mid or not content.strip():
            continue
        try:
            emb = await _embed(content[:2000])
            rows = await run_cypher(
                "MATCH (mn:Minutes {pg_id:$mid})<-[:`기록`]-(s:Session {id:$sid})"
                "-[:`소속`]->(mg:Meetings) "
                "WITH mn, s, mg "
                "CALL db.index.vector.queryNodes('agendaEmbedding', 5, $emb) YIELD node AS ag, score "
                "WHERE score >= $lifecycle_th "
                "WITH mn, s, mg, ag, score "
                "WHERE (mg)-[:`추출`|`관할`]-(ag) AND NOT (mn)-[:`도출`]->(ag) "
                "MERGE (mn)-[r:`도출`]->(ag) "
                "SET r.score=score, r.kind='minutes_agenda', r.discovered_by='knowledge_agent', r.discovered_at=$ts "
                "MERGE (ag)-[r2:`논의`]->(s) "
                "SET r2.score=score, r2.kind='session_agenda', r2.discovered_by='knowledge_agent', r2.discovered_at=$ts "
                "RETURN ag.title AS title, score",
                {
                    "sid": sid,
                    "emb": emb,
                    "mid": mid,
                    "ts": ts,
                    "lifecycle_th": _LIFECYCLE_LINK_THRESHOLD,
                },
            )
            if rows:
                linked = [r.get("title", "?") for r in rows]
                actions.append(
                    {
                        "kind": "lifecycle",
                        "detail": f"〔{session_title}〕 → 안건 {len(linked)}개: {', '.join(f'[{t}]' for t in linked[:3])}",
                        "evidence": "회의록 내용과 안건을 임베딩으로 연결, 회의→회의록→안건 생명주기를 이었습니다.",
                        "highlight": session_title,
                    }
                )
                stats["lifecycle_links"] += len(rows)
        except Exception:
            pass

    # ①-b 이월(carry-forward)
    try:
        cf = await run_cypher(
            "MATCH (s:Session)-[:`소속`]->(mg:Meetings)-[:`추출`|`관할`]-(ag:Agenda) "
            "WHERE coalesce(ag.status,'') IN ['ON_HOLD','IN_PROGRESS'] AND coalesce(s.scheduled_at,'')<>'' "
            "WITH ag, s ORDER BY s.scheduled_at DESC "
            "WITH ag, collect(s)[0] AS latest "
            "WHERE latest IS NOT NULL AND NOT (latest)-[:`도출`]->(ag) "
            "MERGE (latest)-[r:`도출`]->(ag) SET r.kind='carry_forward', r.discovered_at=$ts "
            "RETURN count(*) AS n",
            {"ts": ts},
        )
        n = cf[0].get("n", 0) if cf else 0
        if n:
            stats["carry_links"] = n
            actions.append(
                {
                    "kind": "lifecycle",
                    "detail": f"미해결 안건 {n}건을 다음 회차로 이월",
                    "evidence": "아직 끝나지 않은 안건을 가장 최근 회차와 연결해 생명주기를 다음 회의로 이어줬습니다(안건→회의).",
                    "highlight": None,
                }
            )
    except Exception:
        pass

    # ①-c 세션↔안건 연결 보완 — 발제세션(canonical) 단일화. 역방향 '진행'·중복 '다룸'은 폐지하고
    #     발제세션 하나로만 표현(Neo4j는 양방향 탐색 가능). 발제세션 없는 떠있는 안건을 같은 회의체 세션과 연결.
    try:
        floating_rows = await run_cypher(
            "MATCH (s:Session)-[:`소속`]->(mg:Meetings)-[:`추출`|`관할`]-(ag:Agenda) "
            "WHERE NOT (ag)-[:`논의`]->(:Session) "
            "  AND NOT coalesce(ag.status,'') IN ['DONE','COMPLETED','CLOSED','RESOLVED'] "
            "WITH s, ag LIMIT 200 "
            "MERGE (ag)-[r:`논의`]->(s) "
            "SET r.kind='session_agenda_group', r.discovered_by='knowledge_agent', r.discovered_at=$ts "
            "RETURN count(r) AS n",
            {"ts": ts},
        )
        total_n = floating_rows[0].get("n", 0) if floating_rows else 0
        if total_n:
            stats["session_agenda_links"] = total_n
            actions.append(
                {
                    "kind": "session_agenda",
                    "detail": f"세션↔안건 연결 {total_n}건 보완",
                    "evidence": "회의(세션)는 아젠다와 연결되어야 한다는 원칙에 따라 미연결 안건을 같은 회의체 세션과 이어줬습니다.",
                    "highlight": None,
                }
            )
    except Exception:
        pass

    # ② 회의 간 의미 유사 안건 → `관련` 지식 링크
    for link in sem.get("agenda_links", []):
        a_id, b_id = link.get("a_id"), link.get("b_id")
        if not a_id or not b_id:
            continue
        try:
            await run_cypher(
                "MATCH (a:Agenda {id:$a}), (b:Agenda {id:$b}) "
                "MERGE (a)-[r:`관련`]-(b) "
                "SET r.score = $score, r.discovered_by = 'knowledge_agent', r.discovered_at = $ts",
                {
                    "a": a_id,
                    "b": b_id,
                    "score": round(link.get("score", 0.0), 4),
                    "ts": ts,
                },
            )
            pct = link.get("score", 0.0) * 100
            actions.append(
                {
                    "kind": "related",
                    "detail": f"[{link.get('a_title', '?')}] ↔ [{link.get('b_title', '?')}]",
                    "evidence": (
                        f"'{link.get('a_mg', '')}' 회의의 안건과 '{link.get('b_mg', '')}' 회의의 안건이 "
                        f"의미상 {pct:.0f}% 유사 — 회의 경계를 넘는 지식 연결을 생성했습니다."
                    ),
                    "highlight": link.get("a_title"),
                }
            )
            stats["related_agendas"] += 1
        except Exception:
            pass

    # ② 문서 ↔ 안건 적합 → canonical 연결
    # 안건으로 들어오는 문서 관계: 보고자료=`취급`, 회의록=`도출` (라벨로 분기). `발제`는 폐지.
    for link in sem.get("doc_links", []):
        d_id, ag_id = link.get("doc_id"), link.get("ag_id")
        if not d_id or not ag_id:
            continue
        try:
            await run_cypher(
                "MATCH (d {id:$d}), (a:Agenda {id:$a}) WHERE d:Report OR d:Minutes "
                "FOREACH (_ IN CASE WHEN d:Report THEN [1] ELSE [] END | "
                "  MERGE (d)-[r1:`취급`]->(a) "
                "  SET r1.score=$score, r1.discovered_by='knowledge_agent', r1.discovered_at=$ts) "
                "FOREACH (_ IN CASE WHEN d:Minutes THEN [1] ELSE [] END | "
                "  MERGE (d)-[r2:`도출`]->(a) "
                "  SET r2.score=$score, r2.discovered_by='knowledge_agent', r2.discovered_at=$ts)",
                {
                    "d": d_id,
                    "a": ag_id,
                    "score": round(link.get("score", 0.0), 4),
                    "ts": ts,
                },
            )
            pct = link.get("score", 0.0) * 100
            actions.append(
                {
                    "kind": "doc_ref",
                    "detail": f"문서 [{link.get('doc_title', '?')}] → 안건 [{link.get('ag_title', '?')}]",
                    "evidence": f"문서 내용이 해당 안건과 {pct:.0f}% 부합 — 보고자료는 '취급', 회의록은 '도출' 관계로 연결했습니다.",
                    "highlight": link.get("ag_title"),
                }
            )
            stats["doc_refs"] += 1
        except Exception:
            pass

    # ③ 고아 문서 → 임베딩으로 가장 적합한 안건에 연결 (보고자료=취급, 회의록=도출)
    for doc in struct.get("orphan_documents", []):
        if not doc.get("emb") or not doc.get("id"):
            continue
        try:
            rows = await run_cypher(
                "MATCH (d {id:$id}) WHERE (d:Report OR d:Minutes) AND d.embedding IS NOT NULL "
                "CALL db.index.vector.queryNodes('agendaEmbedding', 1, d.embedding) "
                "YIELD node, score "
                "WITH d, node, score WHERE score >= $th "
                "FOREACH (_ IN CASE WHEN d:Report THEN [1] ELSE [] END | "
                "  MERGE (d)-[r1:`취급`]->(node) "
                "  SET r1.auto_linked=true, r1.score=score, r1.discovered_at=$ts) "
                "FOREACH (_ IN CASE WHEN d:Minutes THEN [1] ELSE [] END | "
                "  MERGE (d)-[r2:`도출`]->(node) "
                "  SET r2.auto_linked=true, r2.score=score, r2.discovered_at=$ts) "
                "RETURN node.title AS title, score",
                {"id": doc["id"], "th": _ORPHAN_ATTACH_THRESHOLD, "ts": ts},
            )
            if rows:
                title = rows[0].get("title", "?")
                score = float(rows[0].get("score") or 0.0)
                actions.append(
                    {
                        "kind": "doc_attach",
                        "detail": f"고아 문서 [{doc.get('title', '?')}] → 안건 [{title}]",
                        "evidence": (
                            f"어디에도 연결되지 않던 문서를 의미상 가장 가까운 안건"
                            f"(유사도 {score * 100:.0f}%)에 자동 편입했습니다."
                        ),
                        "highlight": title,
                    }
                )
                stats["doc_attached"] += 1
        except Exception:
            pass

    # ④ 소속 무결성(baseline) 보정
    for issue in member.get("issues", []):
        itype, pid = issue.get("type"), issue.get("pid")
        name, dept = issue.get("person", "?"), issue.get("dept", "")
        current = issue.get("current")
        if not dept or not pid:
            continue
        try:
            if itype == "legacy":
                await run_cypher(
                    "MATCH (p:User {id:$pid})-[r:`소속부서`]->(d:Department) "
                    "MERGE (p)-[:`소속`]->(d) DELETE r",
                    {"pid": pid},
                )
                actions.append(
                    {
                        "kind": "membership",
                        "detail": f"{name} → {dept}",
                        "evidence": "구버전 소속 관계를 표준 형식으로 정리했습니다.",
                        "highlight": name,
                    }
                )
            elif itype == "missing":
                await run_cypher(
                    "MATCH (p:User {id:$pid}) MERGE (d:Department {name:$dept}) "
                    "MERGE (p)-[:`소속`]->(d)",
                    {"pid": pid, "dept": dept},
                )
                actions.append(
                    {
                        "kind": "membership",
                        "detail": f"{name} → {dept}",
                        "evidence": f"누락된 '{dept}' 소속 연결을 복구했습니다('미지정' 해소).",
                        "highlight": name,
                    }
                )
            elif itype == "mismatch":
                await run_cypher(
                    "MATCH (p:User {id:$pid})-[r:`소속`]->(d:Department) "
                    "WHERE d.name <> $dept DELETE r",
                    {"pid": pid, "dept": dept},
                )
                await run_cypher(
                    "MATCH (p:User {id:$pid}) MERGE (d:Department {name:$dept}) "
                    "MERGE (p)-[:`소속`]->(d)",
                    {"pid": pid, "dept": dept},
                )
                actions.append(
                    {
                        "kind": "membership",
                        "detail": f"{name} → {dept}",
                        "evidence": f"프로필과 다르게 '{current}'로 연결됐던 소속을 '{dept}'로 교정했습니다.",
                        "highlight": name,
                    }
                )
            stats["membership_fixed"] += 1
        except Exception:
            pass

    # ① 불필요한 연결 정제 — stale/weak 자동 생성 관계 제거
    for link in struct.get("stale_links", []):
        kind = link.get("kind")
        from_id = link.get("from_id")
        to_id = link.get("to_id")
        rel = link.get("rel", "")
        if not from_id or not to_id or not rel:
            continue
        try:
            if kind == "stale_carry":
                # 완료된 안건에 달린 이월(carry_forward) 관계 제거
                await run_cypher(
                    "MATCH (a:Session {id:$fid})-[r:`도출`]->(b:Agenda {id:$tid}) "
                    "WHERE r.kind = 'carry_forward' DELETE r",
                    {"fid": from_id, "tid": to_id},
                )
            elif kind == "stale_lifecycle":
                # 완료된 안건에 달린 Minutes 도출 관계 제거
                await run_cypher(
                    "MATCH (a:Minutes)-[r:`도출`]->(b:Agenda {id:$tid}) "
                    "WHERE r.kind = 'minutes_agenda' DELETE r",
                    {"tid": to_id},
                )
            elif kind == "weak_related":
                await run_cypher(
                    "MATCH (a:Agenda {id:$fid})-[r:`관련`]-(b:Agenda {id:$tid}) "
                    "WHERE r.discovered_by = 'knowledge_agent' DELETE r",
                    {"fid": from_id, "tid": to_id},
                )
            elif kind == "weak_ref":
                # AI가 의미유사로 자동 연결한 문서→안건(발제/도출) 중 임계값 미달분 제거.
                # 라이프사이클 도출(r.kind 보유)·수동 발제는 건드리지 않는다.
                await run_cypher(
                    "MATCH (a {id:$fid})-[r:`취급`|`도출`|`발제`]->(b:Agenda {id:$tid}) "
                    "WHERE (a:Report OR a:Minutes) AND r.discovered_by = 'knowledge_agent' "
                    "  AND r.kind IS NULL DELETE r",
                    {"fid": from_id, "tid": to_id},
                )
            elif kind == "weak_attach":
                await run_cypher(
                    # 자동연결 문서→안건 엣지(도출, 구 데이터는 발제)의 임계값 미달분 제거
                    "MATCH (a {id:$fid})-[r:`취급`|`도출`|`발제`]->(b:Agenda {id:$tid}) "
                    "WHERE (a:Report OR a:Minutes) AND r.auto_linked = true DELETE r",
                    {"fid": from_id, "tid": to_id},
                )
            evidence = {
                "stale_carry": "완료된 안건에 달린 이월 관계를 정리했습니다.",
                "stale_lifecycle": "완료된 안건과 연결된 회의록 도출 관계를 정리했습니다.",
                "weak_related": f"임계값 미달({link.get('score', 0) * 100:.0f}%) 자동 '관련' 링크를 지웠습니다.",
                "weak_ref": f"임계값 미달({link.get('score', 0) * 100:.0f}%) 자동 문서→안건 링크를 지웠습니다.",
                "weak_attach": f"임계값 미달({link.get('score', 0) * 100:.0f}%) 자동 '발제' 링크를 지웠습니다.",
            }.get(kind, "불필요한 연결을 제거했습니다.")
            actions.append(
                {
                    "kind": "pruned",
                    "detail": link.get("label", "?"),
                    "evidence": evidence,
                    "highlight": None,
                }
            )
            stats["pruned_links"] += 1
        except Exception:
            pass

    return {
        "actions": actions,
        "stats": stats,
        "advisories": {
            "ownerless_agendas": struct.get("ownerless_agendas", []),
            "minuteless_sessions": struct.get("minuteless_sessions", []),
            "isolated_persons": struct.get("isolated_persons", []),
        },
    }


async def summarize_relationship_analysis(report: dict) -> AsyncGenerator[str, None]:
    stats = report.get("stats", {})
    actions = report.get("actions", [])
    advisories = report.get("advisories", {})
    counts = report.get("counts", {})
    findings = report.get("findings", {})

    act_lines = []
    for a in actions[:40]:
        tag = {
            "session_chain": "🧵 회차 연결",
            "lifecycle": "🔄 생명주기",
            "related": "🔗 회의 간 연결",
            "doc_ref": "📎 문서 연결",
            "doc_attach": "🧩 고아 문서 편입",
            "membership": "👤 소속 보정",
        }.get(a.get("kind"), "•")
        act_lines.append(f"- {tag} | {a.get('detail', '')} — {a.get('evidence', '')}")
    act_block = "\n".join(act_lines) if act_lines else "(이번에 새로 만든 연결 없음)"

    adv_lines = []
    own = advisories.get("ownerless_agendas", [])
    if own:
        sample = ", ".join(f"[{o.get('title', '?')}]" for o in own[:5])
        adv_lines.append(
            f"- 담당자 미지정 안건 {len(own)}건: {sample}{' 외' if len(own) > 5 else ''}"
        )
    mls = advisories.get("minuteless_sessions", [])
    if mls:
        adv_lines.append(f"- 회의록이 없는 세션 {len(mls)}건")
    iso = advisories.get("isolated_persons", [])
    if iso:
        sample = ", ".join(p.get("name", "?") for p in iso[:5])
        adv_lines.append(
            f"- 어떤 활동에도 연결되지 않은 구성원 {len(iso)}명: {sample}{' 외' if len(iso) > 5 else ''}"
        )
    adv_block = "\n".join(adv_lines) if adv_lines else "(없음)"

    llm = _make_llm(temperature=0.2)
    async for chunk in llm.astream(
        [
            SystemMessage(content=RELATIONSHIP_SUMMARY_SYSTEM),
            HumanMessage(
                content=relationship_summary_human(
                    counts, findings, stats, act_block, adv_block
                )
            ),
        ]
    ):
        if chunk.content:
            yield cast(str, chunk.content)
