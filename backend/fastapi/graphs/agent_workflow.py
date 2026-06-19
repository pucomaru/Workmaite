"""에이전트 워크플로우 (LangGraph StateGraph) — 가드레일·트리아주·재작성·환각검증 일체형.

기존 라이브 경로(routers/supervisor.py::supervisor_chat 의 if/elif 디스패치)는 그대로 두고,
요청된 단계를 갖춘 **실제 그래프**를 추가형으로 제공한다. 기존 안전 컴포넌트를 노드로 재사용:
- LLM: llm_factory (model_override_var=사용자 모델선택 반영 + 전역 토큰훅 자동집계)
- 핸들러: graphs.supervisor_graph._get_agent (도구 기반 react agent, RunnableConfig 스코프)
- 검색/환각근거: graphdb.retrieval_registry.hybrid_search (멀티테넌트 스코프드 벡터+풀텍스트)
- 스코프: core.agent_scope (sub-tool IDOR 가드)

★ fast-mode: triage·query_rewrite·classify(intent+internal/external)를 **단일 LLM 호출**
   (triage_gate)로 병합해 답변 전 지연(TTFT)을 줄인다. 답변 생성·환각검증은 분리.
★ jailbreak 가드는 최전선(routers/supervisor.py::classify_intent)으로 이동 — 라우팅·디스패치보다
   앞단에서 모든 경로 공통 차단(추가 LLM 콜 없이 라우팅 결정에 통합). 이 그래프는 안전 검사된 입력을 전제.

흐름:
  START → triage_gate ─(정보부족)→ clarify → END
                      ├(external)→ external_refuse → END
                      ├(생성요청)→ delegate → END
                      └(내부 Q&A)→ qa_handle → hallucination_guard ─(근거확인)→ END
                                                                  ├(미확인·재시도)→ qa_handle
                                                                  └(재시도소진)→ caveat → END
"""

import asyncio
import logging
import os
from typing import AsyncGenerator, Literal, Optional, TypedDict, cast

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

_MAX_HANDLE_ATTEMPTS = 2  # 환각 가드 재생성 상한(비스트리밍 그래프 전용)

# 환각 근거로 검색할 라벨(벡터+풀텍스트). 내용이 풍부한 라벨 우선.
# AGENT_WORKFLOW_GROUNDING_LABELS=콤마구분 으로 override 가능.
_DEFAULT_GROUNDING_LABELS = ["Minutes", "MinutesChunk", "ReportChunk", "Agenda"]

_CAVEAT_SUFFIX = (
    "\n\n⚠️ 일부 내용은 확인된 근거가 충분치 않을 수 있습니다. "
    "정확한 내용은 해당 회의록·보고서에서 확인해 주세요."
)


# ─── 상태 ────────────────────────────────────────────────────────────────────
class WState(TypedDict, total=False):
    # 입력
    message: str
    history: list  # list[BaseMessage]
    user_id: int
    allowed_meeting_ids: list[int]
    is_admin: bool
    meeting_id: Optional[int]
    thread_id: Optional[str]
    # 파생 (triage_gate가 채움)
    rewritten: str
    intent: str
    qa_type: str  # "internal" | "external"
    plan: str
    answer: str
    clarify_question: Optional[str]
    grounded: bool
    attempts: int


# ─── 구조화 출력 스키마 ────────────────────────────────────────────────────────
class _Gate(BaseModel):
    """fast-mode 통합 게이트 — triage + rewrite + classify를 한 번에.

    (jailbreak는 최전선 routers/supervisor.py::classify_intent 로 이동 — 모든 경로 공통 차단.)
    """

    has_enough_info: bool = Field(
        description="요청을 처리하기에 필요한 정보가 충분하면 true (단순 인사·사용법은 충분으로 본다)"
    )
    clarifying_question: str = Field(
        default="",
        description="정보 부족 시 사용자에게 할 되물음 1개. 충분하면 빈 문자열.",
    )
    plan: str = Field(default="", description="요청 처리 계획 1~2문장")
    rewritten: str = Field(
        description="대화 맥락을 반영해 그 자체로 이해되고 검색에 적합한 한 문장 질의. 의미는 바꾸지 말 것."
    )
    intent: Literal[
        "supervisor_direct",
        "knowledge_manager",
        "task_extractor",
        "minutes_generator",
        "report_reviewer",
    ] = Field(description="요청을 처리할 에이전트")
    qa_type: Literal["internal", "external"] = Field(
        description="회의체 데이터로 답하는 내부질의=internal / 외부 세상 사실확인(날씨·시세·일반상식 등)=external"
    )


