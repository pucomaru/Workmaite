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
    return user.role == "SYSTEM_ADMIN"


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


def require_meeting_member_by_session(db: Session, user: models.User, session_id: int) -> None:
    row = (
        db.query(models.MeetingSession.meeting_id)
        .filter(models.MeetingSession.id == session_id)
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="세션을 찾을 수 없습니다.")
    require_meeting_member(db, user, row.meeting_id)


def require_user_update_permission(current_user: models.User, target: models.User) -> None:
    """사용자 정보 수정 권한 (MT-1): 본인, SYSTEM_ADMIN, 같은 회사 COMPANY_ADMIN만."""
    if target.id == current_user.id or is_system_admin(current_user):
        return
    same_company_admin = (
        current_user.role == "COMPANY_ADMIN"
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
            .filter(models.User.company_id == user.company_id)
            .all()
        }
    return ids


def require_meeting_member_by_report(db: Session, user: models.User, report_id: int) -> None:
    row = (
        db.query(models.Report.meeting_id)
        .filter(models.Report.id == report_id)
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="보고서를 찾을 수 없습니다.")
    require_meeting_member(db, user, row.meeting_id)
