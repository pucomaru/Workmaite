"""나온 (Naon) - 카드뉴스 기획·생성 Agent (LangGraph Human-in-the-Loop)

흐름:
  1. chat_stream()       — 나온과 자유 대화 (LangChain streaming, 기획 요구사항 파악)
  2. start_proposal()    — LangGraph propose_node 실행 → interrupt() 로 그래프 일시 정지
                          → 기획안(plan) 반환, thread_id 로 상태 보존
  3. resume_proposal()   — Command(resume=...) 로 그래프 재개
                          · approved=True  → generate_node → 카드뉴스 완성
                          · approved=False → 대화 계속 (그래프 종료, 새 propose 대기)
"""

import os, json, re
from typing import TypedDict, Optional, List, AsyncGenerator

from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.types import interrupt, Command

MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
_DB = os.path.join(os.path.dirname(__file__), "..", "checkpoints.db")

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

카드뉴스란: 모바일 환경에 최적화된 슬라이드형 콘텐츠로, 핵심 정보를 간결한 글과
시각적 구성으로 전달합니다. SNS·포털·사내 공유에 주로 활용됩니다.

핵심 원칙: 카드뉴스는 누가 읽느냐에 따라 구성·언어·톤이 완전히 달라져야 합니다.

[대상별 설계 원칙]

C레벨 (CEO, CFO, CSO 등)
- 목적: 빠른 판단/의사결정 지원 / 분량: 5~7장
- 첫 장에 결론/핵심 수치 즉시 노출
- 언어: 숫자/비율/비교 중심 ("전년比 +23%")
- 구성: 결론 -> 근거 -> 요청사항 순
- 시각화: 단순 그래프/아이콘 (복잡한 표 금지)
- 톤: 간결/단정/객관적 / 금지: 배경 설명 장황, 감성 카피
- 슬라이드 예시: 핵심 지표 요약 / 원인 분석 / 대안 비교 / 권고안 / 요청 사항

임원 (본부장, 부문장, 이사 등)
- 목적: 전략 방향 정렬/부서 간 조율 근거 제공 / 분량: 7~10장
- 이슈 배경 + 핵심 메시지로 시작
- 언어: 전략적 용어 + 실행 맥락 병기
- 구성: 배경 -> 현황 -> 분석 -> 방향 -> 실행계획
- 포함 필수: 리스크 요인, 타부서 협조 필요 사항
- 슬라이드 예시: 발제 배경/목적 / 현황 및 문제 정의 / 시장·내부 분석 / 대안 검토 / 권고 방향 / 실행 로드맵 / 기대 효과·리스크 / 협조 요청 사항

구성원 (팀장, 실무자, 전직원)
- 목적: 정보 공유/행동 변화 유도/내부 문화 전달 / 분량: 6~10장
- 첫 장에 공감 가는 문제 제기 또는 훅(Hook) 카피
- 언어: 쉬운 단어/구어체/실생활 예시
- 구성: 문제공감 -> 내용 전달 -> 행동 유도
- 포함 필수: 나에게 미치는 영향, 해야 할 행동(CTA)
- 슬라이드 예시: 공감형 훅 / 현황/배경 설명 / 핵심 내용 / 내가 해야 할 것 / 문의/참고 안내

외부인 (고객, 파트너, 미디어, 일반 대중)
- 목적: 브랜드 신뢰 구축/정보 전달/관계 형성 / 분량: 6~8장
- 첫 장에 강한 비주얼 + 궁금증 유발 카피
- 언어: 전문용어 배제/보편적 언어/스토리텔링
- 구성: 흥미유발 -> 가치 전달 -> 신뢰 증거 -> CTA
- 포함 필수: 브랜드 로고, 출처, 연락처/링크(CTA)
- 슬라이드 예시: 시선 끄는 비주얼+카피 / 공감/문제 제시 / 해결책/가치 / 구체적 사례/수치 / 고객 혜택 요약 / CTA

