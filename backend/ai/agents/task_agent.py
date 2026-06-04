# 과제 추출 Agent - 회의록/문서를 입력받아 과제·담당자·기한 추출
# HITL (Human-In-The-Loop): 추출 결과에 대한 사용자 Approve/Reject 포함
# 수동 트리거 방식 유지 (POST /archive/extract-agendas)
import os, json, re, uuid
from typing import AsyncGenerator, List, Optional, Annotated
from typing_extensions import TypedDict

from langchain_openai import ChatOpenAI
from langchain_core.messages import BaseMessage, SystemMessage, HumanMessage, AIMessage
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.types import interrupt, Command
from pydantic import BaseModel, Field

MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")


# ── State ─────────────────────────────────────────────────────────────────
class TaskState(TypedDict):
    messages: Annotated[List[BaseMessage], add_messages]
    departments: List[str]
    knowledge: List[dict]
    meeting_context: str


class ExtractionState(TypedDict):
    messages: Annotated[List[BaseMessage], add_messages]
    content: str
    departments: List[str]
    knowledge: List[dict]
    proposed: Optional[dict]


# ── Pydantic schemas ──────────────────────────────────────────────────────
class AgendaItem(BaseModel):
    department: Optional[str] = Field(None, description="담당 부서 (없으면 null)")
    content: str = Field(..., description="아젠다 내용")


class TodoItem(BaseModel):
    content: str = Field(..., description="할 일 내용")
    department: Optional[str] = Field(None, description="담당 부서")
    due_date: Optional[str] = Field(None, description="마감일 YYYY-MM-DD")


class ExtractionResult(BaseModel):
    agendas: List[AgendaItem] = Field(default_factory=list)
    todos: List[TodoItem] = Field(default_factory=list)


# ── Helpers ────────────────────────────────────────────────────────────────
def _parse_json_from_text(text: str):
    """LLM 응답에서 JSON 추출. 마크다운 코드블록, 일반 JSON 모두 처리."""
    match = re.search(r'```(?:json)?\s*(\{[\s\S]*?\}|\[[\s\S]*?\])\s*```', text)
    if match:
        try:
            return json.loads(match.group(1))
        except Exception:
            pass
    match = re.search(r'\{[\s\S]*\}', text)
    if match:
        try:
            return json.loads(match.group())
        except Exception:
            pass
    match = re.search(r'\[[\s\S]*\]', text)
    if match:
        try:
            return json.loads(match.group())
        except Exception:
            pass
    return None


def _build_system_prompt(
    knowledge: List[dict] = None,
    departments: List[str] = None,
    meeting_context: str = "",
) -> str:
    base = """너는 TaskAgent야. 회의록과 문서에서 과제·담당자·기한을 추출하는 AI야.

말할 때는 회사 동료처럼 자연스럽고 편하게 말해. "~요" 체로 말하고, 헤딩이나 번호 목록 같은 형식 쓰지 마. 그냥 대화하듯 써. 사용자가 짧게 물으면 짧게 답하고, 공감 표현("아 그렇군요", "맞아요" 등)도 자연스럽게 섞어.

보고자료나 회의록에서 아젠다랑 To-do 뽑는 게 주 역할이야. 그 외에 현황 요약, 리스크 점검, 준비사항 확인 같은 것도 도와줘.

자료 분석해서 아젠다/To-do를 추출할 때는 먼저 말로 설명하고, 설명 끝나면 빈 줄 하나 뒤에 JSON 코드블록만 붙여. 그게 전부야. 추가 제목, 레이블, 번호 절대 붙이지 마.

```json
{"agendas":[{"department":"담당부서 또는 null","content":"아젠다 항목"}],"todos":[{"content":"실행 과제","department":"담당부서 또는 null","due_date":"YYYY-MM-DD 또는 null"}]}
```

부서 정보 불명확하면 null. 추출이 필요 없는 질문엔 JSON 붙이지 마."""

    if meeting_context:
        base += f"\n\n## 이번 회의 맥락\n{meeting_context}"
    if departments:
        base += "\n\n## 참여 부서 목록 (To-do 배정 시 이 목록에서 선택)\n" + "\n".join(f"- {d}" for d in departments if d)
    if knowledge:
        criteria = "\n".join([f"- [{k.get('category','')}] {k.get('title','')}" for k in knowledge])
        base += f"\n\n## 조직 아젠다 선정 기준\n{criteria}"
    return base


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
async def _chat_node(state: TaskState) -> dict:
    system = _build_system_prompt(
        state.get("knowledge"), state.get("departments"), state.get("meeting_context", "")
    )
    llm = ChatOpenAI(model=MODEL, temperature=0.1, api_key=os.getenv("OPENAI_API_KEY"), streaming=True)
    response = await llm.ainvoke([SystemMessage(content=system)] + state["messages"])
    return {"messages": [response]}


