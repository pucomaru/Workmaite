import logging
import os
import json
import re
import uuid
from typing import Any, AsyncGenerator, List, Optional, Annotated, cast
from typing_extensions import TypedDict

from llm.llm_factory import StructuredOutputError, ainvoke_structured, llm_factory
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
    ANALYZE_FILE_SYSTEM,
    analyze_file_human,
)
from llm.agent_logging import log_agent_run

MODEL = os.environ["OPENAI_MODEL"]
logger = logging.getLogger(__name__)


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
    feedback: List[str] = Field(
        default_factory=list, description="구체적인 피드백 항목들"
    )


class ElementScore(BaseModel):
    """12대 필수요소 개별 평가 (P3A-2)."""

    id: int = Field(0, description="요소 번호 1-12")
    name: str = Field("", description="요소 이름")
    present: bool = Field(False, description="요소 존재 여부")
    score: int = Field(0, ge=0, le=100, description="present=false면 0")
    comment: str = Field("", description="평가 코멘트")


class ReviewPrinciples(BaseModel):
    """5대 보고 원칙 충족 여부."""

    so_what: bool = False
    one_page_one_message: bool = False
    data_based: bool = False
    decision_focused: bool = False
    concise: bool = False


class ProposedReview(BaseModel):
    """HITL 검토 제안 (review_propose_prompt의 JSON 스펙)."""

    score: int = Field(..., ge=0, le=100)
    feedback: List[str] = Field(default_factory=list)
    element_scores: List[ElementScore] = Field(default_factory=list)
    missing_elements: List[str] = Field(default_factory=list)
    improvement_suggestions: List[str] = Field(default_factory=list)


class DirectReview(BaseModel):
    """직접 검토 (review_direct_prompt의 JSON 스펙)."""

    score: int = Field(..., ge=0, le=100)
    feedback: List[str] = Field(default_factory=list)
    element_scores: List[ElementScore] = Field(default_factory=list)
    principles: ReviewPrinciples = Field(default_factory=ReviewPrinciples)
    missing_elements: List[str] = Field(default_factory=list)


# ── Archive Analysis Schemas ───────────────────────────────────────────────
class ArchiveSubScore(BaseModel):
    score: int = Field(0, ge=0)
    max: int = Field(0, ge=0)


class ArchiveCategoryResult(BaseModel):
    score: int = Field(0, ge=0, le=100)
    max: int = Field(0)
    sub_scores: dict[str, ArchiveSubScore] = Field(default_factory=dict)
    strengths: List[str] = Field(default_factory=list)
    improvements: List[str] = Field(default_factory=list)


class ArchiveTopImprovement(BaseModel):
    category: str = Field("")
    action: str = Field("")


class ArchiveMatchedAgenda(BaseModel):
    id: str = Field("")
    content: str = Field("")
    reason: str = Field("")


class ArchiveAnalysisResult(BaseModel):
    score: int = Field(0, ge=0, le=100)
    detail_scores: dict[str, ArchiveCategoryResult] = Field(default_factory=dict)
    top_improvements: List[ArchiveTopImprovement] = Field(default_factory=list)
    feedback: List[str] = Field(default_factory=list)
    matched_agendas: List[ArchiveMatchedAgenda] = Field(default_factory=list)
    agendas: List[dict] = Field(default_factory=list)
    related_depts: List[str] = Field(default_factory=list)


# ── LLM ───────────────────────────────────────────────────────────────────
def _make_llm(temperature: float = 0.2) -> ChatOpenAI:
    return llm_factory("review", temperature=temperature)


def _build_system_with_knowledge(
    knowledge: List[dict], meeting_context: str = ""
) -> str:
    system = REPORT_REVIEW_SYSTEM
    if meeting_context:
        system += f"\n\n[회의체 맥락 — 이 정보를 항상 참고하세요]\n{meeting_context}"
    if knowledge:
        criteria = "\n".join(
            [f"- {k.get('title', '')}: {k.get('content', '')[:100]}" for k in knowledge]
        )
        system += f"\n\n[보고서 검토 기준]\n{criteria}"
    return system


