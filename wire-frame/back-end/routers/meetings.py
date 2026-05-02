from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, joinedload
import models, schemas
from database import get_db
from auth import get_current_user
from notifications import create_notification

router = APIRouter(prefix="/api", tags=["meetings"])


@router.get("/meetings", response_model=List[schemas.MeetingOut])
def list_meetings(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    member_rows = db.query(models.MeetingMember).filter(
        models.MeetingMember.user_id == current_user.id
    ).all()
    meeting_ids = [r.meeting_id for r in member_rows]
    return db.query(models.Meeting).filter(models.Meeting.id.in_(meeting_ids)).all()


@router.post("/meetings", response_model=schemas.MeetingOut)
def create_meeting(
    data: schemas.MeetingCreate,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    meeting = models.Meeting(
        title=data.title,
        purpose=data.purpose,
        start_date=data.start_date,
        end_date=data.end_date,
        created_by=current_user.id,
    )
    db.add(meeting)
    db.flush()
    member = models.MeetingMember(meeting_id=meeting.id, user_id=current_user.id, role="admin")
    db.add(member)
    loop = models.MeetingLoop(meeting_id=meeting.id, loop_number=1)
    db.add(loop)
    db.commit()
    db.refresh(meeting)
    return meeting


@router.get("/meetings/{meeting_id}", response_model=schemas.MeetingOut)
def get_meeting(
    meeting_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    meeting = db.query(models.Meeting).filter(models.Meeting.id == meeting_id).first()
    if not meeting:
        raise HTTPException(status_code=404, detail="회의체를 찾을 수 없습니다.")
    return meeting


@router.patch("/meetings/{meeting_id}")
def update_meeting(
    meeting_id: int,
    data: dict,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    meeting = db.query(models.Meeting).filter(models.Meeting.id == meeting_id).first()
    if not meeting:
        raise HTTPException(status_code=404, detail="Not found")
    # 제목 수정 및 종료는 관리자만 가능
    if "title" in data or "status" in data:
        member = db.query(models.MeetingMember).filter(
            models.MeetingMember.meeting_id == meeting_id,
            models.MeetingMember.user_id == current_user.id,
        ).first()
        if not member or member.role != "admin":
            raise HTTPException(status_code=403, detail="관리자만 수정할 수 있습니다.")
    if "title" in data:
        meeting.title = data["title"]
    if "status" in data:
        meeting.status = data["status"]
        if data["status"] == "ended" and not meeting.end_date:
            from datetime import datetime
            meeting.end_date = datetime.utcnow()
    if "purpose" in data:
        meeting.purpose = data["purpose"]
    if "start_date" in data:
        meeting.start_date = data["start_date"]
    if "end_date" in data:
        meeting.end_date = data["end_date"]
    db.commit()
    db.refresh(meeting)
    return meeting


@router.get("/meetings/{meeting_id}/members", response_model=List[schemas.MeetingMemberOut])
def get_members(
    meeting_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return (
        db.query(models.MeetingMember)
        .options(joinedload(models.MeetingMember.user))
        .filter(models.MeetingMember.meeting_id == meeting_id)
        .all()
    )


@router.post("/meetings/{meeting_id}/members")
def add_member(
    meeting_id: int,
    data: schemas.MeetingMemberAdd,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    existing = db.query(models.MeetingMember).filter(
        models.MeetingMember.meeting_id == meeting_id,
        models.MeetingMember.user_id == data.user_id,
    ).first()
    if existing:
        existing.role = data.role
        db.commit()
        return existing

    member = models.MeetingMember(meeting_id=meeting_id, user_id=data.user_id, role=data.role)
    db.add(member)
    db.flush()

    meeting = db.query(models.Meeting).filter(models.Meeting.id == meeting_id).first()
    create_notification(
        db,
        user_id=data.user_id,
        type="meeting_invite",
        message=f"'{meeting.title}' 회의체에 초대되었습니다.",
        ref_id=meeting_id,
        ref_type="meeting",
    )
    db.commit()
    return member


@router.patch("/meetings/{meeting_id}/members/{member_id}")
def update_member_role(
    meeting_id: int,
    member_id: int,
    data: dict,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    member = db.query(models.MeetingMember).filter(
        models.MeetingMember.id == member_id,
        models.MeetingMember.meeting_id == meeting_id,
    ).first()
    if not member:
        raise HTTPException(status_code=404, detail="Not found")
    if "role" in data:
        member.role = data["role"]
    db.commit()
    return member


@router.delete("/meetings/{meeting_id}/members/{member_id}")
def remove_member(
    meeting_id: int,
    member_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    member = db.query(models.MeetingMember).filter(
        models.MeetingMember.id == member_id,
        models.MeetingMember.meeting_id == meeting_id,
    ).first()
    if not member:
        raise HTTPException(status_code=404, detail="Not found")
    db.delete(member)
    db.commit()
    return {"ok": True}


@router.delete("/meetings/{meeting_id}")
def delete_meeting(
    meeting_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    meeting = db.query(models.Meeting).filter(models.Meeting.id == meeting_id).first()
    if not meeting:
        raise HTTPException(status_code=404, detail="Not found")
    member = db.query(models.MeetingMember).filter(
        models.MeetingMember.meeting_id == meeting_id,
        models.MeetingMember.user_id == current_user.id,
    ).first()
    if not member or member.role != "admin":
        raise HTTPException(status_code=403, detail="관리자만 삭제할 수 있습니다.")

    # 연관 데이터 삭제
    session_ids = [
        s.id for s in db.query(models.MeetingSession.id)
        .join(models.MeetingLoop, models.MeetingSession.loop_id == models.MeetingLoop.id)
        .filter(models.MeetingLoop.meeting_id == meeting_id).all()
    ]
    if session_ids:
        db.query(models.Minutes).filter(models.Minutes.session_id.in_(session_ids)).delete(synchronize_session=False)
        db.query(models.ChatMessage).filter(
            models.ChatMessage.context_type == "room",
            models.ChatMessage.context_id.in_(session_ids),
        ).delete(synchronize_session=False)
        db.query(models.MeetingSession).filter(models.MeetingSession.id.in_(session_ids)).delete(synchronize_session=False)

    db.query(models.MeetingLoop).filter(models.MeetingLoop.meeting_id == meeting_id).delete(synchronize_session=False)
    db.query(models.Report).filter(models.Report.meeting_id == meeting_id).delete(synchronize_session=False)
    db.query(models.Agenda).filter(models.Agenda.meeting_id == meeting_id).delete(synchronize_session=False)
    db.query(models.Todo).filter(models.Todo.meeting_id == meeting_id).delete(synchronize_session=False)
    db.query(models.Notification).filter(models.Notification.ref_id == meeting_id, models.Notification.ref_type == "meeting").delete(synchronize_session=False)
    db.query(models.MeetingMember).filter(models.MeetingMember.meeting_id == meeting_id).delete(synchronize_session=False)
    db.delete(meeting)
    db.commit()
    return {"ok": True}


@router.get("/users/search")
def search_users(
    q: str = Query(""),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    users = db.query(models.User).filter(
        (models.User.name.contains(q)) | (models.User.employee_id.contains(q))
    ).limit(20).all()
    return [{"id": u.id, "name": u.name, "employee_id": u.employee_id, "department": u.department} for u in users]


@router.get("/meetings/{meeting_id}/my-role")
def my_role(
    meeting_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    member = db.query(models.MeetingMember).filter(
        models.MeetingMember.meeting_id == meeting_id,
        models.MeetingMember.user_id == current_user.id,
    ).first()
    if not member:
        raise HTTPException(status_code=403, detail="접근 권한이 없습니다.")
    return {"role": member.role}
