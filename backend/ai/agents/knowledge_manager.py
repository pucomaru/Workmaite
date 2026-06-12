import logging
import os, json, re, uuid
from datetime import datetime
from typing import AsyncGenerator, List, Optional, Annotated
from typing_extensions import TypedDict

logger = logging.getLogger(__name__)

from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_core.messages import BaseMessage, SystemMessage, HumanMessage, AIMessage
from langchain_core.tools import tool
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.managed import RemainingSteps
from langgraph.prebuilt import create_react_agent
from pydantic import BaseModel, Field

from routers.prompts import (
    KNOWLEDGE_SYSTEM,
    RELATIONSHIP_SUMMARY_SYSTEM,
    relationship_summary_human,
)

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
    return ChatOpenAI(
        model=MODEL,
        temperature=temperature,
        api_key=os.environ["OPENAI_API_KEY"],
        streaming=True,
    )


# ── Neo4j 벡터 인덱스 관리 ─────────────────────────────────────────────────
async def ensure_vector_indexes() -> None:
    """Neo4j 5.19 내장 벡터 인덱스가 없으면 Cypher로 생성합니다."""
    from neo4j_client import run_cypher

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
        """CREATE VECTOR INDEX humanJudgmentEmbedding IF NOT EXISTS
           FOR (hj:HumanJudgment) ON (hj.embedding)
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
    embeddings = OpenAIEmbeddings(api_key=os.environ["OPENAI_API_KEY"])
    return await embeddings.aembed_query(text[:2000])


# ── Neo4j 저장 함수 ────────────────────────────────────────────────────────
async def store_minutes(
    title: str,
    content: str,
    meeting_id: int,
    session_id: int = None,
) -> dict:
    from neo4j_client import run_cypher

    await ensure_vector_indexes()
    node_id = f"minutes-{uuid.uuid4().hex[:8]}"
    embedding = await _embed(content)
    created_at = datetime.utcnow().isoformat()

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
                   MERGE (m)-[:BELONGS_TO]->(mg)""",
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
    from neo4j_client import run_cypher

    await ensure_vector_indexes()
    node_id = f"agenda-{uuid.uuid4().hex[:8]}"
    embedding = await _embed(content)
    created_at = datetime.utcnow().isoformat()

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
                   MERGE (t)-[:BELONGS_TO]->(mg)""",
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
    from neo4j_client import run_cypher

    await ensure_vector_indexes()
    node_id = f"reportchunk-{uuid.uuid4().hex[:8]}"
    embedding = await _embed(content)
    created_at = datetime.utcnow().isoformat()

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
                   MERGE (c)-[:BELONGS_TO]->(mg)""",
                {"cid": node_id, "mg_id": f"mg-{meeting_id}"},
            )
        except Exception:
            pass

    return {"id": node_id, "status": "stored", "node_type": "ReportChunk"}



async def search_knowledge(
    query: str,
    node_type: str = "Minutes",
    k: int = 5,
) -> List[dict]:
    from neo4j_client import run_cypher

    # 인덱스명은 neo4j_sync._VECTOR_INDEXES와 일치해야 한다 (불일치 시 검색이 조용히 0건이 됨)
    index_map = {
        "Minutes":       "minutesEmbedding",
        "Agenda":        "agendaEmbedding",
        "HumanJudgment": "humanJudgmentEmbedding",
        "ReportChunk":   "reportChunkEmbedding",
        "MinutesChunk":  "minutesChunkEmbedding",
        "KnowledgeChunk": "reportChunkEmbedding",  # 지식 문서는 ReportChunk 라벨로 저장됨
    }
    index_name = index_map.get(node_type, "minutesChunkEmbedding")
    embedding = await _embed(query)

    # 구버전 DB에는 Minutes 인덱스가 레거시 이름으로 존재할 수 있어 폴백 후보를 둔다
    candidates = [index_name]
    if node_type == "Minutes":
        candidates.append("minutes_embedding_index")

    last_err: Exception | None = None
    for idx in candidates:
        try:
            rows = await run_cypher(
                f"""CALL db.index.vector.queryNodes('{idx}', $k, $embedding)
                    YIELD node, score
                    RETURN node.title AS title, node.content AS content,
                           node.meeting_id AS meeting_id, score
                    ORDER BY score DESC""",
                {"k": k, "embedding": embedding},
            )
            if not rows:
                logger.warning(f"[search_knowledge] 검색 결과 0건: node_type={node_type} index={idx} query={query[:50]!r}")
            return rows
        except Exception as e:
            last_err = e
    logger.warning(f"[search_knowledge] 검색 실패 ({node_type}/{candidates}): {last_err}")
    return []


