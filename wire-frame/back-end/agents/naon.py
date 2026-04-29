"""나온 (Naon) - 카드뉴스 기획·생성 Agent (LangGraph Human-in-the-Loop)

흐름:
  1. chat_stream()       — 나온과 자유 대화 (LangChain streaming, 기획 요구사항 파악)
  2. start_proposal()    — LangGraph propose_node 실행 → interrupt() 로 그래프 일시 정지
                          → 기획안(plan) 반환, thread_id 로 상태 보존
  3. resume_proposal()   — Command(resume=...) 로 그래프 재개
                          · approved=True  → generate_node → 카드뉴스 완성
                          · approved=False → 대화 계속 (그래프 종료, 새 propose 대기)
"""

import os, json, re, uuid
from typing import TypedDict, Optional, List, AsyncGenerator

from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import interrupt, Command

MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

SLIDE_COLORS = {
    "cover":    "#1e3a5f",
    "context":  "#1a4731",
    "content":  "#2d3748",
    "decision": "#3b1f6e",
    "action":   "#7c2d12",
    "closing":  "#1e3a5f",
}
SLIDE_EMOJIS = {
    "cover": "📋", "context": "🔍", "content": "💡",
    "decision": "✅", "action": "🚀", "closing": "🙏",
}


def _make_llm(temperature: float = 0.4) -> ChatOpenAI:
    return ChatOpenAI(
        model=MODEL,
        temperature=temperature,
        api_key=os.getenv("OPENAI_API_KEY"),
    )


def _to_lc(messages: List[dict]):
    result = []
    for m in messages:
        if m["role"] == "system":
            result.append(SystemMessage(content=m["content"]))
        elif m["role"] == "user":
            result.append(HumanMessage(content=m["content"]))
        else:
            result.append(AIMessage(content=m["content"]))
    return result


# ─────────────────────────────────────────────────────────────────
# 1. 일반 채팅 (LangChain 스트리밍, 그래프 없음)
# ─────────────────────────────────────────────────────────────────

CHAT_SYSTEM = """당신은 카드뉴스 기획 전문가 나온(Naon)입니다.

카드뉴스란: 모바일 환경에 최적화된 10장 내외의 슬라이드로, 핵심 정보를 간결한 글과
시각적 구성으로 전달하는 콘텐츠입니다. SNS·포털·사내 공유에 주로 활용됩니다.

역할: 사용자가 원하는 카드뉴스 방향을 파악합니다. 반드시 아래 4가지를 확인하세요.
  ① 목적   — 어디에 쓸 것인가? (임원 보고 / 팀 공유 / 사내 SNS / 외부 공개)
  ② 독자   — 누가 볼 것인가? (경영진 / 실무자 / 전 직원 / 외부)
  ③ 강조점 — 무엇을 부각할 것인가? (결정사항 / 성과 / 문제 / 과제)
  ④ 톤앤매너 — 어떤 느낌? (전문적·공식적 / 친근하고 쉽게 / 간결하고 임팩트 있게)

중요: 이미지 생성은 비용이 드는 작업입니다. 충분히 논의한 뒤 [기획안 요청]을 안내하세요.
4가지 정보가 파악되면 "이제 기획안 요청 버튼을 눌러주세요."라고 안내하세요.
한국어로 응답합니다."""


async def chat_stream(
    message: str,
    chat_history: List[dict],
) -> AsyncGenerator[str, None]:
    """나온과의 자유 대화 — LangChain 스트리밍."""
    messages = [{"role": "system", "content": CHAT_SYSTEM}]
    for h in chat_history[-12:]:
        messages.append(h)
    messages.append({"role": "user", "content": message})

    llm = _make_llm(temperature=0.5)
    async for chunk in llm.astream(_to_lc(messages)):
        if chunk.content:
            yield chunk.content


# ─────────────────────────────────────────────────────────────────
# 2. LangGraph HITL 그래프
# ─────────────────────────────────────────────────────────────────

