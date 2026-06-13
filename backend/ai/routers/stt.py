import io
import os
import logging
from typing import Optional

from fastapi import APIRouter, UploadFile, File, Form, Depends, HTTPException
from sqlalchemy.orm import Session

from auth import get_current_user
from access_guard import require_meeting_member_by_session
from database import get_db
import models
from models import SttSegment

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/stt", tags=["stt"])


async def _transcribe_openai(data: bytes, filename: str, lang_code: str) -> str:
    """OpenAI 음성 전사 (화자분리 없는 단순 전사 — 안정성·한국어 정확도 우선)."""
    import openai

    client = openai.AsyncOpenAI(api_key=os.environ["OPENAI_API_KEY"])
    resp = await client.audio.transcriptions.create(
        model=os.environ.get("STT_MODEL", "gpt-4o-mini-transcribe"),
        file=(filename, io.BytesIO(data), "audio/webm"),
        language=lang_code,
    )
    return (resp.text or "").strip()


@router.post("/transcribe")
async def transcribe(
    audio: UploadFile = File(...),
    lang: str = Form("ko"),
    session_id: Optional[int] = Form(None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    if session_id:
        require_meeting_member_by_session(db, current_user, session_id)
    lang_code = lang.split("-")[0].lower() if lang else "ko"
    data = await audio.read()
    filename = audio.filename or "audio.webm"

    # 단순 전사 (화자분리 없음)
    try:
        full_text = await _transcribe_openai(data, filename, lang_code)
    except Exception as e:
        logger.error(f"[STT] 전사 실패: {e}")
        raise HTTPException(
            status_code=502, detail="음성 인식에 실패했습니다. 다시 시도해주세요."
        )

    # DB 저장 — 화자 라벨 없이 텍스트만
    text_id: int | None = None
    if session_id and full_text.strip():
        try:
            obj = SttSegment(
                session_id=session_id,
                speaker_label="",  # 화자분리 미사용
                content=full_text.strip(),
                start_sec=0,
                end_sec=0,
                provider="openai",
            )
            db.add(obj)
            db.commit()
            text_id = obj.id
        except Exception as dbe:
            logger.warning(f"[STT] DB 저장 실패: {dbe}")
            db.rollback()

    return {"text": full_text, "segments": [], "text_id": text_id, "provider": "openai"}
