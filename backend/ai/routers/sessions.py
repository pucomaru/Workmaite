from typing import List
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
import models, schemas
from database import get_db
from auth import get_current_user
from notifications import create_notification
from neo4j_sync import sync_session, delete_session

router = APIRouter(prefix="/api", tags=["sessions"])

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
    # 루프가 없으면 기본 루프 자동 생성
    if data.loop_id:
        loop = db.query(models.MeetingLoop).filter(
            models.MeetingLoop.id == data.loop_id,
            models.MeetingLoop.meeting_id == meeting_id,
        ).first()
        if not loop:
            raise HTTPException(status_code=404, detail="루프를 찾을 수 없습니다.")
    else:
        loop = db.query(models.MeetingLoop).filter(
            models.MeetingLoop.meeting_id == meeting_id
        ).first()
        if not loop:
            loop = models.MeetingLoop(meeting_id=meeting_id, loop_number=1)
            db.add(loop)
            db.flush()

    count = db.query(models.MeetingSession).filter(
        models.MeetingSession.meeting_id == meeting_id
    ).count()

    session = models.MeetingSession(
        meeting_id=meeting_id,
        loop_id=data.loop_id,
        session_number=count + 1,
        title=data.title,
        location=data.location,
        password=data.password,
        scheduled_at=data.scheduled_at,
    )
    db.add(session)
    db.flush()

    members = db.query(models.MeetingMember).filter(
        models.MeetingMember.meeting_id == meeting_id
    ).all()
    meeting = db.query(models.Meeting).filter(models.Meeting.id == meeting_id).first()
    for m in members:
        if m.user_id != current_user.id:
            create_notification(
                db,
                user_id=m.user_id,
                type="session_created",
                message=f"'{meeting.title}' {loop.loop_number}차 회의가 생성되었습니다.",
                ref_id=session.id,
                ref_type="session",
            )

    db.commit()
    db.refresh(session)

    # Neo4j 동기화 (백그라운드): neo4j_sync.sync_session 사용
    background_tasks.add_task(
        sync_session,
        session_id=session.id,
        meeting_id=meeting_id,
        title=session.title or "",
        status=str(session.status or "SCHEDULED"),
        scheduled_at=session.scheduled_at.isoformat() if session.scheduled_at else None,
    )
    return session

