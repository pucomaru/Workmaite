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
    REPORT_REVIEW_SYSTEM,
    review_propose_prompt,
    review_direct_prompt,
    STATUS_STREAM_SYSTEM,
    status_stream_context,
    ANALYZE_FILE_SYSTEM,
    analyze_file_human,
)
from agent_logging import log_agent_run

MODEL = os.environ["OPENAI_MODEL"]


# ── State ─────────────────────────────────────────────────────────────────
class ReportState(TypedDict):
    messages: Annotated[List[BaseMessage], add_messages]
    remaining_steps: RemainingSteps
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
        stream_usage=True,
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
        prompt=_report_state_modifier,
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


# ── 아카이브 파일 검토 그래프 (LangGraph) ──────────────────────────────────
class ArchiveFileState(TypedDict):
    file_name: str
    file_type: str
    dept_name: str
    file_content: str
    graph_context: str
    candidate_agendas: List[dict]
    retrieved_context: str
    result: Optional[dict]


def _candidate_agendas_to_str(candidate_agendas: List[dict]) -> str:
    lines = []
    for ag in candidate_agendas or []:
        if not isinstance(ag, dict):
            continue
        ag_id = ag.get("id")
        content = (ag.get("content") or "").strip()
        if ag_id is None or not content:
            continue
        lines.append(f"- id={ag_id} | {content}")
    return "\n".join(lines)


async def _archive_retrieve_node(state: ArchiveFileState) -> dict:
    """Neo4j 지식베이스에서 파일과 관련된 회의록·안건 맥락을 검색합니다."""
    from agents.knowledge_manager import search_knowledge

    query = " ".join(filter(None, [
        state.get("file_name", ""),
        (state.get("file_content", "") or "")[:500],
    ])).strip()
    if not query:
        return {"retrieved_context": ""}

    try:
        minutes = await search_knowledge(query, node_type="Minutes", k=2)
        agendas = await search_knowledge(query, node_type="Agenda", k=3)
    except Exception as e:
        return {"retrieved_context": f"[지식 검색 실패: {e}]"}

    lines = []
    for r in agendas:
        lines.append(f"[안건] {r.get('title','?')}: {r.get('content','')[:150]}")
    for r in minutes:
        lines.append(f"[회의록] {r.get('title','?')}: {r.get('content','')[:150]}")
    return {"retrieved_context": "\n".join(lines)}


async def _archive_analyze_node(state: ArchiveFileState) -> dict:
    """검토 결과 JSON을 생성하고 matched_agenda를 후보 목록으로 검증합니다."""
    llm = _make_llm(temperature=0.2)

    candidate_str = _candidate_agendas_to_str(state.get("candidate_agendas", []))
    graph_context = state.get("graph_context", "") or ""
    retrieved = state.get("retrieved_context", "")
    if retrieved:
        graph_context = f"{graph_context}\n\n[관련 지식 검색 결과]\n{retrieved}".strip()

    response = await llm.ainvoke([
        SystemMessage(content=ANALYZE_FILE_SYSTEM),
        HumanMessage(content=analyze_file_human(
            state.get("file_name", ""),
            state.get("file_type", ""),
            state.get("dept_name", ""),
            state.get("file_content", ""),
            graph_context,
            candidate_str,
        )),
    ])

    text = (response.content or "").strip()
    return {"result": _parse_archive_result(text, state.get("candidate_agendas", []))}


def _parse_archive_result(text: str, candidate_agendas: List[dict]) -> dict:
    """LLM 응답 텍스트에서 JSON을 추출하고 matched_agendas를 후보로 검증합니다."""
    match = re.search(r'\{[\s\S]*\}', text or "")
    parsed = {}
    if match:
        try:
            parsed = json.loads(match.group(0))
        except Exception:
            parsed = {}

    # matched_agendas 환각 방지: 후보 목록에 있는 id만 허용 (다중 지원)
    valid_ids = {
        str(ag.get("id"))
        for ag in candidate_agendas or []
        if isinstance(ag, dict) and ag.get("id") is not None
    }
    raw_matched = parsed.get("matched_agendas")
    if raw_matched is None:
        # 구버전 호환: 단일 matched_agenda 도 수용
        single = parsed.get("matched_agenda")
        raw_matched = [single] if isinstance(single, dict) else []
    matched_agendas = []
    seen_ids = set()
    for m in raw_matched if isinstance(raw_matched, list) else []:
        if not isinstance(m, dict):
            continue
        mid = str(m.get("id"))
        if mid in valid_ids and mid not in seen_ids:
            seen_ids.add(mid)
            matched_agendas.append({
                "id": mid,
                "content": m.get("content"),
                "reason": m.get("reason", ""),
            })

    return {
        "score": int(parsed.get("score", 70)),
        "feedback": parsed.get("feedback", []),
        "matched_agendas": matched_agendas,
        "agendas": parsed.get("agendas", []),
        "related_depts": parsed.get("related_depts", []),
    }


