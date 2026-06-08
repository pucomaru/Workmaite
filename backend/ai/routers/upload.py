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

@router.post("/reports/{meeting_id}")
async def upload_report(
    meeting_id: int,
    file: UploadFile = File(...),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """보고자료를 R2에 업로드하고 reports 테이블에 저장합니다."""
    content = await file.read()
    if len(content) > _MAX_BYTES:
        raise HTTPException(status_code=413, detail="파일 크기는 50MB를 초과할 수 없습니다.")

    meeting = db.query(models.Meeting).filter(models.Meeting.id == meeting_id).first()
    if not meeting:
        raise HTTPException(status_code=404, detail="회의체를 찾을 수 없습니다.")

    key, stored_name = _unique_key(f"reports/{meeting_id}", file.filename or "file")
    r2_url = upload_bytes(content, key, get_content_type(file.filename or ""))

    report = models.Report(
        meeting_id=meeting_id,
        upload_id=current_user.id,
        file_name=stored_name,
        file_path=r2_url,
        human_status="pending",
        submitter_department=current_user.department or "",
    )
    db.add(report)
    db.commit()
    db.refresh(report)

    return {
        "id": report.id,
        "file_name": stored_name,
        "file_path": r2_url,
        "meeting_id": meeting_id,
    }


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
