"""혜안 (Hyean) - Supervisor Agent + 암묵지 관리 (LangGraph)"""
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
class HyeanState(TypedDict):
    messages: Annotated[List[BaseMessage], add_messages]
    meeting_status: dict
    user_role: str
    knowledge: List[dict]


class KnowledgeProposalState(TypedDict):
    messages: Annotated[List[BaseMessage], add_messages]
    recent_events: List[dict]
    current_knowledge: List[dict]
    scope: str
    meeting_id: Optional[int]
    proposed_update: Optional[dict]


# ── Pydantic schemas ──────────────────────────────────────────────────────
class KnowledgeProposal(BaseModel):
    category: str = Field(..., description="암묵지 카테고리")
    title: str = Field(..., description="기준 제목")
    proposed_content: str = Field(..., description="새 기준 내용 (마크다운)")
    diff_summary: str = Field(..., description="변경 요약")
    evidence_summary: str = Field(..., description="이벤트 패턴에서 도출된 근거")


class MeetingStatusSummary(BaseModel):
    status_text: str = Field(..., description="현황 요약")
    next_actions: List[str] = Field(default_factory=list, description="다음 액션 목록")
    warnings: List[str] = Field(default_factory=list, description="주의 사항")


# ── Tool ──────────────────────────────────────────────────────────────────
@tool
def propose_knowledge_update_tool(events_json: str, current_knowledge_json: str) -> str:
    """이벤트 패턴을 분석해 암묵지 업데이트를 제안한다. JSON 문자열 입력."""
    return json.dumps({"category": "", "title": "", "proposed_content": "", "diff_summary": "", "evidence_summary": ""}, ensure_ascii=False)


# ── LLM ───────────────────────────────────────────────────────────────────
def _make_llm(temperature: float = 0.3) -> ChatOpenAI:
    return ChatOpenAI(
        model=MODEL,
        temperature=temperature,
        api_key=os.getenv("OPENAI_API_KEY"),
        streaming=True,
    )


def _status_system_prompt() -> str:
    return """당신은 회의체 운영 현황을 파악하고 안내하는 AI 혜안(Hyean)입니다.
현재 회의체의 상태를 분석하여:
1. 현황을 자연어로 간결하게 설명합니다
2. 다음에 해야 할 액션을 추천합니다
3. 주의가 필요한 사항을 알립니다
한국어로, 친근하지만 전문적으로 응답합니다."""


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
async def _chat_node(state: HyeanState) -> dict:
    status_text = json.dumps(state.get("meeting_status", {}), ensure_ascii=False, indent=2)
    user_role = state.get("user_role", "presenter")

    system_msgs: List[BaseMessage] = [
        SystemMessage(content=_status_system_prompt()),
        HumanMessage(content=f"[회의체 현황]\n{status_text}\n\n[사용자 역할] {user_role}"),
        AIMessage(content="현황을 확인했습니다. 무엇이 궁금하신가요?"),
    ]
    llm = _make_llm()
    response = await llm.ainvoke(system_msgs + state["messages"])
    return {"messages": [response]}


def _build_chat_graph():
    builder = StateGraph(HyeanState)
    builder.add_node("chat", _chat_node)
    builder.add_edge(START, "chat")
    builder.add_edge("chat", END)
    return builder.compile()

_chat_graph = _build_chat_graph()


# ── HITL 암묵지 제안 그래프 ────────────────────────────────────────────────
async def _analyze_propose_node(state: KnowledgeProposalState) -> dict:
    """이벤트 패턴 분석 → 암묵지 업데이트 제안 → interrupt()로 관리자 확인 대기."""
    recent_events = state.get("recent_events", [])
    current_knowledge = state.get("current_knowledge", [])

    if len(recent_events) < 3:
        return {"proposed_update": None}

    events_text = json.dumps(recent_events[-10:], ensure_ascii=False, indent=2)
    knowledge_text = json.dumps(current_knowledge[:5], ensure_ascii=False, indent=2)

    prompt = f"""최근 회의 활동 데이터를 분석하여 이 회의체의 메모리를 업데이트해주세요.

반드시 JSON 형식으로만 응답하세요. 업데이트할 내용이 없으면 null을 반환하세요.
형식:
{{
  "category": "meeting_standard",
  "title": "기억할 항목 제목",
  "proposed_content": "업데이트된 내용 (마크다운)",
  "diff_summary": "변경 요약",
  "evidence_summary": "근거"
}}

카테고리: report_standard(보고서 기준), agenda_standard(아젠다 기준), todo_standard(과제 기준), meeting_standard(회의 운영 기준)

[최근 활동]
{events_text}

[현재 메모리]
{knowledge_text}"""

    llm = ChatOpenAI(model=MODEL, temperature=0.2, api_key=os.getenv("OPENAI_API_KEY"))
    response = await llm.ainvoke([
        SystemMessage(content="당신은 회의체의 운영 패턴을 학습하고 메모리를 업데이트하는 AI입니다."),
        HumanMessage(content=prompt),
    ])
    text = response.content.strip()
    if text.lower() == "null":
        return {"proposed_update": None}

    match = re.search(r'\{.*\}', text, re.DOTALL)
    proposed = None
    if match:
        try:
            proposed = json.loads(match.group())
        except Exception:
            pass

    if not proposed:
        return {"proposed_update": None}

    # HITL: 관리자 확인 대기
    feedback = interrupt(proposed)

    if feedback.get("approved"):
        return {"proposed_update": proposed}
    return {"proposed_update": None}


