import io
import os
import re
import unicodedata
import logging
from typing import Optional

from fastapi import APIRouter, UploadFile, File, Form, Depends, HTTPException
from sqlalchemy.orm import Session

from core.auth import get_current_user
from core.access_guard import require_meeting_member_by_session
from core.stt_prompt import build_vocab_prompt
from db.database import get_db
from db import models
from db.models import SttSegment
from llm.pricing import STT_PRICING

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/stt", tags=["stt"])


def _clean_transcript(text: str) -> str:
    """STT 출력에서 깨진 문자·인코딩 오류를 제거합니다."""
    # Unicode 대체 문자(U+FFFD) 제거
    text = text.replace("�", "")
    # 제어 문자 제거 (탭·줄바꿈 제외)
    text = "".join(
        ch for ch in text if unicodedata.category(ch)[0] != "C" or ch in ("\n", "\t")
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


def _resolve_stt_model(requested: Optional[str]) -> str:
    """요청 모델이 pricing.yaml에 등록된(=단가 있는) 모델이면 사용, 아니면 기본값
    (임의 모델 주입 차단)."""
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
    resp = await client.audio.transcriptions.create(
        model=model,
        file=(filename, io.BytesIO(data), "audio/webm"),
        language=lang_code,
        prompt=prompt if prompt else openai.omit,
    )
    return (resp.text or "").strip()


@router.post("/transcribe", summary="음성 파일 전사")
async def transcribe(
    audio: UploadFile = File(...),
    lang: str = Form("ko"),
    session_id: Optional[int] = Form(None),
    duration_sec: float = Form(0.0),  # 클라이언트 측정 녹음 길이 — STT 비용 산정용 (P4)
    model: Optional[str] = Form(None),  # 선택 STT 모델 (없으면 STT_MODEL env)
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """업로드된 음성 파일을 STT로 전사하고 stt_segments에 저장합니다.

    도메인 어휘 프롬프트로 고유명사 인식률을 높이고 사용량을 녹음자에 귀속한다.
    session_id가 있으면 해당 회의체 구성원만 호출 가능. 인증 필요.
    """
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
