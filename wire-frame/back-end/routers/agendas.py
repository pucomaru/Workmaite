from datetime import datetime
from typing import List
from fastapi import APIRouter, Depends, HTTPException, Body
from sqlalchemy.orm import Session
import models, schemas
from database import get_db
from auth import get_current_user
from notifications import create_notification
from websocket_manager import manager

router = APIRouter(prefix="/api", tags=["agendas"])


def _get_member_role(db, meeting_id, user_id):
    m = db.query(models.MeetingMember).filter(
        models.MeetingMember.meeting_id == meeting_id,
        models.MeetingMember.user_id == user_id,
    ).first()
    return m.role if m else None


@router.get("/meetings/{meeting_id}/agendas", response_model=List[schemas.AgendaOut])
def list_agendas(
    meeting_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return db.query(models.Agenda).filter(models.Agenda.meeting_id == meeting_id).all()


@router.post("/meetings/{meeting_id}/agendas", response_model=schemas.AgendaOut)
def create_agenda(
    meeting_id: int,
    data: schemas.AgendaCreate,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    agenda = models.Agenda(
        meeting_id=meeting_id,
        department=data.department,
        content=data.content,
        agenda_type=data.agenda_type or "draft",
        presenter_name=data.presenter_name,
        duration_minutes=data.duration_minutes,
        order_num=data.order_num or 0,
    )
    db.add(agenda)
    db.commit()
    db.refresh(agenda)
    return agenda


@router.patch("/meetings/{meeting_id}/agendas/{agenda_id}", response_model=schemas.AgendaOut)
def update_agenda(
    meeting_id: int,
    agenda_id: int,
    data: schemas.AgendaUpdate,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    agenda = db.query(models.Agenda).filter(
        models.Agenda.id == agenda_id,
        models.Agenda.meeting_id == meeting_id,
    ).first()
    if not agenda:
        raise HTTPException(status_code=404, detail="Not found")
    if data.department is not None:
        agenda.department = data.department
    if data.content is not None:
        agenda.content = data.content
    if data.agenda_type is not None:
        agenda.agenda_type = data.agenda_type
    if data.presenter_name is not None:
        agenda.presenter_name = data.presenter_name
    if data.duration_minutes is not None:
        agenda.duration_minutes = data.duration_minutes
    if data.order_num is not None:
        agenda.order_num = data.order_num
    if data.purpose is not None:
        agenda.purpose = data.purpose
    if data.due_date is not None:
        agenda.due_date = data.due_date
    if data.related_meeting is not None:
        agenda.related_meeting = data.related_meeting
    db.commit()
    db.refresh(agenda)
    return agenda


@router.delete("/meetings/{meeting_id}/agendas/{agenda_id}")
def delete_agenda(
    meeting_id: int,
    agenda_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    agenda = db.query(models.Agenda).filter(
        models.Agenda.id == agenda_id,
        models.Agenda.meeting_id == meeting_id,
    ).first()
    if not agenda:
        raise HTTPException(status_code=404, detail="Not found")
    db.delete(agenda)
    db.commit()
    return {"ok": True}


@router.post("/meetings/{meeting_id}/agendas/{agenda_id}/confirm", response_model=schemas.AgendaOut)
async def confirm_agenda(
    meeting_id: int,
    agenda_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    role = _get_member_role(db, meeting_id, current_user.id)
    if role != "admin":
        raise HTTPException(status_code=403, detail="Admin만 확정할 수 있습니다.")

    agenda = db.query(models.Agenda).filter(
        models.Agenda.id == agenda_id,
        models.Agenda.meeting_id == meeting_id,
    ).first()
    if not agenda:
        raise HTTPException(status_code=404, detail="Not found")

    agenda.status = "confirmed"
    agenda.agenda_type = "scheduled"
    agenda.confirmed_at = datetime.utcnow()
    agenda.confirmed_by = current_user.id

    # Notify all presenters
    presenters = db.query(models.MeetingMember).filter(
        models.MeetingMember.meeting_id == meeting_id,
        models.MeetingMember.role == "presenter",
    ).all()
    for p in presenters:
        create_notification(
            db,
            user_id=p.user_id,
            type="agenda_confirmed",
            message=f"새 아젠다가 확정되었습니다: {agenda.content[:50]}",
            ref_id=meeting_id,
            ref_type="meeting",
        )

    # Save tacit event
    meeting = db.query(models.Meeting).filter(models.Meeting.id == meeting_id).first()
    event = models.TacitEvent(
        event_type="agenda_confirmed",
        meeting_id=meeting_id,
        meeting_type=meeting.purpose[:50] if meeting.purpose else None,
        payload={"agenda_id": agenda_id, "content": agenda.content, "department": agenda.department},
        actor_id=current_user.id,
    )
    db.add(event)
    db.commit()
    db.refresh(agenda)

    await manager.broadcast_meeting(meeting_id, {"type": "agenda_updated", "agenda": {
        "id": agenda.id, "status": agenda.status, "confirmed_at": str(agenda.confirmed_at)
    }})
    return agenda


@router.post("/meetings/{meeting_id}/agendas/{agenda_id}/close", response_model=schemas.AgendaOut)
async def close_agenda(
    meeting_id: int,
    agenda_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    role = _get_member_role(db, meeting_id, current_user.id)
    if role != "admin":
        raise HTTPException(status_code=403, detail="Admin만 마감할 수 있습니다.")
    agenda = db.query(models.Agenda).filter(
        models.Agenda.id == agenda_id,
        models.Agenda.meeting_id == meeting_id,
    ).first()
    if not agenda:
        raise HTTPException(status_code=404, detail="Not found")
    agenda.agenda_type = "closed"
    db.commit()
    db.refresh(agenda)
    await manager.broadcast_meeting(meeting_id, {"type": "agenda_updated", "agenda": {
        "id": agenda.id, "agenda_type": agenda.agenda_type
    }})
    return agenda


@router.post("/meetings/{meeting_id}/agendas/{agenda_id}/mark-tbd", response_model=schemas.AgendaOut)
async def mark_agenda_tbd(
    meeting_id: int,
    agenda_id: int,
    data: dict = Body(default={}),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """아젠다를 TBD(미결) 상태로 표시 — Admin만 가능"""
    role = _get_member_role(db, meeting_id, current_user.id)
    if role != "admin":
        raise HTTPException(status_code=403, detail="Admin만 TBD 처리할 수 있습니다.")

    agenda = db.query(models.Agenda).filter(
        models.Agenda.id == agenda_id,
        models.Agenda.meeting_id == meeting_id,
    ).first()
    if not agenda:
        raise HTTPException(status_code=404, detail="Not found")

    agenda.status = "tbd"
    db.commit()
    db.refresh(agenda)

    await manager.broadcast_meeting(meeting_id, {"type": "agenda_updated", "agenda": {
        "id": agenda.id, "status": agenda.status,
    }})
    return agenda


@router.get("/meetings/{meeting_id}/agendas/assigned", response_model=List[schemas.AgendaOut])
def assigned_agendas(
    meeting_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return db.query(models.Agenda).filter(
        models.Agenda.meeting_id == meeting_id,
        models.Agenda.status == "confirmed",
    ).all()
