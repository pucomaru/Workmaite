"""usage.py — 토큰 사용량 조회 엔드포인트"""
from datetime import datetime, timedelta, date as date_type
from typing import Optional

from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func

import models
from auth import get_current_user
from database import get_db

router = APIRouter(prefix="/api/usage", tags=["usage"])


@router.get("/tokens")
def get_token_usage(
    start_date: Optional[str] = Query(default=None, description="시작일 (YYYY-MM-DD)"),
    end_date: Optional[str]   = Query(default=None, description="종료일 (YYYY-MM-DD)"),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """현재 사용자의 토큰 사용량 요약을 반환합니다.

    - ``by_model``: 기간 내 모델별 집계
    - ``total_all_time``: 전체 기간 누적
    - ``daily``: 기간 내 일별 집계
    """
    # 날짜 파싱 / 기본값 체우기
    today = date_type.today()
    try:
        date_from = datetime.strptime(start_date, "%Y-%m-%d") if start_date else datetime.combine(today - timedelta(days=29), datetime.min.time())
        date_to   = datetime.strptime(end_date,   "%Y-%m-%d") if end_date   else datetime.combine(today, datetime.max.time())
    except ValueError:
        raise HTTPException(status_code=400, detail="날짜 형식은 YYYY-MM-DD 입니다.")

    if date_from > date_to:
        raise HTTPException(status_code=400, detail="시작일은 종료일보다 이전이어야 합니다.")

    # end_date는 해당 날짜 끝(23:59:59)를 포함
    date_to = date_to.replace(hour=23, minute=59, second=59)

    since = date_from
    until = date_to

    # ── 기간 내 모델별 집계 ─────────────────────────────────────────────────
    model_rows = (
        db.query(
            models.TokenUsageLog.model_name,
            func.sum(models.TokenUsageLog.prompt_tokens).label("prompt_tokens"),
            func.sum(models.TokenUsageLog.completion_tokens).label("completion_tokens"),
            func.sum(models.TokenUsageLog.estimated_cost_usd).label("total_cost"),
        )
        .join(models.AgentLog, models.TokenUsageLog.agent_log_id == models.AgentLog.id)
        .filter(
            models.AgentLog.user_id == current_user.id,
            models.TokenUsageLog.created_at >= since,
            models.TokenUsageLog.created_at <= until,
        )
        .group_by(models.TokenUsageLog.model_name)
        .all()
    )

    # ── 전체 기간 누적 ──────────────────────────────────────────────────────
    all_time_row = (
        db.query(
            func.sum(models.TokenUsageLog.prompt_tokens).label("prompt_tokens"),
            func.sum(models.TokenUsageLog.completion_tokens).label("completion_tokens"),
            func.sum(models.TokenUsageLog.estimated_cost_usd).label("total_cost"),
        )
        .join(models.AgentLog, models.TokenUsageLog.agent_log_id == models.AgentLog.id)
        .filter(models.AgentLog.user_id == current_user.id)
        .first()
    )

    # ── 기간 내 일별 집계 ───────────────────────────────────────────────────
    daily_rows = (
        db.query(
            func.date(models.TokenUsageLog.created_at).label("date"),
            func.sum(models.TokenUsageLog.prompt_tokens).label("prompt_tokens"),
            func.sum(models.TokenUsageLog.completion_tokens).label("completion_tokens"),
            func.sum(models.TokenUsageLog.estimated_cost_usd).label("cost"),
        )
        .join(models.AgentLog, models.TokenUsageLog.agent_log_id == models.AgentLog.id)
        .filter(
            models.AgentLog.user_id == current_user.id,
            models.TokenUsageLog.created_at >= since,
            models.TokenUsageLog.created_at <= until,
        )
        .group_by(func.date(models.TokenUsageLog.created_at))
        .order_by(func.date(models.TokenUsageLog.created_at))
        .all()
    )

    # ── context_type별 집계 (어떤 에이전트를 많이 썼는지) ───────────────────
    context_rows = (
        db.query(
            models.AgentLog.context_type,
            func.sum(models.TokenUsageLog.prompt_tokens).label("prompt_tokens"),
            func.sum(models.TokenUsageLog.completion_tokens).label("completion_tokens"),
            func.sum(models.TokenUsageLog.estimated_cost_usd).label("total_cost"),
        )
        .join(models.AgentLog, models.TokenUsageLog.agent_log_id == models.AgentLog.id)
        .filter(
            models.AgentLog.user_id == current_user.id,
            models.TokenUsageLog.created_at >= since,
            models.TokenUsageLog.created_at <= until,
        )
        .group_by(models.AgentLog.context_type)
        .all()
    )

    by_model = [
        {
            "model_name": r.model_name,
            "prompt_tokens": int(r.prompt_tokens or 0),
            "completion_tokens": int(r.completion_tokens or 0),
            "total_tokens": int((r.prompt_tokens or 0) + (r.completion_tokens or 0)),
            "cost": round(float(r.total_cost or 0), 6),
        }
        for r in model_rows
    ]
    by_model.sort(key=lambda x: x["total_tokens"], reverse=True)

    total_all_time = {
        "prompt_tokens": int(all_time_row.prompt_tokens or 0) if all_time_row else 0,
        "completion_tokens": int(all_time_row.completion_tokens or 0) if all_time_row else 0,
        "total_tokens": int(
            (all_time_row.prompt_tokens or 0) + (all_time_row.completion_tokens or 0)
        ) if all_time_row else 0,
        "cost": round(float(all_time_row.total_cost or 0), 6) if all_time_row else 0,
    }

    daily = [
        {
            "date": str(r.date),
            "prompt_tokens": int(r.prompt_tokens or 0),
            "completion_tokens": int(r.completion_tokens or 0),
            "total_tokens": int((r.prompt_tokens or 0) + (r.completion_tokens or 0)),
            "cost": round(float(r.cost or 0), 6),
        }
        for r in daily_rows
    ]

    by_context = [
        {
            "context_type": r.context_type,
            "prompt_tokens": int(r.prompt_tokens or 0),
            "completion_tokens": int(r.completion_tokens or 0),
            "total_tokens": int((r.prompt_tokens or 0) + (r.completion_tokens or 0)),
            "cost": round(float(r.total_cost or 0), 6),
        }
        for r in context_rows
    ]
    by_context.sort(key=lambda x: x["total_tokens"], reverse=True)

    # 기간 내 총계
    period_total_tokens = sum(r["total_tokens"] for r in by_model)
    period_total_cost = round(sum(r["cost"] for r in by_model), 6)

    return {
        "start_date": since.strftime("%Y-%m-%d"),
        "end_date": until.strftime("%Y-%m-%d"),
        "period_total_tokens": period_total_tokens,
        "period_total_cost": period_total_cost,
        "by_model": by_model,
        "by_context": by_context,
        "total_all_time": total_all_time,
        "daily": daily,
    }
