"""usage.py — 토큰 / STT 사용량 조회 엔드포인트"""

from datetime import datetime, timedelta, date as date_type
from typing import Optional

from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func

from db import models
from core.auth import get_current_user
from db.database import get_db

router = APIRouter(prefix="/api/usage", tags=["usage"])

# ── context_type → section 매핑 ──────────────────────────────────────────────
# context_type 분류는 context_types 모듈로 통합 (HC-8)
# 에이전트(context_type) 라벨·그룹은 context_types로 통합 (P3) — 4섹션 축약 해제
from core.context_types import agent_of, agent_label, context_label  # noqa: E402

# ── STT 단가는 pricing.yaml로 이전 (P0) — 코드 하드코딩 제거 ──────────────────
from llm.pricing import stt_cost, stt_cost_per_min  # noqa: E402

# STT provider/모델 → 표시 라벨. provider에 실제 STT 모델명이 저장된다(P4).
_STT_LABELS = {
    "gpt-realtime-whisper": "gpt-realtime-whisper",
    "gpt-4o-transcribe": "gpt-4o-transcribe",
    "gpt-4o-mini-transcribe": "gpt-4o-mini-transcribe",
    "whisper-1": "whisper-1",
}


def _stt_label(prov: str) -> str:
    """provider(모델명) → 라벨. diarize 등 변형은 prefix 매칭."""
    if prov in _STT_LABELS:
        return _STT_LABELS[prov]
    for k, v in _STT_LABELS.items():
        if prov and prov.startswith(k):
            return v
    return prov or "STT"


