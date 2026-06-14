"""
routers/sync.py — Neo4j 동기화 관련 API
=========================================
엔드포인트:
  POST /api/sync/retry              재시도 작업 수동 트리거
  POST /api/sync/user/{id}          특정 User 동기화 (Spring Boot → FastAPI)
  DELETE /api/sync/user/{id}        User 삭제 동기화
  POST /api/sync/department/{name}  특정 Department 동기화
  POST /api/sync/company/{name}     특정 Company 동기화
  POST /api/sync/meeting/{id}       특정 Meeting 수동 동기화
  POST /api/sync/session/{id}       특정 Session 수동 동기화
  POST /api/sync/agenda/{id}        특정 Agenda 수동 동기화
  POST /api/sync/minutes/{id}       특정 Minutes 수동 동기화
  POST /api/sync/report/{id}        특정 Report 수동 동긲화
  DELETE /api/sync/meeting/{id}     Meeting 삭제 동기화
  POST /api/sync/all                전체 PostgreSQL→Neo4j 동기화
  POST /api/sync/member             특정 User를 Meeting에 구성원 관계로 추가 (Spring Boot 내부 호출)
  DELETE /api/sync/member/delete    특정 User를 Meeting에서 구성원 관계 삭제 (Spring Boot 내부 호출)
"""

import os
import logging
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session as DBSession

from db import models
from db.database import get_db
from core.auth import get_current_user

# 서버 간 내부 호출 인증 (Spring Boot → FastAPI)
_INTERNAL_SECRET = os.environ["INTERNAL_SECRET"]


def verify_internal(x_internal_secret: Optional[str] = Header(None)):
    if x_internal_secret != _INTERNAL_SECRET:
        raise HTTPException(status_code=401, detail="Internal secret mismatch")


from graphdb.neo4j_sync import (  # noqa: E402
    sync_user,
    sync_department,
    sync_company,
    sync_meeting,
    sync_meeting_member,
    delete_meeting_member,
    sync_session,
    sync_agenda,
    sync_minutes,
    sync_report,
    delete_meeting,
    delete_session,
    delete_agenda,
    retry_failed_syncs,
    sync_all_from_pg,
)
from graphdb.neo4j_client import run_cypher  # noqa: E402

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/sync", tags=["sync"])


# ─── 재시도 트리거 ────────────────────────────────────────────────────────────


@router.post("/retry")
async def trigger_retry(
    max_retries: int = 3,
    current_user: models.User = Depends(get_current_user),
):
    """
    agent_logs의 실패 항목을 재시도합니다.
    - max_retries: 이 횟수 미만인 항목만 대상
    """
    result = await retry_failed_syncs(max_retries=max_retries)
    return {
        "success": True,
        "message": f"재시도 완료: {result['recovered']}건 복구, {result['retried'] - result['recovered'] - result['skipped']}건 실패, {result['skipped']}건 건너뜀",
        **result,
    }


# ─── User 동기화 (SpringBoot → FastAPI → Neo4j) ──────────────────────────────


@router.post("/user/{user_id}")
async def sync_user_manual(
    user_id: int,
    _: None = Depends(verify_internal),
    db: DBSession = Depends(get_db),
):
    """특정 User를 Neo4j에 동기화합니다. Spring Boot에서 유저 생성/수정 시 호출합니다."""
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User를 찾을 수 없습니다.")
    await sync_user(
        user_id=user.id,
        name=user.name,
        email=user.email,
        company=user.company_name,
        department=user.department,
        position=user.position,
        created_at=user.created_at.isoformat() + "Z" if user.created_at else None,
    )
    return {"success": True, "user_id": user_id}


@router.delete("/user/{user_id}")
async def delete_user_sync(
    user_id: int,
    _: None = Depends(verify_internal),
):
    """User 노드 및 연결된 모든 관계를 Neo4j에서 삭제합니다."""
    await run_cypher(
        "MATCH (u:User {pg_id: $pg_id}) DETACH DELETE u",
        {"pg_id": user_id},
    )
    return {"success": True, "user_id": user_id}


# ─── Department / Company 수동 동기화 ───────────────────────────────────


@router.post("/department")
async def sync_department_manual(
    name: str,
    _: None = Depends(verify_internal),
):
    """Department 노드를 Neo4j에 수동으로 동기화합니다."""
    if not name:
        raise HTTPException(status_code=400, detail="name 필수")
    await sync_department(name)
    return {"success": True, "name": name}


