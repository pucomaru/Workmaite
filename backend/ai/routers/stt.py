import os
import tempfile
import whisper
from fastapi import APIRouter, UploadFile, File

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
    with tempfile.NamedTemporaryFile(suffix=".webm", delete=False) as tmp:
        tmp.write(data)
        tmp_path = tmp.name
    try:
        result = _get_model().transcribe(tmp_path, language=lang)
        return {"text": result["text"].strip()}
    finally:
        os.unlink(tmp_path)
