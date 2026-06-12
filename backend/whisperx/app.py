import os
import logging
import subprocess
import tempfile

import numpy as np
import torch
import whisperx
from pyannote.audio import Pipeline as _Pipeline
from fastapi import FastAPI, UploadFile, File
from fastapi.responses import JSONResponse

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()

DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
COMPUTE_TYPE = "float16" if DEVICE == "cuda" else "int8"
MODEL_SIZE = os.environ.get("ASR_MODEL", "small")
HF_TOKEN = os.environ["HF_TOKEN"]

logger.info(f"[WhisperX] device={DEVICE}, model={MODEL_SIZE}")

model = whisperx.load_model(MODEL_SIZE, DEVICE, compute_type=COMPUTE_TYPE)
diarize_model = _Pipeline.from_pretrained(
    "pyannote/speaker-diarization-3.1",
    token=HF_TOKEN,
).to(torch.device(DEVICE))

# align model은 언어별로 1회만 로드해 캐시한다 (P4-4 — 매 요청 로드 제거)
_align_cache: dict = {}


def _get_align_model(language: str):
    if language not in _align_cache:
        _align_cache[language] = whisperx.load_align_model(language_code=language, device=DEVICE)
    return _align_cache[language]


# 한국어 align model 워밍업 (첫 요청 지연 제거)
try:
    _get_align_model("ko")
except Exception as _e:
    logger.warning(f"[WhisperX] ko align 워밍업 실패(요청 시 재시도): {_e}")

logger.info("[WhisperX] 모델 로드 완료")


@app.get("/")
def health():
    return {"status": "ok"}


@app.post("/asr")
async def asr(
    audio_file: UploadFile = File(...),
    language: str = "ko",
    output: str = "json",
):
    data = await audio_file.read()

    with tempfile.NamedTemporaryFile(suffix=".webm", delete=False) as f:
        f.write(data)
        tmp_path = f.name

    wav_path = tmp_path.replace(".webm", ".wav")
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-i", tmp_path, "-ar", "16000", "-ac", "1", wav_path],
            capture_output=True, check=True,
        )
        wav_size = os.path.getsize(wav_path) if os.path.exists(wav_path) else 0

        audio = whisperx.load_audio(wav_path)
        rms = float(np.sqrt(np.mean(audio.astype(np.float64) ** 2)))
        logger.info(f"[WhisperX] webm={os.path.getsize(tmp_path)}B wav={wav_size}B rms={rms:.4f}")

        result = model.transcribe(audio, language=language, batch_size=8)

        if not result.get("segments"):
            logger.warning(f"[WhisperX] 세그먼트 없음 (rms={rms:.4f})")
            return {"text": "", "segments": []}

        align_model, metadata = _get_align_model(language)  # 캐시 (P4-4)
        result = whisperx.align(
            result["segments"], align_model, metadata, wav_path, DEVICE
        )

        diarize_segments = diarize_model(wav_path)
        result = whisperx.assign_word_speakers(diarize_segments, result)

        segments = []
        for seg in result["segments"]:
            segments.append({
                "speaker": seg.get("speaker", "A").replace("SPEAKER_", ""),
                "text": seg.get("text", "").strip(),
                "start": round(seg.get("start", 0.0), 2),
                "end": round(seg.get("end", 0.0), 2),
            })

        full_text = " ".join(s["text"] for s in segments)
        logger.info(f"[WhisperX] 완료: {len(segments)}개 세그먼트")
        return {"text": full_text, "segments": segments}

    except Exception as e:
        logger.error(f"[WhisperX] 오류: {e}")
        return JSONResponse(status_code=500, content={"error": str(e)})
    finally:
        os.unlink(tmp_path)
        if os.path.exists(wav_path):
            os.unlink(wav_path)
