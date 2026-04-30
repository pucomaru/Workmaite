"""가온 (Gaon) - Agenda/Todo 추출 Agent (LangGraph)"""
import os, json, re, uuid
from typing import AsyncGenerator, List, Optional, Annotated
from typing_extensions import TypedDict

from langchain_openai import ChatOpenAI
from langchain_core.messages import BaseMessage, SystemMessage, HumanMessage, AIMessage
from langchain_core.tools import tool
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.types import interrupt, Command
from pydantic import BaseModel, Field

MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
_DB = os.path.join(os.path.dirname(__file__), "..", "checkpoints.db")


# ── State ─────────────────────────────────────────────────────────────────
class GaonState(TypedDict):
    messages: Annotated[List[BaseMessage], add_messages]
    departments: List[str]
    knowledge: List[dict]


class ExtractionState(TypedDict):
    messages: Annotated[List[BaseMessage], add_messages]
    content: str
    departments: List[str]
    knowledge: List[dict]
    proposed: Optional[dict]


# ── Pydantic schemas ──────────────────────────────────────────────────────
class AgendaItem(BaseModel):
    department: Optional[str] = Field(None, description="담당 부서 (없으면 null)")
    content: str = Field(..., description="아젠다 내용")


class TodoItem(BaseModel):
    content: str = Field(..., description="할 일 내용")
    department: Optional[str] = Field(None, description="담당 부서")
    due_date: Optional[str] = Field(None, description="마감일 YYYY-MM-DD")


class ExtractionResult(BaseModel):
    agendas: List[AgendaItem] = Field(default_factory=list)
    todos: List[TodoItem] = Field(default_factory=list)


# ── Tool ──────────────────────────────────────────────────────────────────
@tool
def parse_extraction_tool(text: str) -> str:
    """응답 텍스트에서 아젠다/Todo JSON을 파싱해 반환한다."""
    parsed = _parse_json_from_text(text)
    return json.dumps(parsed, ensure_ascii=False) if parsed else "{}"


# ── LLM ───────────────────────────────────────────────────────────────────
def _make_llm(temperature: float = 0.1) -> ChatOpenAI:
    return ChatOpenAI(
        model=MODEL,
        temperature=temperature,
        api_key=os.getenv("OPENAI_API_KEY"),
        streaming=True,
    )


# ── Helpers ────────────────────────────────────────────────────────────────
def _parse_json_from_text(text: str):
    """LLM 응답에서 JSON 추출. 마크다운 코드블록, 일반 JSON 모두 처리."""
    match = re.search(r'```(?:json)?\s*(\{[\s\S]*?\}|\[[\s\S]*?\])\s*```', text)
    if match:
        try:
            return json.loads(match.group(1))
        except Exception:
            pass
    match = re.search(r'\{[\s\S]*\}', text)
    if match:
        try:
            return json.loads(match.group())
        except Exception:
            pass
    match = re.search(r'\[[\s\S]*\]', text)
    if match:
        try:
            return json.loads(match.group())
        except Exception:
            pass
    return None


def _build_system_prompt(knowledge: List[dict] = None, departments: List[str] = None) -> str:
    base = """당신은 회의체 아젠다 및 To-do 추출 전문 AI 가온(Gaon)입니다.
사용자가 업로드한 보고자료와 이전 회의록을 분석하여:
1. 회의 아젠다 항목을 추출합니다 (담당 부서, 내용)
2. To-do 과제를 도출합니다 (내용, 마감일, 담당 부서)

아젠다 추출 요청 시 반드시 아래 JSON 형식으로 응답하세요:
{
  "agendas": [{"department": "부서명", "content": "아젠다 내용"}],
  "todos": [{"content": "할 일 내용", "department": "담당부서", "due_date": "YYYY-MM-DD 또는 null"}]
}

- 한국어로 응답합니다
- 담당 부서가 불명확하면 null로 표기합니다"""

    if departments:
        base += "\n\n[회의 참여자 담당 부서 목록 - 이 중에서 부서를 배정하세요]\n" + "\n".join(f"- {d}" for d in departments if d)
    if knowledge:
        criteria = "\n".join([f"- [{k.get('category','')}] {k.get('title','')}" for k in knowledge])
        base += f"\n\n[조직 아젠다 선정 기준]\n{criteria}"
    return base


def _to_base_messages(messages: List[dict]) -> List[BaseMessage]:
    result = []
    for m in messages:
        role, content = m.get("role", ""), m.get("content", "")
        if role == "user":
            result.append(HumanMessage(content=content))
        elif role in ("assistant", "agent"):
            result.append(AIMessage(content=content))
    return result


# ── Chat graph nodes ───────────────────────────────────────────────────────
async def _chat_node(state: GaonState) -> dict:
    system = _build_system_prompt(state.get("knowledge"), state.get("departments"))
    llm = _make_llm()
    response = await llm.ainvoke([SystemMessage(content=system)] + state["messages"])
    return {"messages": [response]}


def _build_chat_graph():
    builder = StateGraph(GaonState)
    builder.add_node("chat", _chat_node)
    builder.add_edge(START, "chat")
    builder.add_edge("chat", END)
    return builder.compile()

_chat_graph = _build_chat_graph()


