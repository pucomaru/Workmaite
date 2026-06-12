"""usage.py — 토큰 / STT 사용량 조회 엔드포인트"""
from datetime import datetime, timedelta, date as date_type
from typing import Optional

from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func

import models
from auth import get_current_user
from database import get_db

router = APIRouter(prefix="/api/usage", tags=["usage"])

# ── context_type → section 매핑 ──────────────────────────────────────────────
# context_type 분류는 context_types 모듈로 통합 (HC-8)
from context_types import section_of as _section_of

_SECTION_LABELS = {
    "task_extraction": "아젠다 추출 Agent",
    "report_analysis": "보고서 분석 Agent",
    "meeting":         "회의 Agent",
    "other":           "기타",
}
_SECTION_ORDER = ["task_extraction", "report_analysis", "meeting", "other"]

# ── STT 제공자별 비용 ─────────────────────────────────────────────────────────
_STT_PROVIDERS: dict[str, dict] = {
    "gcapi":        {"label": "Google Cloud",   "cost_per_min": 0.010},
    "whisperapi":   {"label": "OpenAI Whisper", "cost_per_min": 0.006},
    "localwhisper": {"label": "Local Whisper",  "cost_per_min": 0.000},
}
_STT_FALLBACK = {"label": "STT", "cost_per_min": 0.010}


@router.get("/tokens")
def get_token_usage(
    start_date:   Optional[str]  = Query(default=None, description="시작일 (YYYY-MM-DD)"),
    end_date:     Optional[str]  = Query(default=None, description="종료일 (YYYY-MM-DD)"),
    current_user: models.User    = Depends(get_current_user),
    db:           Session        = Depends(get_db),
):
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

    _base = (
        lambda q: q
        .join(models.AgentLog, models.TokenUsageLog.agent_log_id == models.AgentLog.id)
        .filter(
            models.AgentLog.user_id == current_user.id,
            models.TokenUsageLog.created_at >= since,
            models.TokenUsageLog.created_at <= until,
        )
    )

    # ── 1. 모델별 합계 ─────────────────────────────────────────────────────────
    model_rows = _base(
        db.query(
            models.TokenUsageLog.model_name,
            func.sum(models.TokenUsageLog.prompt_tokens).label("pt"),
            func.sum(models.TokenUsageLog.completion_tokens).label("ct"),
            func.sum(models.TokenUsageLog.estimated_cost_usd).label("cost"),
        )
    ).group_by(models.TokenUsageLog.model_name).all()

    # ── 2. 모델 × context_type 세분화 ──────────────────────────────────────────
    mc_rows = _base(
        db.query(
            models.TokenUsageLog.model_name,
            models.AgentLog.context_type,
            func.sum(models.TokenUsageLog.prompt_tokens).label("pt"),
            func.sum(models.TokenUsageLog.completion_tokens).label("ct"),
            func.sum(models.TokenUsageLog.estimated_cost_usd).label("cost"),
        )
    ).group_by(models.TokenUsageLog.model_name, models.AgentLog.context_type).all()

    # by_mc[model][section] = {total_tokens, cost}
    by_mc: dict[str, dict] = {}
    for r in mc_rows:
        sec = _section_of(r.context_type)
        by_mc.setdefault(r.model_name, {}).setdefault(sec, {"total_tokens": 0, "cost": 0.0})
        by_mc[r.model_name][sec]["total_tokens"] += int((r.pt or 0) + (r.ct or 0))
        by_mc[r.model_name][sec]["cost"]         += float(r.cost or 0)

    # ── 3. 전체 기간 누적 ──────────────────────────────────────────────────────
    all_time = (
        db.query(
            func.sum(models.TokenUsageLog.prompt_tokens).label("pt"),
            func.sum(models.TokenUsageLog.completion_tokens).label("ct"),
            func.sum(models.TokenUsageLog.estimated_cost_usd).label("cost"),
        )
        .join(models.AgentLog, models.TokenUsageLog.agent_log_id == models.AgentLog.id)
        .filter(models.AgentLog.user_id == current_user.id)
        .first()
    )

    # ── 4. STT 제공자별 집계 ────────────────────────────────────────────────────
    stt_base = (
        db.query(
            models.SttSegment.provider,
            func.sum(models.SttSegment.end_sec - models.SttSegment.start_sec).label("secs"),
        )
        .join(models.MeetingSession, models.SttSegment.session_id == models.MeetingSession.id)
        .join(models.MeetingMember,  models.MeetingSession.meeting_id == models.MeetingMember.meeting_id)
        .filter(
            models.MeetingMember.user_id == current_user.id,
            models.SttSegment.created_at >= since,
            models.SttSegment.created_at <= until,
            models.SttSegment.provider.isnot(None),
        )
        .group_by(models.SttSegment.provider)
        .all()
    )

    by_provider = []
    stt_total_secs = 0.0
    stt_total_cost = 0.0
    for r in stt_base:
        secs  = float(r.secs or 0)
        mins  = secs / 60.0
        prov  = r.provider
        info  = _STT_PROVIDERS.get(prov, _STT_FALLBACK)
        cost  = round(mins * info["cost_per_min"], 6)
        by_provider.append({
            "provider":     prov,
            "label":        info["label"],
            "seconds":      round(secs, 1),
            "minutes":      round(mins, 2),
            "cost_per_min": info["cost_per_min"],
            "cost":         cost,
        })
        stt_total_secs += secs
        stt_total_cost += cost
    by_provider.sort(key=lambda x: x["seconds"], reverse=True)

    # ── 5. 모델 목록 조합 ──────────────────────────────────────────────────────
    by_model = sorted([
        {
            "model_name":   r.model_name,
            "total_tokens": int((r.pt or 0) + (r.ct or 0)),
            "cost":         round(float(r.cost or 0), 6),
            "by_context": [
                {
                    "section": s,
                    "label":   _SECTION_LABELS.get(s, s),
                    "total_tokens": by_mc.get(r.model_name, {}).get(s, {}).get("total_tokens", 0),
                    "cost":         round(by_mc.get(r.model_name, {}).get(s, {}).get("cost", 0.0), 6),
                }
                for s in _SECTION_ORDER
                if s in by_mc.get(r.model_name, {})
            ],
        }
        for r in model_rows
    ], key=lambda x: x["total_tokens"], reverse=True)

    period_tokens    = sum(r["total_tokens"] for r in by_model)
    period_llm_cost  = round(sum(r["cost"] for r in by_model), 6)
    period_grand_cost = round(period_llm_cost + stt_total_cost, 6)

    return {
        "start_date":          since.strftime("%Y-%m-%d"),
        "end_date":            until.strftime("%Y-%m-%d"),
        "period_total_tokens": period_tokens,
        "period_total_cost":   period_llm_cost,
        "period_grand_cost":   period_grand_cost,
        "total_all_time": {
            "total_tokens": int((all_time.pt or 0) + (all_time.ct or 0)) if all_time else 0,
            "cost":         round(float(all_time.cost or 0), 6) if all_time else 0,
        },
        "sections": {
            "ai_model": {
                "total_tokens": period_tokens,
                "cost":         period_llm_cost,
                "by_model":     by_model,
            },
            "stt": {
                "total_seconds": round(stt_total_secs, 1),
                "total_minutes": round(stt_total_secs / 60.0, 2),
                "total_cost":    round(stt_total_cost, 6),
                "by_provider":   by_provider,
            },
        },
    }
