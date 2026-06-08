"""upload.py — 파일 업로드 엔드포인트 (Cloudflare R2)

경로 규칙:
  reports/{meeting_id}/{uuid}_{filename}
  minutes/{session_id}/{uuid}_minutes.pdf   ← HTML→PDF 변환 후 저장
  chat/{thread_id}/{uuid}_{filename}

Ingress: /api/upload → FastAPI (workmaite-ai:8000)
"""
import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session
from weasyprint import CSS, HTML as WeasyHTML

import models
from auth import get_current_user
from database import get_db
from r2_storage import generate_presigned_url, get_content_type, upload_bytes, url_to_key

router = APIRouter(prefix="/api/upload", tags=["upload"])

_MAX_BYTES = 50 * 1024 * 1024  # 50 MB


def _unique_key(prefix: str, filename: str) -> tuple[str, str]:
    """중복 없는 R2 오브젝트 키와 저장용 파일명을 반환합니다."""
    safe = filename.replace(" ", "_")
    uid = uuid.uuid4().hex[:8]
    return f"{prefix}/{uid}_{safe}", f"{uid}_{safe}"


_PDF_CSS = CSS(string="""
    body {
        font-family: 'Noto Sans CJK KR', 'NanumGothic', Arial, sans-serif;
        font-size: 11pt; line-height: 1.8; color: #1e293b;
        padding: 40px 50px; max-width: 680px; margin: 0 auto;
    }
    h1 { font-size: 17pt; font-weight: bold; border-bottom: 2px solid #e2e8f0; padding-bottom: 8px; margin-bottom: 14px; }
    h2 { font-size: 13pt; font-weight: bold; color: #1e40af; margin-top: 18px; margin-bottom: 6px; }
    h3 { font-size: 11pt; font-weight: bold; color: #475569; margin-top: 12px; margin-bottom: 4px; }
    p  { margin: 0 0 6px; }
    ul, ol { padding-left: 20px; margin: 4px 0; }
    li { margin-bottom: 2px; }
    table { width: 100%; border-collapse: collapse; margin: 8px 0; font-size: 10pt; }
    th, td { border: 1px solid #e2e8f0; padding: 5px 8px; text-align: left; }
    th { background: #f1f5f9; font-weight: bold; }
    hr { border: none; border-top: 1px solid #e2e8f0; margin: 12px 0; }
""")


def _html_to_pdf(html_content: str, title: str = "회의록") -> bytes:
    """HTML 문자열을 PDF bytes로 변환합니다."""
    full_html = (
        f'<!DOCTYPE html><html><head><meta charset="utf-8"><title>{title}</title></head>'
        f"<body>{html_content}</body></html>"
    )
    return WeasyHTML(string=full_html).write_pdf(stylesheets=[_PDF_CSS])


# ── 보고자료 업로드 ────────────────────────────────────────────────────────────

