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
import re
from typing import Any

import websockets  # uvicorn[standard] 의존성
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from jose import JWTError, jwt

from core.auth import SECRET_KEY, ALGORITHMS
from core.access_guard import require_meeting_member_by_session
from db.database import SessionLocal
from db import models
from db.models import SttSegment
from llm.pricing import STT_PRICING

logger = logging.getLogger(__name__)
router = APIRouter()

_OPENAI_REALTIME_URL = "wss://api.openai.com/v1/realtime?intent=transcription"
_SAMPLE_RATE = 24000  # 브라우저가 24kHz PCM16 mono로 송신 (OpenAI Realtime 기본 포맷)
_DEFAULT_REALTIME_MODEL = os.environ.get("STT_MODEL", "gpt-realtime-whisper")
_KNOWN_STT = tuple(STT_PRICING.keys())


def _resolve_model(requested) -> str:
    if requested:
        req = str(requested).strip()
        if any(req == k or req.startswith(k) for k in _KNOWN_STT):
            return req
    return _DEFAULT_REALTIME_MODEL


# ── 문장 단위 재조립 ─────────────────────────────────────────────────────────
# gpt-realtime-whisper는 turn_detection 미지원이라 짧은 조각으로 끊겨 온다. 누적 텍스트를
# 문장 단위로 끊어 저장/표시한다. 1차로 kiwipiepy(Kiwi)의 형태소 기반 분절을 쓰고(구두점이
# 없는 한국어 구어체도 분절 가능), 미설치/실패 시 구두점 정규식으로 폴백한다.
_SENT_RE = re.compile(r"[^.!?。．…！？]*[.!?。．…！？]+['\"”’)\]]*\s*")
_ENDS_SENT = re.compile(r"[.!?。．…！？]['\"”’)\]]*$")
_HAS_WORD = re.compile(
    r"[0-9A-Za-z가-힣]"
)  # 실제 단어 포함 여부 — 구두점만인 조각 제외용
_MAX_BUF_CHARS = 160  # 종결부호 없이 길어지면 강제로 한 줄 확정(버퍼 무한증가 방지)

try:
    from kiwipiepy import Kiwi as _Kiwi

    _KIWI = _Kiwi()
    logger.info("[Realtime STT] kiwipiepy 문장 분절 사용")
except Exception as _e:  # 미설치/로드 실패 → 정규식 폴백
    _KIWI = None
    logger.warning(f"[Realtime STT] kiwipiepy 미사용, 구두점 정규식 폴백: {_e}")


def _split_by_regex(text: str, force: bool = False):
    raw = _SENT_RE.findall(text)
    if not raw:
        return (
            ([text], "") if force else ([], text)
        )  # 종결부호 없음 → force면 통째 확정
    tail = text[sum(len(s) for s in raw) :].strip()
    sents = [s.strip() for s in raw if s.strip()]
    if force and tail:
        sents.append(tail)
        tail = ""
    return sents, tail


def _split_sentences(text: str, allow_ef: bool = False, force: bool = False):
    """누적 텍스트를 (완결 문장 리스트, 미완결 꼬리)로 분리한다.

    - delta(스트리밍): 마지막 문장은 종결부호(.?!)로 끝날 때만 확정한다. 종결어미로 끝나도
      바로 뒤에 마침표가 따라올 수 있어("…입니다" 다음 ".") 한 텀 기다린다 → 마침표가 별도
      줄로 쪼개지는 것을 막는다.
    - completed(발화 commit=pause, allow_ef=True): 구두점이 없어도 마지막이 종결어미(EF)면
      확정한다(즉시성 유지). pause 시점이라 문장 중간이면 EF가 아니므로 오분절되지 않는다.
    - stop(force=True): 버퍼 전체를 한 번에 확정한다.
    """
    text = (text or "").strip()
    if not text:
        return [], ""
    if _KIWI is None:
        return _split_by_regex(text, force)
    try:
        sents = [
            s
            for s in _KIWI.split_into_sents(text, return_tokens=allow_ef)
            if s.text.strip()
        ]
    except Exception:
        return _split_by_regex(text, force)
    if not sents:
        return [], ""
    texts = [s.text.strip() for s in sents]
    if force:
        return texts, ""
    last_done = bool(_ENDS_SENT.search(texts[-1]))
    if not last_done and allow_ef and sents[-1].tokens:
        last_done = sents[-1].tokens[-1].tag == "EF"
    if last_done:
        return texts, ""
    return texts[:-1], texts[-1]  # 마지막은 아직 말하는 중 → 꼬리


