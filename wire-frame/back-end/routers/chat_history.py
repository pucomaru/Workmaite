from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List
from datetime import datetime

import models
from database import get_db
from auth import get_current_user

router = APIRouter(prefix="/api/chats", tags=["chat_history"])

VALID_CONTEXT_TYPES = {"agenda", "prepare", "todo", "cardnews", "room"}


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
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if context_type not in VALID_CONTEXT_TYPES:
        raise HTTPException(status_code=400, detail=f"유효하지 않은 context_type: {context_type}")

    messages = (
        db.query(models.ChatMessage)
        .filter(
            models.ChatMessage.user_id == current_user.id,
            models.ChatMessage.context_type == context_type,
            models.ChatMessage.context_id == context_id,
        )
        .order_by(models.ChatMessage.created_at)
        .all()
    )
    return messages


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
    if body.role not in ("user", "agent"):
        raise HTTPException(status_code=400, detail="role은 'user' 또는 'agent'여야 합니다")

    msg = models.ChatMessage(
        user_id=current_user.id,
        context_type=context_type,
        context_id=context_id,
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

    deleted = (
        db.query(models.ChatMessage)
        .filter(
            models.ChatMessage.user_id == current_user.id,
            models.ChatMessage.context_type == context_type,
            models.ChatMessage.context_id == context_id,
        )
        .delete()
    )
    db.commit()
    return {"deleted": deleted}
