from typing import List
from fastapi import APIRouter, Depends, BackgroundTasks, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime
import os, base64, httpx
import models, schemas
from database import get_db
from auth import get_current_user

router = APIRouter(prefix="/api", tags=["todos"])

NEO4J_URL      = os.getenv("NEO4J_URL", "http://localhost:7474")
NEO4J_USER     = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "neo4j")
NEO4J_DB       = os.getenv("NEO4J_DATABASE", "neo4j")

async def _neo4j(stmt: str, params: dict | None = None):
    try:
        creds = base64.b64encode(f"{NEO4J_USER}:{NEO4J_PASSWORD}".encode()).decode()
        headers = {"Authorization": f"Basic {creds}", "Content-Type": "application/json", "Accept": "application/json"}
        body = {"statements": [{"statement": stmt, **(({"parameters": params}) if params else {})}]}
        async with httpx.AsyncClient(timeout=8.0) as client:
            await client.post(f"{NEO4J_URL}/db/{NEO4J_DB}/tx/commit", json=body, headers=headers)
    except Exception as e:
        print(f"[Neo4j sync warn] {e}")

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
async def create_todo(
    meeting_id: int,
    data: schemas.TodoCreate,
    background_tasks: BackgroundTasks,
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

    # Neo4j 동기화 (백그라운드)
    ag_id = f"agenda-{todo.id}"
    mg_id = f"mg-sqlite-{meeting_id}"
    async def _sync():
        await _neo4j(
            "MERGE (a:Agenda {id:$id}) SET a.title=$title, a.priority=$priority, a.status='pending', a.due_date=$due "
            "WITH a MATCH (mg:MeetingGroup {id:$mgid}) MERGE (a)-[:OWNED_BY]->(mg)",
            {"id": ag_id, "title": todo.content or "", "priority": todo.priority or "normal",
             "due": str(todo.due_date or ""), "mgid": mg_id},
        )
        if todo.assignee_name:
            await _neo4j(
                "MATCH (a:Agenda {id:$aid}) MATCH (p:Person) WHERE p.name=$name MERGE (a)-[:ASSIGNED_TO]->(p)",
                {"aid": ag_id, "name": todo.assignee_name},
            )
    background_tasks.add_task(_sync)
    return todo


@router.get("/sessions/{session_id}/stt-segments", response_model=List[schemas.SttSegmentOut])
def get_stt_segments(
    session_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    segments = (
        db.query(models.SttSegment)
        .filter(models.SttSegment.session_id == session_id)
        .order_by(models.SttSegment.start_sec)
        .all()
    )
    result = []
    for s in segments:
        user = db.query(models.User).filter(models.User.id == s.speaker_user_id).first() if s.speaker_user_id else None
        item = schemas.SttSegmentOut(
            id=s.id,
            session_id=s.session_id,
            speaker_label=s.speaker_label,
            speaker_user_id=s.speaker_user_id,
            speaker_name=user.name if user else None,
            content=s.content,
            start_sec=s.start_sec,
            end_sec=s.end_sec,
            confidence=s.confidence,
            created_at=s.created_at,
        )
        result.append(item)
    return result


@router.get("/sessions/{session_id}/minutes", response_model=schemas.MinutesOut)
def get_minutes(
    session_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    m = db.query(models.Minutes).filter(models.Minutes.session_id == session_id).first()
    if not m:
        raise HTTPException(status_code=404, detail="Minutes not found")
    return m


@router.post("/sessions/{session_id}/minutes", response_model=schemas.MinutesOut)
def save_minutes(
    session_id: int,
    data: schemas.MinutesSave,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    m = db.query(models.Minutes).filter(models.Minutes.session_id == session_id).first()
    if m:
        m.content_summary = data.content_summary
        m.updated_at = datetime.utcnow()
    else:
        m = models.Minutes(
            session_id=session_id,
            recorder_id=current_user.id,
            content_summary=data.content_summary,
        )
        db.add(m)
    db.commit()
    db.refresh(m)
    return m


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
