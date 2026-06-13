"""회의체 멤버십 인가 가드 (P1-4, SEC-5 IDOR 차단).

Spring의 MeetingAccessGuard와 동일한 규칙:
- SYSTEM_ADMIN은 전체 통과
- 그 외에는 meeting_members 멤버십 필요
라우트 핸들러 시작 지점에서 호출한다.
"""

import logging

from fastapi import HTTPException
from sqlalchemy.orm import Session

import models

logger = logging.getLogger(__name__)


def is_system_admin(user: models.User) -> bool:
    return user.company_role == "SYSTEM_ADMIN"


def require_meeting_member(db: Session, user: models.User, meeting_id: int) -> None:
    """현재 사용자가 회의체 멤버인지 검증 (아니면 403)."""
    if is_system_admin(user):
        return
    member = (
        db.query(models.MeetingMember.id)
        .filter(
            models.MeetingMember.meeting_id == meeting_id,
            models.MeetingMember.user_id == user.id,
        )
        .first()
    )
    if not member:
        logger.warning(f"[Guard] user={user.id} meeting={meeting_id} 접근 거부")
        raise HTTPException(status_code=403, detail="회의체 접근 권한이 없습니다.")


def require_meeting_member_by_session(
    db: Session, user: models.User, session_id: int
) -> None:
    row = (
        db.query(models.MeetingSession.meeting_id)
        .filter(models.MeetingSession.id == session_id)
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="세션을 찾을 수 없습니다.")
    require_meeting_member(db, user, row.meeting_id)


def require_user_update_permission(
    current_user: models.User, target: models.User
) -> None:
    """사용자 정보 수정 권한 (MT-1): 본인, SYSTEM_ADMIN, 같은 회사 COMPANY_ADMIN만."""
    if target.id == current_user.id or is_system_admin(current_user):
        return
    same_company_admin = (
        current_user.company_role == "COMPANY_ADMIN"
        and current_user.company_id is not None
        and current_user.company_id == target.company_id
    )
    if not same_company_admin:
        raise HTTPException(status_code=403, detail="접근 권한이 없습니다.")


def visible_user_ids(db: Session, user: models.User) -> set[int] | None:
    """디렉터리 가시성 (MT-3): 본인 + 내 회사 + 공유 회의체 인원. None이면 전체(SYSTEM_ADMIN)."""
    if is_system_admin(user):
        return None
    ids = {user.id}
    my_meetings = [
        r.meeting_id
        for r in db.query(models.MeetingMember.meeting_id)
        .filter(models.MeetingMember.user_id == user.id)
        .all()
    ]
    if my_meetings:
        ids |= {
            r.user_id
            for r in db.query(models.MeetingMember.user_id)
            .filter(models.MeetingMember.meeting_id.in_(my_meetings))
            .all()
        }
    if user.company_id is not None:
        ids |= {
            r.id
            for r in db.query(models.User.id)
            .filter(
                models.User.company_id == user.company_id,
                models.User.is_active.is_(True),  # 탈퇴 계정 제외(MT-6)
            )
            .all()
        }
    return ids


def require_meeting_member_by_report(
    db: Session, user: models.User, report_id: int
) -> None:
    require_meeting_member(db, user, meeting_id_of_report(db, report_id))


# ───────────────── 회사/소유 결합 인가 (company_role × meeting_role) ─────────────────
# 회사 귀속 = meetings.created_by의 회사. 세션·아젠다·회의록·보고서는 소속 회의체를 상속.
# Spring MeetingAccessGuard의 requireView/requireMeetingEdit/requireOwnedEdit와 동일 규칙.


def _meeting_company_id(db: Session, meeting_id: int) -> int | None:
    """회의체 소유 회사 = 생성자(created_by)의 회사."""
    row = (
        db.query(models.Meeting.created_by)
        .filter(models.Meeting.id == meeting_id)
        .first()
    )
    if not row or row.created_by is None:
        return None
    u = (
        db.query(models.User.company_id)
        .filter(models.User.id == row.created_by)
        .first()
    )
    return u.company_id if u else None


def _company_participates_in(db: Session, meeting_id: int, company_id: int | None) -> bool:
    """호출자 회사가 해당 회의체에 멤버를 한 명이라도 갖는가 (회사 관리자 조회 범위)."""
    if company_id is None:
        return False
    member_ids = [
        r.user_id
        for r in db.query(models.MeetingMember.user_id)
        .filter(models.MeetingMember.meeting_id == meeting_id)
        .all()
    ]
    if not member_ids:
        return False
    return (
        db.query(models.User.id)
        .filter(models.User.id.in_(member_ids), models.User.company_id == company_id)
        .first()
        is not None
    )


