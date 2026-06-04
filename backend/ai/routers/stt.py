import os
import tempfile
import logging
from typing import Optional

import openai
from fastapi import APIRouter, UploadFile, File, Form, Depends
from sqlalchemy.orm import Session

from database import get_db
from models import SttSegment
from r2_storage import upload_bytes, get_content_type

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/stt", tags=["stt"])

# ── Whisper 로컬 모델 (fallback) ──────────────────────────────
_whisper_model = None

def _get_whisper():
    global _whisper_model
    if _whisper_model is None:
        try:
            import whisper
            model_name = os.getenv("WHISPER_MODEL", "tiny")
            _whisper_model = whisper.load_model(model_name)
        except Exception as e:
            logger.warning(f"[STT] 로컬 Whisper 로드 실패: {e}")
    return _whisper_model


def _openai_client():
    return openai.AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))


@router.post("/transcribe")
async def transcribe(
    audio:      UploadFile     = File(...),
    lang:       str            = Form("ko"),
    session_id: Optional[int]  = Form(None),
    db:         Session        = Depends(get_db),
):
    """
    음성 파일 → STT + 발화자 구분(diarization).

    우선순위:
    1. OpenAI gpt-4o-transcribe-diarize  (발화자 구분 포함)
    2. 로컬 Whisper fallback              (발화자 구분 없음)

    Response:
        { "text": "...", "segments": [{ "speaker": "A", "text": "...", "start": 0.0, "end": 3.2 }], "audio_url": "..." }
    """
    data     = await audio.read()
    filename = audio.filename or "audio.webm"
    suffix   = os.path.splitext(filename)[1] or ".webm"

    # lang 정규화: ko-KR → ko, en-US → en
    lang_code = lang.split("-")[0].lower() if lang else "ko"

    # ── R2 업로드 ─────────────────────────────────────────────
    audio_url = None
    try:
        audio_url = upload_bytes(data, f"audio/{filename}", get_content_type(filename))
    except Exception:
        pass

    # ── OpenAI Diarize 시도 ──────────────────────────────────
    segments: list[dict] = []
    full_text = ""
    used_openai = False

    try:
        client = _openai_client()
        mime = "audio/webm" if suffix == ".webm" else "audio/mpeg"
        result = await client.audio.transcriptions.create(
            model="gpt-4o-transcribe-diarize",
            file=(filename, data, mime),
            language=lang_code,
            response_format="diarized_json",
        )
        raw_segs = getattr(result, "segments", None) or []
        for seg in raw_segs:
            segments.append({
                "speaker": getattr(seg, "speaker", "A"),
                "text":    seg.text.strip(),
                "start":   float(getattr(seg, "start", 0.0)),
                "end":     float(getattr(seg, "end",   0.0)),
            })
        full_text  = " ".join(s["text"] for s in segments)
        used_openai = True
        logger.info(f"[STT] OpenAI diarize 완료: {len(segments)}개 세그먼트")

    except Exception as e:
        logger.warning(f"[STT] OpenAI diarize 실패 → 로컬 Whisper 시도: {e}")

    # ── Whisper fallback ──────────────────────────────────────
    if not used_openai:
        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
                tmp.write(data); tmp_path = tmp.name
            model = _get_whisper()
            if model:
                wresult   = model.transcribe(tmp_path, language=lang_code)
                full_text = wresult["text"].strip()
                segments  = [{"speaker": "A", "text": full_text, "start": 0.0, "end": 0.0}]
        except Exception as we:
            logger.error(f"[STT] Whisper 실패: {we}")
        finally:
            if tmp_path:
                try: os.unlink(tmp_path)
                except Exception: pass

    # ── DB 저장 (session_id 있을 때만) ────────────────────────
    if session_id and segments:
        try:
            for seg in segments:
                db.add(SttSegment(
                    session_id    = session_id,
                    speaker_label = f"SPEAKER_{seg['speaker']}",
                    content       = seg["text"],
                    start_sec     = seg["start"],
                    end_sec       = seg["end"],
                ))
            db.commit()
        except Exception as dbe:
            logger.warning(f"[STT] DB 저장 실패: {dbe}")
            db.rollback()

    return {"text": full_text, "segments": segments, "audio_url": audio_url}
