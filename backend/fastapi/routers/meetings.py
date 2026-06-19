from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from sqlalchemy import text
from db import models
from db.database import get_db
from core.auth import get_current_user
from core.access_guard import (
    require_user_update_permission,
    is_system_admin,
)
from graphdb.neo4j_sync import (
    sync_user,
    delete_user as neo4j_delete_user,
    rename_company as neo4j_rename_company,
    rename_department as neo4j_rename_department,
)
import logging

_logger = logging.getLogger(__name__)


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


# ── /api/ai prefix 라우터 (Ingress: /api/ai → FastAPI) ───────────────────────
ai_router = APIRouter(prefix="/api/ai", tags=["ai"])


@ai_router.patch("/companies/rename", summary="회사명 변경")
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
    # Neo4j(Company 노드 + 소속 User.company 속성) 동기화를 응답 전에 완료한다.
    # 백그라운드로 두면 프런트의 그래프 새로고침이 갱신 전 stale 데이터를 받아 옛 이름이 굳는다.
    await neo4j_rename_company(old_name, new_name)
    return {"ok": True, "id": company.id, "name": new_name}


@ai_router.patch("/departments/rename", summary="부서명 변경")
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

    company = None
    if company_name:
        company = (
            db.query(models.Company).filter(models.Company.name == company_name).first()
        )

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
    # 응답 전에 Neo4j 동기화 완료 (그래프 새로고침이 갱신된 값을 받도록).
    await neo4j_rename_department(old_name, new_name, company_name or None)
    return {"ok": True, "name": new_name, "updated": updated}


@ai_router.get("/company/members", summary="회사 구성원 목록 조회")
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
            # 소속 회의체가 없어도 본인은 보여준다 (아래 방어 로직이 current_user를 채운다).
            visible_users = []
        else:
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

    # 현재 사용자는 관리 화면에 항상 보이도록 보장 — 가시범위 경계로 본인이 누락되는 어떤 경우도 방어한다.
    if current_user.id not in visible_ids:
        visible_users.append(current_user)
        visible_ids.add(current_user.id)

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


# (제거됨) /api/ai/meetings/{id}/members/{member_id} — 프런트가 Spring(/api/v1)로 이전. 중복 제거.


@ai_router.delete("/users/{user_id}", summary="사용자 계정 삭제")
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
    uid = user_id
    # FK 참조 정리 후 users 행 하드 삭제
    # 1) 세션·토큰 제거
    db.execute(text("DELETE FROM refresh_tokens WHERE user_id = :uid"), {"uid": uid})
    db.execute(text("DELETE FROM session_members WHERE user_id = :uid"), {"uid": uid})
    db.execute(text("DELETE FROM meeting_members WHERE user_id = :uid"), {"uid": uid})
    # 2) nullable FK → NULL (보고서·채팅 이력은 유지)
    db.execute(
        text("UPDATE reports SET upload_id = NULL WHERE upload_id = :uid"), {"uid": uid}
    )
    db.execute(
        text("UPDATE chat_messages SET user_id = NULL WHERE user_id = :uid"),
        {"uid": uid},
    )
    db.execute(
        text("UPDATE chat_feedback SET user_id = NULL WHERE user_id = :uid"),
        {"uid": uid},
    )
    db.execute(
        text("UPDATE meetings SET created_by = NULL WHERE created_by = :uid"),
        {"uid": uid},
    )
    db.execute(
        text("UPDATE agenda SET assignee_id = NULL WHERE assignee_id = :uid"),
        {"uid": uid},
    )
    db.execute(
        text(
            "UPDATE stt_segments SET speaker_user_id = NULL WHERE speaker_user_id = :uid"
        ),
        {"uid": uid},
    )
    db.execute(
        text("UPDATE minutes SET recorder_id = NULL WHERE recorder_id = :uid"),
        {"uid": uid},
    )
    db.execute(
        text("UPDATE agent_logs SET user_id = NULL WHERE user_id = :uid"), {"uid": uid}
    )
    db.execute(
        text("UPDATE hitl_reviews SET reviewer_id = NULL WHERE reviewer_id = :uid"),
        {"uid": uid},
    )
    db.execute(
        text("UPDATE audit_logs SET actor_id = NULL WHERE actor_id = :uid"),
        {"uid": uid},
    )
    # 사용자가 만든 수동 관계(그래프 자유 관계·회의체 협의) created_by → NULL.
    # 이 둘은 users(id)를 NO ACTION으로 참조해, 누락 시 DELETE FROM users가 FK 위반으로
    # 실패한다(= 관계를 만든 적 있는 사용자는 계정 삭제 불가). 관계 자체는 보존한다.
    db.execute(
        text("UPDATE graph_relations SET created_by = NULL WHERE created_by = :uid"),
        {"uid": uid},
    )
    db.execute(
        text("UPDATE meeting_relations SET created_by = NULL WHERE created_by = :uid"),
        {"uid": uid},
    )
    # 3) users 행 삭제
    db.execute(text("DELETE FROM users WHERE id = :uid"), {"uid": uid})
    db.commit()
    background_tasks.add_task(neo4j_delete_user, user_id)
    return {"ok": True}


