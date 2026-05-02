"""아라 (Ara) - 회의 진행 Agent + 회의록 생성 (LangGraph)"""
import os, uuid
from typing import AsyncGenerator, List, Optional, Annotated
from typing_extensions import TypedDict

from langchain_openai import ChatOpenAI
from langchain_core.messages import BaseMessage, SystemMessage, HumanMessage, AIMessage
from langchain_core.tools import tool
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from pydantic import BaseModel, Field

MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
_DB = os.path.join(os.path.dirname(__file__), "..", "checkpoints.db")


# ── State ─────────────────────────────────────────────────────────────────
class AraState(TypedDict):
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


# ── Tool ──────────────────────────────────────────────────────────────────
@tool
def summarize_transcript_tool(transcript: str) -> str:
    """회의 녹취록을 요약한다. transcript는 원문 텍스트."""
    return f"회의록 요약 작업: {len(transcript)}자 녹취록"


# ── LLM ───────────────────────────────────────────────────────────────────
def _make_llm(temperature: float = 0.3) -> ChatOpenAI:
    return ChatOpenAI(
        model=MODEL,
        temperature=temperature,
        api_key=os.getenv("OPENAI_API_KEY"),
        streaming=True,
    )


SYSTEM_PROMPT = """당신은 회의 진행을 돕는 AI 아라(Ara)입니다.
- 지난 회의 내용을 요약 제공합니다
- 현재 아젠다 진행 상황을 안내합니다
- 회의 중 궁금한 사항에 답변합니다
- 간결하고 실용적으로 응답합니다
한국어로 응답합니다."""


def _to_base_messages(messages: List[dict]) -> List[BaseMessage]:
    result = []
    for m in messages:
        role, content = m.get("role", ""), m.get("content", "")
        if role == "user":
            result.append(HumanMessage(content=content))
        elif role in ("assistant", "agent"):
            result.append(AIMessage(content=content))
    return result


def _build_context_prompt(previous_minutes: List[str], current_agendas: List[dict], meeting_context: str = "") -> Optional[str]:
    parts = []
    if meeting_context:
        parts.append(f"[회의체 맥락]\n{meeting_context}")
    if previous_minutes:
        parts.append("[이전 회의 요약]\n" + "\n".join(previous_minutes[:2]))
    if current_agendas:
        agenda_text = "\n".join([f"- {a.get('content','')}" for a in current_agendas])
        parts.append(f"[현재 아젠다]\n{agenda_text}")
    return "\n\n".join(parts) if parts else None


# ── Graph nodes ────────────────────────────────────────────────────────────
async def _chat_node(state: AraState) -> dict:
    context = _build_context_prompt(state.get("previous_minutes", []), state.get("current_agendas", []), state.get("meeting_context", ""))
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
    builder = StateGraph(AraState)
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
    Returns: (markdown_summary: str, structured: dict)
    structured keys: attendees, decisions, action_items, tbd_items, next_meeting_note
    """
    if not raw_transcript or len(raw_transcript.strip()) < 5:
        empty = {
            "attendees": [], "decisions": [], "action_items": [],
            "tbd_items": [], "next_meeting_note": "",
        }
        return "회의 내용이 기록되지 않았습니다.", empty

    # ── TPO 정보 구성 ─────────────────────────────────────────────────
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

    # ── Joiner 정보 ───────────────────────────────────────────────────
    participant_lines = []
    if participants:
        for p in participants:
            role_label = "관리자" if p.get("role") == "admin" else "발제자"
            participant_lines.append(f"- {p.get('name','?')} ({p.get('dept','')}, {role_label})")

    # ── 아젠다 목록 ───────────────────────────────────────────────────
    agenda_lines = []
    if agendas:
        for i, a in enumerate(agendas, 1):
            status_label = {"confirmed": "확정", "draft": "검토중", "tbd": "미결"}.get(a.get("status",""), a.get("status",""))
            agenda_lines.append(f"{i}. [{status_label}] {a.get('content','')} (담당: {a.get('department') or '미정'})")

    # ── 기존 Todo 목록 ────────────────────────────────────────────────
    todo_lines = []
    if todos:
        for t in todos:
            due = t.get("due_date","").split("T")[0] if t.get("due_date") else "기한 미정"
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

    # 마크다운 부분 추출 (## [1] 이후 ~ ## [2] 이전)
    md_part = full_text
    json_part = {}
    split_marker = "## [2]"
    if split_marker in full_text:
        parts = full_text.split(split_marker, 1)
        md_part = parts[0].replace("## [1]", "").strip()
        raw_json_text = parts[1]
        # JSON 코드블록 파싱
        import re as _re
        m = _re.search(r'```(?:json)?\s*(\{[\s\S]*?\})\s*```', raw_json_text)
        if m:
            try:
                import json as _json
                json_part = _json.loads(m.group(1))
            except Exception:
                pass

    return md_part, json_part
