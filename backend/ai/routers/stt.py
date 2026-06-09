import io
import os
import logging
from typing import Optional

import httpx
from fastapi import APIRouter, UploadFile, File, Form, Depends
from sqlalchemy.orm import Session

from database import get_db
from models import MeetingSession, SttSegment

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/stt", tags=["stt"])


async def _transcribe_local(data: bytes, filename: str, lang_code: str) -> tuple[str, list[dict]]:
    whisper_url = os.environ.get("WHISPER_URL", "http://workmaite-whisper:9000")
    async with httpx.AsyncClient(timeout=120.0) as client:
        resp = await client.post(
            f"{whisper_url}/asr",
            params={"language": lang_code, "output": "json"},
            files={"audio_file": (filename, data, "audio/webm")},
        )
        resp.raise_for_status()
        body = resp.json()
        text = body.get("text", "").strip()
        segments = body.get("segments", [])
        return text, segments


async def _transcribe_external(data: bytes, filename: str, lang_code: str) -> list[dict]:
    import openai
    client = openai.AsyncOpenAI(api_key=os.environ["OPENAI_API_KEY"])
    resp = await client.audio.transcriptions.create(
        model="gpt-4o-transcribe-diarize",
        file=(filename, io.BytesIO(data), "audio/webm"),
        language=lang_code,
        response_format="diarized_json",
    )
    return [
        {"speaker": seg.speaker, "text": seg.text, "start": seg.start, "end": seg.end}
        for seg in resp.segments
    ]


@router.post("/transcribe")
async def transcribe(
    audio:      UploadFile     = File(...),
    lang:       str            = Form("ko"),
    session_id: Optional[int]  = Form(None),
    db:         Session        = Depends(get_db),
):
    lang_code = lang.split("-")[0].lower() if lang else "ko"
    data      = await audio.read()
    filename  = audio.filename or "audio.webm"

    stt_type = "whisper"
    if session_id:
        row = db.query(MeetingSession).filter(MeetingSession.id == session_id).first()
        if row:
            stt_type = row.type

    segments: list[dict] = []
    full_text = ""

    try:
        if stt_type == "external":
            segments = await _transcribe_external(data, filename, lang_code)
            full_text = " ".join(seg["text"] for seg in segments)
            logger.info(f"[STT] OpenAI diarize API 완료: {len(segments)}개 세그먼트")
        else:
            full_text, local_segments = await _transcribe_local(data, filename, lang_code)
            logger.info(f"[STT] WhisperX 완료: {len(full_text)}자, {len(local_segments)}개 세그먼트")
            segments = [s for s in local_segments if s.get("text", "").strip()]
    except Exception as e:
        logger.error(f"[STT] 변환 실패 (type={stt_type}): {e}")

    if session_id and segments:
        try:
            for seg in segments:
                if not seg.get("text", "").strip():
                    continue
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

    return {"text": full_text, "segments": segments}