# ── HITL 추출 그래프 ─────────────────────────────────────────────────────
async def _extract_propose_node(state: ExtractionState) -> dict:
    """문서 분석 → 아젠다/Todo 제안 → interrupt()로 사용자 확인 대기."""
    dept_hint = ""
    if state.get("departments"):
        dept_hint = f"\n담당 부서는 반드시 다음 목록에서 선택하세요: {', '.join(state['departments'])}"

    llm = ChatOpenAI(model=MODEL, temperature=0.0, api_key=os.getenv("OPENAI_API_KEY"))
    response = await llm.ainvoke([
        SystemMessage(content=_build_system_prompt(state.get("knowledge"), state.get("departments"))),
        HumanMessage(content=(
            f"다음 문서에서 아젠다와 Todo를 추출해 JSON 형식으로만 응답하세요.{dept_hint}\n\n"
            f"[문서]\n{state['content'][:8000]}"
        )),
    ])
    proposed = _parse_json_from_text(response.content)
    if isinstance(proposed, list):
        proposed = {"agendas": proposed, "todos": []}
    if not isinstance(proposed, dict):
        proposed = {"agendas": [], "todos": []}

    # HITL: 사용자 확인 대기
    feedback = interrupt(proposed)

    if feedback.get("approved"):
        return {"proposed": proposed}
    return {"proposed": None}


def _build_extraction_graph():
    builder = StateGraph(ExtractionState)
    builder.add_node("propose", _extract_propose_node)
    builder.add_edge(START, "propose")
    builder.add_edge("propose", END)
    return builder.compile()

_extraction_graph = _build_extraction_graph()


# ── Public API ─────────────────────────────────────────────────────────────
async def chat_stream(
    message: str,
    chat_history: List[dict],
    file_content: str = "",
    previous_minutes: List[str] = None,
    knowledge: List[dict] = None,
    departments: List[str] = None,
    meeting_id: int = 0,
) -> AsyncGenerator[str, None]:
    parts = []
    if file_content:
        parts.append(f"[업로드된 문서 내용]\n{file_content[:6000]}")
    if previous_minutes:
        parts.append("[이전 회의록]\n" + "\n\n".join(previous_minutes[:3])[:3000])
    parts.append(message)
    full_message = "\n\n".join(parts)

    history = _to_base_messages(chat_history[-10:])
    input_msgs = history + [HumanMessage(content=full_message)]
    config = {"configurable": {"thread_id": str(uuid.uuid4())}}

    async for event in _chat_graph.astream_events(
        {"messages": input_msgs, "departments": departments or [], "knowledge": knowledge or []},
        config,
        version="v2",
    ):
        if event["event"] == "on_chat_model_stream":
            chunk = event["data"]["chunk"]
            if chunk.content:
                yield chunk.content


async def extract_agendas_and_todos(
    content: str,
    previous_minutes: List[str] = None,
    knowledge: List[dict] = None,
    departments: List[str] = None,
) -> dict:
    """문서에서 아젠다/Todo 직접 추출 (HITL 없음). 확인 후 저장용."""
    dept_hint = ""
    if departments:
        dept_hint = f"\n담당 부서는 반드시 다음 목록에서 선택하세요: {', '.join(d for d in departments if d)}"

    prev_hint = ""
    if previous_minutes:
        prev_hint = "\n\n[이전 회의록 참고]\n" + "\n\n".join(previous_minutes[:2])[:2000]

    prompt = f"""다음 문서를 분석하여 회의 아젠다와 To-do 과제를 추출해주세요.
{dept_hint}
반드시 아래 JSON 형식으로만 응답하세요 (다른 텍스트 없이):
{{
  "agendas": [{{"department": "부서명 또는 null", "content": "아젠다 내용"}}],
  "todos": [{{"content": "할 일 내용", "department": "담당부서 또는 null", "due_date": "YYYY-MM-DD 또는 null"}}]
}}
{prev_hint}

[분석할 문서]
{content[:8000]}"""

    llm = ChatOpenAI(model=MODEL, temperature=0.0, api_key=os.getenv("OPENAI_API_KEY"))
    response = await llm.ainvoke([
        SystemMessage(content=_build_system_prompt(knowledge, departments)),
        HumanMessage(content=prompt),
    ])
    parsed = _parse_json_from_text(response.content)
    if isinstance(parsed, list):
        return {"agendas": parsed, "todos": []}
    if isinstance(parsed, dict):
        return {"agendas": parsed.get("agendas", []), "todos": parsed.get("todos", [])}
    return {"agendas": [], "todos": []}


async def start_extraction_review(
    thread_id: str,
    content: str,
    departments: List[str] = None,
    knowledge: List[dict] = None,
) -> dict:
    """[HITL Step 1] 아젠다 추출 제안 → interrupt()로 일시 정지. 제안 결과 반환."""
    config = {"configurable": {"thread_id": thread_id}}
    await _extraction_graph.ainvoke(
        {"messages": [], "content": content, "departments": departments or [],
         "knowledge": knowledge or [], "proposed": None},
        config,
    )
    state = _extraction_graph.get_state(config)
    if state.tasks and state.tasks[0].interrupts:
        proposed = state.tasks[0].interrupts[0].value
        return {"status": "pending", "proposed": proposed}
    return {"status": "error", "proposed": None}


async def confirm_extraction_review(thread_id: str, approved: bool) -> dict:
    """[HITL Step 2] interrupt() 지점 재개. approved=True면 추출 결과 반환."""
    config = {"configurable": {"thread_id": thread_id}}
    result = await _extraction_graph.ainvoke(
        Command(resume={"approved": approved}),
        config,
    )
    if approved:
        return {"status": "confirmed", "extraction": result.get("proposed")}
    return {"status": "rejected"}
