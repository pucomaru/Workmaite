"""LLM/임베딩/STT 단가표 로더 (P5-3, HC-7) — pricing.yaml에서 로드, 코드 하드코딩 제거.

PRICING_FILE env로 경로 오버라이드 가능. 파일이 없거나 깨져도 내장 기본값으로 동작한다.

노출 심볼:
  - PRICING, DEFAULT_PRICE, estimate_cost  : LLM 토큰 단가 (input/output per 1M)
  - EMBEDDING_PRICING, embedding_cost      : 임베딩 단가 (단일 입력 요율 per 1M)
  - STT_PRICING, stt_cost, stt_cost_per_min: STT 단가 (분당 USD, 토큰요율 병기)
estimate_cost는 임베딩 모델명을 자동 인식해 임베딩 요율로 가격책정한다
(token_usage_logs를 일원화 기록하므로 _finalize가 모델 구분 없이 호출 가능).
"""

import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

_FALLBACK_DEFAULT = (2.50, 10.00)
_FALLBACK_MODELS = {"gpt-4o-mini": (0.15, 0.60), "gpt-4o": (2.50, 10.00)}
_FALLBACK_EMB_DEFAULT = 0.13  # text-embedding-3-large
_FALLBACK_EMB_MODELS = {"text-embedding-3-small": 0.02, "text-embedding-3-large": 0.13}
_FALLBACK_STT_DEFAULT = {"per_min": 0.017}  # gpt-realtime-whisper
_FALLBACK_STT_MODELS = {
    "gpt-realtime-whisper": {"per_min": 0.017},
    "gpt-4o-transcribe": {"per_min": 0.006, "input": 2.50, "output": 10.00},
    "gpt-4o-mini-transcribe": {"per_min": 0.003, "input": 1.25, "output": 5.00},
    "whisper-1": {"per_min": 0.006},
}


def _load():
    path = Path(os.environ.get("PRICING_FILE", Path(__file__).parent / "pricing.yaml"))
    try:
        import yaml

        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        models = {k: tuple(v) for k, v in (data.get("models") or {}).items()}
        default = tuple(data.get("default") or _FALLBACK_DEFAULT)

        emb = data.get("embedding") or {}
        emb_models = {k: float(v) for k, v in (emb.get("models") or {}).items()}
        emb_default = float(emb.get("default", _FALLBACK_EMB_DEFAULT))

        stt = data.get("stt") or {}
        stt_models = {k: dict(v) for k, v in (stt.get("models") or {}).items()}
        stt_default = dict(stt.get("default") or _FALLBACK_STT_DEFAULT)
        return models, default, emb_models, emb_default, stt_models, stt_default
    except Exception as e:
        logger.warning(f"[Pricing] {path} 로드 실패, 내장 기본값 사용: {e}")
        return (
            dict(_FALLBACK_MODELS),
            _FALLBACK_DEFAULT,
            dict(_FALLBACK_EMB_MODELS),
            _FALLBACK_EMB_DEFAULT,
            dict(_FALLBACK_STT_MODELS),
            dict(_FALLBACK_STT_DEFAULT),
        )


(
    PRICING,
    DEFAULT_PRICE,
    EMBEDDING_PRICING,
    EMBEDDING_DEFAULT,
    STT_PRICING,
    STT_DEFAULT,
) = _load()


def _match_key(key: str, table) -> str | None:
    """최장 prefix 매칭 — "gpt-4o-mini-…"가 "gpt-4o" 단가로 잡히는 것 방지."""
    return max(
        (n for n in table if key == n or key.startswith(n)), key=len, default=None
    )


def estimate_cost(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    """LLM/임베딩 토큰 비용(USD). 임베딩 모델은 자동 인식해 단일 요율로 계산한다."""
    key = (model or "").lower()
    # 임베딩 모델이면 임베딩 요율로 (완성 토큰 개념 없음 — 입력 토큰만 과금)
    emb = _match_key(key, EMBEDDING_PRICING)
    if emb is not None:
        rate = EMBEDDING_PRICING[emb]
        return round((prompt_tokens + completion_tokens) / 1_000_000 * rate, 6)
    name = _match_key(key, PRICING)
    in_rate, out_rate = PRICING.get(name or "", DEFAULT_PRICE)
    return round(
        prompt_tokens / 1_000_000 * in_rate + completion_tokens / 1_000_000 * out_rate,
        6,
    )


def embedding_cost(model: str, tokens: int) -> float:
    """임베딩 입력 토큰 비용(USD)."""
    emb = _match_key((model or "").lower(), EMBEDDING_PRICING)
    rate = EMBEDDING_PRICING.get(emb or "", EMBEDDING_DEFAULT)
    return round(tokens / 1_000_000 * rate, 6)


def _stt_info(model: str) -> dict:
    m = _match_key((model or "").lower(), STT_PRICING)
    return STT_PRICING.get(m or "", STT_DEFAULT)


def stt_cost_per_min(model: str) -> float:
    """STT 모델의 분당 단가(USD)."""
    return float(_stt_info(model).get("per_min", STT_DEFAULT.get("per_min", 0.017)))


def stt_cost(
    model: str,
    seconds: float = 0.0,
    *,
    audio_tokens: int | None = None,
    text_tokens: int | None = None,
) -> float:
    """STT 비용(USD). 기본은 분당 과금. 토큰 단가가 등록된 모델에서 audio/text_tokens가
    주어지면 토큰 기반 합산이 분당 과금보다 크면 그쪽을 채택한다(과소청구 방지)."""
    info = _stt_info(model)
    per_min = float(info.get("per_min", STT_DEFAULT.get("per_min", 0.017)))
    cost = seconds / 60.0 * per_min
    if (audio_tokens or text_tokens) and ("input" in info or "output" in info):
        tok_cost = (audio_tokens or 0) / 1_000_000 * float(info.get("input", 0.0)) + (
            text_tokens or 0
        ) / 1_000_000 * float(info.get("output", 0.0))
        cost = max(cost, tok_cost)
    return round(cost, 6)