class ProposalState(TypedDict):
    chat_history: List[dict]   # 나온과의 대화 기록 (요구사항 파악용)
    minutes_list: List[str]    # 선택한 회의 차수의 회의록 텍스트
    meeting_title: str
    plan: Optional[dict]       # propose_node 가 생성한 기획안
    card_news: Optional[dict]  # generate_node 가 완성한 카드뉴스


async def _propose_node(state: ProposalState) -> dict:
    """
    [Node 1] 대화 내용 + 회의록 → 기획안 생성 → interrupt() 로 일시 정지.
    interrupt() 는 LangGraph 가 상태를 체크포인터에 저장하고 그래프를 멈춘다.
    resume_proposal() 이 Command(resume=...) 를 보내면 feedback 값을 받아 재개한다.
    """
    plan = await _build_plan(
        chat_history=state["chat_history"],
        minutes_list=state["minutes_list"],
        meeting_title=state["meeting_title"],
    )

    # ── Human-in-the-loop 지점 ──────────────────────────────────
    # interrupt(plan) 호출 → LangGraph 가 그래프를 여기서 멈춤
    # 프론트엔드는 이 plan 을 보여주고 [승인] / [수정 요청] 을 기다린다
    feedback = interrupt(plan)
    # ── 재개 후 ─────────────────────────────────────────────────

    if feedback.get("approved"):
        return {"plan": plan}
    else:
        # 거부: plan 을 None 으로 두고 종료 (프론트는 대화를 이어서 진행)
        return {"plan": None}


async def _generate_node(state: ProposalState) -> dict:
    """[Node 2] 승인된 기획안 → 회의록 내용으로 슬라이드 보강 → 완성."""
    card_news = await _enrich_plan(state["plan"], state["minutes_list"])
    return {"card_news": card_news}


def _route_after_propose(state: ProposalState) -> str:
    """propose_node 완료 후 라우팅: 승인됐으면 generate, 거부됐으면 종료."""
    return "generate" if state.get("plan") else END


# 그래프 빌드
_checkpointer = MemorySaver()   # 실제 운영에서는 SqliteSaver / PostgresSaver 권장

def _build_graph() -> StateGraph:
    builder = StateGraph(ProposalState)
    builder.add_node("propose", _propose_node)
    builder.add_node("generate", _generate_node)
    builder.set_entry_point("propose")
    builder.add_conditional_edges("propose", _route_after_propose, {
        "generate": "generate",
        END: END,
    })
    builder.add_edge("generate", END)
    return builder.compile(checkpointer=_checkpointer)

_graph = _build_graph()


# ─────────────────────────────────────────────────────────────────
# 3. Public API (routers/agents.py 에서 호출)
# ─────────────────────────────────────────────────────────────────

async def start_proposal(
    thread_id: str,
    chat_history: List[dict],
    minutes_list: List[str],
    meeting_title: str,
) -> dict:
    """
    propose_node 를 실행한다. interrupt() 지점에서 그래프가 멈추고
    기획안(plan) 을 반환한다. thread_id 로 상태가 checkpointer 에 보존된다.
    """
    config = {"configurable": {"thread_id": thread_id}}
    await _graph.ainvoke(
        {
            "chat_history": chat_history,
            "minutes_list": minutes_list,
            "meeting_title": meeting_title,
            "plan": None,
            "card_news": None,
        },
        config,
    )

    # interrupt() 로 멈춘 상태 확인
    state = _graph.get_state(config)
    if state.tasks and state.tasks[0].interrupts:
        plan = state.tasks[0].interrupts[0].value
        # 슬라이드 색상·이모지 보강
        for slide in plan.get("slides", []):
            t = slide.get("type", "content")
            slide.setdefault("bg_color", SLIDE_COLORS.get(t, "#2d3748"))
            slide.setdefault("emoji", SLIDE_EMOJIS.get(t, "💡"))
        return {"status": "plan_ready", "plan": plan}

    return {"status": "error", "plan": None, "detail": "기획안 생성 실패"}


