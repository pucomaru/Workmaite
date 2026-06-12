"""AI 에이전트 사용 로그(agent_logs)와 토큰 사용량(token_usage_logs)을 기록하는 데코레이터.

LangChain의 register_configure_hook + ContextVar 메커니즘을 사용해, 데코레이터로
감싼 함수 안에서 일어나는 모든 LLM 호출의 토큰 사용량을 자동으로 수집한다.
(langchain의 get_openai_callback과 동일한 원리 — LLM 호출부를 수정하지 않아도 된다.)

사용 예:
    from agent_logging import log_agent_run

    @log_agent_run("archive_analyze", user_id="user_id", meeting_id="meeting_id")
    async def analyze_archive_file(...):
        ...

    @log_agent_run("minutes_stream", meeting_id="meeting_id")
    async def generate_minutes_stream(...):   # async generator 도 지원
        ...
"""
import asyncio
import functools
import inspect
import json
import logging
import uuid
from contextvars import ContextVar
from datetime import datetime
from typing import Any, Callable, Optional

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.outputs import LLMResult
from langchain_core.tracers.context import register_configure_hook

import models
from langchain_core.tracers.context import collect_runs
from database import SessionLocal

logger = logging.getLogger("agent_logging")

# ── 모델별 1M 토큰당 단가 (USD): (prompt, completion) ─────────────────────────
_PRICING: dict[str, tuple[float, float]] = {
    "gpt-4o":        (2.50, 10.00),
    "gpt-4o-mini":   (0.15, 0.60),
    "gpt-4.1":       (2.00, 8.00),
    "gpt-4.1-mini":  (0.40, 1.60),
    "gpt-4.1-nano":  (0.10, 0.40),
    "gpt-4-turbo":   (10.00, 30.00),
    "gpt-4":         (30.00, 60.00),
    "gpt-3.5-turbo": (0.50, 1.50),
    "o1":            (15.00, 60.00),
    "o1-mini":       (1.10, 4.40),
    "o3-mini":       (1.10, 4.40),
}
_DEFAULT_PRICE = (0.15, 0.60)  # 알 수 없는 모델 → gpt-4o-mini 기준