def _build_chat_graph():
    builder = StateGraph(TaskState)
    builder.add_node("chat", _chat_node)
    builder.add_edge(START, "chat")
    builder.add_edge("chat", END)
    return builder.compile()

_chat_graph = _build_chat_graph()


# ── HITL 추출 그래프 ─────────────────────────────────────────────────────
async def _extract_propose_node(state: ExtractionState) -> dict:
    """문서 분석 → 아젠다/Todo 제안 → interrupt()로 사용자 확인 대기."""
    dept_hint = ""
    if state.get("departments"):
        dept_hint = f"\n담당 부서는 반드시 다음 목록에서 선택하세요: {', '.join(state['departments'])}"

    llm = ChatOpenAI(model=MODEL, temperature=0.0, api_key=os.getenv("OPENAI_API_KEY"))
    response = await llm.ainvoke([
        SystemMessage(content=_build_system_prompt(state.get("knowledge"), state.get("departments"))),
        HumanMessage(content=(
            f"다음 문서에서 아젠다와 Todo를 추출해 JSON 형식으로만 응답하세요.{dept_hint}\n\n"
            f"[문서]\n{state['content'][:8000]}"
        )),
    ])
    proposed = _parse_json_from_text(response.content)
    if isinstance(proposed, list):
        proposed = {"agendas": proposed, "todos": []}
    if not isinstance(proposed, dict):
        proposed = {"agendas": [], "todos": []}

    # HITL: 사용자 확인 대기
    feedback = interrupt(proposed)

    if feedback.get("approved"):
        return {"proposed": proposed}
    return {"proposed": None}


def _build_extraction_graph():
    builder = StateGraph(ExtractionState)
    builder.add_node("propose", _extract_propose_node)
    builder.add_edge(START, "propose")
    builder.add_edge("propose", END)
    return builder.compile()

_extraction_graph = _build_extraction_graph()


# ── Public API ─────────────────────────────────────────────────────────────
async def chat_stream(
    message: str,
    chat_history: List[dict],
    file_content: str = "",
    previous_minutes: List[str] = None,
    knowledge: List[dict] = None,
    departments: List[str] = None,
    meeting_id: int = 0,
    meeting_context: str = "",
) -> AsyncGenerator[str, None]:
    parts = []
    if file_content:
        parts.append(f"[업로드된 문서 내용]\n{file_content[:6000]}")
    if previous_minutes:
        parts.append("[이전 회의록]\n" + "\n\n".join(previous_minutes[:3])[:3000])
    parts.append(message)
    full_message = "\n\n".join(parts)

    history = _to_base_messages(chat_history[-10:])
    input_msgs = history + [HumanMessage(content=full_message)]
    config = {"configurable": {"thread_id": str(uuid.uuid4())}}

    async for event in _chat_graph.astream_events(
        {
            "messages": input_msgs,
            "departments": departments or [],
            "knowledge": knowledge or [],
            "meeting_context": meeting_context,
        },
        config,
        version="v2",
    ):
        if event["event"] == "on_chat_model_stream":
            chunk = event["data"]["chunk"]
            if chunk.content:
                yield chunk.content