def _to_base_messages(messages: List[dict]) -> List[BaseMessage]:
    result: List[BaseMessage] = []
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
    """보고서 검토에 필요한 관련 회의록·판단 기준·업로드 보고서를 검색합니다.

    Args:
        query: 검색할 내용 (보고서 주제, 검토 기준 등)
    """
    from agents.knowledge_manager import search_knowledge

    minutes_results = await search_knowledge(query, node_type="Minutes", k=3)
    all_results = minutes_results
    if not all_results:
        return "관련 참고 자료를 찾지 못했습니다."
    lines = [
        f"[{r.get('title', '?')}]: {r.get('content', '')[:200]}"
        for r in all_results[:5]
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
        f"[안건] {r.get('title', '?')}: {r.get('content', '')[:150]}"
        for r in results[:3]
    ]
    return "\n".join(lines)


REPORT_TOOLS: list = [search_review_references, get_report_agenda_context]


# ── Chat graph ─────────────────────────────────────────────────────────────────
def _report_state_modifier(state: ReportState) -> List[BaseMessage]:
    system = _build_system_with_knowledge(
        state.get("knowledge", []), state.get("meeting_context", "")
    )
    messages = list(state.get("messages", []))
    reports_info = state.get("reports_info", [])
    if reports_info:
        reports_text = "\n\n".join(
            [
                f"[{r.get('presenter_name', '')} - {r.get('file_name', '')}]\n상태: {r.get('status', '')}"
                for r in reports_info
            ]
        )
        messages = [
            HumanMessage(content=f"다음 보고서 목록을 검토해주세요:\n{reports_text}")
        ] + messages
    return [SystemMessage(content=system)] + messages


def _build_chat_graph():
    return create_react_agent(
        model=_make_llm(),
        tools=REPORT_TOOLS,
        state_schema=ReportState,
        prompt=_report_state_modifier,
    )


_chat_graph = _build_chat_graph()


# ── HITL 보고서 검토 그래프 ──────────────────────────────────────────────
async def _review_propose_node(state: ReportReviewState) -> dict:
    llm = llm_factory("review", temperature=0.1, streaming=False)
    system = _build_system_with_knowledge(state.get("knowledge", []))

    # structured output — 파싱 실패 시 가짜 score=50로 위장하지 않고 명시적으로 실패한다 (P3A-2, H-2)
    result = await ainvoke_structured(
        llm,
        ProposedReview,
        [
            SystemMessage(content=system),
            HumanMessage(
                content=review_propose_prompt(
                    state.get("agenda") or "", state.get("report_content", "")
                )
            ),
        ],
    )
    proposed = result.model_dump()

    feedback = interrupt(proposed)

    if feedback.get("approved"):
        return {"proposed_review": proposed}
    return {"proposed_review": None}


def _build_review_graph():
    builder = StateGraph(ReportReviewState)
    builder.add_node("review", _review_propose_node)
    builder.add_edge(START, "review")
    builder.add_edge("review", END)
    # 체크포인터 필수 — interrupt/resume은 영속 상태 위에서만 동작 (P3A-1, H-1)
    from llm.graph_runtime import get_checkpointer

    return builder.compile(checkpointer=get_checkpointer())


_review_graph = None


def _get_review_graph():
    """체크포인터는 앱 시작 후 준비되므로 첫 사용 시점에 compile한다."""
    global _review_graph
    if _review_graph is None:
        _review_graph = _build_review_graph()
    return _review_graph


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
    reports_text = "\n\n".join(
        [
            f"[{r.get('presenter_name', '')} - {r.get('file_name', '')}]\n상태: {r.get('status', '')}"
            for r in reports_info
        ]
    )
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
    llm = llm_factory("review", temperature=0.1, streaming=False)
    # structured output — 실패 시 StructuredOutputError 전파 (가짜 score=50 fabrication 제거, P3A-2)
    result = await ainvoke_structured(
        llm,
        DirectReview,
        [
            SystemMessage(content=system),
            HumanMessage(content=review_direct_prompt(agenda, report_content)),
        ],
    )
    return result.model_dump()