async def resume_proposal(
    thread_id: str,
    approved: bool,
    feedback: Optional[str] = None,
) -> dict:
    """
    interrupt() 지점에서 멈춰 있는 그래프를 Command(resume=...) 로 재개한다.
    - approved=True  → generate_node 실행 → 카드뉴스 완성
    - approved=False → plan=None 으로 그래프 종료
    """
    config = {"configurable": {"thread_id": thread_id}}
    result = await _graph.ainvoke(
        Command(resume={"approved": approved, "feedback": feedback or ""}),
        config,
    )

    if approved:
        card_news = result.get("card_news")
        if card_news:
            # 슬라이드 보강
            for slide in card_news.get("slides", []):
                t = slide.get("type", "content")
                slide.setdefault("bg_color", SLIDE_COLORS.get(t, "#2d3748"))
                slide.setdefault("emoji", SLIDE_EMOJIS.get(t, "💡"))
        return {"status": "done", "card_news": card_news}
    else:
        return {"status": "rejected", "message": "기획안이 거부되었습니다. 대화를 이어서 요구사항을 수정해 주세요."}


# ─────────────────────────────────────────────────────────────────
# 내부 헬퍼
# ─────────────────────────────────────────────────────────────────

async def _build_plan(
    chat_history: List[dict],
    minutes_list: List[str],
    meeting_title: str,
) -> dict:
    """대화 기록 + 회의록 → 슬라이드 기획안(JSON) 생성."""
    minutes_text = "\n\n---\n\n".join([m[:1500] for m in minutes_list[:3]])
    conversation = "\n".join(
        f"[{'사용자' if h['role'] == 'user' else '나온'}] {h['content']}"
        for h in chat_history[-16:]
    )

    prompt = f"""대화 내용과 회의록을 바탕으로 카드뉴스 기획안을 작성하세요.
반드시 아래 JSON 형식만 반환하세요 (코드블록 없이 순수 JSON):

{{
  "title": "카드뉴스 제목 (20자 이내)",
  "purpose": "목적 한 문장",
  "target": "대상 독자",
  "tone": "톤앤매너",
  "slides": [
    {{
      "slide_no": 1,
      "type": "cover",
      "headline": "메인 헤드라인 (15자 이내)",
      "body": "부제목 또는 핵심 한 줄 메시지",
      "visual_hint": "배경/이미지 추천 요소"
    }}
  ]
}}

슬라이드 구성: 총 8-10장
타입 순서: cover(1) → context(1) → content(4-5) → decision(1) → action(1) → closing(1)
headline: 15자 이내, 임팩트 있게 / body: 3-4줄, 간결하게

[사용자 대화]
{conversation}

[회의 제목] {meeting_title}
[회의록]
{minutes_text[:3000]}"""

    llm = _make_llm(temperature=0.3)
    response = await llm.ainvoke(_to_lc([
        {"role": "system", "content": "카드뉴스 기획 전문가. 요청된 JSON 형식만 반환."},
        {"role": "user", "content": prompt},
    ]))
    return _parse_json(response.content, meeting_title)


async def _enrich_plan(plan: dict, minutes_list: List[str]) -> dict:
    """승인된 기획안 슬라이드에 회의록 내용을 채워 최종 카드뉴스 완성."""
    minutes_text = "\n\n---\n\n".join([m[:1500] for m in minutes_list[:3]])
    outline = json.dumps(
        [{"slide_no": s["slide_no"], "type": s["type"], "headline": s["headline"]}
         for s in plan.get("slides", [])],
        ensure_ascii=False,
    )

    prompt = f"""아래 기획안 슬라이드의 body 를 회의록 내용으로 채우세요.
반드시 아래 JSON 형식만 반환하세요 (코드블록 없이 순수 JSON):

{{
  "title": "{plan.get('title', '')}",
  "purpose": "{plan.get('purpose', '')}",
  "target": "{plan.get('target', '')}",
  "tone": "{plan.get('tone', '')}",
  "slides": [
    {{"slide_no": 1, "type": "...", "headline": "...", "body": "...",
      "visual_hint": "...", "bg_color": "...", "emoji": "..."}}
  ]
}}

슬라이드 개요 (headline 변경 금지):
{outline}

작성 규칙:
- body: 3-4줄, 구체적 수치·결정사항 포함
- bg_color, emoji: 기획안 원본값 유지

[회의록]
{minutes_text[:3000]}"""

    llm = _make_llm(temperature=0.2)
    response = await llm.ainvoke(_to_lc([
        {"role": "system", "content": "카드뉴스 작성 전문가. 요청된 JSON 형식만 반환."},
        {"role": "user", "content": prompt},
    ]))
    result = _parse_json(response.content, plan.get("title", ""))
    # 누락된 색상/이모지 보강
    for slide in result.get("slides", []):
        t = slide.get("type", "content")
        slide.setdefault("bg_color", SLIDE_COLORS.get(t, "#2d3748"))
        slide.setdefault("emoji", SLIDE_EMOJIS.get(t, "💡"))
    return result


