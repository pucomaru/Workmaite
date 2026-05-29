from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from sqlalchemy.orm import Session, joinedload
import os
import models, schemas
from database import get_db
from auth import get_current_user
from notifications import create_notification
from neo4j_sync import (
    sync_meeting,
    sync_meeting_member,
    sync_user,
    delete_meeting,
    delete_meeting_member,
    update_meeting_member_role,
)

router = APIRouter(prefix="/api", tags=["meetings"])


STRATEGIC_DEPT = "전략기획팀"

def _is_strategic(user: models.User) -> bool:
    return (user.department or "").strip() == STRATEGIC_DEPT

def _my_role_in(user_id: int, meeting_id: int, db: Session):
    m = db.query(models.MeetingMember).filter(
        models.MeetingMember.user_id == user_id,
        models.MeetingMember.meeting_id == meeting_id,
    ).first()
    return m.role if m else None


@router.get("/meetings")
def list_meetings(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if _is_strategic(current_user):
        meetings = db.query(models.Meeting).order_by(models.Meeting.created_at.desc()).all()
    else:
        member_rows = db.query(models.MeetingMember).filter(
            models.MeetingMember.user_id == current_user.id
        ).all()
        meeting_ids = [r.meeting_id for r in member_rows]
        meetings = db.query(models.Meeting).filter(models.Meeting.id.in_(meeting_ids)).all()

    result = []
    for m in meetings:
        role = _my_role_in(current_user.id, m.id, db)
        result.append({
            "id": m.id, "title": m.title, "purpose": m.purpose,
            "start_date": m.start_date, "end_date": m.end_date,
            "status": m.status, "guidelines": m.guidelines,
            "meeting_type": m.meeting_type,
            "parent_id": m.parent_id,
            "created_by": m.created_by, "created_at": m.created_at,
            "my_role": role,
        })
    return result


@router.post("/meetings", response_model=schemas.MeetingOut)
async def create_meeting(
    data: schemas.MeetingCreate,
    background_tasks: BackgroundTasks,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    meeting = models.Meeting(
        title=data.title,
        purpose=data.purpose,
        start_date=data.start_date,
        end_date=data.end_date,
        meeting_type=data.meeting_type,
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

    # Neo4j 동기화 (백그라운드)
    async def _sync():
        await sync_meeting(
            meeting_id=meeting.id,
            title=meeting.title,
            purpose=meeting.purpose,
            status=str(meeting.status or "ACTIVE"),
            meeting_type=str(getattr(meeting, "meeting_type", None) or getattr(meeting, "type", None) or ""),
        )
        await sync_user(
            user_id=current_user.id,
            name=current_user.name,
            email=current_user.email,
            company=current_user.company,
            department=current_user.department,
            position=current_user.position,
        )
        await sync_meeting_member(meeting_id=meeting.id, user_id=current_user.id, role="ADMIN")
    background_tasks.add_task(_sync)
    return meeting


@router.get("/meetings/{meeting_id}")
def get_meeting(
    meeting_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    meeting = db.query(models.Meeting).filter(models.Meeting.id == meeting_id).first()
    if not meeting:
        raise HTTPException(status_code=404, detail="회의체를 찾을 수 없습니다.")
    if not _is_strategic(current_user):
        if _my_role_in(current_user.id, meeting_id, db) is None:
            raise HTTPException(status_code=403, detail="접근 권한이 없습니다.")
    role = _my_role_in(current_user.id, meeting_id, db)
    return {
        "id": meeting.id, "title": meeting.title, "purpose": meeting.purpose,
        "start_date": meeting.start_date, "end_date": meeting.end_date,
        "status": meeting.status, "guidelines": meeting.guidelines,
        "created_by": meeting.created_by, "created_at": meeting.created_at,
        "my_role": role,
    }


@router.patch("/meetings/{meeting_id}")
async def update_meeting(
    meeting_id: int,
    data: dict,
    background_tasks: BackgroundTasks,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    meeting = db.query(models.Meeting).filter(models.Meeting.id == meeting_id).first()
    if not meeting:
        raise HTTPException(status_code=404, detail="Not found")
    if "title" in data or "status" in data:
        member = db.query(models.MeetingMember).filter(
            models.MeetingMember.meeting_id == meeting_id,
            models.MeetingMember.user_id == current_user.id,
        ).first()
        if not member or member.role != "admin":
            raise HTTPException(status_code=403, detail="관리자만 수정할 수 있습니다.")
    if "title" in data:      meeting.title = data["title"]
    if "status" in data:
        meeting.status = data["status"]
        if data["status"] == "ended" and not meeting.end_date:
            from datetime import datetime
            meeting.end_date = datetime.utcnow()
    if "purpose" in data:    meeting.purpose = data["purpose"]
    if "start_date" in data: meeting.start_date = data["start_date"]
    if "end_date" in data:   meeting.end_date = data["end_date"]
    if "guidelines" in data: meeting.guidelines = data["guidelines"]
    if "meeting_type" in data: meeting.meeting_type = data["meeting_type"]
    db.commit()
    db.refresh(meeting)

    # Neo4j 동기화 (백그라운드)
    background_tasks.add_task(
        sync_meeting,
        meeting_id=meeting.id,
        title=meeting.title,
        purpose=meeting.purpose,
        status=str(meeting.status or "ACTIVE"),
        meeting_type=str(getattr(meeting, "meeting_type", None) or getattr(meeting, "type", None) or ""),
    )
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
async def add_member(
    meeting_id: int,
    data: schemas.MeetingMemberAdd,
    background_tasks: BackgroundTasks,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    my_role = _my_role_in(current_user.id, meeting_id, db)
    if my_role != "admin":
        raise HTTPException(status_code=403, detail="간사만 구성원을 추가할 수 있습니다.")
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
        db, user_id=data.user_id, type="meeting_invite",
        message=f"'{meeting.title}' 회의체에 초대되었습니다.",
        ref_id=meeting_id, ref_type="meeting",
    )
    db.commit()

    # Neo4j 동기화 (백그라운드): Person 노드 보장 후 관계 생성
    added_user = db.query(models.User).filter(models.User.id == data.user_id).first()
    if added_user:
        async def _sync_member():
            await sync_user(
                user_id=added_user.id,
                name=added_user.name,
                email=added_user.email,
                company=added_user.company,
                department=added_user.department,
                position=added_user.position,
            )
            await sync_meeting_member(
                meeting_id=meeting_id,
                user_id=added_user.id,
                role=data.role.upper(),
            )
        background_tasks.add_task(_sync_member)
    return member


@router.patch("/meetings/{meeting_id}/members/{member_id}")
async def update_member_role(
    meeting_id: int,
    member_id: int,
    data: dict,
    background_tasks: BackgroundTasks,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    my_role = _my_role_in(current_user.id, meeting_id, db)
    if my_role != "admin":
        raise HTTPException(status_code=403, detail="간사만 역할을 변경할 수 있습니다.")
    member = db.query(models.MeetingMember).filter(
        models.MeetingMember.id == member_id,
        models.MeetingMember.meeting_id == meeting_id,
    ).first()
    if not member:
        raise HTTPException(status_code=404, detail="Not found")
    if "role" in data:
        member.role = data["role"]
    db.commit()

    # Neo4j 동기화 (기존 관계 삭제 후 새 역할로 재생성)
    background_tasks.add_task(
        update_meeting_member_role,
        meeting_id=meeting_id,
        user_id=member.user_id,
        new_role=str(data.get("role", member.role)).upper(),
    )
    return member


@router.delete("/meetings/{meeting_id}/members/{member_id}")
async def remove_member(
    meeting_id: int,
    member_id: int,
    background_tasks: BackgroundTasks,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    my_role = _my_role_in(current_user.id, meeting_id, db)
    target = db.query(models.MeetingMember).filter(
        models.MeetingMember.id == member_id,
        models.MeetingMember.meeting_id == meeting_id,
    ).first()
    if not target:
        raise HTTPException(status_code=404, detail="Not found")
    if target.user_id != current_user.id and my_role != "admin":
        raise HTTPException(status_code=403, detail="간사만 구성원을 제거할 수 있습니다.")

    removed_user = db.query(models.User).filter(models.User.id == target.user_id).first()
    db.delete(target)
    db.commit()

    # Neo4j 동기화 (백그라운드): pg_id 기반으로 관계 삭제
    if removed_user:
        background_tasks.add_task(
            delete_meeting_member,
            meeting_id=meeting_id,
            user_id=removed_user.id,
        )
    return {"ok": True}


@router.delete("/meetings/{meeting_id}")
async def delete_meeting(
    meeting_id: int,
    background_tasks: BackgroundTasks,
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

    # Neo4j 동기화 (백그라운드): :Meeting {pg_id} DETACH DELETE
    background_tasks.add_task(delete_meeting, meeting_id=meeting_id)
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
    return [{"id": u.id, "name": u.name, "employee_id": u.employee_id, "email": u.employee_id, "department": u.department, "organization": u.organization, "position": u.position} for u in users]


@router.get("/users/all")
def all_users(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    users = db.query(models.User).order_by(models.User.name).all()
    result = []
    for u in users:
        meetings = []
        for mm in u.meeting_members:
            meetings.append({"id": mm.meeting_id, "member_id": mm.id, "title": mm.meeting.title if mm.meeting else "", "role": mm.role})
        result.append({
            "id": u.id,
            "name": u.name,
            "email": u.employee_id,
            "employee_id": u.employee_id,
            "department": u.department,
            "organization": u.organization,
            "position": u.position,
            "meetings": meetings,
        })
    return result


@router.patch("/users/{user_id}")
def update_user(
    user_id: int,
    data: dict,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Not found")
    if "name" in data and data["name"] is not None:
        user.name = data["name"]
    if "organization" in data:
        user.organization = data["organization"] if data["organization"] else None
    if "department" in data:
        user.department = data["department"] if data["department"] else None
    if "position" in data:
        user.position = data["position"] if data["position"] else None
    db.commit()
    db.refresh(user)
    return {"id": user.id, "name": user.name, "organization": user.organization, "department": user.department, "position": user.position}


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
