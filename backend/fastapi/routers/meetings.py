from typing import List
from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import text
from db import models
from db import schemas
from db.database import get_db
from core.auth import get_current_user
from core.access_guard import (
    require_view,
    require_meeting_edit,
    require_user_update_permission,
    visible_user_ids,
    viewable_meeting_ids,
    is_system_admin,
)
from graphdb.neo4j_sync import (
    sync_meeting,
    sync_user,
    sync_meeting_member,
    delete_meeting_member,
    update_meeting_member_role,
    delete_meeting as neo4j_delete_meeting,
    delete_user as neo4j_delete_user,
    rename_company as neo4j_rename_company,
    rename_department as neo4j_rename_department,
)
import logging

_logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["meetings"])


def _get_or_create_company_id(db: Session, name) -> int | None:
    """회사명으로 companies upsert 후 id 반환 (P1-7② — users.company 문자열 폐기)."""
    if not name or not str(name).strip():
        return None
    name = str(name).strip()
    c = db.query(models.Company).filter(models.Company.name == name).first()
    if not c:
        c = models.Company(name=name)
        db.add(c)
        db.flush()
    return c.id


def _my_role_in(user_id: int, meeting_id: int, db: Session):
    m = (
        db.query(models.MeetingMember)
        .filter(
            models.MeetingMember.user_id == user_id,
            models.MeetingMember.meeting_id == meeting_id,
        )
        .first()
    )
    return m.meeting_role if m else None


