from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
import models, schemas
from database import get_db
from auth import get_current_user
from notifications import create_notification

router = APIRouter(prefix="/api/tacit-knowledge", tags=["tacit_knowledge"])


@router.get("/proposals", response_model=List[schemas.TacitProposalOut])
def list_proposals(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return db.query(models.TacitProposal).order_by(
        models.TacitProposal.created_at.desc()
    ).all()


@router.patch("/proposals/{proposal_id}", response_model=schemas.TacitProposalOut)
def review_proposal(
    proposal_id: int,
    data: schemas.ProposalReview,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    proposal = db.query(models.TacitProposal).filter(
        models.TacitProposal.id == proposal_id
    ).first()
    if not proposal:
        raise HTTPException(status_code=404, detail="Not found")

    proposal.reviewed_by = current_user.id
    proposal.reviewed_at = datetime.utcnow()

    if data.action == "accept":
        proposal.status = "accepted"
        proposal.final_content = proposal.proposed_content
        _apply_proposal(db, proposal)
    elif data.action == "reject":
        proposal.status = "rejected"
    elif data.action == "edit_accept":
        proposal.status = "edited_and_accepted"
        proposal.final_content = data.final_content
        _apply_proposal(db, proposal)

    db.commit()
    db.refresh(proposal)
    return proposal


def _apply_proposal(db: Session, proposal: models.TacitProposal):
    content = proposal.final_content or proposal.proposed_content
    if proposal.scope == "global":
        if proposal.target_id:
            kb = db.query(models.TacitKnowledgeGlobal).filter(
                models.TacitKnowledgeGlobal.id == proposal.target_id
            ).first()
            if kb:
                kb.content = content
                kb.version += 1
                kb.updated_at = datetime.utcnow()
        else:
            kb = models.TacitKnowledgeGlobal(
                category=proposal.category,
                title=proposal.title,
                content=content,
                source_event_ids=proposal.source_event_ids,
            )
            db.add(kb)
    else:
        if proposal.target_id:
            kb = db.query(models.TacitKnowledgeMeeting).filter(
                models.TacitKnowledgeMeeting.id == proposal.target_id
            ).first()
            if kb:
                kb.content = content
                kb.version += 1
                kb.updated_at = datetime.utcnow()
        else:
            kb = models.TacitKnowledgeMeeting(
                meeting_id=proposal.meeting_id,
                category=proposal.category,
                title=proposal.title,
                content=content,
                source_event_ids=proposal.source_event_ids,
            )
            db.add(kb)


@router.get("/global", response_model=List[schemas.TacitKnowledgeGlobalOut])
def list_global(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return db.query(models.TacitKnowledgeGlobal).filter(
        models.TacitKnowledgeGlobal.status == "active"
    ).all()


@router.post("/global", response_model=schemas.TacitKnowledgeGlobalOut)
def create_global(
    data: schemas.TacitKnowledgeCreate,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    kb = models.TacitKnowledgeGlobal(**data.model_dump())
    db.add(kb)
    db.commit()
    db.refresh(kb)
    return kb


@router.patch("/global/{kb_id}", response_model=schemas.TacitKnowledgeGlobalOut)
def update_global(
    kb_id: int,
    data: schemas.TacitKnowledgeUpdate,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    kb = db.query(models.TacitKnowledgeGlobal).filter(
        models.TacitKnowledgeGlobal.id == kb_id
    ).first()
    if not kb:
        raise HTTPException(status_code=404, detail="Not found")
    if data.title:
        kb.title = data.title
    if data.content:
        kb.content = data.content
        kb.version += 1
    if data.status:
        kb.status = data.status
    kb.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(kb)
    return kb


@router.get("/meeting/{meeting_id}", response_model=List)
def list_meeting_knowledge(
    meeting_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return db.query(models.TacitKnowledgeMeeting).filter(
        models.TacitKnowledgeMeeting.meeting_id == meeting_id,
        models.TacitKnowledgeMeeting.status == "active",
    ).all()


@router.post("/meeting/{meeting_id}")
def create_meeting_knowledge(
    meeting_id: int,
    data: schemas.TacitKnowledgeCreate,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    kb = models.TacitKnowledgeMeeting(meeting_id=meeting_id, **data.model_dump())
    db.add(kb)
    db.commit()
    db.refresh(kb)
    return kb


@router.get("/events", response_model=List[schemas.TacitEventOut])
def list_events(
    event_type: Optional[str] = Query(None),
    meeting_id: Optional[int] = Query(None),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    q = db.query(models.TacitEvent)
    if event_type:
        q = q.filter(models.TacitEvent.event_type == event_type)
    if meeting_id:
        q = q.filter(models.TacitEvent.meeting_id == meeting_id)
    return q.order_by(models.TacitEvent.created_at.desc()).limit(100).all()


@router.get("/summary")
def knowledge_summary(
    meeting_id: Optional[int] = Query(None),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    global_kb = db.query(models.TacitKnowledgeGlobal).filter(
        models.TacitKnowledgeGlobal.status == "active"
    ).all()
    meeting_kb = []
    if meeting_id:
        meeting_kb = db.query(models.TacitKnowledgeMeeting).filter(
            models.TacitKnowledgeMeeting.meeting_id == meeting_id,
            models.TacitKnowledgeMeeting.status == "active",
        ).all()
    pending_count = db.query(models.TacitProposal).filter(
        models.TacitProposal.status == "pending"
    ).count()

    return {
        "global": [{"id": k.id, "category": k.category, "title": k.title} for k in global_kb],
        "meeting": [{"id": k.id, "category": k.category, "title": k.title} for k in meeting_kb],
        "pending_proposals": pending_count,
    }