def _build_knowledge_graph():
    builder = StateGraph(KnowledgeProposalState)
    builder.add_node("analyze", _analyze_propose_node)
    builder.add_edge(START, "analyze")
    builder.add_edge("analyze", END)
    return builder.compile()

_knowledge_graph = _build_knowledge_graph()


# ── Public API ─────────────────────────────────────────────────────────────
async def status_stream(
    meeting_status: dict,
    user_role: str,
    active_knowledge: List[dict] = None,
    chat_history: List[dict] = None,
    message: str = "현재 회의체 현황을 알려주세요.",
    meeting_id: int = 0,
) -> AsyncGenerator[str, None]:
    history = _to_base_messages((chat_history or [])[-8:])
    input_msgs = history + [HumanMessage(content=message)]
    config = {"configurable": {"thread_id": str(uuid.uuid4())}}

    async for event in _chat_graph.astream_events(
        {
            "messages": input_msgs,
            "meeting_status": meeting_status,
            "user_role": user_role,
            "knowledge": active_knowledge or [],
        },
        config,
        version="v2",
    ):
        if event["event"] == "on_chat_model_stream":
            chunk = event["data"]["chunk"]
            if chunk.content:
                yield chunk.content


async def analyze_and_propose(
    recent_events: List[dict],
    current_knowledge: List[dict],
    scope: str = "global",
    meeting_id: int = None,
) -> dict | None:
    """회의 활동 분석 → 메모리 업데이트 제안 (즉시 반환, HITL 없음)."""
    if len(recent_events) < 2:
        return None

    events_text = json.dumps(recent_events[-15:], ensure_ascii=False, indent=2)
    knowledge_text = json.dumps(current_knowledge[:5], ensure_ascii=False, indent=2)

    prompt = f"""최근 회의 활동 데이터를 분석하여 이 회의체의 메모리를 업데이트해주세요.

반드시 JSON 형식으로만 응답하세요. 업데이트할 내용이 없으면 null을 반환하세요.
형식:
{{
  "category": "meeting_standard",
  "title": "기억할 항목 제목",
  "proposed_content": "업데이트된 내용 (마크다운)",
  "diff_summary": "변경 요약",
  "evidence_summary": "근거"
}}

카테고리: report_standard(보고서 기준), agenda_standard(아젠다 기준), todo_standard(과제 기준), meeting_standard(회의 운영 기준)

[최근 활동]
{events_text}

[현재 메모리]
{knowledge_text}"""

    llm = ChatOpenAI(model=MODEL, temperature=0.2, api_key=os.getenv("OPENAI_API_KEY"))
    response = await llm.ainvoke([
        SystemMessage(content="당신은 회의체의 운영 패턴을 학습하고 메모리를 업데이트하는 AI입니다. 실제 활동 데이터에서 패턴을 추출해 구체적인 메모리를 만들어주세요."),
        HumanMessage(content=prompt),
    ])
    text = response.content.strip()
    if text.lower() == "null":
        return None
    match = re.search(r'\{.*\}', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except Exception:
            pass
    return None


async def start_knowledge_review(
    thread_id: str,
    recent_events: List[dict],
    current_knowledge: List[dict],
    scope: str = "global",
    meeting_id: int = None,
) -> dict:
    """[HITL Step 1] 암묵지 업데이트 제안 → interrupt()로 일시 정지. 제안 반환."""
    config = {"configurable": {"thread_id": thread_id}}
    await _knowledge_graph.ainvoke(
        {
            "messages": [],
            "recent_events": recent_events,
            "current_knowledge": current_knowledge,
            "scope": scope,
            "meeting_id": meeting_id,
            "proposed_update": None,
        },
        config,
    )
    state = _knowledge_graph.get_state(config)
    if state.tasks and state.tasks[0].interrupts:
        proposed = state.tasks[0].interrupts[0].value
        return {"status": "pending", "proposed": proposed}
    return {"status": "no_proposal", "proposed": None}


async def confirm_knowledge_review(thread_id: str, approved: bool) -> dict:
    """[HITL Step 2] interrupt() 지점 재개. approved=True면 업데이트 데이터 반환."""
    config = {"configurable": {"thread_id": thread_id}}
    result = await _knowledge_graph.ainvoke(
        Command(resume={"approved": approved}),
        config,
    )
    if approved:
        return {"status": "confirmed", "update": result.get("proposed_update")}
    return {"status": "rejected"}
