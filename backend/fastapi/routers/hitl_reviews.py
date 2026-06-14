"""HITL 검토 저장·보고서/추출 검토 시작·확정 라우터 (P3A-4 — routers/supervisor.py에서 분리)."""

import logging
import uuid
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from db import models
from realtime.sse import sse_done, sse_error, sse_token
from agents import (
    report_reviewer as report_agent,
    task_extractor as task_agent,
)
from core.auth import get_current_user
from core.access_guard import (
    require_meeting_edit,
    require_view,
    meeting_id_of_report,
    meeting_id_of_agenda,
)
from db.database import get_db
from services.supervisor_helpers import (
    _get_meeting_context,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/agent", tags=["agents"])


# ─── HITL 검토 저장 ──────────────────────────────────────────────────────────
class HitlReviewCreate(BaseModel):
    target_type: str
    agenda_id: Optional[int] = None
    report_id: Optional[int] = None
    agent_log_id: Optional[int] = None
    status: str = "edited"
    comment: Optional[str] = None


@router.post("/hitl-reviews")
async def create_hitl_review(
    data: HitlReviewCreate,
    background_tasks: BackgroundTasks,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # 검토 작성은 회의체 운영 행위 — 대상 보고서/아젠다의 회의체 편집 권한 필요
    if data.report_id is not None:
        require_meeting_edit(db, current_user, meeting_id_of_report(db, data.report_id))
    elif data.agenda_id is not None:
        require_meeting_edit(db, current_user, meeting_id_of_agenda(db, data.agenda_id))
    review = models.HitlReview(
        agent_log_id=data.agent_log_id,
        target_type=data.target_type,
        agenda_id=data.agenda_id,
        report_id=data.report_id,
        status=data.status,
        reviewer_id=current_user.id,
        comment=data.comment,
        reviewed_at=datetime.utcnow(),
    )
    db.add(review)
    db.commit()
    db.refresh(review)

    # 검토 결과를 대상 Agenda/Report 노드 속성·임베딩으로 흡수 (HumanJudgment 노드 폐지)
    try:
        from graphdb.neo4j_sync import sync_hitl_target

        background_tasks.add_task(sync_hitl_target, review.id)
    except Exception as _se:
        logger.warning(f"[hitl-reviews] Neo4j HITL 대상노드 sync 실패: {_se}")

    return {"id": review.id, "status": review.status}


class HitlReviewPatch(BaseModel):
    status: Optional[str] = None
    comment: Optional[str] = None


@router.patch("/hitl-reviews/{hj_id}")
async def update_hitl_review(
    hj_id: int,
    data: HitlReviewPatch,
    background_tasks: BackgroundTasks,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    from fastapi import HTTPException

    review = db.query(models.HitlReview).filter(models.HitlReview.id == hj_id).first()
    if not review:
        raise HTTPException(status_code=404, detail="HitlReview not found")
    if review.report_id is not None:
        require_meeting_edit(
            db, current_user, meeting_id_of_report(db, review.report_id)
        )
    elif review.agenda_id is not None:
        require_meeting_edit(
            db, current_user, meeting_id_of_agenda(db, review.agenda_id)
        )
    if data.status is not None:
        review.status = data.status
    if data.comment is not None:
        review.comment = data.comment
    review.reviewed_at = datetime.utcnow()
    review.reviewer_id = current_user.id
    db.commit()
    db.refresh(review)

    # 검토 결과를 대상 Agenda/Report 노드 속성·임베딩으로 흡수 (HumanJudgment 노드 폐지)
    try:
        from graphdb.neo4j_sync import sync_hitl_target

        background_tasks.add_task(sync_hitl_target, review.id)
    except Exception as _se:
        logger.warning(f"[hitl-reviews] Neo4j HITL 대상노드 sync 실패: {_se}")

    return {
        "id": review.id,
        "status": review.status,
        "reviewed_at": review.reviewed_at.isoformat() if review.reviewed_at else None,
    }


# ─── 보고서 종합 검토 (스트리밍) ──────────────────────────────────────────────
class GlobalReviewRequest(BaseModel):
    meeting_id: int
    reports_info: List[dict]
    chat_history: Optional[List[dict]] = []


@router.post("/reports/global-review/stream")
async def global_review_stream_ep(
    data: GlobalReviewRequest,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_view(db, current_user, data.meeting_id)
    meeting_context = _get_meeting_context(db, data.meeting_id)

    async def stream():
        try:
            async for chunk in report_agent.global_review_stream(
                reports_info=data.reports_info,
                chat_history=data.chat_history or [],
                meeting_id=data.meeting_id,
                meeting_context=meeting_context,
            ):
                yield sse_token(chunk)
        except Exception as e:
            yield sse_error(str(e))
        yield sse_done()

    return StreamingResponse(stream(), media_type="text/event-stream")


# ─── 보고서 단건 검토 ─────────────────────────────────────────────────────────
class ReviewReportRequest(BaseModel):
    report_content: str
    agenda: Optional[str] = ""


@router.post("/reports/review")
async def review_report_ep(
    data: ReviewReportRequest,
    current_user: models.User = Depends(get_current_user),
):
    try:
        result = await report_agent.review_report(
            report_content=data.report_content,
            agenda=data.agenda or "",
        )
    except Exception as e:
        # 검토 생성 실패는 가짜 점수 대신 명시적 에러로 (P3A-2, H-2)
        raise HTTPException(
            status_code=502, detail=f"보고서 검토 생성 실패 — 다시 시도해주세요: {e}"
        )
    return result


# ─── 보고서 HITL 검토 시작 ────────────────────────────────────────────────────
class StartReportReviewRequest(BaseModel):
    thread_id: Optional[str] = None  # 미지정 시 서버가 run_id 발급 (P3A-1)
    report_content: str
    agenda: Optional[str] = ""


@router.post("/reports/review/start")
async def start_report_review_ep(
    data: StartReportReviewRequest,
    current_user: models.User = Depends(get_current_user),
):
    thread_id = data.thread_id or f"run-{uuid.uuid4()}"  # 서버 발급 run_id (P3A-1)
    result = await report_agent.start_report_review(
        thread_id=thread_id,
        report_content=data.report_content,
        agenda=data.agenda or "",
    )
    result["thread_id"] = thread_id
    return result


# ─── 보고서 HITL 검토 확정 ────────────────────────────────────────────────────
class ConfirmReportReviewRequest(BaseModel):
    thread_id: str
    approved: bool
    title: Optional[str] = ""
    content: Optional[str] = ""
    meeting_id: Optional[int] = None


@router.post("/reports/review/confirm")
async def confirm_report_review_ep(
    data: ConfirmReportReviewRequest,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if data.meeting_id is not None:
        require_meeting_edit(db, current_user, data.meeting_id)
    from core.service_guards import idempotency_guard, release_idempotency

    _idem_key = f"report-confirm:{data.thread_id}"
    idempotency_guard(_idem_key)  # 더블클릭/재시도 중복 차단 (P3C-2)

    try:
        result = await report_agent.confirm_report_review(
            thread_id=data.thread_id,
            approved=data.approved,
            title=data.title or "",
            content=data.content or "",
            meeting_id=data.meeting_id,
        )
    except Exception:
        release_idempotency(_idem_key)  # 실패한 시도는 재시도 가능해야 함
        raise
    return result


# ─── 과제 추출 HITL 시작 ──────────────────────────────────────────────────────
class StartExtractionRequest(BaseModel):
    thread_id: Optional[str] = None  # 미지정 시 서버가 run_id 발급 (P3A-1)
    content: str
    org_dept_list: Optional[str] = ""


@router.post("/extraction/review/start")
async def start_extraction_review_ep(
    data: StartExtractionRequest,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    thread_id = data.thread_id or f"run-{uuid.uuid4()}"  # 서버 발급 run_id (P3A-1)
    result = await task_agent.start_extraction_review(
        thread_id=thread_id,
        content=data.content,
        org_dept_list=data.org_dept_list or "",
    )
    result["thread_id"] = thread_id
    return result


# ─── 과제 추출 HITL 확정 ──────────────────────────────────────────────────────
class ConfirmExtractionRequest(BaseModel):
    thread_id: str
    approved: bool
    meeting_id: Optional[int] = None


@router.post("/extraction/review/confirm")
async def confirm_extraction_review_ep(
    data: ConfirmExtractionRequest,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if data.meeting_id is not None:
        require_meeting_edit(db, current_user, data.meeting_id)
    from core.service_guards import idempotency_guard, release_idempotency

    _idem_key = f"extract-confirm:{data.thread_id}"
    idempotency_guard(_idem_key)  # 더블클릭/재시도 중복 차단 (P3C-2)

    try:
        result = await task_agent.confirm_extraction_review(
            thread_id=data.thread_id,
            approved=data.approved,
            meeting_id=data.meeting_id,
        )
    except Exception:
        release_idempotency(_idem_key)  # 실패한 시도는 재시도 가능해야 함
        raise
    return result
