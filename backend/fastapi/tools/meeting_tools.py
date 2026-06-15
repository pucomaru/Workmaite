"""스코프 강제 회의체 도구 (P3B-1, AI-2·AI-3).

모든 도구는 RunnableConfig의 `user_id`/`allowed_meeting_ids`를 쿼리에 강제 주입한다
— 모델이 임의 meeting_id를 넘겨도 허용 범위 밖이면 데이터가 나가지 않는다
(모델의 선의에 의존 금지, Plan §8 원칙 2).

출력은 토큰 효율을 위해 필요한 필드만 + 상한(기본 20건)으로 자른다.
에러/거부는 모델이 복구할 수 있는 한국어 문장으로 반환한다.
"""

import logging
from typing import cast

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

from db import models
from db.database import SessionLocal

logger = logging.getLogger(__name__)

_LIMIT = 20


def _scope(config: RunnableConfig) -> tuple[int | None, set[int], bool]:
    c = (config or {}).get("configurable", {})
    return (
        c.get("user_id"),
        set(c.get("allowed_meeting_ids") or []),
        bool(c.get("is_admin", False)),
    )


def _denied(meeting_id: int) -> str:
    return (
        f"[접근 거부] meeting_id={meeting_id}는 현재 사용자의 소속 회의체가 아닙니다. "
        "list_my_meetings 도구로 접근 가능한 회의체를 먼저 확인하세요."
    )


def _check(meeting_id: int, allowed: set[int], is_admin: bool) -> bool:
    return is_admin or meeting_id in allowed


@tool
def list_my_meetings(config: RunnableConfig) -> str:
    """현재 사용자가 접근 가능한 회의체 목록(id, 제목, 상태)을 반환한다."""
    user_id, allowed, is_admin = _scope(cast(RunnableConfig, config))
    db = SessionLocal()
    try:
        q = db.query(models.Meeting)
        if not is_admin:
            if not allowed:
                return "소속된 회의체가 없습니다."
            q = q.filter(models.Meeting.id.in_(allowed))
        rows = q.order_by(models.Meeting.created_at.desc()).limit(_LIMIT).all()
        return (
            "\n".join(f"- [{m.id}] {m.title} ({m.status})" for m in rows)
            or "회의체가 없습니다."
        )
    finally:
        db.close()


@tool
def get_meeting_status(meeting_id: int, config: RunnableConfig) -> str:
    """회의체 현황 요약: 세션 수(상태별), 아젠다 수(상태별), 보고서 수(검토 상태별)."""
    _, allowed, is_admin = _scope(cast(RunnableConfig, config))
    if not _check(meeting_id, allowed, is_admin):
        return _denied(meeting_id)
    db = SessionLocal()
    try:
        m = db.query(models.Meeting).filter(models.Meeting.id == meeting_id).first()
        if not m:
            return f"meeting_id={meeting_id} 회의체를 찾을 수 없습니다."
        from sqlalchemy import func

        def _counts(model, status_col):
            rows = (
                db.query(status_col, func.count())
                .filter(model.meeting_id == meeting_id)
                .group_by(status_col)
                .all()
            )
            return ", ".join(f"{s or '?'} {c}건" for s, c in rows) or "없음"

        sessions = _counts(models.MeetingSession, models.MeetingSession.status)
        agendas = _counts(models.Agenda, models.Agenda.status)
        reports = _counts(models.Report, models.Report.human_status)
        return (
            f"[{m.title}] 상태: {m.status}\n"
            f"- 세션: {sessions}\n- 아젠다: {agendas}\n- 보고서: {reports}"
        )
    finally:
        db.close()


@tool
def list_agendas(
    meeting_id: int, status: str | None = None, config: RunnableConfig = None
) -> str:
    """회의체의 아젠다 목록(제목, 담당부서, 상태, 마감일). status로 필터 가능(draft/ongoing/done)."""
    _, allowed, is_admin = _scope(cast(RunnableConfig, config))
    if not _check(meeting_id, allowed, is_admin):
        return _denied(meeting_id)
    db = SessionLocal()
    try:
        q = db.query(models.Agenda).filter(models.Agenda.meeting_id == meeting_id)
        if status:
            q = q.filter(models.Agenda.status == status)
        rows = q.order_by(models.Agenda.created_at.desc()).limit(_LIMIT).all()
        if not rows:
            return "해당 조건의 아젠다가 없습니다."
        return "\n".join(
            f"- [{a.id}] {a.title} | {a.department or '부서미정'}"
            + (f" | 마감 {a.due_date:%Y-%m-%d}" if a.due_date else "")
            for a in rows
        )
    finally:
        db.close()


