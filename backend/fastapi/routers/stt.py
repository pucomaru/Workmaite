import io
import os
import re
import unicodedata
import uuid
import logging
from datetime import datetime, timedelta
from typing import Optional

import httpx
from fastapi import APIRouter, UploadFile, File, Form, Depends, HTTPException
from sqlalchemy.orm import Session

from core.auth import get_current_user
from core.access_guard import require_meeting_member_by_session
from core.stt_prompt import build_vocab_prompt
from db.database import get_db
from db import models
from db.models import SttSegment
from llm.pricing import STT_PRICING, estimate_cost

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/stt", tags=["stt"])


def _clean_transcript(text: str) -> str:
    """STT 출력에서 깨진 문자·인코딩 오류를 제거합니다."""
    # Unicode 대체 문자(U+FFFD) 제거
    text = text.replace("�", "")
    # 제어 문자 제거 (탭·줄바꿈 제외)
    text = "".join(
        ch for ch in text
        if unicodedata.category(ch)[0] != "C" or ch in ("\n", "\t")
    )
    # 단독 한글 자모(ㄱ~ㅣ, U+3131~U+314E/U+314F~U+3163) 연속 2개 이상 → 제거
    # (정상 한글은 완성형 U+AC00~U+D7A3, 자모 단독은 인코딩 깨짐 신호)
    text = re.sub(r"[ㄱ-ㆎ]{2,}", "", text)
    # 공백 정리
    text = re.sub(r" {2,}", " ", text).strip()
    return text

# 배치 전사 기본 모델. gpt-realtime-whisper는 실시간 전용(P5)이라 배치에선 제외.
_DEFAULT_STT_MODEL = os.environ.get("STT_MODEL", "gpt-realtime-whisper")
_KNOWN_STT = tuple(STT_PRICING.keys())

# 화자분리 전사 모델 — STT 종료 시 전체 오디오 1회 배치 전사로 화자(A/B/…)를 구분한다.
_DIARIZE_MODEL = os.environ.get("DIARIZE_MODEL", "gpt-4o-transcribe-diarize")
_OPENAI_TRANSCRIBE_URL = "https://api.openai.com/v1/audio/transcriptions"


def _resolve_stt_model(requested: Optional[str]) -> str:
    """요청 모델이 pricing.yaml에 등록된(=단가 있는) 모델이면 사용, 아니면 기본값.
    gpt-4o-transcribe-diarize 등 변형은 prefix로 허용한다 (임의 모델 주입 차단)."""
    if requested:
        req = requested.strip()
        if any(req == k or req.startswith(k) for k in _KNOWN_STT):
            return req
    return _DEFAULT_STT_MODEL


async def _transcribe_openai(
    data: bytes, filename: str, lang_code: str, model: str, prompt: str = ""
) -> str:
    """OpenAI 음성 전사 (화자분리 없는 단순 전사 — 안정성·한국어 정확도 우선).
    녹음은 1인이므로 diarization 불필요: 단일 화자로 저장한다.
    prompt: 도메인 어휘 힌트(회의 제목·참석자·부서) — 고유명사 인식률 향상 (P-STT1)."""
    import openai

    client = openai.AsyncOpenAI(api_key=os.environ["OPENAI_API_KEY"])
    kwargs = {
        "model": model,
        "file": (filename, io.BytesIO(data), "audio/webm"),
        "language": lang_code,
    }
    if prompt:
        kwargs["prompt"] = prompt
    resp = await client.audio.transcriptions.create(**kwargs)
    return (resp.text or "").strip()


