import json
import os
from datetime import datetime
from typing import List, Optional, Literal, cast

from fastapi import APIRouter, Depends, BackgroundTasks
from fastapi.responses import StreamingResponse
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, BaseMessage
from sqlalchemy.orm import Session, joinedload

from db import models
from db import schemas
from db.database import get_db, SessionLocal
from core.auth import get_current_user
from core.access_guard import require_view
from realtime.sse import sse_done, sse_event, sse_token
from llm.metrics import instrument_stream
from agents import (
    task_extractor as task_agent,
    minutes_generator as minutes_agent,
    report_reviewer as report_agent,
)
from graphdb.neo4j_client import (
    get_meeting_graph_context,
    graph_context_to_str,
    run_cypher,
)
from pydantic import BaseModel, Field
import logging

from .prompts import make_llm
from llm.agent_logging import (
    TokenUsageCollector,
    _token_collector_var,
    _create_log,
    _finalize,
)
from graphdb.neo4j_ids import to_mg_id
from llm.llm_factory import model_override_var
from llm.pricing import PRICING

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/agent", tags=["agents"])


def _to_base_messages(messages: List[dict]) -> List[BaseMessage]:
    result: List[BaseMessage] = []
    for m in messages:
        role, content = m.get("role", ""), m.get("content", "") or ""
        if role == "user":
            result.append(HumanMessage(content=content))
        elif role in ("assistant", "agent"):
            result.append(AIMessage(content=content))
    return result


# ─── Knowledge Base 요청 스키마 ───────────────────────────────────────────────
class _StoreMinutesReq(BaseModel):
    meeting_id: int
    session_id: Optional[int] = None
    title: str
    content: str


class _StoreTaskReq(BaseModel):
    content: str
    department: Optional[str] = None
    due_date: Optional[str] = None
    meeting_id: Optional[int] = None


class _StoreReportReq(BaseModel):
    title: str
    content: str
    meeting_id: Optional[int] = None
    score: Optional[int] = None


class _ProposeRelationshipsReq(BaseModel):
    """POST /knowledge/propose-relationships 요청 바디."""

    meeting_id: int
    node_types: Optional[List[str]] = None  # None이면 Agenda·Minutes 전체


class _ConfirmRelationshipsReq(BaseModel):
    """POST /knowledge/confirm-relationships 요청 바디."""

    proposal_id: str
    approved: bool
    reject_reason: Optional[str] = None  # approved=False 일 때 반려 사유


# ─── Supervisor 라우팅 — LLM이 직접 에이전트를 선택 ───────────────────────────
class _RoutingDecision(BaseModel):
    """LLM 슈퍼바이저의 라우팅 결정 스트럭처드 아웃풋."""

    thinking: str = Field(
        description="어떤 에이전트가 적합한지 한국어로 1~2문장 근거 설명"
    )
    agent: Literal[
        "task_extractor",
        "minutes_generator",
        "report_reviewer",
        "knowledge_manager",
        "supervisor_direct",
        # 프롬프트가 지시하는데 Literal에 없어 반환 불가였던 죽은 라벨 복구 (P3A-5
        # — eval r15에서 코딩 요청이 task_extractor로 오분류되는 것으로 실측 확인)
        "off_topic",
    ] = Field(description="위임할 에이전트 이름")


_ROUTING_SYSTEM = """\
당신은 워크메이트 AI 슈퍼바이저입니다.
사용자의 요청 '의도'를 의미적으로 파악해 가장 적합한 에이전트를 선택하고 처리 계획을 세우세요.
특정 단어의 포함 여부가 아니라 사용자가 실제로 무엇을 원하는지로 판단하세요.

에이전트 선택 기준:
- task_extractor: 아젠다·과제·할 일·투두·Todo 새로 추출, 다음 회의 준비, 아카이브 파일 분석·추출
- minutes_generator: 회의록 작성·요약·편집, 회의 진행 보조, 실시간 통역·속기
- report_reviewer: 보고서·문서 검토·분석, 리뷰·피드백, 파일·자료 평가
- knowledge_manager: 과거 회의 내용 검색, 지식 베이스 저장·관리, HITL 검토·승인, 관계 그래프 조회
- supervisor_direct: 회의체 현황·브리핑, 과제 진행 상황 조회, 보고서 제출 현황 조회, 소속 회의체 목록, 구성원 안내, 인사·사용법·그 외 회의체 운영 관련 단순 질의(기본값)
- off_topic: 회의체 운영과 전혀 관련 없는 질문 (날씨·나이·코딩·개인 신상·잡담·일반 상식 등)

참고 (강제 규칙 아님 — 판단 보조용 예시):
- 회의체 현황·브리핑·소속·진행/제출 현황을 묻는 단순 조회성 질문은 대체로 supervisor_direct가 적합합니다.
- "오늘 날씨", "농담 해줘"처럼 회의체와 무관한 잡담은 off_topic입니다.
  단, 인사("안녕하세요", "고마워")와 워크메이트 사용법 질문은 off_topic이 아니라 supervisor_direct입니다.
- 의도가 모호하면 supervisor_direct를 기본으로 선택하세요(되묻거나 도구로 확인할 수 있습니다).

thinking 필드에 선택 이유를 한국어 1~2문장으로 작성하세요."""


async def classify_intent(
    message: str, history: List[dict] | None = None
) -> tuple[str, str, List[str]]:
    """사용자 메시지를 분석해 (에이전트명, 근거, 처리단계) 튜플을 반환합니다.

    history(최근 대화)를 주면 멀티턴 맥락을 반영해 라우팅한다 (AI-9 — 예:
    "방금 그거 회의록으로 만들어줘"처럼 직전 대화를 가리키는 요청).
    """
    try:
        human = message[:500]
        if history:
            recent = "\n".join(
                f"{m.get('role', 'user')}: {str(m.get('content', ''))[:120]}"
                for m in history[-6:]
            )
            human = f"[최근 대화]\n{recent}\n\n[현재 요청]\n{message[:500]}"
        routing_llm = make_llm(temperature=0.0, streaming=False).with_structured_output(
            _RoutingDecision
        )
        decision = await routing_llm.ainvoke(
            [
                SystemMessage(content=_ROUTING_SYSTEM),
                HumanMessage(content=human),
            ]
        )
        decision = cast(_RoutingDecision, decision)
        return decision.agent, decision.thinking, []
    except Exception as e:
        logger.warning(f"[Supervisor] 라우팅 LLM 실패, supervisor_direct 사용: {e}")
        return "supervisor_direct", "기본 처리 경로로 응답합니다.", []


# ─── Helpers — services 레이어로 분리됨 (P3A-4) ──────────────────────────────
from services.supervisor_helpers import (  # noqa: F401, E402
    _extract_text_from_file,
    _format_schedule_table,
    _get_meeting_context,
    _get_member_org_depts,
    _get_previous_minutes,
    _log_activity,
    _stream_plan,
    _build_session_context,
    _format_session_context_str,
)
from core.access_guard import require_view_by_session


