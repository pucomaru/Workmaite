"""upload.py — 파일 업로드 엔드포인트 (Cloudflare R2)

경로 규칙:
  reports/{meeting_id}/{uuid}_{filename}
  minutes/{session_id}/{uuid}_minutes.pdf   ← HTML→PDF 변환 후 저장
  chat/{thread_id}/{uuid}_{filename}

Ingress: /api/upload → FastAPI (workmaite-ai:8000)
"""

import logging
import re
import uuid
from typing import Optional


from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    UploadFile,
)
from sqlalchemy import text
from sqlalchemy.orm import Session

from db import models
from core.auth import get_current_user
from core.access_guard import (
    is_system_admin,
    require_view,
    require_view_by_report,
    require_view_by_session,
    require_meeting_edit,
    require_owned_edit,
    meeting_id_of_report,
)
from db.database import get_db
from storage.r2_storage import (
    generate_presigned_url,
    get_content_type,
    upload_bytes,
    url_to_key,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/upload", tags=["upload"])


def _replace_report_agendas(db, report_id: int, raw_ids) -> None:
    """report_agendas 조인 테이블 동기화 (P2-8 dual-write).

    related_agenda_ids JSONB(["agenda-174", 174, ...])와 같은 내용을 정규화 테이블에 반영한다.
    읽기 경로가 전환되면 JSONB 쪽 쓰기를 제거한다.
    """
    import re as _re

    pg_ids = set()
    for v in raw_ids or []:
        s = str(v)
        m = _re.search(r"\d+$", s)
        if m:
            pg_ids.add(int(m.group()))
    db.query(models.ReportAgenda).filter(
        models.ReportAgenda.report_id == report_id
    ).delete()
    if pg_ids:
        existing = {
            row.id
            for row in db.query(models.Agenda.id)
            .filter(models.Agenda.id.in_(pg_ids))
            .all()
        }
        for aid in pg_ids & existing:
            db.add(models.ReportAgenda(report_id=report_id, agenda_id=aid))
    db.commit()


_MAX_BYTES = 100 * 1024 * 1024  # 100 MB


def _unique_key(prefix: str, filename: str) -> tuple[str, str]:
    """중복 없는 R2 오브젝트 키와 저장용 파일명을 반환합니다."""
    safe = filename.replace(" ", "_")
    uid = uuid.uuid4().hex[:8]
    return f"{prefix}/{uid}_{safe}", f"{uid}_{safe}"


_PDF_CSS = """
@font-face {
    font-family: 'NanumGothic';
    src: local('NanumGothic'), local('Noto Sans CJK KR'), local('Apple SD Gothic Neo');
}
body {
    font-family: 'NanumGothic', 'Noto Sans CJK KR', 'Apple SD Gothic Neo', sans-serif;
    font-size: 12px; line-height: 1.7; color: #1e293b;
    padding: 40px; max-width: 820px; margin: 0 auto;
}
h1 { font-size: 20px; font-weight: 800; border-bottom: 2px solid #e2e8f0; padding-bottom: 10px; margin-bottom: 16px; }
h2 { font-size: 16px; font-weight: 700; color: #1e40af; margin-top: 20px; margin-bottom: 6px; }
h3 { font-size: 14px; font-weight: 700; color: #475569; margin-top: 12px; margin-bottom: 4px; }
p  { margin: 0 0 6px; }
ul, ol { padding-left: 20px; margin: 4px 0; }
li { margin-bottom: 2px; }
table { width: 100%; border-collapse: collapse; margin: 8px 0; font-size: 12px; }
th, td { border: 1px solid #e2e8f0; padding: 6px 10px; text-align: left; }
th { background: #f1f5f9; font-weight: 600; }
hr { border: none; border-top: 1px solid #e2e8f0; margin: 14px 0; }
"""


def _html_to_pdf(html_content: str, title: str = "회의록") -> bytes:
    """HTML 문자열을 WeasyPrint로 PDF bytes로 변환합니다."""
    from weasyprint import HTML

    logger.info(f"[PDF변환] 시작 — title={title!r}, HTML 길이={len(html_content)}자")
    full_html = (
        f"<!DOCTYPE html><html><head>"
        f'<meta charset="utf-8"><title>{title}</title>'
        f"<style>{_PDF_CSS}</style>"
        f"</head><body>{html_content}</body></html>"
    )
    pdf_bytes = HTML(string=full_html).write_pdf()
    logger.info(f"[PDF변환] 완료 — PDF 크기={len(pdf_bytes)} bytes")
    if not pdf_bytes:
        raise RuntimeError("PDF 변환 결과가 비어있습니다 (0 bytes)")
    return pdf_bytes


# ── 보고자료 업로드 ────────────────────────────────────────────────────────────


@router.get("/reports/rejected", summary="반려된 보고서 목록 조회")
async def get_rejected_reports(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """현재 사용자가 업로드한 rejected 보고서 목록을 반환합니다(본인 업로드분만)."""
    # 재제출된 항목(자식 버전이 있는 항목) 제외
    resubmitted_ids = (
        db.query(models.Report.parent_id)
        .filter(models.Report.parent_id.isnot(None))
        .subquery()
    )

    rows = (
        db.query(models.Report, models.ReportScore)
        .outerjoin(models.ReportScore, models.ReportScore.report_id == models.Report.id)
        .filter(
            models.Report.upload_id == current_user.id,
            models.Report.human_status == "rejected",
            ~models.Report.id.in_(resubmitted_ids),  # type: ignore[arg-type]
        )
        .order_by(models.Report.created_at.desc())
        .all()
    )
    return [
        {
            "id": r.id,
            "file_name": r.file_name,
            "meeting_id": r.meeting_id,
            "submitter_department": r.submitter_department,
            "version": r.version,
            "total_score": rs.total_score if rs else None,
        }
        for r, rs in rows
    ]


@router.post("/reports/{meeting_id}", summary="보고자료 업로드")
async def upload_report(
    meeting_id: int,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    dept_name: Optional[str] = Form(None),
    parent_report_id: Optional[int] = Form(None),
    related_agenda_ids: Optional[str] = Form("[]"),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """보고자료를 R2에 업로드하고 reports 테이블에 pending 상태로 저장합니다.

    회의체 조회 권한 필요. 파일 크기 상한(_MAX_BYTES)을 초과하면 413으로 거부한다.
    """
    require_view(db, current_user, meeting_id)
    content = await file.read()
    if len(content) > _MAX_BYTES:
        raise HTTPException(
            status_code=413, detail="파일 크기는 50MB를 초과할 수 없습니다."
        )

    meeting = db.query(models.Meeting).filter(models.Meeting.id == meeting_id).first()
    if not meeting:
        raise HTTPException(status_code=404, detail="회의체를 찾을 수 없습니다.")

    original_name = file.filename or "file"
    key, _ = _unique_key(f"reports/{meeting_id}", original_name)
    r2_url = upload_bytes(content, key, get_content_type(original_name))

    version = 1
    if parent_report_id:
        parent = (
            db.query(models.Report).filter(models.Report.id == parent_report_id).first()
        )
        if parent:
            version = parent.version + 1

    import json as _json

    try:
        agenda_ids = _json.loads(related_agenda_ids or "[]")
    except Exception:
        agenda_ids = []

    report = models.Report(
        meeting_id=meeting_id,
        upload_id=current_user.id,
        file_name=original_name,
        file_path=r2_url,
        human_status="pending",
        submitter_department=dept_name or current_user.department or "",
        parent_id=parent_report_id,
        version=version,
        related_agenda_ids=agenda_ids,
    )
    db.add(report)
    db.commit()
    db.refresh(report)
    _replace_report_agendas(db, report.id, agenda_ids)  # 정규화 dual-write (P2-8)

    from graphdb.file_embedder import embed_and_store as _embed_and_store

    background_tasks.add_task(
        _embed_and_store,
        r2_url,
        original_name,
        "report",
        meeting_id,
        f"report-{report.id}",
        user_id=current_user.id,  # 임베딩 사용량을 업로더에 귀속 (P2)
    )

    try:
        from graphdb.neo4j_sync import sync_report as _sync_report
        import asyncio

        asyncio.create_task(
            _sync_report(
                report_id=report.id,
                meeting_id=meeting_id,
                file_name=original_name,
                file_path=r2_url,
                submitter_department=report.submitter_department,
                human_status="pending",
                related_agenda_ids=agenda_ids,
                created_at=report.created_at.isoformat() if report.created_at else None,
            )
        )
    except Exception:
        pass

    return {
        "id": report.id,
        "file_name": original_name,
        "file_path": r2_url,
        "meeting_id": meeting_id,
    }


@router.get("/reports/{report_id}/score", summary="보고서 AI 검토 결과 조회")
async def get_report_score(
    report_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """저장된 AI 검토 결과를 조회합니다 (pending 보고서 재검토용). 회의체 조회 권한 필요."""
    require_view_by_report(db, current_user, report_id)
    report = db.query(models.Report).filter(models.Report.id == report_id).first()
    if not report:
        raise HTTPException(status_code=404, detail="보고서를 찾을 수 없습니다.")

    rs = (
        db.query(models.ReportScore)
        .filter(models.ReportScore.report_id == report_id)
        .first()
    )

    report_info = {
        "id": report.id,
        "file_name": report.file_name,
        "file_path": report.file_path,
        "human_status": report.human_status,
        "related_agenda_ids": report.related_agenda_ids or [],
    }

    # 아직 AI 검토가 없으면 빈 결과 반환 (404 대신 200)
    if not rs:
        return {
            "score": None,
            "detail_scores": {},
            "top_improvements": [],
            "feedback": [],
            "report": report_info,
        }

    feedback = rs.feedback.split("\n") if rs.feedback else []
    detail_scores = dict(rs.detail_scores or {})
    top_improvements = detail_scores.pop("_top_improvements", [])
    return {
        "score": rs.total_score,
        "detail_scores": detail_scores,
        "top_improvements": top_improvements,
        "feedback": feedback,
        "report": report_info,
    }


@router.post("/reports/{report_id}/score", summary="보고서 AI 검토 결과 저장")
async def save_report_score(
    report_id: int,
    data: dict,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """AI 검토 완료 후 report_scores 테이블에 결과를 저장합니다.

    검토(운영) 행위 — 간사/회사관리자/시스템관리자만.
    """
    require_meeting_edit(db, current_user, meeting_id_of_report(db, report_id))

    report = db.query(models.Report).filter(models.Report.id == report_id).first()
    if not report:
        raise HTTPException(status_code=404, detail="보고서를 찾을 수 없습니다.")

    feedback = data.get("feedback", [])
    feedback_text = (
        "\n".join(feedback) if isinstance(feedback, list) else (feedback or "")
    )
    detail_scores = dict(data.get("detail_scores") or {})
    top_improvements = data.get("top_improvements") or []
    if top_improvements:
        detail_scores["_top_improvements"] = top_improvements

    existing = (
        db.query(models.ReportScore)
        .filter(models.ReportScore.report_id == report_id)
        .first()
    )
    if existing:
        existing.ai_status = "success"
        existing.total_score = data.get("score")
        existing.detail_scores = detail_scores
        existing.feedback = feedback_text
    else:
        db.add(
            models.ReportScore(
                report_id=report_id,
                ai_status="success",
                total_score=data.get("score"),
                detail_scores=detail_scores,
                feedback=feedback_text,
            )
        )

    db.commit()
    return {"status": "ok"}


@router.post("/reports/{report_id}/review", summary="보고서 검토 결정 제출")
async def submit_report_review(
    report_id: int,
    data: dict,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """사람의 보고서 검토 결과(승인/반려 + 피드백)를 저장하고 연결 안건 상태를 갱신합니다.

    검토 결정(운영) 행위 — 간사/회사관리자/시스템관리자만.
    """
    require_meeting_edit(db, current_user, meeting_id_of_report(db, report_id))
    from datetime import datetime as _dt
    from sqlalchemy import desc as _desc

    report = db.query(models.Report).filter(models.Report.id == report_id).first()
    if not report:
        raise HTTPException(status_code=404, detail="보고서를 찾을 수 없습니다.")

    action = data.get("action")  # "approved" or "rejected"
    if action not in ("approved", "rejected"):
        raise HTTPException(
            status_code=400, detail="action은 approved 또는 rejected여야 합니다."
        )

    report.human_status = action

    # 최종 아젠다 연결 업데이트 (step 2에서 사용자가 선택/확정한 값)
    if "related_agenda_ids" in data:
        report.related_agenda_ids = data["related_agenda_ids"]
        _replace_report_agendas(db, report.id, data["related_agenda_ids"])  # P2-8

    # approved 시 연결된 아젠다 자동 완료 / rejected 시 done 아젠다 되돌리기
    agendas_to_sync: list = []
    agendas_to_revert: list = []
    if action == "approved":
        import re as _re

        def _parse_agenda_pg_id(v):
            s = str(v)
            if s.isdigit():
                return int(s)
            m = _re.search(r"\d+$", s)  # "agenda-5" → 5
            return int(m.group()) if m else None

        pg_ids = [
            pid
            for i in (report.related_agenda_ids or [])
            if (pid := _parse_agenda_pg_id(i)) is not None
        ]
        if pg_ids:
            agendas_to_sync = (
                db.query(models.Agenda)
                .filter(models.Agenda.id.in_(pg_ids), models.Agenda.status != "done")
                .all()
            )
            for ag in agendas_to_sync:
                ag.status = "done"

    elif action == "rejected":
        from sqlalchemy import cast as _cast
        from sqlalchemy.dialects.postgresql import JSONB as _JSONB
        import re as _re

        def _parse_agenda_pg_id(v):
            s = str(v)
            if s.isdigit():
                return int(s)
            m = _re.search(r"\d+$", s)
            return int(m.group()) if m else None

        related_ids = [
            pid
            for i in (report.related_agenda_ids or [])
            if (pid := _parse_agenda_pg_id(i)) is not None
        ]
        for ag_id in related_ids:
            still_approved = (
                db.query(models.Report)
                .filter(
                    models.Report.id != report_id,
                    models.Report.human_status == "approved",
                    _cast(models.Report.related_agenda_ids, _JSONB).op("@>")(
                        _cast([ag_id], _JSONB)
                    ),
                )
                .first()
            )
            if not still_approved:
                agenda = (
                    db.query(models.Agenda)
                    .filter(models.Agenda.id == ag_id, models.Agenda.status == "done")
                    .first()
                )
                if agenda:
                    agenda.status = "ongoing"
                    agendas_to_revert.append(agenda)

    # 가장 최근 agent_log 연결 (archive_analyze_stream)
    agent_log = (
        db.query(models.AgentLog)
        .filter(
            models.AgentLog.user_id == current_user.id,
            models.AgentLog.context_type == "archive_analyze_stream",
        )
        .order_by(_desc(models.AgentLog.created_at))
        .first()
    )

    db.add(
        models.HitlReview(
            agent_log_id=agent_log.id if agent_log else None,
            target_type="report",
            report_id=report_id,
            ai_rationale=data.get("ai_rationale", ""),
            status=action,
            reviewer_id=current_user.id,
            comment=data.get("feedback", "") or None,
            reviewed_at=_dt.utcnow(),
        )
    )

    db.commit()

    # 완료 처리된 아젠다를 Neo4j에 동기화 (그래프 노드 status 반영)
    if agendas_to_sync:
        try:
            from graphdb.neo4j_sync import sync_agenda as _sync_agenda
            import asyncio as _asyncio
            import json as _json

            for ag in agendas_to_sync:
                dept_str = ""
                if ag.department:
                    dept_str = (
                        _json.dumps(ag.department, ensure_ascii=False)
                        if isinstance(ag.department, (dict, list))
                        else str(ag.department)
                    )
                _asyncio.create_task(
                    _sync_agenda(
                        agenda_id=ag.id,
                        meeting_id=ag.meeting_id,
                        title=ag.title or "",
                        status="done",
                        assignee_id=ag.assignee_id,
                        priority=ag.priority or "medium",
                        due_date=ag.due_date.isoformat() if ag.due_date else None,
                        session_id=ag.session_id,
                        department=dept_str,
                        ai_evidence=ag.ai_evidence,
                        created_at=ag.created_at.isoformat() if ag.created_at else None,
                    )
                )
        except Exception:
            pass  # Neo4j 동기화 실패는 주요 흐름에 영향 없음

    # 반려 시 되돌린 아젠다를 Neo4j에 동기화
    if agendas_to_revert:
        try:
            from graphdb.neo4j_sync import sync_agenda as _sync_agenda
            import asyncio as _asyncio
            import json as _json

            for ag in agendas_to_revert:
                dept_str = ""
                if ag.department:
                    dept_str = (
                        _json.dumps(ag.department, ensure_ascii=False)
                        if isinstance(ag.department, (dict, list))
                        else str(ag.department)
                    )
                _asyncio.create_task(
                    _sync_agenda(
                        agenda_id=ag.id,
                        meeting_id=ag.meeting_id,
                        title=ag.title or "",
                        status="ongoing",
                        assignee_id=ag.assignee_id,
                        priority=ag.priority or "medium",
                        due_date=ag.due_date.isoformat() if ag.due_date else None,
                        session_id=ag.session_id,
                        department=dept_str,
                        ai_evidence=ag.ai_evidence,
                        created_at=ag.created_at.isoformat() if ag.created_at else None,
                    )
                )
        except Exception:
            pass

    return {"status": "ok", "action": action}


@router.delete("/reports/{report_id}", summary="보고서 삭제")
async def delete_report(
    report_id: int,
    background_tasks: BackgroundTasks,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """보고서를 R2·report_scores·hitl_reviews·reports·Neo4j에서 삭제합니다.

    업로더 본인 또는 간사/회사관리자/시스템관리자만.
    """
    require_view_by_report(db, current_user, report_id)
    report = db.query(models.Report).filter(models.Report.id == report_id).first()
    if not report:
        raise HTTPException(status_code=404, detail="보고서를 찾을 수 없습니다.")
    require_owned_edit(db, current_user, report.meeting_id, report.upload_id)

    if report.file_path:
        try:
            from storage.r2_storage import url_to_key
            import boto3
            import os

            key = url_to_key(report.file_path)
            s3 = boto3.client(
                "s3",
                endpoint_url=os.environ["R2_ENDPOINT"],
                aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
                aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
            )
            s3.delete_object(Bucket="workmaite-bucket", Key=key)
        except Exception:
            pass  # R2 삭제 실패해도 DB는 삭제

    # approved 보고서 삭제 시 연결 아젠다 되돌리기 준비
    was_approved = report.human_status == "approved"
    agenda_ids_to_check = []
    if was_approved:
        import re as _re

        def _to_pg_id(v):
            s = str(v)
            if s.isdigit():
                return int(s)
            m = _re.search(r"\d+$", s)
            return int(m.group()) if m else None

        agenda_ids_to_check = [
            pid
            for i in (report.related_agenda_ids or [])
            if (pid := _to_pg_id(i)) is not None
        ]

    # DB 삭제 (report_scores, hitl_reviews는 FK cascade 없으므로 직접 삭제)
    # 자식 버전들의 parent_id를 삭제 대상의 parent로 재연결 (체인 유지, FK 제약 위반 방지)
    db.query(models.Report).filter(models.Report.parent_id == report_id).update(
        {"parent_id": report.parent_id}
    )
    db.query(models.ReportScore).filter(
        models.ReportScore.report_id == report_id
    ).delete()
    db.query(models.HitlReview).filter(
        models.HitlReview.report_id == report_id,
    ).delete()
    db.delete(report)
    db.flush()

    # 삭제 후 approved 보고서가 없는 아젠다를 ongoing으로 되돌리기
    from sqlalchemy import cast as _cast
    from sqlalchemy.dialects.postgresql import JSONB as _JSONB

    for ag_id in agenda_ids_to_check:
        still_approved = (
            db.query(models.Report)
            .filter(
                models.Report.id != report_id,
                models.Report.human_status == "approved",
                _cast(models.Report.related_agenda_ids, _JSONB).op("@>")(
                    _cast([ag_id], _JSONB)
                ),
            )
            .first()
        )
        if not still_approved:
            db.query(models.Agenda).filter(
                models.Agenda.id == ag_id,
                models.Agenda.status == "done",
            ).update({"status": "ongoing"}, synchronize_session=False)

    db.commit()
    # Neo4j Report 노드(+청크)도 제거 — PG만 지우면 그래프에 orphan으로 남아 새로고침 시 부활한다
    from graphdb.neo4j_client import run_cypher as _run_cypher
    from graphdb.neo4j_ids import to_report_id as _to_report_id

    background_tasks.add_task(
        _run_cypher,
        "MATCH (r:Report {id: $rid}) "
        "OPTIONAL MATCH (c:ReportChunk)-[:`청크`]->(r) DETACH DELETE c, r",
        {"rid": _to_report_id(report_id)},
    )
    return {"status": "ok"}


# ── 회의록 HTML → PDF 변환 후 R2 저장 ───────────────────────────────────────


def _first_sentence_title(html: str) -> str:
    """회의록 본문(Tiptap HTML/마크다운)에서 첫 문장을 제목으로 추출한다.

    태그·마크다운 머리표를 제거하고 첫 종결부호(. ! ? 。) 또는 줄바꿈까지를 취한다.
    맨 앞이 '회의록' 같은 일반 머리글이면 다음 의미있는 문장을 사용한다. 최대 60자.
    """
    text = re.sub(r"<[^>]+>", " ", html or "")
    text = text.replace("&nbsp;", " ")
    for raw_line in re.split(r"[\r\n]+", text):
        line = re.sub(r"^[#>*\-\s]+", "", raw_line).strip()  # 마크다운 머리표 제거
        line = re.sub(r"\s+", " ", line)
        if not line or line in ("회의록", "회의록.", "# 회의록"):
            continue
        # 첫 문장만 (종결부호까지)
        m = re.match(r"^(.+?[.!?。])(\s|$)", line)
        first = (m.group(1) if m else line).strip()
        return first[:60]
    return ""


@router.post("/minutes/{session_id}", summary="회의록 PDF 저장")
async def upload_minutes(
    session_id: int,
    background_tasks: BackgroundTasks,
    content: str = Form(...),  # Tiptap 에디터 HTML
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Tiptap HTML을 PDF로 변환하여 R2에 저장하고 minutes 테이블에 upsert합니다.

    회의체 조회 권한 필요. PDF 변환 실패 시에도 회의록 내용은 저장한다.
    """
    require_view_by_session(db, current_user, session_id)
    logger.info(
        f"[minutes] 요청 — session_id={session_id}, user_id={current_user.id}, content_len={len(content)}"
    )

    session = (
        db.query(models.MeetingSession)
        .filter(models.MeetingSession.id == session_id)
        .first()
    )
    if not session:
        raise HTTPException(status_code=404, detail="세션을 찾을 수 없습니다.")

    # 저장되는 회의록 제목 = 본문 첫 문장. 없으면 세션 제목으로 폴백.
    doc_title = _first_sentence_title(content) or (
        session.title or f"회의_{session_id}"
    )
    safe_title = doc_title.replace("/", "_").replace(" ", "_")[:60]
    stored_name = f"{safe_title}.pdf"

    # HTML → PDF 변환 후 R2 업로드. 변환 실패(예: WeasyPrint 시스템 라이브러리
    # libgobject/pango 미설치 환경)에도 회의록 '내용'은 저장한다 — 작업 유실 방지.
    # (PDF 파일은 file_path=NULL로 남고, 다음 저장 시 환경이 갖춰지면 재생성된다.)
    r2_url: Optional[str] = None
    try:
        pdf_bytes = _html_to_pdf(content, session.title or f"회의록_{session_id}")
        key = f"minutes/{session_id}/{uuid.uuid4().hex[:8]}_{stored_name}"
        r2_url = upload_bytes(pdf_bytes, key, "application/pdf")
        logger.info(f"[minutes] R2 업로드 완료 — key={key}, url={r2_url}")
    except Exception as e:
        logger.error(
            f"[minutes] PDF 변환/R2 업로드 실패 — 내용만 저장 — "
            f"session_id={session_id}, error={e}",
            exc_info=True,
        )

    # ── short_summary LLM 생성 ─────────────────────────────────────
    short_summary = None
    try:
        from openai import AsyncOpenAI

        openai_client = AsyncOpenAI()
        summary_response = await openai_client.chat.completions.create(
            model="gpt-4o-mini",
            max_tokens=300,
            messages=[
                {
                    "role": "user",
                    "content": f"다음 회의록을 3~5줄로 핵심만 요약해줘. 결정사항과 액션아이템 위주로. 불릿포인트 없이 자연스러운 문장으로.\n\n{content}",
                }
            ],
        )
        short_summary = summary_response.choices[0].message.content
    except Exception as e:
        logger.warning(f"[minutes] short_summary 생성 실패 — {e}")
        short_summary = None

    # ── 파라미터 사전 확인 ──────────────────────────────────────────
    params = {
        "session_id": session_id,
        "file_name": stored_name,
        "file_path": r2_url,
        "recorder_id": current_user.id,
        "content_summary": content[:80] + "..." if len(content) > 80 else content,
    }
    logger.info(
        f"[minutes] UPSERT 파라미터 확인 — "
        f"session_id={params['session_id']!r}, "
        f"file_name={params['file_name']!r}, "
        f"file_path={params['file_path']!r}, "
        f"recorder_id={params['recorder_id']!r}"
    )

    logger.info(f"[minutes] short_summary 값 — {short_summary!r}")

    # PostgreSQL native UPSERT — 원자적으로 INSERT or UPDATE
    try:
        result = db.execute(
            text("""
            INSERT INTO minutes (session_id, file_name, file_path, recorder_id, content_summary, short_summary, status, generated_at)
            VALUES (:session_id, :file_name, :file_path, :recorder_id, :content_summary, :short_summary, 'completed', NOW())
            ON CONFLICT (session_id) DO UPDATE SET
                file_name        = EXCLUDED.file_name,
                file_path        = EXCLUDED.file_path,
                recorder_id      = EXCLUDED.recorder_id,
                content_summary  = EXCLUDED.content_summary,
                short_summary    = EXCLUDED.short_summary,
                status           = 'completed',
                generated_at     = NOW()
            RETURNING id
        """),
            {
                "session_id": session_id,
                "file_name": stored_name,
                "file_path": r2_url,
                "recorder_id": current_user.id,
                "content_summary": content,
                "short_summary": short_summary,
            },
        )

        row = result.fetchone()
        logger.info(f"[minutes] RETURNING 결과 — row={row!r} (None이면 UPSERT 미실행)")
        if row is None:
            db.rollback()
            raise HTTPException(
                status_code=500, detail="회의록 UPSERT 결과 없음 — RETURNING id가 None"
            )

        minutes_id = row[0]
        db.commit()
        logger.info(f"[minutes] commit 완료 — minutes_id={minutes_id}")
        from graphdb.neo4j_sync import sync_minutes

        background_tasks.add_task(
            sync_minutes,
            minutes_id=minutes_id,
            session_id=session_id,
            content_summary=content,
            short_summary=short_summary,
            file_name=stored_name,
            file_path=r2_url,
            status="completed",
        )

        # ── commit 후 SELECT로 실제 저장 값 검증 ──────────────────
        verify = db.execute(
            text(
                "SELECT id, session_id, file_name, file_path FROM minutes WHERE id = :id"
            ),
            {"id": minutes_id},
        ).fetchone()

        if verify is None:
            logger.error(
                f"[minutes] 저장 검증 실패 — id={minutes_id} 가 SELECT에서 조회되지 않음"
            )
            raise HTTPException(status_code=500, detail="회의록 저장 검증 실패")

        logger.info(
            f"[minutes] 저장 검증 성공 — "
            f"id={verify[0]}, session_id={verify[1]}, "
            f"file_name={verify[2]!r}, file_path={verify[3]!r}"
        )

        if verify[2] != stored_name or verify[3] != r2_url:
            logger.error(
                f"[minutes] 저장 값 불일치! "
                f"expected file_name={stored_name!r} got={verify[2]!r}, "
                f"expected file_path={r2_url!r} got={verify[3]!r}"
            )
            raise HTTPException(status_code=500, detail="회의록 저장 값 불일치")

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(
            f"[minutes] DB 저장 실패 — session_id={session_id}, error={e}",
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail=f"회의록 DB 저장 실패: {e}")

    return {
        "id": minutes_id,
        "file_name": stored_name,
        "file_path": r2_url,
        "session_id": session_id,
    }


# ── 채팅 첨부파일 업로드 ───────────────────────────────────────────────────────


@router.post("/chat", summary="채팅 첨부파일 업로드")
async def upload_chat_file(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    thread_id: str = Form(...),
    context_type: Optional[str] = Form(None),
    meeting_id: Optional[int] = Form(None),
    session_id: Optional[int] = Form(None),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """채팅 첨부파일을 R2에 업로드하고 chat_messages 테이블에 저장합니다.

    meeting_id/session_id가 있으면 해당 회의체 조회 권한 필요. 파일 크기 상한 초과 시 413.
    """
    if meeting_id:
        require_view(db, current_user, meeting_id)
    if session_id:
        require_view_by_session(db, current_user, session_id)
    content = await file.read()
    if len(content) > _MAX_BYTES:
        raise HTTPException(
            status_code=413, detail="파일 크기는 50MB를 초과할 수 없습니다."
        )

    key, stored_name = _unique_key(f"chat/{thread_id}", file.filename or "file")
    r2_url = upload_bytes(content, key, get_content_type(file.filename or ""))

    msg = models.ChatMessage(
        thread_id=thread_id,
        user_id=current_user.id,
        role="user",
        content=f"[첨부파일] {stored_name}",
        file_path=r2_url,
        file_name=stored_name,
        context_type=context_type,
        meeting_id=meeting_id,
        session_id=session_id,
    )
    db.add(msg)
    db.commit()
    db.refresh(msg)

    from graphdb.file_embedder import embed_and_store as _embed_and_store

    background_tasks.add_task(
        _embed_and_store,
        r2_url,
        stored_name,
        context_type or "document",
        meeting_id,
        f"chat-{msg.id}",
        user_id=current_user.id,  # 임베딩 사용량을 업로더에 귀속 (P2)
    )

    return {
        "id": msg.id,
        "file_name": stored_name,
        "file_path": r2_url,
        "thread_id": thread_id,
    }


# ── Presigned URL 다운로드 ────────────────────────────────────────────────────


def _authorize_presigned_access(db, current_user, file_path: str, key: str) -> None:
    """presigned 발급 전 파일 접근 권한 검증 (SEC-5).

    R2 키 프리픽스(reports/{meeting_id}, minutes/{session_id})로 소속 회의체를 해석해 조회 권한을
    확인한다. 그 외(채팅 첨부 등)는 해당 file_path를 가진 메시지의 소유자 본인 또는 회의체 조회 권한자만.
    """
    if is_system_admin(current_user):
        return
    parts = (key or "").split("/")
    if len(parts) >= 2 and parts[1].isdigit():
        if parts[0] == "reports":
            require_view(db, current_user, int(parts[1]))
            return
        if parts[0] == "minutes":
            require_view_by_session(db, current_user, int(parts[1]))
            return
    msg = (
        db.query(models.ChatMessage)
        .filter(models.ChatMessage.file_path == file_path)
        .first()
    )
    if msg:
        if msg.user_id == current_user.id:
            return
        if msg.meeting_id:
            require_view(db, current_user, msg.meeting_id)
            return
        if msg.session_id:
            require_view_by_session(db, current_user, msg.session_id)
            return
    raise HTTPException(status_code=403, detail="파일 접근 권한이 없습니다.")


@router.get("/presigned", summary="다운로드용 presigned URL 발급")
def get_presigned_url(
    file_path: str,
    expires_in: int = 3600,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """R2 file_path로 시간 제한 presigned URL을 생성합니다.

    Query params:
      file_path  : DB에 저장된 R2 URL 또는 object key
      expires_in : 유효 시간(초), 기본 1시간
    """
    if expires_in < 60 or expires_in > 86400:
        raise HTTPException(
            status_code=400, detail="expires_in은 60~86400 사이여야 합니다."
        )

    key = url_to_key(file_path)
    _authorize_presigned_access(db, current_user, file_path, key)
    try:
        url = generate_presigned_url(key, expires_in)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"presigned URL 생성 실패: {e}")

    return {"url": url, "expires_in": expires_in}