async def start_report_review(
    thread_id: str,
    report_content: str,
    agenda: str = "",
    knowledge: List[dict] = None,
) -> dict:
    config = {"configurable": {"thread_id": thread_id}}
    graph = _get_review_graph()
    try:
        await graph.ainvoke(
            {
                "messages": [],
                "report_content": report_content,
                "agenda": agenda,
                "knowledge": knowledge or [],
                "proposed_review": None,
            },
            config,
        )
    except StructuredOutputError as e:
        return {"status": "error", "proposed": None, "message": str(e)}
    state = await graph.aget_state(config)
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
    result = await _get_review_graph().ainvoke(
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


# ── 아카이브 파일 검토 ─────────────────────────────────────────────────────
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
    from agents.knowledge_manager import search_knowledge

    file_name = state.get("file_name", "")
    dept_name = state.get("dept_name", "")
    content = state.get("file_content", "") or ""
    # 파일명이 "보고자료_최종.pdf"처럼 내용을 담지 않는 경우를 보완하기 위해
    # 단순 content[:500] 대신 의미 있는 단락 우선 추출
    paragraphs = [
        p.strip() for p in content.split("\n") if p.strip() and len(p.strip()) > 15
    ]
    content_excerpt = " ".join(paragraphs[:5])[:600] if paragraphs else content[:500]
    query = " ".join(filter(None, [dept_name, file_name, content_excerpt])).strip()
    if not query:
        return {"retrieved_context": ""}

    try:
        minutes = await search_knowledge(query, node_type="Minutes", k=2)
        agendas = await search_knowledge(query, node_type="Agenda", k=3)
    except Exception as e:
        return {"retrieved_context": f"[지식 검색 실패: {e}]"}

    lines = []
    for r in agendas:
        lines.append(f"[안건] {r.get('title', '?')}: {r.get('content', '')[:150]}")
    for r in minutes:
        lines.append(f"[회의록] {r.get('title', '?')}: {r.get('content', '')[:150]}")
    return {"retrieved_context": "\n".join(lines)}


async def _archive_analyze_node(state: ArchiveFileState) -> dict:
    candidate_str = _candidate_agendas_to_str(state.get("candidate_agendas", []))
    graph_context = state.get("graph_context", "") or ""
    retrieved = state.get("retrieved_context", "")
    if retrieved:
        graph_context = f"{graph_context}\n\n[관련 지식 검색 결과]\n{retrieved}".strip()

    messages = [
        SystemMessage(content=ANALYZE_FILE_SYSTEM),
        HumanMessage(
            content=analyze_file_human(
                state.get("file_name", ""),
                state.get("file_type", ""),
                state.get("dept_name", ""),
                state.get("file_content", ""),
                graph_context,
                candidate_str,
            )
        ),
    ]
    candidate_agendas = state.get("candidate_agendas", [])

    try:
        llm = llm_factory("review", temperature=0.1, streaming=False)
        structured = await ainvoke_structured(
            llm, ArchiveAnalysisResult, messages, retries=1
        )
        return {
            "result": _format_archive_result(structured.model_dump(), candidate_agendas)
        }
    except StructuredOutputError as e:
        logger.warning(
            f"[archive-analyze] structured output 실패, 자유 텍스트 폴백: {e}"
        )
        llm_fallback = _make_llm(temperature=0.2)
        response = await llm_fallback.ainvoke(messages)
        text = cast(str, response.content or "").strip()
        return {"result": _parse_archive_result(text, candidate_agendas)}


_DETAIL_SCORE_SCHEMA: dict[str, dict[str, Any]] = {
    "목적및배경": {
        "max": 15,
        "subs": {"목적명확성": 5, "배경논리성": 5, "보고범위대상": 5},
    },
    "현황분석": {
        "max": 20,
        "subs": {"데이터신뢰성": 7, "문제핵심도출": 7, "내외부환경균형": 6},
    },
    "핵심내용": {
        "max": 20,
        "subs": {"논리구조": 7, "MECE충족도": 7, "핵심메시지전달": 6},
    },
    "실행계획": {
        "max": 20,
        "subs": {"SMART충족": 7, "일정자원계획": 7, "우선순위의존관계": 6},
    },
    "기대효과": {
        "max": 15,
        "subs": {"정량적효과": 5, "정성적효과": 5, "목적과연결성": 5},
    },
    "리스크및대안": {"max": 10, "subs": {"리스크식별": 5, "대응방식대안": 5}},
}


def _validate_detail_scores(raw: dict) -> dict:
    result = {}
    for key, schema in _DETAIL_SCORE_SCHEMA.items():
        max_score = schema["max"]
        item = raw.get(key, {}) if isinstance(raw, dict) else {}
        if not isinstance(item, dict):
            item = {}

        raw_subs = item.get("sub_scores", {})
        if not isinstance(raw_subs, dict):
            raw_subs = {}
        sub_scores = {}
        for sub_key, sub_max in schema["subs"].items():
            sub_item = raw_subs.get(sub_key, {})
            sub_score = sub_item.get("score", 0) if isinstance(sub_item, dict) else 0
            sub_scores[sub_key] = {
                "score": max(0, min(int(sub_score), sub_max)),
                "max": sub_max,
            }

        computed = sum(v["score"] for v in sub_scores.values())
        raw_score = item.get("score", 0)
        score = (
            computed
            if raw_subs
            else max(
                0,
                min(
                    int(raw_score if isinstance(raw_score, (int, float)) else 0),
                    max_score,
                ),
            )
        )

        result[key] = {
            "score": score,
            "max": max_score,
            "sub_scores": sub_scores,
            "strengths": item.get("strengths", [])
            if isinstance(item.get("strengths"), list)
            else [],
            "improvements": item.get("improvements", [])
            if isinstance(item.get("improvements"), list)
            else [],
        }
    return result


def _format_archive_result(parsed: dict, candidate_agendas: List[dict]) -> dict:
    """dict (structured output model_dump 또는 regex 파싱 결과) → 검증된 최종 결과.

    _validate_detail_scores가 sub_score 합계를 재계산하고 max 값을 스키마 기준으로 교정한다.
    """
    raw_detail = parsed.get("detail_scores", {})
    detail_scores = _validate_detail_scores(raw_detail)
    computed_score = sum(v["score"] for v in detail_scores.values())
    # 평가 실패 시 그럴듯한 점수를 주지 않는다 — LLM이 점수를 주면 존중, 없으면 0.
    score = computed_score if raw_detail else int(parsed.get("score") or 0)

    valid_ids = {
        str(ag.get("id"))
        for ag in candidate_agendas or []
        if isinstance(ag, dict) and ag.get("id") is not None
    }
    raw_matched = parsed.get("matched_agendas") or []
    if not isinstance(raw_matched, list):
        raw_matched = []
    matched_agendas: List[dict] = []
    seen_ids: set[str] = set()
    for m in raw_matched:
        if not isinstance(m, dict):
            continue
        mid = str(m.get("id", ""))
        if mid in valid_ids and mid not in seen_ids:
            seen_ids.add(mid)
            matched_agendas.append(
                {"id": mid, "content": m.get("content"), "reason": m.get("reason", "")}
            )

    raw_top = parsed.get("top_improvements") or []
    top_improvements = [
        t.model_dump() if hasattr(t, "model_dump") else t
        for t in raw_top
        if t and (isinstance(t, dict) or hasattr(t, "model_dump"))
    ]

    return {
        "score": score,
        "detail_scores": detail_scores,
        "top_improvements": top_improvements,
        "feedback": parsed.get("feedback", []),
        "matched_agendas": matched_agendas,
        "agendas": parsed.get("agendas", []),
        "related_depts": parsed.get("related_depts", []),
    }


def _parse_archive_result(text: str, candidate_agendas: List[dict]) -> dict:
    """자유 텍스트에서 JSON 추출 → _format_archive_result (regex 폴백 전용)."""
    match = re.search(r"\{[\s\S]*\}", text or "")
    parsed: dict = {}
    if match:
        try:
            parsed = json.loads(match.group(0))
        except Exception:
            parsed = {}
    # 레거시 단수 키 처리
    if "matched_agendas" not in parsed:
        single = parsed.get("matched_agenda")
        parsed["matched_agendas"] = [single] if isinstance(single, dict) else []
    return _format_archive_result(parsed, candidate_agendas)


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
        "score": 0,
        "feedback": [
            "⚠️ AI 평가에 오류가 발생했습니다.",
            "다시 시도하거나 수동으로 검토해 주세요.",
        ],
        "matched_agendas": [],
        "agendas": [],
        "related_depts": [],
    }


