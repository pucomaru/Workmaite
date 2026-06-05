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

    # 부서 노드와 연결: (KnowledgeTask)-[:ASSIGNED_TO_DEPT]->(Department)
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

    # 회의체 노드와 연결: (KnowledgeTask)-[:BELONGS_TO]->(Meeting)
    if meeting_id:
        try:
            await run_cypher(
                """MATCH (t:KnowledgeTask {id: $tid})
                   MATCH (mg:Meeting {pg_id: $pg_id})
                   MERGE (t)-[:BELONGS_TO]->(mg)""",
                {"tid": node_id, "pg_id": meeting_id},
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


# ── 지식 그래프 관리(재구성) ──────────────────────────────────────────────────
# [KnowledgeAgent 역할 = 관리]
# Supervisor가 "분석"하여 발굴한 잠재 연결·구조 공백을 받아, Neo4j 그래프를
# 실제로 재구성(관리)합니다. 발굴·분석은 Supervisor가, 변경·관리는 KnowledgeAgent가 담당.
#   ① 회의 간 의미 유사 안건 → `관련` 지식 링크 생성 (유사도 점수 기록)
#   ② 문서 ↔ 안건 적합 → `참조` 링크 생성
#   ③ 고아 문서 → 임베딩으로 가장 적합한 안건 탐색 후 `첨부` 자동 연결
#   ④ 소속 무결성(baseline) 보정
_ORPHAN_ATTACH_THRESHOLD = 0.78  # 고아 문서 자동 연결 임계값 (cosine)


async def reconcile_graph(analysis: dict) -> dict:
    """[관리 역할] Supervisor가 분석한 잠재 연결·구조 공백을 Neo4j에 실제 반영합니다.

    Args:
        analysis: Supervisor `_analyze_graph()` 결과
            { "semantic": {"agenda_links":[...], "doc_links":[...]},
              "structural": {"orphan_documents":[...], ...},
              "membership": {"issues":[...]}, "counts": {...} }

    Returns:
        { "actions":  [ {kind, detail, evidence, highlight}, ... ],
          "stats":    {related_agendas, doc_refs, doc_attached, membership_fixed},
          "advisories": {ownerless_agendas, minuteless_sessions, isolated_persons} }
    """
    from neo4j_client import run_cypher

    sem    = analysis.get("semantic", {})
    struct = analysis.get("structural", {})
    member = analysis.get("membership", {})

    actions: List[dict] = []
    stats = {"session_links": 0, "lifecycle_links": 0, "carry_links": 0,
             "related_agendas": 0, "doc_refs": 0, "doc_attached": 0, "membership_fixed": 0}
    ts = datetime.utcnow().isoformat()

    # ⓪ 구조 골격 — 같은 회의체 세션 시간순 '후속' 체인 (1차→2차→3차)
    # Supervisor가 시간순으로 정렬해 넘긴 '끊긴 회차' 쌍을 이어 회의 흐름을 복원합니다.
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

    # ① 회의 생명주기 — Minutes → Agenda 브릿지 (임베딩 기반)
    # Supervisor가 넘긴 '미연결 회의록' 본문을 임베딩해
    # 같은 회의체 안건 중 의미상 가까운 것에 Minutes-[도출]->Agenda 관계를 생성.
    # Decision 노드 없이 회의→회의록→안건→다음 회의 순환을 닫습니다.
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
                "-[:`소속`|`개최`]->(mg:MeetingGroup) "
                "WITH mn, mg "
                "CALL db.index.vector.queryNodes('agendaEmbedding', 5, $emb) YIELD node AS ag, score "
                "WHERE score >= 0.72 "
                "WITH mn, mg, ag, score "
                "WHERE (ag)-[:`관할`]->(mg) AND NOT (mn)-[:`도출`]->(ag) "
                "MERGE (mn)-[r:`도출`]->(ag) "
                "SET r.score=score, r.kind='minutes_agenda', r.discovered_by='knowledge_agent', r.discovered_at=$ts "
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

    # ①-b 이월(carry-forward) — 미해결 안건을 각 회의체의 최신 회차에 `도출`로 연결 (안건→다음 회의)
    try:
        cf = await run_cypher(
            "MATCH (s:Session)-[:`소속`|`개최`]->(mg:MeetingGroup)<-[:`관할`]-(ag:Agenda) "
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
                "MATCH (d:Document {id:$d}), (a:Agenda {id:$a}) "
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

    # ③ 고아 문서 → 임베딩으로 가장 적합한 안건에 `첨부` 자동 연결
    for doc in struct.get("orphan_documents", []):
        if not doc.get("emb") or not doc.get("id"):
            continue
        try:
            rows = await run_cypher(
                "MATCH (d:Document {id:$id}) WHERE d.embedding IS NOT NULL "
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
                    "MATCH (p:Person {id:$pid})-[r:`소속부서`]->(d:Department) "
                    "MERGE (p)-[:`소속`]->(d) DELETE r", {"pid": pid})
                actions.append({"kind": "membership", "detail": f"{name} → {dept}",
                                "evidence": "구버전 소속 관계를 표준 형식으로 정리했습니다.",
                                "highlight": name})
            elif itype == "missing":
                await run_cypher(
                    "MATCH (p:Person {id:$pid}) MERGE (d:Department {name:$dept}) "
                    "MERGE (p)-[:`소속`]->(d)", {"pid": pid, "dept": dept})
                actions.append({"kind": "membership", "detail": f"{name} → {dept}",
                                "evidence": f"누락된 '{dept}' 소속 연결을 복구했습니다('미지정' 해소).",
                                "highlight": name})
            elif itype == "mismatch":
                await run_cypher(
                    "MATCH (p:Person {id:$pid})-[r:`소속`]->(d:Department) "
                    "WHERE d.name <> $dept DELETE r", {"pid": pid, "dept": dept})
                await run_cypher(
                    "MATCH (p:Person {id:$pid}) MERGE (d:Department {name:$dept}) "
                    "MERGE (p)-[:`소속`]->(d)", {"pid": pid, "dept": dept})
                actions.append({"kind": "membership", "detail": f"{name} → {dept}",
                                "evidence": f"프로필과 다르게 '{current}'로 연결됐던 소속을 '{dept}'로 교정했습니다.",
                                "highlight": name})
            stats["membership_fixed"] += 1
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
    """[관리 역할] Supervisor 분석 → KnowledgeAgent 재구성 결과를 근거와 함께 보고합니다."""
    stats     = report.get("stats", {})
    actions   = report.get("actions", [])
    advisories = report.get("advisories", {})
    counts    = report.get("counts", {})
    findings  = report.get("findings", {})

    # 실제 적용된 재구성 내역 (근거 포함)
    act_lines = []
    for a in actions[:40]:
        tag = {"session_chain": "🧵 회차 연결", "lifecycle": "🔄 생명주기", "related": "🔗 회의 간 연결",
               "doc_ref": "📎 문서 참조", "doc_attach": "🧩 고아 문서 편입",
               "membership": "👤 소속 보정"}.get(a.get("kind"), "•")
        act_lines.append(f"- {tag} | {a.get('detail','')} — {a.get('evidence','')}")
    act_block = "\n".join(act_lines) if act_lines else "(이번에 새로 만든 연결 없음)"

    # 자동으로 고칠 수 없어 사용자 확인이 필요한 공백
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

    system = (
        "당신은 조직의 지식 그래프를 책임지는 KnowledgeAgent입니다. "
        "Supervisor가 '분석'해 넘긴 결과를, 당신이 직접 그래프에 '재구성'한 결과를 사용자에게 보고합니다.\n"
        "[작성 원칙]\n"
        "1. 기술 용어(Cypher, 노드, 임베딩 차원 등) 금지 — '회의 흐름', '의미 유사도', '회의 간 연결' 같은 업무 언어 사용\n"
        "2. 보고 우선순위: ① 가장 기본인 '회의 흐름'(같은 회의체 1차→2차→3차 세션 연결), "
        "② '회의 생명주기'(회의록이 안건과 이어졌는지 — 회의→회의록→안건→다음 회의)를 다루고, "
        "그다음 ③ 회의 경계를 넘는 의미 기반 연결을 설명하세요\n"
        "3. 핵심은 '흩어져 있던 회의 지식을 어떻게 이어 붙였는지'입니다. 단순 정합성 점검처럼 보고하지 말 것\n"
        "4. 다음 순서로 간결하게:\n"
        "   📊 분석 요약 (무엇을 훑었고 무엇을 발견했는지)\n"
        "   🧵 회의 흐름 복원 (세션 시간순 연결)\n"
        "   🔄 회의 생명주기 복원 (회의록이 안건과 이어졌는지 확인·연결)\n"
        "   🔗 회의 간 새 지식 연결 (실제 사례와 유사도를 근거로)\n"
        "   ⚠️ 사용자 확인이 필요한 공백 (자동으로 메울 수 없는 부분)\n"
        "   ✅ 결과 한 줄 요약\n"
        "5. 발견·연결이 하나도 없으면 '이미 충분히 연결돼 있다'고 안내\n"
        "6. 정중하고 명확한 비서 말투"
    )
    human = (
        f"[Supervisor 분석 범위]\n"
        f"- 회의 {counts.get('meetings',0)}개 · 세션 {counts.get('sessions',0)}개 · "
        f"안건 {counts.get('agendas',0)}개 · 문서 {counts.get('documents',0)}개 · 구성원 {counts.get('persons',0)}명\n\n"
        f"[Supervisor 발굴 결과]\n"
        f"- 끊긴 회의 흐름(세션 미연결): {findings.get('session_missing',0)}건 "
        f"(회의체 {findings.get('session_groups',0)}곳)\n"
        f"- 회의록→안건 미연결: {findings.get('lifecycle_gaps',0)}건\n"
        f"- 회의 간 잠재 연관 안건: {findings.get('agenda_links',0)}쌍\n"
        f"- 미연결 문서-안건 적합쌍: {findings.get('doc_links',0)}건\n"
        f"- 담당자 없는 안건: {findings.get('ownerless',0)}건 / 고아 문서: {findings.get('orphans',0)}건\n\n"
        f"[KnowledgeAgent 재구성 통계]\n"
        f"- 회의 흐름(세션) '후속' 연결: {stats.get('session_links',0)}건\n"
        f"- 회의록→안건 연결(생명주기): {stats.get('lifecycle_links',0)}건\n"
        f"- 미해결 안건 다음 회차 이월: {stats.get('carry_links',0)}건\n"
        f"- 회의 간 '관련' 링크 생성: {stats.get('related_agendas',0)}건\n"
        f"- 문서 '참조' 링크 생성: {stats.get('doc_refs',0)}건\n"
        f"- 고아 문서 자동 편입: {stats.get('doc_attached',0)}건\n"
        f"- 소속 무결성 보정: {stats.get('membership_fixed',0)}건\n\n"
        f"[재구성 상세 내역 및 근거]\n{act_block}\n\n"
        f"[사용자 확인 필요 — 자동 보완 불가]\n{adv_block}\n\n"
        "위 결과를 사용자에게 보고해 주세요."
    )

    llm = _make_llm(temperature=0.2)
    async for chunk in llm.astream([SystemMessage(content=system), HumanMessage(content=human)]):
        if chunk.content:
            yield chunk.content
