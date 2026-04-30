import asyncio
from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Body, BackgroundTasks
from sqlalchemy.orm import Session
import models, schemas
from database import get_db
from auth import get_current_user
from notifications import create_notification
from websocket_manager import manager
from agents.ara import generate_minutes

router = APIRouter(prefix="/api", tags=["sessions"])


# ── Loop endpoints ────────────────────────────────────────────────────────────

@router.get("/meetings/{meeting_id}/loops", response_model=List[schemas.LoopOut])
def list_loops(
    meeting_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return db.query(models.MeetingLoop).filter(
        models.MeetingLoop.meeting_id == meeting_id
    ).order_by(models.MeetingLoop.loop_number.asc()).all()


@router.post("/meetings/{meeting_id}/loops", response_model=schemas.LoopOut)
async def create_loop(
    meeting_id: int,
    background_tasks: BackgroundTasks,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    count = db.query(models.MeetingLoop).filter(
        models.MeetingLoop.meeting_id == meeting_id
    ).count()
    loop = models.MeetingLoop(
        meeting_id=meeting_id,
        loop_number=count + 1,
    )
    db.add(loop)
    db.commit()
    db.refresh(loop)
    # 루프 생성 시 AI 메모리 자동 갱신
    from routers.tacit_knowledge import _do_refresh_memory
    background_tasks.add_task(_do_refresh_memory, meeting_id, loop.loop_number)
    return loop


# ── Session endpoints ─────────────────────────────────────────────────────────

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
    return session


@router.patch("/sessions/{session_id}", response_model=schemas.SessionOut)
def update_session(
    session_id: int,
    data: schemas.SessionUpdate,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    session = db.query(models.MeetingSession).filter(
        models.MeetingSession.id == session_id
    ).first()
    if not session:
        raise HTTPException(status_code=404, detail="Not found")
    if session.status == "ongoing":
        raise HTTPException(status_code=400, detail="진행 중인 회의는 수정할 수 없습니다.")
    if data.title is not None:
        session.title = data.title
    if data.scheduled_at is not None:
        session.scheduled_at = data.scheduled_at
    if data.password is not None:
        session.password = data.password
    db.commit()
    db.refresh(session)
    return session


@router.delete("/sessions/{session_id}")
def delete_session(
    session_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    session = db.query(models.MeetingSession).filter(
        models.MeetingSession.id == session_id
    ).first()
    if not session:
        raise HTTPException(status_code=404, detail="Not found")
    if session.status == "ongoing":
        raise HTTPException(status_code=400, detail="진행 중인 회의는 삭제할 수 없습니다.")

    # 연관 데이터 삭제
    db.query(models.Minutes).filter(models.Minutes.session_id == session_id).delete()
    db.query(models.ChatMessage).filter(
        models.ChatMessage.context_type == "room",
        models.ChatMessage.context_id == session_id,
    ).delete()

    # session_number 재정렬
    meeting_id = session.meeting_id
    db.delete(session)
    db.flush()

    remaining = db.query(models.MeetingSession).filter(
        models.MeetingSession.meeting_id == meeting_id
    ).order_by(models.MeetingSession.session_number.asc()).all()
    for i, s in enumerate(remaining, start=1):
        s.session_number = i

    db.commit()
    return {"ok": True}


@router.post("/sessions/{session_id}/start")
async def start_session(
    session_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    session = db.query(models.MeetingSession).filter(
        models.MeetingSession.id == session_id
    ).first()
    if not session:
        raise HTTPException(status_code=404, detail="Not found")
    session.status = "ongoing"
    session.started_at = datetime.utcnow()
    db.commit()
    return {"ok": True}


@router.post("/sessions/{session_id}/end")
async def end_session(
    session_id: int,
    body: Optional[dict] = Body(default=None),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    session = db.query(models.MeetingSession).filter(
        models.MeetingSession.id == session_id
    ).first()
    if not session:
        raise HTTPException(status_code=404, detail="Not found")
    session.status = "ended"
    session.ended_at = datetime.utcnow()

    # 발화 녹취를 content_raw 형태로 변환
    raw_transcript = ""
    if body and body.get("transcript"):
        lines = [
            f"[{seg['time']}] {seg['name']}: {seg['text']}"
            for seg in body["transcript"]
        ]
        raw_transcript = "\n".join(lines)

    db.commit()
    asyncio.create_task(_generate_minutes_async(session_id, session.meeting_id, raw_transcript, db))
    return {"ok": True, "message": "회의가 종료되었습니다. 회의록을 생성 중입니다."}


async def _generate_minutes_async(session_id: int, meeting_id: int, raw_transcript: str, db: Session):
    await asyncio.sleep(1)
    existing = db.query(models.Minutes).filter(
        models.Minutes.session_id == session_id
    ).first()

    # 발화 녹취 우선, 없으면 기존 raw
    raw = raw_transcript or (existing.content_raw if existing else "")

    summary = await generate_minutes(raw)
    if existing:
        existing.content_summary = summary
        existing.generated_at = datetime.utcnow()
    else:
        minutes = models.Minutes(
            session_id=session_id,
            content_raw=raw,
            content_summary=summary,
        )
        db.add(minutes)

    db.commit()

    members = db.query(models.MeetingMember).filter(
        models.MeetingMember.meeting_id == meeting_id
    ).all()
    for m in members:
        create_notification(
            db,
            user_id=m.user_id,
            type="minutes_generated",
            message="회의록이 생성되었습니다.",
            ref_id=session_id,
            ref_type="session",
        )
    db.commit()

    await manager.broadcast_session(session_id, {
        "type": "minutes_generated",
        "session_id": session_id,
        "summary": summary,
    })


@router.post("/sessions/{session_id}/transcript-chunk")
async def save_transcript(
    session_id: int,
    data: dict,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    minutes = db.query(models.Minutes).filter(
        models.Minutes.session_id == session_id
    ).first()
    chunk = data.get("text", "")
    if minutes:
        minutes.content_raw = (minutes.content_raw or "") + "\n" + chunk
    else:
        minutes = models.Minutes(session_id=session_id, content_raw=chunk)
        db.add(minutes)
    db.commit()
    return {"ok": True}


@router.get("/sessions/{session_id}/minutes", response_model=schemas.MinutesOut)
def get_minutes(
    session_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    minutes = db.query(models.Minutes).filter(
        models.Minutes.session_id == session_id
    ).first()
    if not minutes:
        raise HTTPException(status_code=404, detail="회의록이 없습니다.")
    return minutes


@router.get("/all-minutes")
def get_all_minutes(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    member_rows = db.query(models.MeetingMember).filter(
        models.MeetingMember.user_id == current_user.id
    ).all()
    meeting_ids = [r.meeting_id for r in member_rows]

    sessions = (
        db.query(models.MeetingSession)
        .filter(models.MeetingSession.meeting_id.in_(meeting_ids))
        .order_by(models.MeetingSession.ended_at.desc().nullsfirst())
        .all()
    )
    session_ids = [s.id for s in sessions]
    minutes_list = db.query(models.Minutes).filter(
        models.Minutes.session_id.in_(session_ids)
    ).all()
    minutes_map = {m.session_id: m for m in minutes_list}

    meetings = {m.id: m for m in db.query(models.Meeting).filter(models.Meeting.id.in_(meeting_ids)).all()}

    result = []
    for s in sessions:
        m = minutes_map.get(s.id)
        if not m:
            continue
        meeting = meetings.get(s.meeting_id)
        result.append({
            "session_id": s.id,
            "session_number": s.session_number,
            "session_title": s.title,
            "meeting_id": s.meeting_id,
            "meeting_title": meeting.title if meeting else "-",
            "ended_at": s.ended_at,
            "content_summary": m.content_summary,
            "content_raw": m.content_raw,
            "minutes_id": m.id,
        })
    return result
