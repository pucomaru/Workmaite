# 보고서 검토 Agent - 보고서 초안을 입력받아 검토/개선안 생성
# HITL (Human-In-The-Loop): 검토 결과에 대한 사용자 Approve/Reject 포함
import os, json, re, uuid
from typing import AsyncGenerator, List, Optional, Annotated
from typing_extensions import TypedDict

from langchain_openai import ChatOpenAI
from langchain_core.messages import BaseMessage, SystemMessage, HumanMessage, AIMessage
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.types import interrupt, Command
from pydantic import BaseModel, Field

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


REVIEW_SYSTEM_PROMPT = """당신은 대기업 발제자료 검토 전문 AI ReportAgent입니다.
발제자료를 아래 **12대 필수요소** 기준으로 평가하고, 5대 핵심 원칙도 함께 점검합니다.

[12대 필수요소]
1. 표지 (Cover Page) — 제목·발제자·일시·장소·문서 보안 등급
2. 목차 (Table of Contents) — 전체 흐름, 10p 이상 필수
3. 요약 (Executive Summary) — 1페이지 내 핵심 문제·제안·기대 효과
4. 배경 및 현황 분석 — 문제 제기 근거, 내부/외부 환경 분석
5. 문제 정의 (Problem Statement) — 수치·사실 기반, 범위·심각도·시급성
6. 목표 설정 (Objectives) — KPI 등 정량/정성 목표, 단기·중기·장기
7. 대안 검토 (Options/Alternatives) — 2개 이상 대안, 장단점·비용·리스크 비교
8. 권고안 (Recommendation) — 최적 방향과 선택 근거, 발제자 확신
9. 실행 계획 (Action Plan) — 단계별 일정·담당·예산, 마일스톤
10. 기대 효과 및 리스크 관리 — ROI 등 정량 효과, 리스크 대응
11. 결론 및 요청 사항 (Conclusion & Ask) — 핵심 3줄, 의사결정 요청 명시
12. 부록 (Appendix) — 상세 데이터, 참고 문헌, 관련 법령

[5대 핵심 원칙]
- So What?: 모든 페이지에 핵심 메시지가 있는가
- 1 Page 1 Message: 슬라이드당 메시지 1개
- 데이터 기반: 주장마다 수치·출처가 있는가
- 의사결정 중심: 결정을 끌어내는 구성인가
- 간결함: 불필요한 내용 없이 핵심만 담았는가

한국어로, 구체적이고 건설적으로 응답합니다."""


def _build_system_with_knowledge(knowledge: List[dict], meeting_context: str = "") -> str:
    system = REVIEW_SYSTEM_PROMPT
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


# ── Chat graph nodes ───────────────────────────────────────────────────────
async def _chat_node(state: ReportState) -> dict:
    system = _build_system_with_knowledge(state.get("knowledge", []), state.get("meeting_context", ""))
    reports_info = state.get("reports_info", [])

    system_msgs: List[BaseMessage] = [SystemMessage(content=system)]
    if reports_info:
        reports_text = "\n\n".join([
            f"[{r.get('presenter_name','')} - {r.get('file_name','')}]\n상태: {r.get('status','')}"
            for r in reports_info
        ])
        system_msgs += [HumanMessage(content=f"다음 보고서 목록을 검토해주세요:\n{reports_text}")]

    llm = _make_llm()
    response = await llm.ainvoke(system_msgs + state["messages"])
    return {"messages": [response]}


def _build_chat_graph():
    builder = StateGraph(ReportState)
    builder.add_node("chat", _chat_node)
    builder.add_edge(START, "chat")
    builder.add_edge("chat", END)
    return builder.compile()

_chat_graph = _build_chat_graph()