def _is_meeting_admin(db: Session, user: models.User, meeting_id: int) -> bool:
    return (
        db.query(models.MeetingMember.id)
        .filter(
            models.MeetingMember.meeting_id == meeting_id,
            models.MeetingMember.user_id == user.id,
            models.MeetingMember.meeting_role == "admin",
        )
        .first()
        is not None
    )


def can_edit_meeting(db: Session, user: models.User, meeting_id: int) -> bool:
    """회의체 하위 전체 편집 권한: 시스템관리자 | (회사관리자 & 자사 소유) | 간사."""
    if is_system_admin(user):
        return True
    if (
        user.company_role == "COMPANY_ADMIN"
        and user.company_id is not None
        and user.company_id == _meeting_company_id(db, meeting_id)
    ):
        return True
    return _is_meeting_admin(db, user, meeting_id)


def require_view(db: Session, user: models.User, meeting_id: int) -> None:
    """조회 권한: 시스템관리자 | (회사관리자 & 자사가 참여한 회의체) | 멤버."""
    if is_system_admin(user):
        return
    if user.company_role == "COMPANY_ADMIN" and _company_participates_in(
        db, meeting_id, user.company_id
    ):
        return
    member = (
        db.query(models.MeetingMember.id)
        .filter(
            models.MeetingMember.meeting_id == meeting_id,
            models.MeetingMember.user_id == user.id,
        )
        .first()
    )
    if member is None:
        raise HTTPException(status_code=403, detail="회의체 접근 권한이 없습니다.")


def require_meeting_edit(db: Session, user: models.User, meeting_id: int) -> None:
    """회의체 하위 전체 편집 권한 요구 (간사/회사관리자/시스템관리자)."""
    if not can_edit_meeting(db, user, meeting_id):
        raise HTTPException(
            status_code=403, detail="편집 권한이 없습니다. (간사/회사관리자/시스템관리자만)"
        )


def require_owned_edit(
    db: Session, user: models.User, meeting_id: int, owner_id: int | None
) -> None:
    """소유물 편집 권한: 회의체 전체 편집 권한자 | 소유자 본인(참여자는 자신의 것만)."""
    if can_edit_meeting(db, user, meeting_id):
        return
    if owner_id is not None and owner_id == user.id:
        return
    raise HTTPException(status_code=403, detail="본인이 작성한 항목만 편집할 수 있습니다.")


def meeting_id_of_session(db: Session, session_id: int) -> int:
    row = (
        db.query(models.MeetingSession.meeting_id)
        .filter(models.MeetingSession.id == session_id)
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="세션을 찾을 수 없습니다.")
    return row.meeting_id


def meeting_id_of_report(db: Session, report_id: int) -> int:
    row = (
        db.query(models.Report.meeting_id).filter(models.Report.id == report_id).first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="보고서를 찾을 수 없습니다.")
    return row.meeting_id


def meeting_id_of_agenda(db: Session, agenda_id: int) -> int:
    row = (
        db.query(models.Agenda.meeting_id).filter(models.Agenda.id == agenda_id).first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="아젠다를 찾을 수 없습니다.")
    return row.meeting_id


def require_view_by_session(db: Session, user: models.User, session_id: int) -> None:
    require_view(db, user, meeting_id_of_session(db, session_id))


def require_view_by_report(db: Session, user: models.User, report_id: int) -> None:
    require_view(db, user, meeting_id_of_report(db, report_id))


def viewable_meeting_ids(db: Session, user: models.User) -> set[int] | None:
    """조회 가능한 회의체 id 집합. None이면 전체(SYSTEM_ADMIN). 목록·그래프·AI 스코프에 공통 사용."""
    if is_system_admin(user):
        return None
    if user.company_role == "COMPANY_ADMIN" and user.company_id is not None:
        rows = (
            db.query(models.MeetingMember.meeting_id)
            .join(models.User, models.User.id == models.MeetingMember.user_id)
            .filter(models.User.company_id == user.company_id)
            .distinct()
            .all()
        )
        return {r.meeting_id for r in rows}
    rows = (
        db.query(models.MeetingMember.meeting_id)
        .filter(models.MeetingMember.user_id == user.id)
        .all()
    )
    return {r.meeting_id for r in rows}
