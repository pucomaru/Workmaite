"""
routers/sync.py — Neo4j 동기화 관련 API
=========================================
엔드포인트:
  POST /api/sync/retry              재시도 작업 수동 트리거
  GET  /api/sync/logs               실패 로그 목록 조회
  POST /api/sync/meeting/{id}       특정 Meeting 수동 동기화
  POST /api/sync/session/{id}       특정 Session 수동 동기화
  POST /api/sync/agenda/{id}        특정 Agenda 수동 동기화
  POST /api/sync/user/{id}          특정 User 수동 동기화
  POST /api/sync/member             MeetingMember 관계 수동 동기화
  POST /api/sync/file               파일 업로드 → 임베딩 → Neo4j 저장
  POST /api/sync/search             벡터 유사도 검색
  POST /api/sync/all                전체 PostgreSQL→Neo4j 동기화
"""

import os
import logging
from typing import Optional, List

from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException, BackgroundTasks
from pydantic import BaseModel
from sqlalchemy.orm import Session as DBSession

import models
from database import get_db
from auth import get_current_user
from neo4j_sync import (
    sync_meeting,
    sync_session,
    sync_agenda,
    sync_user,
    sync_minutes,
    sync_meeting_member,
    delete_meeting,
    delete_meeting_member,
    retry_failed_syncs,
    sync_all_from_pg,
    vector_search,
)
from file_embedder import process_and_embed_file, embed_query

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/sync", tags=["sync"])

UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)


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


# ─── 실패 로그 조회 ───────────────────────────────────────────────────────────

@router.get("/logs")
def get_sync_logs(
    status: Optional[str] = None,
    operation: Optional[str] = None,
    limit: int = 50,
    current_user: models.User = Depends(get_current_user),
    db: DBSession = Depends(get_db),
):
    """agent_logs 조회. status(failed/recovered), operation으로 필터링."""
    query = db.query(models.AgentLog)
    if status:
        query = query.filter(models.AgentLog.status == status)
    if operation:
        query = query.filter(models.AgentLog.operation == operation)
    logs = (
        query.order_by(models.AgentLog.created_at.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "id": l.id,
            "operation": l.operation,
            "entity_type": l.entity_type,
            "entity_id": l.entity_id,
            "status": l.status,
            "error_detail": l.error_detail,
            "retry_count": l.retry_count,
            "created_at": l.created_at.isoformat() if l.created_at else None,
            "updated_at": l.updated_at.isoformat() if l.updated_at else None,
        }
        for l in logs
    ]


# ─── Meeting 삭제 동기화 (SpringBoot → FastAPI → Neo4j) ──────────────────────

@router.delete("/meeting/{meeting_id}/delete")
async def delete_meeting_sync(
    meeting_id: int,
    current_user: models.User = Depends(get_current_user),
):
    """Meeting 노드 및 연결된 모든 관계를 Neo4j에서 삭제합니다."""
    await delete_meeting(meeting_id=meeting_id)
    return {"success": True, "meeting_id": meeting_id}


# ─── MeetingMember 관계 삭제 동기화 ──────────────────────────────────────────

@router.delete("/member/delete")
async def delete_member_sync(
    meetingId: int,
    userId: int,
    current_user: models.User = Depends(get_current_user),
):
    """Person → Meeting 멤버십 관계를 Neo4j에서 삭제합니다."""
    await delete_meeting_member(meeting_id=meetingId, user_id=userId)
    return {"success": True, "meeting_id": meetingId, "user_id": userId}


# ─── Meeting 수동 동기화 ──────────────────────────────────────────────────────

@router.post("/meeting/{meeting_id}")
async def sync_meeting_manual(
    meeting_id: int,
    current_user: models.User = Depends(get_current_user),
    db: DBSession = Depends(get_db),
):
    """특정 Meeting을 Neo4j에 수동으로 동기화합니다."""
    meeting = db.query(models.Meeting).filter(models.Meeting.id == meeting_id).first()
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting을 찾을 수 없습니다.")
    await sync_meeting(
        meeting_id=meeting.id,
        title=meeting.title,
        purpose=meeting.purpose,
        status=str(meeting.status or "ACTIVE"),
        meeting_type=str(meeting.type or ""),
    )
    return {"success": True, "meeting_id": meeting_id, "title": meeting.title}


# ─── Session 수동 동기화 ──────────────────────────────────────────────────────