[공통 필수 요소]
- 1장 1메시지: 카드 한 장에 핵심 하나만
- 텍스트: 3~5줄 이내 권장
- 일관된 디자인: 컬러/폰트/레이아웃 통일
- 출처/날짜 명시 (특히 수치 데이터)
- 마지막 장에 CTA 반드시 포함
- 모바일 최적화: 세로형/가독성 높은 폰트

역할: 자연스러운 대화를 통해 아래 4가지를 파악하세요.
1) 회의 차수 - 몇 차 회의 내용을 기반으로 할까요? (예: "1차, 2차 회의" / "전체")
2) 대상 독자 - 누가 볼 것인가요? (C레벨 / 임원 / 구성원 / 외부인)
3) 활용 자료 - 무엇을 기반으로 만들까요? (회의록 / 보고서 / 아젠다 / To-do / 의사결정)
4) 강조점   - 특별히 부각할 내용이 있나요?

파악 방법:
- 사용자의 답변에서 자연스럽게 위 정보를 추출/확인합니다
- 모호하면 친근하게 되물어봅니다 ("1차만 쓸까요, 2차까지 포함할까요?")
- 4가지가 모두 파악되면: "좋아요! [카드뉴스 생성] 버튼을 누르시면 제가 설정을 자동으로 읽어서 바로 시작할게요!"
- 사용자가 기본값 OK라고 하면 전체 회의 / 구성원 대상 / 전체 자료로 진행한다고 안내

