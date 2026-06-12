import io
import os
import logging
from typing import Optional

from datetime import datetime

from fastapi import APIRouter, UploadFile, File, Form, Depends, HTTPException
from pydantic import BaseModel
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
        model=os.environ.get("STT_MODEL", "gpt-4o-transcribe"),
        file=(filename, io.BytesIO(data), "audio/webm"),
        language=lang_code,
    )
    return (resp.text or "").strip()


class SaveSegmentsRequest(BaseModel):
    session_id: int
    segments: list[dict]  # [{text, start, end}]


def _wlk_time_to_sec(t: str) -> float:
    """'0:00:03' 또는 '0:03' → 초 단위 float"""
    try:
        parts = [float(x) for x in str(t).split(":")]
        if len(parts) == 3:
            return parts[0] * 3600 + parts[1] * 60 + parts[2]
        if len(parts) == 2:
            return parts[0] * 60 + parts[1]
        return parts[0]
    except Exception:
        return 0.0


@router.post("/save")
async def save_wlk_segments(
    body: SaveSegmentsRequest,
    db:   Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """WhisperLiveKit WebSocket에서 받은 세그먼트를 DB에 저장하고 ID를 반환합니다."""
    require_meeting_member_by_session(db, current_user, body.session_id)
    saved = []
    for seg in body.segments:
        text = (seg.get("text") or "").strip()
        if not text:
            continue
        obj = SttSegment(
            session_id    = body.session_id,
            speaker_label = "",  # 화자분리 미사용
            content       = text,
            start_sec     = _wlk_time_to_sec(seg.get("start", 0)),
            end_sec       = _wlk_time_to_sec(seg.get("end", 0)),
        )
        db.add(obj)
        saved.append((obj, seg))
    try:
        db.commit()
        for obj, seg in saved:
            db.refresh(obj)
            seg["id"] = obj.id
    except Exception as e:
        logger.warning(f"[STT/save] DB 저장 실패: {e}")
        db.rollback()
        return {"segments": body.segments}
    return {"segments": [s for _, s in saved]}


@router.post("/transcribe")
async def transcribe(
    audio:      UploadFile     = File(...),
    lang:       str            = Form("ko"),
    session_id: Optional[int]  = Form(None),
    stt_mode:   Optional[str]  = Form(None),   # ctrl-bar 선택값 (우선순위 최고)
    db:         Session        = Depends(get_db),
    current_user: models.User  = Depends(get_current_user),
):
    # stt_mode는 더 이상 사용하지 않음(화자분리 폐기) — 호환 위해 파라미터만 유지
    if session_id:
        require_meeting_member_by_session(db, current_user, session_id)
    lang_code = lang.split("-")[0].lower() if lang else "ko"
    data      = await audio.read()
    filename  = audio.filename or "audio.webm"

    # 단순 전사 (화자분리 없음)
    try:
        full_text = await _transcribe_openai(data, filename, lang_code)
    except Exception as e:
        logger.error(f"[STT] 전사 실패: {e}")
        raise HTTPException(status_code=502, detail="음성 인식에 실패했습니다. 다시 시도해주세요.")

    # DB 저장 — 화자 라벨 없이 텍스트만
    text_id: int | None = None
    if session_id and full_text.strip():
        try:
            obj = SttSegment(
                session_id    = session_id,
                speaker_label = "",      # 화자분리 미사용
                content       = full_text.strip(),
                start_sec     = 0,
                end_sec       = 0,
                provider      = "openai",
            )
            db.add(obj)
            db.commit()
            text_id = obj.id
        except Exception as dbe:
            logger.warning(f"[STT] DB 저장 실패: {dbe}")
            db.rollback()

    # 원본 오디오 보존 (P4-2): 세션별로 R2에 누적 저장 — 재처리 대비
    if session_id:
        try:
            from r2_storage import upload_bytes
            ts = datetime.utcnow().strftime("%H%M%S_%f")
            upload_bytes(data, f"sessions/{session_id}/audio/{ts}_{filename}", "audio/webm")
        except Exception as ae:
            logger.warning(f"[STT] 원음 R2 보존 실패(무시): {ae}")

    return {"text": full_text, "segments": [], "text_id": text_id, "provider": "openai"}
