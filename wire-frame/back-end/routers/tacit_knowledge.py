from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
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


@router.get("/meeting/{meeting_id}", response_model=List[schemas.TacitKnowledgeMeetingOut])
def list_meeting_knowledge(
    meeting_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return db.query(models.TacitKnowledgeMeeting).filter(
        models.TacitKnowledgeMeeting.meeting_id == meeting_id,
        models.TacitKnowledgeMeeting.status == "active",
    ).order_by(models.TacitKnowledgeMeeting.updated_at.desc()).all()


@router.post("/meeting/{meeting_id}", response_model=schemas.TacitKnowledgeMeetingOut)
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


@router.patch("/meeting-item/{kb_id}", response_model=schemas.TacitKnowledgeMeetingOut)
def update_meeting_knowledge(
    kb_id: int,
    data: schemas.TacitKnowledgeUpdate,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    kb = db.query(models.TacitKnowledgeMeeting).filter(
        models.TacitKnowledgeMeeting.id == kb_id
    ).first()
    if not kb:
        raise HTTPException(status_code=404, detail="Not found")
    if data.title:
        kb.title = data.title
    if data.content:
        kb.content = data.content
        kb.version += 1
    kb.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(kb)
    return kb


@router.delete("/meeting-item/{kb_id}")
def delete_meeting_knowledge(
    kb_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    kb = db.query(models.TacitKnowledgeMeeting).filter(
        models.TacitKnowledgeMeeting.id == kb_id
    ).first()
    if not kb:
        raise HTTPException(status_code=404, detail="Not found")
    kb.status = "archived"
    db.commit()
    return {"ok": True}


@router.post("/meeting/{meeting_id}/refresh")
async def refresh_meeting_memory(
    meeting_id: int,
    background_tasks: BackgroundTasks,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """AI가 현재 회의 활동을 분석해 메모리를 갱신합니다."""
    # Get latest loop number
    latest_loop = db.query(models.MeetingLoop).filter(
        models.MeetingLoop.meeting_id == meeting_id
    ).order_by(models.MeetingLoop.loop_number.desc()).first()
    loop_number = latest_loop.loop_number if latest_loop else 1
    background_tasks.add_task(_do_refresh_memory, meeting_id, loop_number)
    return {"ok": True, "message": "메모리 갱신을 시작했습니다."}


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


# ── Background: AI 메모리 갱신 ────────────────────────────────────────────────
async def _do_refresh_memory(meeting_id: int, loop_number: int):
    """AI가 회의 활동을 분석해 메모리를 카테고리별로 자동 갱신합니다."""
    import traceback
    from database import SessionLocal
    from agents.hyean import analyze_and_propose

    db = SessionLocal()
    try:
        meeting = db.query(models.Meeting).filter(models.Meeting.id == meeting_id).first()
        if not meeting:
            return

        # ── 활동 데이터 수집 ──────────────────────────────────
        events = [{"type": "meeting_context", "title": meeting.title}]

        msgs = (
            db.query(models.ChatMessage)
            .filter(models.ChatMessage.context_id == meeting_id)
            .order_by(models.ChatMessage.created_at.desc())
            .limit(40)
            .all()
        )
        for m in reversed(msgs):
            events.append({"type": "chat", "role": m.role, "content": m.content[:400]})

        agendas = (
            db.query(models.Agenda)
            .filter(models.Agenda.meeting_id == meeting_id)
            .order_by(models.Agenda.created_at.desc())
            .limit(10)
            .all()
        )
        for a in agendas:
            events.append({
                "type": "agenda",
                "department": a.department or "",
                "content": a.content[:300],
                "status": a.status,
            })

        todos = (
            db.query(models.Todo)
            .filter(models.Todo.meeting_id == meeting_id)
            .order_by(models.Todo.created_at.desc())
            .limit(15)
            .all()
        )
        for t in todos:
            events.append({"type": "todo", "content": t.content[:200], "status": t.status})

        # 회의록 (MinutesItem 이 있으면)
        try:
            minutes_items = (
                db.query(models.MinutesItem)
                .join(models.MeetingSession, models.MinutesItem.session_id == models.MeetingSession.id)
                .filter(models.MeetingSession.meeting_id == meeting_id)
                .order_by(models.MinutesItem.created_at.desc())
                .limit(10)
                .all()
            )
            for mi in minutes_items:
                events.append({"type": "minutes", "content": (mi.content or "")[:300]})
        except Exception:
            pass  # MinutesItem 모델 없을 수 있음

        if len(events) < 3:
            return

        # ── 현재 메모리 목록 ──────────────────────────────────
        current_memory = (
            db.query(models.TacitKnowledgeMeeting)
            .filter(
                models.TacitKnowledgeMeeting.meeting_id == meeting_id,
                models.TacitKnowledgeMeeting.status == "active",
            )
            .all()
        )
        current_knowledge = [
            {"id": k.id, "category": k.category, "title": k.title, "content": k.content[:300]}
            for k in current_memory
        ]

        # ── AI 분석: 카테고리별로 순회 ─────────────────────────
        categories = ["meeting_standard", "report_standard", "agenda_standard", "todo_standard"]
        updated = 0
        for cat in categories:
            cat_events = [e for e in events if e.get("type") in ("meeting_context", "chat", cat.split("_")[0])]
            # 해당 카테고리 관련 이벤트가 부족하면 스킵
            if len(cat_events) < 2:
                continue

            cat_knowledge = [k for k in current_knowledge if k["category"] == cat]

            try:
                proposal = await analyze_and_propose(
                    recent_events=events,  # 전체 컨텍스트 전달
                    current_knowledge=cat_knowledge,
                    scope="meeting",
                    meeting_id=meeting_id,
                )
            except Exception as e:
                print(f"[Memory Refresh] analyze_and_propose 실패 (category={cat}): {e}")
                continue

            if not proposal or not proposal.get("proposed_content"):
                continue

            # 제안된 카테고리 우선, 없으면 현재 cat 사용
            final_cat = proposal.get("category") or cat

            existing = next(
                (k for k in current_memory if k.category == final_cat), None
            )
            if existing:
                existing.content = proposal["proposed_content"]
                existing.title = proposal.get("title") or existing.title
                existing.version += 1
                existing.loop_number = loop_number
                existing.updated_at = datetime.utcnow()
            else:
                kb = models.TacitKnowledgeMeeting(
                    meeting_id=meeting_id,
                    category=final_cat,
                    title=proposal.get("title") or "회의 패턴",
                    content=proposal["proposed_content"],
                    loop_number=loop_number,
                )
                db.add(kb)
            updated += 1

        if updated > 0:
            db.commit()
            print(f"[Memory Refresh] meeting={meeting_id} loop={loop_number} → {updated}개 항목 갱신")
        else:
            print(f"[Memory Refresh] meeting={meeting_id}: AI 제안 없음 (이벤트 부족 or 변경 없음)")

    except Exception:
        print(f"[Memory Refresh Error] meeting={meeting_id}\n{traceback.format_exc()}")
        try:
            db.rollback()
        except Exception:
            pass
    finally:
        db.close()
