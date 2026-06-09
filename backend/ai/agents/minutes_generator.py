import os, uuid, re as _re, json as _json
from typing import AsyncGenerator, List, Optional, Annotated
from typing_extensions import TypedDict

from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_core.messages import BaseMessage, SystemMessage, HumanMessage, AIMessage
from langchain_core.tools import tool
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.managed import RemainingSteps
from langgraph.prebuilt import create_react_agent
from pydantic import BaseModel, Field

from routers.prompts import MINUTES_SYSTEM, generate_minutes_system, generate_minutes_human

MODEL = os.environ["OPENAI_MODEL"]


# ── State ─────────────────────────────────────────────────────────────────
class MinutesState(TypedDict):
    messages: Annotated[List[BaseMessage], add_messages]
    remaining_steps: RemainingSteps
    previous_minutes: List[str]
    current_agendas: List[dict]
    meeting_context: str


# ── Pydantic schemas ──────────────────────────────────────────────────────
class MinutesSection(BaseModel):
    title: str = Field(..., description="섹션 제목")
    content: str = Field(..., description="섹션 내용")


class MeetingMinutes(BaseModel):
    summary: str = Field(..., description="회의 요약 (3-5줄)")
    sections: List[MinutesSection] = Field(default_factory=list, description="주요 논의/결정/과제 섹션")


# ── LLM ───────────────────────────────────────────────────────────────────
def _make_llm(temperature: float = 0.3) -> ChatOpenAI:
    return ChatOpenAI(
        model=MODEL,
        temperature=temperature,
        api_key=os.environ["OPENAI_API_KEY"],
        streaming=True,
    )


# ── Neo4j 벡터 검색 (유사 회의록) ────────────────────────────────────────
async def _search_similar_minutes(text: str, k: int = 3) -> List[str]:
    try:
        from neo4j_client import run_cypher
        embeddings = OpenAIEmbeddings(api_key=os.environ["OPENAI_API_KEY"])
        query_vec = await embeddings.aembed_query(text[:500])

        rows = await run_cypher(
            """CALL db.index.vector.queryNodes('minutes_embedding_index', $k, $embedding)
               YIELD node, score
               RETURN node.content AS content, node.title AS title, score
               ORDER BY score DESC""",
            {"k": k, "embedding": query_vec},
        )
        return [
            f"[{r.get('title', '유사 회의록')}]\n{r.get('content', '')}"
            for r in rows if r.get("content")
        ]
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


def _build_context_prompt(
    previous_minutes: List[str],
    current_agendas: List[dict],
    meeting_context: str = "",
) -> Optional[str]:
    parts = []
    if meeting_context:
        parts.append(f"[회의체 맥락]\n{meeting_context}")
    if previous_minutes:
        parts.append("[이전/유사 회의 요약]\n" + "\n".join(previous_minutes[:2]))
    if current_agendas:
        agenda_text = "\n".join([f"- {a.get('content','')}" for a in current_agendas])
        parts.append(f"[현재 아젠다]\n{agenda_text}")
    return "\n\n".join(parts) if parts else None


# ── Tools ──────────────────────────────────────────────────────────────────────
@tool
async def search_similar_minutes_tool(query: str) -> str:
    """이전 회의에서 유사한 회의록 내용을 검색합니다.

    Args:
        query: 현재 회의 주제나 논의 내용 요약
    """
    from agents.knowledge_manager import search_knowledge
    results = await _search_similar_minutes(query, k=3)
    chunk_results = await search_knowledge(query, node_type="MinutesChunk", k=2)
    all_results = results + [r.get("content", "") for r in chunk_results if r.get("content")]
    if not all_results:
        return "유사한 이전 회의록을 찾지 못했습니다."
    return "\n\n---\n\n".join(all_results[:3])


@tool
async def get_agenda_status(query: str) -> str:
    """현재 진행 중이거나 보류된 안건을 검색합니다.

    Args:
        query: 관련 안건 주제나 키워드
    """
    from agents.knowledge_manager import search_knowledge
    results = await search_knowledge(query, node_type="Agenda", k=5)
    if not results:
        return "관련 안건을 찾지 못했습니다."
    lines = [
        f"- {r.get('title','?')}: {r.get('content','')[:150]}"
        for r in results[:4]
    ]
    return "\n".join(lines)


