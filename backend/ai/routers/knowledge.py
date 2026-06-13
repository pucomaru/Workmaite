"""Knowledge Base 저장·관계 제안·지식 채팅 라우터 (P3A-4 — routers/supervisor.py에서 분리)."""

import logging
from typing import List, Optional

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

import models
from sse import sse_done, sse_error, sse_token
from agents import (
    knowledge_manager as knowledge_agent,
)
from auth import get_current_user
from access_guard import require_meeting_edit, require_view
from database import get_db
from services.supervisor_helpers import (
    _get_meeting_context,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/agent", tags=["agents"])


# ─── Knowledge Base 요청 스키마 ───────────────────────────────────────────────
class _StoreMinutesReq(BaseModel):
    meeting_id: int
    session_id: Optional[int] = None
    title: str
    content: str


class _StoreTaskReq(BaseModel):
    content: str
    department: Optional[str] = None
    due_date: Optional[str] = None
    meeting_id: Optional[int] = None


class _StoreReportReq(BaseModel):
    title: str
    content: str
    meeting_id: Optional[int] = None
    score: Optional[int] = None


class _ProposeRelationshipsReq(BaseModel):
    """POST /knowledge/propose-relationships 요청 바디."""

    meeting_id: int
    node_types: Optional[List[str]] = None  # None이면 Agenda·Minutes 전체


class _ConfirmRelationshipsReq(BaseModel):
    """POST /knowledge/confirm-relationships 요청 바디."""

    proposal_id: str
    approved: bool
    reject_reason: Optional[str] = None  # approved=False 일 때 반려 사유


# ─── Knowledge Base 저장 ──────────────────────────────────────────────────────
@router.post("/knowledge/store-minutes")
async def knowledge_store_minutes(
    data: _StoreMinutesReq,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_meeting_edit(db, current_user, data.meeting_id)
    try:
        return await knowledge_agent.store_minutes(
            title=data.title,
            content=data.content,
            meeting_id=data.meeting_id,
            session_id=data.session_id,
        )
    except Exception as e:
        return {"status": "error", "detail": str(e)}


@router.post("/knowledge/store-task")
async def knowledge_store_task(
    data: _StoreTaskReq,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if data.meeting_id is not None:
        require_meeting_edit(db, current_user, data.meeting_id)
    try:
        return await knowledge_agent.store_task(
            content=data.content,
            department=data.department,
            due_date=data.due_date,
            meeting_id=data.meeting_id,
        )
    except Exception as e:
        return {"status": "error", "detail": str(e)}


@router.post("/knowledge/store-report")
async def knowledge_store_report(
    data: _StoreReportReq,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if data.meeting_id is not None:
        require_meeting_edit(db, current_user, data.meeting_id)
    try:
        return await knowledge_agent.store_report(
            title=data.title,
            content=data.content,
            meeting_id=data.meeting_id,
            score=data.score,
        )
    except Exception as e:
        return {"status": "error", "detail": str(e)}


@router.post(
    "/knowledge/propose-relationships", summary="Knowledge Propose Relationships"
)
async def knowledge_propose_relationships(
    data: _ProposeRelationshipsReq,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Neo4j 노드 간 연결 관계를 LLM이 분석해 제안. proposal_id를 반환."""
    # 그래프 편집 준비 — 간사/회사관리자/시스템관리자만. confirm은 서버발급 proposal_id로 간접 보호.
    require_meeting_edit(db, current_user, data.meeting_id)
    try:
        result = await knowledge_agent.propose_relationships(
            meeting_id=data.meeting_id,
            node_types=data.node_types,
        )
        return result
    except Exception as e:
        return {"status": "error", "detail": str(e)}


@router.post(
    "/knowledge/confirm-relationships", summary="Knowledge Confirm Relationships"
)
async def knowledge_confirm_relationships(
    data: _ConfirmRelationshipsReq,
    _: models.User = Depends(get_current_user),  # 인증 가드 (본문에서 미사용)
):
    """제안된 관계를 승인(Neo4j MERGE) 또는 반려(제안 폐기)."""
    try:
        result = await knowledge_agent.confirm_relationships(
            proposal_id=data.proposal_id,
            approved=data.approved,
            reject_reason=data.reject_reason,
        )
        return result
    except Exception as e:
        return {"status": "error", "detail": str(e)}


# ─── 지식 관리 채팅 (스트리밍) ───────────────────────────────────────────────
class KnowledgeChatRequest(BaseModel):
    message: str
    chat_history: Optional[List[dict]] = []
    meeting_id: Optional[int] = 0


@router.post("/knowledge/chat/stream")
async def knowledge_chat_stream_ep(
    data: KnowledgeChatRequest,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if data.meeting_id:
        require_view(db, current_user, data.meeting_id)
    meeting_context = (
        _get_meeting_context(db, data.meeting_id) if data.meeting_id else ""
    )

    async def stream():
        try:
            async for chunk in knowledge_agent.chat_stream(
                message=data.message,
                chat_history=data.chat_history or [],
                meeting_id=data.meeting_id or 0,
                meeting_context=meeting_context,
            ):
                yield sse_token(chunk)
        except Exception as e:
            yield sse_error(str(e))
        yield sse_done()

    return StreamingResponse(stream(), media_type="text/event-stream")