def _parse_json(text: str, fallback_title: str) -> dict:
    match = re.search(r'\{[\s\S]*\}', text.strip())
    if match:
        try:
            return json.loads(match.group())
        except Exception:
            pass
    return {
        "title": fallback_title,
        "purpose": "", "target": "", "tone": "",
        "slides": [{"slide_no": 1, "type": "cover", "headline": "회의 결과",
                    "body": "내용을 불러올 수 없습니다.",
                    "visual_hint": "", "bg_color": SLIDE_COLORS["cover"],
                    "emoji": SLIDE_EMOJIS["cover"]}],
    }


# ─────────────────────────────────────────────────────────────────
# 레거시 호환 (기존 generate_card_news 호출 유지)
# ─────────────────────────────────────────────────────────────────
async def generate_card_news(
    plan: Optional[dict] = None,
    minutes_list: Optional[List[str]] = None,
    emphasis_points: str = "",
    meeting_title: str = "",
    chat_history: Optional[List[dict]] = None,
) -> dict:
    if plan and plan.get("slides"):
        return await _enrich_plan(plan, minutes_list or [])
    return await _build_plan(chat_history or [], minutes_list or [], meeting_title)
import os, json, re
from typing import AsyncGenerator, List, Optional
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage

MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

# 슬라이드 타입별 배경색
SLIDE_COLORS = {
    "cover":    "#1e3a5f",
    "context":  "#1a4731",
    "content":  "#2d3748",
    "decision": "#3b1f6e",
    "action":   "#7c2d12",
    "closing":  "#1e3a5f",
}

SLIDE_EMOJIS = {
    "cover":    "📋",
    "context":  "🔍",
    "content":  "💡",
    "decision": "✅",
    "action":   "🚀",
    "closing":  "🙏",
}


def _make_llm(temperature: float = 0.4) -> ChatOpenAI:
    return ChatOpenAI(
        model=MODEL,
        temperature=temperature,
        api_key=os.getenv("OPENAI_API_KEY"),
    )


def _to_lc_messages(messages: List[dict]):
    result = []
    for m in messages:
        role, content = m["role"], m["content"]
        if role == "system":
            result.append(SystemMessage(content=content))
        elif role == "user":
            result.append(HumanMessage(content=content))
        else:
            result.append(AIMessage(content=content))
    return result


# ── 상담 시스템 프롬프트 ──────────────────────────────────────────
SYSTEM_PROMPT = """당신은 카드뉴스 기획 전문가 나온(Naon)입니다.

카드뉴스란: 모바일 환경에 최적화된 이미지 중심 뉴스 포맷으로, 10장 내외의 슬라이드에
핵심 정보를 간결한 글과 시각적 구성으로 전달하는 콘텐츠입니다.

당신의 역할:
1. 사용자가 원하는 카드뉴스 방향을 파악하기 위해 적극적으로 질문합니다.
2. 반드시 파악해야 할 4가지 정보:
   - 목적: 어디에 쓸 것인가? (임원 보고 / 팀 내 공유 / 사내 SNS / 외부 공개)
   - 대상 독자: 누가 볼 것인가? (경영진 / 실무자 / 전 직원 / 외부)
   - 강조 포인트: 무엇을 가장 부각할 것인가? (특정 결정사항 / 성과 / 문제 / 과제)
   - 톤앤매너: 어떤 느낌으로? (전문적·공식적 / 친근하고 쉽게 / 간결하고 임팩트 있게)
3. 위 4가지 중 모르는 정보가 있으면 반드시 먼저 질문하세요.
4. 정보가 충분해지면 "기획안을 작성할 준비가 되었습니다. [기획안 요청] 버튼을 눌러주세요."라고 안내하세요.

중요: 이미지 생성은 비용이 드는 작업입니다. 충분한 논의 후 기획안을 확정하고, 사용자가 승인한 뒤에만 생성합니다.
한국어로 응답합니다."""


