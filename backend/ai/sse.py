"""SSE v2 이벤트 포매터 (P3A-6, FE-2).

v1은 `data: [PLANNING] ...` 같은 문자열 프리픽스 프로토콜이라 LLM 출력에
'data:'나 '[DONE]'이 포함되면 오동작했다. v2는 SSE 표준 `event:` 필드로
타입을 분리하고 payload는 JSON으로 감싼다 (프론트 api.js는 v1/v2 모두 파싱).

이벤트 타입: run | planning | token | tool_call | result | highlight | usage | error | done
"""
import json


def sse_event(event: str, data) -> str:
    """타입 있는 SSE 이벤트 한 건을 직렬화한다. data는 dict 또는 str."""
    if isinstance(data, str):
        data = {"text": data}
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False, default=str)}\n\n"


def sse_token(text: str) -> str:
    return sse_event("token", {"text": text})


def sse_done() -> str:
    return sse_event("done", {})


def sse_error(message: str) -> str:
    return sse_event("error", {"message": str(message)[:500]})