async def extract_agendas_and_todos(
    content: str,
    previous_minutes: List[str] = None,
    knowledge: List[dict] = None,
    departments: List[str] = None,
) -> dict:
    """문서에서 아젠다/Todo 직접 추출 (HITL 없음). 확인 후 저장용."""
    dept_hint = ""
    if departments:
        dept_hint = f"\n담당 부서는 반드시 다음 목록에서 선택하세요: {', '.join(d for d in departments if d)}"

    prev_hint = ""
    if previous_minutes:
        prev_hint = "\n\n[이전 회의록 참고]\n" + "\n\n".join(previous_minutes[:2])[:2000]

    prompt = f"""아래 문서에서 회의 아젠다와 부서별 To-do를 뽑아줘.{dept_hint}

말로 간단히 설명한 다음, 바로 JSON 코드블록 붙여줘. 제목이나 레이블은 붙이지 마.
{prev_hint}

{content[:8000]}"""

    llm = ChatOpenAI(model=MODEL, temperature=0.0, api_key=os.getenv("OPENAI_API_KEY"))
    response = await llm.ainvoke([
        SystemMessage(content=_build_system_prompt(knowledge, departments)),
        HumanMessage(content=prompt),
    ])
    parsed = _parse_json_from_text(response.content)
    reason = re.sub(r'```(?:json)?\s*[\s\S]*?```', '', response.content).strip()
    reason = re.sub(r'\{[^{}]*"agendas"[^{}]*\}', '', reason).strip()
    if isinstance(parsed, list):
        return {"agendas": parsed, "todos": [], "reason": reason}
    if isinstance(parsed, dict):
        return {"agendas": parsed.get("agendas", []), "todos": parsed.get("todos", []), "reason": reason}
    return {"agendas": [], "todos": [], "reason": reason}


async def start_extraction_review(
    thread_id: str,
    content: str,
    departments: List[str] = None,
    knowledge: List[dict] = None,
) -> dict:
    """[HITL Step 1] 아젠다 추출 제안 → interrupt()로 일시 정지. 제안 결과 반환."""
    config = {"configurable": {"thread_id": thread_id}}
    await _extraction_graph.ainvoke(
        {
            "messages": [],
            "content": content,
            "departments": departments or [],
            "knowledge": knowledge or [],
            "proposed": None,
        },
        config,
    )
    state = _extraction_graph.get_state(config)
    if state.tasks and state.tasks[0].interrupts:
        proposed = state.tasks[0].interrupts[0].value
        return {"status": "pending", "proposed": proposed}
    return {"status": "error", "proposed": None}


async def confirm_extraction_review(
    thread_id: str,
    approved: bool,
    meeting_id: int = None,  # HITL Approve 시 Neo4j 저장에 사용할 회의체 ID
) -> dict:
    """[HITL Step 2] interrupt() 지점 재개. approved=True면 추출 결과를 반환하고 Knowledge Base에 저장."""
    config = {"configurable": {"thread_id": thread_id}}
    result = await _extraction_graph.ainvoke(
        Command(resume={"approved": approved}),
        config,
    )
    if approved:
        extraction = result.get("proposed")

        # HITL Approve 시 Knowledge Base 자동 저장 - 승인된 각 Todo를 Neo4j KnowledgeTask 노드로 저장
        if extraction:
            try:
                from agents import knowledge_agent as _ka
                for todo in extraction.get("todos", []):
                    if todo.get("content"):
                        await _ka.store_task(
                            content=todo["content"],
                            department=todo.get("department"),
                            due_date=todo.get("due_date"),
                            meeting_id=meeting_id,
                        )
            except Exception:
                pass

        return {"status": "confirmed", "extraction": extraction}
    return {"status": "rejected"}
