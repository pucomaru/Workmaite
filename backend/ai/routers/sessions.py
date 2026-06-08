import logging
import os
from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from pydantic import BaseModel
from sqlalchemy.orm import Session
import models, schemas
from database import get_db
from auth import get_current_user
from neo4j_sync import sync_session, sync_minutes, delete_session

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["sessions"])


def _md_to_pdf(md_text: str) -> bytes:
    import markdown
    from routers.upload import _html_to_pdf
    html_body = markdown.markdown(md_text, extensions=["tables", "nl2br"])
    return _html_to_pdf(html_body)


@router.get("/meetings/{meeting_id}/sessions", response_model=List[schemas.SessionOut])
def list_sessions(
    meeting_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return db.query(models.MeetingSession).filter(
        models.MeetingSession.meeting_id == meeting_id
    ).order_by(models.MeetingSession.id.desc()).all()


@router.post("/meetings/{meeting_id}/sessions", response_model=schemas.SessionOut)
async def create_session(
    meeting_id: int,
    data: schemas.SessionCreate,
    background_tasks: BackgroundTasks,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    meeting = db.query(models.Meeting).filter(models.Meeting.id == meeting_id).first()
    if not meeting:
        raise HTTPException(status_code=404, detail="회의체를 찾을 수 없습니다.")

    session = models.MeetingSession(
        meeting_id=meeting_id,
        title=data.title,
        type=data.type or "offline",
        location=data.location,
        description=data.description,
        scheduled_at=data.scheduled_at,
    )
    db.add(session)
    db.flush()

    db.commit()
    db.refresh(session)

    background_tasks.add_task(
        sync_session,
        session_id=session.id,
        meeting_id=meeting_id,
        title=session.title or "",
        status=str(session.status or "scheduled"),
        scheduled_at=session.scheduled_at.isoformat() if session.scheduled_at else None,
        location=session.location,
        description=session.description,
    )
    return session


@router.patch("/meetings/{meeting_id}/sessions/{session_id}", response_model=schemas.SessionOut)
async def update_session(
    meeting_id: int,
    session_id: int,
    data: schemas.SessionUpdate,
    background_tasks: BackgroundTasks,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    session = db.query(models.MeetingSession).filter(
        models.MeetingSession.id == session_id,
        models.MeetingSession.meeting_id == meeting_id,
    ).first()
    if not session:
        raise HTTPException(status_code=404, detail="세션을 찾을 수 없습니다.")

    if data.title is not None:       session.title = data.title
    if data.type is not None:        session.type = data.type
    if data.location is not None:    session.location = data.location
    if data.description is not None: session.description = data.description
    if data.scheduled_at is not None: session.scheduled_at = data.scheduled_at
    db.commit()
    db.refresh(session)

    background_tasks.add_task(
        sync_session,
        session_id=session.id,
        meeting_id=meeting_id,
        title=session.title or "",
        status=str(session.status or "scheduled"),
        scheduled_at=session.scheduled_at.isoformat() if session.scheduled_at else None,
        location=session.location,
        description=session.description,
    )
    return session


@router.delete("/meetings/{meeting_id}/sessions/{session_id}")
async def delete_session_endpoint(
    meeting_id: int,
    session_id: int,
    background_tasks: BackgroundTasks,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    session = db.query(models.MeetingSession).filter(
        models.MeetingSession.id == session_id,
        models.MeetingSession.meeting_id == meeting_id,
    ).first()
    if not session:
        raise HTTPException(status_code=404, detail="세션을 찾을 수 없습니다.")

    db.query(models.Minutes).filter(models.Minutes.session_id == session_id).delete(synchronize_session=False)
    db.query(models.SttSegment).filter(models.SttSegment.session_id == session_id).delete(synchronize_session=False)
    db.query(models.ChatMessage).filter(models.ChatMessage.session_id == session_id).delete(synchronize_session=False)
    db.delete(session)
    db.commit()

    background_tasks.add_task(delete_session, session_id=session_id)
    return {"ok": True}


# ─── 회의록 저장 ──────────────────────────────────────────────────────────────

class MinutesSaveRequest(BaseModel):
    content: str               # 생성된 회의록 전체 텍스트
    content_summary: Optional[str] = None  # 요약 (없으면 content 앞 500자 사용)
    file_name: Optional[str] = None        # 저장할 파일명 (없으면 자동 생성)


@router.post("/sessions/{session_id}/minutes", response_model=schemas.MinutesOut)
async def save_minutes(
    session_id: int,
    body: MinutesSaveRequest,
    background_tasks: BackgroundTasks,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    생성된 회의록을 R2에 업로드하고 PostgreSQL minutes 테이블에 저장합니다.
    스트리밍으로 생성 완료 후 프론트에서 최종 텍스트를 보내면 이 API를 호출합니다.
    """
    session = db.query(models.MeetingSession).filter(
        models.MeetingSession.id == session_id
    ).first()
    if not session:
        raise HTTPException(status_code=404, detail="세션을 찾을 수 없습니다.")

    # 파일명 결정 (.pdf)
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    base_name = body.file_name or f"minutes_{session_id}_{ts}"
    base_name = base_name.removesuffix(".pdf").removesuffix(".md")
    file_name = base_name + ".pdf"

    # MD → PDF 변환 후 R2 업로드
    r2_url: Optional[str] = None
    try:
        pdf_bytes = _md_to_pdf(body.content)
        from r2_storage import upload_bytes
        r2_url = upload_bytes(
            pdf_bytes,
            f"minutes/{session_id}/{file_name}",
            "application/pdf",
        )
        logger.info(f"[sessions/minutes] R2 업로드 완료 — session_id={session_id}, url={r2_url}")
    except Exception as e:
        logger.warning(f"[sessions/minutes] PDF 변환/R2 업로드 실패 (무시): {e}")

    summary = body.content_summary or body.content[:500]

    # minutes 테이블 upsert (session_id UNIQUE)
    existing = db.query(models.Minutes).filter(
        models.Minutes.session_id == session_id
    ).first()

    if existing:
        existing.content_original = body.content
        existing.content_summary  = summary
        existing.recorder_id      = current_user.id
        existing.generated_at     = datetime.utcnow()
        if r2_url:  # R2 업로드 실패 시 기존 file_path 보존
            existing.file_name = file_name
            existing.file_path = r2_url
        minutes = existing
    else:
        minutes = models.Minutes(
            session_id       = session_id,
            content_original = body.content,
            content_summary  = summary,
            file_name        = file_name if r2_url else None,
            file_path        = r2_url,
            recorder_id      = current_user.id,
        )
        db.add(minutes)

    db.commit()
    db.refresh(minutes)

    # Neo4j 동기화 (백그라운드)
    background_tasks.add_task(
        sync_minutes,
        minutes_id=minutes.id,
        session_id=session_id,
        content_summary=summary,
    )

    return minutes