@tool
def report_submission_status(meeting_id: int, config: RunnableConfig) -> str:
    """회의체의 보고서 제출 현황(파일명, 제출 부서, 검토 상태)."""
    _, allowed, is_admin = _scope(cast(RunnableConfig, config))
    if not _check(meeting_id, allowed, is_admin):
        return _denied(meeting_id)
    db = SessionLocal()
    try:
        rows = (
            db.query(models.Report)
            .filter(models.Report.meeting_id == meeting_id)
            .order_by(models.Report.created_at.desc())
            .limit(_LIMIT)
            .all()
        )
        if not rows:
            return "제출된 보고서가 없습니다."
        return "\n".join(
            f"- {r.file_name or '이름없음'} | {r.submitter_department or '?'} | {r.human_status}"
            for r in rows
        )
    finally:
        db.close()


@tool
async def search_minutes(query: str, config: RunnableConfig) -> str:
    """과거 회의록을 의미 검색한다. 접근 가능한 회의체의 회의록만 대상."""
    _, allowed, is_admin = _scope(cast(RunnableConfig, config))
    try:
        from graphdb.retrieval_registry import (
            hybrid_search,
        )  # 벡터+풀텍스트 RRF (P3B-6 2단계)

        rows = await hybrid_search(
            "Minutes",
            query,
            k=3,
            meeting_ids=None if is_admin else list(allowed),
        )
        if not rows:
            return "관련 회의록을 찾지 못했습니다."
        return "\n\n".join(
            f"[{r.get('title') or '회의록'}] (유사도 {r['score']:.2f})\n{(r.get('summary') or r.get('content') or '')[:500]}"
            for r in rows
        )
    except Exception as e:
        logger.warning(f"[tools] search_minutes 실패: {e}")
        return f"회의록 검색 중 오류가 발생했습니다: {e}. 다른 도구를 사용하거나 질문을 바꿔보세요."


@tool
async def search_with_context(query: str, config: RunnableConfig) -> str:
    """주제로 아젠다를 찾고 연결된 세션·보고서까지 경로로 보여준다 (그래프 확장 검색, P3B-7).

    "이 아젠다가 어느 회의/보고서와 연결됐나" 같은 맥락 질문에 적합하다.
    """
    _, allowed, is_admin = _scope(cast(RunnableConfig, config))
    try:
        from graphdb.retrieval_registry import graph_expanded_search

        rows = await graph_expanded_search(
            query, meeting_ids=None if is_admin else list(allowed), k=3
        )
        if not rows:
            return "관련 아젠다를 찾지 못했습니다."
        return "\n".join(f"- {r['path']}" for r in rows)
    except Exception as e:
        logger.warning(f"[tools] search_with_context 실패: {e}")
        return f"검색 중 오류: {e}"


_TRANSCRIPT_LIMIT = 80


@tool
def get_meeting_transcript(meeting_id: int, config: RunnableConfig) -> str:
    """회의체의 가장 최근 회의(세션)에서 기록된 STT 발화(누가 무엇을 말했는지)를 순서대로 반환한다.
    "회의에서 무슨 얘기가 오갔는지 / 누가 무엇을 말했는지 / 어떤 발언이 있었는지" 류 질문에 사용한다.

    Args:
        meeting_id: 회의체 ID
    """
    _, allowed, is_admin = _scope(cast(RunnableConfig, config))
    if not _check(meeting_id, allowed, is_admin):
        return _denied(meeting_id)
    db = SessionLocal()
    try:
        sess = (
            db.query(models.MeetingSession)
            .filter(models.MeetingSession.meeting_id == meeting_id)
            .order_by(models.MeetingSession.id.desc())
            .first()
        )
        if not sess:
            return "이 회의체에는 진행된 회의(세션)가 없습니다."
        segs = (
            db.query(models.SttSegment)
            .filter(models.SttSegment.session_id == sess.id)
            .order_by(models.SttSegment.start_sec.asc())
            .limit(_TRANSCRIPT_LIMIT)
            .all()
        )
        if not segs:
            return f"'{sess.title or '최근 회의'}'의 발화(전사) 기록이 없습니다."
        body = "\n".join(f"{s.speaker_label}: {s.content}" for s in segs if s.content)
        more = " …(이하 생략)" if len(segs) >= _TRANSCRIPT_LIMIT else ""
        return f"[{sess.title or '최근 회의'} 발화 기록]\n{body}{more}"
    finally:
        db.close()


SUPERVISOR_TOOLS = [
    list_my_meetings,
    get_meeting_status,
    list_agendas,
    report_submission_status,
    search_minutes,
    search_with_context,
    get_meeting_transcript,
]
