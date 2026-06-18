"""usage.py — 토큰 / STT 사용량 조회 엔드포인트"""

import re
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
    """provider(모델명) → 라벨. 변형 모델명은 prefix 매칭."""
    if prov in _STT_LABELS:
        return _STT_LABELS[prov]
    for k, v in _STT_LABELS.items():
        if prov and prov.startswith(k):
            return v
    return prov or "STT"


# 모델명 끝의 날짜 스냅샷 접미사 (예: gpt-4o-mini-2024-07-18) 제거용 — 같은 모델의
# 버전 변형을 하나로 합쳐 보여준다(gpt-4o-mini-2024-07-18 → gpt-4o-mini).
_MODEL_DATE_RE = re.compile(r"-\d{4}-\d{2}-\d{2}$")


def _normalize_model(name: str) -> str:
    return _MODEL_DATE_RE.sub("", name) if name else name


def _is_stt_model(name: str) -> bool:
    """token_usage_logs에 기록되지만 LLM이 아니라 STT(전사/화자분리) 비용인 모델.
    (예: gpt-4o-transcribe-diarize) — AI 모델 섹션이 아니라 STT 섹션으로 분류한다."""
    n = (name or "").lower()
    return "transcribe" in n or "diarize" in n


@router.get("/tokens", summary="토큰·STT 사용량 조회")
def get_token_usage(
    start_date: Optional[str] = Query(default=None, description="시작일 (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(default=None, description="종료일 (YYYY-MM-DD)"),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """본인의 LLM 토큰·STT 사용량과 비용을 기간별·모델별·에이전트별로 집계해 반환합니다.

    모델별/context_type별 세분화와 전체 기간 누적을 함께 제공한다. 인증 필요(본인 데이터만).
    """
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

    # ── 1+2. 모델 × context_type 세분화 (모델 합계는 여기서 파생) ────────────────
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
    # 모델명은 날짜 접미사를 제거해 정규화하고, 전사/화자분리(STT) 모델은 LLM 집계에서 분리한다.
    by_mc: dict[str, dict] = {}
    by_agent: dict[str, dict] = {}
    stt_token_models: dict[str, dict] = {}  # STT(토큰 기반) — STT 섹션으로 분류
    for r in mc_rows:
        ctx = r.context_type
        tokens = int((r.pt or 0) + (r.ct or 0))
        cost = float(r.cost or 0)
        model = _normalize_model(r.model_name)
        if _is_stt_model(r.model_name):
            m = stt_token_models.setdefault(model, {"total_tokens": 0, "cost": 0.0})
            m["total_tokens"] += tokens
            m["cost"] += cost
            continue
        by_mc.setdefault(model, {}).setdefault(ctx, {"total_tokens": 0, "cost": 0.0})
        by_mc[model][ctx]["total_tokens"] += tokens
        by_mc[model][ctx]["cost"] += cost
        grp = by_agent.setdefault(agent_of(ctx), {"total_tokens": 0, "cost": 0.0})
        grp["total_tokens"] += tokens
        grp["cost"] += cost

    # ── 3. 전체 기간 누적 ──────────────────────────────────────────────────────
    # STT(전사/화자분리) 토큰 모델은 LLM 누적에서 제외 — STT 누적에 합산한다.
    _not_stt = (
        ~models.TokenUsageLog.model_name.ilike("%transcribe%"),
        ~models.TokenUsageLog.model_name.ilike("%diarize%"),
    )
    all_time = (
        db.query(
            func.sum(models.TokenUsageLog.prompt_tokens).label("pt"),
            func.sum(models.TokenUsageLog.completion_tokens).label("ct"),
            func.sum(models.TokenUsageLog.estimated_cost_usd).label("cost"),
        )
        .join(models.AgentLog, models.TokenUsageLog.agent_log_id == models.AgentLog.id)
        .filter(models.AgentLog.user_id == current_user.id, *_not_stt)
        .first()
    )
    all_time_llm_cost = float(all_time.cost or 0) if all_time else 0.0
    # STT 토큰 모델 전체 기간 누적 비용 (STT 섹션 누적에 합산)
    all_time_stt_token_cost = float(
        db.query(func.sum(models.TokenUsageLog.estimated_cost_usd))
        .join(models.AgentLog, models.TokenUsageLog.agent_log_id == models.AgentLog.id)
        .filter(
            models.AgentLog.user_id == current_user.id,
            models.TokenUsageLog.model_name.ilike("%transcribe%")
            | models.TokenUsageLog.model_name.ilike("%diarize%"),
        )
        .scalar()
        or 0.0
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
            # 수동 입력 전사(provider="manual")는 STT 사용량/비용에서 제외
            ~models.SttSegment.provider.ilike("manual"),
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
    # 토큰 기반 STT 모델(전사/화자분리, 예: gpt-4o-transcribe-diarize)을 STT 섹션에 합류.
    # 분(minute) 기반이 아니라 토큰 기반이므로 seconds/minutes는 0, tokens 필드로 표기한다.
    for model, agg in stt_token_models.items():
        by_provider.append(
            {
                "provider": model,
                "label": _stt_label(model),
                "seconds": 0,
                "minutes": 0,
                "cost_per_min": 0,
                "cost": round(agg["cost"], 6),
                "tokens": agg["total_tokens"],  # 토큰 기반 STT 사용량
            }
        )
        stt_total_cost += agg["cost"]
    by_provider.sort(key=lambda x: (x["seconds"], x.get("tokens", 0)), reverse=True)

    # ── 4-1. STT 전체 기간 누적 비용 (누적 비용에 합산) ─────────────────────────
    stt_all_time_rows = (
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
            models.SttSegment.provider.isnot(None),
            # 수동 입력 전사(provider="manual")는 STT 누적 사용량/비용에서 제외
            ~models.SttSegment.provider.ilike("manual"),
        )
        .group_by(models.SttSegment.provider)
        .all()
    )
    stt_all_time_cost = (
        sum(stt_cost(r.provider, float(r.secs or 0)) for r in stt_all_time_rows)
        + all_time_stt_token_cost
    )

    # ── 5. 모델 목록 조합 (모델별 → context_type별 세분화) ──────────────────────
    by_model = sorted(
        [
            {
                "model_name": model,
                "total_tokens": sum(v["total_tokens"] for v in ctxs.values()),
                "cost": round(sum(v["cost"] for v in ctxs.values()), 6),
                "by_context": sorted(
                    [
                        {
                            "section": ctx,  # context_type 원본 (키)
                            "group": agent_of(ctx),  # 칩 색상용 에이전트 그룹
                            "label": context_label(ctx),
                            "total_tokens": v["total_tokens"],
                            "cost": round(v["cost"], 6),
                        }
                        for ctx, v in ctxs.items()
                    ],
                    key=lambda x: x["total_tokens"],
                    reverse=True,
                ),
            }
            for model, ctxs in by_mc.items()
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
            # 누적 비용 = LLM 누적 + STT 누적 (기간 비용과 동일하게 STT 합산)
            "cost": round(all_time_llm_cost + stt_all_time_cost, 6),
            "llm_cost": round(all_time_llm_cost, 6),
            "stt_cost": round(stt_all_time_cost, 6),
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