@ai_router.patch("/users/{user_id}", summary="사용자 정보 수정")
async def ai_update_user(
    user_id: int,
    data: dict,
    background_tasks: BackgroundTasks,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """사용자 정보(이름·이메일·회사·부서·직책)를 수정하고 Neo4j에 동기화합니다.

    권한: 본인 또는 SYSTEM_ADMIN, 같은 회사 COMPANY_ADMIN만 가능(MT-1).
    이메일(로그인 자격) 변경은 관리자만 허용 — 본인 자가수정으로는 불가.
    """
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Not found")
    require_user_update_permission(current_user, user)
    if "name" in data and data["name"] is not None:
        user.name = data["name"]
    # 이메일(로그인 자격) 변경 — 관리자(SYSTEM_ADMIN/같은 회사 COMPANY_ADMIN)만 허용.
    # 본인 자가수정으로는 변경 불가(자격 탈취/혼선 방지). 중복은 활성 계정 기준으로 차단.
    if "email" in data and data["email"] is not None:
        new_email = str(data["email"]).strip()
        if new_email and new_email != user.email:
            is_admin_caller = is_system_admin(current_user) or (
                current_user.company_role == "COMPANY_ADMIN"
                and current_user.company_id is not None
                and current_user.company_id == user.company_id
            )
            if not is_admin_caller:
                raise HTTPException(
                    status_code=403,
                    detail="이메일은 관리자만 변경할 수 있습니다.",
                )
            if "@" not in new_email or "." not in new_email.split("@")[-1]:
                raise HTTPException(
                    status_code=400, detail="올바른 이메일 형식이 아닙니다."
                )
            taken = (
                db.query(models.User.id)
                .filter(
                    models.User.email == new_email,
                    models.User.id != user.id,
                )
                .first()
            )
            if taken:
                raise HTTPException(
                    status_code=409, detail="이미 사용 중인 이메일입니다."
                )
            user.email = new_email
    if "company" in data:
        user.company_id = _get_or_create_company_id(db, data["company"])
    if "department" in data:
        user.department = data["department"] if data["department"] else None
    if "position" in data:
        user.position = data["position"] if data["position"] else None
    db.commit()
    db.refresh(user)
    # company는 관계(company.name) 경유라 company_id만 바꾸면 stale일 수 있어 id로 직접 조회한다.
    company_name = None
    if user.company_id is not None:
        _co = (
            db.query(models.Company)
            .filter(models.Company.id == user.company_id)
            .first()
        )
        company_name = _co.name if _co else None
    # 동기로 Neo4j(User.company 속성) 반영 — 백그라운드 지연/유실로 그래프에 옛 회사명이 굳는 것 방지.
    await sync_user(
        user_id=user.id,
        name=user.name,
        email=user.email,
        company=company_name,
        department=user.department,
        position=user.position,
    )
    return {
        "id": user.id,
        "name": user.name,
        "email": user.email,
        "company": user.company_name,
        "department": user.department,
        "position": user.position,
    }


# (제거됨) /api/ai/meetings/{id} 회의체 삭제 — Spring(/api/v1) MeetingService.deleteMeeting로 이전.
# 회의체 삭제는 PG 원천(Spring) + 아웃박스 → Neo4j 동기화 경로를 사용한다. 중복 제거.
