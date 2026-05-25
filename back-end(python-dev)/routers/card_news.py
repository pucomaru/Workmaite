from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
import models, schemas
from database import get_db
from auth import get_current_user

router = APIRouter(prefix="/api", tags=["card_news"])


@router.get("/meetings/{meeting_id}/card-news", response_model=List[schemas.CardNewsOut])
def list_card_news(
    meeting_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return db.query(models.CardNews).filter(models.CardNews.meeting_id == meeting_id).all()


@router.get("/card-news/{card_id}", response_model=schemas.CardNewsOut)
def get_card_news(
    card_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    card = db.query(models.CardNews).filter(models.CardNews.id == card_id).first()
    if not card:
        raise HTTPException(status_code=404, detail="Not found")
    return card


@router.delete("/card-news/{card_id}")
def delete_card_news(
    card_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    card = db.query(models.CardNews).filter(models.CardNews.id == card_id).first()
    if not card:
        raise HTTPException(status_code=404, detail="Not found")
    # 관리자만 삭제 가능
    member = db.query(models.MeetingMember).filter(
        models.MeetingMember.meeting_id == card.meeting_id,
        models.MeetingMember.user_id == current_user.id,
    ).first()
    if not member or member.role != "admin":
        raise HTTPException(status_code=403, detail="관리자만 삭제할 수 있습니다.")
    db.delete(card)
    db.commit()
    return {"ok": True}
