# 지식 정제 Agent - 승인된 회의록·과제·보고서를 Neo4j에 저장하고 Knowledge Base를 자동 업데이트
# 벡터 인덱싱: Neo4j 5.19 내장 벡터 검색 사용 (Cypher 기반, pgvector 미사용)
import os, json, re, uuid
from datetime import datetime
from typing import AsyncGenerator, List, Optional, Annotated
from typing_extensions import TypedDict

from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_core.messages import BaseMessage, SystemMessage, HumanMessage, AIMessage
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from pydantic import BaseModel, Field

MODEL = os.environ["OPENAI_MODEL"]


# ── State ─────────────────────────────────────────────────────────────────
class KnowledgeState(TypedDict):
    messages: Annotated[List[BaseMessage], add_messages]
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


SYSTEM_PROMPT = """당신은 조직 지식 관리 전문 AI KnowledgeAgent입니다.
- 승인된 회의록·과제·보고서를 Neo4j Knowledge Base에 정제·저장합니다
- 조직의 패턴과 암묵지를 분석해 인사이트를 제공합니다
- 지식 그래프에서 연관 정보를 검색하고 요약합니다
한국어로 응답합니다."""


# ── Neo4j 벡터 인덱스 관리 ─────────────────────────────────────────────────
async def ensure_vector_indexes() -> None:
    """Neo4j 5.19 내장 벡터 인덱스가 없으면 Cypher로 생성합니다."""
    from neo4j_client import run_cypher

    index_queries = [
        # 회의록 벡터 인덱스
        """CREATE VECTOR INDEX minutes_embedding_index IF NOT EXISTS
           FOR (m:Minutes) ON (m.embedding)
           OPTIONS {indexConfig: {
             `vector.dimensions`: 1536,
             `vector.similarity_function`: 'cosine'
           }}""",
        # 과제(Agenda) 벡터 인덱스 — PM 스키마: agendaEmbedding
        """CREATE VECTOR INDEX agendaEmbedding IF NOT EXISTS
           FOR (t:Agenda) ON (t.embedding)
           OPTIONS {indexConfig: {
             `vector.dimensions`: 1536,
             `vector.similarity_function`: 'cosine'
           }}""",
        # AI 보고서 검토 결과(AIJudgment) 벡터 인덱스 — PM 스키마: aiJudgmentEmbedding
        """CREATE VECTOR INDEX aiJudgmentEmbedding IF NOT EXISTS
           FOR (r:AIJudgment) ON (r.embedding)
           OPTIONS {indexConfig: {
             `vector.dimensions`: 1536,
             `vector.similarity_function`: 'cosine'
           }}""",
        # 사람 판단(HumanJudgment) 벡터 인덱스 — PM 스키마: humanJudgmentEmbedding
        """CREATE VECTOR INDEX humanJudgmentEmbedding IF NOT EXISTS
           FOR (hj:HumanJudgment) ON (hj.embedding)
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
    """승인된 회의록을 Neo4j에 저장하고 벡터 임베딩을 인덱싱합니다."""
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

    # 회의체와 연결
    if meeting_id:
        try:
            await run_cypher(
                """MATCH (m:Minutes {id: $mid})
                   MATCH (mg:Meeting {pg_id: $pg_id})
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
    """승인된 과제를 Neo4j Agenda 노드에 저장하고 벡터 임베딩을 인덱싱합니다."""
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

    # 부서 노드와 연결: (Agenda)-[:ASSIGNED_TO_DEPT]->(Department)
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

    # 회의체 노드와 연결: (Agenda)-[:BELONGS_TO]->(Meeting)
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
    """승인된 보고서 검토 결과를 Neo4j AIJudgment 노드에 저장하고 벡터 임베딩을 인덱싱합니다."""
    from neo4j_client import run_cypher

    await ensure_vector_indexes()
    node_id = f"aijudgment-{uuid.uuid4().hex[:8]}"
    embedding = await _embed(content)
    created_at = datetime.utcnow().isoformat()

    await run_cypher(
        """MERGE (r:AIJudgment {id: $id})
           SET r.title = $title,
               r.content = $content,
               r.meeting_id = $meeting_id,
               r.score = $score,
               r.created_at = $created_at
           WITH r
           CALL db.create.setNodeVectorProperty(r, 'embedding', $embedding)
           RETURN r.id AS id""",
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

    # 회의체 노드와 연결: (AIJudgment)-[:BELONGS_TO]->(Meeting)
    if meeting_id:
        try:
            await run_cypher(
                """MATCH (r:AIJudgment {id: $rid})
                   MATCH (mg:Meeting {pg_id: $pg_id})
                   MERGE (r)-[:BELONGS_TO]->(mg)""",
                {"rid": node_id, "pg_id": meeting_id},
            )
        except Exception:
            pass

    return {"id": node_id, "status": "stored", "node_type": "AIJudgment"}


async def search_knowledge(query: str, node_type: str = "Minutes", k: int = 5) -> List[dict]:
    """Neo4j 벡터 검색으로 유사 지식을 조회합니다 (Cypher 기반)."""
    from neo4j_client import run_cypher

    # PM 스키마 기준 인덱스명으로 통일
    index_map = {
        "Minutes": "minutes_embedding_index",
        "Agenda": "agendaEmbedding",
        "AIJudgment": "aiJudgmentEmbedding",
        "HumanJudgment": "humanJudgmentEmbedding",
    }
    index_name = index_map.get(node_type, "minutes_embedding_index")
    embedding = await _embed(query)

    try:
        rows = await run_cypher(
            f"""CALL db.index.vector.queryNodes('{index_name}', $k, $embedding)
                YIELD node, score
                RETURN node.title AS title, node.content AS content,
                       node.meeting_id AS meeting_id, score
                ORDER BY score DESC""",
            {"k": k, "embedding": embedding},
        )
        return rows
    except Exception:
        return []


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
        node_types = ["Agenda", "AIJudgment", "Minutes"]

    # 해당 회의체의 노드 수집
    nodes: List[dict] = []
    queries = {
        "Agenda":      "MATCH (n:Agenda {meeting_id: $mid}) RETURN n.id AS id, n.content AS content, 'Agenda' AS type",
        "AIJudgment":  "MATCH (n:AIJudgment {meeting_id: $mid}) RETURN n.id AS id, n.title AS content, 'AIJudgment' AS type",
        "Minutes":     "MATCH (n:Minutes {meeting_id: $mid}) RETURN n.id AS id, n.title AS content, 'Minutes' AS type",
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


# ── Graph nodes ────────────────────────────────────────────────────────────
async def _chat_node(state: KnowledgeState) -> dict:
    knowledge = state.get("knowledge", [])
    meeting_context = state.get("meeting_context", "")

    system = SYSTEM_PROMPT
    if meeting_context:
        system += f"\n\n[회의체 맥락]\n{meeting_context}"
    if knowledge:
        kb_text = "\n".join([f"- [{k.get('category','')}] {k.get('title','')}: {k.get('content','')[:100]}" for k in knowledge[:10]])
        system += f"\n\n[Knowledge Base 현황]\n{kb_text}"

    llm = _make_llm()
    response = await llm.ainvoke([SystemMessage(content=system)] + state["messages"])
    return {"messages": [response]}


# ── Graph ─────────────────────────────────────────────────────────────────
def _build_graph():
    builder = StateGraph(KnowledgeState)
    builder.add_node("chat", _chat_node)
    builder.add_edge(START, "chat")
    builder.add_edge("chat", END)
    return builder.compile()

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