# ── 공개 Tool 함수 (Agent가 직접 호출 가능) ──────────────────────────────────
@tool
async def search_knowledge_graph(query: str, node_type: str = "Minutes") -> str:
    """지식 그래프에서 의미 기반으로 문서를 검색합니다.

    Args:
        query: 검색할 키워드 또는 자연어 쿼리
        node_type: 검색 대상 노드 타입 (Minutes / Agenda / HumanJudgment)
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
        parts.append(f"[{node_type}] {title}\n{content}\n(유사도 {score*100:.0f}%)")
    for r in extra[:2]:
        title = r.get("title") or ""
        content = r.get("content", "")[:250]
        score = float(r.get("score") or 0)
        parts.append(f"[KnowledgeChunk] {title}\n{content}\n(유사도 {score*100:.0f}%)")

    if not parts:
        return "관련 자료를 찾지 못했습니다."
    return "\n\n---\n\n".join(parts)


@tool
async def fetch_meeting_graph_context(meeting_id: int) -> str:
    """특정 회의체의 Neo4j 그래프 컨텍스트(안건·세션·구성원 등)를 조회합니다.

    Args:
        meeting_id: 조회할 회의체 ID (PostgreSQL PK)
    """
    from neo4j_client import get_meeting_graph_context, graph_context_to_str
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
    from neo4j_client import run_cypher

    if node_types is None:
        node_types = ["Agenda", "Minutes"]

    # 해당 회의체의 노드 수집
    nodes: List[dict] = []
    queries = {
        "Agenda":  "MATCH (n:Agenda {meeting_id: $mid}) RETURN n.id AS id, n.content AS content, 'Agenda' AS type",
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
        return {"proposal_id": None, "relationships": [], "message": "분석할 노드가 없습니다."}

    # LLM에게 노드 목록 전달 → 연결 관계 제안
    node_list_text = "\n".join([
        f"- [{r['type']}] id={r['id']}: {str(r.get('content', ''))[:100]}"
        for r in nodes
    ])
    llm = ChatOpenAI(model=MODEL, temperature=0.1, api_key=os.getenv("OPENAI_API_KEY"))
    response = await llm.ainvoke([
        SystemMessage(content="""회의체 온톨로지 분석 전문가입니다.
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
}"""),
        HumanMessage(content=f"회의체 ID: {meeting_id}\n\n노드 목록:\n{node_list_text}\n\n위 노드들 간에 연결해야 할 관계를 분석해 주세요."),
    ])

    try:
        import re as _re2
        _m = _re2.search(r'\{[\s\S]*\}', response.content)
        parsed = json.loads(_m.group(0)) if _m else {"relationships": []}
    except Exception:
        parsed = {"relationships": []}

    relationships = parsed.get("relationships", [])

    # 메모리에 임시 저장
    proposal_id = f"proposal-{uuid.uuid4().hex[:8]}"
    _proposals[proposal_id] = {
        "meeting_id": meeting_id,
        "relationships": relationships,
        "created_at": datetime.utcnow().isoformat(),
    }

    return {"proposal_id": proposal_id, "relationships": relationships}


async def confirm_relationships(
    proposal_id: str,
    approved: bool,
    reject_reason: str = None,
) -> dict:
    """제안된 관계를 승인하면 Neo4j에 MERGE, 반려하면 HumanJudgment 노드를 생성합니다.
    승인 반환: {status:"confirmed", relationships:[...]}
    반려 반환: {status:"rejected", human_judgment_id:str}
    """
    from neo4j_client import run_cypher

    proposal = _proposals.get(proposal_id)
    if not proposal:
        return {"status": "error", "message": "존재하지 않는 proposal_id입니다."}

    relationships = proposal["relationships"]
    meeting_id = proposal["meeting_id"]

    if approved:
        # 승인: 제안된 관계를 Neo4j에 MERGE
        merged = []
        for rel in relationships:
            try:
                await run_cypher(
                    f"""MATCH (a {{id: $from_id}})
                        MATCH (b {{id: $to_id}})
                        MERGE (a)-[:{rel['rel_type']}]->(b)""",
                    {"from_id": rel["from_id"], "to_id": rel["to_id"]},
                )
                merged.append(rel)
            except Exception:
                pass
        _proposals.pop(proposal_id, None)
        return {"status": "confirmed", "relationships": merged}

    else:
        # 반려: HumanJudgment 노드 생성 + humanJudgmentEmbedding 등록
        await ensure_vector_indexes()
        reason_text = reject_reason or "사유 없음"
        node_id = f"humanjudgment-{uuid.uuid4().hex[:8]}"
        embedding = await _embed(reason_text)
        created_at = datetime.utcnow().isoformat()
        try:
            await run_cypher(
                """MERGE (hj:HumanJudgment {id: $id})
                   SET hj.proposal_id = $proposal_id,
                       hj.meeting_id = $meeting_id,
                       hj.reason = $reason,
                       hj.decision = 'rejected',
                       hj.created_at = $created_at
                   WITH hj
                   CALL db.create.setNodeVectorProperty(hj, 'embedding', $embedding)
                   RETURN hj.id AS id""",
                {
                    "id": node_id,
                    "proposal_id": proposal_id,
                    "meeting_id": meeting_id,
                    "reason": reason_text,
                    "created_at": created_at,
                    "embedding": embedding,
                },
            )
        except Exception:
            pass
        _proposals.pop(proposal_id, None)
        return {"status": "rejected", "human_judgment_id": node_id}


# ── Helpers ────────────────────────────────────────────────────────────────
def _to_base_messages(messages: List[dict]) -> List[BaseMessage]:
    result = []
    for m in messages:
        role, content = m.get("role", ""), m.get("content", "")
        if role == "user":
            result.append(HumanMessage(content=content))
        elif role in ("assistant", "agent"):
            result.append(AIMessage(content=content))
    return result


# ── Graph ─────────────────────────────────────────────────────────────────
def _knowledge_state_modifier(state: KnowledgeState) -> List[BaseMessage]:
    """런타임 컨텍스트(knowledge·meeting_context)를 시스템 메시지로 주입합니다."""
    knowledge = state.get("knowledge", [])
    meeting_context = state.get("meeting_context", "")
    system = KNOWLEDGE_SYSTEM
    if meeting_context:
        system += f"\n\n[회의체 맥락]\n{meeting_context}"
    if knowledge:
        kb_text = "\n".join([
            f"- [{k.get('category','')}] {k.get('title','')}: {k.get('content','')[:100]}"
            for k in knowledge[:10]
        ])
        system += f"\n\n[Knowledge Base 현황]\n{kb_text}"
    return [SystemMessage(content=system)] + list(state.get("messages", []))


def _build_graph():
    """LangGraph create_react_agent — KNOWLEDGE_TOOLS를 도구로 사용하는 에이전트 그래프."""
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
_ORPHAN_ATTACH_THRESHOLD = 0.78


async def reconcile_graph(analysis: dict) -> dict:
    from neo4j_client import run_cypher

    sem    = analysis.get("semantic", {})
    struct = analysis.get("structural", {})
    member = analysis.get("membership", {})

    actions: List[dict] = []
    stats = {"session_links": 0, "lifecycle_links": 0, "carry_links": 0,
             "session_agenda_links": 0,
             "related_agendas": 0, "doc_refs": 0, "doc_attached": 0, "membership_fixed": 0,
             "pruned_links": 0}
    ts = datetime.utcnow().isoformat()

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
                actions.append({
                    "kind": "session_chain",
                    "detail": f"[{a_t}] → [{b_t}]" + (f" · {mg_title}" if mg_title else ""),
                    "evidence": "같은 회의체의 연속된 회차를 시간순으로 이어 회의의 흐름(맥락)을 복원했습니다.",
                    "highlight": pair.get("b_title") or None,
                })
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
                "MATCH (mn:Minutes {pg_id:$mid})-[:`생성`]->(s:Session {id:$sid})"
                "-[:`소속`|`개최`]->(mg:Meetings) "
                "WITH mn, s, mg "
                "CALL db.index.vector.queryNodes('agendaEmbedding', 5, $emb) YIELD node AS ag, score "
                "WHERE score >= 0.72 "
                "WITH mn, s, mg, ag, score "
                "WHERE (ag)-[:`관할`]->(mg) AND NOT (mn)-[:`도출`]->(ag) "
                "MERGE (mn)-[r:`도출`]->(ag) "
                "SET r.score=score, r.kind='minutes_agenda', r.discovered_by='knowledge_agent', r.discovered_at=$ts "
                "MERGE (ag)-[r2:`다룸`]->(s) "
                "SET r2.score=score, r2.kind='session_agenda', r2.discovered_by='knowledge_agent', r2.discovered_at=$ts "
                "RETURN ag.title AS title, score",
                {"sid": sid, "emb": emb, "mid": mid, "ts": ts},
            )
            if rows:
                linked = [r.get("title", "?") for r in rows]
                actions.append({
                    "kind": "lifecycle",
                    "detail": f"〔{session_title}〕 → 안건 {len(linked)}개: {', '.join(f'[{t}]' for t in linked[:3])}",
                    "evidence": "회의록 내용과 안건을 임베딩으로 연결, 회의→회의록→안건 생명주기를 이었습니다.",
                    "highlight": session_title,
                })
                stats["lifecycle_links"] += len(rows)
        except Exception:
            pass

    # ①-b 이월(carry-forward)
    try:
        cf = await run_cypher(
            "MATCH (s:Session)-[:`소속`|`개최`]->(mg:Meetings)<-[:`관할`]-(ag:Agenda) "
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
            actions.append({
                "kind": "lifecycle",
                "detail": f"미해결 안건 {n}건을 다음 회차로 이월",
                "evidence": "아직 끝나지 않은 안건을 가장 최근 회차와 연결해 생명주기를 다음 회의로 이어줬습니다(안건→회의).",
                "highlight": None,
            })
    except Exception:
        pass

    # ①-c 세션 → 안건 직접 연결 보완 (원칙: 회의는 아젠다와 연결되어야 한다)
    try:
        # 1단계: 발제세션 역방향 보완 — (ag)-[:발제세션]->(s) 가 있으면 (s)-[:진행]->(ag) 도 있어야 함
        direct_rows = await run_cypher(
            "MATCH (ag:Agenda)-[:`발제세션`]->(s:Session) "
            "WHERE NOT (s)-[:`진행`]->(ag) "
            "MERGE (s)-[r:`진행`]->(ag) "
            "SET r.kind='session_agenda_direct', r.discovered_by='knowledge_agent', r.discovered_at=$ts "
            "RETURN count(r) AS n",
            {"ts": ts},
        )
        direct_n = direct_rows[0].get("n", 0) if direct_rows else 0

        # 2단계: 발제세션 링크 없이 회의체 내 떠 있는 안건을 같은 회의체의 세션과 연결
        floating_rows = await run_cypher(
            "MATCH (s:Session)-[:`소속`|`개최`]->(mg:Meetings)<-[:`관할`]-(ag:Agenda) "
            "WHERE NOT (ag)-[:`발제세션`]->(:Session) "
            "  AND NOT (s)-[:`진행`|`다룸`|`도출`]->(ag) "
            "  AND NOT coalesce(ag.status,'') IN ['DONE','COMPLETED','CLOSED','RESOLVED'] "
            "WITH s, ag LIMIT 200 "
            "MERGE (s)-[r:`진행`]->(ag) "
            "SET r.kind='session_agenda_group', r.discovered_by='knowledge_agent', r.discovered_at=$ts "
            "RETURN count(r) AS n",
            {"ts": ts},
        )
        floating_n = floating_rows[0].get("n", 0) if floating_rows else 0

        total_n = direct_n + floating_n
        if total_n:
            stats["session_agenda_links"] = total_n
            actions.append({
                "kind": "session_agenda",
                "detail": f"세션→안건 연결 {total_n}건 (직접 {direct_n}건 + 그룹 {floating_n}건)",
                "evidence": "회의(세션)는 아젠다와 연결되어야 한다는 원칙에 따라 미연결 세션-안건 쌍을 이어줬습니다.",
                "highlight": None,
            })
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
                {"a": a_id, "b": b_id, "score": round(link.get("score", 0.0), 4), "ts": ts},
            )
            pct = link.get("score", 0.0) * 100
            actions.append({
                "kind": "related",
                "detail": f"[{link.get('a_title','?')}] ↔ [{link.get('b_title','?')}]",
                "evidence": (f"'{link.get('a_mg','')}' 회의의 안건과 '{link.get('b_mg','')}' 회의의 안건이 "
                             f"의미상 {pct:.0f}% 유사 — 회의 경계를 넘는 지식 연결을 생성했습니다."),
                "highlight": link.get("a_title"),
            })
            stats["related_agendas"] += 1
        except Exception:
            pass

    # ② 문서 ↔ 안건 적합 → `참조` 링크
    for link in sem.get("doc_links", []):
        d_id, ag_id = link.get("doc_id"), link.get("ag_id")
        if not d_id or not ag_id:
            continue
        try:
            await run_cypher(
                "MATCH (d {id:$d}), (a:Agenda {id:$a}) WHERE d:Report OR d:Minutes "
                "MERGE (d)-[r:`참조`]->(a) "
                "SET r.score = $score, r.discovered_by = 'knowledge_agent', r.discovered_at = $ts",
                {"d": d_id, "a": ag_id, "score": round(link.get("score", 0.0), 4), "ts": ts},
            )
            pct = link.get("score", 0.0) * 100
            actions.append({
                "kind": "doc_ref",
                "detail": f"문서 [{link.get('doc_title','?')}] → 안건 [{link.get('ag_title','?')}]",
                "evidence": f"문서 내용이 해당 안건과 {pct:.0f}% 부합 — '참조' 관계로 연결했습니다.",
                "highlight": link.get("ag_title"),
            })
            stats["doc_refs"] += 1
        except Exception:
            pass

    # ③ 고아 문서 → 임베딩으로 가장 적합한 안건에 `첨부`
    for doc in struct.get("orphan_documents", []):
        if not doc.get("emb") or not doc.get("id"):
            continue
        try:
            rows = await run_cypher(
                "MATCH (d {id:$id}) WHERE (d:Report OR d:Minutes) AND d.embedding IS NOT NULL "
                "CALL db.index.vector.queryNodes('agendaEmbedding', 1, d.embedding) "
                "YIELD node, score "
                "WITH d, node, score WHERE score >= $th "
                "MERGE (d)-[r:`첨부`]->(node) "
                "SET r.auto_linked = true, r.score = score, r.discovered_at = $ts "
                "RETURN node.title AS title, score",
                {"id": doc["id"], "th": _ORPHAN_ATTACH_THRESHOLD, "ts": ts},
            )
            if rows:
                title = rows[0].get("title", "?")
                score = float(rows[0].get("score") or 0.0)
                actions.append({
                    "kind": "doc_attach",
                    "detail": f"고아 문서 [{doc.get('title','?')}] → 안건 [{title}]",
                    "evidence": (f"어디에도 연결되지 않던 문서를 의미상 가장 가까운 안건"
                                 f"(유사도 {score*100:.0f}%)에 자동 편입했습니다."),
                    "highlight": title,
                })
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
                    "MERGE (p)-[:`소속`]->(d) DELETE r", {"pid": pid})
                actions.append({"kind": "membership", "detail": f"{name} → {dept}",
                                "evidence": "구버전 소속 관계를 표준 형식으로 정리했습니다.",
                                "highlight": name})
            elif itype == "missing":
                await run_cypher(
                    "MATCH (p:User {id:$pid}) MERGE (d:Department {name:$dept}) "
                    "MERGE (p)-[:`소속`]->(d)", {"pid": pid, "dept": dept})
                actions.append({"kind": "membership", "detail": f"{name} → {dept}",
                                "evidence": f"누락된 '{dept}' 소속 연결을 복구했습니다('미지정' 해소).",
                                "highlight": name})
            elif itype == "mismatch":
                await run_cypher(
                    "MATCH (p:User {id:$pid})-[r:`소속`]->(d:Department) "
                    "WHERE d.name <> $dept DELETE r", {"pid": pid, "dept": dept})
                await run_cypher(
                    "MATCH (p:User {id:$pid}) MERGE (d:Department {name:$dept}) "
                    "MERGE (p)-[:`소속`]->(d)", {"pid": pid, "dept": dept})
                actions.append({"kind": "membership", "detail": f"{name} → {dept}",
                                "evidence": f"프로필과 다르게 '{current}'로 연결됐던 소속을 '{dept}'로 교정했습니다.",
                                "highlight": name})
            stats["membership_fixed"] += 1
        except Exception:
            pass

    # ① 불필요한 연결 정제 — stale/weak 자동 생성 관계 제거
    for link in struct.get("stale_links", []):
        kind    = link.get("kind")
        from_id = link.get("from_id")
        to_id   = link.get("to_id")
        rel     = link.get("rel", "")
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
                await run_cypher(
                    "MATCH (a {id:$fid})-[r:`참조`]->(b:Agenda {id:$tid}) "
                    "WHERE (a:Report OR a:Minutes) AND r.discovered_by = 'knowledge_agent' DELETE r",
                    {"fid": from_id, "tid": to_id},
                )
            elif kind == "weak_attach":
                await run_cypher(
                    "MATCH (a {id:$fid})-[r:`첨부`]->(b:Agenda {id:$tid}) "
                    "WHERE (a:Report OR a:Minutes) AND r.auto_linked = true DELETE r",
                    {"fid": from_id, "tid": to_id},
                )
            evidence = {
                "stale_carry":     "완료된 안건에 달린 이월 관계를 정리했습니다.",
                "stale_lifecycle": "완료된 안건과 연결된 회의록 도출 관계를 정리했습니다.",
                "weak_related":    f"임계값 미달({link.get('score',0)*100:.0f}%) 자동 '관련' 링크를 지웠습니다.",
                "weak_ref":        f"임계값 미달({link.get('score',0)*100:.0f}%) 자동 '참조' 링크를 지웠습니다.",
                "weak_attach":     f"임계값 미달({link.get('score',0)*100:.0f}%) 자동 '첨부' 링크를 지웠습니다.",
            }.get(kind, "불필요한 연결을 제거했습니다.")
            actions.append({
                "kind": "pruned",
                "detail": link.get("label", "?"),
                "evidence": evidence,
                "highlight": None,
            })
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
    stats     = report.get("stats", {})
    actions   = report.get("actions", [])
    advisories = report.get("advisories", {})
    counts    = report.get("counts", {})
    findings  = report.get("findings", {})

    act_lines = []
    for a in actions[:40]:
        tag = {"session_chain": "🧵 회차 연결", "lifecycle": "🔄 생명주기", "related": "🔗 회의 간 연결",
               "doc_ref": "📎 문서 참조", "doc_attach": "🧩 고아 문서 편입",
               "membership": "👤 소속 보정"}.get(a.get("kind"), "•")
        act_lines.append(f"- {tag} | {a.get('detail','')} — {a.get('evidence','')}")
    act_block = "\n".join(act_lines) if act_lines else "(이번에 새로 만든 연결 없음)"

    adv_lines = []
    own = advisories.get("ownerless_agendas", [])
    if own:
        sample = ", ".join(f"[{o.get('title','?')}]" for o in own[:5])
        adv_lines.append(f"- 담당자 미지정 안건 {len(own)}건: {sample}{' 외' if len(own) > 5 else ''}")
    mls = advisories.get("minuteless_sessions", [])
    if mls:
        adv_lines.append(f"- 회의록이 없는 세션 {len(mls)}건")
    iso = advisories.get("isolated_persons", [])
    if iso:
        sample = ", ".join(p.get("name", "?") for p in iso[:5])
        adv_lines.append(f"- 어떤 활동에도 연결되지 않은 구성원 {len(iso)}명: {sample}{' 외' if len(iso) > 5 else ''}")
    adv_block = "\n".join(adv_lines) if adv_lines else "(없음)"

    llm = _make_llm(temperature=0.2)
    async for chunk in llm.astream([
        SystemMessage(content=RELATIONSHIP_SUMMARY_SYSTEM),
        HumanMessage(content=relationship_summary_human(counts, findings, stats, act_block, adv_block)),
    ]):
        if chunk.content:
            yield chunk.content