class _Grounding(BaseModel):
    grounded: bool = Field(
        description="답변이 제공된 근거로 뒷받침되면 true. 근거에 없는 사실 단정(수치·이름·일정)이 있으면 false. "
        "답변이 '확인되지 않았다'고 정직하게 말하면 true."
    )
    reason: str = Field(description="판단 근거 한 문장")


# ─── LLM 헬퍼 (모델선택·토큰훅은 llm_factory가 처리) ───────────────────────────
async def _struct(model_cls, system: str, human: str):
    from llm.llm_factory import llm_factory

    llm = llm_factory("routing", streaming=False).with_structured_output(model_cls)
    return await llm.ainvoke(
        [SystemMessage(content=system), HumanMessage(content=human)]
    )


def _format_history(history) -> str:
    out = []
    for m in (history or [])[-6:]:
        role = "사용자" if isinstance(m, HumanMessage) else "AI"
        out.append(f"{role}: {str(getattr(m, 'content', ''))[:160]}")
    return "\n".join(out) or "(이전 대화 없음)"


def _grounding_labels() -> list[str]:
    env = os.environ.get("AGENT_WORKFLOW_GROUNDING_LABELS")
    if env:
        labels = [x.strip() for x in env.split(",") if x.strip()]
        if labels:
            return labels
    return _DEFAULT_GROUNDING_LABELS


# ─── 게이트 노드 (fast-mode 통합 LLM 1회) ─────────────────────────────────────
_GATE_SYS = (
    "당신은 회의체 운영 지원 AI의 처리 게이트다. (안전성은 상위 단계에서 이미 검사됨.) "
    "사용자 요청에 대해 아래를 한 번에 판단하라.\n"
    "1) has_enough_info: 기본값은 true다. 도구로 조회하거나 합리적으로 추론해 답할 수 있으면 true. "
    "되묻기는 최소화하라 — 정말로 무엇을 묻는지조차 알 수 없을 때만 false로 두고 clarifying_question 1개. "
    "회의체가 불명확하면 되묻지 말고 목록을 조회해 추론하라. 이미 대화에서 답한 정보는 다시 묻지 마라.\n"
    "2) plan: 처리 계획 1~2문장.\n"
    "3) rewritten: 대화 맥락을 반영해 지시대명사를 풀고 단독으로 이해되는 검색 친화 질의로 다시 쓴 질문.\n"
    "4) intent: supervisor_direct(현황·브리핑·목록·일반조회)/knowledge_manager(과거 회의 검색·지식)/"
    "task_extractor(아젠다·과제 추출)/minutes_generator(회의록 작성·요약)/report_reviewer(보고서 검토).\n"
    "5) qa_type: internal(회의체 데이터로 답) / external(날씨·시세·일반상식 등 외부 사실확인)."
)


async def triage_gate(state: WState) -> dict:
    human = (
        f"질문: {state['message']}\n"
        f"현재 보고 있는 회의체 meeting_id: {state.get('meeting_id') or '없음(전역)'}\n"
        f"[최근 대화]\n{_format_history(state.get('history'))}"
    )
    try:
        v = await _struct(_Gate, _GATE_SYS, human)
    except Exception as e:
        # 가용성 우선 — 게이트 실패 시 통과(내부 Q&A로 가정, 원문 사용)
        logger.warning(f"[workflow] triage_gate 실패(통과·원문 사용): {e}")
        return {
            "rewritten": state["message"],
            "intent": "supervisor_direct",
            "qa_type": "internal",
            "plan": "",
        }
    out: dict = {
        "plan": v.plan or "",
        "rewritten": (v.rewritten or state["message"]).strip(),
        "intent": v.intent,
        "qa_type": v.qa_type,
    }
    if not v.has_enough_info:
        out["clarify_question"] = (
            v.clarifying_question or "어떤 회의체에 대한 질문인지 알려주시겠어요?"
        )
    return out


