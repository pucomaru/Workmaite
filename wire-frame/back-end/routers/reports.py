import os
from datetime import datetime
from typing import List
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import FileResponse
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
    submit: bool = Form(False),  # True면 즉시 제출, False면 draft
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    filename = f"{meeting_id}_{current_user.id}_{file.filename}"
    file_path = os.path.join(UPLOAD_DIR, filename)
    content = await file.read()
    with open(file_path, "wb") as f:
        f.write(content)

    new_status = "submitted" if submit else "draft"
    report = db.query(models.Report).filter(
        models.Report.meeting_id == meeting_id,
        models.Report.presenter_id == current_user.id,
    ).first()

    if report:
        report.file_path = file_path
        report.file_name = file.filename
        report.status = new_status
        report.submitted_at = datetime.utcnow() if submit else report.submitted_at
        report.review_comment = None  # 재업로드 시 기존 사유 초기화
    else:
        report = models.Report(
            meeting_id=meeting_id,
            presenter_id=current_user.id,
            file_path=file_path,
            file_name=file.filename,
            status=new_status,
            submitted_at=datetime.utcnow() if submit else None,
        )
        db.add(report)

    db.flush()

    if submit:
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
        event_type="report_submitted" if submit else "report_draft_saved",
        meeting_id=meeting_id,
        payload={"reporter": current_user.name, "file": file.filename, "status": new_status},
        actor_id=current_user.id,
    )
    db.add(event)
    db.commit()
    db.refresh(report)

    await manager.broadcast_meeting(meeting_id, {"type": "report_submitted", "report_id": report.id, "status": new_status})
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
    if data.comment is not None:
        report.review_comment = data.comment

    status_label = '승인' if data.status == 'approved' else '반려'
    notif_msg = f"보고서가 {status_label}되었습니다."
    if data.comment:
        notif_msg += f" 사유: {data.comment}"

    create_notification(
        db,
        user_id=report.presenter_id,
        type="report_reviewed",
        message=notif_msg,
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


@router.get("/reports/{report_id}/download")
def download_report(
    report_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    report = db.query(models.Report).filter(models.Report.id == report_id).first()
    if not report:
        raise HTTPException(status_code=404, detail="Not found")
    # 해당 meeting 구성원인지 확인
    member = db.query(models.MeetingMember).filter(
        models.MeetingMember.meeting_id == report.meeting_id,
        models.MeetingMember.user_id == current_user.id,
    ).first()
    if not member:
        raise HTTPException(status_code=403, detail="Access denied")
    if not report.file_path or not os.path.exists(report.file_path):
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(
        path=report.file_path,
        filename=report.file_name,
        media_type="application/octet-stream",
    )


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