@router.post("/session/{session_id}")
async def sync_session_manual(
    session_id: int,
    current_user: models.User = Depends(get_current_user),
    db: DBSession = Depends(get_db),
):
    """특정 Session을 Neo4j에 수동으로 동기화합니다."""
    session = db.query(models.MeetingSession).filter(models.MeetingSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session을 찾을 수 없습니다.")
    await sync_session(
        session_id=session.id,
        meeting_id=session.meeting_id,
        title=session.title or "",
        status=str(session.status or "scheduled"),
        scheduled_at=session.scheduled_at.isoformat() if session.scheduled_at else None,
    )
    return {"success": True, "session_id": session_id, "title": session.title}


# ─── 파일 업로드 + 임베딩 ─────────────────────────────────────────────────────

@router.post("/file")
async def upload_and_embed_file(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    meeting_id: Optional[int] = Form(None),
    session_id: Optional[int] = Form(None),
    current_user: models.User = Depends(get_current_user),
):
    """
    파일을 업로드하고 임베딩 파이프라인을 백그라운드에서 실행합니다.
    - 텍스트 추출 → 청킹 → text-embedding-3-small → Neo4j VectorIndex
    - Neo4j 저장 실패 시 agent_logs에 기록
    """
    # 파일 저장
    safe_name = file.filename.replace(" ", "_")
    dest = os.path.join(UPLOAD_DIR, safe_name)
    content = await file.read()
    with open(dest, "wb") as f:
        f.write(content)

    # 백그라운드에서 임베딩 파이프라인 실행
    background_tasks.add_task(
        _run_embed,
        file_path=dest,
        file_name=safe_name,
        meeting_id=meeting_id,
        session_id=session_id,
        uploader_id=current_user.id,
    )

    return {
        "success": True,
        "message": f"{safe_name} 저장 완료. 임베딩이 백그라운드에서 처리됩니다.",
        "file_name": safe_name,
        "meeting_id": meeting_id,
        "session_id": session_id,
    }


async def _run_embed(
    file_path: str,
    file_name: str,
    meeting_id: Optional[int],
    session_id: Optional[int],
    uploader_id: int,
):
    """BackgroundTask 래퍼 — 임베딩 파이프라인 실행."""
    try:
        result = await process_and_embed_file(
            file_path=file_path,
            file_name=file_name,
            meeting_id=meeting_id,
            session_id=session_id,
            extra_meta={"uploader_id": uploader_id},
        )
        logger.info(f"[Sync] 파일 임베딩 완료: {result}")
    except Exception as e:
        logger.error(f"[Sync] 파일 임베딩 실패: {e}")


# ─── 벡터 유사도 검색 ─────────────────────────────────────────────────────────

class SearchRequest(BaseModel):
    query: str
    meeting_id: Optional[int] = None
    top_k: int = 5


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
    current_user: models.User = Depends(get_current_user),
    db: DBSession = Depends(get_db),
):
    """특정 Agenda를 Neo4j에 수동으로 동기화합니다."""
    agenda = db.query(models.Agenda).filter(models.Agenda.id == agenda_id).first()
    if not agenda:
        raise HTTPException(status_code=404, detail="Agenda를 찾을 수 없습니다.")
    await sync_agenda(
        agenda_id=agenda.id,
        meeting_id=agenda.meeting_id,
        title=agenda.title or "",
        content=agenda.content,
        status=str(agenda.status or "ON_HOLD"),
        order_index=agenda.order_index or 0,
        assignee_id=agenda.assignee_id,
    )
    return {"success": True, "agenda_id": agenda_id, "title": agenda.title}


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
    )
    return {"success": True, "minutes_id": minutes_id}


# ─── User 수동 동기화 ─────────────────────────────────────────────────────────

@router.post("/user/{user_id}")
async def sync_user_manual(
    user_id: int,
    current_user: models.User = Depends(get_current_user),
    db: DBSession = Depends(get_db),
):
    """특정 User를 Neo4j에 수동으로 동기화합니다."""
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User를 찾을 수 없습니다.")
    await sync_user(
        user_id=user.id,
        name=user.name,
        email=user.email,
        company=user.company,
        department=user.department,
        position=user.position,
    )
    return {"success": True, "user_id": user_id, "name": user.name}


# ─── MeetingMember 관계 수동 동기화 ──────────────────────────────────────────

@router.post("/member")
async def sync_member_manual(
    meetingId: int,
    userId: int,
    current_user: models.User = Depends(get_current_user),
    db: DBSession = Depends(get_db),
):
    """특정 MeetingMember 관계를 Neo4j에 수동으로 동기화합니다."""
    member = (
        db.query(models.MeetingMember)
        .filter(models.MeetingMember.meeting_id == meetingId, models.MeetingMember.user_id == userId)
        .first()
    )
    if not member:
        raise HTTPException(status_code=404, detail="MeetingMember를 찾을 수 없습니다.")
    await sync_meeting_member(
        meeting_id=member.meeting_id,
        user_id=member.user_id,
        role=str(member.role or "MEMBER"),
    )
    return {"success": True, "meeting_id": meetingId, "user_id": userId}


@router.post("/search")
async def vector_similarity_search(
    req: SearchRequest,
    current_user: models.User = Depends(get_current_user),
):
    """
    텍스트 쿼리를 임베딩하여 Neo4j VectorIndex에서 유사 문서 청크를 검색합니다.
    """
    if not req.query.strip():
        raise HTTPException(status_code=400, detail="검색어를 입력하세요.")

    query_emb = await embed_query(req.query)
    results = await vector_search(
        query_embedding=query_emb,
        top_k=req.top_k,
        meeting_id=req.meeting_id,
    )

    return {
        "query": req.query,
        "meeting_id": req.meeting_id,
        "results": results,
    }