# ─── 종단/핸들러 노드 ─────────────────────────────────────────────────────────
def _clarify(state: WState) -> dict:
    return {"answer": state.get("clarify_question") or "조금 더 자세히 알려주시겠어요?"}


def _external_refuse(state: WState) -> dict:
    return {
        "answer": "현재 서비스 단계에서는 외부 정보(서비스 외부의 사실 확인·일반 상식 등)는 제공하지 않습니다. "
        "회의체 운영(현황·아젠다·회의록·보고서)과 관련된 질문을 도와드릴게요."
    }


def _delegate(state: WState) -> dict:
    label = {
        "task_extractor": "아젠다/과제 추출",
        "minutes_generator": "회의록 작성·요약",
        "report_reviewer": "보고서 검토",
    }.get(state.get("intent", ""), "해당")
    return {
        "answer": f"'{label}' 작업은 해당 화면의 전용 기능에서 진행해 주세요. "
        "이 대화에서는 현황 조회·질의응답을 도와드립니다.",
        "grounded": True,
    }


async def qa_handle(state: WState) -> dict:
    """내부 Q&A 처리 — 도구 기반 react agent로 답을 생성한다(스코프 강제)."""
    from graphs.supervisor_graph import _get_agent
    from core.agent_scope import set_meeting_scope, reset_meeting_scope

    q = state.get("rewritten") or state["message"]
    attempts = state.get("attempts", 0)
    if attempts > 0:
        # 재생성: 환각 가드가 근거 부족 판정 → 더 보수적으로
        q = (
            "다음 질문에 반드시 도구로 확인한 근거에만 기반해 답하고, 확인되지 않으면 "
            f"'확인되지 않았습니다'라고 답하라:\n{q}"
        )

    config = {
        "configurable": {
            "thread_id": state.get("thread_id") or "workflow",
            "user_id": state["user_id"],
            "allowed_meeting_ids": list(state.get("allowed_meeting_ids") or []),
            "is_admin": state.get("is_admin", False),
        }
    }
    scope_token = set_meeting_scope(
        state.get("allowed_meeting_ids") or [], state.get("is_admin", False)
    )
    try:
        msgs = list(state.get("history") or []) + [HumanMessage(content=q)]
        result = await _get_agent().ainvoke({"messages": msgs}, config)
        answer = ""
        for m in reversed(result.get("messages", [])):
            if (
                isinstance(m, AIMessage)
                and isinstance(m.content, str)
                and m.content.strip()
            ):
                answer = m.content
                break
        return {"answer": answer, "attempts": attempts + 1}
    finally:
        reset_meeting_scope(scope_token)


_GROUND_SYS = (
    "주어진 [검색된 근거]만을 기준으로 [답변]에 근거 없는 사실 단정(수치·이름·일정 등)이 있는지 검사하라. "
    "근거로 뒷받침되거나, 답변이 '확인되지 않았다'고 정직하게 말하면 grounded=true. 근거에 없는데 단정하면 false."
)


async def _gather_grounding_context(
    query: str, meeting_ids: Optional[list[int]]
) -> str:
    """여러 라벨에서 근거를 병렬 검색해 합친다(환각 검증용)."""
    from graphdb.retrieval_registry import hybrid_search

    async def _one(label: str) -> list[str]:
        try:
            rows = await hybrid_search(label, query, k=3, meeting_ids=meeting_ids)
            return [
                (r.get("summary") or r.get("content") or r.get("title") or "")
                for r in rows
            ]
        except Exception as e:
            logger.warning(f"[workflow] 근거 검색 실패({label}): {e}")
            return []

    labels = _grounding_labels()
    groups = await asyncio.gather(*[_one(label) for label in labels])
    snippets = [s[:400] for g in groups for s in g if s and s.strip()]
    return "\n".join(snippets[:12]).strip()  # 프롬프트 비대화 방지(상한)


