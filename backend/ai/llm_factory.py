"""LLM 클라이언트 팩토리 (P3A-7, H-11).

ChatOpenAI 생성이 에이전트마다 중복(4곳의 _make_llm + 직접 생성 12곳)되어 있던 것을
단일 팩토리로 통합한다. 모든 클라이언트에 timeout/retry가 일관 적용되고,
작업 프로파일별 모델을 env로 분리할 수 있다 (예: OPENAI_MODEL_ROUTING=gpt-4o-mini).
"""
import os

from langchain_openai import ChatOpenAI

# 작업 프로파일 → 기본값. 모델은 OPENAI_MODEL_{PROFILE} env가 있으면 그것을, 없으면 OPENAI_MODEL.
_PROFILES: dict[str, dict] = {
    "chat":      {"temperature": 0.2, "streaming": True},   # 대화/스트리밍
    "routing":   {"temperature": 0.0, "streaming": False},  # intent 분류 등 결정적 작업
    "extract":   {"temperature": 0.0, "streaming": False},  # 구조화 추출
    "minutes":   {"temperature": 0.3, "streaming": True},   # 회의록 생성
    "review":    {"temperature": 0.1, "streaming": True},   # 보고서 검토
    "knowledge": {"temperature": 0.2, "streaming": True},   # 지식 관리
}


def llm_factory(
    profile: str = "chat",
    *,
    temperature: float | None = None,
    streaming: bool | None = None,
    max_tokens: int | None = None,
) -> ChatOpenAI:
    cfg = _PROFILES.get(profile, _PROFILES["chat"])
    model = os.environ.get(f"OPENAI_MODEL_{profile.upper()}") or os.environ["OPENAI_MODEL"]
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
