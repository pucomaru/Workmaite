import logging
import os
from datetime import datetime
from typing import List, Optional, cast
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from pydantic import BaseModel
from sqlalchemy.orm import Session
from openai import AsyncOpenAI
from db import models
from db import schemas
from db.database import get_db
from core.auth import get_current_user
from core.access_guard import (
    require_view_by_session,
    require_owned_edit,
    require_meeting_edit,
    meeting_id_of_session,
)
from graphdb.neo4j_sync import sync_minutes
from graphdb.neo4j_client import run_cypher

_openai = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/ai", tags=["sessions"])


def _md_to_pdf(md_text: str) -> bytes:
    import markdown
    from routers.upload import _html_to_pdf

    html_body = markdown.markdown(md_text, extensions=["tables", "nl2br"])
    return _html_to_pdf(html_body)


# ─── 회의록 저장 ──────────────────────────────────────────────────────────────


class MinutesSaveRequest(BaseModel):
    content: str  # 생성된 회의록 전체 텍스트
    content_summary: Optional[str] = None  # 요약 (없으면 content 앞 500자 사용)
    file_name: Optional[str] = None  # 저장할 파일명 (없으면 자동 생성)


@router.post(
    "/sessions/{session_id}/minutes",
    response_model=schemas.MinutesOut,
    summary="회의록 저장",
)
async def save_minutes(
    session_id: int,
    body: MinutesSaveRequest,
    background_tasks: BackgroundTasks,
    draft: bool = False,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """생성된 회의록을 PostgreSQL minutes 테이블에 저장합니다.

    draft=true(초안 자동저장): PDF/R2 업로드와 Neo4j 동기화를 건너뛰고 내용만 upsert한다 →
    생성 직후 새로고침/탭 이동에도 초안이 유지된다(확정 전까지 그래프에는 노출하지 않음).
    draft=false(확정 저장): PDF 변환→R2 업로드→Neo4j 동기화까지 수행한다.
    """
    require_view_by_session(db, current_user, session_id)
    session = (
        db.query(models.MeetingSession)
        .filter(models.MeetingSession.id == session_id)
        .first()
    )
    if not session:
        raise HTTPException(status_code=404, detail="세션을 찾을 수 없습니다.")

    # 파일명 결정 (.pdf)
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    base_name = body.file_name or f"minutes_{session_id}_{ts}"
    base_name = base_name.removesuffix(".pdf").removesuffix(".md")
    file_name = base_name + ".pdf"

    # MD → PDF 변환 후 R2 업로드 (확정 저장 시에만 — 초안은 내용만 빠르게 저장)
    r2_url: Optional[str] = None
    if not draft:
        try:
            pdf_bytes = _md_to_pdf(body.content)
            from storage.r2_storage import upload_bytes

            r2_url = upload_bytes(
                pdf_bytes,
                f"minutes/{session_id}/{file_name}",
                "application/pdf",
            )
            logger.info(
                f"[sessions/minutes] R2 업로드 완료 — session_id={session_id}, url={r2_url}"
            )
        except Exception as e:
            logger.warning(f"[sessions/minutes] PDF 변환/R2 업로드 실패 (무시): {e}")

    summary = body.content_summary or body.content[:500]

    # minutes 테이블 upsert (session_id UNIQUE)
    existing = (
        db.query(models.Minutes).filter(models.Minutes.session_id == session_id).first()
    )

    if existing:
        # 기존 회의록 덮어쓰기는 작성자 본인 또는 간사/회사관리자/시스템관리자만
        require_owned_edit(db, current_user, session.meeting_id, existing.recorder_id)
        existing.content_original = body.content
        existing.content_summary = summary
        existing.recorder_id = current_user.id
        existing.generated_at = datetime.utcnow()
        if r2_url:  # R2 업로드 실패 시 기존 file_path 보존
            existing.file_name = file_name
            existing.file_path = r2_url
        minutes = existing
    else:
        minutes = models.Minutes(
            session_id=session_id,
            content_original=body.content,
            content_summary=summary,
            file_name=file_name if r2_url else None,
            file_path=r2_url,
            recorder_id=current_user.id,
        )
        db.add(minutes)

    db.commit()
    db.refresh(minutes)

    # Neo4j 동기화 (백그라운드) — 확정 저장 시에만. 초안은 그래프에 노출하지 않는다.
    if not draft:
        background_tasks.add_task(
            sync_minutes,
            minutes_id=minutes.id,
            session_id=session_id,
            content_summary=summary,
        )

    return minutes


# ─── 회의록 조회 ──────────────────────────────────────────────────────────────


@router.get(
    "/sessions/{session_id}/minutes",
    response_model=Optional[schemas.MinutesOut],
    summary="회의록 조회",
)
def get_minutes(
    session_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """세션의 회의록을 조회합니다(없으면 200 + null). 회의체 조회 권한 필요."""
    require_view_by_session(db, current_user, session_id)
    # 회의록이 없으면 404가 아니라 200 + null — "아직 생성/저장 안 함"은 에러가 아닌 정상 빈 상태.
    # (#3 수정 후 '생성'만으론 저장 안 되므로 미저장 세션이 흔해 404 소음만 났다.)
    return (
        db.query(models.Minutes).filter(models.Minutes.session_id == session_id).first()
    )


# ─── 회의록 내용 수정 ─────────────────────────────────────────────────────────


class MinutesContentUpdate(BaseModel):
    content: str
    content_summary: Optional[str] = None


@router.patch(
    "/sessions/{session_id}/minutes",
    response_model=schemas.MinutesOut,
    summary="회의록 내용 수정",
)
async def update_minutes_content(
    session_id: int,
    body: MinutesContentUpdate,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """회의록 본문·요약을 수정합니다. 작성자 본인 또는 간사/회사관리자/시스템관리자만."""
    require_view_by_session(db, current_user, session_id)
    minutes = (
        db.query(models.Minutes).filter(models.Minutes.session_id == session_id).first()
    )
    if not minutes:
        raise HTTPException(status_code=404, detail="회의록을 찾을 수 없습니다.")
    require_owned_edit(
        db, current_user, meeting_id_of_session(db, session_id), minutes.recorder_id
    )
    minutes.content_original = body.content
    minutes.content_summary = body.content_summary or body.content[:500]
    minutes.recorder_id = current_user.id
    minutes.generated_at = datetime.utcnow()
    db.commit()
    db.refresh(minutes)
    return minutes


# ─── 회의록 삭제 ──────────────────────────────────────────────────────────────


@router.delete("/sessions/{session_id}/minutes", summary="회의록 삭제")
async def delete_minutes(
    session_id: int,
    background_tasks: BackgroundTasks,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """회의록을 PostgreSQL·Neo4j에서 삭제합니다(멱등). 작성자 본인 또는 간사/회사관리자/시스템관리자만."""
    require_view_by_session(db, current_user, session_id)
    minutes = (
        db.query(models.Minutes).filter(models.Minutes.session_id == session_id).first()
    )
    if minutes:
        require_owned_edit(
            db, current_user, meeting_id_of_session(db, session_id), minutes.recorder_id
        )
        _mid = minutes.id
        db.delete(minutes)
        db.commit()
        # Neo4j Minutes 노드도 pg_id로 제거 (PG만 지우면 그래프에 orphan으로 남음)
        background_tasks.add_task(
            run_cypher,
            "MATCH (mn:Minutes {pg_id: $pg_id}) DETACH DELETE mn",
            {"pg_id": _mid},
        )
    # PG 행 유무와 무관하게, 세션의 Minutes 노드(과거 orphan·pg_id 불일치 잔재 포함)를 그래프에서
    # 함께 정리한다 → "삭제 OK인데 아카이브 그래프에 남아있음"을 방지(견고한 삭제).
    # Minutes 노드는 sync 시 session_id를 '속성'으로 갖는다(neo4j_sync.sync_minutes). Session 노드가
    # 없어 `기록` 관계가 안 걸린 orphan도 session_id 속성으로 잡아 지운다.
    # PG에 행이 없어도 404가 아니라 idempotent하게 성공 처리(목표 상태=없음은 이미 달성).
    background_tasks.add_task(
        run_cypher,
        "MATCH (mn:Minutes) "
        "WHERE mn.session_id = $sid OR (mn)<-[:`기록`]-(:Session {pg_id: $sid}) "
        "DETACH DELETE mn",
        {"sid": session_id},
    )
    return {"ok": True}


# ─── 대화기록 문단 정제 ────────────────────────────────────────────────────────


class RefineChunkRequest(BaseModel):
    session_id: int
    text: str
    context: Optional[str] = None
    recording_start_sec: Optional[float] = None
    recording_end_sec: Optional[float] = None


class RefineChunkResponse(BaseModel):
    title: str
    bullets: List[str]


@router.post(
    "/sessions/refine-chunk",
    response_model=RefineChunkResponse,
    summary="실시간 발화 청크 정제·요약",
)
async def refine_chunk(
    body: RefineChunkRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """회의 중 발화 원문을 LLM으로 정제해 제목·요약 블록으로 저장합니다.

    GraphRAG(보고자료·안건 맥락)를 주입해 전문용어 교정 정확도를 높인다.
    회의체 운영 행위 — 간사/회사관리자/시스템관리자만.
    """
    # 실시간 요약 블록 기록은 회의체 운영 행위 — 간사/회사관리자/시스템관리자만
    require_meeting_edit(db, current_user, meeting_id_of_session(db, body.session_id))
    session = (
        db.query(models.MeetingSession)
        .filter(models.MeetingSession.id == body.session_id)
        .first()
    )

    prev_block_titles = (
        db.query(models.SessionSummaryBlock.title)
        .filter(
            models.SessionSummaryBlock.session_id == body.session_id,
            models.SessionSummaryBlock.title.isnot(None),
        )
        .order_by(models.SessionSummaryBlock.block_index)
        .all()
    )

    agenda_titles = []
    if session:
        selected_agenda_ids = [
            row.agenda_id
            for row in db.query(models.SessionAgenda.agenda_id)
            .filter(models.SessionAgenda.session_id == body.session_id)
            .all()
        ]
        if selected_agenda_ids:
            agenda_titles = (
                db.query(models.Agenda.title)
                .filter(
                    models.Agenda.id.in_(selected_agenda_ids),
                    models.Agenda.title.isnot(None),
                )
                .order_by(models.Agenda.created_at)
                .all()
            )

    context_line = f"회의 맥락: {body.context}\n" if body.context else ""
    if agenda_titles:
        agendas = "\n".join(f"  • {row.title}" for row in agenda_titles)
        agenda_line = f"[회의 안건]\n{agendas}\n"
    else:
        agenda_line = ""
    if prev_block_titles:
        titles = "\n".join(f"  • {row.title}" for row in prev_block_titles)
        prev_line = f"[이번 회의 앞선 논의]\n{titles}\n"
    else:
        prev_line = ""
    # 보고자료-[:취급]->안건 + 추출 근거 맥락 — 전문용어 교정·요약 정확도 향상(GraphRAG)
    rag_line = ""
    if session:
        try:
            from core.meeting_context import meeting_report_agenda_context

            _ctx = meeting_report_agenda_context(db, session.meeting_id)
            if _ctx:
                rag_line = f"[관련 보고자료·안건]\n{_ctx}\n"
        except Exception:
            rag_line = ""
    prompt = f"""{context_line}{agenda_line}{prev_line}{rag_line}아래는 회의 중 발화된 원문입니다.
        다음 조건에 따라 정리해주세요:
        1. 필러워드(어, 음, 그, 아 등) 제거
        2. 오탈자 교정
        3. 핵심 내용을 나타내는 짧은 제목 1개 생성
        4. 핵심 내용을 3~5개 불릿포인트로 요약

        반드시 아래 JSON 형식으로만 응답하세요:
        {{"title": "제목", "bullets": ["• 내용1", "• 내용2", "• 내용3"]}}

        원문:
        {body.text}"""

    resp = await _openai.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"},
        temperature=0.3,
    )

    import json

    result = json.loads(cast(str, resp.choices[0].message.content))
    title = result.get("title", "")
    bullets = result.get("bullets", [])

    block_index = (
        db.query(models.SessionSummaryBlock)
        .filter(models.SessionSummaryBlock.session_id == body.session_id)
        .count()
    )
    db.add(
        models.SessionSummaryBlock(
            session_id=body.session_id,
            block_index=block_index,
            title=title,
            bullets=bullets,
            recording_start_sec=body.recording_start_sec,
            recording_end_sec=body.recording_end_sec,
        )
    )
    db.commit()

    return RefineChunkResponse(title=title, bullets=bullets)


class RefreshBlockRequest(BaseModel):
    segment_id: int


REFINE_EVERY = 5  # 프론트와 동일한 청크 크기


@router.post(
    "/sessions/{session_id}/blocks/refresh",
    summary="요약 블록 재정제",
)
async def refresh_block(
    session_id: int,
    body: RefreshBlockRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """지정 세그먼트가 속한 요약 블록을 LLM으로 다시 정제합니다.

    회의체 운영 행위 — 간사/회사관리자/시스템관리자만.
    """
    require_meeting_edit(db, current_user, meeting_id_of_session(db, session_id))

    # 세션의 모든 세그먼트를 createdAt/id 순으로 정렬
    all_segs = (
        db.query(models.SttSegment)
        .filter(models.SttSegment.session_id == session_id)
        .order_by(models.SttSegment.created_at, models.SttSegment.id)
        .all()
    )
    seg_ids = [s.id for s in all_segs]
    if body.segment_id not in seg_ids:
        return {"ok": False, "message": "segment not found"}

    seg_pos = seg_ids.index(body.segment_id)
    block_index = seg_pos // REFINE_EVERY

    block = (
        db.query(models.SessionSummaryBlock)
        .filter(
            models.SessionSummaryBlock.session_id == session_id,
            models.SessionSummaryBlock.block_index == block_index,
        )
        .first()
    )
    if not block:
        return {"ok": False, "message": "no block found"}

    # 해당 블록에 속한 세그먼트만 추출
    chunk_start = block_index * REFINE_EVERY
    chunk_end = chunk_start + REFINE_EVERY
    segs = all_segs[chunk_start:chunk_end]
    text = "\n".join(s.content for s in segs if s.content)
    if not text.strip():
        return {"ok": False, "message": "no text in block"}

    prev_block_titles = (
        db.query(models.SessionSummaryBlock.title)
        .filter(
            models.SessionSummaryBlock.session_id == session_id,
            models.SessionSummaryBlock.block_index < block.block_index,
            models.SessionSummaryBlock.title.isnot(None),
        )
        .order_by(models.SessionSummaryBlock.block_index)
        .all()
    )
    prev_line = ""
    if prev_block_titles:
        titles = "\n".join(f"  • {row.title}" for row in prev_block_titles)
        prev_line = f"[이번 회의 앞선 논의]\n{titles}\n"

    # 보고자료-[:취급]->안건 + 추출 근거 맥락 (GraphRAG) — 재정제에도 동일하게 주입
    rag_line = ""
    try:
        from core.meeting_context import meeting_report_agenda_context

        _sess = (
            db.query(models.MeetingSession)
            .filter(models.MeetingSession.id == session_id)
            .first()
        )
        if _sess:
            _ctx = meeting_report_agenda_context(db, _sess.meeting_id)
            if _ctx:
                rag_line = f"[관련 보고자료·안건]\n{_ctx}\n"
    except Exception:
        rag_line = ""

    prompt = f"""{prev_line}{rag_line}아래는 회의 중 발화된 원문입니다.
        다음 조건에 따라 정리해주세요:
        1. 필러워드(어, 음, 그, 아 등) 제거
        2. 오탈자 교정
        3. 핵심 내용을 나타내는 짧은 제목 1개 생성
        4. 핵심 내용을 3~5개 불릿포인트로 요약

        반드시 아래 JSON 형식으로만 응답하세요:
        {{"title": "제목", "bullets": ["• 내용1", "• 내용2", "• 내용3"]}}

        원문:
        {text}"""

    import json as _json

    resp = await _openai.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"},
        temperature=0.3,
    )
    result = _json.loads(cast(str, resp.choices[0].message.content))
    new_title = result.get("title", block.title)
    new_bullets = result.get("bullets", block.bullets)

    block.title = new_title
    block.bullets = new_bullets
    db.commit()

    return {
        "ok": True,
        "block_index": block.block_index,
        "title": new_title,
        "bullets": new_bullets,
        "recording_start_sec": block.recording_start_sec,
        "recording_end_sec": block.recording_end_sec,
    }