def _user_id_from_token(token: str):
    if not token:
        return None
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=ALGORITHMS)
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
    # GA Realtime는 beta 헤더 불필요 — beta 헤더를 보내면 서버가 구 프로토콜로 처리해
    # 아래 GA형 session.update(session.type=transcription, audio.input...)를 거부할 수 있다.
    headers = {"Authorization": f"Bearer {api_key}"}

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

    state: dict[str, Any] = {
        "bytes_since_final": 0,
        "offset": 0.0,
        "buf": "",  # delta로 누적되는 미확정 전사 텍스트(문장 확정 시 비워짐)
        "buf_bytes": 0,  # buf에 대응하는 오디오 바이트(문장별 시간 배분용)
    }

    try:
        async with websockets.connect(
            _OPENAI_REALTIME_URL, additional_headers=headers, max_size=None
        ) as oai:
            # GA Realtime 전사 세션 설정 — session.update + session.type=transcription +
            # 중첩 audio.input(format/transcription).
            _input_cfg = {
                "format": {"type": "audio/pcm", "rate": _SAMPLE_RATE},
                "transcription": {"model": model, "language": lang},
            }
            # turn_detection(server_vad)은 지원 모델에만 추가 — 침묵(silence_duration) 기준으로
            # 발화를 끊어 문장 단위에 가깝게 분절한다. gpt-realtime-whisper는 turn_detection을
            # 지원하지 않으므로(넣으면 session.update 전체가 invalid_request_error로 거부됨) 생략하고
            # 모델 내장 분절(speech_started/committed 자동 발생)을 사용한다.
            if model.startswith(("gpt-4o-transcribe", "gpt-4o-mini-transcribe")):
                _input_cfg["turn_detection"] = {
                    "type": "server_vad",
                    "threshold": 0.5,
                    "prefix_padding_ms": 300,
                    "silence_duration_ms": 700,
                }
            await oai.send(
                json.dumps(
                    {
                        "type": "session.update",
                        "session": {
                            "type": "transcription",
                            "audio": {"input": _input_cfg},
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

            async def _emit_complete(sentences, tail):
                """완결 문장들을 각각 stt_segment로 저장하고 final로 전송한다. buf_bytes를
                글자수 비율로 배분해 문장별 시간(start/end)을 추정한다(총합=실제 오디오 길이)."""
                sentences = [
                    s for s in sentences if _HAS_WORD.search(s)
                ]  # 구두점만인 조각 제외
                if not sentences:
                    state["buf"] = tail
                    return
                total = sum(len(s) for s in sentences) + len(tail)
                fchars = sum(len(s) for s in sentences)
                fbytes = (
                    state["buf_bytes"]
                    if total == 0
                    else int(state["buf_bytes"] * fchars / total)
                )
                state["buf_bytes"] = max(0, state["buf_bytes"] - fbytes)
                state["buf"] = tail
                dur_total = fbytes / (2 * _SAMPLE_RATE)
                for s in sentences:
                    sdur = dur_total * (len(s) / fchars) if fchars else 0.0
                    start = round(state["offset"], 2)
                    end = round(start + sdur, 2)
                    state["offset"] = end
                    sid = None
                    if session_id:
                        sid = await asyncio.to_thread(
                            _save_segment, session_id, user_id, s, model, start, end
                        )
                    logger.info(f"[Realtime STT] 문장 확정: {s!r}")
                    await websocket.send_json(
                        {"type": "final", "text": s, "text_id": sid}
                    )

            async def client_to_oai():
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
                            # 남은 버퍼를 강제 커밋 → OpenAI가 마지막 .completed를 내보낸다.
                            # server_vad가 발화 끝을 못 잡아 부분 전사(partial)가 최종(final)으로
                            # 넘어가지 않고 'pending'에 머무는 문제를 방지한다. oai는 바깥에서
                            # 닫아 마지막 전사를 받을 시간을 확보한다.
                            state["stopping"] = True
                            try:
                                await oai.send(
                                    json.dumps({"type": "input_audio_buffer.commit"})
                                )
                            except Exception:
                                pass
                            break

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
                            # delta마다 버퍼에 누적하고 문장 단위 확정을 시도한다. 마지막 문장은
                            # 종결부호가 붙어야 확정 → 뒤따라오는 마침표가 별도 줄로 쪼개지지 않게.
                            state["buf_bytes"] += state["bytes_since_final"]
                            state["bytes_since_final"] = 0
                            state["buf"] += delta
                            complete, tail = await asyncio.to_thread(
                                _split_sentences, state["buf"]
                            )
                            if not complete and len(tail) > _MAX_BUF_CHARS:
                                complete, tail = [tail], ""
                            if complete:
                                await _emit_complete(complete, tail)
                            # 직전 문장 뒤에 떨어진 구두점만 남으면 비운다(별도 줄 생성 방지)
                            if state["buf"] and not _HAS_WORD.search(state["buf"]):
                                state["buf"] = ""
                            await websocket.send_json(
                                {"type": "partial", "text": state["buf"]}
                            )
                    elif t == "conversation.item.input_audio_transcription.completed":
                        # 발화 종료(pause) 시점 — 구두점이 없어도 종결어미(EF)로 확정 허용
                        # (allow_ef=True). pause라 문장 중간이면 EF가 아니라 오분절되지 않는다.
                        state["buf_bytes"] += state["bytes_since_final"]
                        state["bytes_since_final"] = 0
                        complete, tail = await asyncio.to_thread(
                            _split_sentences, state["buf"], True
                        )
                        if not complete and len(tail) > _MAX_BUF_CHARS:
                            complete, tail = [tail], ""
                        if complete:
                            await _emit_complete(complete, tail)
                        if state["buf"] and not _HAS_WORD.search(state["buf"]):
                            state["buf"] = ""
                        await websocket.send_json(
                            {"type": "partial", "text": state["buf"]}
                        )
                    elif t == "error":
                        err = ev.get("error") or {}
                        logger.warning(f"[Realtime STT] OpenAI 오류 이벤트: {err}")
                        await websocket.send_json(
                            {
                                "type": "error",
                                "message": err.get("message", "전사 오류"),
                            }
                        )
                    elif t in (
                        "session.created",
                        "session.updated",
                        "transcription_session.created",
                        "transcription_session.updated",
                    ):
                        logger.info(f"[Realtime STT] {t} (model={model})")
                    else:
                        # delta 외 모든 이벤트(speech_started/stopped, committed 등) 가시화 —
                        # pending 원인 진단용.
                        logger.info(f"[Realtime STT] event: {t}")

            t1 = asyncio.create_task(client_to_oai())
            t2 = asyncio.create_task(oai_to_client())
            done, _ = await asyncio.wait({t1, t2}, return_when=asyncio.FIRST_COMPLETED)
            # 정상 종료(stop)면 마지막 전사(.completed)를 받을 시간을 잠깐 준다.
            if state.get("stopping") and t2 not in done:
                try:
                    await asyncio.wait({t2}, timeout=3.0)
                except Exception:
                    pass
            for p in (t1, t2):
                if not p.done():
                    p.cancel()
            # 취소/종료된 태스크의 예외를 회수 — 브라우저가 먼저 끊기면 oai_to_client의 send가
            # WebSocketDisconnect를 던지는데, 회수하지 않으면 "Task exception was never
            # retrieved" 트레이스백이 콘솔에 찍힌다(정상 종료라 무시해도 됨).
            for p in (t1, t2):
                try:
                    await p
                except BaseException:
                    pass
            # 종료 시 버퍼에 남은 미완결 텍스트도 한 문장으로 확정 저장한다.
            if state["buf"].strip():
                try:
                    await _emit_complete([state["buf"].strip()], "")
                except Exception:
                    pass
            try:
                await oai.close()
            except Exception:
                pass
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
