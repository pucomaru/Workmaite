import os
from datetime import datetime
from typing import List
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session, joinedload
import models, schemas
from database import get_db
from auth import get_current_user
from notifications import create_notification
from websocket_manager import manager

UPLOAD_DIR = "uploads"
router = APIRouter(prefix="/api", tags=["reports"])


@router.get("/meetings/{meeting_id}/reports", response_model=List[schemas.ReportOut])
def list_reports(
    meeting_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return (
        db.query(models.Report)
        .options(joinedload(models.Report.presenter))
        .filter(models.Report.meeting_id == meeting_id)
        .all()
    )


@router.post("/meetings/{meeting_id}/reports", response_model=schemas.ReportOut)
async def submit_report(
    meeting_id: int,
    file: UploadFile = File(...),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    filename = f"{meeting_id}_{current_user.id}_{file.filename}"
    file_path = os.path.join(UPLOAD_DIR, filename)
    content = await file.read()
    with open(file_path, "wb") as f:
        f.write(content)

    report = db.query(models.Report).filter(
        models.Report.meeting_id == meeting_id,
        models.Report.presenter_id == current_user.id,
    ).first()

    if report:
        report.file_path = file_path
        report.file_name = file.filename
        report.status = "submitted"
        report.submitted_at = datetime.utcnow()
    else:
        report = models.Report(
            meeting_id=meeting_id,
            presenter_id=current_user.id,
            file_path=file_path,
            file_name=file.filename,
            status="submitted",
            submitted_at=datetime.utcnow(),
        )
        db.add(report)

    db.flush()

    admins = db.query(models.MeetingMember).filter(
        models.MeetingMember.meeting_id == meeting_id,
        models.MeetingMember.role == "admin",
    ).all()
    meeting = db.query(models.Meeting).filter(models.Meeting.id == meeting_id).first()
    for a in admins:
        create_notification(
            db,
            user_id=a.user_id,
            type="report_submitted",
            message=f"{current_user.name}님이 '{meeting.title}' 보고서를 제출했습니다.",
            ref_id=meeting_id,
            ref_type="meeting",
        )

    event = models.TacitEvent(
        event_type="report_submitted",
        meeting_id=meeting_id,
        payload={"reporter": current_user.name, "file": file.filename},
        actor_id=current_user.id,
    )
    db.add(event)
    db.commit()
    db.refresh(report)

    await manager.broadcast_meeting(meeting_id, {"type": "report_submitted", "report_id": report.id})
    return report


@router.patch("/reports/{report_id}/status", response_model=schemas.ReportOut)
async def update_report_status(
    report_id: int,
    data: schemas.ReportStatusUpdate,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    report = db.query(models.Report).filter(models.Report.id == report_id).first()
    if not report:
        raise HTTPException(status_code=404, detail="Not found")

    report.status = data.status
    if data.status == "approved":
        report.approved_at = datetime.utcnow()

    create_notification(
        db,
        user_id=report.presenter_id,
        type="report_reviewed",
        message=f"보고서가 {'승인' if data.status == 'approved' else '반려'}되었습니다.",
        ref_id=report.meeting_id,
        ref_type="meeting",
    )

    event = models.TacitEvent(
        event_type=f"report_{data.status}",
        meeting_id=report.meeting_id,
        payload={"report_id": report_id, "status": data.status},
        actor_id=current_user.id,
    )
    db.add(event)
    db.commit()
    db.refresh(report)

    await manager.broadcast_meeting(report.meeting_id, {
        "type": "report_status_updated",
        "report_id": report_id,
        "status": data.status,
    })
    return report


@router.get("/all-reports")
def get_all_reports(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    member_rows = db.query(models.MeetingMember).filter(
        models.MeetingMember.user_id == current_user.id
    ).all()
    meeting_ids = [r.meeting_id for r in member_rows]

    reports = (
        db.query(models.Report)
        .options(joinedload(models.Report.presenter))
        .filter(models.Report.meeting_id.in_(meeting_ids))
        .order_by(models.Report.submitted_at.desc().nullsfirst())
        .all()
    )
    meetings = {m.id: m for m in db.query(models.Meeting).filter(models.Meeting.id.in_(meeting_ids)).all()}

    result = []
    for r in reports:
        meeting = meetings.get(r.meeting_id)
        result.append({
            "id": r.id,
            "meeting_id": r.meeting_id,
            "meeting_title": meeting.title if meeting else "-",
            "presenter_name": r.presenter.name if r.presenter else "-",
            "file_name": r.file_name,
            "status": r.status,
            "submitted_at": r.submitted_at,
            "approved_at": r.approved_at,
        })
    return result
