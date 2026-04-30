from datetime import datetime, timedelta
from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
import models, schemas
from database import get_db
from auth import get_current_user

router = APIRouter(prefix="/api", tags=["todos"])


@router.get("/todos/urgent")
def urgent_todos(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    deadline = datetime.utcnow() + timedelta(days=3)
    todos = db.query(models.Todo).filter(
        models.Todo.user_id == current_user.id,
        models.Todo.status == "pending",
        models.Todo.due_date <= deadline,
    ).order_by(models.Todo.due_date.asc()).all()
    return todos


@router.get("/meetings/{meeting_id}/todos/mine", response_model=List[schemas.TodoOut])
def my_todos(
    meeting_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return db.query(models.Todo).filter(
        models.Todo.meeting_id == meeting_id,
        models.Todo.user_id == current_user.id,
    ).all()


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
        due_date=data.due_date,
        agenda_id=data.agenda_id,
        source_type=data.source_type or "report",
    )
    db.add(todo)
    db.commit()
    db.refresh(todo)
    return todo


@router.patch("/todos/{todo_id}", response_model=schemas.TodoOut)
def update_todo(
    todo_id: int,
    data: schemas.TodoUpdate,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    todo = db.query(models.Todo).filter(
        models.Todo.id == todo_id,
        models.Todo.user_id == current_user.id,
    ).first()
    if not todo:
        raise HTTPException(status_code=404, detail="Not found")
    if data.content is not None:
        todo.content = data.content
    if data.due_date is not None:
        todo.due_date = data.due_date
    if data.status is not None:
        old_status = todo.status
        todo.status = data.status

        if data.status == "done" and old_status != "done":
            event = models.TacitEvent(
                event_type="todo_completed",
                meeting_id=todo.meeting_id,
                payload={"todo_id": todo_id, "content": todo.content},
                actor_id=current_user.id,
            )
            db.add(event)
        elif data.status == "delayed":
            event = models.TacitEvent(
                event_type="todo_delayed",
                meeting_id=todo.meeting_id,
                payload={"todo_id": todo_id, "content": todo.content},
                actor_id=current_user.id,
            )
            db.add(event)

    db.commit()
    db.refresh(todo)
    return todo


@router.delete("/todos/{todo_id}")
def delete_todo(
    todo_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    todo = db.query(models.Todo).filter(models.Todo.id == todo_id).first()
    if not todo:
        raise HTTPException(status_code=404, detail="Not found")
    db.delete(todo)
    db.commit()
    return {"ok": True}


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
