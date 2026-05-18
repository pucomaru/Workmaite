import os
from typing import List
from fastapi import APIRouter, Depends, UploadFile, File, Form, BackgroundTasks
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
import models, schemas
from database import get_db, SessionLocal
from auth import get_current_user
from agents import gaon, naru, ara, naon, hyean
from datetime import datetime

router = APIRouter(prefix="/api/agent", tags=["agents"])


def _log_activity(meeting_id: int, agent: str, action: str, detail: str = ""):
    """백그라운드에서 ActivityMemory에 활동 기록 append."""
    if not meeting_id:
        return
    from routers.tacit_knowledge import append_activity_log
    db = SessionLocal()
    try:
        append_activity_log(db, meeting_id, agent, action, detail)
    except Exception as e:
        print(f"[ActivityLog Error] {e}")
    finally:
        db.close()


def _get_knowledge(db: Session, meeting_id: int = None) -> List[dict]:
    global_kb = db.query(models.TacitKnowledgeGlobal).filter(
        models.TacitKnowledgeGlobal.status == "active"
    ).all()
    meeting_kb = []
    if meeting_id:
        meeting_kb = db.query(models.TacitKnowledgeMeeting).filter(
            models.TacitKnowledgeMeeting.meeting_id == meeting_id,
            models.TacitKnowledgeMeeting.status == "active",
        ).all()
    return [
        {"category": k.category, "title": k.title, "content": k.content}
        for k in list(global_kb) + list(meeting_kb)
    ]


def _get_meeting_context(db: Session, meeting_id: int) -> str:
    """회의체 기본 맥락 문자열 구성 — Supervisor 패턴으로 서브에이전트에 주입."""
    if not meeting_id:
        return ""
    meeting = db.query(models.Meeting).filter(models.Meeting.id == meeting_id).first()
    if not meeting:
        return ""
    lines = [f"회의체 이름: {meeting.title}"]
    if meeting.purpose:
        lines.append(f"회의 목적: {meeting.purpose}")
    members = db.query(models.MeetingMember).filter(
        models.MeetingMember.meeting_id == meeting_id
    ).all()
    if members:
        member_parts = []
        for m in members:
            user = db.query(models.User).filter(models.User.id == m.user_id).first()
            if user:
                role_label = "운영자" if m.role == "admin" else "발제자"
                dept = user.department or ""
                member_parts.append(f"{user.name}({dept}, {role_label})")
        if member_parts:
            lines.append(f"참여자: {', '.join(member_parts)}")
    return "\n".join(lines)


# ─── 가온 Agent ───────────────────────────────
@router.post("/gaon/chat")
async def gaon_chat(
    data: schemas.AgentChatRequest,
    background_tasks: BackgroundTasks,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    knowledge = _get_knowledge(db, data.meeting_id)
    previous_minutes = _get_previous_minutes(db, data.meeting_id)
    departments = _get_member_departments(db, data.meeting_id)
    meeting_context = _get_meeting_context(db, data.meeting_id)
    background_tasks.add_task(_log_activity, data.meeting_id, "가온", "아젠다/과제 대화", f'"{data.message[:80]}"')

    async def stream():
        async for chunk in gaon.chat_stream(
            message=data.message,
            chat_history=data.chat_history or [],
            previous_minutes=previous_minutes,
            knowledge=knowledge,
            departments=departments,
            meeting_context=meeting_context,
        ):
            yield f"data: {chunk.replace(chr(10), chr(92)+chr(110))}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream")


