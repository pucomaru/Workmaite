import os
from typing import List
from fastapi import APIRouter, Depends, UploadFile, File, Form
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
import models, schemas
from database import get_db
from auth import get_current_user
from agents import gaon, naru, ara, naon, hyean
from datetime import datetime

router = APIRouter(prefix="/api/agent", tags=["agents"])


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


# ─── 가온 Agent ───────────────────────────────
@router.post("/gaon/chat")
async def gaon_chat(
    data: schemas.AgentChatRequest,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    knowledge = _get_knowledge(db, data.meeting_id)
    previous_minutes = _get_previous_minutes(db, data.meeting_id)
    departments = _get_member_departments(db, data.meeting_id)

    async def stream():
        async for chunk in gaon.chat_stream(
            message=data.message,
            chat_history=data.chat_history or [],
            previous_minutes=previous_minutes,
            knowledge=knowledge,
            departments=departments,
        ):
            yield f"data: {chunk}\n\n"
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

    saved_agendas, saved_todos = _save_extracted(db, meeting_id, result)
    return {"agendas": saved_agendas, "todos": saved_todos}


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
    return {"agendas": saved_agendas, "todos": saved_todos}


# ─── 나루 Agent ───────────────────────────────
@router.post("/naru/chat")
async def naru_chat(
    data: schemas.AgentChatRequest,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    knowledge = _get_knowledge(db, data.meeting_id)

    async def stream():
        async for chunk in naru.chat_stream(
            message=data.message,
            chat_history=data.chat_history or [],
            knowledge=knowledge,
        ):
            yield f"data: {chunk}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream")


@router.post("/naru/global-review")
async def global_review(
    data: schemas.AgentChatRequest,
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

    async def stream():
        async for chunk in naru.global_review_stream(
            reports_info=reports_info,
            chat_history=data.chat_history or [],
            knowledge=knowledge,
        ):
            yield f"data: {chunk}\n\n"
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
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    previous_minutes = _get_previous_minutes(db, data.meeting_id)
    agendas = db.query(models.Agenda).filter(
        models.Agenda.meeting_id == data.meeting_id,
        models.Agenda.status == "confirmed",
    ).all()
    agendas_list = [{"content": a.content, "department": a.department} for a in agendas]

    async def stream():
        async for chunk in ara.chat_stream(
            message=data.message,
            chat_history=data.chat_history or [],
            previous_minutes=previous_minutes,
            current_agendas=agendas_list,
        ):
            yield f"data: {chunk}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream")

import uuid as _uuid

# ─── 나온 Agent (LangGraph Human-in-the-Loop) ───────────────────

@router.post("/naon/chat")
async def naon_chat(
    data: schemas.AgentChatRequest,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """나온과의 자유 대화 (스트리밍). 기획 요구사항 파악 단계."""
    async def stream():
        async for chunk in naon.chat_stream(
            message=data.message,
            chat_history=data.chat_history or [],
        ):
            yield f"data: {chunk}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream")


@router.post("/naon/propose-plan")
async def naon_propose_plan(
    data: schemas.CardNewsPlanRequest,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    [LangGraph HITL Step 1]
    propose_node 를 실행하고 interrupt() 지점에서 그래프를 일시 정지한다.
    생성된 기획안(plan)과 thread_id 를 반환한다.
    프론트엔드는 이 plan 을 사용자에게 보여주고 승인/거부를 기다린다.
    """
    minutes_list = []
    for sid in data.session_ids:
        m = db.query(models.Minutes).filter(models.Minutes.session_id == sid).first()
        if m and m.content_summary:
            minutes_list.append(m.content_summary)

    meeting = db.query(models.Meeting).filter(models.Meeting.id == data.meeting_id).first()
    thread_id = data.thread_id or str(_uuid.uuid4())

    result = await naon.start_proposal(
        thread_id=thread_id,
        chat_history=data.chat_history or [],
        minutes_list=minutes_list,
        meeting_title=meeting.title if meeting else "",
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
@router.post("/hyean/status")
async def hyean_status(
    data: schemas.HyeanStatusRequest,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    meeting_status = _build_meeting_status(db, data.meeting_id)
    knowledge = _get_knowledge(db, data.meeting_id)

    async def stream():
        async for chunk in hyean.status_stream(
            meeting_status=meeting_status,
            user_role=data.user_role,
            active_knowledge=knowledge,
        ):
            yield f"data: {chunk}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream")


@router.post("/hyean/chat")
async def hyean_chat(
    data: schemas.AgentChatRequest,
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

    async def stream():
        async for chunk in hyean.status_stream(
            meeting_status=meeting_status,
            user_role=user_role,
            active_knowledge=knowledge,
            chat_history=data.chat_history,
            message=data.message,
        ):
            yield f"data: {chunk}\n\n"
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
