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


# ─── 아카이브 과제 추출 (컨텍스트 기반) ──────────────────────────────────
@router.post("/archive/extract-agendas")
async def archive_extract_agendas(
    meeting_id: int = Form(...),
    selected_file_ids: str = Form("[]"),   # JSON 문자열
    selected_similar_docs: str = Form("[]"),
    files: List[UploadFile] = File(default=[]),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    아카이브 과제 탭에서 호출되는 AI 과제 추출 엔드포인트.
    - 회의체 기본 정보 (목적, 지침, 구성원)
    - 최근 회의록 최대 3건
    - 미완료 과제
    - 선택된 파일 (DB 저장 파일 or 새로 업로드)
    를 컨텍스트로 조합해 LLM에 전달, 구조화된 과제 목록을 반환한다.
    """
    import json as _json, os as _os, re as _re

    selected_ids = _json.loads(selected_file_ids) if selected_file_ids else []

    # ── 1. 회의체 기본 정보 ────────────────────────────────────────────
    meeting = db.query(models.Meeting).filter(models.Meeting.id == meeting_id).first()
    if not meeting:
        return {"agendas": [], "error": "회의체를 찾을 수 없습니다."}

    meeting_context = _get_meeting_context(db, meeting_id)
    departments = _get_member_departments(db, meeting_id)
    knowledge = _get_knowledge(db, meeting_id)

    # ── 2. 최근 회의록 (최대 3건) ──────────────────────────────────────
    previous_minutes = _get_previous_minutes(db, meeting_id)[:3]

    # ── 3. 미완료 과제 ────────────────────────────────────────────────
    pending_todos = db.query(models.Todo).filter(
        models.Todo.meeting_id == meeting_id,
        models.Todo.status.in_(["pending", "in_progress", "at_risk"]),
    ).order_by(models.Todo.created_at.desc()).limit(10).all()

    pending_todos_text = ""
    if pending_todos:
        todo_lines = []
        for t in pending_todos:
            assignee = f" (담당: {t.assignee_name}" if t.assignee_name else ""
            if t.assignee_dept and assignee:
                assignee += f", {t.assignee_dept}"
            if assignee:
                assignee += ")"
            due = f" [마감: {t.due_date.strftime('%Y-%m-%d')}]" if t.due_date else ""
            todo_lines.append(f"- [{t.status}] {t.content}{assignee}{due}")
        pending_todos_text = "\n".join(todo_lines)

    # ── 4. 파일 텍스트 추출 ───────────────────────────────────────────
    file_texts = []

    # DB에 저장된 보고서
    for fid in selected_ids:
        try:
            report = db.query(models.Report).filter(models.Report.id == int(fid)).first()
            if report and report.file_path and _os.path.exists(report.file_path):
                with open(report.file_path, "rb") as f:
                    raw = f.read()
                text = _extract_text_from_file(raw, report.file_name or "")
                if text.strip():
                    file_texts.append(f"[보고서: {report.file_name}]\n{text[:4000]}")
        except Exception as e:
            print(f"[DB 파일 추출 오류] {e}")

    # 새로 업로드된 파일 (multipart)
    for upload in files:
        if not upload or not upload.filename:
            continue
        try:
            raw = await upload.read()
            fname = upload.filename.lower()
            text = _extract_text_from_file(raw, fname)
            if text.strip():
                file_texts.append(f"[첨부: {upload.filename}]\n{text[:4000]}")
            else:
                file_texts.append(f"[첨부: {upload.filename}] - 텍스트 추출 불가")
        except Exception as e:
            print(f"[업로드 파일 추출 오류] {upload.filename}: {e}")

    # ── 5. 프롬프트 구성 ──────────────────────────────────────────────
    context_parts = [f"[회의체 정보]\n{meeting_context}"]

    if meeting.guidelines:
        context_parts.append(f"[회의 지침]\n{meeting.guidelines}")

    if previous_minutes:
        minutes_text = "\n\n".join(
            f"[회의록 {i+1}]\n{m}" for i, m in enumerate(previous_minutes)
        )
        context_parts.append(f"[최근 회의록]\n{minutes_text}")

    if pending_todos_text:
        context_parts.append(f"[미완료 과제]\n{pending_todos_text}")

    if file_texts:
        context_parts.append(f"[첨부 자료]\n" + "\n\n".join(file_texts))

    if knowledge:
        kb_text = "\n".join(
            f"- [{k['category']}] {k['title']}: {k['content']}" for k in knowledge[:5]
        )
        context_parts.append(f"[조직 암묵지]\n{kb_text}")

    full_context = "\n\n".join(context_parts)

    # ── 6. LLM 호출 ───────────────────────────────────────────────────
    from langchain_openai import ChatOpenAI
    from langchain_core.messages import SystemMessage, HumanMessage

    llm = ChatOpenAI(
        model=_os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
        temperature=0.15,
        api_key=_os.getenv("OPENAI_API_KEY"),
    )

    dept_list = ", ".join(departments) if departments else "정보 없음"

    system_prompt = f"""당신은 회의체 운영 전문 AI입니다.
주어진 컨텍스트(회의체 정보, 회의록, 미완료 과제, 첨부 자료)를 분석하여
다음 회의에서 다뤄야 할 핵심 과제와 아젠다를 추출해 주세요.

참여 부서: {dept_list}

규칙:
1. 첨부 자료가 있으면 그 내용을 최우선으로 분석하여 구체적인 후속 과제를 추출하세요
2. 미완료 과제가 있으면 반드시 포함하되 중복은 제거하세요
3. 과제는 실행 가능하고 구체적으로 작성하세요 (문서에서 언급된 날짜, 수치, 담당자 반영)
4. bullets는 과제의 세부 실행 항목 2-4개로 작성하세요
5. 3-6개 과제를 추출하세요
6. 문서에 일정이 명시되어 있으면 bullets에 반드시 포함하세요

반드시 아래 JSON 형식으로만 응답하세요:
{{
  "agendas": [
    {{
      "title": "과제/아젠다 제목",
      "bullets": ["세부 항목1", "세부 항목2", "세부 항목3"],
      "department": "담당부서명 또는 null",
      "priority": "urgent_important" | "important" | "urgent" | "normal"
    }}
  ]
}}"""

    human_prompt = f"다음 컨텍스트를 바탕으로 과제를 추출해 주세요:\n\n{full_context}"

    try:
        response = await llm.ainvoke([
            SystemMessage(content=system_prompt),
            HumanMessage(content=human_prompt),
        ])
        raw_text = response.content.strip()
        print(f"[LLM RAW] {raw_text[:500]}")
        try:
            match = _re.search(r'\{[\s\S]*\}', raw_text)
            if match:
                json_str = match.group(0)
                open_count = json_str.count('{') - json_str.count('}')
                if open_count > 0:
                    json_str += '}' * open_count
                parsed = _json.loads(json_str)
            else:
                parsed = _json.loads(raw_text)
        except Exception as parse_err:
            print(f"[JSON 파싱 오류] {parse_err}")
            parsed = {"agendas": []}
        agendas = parsed.get("agendas", [])
        print(f"[AGENDAS] {agendas}")
        result = []
        for ag in agendas:
            result.append({
                "title": ag.get("title", ""),
                "bullets": ag.get("bullets", []),
                "department": ag.get("department"),
                "priority": ag.get("priority", "normal"),
                "_state": None,
                "_editing": False,
            })

        return {
            "agendas": result,
            "context_used": {
                "minutes_count": len(previous_minutes),
                "todos_count": len(pending_todos),
                "files_count": len(file_texts),
            }
        }

    except Exception as e:
        print(f"[archive/extract-agendas 오류] {e}")
        return {"agendas": [], "error": f"AI 분석 중 오류: {str(e)}"}


# ─── 아카이브 채팅 기반 과제 업데이트 ──────────────────────────────────────
@router.post("/archive/chat-extract")
async def archive_chat_extract(
    data: schemas.AgentChatRequest,
    background_tasks: BackgroundTasks,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    아카이브 과제 탭 채팅 - 사용자가 채팅으로 과제를 수정/추가 요청하면
    현재 추출된 과제 목록을 업데이트해서 반환한다.
    """
    import json as _json, os as _os, re as _re
    from langchain_openai import ChatOpenAI
    from langchain_core.messages import SystemMessage, HumanMessage

    meeting_id = data.meeting_id
    message = data.message or ""
    current_agendas = data.chat_history[0].get("agendas", []) if data.chat_history else []

    meeting_context = _get_meeting_context(db, meeting_id) if meeting_id else ""
    departments = _get_member_departments(db, meeting_id) if meeting_id else []
    dept_list = ", ".join(departments) if departments else "정보 없음"

    llm = ChatOpenAI(
        model=_os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
        temperature=0.15,
        api_key=_os.getenv("OPENAI_API_KEY"),
    )

    current_agendas_text = _json.dumps(current_agendas, ensure_ascii=False, indent=2) if current_agendas else "없음"

    system_prompt = f"""당신은 회의체 과제 관리 AI입니다.
현재 추출된 과제 목록과 사용자의 요청을 바탕으로 과제 목록을 업데이트해주세요.

회의체 정보: {meeting_context}
참여 부서: {dept_list}

현재 과제 목록:
{current_agendas_text}

규칙:
1. 사용자가 과제 추가를 요청하면 새 과제를 목록에 추가하세요
2. 사용자가 과제 수정을 요청하면 해당 과제를 수정하세요
3. 사용자가 과제 삭제를 요청하면 해당 과제를 제거하세요
4. 변경되지 않은 과제는 그대로 유지하세요
5. 반드시 아래 JSON 형식으로 전체 과제 목록을 반환하세요

{{
  "agendas": [
    {{
      "title": "과제 제목",
      "bullets": ["세부 항목1", "세부 항목2"],
      "department": "담당부서 또는 null",
      "priority": "urgent_important" | "important" | "urgent" | "normal"
    }}
  ],
  "message": "변경 사항 설명 (한 문장)"
}}"""

    try:
        response = await llm.ainvoke([
            SystemMessage(content=system_prompt),
            HumanMessage(content=message),
        ])
        raw_text = response.content.strip()
        print(f"[chat-extract RAW] {raw_text[:300]}")

        try:
            match = _re.search(r'\{{[\s\S]*\}}', raw_text)
            if match:
                json_str = match.group(0)
                open_count = json_str.count('{') - json_str.count('}')
                if open_count > 0:
                    json_str += '}' * open_count
                parsed = _json.loads(json_str)
            else:
                parsed = _json.loads(raw_text)
        except Exception:
            parsed = {"agendas": current_agendas, "message": raw_text}

        agendas = parsed.get("agendas", current_agendas)
        reply_msg = parsed.get("message", "과제 목록을 업데이트했습니다.")

        result = [
            {
                "title": ag.get("title", ""),
                "bullets": ag.get("bullets", []),
                "department": ag.get("department"),
                "priority": ag.get("priority", "normal"),
                "_state": None,
                "_editing": False,
            }
            for ag in agendas
        ]
        return {"agendas": result, "reply": reply_msg}

    except Exception as e:
        print(f"[chat-extract 오류] {e}")
        return {"agendas": current_agendas, "reply": f"오류: {str(e)}"}

@router.post("/archive/analyze-file")
async def analyze_archive_file(
    data: dict,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    아카이브에서 자료 업로드 시 AI가 문서를 검토하고
    - 적합성 점수(0-100)
    - 검토 의견 (피드백 항목)
    - 제안 아젠다 목록
    - 유관부서 목록
    을 반환한다. GraphDB(온톨로지) 맥락도 활용한다.
    """
    import json as _json
    from langchain_openai import ChatOpenAI
    from langchain_core.messages import SystemMessage, HumanMessage

    file_name: str = data.get("file_name", "")
    file_type: str = data.get("file_type", "")
    dept_name: str = data.get("dept_name", "")
    graph_context: str = data.get("graph_context", "")  # JSON-serialised nodes/edges summary

    # 글로벌 암묵지 컨텍스트 로드
    knowledge_items = _get_knowledge(db)
    knowledge_text = "\n".join(
        f"[{k['category']}] {k['title']}: {k['content']}" for k in knowledge_items[:10]
    ) if knowledge_items else "없음"

    llm = ChatOpenAI(
        model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
        temperature=0.2,
        api_key=os.getenv("OPENAI_API_KEY"),
    )

    system_msg = SystemMessage(content="""당신은 조직 온톨로지·지식 관리 전문 AI입니다.
파일 이름, 유형, 업로드 부서, 그리고 현재 조직 그래프(GraphDB) 맥락을 바탕으로
해당 자료의 적합성·완성도를 평가하고 아래 JSON을 반드시 반환하세요.

{
  "score": <0-100 정수>,
  "feedback": ["피드백 항목1", "피드백 항목2", ...],  // 3-5개, 구체적이고 건설적으로
  "agendas": [
    {"content": "아젠다 내용", "department": "담당부서명"},
    ...
  ],  // 1-3개
  "related_depts": ["부서명1", "부서명2", ...]  // 유관부서 2-4개
}

- score: 파일명·유형·부서 적합성, 그래프 맥락 연계도 등을 종합한 점수
- feedback: 보완할 점, 잘된 점 포함
- agendas: 이 자료가 다음 회의에서 다뤄야 할 아젠다 제안
- related_depts: 이 자료와 협업이 필요한 유관부서 (그래프에 이미 존재하는 부서 우선)
반드시 JSON만 반환하고 다른 설명은 쓰지 마세요.""")

    human_msg = HumanMessage(content=f"""파일 이름: {file_name}
파일 유형: {file_type}
업로드 부서: {dept_name}

[현재 조직 그래프 맥락]
{graph_context or '(그래프 정보 없음)'}

[조직 암묵지]
{knowledge_text}
""")

    try:
        response = await llm.ainvoke([system_msg, human_msg])
        raw = response.content.strip()
        # JSON 추출
        import re as _re
        match = _re.search(r'\{[\s\S]*\}', raw)
        if match:
            result = _json.loads(match.group(0))
        else:
            result = _json.loads(raw)
        return {
            "score": int(result.get("score", 70)),
            "feedback": result.get("feedback", []),
            "agendas": result.get("agendas", []),
            "related_depts": result.get("related_depts", []),
        }
    except Exception as e:
        return {
            "score": 70,
            "feedback": [f"AI 분석 중 오류: {str(e)}", "수동으로 검토해 주세요."],
            "agendas": [{"content": f"{file_name} 관련 안건 검토", "department": dept_name}],
            "related_depts": [],
        }