@router.get("/meetings")
def list_meetings(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    vids = viewable_meeting_ids(db, current_user)  # None이면 전체(SYSTEM_ADMIN)
    mq = db.query(models.Meeting)
    if vids is not None:
        if not vids:
            return []
        mq = mq.filter(models.Meeting.id.in_(vids))
    meetings = mq.order_by(models.Meeting.created_at.desc()).all()

    result = []
    for m in meetings:
        role = _my_role_in(current_user.id, m.id, db)
        result.append(
            {
                "id": m.id,
                "title": m.title,
                "description": m.description,
                "start_date": m.start_date,
                "end_date": m.end_date,
                "status": m.status,
                "guidelines": m.guidelines,
                "meeting_type": m.type,
                "parent_id": None,
                "created_by": m.created_by,
                "created_at": m.created_at,
                "my_role": role,
            }
        )
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
    member = models.MeetingMember(
        meeting_id=meeting.id, user_id=current_user.id, meeting_role="admin"
    )
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
    require_view(db, current_user, meeting_id)
    role = _my_role_in(current_user.id, meeting_id, db)
    return {
        "id": meeting.id,
        "title": meeting.title,
        "description": meeting.description,
        "start_date": meeting.start_date,
        "end_date": meeting.end_date,
        "status": meeting.status,
        "guidelines": meeting.guidelines,
        "created_by": meeting.created_by,
        "created_at": meeting.created_at,
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
    # 회의체 수정은 간사/회사관리자/시스템관리자만
    require_meeting_edit(db, current_user, meeting_id)
    meeting = db.query(models.Meeting).filter(models.Meeting.id == meeting_id).first()
    if not meeting:
        raise HTTPException(status_code=404, detail="Not found")
    if "title" in data:
        meeting.title = data["title"]
    if "status" in data:
        meeting.status = data["status"]
        if data["status"] == "ended" and not meeting.end_date:
            from datetime import datetime

            meeting.end_date = datetime.utcnow()
    if "description" in data:
        meeting.description = data["description"]
    if "start_date" in data:
        meeting.start_date = data["start_date"]
    if "end_date" in data:
        meeting.end_date = data["end_date"]
    if "guidelines" in data:
        meeting.guidelines = data["guidelines"]
    if "context" in data:
        meeting.context = data["context"]
    if "meeting_type" in data:
        meeting.type = data["meeting_type"]
    db.commit()
    db.refresh(meeting)

    # Neo4j 동기화 (백그라운드)
    background_tasks.add_task(
        sync_meeting,
        meeting_id=meeting.id,
        title=meeting.title,
        description=meeting.description,
        guidelines=meeting.guidelines,
        context=meeting.context,
        status=str(meeting.status or "active"),
        meeting_type=str(meeting.type or ""),
        start_date=meeting.start_date.isoformat() if meeting.start_date else None,
        end_date=meeting.end_date.isoformat() if meeting.end_date else None,
        created_by=meeting.created_by,
    )
    return meeting


@router.get(
    "/meetings/{meeting_id}/members", response_model=List[schemas.MeetingMemberOut]
)
def get_members(
    meeting_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_view(db, current_user, meeting_id)
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
    require_meeting_edit(db, current_user, meeting_id)
    existing = (
        db.query(models.MeetingMember)
        .filter(
            models.MeetingMember.meeting_id == meeting_id,
            models.MeetingMember.user_id == data.user_id,
        )
        .first()
    )
    if existing:
        existing.meeting_role = data.meeting_role
        db.commit()
        background_tasks.add_task(
            update_meeting_member_role, meeting_id, data.user_id, data.meeting_role
        )
        return existing

    member = models.MeetingMember(
        meeting_id=meeting_id, user_id=data.user_id, meeting_role=data.meeting_role
    )
    db.add(member)
    db.flush()

    added_user = db.query(models.User).filter(models.User.id == data.user_id).first()
    db.commit()

    if added_user:

        async def _sync_member():
            await sync_user(
                user_id=added_user.id,
                name=added_user.name,
                email=added_user.email,
                company=added_user.company_name,
                department=added_user.department,
                position=added_user.position,
            )
            await sync_meeting_member(
                meeting_id=meeting_id, user_id=added_user.id, role=data.meeting_role
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
    require_meeting_edit(db, current_user, meeting_id)
    member = (
        db.query(models.MeetingMember)
        .filter(
            models.MeetingMember.id == member_id,
            models.MeetingMember.meeting_id == meeting_id,
        )
        .first()
    )
    if not member:
        raise HTTPException(status_code=404, detail="Not found")
    new_role = data.get("meeting_role", data.get("role"))  # 구 키 role 하위호환
    if new_role is not None:
        member.meeting_role = new_role
    db.commit()
    if new_role is not None:
        background_tasks.add_task(
            update_meeting_member_role, meeting_id, member.user_id, new_role
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
    target = (
        db.query(models.MeetingMember)
        .filter(
            models.MeetingMember.id == member_id,
            models.MeetingMember.meeting_id == meeting_id,
        )
        .first()
    )
    if not target:
        raise HTTPException(status_code=404, detail="Not found")
    # 본인 탈퇴는 허용, 타인 제거는 간사/회사관리자/시스템관리자만
    if target.user_id != current_user.id:
        require_meeting_edit(db, current_user, meeting_id)

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
    # 회의체 삭제는 간사/회사관리자/시스템관리자만
    require_meeting_edit(db, current_user, meeting_id)

    # ── 1. ID 선수집 ──────────────────────────────────────────────
    session_ids = [
        r.id
        for r in db.query(models.MeetingSession.id)
        .filter(models.MeetingSession.meeting_id == meeting_id)
        .all()
    ]
    report_ids = [
        r.id
        for r in db.query(models.Report.id)
        .filter(models.Report.meeting_id == meeting_id)
        .all()
    ]
    agent_log_ids = [
        r.id
        for r in db.query(models.AgentLog.id)
        .filter(models.AgentLog.meeting_id == meeting_id)
        .all()
    ]

    # ── 2. 세션 하위 (session_id FK) ─────────────────────────────
    if session_ids:
        db.query(models.SttSegment).filter(
            models.SttSegment.session_id.in_(session_ids)
        ).delete(synchronize_session=False)
        db.query(models.SessionMember).filter(
            models.SessionMember.session_id.in_(session_ids)
        ).delete(synchronize_session=False)
        db.query(models.Minutes).filter(
            models.Minutes.session_id.in_(session_ids)
        ).delete(synchronize_session=False)

    # ── 3. 채팅 메시지 (meeting_id 전체) ─────────────────────────
    db.query(models.ChatMessage).filter(
        models.ChatMessage.meeting_id == meeting_id
    ).delete(synchronize_session=False)

    # ── 4. 세션 ──────────────────────────────────────────────────
    if session_ids:
        db.query(models.MeetingSession).filter(
            models.MeetingSession.id.in_(session_ids)
        ).delete(synchronize_session=False)

    # ── 5. 보고서 하위 (report_id FK) ────────────────────────────
    if report_ids:
        db.query(models.HitlReview).filter(
            models.HitlReview.report_id.in_(report_ids)
        ).delete(synchronize_session=False)
        db.query(models.ReportScore).filter(
            models.ReportScore.report_id.in_(report_ids)
        ).delete(synchronize_session=False)

    # ── 6. 보고서 ─────────────────────────────────────────────────
    db.query(models.Report).filter(models.Report.meeting_id == meeting_id).delete(
        synchronize_session=False
    )

    # ── 7. AgentLog 하위 (agent_log_id FK) ───────────────────────
    if agent_log_ids:
        db.query(models.TokenUsageLog).filter(
            models.TokenUsageLog.agent_log_id.in_(agent_log_ids)
        ).delete(synchronize_session=False)
        db.query(models.HitlReview).filter(
            models.HitlReview.agent_log_id.in_(agent_log_ids)
        ).delete(synchronize_session=False)

    # ── 8. AgentLog ───────────────────────────────────────────────
    db.query(models.AgentLog).filter(models.AgentLog.meeting_id == meeting_id).delete(
        synchronize_session=False
    )

    # ── 9. 아젠다 / 멤버 / 회의체 ────────────────────────────────
    db.query(models.Agenda).filter(models.Agenda.meeting_id == meeting_id).delete(
        synchronize_session=False
    )
    db.query(models.MeetingMember).filter(
        models.MeetingMember.meeting_id == meeting_id
    ).delete(synchronize_session=False)
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
    visible = visible_user_ids(db, current_user)  # MT-3 디렉터리 스코프
    query = db.query(models.User).filter(
        models.User.name.contains(q),
        models.User.is_active.is_(True),  # 탈퇴 계정 제외(MT-6)
    )
    if visible is not None:
        query = query.filter(models.User.id.in_(visible))
    users = query.limit(20).all()
    return [
        {
            "id": u.id,
            "name": u.name,
            "email": u.email,
            "department": u.department,
            "company": u.company_name,
            "position": u.position,
        }
        for u in users
    ]


@router.get("/users/all")
def all_users(
    limit: int = Query(100, le=500),
    offset: int = Query(0, ge=0),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    visible = visible_user_ids(db, current_user)  # MT-3 디렉터리 스코프
    users_query = (
        db.query(models.User)
        .filter(models.User.is_active.is_(True))  # 탈퇴 계정 제외(MT-6)
        .order_by(models.User.name)
    )
    if visible is not None:
        users_query = users_query.filter(models.User.id.in_(visible))
    users = users_query.offset(offset).limit(limit).all()  # P8-5 페이지네이션

    # 사용자별 개별 쿼리(N+1, PG-6) → 멤버십+회의체 일괄 2쿼리로 교체
    user_ids = [u.id for u in users]
    all_members = (
        (
            db.query(models.MeetingMember)
            .filter(models.MeetingMember.user_id.in_(user_ids))
            .all()
        )
        if user_ids
        else []
    )
    meeting_ids = {mm.meeting_id for mm in all_members}
    titles = (
        {
            m.id: m.title
            for m in db.query(models.Meeting.id, models.Meeting.title)
            .filter(models.Meeting.id.in_(meeting_ids))
            .all()
        }
        if meeting_ids
        else {}
    )
    members_by_user: dict[int, list] = {}
    for mm in all_members:
        members_by_user.setdefault(mm.user_id, []).append(mm)

    result = []
    for u in users:
        meetings = [
            {
                "id": mm.meeting_id,
                "member_id": mm.id,
                "title": titles.get(mm.meeting_id, ""),
                "role": mm.meeting_role,
            }
            for mm in members_by_user.get(u.id, [])
        ]
        result.append(
            {
                "id": u.id,
                "name": u.name,
                "email": u.email,
                "department": u.department,
                "company": u.company_name,
                "company_id": u.company_id,
                "position": u.position,
                "role": u.company_role,  # 역할 변경 UI용 (P1-7②)
                "meetings": meetings,
            }
        )
    return result


@router.patch("/users/{user_id}")
def update_user(
    user_id: int,
    data: dict,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # MT-1: 본인 또는 SYSTEM_ADMIN, 같은 회사 COMPANY_ADMIN만 수정 가능
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Not found")
    require_user_update_permission(current_user, user)
    if "name" in data and data["name"] is not None:
        user.name = data["name"]
    if "company" in data:
        user.company_id = _get_or_create_company_id(db, data["company"])
    if "department" in data:
        user.department = data["department"] if data["department"] else None
    if "position" in data:
        user.position = data["position"] if data["position"] else None
    db.commit()
    db.refresh(user)
    return {
        "id": user.id,
        "name": user.name,
        "company": user.company_name,
        "department": user.department,
        "position": user.position,
    }


@router.get("/meetings/{meeting_id}/my-role")
def my_role(
    meeting_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    member = (
        db.query(models.MeetingMember)
        .filter(
            models.MeetingMember.meeting_id == meeting_id,
            models.MeetingMember.user_id == current_user.id,
        )
        .first()
    )
    if not member:
        raise HTTPException(status_code=403, detail="접근 권한이 없습니다.")
    return {"role": member.meeting_role}


# ── /api/ai prefix 라우터 (Ingress: /api/ai → FastAPI) ───────────────────────
ai_router = APIRouter(prefix="/api/ai", tags=["ai"])


@ai_router.patch("/companies/rename")
async def rename_company_endpoint(
    data: dict,
    background_tasks: BackgroundTasks,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """회사명 변경 — SYSTEM_ADMIN 또는 해당 회사 COMPANY_ADMIN만.

    그래프 회사 노드는 이름으로 식별되므로 old_name으로 회사를 찾는다.
    companies.name 한 행만 바꾸면 users.company_name(파생 property)이 전부 따라온다.
    """
    old_name = (data.get("old_name") or "").strip()
    new_name = (data.get("new_name") or "").strip()
    if not old_name or not new_name:
        raise HTTPException(status_code=400, detail="old_name, new_name이 필요합니다.")
    company = db.query(models.Company).filter(models.Company.name == old_name).first()
    if not company:
        raise HTTPException(status_code=404, detail="회사를 찾을 수 없습니다.")
    # 권한: SYSTEM_ADMIN 또는 같은 회사 COMPANY_ADMIN
    is_co_admin = (
        current_user.company_role == "COMPANY_ADMIN"
        and current_user.company_id == company.id
    )
    if not is_system_admin(current_user) and not is_co_admin:
        raise HTTPException(status_code=403, detail="회사명을 변경할 권한이 없습니다.")
    if old_name == new_name:
        return {"ok": True, "id": company.id, "name": new_name}
    # 중복 검사 (companies.name UNIQUE)
    if (
        db.query(models.Company)
        .filter(models.Company.name == new_name, models.Company.id != company.id)
        .first()
    ):
        raise HTTPException(status_code=409, detail="이미 존재하는 회사명입니다.")
    company.name = new_name
    db.commit()
    background_tasks.add_task(neo4j_rename_company, old_name, new_name)
    return {"ok": True, "id": company.id, "name": new_name}


@ai_router.patch("/departments/rename")
async def rename_department_endpoint(
    data: dict,
    background_tasks: BackgroundTasks,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """부서명 변경 — SYSTEM_ADMIN 또는 해당 회사 COMPANY_ADMIN만.

    부서는 별도 테이블 없이 users.department(문자열)로만 존재하므로
    old_name과 일치하는 users 행의 department를 일괄 변경한다.
    company_name이 주어지면 그 회사 소속으로 한정해 타 회사 동명 부서를 보호한다.
    """
    old_name = (data.get("old_name") or "").strip()
    new_name = (data.get("new_name") or "").strip()
    company_name = (data.get("company_name") or "").strip()
    if not old_name or not new_name:
        raise HTTPException(status_code=400, detail="old_name, new_name이 필요합니다.")

    # 회사 scope 해석 (있으면 company_id로 한정)
    company = None
    if company_name:
        company = (
            db.query(models.Company).filter(models.Company.name == company_name).first()
        )

    # 권한: SYSTEM_ADMIN(전체) 또는 COMPANY_ADMIN(자기 회사에 한해)
    if not is_system_admin(current_user):
        is_co_admin = (
            current_user.company_role == "COMPANY_ADMIN"
            and company is not None
            and current_user.company_id == company.id
        )
        if not is_co_admin:
            raise HTTPException(
                status_code=403, detail="부서명을 변경할 권한이 없습니다."
            )

    if old_name == new_name:
        return {"ok": True, "name": new_name}

    q = db.query(models.User).filter(models.User.department == old_name)
    if company is not None:
        q = q.filter(models.User.company_id == company.id)
    updated = q.update({models.User.department: new_name}, synchronize_session=False)
    db.commit()
    background_tasks.add_task(
        neo4j_rename_department, old_name, new_name, company_name or None
    )
    return {"ok": True, "name": new_name, "updated": updated}


@ai_router.get("/company/members")
def company_members(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """회사 관리 탭 데이터. 역할별 가시 범위(MT-3):
    - SYSTEM_ADMIN: 전체 사용자 (회사 경계 무시)
    - COMPANY_ADMIN: 자기 회사 소속 사용자만
    - 일반 사용자: 본인이 속한 회의체의 구성원만
    """
    # 1) 역할별 가시 사용자 집합
    if is_system_admin(current_user):
        visible_users = db.query(models.User).all()
    elif (
        current_user.company_role == "COMPANY_ADMIN"
        and current_user.company_id is not None
    ):
        visible_users = (
            db.query(models.User)
            .filter(models.User.company_id == current_user.company_id)
            .all()
        )
    else:
        my_meeting_ids = [
            mm.meeting_id
            for mm in db.query(models.MeetingMember.meeting_id)
            .filter(models.MeetingMember.user_id == current_user.id)
            .all()
        ]
        if not my_meeting_ids:
            return {"meetings": [], "members": []}
        shared_user_ids = {
            mm.user_id
            for mm in db.query(models.MeetingMember.user_id)
            .filter(models.MeetingMember.meeting_id.in_(my_meeting_ids))
            .all()
        }
        visible_users = (
            db.query(models.User).filter(models.User.id.in_(shared_user_ids)).all()
        )

    visible_ids = {u.id for u in visible_users}

    # 2) 가시 사용자들의 회의체 참여 정보 묶기
    member_rows = (
        db.query(models.MeetingMember)
        .filter(models.MeetingMember.user_id.in_(visible_ids))
        .all()
        if visible_ids
        else []
    )
    involved_meeting_ids = {mm.meeting_id for mm in member_rows}
    meetings_meta = (
        {
            m.id: m
            for m in db.query(models.Meeting)
            .filter(models.Meeting.id.in_(involved_meeting_ids))
            .all()
        }
        if involved_meeting_ids
        else {}
    )
    user_meetings: dict[int, list] = {}
    for mm in member_rows:
        meeting = meetings_meta.get(mm.meeting_id)
        user_meetings.setdefault(mm.user_id, []).append(
            {
                "id": mm.meeting_id,
                "member_id": mm.id,
                "title": meeting.title if meeting else "",
                "role": mm.meeting_role,
            }
        )

    # 3) 필터 드롭다운: 본인이 속한 회의체 + 본인 역할
    my_membership = (
        db.query(models.MeetingMember)
        .filter(models.MeetingMember.user_id == current_user.id)
        .all()
    )
    my_role_map = {mm.meeting_id: mm.meeting_role for mm in my_membership}
    meetings_list = [
        {"id": m.id, "title": m.title, "my_role": my_role_map.get(m.id)}
        for m in sorted(
            db.query(models.Meeting)
            .filter(models.Meeting.id.in_(list(my_role_map.keys())))
            .all()
            if my_role_map
            else [],
            key=lambda x: x.title or "",
        )
    ]

    # 4) members
    members = [
        {
            "id": u.id,
            "name": u.name,
            "email": u.email,
            "department": u.department,
            "company": u.company_name,
            "company_id": u.company_id,
            "position": u.position,
            "role": u.company_role,
            "meetings": user_meetings.get(u.id, []),
        }
        for u in visible_users
    ]
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
    target = (
        db.query(models.MeetingMember)
        .filter(
            models.MeetingMember.id == member_id,
            models.MeetingMember.meeting_id == meeting_id,
        )
        .first()
    )
    if not target:
        raise HTTPException(status_code=404, detail="Not found")
    # 제거 권한: 본인 / 회의체 간사 / SYSTEM_ADMIN / 같은 회사 COMPANY_ADMIN
    target_user = db.query(models.User).filter(models.User.id == target.user_id).first()
    is_company_admin = (
        current_user.company_role == "COMPANY_ADMIN"
        and current_user.company_id is not None
        and target_user is not None
        and current_user.company_id == target_user.company_id
    )
    if (
        target.user_id != current_user.id
        and my_role != "admin"
        and not is_system_admin(current_user)
        and not is_company_admin
    ):
        raise HTTPException(
            status_code=403,
            detail="구성원을 제거할 권한이 없습니다. (회의체 간사 또는 관리자만 가능)",
        )

    removed_user_id = target.user_id
    db.delete(target)
    db.commit()
    background_tasks.add_task(delete_meeting_member, meeting_id, removed_user_id)
    return {"ok": True}


@ai_router.delete("/users/{user_id}")
async def ai_delete_user(
    user_id: int,
    background_tasks: BackgroundTasks,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """사용자 계정 삭제(소프트 삭제) — SYSTEM_ADMIN 또는 같은 회사 COMPANY_ADMIN만 (MT-6).

    하드 삭제는 작성한 회의록·보고서·감사 로그 등 users(id)를 RESTRICT로 참조하는
    행이 하나라도 있으면 불가능했다(사실상 활동한 모든 사용자 삭제 불가). 대신 행은
    남기고 is_active=False로 비활성화한다.
    - 표시용 이름(name)은 보존 → 과거 작성물의 작성자 표기 유지
    - 로그인 자격(email)은 익명화 → ① 재로그인 차단 ② 같은 이메일로 재가입 허용
    """
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Not found")
    if user.id == current_user.id:
        raise HTTPException(status_code=400, detail="본인 계정은 삭제할 수 없습니다.")
    is_company_admin = (
        current_user.company_role == "COMPANY_ADMIN"
        and current_user.company_id is not None
        and current_user.company_id == user.company_id
    )
    if not is_system_admin(current_user) and not is_company_admin:
        raise HTTPException(
            status_code=403, detail="계정을 삭제할 권한이 없습니다. (관리자만 가능)"
        )
    if not user.is_active:
        return {"ok": True}  # 이미 탈퇴 처리됨 (멱등)

    # 소프트 삭제 + 자격 익명화
    user.is_active = False
    user.email = (
        f"deleted+{user.id}@deleted.invalid"  # 원래 이메일 슬롯 해제(재가입 허용)
    )
    user.password_hash = "!"  # BCrypt와 절대 매칭되지 않는 불용 해시
    # 활성 세션(refresh token) 폐기 — 행이 남으므로 명시적으로 정리
    db.execute(
        text("DELETE FROM refresh_tokens WHERE user_id = :uid"), {"uid": user_id}
    )
    # 활성 회의체 명단에서 제거 (참석 이력·발화 등은 별도 테이블에 보존됨)
    db.query(models.MeetingMember).filter(
        models.MeetingMember.user_id == user_id
    ).delete()
    db.commit()
    background_tasks.add_task(neo4j_delete_user, user_id)
    return {"ok": True}


@ai_router.patch("/users/{user_id}")
async def ai_update_user(
    user_id: int,
    data: dict,
    background_tasks: BackgroundTasks,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # MT-1: 본인 또는 SYSTEM_ADMIN, 같은 회사 COMPANY_ADMIN만 수정 가능
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Not found")
    require_user_update_permission(current_user, user)
    if "name" in data and data["name"] is not None:
        user.name = data["name"]
    if "company" in data:
        user.company_id = _get_or_create_company_id(db, data["company"])
    if "department" in data:
        user.department = data["department"] if data["department"] else None
    if "position" in data:
        user.position = data["position"] if data["position"] else None
    db.commit()
    db.refresh(user)
    background_tasks.add_task(
        sync_user,
        user_id=user.id,
        name=user.name,
        email=user.email,
        company=user.company_name,
        department=user.department,
        position=user.position,
    )
    return {
        "id": user.id,
        "name": user.name,
        "company": user.company_name,
        "department": user.department,
        "position": user.position,
    }


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
    # 회의체 삭제는 간사/회사관리자/시스템관리자만
    require_meeting_edit(db, current_user, meeting_id)

    # ── 1. ID 선수집 ──────────────────────────────────────────────
    session_ids = [
        r.id
        for r in db.query(models.MeetingSession.id)
        .filter(models.MeetingSession.meeting_id == meeting_id)
        .all()
    ]
    report_ids = [
        r.id
        for r in db.query(models.Report.id)
        .filter(models.Report.meeting_id == meeting_id)
        .all()
    ]
    agent_log_ids = [
        r.id
        for r in db.query(models.AgentLog.id)
        .filter(models.AgentLog.meeting_id == meeting_id)
        .all()
    ]

    # ── 2. 세션 하위 (session_id FK) ─────────────────────────────
    if session_ids:
        db.query(models.SttSegment).filter(
            models.SttSegment.session_id.in_(session_ids)
        ).delete(synchronize_session=False)
        db.query(models.SessionMember).filter(
            models.SessionMember.session_id.in_(session_ids)
        ).delete(synchronize_session=False)
        db.query(models.Minutes).filter(
            models.Minutes.session_id.in_(session_ids)
        ).delete(synchronize_session=False)

    # ── 3. 채팅 메시지 (meeting_id 전체) ─────────────────────────
    db.query(models.ChatMessage).filter(
        models.ChatMessage.meeting_id == meeting_id
    ).delete(synchronize_session=False)

    # ── 4. 세션 ──────────────────────────────────────────────────
    if session_ids:
        db.query(models.MeetingSession).filter(
            models.MeetingSession.id.in_(session_ids)
        ).delete(synchronize_session=False)

    # ── 5. 보고서 하위 (report_id FK) ────────────────────────────
    if report_ids:
        db.query(models.HitlReview).filter(
            models.HitlReview.report_id.in_(report_ids)
        ).delete(synchronize_session=False)
        db.query(models.ReportScore).filter(
            models.ReportScore.report_id.in_(report_ids)
        ).delete(synchronize_session=False)

    # ── 6. 보고서 ─────────────────────────────────────────────────
    db.query(models.Report).filter(models.Report.meeting_id == meeting_id).delete(
        synchronize_session=False
    )

    # ── 7. AgentLog 하위 (agent_log_id FK) ───────────────────────
    if agent_log_ids:
        db.query(models.TokenUsageLog).filter(
            models.TokenUsageLog.agent_log_id.in_(agent_log_ids)
        ).delete(synchronize_session=False)
        db.query(models.HitlReview).filter(
            models.HitlReview.agent_log_id.in_(agent_log_ids)
        ).delete(synchronize_session=False)

    # ── 8. AgentLog ───────────────────────────────────────────────
    db.query(models.AgentLog).filter(models.AgentLog.meeting_id == meeting_id).delete(
        synchronize_session=False
    )

    # ── 9. 아젠다 / 멤버 / 회의체 ────────────────────────────────
    db.query(models.Agenda).filter(models.Agenda.meeting_id == meeting_id).delete(
        synchronize_session=False
    )
    db.query(models.MeetingMember).filter(
        models.MeetingMember.meeting_id == meeting_id
    ).delete(synchronize_session=False)
    db.delete(meeting)
    db.commit()

    background_tasks.add_task(neo4j_delete_meeting, meeting_id=meeting_id)
    return {"ok": True}
