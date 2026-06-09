import os
import io
import logging
import tempfile

import torch
import whisperx
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
diarize_model = whisperx.DiarizationPipeline(use_auth_token=HF_TOKEN, device=DEVICE)

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

    try:
        result = model.transcribe(tmp_path, language=language)

        if not result.get("segments"):
            return {"text": "", "segments": []}

        # forced alignment
        align_model, metadata = whisperx.load_align_model(
            language_code=language, device=DEVICE
        )
        result = whisperx.align(
            result["segments"], align_model, metadata, tmp_path, DEVICE
        )

        # 화자 분리
        diarize_segments = diarize_model(tmp_path)
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
