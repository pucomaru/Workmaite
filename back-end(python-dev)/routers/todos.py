from typing import List
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
import models, schemas
from database import get_db
from auth import get_current_user

router = APIRouter(prefix="/api", tags=["todos"])

@router.get("/meetings/{meeting_id}/todos", response_model=List[schemas.TodoOut])
def all_todos(
    meeting_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return db.query(models.Todo).filter(
        models.Todo.meeting_id == meeting_id,
    ).all()


@router.post("/meetings/{meeting_id}/todos", response_model=schemas.TodoOut)
def create_todo(
    meeting_id: int,
    data: schemas.TodoCreate,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    todo = models.Todo(
        meeting_id=meeting_id,
        user_id=current_user.id,
        content=data.content,
        assignee_name=data.assignee_name,
        assignee_dept=data.assignee_dept,
        how=data.how,
        why=data.why,
        priority=data.priority or "normal",
        tags=data.tags,
        due_date=data.due_date,
        agenda_id=data.agenda_id,
        source_type=data.source_type or "report",
    )
    db.add(todo)
    db.commit()
    db.refresh(todo)
    return todo


@router.get("/calendar/events")
def calendar_events(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    member_rows = db.query(models.MeetingMember).filter(
        models.MeetingMember.user_id == current_user.id
    ).all()
    meeting_ids = [r.meeting_id for r in member_rows]

    sessions = (
        db.query(models.MeetingSession, models.Meeting.title.label("meeting_title"))
        .join(models.Meeting, models.Meeting.id == models.MeetingSession.meeting_id)
        .filter(
            models.MeetingSession.meeting_id.in_(meeting_ids),
            models.MeetingSession.scheduled_at.isnot(None),
            models.MeetingSession.status != 'ended',
        ).all()
    )

    todos = db.query(models.Todo).filter(
        models.Todo.user_id == current_user.id,
        models.Todo.due_date.isnot(None),
    ).all()

    events = []
    for s, meeting_title in sessions:
        events.append({
            "type": "session",
            "id": s.id,
            "title": s.title,
            "date": s.scheduled_at.isoformat() if s.scheduled_at else None,
            "meeting_id": s.meeting_id,
            "meeting_title": meeting_title,
        })
    for t in todos:
        events.append({
            "type": "todo",
            "id": t.id,
            "title": t.content,
            "date": t.due_date.isoformat() if t.due_date else None,
            "meeting_id": t.meeting_id,
        })
    return events