@log_agent_run(
    "archive_analyze_stream",
    user_id="user_id",
    meeting_id="meeting_id",
    capture_output=lambda ev: (
        ev.get("data") if isinstance(ev, dict) and ev.get("type") == "result" else None
    ),
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
    candidate_agendas = candidate_agendas or []

    yield {
        "type": "status",
        "stage": "retrieve",
        "message": "관련 회의록·안건을 검색하고 있습니다…",
    }
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
        retrieved = await _archive_retrieve_node(cast(ArchiveFileState, state))
        state.update(retrieved)
    except Exception as e:
        state["retrieved_context"] = f"[지식 검색 실패: {e}]"

    yield {"type": "status", "stage": "analyze", "message": "자료를 분석하고 있습니다…"}

    candidate_str = _candidate_agendas_to_str(candidate_agendas)
    ctx = cast(str, state.get("graph_context", "") or "")
    retrieved_ctx = state.get("retrieved_context", "")
    if retrieved_ctx:
        ctx = f"{ctx}\n\n[관련 지식 검색 결과]\n{retrieved_ctx}".strip()

    messages = [
        SystemMessage(content=ANALYZE_FILE_SYSTEM),
        HumanMessage(
            content=analyze_file_human(
                file_name,
                file_type,
                dept_name,
                file_content,
                ctx,
                candidate_str,
            )
        ),
    ]

    # 1단계: 스트리밍으로 토큰 전달 (사용자 UX — 실시간 응답 경험)
    full_text = ""
    try:
        async for chunk in _make_llm(temperature=0.2).astream(messages):
            token = cast(str, chunk.content or "")
            if token:
                full_text += token
                yield {"type": "token", "content": token}
    except Exception as e:
        yield {
            "type": "result",
            "data": {
                "score": 0,
                "feedback": [
                    "⚠️ AI 평가에 오류가 발생했습니다.",
                    f"오류: {str(e)}",
                    "다시 시도하거나 수동으로 검토해 주세요.",
                ],
                "matched_agendas": [],
                "agendas": [
                    {"content": f"{file_name} 관련 안건 검토", "department": dept_name}
                ],
                "related_depts": [],
            },
        }
        return

    # 2단계: structured output으로 신뢰할 수 있는 채점 결과 추출
    # (스트리밍 자유 텍스트는 regex 파싱에 의존해 채점 오류가 무음 발생하므로 별도 호출)
    try:
        llm_structured = llm_factory("review", temperature=0.1, streaming=False)
        structured = await ainvoke_structured(
            llm_structured, ArchiveAnalysisResult, messages, retries=1
        )
        result = _format_archive_result(structured.model_dump(), candidate_agendas)
    except StructuredOutputError:
        # structured output 실패 시 스트리밍 텍스트에서 regex 폴백
        result = _parse_archive_result(full_text, candidate_agendas)

    yield {"type": "result", "data": result}
