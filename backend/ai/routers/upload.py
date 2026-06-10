"""upload.py — 파일 업로드 엔드포인트 (Cloudflare R2)

경로 규칙:
  reports/{meeting_id}/{uuid}_{filename}
  minutes/{session_id}/{uuid}_minutes.pdf   ← HTML→PDF 변환 후 저장
  chat/{thread_id}/{uuid}_{filename}

Ingress: /api/upload → FastAPI (workmaite-ai:8000)
"""
import logging
import uuid
from datetime import datetime
from io import BytesIO
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import text
from sqlalchemy.orm import Session
from xhtml2pdf import pisa

import json
import models
from auth import get_current_user
from database import get_db
from fastapi.responses import StreamingResponse
from r2_storage import generate_presigned_url, get_content_type, upload_bytes, url_to_key

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/upload", tags=["upload"])

_MAX_BYTES = 100 * 1024 * 1024  # 100 MB


def _unique_key(prefix: str, filename: str) -> tuple[str, str]:
    """중복 없는 R2 오브젝트 키와 저장용 파일명을 반환합니다."""
    safe = filename.replace(" ", "_")
    uid = uuid.uuid4().hex[:8]
    return f"{prefix}/{uid}_{safe}", f"{uid}_{safe}"


_KOREAN_FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",               # Linux (Nanum)
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",        # Linux (Noto)
    "/System/Library/Fonts/Supplemental/AppleGothic.ttf",            # macOS
    "/System/Library/Fonts/Supplemental/NotoSansGothic-Regular.ttf", # macOS
]

def _korean_font_face() -> str:
    import os
    for path in _KOREAN_FONT_CANDIDATES:
        if os.path.exists(path):
            logger.info(f"[PDF폰트] 사용: {path}")
            return f"@font-face {{ font-family: 'KoreanFont'; src: url('{path}'); }}\n"
    logger.warning("[PDF폰트] 한글 폰트를 찾지 못했습니다.")
    return ""

_PDF_CSS_BASE = """
body {
    font-family: 'KoreanFont', sans-serif;
    font-size: 11pt; line-height: 1.8; color: #1e293b;
    padding: 40px 50px;
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
"""


def _html_to_pdf(html_content: str, title: str = "회의록") -> bytes:
    """HTML 문자열을 PDF bytes로 변환합니다."""
    logger.info(f"[PDF변환] 시작 — title={title!r}, HTML 길이={len(html_content)}자")
    css = _korean_font_face() + _PDF_CSS_BASE
    full_html = (
        f'<!DOCTYPE html><html><head>'
        f'<meta charset="utf-8"><title>{title}</title>'
        f'<style>{css}</style>'
        f'</head><body>{html_content}</body></html>'
    )
    buf = BytesIO()
    result = pisa.CreatePDF(full_html.encode("utf-8"), dest=buf, encoding="utf-8")
    if result.err:
        raise RuntimeError(f"xhtml2pdf 변환 오류: {result.err}")
    pdf_bytes = buf.getvalue()
    logger.info(f"[PDF변환] 완료 — PDF 크기={len(pdf_bytes)} bytes")
    if len(pdf_bytes) == 0:
        raise RuntimeError("PDF 변환 결과가 비어있습니다 (0 bytes)")
    return pdf_bytes


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
    background_tasks: BackgroundTasks,
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

    from file_embedder import embed_and_store as _embed_and_store
    background_tasks.add_task(
        _embed_and_store, r2_url, original_name, "report", meeting_id, f"report-{report.id}"
    )

    try:
        from neo4j_sync import sync_report as _sync_report
        import asyncio
        asyncio.create_task(_sync_report(
            report_id=report.id,
            meeting_id=meeting_id,
            file_name=original_name,
            file_path=r2_url,
            submitter_department=report.submitter_department,
            human_status="pending",
            related_agenda_ids=agenda_ids,
            created_at=report.created_at.isoformat() if report.created_at else None,
        ))
    except Exception:
        pass

    return {
        "id": report.id,
        "file_name": original_name,
        "file_path": r2_url,
        "meeting_id": meeting_id,
    }