@router.get("/tokens")
def get_token_usage(
    start_date: Optional[str] = Query(default=None, description="시작일 (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(default=None, description="종료일 (YYYY-MM-DD)"),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    today = date_type.today()
    try:
        date_from = (
            datetime.strptime(start_date, "%Y-%m-%d")
            if start_date
            else datetime.combine(today - timedelta(days=29), datetime.min.time())
        )
        date_to = (
            datetime.strptime(end_date, "%Y-%m-%d")
            if end_date
            else datetime.combine(today, datetime.max.time())
        )
    except ValueError:
        raise HTTPException(status_code=400, detail="날짜 형식은 YYYY-MM-DD 입니다.")

    if date_from > date_to:
        raise HTTPException(
            status_code=400, detail="시작일은 종료일보다 이전이어야 합니다."
        )

    date_to = date_to.replace(hour=23, minute=59, second=59)
    since, until = date_from, date_to

    def _base(q):
        return q.join(
            models.AgentLog, models.TokenUsageLog.agent_log_id == models.AgentLog.id
        ).filter(
            models.AgentLog.user_id == current_user.id,
            models.TokenUsageLog.created_at >= since,
            models.TokenUsageLog.created_at <= until,
        )

    # ── 1. 모델별 합계 ─────────────────────────────────────────────────────────
    model_rows = (
        _base(
            db.query(
                models.TokenUsageLog.model_name,
                func.sum(models.TokenUsageLog.prompt_tokens).label("pt"),
                func.sum(models.TokenUsageLog.completion_tokens).label("ct"),
                func.sum(models.TokenUsageLog.estimated_cost_usd).label("cost"),
            )
        )
        .group_by(models.TokenUsageLog.model_name)
        .all()
    )

    # ── 2. 모델 × context_type 세분화 ──────────────────────────────────────────
    mc_rows = (
        _base(
            db.query(
                models.TokenUsageLog.model_name,
                models.AgentLog.context_type,
                func.sum(models.TokenUsageLog.prompt_tokens).label("pt"),
                func.sum(models.TokenUsageLog.completion_tokens).label("ct"),
                func.sum(models.TokenUsageLog.estimated_cost_usd).label("cost"),
            )
        )
        .group_by(models.TokenUsageLog.model_name, models.AgentLog.context_type)
        .all()
    )

    # by_mc[model][context_type] = {total_tokens, cost};  by_agent[group] = {…} (모델 합산)
    by_mc: dict[str, dict] = {}
    by_agent: dict[str, dict] = {}
    for r in mc_rows:
        ctx = r.context_type
        tokens = int((r.pt or 0) + (r.ct or 0))
        cost = float(r.cost or 0)
        by_mc.setdefault(r.model_name, {}).setdefault(
            ctx, {"total_tokens": 0, "cost": 0.0}
        )
        by_mc[r.model_name][ctx]["total_tokens"] += tokens
        by_mc[r.model_name][ctx]["cost"] += cost
        grp = by_agent.setdefault(agent_of(ctx), {"total_tokens": 0, "cost": 0.0})
        grp["total_tokens"] += tokens
        grp["cost"] += cost

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
            func.sum(models.SttSegment.end_sec - models.SttSegment.start_sec).label(
                "secs"
            ),
        )
        .join(
            models.MeetingSession,
            models.SttSegment.session_id == models.MeetingSession.id,
        )
        .join(
            models.MeetingMember,
            models.MeetingSession.meeting_id == models.MeetingMember.meeting_id,
        )
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
        secs = float(r.secs or 0)
        mins = secs / 60.0
        prov = r.provider
        # 단가는 pricing.yaml에서 (provider에 실제 STT 모델명이 저장되면 모델별 단가 적용)
        cost = stt_cost(prov, secs)
        by_provider.append(
            {
                "provider": prov,
                "label": _stt_label(prov),
                "seconds": round(secs, 1),
                "minutes": round(mins, 2),
                "cost_per_min": stt_cost_per_min(prov),
                "cost": cost,
            }
        )
        stt_total_secs += secs
        stt_total_cost += cost
    by_provider.sort(key=lambda x: x["seconds"], reverse=True)

    # ── 5. 모델 목록 조합 (모델별 → context_type별 세분화) ──────────────────────
    by_model = sorted(
        [
            {
                "model_name": r.model_name,
                "total_tokens": int((r.pt or 0) + (r.ct or 0)),
                "cost": round(float(r.cost or 0), 6),
                "by_context": sorted(
                    [
                        {
                            "section": ctx,  # context_type 원본 (키)
                            "group": agent_of(ctx),  # 칩 색상용 에이전트 그룹
                            "label": context_label(ctx),
                            "total_tokens": v["total_tokens"],
                            "cost": round(v["cost"], 6),
                        }
                        for ctx, v in by_mc.get(r.model_name, {}).items()
                    ],
                    key=lambda x: x["total_tokens"],
                    reverse=True,
                ),
            }
            for r in model_rows
        ],
        key=lambda x: x["total_tokens"],
        reverse=True,
    )

    # ── 6. 에이전트(그룹)별 합계 — supervisor/서브에이전트 구분 요약 ──────────────
    by_agent_list = sorted(
        [
            {
                "key": k,
                "label": agent_label(k),
                "total_tokens": v["total_tokens"],
                "cost": round(v["cost"], 6),
            }
            for k, v in by_agent.items()
        ],
        key=lambda x: x["total_tokens"],
        reverse=True,
    )

    period_tokens = sum(r["total_tokens"] for r in by_model)
    period_llm_cost = round(sum(r["cost"] for r in by_model), 6)
    period_grand_cost = round(period_llm_cost + stt_total_cost, 6)

    return {
        "start_date": since.strftime("%Y-%m-%d"),
        "end_date": until.strftime("%Y-%m-%d"),
        "period_total_tokens": period_tokens,
        "period_total_cost": period_llm_cost,
        "period_grand_cost": period_grand_cost,
        "total_all_time": {
            "total_tokens": int((all_time.pt or 0) + (all_time.ct or 0))
            if all_time
            else 0,
            "cost": round(float(all_time.cost or 0), 6) if all_time else 0,
        },
        "sections": {
            "ai_model": {
                "total_tokens": period_tokens,
                "cost": period_llm_cost,
                "by_model": by_model,
                "by_agent": by_agent_list,  # 에이전트(그룹)별 합계 (P3)
            },
            "stt": {
                "total_seconds": round(stt_total_secs, 1),
                "total_minutes": round(stt_total_secs / 60.0, 2),
                "total_cost": round(stt_total_cost, 6),
                "by_provider": by_provider,
            },
        },
    }
