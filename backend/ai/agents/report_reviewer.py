import os, json, re, uuid
from typing import AsyncGenerator, List, Optional, Annotated
from typing_extensions import TypedDict

from langchain_openai import ChatOpenAI
from langchain_core.messages import BaseMessage, SystemMessage, HumanMessage, AIMessage
from langchain_core.tools import tool
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import create_react_agent
from langgraph.types import interrupt, Command
from pydantic import BaseModel, Field

from routers.prompts import (
    REPORT_REVIEW_SYSTEM,
    review_propose_prompt,
    review_direct_prompt,
    STATUS_STREAM_SYSTEM,
    status_stream_context,
)

MODEL = os.environ["OPENAI_MODEL"]


# ── State ─────────────────────────────────────────────────────────────────
class ReportState(TypedDict):
    messages: Annotated[List[BaseMessage], add_messages]
    knowledge: List[dict]
    reports_info: List[dict]
    meeting_context: str


class ReportReviewState(TypedDict):
    messages: Annotated[List[BaseMessage], add_messages]
    report_content: str
    agenda: str
    knowledge: List[dict]
    proposed_review: Optional[dict]


# ── Pydantic schemas ──────────────────────────────────────────────────────
class ReviewFeedbackItem(BaseModel):
    point: str = Field(..., description="피드백 항목")


class ReviewResult(BaseModel):
    score: int = Field(..., ge=0, le=100, description="보고서 점수 (0-100)")
    feedback: List[str] = Field(default_factory=list, description="구체적인 피드백 항목들")


# ── LLM ───────────────────────────────────────────────────────────────────
def _make_llm(temperature: float = 0.2) -> ChatOpenAI:
    return ChatOpenAI(
        model=MODEL,
        temperature=temperature,
        api_key=os.environ["OPENAI_API_KEY"],
        streaming=True,
    )


def _build_system_with_knowledge(knowledge: List[dict], meeting_context: str = "") -> str:
    system = REPORT_REVIEW_SYSTEM
    if meeting_context:
        system += f"\n\n[회의체 맥락 — 이 정보를 항상 참고하세요]\n{meeting_context}"
    if knowledge:
        criteria = "\n".join([f"- {k.get('title','')}: {k.get('content','')[:100]}" for k in knowledge])
        system += f"\n\n[보고서 검토 기준]\n{criteria}"
    return system


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
async def search_review_references(query: str) -> str:
    """보고서 검토에 필요한 관련 회의록·판단 기준을 검색합니다.

    Args:
        query: 검색할 내용 (보고서 주제, 검토 기준 등)
    """
    from agents.knowledge_manager import search_knowledge
    minutes_results = await search_knowledge(query, node_type="Minutes", k=3)
    judgment_results = await search_knowledge(query, node_type="AIJudgment", k=2)
    all_results = minutes_results + judgment_results
    if not all_results:
        return "관련 참고 자료를 찾지 못했습니다."
    lines = [
        f"[{r.get('title','?')}]: {r.get('content','')[:200]}"
        for r in all_results[:4]
    ]
    return "\n\n".join(lines)


@tool
async def get_report_agenda_context(query: str) -> str:
    """보고서와 관련된 안건 컨텍스트를 검색합니다.

    Args:
        query: 검색할 내용 (보고서의 주제나 관련 안건)
    """
    from agents.knowledge_manager import search_knowledge
    results = await search_knowledge(query, node_type="Agenda", k=3)
    if not results:
        return "관련 안건을 찾지 못했습니다."
    lines = [
        f"[안건] {r.get('title','?')}: {r.get('content','')[:150]}"
        for r in results[:3]
    ]
    return "\n".join(lines)


REPORT_TOOLS: list = [search_review_references, get_report_agenda_context]


