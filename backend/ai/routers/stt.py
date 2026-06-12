import io
import os
import asyncio
import logging
from typing import Optional

import httpx
from datetime import datetime

from fastapi import APIRouter, UploadFile, File, Form, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from auth import get_current_user
from access_guard import require_meeting_member_by_session
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

    cfg_kwargs = dict(
        encoding=speech.RecognitionConfig.AudioEncoding.WEBM_OPUS,
        sample_rate_hertz=48000,
        audio_channel_count=1,
        model="latest_short",
        use_enhanced=True,
        language_code=bcp47,
        enable_automatic_punctuation=True,
        enable_word_time_offsets=True,
    )
    if max_speakers > 1:
        cfg_kwargs["diarization_config"] = speech.SpeakerDiarizationConfig(
            enable_speaker_diarization=True,
            min_speaker_count=1,
            max_speaker_count=max_speakers,
        )

    config = speech.RecognitionConfig(**cfg_kwargs)

    loop = asyncio.get_event_loop()
    response = await loop.run_in_executor(
        None, lambda: client.recognize(config=config, audio=audio)
    )

    segments: list[dict] = []
    if not response.results:
        return segments

    # Google STT v1 diarization: 마지막 result에만 전체 발화의 speaker_tag가 채워짐
    # 앞의 result들은 동일 내용을 speaker_tag=0으로 중복 반환하므로 무시
    alt = response.results[-1].alternatives[0] if response.results[-1].alternatives else None
    if not alt:
        return segments
    words = list(alt.words)

    if not words:
        text = alt.transcript.strip()
        if text:
            segments.append({"speaker": "1", "text": text, "start": 0.0, "end": 0.0})
        return segments

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


class SaveSegmentsRequest(BaseModel):
    session_id: int
    segments: list[dict]  # [{speaker, text, start, end}]


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
        raw_spk = str(seg.get("speaker") or "1")
        speaker_label = raw_spk if raw_spk.startswith("화자_") else f"화자_{raw_spk}"
        obj = SttSegment(
            session_id    = body.session_id,
            speaker_label = speaker_label,
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
            seg["speaker"] = obj.speaker_label
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
    if session_id:
        require_meeting_member_by_session(db, current_user, session_id)
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
            attendee_count = db.query(models.SessionMember).filter(
                models.SessionMember.session_id == session_id
            ).count()
            max_speakers = attendee_count if attendee_count > 0 else 1

    effective_mode = effective_mode or "localwhisper"

    segments: list[dict] = []
    full_text = ""

    async def _run(mode: str) -> tuple[list[dict], str]:
        if mode == "whisperapi":
            segs = await _transcribe_external(data, filename, lang_code)
            return segs, " ".join(s["text"] for s in segs)
        if mode == "gcapi":
            segs = await _transcribe_cloud(data, lang_code, max_speakers)
            return segs, " ".join(s["text"] for s in segs)
        text, _ = await _transcribe_local(data, filename, lang_code)
        return [], text

    # provider 폴백 체인 (P4-3): 선택 provider 실패 → localwhisper로 폴백
    chain = [effective_mode] + (["localwhisper"] if effective_mode != "localwhisper" else [])
    used_mode = effective_mode
    last_err: Exception | None = None
    for mode in chain:
        try:
            segments, full_text = await _run(mode)
            used_mode = mode
            last_err = None
            logger.info(f"[STT] {mode} 완료: {len(segments)}seg/{len(full_text)}자")
            break
        except Exception as e:
            last_err = e
            logger.error(f"[STT] {mode} 실패: {e}")
    if last_err is not None:
        raise HTTPException(status_code=502, detail=f"음성 인식에 실패했습니다. 다시 시도해주세요. ({last_err})")
    effective_mode = used_mode

    # 화자 레이블 정규화: "1" → "화자_1" (DB 저장 형식과 일치)
    for seg in segments:
        raw = str(seg.get("speaker") or "0")
        seg["speaker"] = raw if raw.startswith("화자_") else f"화자_{raw}"

    # DB 저장 + ID 반환
    saved_objs: list[SttSegment] = []
    saved_seg_indices: list[int] = []
    text_id: int | None = None

    if session_id and (segments or full_text.strip()):
        try:
            if segments:
                for i, seg in enumerate(segments):
                    if not seg.get("text", "").strip():
                        continue
                    obj = SttSegment(
                        session_id    = session_id,
                        speaker_label = seg["speaker"],
                        content       = seg["text"],
                        start_sec     = seg.get("start", 0),
                        end_sec       = seg.get("end", 0),
                        provider      = effective_mode,
                    )
                    db.add(obj)
                    saved_objs.append(obj)
                    saved_seg_indices.append(i)
            elif full_text.strip():
                obj = SttSegment(
                    session_id    = session_id,
                    speaker_label = "화자_0",
                    content       = full_text.strip(),
                    start_sec     = 0,
                    end_sec       = 0,
                    provider      = effective_mode,
                )
                db.add(obj)
                saved_objs.append(obj)
            db.commit()
            # DB ID를 세그먼트에 역주입
            if segments:
                for obj, seg_idx in zip(saved_objs, saved_seg_indices):
                    segments[seg_idx]["id"] = obj.id
            elif saved_objs:
                text_id = saved_objs[0].id
        except Exception as dbe:
            logger.warning(f"[STT] DB 저장 실패: {dbe}")
            db.rollback()

    # 원본 오디오 보존 (P4-2): 세션별로 R2에 누적 저장 — 재처리·분쟁 대비
    if session_id:
        try:
            from r2_storage import upload_bytes
            ts = datetime.utcnow().strftime("%H%M%S_%f")
            upload_bytes(data, f"sessions/{session_id}/audio/{ts}_{filename}", "audio/webm")
        except Exception as ae:
            logger.warning(f"[STT] 원음 R2 보존 실패(무시): {ae}")

    return {"text": full_text, "segments": segments, "text_id": text_id, "provider": effective_mode}
