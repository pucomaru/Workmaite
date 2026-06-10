import io
import os
import asyncio
import logging
from typing import Optional

import httpx
from fastapi import APIRouter, UploadFile, File, Form, Depends
from sqlalchemy.orm import Session

from database import get_db
import models
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


def _speech_client():
    import json
    from google.cloud import speech
    from google.oauth2 import service_account

    raw = os.environ.get("GOOGLE_CLOUD_STT_CREDENTIALS", "").strip()
    if not raw:
        raise RuntimeError("GOOGLE_CLOUD_STT_CREDENTIALS 환경변수가 설정되지 않았습니다.")
    creds = service_account.Credentials.from_service_account_info(
        json.loads(raw),
        scopes=["https://www.googleapis.com/auth/cloud-platform"],
    )
    return speech.SpeechClient(credentials=creds)


async def _transcribe_cloud(data: bytes, lang_code: str, max_speakers: int = 6) -> list[dict]:
    """Google Cloud Speech-to-Text v1 — 화자 분리(diarization) 포함."""
    from google.cloud import speech

    lang_map = {
        "ko": "ko-KR", "en": "en-US", "ja": "ja-JP",
        "zh": "cmn-Hans-CN", "fr": "fr-FR", "de": "de-DE",
    }
    bcp47 = lang_map.get(lang_code, f"{lang_code}-{lang_code.upper()}")

    client = _speech_client()
    audio = speech.RecognitionAudio(content=data)
    config = speech.RecognitionConfig(
        encoding=speech.RecognitionConfig.AudioEncoding.WEBM_OPUS,
        language_code=bcp47,
        enable_automatic_punctuation=True,
        enable_word_time_offsets=True,
        diarization_config=speech.SpeakerDiarizationConfig(
            enable_speaker_diarization=True,
            min_speaker_count=1,
            max_speaker_count=max(2, max_speakers),
        ),
    )

    loop = asyncio.get_event_loop()
    response = await loop.run_in_executor(
        None, lambda: client.recognize(config=config, audio=audio)
    )

    segments: list[dict] = []
    for result in response.results:
        if not result.alternatives:
            continue
        alt = result.alternatives[0]
        words = list(alt.words)

        if not words:
            text = alt.transcript.strip()
            if text:
                segments.append({"speaker": "1", "text": text, "start": 0.0, "end": 0.0})
            continue

        # 연속된 동일 화자 단어를 하나의 세그먼트로 병합
        cur_speaker = str(words[0].speaker_tag)
        cur_words: list[str] = [words[0].word]
        cur_start = words[0].start_time.total_seconds()
        prev_end = words[0].end_time.total_seconds()

        for w in words[1:]:
            spk = str(w.speaker_tag)
            t_end = w.end_time.total_seconds()
            if spk == cur_speaker:
                cur_words.append(w.word)
                prev_end = t_end
            else:
                segments.append({
                    "speaker": cur_speaker,
                    "text": " ".join(cur_words),
                    "start": cur_start,
                    "end": prev_end,
                })
                cur_speaker = spk
                cur_words = [w.word]
                cur_start = w.start_time.total_seconds()
                prev_end = t_end

        if cur_words:
            segments.append({
                "speaker": cur_speaker,
                "text": " ".join(cur_words),
                "start": cur_start,
                "end": prev_end,
            })

    return segments


@router.post("/transcribe")
async def transcribe(
    audio:      UploadFile     = File(...),
    lang:       str            = Form("ko"),
    session_id: Optional[int]  = Form(None),
    stt_mode:   Optional[str]  = Form(None),   # ctrl-bar 선택값 (우선순위 최고)
    db:         Session        = Depends(get_db),
):
    lang_code = lang.split("-")[0].lower() if lang else "ko"
    data      = await audio.read()
    filename  = audio.filename or "audio.webm"

    effective_mode = stt_mode
    max_speakers   = 6

    if session_id:
        row = db.query(MeetingSession).filter(MeetingSession.id == session_id).first()
        if row:
            if not effective_mode:
                effective_mode = row.type
            member_count = db.query(models.MeetingMember).filter(
                models.MeetingMember.meeting_id == row.meeting_id
            ).count()
            if member_count > 0:
                max_speakers = member_count

    effective_mode = effective_mode or "localwhisper"

    segments: list[dict] = []
    full_text = ""

    try:
        if effective_mode == "whisperapi":
            segments = await _transcribe_external(data, filename, lang_code)
            full_text = " ".join(seg["text"] for seg in segments)
            logger.info(f"[STT] OpenAI diarize API 완료: {len(segments)}개 세그먼트")

        elif effective_mode == "gcapi":
            segments = await _transcribe_cloud(data, lang_code, max_speakers)
            full_text = " ".join(seg["text"] for seg in segments)
            logger.info(f"[STT] Cloud STT 완료: {len(segments)}개 세그먼트 (max_speakers={max_speakers})")

        else:  # localwhisper — 화자분리 없음, 전체 텍스트를 단일 항목으로 반환
            full_text, _ = await _transcribe_local(data, filename, lang_code)
            logger.info(f"[STT] WhisperX 완료: {len(full_text)}자")
            # segments는 비워서 프론트가 onResult(full_text) 단일 콜백을 쓰게 함

    except Exception as e:
        logger.error(f"[STT] 변환 실패 (mode={effective_mode}): {e}")

    # DB 저장: localwhisper는 full_text 단일 행, 나머지는 화자별 세그먼트
    if session_id and (segments or full_text.strip()):
        try:
            if segments:
                for seg in segments:
                    if not seg.get("text", "").strip():
                        continue
                    db.add(SttSegment(
                        session_id    = session_id,
                        speaker_label = f"SPEAKER_{seg.get('speaker', '0')}",
                        content       = seg["text"],
                        start_sec     = seg.get("start", 0),
                        end_sec       = seg.get("end", 0),
                    ))
            elif full_text.strip():
                db.add(SttSegment(
                    session_id    = session_id,
                    speaker_label = "SPEAKER_0",
                    content       = full_text.strip(),
                    start_sec     = 0,
                    end_sec       = 0,
                ))
            db.commit()
        except Exception as dbe:
            logger.warning(f"[STT] DB 저장 실패: {dbe}")
            db.rollback()

    return {"text": full_text, "segments": segments}
