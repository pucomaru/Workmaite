"""LLM 단가표 로더 (P5-3, HC-7) — pricing.yaml에서 로드, 코드 하드코딩 제거.

PRICING_FILE env로 경로 오버라이드 가능. 파일이 없거나 깨져도 내장 기본값으로 동작한다.
"""
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

_FALLBACK_DEFAULT = (2.50, 10.00)
_FALLBACK_MODELS = {"gpt-4o-mini": (0.15, 0.60), "gpt-4o": (2.50, 10.00)}


def _load() -> tuple[dict[str, tuple[float, float]], tuple[float, float]]:
    path = Path(os.environ.get("PRICING_FILE", Path(__file__).parent / "pricing.yaml"))
    try:
        import yaml
        data = yaml.safe_load(path.read_text())
        models = {k: tuple(v) for k, v in (data.get("models") or {}).items()}
        default = tuple(data.get("default") or _FALLBACK_DEFAULT)
        return models, default
    except Exception as e:
        logger.warning(f"[Pricing] {path} 로드 실패, 내장 기본값 사용: {e}")
        return dict(_FALLBACK_MODELS), _FALLBACK_DEFAULT


PRICING, DEFAULT_PRICE = _load()


def estimate_cost(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    key = (model or "").lower()
    # 최장 prefix 매칭 — "gpt-4o-mini-…"가 "gpt-4o" 단가로 잡히는 것 방지 (기존 코드의 잠재 버그)
    name = max((n for n in PRICING if key == n or key.startswith(n)), key=len, default=None)
    in_rate, out_rate = PRICING.get(name, DEFAULT_PRICE)
    return round(prompt_tokens / 1_000_000 * in_rate + completion_tokens / 1_000_000 * out_rate, 6)
