"""실시간 전사 (P5) — 브라우저 PCM16 → FastAPI WS → OpenAI Realtime transcription 프록시.

브라우저가 24kHz mono PCM16 오디오를 바이너리 프레임으로 보내면, OpenAI Realtime API의
transcription 세션으로 중계하고 부분(delta)/최종(completed) 전사를 다시 스트리밍한다.
최종 전사는 stt_segments에 저장하고(speaker_user_id=녹음자, provider=모델), 누적 오디오
길이로 비용을 산정한다(usage.py가 SttSegment 길이×pricing.yaml로 조회시 계산).

녹음은 1인 전제 — 화자분리 없이 단일 화자("화자01")로 저장한다.

WS 프로토콜 (브라우저 ↔ 본 서버):
  브라우저→서버: 첫 텍스트 {"type":"start","lang":"ko","model":"gpt-4o-transcribe"} (선택),
                이후 바이너리 PCM16 프레임, 종료 시 {"type":"stop"}.
  서버→브라우저: {"type":"ready","model":...} | {"type":"partial","text":...}
                | {"type":"final","text":...,"text_id":...} | {"type":"error","message":...}
"""

import asyncio
import base64
import json
import logging
import os

import websockets  # uvicorn[standard] 의존성
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from jose import JWTError, jwt

from core.auth import SECRET_KEY, ALGORITHM
from core.access_guard import require_meeting_member_by_session
from db.database import SessionLocal
from db import models
from db.models import SttSegment
from llm.pricing import STT_PRICING

logger = logging.getLogger(__name__)
router = APIRouter()

_OPENAI_REALTIME_URL = "wss://api.openai.com/v1/realtime?intent=transcription"
_SAMPLE_RATE = 24000  # 브라우저가 24kHz PCM16 mono로 송신 (OpenAI Realtime 기본 포맷)
_DEFAULT_REALTIME_MODEL = os.environ.get("STT_REALTIME_MODEL", "gpt-4o-transcribe")
_KNOWN_STT = tuple(STT_PRICING.keys())


def _resolve_model(requested) -> str:
    if requested:
        req = str(requested).strip()
        if any(req == k or req.startswith(k) for k in _KNOWN_STT):
            return req
    return _DEFAULT_REALTIME_MODEL


def _user_id_from_token(token: str):
    if not token:
        return None
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("type") == "refresh":  # refresh 토큰으로 WS 인증 불가 (SEC-7)
            return None
        sub = payload.get("sub")
        return int(sub) if sub is not None else None
    except (JWTError, ValueError):
        return None


def _authorize(user_id: int, session_id: int) -> bool:
    """세션이 속한 회의체 멤버인지 검증 (블로킹 DB — to_thread로 호출)."""
    db = SessionLocal()
    try:
        user = (
            db.query(models.User)
            .filter(models.User.id == user_id, models.User.is_active.is_(True))
            .first()
        )
        if not user:
            return False
        require_meeting_member_by_session(db, user, session_id)
        return True
    except Exception:
        return False
    finally:
        db.close()


def _save_segment(session_id, user_id, text, model, start_sec, end_sec):
    db = SessionLocal()
    try:
        obj = SttSegment(
            session_id=session_id,
            speaker_label="화자01",
            speaker_user_id=user_id,  # 녹음 버튼을 누른 사람
            content=text,
            start_sec=start_sec,
            end_sec=end_sec,
            provider=model,  # 실제 STT 모델명 — usage 모델별 단가
        )
        db.add(obj)
        db.commit()
        return obj.id
    except Exception as e:
        db.rollback()
        logger.warning(f"[Realtime STT] 세그먼트 저장 실패: {e}")
        return None
    finally:
        db.close()