한국어로 응답합니다."""


# 대상별 슬라이드 설계 명세
TARGET_SPECS = {
    "c_level": {
        "label": "C레벨 (CEO·CFO·CSO)",
        "slide_count": "5~7장",
        "first_card": "결론·핵심 수치 즉시 노출",
        "language": "숫자·비율·비교 중심 (예: 전년比 +23%)",
        "structure": "결론 → 근거 → 요청사항",
        "tone": "간결·단정·객관적. 배경 설명 최소화, 감성 카피 금지",
        "visualization": "단순 그래프·아이콘, 복잡한 표 금지",
        "slide_types": ["cover", "summary", "analysis", "options", "recommendation", "ask"],
        "slide_outline": [
            {"type": "cover",          "hint": "핵심 결론 + 날짜·보고자"},
            {"type": "summary",        "hint": "핵심 지표 3가지 (What happened)"},
            {"type": "analysis",       "hint": "원인 분석 (Why) — 2~3줄"},
            {"type": "options",        "hint": "대안 비교 (Options) — 표/아이콘"},
            {"type": "recommendation", "hint": "권고안 (Recommendation)"},
            {"type": "ask",            "hint": "요청 사항 (Ask) + CTA"},
        ],
    },
    "executive": {
        "label": "임원 (본부장·부문장·이사)",
        "slide_count": "7~10장",
        "first_card": "이슈 배경 + 핵심 메시지",
        "language": "전략적 용어 + 실행 맥락 병기",
        "structure": "배경 → 현황 → 분석 → 방향 → 실행계획",
        "tone": "논리적·설득적. 리스크·타부서 협조 반드시 포함",
        "visualization": "로드맵·비교표·플로우차트",
        "slide_types": ["cover", "context", "problem", "analysis", "options", "direction", "roadmap", "effect_risk", "cooperation"],
        "slide_outline": [
            {"type": "cover",       "hint": "발제 배경·목적"},
            {"type": "context",     "hint": "현황 및 문제 정의"},
            {"type": "analysis",    "hint": "시장·내부 분석"},
            {"type": "options",     "hint": "대안 검토"},
            {"type": "direction",   "hint": "권고 방향"},
            {"type": "roadmap",     "hint": "실행 로드맵 (타임라인)"},
            {"type": "effect_risk", "hint": "기대 효과 & 리스크"},
            {"type": "cooperation", "hint": "협조 요청 사항 + CTA"},
        ],
    },
    "staff": {
        "label": "구성원 (팀장·실무자·전직원)",
        "slide_count": "6~10장",
        "first_card": "공감형 훅 카피 (\"혹시 이런 경험 있으신가요?\")",
        "language": "쉬운 단어·구어체·실생활 예시",
        "structure": "문제공감 → 내용 전달 → 행동 유도",
        "tone": "친근·명확·동기부여형. 나에게 미치는 영향·CTA 필수",
        "visualization": "인포그래픽·이모지 활용 가능",
        "slide_types": ["hook", "context", "content", "content", "content", "action", "info"],
        "slide_outline": [
            {"type": "hook",    "hint": "공감형 훅 카피"},
            {"type": "context", "hint": "현황·배경 설명"},
            {"type": "content", "hint": "핵심 내용 ①"},
            {"type": "content", "hint": "핵심 내용 ②"},
            {"type": "content", "hint": "핵심 내용 ③"},
            {"type": "action",  "hint": "내가 해야 할 것 (Action·CTA)"},
            {"type": "info",    "hint": "문의·참고 안내"},
        ],
    },
    "external": {
        "label": "외부인 (고객·파트너·미디어)",
        "slide_count": "6~8장",
        "first_card": "강한 비주얼 + 궁금증 유발 카피",
        "language": "전문용어 배제·보편적 언어·스토리텔링",
        "structure": "흥미유발 → 가치 전달 → 신뢰 증거 → CTA",
        "tone": "감성적·신뢰감·매력적. 브랜드 로고·출처·연락처 필수",
        "visualization": "고품질 이미지·브랜드 컬러 일관성",
        "slide_types": ["visual_hook", "empathy", "solution", "evidence", "benefit", "cta"],
        "slide_outline": [
            {"type": "visual_hook", "hint": "시선 끄는 비주얼 + 한 줄 카피"},
            {"type": "empathy",     "hint": "공감 또는 문제 제시"},
            {"type": "solution",    "hint": "우리의 해결책·가치"},
            {"type": "evidence",    "hint": "구체적 사례·수치·증거"},
            {"type": "benefit",     "hint": "고객 혜택 중심 요약"},
            {"type": "cta",         "hint": "CTA (방문·신청·문의 유도) + 연락처"},
        ],
    },
}


async def chat_stream(
    message: str,
    chat_history: List[dict],
    meeting_context: str = "",
) -> AsyncGenerator[str, None]:
    """나온과의 자유 대화 — LangChain 스트리밍."""
    system_content = CHAT_SYSTEM
    if meeting_context:
        system_content += f"\n\n[회의체 맥락 — 이 정보를 항상 참고하세요]\n{meeting_context}"
    messages = [{"role": "system", "content": system_content}]
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
    sources: List[str]         # 회의록·보고서·아젠다·To-do·의사결정 등 수집된 자료 청크
    meeting_title: str
    target_audience: str       # c_level | executive | staff | external
    style_hints: Optional[dict]  # 슬라이드 분량, 첫 장, 톤, 시각화 등 사용자 세부 설정
    plan: Optional[dict]       # propose_node 가 생성한 기획안
    card_news: Optional[dict]  # generate_node 가 완성한 카드뉴스


async def _propose_node(state: ProposalState) -> dict:
    """
    [Node 1] 대화 내용 + 수집 자료 → 기획안 생성 → interrupt() 로 일시 정지.
    """
    plan = await _build_plan(
        chat_history=state["chat_history"],
        sources=state["sources"],
        meeting_title=state["meeting_title"],
        target_audience=state.get("target_audience", "staff"),
        style_hints=state.get("style_hints"),
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
    """[Node 2] 승인된 기획안 → 수집 자료로 슬라이드 보강 → 완성."""
    card_news = await _enrich_plan(state["plan"], state["sources"])
    return {"card_news": card_news}


def _route_after_propose(state: ProposalState) -> str:
    """propose_node 완료 후 라우팅: 승인됐으면 generate, 거부됐으면 종료."""
    return "generate" if state.get("plan") else END


# 그래프 빌드
def _build_graph_structure() -> StateGraph:
    builder = StateGraph(ProposalState)
    builder.add_node("propose", _propose_node)
    builder.add_node("generate", _generate_node)
    builder.set_entry_point("propose")
    builder.add_conditional_edges("propose", _route_after_propose, {
        "generate": "generate",
        END: END,
    })
    builder.add_edge("generate", END)
    return builder

_graph_structure = _build_graph_structure()

async def _get_graph():
    """AsyncSqliteSaver를 checkpointer로 사용하는 그래프 생성"""
    async with AsyncSqliteSaver.from_conn_string(_DB) as checkpointer:
        return _graph_structure.compile(checkpointer=checkpointer), checkpointer


# ─────────────────────────────────────────────────────────────────
# 3. Public API (routers/agents.py 에서 호출)
# ─────────────────────────────────────────────────────────────────

async def start_proposal(
    thread_id: str,
    chat_history: List[dict],
    sources: List[str],
    meeting_title: str,
    target_audience: str = "staff",
    style_hints: Optional[dict] = None,
) -> dict:
    """
    propose_node 를 실행한다. interrupt() 지점에서 그래프가 멈추고
    기획안(plan) 을 반환한다. thread_id 로 상태가 checkpointer 에 보존된다.
    """
    config = {"configurable": {"thread_id": thread_id}}
    async with AsyncSqliteSaver.from_conn_string(_DB) as checkpointer:
        graph = _graph_structure.compile(checkpointer=checkpointer)
        await graph.ainvoke(
            {
                "chat_history": chat_history,
                "sources": sources,
                "meeting_title": meeting_title,
                "target_audience": target_audience,
                "style_hints": style_hints,
                "plan": None,
                "card_news": None,
            },
            config,
        )
        state = graph.get_state(config)
        if state.tasks and state.tasks[0].interrupts:
            plan = state.tasks[0].interrupts[0].value
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
    async with AsyncSqliteSaver.from_conn_string(_DB) as checkpointer:
        graph = _graph_structure.compile(checkpointer=checkpointer)
        result = await graph.ainvoke(
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
    sources: List[str],
    meeting_title: str,
    target_audience: str = "staff",
    style_hints: Optional[dict] = None,
) -> dict:
    """대화 기록 + 수집 자료(회의록·보고서·아젠다·To-do·의사결정) → 슬라이드 기획안(JSON) 생성."""
    # 소스를 구분자로 합치되 총 4000자 이내로 제한
    source_text = "\n\n---\n\n".join(s[:800] for s in sources[:8])
    conversation = "\n".join(
        f"[{'사용자' if h['role'] == 'user' else '나온'}] {h['content']}"
        for h in chat_history[-16:]
    )

    spec = TARGET_SPECS.get(target_audience, TARGET_SPECS["staff"])
    outline_hint = "\n".join(
        f"  - {s['type']}: {s['hint']}"
        for s in spec["slide_outline"]
    )

    # 사용자 스타일 힌트 텍스트 생성
    FIRST_CARD_MAP = {
        "conclusion":  "결론·핵심 수치를 첫 장에 즉시 노출 (배경 설명 최소화)",
        "issue_bg":    "이슈 배경과 핵심 메시지로 시작 (발제 맥락 명확히)",
        "hook":        "공감형 훅 카피로 시작 (예: '혹시 이런 경험 있으신가요?')",
        "visual_hook": "강한 비주얼과 궁금증 유발 카피로 첫 장 구성",
    }
    TONE_MAP = {
        "concise":   "간결·단정·객관적 (배경 설명 최소화, 감성 카피 금지)",
        "logical":   "논리적·설득적 (리스크·타부서 협조사항 반드시 포함)",
        "friendly":  "친근·명확·동기부여형 (구어체·실생활 예시 활용)",
        "emotional": "감성적·신뢰감·매력적 (스토리텔링·브랜드 일관성)",
    }
    VISUAL_MAP = {
        "simple_graph": "단순 그래프·아이콘 위주 (복잡한 표 금지)",
        "roadmap":      "로드맵·비교표·플로우차트 활용 (전략 시각화)",
        "infographic":  "인포그래픽·이모지·캐릭터 활용 가능 (친근한 시각화)",
        "image_brand":  "고품질 이미지·브랜드 컬러 일관성 필수",
    }

    style_text = ""
    unset_fields = []
    if style_hints:
        parts = []
        sc = style_hints.get("slide_count")
        fc = style_hints.get("first_card")
        tn = style_hints.get("tone")
        vs = style_hints.get("visual_style")
        if sc:
            parts.append(f"슬라이드 수: 정확히 {sc}장")
        else:
            unset_fields.append(("슬라이드 분량", ["5장", "6장", "7장", "8장", "10장"]))
        if fc and fc in FIRST_CARD_MAP:
            parts.append(f"첫 장 구성: {FIRST_CARD_MAP[fc]}")
        else:
            unset_fields.append(("첫 장 구성 방식", ["결론·수치 우선", "이슈 배경+메시지", "공감형 훅 카피", "비주얼+궁금증 카피"]))
        if tn and tn in TONE_MAP:
            parts.append(f"언어·톤: {TONE_MAP[tn]}")
        else:
            unset_fields.append(("언어·톤", ["간결·객관", "논리적·설득", "친근·동기부여", "감성·신뢰"]))
        if vs and vs in VISUAL_MAP:
            parts.append(f"시각화 방향: {VISUAL_MAP[vs]}")
        else:
            unset_fields.append(("시각화 스타일", ["단순 그래프·아이콘", "로드맵·비교표", "인포그래픽·이모지", "이미지·브랜드컬러"]))
        if style_hints.get("include_cta"):
            parts.append("마지막 장에 CTA(다음 행동 유도) 반드시 포함")
        if style_hints.get("include_source_date"):
            parts.append("수치 데이터에 출처·날짜 명시")
        if style_hints.get("include_brand_logo"):
            parts.append("브랜드 로고 슬라이드 포함")
        if parts:
            style_text = "\n[사용자 추가 스타일 설정]\n" + "\n".join(f"- {p}" for p in parts)
        cr = style_hints.get("custom_request")
        if cr and cr.strip():
            style_text += f"\n\n[사용자 직접 요청]\n{cr.strip()}"

    # 미설정 항목 안내 — 나온이 맥락으로 판단하되, 판단 어려우면 JSON에 질문 포함
    unset_hint = ""
    if unset_fields:
        field_names = ", ".join(f[0] for f in unset_fields)
        unset_hint = (
            f"\n[사용자가 지정하지 않은 항목: {field_names}]\n"
            "대화·자료 맥락에서 최적값을 스스로 판단하세요.\n"
            "판단이 불가능하거나 명확히 확인이 필요한 항목만 'clarifying_questions'에 포함하세요.\n"
            "질문이 없으면 반드시 빈 배열 []로 두세요."
        )

    # clarifying_questions options 힌트 (JSON 스키마 예시에 포함)
    cq_options_hint = ""
    if unset_fields:
        ex_field, ex_opts = unset_fields[0]
        opts_str = json.dumps(ex_opts, ensure_ascii=False)
        cq_options_hint = f'\n    {{"question": "{ex_field}을(를) 어떻게 할까요?", "options": {opts_str}}}'

    prompt = f"""사용자 대화와 아래 미팅 자료(회의록·보고서·아젠다·To-do·의사결정 등)를 종합하여
