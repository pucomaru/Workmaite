"""아라 (Ara) - 회의 진행 Agent + 회의록 생성 (LangGraph)"""
import os, uuid
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
class AraState(TypedDict):
    messages: Annotated[List[BaseMessage], add_messages]
    previous_minutes: List[str]
    current_agendas: List[dict]


# ── Pydantic schemas ──────────────────────────────────────────────────────
class MinutesSection(BaseModel):
    title: str = Field(..., description="섹션 제목")
    content: str = Field(..., description="섹션 내용")


class MeetingMinutes(BaseModel):
    summary: str = Field(..., description="회의 요약 (3-5줄)")
    sections: List[MinutesSection] = Field(default_factory=list, description="주요 논의/결정/과제 섹션")


# ── Tool ──────────────────────────────────────────────────────────────────
@tool
def summarize_transcript_tool(transcript: str) -> str:
    """회의 녹취록을 요약한다. transcript는 원문 텍스트."""
    return f"회의록 요약 작업: {len(transcript)}자 녹취록"


# ── LLM ───────────────────────────────────────────────────────────────────
def _make_llm(temperature: float = 0.3) -> ChatOpenAI:
    return ChatOpenAI(
        model=MODEL,
        temperature=temperature,
        api_key=os.getenv("OPENAI_API_KEY"),
        streaming=True,
    )


SYSTEM_PROMPT = """당신은 회의 진행을 돕는 AI 아라(Ara)입니다.
- 지난 회의 내용을 요약 제공합니다
- 현재 아젠다 진행 상황을 안내합니다
- 회의 중 궁금한 사항에 답변합니다
- 간결하고 실용적으로 응답합니다
한국어로 응답합니다."""


def _to_base_messages(messages: List[dict]) -> List[BaseMessage]:
    result = []
    for m in messages:
        role, content = m.get("role", ""), m.get("content", "")
        if role == "user":
            result.append(HumanMessage(content=content))
        elif role in ("assistant", "agent"):
            result.append(AIMessage(content=content))
    return result


def _build_context_prompt(previous_minutes: List[str], current_agendas: List[dict]) -> Optional[str]:
    parts = []
    if previous_minutes:
        parts.append("[이전 회의 요약]\n" + "\n".join(previous_minutes[:2]))
    if current_agendas:
        agenda_text = "\n".join([f"- {a.get('content','')}" for a in current_agendas])
        parts.append(f"[현재 아젠다]\n{agenda_text}")
    return "\n\n".join(parts) if parts else None


# ── Graph nodes ────────────────────────────────────────────────────────────
async def _chat_node(state: AraState) -> dict:
    context = _build_context_prompt(state.get("previous_minutes", []), state.get("current_agendas", []))
    system_msgs: List[BaseMessage] = [SystemMessage(content=SYSTEM_PROMPT)]
    if context:
        system_msgs += [
            HumanMessage(content=context),
            AIMessage(content="회의 정보를 확인했습니다. 도움이 필요하신 게 있나요?"),
        ]
    llm = _make_llm()
    response = await llm.ainvoke(system_msgs + state["messages"])
    return {"messages": [response]}


# ── Graph ─────────────────────────────────────────────────────────────────
def _build_graph():
    builder = StateGraph(AraState)
    builder.add_node("chat", _chat_node)
    builder.add_edge(START, "chat")
    builder.add_edge("chat", END)
    return builder.compile()

_graph = _build_graph()


# ── Public API ─────────────────────────────────────────────────────────────
async def chat_stream(
    message: str,
    chat_history: List[dict],
    previous_minutes: List[str] = None,
    current_agendas: List[dict] = None,
    meeting_id: int = 0,
) -> AsyncGenerator[str, None]:
    history = _to_base_messages(chat_history[-10:])
    input_msgs = history + [HumanMessage(content=message)]
    config = {"configurable": {"thread_id": str(uuid.uuid4())}}

    async for event in _graph.astream_events(
        {
            "messages": input_msgs,
            "previous_minutes": previous_minutes or [],
            "current_agendas": current_agendas or [],
        },
        config,
        version="v2",
    ):
        if event["event"] == "on_chat_model_stream":
            chunk = event["data"]["chunk"]
            if chunk.content:
                yield chunk.content


async def generate_minutes(raw_transcript: str) -> str:
    if not raw_transcript or len(raw_transcript.strip()) < 10:
        return "회의 내용이 기록되지 않았습니다."

    prompt = f"""다음 회의 녹취록을 바탕으로 회의록을 작성해주세요.

형식:
## 회의 요약
(3-5줄 요약)

## 주요 논의 사항
- 항목별 정리

## 결정 사항
- 결정된 내용

## 후속 과제
- 과제 및 담당자

[녹취록]
{raw_transcript[:4000]}"""

    llm = ChatOpenAI(model=MODEL, temperature=0.2, api_key=os.getenv("OPENAI_API_KEY"))
    response = await llm.ainvoke([
        SystemMessage(content="당신은 전문 회의록 작성 AI입니다. 한국어로 작성합니다."),
        HumanMessage(content=prompt),
    ])
    return response.content