def _estimate_cost(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    key = (model or "").lower()
    price = next((p for name, p in _PRICING.items() if key == name or key.startswith(name)), None)
    in_rate, out_rate = price or _DEFAULT_PRICE
    return round(prompt_tokens / 1_000_000 * in_rate + completion_tokens / 1_000_000 * out_rate, 6)


class TokenUsageCollector(BaseCallbackHandler):
    """LLM 호출의 토큰 사용량을 모델별로 누적한다 (스트리밍 포함)."""

    raise_error = False

    def __init__(self) -> None:
        # model_name -> {"prompt": int, "completion": int}
        self.usage: dict[str, dict[str, int]] = {}

    def _add(self, model: str, prompt: int, completion: int) -> None:
        if not (prompt or completion):
            return
        slot = self.usage.setdefault(model or "unknown", {"prompt": 0, "completion": 0})
        slot["prompt"] += int(prompt or 0)
        slot["completion"] += int(completion or 0)

    def on_llm_end(self, response: LLMResult, **kwargs: Any) -> None:
        model = ""
        prompt = completion = 0

        llm_output = response.llm_output or {}
        if isinstance(llm_output, dict):
            model = llm_output.get("model_name") or llm_output.get("model") or ""
            tu = llm_output.get("token_usage") or llm_output.get("usage") or {}
            if isinstance(tu, dict):
                prompt = tu.get("prompt_tokens", 0) or 0
                completion = tu.get("completion_tokens", 0) or 0

        # llm_output 에 토큰 정보가 없으면 메시지의 usage_metadata 에서 집계
        if not (prompt or completion):
            for gens in response.generations:
                for gen in gens:
                    msg = getattr(gen, "message", None)
                    if msg is None:
                        continue
                    um = getattr(msg, "usage_metadata", None)
                    if um:
                        prompt += um.get("input_tokens", 0) or 0
                        completion += um.get("output_tokens", 0) or 0
                    if not model:
                        rm = getattr(msg, "response_metadata", None) or {}
                        model = rm.get("model_name") or rm.get("model") or model

        self._add(model, prompt, completion)


# ── ContextVar 자동 부착 (LangChain 전역 콜백 훅) ──────────────────────────────
_token_collector_var: ContextVar[Optional[TokenUsageCollector]] = ContextVar(
    "workmaite_token_collector", default=None
)
register_configure_hook(_token_collector_var, inheritable=True)


# ── 컨텍스트 값 해석 (meeting_id / session_id / user_id) ───────────────────────
def _resolve(spec: Any, bound: inspect.BoundArguments) -> Optional[int]:
    if spec is None:
        return None
    if callable(spec):
        try:
            return spec(bound.arguments)
        except Exception:
            return None
    val = bound.arguments.get(spec)
    if val is None:
        return None
    if hasattr(val, "id"):  # current_user 같은 ORM 객체
        return getattr(val, "id")
    try:
        return int(val)
    except (TypeError, ValueError):
        return None


def _safe_input(bound: inspect.BoundArguments) -> Optional[dict]:
    """직렬화 가능한 입력 요약 (DB 세션·파일·대용량 객체는 제외)."""
    skip = {"db", "background_tasks", "current_user", "file", "self", "cls"}
    out: dict = {}
    for k, v in bound.arguments.items():
        if k in skip:
            continue
        if isinstance(v, bool) or isinstance(v, (int, float)):
            out[k] = v
        elif isinstance(v, str):
            out[k] = v if len(v) <= 300 else v[:300] + "…"
        elif isinstance(v, (list, dict)):
            try:
                s = json.dumps(v, ensure_ascii=False, default=str)
                out[k] = v if len(s) <= 800 else f"[{type(v).__name__} len={len(v)}]"
            except Exception:
                out[k] = f"[{type(v).__name__}]"
    return out or None


def _safe_output(result: Any) -> Optional[dict]:
    """결과 dict 에서 핵심 지표만 요약."""
    if not isinstance(result, dict):
        return None
    out: dict = {}
    for k in ("score", "status", "matched_agendas", "related_depts"):
        if k in result:
            out[k] = result[k]
    if isinstance(result.get("feedback"), list):
        out["feedback_count"] = len(result["feedback"])
    if isinstance(result.get("agendas"), list):
        out["agenda_count"] = len(result["agendas"])
    return out or None


# ── DB 기록 ────────────────────────────────────────────────────────────────
def _create_log(*, context_type, meeting_id, session_id, user_id, input_data) -> Optional[int]:
    db = SessionLocal()
    try:
        log = models.AgentLog(
            task_id=str(uuid.uuid4()),
            context_type=context_type,
            meeting_id=meeting_id,
            session_id=session_id,
            user_id=user_id,
            status="running",
            input_data=input_data,
        )
        db.add(log)
        db.commit()
        db.refresh(log)
        return log.id
    except Exception as e:
        db.rollback()
        logger.warning(f"[agent_logging] AgentLog 생성 실패 ({context_type}): {e}")
        return None
    finally:
        db.close()


def _extract_trace_id(runs_cm, runs_cb) -> Optional[str]:
    try:
        runs_cm.__exit__(None, None, None)
        if runs_cb.traced_runs:
            return str(runs_cb.traced_runs[0].id)
    except Exception:
        pass
    return None


def _finalize(log_id: Optional[int], collector: TokenUsageCollector,
              error: Optional[BaseException], output_data: Optional[dict],
              trace_id: Optional[str] = None) -> None:
    if log_id is None:
        return
    db = SessionLocal()
    try:
        log = db.query(models.AgentLog).filter(models.AgentLog.id == log_id).first()
        if not log:
            return
        log.status = "failed" if error else "success"
        log.error_message = str(error)[:1000] if error else None
        log.ended_at = datetime.utcnow()
        if trace_id:
            log.trace_id = trace_id
        if output_data:
            log.output_data = output_data

        for model_name, u in collector.usage.items():
            pt, ct = u["prompt"], u["completion"]
            db.add(models.TokenUsageLog(
                agent_log_id=log.id,
                model_name=model_name,
                prompt_tokens=pt,
                completion_tokens=ct,
                estimated_cost_usd=_estimate_cost(model_name, pt, ct),
            ))
        db.commit()
    except Exception as e:
        db.rollback()
        logger.warning(f"[agent_logging] 로그 마무리 실패: {e}")
    finally:
        db.close()


# ── 데코레이터 ──────────────────────────────────────────────────────────────
def log_agent_run(
    context_type: str,
    *,
    meeting_id: Any = None,
    session_id: Any = None,
    user_id: Any = None,
    capture_output: Optional[Callable[[Any], Optional[dict]]] = None,
):
    """에이전트 실행을 agent_logs + token_usage_logs 에 기록하는 데코레이터.

    Args:
        context_type: agent_logs.context_type 값.
        meeting_id / session_id / user_id: 인자 이름(str), arguments dict 를 받는
            callable, 또는 current_user 같은 객체 인자 이름. 객체면 .id 를 사용.
        capture_output: 결과(또는 스트리밍 이벤트)에서 출력 dict 를 뽑아내는 함수.
            async generator 의 경우, 각 yield 항목에 대해 호출되어 마지막 non-None
            반환값이 output_data 로 기록된다.
    """
    def decorator(func):
        sig = inspect.signature(func)

        def _start(args, kwargs):
            bound = sig.bind(*args, **kwargs)
            bound.apply_defaults()
            collector = TokenUsageCollector()
            token = _token_collector_var.set(collector)
            # 루트 run id 수집 — LangSmith 트레이스 연결 (P3A-3). 트레이싱 off여도 동작.
            runs_cm = collect_runs()
            runs_cb = runs_cm.__enter__()
            log_id = _create_log(
                context_type=context_type,
                meeting_id=_resolve(meeting_id, bound),
                session_id=_resolve(session_id, bound),
                user_id=_resolve(user_id, bound),
                input_data=_safe_input(bound),
            )
            return log_id, collector, token, runs_cm, runs_cb

        if inspect.isasyncgenfunction(func):
            @functools.wraps(func)
            async def agen_wrapper(*args, **kwargs):
                log_id, collector, token, runs_cm, runs_cb = _start(args, kwargs)
                error = None
                captured: Optional[dict] = None
                try:
                    async for item in func(*args, **kwargs):
                        if capture_output:
                            try:
                                c = capture_output(item)
                                if c is not None:
                                    captured = c
                            except Exception:
                                pass
                        yield item
                except BaseException as e:  # noqa: BLE001
                    error = e
                    raise
                finally:
                    _token_collector_var.reset(token)
                    _trace_id = _extract_trace_id(runs_cm, runs_cb)
                    # call_soon으로 스케줄링: GeneratorExit/클라이언트 연결 끊김 시에도
                    # 이벤트 루프가 살아있는 한 _finalize가 반드시 실행된다.
                    _err = error
                    _out = _safe_output(captured)
                    try:
                        asyncio.get_running_loop().call_soon(
                            functools.partial(_finalize, log_id, collector, _err, _out, _trace_id)
                        )
                    except RuntimeError:
                        _finalize(log_id, collector, _err, _out, _trace_id)
            return agen_wrapper

        @functools.wraps(func)
        async def coro_wrapper(*args, **kwargs):
            log_id, collector, token, runs_cm, runs_cb = _start(args, kwargs)
            error = None
            result = None
            try:
                result = await func(*args, **kwargs)
                return result
            except BaseException as e:  # noqa: BLE001
                error = e
                raise
            finally:
                _token_collector_var.reset(token)
                trace_id = _extract_trace_id(runs_cm, runs_cb)
                if capture_output:
                    try:
                        out = _safe_output(capture_output(result))
                    except Exception:
                        out = None
                else:
                    out = _safe_output(result)
                _finalize(log_id, collector, error, out, trace_id)
        return coro_wrapper

    return decorator