@router.websocket("/ws/sessions/{session_id}/transcribe")
async def ws_transcribe(websocket: WebSocket, session_id: int):
    # 인증 — 쿼리 파라미터 token의 JWT (기존 WS 엔드포인트와 동일 방식)
    user_id = _user_id_from_token(websocket.query_params.get("token", ""))
    if user_id is None:
        await websocket.close(code=4401)
        return
    if not await asyncio.to_thread(_authorize, user_id, session_id):
        await websocket.close(code=4403)
        return

    await websocket.accept()

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        await websocket.send_json({"type": "error", "message": "STT 미설정"})
        await websocket.close()
        return
    headers = {"Authorization": f"Bearer {api_key}", "OpenAI-Beta": "realtime=v1"}

    # 첫 메시지 — 설정(JSON) 또는 곧바로 오디오(bytes)
    model = _DEFAULT_REALTIME_MODEL
    lang = "ko"
    pending_audio = None
    try:
        first = await asyncio.wait_for(websocket.receive(), timeout=15)
    except (asyncio.TimeoutError, WebSocketDisconnect):
        await websocket.close()
        return
    if first.get("type") == "websocket.disconnect":
        return
    if first.get("text"):
        try:
            cfg = json.loads(first["text"])
            model = _resolve_model(cfg.get("model"))
            lang = (cfg.get("lang") or "ko").split("-")[0].lower()
        except Exception:
            pass
    elif first.get("bytes"):
        pending_audio = first["bytes"]

    state = {"bytes_since_final": 0, "offset": 0.0}

    try:
        async with websockets.connect(
            _OPENAI_REALTIME_URL, additional_headers=headers, max_size=None
        ) as oai:
            await oai.send(
                json.dumps(
                    {
                        "type": "transcription_session.update",
                        "session": {
                            "input_audio_format": "pcm16",
                            "input_audio_transcription": {
                                "model": model,
                                "language": lang,
                            },
                            "turn_detection": {
                                "type": "server_vad",
                                "threshold": 0.5,
                                "prefix_padding_ms": 300,
                                "silence_duration_ms": 500,
                            },
                        },
                    }
                )
            )
            await websocket.send_json({"type": "ready", "model": model})

            async def _append(buf: bytes):
                state["bytes_since_final"] += len(buf)
                await oai.send(
                    json.dumps(
                        {
                            "type": "input_audio_buffer.append",
                            "audio": base64.b64encode(buf).decode("ascii"),
                        }
                    )
                )

            if pending_audio:
                await _append(pending_audio)

            async def client_to_oai():
                try:
                    while True:
                        try:
                            msg = await websocket.receive()
                        except WebSocketDisconnect:
                            break
                        if msg.get("type") == "websocket.disconnect":
                            break
                        if msg.get("bytes"):
                            await _append(msg["bytes"])
                        elif msg.get("text"):
                            try:
                                ev = json.loads(msg["text"])
                            except Exception:
                                continue
                            if ev.get("type") == "stop":
                                break
                finally:
                    try:
                        await oai.close()
                    except Exception:
                        pass

            async def oai_to_client():
                async for raw in oai:
                    try:
                        ev = json.loads(raw)
                    except Exception:
                        continue
                    t = ev.get("type", "")
                    if t == "conversation.item.input_audio_transcription.delta":
                        delta = ev.get("delta") or ""
                        if delta:
                            await websocket.send_json(
                                {"type": "partial", "text": delta}
                            )
                    elif t == "conversation.item.input_audio_transcription.completed":
                        text = (ev.get("transcript") or "").strip()
                        dur = state["bytes_since_final"] / (2 * _SAMPLE_RATE)
                        state["bytes_since_final"] = 0
                        start = round(state["offset"], 2)
                        end = round(start + dur, 2)
                        state["offset"] = end
                        text_id = None
                        if text and session_id:
                            text_id = await asyncio.to_thread(
                                _save_segment,
                                session_id,
                                user_id,
                                text,
                                model,
                                start,
                                end,
                            )
                        await websocket.send_json(
                            {"type": "final", "text": text, "text_id": text_id}
                        )
                    elif t == "error":
                        await websocket.send_json(
                            {
                                "type": "error",
                                "message": (ev.get("error") or {}).get(
                                    "message", "전사 오류"
                                ),
                            }
                        )

            t1 = asyncio.create_task(client_to_oai())
            t2 = asyncio.create_task(oai_to_client())
            _, pending = await asyncio.wait(
                {t1, t2}, return_when=asyncio.FIRST_COMPLETED
            )
            for p in pending:
                p.cancel()
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.warning(f"[Realtime STT] 프록시 오류: {e}")
        try:
            await websocket.send_json(
                {"type": "error", "message": "실시간 전사 연결 오류"}
            )
        except Exception:
            pass
    finally:
        try:
            await websocket.close()
        except Exception:
            pass