# ─── Minutes (아라) 에이전트 ──────────────────────────────────────────────────
@router.post("/minutes/sessions-chat")
async def minutes_sessions_chat(
    data: schemas.AgentChatRequest,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if data.meeting_id:
        require_view(db, current_user, data.meeting_id)
    sessions = (
        db.query(models.MeetingSession)
        .filter(models.MeetingSession.meeting_id == data.meeting_id)
        .order_by(models.MeetingSession.id.desc())
        .all()
    )
    sessions_info = [
        {
            "id": s.id,
            "title": s.title,
            "status": s.status,
            "summary": s.minutes.content_summary
            if s.minutes and s.minutes.content_summary
            else None,
        }
        for s in sessions
    ]
    agendas = (
        db.query(models.Agenda)
        .filter(
            models.Agenda.meeting_id == data.meeting_id,
            models.Agenda.status != "draft",
        )
        .all()
    )

    session_list_text = "\n".join(
        [
            f"- {s['title']} ({s['status']})"
            + (": 요약 있음" if s["summary"] else ": 요약 없음")
            for s in sessions_info
        ]
    )
    extra_context = f"[회의 세션 목록]\n{session_list_text}"
    session_summaries = [
        f"[{s['title']}] {s['summary']}" for s in sessions_info if s["summary"]
    ]
    if session_summaries:
        extra_context += "\n\n[세션별 회의록]\n" + "\n\n".join(session_summaries)

    async def stream():
        _collector = TokenUsageCollector()
        _tok_ctx_token = _token_collector_var.set(_collector)
        _log_id = _create_log(
            context_type="minutes_stream",
            meeting_id=data.meeting_id or None,
            session_id=None,
            user_id=current_user.id,
            input_data={"message": (data.message or "")[:300]},
        )
        _stream_error = None
        try:
            async for chunk in minutes_agent.chat_stream(
                message=data.message,
                chat_history=data.chat_history or [],
                previous_minutes=[extra_context],
                current_agendas=[
                    {"content": a.title, "status": a.status} for a in agendas
                ],
                meeting_context=_get_meeting_context(db, data.meeting_id),
            ):
                yield sse_token(chunk)
            yield sse_done()
        except BaseException as _e:
            _stream_error = _e
            raise
        finally:
            _token_collector_var.reset(_tok_ctx_token)
            _finalize(_log_id, _collector, _stream_error, None)

    return StreamingResponse(
        instrument_stream(stream(), "minutes_chat"), media_type="text/event-stream"
    )  # TTFT 측정 (P5-1)


@router.post("/minutes/generate-minutes")
async def minutes_generate_minutes(
    data: schemas.AgentChatRequest,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if data.meeting_id:
        require_view(db, current_user, data.meeting_id)
    transcript = data.message or ""
    meeting_context = (
        _get_meeting_context(db, data.meeting_id) if data.meeting_id else ""
    )
    agendas = (
        db.query(models.Agenda)
        .filter(
            models.Agenda.meeting_id == data.meeting_id,
            models.Agenda.status != "draft",
        )
        .all()
        if data.meeting_id
        else []
    )
    agenda_text = "\n".join([f"- {a.title} ({a.status})" for a in agendas]) or "없음"
    now = datetime.now().strftime("%Y년 %m월 %d일")
    meeting_obj = (
        db.query(models.Meeting).filter(models.Meeting.id == data.meeting_id).first()
        if data.meeting_id
        else None
    )
    minutes_title = (
        f"{meeting_obj.title} 회의록 ({now})" if meeting_obj else f"회의록 ({now})"
    )

    # session_info
    session_info = None
    if data.session_id:
        session = (
            db.query(models.MeetingSession)
            .filter(models.MeetingSession.id == data.session_id)
            .first()
        )
        if session:
            session_info = {
                "title": session.title,
                "started_at": session.started_at.strftime("%Y-%m-%d %H:%M")
                if session.started_at
                else None,
                "ended_at": session.ended_at.strftime("%Y-%m-%d %H:%M")
                if session.ended_at
                else None,
                "location": session.location,
            }

    # participants: session_id 있으면 세션 참석자, 없으면 회의체 멤버 전체
    participants = []
    if data.session_id:
        sm_rows = (
            db.query(models.SessionMember)
            .filter(models.SessionMember.session_id == data.session_id)
            .all()
        )
        user_ids = [sm.user_id for sm in sm_rows]
        role_map = {sm.user_id: sm.role for sm in sm_rows}
        users = (
            db.query(models.User).filter(models.User.id.in_(user_ids)).all()
            if user_ids
            else []
        )
        participants = [
            {
                "name": u.name,
                "dept": u.department or "",
                "role": role_map.get(u.id, "member"),
            }
            for u in users
        ]
    elif data.meeting_id:
        mm_rows = (
            db.query(models.MeetingMember)
            .options(joinedload(models.MeetingMember.user))
            .filter(models.MeetingMember.meeting_id == data.meeting_id)
            .all()
        )
        participants = [
            {
                "name": mm.user.name,
                "dept": mm.user.department or "",
                "role": mm.meeting_role,
            }
            for mm in mm_rows
            if mm.user
        ]

    # 이전 세션 회의록 (최근 2개 — 흐름 파악용)
    prev_minutes_list = []
    if data.meeting_id and data.session_id:
        prev_sessions = (
            db.query(models.MeetingSession)
            .filter(
                models.MeetingSession.meeting_id == data.meeting_id,
                models.MeetingSession.id < data.session_id,
            )
            .order_by(models.MeetingSession.id.desc())
            .limit(2)
            .all()
        )
        for ps in prev_sessions:
            m = (
                db.query(models.Minutes)
                .filter(models.Minutes.session_id == ps.id)
                .first()
            )
            if m and m.content_summary:
                prev_minutes_list.append(
                    f"[{ps.title or '이전 세션'}]\n{m.content_summary[:600]}"
                )

    # 마감 지난 미배정 안건
    from datetime import datetime as _dt

    overdue_agendas = [
        {
            "title": a.title,
            "due_date": a.due_date.strftime("%Y-%m-%d") if a.due_date else "",
        }
        for a in agendas
        if a.session_id is None
        and a.due_date is not None
        and a.due_date < _dt.utcnow()
        and a.status not in ("done", "completed", "closed")
    ]

    # SessionSummaryBlock (refine-chunk 결과 — 이미 구조화된 논의 흐름)
    summary_blocks = []
    if data.session_id:
        blocks = (
            db.query(models.SessionSummaryBlock)
            .filter(models.SessionSummaryBlock.session_id == data.session_id)
            .order_by(models.SessionSummaryBlock.block_index)
            .all()
        )
        for b in blocks:
            bullets = (
                "\n".join([f"  • {bl}" for bl in (b.bullets or [])])
                if b.bullets
                else ""
            )
            summary_blocks.append(
                f"[{b.title}]\n{bullets}" if bullets else f"[{b.title}]"
            )

    # 관련 보고서 내용 (Neo4j 벡터 검색)
    report_chunks = []
    if agendas:
        try:
            from agents.knowledge_manager import search_knowledge

            query = " ".join([a.title for a in agendas[:5]])
            chunks = await search_knowledge(query, k=5)
            report_chunks = [c.get("content", "") for c in chunks if c.get("content")]
        except Exception:
            pass

    async def stream():
        _collector = TokenUsageCollector()
        _tok_ctx_token = _token_collector_var.set(_collector)
        _log_id = _create_log(
            context_type="minutes_generate",
            meeting_id=data.meeting_id or None,
            session_id=data.session_id or None,
            user_id=current_user.id,
            input_data={"session_id": data.session_id},
        )
        _stream_error = None
        try:
            # 한 번만 생성·스트리밍한다 — 기존엔 generate_minutes_stream을 두 번 호출해 회의록이
            # 두 벌로 이어붙던 버그가 있었다("여러개 생성"의 원인). 전체 컨텍스트(이전 회의록·
            # 요약블록·보고서·미배정 안건)를 사용한다.
            async for chunk in minutes_agent.generate_minutes_stream(
                transcript=transcript,
                meeting_context=meeting_context,
                agenda_text=agenda_text,
                now=now,
                meeting_id=data.meeting_id,
                session_id=data.session_id,
                title=minutes_title,
                session_info=session_info,
                participants=participants,
                prev_minutes=prev_minutes_list,
                summary_blocks=summary_blocks,
                report_chunks=report_chunks,
                overdue_agendas=overdue_agendas,
            ):
                yield sse_token(chunk)
            # 생성은 미리보기만 — PG/Neo4j 영속화는 사용자가 '아카이브 저장'(/api/upload/minutes)을
            # 누를 때만 한다. 생성만으로 DB·그래프에 박히면 사용자 의도와 어긋나므로 자동 저장 제거.
            yield sse_done()
        except BaseException as _e:
            _stream_error = _e
            raise
        finally:
            _token_collector_var.reset(_tok_ctx_token)
            _finalize(_log_id, _collector, _stream_error, None)

    return StreamingResponse(
        instrument_stream(stream(), "minutes_generate"), media_type="text/event-stream"
    )  # TTFT 측정 (P5-1)


# ─── 롤링 요약 캐시 (session_id + 마지막 블록 id → 압축 텍스트) ─────────────
_rolling_summary_cache: dict[tuple, str] = {}
_ROLLING_THRESHOLD = 5   # 이 블록 수 초과 시 오래된 블록 압축
_ROLLING_KEEP_RECENT = 3  # 최근 N개 블록은 항상 전문 유지


async def _get_rolling_summary_text(summary_blocks: list) -> str:
    """블록이 THRESHOLD 초과 시 오래된 블록을 LLM으로 압축, 최근 블록은 전문 유지."""
    if len(summary_blocks) <= _ROLLING_THRESHOLD:
        # 전부 그대로 렌더링
        parts = []
        for b in summary_blocks:
            bullets = "\n".join(f"  • {bl}" for bl in (b.bullets or [])) if b.bullets else ""
            parts.append(f"[{b.title}]\n{bullets}" if bullets else f"[{b.title}]")
        return "\n\n".join(parts)

    old_blocks = summary_blocks[:-_ROLLING_KEEP_RECENT]
    recent_blocks = summary_blocks[-_ROLLING_KEEP_RECENT:]
    cache_key = (summary_blocks[0].session_id, summary_blocks[-1].id)

    if cache_key not in _rolling_summary_cache:
        old_text = "\n\n".join(
            f"[{b.title}]\n" + "\n".join(f"• {bl}" for bl in (b.bullets or []))
            for b in old_blocks
        )
        try:
            from langchain_core.messages import HumanMessage as _HM
            _llm = make_llm(temperature=0.1, streaming=False)
            _res = await _llm.ainvoke([
                _HM(content=(
                    "아래는 회의 진행 중 생성된 실시간 요약 블록들입니다. "
                    "핵심 결정사항과 액션아이템만 남겨 3~5줄로 압축하세요. "
                    "불필요한 설명 없이 bullet 형식으로만 작성하세요.\n\n" + old_text
                ))
            ])
            merged = f"[전반부 요약]\n{_res.content.strip()}"
        except Exception:
            merged = "\n".join(f"[{b.title}]" for b in old_blocks)
        _rolling_summary_cache[cache_key] = merged

    recent_parts = []
    for b in recent_blocks:
        bullets = "\n".join(f"  • {bl}" for bl in (b.bullets or [])) if b.bullets else ""
        recent_parts.append(f"[{b.title}]\n{bullets}" if bullets else f"[{b.title}]")

    return _rolling_summary_cache[cache_key] + "\n\n" + "\n\n".join(recent_parts)


# ─── 세션 전용 챗 ────────────────────────────────────────────────────────────
@router.post("/session/chat")
async def session_chat(
    data: schemas.AgentChatRequest,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """세션 상태에 따라 분기하는 회의 전용 챗봇.

    scheduled → 기본 정보(일정·참석자·안건)만 안내
    ongoing   → 진행 중 안내
    ended     → 회의록 미생성 안내
    archived  → Neo4j RAG로 회의록 기반 답변
    """
    if not data.session_id:
        # 세션 미선택 시 supervisor 로직으로 fallback
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="session_id가 필요합니다.")

    require_view_by_session(db, current_user, data.session_id)

    ctx = _build_session_context(db, data.session_id)
    if not ctx:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="세션을 찾을 수 없습니다.")

    session = ctx["session"]
    status = session.status

    # 상태별 추가 컨텍스트
    if status == "archived":
        # Neo4j RAG — 회의록 임베딩 검색
        try:
            from graphdb.retrieval_registry import vector_search
            rag_rows = await vector_search(
                "Minutes",
                data.message,
                k=3,
                meeting_ids=[session.meeting_id],
            )
            rag_text = "\n\n".join(
                r.get("summary") or r.get("content") or ""
                for r in rag_rows
                if r.get("summary") or r.get("content")
            )
        except Exception as e:
            logger.warning(f"[session_chat] RAG 검색 실패 (무시): {e}")
            rag_text = ""
    else:
        rag_text = ""

    # 블록이 THRESHOLD 초과 시 오래된 블록을 LLM으로 압축 (rolling summary)
    summary_blocks = ctx.get("summary_blocks", [])
    if summary_blocks:
        ctx["summary_text_override"] = await _get_rolling_summary_text(summary_blocks)

    base_context = _format_session_context_str(ctx)

    status_guide = {
        "scheduled": (
            "이 회의는 아직 시작되지 않았습니다.\n"
            "아래 데이터에 있는 일정·장소·참석자·안건은 그대로 답변하세요.\n"
            "안건([안건] 섹션)이 비어 있으면 '이 회의에 등록된 안건이 없습니다'라고 답변하세요.\n"
            "회의 중 발언·대화 내용·결정사항·요약처럼 회의가 시작돼야 알 수 있는 정보를 물을 때만 "
            "'아직 시작되지 않은 회의라 해당 정보가 없습니다'라고 답변하세요."
        ),
        "ongoing": (
            "이 회의는 현재 진행 중입니다.\n"
            "확정 회의록은 회의 종료 후 확인 가능하다고 안내하세요.\n"
            "일정·참석자·안건 정보는 아래 데이터를 참고해 답변할 수 있습니다.\n"
            "실시간 요약 블록이 있으면 그것을 바탕으로 '지금까지의 내용'을 답변할 수 있습니다."
        ),
        "ended": (
            "이 회의는 종료됐지만 확정 회의록이 아직 생성되지 않았습니다.\n"
            "아래에 [실시간 요약 블록]이 있으면 그것을 바탕으로 회의 내용을 부분적으로 답변할 수 있습니다.\n"
            "요약 블록도 없는 경우에는 '확정 회의록이 아직 생성되지 않아 정확한 내용을 확인하기 어렵습니다'라고 안내하세요.\n"
            "일정·참석자·안건 정보는 아래 데이터를 참고해 답변할 수 있습니다."
        ),
        "archived": "이 회의는 완료된 회의입니다. 아래 회의록 데이터를 바탕으로 답변하세요.",
    }.get(status, "")

    system_prompt = f"""당신은 [{session.title}] 회의 전용 AI 어시스턴트입니다.
{status_guide}

[답변 형식 — 반드시 지킬 것]
- 항상 "~입니다", "~습니다" 형태의 정중한 문장으로 답하세요.
- "현재까지 논의된 내용은 다음과 같습니다:", "다음과 같습니다:" 같은 불필요한 도입 문구는 쓰지 마세요.
- "추가 질문이 있으시면 말씀해 주세요", "도움이 필요하시면 언제든지 말씀해 주세요" 같은 마무리 문장은 절대 쓰지 마세요.
- 회의 내용 요약 시 핵심 결정사항·액션아이템만 bullet로 간결하게 정리하세요. 같은 내용 중복 금지.
- 이 회의와 무관한 질문에는 "이 회의와 관련된 질문만 답변할 수 있습니다."라고만 답하세요.
- 회의 관련 질문이지만 데이터가 없는 경우 off-topic으로 처리하지 말고 이유를 설명하세요.

{base_context}"""

    if rag_text:
        system_prompt += f"\n\n[검색된 관련 회의록 내용]\n{rag_text}"

    def _to_messages(history: list) -> list:
        result = []
        for m in (history or [])[-10:]:
            role, content = m.get("role", ""), m.get("content", "") or ""
            if role == "user":
                result.append(HumanMessage(content=content))
            elif role in ("assistant", "agent"):
                result.append(AIMessage(content=content))
        return result

    async def stream():
        messages = (
            [SystemMessage(content=system_prompt)]
            + _to_messages(data.chat_history)
            + [HumanMessage(content=data.message)]
        )
        full_response = ""
        try:
            async for chunk in make_llm(temperature=0.3, streaming=True).astream(messages):
                if chunk.content:
                    full_response += chunk.content
                    yield sse_token(chunk.content)
        finally:
            # 대화 기록 저장
            thread_id = f"sessions-{data.session_id}"
            try:
                db_local = SessionLocal()
                try:
                    db_local.add(models.ChatMessage(
                        thread_id=thread_id,
                        user_id=current_user.id,
                        context_type="sessions",
                        role="user",
                        content=data.message,
                        session_id=data.session_id,
                    ))
                    if full_response:
                        db_local.add(models.ChatMessage(
                            thread_id=thread_id,
                            user_id=current_user.id,
                            context_type="sessions",
                            role="agent",
                            content=full_response,
                            session_id=data.session_id,
                        ))
                    db_local.commit()
                finally:
                    db_local.close()
            except Exception as e:
                logger.warning(f"[session_chat] 대화 기록 저장 실패 (무시): {e}")
            yield sse_done()

    return StreamingResponse(stream(), media_type="text/event-stream")


# ─── 모델 목록 ────────────────────────────────────────────────────────────────
@router.get("/models")
async def list_models(current_user: models.User = Depends(get_current_user)):
    """컴포저에서 선택 가능한 LLM 모델 목록 — pricing.yaml에 단가가 등록된 모델만 노출."""
    return {
        "models": sorted(PRICING.keys()),
        "default": os.environ.get("OPENAI_MODEL", ""),
    }


# ─── Supervisor Chat ──────────────────────────────────────────────────────────
@router.post("/supervisor/chat")
async def supervisor_chat(
    data: schemas.AgentChatRequest,
    background_tasks: BackgroundTasks,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    msg = data.message or ""

    # 사용자 선택 모델 — pricing.yaml에 등록된 모델만 허용 (임의 모델명 차단)
    _model_override = data.model if data.model in PRICING else None
    if _model_override:
        model_override_var.set(_model_override)

    # 서비스 가드 (P3C-1): 일일 토큰 예산(PG 집계 — 비용 상한)
    from core.service_guards import check_daily_token_budget

    check_daily_token_budget(db, current_user.id)

    # ── LLM 라우팅 결정 — 최근 대화 맥락 포함 (AI-9) ────────────────────────────
    _route, _route_thinking, _route_steps = await classify_intent(
        msg, data.chat_history or []
    )

    background_tasks.add_task(
        _log_activity,
        data.meeting_id,
        f"워크메이트[{_route}]",
        "Supervisor 대화",
        f'"{msg[:80]}"',
    )

    user_person_id: str | None = None
    user_allowed_mg_ids: set[str] = set()
    is_admin = (
        current_user.company_role == "SYSTEM_ADMIN"
    )  # RBAC (P1-3) — position 자가신고 판별 제거
    pg_meeting_ids: set[int] = {
        row.meeting_id
        for row in db.query(models.MeetingMember.meeting_id)
        .filter(models.MeetingMember.user_id == current_user.id)
        .all()
    }
    # 회사 관리자는 자사 구성원이 참여한 회의체까지 AI 조회 범위에 포함 (SEC-5/MT)
    if (
        current_user.company_role == "COMPANY_ADMIN"
        and current_user.company_id is not None
    ):
        pg_meeting_ids |= {
            row.meeting_id
            for row in db.query(models.MeetingMember.meeting_id)
            .join(models.User, models.User.id == models.MeetingMember.user_id)
            .filter(models.User.company_id == current_user.company_id)
            .all()
        }
    try:
        p_rows = await run_cypher(
            # 사용자 매칭은 pg_id 단일 키 (email/name 매칭은 동명이인·개명 시 오인 — SEC-12)
            "MATCH (p:User {pg_id: $pg_id}) "
            "RETURN coalesce(p.id, toString(p.pg_id)) AS pid LIMIT 1",
            {"pg_id": current_user.id},
        )
        if p_rows:
            user_person_id = p_rows[0]["pid"]
            mg_access_rows = await run_cypher(
                "MATCH (p:User {id: $pid})-[:`운영`|`참여`]->(mg) "
                "WHERE mg:Meetings OR mg:Meeting_session "
                "RETURN coalesce(mg.id, 'mg-sqlite-' + toString(mg.pg_id)) AS mg_id",
                {"pid": user_person_id},
            )
            user_allowed_mg_ids = {r["mg_id"] for r in mg_access_rows}
    except Exception:
        pass

    _thread_id = (
        data.thread_id
        if data.thread_id
        else (
            f"meeting_{data.meeting_id}"
            if data.meeting_id
            else f"global_{current_user.id}"
        )
    )

    def _save_assistant_msg(text: str) -> None:
        """조기 종료 분기(off_topic·접근거부 등)의 assistant 응답도 chat_messages에 저장한다.
        메인 경로는 stream()의 finally에서 저장하지만, 이 분기들은 그 try에 닿기 전에 return해
        저장이 누락됐다(회의체와 무관한 질문의 답변이 기록되지 않던 원인)."""
        if not text or not text.strip():
            return
        _sdb = SessionLocal()
        try:
            _sdb.add(
                models.ChatMessage(
                    thread_id=_thread_id,
                    user_id=current_user.id,
                    role="assistant",
                    content=text,
                    context_type="supervisor",
                    meeting_id=data.meeting_id or None,
                )
            )
            _sdb.commit()
        except Exception as _e:
            logger.warning(f"[supervisor_chat] assistant(조기응답) 저장 실패: {_e}")
            _sdb.rollback()
        finally:
            _sdb.close()

    async def stream():
        _collector = TokenUsageCollector()
        _tok_ctx_token = _token_collector_var.set(_collector)
        # 제너레이터는 엔드포인트와 다른 컨텍스트에서 iterate될 수 있어 여기서 다시 설정
        _model_ctx_token = (
            model_override_var.set(_model_override) if _model_override else None
        )
        _log_id = _create_log(
            context_type="supervisor",
            meeting_id=data.meeting_id or None,
            session_id=None,
            user_id=current_user.id,
            input_data={
                "message": msg[:300] if msg else None,
                "route": _route,
                "model": _model_override,
            },
        )
        _stream_error = None
        # 멀티테넌트 검색 스코프 — 하위 검색 도구(search_knowledge 등)가 현재 사용자가 볼 수 있는
        # 회의체만 검색하도록 강제(IDOR 방지). meeting_tools가 못 닿는 sub-agent 도구의 공백을 메움.
        from core.agent_scope import set_meeting_scope, reset_meeting_scope

        _scope_token = set_meeting_scope(pg_meeting_ids, is_admin)
        # DB에서 최근 20개 대화 이력 조회 (시간 오름차순)
        _db_rows = (
            db.query(models.ChatMessage)
            .filter(
                models.ChatMessage.thread_id == _thread_id,
                models.ChatMessage.user_id == current_user.id,
            )
            .order_by(models.ChatMessage.created_at.desc())
            .limit(20)
            .all()
        )
        _chat_history_from_db: list[dict] = [
            {"role": m.role, "content": m.content or ""} for m in reversed(_db_rows)
        ]

        neo4j_ctx = {}
        neo4j_ctx_str = ""
        hl_candidates: list[str] = []
        try:
            yield sse_event(
                "run", {"run_id": _thread_id}
            )  # 중단/이어보기용 식별자 (P3A-6)
            if _route_thinking:
                yield sse_event(
                    "planning", _route_thinking
                )  # 라우팅 근거 1줄 (steps 연극 제거, H-13)

            # ── off_topic 조기 종료: 회의체 운영 외 질문 ──────────
            # 고정 문구 대신 LLM이 사용자 질문 맥락에 맞춰 정중히 안내하도록 생성(하드코딩 제거).
            if _route == "off_topic":
                _off_sys = (
                    "당신은 회의체 운영 지원 AI입니다. 사용자의 질문은 회의체 운영(회의체 현황·"
                    "아젠다·회의록·보고서)과 무관합니다. (1) 회의체 운영 전용 비서임을 한 문장으로 "
                    "정중하고 친근하게 안내하고, (2) 사용자의 질문 맥락에 맞춰 도울 수 있는 회의체 "
                    "관련 질문 2가지를 자연스럽게 제안하세요. 짧게, 마크다운·번호기호 없이."
                )
                _off_chunks: list[str] = []
                try:
                    _off_llm = make_llm(temperature=0.5)
                    async for _c in _off_llm.astream(
                        [
                            SystemMessage(content=_off_sys),
                            HumanMessage(content=msg or ""),
                        ]
                    ):
                        _t = (
                            _c.content
                            if isinstance(_c.content, str)
                            else str(_c.content)
                        )
                        if _t:
                            _off_chunks.append(_t)
                            yield sse_token(_t)
                except Exception as _off_err:
                    logger.warning(f"[off_topic] LLM 생성 실패: {_off_err}")
                    _fb = "저는 회의체 운영(현황·아젠다·회의록·보고서) 질문을 도와드려요. 무엇을 도와드릴까요?"
                    _off_chunks = [_fb]
                    yield sse_token(_fb)
                _save_assistant_msg("".join(_off_chunks))
                yield sse_done()
                return
            if data.meeting_id:
                mid_neo4j = to_mg_id(int(data.meeting_id))

                if not is_admin:
                    has_access = (
                        mid_neo4j in user_allowed_mg_ids
                        if user_allowed_mg_ids
                        else int(data.meeting_id) in pg_meeting_ids
                    )
                    if not has_access:
                        yield sse_event(
                            "planning",
                            f"접근 권한 없음 — {current_user.name}님은 이 회의체에 대한 접근 권한이 없습니다",
                        )
                        yield sse_token("이 회의체에 대한 접근 권한이 없습니다.")
                        _save_assistant_msg("이 회의체에 대한 접근 권한이 없습니다.")
                        yield sse_done()
                        return

                neo4j_ctx = await get_meeting_graph_context(data.meeting_id)

                if neo4j_ctx.get("meeting", {}).get("title"):
                    yield sse_event(
                        "planning",
                        f"[{neo4j_ctx['meeting']['title']}] 회의체 정보 확인",
                    )
                if neo4j_ctx.get("agendas"):
                    yield sse_event(
                        "planning", f"아젠다 {len(neo4j_ctx['agendas'])}건 분석"
                    )

                neo4j_ctx_str = graph_context_to_str(neo4j_ctx)

                for ag in neo4j_ctx.get("agendas", []):
                    if ag.get("title"):
                        hl_candidates.append(ag["title"])
                for s in neo4j_ctx.get("recent_sessions", []):
                    if s.get("title"):
                        hl_candidates.append(s["title"])
                if neo4j_ctx.get("meeting", {}).get("title"):
                    hl_candidates.append(neo4j_ctx["meeting"]["title"])
            else:
                try:
                    mg_detail_rows: list[dict] = []
                    if user_person_id:
                        mg_detail_rows = await run_cypher(
                            """MATCH (me:User {id: $pid})-[:`참여`|`운영`]->(mg:Meetings)
                               WITH DISTINCT mg
                               OPTIONAL MATCH (sec:User)-[:`운영`]->(mg)
                               OPTIONAL MATCH (mem:User)-[:`참여`]->(mg)
                               WITH mg,
                                    head(collect(DISTINCT
                                        sec.name + '||' + coalesce(sec.department, '')
                                    )) AS sec_info,
                                    [d IN collect(DISTINCT mem.department)
                                     WHERE d IS NOT NULL AND d <> ''] AS member_depts
                               OPTIONAL MATCH (s:Session)-[:`소속`]->(mg)
                               WITH mg, sec_info, member_depts,
                                    max(s.scheduled_at) AS latest_session_date
                               OPTIONAL MATCH (d:Report)-[:`첨부`]->(mg)
                               RETURN mg.id AS mg_id, mg.title AS title,
                                      coalesce(mg.meeting_type, '') AS meeting_type,
                                      sec_info, member_depts, latest_session_date,
                                      count(DISTINCT d) AS report_count
                               ORDER BY mg.title""",
                            {"pid": user_person_id},
                        )
                    elif is_admin:
                        mg_detail_rows = await run_cypher(
                            """MATCH (mg:Meetings)
                               OPTIONAL MATCH (sec:User)-[:`운영`]->(mg)
                               OPTIONAL MATCH (mem:User)-[:`참여`]->(mg)
                               WITH mg,
                                    head(collect(DISTINCT
                                        sec.name + '||' + coalesce(sec.department, '')
                                    )) AS sec_info,
                                    [d IN collect(DISTINCT mem.department)
                                     WHERE d IS NOT NULL AND d <> ''] AS member_depts
                               OPTIONAL MATCH (s:Session)-[:`소속`]->(mg)
                               WITH mg, sec_info, member_depts,
                                    max(s.scheduled_at) AS latest_session_date
                               OPTIONAL MATCH (d:Report)-[:`첨부`]->(mg)
                               RETURN mg.id AS mg_id, mg.title AS title,
                                      coalesce(mg.meeting_type, '') AS meeting_type,
                                      sec_info, member_depts, latest_session_date,
                                      count(DISTINCT d) AS report_count
                               ORDER BY mg.title LIMIT 20"""
                        )

                    if mg_detail_rows:
                        # mg_id 기준 중복 제거
                        seen_mg_ids: set = set()
                        unique_rows: list[dict] = []
                        for _row in mg_detail_rows:
                            _mid = _row.get("mg_id", "")
                            if _mid and _mid in seen_mg_ids:
                                continue
                            if _mid:
                                seen_mg_ids.add(_mid)
                            unique_rows.append(_row)

                        yield sse_event(
                            "planning", f"소속 회의체 {len(unique_rows)}건 상세 조회"
                        )

                        ctx_lines = ["[소속 회의체 목록]"]
                        for _row in unique_rows:
                            _title = _row.get("title") or "?"
                            _mtype = _row.get("meeting_type") or ""
                            _sec_info = _row.get("sec_info") or ""
                            _depts: list = _row.get("member_depts") or []
                            _latest = _row.get("latest_session_date") or ""
                            _rcount = _row.get("report_count") or 0

                            _type_label = f" — {_mtype}" if _mtype else ""
                            ctx_lines.append(f"\n📋 {_title}{_type_label}")

                            if _sec_info:
                                _parts = _sec_info.split("||", 1)
                                _sec_name = _parts[0].strip()
                                _sec_dept = (
                                    f"({_parts[1].strip()})"
                                    if len(_parts) > 1 and _parts[1].strip()
                                    else ""
                                )
                                ctx_lines.append(
                                    f"  - 간사: {_sec_name} {_sec_dept}".rstrip()
                                )
                            else:
                                ctx_lines.append("  - 간사: 미지정")

                            _unique_depts = list(dict.fromkeys(d for d in _depts if d))
                            ctx_lines.append(
                                f"  - 참여부서: {', '.join(_unique_depts[:8])}"
                                if _unique_depts
                                else "  - 참여부서: 없음"
                            )

                            if _latest:
                                _date_str = str(_latest)[:10].replace("-", ".")
                                ctx_lines.append(f"  - 최근 회의: {_date_str}")
                            else:
                                ctx_lines.append("  - 최근 회의: 없음")

                            ctx_lines.append(f"  - 보고자료: {_rcount}건 제출")

                            if _title not in hl_candidates:
                                hl_candidates.append(_title)

                        neo4j_ctx_str = "\n".join(ctx_lines)

                    else:
                        # PostgreSQL fallback: Neo4j에 데이터 없는 경우
                        _pg_mids = list(pg_meeting_ids)[:20]
                        _pg_meetings = (
                            (
                                db.query(models.Meeting)
                                .filter(models.Meeting.id.in_(_pg_mids))
                                .order_by(models.Meeting.title)
                                .all()
                            )
                            if _pg_mids
                            else []
                        )

                        if _pg_meetings:
                            yield sse_event(
                                "planning", f"소속 회의체 {len(_pg_meetings)}건 조회"
                            )
                            ctx_lines = ["[소속 회의체 목록]"]
                            for _mg in _pg_meetings:
                                _mems = (
                                    db.query(models.MeetingMember)
                                    .filter(models.MeetingMember.meeting_id == _mg.id)
                                    .all()
                                )
                                _user_ids = [m.user_id for m in _mems]
                                _users = {
                                    u.id: u
                                    for u in db.query(models.User)
                                    .filter(models.User.id.in_(_user_ids))
                                    .all()
                                }
                                _admin_mem = next(
                                    (m for m in _mems if m.meeting_role == "admin"),
                                    None,
                                )
                                _sec = (
                                    _users.get(_admin_mem.user_id)
                                    if _admin_mem
                                    else None
                                )
                                _depts = list(
                                    dict.fromkeys(
                                        _users[m.user_id].department
                                        for m in _mems
                                        if m.user_id in _users
                                        and _users[m.user_id].department
                                    )
                                )
                                _sessions = (
                                    db.query(models.MeetingSession)
                                    .filter(
                                        models.MeetingSession.meeting_id == _mg.id,
                                    )
                                    .order_by(models.MeetingSession.scheduled_at.desc())
                                    .limit(5)
                                    .all()
                                )
                                _rcount = (
                                    db.query(models.Report)
                                    .filter(models.Report.meeting_id == _mg.id)
                                    .count()
                                )
                                _status_ko_map = {
                                    "scheduled": "예정됨", "ongoing": "진행 중",
                                    "ended": "종료됨", "archived": "완료",
                                }
                                _type_label = f" — {_mg.type}" if _mg.type else ""
                                ctx_lines.append(f"\n📋 {_mg.title}{_type_label}")
                                if _sec:
                                    _sec_dept = (
                                        f"({_sec.department})"
                                        if _sec.department
                                        else ""
                                    )
                                    ctx_lines.append(
                                        f"  - 간사: {_sec.name} {_sec_dept}".rstrip()
                                    )
                                else:
                                    ctx_lines.append("  - 간사: 미지정")
                                ctx_lines.append(
                                    f"  - 참여부서: {', '.join(_depts[:8])}"
                                    if _depts
                                    else "  - 참여부서: 없음"
                                )
                                if _sessions:
                                    ctx_lines.append("  - 회의 목록:")
                                    for _s in _sessions:
                                        _s_status = _status_ko_map.get(_s.status, _s.status)
                                        _s_date = (
                                            _s.scheduled_at.strftime("%Y.%m.%d")
                                            if _s.scheduled_at else "일정 미정"
                                        )
                                        ctx_lines.append(
                                            f"    · {_s.title} ({_s_date}, {_s_status})"
                                        )
                                else:
                                    ctx_lines.append("  - 예정된 회의가 없습니다")
                                ctx_lines.append(f"  - 보고자료: {_rcount}건 제출")
                                if _mg.title not in hl_candidates:
                                    hl_candidates.append(_mg.title)
                            neo4j_ctx_str = "\n".join(ctx_lines)
                        else:
                            org_rows = await run_cypher(
                                "MATCH (org:Company) RETURN org.name AS name LIMIT 1"
                            )
                            if org_rows:
                                yield sse_event(
                                    "planning",
                                    f"조직: {org_rows[0].get('name', '?')} 확인",
                                )
                except Exception:
                    pass

        except Exception as _outer_e:
            yield sse_event("planning", "지식 그래프 조회 중 오류 발생")

        _user_scope_header = (
            f"[현재 사용자] {current_user.name}"
            + (f" / {current_user.position}" if current_user.position else "")
            + (f" / {current_user.department}" if current_user.department else "")
            + "\n[데이터 접근 범위] 본인이 소속된 회의체의 정보만 제공합니다. "
            "다른 사용자 또는 비소속 회의체의 민감 정보는 노출하지 마세요.\n"
        )

        # 내가 참석자로 등록된 예정·진행 중 세션 목록 (SessionMember 우선, MeetingMember 폴백)
        _upcoming_ctx = ""
        try:
            _status_ko = {"scheduled": "예정됨", "ongoing": "진행 중"}
            _upcoming = (
                db.query(models.MeetingSession, models.Meeting.title)
                .join(models.SessionMember, models.SessionMember.session_id == models.MeetingSession.id)
                .join(models.Meeting, models.Meeting.id == models.MeetingSession.meeting_id)
                .filter(
                    models.SessionMember.user_id == current_user.id,
                    models.MeetingSession.status.in_(["scheduled", "ongoing"]),
                )
                .order_by(models.MeetingSession.scheduled_at)
                .limit(10)
                .all()
            )
            # SessionMember 결과 없으면 MeetingMember 기반으로 폴백
            if not _upcoming and pg_meeting_ids:
                _upcoming = (
                    db.query(models.MeetingSession, models.Meeting.title)
                    .join(models.Meeting, models.Meeting.id == models.MeetingSession.meeting_id)
                    .filter(
                        models.MeetingSession.meeting_id.in_(list(pg_meeting_ids)),
                        models.MeetingSession.status.in_(["scheduled", "ongoing"]),
                    )
                    .order_by(models.MeetingSession.scheduled_at)
                    .limit(10)
                    .all()
                )
            if _upcoming:
                _lines = ["[내 예정·진행 중 회의]"]
                for _s, _ in _upcoming:
                    _date = (
                        _s.scheduled_at.strftime("%Y.%m.%d %H:%M")
                        if _s.scheduled_at else "일정 미정"
                    )
                    _lines.append(
                        f"  - 제목: {_s.title} / 일시: {_date}"
                        + (f" / 장소: {_s.location}" if _s.location else "")
                        + f" / 상태: {_status_ko.get(_s.status, _s.status)}"
                    )
                _upcoming_ctx = "\n".join(_lines)
            else:
                _upcoming_ctx = "[내 예정·진행 중 회의]\n  예정된 회의가 없습니다."
        except Exception as _ue:
            logger.warning(f"[upcoming_ctx] 조회 실패: {_ue}")
            _upcoming_ctx = "[내 예정·진행 중 회의]\n  예정된 회의가 없습니다."

        def _enrich(base_ctx: str) -> str:
            parts = [_user_scope_header, base_ctx]
            if _upcoming_ctx:
                parts.append(_upcoming_ctx)
            if neo4j_ctx_str and neo4j_ctx_str != "(Neo4j 데이터 없음)":
                parts.append(f"[Neo4j 그래프 컨텍스트]\n{neo4j_ctx_str}")
            return "\n\n".join(parts)

        # ── 라우팅 공통: assistant 응답 수집 (finally에서 저장) ─────────────
        _assistant_chunks: list[str] = []

        try:
            # ── B 유형: 현황 조회 / 지식 베이스 / 인사 / 일반 질문 ──────────

            if _route in ("supervisor_direct", "knowledge_manager"):
                # ── 일정 조회 fast path: Neo4j 도구 없이 DB 데이터로 직접 답변 ──
                _SCHEDULE_KEYWORDS = ["일정", "곧 시작", "예정된 회의", "다음 회의", "언제 있", "회의 있어", "회의있어", "회의 언제"]
                _is_schedule_query = any(kw in msg for kw in _SCHEDULE_KEYWORDS)
                if _is_schedule_query and _upcoming_ctx:
                    _now_str = datetime.now().strftime("%Y년 %m월 %d일 %H:%M")
                    _sched_system = (
                        f"현재 시각: {_now_str}\n\n"
                        "당신은 회의 일정 안내 어시스턴트입니다.\n"
                        "아래 [내 예정·진행 중 회의] 데이터와 현재 시각을 바탕으로 질문에 맞게 답하세요.\n"
                        "- '곧 시작하는' → 2시간 이내 시작 예정인 회의\n"
                        "- '오늘' → 오늘 날짜 기준\n"
                        "- '이번 주' → 이번 주 월~일 기준\n\n"
                        "출력 형식 (회의마다):\n"
                        "IT 인프라 개선 위원회\n"
                        "6/17 13:30 SK U타워\n"
                        "예정되어 있습니다.\n\n"
                        "규칙:\n"
                        "- 데이터의 '제목' 필드를 그대로 회의명으로 쓰세요. '회의명'이라는 단어를 쓰지 마세요.\n"
                        "- 조건에 해당하는 회의가 없으면 없다고 명확히 말하고, 가장 가까운 다음 회의를 안내하세요.\n"
                        "- 여러 개면 빠른 것부터 순서대로 나열하세요.\n"
                        "- 도입 문구나 마무리 인사 없이 바로 답하세요.\n\n"
                        + _upcoming_ctx
                    )
                    _sched_msgs = [SystemMessage(content=_sched_system), HumanMessage(content=msg)]
                    async for _chunk in make_llm(temperature=0.2, streaming=True).astream(_sched_msgs):
                        if _chunk.content:
                            _assistant_chunks.append(_chunk.content)
                            yield sse_token(_chunk.content)
                    yield sse_done()
                    return

                # 도구 기반 JIT 에이전트 (P3A-5/P3B-2) — 사전조립 컨텍스트 경로는 제거됨.
                # 스코프는 tools가 RunnableConfig 기준으로 강제, 진행표시는 실제 도구 이벤트에서 파생.
                from graphs.supervisor_graph import direct_agent_stream

                async for _kind, _text in direct_agent_stream(
                    msg,
                    _to_base_messages(_chat_history_from_db),
                    user_id=current_user.id,
                    allowed_meeting_ids=list(pg_meeting_ids),
                    is_admin=is_admin,
                    meeting_id=data.meeting_id or None,
                    upcoming_ctx=_upcoming_ctx,
                    thread_id=_thread_id,
                ):
                    if _kind == "planning":
                        yield sse_event("planning", _text)
                    elif _kind == "action":
                        # 쓰기 제안 → 프런트 확인 카드. 실제 실행은 사용자 확인 후 기존 엔드포인트로.
                        try:
                            yield sse_event("action_confirm", json.loads(_text))
                        except Exception:
                            pass
                    else:
                        _assistant_chunks.append(_text)  # finally에서 DB 저장 (P3B-3)
                        yield sse_token(_text)
                yield sse_done()
                return

            if _route == "task_extractor":
                _org_dept_pairs = _get_member_org_depts(db, data.meeting_id)
                _org_dept_list = (
                    "\n".join(
                        f"- {p['company']} / {p['department']}"
                        if p.get("company")
                        else f"- {p['department']}"
                        for p in _org_dept_pairs
                    )
                    if _org_dept_pairs
                    else "정보 없음"
                )
                gen = task_agent.chat_stream(
                    message=msg,
                    chat_history=_chat_history_from_db,
                    previous_minutes=_get_previous_minutes(db, data.meeting_id),
                    knowledge=[],
                    org_dept_list=_org_dept_list,
                    meeting_context=_enrich(_get_meeting_context(db, data.meeting_id)),
                )
            elif _route == "minutes_generator":
                agendas = (
                    db.query(models.Agenda)
                    .filter(
                        models.Agenda.meeting_id == data.meeting_id,
                        models.Agenda.status.in_(["ON_HOLD", "IN_PROGRESS"]),
                    )
                    .all()
                )
                gen = minutes_agent.chat_stream(
                    message=msg,
                    chat_history=_chat_history_from_db,
                    previous_minutes=_get_previous_minutes(db, data.meeting_id),
                    current_agendas=[
                        {"content": a.title, "status": a.status} for a in agendas
                    ],
                    meeting_context=_enrich(_get_meeting_context(db, data.meeting_id)),
                )
            else:  # report_reviewer
                gen = report_agent.chat_stream(
                    message=msg,
                    chat_history=_chat_history_from_db,
                    knowledge=[],
                    meeting_context=_enrich(_get_meeting_context(db, data.meeting_id)),
                )

            async for chunk in gen:
                _assistant_chunks.append(chunk)
                yield sse_token(chunk)

            if hl_candidates and _assistant_chunks:
                full_text = "".join(_assistant_chunks)
                matched = [c for c in hl_candidates if c and c in full_text]
                if matched:
                    yield sse_event("highlight", matched)

            yield sse_done()

        except BaseException as _e:
            _stream_error = _e
            raise
        finally:
            # GeneratorExit·예외·정상 종료 모두에서 assistant 메시지 저장
            _token_collector_var.reset(_tok_ctx_token)
            reset_meeting_scope(_scope_token)
            if _model_ctx_token is not None:
                model_override_var.reset(_model_ctx_token)
            _finalize(_log_id, _collector, _stream_error, None)
            # chunk.content가 문자열이 아닌(리스트 등) 경우 "".join이 TypeError로 깨져 저장이 통째로
            # 실패하던 문제 방지 — 모든 조각을 str로 강제 변환 후 결합한다.
            _assistant_text = "".join(
                c if isinstance(c, str) else str(c) for c in _assistant_chunks
            )
            if _assistant_text.strip():
                _save_db = SessionLocal()
                try:
                    _save_db.add(
                        models.ChatMessage(
                            thread_id=_thread_id,
                            user_id=current_user.id,
                            role="assistant",
                            content=_assistant_text,
                            context_type="supervisor",
                            meeting_id=data.meeting_id or None,
                        )
                    )
                    _save_db.commit()
                except Exception as _e:
                    logger.warning(f"[supervisor_chat] AI 응답 저장 실패: {_e}")
                    _save_db.rollback()
                finally:
                    _save_db.close()

    # 사용자 메시지 저장
    if msg:
        try:
            db.add(
                models.ChatMessage(
                    thread_id=_thread_id,
                    user_id=current_user.id,
                    role="user",
                    content=msg,
                    context_type="supervisor",
                    meeting_id=data.meeting_id or None,
                )
            )
            db.commit()
        except Exception as _e:
            logger.warning(f"[supervisor_chat] 사용자 메시지 저장 실패: {_e}")
            db.rollback()

    return StreamingResponse(
        instrument_stream(stream(), "supervisor_chat"), media_type="text/event-stream"
    )  # TTFT 측정 (P5-1)


# ─── Supervisor Chat 히스토리 조회 ───────────────────────────────────────────
# ─── 응답 피드백 (P3C-3, H-9) ────────────────────────────────────────────────
class FeedbackRequest(BaseModel):
    thread_id: str
    rating: int  # 1=up / -1=down
    reason: Optional[str] = None
    message_id: Optional[int] = None
    content_snippet: Optional[str] = None


@router.post("/feedback")
async def submit_feedback(
    data: FeedbackRequest,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """응답 수집"""
    if data.rating not in (1, -1):
        from fastapi import HTTPException

        raise HTTPException(status_code=400, detail="rating은 1 또는 -1이어야 합니다.")
    fb = models.ChatFeedback(
        user_id=current_user.id,
        thread_id=data.thread_id,
        message_id=data.message_id,
        rating=data.rating,
        reason=(data.reason or "")[:1000] or None,
        content_snippet=(data.content_snippet or "")[:500] or None,
    )
    db.add(fb)
    db.commit()
    return {"ok": True, "id": fb.id}


@router.get("/supervisor/chat/history")
async def supervisor_chat_history(
    meeting_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    is_admin = (
        current_user.company_role == "SYSTEM_ADMIN"
    )  # RBAC (P1-3) — position 자가신고 판별 제거
    if not is_admin:
        member = (
            db.query(models.MeetingMember)
            .filter(
                models.MeetingMember.meeting_id == meeting_id,
                models.MeetingMember.user_id == current_user.id,
            )
            .first()
        )
        if not member:
            from fastapi import HTTPException

            raise HTTPException(
                status_code=403, detail="이 회의체에 대한 접근 권한이 없습니다."
            )

    messages = (
        db.query(models.ChatMessage)
        .filter(
            models.ChatMessage.meeting_id == meeting_id,
            models.ChatMessage.context_type == "supervisor",
        )
        .order_by(models.ChatMessage.created_at.asc())
        .all()
    )
    return [
        {
            "id": m.id,
            "role": m.role,
            "content": m.content,
            "user_id": m.user_id,
            "created_at": m.created_at.isoformat() if m.created_at else None,
        }
        for m in messages
    ]