async def chat_stream(
    message: str,
    chat_history: List[dict],
) -> AsyncGenerator[str, None]:
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    for h in chat_history[-12:]:
        messages.append(h)
    messages.append({"role": "user", "content": message})

    llm = _make_llm(temperature=0.5)
    async for chunk in llm.astream(_to_lc_messages(messages)):
        if chunk.content:
            yield chunk.content


# ── 기획안 제안 (생성 전 검토용) ──────────────────────────────────
async def propose_plan(
    chat_history: List[dict],
    minutes_list: List[str],
    meeting_title: str = "",
) -> dict:
    """대화 내용과 회의록을 바탕으로 카드뉴스 기획안(슬라이드 구조)을 제안한다.
    실제 이미지 생성 없이 텍스트 기획안만 반환한다."""
    minutes_text = "\n\n---\n\n".join([m[:1500] for m in minutes_list[:3]])

    # 대화에서 요구사항 추출
    conversation = "\n".join(
        f"[{'사용자' if h['role']=='user' else '나온'}] {h['content']}"
        for h in chat_history[-16:]
    )

    prompt = f"""대화 내용과 회의록을 바탕으로 카드뉴스 기획안을 작성해주세요.
반드시 아래 JSON 형식으로만 응답하세요 (코드블록 없이 순수 JSON):

{{
  "title": "카드뉴스 제목 (20자 이내)",
  "purpose": "목적 한 문장",
  "target": "대상 독자",
  "tone": "톤앤매너",
  "slides": [
    {{
      "slide_no": 1,
      "type": "cover",
      "headline": "메인 헤드라인 (15자 이내)",
      "body": "부제목 또는 핵심 한 줄 메시지",
      "visual_hint": "이미지/배경에 넣으면 좋을 요소 설명"
    }},
    {{
      "slide_no": 2,
      "type": "context",
      "headline": "배경·상황 제목",
      "body": "2-3줄 배경 설명",
      "visual_hint": "추천 시각 요소"
    }}
  ]
}}

슬라이드 구성 규칙:
- 총 8-10장으로 구성
- 슬라이드 타입: cover(1장) → context(1장) → content(4-5장) → decision(1장) → action(1장) → closing(1장)
- headline: 각 슬라이드의 핵심 메시지, 15자 이내, 임팩트 있게
- body: 3-4줄의 구체적 내용, 구어체 금지, 간결하게
- visual_hint: 실제 이미지 생성 시 참고할 시각적 요소 설명 (아이콘, 색상, 레이아웃 등)

[사용자와의 대화]
{conversation}

[회의 제목]
{meeting_title}

[회의록]
{minutes_text[:3000]}"""

    llm = _make_llm(temperature=0.3)
    response = await llm.ainvoke(_to_lc_messages([
        {"role": "system", "content": "당신은 카드뉴스 기획 전문가입니다. 요청된 JSON 형식만 반환하세요."},
        {"role": "user", "content": prompt},
    ]))

    text = response.content.strip()
    # JSON 블록 추출
    match = re.search(r'\{[\s\S]*\}', text)
    if match:
        try:
            plan = json.loads(match.group())
            # 슬라이드에 색상·이모지 보강
            for slide in plan.get("slides", []):
                t = slide.get("type", "content")
                slide.setdefault("bg_color", SLIDE_COLORS.get(t, "#2d3748"))
                slide.setdefault("emoji", SLIDE_EMOJIS.get(t, "💡"))
            return plan
        except Exception:
            pass

    # 파싱 실패 시 기본 구조 반환
    return {
        "title": f"{meeting_title} 회의 결과",
        "purpose": "회의 내용 공유",
        "target": "팀 구성원",
        "tone": "전문적",
        "slides": [
            {"slide_no": 1, "type": "cover", "headline": "회의 결과 요약",
             "body": "주요 내용을 정리했습니다.", "visual_hint": "제목 배경",
             "bg_color": SLIDE_COLORS["cover"], "emoji": SLIDE_EMOJIS["cover"]},
        ]
    }


