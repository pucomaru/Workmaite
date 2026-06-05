# 회의록 작성 Agent - STT 변환 결과를 입력받아 회의록 생성
# Knowledge Base (Neo4j 벡터 검색)에서 유사 회의록을 조회해 프롬프트에 주입
import os, uuid, re as _re, json as _json
from typing import AsyncGenerator, List, Optional, Annotated
from typing_extensions import TypedDict

from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_core.messages import BaseMessage, SystemMessage, HumanMessage, AIMessage
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from pydantic import BaseModel, Field

MODEL = os.environ["OPENAI_MODEL"]


# ── State ─────────────────────────────────────────────────────────────────
class MinutesState(TypedDict):
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


# ── LLM ───────────────────────────────────────────────────────────────────
def _make_llm(temperature: float = 0.3) -> ChatOpenAI:
    return ChatOpenAI(
        model=MODEL,
        temperature=temperature,
        api_key=os.environ["OPENAI_API_KEY"],
        streaming=True,
    )


SYSTEM_PROMPT = """당신은 회의록 작성 전문 AI MinutesAgent입니다.
- STT 변환 텍스트를 분석해 구조적 회의록을 생성합니다
- 이전 유사 회의록을 참고해 일관성 있는 형식을 유지합니다
- 결정 사항, 액션 아이템, 참석자 정보를 명확히 기록합니다
한국어로 응답합니다."""


# ── Neo4j 벡터 검색 (유사 회의록) ────────────────────────────────────────
async def _search_similar_minutes(text: str, k: int = 3) -> List[str]:
    """Neo4j 내장 벡터 검색으로 유사 회의록을 조회합니다 (Cypher 기반)."""
    try:
        from neo4j_client import run_cypher
        embeddings = OpenAIEmbeddings(api_key=os.environ["OPENAI_API_KEY"])
        query_vec = await embeddings.aembed_query(text[:500])

        rows = await run_cypher(
            """CALL db.index.vector.queryNodes('minutes_embedding_index', $k, $embedding)
               YIELD node, score
               RETURN node.content AS content, node.title AS title, score
               ORDER BY score DESC""",
            {"k": k, "embedding": query_vec},
        )
        return [
            f"[{r.get('title', '유사 회의록')}]\n{r.get('content', '')}"
            for r in rows if r.get("content")
        ]
    except Exception:
        return []


# ── Helpers ────────────────────────────────────────────────────────────────
def _to_base_messages(messages: List[dict]) -> List[BaseMessage]:
    result = []
    for m in messages:
        role, content = m.get("role", ""), m.get("content", "")
        if role == "user":
            result.append(HumanMessage(content=content))
        elif role in ("assistant", "agent"):
            result.append(AIMessage(content=content))
    return result


def _build_context_prompt(
    previous_minutes: List[str],
    current_agendas: List[dict],
    meeting_context: str = "",
) -> Optional[str]:
    parts = []
    if meeting_context:
        parts.append(f"[회의체 맥락]\n{meeting_context}")
    if previous_minutes:
        parts.append("[이전/유사 회의 요약]\n" + "\n".join(previous_minutes[:2]))
    if current_agendas:
        agenda_text = "\n".join([f"- {a.get('content','')}" for a in current_agendas])
        parts.append(f"[현재 아젠다]\n{agenda_text}")
    return "\n\n".join(parts) if parts else None


# ── Graph nodes ────────────────────────────────────────────────────────────
async def _chat_node(state: MinutesState) -> dict:
    context = _build_context_prompt(
        state.get("previous_minutes", []),
        state.get("current_agendas", []),
        state.get("meeting_context", ""),
    )
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
    builder = StateGraph(MinutesState)
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