MINUTES_TOOLS: list = [search_similar_minutes_tool, get_agenda_status]


# ── Graph ─────────────────────────────────────────────────────────────────
def _minutes_state_modifier(state: MinutesState) -> List[BaseMessage]:
    """런타임 컨텍스트(previous_minutes·current_agendas·meeting_context)를 시스템 메시지로 주입합니다."""
    context = _build_context_prompt(
        state.get("previous_minutes", []),
        state.get("current_agendas", []),
        state.get("meeting_context", ""),
    )
    base: List[BaseMessage] = [SystemMessage(content=MINUTES_SYSTEM)]
    if context:
        base += [
            HumanMessage(content=context),
            AIMessage(content="회의 정보를 확인했습니다. 도움이 필요하신 게 있나요?"),
        ]
    return base + list(state.get("messages", []))


def _build_graph():
    """LangGraph create_react_agent — MINUTES_TOOLS를 도구로 사용하는 에이전트 그래프."""
    return create_react_agent(
        model=_make_llm(),
        tools=MINUTES_TOOLS,
        state_schema=MinutesState,
        prompt=_minutes_state_modifier,
    )


_graph = _build_graph()


# ── Public API ─────────────────────────────────────────────────────────────
async def chat_stream(
    message: str,
    chat_history: List[dict],
    previous_minutes: List[str] = None,
    current_agendas: List[dict] = None,
    meeting_id: int = 0,
    meeting_context: str = "",
) -> AsyncGenerator[str, None]:
    history = _to_base_messages(chat_history[-10:])
    input_msgs = history + [HumanMessage(content=message)]
    config = {"configurable": {"thread_id": str(uuid.uuid4())}}

    async for event in _graph.astream_events(
        {
            "messages": input_msgs,
            "previous_minutes": previous_minutes or [],
            "current_agendas": current_agendas or [],
            "meeting_context": meeting_context,
        },
        config,
        version="v2",
    ):
        if event["event"] == "on_chat_model_stream":
            chunk = event["data"]["chunk"]
            if chunk.content:
                yield chunk.content