# ── 확정된 기획안으로 카드뉴스 생성 ─────────────────────────────────
async def generate_card_news(
    plan: Optional[dict] = None,
    minutes_list: Optional[List[str]] = None,
    emphasis_points: str = "",
    meeting_title: str = "",
    chat_history: Optional[List[dict]] = None,
) -> dict:
    """확정된 기획안(plan)이 있으면 그것을 바탕으로, 없으면 새로 생성한다."""
    if plan and plan.get("slides"):
        # 기획안이 이미 확정됐으면 슬라이드 내용만 보강
        return await _enrich_plan(plan, minutes_list or [], meeting_title)

    # 기획안 없이 바로 생성 (레거시 호환)
    minutes_text = "\n\n---\n\n".join([m[:1500] for m in (minutes_list or [])[:3]])
    return await propose_plan(
        chat_history=chat_history or [],
        minutes_list=minutes_list or [],
        meeting_title=meeting_title,
    )


async def _enrich_plan(plan: dict, minutes_list: List[str], meeting_title: str) -> dict:
    """기획안 슬라이드의 body를 회의록 내용으로 보강한다."""
    minutes_text = "\n\n---\n\n".join([m[:1500] for m in minutes_list[:3]])
    slides_outline = json.dumps(
        [{"slide_no": s["slide_no"], "type": s["type"], "headline": s["headline"]}
         for s in plan.get("slides", [])],
        ensure_ascii=False
    )

    prompt = f"""아래 카드뉴스 기획안의 각 슬라이드 body를 회의록 내용으로 채워주세요.
반드시 아래 JSON 형식으로만 응답하세요 (코드블록 없이 순수 JSON):

{{
  "title": "{plan.get('title', meeting_title)}",
  "purpose": "{plan.get('purpose', '')}",
  "target": "{plan.get('target', '')}",
  "tone": "{plan.get('tone', '')}",
  "slides": [
    {{"slide_no": 1, "type": "cover", "headline": "...", "body": "...", "visual_hint": "...", "bg_color": "...", "emoji": "..."}}
  ]
}}

슬라이드 구성 (headline은 변경 금지):
{slides_outline}

작성 규칙:
- body는 3-4줄, 간결하고 임팩트 있게
- 구체적 수치/이름/결정사항이 있으면 반드시 포함
- 각 슬라이드의 bg_color와 emoji는 기존 값 유지

[회의록]
{minutes_text[:3000]}"""

    llm = _make_llm(temperature=0.2)
    response = await llm.ainvoke(_to_lc_messages([
        {"role": "system", "content": "당신은 카드뉴스 작성 전문가입니다. 요청된 JSON 형식만 반환하세요."},
        {"role": "user", "content": prompt},
    ]))

    text = response.content.strip()
    match = re.search(r'\{[\s\S]*\}', text)
    if match:
        try:
            result = json.loads(match.group())
            # 색상·이모지 보강 (누락 시)
            for slide in result.get("slides", []):
                t = slide.get("type", "content")
                slide.setdefault("bg_color", SLIDE_COLORS.get(t, "#2d3748"))
                slide.setdefault("emoji", SLIDE_EMOJIS.get(t, "💡"))
            return result
        except Exception:
            pass

    # 보강 실패 시 원본 기획안 반환
    return plan