def _build_archive_file_graph():
    builder = StateGraph(ArchiveFileState)
    builder.add_node("retrieve", _archive_retrieve_node)
    builder.add_node("analyze", _archive_analyze_node)
    builder.add_edge(START, "retrieve")
    builder.add_edge("retrieve", "analyze")
    builder.add_edge("analyze", END)
    return builder.compile()


_archive_file_graph = _build_archive_file_graph()


@log_agent_run(
    "archive_analyze",
    user_id="user_id",
    meeting_id="meeting_id",
    capture_output=lambda r: r if isinstance(r, dict) else None,
)
async def analyze_archive_file(
    file_name: str,
    file_type: str,
    dept_name: str,
    file_content: str,
    graph_context: str = "",
    candidate_agendas: List[dict] = None,
    user_id: Optional[int] = None,
    meeting_id: Optional[int] = None,
) -> dict:
    """아카이브 파일 검토 LangGraph 실행 → 검토 결과 dict 반환."""
    config = {"configurable": {"thread_id": str(uuid.uuid4())}}
    final_state = await _archive_file_graph.ainvoke(
        {
            "file_name": file_name,
            "file_type": file_type,
            "dept_name": dept_name,
            "file_content": file_content,
            "graph_context": graph_context,
            "candidate_agendas": candidate_agendas or [],
            "retrieved_context": "",
            "result": None,
        },
        config,
    )
    return final_state.get("result") or {
        "score": 70,
        "feedback": ["검토 결과를 생성하지 못했습니다."],
        "matched_agendas": [],
        "agendas": [],
        "related_depts": [],
    }


@log_agent_run(
    "archive_analyze_stream",
    user_id="user_id",
    meeting_id="meeting_id",
    capture_output=lambda ev: ev.get("data") if isinstance(ev, dict) and ev.get("type") == "result" else None,
)
async def analyze_archive_file_stream(
    file_name: str,
    file_type: str,
    dept_name: str,
    file_content: str,
    graph_context: str = "",
    candidate_agendas: List[dict] = None,
    user_id: Optional[int] = None,
    meeting_id: Optional[int] = None,
) -> AsyncGenerator[dict, None]:
    """아카이브 파일 검토를 스트리밍으로 실행 → 진행 상태/토큰/최종 결과 이벤트를 yield."""
    candidate_agendas = candidate_agendas or []

    # 1. 관련 지식 검색 (retrieve)
    yield {"type": "status", "stage": "retrieve", "message": "관련 회의록·안건을 검색하고 있습니다…"}
    state = {
        "file_name": file_name,
        "file_type": file_type,
        "dept_name": dept_name,
        "file_content": file_content,
        "graph_context": graph_context,
        "candidate_agendas": candidate_agendas,
        "retrieved_context": "",
    }
    try:
        retrieved = await _archive_retrieve_node(state)
        state.update(retrieved)
    except Exception as e:
        state["retrieved_context"] = f"[지식 검색 실패: {e}]"

    # 2. LLM 검토 스트리밍 (analyze)
    yield {"type": "status", "stage": "analyze", "message": "자료를 분석하고 있습니다…"}

    candidate_str = _candidate_agendas_to_str(candidate_agendas)
    ctx = state.get("graph_context", "") or ""
    retrieved_ctx = state.get("retrieved_context", "")
    if retrieved_ctx:
        ctx = f"{ctx}\n\n[관련 지식 검색 결과]\n{retrieved_ctx}".strip()

    llm = _make_llm(temperature=0.2)
    messages = [
        SystemMessage(content=ANALYZE_FILE_SYSTEM),
        HumanMessage(content=analyze_file_human(
            file_name, file_type, dept_name, file_content, ctx, candidate_str,
        )),
    ]

    full_text = ""
    try:
        async for chunk in llm.astream(messages):
            token = chunk.content or ""
            if token:
                full_text += token
                yield {"type": "token", "content": token}
    except Exception as e:
        yield {
            "type": "result",
            "data": {
                "score": 70,
                "feedback": [f"AI 분석 중 오류: {str(e)}", "수동으로 검토해 주세요."],
                "matched_agendas": [],
                "agendas": [{"content": f"{file_name} 관련 안건 검토", "department": dept_name}],
                "related_depts": [],
            },
        }
        return

    # 3. 최종 결과 파싱·검증
    result = _parse_archive_result(full_text, candidate_agendas)
    yield {"type": "result", "data": result}

