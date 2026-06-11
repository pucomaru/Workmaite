import logging
import os
from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from pydantic import BaseModel
from sqlalchemy.orm import Session
from openai import AsyncOpenAI
import models, schemas
from database import get_db
from auth import get_current_user
from neo4j_sync import sync_minutes

_openai = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/ai", tags=["sessions"])


def _md_to_pdf(md_text: str) -> bytes:
    import markdown
    from routers.upload import _html_to_pdf
    html_body = markdown.markdown(md_text, extensions=["tables", "nl2br"])
    return _html_to_pdf(html_body)


# ─── 회의록 저장 ──────────────────────────────────────────────────────────────

class MinutesSaveRequest(BaseModel):
    content: str               # 생성된 회의록 전체 텍스트
    content_summary: Optional[str] = None  # 요약 (없으면 content 앞 500자 사용)
    file_name: Optional[str] = None        # 저장할 파일명 (없으면 자동 생성)


@router.post("/sessions/{session_id}/minutes", response_model=schemas.MinutesOut)
async def save_minutes(
    session_id: int,
    body: MinutesSaveRequest,
    background_tasks: BackgroundTasks,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    생성된 회의록을 R2에 업로드하고 PostgreSQL minutes 테이블에 저장합니다.
    스트리밍으로 생성 완료 후 프론트에서 최종 텍스트를 보내면 이 API를 호출합니다.
    """
    session = db.query(models.MeetingSession).filter(
        models.MeetingSession.id == session_id
    ).first()
    if not session:
        raise HTTPException(status_code=404, detail="세션을 찾을 수 없습니다.")

    # 파일명 결정 (.pdf)
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    base_name = body.file_name or f"minutes_{session_id}_{ts}"
    base_name = base_name.removesuffix(".pdf").removesuffix(".md")
    file_name = base_name + ".pdf"

    # MD → PDF 변환 후 R2 업로드
    r2_url: Optional[str] = None
    try:
        pdf_bytes = _md_to_pdf(body.content)
        from r2_storage import upload_bytes
        r2_url = upload_bytes(
            pdf_bytes,
            f"minutes/{session_id}/{file_name}",
            "application/pdf",
        )
        logger.info(f"[sessions/minutes] R2 업로드 완료 — session_id={session_id}, url={r2_url}")
    except Exception as e:
        logger.warning(f"[sessions/minutes] PDF 변환/R2 업로드 실패 (무시): {e}")

    summary = body.content_summary or body.content[:500]

    # minutes 테이블 upsert (session_id UNIQUE)
    existing = db.query(models.Minutes).filter(
        models.Minutes.session_id == session_id
    ).first()

    if existing:
        existing.content_original = body.content
        existing.content_summary  = summary
        existing.recorder_id      = current_user.id
        existing.generated_at     = datetime.utcnow()
        if r2_url:  # R2 업로드 실패 시 기존 file_path 보존
            existing.file_name = file_name
            existing.file_path = r2_url
        minutes = existing
    else:
        minutes = models.Minutes(
            session_id       = session_id,
            content_original = body.content,
            content_summary  = summary,
            file_name        = file_name if r2_url else None,
            file_path        = r2_url,
            recorder_id      = current_user.id,
        )
        db.add(minutes)

    db.commit()
    db.refresh(minutes)

    # Neo4j 동기화 (백그라운드)
    background_tasks.add_task(
        sync_minutes,
        minutes_id=minutes.id,
        session_id=session_id,
        content_summary=summary,
    )

    return minutes


# ─── 회의록 조회 ──────────────────────────────────────────────────────────────

@router.get("/sessions/{session_id}/minutes", response_model=schemas.MinutesOut)
def get_minutes(
    session_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    minutes = db.query(models.Minutes).filter(models.Minutes.session_id == session_id).first()
    if not minutes:
        raise HTTPException(status_code=404, detail="회의록을 찾을 수 없습니다.")
    return minutes


# ─── 회의록 내용 수정 ─────────────────────────────────────────────────────────

class MinutesContentUpdate(BaseModel):
    content: str
    content_summary: Optional[str] = None


@router.patch("/sessions/{session_id}/minutes", response_model=schemas.MinutesOut)
async def update_minutes_content(
    session_id: int,
    body: MinutesContentUpdate,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    minutes = db.query(models.Minutes).filter(models.Minutes.session_id == session_id).first()
    if not minutes:
        raise HTTPException(status_code=404, detail="회의록을 찾을 수 없습니다.")
    minutes.content_original = body.content
    minutes.content_summary = body.content_summary or body.content[:500]
    minutes.recorder_id = current_user.id
    minutes.generated_at = datetime.utcnow()
    db.commit()
    db.refresh(minutes)
    return minutes


# ─── 회의록 삭제 ──────────────────────────────────────────────────────────────

@router.delete("/sessions/{session_id}/minutes")
async def delete_minutes(
    session_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    minutes = db.query(models.Minutes).filter(models.Minutes.session_id == session_id).first()
    if not minutes:
        raise HTTPException(status_code=404, detail="회의록을 찾을 수 없습니다.")
    db.delete(minutes)
    db.commit()
    return {"ok": True}


# ─── 대화기록 문단 정제 ────────────────────────────────────────────────────────

class RefineChunkRequest(BaseModel):
    session_id: int
    text: str
    context: Optional[str] = None
    recording_start_sec: Optional[float] = None
    recording_end_sec: Optional[float] = None

class RefineChunkResponse(BaseModel):
    title: str
    bullets: List[str]


@router.post("/sessions/refine-chunk", response_model=RefineChunkResponse)
async def refine_chunk(
    body: RefineChunkRequest,
    db: Session = Depends(get_db),
    _: models.User = Depends(get_current_user),
):
    context_line = f"회의 맥락: {body.context}\n" if body.context else ""
    prompt = f"""{context_line}아래는 회의 중 발화된 원문입니다.
        다음 조건에 따라 정리해주세요:
        1. 필러워드(어, 음, 그, 아 등) 제거
        2. 오탈자 교정
        3. 핵심 내용을 나타내는 짧은 제목 1개 생성
        4. 핵심 내용을 3~5개 불릿포인트로 요약

        반드시 아래 JSON 형식으로만 응답하세요:
        {{"title": "제목", "bullets": ["• 내용1", "• 내용2", "• 내용3"]}}

        원문:
        {body.text}"""

    resp = await _openai.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"},
        temperature=0.3,
    )

    import json
    result = json.loads(resp.choices[0].message.content)
    title = result.get("title", "")
    bullets = result.get("bullets", [])

    block_index = db.query(models.SessionSummaryBlock).filter(
        models.SessionSummaryBlock.session_id == body.session_id
    ).count()
    db.add(models.SessionSummaryBlock(
        session_id=body.session_id,
        block_index=block_index,
        title=title,
        bullets=bullets,
        recording_start_sec=body.recording_start_sec,
        recording_end_sec=body.recording_end_sec,
    ))
    db.commit()

    return RefineChunkResponse(title=title, bullets=bullets)
