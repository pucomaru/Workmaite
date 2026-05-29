# 회의록 작성 Agent - STT 변환 결과를 입력받아 회의록 생성
# Knowledge Base (Neo4j 벡터 검색)에서 유사 회의록을 조회해 프롬프트에 주입
import os, uuid, re as _re, json as _json
from typing import AsyncGenerator, List, Optional, Annotated
from typing_extensions import TypedDict

from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_core.messages import BaseMessage, SystemMessage, HumanMessage, AIMessage
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from pydantic import BaseModel, Field

MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")


# ── State ─────────────────────────────────────────────────────────────────
class MinutesState(TypedDict):
    messages: Annotated[List[BaseMessage], add_messages]
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
        api_key=os.getenv("OPENAI_API_KEY"),
        streaming=True,
    )


SYSTEM_PROMPT = """당신은 회의록 작성 전문 AI MinutesAgent입니다.
- STT 변환 텍스트를 분석해 구조적 회의록을 생성합니다
- 이전 유사 회의록을 참고해 일관성 있는 형식을 유지합니다
- 결정 사항, 액션 아이템, 참석자 정보를 명확히 기록합니다
한국어로 응답합니다."""


# ── Neo4j 벡터 검색 (유사 회의록) ────────────────────────────────────────
async def _search_similar_minutes(text: str, k: int = 3) -> List[str]:
    """Neo4j 내장 벡터 검색으로 유사 회의록을 조회합니다 (Cypher 기반)."""
    try:
        from neo4j_client import run_cypher
        embeddings = OpenAIEmbeddings(api_key=os.getenv("OPENAI_API_KEY"))
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


# ── Graph nodes ────────────────────────────────────────────────────────────
async def _chat_node(state: MinutesState) -> dict:
    context = _build_context_prompt(
        state.get("previous_minutes", []),
        state.get("current_agendas", []),
        state.get("meeting_context", ""),
    )
    system_msgs: List[BaseMessage] = [SystemMessage(content=SYSTEM_PROMPT)]
    if context:
        system_msgs += [
            HumanMessage(content=context),
            AIMessage(content="회의 정보를 확인했습니다. 도움이 필요하신 게 있나요?"),
        ]
    llm = _make_llm()
    response = await llm.ainvoke(system_msgs + state["messages"])
    return {"messages": [response]}


# ── Graph ─────────────────────────────────────────────────────────────────
def _build_graph():
    builder = StateGraph(MinutesState)
    builder.add_node("chat", _chat_node)
    builder.add_edge(START, "chat")
    builder.add_edge("chat", END)
    return builder.compile()

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
) -> tuple:
    """
    회의록 5대 필수요소를 포함한 구조적 회의록 생성.
    Neo4j 벡터 검색으로 유사 회의록을 조회해 프롬프트에 주입합니다.
    Returns: (markdown_summary: str, structured: dict)
    structured keys: attendees, decisions, action_items, tbd_items, next_meeting_note
    """
    if not raw_transcript or len(raw_transcript.strip()) < 5:
        empty = {
            "attendees": [], "decisions": [], "action_items": [],
            "tbd_items": [], "next_meeting_note": "",
        }
        return "회의 내용이 기록되지 않았습니다.", empty

    # Neo4j 유사 회의록 벡터 검색
    similar_minutes = await _search_similar_minutes(raw_transcript)

    # TPO 정보 구성
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

---
위 내용을 바탕으로 다음 두 가지를 작성하세요.

## [1] 마크다운 회의록
아래 섹션을 반드시 포함하세요:

### 📋 회의 개요 (TPO)
- 일시, 장소, 목적

### 👥 참석자 (Joiner)
- 이름 / 부서 / 역할 / 참석여부

### ✅ 결정 사항 (Done)
- 확정된 내용과 결정 주체

### 📌 실행 계획 (WILL DO)
| 업무 내용 | 담당자 | 기한 | 상태 |
각 항목 반드시 담당자·기한 포함

### ⚠️ 미결 안건 (TBD)
- 결론이 나지 않은 안건과 이유

### 📅 차기 회의
- 예정일, 주요 안건 예고

## [2] JSON 구조 데이터
다음 키를 가진 JSON을 ```json ... ``` 코드블록으로 출력하세요:
{{
  "attendees": [{{"name": "이름", "dept": "부서", "role": "admin|presenter", "present": true, "note": ""}}],
  "absent": [{{"name": "이름", "dept": "부서", "reason": "사유"}}],
  "decisions": [{{"content": "결정 내용", "decided_by": "결정 주체", "agenda_ref": "관련 안건 번호(없으면 null)"}}],
  "action_items": [{{"content": "업무 내용", "assignee": "담당자", "due_date": "YYYY-MM-DD 또는 null", "status": "pending"}}],
  "tbd_items": [{{"content": "미결 안건", "reason": "미결 이유"}}],
  "next_meeting_note": "차기 회의 예정일 및 주요 안건 (없으면 빈 문자열)"
}}
- 불명확한 경우 빈 배열 []로 표기하세요
- 반드시 JSON을 포함하세요"""

    llm = ChatOpenAI(model=MODEL, temperature=0.2, api_key=os.getenv("OPENAI_API_KEY"))
    response = await llm.ainvoke([
        SystemMessage(content=(
            "당신은 전문 회의록 작성 AI입니다. 한국어로 작성합니다.\n"
            "회의록에는 무슨 말이 오갔는가보다 무엇이 결정되고 누가 무엇을 해야 하는가를 명확히 기록합니다.\n"
            "5대 필수 요소(Joiner·TPO·Done·WILL DO·TBD)를 반드시 포함하세요."
        )),
        HumanMessage(content=prompt),
    ])

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

    return md_part, json_part