# ── Chat graph ─────────────────────────────────────────────────────────────────
def _report_state_modifier(state: ReportState) -> List[BaseMessage]:
    """런타임 컨텍스트(knowledge·meeting_context·reports_info)를 시스템 메시지로 주입합니다."""
    system = _build_system_with_knowledge(state.get("knowledge", []), state.get("meeting_context", ""))
    messages = list(state.get("messages", []))
    reports_info = state.get("reports_info", [])
    if reports_info:
        reports_text = "\n\n".join([
            f"[{r.get('presenter_name','')} - {r.get('file_name','')}]\n상태: {r.get('status','')}"
            for r in reports_info
        ])
        messages = [HumanMessage(content=f"다음 보고서 목록을 검토해주세요:\n{reports_text}")] + messages
    return [SystemMessage(content=system)] + messages


def _build_chat_graph():
    """LangGraph create_react_agent — REPORT_TOOLS를 도구로 사용하는 에이전트 그래프."""
    return create_react_agent(
        model=_make_llm(),
        tools=REPORT_TOOLS,
        state_schema=ReportState,
        state_modifier=_report_state_modifier,
    )


_chat_graph = _build_chat_graph()


# ── HITL 보고서 검토 그래프 ──────────────────────────────────────────────
async def _review_propose_node(state: ReportReviewState) -> dict:
    llm = ChatOpenAI(model=MODEL, temperature=0.1, api_key=os.environ["OPENAI_API_KEY"])
    system = _build_system_with_knowledge(state.get("knowledge", []))

    response = await llm.ainvoke([
        SystemMessage(content=system),
        HumanMessage(content=review_propose_prompt(
            state.get("agenda") or "", state.get("report_content", "")
        )),
    ])
    text = response.content
    match = re.search(r'\{.*\}', text, re.DOTALL)
    proposed = None
    if match:
        try:
            proposed = json.loads(match.group())
        except Exception:
            pass

    if not proposed:
        proposed = {"score": 50, "feedback": ["구조화된 검토를 수행했습니다."], "element_scores": [], "missing_elements": [], "improvement_suggestions": []}

    feedback = interrupt(proposed)

    if feedback.get("approved"):
        return {"proposed_review": proposed}
    return {"proposed_review": None}


def _build_review_graph():
    builder = StateGraph(ReportReviewState)
    builder.add_node("review", _review_propose_node)
    builder.add_edge(START, "review")
    builder.add_edge("review", END)
    return builder.compile()

_review_graph = _build_review_graph()


# ── Public API ─────────────────────────────────────────────────────────────
async def chat_stream(
    message: str,
    chat_history: List[dict],
    knowledge: List[dict] = None,
    meeting_id: int = 0,
    meeting_context: str = "",
    reports_info: List[dict] = None,
) -> AsyncGenerator[str, None]:
    history = _to_base_messages(chat_history[-10:])
    input_msgs = history + [HumanMessage(content=message)]
    config = {"configurable": {"thread_id": str(uuid.uuid4())}}

    async for event in _chat_graph.astream_events(
        {
            "messages": input_msgs,
            "knowledge": knowledge or [],
            "reports_info": reports_info or [],
            "meeting_context": meeting_context,
        },
        config,
        version="v2",
    ):
        if event["event"] == "on_chat_model_stream":
            chunk = event["data"]["chunk"]
            if chunk.content:
                yield chunk.content


async def global_review_stream(
    reports_info: List[dict],
    chat_history: List[dict],
    knowledge: List[dict] = None,
    meeting_id: int = 0,
    meeting_context: str = "",
) -> AsyncGenerator[str, None]:
    reports_text = "\n\n".join([
        f"[{r.get('presenter_name','')} - {r.get('file_name','')}]\n상태: {r.get('status','')}"
        for r in reports_info
    ])
    user_msg = f"다음 보고서 목록을 종합 검토해주세요:\n{reports_text}"

    history = _to_base_messages(chat_history[-8:])
    input_msgs = history + [HumanMessage(content=user_msg)]
    config = {"configurable": {"thread_id": str(uuid.uuid4())}}

    async for event in _chat_graph.astream_events(
        {
            "messages": input_msgs,
            "knowledge": knowledge or [],
            "reports_info": reports_info,
            "meeting_context": meeting_context,
        },
        config,
        version="v2",
    ):
        if event["event"] == "on_chat_model_stream":
            chunk = event["data"]["chunk"]
            if chunk.content:
                yield chunk.content


