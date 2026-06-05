from typing import List
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
import models, schemas
from database import get_db
from auth import get_current_user
from notifications import create_notification
from neo4j_sync import sync_session, delete_session

router = APIRouter(prefix="/api/v1", tags=["sessions"])


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

    members = db.query(models.MeetingMember).filter(
        models.MeetingMember.meeting_id == meeting_id
    ).all()
    for m in members:
        if m.user_id != current_user.id:
            create_notification(
                db,
                user_id=m.user_id,
                type="session_created",
                message=f"'{meeting.title}' 회의 세션이 생성되었습니다.",
                ref_id=session.id,
                ref_type="session",
            )

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