@router.post("/gaon/extract-agenda")
async def extract_agenda(
    meeting_id: int = Form(...),
    file: UploadFile = File(None),
    chat_history: str = Form("[]"),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    file_content = ""
    if file:
        raw = await file.read()
        fname = (file.filename or "").lower()
        file_content = _extract_text_from_file(raw, fname)

    if not file_content.strip():
        return {"agendas": [], "todos": [], "error": "파일에서 텍스트를 추출할 수 없습니다."}

    previous_minutes = _get_previous_minutes(db, meeting_id)
    knowledge = _get_knowledge(db, meeting_id)
    departments = _get_member_departments(db, meeting_id)

    result = await gaon.extract_agendas_and_todos(
        content=file_content,
        previous_minutes=previous_minutes,
        knowledge=knowledge,
        departments=departments,
    )

    # 저장하지 않고 추출 결과만 반환 — 프론트에서 사용자 승인 후 저장
    agendas_out = [
        {"department": a.get("department"), "content": a.get("content", "")}
        for a in result.get("agendas", []) if a.get("content", "").strip()
    ]
    todos_out = [
        {k: v for k, v in t.items()}
        for t in result.get("todos", []) if t.get("content", "").strip()
    ]
    return {"agendas": agendas_out, "todos": todos_out}


@router.post("/gaon/extract-from-text")
async def extract_from_text(
    data: dict,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """채팅 응답 텍스트에서 JSON을 직접 파싱해 저장. LLM 재호출 없음."""
    meeting_id = data.get("meeting_id")
    text = data.get("text", "")
    if not meeting_id or not text:
        return {"agendas": [], "todos": []}

    parsed = gaon._parse_json_from_text(text)
    if not parsed:
        return {"agendas": [], "todos": []}

    if isinstance(parsed, list):
        result = {"agendas": parsed, "todos": []}
    else:
        result = {
            "agendas": parsed.get("agendas", []),
            "todos": parsed.get("todos", []),
        }

    saved_agendas, saved_todos = _save_extracted(db, meeting_id, result)
    if saved_agendas or saved_todos:
        _log_activity(meeting_id, "가온", "응답에서 아젠다/과제 추출",
            f"아젠다 {len(saved_agendas)}개 / 과제 {len(saved_todos)}개")
    return {"agendas": saved_agendas, "todos": saved_todos}


# ─── 나루 Agent ───────────────────────────────
@router.post("/naru/chat")
async def naru_chat(
    data: schemas.AgentChatRequest,
    background_tasks: BackgroundTasks,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    knowledge = _get_knowledge(db, data.meeting_id)
    meeting_context = _get_meeting_context(db, data.meeting_id)
    background_tasks.add_task(_log_activity, data.meeting_id, "나루", "보고서 검토 대화", f'"{data.message[:80]}"')

    async def stream():
        async for chunk in naru.chat_stream(
            message=data.message,
            chat_history=data.chat_history or [],
            knowledge=knowledge,
            meeting_context=meeting_context,
        ):
            yield f"data: {chunk.replace(chr(10), chr(92)+chr(110))}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream")


@router.post("/naru/global-review")
async def global_review(
    data: schemas.AgentChatRequest,
    background_tasks: BackgroundTasks,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    from sqlalchemy.orm import joinedload
    reports = (
        db.query(models.Report)
        .options(joinedload(models.Report.presenter))
        .filter(models.Report.meeting_id == data.meeting_id)
        .all()
    )
    reports_info = [
        {
            "presenter_name": r.presenter.name if r.presenter else "Unknown",
            "file_name": r.file_name or "",
            "status": r.status,
        }
        for r in reports
    ]
    knowledge = _get_knowledge(db, data.meeting_id)
    meeting_context = _get_meeting_context(db, data.meeting_id)
    background_tasks.add_task(_log_activity, data.meeting_id, "나루", "전체 보고서 종합 검토",
        f"보고서 {len(reports_info)}개 검토 요청")

    async def stream():
        async for chunk in naru.global_review_stream(
            reports_info=reports_info,
            chat_history=data.chat_history or [],
            knowledge=knowledge,
            meeting_context=meeting_context,
        ):
            yield f"data: {chunk.replace(chr(10), chr(92)+chr(110))}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream")


# ─── 보고서 검토 Agent ────────────────────────
@router.post("/report-review")
async def report_review(
    data: schemas.ReportReviewRequest,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    knowledge = _get_knowledge(db)
    result = await naru.review_report(
        report_content=data.report_content,
        agenda=data.agenda or "",
        knowledge=knowledge,
    )
    return result


# ─── 아라 Agent ───────────────────────────────
@router.post("/ara/chat")
async def ara_chat(
    data: schemas.AgentChatRequest,
    background_tasks: BackgroundTasks,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    previous_minutes = _get_previous_minutes(db, data.meeting_id)
    agendas = db.query(models.Agenda).filter(
        models.Agenda.meeting_id == data.meeting_id,
        models.Agenda.status == "confirmed",
    ).all()
    agendas_list = [{'content': a.content, 'department': a.department} for a in agendas]
    meeting_context = _get_meeting_context(db, data.meeting_id)
    background_tasks.add_task(_log_activity, data.meeting_id, "아라", "회의 진행 대화", f'"{data.message[:80]}"')

    async def stream():
        async for chunk in ara.chat_stream(
            message=data.message,
            chat_history=data.chat_history or [],
            previous_minutes=previous_minutes,
            current_agendas=agendas_list,
            meeting_context=meeting_context,
        ):
            yield f"data: {chunk.replace(chr(10), chr(92)+chr(110))}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream")


@router.post("/ara/sessions-chat")
async def ara_sessions_chat(
    data: schemas.AgentChatRequest,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """회의 탭 전용 아라: 전체/특정 세션 요약·질의응답."""
    # 전체 세션 목록 + 회의록 수집
    sessions = (
        db.query(models.MeetingSession)
        .filter(models.MeetingSession.meeting_id == data.meeting_id)
        .order_by(models.MeetingSession.id.desc())
        .all()
    )
    sessions_info = []
    for s in sessions:
        info = {
            "id": s.id,
            "title": s.title,
            "status": s.status,
            "summary": s.minutes.content_summary if s.minutes and s.minutes.content_summary else None,
        }
        sessions_info.append(info)

    agendas = db.query(models.Agenda).filter(
        models.Agenda.meeting_id == data.meeting_id,
        models.Agenda.status == "confirmed",
    ).all()
    agendas_list = [{"content": a.content, "department": a.department} for a in agendas]

    # 세션 요약들을 previous_minutes 형태로 전달
    session_summaries = [
        f"[{s['title']}] {s['summary']}"
        for s in sessions_info if s["summary"]
    ]
    # 세션 목록 컨텍스트 (요약 없는 것 포함)
    session_list_text = "\n".join([
        f"- {s['title']} ({s['status']})" + (f": 요약 있음" if s['summary'] else ": 요약 없음")
        for s in sessions_info
    ])
    extra_context = f"[회의 세션 목록]\n{session_list_text}"
    if session_summaries:
        extra_context += f"\n\n[세션별 회의록]\n" + "\n\n".join(session_summaries)

    async def stream():
        async for chunk in ara.chat_stream(
            message=data.message,
            chat_history=data.chat_history or [],
            previous_minutes=[extra_context],
            current_agendas=agendas_list,
            meeting_context=_get_meeting_context(db, data.meeting_id),
        ):
            yield f"data: {chunk.replace(chr(10), chr(92)+chr(110))}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream")

import uuid as _uuid

# ─── 나온 Agent (LangGraph Human-in-the-Loop) ───────────────────

@router.post("/naon/chat")
async def naon_chat(
    data: schemas.AgentChatRequest,
    background_tasks: BackgroundTasks,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """나온과의 자유 대화 (스트리밍). 기획 요구사항 파악 단계."""
    meeting_context = _get_meeting_context(db, data.meeting_id)
    background_tasks.add_task(_log_activity, data.meeting_id, "나온", "카드뉴스 기획 대화", f'"{data.message[:80]}"')

    async def stream():
        async for chunk in naon.chat_stream(
            message=data.message,
            chat_history=data.chat_history or [],
            meeting_context=meeting_context,
        ):
            yield f"data: {chunk.replace(chr(10), chr(92)+chr(110))}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream")


@router.post("/naon/extract-params")
async def naon_extract_params(
    data: schemas.CardNewsExtractRequest,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """대화 기록에서 카드뉴스 파라미터(회의차수·대상·소스)를 자동 추출합니다."""
    result = await naon.extract_params_from_chat(
        chat_history=data.chat_history,
        available_sessions=data.available_sessions,
    )
    return result


@router.post("/naon/propose-plan")
async def naon_propose_plan(
    data: schemas.CardNewsPlanRequest,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    [LangGraph HITL Step 1]
    propose_node 를 실행하고 interrupt() 지점에서 그래프를 일시 정지한다.
    회의록뿐 아니라 보고서·아젠다·To-do·의사결정 등 미팅 전체 자료를 취합하여 전달한다.
    """
    meeting = db.query(models.Meeting).filter(models.Meeting.id == data.meeting_id).first()

    # ── 소스 수집 ───────────────────────────────────────────────
    source_chunks: list[str] = []

    # 1. 회의록 (session별)
    if data.include_minutes is not False:
        for sid in data.session_ids:
            m = db.query(models.Minutes).filter(models.Minutes.session_id == sid).first()
            if m:
                session_obj = db.query(models.MeetingSession).filter(models.MeetingSession.id == sid).first()
                label = f"【{session_obj.session_number}차 회의록】" if session_obj else "【회의록】"
                if m.content_summary:
                    source_chunks.append(f"{label}\n{m.content_summary}")
                # 의사결정 사항
                if data.include_decisions is not False and m.decisions_json:
                    decisions = "\n".join(f"- {d.get('content','')}" for d in m.decisions_json if d.get('content'))
                    if decisions:
                        source_chunks.append(f"【의사결정 사항】\n{decisions}")
                # Action Items
                if m.action_items_json:
                    actions = "\n".join(f"- {a.get('content','')} (담당: {a.get('assignee','')})" for a in m.action_items_json if a.get('content'))
                    if actions:
                        source_chunks.append(f"【Action Items】\n{actions}")

    # 2. 보고서 (approved된 것 우선)
    if data.include_reports is not False:
        reports = db.query(models.Report).filter(
            models.Report.meeting_id == data.meeting_id,
            models.Report.status.in_(["approved", "submitted"]),
        ).order_by(models.Report.submitted_at.desc()).limit(5).all()
        for r in reports:
            parts = [f"【보고서: {r.file_name or '첨부 자료'}】"]
            if r.feedback:
                fb = r.feedback if isinstance(r.feedback, list) else [r.feedback]
                parts.append("피드백: " + " / ".join(str(f) for f in fb[:3]))
            if r.review_comment:
                parts.append(f"검토 의견: {r.review_comment}")
            source_chunks.append("\n".join(parts))

    # 3. 아젠다 (confirmed)
    if data.include_agendas is not False:
        agendas = db.query(models.Agenda).filter(
            models.Agenda.meeting_id == data.meeting_id,
            models.Agenda.status == "confirmed",
        ).order_by(models.Agenda.order_num).all()
        if agendas:
            agenda_lines = "\n".join(
                f"- [{a.agenda_type or 'draft'}] {a.content}" + (f" (발표: {a.presenter_name})" if a.presenter_name else "")
                for a in agendas
            )
            source_chunks.append(f"【확정 아젠다】\n{agenda_lines}")

    # 4. To-do (done + at_risk 포함 전체)
    if data.include_todos is not False:
        todos = db.query(models.Todo).filter(
            models.Todo.meeting_id == data.meeting_id,
        ).order_by(models.Todo.created_at).all()
        if todos:
            todo_lines = "\n".join(
                f"- [{t.status}] {t.content}" + (f" (담당: {t.assignee_name})" if t.assignee_name else "")
                for t in todos
            )
            source_chunks.append(f"【To-do 목록】\n{todo_lines}")

    thread_id = data.thread_id or str(_uuid.uuid4())
    style_hints = {
        "slide_count": data.slide_count,
        "first_card": data.first_card,
        "tone": data.tone,
        "visual_style": data.visual_style,
        "include_cta": data.include_cta,
        "include_source_date": data.include_source_date,
        "include_brand_logo": data.include_brand_logo,
        "custom_request": data.custom_request,
    }
    result = await naon.start_proposal(
        thread_id=thread_id,
        chat_history=data.chat_history or [],
        sources=source_chunks,
        meeting_title=meeting.title if meeting else "",
        target_audience=data.target_audience or "staff",
        style_hints=style_hints,
    )
    return {**result, "thread_id": thread_id}


@router.post("/naon/resume-plan")
async def naon_resume_plan(
    data: schemas.CardNewsResumeRequest,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    [LangGraph HITL Step 2]
    interrupt() 로 멈춰 있는 그래프를 Command(resume=...) 로 재개한다.
    - approved=True  → generate_node 실행 → 카드뉴스 DB 저장 후 반환
    - approved=False → 그래프 종료 (프론트는 대화로 복귀)
    """
    result = await naon.resume_proposal(
        thread_id=data.thread_id,
        approved=data.approved,
        feedback=data.feedback,
    )

    if data.approved and result.get("card_news"):
        content = result["card_news"]
        card = models.CardNews(
            meeting_id=data.meeting_id,
            session_ids=data.session_ids,
            title=content.get("title", ""),
            content=content,
        )
        db.add(card)
        db.commit()
        db.refresh(card)
        return {**result, "card_news_id": card.id}

    return result


@router.post("/naon/generate-card-news")
async def generate_card_news(
    data: schemas.CardNewsGenerateRequest,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """레거시 호환 엔드포인트 (기존 flow 유지)."""
    minutes_list = []
    for sid in data.session_ids:
        m = db.query(models.Minutes).filter(models.Minutes.session_id == sid).first()
        if m and m.content_summary:
            minutes_list.append(m.content_summary)

    meeting = db.query(models.Meeting).filter(models.Meeting.id == data.meeting_id).first()
    content = await naon.generate_card_news(
        plan=data.plan,
        minutes_list=minutes_list,
        emphasis_points=data.emphasis_points or "",
        meeting_title=meeting.title if meeting else "",
        chat_history=data.chat_history or [],
    )

    card = models.CardNews(
        meeting_id=data.meeting_id,
        session_ids=data.session_ids,
        title=content.get("title", ""),
        content=content,
    )
    db.add(card)
    db.commit()
    db.refresh(card)
    return {"card_news_id": card.id, "content": content}


# ─── 혜안 Agent ───────────────────────────────
@router.get("/hyean/status-cache/{meeting_id}")
async def hyean_status_cache(
    meeting_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """저장된 현황 요약 반환. 없으면 null."""
    cache = db.query(models.MeetingStatusCache).filter(
        models.MeetingStatusCache.meeting_id == meeting_id
    ).first()
    if not cache:
        return {"content": None, "generated_at": None}
    return {"content": cache.content, "generated_at": cache.generated_at}


@router.post("/hyean/status-cache/{meeting_id}")
async def hyean_save_status_cache(
    meeting_id: int,
    data: dict,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """현황 요약 텍스트를 DB에 저장(upsert)."""
    content = data.get("content", "").strip()
    if not content:
        return {"ok": False}
    cache = db.query(models.MeetingStatusCache).filter(
        models.MeetingStatusCache.meeting_id == meeting_id
    ).first()
    if cache:
        cache.content = content
        cache.generated_at = datetime.utcnow()
    else:
        cache = models.MeetingStatusCache(meeting_id=meeting_id, content=content)
        db.add(cache)
    db.commit()
    return {"ok": True}


@router.post("/hyean/status")
async def hyean_status(
    data: schemas.HyeanStatusRequest,
    background_tasks: BackgroundTasks,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    meeting_status = _build_meeting_status(db, data.meeting_id)
    knowledge = _get_knowledge(db, data.meeting_id)
    background_tasks.add_task(_log_activity, data.meeting_id, "혜안", "회의 현황 분석 요청", "")

    async def stream():
        async for chunk in hyean.status_stream(
            meeting_status=meeting_status,
            user_role=data.user_role,
            active_knowledge=knowledge,
            user_name=current_user.name,
        ):
            yield f"data: {chunk.replace(chr(10), chr(92)+chr(110))}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream")


@router.post("/supervisor/chat")
async def supervisor_chat(
    data: schemas.AgentChatRequest,
    background_tasks: BackgroundTasks,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """워크메이트 Supervisor — 사용자 메시지를 분석해 적절한 서브에이전트에 투명하게 위임."""
    msg = data.message or ""
    msg_lower = msg.lower()

    # ── 인텐트 분류 (키워드 기반, 추후 LLM 분류로 교체 가능) ──────────────
    if any(kw in msg_lower for kw in [
        '아젠다', '의제', '과제', '할 일', '할일', '투두', 'todo', 'agenda',
        '추출', '과제 목록', '안건', '다음 회의'
    ]):
        _route = 'gaon'
    elif any(kw in msg_lower for kw in [
        '카드뉴스', '카드 뉴스', '콘텐츠', '소셜', 'sns', '홍보', '카드',
        'card news', '인포그래픽', '소식지'
    ]):
        _route = 'naon'
    elif any(kw in msg_lower for kw in [
        '통역', '번역', '실시간 회의', '회의 진행', '발표', '회의록 작성',
        '속기', '회의 보조'
    ]):
        _route = 'ara'
    elif any(kw in msg_lower for kw in [
        '검토', '보고서', '자료 분석', '리뷰', 'review', '문제점', '개선',
        '첨삭', '피드백', '문서 검토', '파일 검토'
    ]):
        _route = 'naru'
    else:
        _route = 'hyean'

    knowledge = _get_knowledge(db, data.meeting_id)
    background_tasks.add_task(
        _log_activity, data.meeting_id, f"워크메이트[{_route}]",
        "Supervisor 대화", f'"{msg[:80]}"'
    )

    async def stream():
        if _route == 'gaon':
            previous_minutes = _get_previous_minutes(db, data.meeting_id)
            departments = _get_member_departments(db, data.meeting_id)
            meeting_context = _get_meeting_context(db, data.meeting_id)
            gen = gaon.chat_stream(
                message=msg, chat_history=data.chat_history or [],
                previous_minutes=previous_minutes, knowledge=knowledge,
                departments=departments, meeting_context=meeting_context,
            )
        elif _route == 'naru':
            meeting_context = _get_meeting_context(db, data.meeting_id)
            gen = naru.chat_stream(
                message=msg, chat_history=data.chat_history or [],
                knowledge=knowledge, meeting_context=meeting_context,
            )
        elif _route == 'ara':
            previous_minutes = _get_previous_minutes(db, data.meeting_id)
            agendas = db.query(models.Agenda).filter(
                models.Agenda.meeting_id == data.meeting_id,
                models.Agenda.status == "confirmed",
            ).all()
            gen = ara.chat_stream(
                message=msg, chat_history=data.chat_history or [],
                previous_minutes=previous_minutes,
                current_agendas=[{'content': a.content, 'department': a.department} for a in agendas],
                meeting_context=_get_meeting_context(db, data.meeting_id),
            )
        elif _route == 'naon':
            meeting_context = _get_meeting_context(db, data.meeting_id)
            gen = naon.chat_stream(
                message=msg, chat_history=data.chat_history or [],
                meeting_context=meeting_context,
            )
        else:  # hyean
            member = db.query(models.MeetingMember).filter(
                models.MeetingMember.meeting_id == data.meeting_id,
                models.MeetingMember.user_id == current_user.id,
            ).first()
            gen = hyean.status_stream(
                meeting_status=_build_meeting_status(db, data.meeting_id),
                user_role=member.role if member else "presenter",
                active_knowledge=knowledge,
                chat_history=data.chat_history,
                message=msg,
                user_name=current_user.name,
            )
        async for chunk in gen:
            yield f"data: {chunk.replace(chr(10), chr(92)+chr(110))}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream")


@router.post("/hyean/chat")
async def hyean_chat(
    data: schemas.AgentChatRequest,
    background_tasks: BackgroundTasks,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    member = db.query(models.MeetingMember).filter(
        models.MeetingMember.meeting_id == data.meeting_id,
        models.MeetingMember.user_id == current_user.id,
    ).first()
    user_role = member.role if member else "presenter"
    meeting_status = _build_meeting_status(db, data.meeting_id)
    knowledge = _get_knowledge(db, data.meeting_id)
    background_tasks.add_task(_log_activity, data.meeting_id, "혜안", "현황 대화", f'"{ data.message[:80] }"')

    async def stream():
        async for chunk in hyean.status_stream(
            meeting_status=meeting_status,
            user_role=user_role,
            active_knowledge=knowledge,
            chat_history=data.chat_history,
            message=data.message,
            user_name=current_user.name,
        ):
            yield f"data: {chunk.replace(chr(10), chr(92)+chr(110))}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream")


# ─── Helpers ─────────────────────────────────
def _extract_text_from_file(raw: bytes, filename: str) -> str:
    """파일 종류에 따라 텍스트 추출."""
    import io

    # PDF
    if filename.endswith(".pdf"):
        try:
            import pdfplumber
            with pdfplumber.open(io.BytesIO(raw)) as pdf:
                pages = [p.extract_text() or "" for p in pdf.pages]
            return "\n".join(pages).strip()
        except Exception as e:
            return f"[PDF 추출 오류: {e}]"

    # DOCX
    if filename.endswith(".docx"):
        try:
            import docx as _docx
            doc = _docx.Document(io.BytesIO(raw))
            return "\n".join(p.text for p in doc.paragraphs if p.text.strip())
        except Exception as e:
            return f"[DOCX 추출 오류: {e}]"

    # XLSX
    if filename.endswith((".xlsx", ".xls")):
        try:
            import openpyxl
            wb = openpyxl.load_workbook(io.BytesIO(raw), data_only=True)
            lines = []
            for ws in wb.worksheets:
                for row in ws.iter_rows(values_only=True):
                    row_text = "\t".join(str(c) if c is not None else "" for c in row)
                    if row_text.strip():
                        lines.append(row_text)
            return "\n".join(lines)
        except Exception as e:
            return f"[XLSX 추출 오류: {e}]"

    # 텍스트 파일 (txt, csv, md 등)
    for enc in ("utf-8", "euc-kr", "cp949"):
        try:
            return raw.decode(enc)
        except Exception:
            pass

    return ""


def _get_member_departments(db: Session, meeting_id: int) -> List[str]:
    from sqlalchemy.orm import joinedload
    members = (
        db.query(models.MeetingMember)
        .options(joinedload(models.MeetingMember.user))
        .filter(models.MeetingMember.meeting_id == meeting_id)
        .all()
    )
    return list({m.user.department for m in members if m.user and m.user.department})


def _save_extracted(db: Session, meeting_id: int, result: dict):
    def _clean_dept(val):
        if val is None or str(val).lower() in ("null", "none", ""):
            return None
        return str(val).strip()

    saved_agendas = []
    for a in result.get("agendas", []):
        if not a.get("content", "").strip():
            continue
        agenda = models.Agenda(
            meeting_id=meeting_id,
            department=_clean_dept(a.get("department")),
            content=a["content"],
        )
        db.add(agenda)
        db.flush()
        saved_agendas.append({"id": agenda.id, "department": agenda.department, "content": agenda.content})

    saved_todos = []
    for t in result.get("todos", []):
        if not t.get("content", "").strip():
            continue
        from datetime import datetime as _dt
        due = None
        if t.get("due_date"):
            try:
                due = _dt.strptime(t["due_date"], "%Y-%m-%d")
            except Exception:
                pass
        # 담당부서 기반으로 멤버 찾기
        user_id = None
        if t.get("department"):
            member = (
                db.query(models.MeetingMember)
                .join(models.User, models.MeetingMember.user_id == models.User.id)
                .filter(
                    models.MeetingMember.meeting_id == meeting_id,
                    models.User.department == t["department"],
                )
                .first()
            )
            if member:
                user_id = member.user_id

        if not user_id:
            # 담당자 미정 시 admin에게 할당
            admin = db.query(models.MeetingMember).filter(
                models.MeetingMember.meeting_id == meeting_id,
                models.MeetingMember.role == "admin",
            ).first()
            user_id = admin.user_id if admin else None

        if user_id:
            todo = models.Todo(
                meeting_id=meeting_id,
                user_id=user_id,
                content=t["content"],
                due_date=due,
                source_type="meeting_minutes",
            )
            db.add(todo)
            db.flush()
            saved_todos.append({"id": todo.id, "content": todo.content})

    db.commit()
    return saved_agendas, saved_todos


def _get_previous_minutes(db: Session, meeting_id: int) -> List[str]:
    sessions = db.query(models.MeetingSession).filter(
        models.MeetingSession.meeting_id == meeting_id,
        models.MeetingSession.status == "ended",
    ).all()
    result = []
    for s in sessions:
        if s.minutes and s.minutes.content_summary:
            result.append(s.minutes.content_summary)
    return result


def _build_meeting_status(db: Session, meeting_id: int) -> dict:
    agendas = db.query(models.Agenda).filter(models.Agenda.meeting_id == meeting_id).all()
    reports = db.query(models.Report).filter(models.Report.meeting_id == meeting_id).all()
    todos = db.query(models.Todo).filter(models.Todo.meeting_id == meeting_id).all()
    sessions = db.query(models.MeetingSession).filter(
        models.MeetingSession.meeting_id == meeting_id
    ).all()

    return {
        "agendas": {"total": len(agendas), "confirmed": sum(1 for a in agendas if a.status == "confirmed")},
        "reports": {
            "total": len(reports),
            "submitted": sum(1 for r in reports if r.status == "submitted"),
            "approved": sum(1 for r in reports if r.status == "approved"),
            "rejected": sum(1 for r in reports if r.status == "rejected"),
        },
        "todos": {
            "total": len(todos),
            "pending": sum(1 for t in todos if t.status == "pending"),
            "done": sum(1 for t in todos if t.status == "done"),
        },
        "sessions": {"total": len(sessions), "ended": sum(1 for s in sessions if s.status == "ended")},
    }