async def hallucination_guard(state: WState) -> dict:
    """여러 벡터 라벨에서 근거를 모아 답변의 사실성(grounding)을 LLM으로 검증한다."""
    ans = (state.get("answer") or "").strip()
    if not ans:
        return {"grounded": True}
    q = state.get("rewritten") or state["message"]
    mids = (
        None if state.get("is_admin") else list(state.get("allowed_meeting_ids") or [])
    )
    try:
        ctx = await _gather_grounding_context(q, mids)
    except Exception as e:
        logger.warning(f"[workflow] 근거 수집 실패(검증 생략): {e}")
        return {"grounded": True}
    if not ctx:
        # 근거 자료가 없으면 환각 판정 불가 — 보수적으로 통과
        return {"grounded": True}
    v = await _struct(_Grounding, _GROUND_SYS, f"[검색된 근거]\n{ctx}\n\n[답변]\n{ans}")
    if not v.grounded:
        logger.info(f"[workflow] 환각 의심: {v.reason}")
    return {"grounded": bool(v.grounded)}


def _caveat(state: WState) -> dict:
    return {"answer": (state.get("answer") or "") + _CAVEAT_SUFFIX}


# ─── 라우팅(조건부 엣지) ──────────────────────────────────────────────────────
def _after_gate(state: WState) -> str:
    if state.get("clarify_question"):
        return "clarify"
    if state.get("qa_type") == "external":
        return "external_refuse"
    if state.get("intent") in (
        "task_extractor",
        "minutes_generator",
        "report_reviewer",
    ):
        return "delegate"
    return "qa_handle"


def _after_ground(state: WState) -> str:
    if state.get("grounded"):
        return "END"
    if state.get("attempts", 0) >= _MAX_HANDLE_ATTEMPTS:
        return "caveat"
    return "qa_handle"


# ─── 그래프 빌드(싱글톤) ──────────────────────────────────────────────────────
_workflow = None


def get_workflow():
    """컴파일된 워크플로우(싱글톤). 모델 선택은 노드별 llm_factory가 요청마다 동적 해석한다."""
    global _workflow
    if _workflow is None:
        b = StateGraph(WState)
        b.add_node("triage_gate", triage_gate)
        b.add_node("clarify", _clarify)
        b.add_node("external_refuse", _external_refuse)
        b.add_node("delegate", _delegate)
        b.add_node("qa_handle", qa_handle)
        b.add_node("hallucination_guard", hallucination_guard)
        b.add_node("caveat", _caveat)

        b.add_edge(START, "triage_gate")
        b.add_conditional_edges(
            "triage_gate",
            _after_gate,
            {
                "clarify": "clarify",
                "external_refuse": "external_refuse",
                "delegate": "delegate",
                "qa_handle": "qa_handle",
            },
        )
        b.add_edge("clarify", END)
        b.add_edge("external_refuse", END)
        b.add_edge("delegate", END)
        b.add_edge("qa_handle", "hallucination_guard")
        b.add_conditional_edges(
            "hallucination_guard",
            _after_ground,
            {"END": END, "caveat": "caveat", "qa_handle": "qa_handle"},
        )
        b.add_edge("caveat", END)
        _workflow = b.compile()
    return _workflow