async def generate_minutes(
    raw_transcript: str,
    session_info: dict = None,
    meeting_info: dict = None,
    participants: list = None,
    agendas: list = None,
    todos: list = None,
    meeting_id: int = None,   # Neo4j Knowledge Base 저장용 회의체 ID
    session_id: int = None,   # Neo4j Knowledge Base 저장용 세션 ID
) -> tuple:
    """
    회의록 5대 필수요소를 포함한 구조적 회의록 생성.
    Neo4j 벡터 검색으로 유사 회의록을 조회해 프롬프트에 주입합니다.
    Returns: (markdown_summary: str, structured: dict)
    structured keys: attendees, decisions, action_items, tbd_items, next_meeting_note
    """
    if not raw_transcript or len(raw_transcript.strip()) < 5:
        empty = {
            "attendees": [], "decisions": [], "action_items": [],
            "tbd_items": [], "next_meeting_note": "",
        }
        return "회의 내용이 기록되지 않았습니다.", empty

    similar_minutes = await _search_similar_minutes(raw_transcript)

    tpo_lines = []
    if session_info:
        if session_info.get("title"):
            tpo_lines.append(f"회의 제목: {session_info['title']}")
        if session_info.get("started_at"):
            tpo_lines.append(f"시작: {session_info['started_at']}")
        if session_info.get("ended_at"):
            tpo_lines.append(f"종료: {session_info['ended_at']}")
        if session_info.get("location"):
            tpo_lines.append(f"장소: {session_info['location']}")
    if meeting_info:
        if meeting_info.get("purpose"):
            tpo_lines.append(f"회의 목적: {meeting_info['purpose']}")

    participant_lines = []
    if participants:
        for p in participants:
            role_label = "관리자" if p.get("role") == "admin" else "발제자"
            participant_lines.append(f"- {p.get('name','?')} ({p.get('dept','')}, {role_label})")

    agenda_lines = []
    if agendas:
        for i, a in enumerate(agendas, 1):
            status_label = {"confirmed": "확정", "draft": "검토중", "tbd": "미결"}.get(
                a.get("status", ""), a.get("status", "")
            )
            agenda_lines.append(
                f"{i}. [{status_label}] {a.get('content','')} (담당: {a.get('department') or '미정'})"
            )

    todo_lines = []
    if todos:
        for t in todos:
            due = t.get("due_date", "").split("T")[0] if t.get("due_date") else "기한 미정"
            todo_lines.append(f"- {t.get('content','')} / 담당: {t.get('assignee','미정')} / 기한: {due}")

    context_block = ""
    if tpo_lines:
        context_block += "[회의 기본 정보]\n" + "\n".join(tpo_lines) + "\n\n"
    if participant_lines:
        context_block += "[참석자]\n" + "\n".join(participant_lines) + "\n\n"
    if agenda_lines:
        context_block += "[안건 목록]\n" + "\n".join(agenda_lines) + "\n\n"
    if todo_lines:
        context_block += "[등록된 Todo]\n" + "\n".join(todo_lines) + "\n\n"
    if similar_minutes:
        context_block += "[유사 회의록 참고]\n" + "\n\n".join(similar_minutes[:2]) + "\n\n"

    prompt = f"""{context_block}[회의 녹취/기록]
{raw_transcript[:5000]}

위 회의 내용을 바탕으로 두 파트로 응답하세요.

## [1]
# 회의록
## 1. 회의 목적 및 배경
## 2. 주요 논의 사항
## 3. 결정 사항
## 4. 액션 아이템
| 담당자 | 내용 | 기한 |
|--------|------|------|
## 5. 보류 및 추가 검토 사항
## 6. 다음 회의 안건

## [2]
```json
{{
  "attendees": ["참석자 목록"],
  "decisions": ["결정 사항 목록"],
  "action_items": [{{"assignee": "담당자", "content": "내용", "due_date": "기한"}}],
  "tbd_items": ["보류 사항 목록"],
  "next_meeting_note": "다음 회의 안건"
}}
```"""

    llm = _make_llm(temperature=0.2)
    response = await llm.ainvoke([SystemMessage(content=SYSTEM_PROMPT), HumanMessage(content=prompt)])
    full_text = response.content

    md_part = full_text
    json_part = {}
    split_marker = "## [2]"
    if split_marker in full_text:
        parts = full_text.split(split_marker, 1)
        md_part = parts[0].replace("## [1]", "").strip()
        raw_json_text = parts[1]
        m = _re.search(r'```(?:json)?\s*(\{[\s\S]*?\})\s*```', raw_json_text)
        if m:
            try:
                json_part = _json.loads(m.group(1))
            except Exception:
                pass

    # HITL Approve 시 Knowledge Base 자동 저장 - 회의록 생성 완료 후 Neo4j에 Minutes 노드 저장
    if meeting_id and md_part:
        try:
            from agents import knowledge_agent as _ka
            _title = session_info.get("title", "회의록") if session_info else "회의록"
            await _ka.store_minutes(
                title=_title,
                content=md_part,
                meeting_id=meeting_id,
                session_id=session_id,
            )
        except Exception:
            pass

    return md_part, json_part


async def generate_minutes_stream(
    transcript: str,
    meeting_context: str = "",
    agenda_text: str = "없음",
    now: str = "",
    meeting_id: int = None,   # Neo4j Knowledge Base 저장용 회의체 ID
    session_id: int = None,   # Neo4j Knowledge Base 저장용 세션 ID
    title: str = "",          # Neo4j 저장 시 사용할 회의록 타이틀
) -> AsyncGenerator[str, None]:
    from datetime import datetime as _dt
    if not now:
        now = _dt.now().strftime("%Y년 %m월 %d일")

    system_prompt = f"""당신은 전문 회의록 작성 AI 워크메이트입니다.
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
    collected_parts: List[str] = []  # 스트리밍 완료 후 Knowledge Base 저장을 위한 전체 텍스트 수집
    async for chunk in llm.astream([SystemMessage(content=system_prompt), HumanMessage(content=user_prompt)]):
        if chunk.content:
            collected_parts.append(chunk.content)
            yield chunk.content

    # HITL Approve 시 Knowledge Base 자동 저장 - 스트리밍 완료 후 Neo4j에 Minutes 노드 저장
    if meeting_id and collected_parts:
        try:
            from agents import knowledge_agent as _ka
            await _ka.store_minutes(
                title=title or f"회의록 ({now})",
                content="".join(collected_parts),
                meeting_id=meeting_id,
                session_id=session_id,
            )
        except Exception:
            pass
