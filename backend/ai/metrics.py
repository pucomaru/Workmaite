"""챗봇 체감 품질 메트릭 (P5-1) — TTFT·스트림 총 시간 Prometheus 히스토그램.

/metrics는 prometheus_fastapi_instrumentator가 이미 노출 중 — 같은 레지스트리에 등록된다.
"""
import time
from typing import AsyncGenerator

from prometheus_client import Histogram

CHAT_TTFT = Histogram(
    "workmaite_chat_ttft_seconds",
    "첫 토큰까지 시간 (체감 응답성의 핵심 지표)",
    ["route"],
    buckets=(0.25, 0.5, 1, 2, 3, 5, 8, 13, 21, 34),
)
CHAT_STREAM_DURATION = Histogram(
    "workmaite_chat_stream_seconds",
    "스트림 총 시간",
    ["route"],
    buckets=(1, 2, 5, 10, 20, 40, 80, 160),
)


async def instrument_stream(gen: AsyncGenerator[str, None], route: str) -> AsyncGenerator[str, None]:
    """SSE generator를 감싸 첫 token 이벤트까지의 시간과 총 시간을 기록한다."""
    t0 = time.monotonic()
    first_token = False
    try:
        async for item in gen:
            if not first_token and isinstance(item, str) and item.startswith("event: token"):
                CHAT_TTFT.labels(route).observe(time.monotonic() - t0)
                first_token = True
            yield item
    finally:
        CHAT_STREAM_DURATION.labels(route).observe(time.monotonic() - t0)
