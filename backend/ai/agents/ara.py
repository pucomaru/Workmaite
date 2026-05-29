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
    meeting_context: str


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


def _build_context_prompt(previous_minutes: List[str], current_agendas: List[dict], meeting_context: str = "") -> Optional[str]:
    parts = []
    if meeting_context:
        parts.append(f"[회의체 맥락]\n{meeting_context}")
    if previous_minutes:
        parts.append("[이전 회의 요약]\n" + "\n".join(previous_minutes[:2]))
    if current_agendas:
        agenda_text = "\n".join([f"- {a.get('content','')}" for a in current_agendas])
        parts.append(f"[현재 아젠다]\n{agenda_text}")
    return "\n\n".join(parts) if parts else None


# ── Graph nodes ────────────────────────────────────────────────────────────
async def _chat_node(state: AraState) -> dict:
    context = _build_context_prompt(state.get("previous_minutes", []), state.get("current_agendas", []), state.get("meeting_context", ""))
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
    meeting_context: str = "",
) -> AsyncGenerator[str, None]:
    history = _to_base_messages(chat_history[-10:])
    input_msgs = history + [HumanMessage(content=message)]
    config = {"configurable": {"thread_id": str(uuid.uuid4())}}

    async for event in _graph.astream_events(
        {
            "messages": input_msgs,
            "previous_minutes": previous_minutes or [],
            "current_agendas": current_agendas or [],
            "meeting_context": meeting_context,
        },
        config,
        version="v2",
    ):
        if event["event"] == "on_chat_model_stream":
            chunk = event["data"]["chunk"]
            if chunk.content:
                yield chunk.content


async def generate_minutes_stream(
    transcript: str,
    meeting_context: str = "",
    agenda_text: str = "없음",
    now: str = "",
) -> AsyncGenerator[str, None]:
    from datetime import datetime as _dt
    if not now:
        now = _dt.now().strftime("%Y년 %m월 %d일")

    system_prompt = f"""당신은 전문 회의록 작성 AI 아라(Ara)입니다.
제공된 STT 대화 기록을 분석해 실무에서 바로 활용 가능한 고품질 회의록을 작성합니다.

회의 정보:
{meeting_context}

등록된 안건:
{agenda_text}

회의록 작성 원칙:
1. 발언 내용을 그대로 옮기지 말고, 핵심 의미를 추출해 재구성하세요.
2. 발언자별 주요 발언을 정확히 귀속시키세요.
3. 결정 사항은 "~로 결정", "~하기로 합의" 등 명확한 표현을 사용하세요.
4. 액션 아이템은 반드시 담당자, 내용, 기한을 포함하세요.
5. 수치, 날짜, 고유명사는 정확하게 기재하세요.
6. 아래 형식을 반드시 따르세요."""

    user_prompt = f"""다음 STT 대화 기록으로 회의록을 작성해주세요.

---
{transcript}
---

아래 형식으로 작성하세요:

# 회의록

**일시:** {now}
**참석자:** (대화 기록에서 발언자 추출)

---

## 1. 회의 목적 및 배경
(이 회의가 왜 열렸는지, 무엇을 논의하기 위한 자리인지 2-3문장으로)

## 2. 안건별 주요 논의
(각 주제마다 소제목(###)을 붙이고, 누가 말했냐가 아닌 어떤 내용이 논의됐고 어떤 방향으로 흘렀는지 흐름 중심으로 서술. 핵심 수치나 쟁점은 bullet point로 강조)

## 3. 결정 사항
(회의에서 확정된 내용. 각 항목에 결정 배경도 한 줄 포함)
- **[결정 내용]** - 배경: ~

## 4. 액션 아이템
(담당자가 해야 할 일)
| 담당자 | 내용 | 기한 |
|--------|------|------|

## 5. 보류 및 추가 검토 사항
(이번 회의에서 결론 내지 못한 항목)

## 6. 다음 회의 안건
(이번 논의에서 도출된 다음 회의 주제)"""

    llm = _make_llm(temperature=0.2)
    async for chunk in llm.astream([SystemMessage(content=system_prompt), HumanMessage(content=user_prompt)]):
        if chunk.content:
            yield chunk.content