@router.get("/reports/rejected")
async def get_rejected_reports(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """현재 사용자가 업로드한 rejected 보고서 목록을 반환합니다."""
    from sqlalchemy.orm import aliased
    # 재제출된 항목(자식 버전이 있는 항목) 제외
    from sqlalchemy import exists
    resubmitted_ids = db.query(models.Report.parent_id).filter(
        models.Report.parent_id.isnot(None)
    ).subquery()

    rows = (
        db.query(models.Report, models.ReportScore)
        .outerjoin(models.ReportScore, models.ReportScore.report_id == models.Report.id)
        .filter(
            models.Report.upload_id == current_user.id,
            models.Report.human_status == "rejected",
            ~models.Report.id.in_(resubmitted_ids),
        )
        .order_by(models.Report.created_at.desc())
        .all()
    )
    return [
        {
            "id": r.id,
            "file_name": r.file_name,
            "meeting_id": r.meeting_id,
            "submitter_department": r.submitter_department,
            "version": r.version,
            "total_score": rs.total_score if rs else None,
        }
        for r, rs in rows
    ]


@router.post("/reports/{meeting_id}")
async def upload_report(
    meeting_id: int,
    file: UploadFile = File(...),
    dept_name: Optional[str] = Form(None),
    parent_report_id: Optional[int] = Form(None),
    related_agenda_ids: Optional[str] = Form("[]"),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """보고자료를 R2에 업로드하고 reports 테이블에 pending 상태로 저장합니다."""
    content = await file.read()
    if len(content) > _MAX_BYTES:
        raise HTTPException(status_code=413, detail="파일 크기는 50MB를 초과할 수 없습니다.")

    meeting = db.query(models.Meeting).filter(models.Meeting.id == meeting_id).first()
    if not meeting:
        raise HTTPException(status_code=404, detail="회의체를 찾을 수 없습니다.")

    original_name = file.filename or "file"
    key, _ = _unique_key(f"reports/{meeting_id}", original_name)
    r2_url = upload_bytes(content, key, get_content_type(original_name))

    version = 1
    if parent_report_id:
        parent = db.query(models.Report).filter(models.Report.id == parent_report_id).first()
        if parent:
            version = parent.version + 1

    import json as _json
    try:
        agenda_ids = _json.loads(related_agenda_ids or "[]")
    except Exception:
        agenda_ids = []

    report = models.Report(
        meeting_id=meeting_id,
        upload_id=current_user.id,
        file_name=original_name,
        file_path=r2_url,
        human_status="pending",
        submitter_department=dept_name or current_user.department or "",
        parent_id=parent_report_id,
        version=version,
        related_agenda_ids=agenda_ids,
    )
    db.add(report)
    db.commit()
    db.refresh(report)

    return {
        "id": report.id,
        "file_name": original_name,
        "file_path": r2_url,
        "meeting_id": meeting_id,
    }


@router.post("/reports/{report_id}/score")
async def save_report_score(
    report_id: int,
    data: dict,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """AI 검토 완료 후 report_scores 테이블에 결과를 저장합니다."""
    import json as _json

    report = db.query(models.Report).filter(models.Report.id == report_id).first()
    if not report:
        raise HTTPException(status_code=404, detail="보고서를 찾을 수 없습니다.")

    feedback = data.get("feedback", [])
    feedback_text = "\n".join(feedback) if isinstance(feedback, list) else (feedback or "")
    detail_scores = data.get("detail_scores") or {}

    existing = db.query(models.ReportScore).filter(models.ReportScore.report_id == report_id).first()
    if existing:
        existing.ai_status = "success"
        existing.total_score = data.get("score")
        existing.detail_scores = detail_scores
        existing.feedback = feedback_text
    else:
        db.add(models.ReportScore(
            report_id=report_id,
            ai_status="success",
            total_score=data.get("score"),
            detail_scores=detail_scores,
            feedback=feedback_text,
        ))

    db.commit()
    return {"status": "ok"}


@router.post("/reports/{report_id}/review")
async def submit_report_review(
    report_id: int,
    data: dict,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """사람의 보고서 검토 결과(승인/반려 + 피드백)를 저장합니다."""
    import json as _json
    from datetime import datetime as _dt
    from sqlalchemy import desc as _desc

    report = db.query(models.Report).filter(models.Report.id == report_id).first()
    if not report:
        raise HTTPException(status_code=404, detail="보고서를 찾을 수 없습니다.")

    action = data.get("action")  # "approved" or "rejected"
    if action not in ("approved", "rejected"):
        raise HTTPException(status_code=400, detail="action은 approved 또는 rejected여야 합니다.")

    report.human_status = action

    # 최종 아젠다 연결 업데이트 (step 2에서 사용자가 선택/확정한 값)
    if "related_agenda_ids" in data:
        report.related_agenda_ids = data["related_agenda_ids"]

    # 가장 최근 agent_log 연결 (archive_analyze_stream)
    agent_log = (
        db.query(models.AgentLog)
        .filter(
            models.AgentLog.user_id == current_user.id,
            models.AgentLog.context_type == "archive_analyze_stream",
        )
        .order_by(_desc(models.AgentLog.created_at))
        .first()
    )

    review_prompt = data.get("ai_result", {})
    review_comment = {"comment": data.get("feedback", "")}

    db.add(models.HitlReview(
        agent_log_id=agent_log.id if agent_log else None,
        target_type="report",
        target_id=report_id,
        review_prompt=review_prompt,      # dict → JSONB
        ai_rationale=data.get("ai_rationale", ""),
        status=action,
        reviewer_id=current_user.id,
        review_comment=review_comment,    # dict → JSONB
        reviewed_at=_dt.utcnow(),
    ))

    db.commit()
    return {"status": "ok", "action": action}


@router.delete("/reports/{report_id}")
async def delete_report(
    report_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """보고서를 R2, report_scores, hitl_reviews, reports 테이블에서 삭제합니다."""
    report = db.query(models.Report).filter(models.Report.id == report_id).first()
    if not report:
        raise HTTPException(status_code=404, detail="보고서를 찾을 수 없습니다.")

    # R2에서 파일 삭제
    if report.file_path:
        try:
            from r2_storage import url_to_key
            import boto3, os
            key = url_to_key(report.file_path)
            s3 = boto3.client(
                "s3",
                endpoint_url=os.environ["R2_ENDPOINT"],
                aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
                aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
            )
            s3.delete_object(Bucket="workmaite-bucket", Key=key)
        except Exception as e:
            pass  # R2 삭제 실패해도 DB는 삭제

    # DB 삭제 (report_scores, hitl_reviews는 FK cascade 없으므로 직접 삭제)
    db.query(models.ReportScore).filter(models.ReportScore.report_id == report_id).delete()
    db.query(models.HitlReview).filter(
        models.HitlReview.target_type == "report",
        models.HitlReview.target_id == report_id,
    ).delete()
    db.delete(report)
    db.commit()
    return {"status": "ok"}


# ── 회의록 HTML → PDF 변환 후 R2 저장 ───────────────────────────────────────

@router.post("/minutes/{session_id}")
async def upload_minutes(
    session_id: int,
    content: str = Form(...),  # Tiptap 에디터 HTML
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Tiptap HTML을 PDF로 변환하여 R2에 저장하고 minutes 테이블에 upsert합니다."""
    session = db.query(models.MeetingSession).filter(models.MeetingSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="세션을 찾을 수 없습니다.")

    try:
        pdf_bytes = _html_to_pdf(content, session.title or f"회의록_{session_id}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"PDF 변환 실패: {e}")

    key, stored_name = _unique_key(f"minutes/{session_id}", "minutes.pdf")
    r2_url = upload_bytes(pdf_bytes, key, "application/pdf")

    existing = db.query(models.Minutes).filter(models.Minutes.session_id == session_id).first()
    if existing:
        existing.file_name = stored_name
        existing.file_path = r2_url
        existing.recorder_id = current_user.id
        existing.generated_at = datetime.utcnow()
        existing.content_summary = content
        minutes = existing
    else:
        minutes = models.Minutes(
            session_id=session_id,
            file_name=stored_name,
            file_path=r2_url,
            recorder_id=current_user.id,
            content_summary=content,
        )
        db.add(minutes)

    db.commit()
    db.refresh(minutes)

    return {
        "id": minutes.id,
        "file_name": stored_name,
        "file_path": r2_url,
        "session_id": session_id,
    }


# ── 채팅 첨부파일 업로드 ───────────────────────────────────────────────────────

@router.post("/chat")
async def upload_chat_file(
    file: UploadFile = File(...),
    thread_id: str = Form(...),
    context_type: Optional[str] = Form(None),
    meeting_id: Optional[int] = Form(None),
    session_id: Optional[int] = Form(None),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """채팅 첨부파일을 R2에 업로드하고 chat_messages 테이블에 저장합니다."""
    content = await file.read()
    if len(content) > _MAX_BYTES:
        raise HTTPException(status_code=413, detail="파일 크기는 50MB를 초과할 수 없습니다.")

    key, stored_name = _unique_key(f"chat/{thread_id}", file.filename or "file")
    r2_url = upload_bytes(content, key, get_content_type(file.filename or ""))

    msg = models.ChatMessage(
        thread_id=thread_id,
        user_id=current_user.id,
        role="user",
        content=f"[첨부파일] {stored_name}",
        file_path=r2_url,
        file_name=stored_name,
        context_type=context_type,
        meeting_id=meeting_id,
        session_id=session_id,
    )
    db.add(msg)
    db.commit()
    db.refresh(msg)

    return {
        "id": msg.id,
        "file_name": stored_name,
        "file_path": r2_url,
        "thread_id": thread_id,
    }


# ── Presigned URL 다운로드 ────────────────────────────────────────────────────

@router.get("/presigned")
def get_presigned_url(
    file_path: str,
    expires_in: int = 3600,
    current_user: models.User = Depends(get_current_user),
):
    """R2 file_path로 시간 제한 presigned URL을 생성합니다.

    Query params:
      file_path  : DB에 저장된 R2 URL 또는 object key
      expires_in : 유효 시간(초), 기본 1시간
    """
    if expires_in < 60 or expires_in > 86400:
        raise HTTPException(status_code=400, detail="expires_in은 60~86400 사이여야 합니다.")

    key = url_to_key(file_path)
    try:
        url = generate_presigned_url(key, expires_in)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"presigned URL 생성 실패: {e}")

    return {"url": url, "expires_in": expires_in}
