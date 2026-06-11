from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from sqlalchemy.orm import Session, joinedload
import os
import models, schemas
from database import get_db
from auth import get_current_user
from neo4j_sync import (
    sync_meeting,
    sync_user,
    sync_meeting_member,
    delete_meeting_member,
    update_meeting_member_role,
    delete_meeting as neo4j_delete_meeting,
)
import logging

_logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["meetings"])


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
            "id": m.id, "title": m.title, "description": m.description,
            "start_date": m.start_date, "end_date": m.end_date,
            "status": m.status, "guidelines": m.guidelines,
            "meeting_type": m.type,
            "parent_id": None,
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
        description=data.description,
        guidelines=data.guidelines,
        type=data.meeting_type,
        start_date=data.start_date,
        end_date=data.end_date,
        created_by=current_user.id,
    )
    db.add(meeting)
    db.flush()
    member = models.MeetingMember(meeting_id=meeting.id, user_id=current_user.id, role="admin")
    db.add(member)
    db.commit()
    db.refresh(meeting)

    # Neo4j 동기화 (백그라운드)
    async def _sync():
        await sync_meeting(
            meeting_id=meeting.id,
            title=meeting.title,
            description=meeting.description,
            guidelines=meeting.guidelines,
            status=str(meeting.status or "active"),
            meeting_type=str(meeting.type or ""),
            start_date=meeting.start_date.isoformat() if meeting.start_date else None,
            end_date=meeting.end_date.isoformat() if meeting.end_date else None,
            created_by=meeting.created_by,
            created_at=meeting.created_at.isoformat() if meeting.created_at else None,
        )
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
        "id": meeting.id, "title": meeting.title, "description": meeting.description,
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
    if "description" in data: meeting.description = data["description"]
    if "start_date" in data: meeting.start_date = data["start_date"]
    if "end_date" in data:   meeting.end_date = data["end_date"]
    if "guidelines" in data: meeting.guidelines = data["guidelines"]
    if "meeting_type" in data: meeting.type = data["meeting_type"]
    db.commit()
    db.refresh(meeting)

    # Neo4j 동기화 (백그라운드)
    background_tasks.add_task(
        sync_meeting,
        meeting_id=meeting.id,
        title=meeting.title,
        description=meeting.description,
        guidelines=meeting.guidelines,
        status=str(meeting.status or "active"),
        meeting_type=str(meeting.type or ""),
        start_date=meeting.start_date.isoformat() if meeting.start_date else None,
        end_date=meeting.end_date.isoformat() if meeting.end_date else None,
        created_by=meeting.created_by,
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
        background_tasks.add_task(update_meeting_member_role, meeting_id, data.user_id, data.role)
        return existing

    member = models.MeetingMember(meeting_id=meeting_id, user_id=data.user_id, role=data.role)
    db.add(member)
    db.flush()

    added_user = db.query(models.User).filter(models.User.id == data.user_id).first()
    db.commit()

    if added_user:
        async def _sync_member():
            await sync_user(
                user_id=added_user.id, name=added_user.name, email=added_user.email,
                company=added_user.company, department=added_user.department,
                position=added_user.position,
            )
            await sync_meeting_member(meeting_id=meeting_id, user_id=added_user.id, role=data.role)
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
    if "role" in data:
        background_tasks.add_task(update_meeting_member_role, meeting_id, member.user_id, data["role"])
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

    removed_user_id = target.user_id
    db.delete(target)
    db.commit()
    background_tasks.add_task(delete_meeting_member, meeting_id, removed_user_id)
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

    # ── 1. ID 선수집 ──────────────────────────────────────────────
    session_ids    = [r.id for r in db.query(models.MeetingSession.id).filter(models.MeetingSession.meeting_id == meeting_id).all()]
    report_ids     = [r.id for r in db.query(models.Report.id).filter(models.Report.meeting_id == meeting_id).all()]
    agent_log_ids  = [r.id for r in db.query(models.AgentLog.id).filter(models.AgentLog.meeting_id == meeting_id).all()]

    # ── 2. 세션 하위 (session_id FK) ─────────────────────────────
    if session_ids:
        db.query(models.SttSegment).filter(models.SttSegment.session_id.in_(session_ids)).delete(synchronize_session=False)
        db.query(models.SessionMember).filter(models.SessionMember.session_id.in_(session_ids)).delete(synchronize_session=False)
        db.query(models.Minutes).filter(models.Minutes.session_id.in_(session_ids)).delete(synchronize_session=False)

    # ── 3. 채팅 메시지 (meeting_id 전체) ─────────────────────────
    db.query(models.ChatMessage).filter(models.ChatMessage.meeting_id == meeting_id).delete(synchronize_session=False)

    # ── 4. 세션 ──────────────────────────────────────────────────
    if session_ids:
        db.query(models.MeetingSession).filter(models.MeetingSession.id.in_(session_ids)).delete(synchronize_session=False)

    # ── 5. 보고서 하위 (report_id FK) ────────────────────────────
    if report_ids:
        db.query(models.HitlReview).filter(models.HitlReview.target_type == "report", models.HitlReview.target_id.in_(report_ids)).delete(synchronize_session=False)
        db.query(models.ReportScore).filter(models.ReportScore.report_id.in_(report_ids)).delete(synchronize_session=False)

    # ── 6. 보고서 ─────────────────────────────────────────────────
    db.query(models.Report).filter(models.Report.meeting_id == meeting_id).delete(synchronize_session=False)

    # ── 7. AgentLog 하위 (agent_log_id FK) ───────────────────────
    if agent_log_ids:
        db.query(models.TokenUsageLog).filter(models.TokenUsageLog.agent_log_id.in_(agent_log_ids)).delete(synchronize_session=False)
        db.query(models.HitlReview).filter(models.HitlReview.agent_log_id.in_(agent_log_ids)).delete(synchronize_session=False)

    # ── 8. AgentLog ───────────────────────────────────────────────
    db.query(models.AgentLog).filter(models.AgentLog.meeting_id == meeting_id).delete(synchronize_session=False)

    # ── 9. 아젠다 / 멤버 / 회의체 ────────────────────────────────
    db.query(models.Agenda).filter(models.Agenda.meeting_id == meeting_id).delete(synchronize_session=False)
    db.query(models.MeetingMember).filter(models.MeetingMember.meeting_id == meeting_id).delete(synchronize_session=False)
    db.delete(meeting)
    db.commit()

    # Neo4j 동기화 (백그라운드)
    background_tasks.add_task(neo4j_delete_meeting, meeting_id=meeting_id)
    return {"ok": True}


@router.get("/users/search")
def search_users(
    q: str = Query(""),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    users = db.query(models.User).filter(
        models.User.name.contains(q)
    ).limit(20).all()
    return [{"id": u.id, "name": u.name, "email": u.email, "department": u.department, "company": u.company, "position": u.position} for u in users]


@router.get("/users/all")
def all_users(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    users = db.query(models.User).order_by(models.User.name).all()
    result = []
    for u in users:
        member_rows = db.query(models.MeetingMember).filter(models.MeetingMember.user_id == u.id).all()
        meeting_ids = [mm.meeting_id for mm in member_rows]
        meetings_map = {
            m.id: m for m in db.query(models.Meeting).filter(models.Meeting.id.in_(meeting_ids)).all()
        } if meeting_ids else {}
        meetings = [
            {"id": mm.meeting_id, "member_id": mm.id, "title": meetings_map.get(mm.meeting_id, None) and meetings_map[mm.meeting_id].title or "", "role": mm.role}
            for mm in member_rows
        ]
        result.append({
            "id": u.id,
            "name": u.name,
            "email": u.email,
            "department": u.department,
            "company": u.company,
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
    if "company" in data:
        user.company = data["company"] if data["company"] else None
    if "department" in data:
        user.department = data["department"] if data["department"] else None
    if "position" in data:
        user.position = data["position"] if data["position"] else None
    db.commit()
    db.refresh(user)
    return {"id": user.id, "name": user.name, "company": user.company, "department": user.department, "position": user.position}


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


# ── /api/ai prefix 라우터 (Ingress: /api/ai → FastAPI) ───────────────────────
ai_router = APIRouter(prefix="/api/ai", tags=["ai"])


@ai_router.get("/company/members")
def company_members(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """조직 탭 데이터: 현재 사용자가 속한 회의체의 구성원만 PostgreSQL 기준으로 반환한다.

    데이터 보기 권한 = '본인이 속한 회의체'. 권한 밖의 사용자/회의체는 노출하지 않는다.
    """
    # 1) 본인이 속한 회의체 id 목록 (PostgreSQL)
    my_membership = db.query(models.MeetingMember).filter(
        models.MeetingMember.user_id == current_user.id
    ).all()
    my_meeting_ids = [mm.meeting_id for mm in my_membership]
    if not my_meeting_ids:
        return {"meetings": [], "members": []}

    # 2) 해당 회의체 메타 (제목 등) + 본인 역할
    my_role_map = {mm.meeting_id: mm.role for mm in my_membership}
    meetings_map = {
        m.id: m
        for m in db.query(models.Meeting).filter(models.Meeting.id.in_(my_meeting_ids)).all()
    }
    meetings_list = [
        {"id": m.id, "title": m.title, "my_role": my_role_map.get(m.id)}
        for m in sorted(meetings_map.values(), key=lambda x: x.title or "")
    ]

    # 3) 해당 회의체들의 전체 멤버십 행
    member_rows = db.query(models.MeetingMember).filter(
        models.MeetingMember.meeting_id.in_(my_meeting_ids)
    ).all()

    # 4) user_id 별로 참여 회의체 묶기
    user_meetings: dict[int, list] = {}
    for mm in member_rows:
        meeting = meetings_map.get(mm.meeting_id)
        user_meetings.setdefault(mm.user_id, []).append({
            "id": mm.meeting_id,
            "member_id": mm.id,
            "title": meeting.title if meeting else "",
            "role": mm.role,
        })

    user_ids = list(user_meetings.keys())
    users_map = {
        u.id: u
        for u in db.query(models.User).filter(models.User.id.in_(user_ids)).all()
    }

    members = []
    for uid, meetings in user_meetings.items():
        u = users_map.get(uid)
        if not u:
            continue
        members.append({
            "id": u.id,
            "name": u.name,
            "email": u.email,
            "department": u.department,
            "company": u.company,
            "position": u.position,
            "meetings": meetings,
        })
    members.sort(key=lambda r: r["name"] or "")

    return {"meetings": meetings_list, "members": members}


@ai_router.delete("/meetings/{meeting_id}/members/{member_id}")
async def ai_remove_member(
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

    removed_user_id = target.user_id
    db.delete(target)
    db.commit()
    background_tasks.add_task(delete_meeting_member, meeting_id, removed_user_id)
    return {"ok": True}


@ai_router.patch("/users/{user_id}")
async def ai_update_user(
    user_id: int,
    data: dict,
    background_tasks: BackgroundTasks,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Not found")
    if "name" in data and data["name"] is not None:
        user.name = data["name"]
    if "company" in data:
        user.company = data["company"] if data["company"] else None
    if "department" in data:
        user.department = data["department"] if data["department"] else None
    if "position" in data:
        user.position = data["position"] if data["position"] else None
    db.commit()
    db.refresh(user)
    background_tasks.add_task(
        sync_user,
        user_id=user.id, name=user.name, email=user.email,
        company=user.company, department=user.department, position=user.position,
    )
    return {"id": user.id, "name": user.name, "company": user.company, "department": user.department, "position": user.position}


@ai_router.delete("/meetings/{meeting_id}")
async def ai_delete_meeting(
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

    # ── 1. ID 선수집 ──────────────────────────────────────────────
    session_ids    = [r.id for r in db.query(models.MeetingSession.id).filter(models.MeetingSession.meeting_id == meeting_id).all()]
    report_ids     = [r.id for r in db.query(models.Report.id).filter(models.Report.meeting_id == meeting_id).all()]
    agent_log_ids  = [r.id for r in db.query(models.AgentLog.id).filter(models.AgentLog.meeting_id == meeting_id).all()]

    # ── 2. 세션 하위 (session_id FK) ─────────────────────────────
    if session_ids:
        db.query(models.SttSegment).filter(models.SttSegment.session_id.in_(session_ids)).delete(synchronize_session=False)
        db.query(models.SessionMember).filter(models.SessionMember.session_id.in_(session_ids)).delete(synchronize_session=False)
        db.query(models.Minutes).filter(models.Minutes.session_id.in_(session_ids)).delete(synchronize_session=False)

    # ── 3. 채팅 메시지 (meeting_id 전체) ─────────────────────────
    db.query(models.ChatMessage).filter(models.ChatMessage.meeting_id == meeting_id).delete(synchronize_session=False)

    # ── 4. 세션 ──────────────────────────────────────────────────
    if session_ids:
        db.query(models.MeetingSession).filter(models.MeetingSession.id.in_(session_ids)).delete(synchronize_session=False)

    # ── 5. 보고서 하위 (report_id FK) ────────────────────────────
    if report_ids:
        db.query(models.HitlReview).filter(models.HitlReview.target_type == "report", models.HitlReview.target_id.in_(report_ids)).delete(synchronize_session=False)
        db.query(models.ReportScore).filter(models.ReportScore.report_id.in_(report_ids)).delete(synchronize_session=False)

    # ── 6. 보고서 ─────────────────────────────────────────────────
    db.query(models.Report).filter(models.Report.meeting_id == meeting_id).delete(synchronize_session=False)

    # ── 7. AgentLog 하위 (agent_log_id FK) ───────────────────────
    if agent_log_ids:
        db.query(models.TokenUsageLog).filter(models.TokenUsageLog.agent_log_id.in_(agent_log_ids)).delete(synchronize_session=False)
        db.query(models.HitlReview).filter(models.HitlReview.agent_log_id.in_(agent_log_ids)).delete(synchronize_session=False)

    # ── 8. AgentLog ───────────────────────────────────────────────
    db.query(models.AgentLog).filter(models.AgentLog.meeting_id == meeting_id).delete(synchronize_session=False)

    # ── 9. 아젠다 / 멤버 / 회의체 ────────────────────────────────
    db.query(models.Agenda).filter(models.Agenda.meeting_id == meeting_id).delete(synchronize_session=False)
    db.query(models.MeetingMember).filter(models.MeetingMember.meeting_id == meeting_id).delete(synchronize_session=False)
    db.delete(meeting)
    db.commit()

    background_tasks.add_task(neo4j_delete_meeting, meeting_id=meeting_id)
    return {"ok": True}
