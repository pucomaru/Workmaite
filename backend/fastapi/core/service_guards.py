"""챗봇 서비스 가드 (P3C-1/P3C-2, H-7/H-8).

- 일일 토큰 예산: **PostgreSQL 집계** — 비용 누적치는 재시작에 리셋되면 안 되므로
  이미 기록 중인 token_usage_logs를 합산해 판정한다 (별도 카운터 불필요).
- idempotency: 확정/커밋류 엔드포인트의 더블클릭·재시도 중복 차단 (인메모리 TTL,
  단일 replica 전제 — HITL 확정은 체크포인터의 resume 상태로도 2차 방어됨).
"""

import logging
import os
import time
from datetime import datetime, time as dtime

from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from db import models

logger = logging.getLogger(__name__)

DAILY_TOKEN_BUDGET = int(os.environ.get("DAILY_TOKEN_BUDGET", "300000"))


def check_daily_token_budget(db: Session, user_id: int) -> None:
    """사용자별 일일 토큰 예산 (PG 집계 — token_usage_logs, 오늘 0시 기준)."""
    since = datetime.combine(datetime.now().date(), dtime.min)
    used = (
        db.query(
            func.coalesce(
                func.sum(
                    models.TokenUsageLog.prompt_tokens
                    + models.TokenUsageLog.completion_tokens
                ),
                0,
            )
        )
        .join(models.AgentLog, models.TokenUsageLog.agent_log_id == models.AgentLog.id)
        .filter(
            models.AgentLog.user_id == user_id, models.TokenUsageLog.created_at >= since
        )
        .scalar()
    )
    if used >= DAILY_TOKEN_BUDGET:
        logger.warning(
            f"[Guard] user={user_id} 일일 토큰 예산 초과 ({used}/{DAILY_TOKEN_BUDGET})"
        )
        raise HTTPException(
            status_code=429,
            detail="오늘 사용 가능한 AI 사용량을 모두 사용했습니다. 내일 다시 이용해주세요.",
        )


# ─── idempotency (P3C-2) ──────────────────────────────────────────────────────
_IDEMPOTENCY_TTL_SEC = 600
_recent_keys: dict[str, float] = {}


def idempotency_guard(key: str) -> None:
    """같은 key의 확정/커밋이 TTL 내 재도착하면 409 — 더블클릭/재시도 중복 차단."""
    now = time.time()
    # 만료 정리 (호출 빈도가 낮은 엔드포인트라 단순 스윕으로 충분)
    for k in [k for k, t in _recent_keys.items() if t < now - _IDEMPOTENCY_TTL_SEC]:
        _recent_keys.pop(k, None)
    if key in _recent_keys:
        raise HTTPException(
            status_code=409, detail="이미 처리된 요청입니다 (중복 차단)."
        )
    _recent_keys[key] = now


def release_idempotency(key: str) -> None:
    """처리 실패 시 키를 해제해 정당한 재시도를 허용한다."""
    _recent_keys.pop(key, None)


# ─── 동시 실행 제한 (P3C-4) ──────────────────────────────────────────────────
import asyncio as _asyncio  # noqa: E402
from contextlib import asynccontextmanager as _acm  # noqa: E402

_user_semaphores: dict[int, _asyncio.Semaphore] = {}


@_acm
async def single_flight(user_id: int):
    """무거운 분석은 사용자당 동시 1개로 제한 — 폭주·중복 분석 방지 (단일 replica 전제)."""
    sem = _user_semaphores.setdefault(user_id, _asyncio.Semaphore(1))
    if sem.locked():
        raise HTTPException(
            status_code=429,
            detail="이전 분석이 진행 중입니다. 완료 후 다시 시도해주세요.",
        )
    async with sem:
        yield