@router.post("/transcribe")
async def transcribe(
    audio: UploadFile = File(...),
    lang: str = Form("ko"),
    session_id: Optional[int] = Form(None),
    duration_sec: float = Form(0.0),  # 클라이언트 측정 녹음 길이 — STT 비용 산정용 (P4)
    model: Optional[str] = Form(None),  # 선택 STT 모델 (없으면 STT_MODEL env)
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    if session_id:
        require_meeting_member_by_session(db, current_user, session_id)
    lang_code = lang.split("-")[0].lower() if lang else "ko"
    stt_model = _resolve_stt_model(model)
    data = await audio.read()
    filename = audio.filename or "audio.webm"

    # 도메인 어휘 프롬프트(회의 제목·참석자·부서) — 고유명사 인식률 향상 (P-STT1)
    vocab_prompt = build_vocab_prompt(db, session_id) if session_id else ""

    # 단순 전사
    try:
        full_text = _clean_transcript(
            await _transcribe_openai(data, filename, lang_code, stt_model, vocab_prompt)
        )
    except Exception as e:
        logger.error(f"[STT] 전사 실패 (model={stt_model}): {e}")
        raise HTTPException(
            status_code=502, detail="음성 인식에 실패했습니다. 다시 시도해주세요."
        )

    # DB 저장 — speaker_label="화자01"(편집 가능, P6), speaker_user_id=녹음자(P4)
    text_id: int | None = None
    if session_id and full_text.strip():
        try:
            obj = SttSegment(
                session_id=session_id,
                speaker_label="화자01",
                speaker_user_id=current_user.id,  # 녹음 버튼을 누른 사람 (P4)
                content=full_text.strip(),
                start_sec=0,
                end_sec=max(0.0, float(duration_sec or 0)),  # 실제 길이 → 비용>0 (P4)
                provider=stt_model,  # 실제 STT 모델명 — usage 모델별 단가 (P0/P4)
            )
            db.add(obj)
            db.commit()
            text_id = obj.id
        except Exception as dbe:
            logger.warning(f"[STT] DB 저장 실패: {dbe}")
            db.rollback()

    return {
        "text": full_text,
        "segments": [],
        "text_id": text_id,
        "provider": stt_model,
        "model": stt_model,
    }


def _map_speaker(label: str, mapping: dict) -> str:
    """diarize 화자 라벨(A/B/…)을 등장 순서대로 화자01/02/…로 매핑."""
    key = (label or "").strip() or "?"
    if key not in mapping:
        mapping[key] = f"화자{len(mapping) + 1:02d}"
    return mapping[key]


@router.post("/diarize")
async def diarize(
    audio: UploadFile = File(...),
    lang: str = Form("ko"),
    session_id: int = Form(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """STT 종료 시 전체 녹음 오디오를 gpt-4o-transcribe-diarize로 1회 전사해 화자를 구분하고,
    해당 세션의 stt_segments를 화자 라벨이 붙은 세그먼트로 교체한다. 오디오는 저장하지 않는다.
    비용은 토큰 과금이라 token_usage_logs(LLM 섹션)로 기록한다."""
    require_meeting_member_by_session(db, current_user, session_id)
    data = await audio.read()
    if not data:
        raise HTTPException(status_code=400, detail="오디오가 비어 있습니다.")

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise HTTPException(status_code=503, detail="STT 미설정")
    lang_code = lang.split("-")[0].lower() if lang else "ko"

    # diarized_json + chunking_strategy=auto 로 화자/타임스탬프 포함 응답 요청 (prompt 미지원)
    form = {
        "model": _DIARIZE_MODEL,
        "response_format": "diarized_json",
        "chunking_strategy": "auto",
        "language": lang_code,
    }
    files = {"file": (audio.filename or "audio.webm", data, "audio/webm")}
    try:
        async with httpx.AsyncClient(timeout=300.0) as cx:
            r = await cx.post(
                _OPENAI_TRANSCRIBE_URL,
                headers={"Authorization": f"Bearer {api_key}"},
                data=form,
                files=files,
            )
        r.raise_for_status()
        payload = r.json()
    except Exception as e:
        logger.error(f"[Diarize] 전사 실패: {e}")
        raise HTTPException(status_code=502, detail="화자 분리 전사에 실패했습니다.")

    raw_segments = payload.get("segments") or []
    mapping: dict[str, str] = {}
    parsed = []
    for seg in raw_segments:
        text = (seg.get("text") or "").strip()
        if not text:
            continue
        parsed.append(
            {
                "speaker": _map_speaker(seg.get("speaker"), mapping),
                "start": float(seg.get("start") or 0.0),
                "end": float(seg.get("end") or 0.0),
                "text": text,
            }
        )
    if not parsed:
        raise HTTPException(status_code=502, detail="화자 분리 결과가 비어 있습니다.")

    # 표시 시각 base — 세션 실제 시작시각(없으면 현재-총길이)에 start_sec를 더해 created_at 부여
    sess = (
        db.query(models.MeetingSession)
        .filter(models.MeetingSession.id == session_id)
        .first()
    )
    total_dur = max((p["end"] for p in parsed), default=0.0)
    base = (
        sess.started_at
        if sess and sess.started_at
        else datetime.utcnow() - timedelta(seconds=total_dur)
    )

    # 기존(실시간) 세그먼트를 화자분리 결과로 교체
    try:
        db.query(SttSegment).filter(SttSegment.session_id == session_id).delete()
        for p in parsed:
            db.add(
                SttSegment(
                    session_id=session_id,
                    speaker_label=p["speaker"],
                    speaker_user_id=None,
                    content=p["text"],
                    start_sec=p["start"],
                    end_sec=p["end"],
                    provider=_DIARIZE_MODEL,
                    created_at=base + timedelta(seconds=p["start"]),
                )
            )
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"[Diarize] 세그먼트 교체 실패: {e}")
        raise HTTPException(status_code=500, detail="화자 분리 결과 저장에 실패했습니다.")

    # 비용 기록 — 토큰 과금(input/output) → AgentLog + TokenUsageLog (usage 모달 집계)
    usage = payload.get("usage") or {}
    in_tok = int(usage.get("input_tokens") or 0)
    out_tok = int(usage.get("output_tokens") or 0)
    if in_tok or out_tok:
        try:
            log = models.AgentLog(
                task_id=str(uuid.uuid4()),
                context_type="stt_diarize",
                session_id=session_id,
                user_id=current_user.id,
                status="success",
                ended_at=datetime.utcnow(),
            )
            db.add(log)
            db.flush()
            db.add(
                models.TokenUsageLog(
                    agent_log_id=log.id,
                    model_name=_DIARIZE_MODEL,
                    prompt_tokens=in_tok,
                    completion_tokens=out_tok,
                    estimated_cost_usd=estimate_cost(_DIARIZE_MODEL, in_tok, out_tok),
                )
            )
            db.commit()
        except Exception as e:
            db.rollback()
            logger.warning(f"[Diarize] 사용량 기록 실패: {e}")

    speakers = sorted(set(p["speaker"] for p in parsed))
    logger.info(
        f"[Diarize] session={session_id} 세그먼트 {len(parsed)}개, 화자 {speakers}"
    )
    return {"segments": len(parsed), "speakers": speakers}
