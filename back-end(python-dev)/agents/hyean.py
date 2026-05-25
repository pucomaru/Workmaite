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
    user_name: str
    knowledge: List[dict]
    meeting_context: str


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
    return """당신은 회의체 운영을 전담하는 AI 비서 혜안(Hyean)입니다.
항상 공손하고 정중한 비서 말투를 사용하세요. ("~드립니다", "~습니다", "말씀드리겠습니다" 등)

[응답 원칙]
- 사용자의 질문에 맞게 자연스럽게 응답합니다. 매번 동일한 형식을 강요하지 않습니다.
- 브리핑 요청이면 핵심 현황을 구조적으로, 특정 질문이면 그 질문에 집중해 답합니다.
- 데이터에 없는 내용은 절대 언급하지 않습니다.
- 추측성 표현 금지: "~일 것 같습니다", "~인 것 같아요", "~으로 보입니다" 사용 불가
- 수치와 이름은 반드시 입력 데이터 기반으로만 사용합니다.
- 부정적 내용은 사실 기반으로 중립적 톤 유지합니다.
- "우측 하단" 또는 "혜안 버튼"을 언급하는 문구는 절대 사용하지 않습니다.
- 데이터에 "persons" 필드가 있으면 구성원별 소속 회의체 정보로 활용합니다.
- 데이터에 "meetings" 배열이 있으면 전체 회의체 현황으로 활용합니다.

[브리핑 요청 시 권장 구조 — 상황에 맞게 취사선택]
- 회의체 현황 요약 (핵심 수치 및 상태)
- 주목할 아젠다 또는 과제 (있는 경우)
- 주의 필요 사항 (지연·미완료·에스컬레이션, 있는 경우만)

[사용자 액션 요청 시]
구체적인 내용을 작성해 보여드린 뒤 확인 후 처리해 드립니다.

한국어로, 공손하고 정중한 비서 말투로 응답합니다."""


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
    user_name = state.get("user_name") or "담당자"
    role_label = {"admin": "운영자", "presenter": "발제자"}.get(user_role, user_role)
    extra_ctx = state.get("meeting_context", "")

    context_block = f"[회의체 현황 데이터]\n{status_text}"
    if extra_ctx and extra_ctx.strip():
        context_block += f"\n\n[Neo4j 그래프 컨텍스트]\n{extra_ctx}"

    system_msgs: List[BaseMessage] = [
        SystemMessage(content=_status_system_prompt()),
        HumanMessage(content=(
            f"[사용자 정보]\n"
            f"- 이름: {user_name}님\n"
            f"- 역할: {role_label}\n\n"
            f"{context_block}\n\n"
            f"위 데이터만을 기반으로, {user_name}님의 질문에 자연스럽게 응대하세요."
        )),
        AIMessage(content=f"안녕하세요, {user_name}님. 무엇이든 말씀해 주세요."),
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

    prompt = f"""아래 회의 활동 데이터에서, 이 조직이 앞으로 더 효율적으로 회의를 운영하는 데 직접 도움이 될 패턴이나 기준을 발견하면 암묵지로 제안해줘.

암묵지란 단순한 활동 기록이 아니야. 다음 중 하나에 해당해야 해:
- 반복적으로 나타나는 의사결정 패턴
- 아젠다나 To-do 배정에서 드러난 암묵적 기준
- 자주 놓치거나 지연되는 유형과 그 대응 기준
- 회의 운영 효율을 높이는 구체적 발견

이런 패턴이 보이지 않으면 null을 반환해.

보이면 아래 JSON 형식으로만 응답해:
{{
  "category": "카테고리",
  "title": "암묵지 제목 (한 줄, 핵심만)",
  "proposed_content": "구체적 내용. 왜 이 기준이 필요한지, 어떤 상황에서 적용하는지 명확하게 서술.",
  "diff_summary": "기존 내용과 어떻게 다른지 한 줄 요약",
  "evidence_summary": "데이터에서 이 패턴을 발견한 근거 (구체적 사례 포함)"
}}

카테고리: meeting_standard(회의 운영 기준), agenda_standard(아젠다 선정·처리 기준), todo_standard(과제 배정·완료 기준), report_standard(보고서·자료 기준)

[회의 활동 데이터]
{events_text}

[현재 등록된 암묵지]
{knowledge_text}"""

    llm = ChatOpenAI(model=MODEL, temperature=0.2, api_key=os.getenv("OPENAI_API_KEY"))
    response = await llm.ainvoke([
        SystemMessage(content="너는 조직의 회의 운영 패턴을 관찰하고, 실제로 운영 효율을 높이는 암묵지만 추출하는 AI야. 단순 로그 요약이나 활동 기록은 암묵지가 아니야. 패턴이 불명확하면 null을 반환해."),
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
    user_name: str = "",
    meeting_context: str = "",
) -> AsyncGenerator[str, None]:
    history = _to_base_messages((chat_history or [])[-8:])
    input_msgs = history + [HumanMessage(content=message)]
    config = {"configurable": {"thread_id": str(uuid.uuid4())}}

    async for event in _chat_graph.astream_events(
        {
            "messages": input_msgs,
            "meeting_status": meeting_status,
            "user_role": user_role,
            "user_name": user_name,
            "knowledge": active_knowledge or [],
            "meeting_context": meeting_context,
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
    """회의 활동 분석 → 암묵지 업데이트 제안 (즉시 반환, HITL 없음)."""
    if len(recent_events) < 2:
        return None

    events_text = json.dumps(recent_events[-15:], ensure_ascii=False, indent=2)
    knowledge_text = json.dumps(current_knowledge[:5], ensure_ascii=False, indent=2)

    prompt = f"""아래 회의 활동 데이터에서, 이 조직이 앞으로 더 효율적으로 회의를 운영하는 데 직접 도움이 될 패턴이나 기준을 발견하면 암묵지로 제안해줘.

암묵지란 단순한 활동 기록이 아니야. 다음 중 하나에 해당해야 해:
- 반복적으로 나타나는 의사결정 패턴 (예: 특정 부서는 항상 X를 먼저 처리해야 다음 단계가 가능하다)
- 아젠다나 To-do 배정에서 드러난 암묵적 기준 (예: 예산 관련 안건은 반드시 재무팀이 먼저 검토한다)
- 자주 놓치거나 지연되는 유형 (예: 외부 협력사 관련 To-do는 마감 2주 전 착수해야 한다)
- 회의 운영에서 효율을 높이는 발견 (예: 이 회의체는 현황 보고를 먼저 끝내야 의사결정 토론이 원활하다)

이런 패턴이 데이터에서 보이지 않으면 null을 반환해.

보이면 아래 JSON 형식으로만 응답해:
{{
  "category": "카테고리",
  "title": "암묵지 제목 (한 줄, 핵심만)",
  "proposed_content": "구체적 내용. 왜 이 기준이 필요한지, 어떤 상황에서 적용하는지 명확하게 서술.",
  "diff_summary": "기존 내용과 어떻게 다른지 한 줄 요약",
  "evidence_summary": "데이터에서 이 패턴을 발견한 근거 (구체적 사례 포함)"
}}

카테고리: meeting_standard(회의 운영 기준), agenda_standard(아젠다 선정·처리 기준), todo_standard(과제 배정·완료 기준), report_standard(보고서·자료 기준)

[회의 활동 데이터]
{events_text}

[현재 등록된 암묵지]
{knowledge_text}"""

    llm = ChatOpenAI(model=MODEL, temperature=0.2, api_key=os.getenv("OPENAI_API_KEY"))
    response = await llm.ainvoke([
        SystemMessage(content="너는 조직의 회의 운영 패턴을 관찰하고, 실제로 운영 효율을 높이는 암묵지만 추출하는 AI야. 단순 로그 요약이나 활동 기록은 암묵지가 아니야. 패턴이 불명확하면 null을 반환해."),
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
