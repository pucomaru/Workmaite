"""LLM 클라이언트 팩토리 (P3A-7, H-11) + structured output 헬퍼 (P3A-2, H-2).

ChatOpenAI 생성이 에이전트마다 중복(4곳의 _make_llm + 직접 생성 12곳)되어 있던 것을
단일 팩토리로 통합한다. 모든 클라이언트에 timeout/retry가 일관 적용되고,
작업 프로파일별 모델을 env로 분리할 수 있다 (예: OPENAI_MODEL_ROUTING=gpt-4o-mini).
"""

import logging
import os
from contextvars import ContextVar

from langchain_openai import ChatOpenAI

logger = logging.getLogger(__name__)

# 요청 단위 모델 오버라이드 — 사용자가 컴포저에서 모델을 선택하면 엔드포인트가 설정한다.
# asyncio task별 컨텍스트라 동시 요청 간 간섭이 없다.
model_override_var: ContextVar[str | None] = ContextVar("model_override", default=None)

# 작업 프로파일 → 기본값. 모델은 OPENAI_MODEL_{PROFILE} env가 있으면 그것을, 없으면 OPENAI_MODEL.
_PROFILES: dict[str, dict] = {
    "chat": {"temperature": 0.2, "streaming": True},  # 대화/스트리밍
    "routing": {"temperature": 0.0, "streaming": False},  # intent 분류 등 결정적 작업
    "extract": {"temperature": 0.0, "streaming": False},  # 구조화 추출
    "minutes": {"temperature": 0.3, "streaming": True},  # 회의록 생성
    "review": {"temperature": 0.1, "streaming": True},  # 보고서 검토
    "knowledge": {"temperature": 0.2, "streaming": True},  # 지식 관리
}


def llm_factory(
    profile: str = "chat",
    *,
    temperature: float | None = None,
    streaming: bool | None = None,
    max_tokens: int | None = None,
) -> ChatOpenAI:
    cfg = _PROFILES.get(profile, _PROFILES["chat"])
    model = (
        model_override_var.get()
        or os.environ.get(f"OPENAI_MODEL_{profile.upper()}")
        or os.environ.get("OPENAI_MODEL", "gpt-4o")
    )
    use_streaming = cfg["streaming"] if streaming is None else streaming
    kwargs: dict = {
        "model": model,
        "temperature": cfg["temperature"] if temperature is None else temperature,
        "api_key": os.environ["OPENAI_API_KEY"],
        "streaming": use_streaming,
        "stream_usage": use_streaming,  # streaming 시 usage 포함 (토큰 추적)
        "timeout": float(os.environ.get("OPENAI_TIMEOUT_SEC", "60")),
        "max_retries": int(os.environ.get("OPENAI_MAX_RETRIES", "2")),
    }
    if max_tokens:
        kwargs["max_tokens"] = max_tokens
    return ChatOpenAI(**kwargs)


class StructuredOutputError(Exception):
    """structured output이 재시도 후에도 실패 — 호출자는 명시적 실패로 처리해야 한다(H-2).

    가짜 기본값(score=50 등)으로 대체하지 말 것: 사용자가 fabricated 결과를
    실제 검토 결과로 신뢰하게 된다.
    """


async def ainvoke_structured(llm: ChatOpenAI, schema, messages, retries: int = 1):
    """pydantic 스키마로 구조화 출력을 요청하고, 실패 시 1회 재시도 후 예외 (P3A-2).

    regex JSON 파싱을 대체한다. function_calling 방식 — 자유 형식 prose 없이
    스키마 인스턴스를 반환한다.
    """
    runnable = llm.with_structured_output(schema, method="function_calling")
    last_error: Exception | None = None
    for attempt in range(retries + 1):
        try:
            result = await runnable.ainvoke(messages)
            if result is not None:
                return result
            last_error = ValueError("structured output이 None을 반환")
        except Exception as e:
            last_error = e
            logger.warning(
                f"[StructuredOutput] {schema.__name__} 시도 {attempt + 1}/{retries + 1} 실패: {e}"
            )
    raise StructuredOutputError(
        f"{schema.__name__} 구조화 출력 실패 (재시도 {retries}회 포함): {last_error}"
    )