# ─── 엔트리포인트 (비스트리밍) ────────────────────────────────────────────────
async def run_agent_workflow(
    message: str,
    history: list | None = None,
    *,
    user_id: int,
    allowed_meeting_ids: list[int],
    is_admin: bool = False,
    meeting_id: int | None = None,
    thread_id: str | None = None,
) -> dict:
    """워크플로우 1회 실행 → 최종 결과 dict.

    반환: {answer, intent, qa_type, plan, blocked(bool), needs_clarification(bool), grounded}
    """
    state: WState = {
        "message": message or "",
        "history": history or [],
        "user_id": user_id,
        "allowed_meeting_ids": list(allowed_meeting_ids or []),
        "is_admin": is_admin,
        "meeting_id": meeting_id,
        "thread_id": thread_id,
        "attempts": 0,
    }
    final = await get_workflow().ainvoke(state)
    return {
        "answer": final.get("answer") or final.get("clarify_question") or "",
        "intent": final.get("intent"),
        "qa_type": final.get("qa_type"),
        "plan": final.get("plan"),
        "needs_clarification": bool(final.get("clarify_question")),
        "grounded": final.get("grounded"),
    }


# ─── 엔트리포인트 (스트리밍 — 라이브 SSE용) ───────────────────────────────────
async def run_agent_workflow_stream(
    message: str,
    history_msgs: list,
    *,
    user_id: int,
    allowed_meeting_ids: list[int],
    is_admin: bool,
    meeting_id: int | None = None,
    upcoming_ctx: str = "",
    thread_id: str | None = None,
) -> AsyncGenerator[tuple[str, str], None]:
    """라이브 SSE용 스트리밍 워크플로우 — graphs.supervisor_graph.direct_agent_stream 의 드롭인 대체.

    fast-mode: jailbreak+triage+rewrite+classify를 triage_gate 1회로 통합(답변 전 지연 최소화).
    답변 생성은 검증된 direct_agent_stream(토큰스트림+도구진행+action+스코프+과금)에 위임하고,
    스트림 종료 후 환각 가드(다중 라벨 벡터 근거)에서 미달 시 주의 문구를 덧붙인다.
    노드 로직은 비스트리밍 그래프와 동일 함수를 재사용한다(단일 소스).

    yield (kind, text): "planning" | "token" | "action" — supervisor_chat이 그대로 소비.
    """
    state: WState = {
        "message": message or "",
        "history": history_msgs or [],
        "user_id": user_id,
        "allowed_meeting_ids": list(allowed_meeting_ids or []),
        "is_admin": is_admin,
        "meeting_id": meeting_id,
        "thread_id": thread_id,
        "attempts": 0,
    }

    # 1) 통합 게이트 (fast-mode: 트리아주+재작성+분류 1회. jailbreak는 상위 supervisor_chat 최전선에서 처리)
    yield ("planning", "요청 점검")
    state.update(cast(WState, await triage_gate(state)))

    if state.get("clarify_question"):
        yield ("planning", "추가 정보 필요")
        yield ("token", state["clarify_question"] or "")
        return
    if state.get("qa_type") == "external":
        yield ("token", _external_refuse(state)["answer"])
        return

    # 2) 답변 생성 — 검증된 스트리밍 경로에 위임 (재작성 질의 사용)
    #    (라이브 경로는 바깥 supervisor_chat이 이미 direct/knowledge로 라우팅했으므로 항상 Q&A 처리)
    yield ("planning", "관련 정보 조회")
    from graphs.supervisor_graph import direct_agent_stream

    answer_parts: list[str] = []
    async for kind, text in direct_agent_stream(
        state.get("rewritten") or message,
        history_msgs,
        user_id=user_id,
        allowed_meeting_ids=allowed_meeting_ids,
        is_admin=is_admin,
        meeting_id=meeting_id,
        upcoming_ctx=upcoming_ctx,
        thread_id=thread_id,
    ):
        if kind == "token":
            answer_parts.append(text)
        yield (kind, text)

    # 3) 환각 가드레일 — 스트림은 되돌릴 수 없으므로 재생성 대신 근거 미달 시 주의 문구만 덧붙인다
    answer = "".join(answer_parts).strip()
    if len(answer) < 30:  # 짧은 응답(되물음·근거없음 등)은 검증 생략
        return
    state["answer"] = answer
    try:
        state.update(cast(WState, await hallucination_guard(state)))
    except Exception as e:
        logger.warning(f"[workflow] 환각 검사 실패(생략): {e}")
        return
    if not state.get("grounded", True):
        yield ("token", _CAVEAT_SUFFIX)