카드뉴스 기획안을 작성하세요.
반드시 아래 JSON 형식만 반환하세요 (코드블록 없이 순수 JSON):

{{
  "title": "카드뉴스 제목 (20자 이내)",
  "purpose": "목적 한 문장",
  "target": "{spec['label']}",
  "tone": "{spec['tone'][:50]}",
  "clarifying_questions": [{cq_options_hint}
  ],
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

clarifying_questions: 스스로 판단 어려운 항목만 포함. 판단 가능하면 반드시 빈 배열 [].
각 질문은 {{"question": "...", "options": ["A", "B", ...]}} 형식.

【대상 독자】 {spec['label']}
【분량】 {spec['slide_count']}
【첫 장 원칙】 {spec['first_card']}
【언어 스타일】 {spec['language']}
【구성 순서】 {spec['structure']}
【톤앤매너】 {spec['tone']}
【시각화 방향】 {spec['visualization']}
【권장 슬라이드 구성】
{outline_hint}
{style_text}
{unset_hint}
headline: 15자 이내, 임팩트 있게 / body: 3~5줄, 간결하게

[사용자 대화]
{conversation}

[회의명] {meeting_title}
[미팅 자료 — 회의록·보고서·아젠다·To-do·의사결정 등]
{source_text[:4000]}"""

    llm = _make_llm(temperature=0.3)
    response = await llm.ainvoke(_to_lc([
        {"role": "system", "content": "카드뉴스 기획 전문가. 요청된 JSON 형식만 반환."},
        {"role": "user", "content": prompt},
    ]))
    result = _parse_json(response.content, meeting_title)
    result.setdefault("target_audience", target_audience)
    result.setdefault("target", spec["label"])
    return result


async def _enrich_plan(plan: dict, sources: List[str]) -> dict:
    """승인된 기획안 슬라이드에 수집 자료를 채워 최종 카드뉴스 완성."""
    minutes_text = "\n\n---\n\n".join([s[:800] for s in sources[:8]])
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

[미팅 자료]
{minutes_text[:4000]}"""

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


# ─────────────────────────────────────────────────────────────────
# 자연어 파라미터 추출
# ─────────────────────────────────────────────────────────────────
async def extract_params_from_chat(
    chat_history: List[dict],
    available_sessions: List[dict],  # [{id, session_number, title}]
) -> dict:
    """
    대화 기록에서 카드뉴스 생성에 필요한 파라미터를 LLM으로 추출합니다.
    반환: {session_ids, target_audience, include_minutes, include_reports,
           include_agendas, include_todos, include_decisions, confidence, summary}
    """
    sessions_info = "\n".join(
        f"- {s['session_number']}차: {s.get('title', '(제목 없음)')} (id={s['id']})"
        for s in available_sessions
    ) if available_sessions else "(회의 목록 없음)"

    conversation = "\n".join(
        f"[{'사용자' if h['role'] == 'user' else '나온'}] {h['content']}"
        for h in chat_history[-20:]
    )

    prompt = f"""아래 대화에서 카드뉴스 생성에 필요한 파라미터를 추출하세요.
코드블록 없이 순수 JSON만 반환하세요:

{{
  "session_ids": [],
  "target_audience": "staff",
  "include_minutes": true,
  "include_reports": true,
  "include_agendas": true,
  "include_todos": true,
  "include_decisions": true,
  "confidence": 0.5,
  "summary": "설정 요약 한 줄"
}}

【값 선택 기준】
- session_ids: 대화에서 언급된 회의 차수의 id 목록. 전체라면 빈 배열 []
- target_audience: "c_level" | "executive" | "staff" | "external"
  · C레벨·CEO·대표·경영진 → "c_level"
  · 임원·이사·본부장·부문장 → "executive"
  · 구성원·팀원·직원·전직원 → "staff" (기본값)
  · 외부·고객·파트너·대중 → "external"
- include_*: 대화에서 특정 자료만 언급했으면 해당 항목만 true, 나머지 false.
  아무것도 언급 없으면 전부 true
- confidence: 0~1. 충분히 파악된 항목이 많을수록 높게. 기본값은 0.5
- summary: 예) "1·2차 회의 / 임원 대상 / 회의록+보고서 활용"

【가용 회의 차수】
{sessions_info}

【대화 기록】
{conversation}"""

    llm = _make_llm(temperature=0.0)
    response = await llm.ainvoke(_to_lc([
        {"role": "system", "content": "JSON만 반환하는 파라미터 추출기입니다."},
        {"role": "user", "content": prompt},
    ]))
    result = _parse_json(response.content, "")
    # 기본값 보정
    result.setdefault("session_ids", [])
    result.setdefault("target_audience", "staff")
    for key in ("include_minutes", "include_reports", "include_agendas", "include_todos", "include_decisions"):
        result.setdefault(key, True)
    result.setdefault("confidence", 0.5)
    result.setdefault("summary", "전체 회의 / 구성원 대상 / 전체 자료")
    return result