# ── HITL 보고서 검토 그래프 ──────────────────────────────────────────────
async def _review_propose_node(state: ReportReviewState) -> dict:
    """보고서 분석 → 검토/개선안 제안 → interrupt()로 사용자 확인 대기."""
    llm = ChatOpenAI(model=MODEL, temperature=0.1, api_key=os.environ["OPENAI_API_KEY"])
    system = _build_system_with_knowledge(state.get("knowledge", []))

    prompt = f"""다음 발제자료를 12대 필수요소 기준으로 검토하세요.

반드시 아래 JSON 형식으로만 응답하세요 (설명 없이 JSON만):
{{
  "score": 75,
  "feedback": ["전체 종합 피드백1", "전체 종합 피드백2"],
  "element_scores": [
    {{"id": 1, "name": "표지", "present": true, "score": 90, "comment": "표지 평가"}},
    {{"id": 2, "name": "목차", "present": false, "score": 0, "comment": "목차 평가"}},
    {{"id": 3, "name": "요약", "present": true, "score": 70, "comment": "요약 평가"}},
    {{"id": 4, "name": "배경 및 현황 분석", "present": false, "score": 0, "comment": "배경 평가"}},
    {{"id": 5, "name": "문제 정의", "present": true, "score": 60, "comment": "문제 정의 평가"}},
    {{"id": 6, "name": "목표 설정", "present": false, "score": 0, "comment": "목표 평가"}},
    {{"id": 7, "name": "대안 검토", "present": false, "score": 0, "comment": "대안 평가"}},
    {{"id": 8, "name": "권고안", "present": true, "score": 80, "comment": "권고안 평가"}},
    {{"id": 9, "name": "실행 계획", "present": false, "score": 0, "comment": "실행 계획 평가"}},
    {{"id": 10, "name": "기대 효과 및 리스크", "present": false, "score": 0, "comment": "기대 효과 평가"}},
    {{"id": 11, "name": "결론 및 요청 사항", "present": true, "score": 65, "comment": "결론 평가"}},
    {{"id": 12, "name": "부록", "present": false, "score": 0, "comment": "부록 평가"}}
  ],
  "missing_elements": ["누락된 요소 목록"],
  "improvement_suggestions": ["개선 제안1", "개선 제안2", "개선 제안3"]
}}

[아젠다]
{state.get('agenda') or '(없음)'}

[발제자료 내용]
{state.get('report_content', '')[:4000]}"""

    response = await llm.ainvoke([SystemMessage(content=system), HumanMessage(content=prompt)])
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

    # HITL: 사용자 확인 대기
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
    """보고서를 12대 필수요소 기준으로 검토하고 점수·피드백·개선안을 반환합니다."""
    system = _build_system_with_knowledge(knowledge or [])
    prompt = f"""다음 발제자료를 12대 필수요소 기준으로 검토하세요.

반드시 아래 JSON 형식으로만 응답하세요 (설명 없이 JSON만):
{{
  "score": 75,
  "feedback": ["전체 종합 피드백1", "전체 종합 피드백2"],
  "element_scores": [
    {{"id": 1, "name": "표지", "present": true, "score": 90, "comment": "제목과 발제자 정보가 명확합니다."}},
    {{"id": 2, "name": "목차", "present": false, "score": 0, "comment": "목차가 없어 전체 흐름 파악이 어렵습니다."}},
    {{"id": 3, "name": "요약 (Executive Summary)", "present": true, "score": 70, "comment": "요약이 있으나 기대 효과가 빠져 있습니다."}},
    {{"id": 4, "name": "배경 및 현황 분석", "present": false, "score": 0, "comment": "배경 분석 없이 바로 본론으로 들어갑니다."}},
    {{"id": 5, "name": "문제 정의", "present": true, "score": 60, "comment": "문제는 언급되나 수치 근거가 부족합니다."}},
    {{"id": 6, "name": "목표 설정", "present": false, "score": 0, "comment": "KPI 등 정량 목표가 없습니다."}},
    {{"id": 7, "name": "대안 검토", "present": false, "score": 0, "comment": "단일 방안만 제시되어 대안 비교가 없습니다."}},
    {{"id": 8, "name": "권고안", "present": true, "score": 80, "comment": "권고 방향은 명확하나 선택 근거가 약합니다."}},
    {{"id": 9, "name": "실행 계획", "present": false, "score": 0, "comment": "일정·담당·예산 계획이 없습니다."}},
    {{"id": 10, "name": "기대 효과 및 리스크", "present": false, "score": 0, "comment": "ROI 및 리스크 대응 방안이 없습니다."}},
    {{"id": 11, "name": "결론 및 요청 사항", "present": true, "score": 65, "comment": "결론은 있으나 구체적인 의사결정 요청이 불명확합니다."}},
    {{"id": 12, "name": "부록", "present": false, "score": 0, "comment": "참고 자료 및 출처가 없습니다."}}
  ],
  "principles": {{
    "so_what": true,
    "one_page_one_message": false,
    "data_based": false,
    "decision_focused": true,
    "concise": true
  }},
  "missing_elements": ["목차", "배경 및 현황 분석", "목표 설정", "대안 검토", "실행 계획", "기대 효과 및 리스크", "부록"]
}}

각 element의 score: present=true면 0-100, present=false면 0.
전체 score는 12개 element 가중 평균 (+ 5대 원칙 보너스 최대 10점).

[아젠다]
{agenda or '(없음)'}

[발제자료 내용]
{report_content[:4000]}"""

    llm = ChatOpenAI(model=MODEL, temperature=0.1, api_key=os.environ["OPENAI_API_KEY"])
    response = await llm.ainvoke([SystemMessage(content=system), HumanMessage(content=prompt)])
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
    """[HITL Step 1] 보고서 검토 제안 → interrupt()로 일시 정지. 제안 결과 반환."""
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
    title: str = "",       # HITL Approve 시 Neo4j 저장에 사용할 보고서 제목
    content: str = "",     # HITL Approve 시 Neo4j 저장에 사용할 보고서 원문
    meeting_id: int = None,  # HITL Approve 시 Neo4j 저장에 사용할 회의체 ID
) -> dict:
    """[HITL Step 2] interrupt() 지점 재개. approved=True면 검토 결과를 반환하고 Knowledge Base에 저장."""
    config = {"configurable": {"thread_id": thread_id}}
    result = await _review_graph.ainvoke(
        Command(resume={"approved": approved}),
        config,
    )
    if approved:
        review = result.get("proposed_review")

        # HITL Approve 시 Knowledge Base 자동 저장 - 승인된 보고서를 Neo4j KnowledgeReport 노드로 저장
        if review and content:
            try:
                from agents import knowledge_agent as _ka
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
    """회의체 현황 스트리밍 — 기존 hyean_status/hyean_chat 엔드포인트 호환용."""
    import json as _json
    status_text = _json.dumps(meeting_status, ensure_ascii=False, indent=2)
    user_label = f"{user_name}님" if user_name else "담당자"
    role_label = {"admin": "운영자", "presenter": "발제자", "SECRETARY": "운영자"}.get(user_role, user_role)

    context_block = f"[회의체 현황 데이터]\n{status_text}"
    if meeting_context and meeting_context.strip():
        context_block += f"\n\n[회의체 맥락]\n{meeting_context}"

    system_msgs: List[BaseMessage] = [
        SystemMessage(content=(
            "당신은 회의체 운영을 지원하는 AI ReportAgent입니다.\n"
            "공손하고 정중한 비서 말투로 응답합니다. ('~드립니다', '~습니다')\n"
            "데이터에 없는 내용은 절대 언급하지 않습니다.\n"
            "추측성 표현 금지: '~일 것 같습니다', '~인 것 같아요' 사용 불가\n"
            "한국어로 응답합니다."
        )),
        HumanMessage(content=(
            f"[사용자 정보]\n- 이름: {user_label}\n- 역할: {role_label}\n\n"
            f"{context_block}\n\n"
            f"위 데이터만을 기반으로, {user_label}의 질문에 자연스럽게 응대하세요."
        )),
        AIMessage(content=f"안녕하세요, {user_label}. 무엇이든 말씀해 주세요."),
    ]

    history = _to_base_messages((chat_history or [])[-8:])
    input_msgs = history + [HumanMessage(content=message)]
    config = {"configurable": {"thread_id": str(uuid.uuid4())}}

    llm = _make_llm()
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
