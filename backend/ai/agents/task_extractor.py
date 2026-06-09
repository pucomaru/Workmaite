import os, json, re, uuid
from typing import AsyncGenerator, List, Optional, Annotated
from typing_extensions import TypedDict

from langchain_openai import ChatOpenAI
from langchain_core.messages import BaseMessage, SystemMessage, HumanMessage, AIMessage
from langchain_core.tools import tool
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.managed import RemainingSteps
from langgraph.prebuilt import create_react_agent
from langgraph.types import interrupt, Command
from pydantic import BaseModel, Field

from routers.prompts import (
    task_system, task_extract_human,
    extract_agendas_system, chat_extract_system,
)

MODEL = os.environ["OPENAI_MODEL"]


# ── State ─────────────────────────────────────────────────────────────────
class TaskState(TypedDict):
    messages: Annotated[List[BaseMessage], add_messages]
    remaining_steps: RemainingSteps
    departments: List[str]
    knowledge: List[dict]
    meeting_context: str


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


# ── Helpers ────────────────────────────────────────────────────────────────
def _parse_json_from_text(text: str):
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


def _to_base_messages(messages: List[dict]) -> List[BaseMessage]:
    result = []
    for m in messages:
        role, content = m.get("role", ""), m.get("content", "")
        if role == "user":
            result.append(HumanMessage(content=content))
        elif role in ("assistant", "agent"):
            result.append(AIMessage(content=content))
    return result


# ── Tools ──────────────────────────────────────────────────────────────────────
@tool
async def search_related_agendas(query: str) -> str:
    """지식 그래프에서 관련 안건·과제를 의미 기반으로 검색합니다.

    Args:
        query: 찾고 싶은 안건/과제 내용 또는 키워드
    """
    from agents.knowledge_manager import search_knowledge
    results = await search_knowledge(query, node_type="Agenda", k=5)
    doc_results = await search_knowledge(query, node_type="DocumentChunk", source_type="agenda", k=3)
    all_results = results + doc_results
    if not all_results:
        return "관련 안건을 찾지 못했습니다."
    lines = [
        f"- [{r.get('title','?')}]: {r.get('content','')[:150]}"
        for r in all_results[:5]
    ]
    return "\n".join(lines)


@tool
async def search_previous_minutes(query: str) -> str:
    """이전 회의록에서 관련 내용을 검색합니다.

    Args:
        query: 검색할 내용 (키워드 또는 자연어 문장)
    """
    from agents.knowledge_manager import search_knowledge
    results = await search_knowledge(query, node_type="Minutes", k=3)
    doc_results = await search_knowledge(query, node_type="DocumentChunk", source_type="archive", k=2)
    all_results = results + doc_results
    if not all_results:
        return "관련 회의록을 찾지 못했습니다."
    lines = [
        f"[{r.get('title','?')}]\n{r.get('content','')[:300]}"
        for r in all_results[:3]
    ]
    return "\n\n".join(lines)


TASK_TOOLS: list = [search_related_agendas, search_previous_minutes]


# ── Chat graph ─────────────────────────────────────────────────────────────────
def _task_state_modifier(state: TaskState) -> List[BaseMessage]:
    """런타임 컨텍스트(departments·knowledge·meeting_context)를 시스템 메시지로 주입합니다."""
    system = task_system(
        state.get("knowledge"),
        state.get("departments"),
        state.get("meeting_context", ""),
    )
    return [SystemMessage(content=system)] + list(state.get("messages", []))


def _build_chat_graph():
    """LangGraph create_react_agent — TASK_TOOLS를 도구로 사용하는 에이전트 그래프."""
    llm = ChatOpenAI(model=MODEL, temperature=0.1, api_key=os.environ["OPENAI_API_KEY"], streaming=True)
    return create_react_agent(
        model=llm,
        tools=TASK_TOOLS,
        state_schema=TaskState,
        prompt=_task_state_modifier,
    )


_chat_graph = _build_chat_graph()


