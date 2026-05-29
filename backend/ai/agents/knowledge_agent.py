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

MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")


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
        api_key=os.getenv("OPENAI_API_KEY"),
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
        # 과제 벡터 인덱스
        """CREATE VECTOR INDEX task_embedding_index IF NOT EXISTS
           FOR (t:KnowledgeTask) ON (t.embedding)
           OPTIONS {indexConfig: {
             `vector.dimensions`: 1536,
             `vector.similarity_function`: 'cosine'
           }}""",
        # 보고서 벡터 인덱스
        """CREATE VECTOR INDEX report_embedding_index IF NOT EXISTS
           FOR (r:KnowledgeReport) ON (r.embedding)
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
    embeddings = OpenAIEmbeddings(api_key=os.getenv("OPENAI_API_KEY"))
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
    """승인된 과제를 Neo4j에 저장하고 벡터 임베딩을 인덱싱합니다."""
    from neo4j_client import run_cypher

    await ensure_vector_indexes()
    node_id = f"task-{uuid.uuid4().hex[:8]}"
    embedding = await _embed(content)
    created_at = datetime.utcnow().isoformat()

    await run_cypher(
        """MERGE (t:KnowledgeTask {id: $id})
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

    # 부서 노드와 연결
    if department:
        try:
            await run_cypher(
                """MATCH (t:KnowledgeTask {id: $tid})
                   MERGE (d:Department {name: $dept})
                   MERGE (t)-[:ASSIGNED_TO_DEPT]->(d)""",
                {"tid": node_id, "dept": department},
            )
        except Exception:
            pass

    return {"id": node_id, "status": "stored", "node_type": "KnowledgeTask"}


async def store_report(
    title: str,
    content: str,
    meeting_id: int = None,
    score: int = None,
) -> dict:
    """승인된 보고서 검토 결과를 Neo4j에 저장하고 벡터 임베딩을 인덱싱합니다."""
    from neo4j_client import run_cypher

    await ensure_vector_indexes()
    node_id = f"report-{uuid.uuid4().hex[:8]}"
    embedding = await _embed(content)
    created_at = datetime.utcnow().isoformat()

    await run_cypher(
        """MERGE (r:KnowledgeReport {id: $id})
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

    if meeting_id:
        try:
            await run_cypher(
                """MATCH (r:KnowledgeReport {id: $rid})
                   MATCH (mg:Meeting {pg_id: $pg_id})
                   MERGE (r)-[:BELONGS_TO]->(mg)""",
                {"rid": node_id, "pg_id": meeting_id},
            )
        except Exception:
            pass

    return {"id": node_id, "status": "stored", "node_type": "KnowledgeReport"}


async def search_knowledge(query: str, node_type: str = "Minutes", k: int = 5) -> List[dict]:
    """Neo4j 벡터 검색으로 유사 지식을 조회합니다 (Cypher 기반)."""
    from neo4j_client import run_cypher

    index_map = {
        "Minutes": "minutes_embedding_index",
        "KnowledgeTask": "task_embedding_index",
        "KnowledgeReport": "report_embedding_index",
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