@router.get("/reports/{report_id}/score")
async def get_report_score(
    report_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """저장된 AI 검토 결과를 조회합니다 (pending 보고서 재검토용)."""
    report = db.query(models.Report).filter(models.Report.id == report_id).first()
    if not report:
        raise HTTPException(status_code=404, detail="보고서를 찾을 수 없습니다.")

    rs = db.query(models.ReportScore).filter(models.ReportScore.report_id == report_id).first()

    report_info = {
        "id": report.id,
        "file_name": report.file_name,
        "file_path": report.file_path,
        "human_status": report.human_status,
        "related_agenda_ids": report.related_agenda_ids or [],
    }

    # 아직 AI 검토가 없으면 빈 결과 반환 (404 대신 200)
    if not rs:
        return {
            "score": None,
            "detail_scores": {},
            "top_improvements": [],
            "feedback": [],
            "report": report_info,
        }

    feedback = rs.feedback.split("\n") if rs.feedback else []
    detail_scores = dict(rs.detail_scores or {})
    top_improvements = detail_scores.pop("_top_improvements", [])
    return {
        "score": rs.total_score,
        "detail_scores": detail_scores,
        "top_improvements": top_improvements,
        "feedback": feedback,
        "report": report_info,
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
    detail_scores = dict(data.get("detail_scores") or {})
    top_improvements = data.get("top_improvements") or []
    if top_improvements:
        detail_scores["_top_improvements"] = top_improvements

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

    # approved 시 연결된 아젠다 자동 완료
    if action == "approved":
        import re as _re
        def _parse_agenda_pg_id(v):
            s = str(v)
            if s.isdigit():
                return int(s)
            m = _re.search(r'\d+$', s)  # "agenda-5" → 5
            return int(m.group()) if m else None

        pg_ids = [pid for i in (report.related_agenda_ids or [])
                  if (pid := _parse_agenda_pg_id(i)) is not None]
        if pg_ids:
            db.query(models.Agenda).filter(
                models.Agenda.id.in_(pg_ids),
                models.Agenda.status != "done",
            ).update({"status": "done"}, synchronize_session=False)

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
    # 자식 버전들의 parent_id를 삭제 대상의 parent로 재연결 (체인 유지, FK 제약 위반 방지)
    db.query(models.Report).filter(models.Report.parent_id == report_id).update({"parent_id": report.parent_id})
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
    logger.info(f"[minutes] 요청 — session_id={session_id}, user_id={current_user.id}, content_len={len(content)}")

    session = db.query(models.MeetingSession).filter(models.MeetingSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="세션을 찾을 수 없습니다.")

    try:
        pdf_bytes = _html_to_pdf(content, session.title or f"회의록_{session_id}")
    except Exception as e:
        logger.error(f"[minutes] PDF 변환 실패 — session_id={session_id}, error={e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"PDF 변환 실패: {e}")

    key, stored_name = _unique_key(f"minutes/{session_id}", "minutes.pdf")
    r2_url = upload_bytes(pdf_bytes, key, "application/pdf")
    logger.info(f"[minutes] R2 업로드 완료 — key={key}, url={r2_url}")

    # ── 파라미터 사전 확인 ──────────────────────────────────────────
    params = {
        "session_id":      session_id,
        "file_name":       stored_name,
        "file_path":       r2_url,
        "recorder_id":     current_user.id,
        "content_summary": content[:80] + "..." if len(content) > 80 else content,
    }
    logger.info(
        f"[minutes] UPSERT 파라미터 확인 — "
        f"session_id={params['session_id']!r}, "
        f"file_name={params['file_name']!r}, "
        f"file_path={params['file_path']!r}, "
        f"recorder_id={params['recorder_id']!r}"
    )

    # PostgreSQL native UPSERT — 원자적으로 INSERT or UPDATE
    try:
        result = db.execute(text("""
            INSERT INTO minutes (session_id, file_name, file_path, recorder_id, content_summary, status, generated_at)
            VALUES (:session_id, :file_name, :file_path, :recorder_id, :content_summary, 'DRAFT', NOW())
            ON CONFLICT (session_id) DO UPDATE SET
                file_name        = EXCLUDED.file_name,
                file_path        = EXCLUDED.file_path,
                recorder_id      = EXCLUDED.recorder_id,
                content_summary  = EXCLUDED.content_summary,
                generated_at     = NOW()
            RETURNING id
        """), {
            "session_id":      session_id,
            "file_name":       stored_name,
            "file_path":       r2_url,
            "recorder_id":     current_user.id,
            "content_summary": content,
        })

        row = result.fetchone()
        logger.info(f"[minutes] RETURNING 결과 — row={row!r} (None이면 UPSERT 미실행)")
        if row is None:
            db.rollback()
            raise HTTPException(status_code=500, detail="회의록 UPSERT 결과 없음 — RETURNING id가 None")

        minutes_id = row[0]
        db.commit()
        logger.info(f"[minutes] commit 완료 — minutes_id={minutes_id}")

        # ── commit 후 SELECT로 실제 저장 값 검증 ──────────────────
        verify = db.execute(text(
            "SELECT id, session_id, file_name, file_path FROM minutes WHERE id = :id"
        ), {"id": minutes_id}).fetchone()

        if verify is None:
            logger.error(f"[minutes] 저장 검증 실패 — id={minutes_id} 가 SELECT에서 조회되지 않음")
            raise HTTPException(status_code=500, detail="회의록 저장 검증 실패")

        logger.info(
            f"[minutes] 저장 검증 성공 — "
            f"id={verify[0]}, session_id={verify[1]}, "
            f"file_name={verify[2]!r}, file_path={verify[3]!r}"
        )

        if verify[2] != stored_name or verify[3] != r2_url:
            logger.error(
                f"[minutes] 저장 값 불일치! "
                f"expected file_name={stored_name!r} got={verify[2]!r}, "
                f"expected file_path={r2_url!r} got={verify[3]!r}"
            )
            raise HTTPException(status_code=500, detail="회의록 저장 값 불일치")

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"[minutes] DB 저장 실패 — session_id={session_id}, error={e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"회의록 DB 저장 실패: {e}")

    return {
        "id": minutes_id,
        "file_name": stored_name,
        "file_path": r2_url,
        "session_id": session_id,
    }


# ── 회의록 파일 직접 업로드 (PDF/기타 파일 → R2, minutes 테이블 upsert) ────────

@router.post("/minutes/{session_id}/file")
async def upload_minutes_file(
    session_id: int,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """기존 PDF 파일을 R2에 직접 업로드하고 minutes 테이블에 file_path를 upsert합니다."""
    logger.info(f"[minutes/file] 요청 — session_id={session_id}, user_id={current_user.id}, filename={file.filename!r}")

    session = db.query(models.MeetingSession).filter(models.MeetingSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="세션을 찾을 수 없습니다.")

    content = await file.read()
    if len(content) > _MAX_BYTES:
        raise HTTPException(status_code=413, detail="파일 크기는 100MB를 초과할 수 없습니다.")

    key, stored_name = _unique_key(f"minutes/{session_id}", file.filename or "minutes.pdf")
    r2_url = upload_bytes(content, key, get_content_type(file.filename or ""))
    logger.info(f"[minutes/file] R2 업로드 완료 — key={key}, url={r2_url}")

    try:
        result = db.execute(text("""
            INSERT INTO minutes (session_id, file_name, file_path, recorder_id, status, generated_at)
            VALUES (:session_id, :file_name, :file_path, :recorder_id, 'DRAFT', NOW())
            ON CONFLICT (session_id) DO UPDATE SET
                file_name    = EXCLUDED.file_name,
                file_path    = EXCLUDED.file_path,
                recorder_id  = EXCLUDED.recorder_id
            RETURNING id
        """), {
            "session_id":  session_id,
            "file_name":   stored_name,
            "file_path":   r2_url,
            "recorder_id": current_user.id,
        })
        row = result.fetchone()
        minutes_id = row[0]
        db.commit()
        logger.info(f"[minutes/file] DB 저장 성공 — id={minutes_id}, session_id={session_id}, file_path={r2_url!r}")
    except Exception as e:
        db.rollback()
        logger.error(f"[minutes/file] DB 저장 실패 — session_id={session_id}, error={e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"회의록 DB 저장 실패: {e}")

    session_obj = db.query(models.MeetingSession).filter(models.MeetingSession.id == session_id).first()
    meeting_id_for_embed = session_obj.meeting_id if session_obj else None
    from file_embedder import embed_and_store as _embed_and_store
    background_tasks.add_task(
        _embed_and_store, r2_url, stored_name, "minutes", meeting_id_for_embed, f"minutes-{minutes_id}"
    )

    return {
        "id": minutes_id,
        "file_name": stored_name,
        "file_path": r2_url,
        "session_id": session_id,
    }


# ── 채팅 첨부파일 업로드 ───────────────────────────────────────────────────────

@router.post("/chat")
async def upload_chat_file(
    background_tasks: BackgroundTasks,
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

    from file_embedder import embed_and_store as _embed_and_store
    background_tasks.add_task(
        _embed_and_store, r2_url, stored_name, context_type or "document", meeting_id, f"chat-{msg.id}"
    )

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