@router.post("/company")
async def sync_company_manual(
    name: str,
    _: None = Depends(verify_internal),
):
    """Company 노드를 Neo4j에 수동으로 동기화합니다."""
    if not name:
        raise HTTPException(status_code=400, detail="name 필수")
    await sync_company(name)
    return {"success": True, "name": name}


# ─── Meeting 삭제 동기화 (SpringBoot → FastAPI → Neo4j) ──────────────────────


@router.delete("/meeting/{meeting_id}/delete")
async def delete_meeting_sync(
    meeting_id: int,
    _: None = Depends(verify_internal),
):
    """Meeting 노드 및 연결된 모든 관계를 Neo4j에서 삭제합니다."""
    await delete_meeting(meeting_id=meeting_id)
    return {"success": True, "meeting_id": meeting_id}


# ─── Meeting 수동 동기화 ──────────────────────────────────────────────────────


@router.post("/meeting/{meeting_id}")
async def sync_meeting_manual(
    meeting_id: int,
    _: None = Depends(verify_internal),
    db: DBSession = Depends(get_db),
):
    """특정 Meeting을 Neo4j에 수동으로 동기화합니다."""
    meeting = db.query(models.Meeting).filter(models.Meeting.id == meeting_id).first()
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting을 찾을 수 없습니다.")
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
    return {"success": True, "meeting_id": meeting_id, "title": meeting.title}


# ─── Session 수동 동기화 ──────────────────────────────────────────────────────


@router.post("/session/{session_id}")
async def sync_session_manual(
    session_id: int,
    _: None = Depends(verify_internal),
    db: DBSession = Depends(get_db),
):
    """특정 Session을 Neo4j에 수동으로 동기화합니다."""
    session = (
        db.query(models.MeetingSession)
        .filter(models.MeetingSession.id == session_id)
        .first()
    )
    if not session:
        raise HTTPException(status_code=404, detail="Session을 찾을 수 없습니다.")
    members = (
        db.query(models.SessionMember)
        .filter(models.SessionMember.session_id == session_id)
        .all()
    )
    attendees = [{"user_id": m.user_id, "role": m.role or "member"} for m in members]
    await sync_session(
        session_id=session.id,
        meeting_id=session.meeting_id,
        title=session.title or "",
        status=str(session.status or "scheduled"),
        scheduled_at=session.scheduled_at.isoformat() if session.scheduled_at else None,
        started_at=session.started_at.isoformat() if session.started_at else None,
        ended_at=session.ended_at.isoformat() if session.ended_at else None,
        location=session.location,
        session_type=session.type,
        description=session.description,
        attendees=attendees,
    )
    return {"success": True, "session_id": session_id, "title": session.title}


# ─── 전체 동기화 (부트스트랩 / 복구) ─────────────────────────────────────────


@router.post("/all")
async def sync_all(
    background_tasks: BackgroundTasks,
    current_user: models.User = Depends(get_current_user),
):
    """
    PostgreSQL의 모든 엔티티를 Neo4j에 전체 동기화합니다.
    Neo4j 재설치 또는 데이터 불일치 복구 시 사용합니다.
    백그라운드에서 실행되며 즉시 응답을 반환합니다.
    """
    background_tasks.add_task(_run_sync_all)
    return {
        "success": True,
        "message": "전체 동기화가 백그라운드에서 시작되었습니다. /api/sync/logs 에서 실패 항목을 확인하세요.",
    }


async def _run_sync_all() -> None:
    try:
        stats = await sync_all_from_pg()
        logger.info(f"[SyncAll] 완료: {stats}")
    except Exception as e:
        logger.error(f"[SyncAll] 실패: {e}")


# ─── Agenda 수동 동기화 ───────────────────────────────────────────────────────