async def generate_minutes(
    raw_transcript: str,
    session_info: dict = None,
    meeting_info: dict = None,
    participants: list = None,
    agendas: list = None,
    todos: list = None,
    meeting_id: int = None,
    session_id: int = None,
) -> tuple:
    """
    회의록 5대 필수요소를 포함한 구조적 회의록 생성.
    Returns: (markdown_summary: str, structured: dict)
    """
    if not raw_transcript or len(raw_transcript.strip()) < 5:
        empty = {
            "attendees": [], "decisions": [], "action_items": [],
            "tbd_items": [], "next_meeting_note": "",
        }
        return "회의 내용이 기록되지 않았습니다.", empty

    similar_minutes = await _search_similar_minutes(raw_transcript)

    tpo_lines = []
    if session_info:
        if session_info.get("title"):
            tpo_lines.append(f"회의 제목: {session_info['title']}")
        if session_info.get("started_at"):
            tpo_lines.append(f"시작: {session_info['started_at']}")
        if session_info.get("ended_at"):
            tpo_lines.append(f"종료: {session_info['ended_at']}")
        if session_info.get("location"):
            tpo_lines.append(f"장소: {session_info['location']}")
    if meeting_info:
        if meeting_info.get("purpose"):
            tpo_lines.append(f"회의 목적: {meeting_info['purpose']}")

    participant_lines = []
    if participants:
        for p in participants:
            role_label = "관리자" if p.get("role") == "admin" else "발제자"
            participant_lines.append(f"- {p.get('name','?')} ({p.get('dept','')}, {role_label})")

    agenda_lines = []
    if agendas:
        for i, a in enumerate(agendas, 1):
            status_label = {"confirmed": "확정", "draft": "검토중", "tbd": "미결"}.get(
                a.get("status", ""), a.get("status", "")
            )
            agenda_lines.append(
                f"{i}. [{status_label}] {a.get('content','')} (담당: {a.get('department') or '미정'})"
            )

    todo_lines = []
    if todos:
        for t in todos:
            due = t.get("due_date", "").split("T")[0] if t.get("due_date") else "기한 미정"
            todo_lines.append(f"- {t.get('content','')} / 담당: {t.get('assignee','미정')} / 기한: {due}")

    context_block = ""
    if tpo_lines:
        context_block += "[회의 기본 정보]\n" + "\n".join(tpo_lines) + "\n\n"
    if participant_lines:
        context_block += "[참석자]\n" + "\n".join(participant_lines) + "\n\n"
    if agenda_lines:
        context_block += "[안건 목록]\n" + "\n".join(agenda_lines) + "\n\n"
    if todo_lines:
        context_block += "[등록된 Todo]\n" + "\n".join(todo_lines) + "\n\n"
    if similar_minutes:
        context_block += "[유사 회의록 참고]\n" + "\n\n".join(similar_minutes[:2]) + "\n\n"

    prompt = f"""{context_block}[회의 녹취/기록]
{raw_transcript[:5000]}

위 회의 내용을 바탕으로 두 파트로 응답하세요.

## [1]
# 회의록
## 1. 회의 목적 및 배경
## 2. 주요 논의 사항
## 3. 결정 사항
## 4. 액션 아이템
| 담당자 | 내용 | 기한 |
|--------|------|------|
## 5. 보류 및 추가 검토 사항
## 6. 다음 회의 안건

## [2]
```json
{{
  "attendees": ["참석자 목록"],
  "decisions": ["결정 사항 목록"],
  "action_items": [{{"assignee": "담당자", "content": "내용", "due_date": "기한"}}],
  "tbd_items": ["보류 사항 목록"],
  "next_meeting_note": "다음 회의 안건"
}}
```"""

    llm = _make_llm(temperature=0.2)
    response = await llm.ainvoke([SystemMessage(content=MINUTES_SYSTEM), HumanMessage(content=prompt)])
    full_text = response.content

    md_part = full_text
    json_part = {}
    split_marker = "## [2]"
    if split_marker in full_text:
        parts = full_text.split(split_marker, 1)
        md_part = parts[0].replace("## [1]", "").strip()
        raw_json_text = parts[1]
        m = _re.search(r'```(?:json)?\s*(\{[\s\S]*?\})\s*```', raw_json_text)
        if m:
            try:
                json_part = _json.loads(m.group(1))
            except Exception:
                pass

    if meeting_id and md_part:
        try:
            from agents import knowledge_manager as _ka
            _title = session_info.get("title", "회의록") if session_info else "회의록"
            await _ka.store_minutes(
                title=_title,
                content=md_part,
                meeting_id=meeting_id,
                session_id=session_id,
            )
        except Exception:
            pass

    return md_part, json_part


async def generate_minutes_stream(
    transcript: str,
    meeting_context: str = "",
    agenda_text: str = "없음",
    now: str = "",
    meeting_id: int = None,
    session_id: int = None,
    title: str = "",
) -> AsyncGenerator[str, None]:
    from datetime import datetime as _dt
    if not now:
        now = _dt.now().strftime("%Y년 %m월 %d일")

    llm = _make_llm(temperature=0.2)
    collected_parts: List[str] = []
    async for chunk in llm.astream([
        SystemMessage(content=generate_minutes_system(meeting_context, agenda_text)),
        HumanMessage(content=generate_minutes_human(transcript, now)),
    ]):
        if chunk.content:
            collected_parts.append(chunk.content)
            yield chunk.content

    if meeting_id and collected_parts:
        try:
            from agents import knowledge_manager as _ka
            await _ka.store_minutes(
                title=title or f"회의록 ({now})",
                content="".join(collected_parts),
                meeting_id=meeting_id,
                session_id=session_id,
            )
        except Exception:
            pass
