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


SYSTEM_PROMPT = """당신은 보고서 검토 전문 AI 나루(Naru)입니다.
전체 보고서를 총괄 분석하여:
1. 공통 품질 이슈를 파악합니다
2. 누락된 내용을 지적합니다
3. 개선 방향을 제시합니다
4. 각 발제자별 피드백을 제공합니다
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


def _build_system_with_knowledge(knowledge: List[dict]) -> str:
    system = SYSTEM_PROMPT
    if knowledge:
        criteria = "\n".join([f"- {k.get('title','')}: {k.get('content','')[:100]}" for k in knowledge])
        system += f"\n\n[보고서 검토 기준]\n{criteria}"
    return system


# ── Graph nodes ────────────────────────────────────────────────────────────
async def _chat_node(state: NaruState) -> dict:
    system = _build_system_with_knowledge(state.get("knowledge", []))
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
) -> AsyncGenerator[str, None]:
    history = _to_base_messages(chat_history[-10:])
    input_msgs = history + [HumanMessage(content=message)]
    config = {"configurable": {"thread_id": str(uuid.uuid4())}}

    async for event in _graph.astream_events(
        {"messages": input_msgs, "knowledge": knowledge or [], "reports_info": []},
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
        {"messages": input_msgs, "knowledge": knowledge or [], "reports_info": reports_info},
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
    prompt = f"""다음 보고서를 검토하고 반드시 JSON 형식으로 응답하세요.
형식: {{"score": 75, "feedback": ["피드백1", "피드백2", "피드백3"]}}

[아젠다]
{agenda}

[보고서 내용]
{report_content[:3000]}"""

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
    return {"score": 70, "feedback": ["보고서를 검토했습니다. 구체적인 피드백을 위해 내용을 더 자세히 작성해 주세요."]}