@router.post("/agenda/{agenda_id}")
async def sync_agenda_manual(
    agenda_id: int,
    _: None = Depends(verify_internal),
    db: DBSession = Depends(get_db),
):
    """특정 Agenda를 Neo4j에 수동으로 동기화합니다."""
    agenda = db.query(models.Agenda).filter(models.Agenda.id == agenda_id).first()
    if not agenda:
        raise HTTPException(status_code=404, detail="Agenda를 찾을 수 없습니다.")
    import json as _json

    dept_str = ""
    if agenda.department:
        dept_str = (
            _json.dumps(agenda.department, ensure_ascii=False)
            if isinstance(agenda.department, (dict, list))
            else str(agenda.department)
        )
    await sync_agenda(
        agenda_id=agenda.id,
        meeting_id=agenda.meeting_id,
        title=agenda.title or "",
        status=str(agenda.status or "draft"),
        assignee_id=agenda.assignee_id,
        priority=agenda.priority or "medium",
        due_date=agenda.due_date.isoformat() if agenda.due_date else None,
        session_id=agenda.session_id,
        department=dept_str,
        ai_evidence=agenda.ai_evidence,
        created_at=agenda.created_at.isoformat() if agenda.created_at else None,
    )
    return {"success": True, "agenda_id": agenda_id, "title": agenda.title}


@router.delete("/agenda/{agenda_id}")
async def delete_agenda_sync(
    agenda_id: int,
    _: None = Depends(verify_internal),
):
    """Agenda 삭제를 Neo4j에 전파합니다 (DATA-4)."""
    await delete_agenda(agenda_id)
    return {"success": True, "agenda_id": agenda_id}


@router.delete("/session/{session_id}")
async def delete_session_sync(
    session_id: int,
    _: None = Depends(verify_internal),
):
    """Session 삭제를 Neo4j에 전파합니다 (DATA-4)."""
    await delete_session(session_id)
    return {"success": True, "session_id": session_id}


# ─── Minutes 수동 동기화 ──────────────────────────────────────────────────────


@router.post("/minutes/{minutes_id}")
async def sync_minutes_manual(
    minutes_id: int,
    current_user: models.User = Depends(get_current_user),
    db: DBSession = Depends(get_db),
):
    """특정 Minutes를 Neo4j에 수동으로 동기화합니다."""
    m = db.query(models.Minutes).filter(models.Minutes.id == minutes_id).first()
    if not m:
        raise HTTPException(status_code=404, detail="Minutes를 찾을 수 없습니다.")
    await sync_minutes(
        minutes_id=m.id,
        session_id=m.session_id,
        content_summary=m.content_summary,
        content_original=m.content_original,
        file_name=m.file_name,
        file_path=m.file_path,
        recorder_id=m.recorder_id,
        status=m.status,
        generated_at=m.generated_at.isoformat() if m.generated_at else None,
    )
    return {"success": True, "minutes_id": minutes_id}


# ─── Member 동기화 (SpringBoot → FastAPI → Neo4j) ────────────────────────────


@router.post("/member")
async def sync_member_manual(
    meetingId: int,
    userId: int,
    role: str = "member",
    _: None = Depends(verify_internal),
):
    """Spring Boot에서 회의 멤버 추가/수정 시 Neo4j에 (User)-[:구성원]->(Meetings) 관계를 동기화합니다."""
    await sync_meeting_member(
        meeting_id=meetingId,
        user_id=userId,
        role=role,
    )
    return {"status": "ok"}


@router.delete("/member/delete")
async def delete_member_manual(
    meetingId: int,
    userId: int,
    _: None = Depends(verify_internal),
):
    """Spring Boot에서 회의 멤버 삭제 시 Neo4j의 (User)-[:구성원]->(Meetings) 관계를 제거합니다."""
    await delete_meeting_member(
        meeting_id=meetingId,
        user_id=userId,
    )
    return {"status": "ok"}


# ─── Report 수동 동기화 ───────────────────────────────────────────────────────


@router.post("/report/{report_id}")
async def sync_report_manual(
    report_id: int,
    current_user: models.User = Depends(get_current_user),
    db: DBSession = Depends(get_db),
):
    """특정 Report를 Neo4j에 수동으로 동기화합니다."""
    r = db.query(models.Report).filter(models.Report.id == report_id).first()
    if not r:
        raise HTTPException(status_code=404, detail="Report를 찾을 수 없습니다.")
    await sync_report(
        report_id=r.id,
        meeting_id=r.meeting_id,
        file_name=r.file_name,
        file_path=r.file_path,
        submitter_department=r.submitter_department,
        human_status=r.human_status or "pending",
        related_agenda_ids=r.related_agenda_ids or [],
        created_at=r.created_at.isoformat() if r.created_at else None,
    )
    return {"success": True, "report_id": report_id}
