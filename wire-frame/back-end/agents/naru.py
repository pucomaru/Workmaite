"""나루 (Naru) - 보고서 검토 Agent (LangGraph)"""
import os, json, re, uuid
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
class NaruState(TypedDict):
    messages: Annotated[List[BaseMessage], add_messages]
    knowledge: List[dict]
    reports_info: List[dict]
    meeting_context: str


# ── Pydantic schemas ──────────────────────────────────────────────────────
class ReviewFeedbackItem(BaseModel):
    point: str = Field(..., description="피드백 항목")


class ReviewResult(BaseModel):
    score: int = Field(..., ge=0, le=100, description="보고서 점수 (0-100)")
    feedback: List[str] = Field(default_factory=list, description="구체적인 피드백 항목들")


# ── Tool ──────────────────────────────────────────────────────────────────
@tool
def review_report_tool(report_content: str, agenda: str = "") -> str:
    """보고서 내용을 검토하고 점수와 피드백을 JSON으로 반환한다."""
    return json.dumps({"score": 0, "feedback": ["검토 중..."]}, ensure_ascii=False)


# ── LLM ───────────────────────────────────────────────────────────────────
def _make_llm(temperature: float = 0.2) -> ChatOpenAI:
    return ChatOpenAI(
        model=MODEL,
        temperature=temperature,
        api_key=os.getenv("OPENAI_API_KEY"),
        streaming=True,
    )


SYSTEM_PROMPT = """당신은 대기업 발제자료 검토 전문 AI 나루(Naru)입니다.
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


def _to_base_messages(messages: List[dict]) -> List[BaseMessage]:
    result = []
    for m in messages:
        role, content = m.get("role", ""), m.get("content", "")
        if role == "user":
            result.append(HumanMessage(content=content))
        elif role in ("assistant", "agent"):
            result.append(AIMessage(content=content))
    return result


def _build_system_with_knowledge(knowledge: List[dict], meeting_context: str = "") -> str:
    system = SYSTEM_PROMPT
    if meeting_context:
        system += f"\n\n[회의체 맥락 — 이 정보를 항상 참고하세요]\n{meeting_context}"
    if knowledge:
        criteria = "\n".join([f"- {k.get('title','')}: {k.get('content','')[:100]}" for k in knowledge])
        system += f"\n\n[보고서 검토 기준]\n{criteria}"
    return system


# ── Graph nodes ────────────────────────────────────────────────────────────
async def _chat_node(state: NaruState) -> dict:
    system = _build_system_with_knowledge(state.get("knowledge", []), state.get("meeting_context", ""))
    reports_info = state.get("reports_info", [])

    system_msgs: List[BaseMessage] = [SystemMessage(content=system)]
    if reports_info:
        reports_text = "\n\n".join([
            f"[{r.get('presenter_name','')} - {r.get('file_name','')}]\n상태: {r.get('status','')}"
            for r in reports_info
        ])
        system_msgs += [
            HumanMessage(content=f"다음 보고서 목록을 검토해주세요:\n{reports_text}"),
        ]

    llm = _make_llm()
    response = await llm.ainvoke(system_msgs + state["messages"])
    return {"messages": [response]}


# ── Graph ─────────────────────────────────────────────────────────────────
def _build_graph():
    builder = StateGraph(NaruState)
    builder.add_node("chat", _chat_node)
    builder.add_edge(START, "chat")
    builder.add_edge("chat", END)
    return builder.compile()

_graph = _build_graph()


# ── Public API ─────────────────────────────────────────────────────────────
async def chat_stream(
    message: str,
    chat_history: List[dict],
    knowledge: List[dict] = None,
    meeting_id: int = 0,
    meeting_context: str = "",
) -> AsyncGenerator[str, None]:
    history = _to_base_messages(chat_history[-10:])
    input_msgs = history + [HumanMessage(content=message)]
    config = {"configurable": {"thread_id": str(uuid.uuid4())}}

    async for event in _graph.astream_events(
        {"messages": input_msgs, "knowledge": knowledge or [], "reports_info": [], "meeting_context": meeting_context},
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

    async for event in _graph.astream_events(
        {"messages": input_msgs, "knowledge": knowledge or [], "reports_info": reports_info, "meeting_context": meeting_context},
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

    llm = ChatOpenAI(model=MODEL, temperature=0.1, api_key=os.getenv("OPENAI_API_KEY"))
    response = await llm.ainvoke([
        SystemMessage(content=system),
        HumanMessage(content=prompt),
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