async def review_report(
    report_content: str,
    agenda: str = "",
    knowledge: List[dict] = None,
) -> dict:
    system = _build_system_with_knowledge(knowledge or [])
    llm = ChatOpenAI(model=MODEL, temperature=0.1, api_key=os.environ["OPENAI_API_KEY"])
    response = await llm.ainvoke([
        SystemMessage(content=system),
        HumanMessage(content=review_direct_prompt(agenda, report_content)),
    ])
    text = response.content
    match = re.search(r'\{.*\}', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except Exception:
            pass
    return {
        "score": 50,
        "feedback": ["발제자료를 검토했습니다. 12대 필수요소를 갖추어 다시 제출해 주세요."],
        "element_scores": [],
        "principles": {},
        "missing_elements": [],
    }


async def start_report_review(
    thread_id: str,
    report_content: str,
    agenda: str = "",
    knowledge: List[dict] = None,
) -> dict:
    config = {"configurable": {"thread_id": thread_id}}
    await _review_graph.ainvoke(
        {
            "messages": [],
            "report_content": report_content,
            "agenda": agenda,
            "knowledge": knowledge or [],
            "proposed_review": None,
        },
        config,
    )
    state = _review_graph.get_state(config)
    if state.tasks and state.tasks[0].interrupts:
        proposed = state.tasks[0].interrupts[0].value
        return {"status": "pending", "proposed": proposed}
    return {"status": "error", "proposed": None}


async def confirm_report_review(
    thread_id: str,
    approved: bool,
    title: str = "",
    content: str = "",
    meeting_id: int = None,
) -> dict:
    config = {"configurable": {"thread_id": thread_id}}
    result = await _review_graph.ainvoke(
        Command(resume={"approved": approved}),
        config,
    )
    if approved:
        review = result.get("proposed_review")

        if review and content:
            try:
                from agents import knowledge_manager as _ka
                await _ka.store_report(
                    title=title or "보고서",
                    content=content,
                    meeting_id=meeting_id,
                    score=review.get("score"),
                )
            except Exception:
                pass

        return {"status": "confirmed", "review": review}
    return {"status": "rejected"}


async def status_stream(
    meeting_status: dict,
    user_role: str,
    active_knowledge: List[dict] = None,
    chat_history: List[dict] = None,
    message: str = "현재 회의체 현황을 알려주세요.",
    meeting_id: int = 0,
    user_name: str = "",
    meeting_context: str = "",
) -> AsyncGenerator[str, None]:
    import json as _json
    status_text = _json.dumps(meeting_status, ensure_ascii=False, indent=2)
    user_label = f"{user_name}님" if user_name else "담당자"
    role_label = {"admin": "운영자", "presenter": "발제자", "SECRETARY": "운영자"}.get(user_role, user_role)

    context_block = f"[회의체 현황 데이터]\n{status_text}"
    if meeting_context and meeting_context.strip():
        context_block += f"\n\n[회의체 맥락]\n{meeting_context}"

    system_msgs: List[BaseMessage] = [
        SystemMessage(content=STATUS_STREAM_SYSTEM),
        HumanMessage(content=status_stream_context(user_label, role_label, context_block)),
        AIMessage(content=f"안녕하세요, {user_label}. 무엇이든 말씀해 주세요."),
    ]

    history = _to_base_messages((chat_history or [])[-8:])
    input_msgs = history + [HumanMessage(content=message)]
    config = {"configurable": {"thread_id": str(uuid.uuid4())}}

    async for event in _chat_graph.astream_events(
        {
            "messages": system_msgs + input_msgs,
            "knowledge": active_knowledge or [],
            "reports_info": [],
            "meeting_context": meeting_context,
        },
        config,
        version="v2",
    ):
        if event["event"] == "on_chat_model_stream":
            chunk = event["data"]["chunk"]
            if chunk.content:
                yield chunk.content
