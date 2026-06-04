import os
import tempfile
import whisper
from fastapi import APIRouter, UploadFile, File
from r2_storage import upload_bytes, get_content_type

router = APIRouter(prefix="/api/stt", tags=["stt"])

_model = None

def _get_model():
    global _model
    if _model is None:
        model_name = os.getenv("WHISPER_MODEL", "tiny")
        _model = whisper.load_model(model_name)
    return _model


@router.post("/transcribe")
async def transcribe(audio: UploadFile = File(...), lang: str = "ko"):
    data = await audio.read()
    filename = audio.filename or "audio.webm"
    suffix = os.path.splitext(filename)[1] or ".webm"

    # R2에 원본 음성 파일 저장
    r2_key = f"audio/{filename}"
    try:
        audio_url = upload_bytes(data, r2_key, get_content_type(filename))
    except Exception:
        audio_url = None

    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(data)
        tmp_path = tmp.name
    try:
        result = _get_model().transcribe(tmp_path, language=lang)
        return {"text": result["text"].strip(), "audio_url": audio_url}
    finally:
        os.unlink(tmp_path)
