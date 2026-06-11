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

# ── 섹션별 context_type 매핑 ──────────────────────────────────────────────────
_TASK_CONTEXTS    = {"task_extract"}
_REPORT_CONTEXTS  = {"archive_analyze", "archive_analyze_stream", "report_review"}
_MEETING_CONTEXTS = {"minutes_generate", "minutes_stream", "supervisor"}

STT_COST_PER_MINUTE = 0.01  # $0.01 / 분


def _section_of(context_type: str) -> str:
    if context_type in _TASK_CONTEXTS:
        return "task_extraction"
    if context_type in _REPORT_CONTEXTS:
        return "report_analysis"
    if context_type in _MEETING_CONTEXTS:
        return "meeting"
    return "other"


@router.get("/tokens")
def get_token_usage(
    start_date: Optional[str] = Query(default=None, description="시작일 (YYYY-MM-DD)"),
    end_date: Optional[str]   = Query(default=None, description="종료일 (YYYY-MM-DD)"),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """현재 사용자의 토큰 사용량 요약 (4개 섹션 + STT)."""
    today = date_type.today()
    try:
        date_from = datetime.strptime(start_date, "%Y-%m-%d") if start_date else datetime.combine(today - timedelta(days=29), datetime.min.time())
        date_to   = datetime.strptime(end_date,   "%Y-%m-%d") if end_date   else datetime.combine(today, datetime.max.time())
    except ValueError:
        raise HTTPException(status_code=400, detail="날짜 형식은 YYYY-MM-DD 입니다.")

    if date_from > date_to:
        raise HTTPException(status_code=400, detail="시작일은 종료일보다 이전이어야 합니다.")

    date_to = date_to.replace(hour=23, minute=59, second=59)
    since, until = date_from, date_to

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

    # ── context_type별 집계 ─────────────────────────────────────────────────
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

    # ── STT 오디오 처리 시간 (사용자 소속 세션) ─────────────────────────────
    stt_row = (
        db.query(
            func.sum(models.SttSegment.end_sec - models.SttSegment.start_sec).label("total_seconds"),
        )
        .join(models.MeetingSession, models.SttSegment.session_id == models.MeetingSession.id)
        .join(models.MeetingMember, models.MeetingSession.meeting_id == models.MeetingMember.meeting_id)
        .filter(
            models.MeetingMember.user_id == current_user.id,
            models.SttSegment.created_at >= since,
            models.SttSegment.created_at <= until,
        )
        .first()
    )
    stt_seconds = float(stt_row.total_seconds or 0) if stt_row else 0.0
    stt_minutes = stt_seconds / 60.0
    stt_cost    = round(stt_minutes * STT_COST_PER_MINUTE, 6)

    # ── 섹션별 집계 ─────────────────────────────────────────────────────────
    _sec: dict[str, dict] = {
        "task_extraction": {"prompt_tokens": 0, "completion_tokens": 0, "cost": 0.0},
        "report_analysis": {"prompt_tokens": 0, "completion_tokens": 0, "cost": 0.0},
        "meeting":         {"prompt_tokens": 0, "completion_tokens": 0, "cost": 0.0},
    }
    for r in context_rows:
        sec = _section_of(r.context_type)
        if sec in _sec:
            _sec[sec]["prompt_tokens"]     += int(r.prompt_tokens or 0)
            _sec[sec]["completion_tokens"] += int(r.completion_tokens or 0)
            _sec[sec]["cost"]              += float(r.total_cost or 0)

    for sec in _sec.values():
        sec["total_tokens"] = sec["prompt_tokens"] + sec["completion_tokens"]
        sec["cost"]         = round(sec["cost"], 6)

    # ── 모델별 목록 ─────────────────────────────────────────────────────────
    by_model = sorted([
        {
            "model_name":        r.model_name,
            "prompt_tokens":     int(r.prompt_tokens or 0),
            "completion_tokens": int(r.completion_tokens or 0),
            "total_tokens":      int((r.prompt_tokens or 0) + (r.completion_tokens or 0)),
            "cost":              round(float(r.total_cost or 0), 6),
        }
        for r in model_rows
    ], key=lambda x: x["total_tokens"], reverse=True)

    period_total_tokens = sum(r["total_tokens"] for r in by_model)
    period_total_cost   = round(sum(r["cost"] for r in by_model), 6)

    total_all_time = {
        "prompt_tokens":     int(all_time_row.prompt_tokens or 0) if all_time_row else 0,
        "completion_tokens": int(all_time_row.completion_tokens or 0) if all_time_row else 0,
        "total_tokens":      int((all_time_row.prompt_tokens or 0) + (all_time_row.completion_tokens or 0)) if all_time_row else 0,
        "cost":              round(float(all_time_row.total_cost or 0), 6) if all_time_row else 0,
    }

    # ── 섹션 응답 조합 ───────────────────────────────────────────────────────
    sections = {
        "ai_model": {
            "total_tokens":      period_total_tokens,
            "prompt_tokens":     sum(r["prompt_tokens"] for r in by_model),
            "completion_tokens": sum(r["completion_tokens"] for r in by_model),
            "cost":              period_total_cost,
            "by_model":          by_model,
        },
        "task_extraction": _sec["task_extraction"],
        "report_analysis": _sec["report_analysis"],
        "meeting": {
            **_sec["meeting"],
            "stt_seconds": round(stt_seconds, 1),
            "stt_minutes": round(stt_minutes, 2),
            "stt_cost":    stt_cost,
            "total_cost":  round(_sec["meeting"]["cost"] + stt_cost, 6),
        },
    }

    return {
        "start_date":          since.strftime("%Y-%m-%d"),
        "end_date":            until.strftime("%Y-%m-%d"),
        "period_total_tokens": period_total_tokens,
        "period_total_cost":   period_total_cost,
        "total_all_time":      total_all_time,
        "sections":            sections,
        # 하위 호환
        "by_model":   by_model,
        "by_context": [
            {
                "context_type":      r.context_type,
                "prompt_tokens":     int(r.prompt_tokens or 0),
                "completion_tokens": int(r.completion_tokens or 0),
                "total_tokens":      int((r.prompt_tokens or 0) + (r.completion_tokens or 0)),
                "cost":              round(float(r.total_cost or 0), 6),
            }
            for r in sorted(context_rows, key=lambda r: (r.prompt_tokens or 0) + (r.completion_tokens or 0), reverse=True)
        ],
    }