# ── HITL 추출 그래프 ─────────────────────────────────────────────────────
async def _extract_propose_node(state: ExtractionState) -> dict:
    dept_hint = ""
    if state.get("departments"):
        dept_hint = f"\n담당 부서는 반드시 다음 목록에서 선택하세요: {', '.join(state['departments'])}"

    llm = ChatOpenAI(model=MODEL, temperature=0.0, api_key=os.environ["OPENAI_API_KEY"])
    response = await llm.ainvoke([
        SystemMessage(content=task_system(state.get("knowledge"), state.get("departments"))),
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
    meeting_context: str = "",
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
        {
            "messages": input_msgs,
            "departments": departments or [],
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


async def extract_agendas_and_todos(
    content: str,
    previous_minutes: List[str] = None,
    knowledge: List[dict] = None,
    departments: List[str] = None,
) -> dict:
    dept_hint = ""
    if departments:
        dept_hint = f"\n담당 부서는 반드시 다음 목록에서 선택하세요: {', '.join(d for d in departments if d)}"

    prev_hint = ""
    if previous_minutes:
        prev_hint = "\n\n[이전 회의록 참고]\n" + "\n\n".join(previous_minutes[:2])[:2000]

    llm = ChatOpenAI(model=MODEL, temperature=0.0, api_key=os.environ["OPENAI_API_KEY"])
    response = await llm.ainvoke([
        SystemMessage(content=task_system(knowledge, departments)),
        HumanMessage(content=task_extract_human(content, dept_hint, prev_hint)),
    ])
    parsed = _parse_json_from_text(response.content)
    reason = re.sub(r'```(?:json)?\s*[\s\S]*?```', '', response.content).strip()
    reason = re.sub(r'\{[^{}]*"agendas"[^{}]*\}', '', reason).strip()
    if isinstance(parsed, list):
        return {"agendas": parsed, "todos": [], "reason": reason}
    if isinstance(parsed, dict):
        return {"agendas": parsed.get("agendas", []), "todos": parsed.get("todos", []), "reason": reason}
    return {"agendas": [], "todos": [], "reason": reason}


async def start_extraction_review(
    thread_id: str,
    content: str,
    departments: List[str] = None,
    knowledge: List[dict] = None,
) -> dict:
    config = {"configurable": {"thread_id": thread_id}}
    await _extraction_graph.ainvoke(
        {
            "messages": [],
            "content": content,
            "departments": departments or [],
            "knowledge": knowledge or [],
            "proposed": None,
        },
        config,
    )
    state = _extraction_graph.get_state(config)
    if state.tasks and state.tasks[0].interrupts:
        proposed = state.tasks[0].interrupts[0].value
        return {"status": "pending", "proposed": proposed}
    return {"status": "error", "proposed": None}


async def confirm_extraction_review(
    thread_id: str,
    approved: bool,
    meeting_id: int = None,
) -> dict:
    config = {"configurable": {"thread_id": thread_id}}
    result = await _extraction_graph.ainvoke(
        Command(resume={"approved": approved}),
        config,
    )
    if approved:
        extraction = result.get("proposed")

        if extraction:
            try:
                from agents import knowledge_manager as _ka
                for todo in extraction.get("todos", []):
                    if todo.get("content"):
                        await _ka.store_task(
                            content=todo["content"],
                            department=todo.get("department"),
                            due_date=todo.get("due_date"),
                            meeting_id=meeting_id,
                        )
            except Exception:
                pass

        return {"status": "confirmed", "extraction": extraction}
    return {"status": "rejected"}


# ── 컨텍스트 기반 아젠다 추출 / 채팅 업데이트 ──────────────────────────────
async def extract_agendas_from_context(context_parts: List[str], dept_list: str) -> dict:
    llm = ChatOpenAI(model=MODEL, temperature=0.15, api_key=os.environ["OPENAI_API_KEY"])
    response = await llm.ainvoke([
        SystemMessage(content=extract_agendas_system(dept_list)),
        HumanMessage(content=f"다음 컨텍스트를 바탕으로 과제를 추출해 주세요:\n\n{chr(10).join(context_parts)}"),
    ])
    return _parse_json_from_text(response.content.strip()) or {"agendas": []}


async def chat_update_agendas(
    message: str,
    meeting_context: str,
    dept_list: str,
    current_agendas_text: str,
) -> dict:
    llm = ChatOpenAI(model=MODEL, temperature=0.15, api_key=os.environ["OPENAI_API_KEY"])
    response = await llm.ainvoke([
        SystemMessage(content=chat_extract_system(meeting_context, dept_list, current_agendas_text)),
        HumanMessage(content=message),
    ])
    return _parse_json_from_text(response.content.strip()) or {}
