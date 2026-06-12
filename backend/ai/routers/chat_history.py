from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List
from datetime import datetime

import models
from database import get_db
from auth import get_current_user

router = APIRouter(prefix="/api/chats", tags=["chat_history"])

VALID_CONTEXT_TYPES = {"agenda", "prepare", "todo", "room", "hyean", "sessions"}


class MessageIn(BaseModel):
    role: str   # user | agent
    content: str


class MessageOut(BaseModel):
    id: int
    role: str
    content: str
    created_at: datetime

    class Config:
        from_attributes = True


# ─── GET: 특정 컨텍스트의 대화 기록 조회 ─────────────────────────────
@router.get("/{context_type}/{context_id}", response_model=List[MessageOut])
def get_chat_history(
    context_type: str,
    context_id: int,
    before_id: int | None = None,
    limit: int | None = None,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if context_type not in VALID_CONTEXT_TYPES:
        raise HTTPException(status_code=400, detail=f"유효하지 않은 context_type: {context_type}")

    thread_id = f"{context_type}-{context_id}"
    q = db.query(models.ChatMessage).filter(
        models.ChatMessage.user_id == current_user.id,
        models.ChatMessage.thread_id == thread_id,
    )
    # keyset 페이지네이션 (P8-2, Spring과 동일 계약) — 파라미터 없으면 기존 전체 반환(호환)
    if before_id is not None or limit is not None:
        size = min(limit or 100, 100)
        if before_id is not None:
            q = q.filter(models.ChatMessage.id < before_id)
        rows = q.order_by(models.ChatMessage.id.desc()).limit(size).all()
        return list(reversed(rows))
    return q.order_by(models.ChatMessage.created_at).all()


# ─── POST: 메시지 1건 저장 ────────────────────────────────────────────
@router.post("/{context_type}/{context_id}", response_model=MessageOut)
def save_message(
    context_type: str,
    context_id: int,
    body: MessageIn,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if context_type not in VALID_CONTEXT_TYPES:
        raise HTTPException(status_code=400, detail=f"유효하지 않은 context_type: {context_type}")
    # assistant/agent 메시지는 서버가 스트림 종료 시 직접 저장한다 (H-5) — 클라이언트는 user만.
    if body.role != "user":
        raise HTTPException(status_code=403, detail="사용자 메시지만 저장할 수 있습니다.")

    msg = models.ChatMessage(
        thread_id=f"{context_type}-{context_id}",
        user_id=current_user.id,
        context_type=context_type,
        role=body.role,
        content=body.content,
    )
    db.add(msg)
    db.commit()
    db.refresh(msg)
    return msg


# ─── DELETE: 특정 컨텍스트의 대화 기록 전체 삭제 ────────────────────
@router.delete("/{context_type}/{context_id}")
def clear_chat_history(
    context_type: str,
    context_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if context_type not in VALID_CONTEXT_TYPES:
        raise HTTPException(status_code=400, detail=f"유효하지 않은 context_type: {context_type}")

    thread_id = f"{context_type}-{context_id}"
    deleted = (
        db.query(models.ChatMessage)
        .filter(
            models.ChatMessage.user_id == current_user.id,
            models.ChatMessage.thread_id == thread_id,
        )
        .delete()
    )
    db.commit()
    return {"deleted": deleted}
