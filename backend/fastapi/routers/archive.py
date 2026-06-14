"""아카이브 과제 추출·파일 검토·아젠다/보고서/회의록 편집 라우터 (P3A-4 — routers/supervisor.py에서 분리)."""

import json
import logging
import os
from typing import List, Optional

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    UploadFile,
)
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from db import models
from db import schemas
from core.access_guard import (
    require_meeting_member,
    require_meeting_edit,
    require_owned_edit,
    meeting_id_of_session,
)
from realtime.sse import sse_done, sse_event
from llm.agent_logging import (
    TokenUsageCollector,
    _token_collector_var,
    _create_log,
    _finalize,
)
from agents import (
    report_reviewer as report_agent,
    task_extractor as task_agent,
)
from core.auth import get_current_user
from db.database import get_db
from services.supervisor_helpers import (
    _extract_text_from_file,
    _get_meeting_context,
    _get_member_org_depts,
    _get_previous_minutes,
    _stream_plan,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/agent", tags=["agents"])


# ─── 아카이브 과제 추출 ───────────────────────────────────────────────────────
@router.post("/archive/extract-agendas")
async def archive_extract_agendas(
    meeting_id: int = Form(...),
    session_id: int | None = Form(
        None
    ),  # 출처 회의록 세션(B안) — 추출 아젠다↔회의록 연결 근거
    selected_file_ids: str = Form("[]"),
    selected_similar_docs: str = Form("[]"),
    files: List[UploadFile] = File(default=[]),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    selected_ids = json.loads(selected_file_ids) if selected_file_ids else []

    meeting = db.query(models.Meeting).filter(models.Meeting.id == meeting_id).first()
    if not meeting:
        return {"agendas": [], "error": "회의체를 찾을 수 없습니다."}

    require_meeting_edit(
        db, current_user, meeting_id
    )  # 아젠다 추출은 간사/회사관리자/시스템관리자만
    meeting_context = _get_meeting_context(db, meeting_id)
    org_dept_pairs = _get_member_org_depts(db, meeting_id)
    previous_minutes = _get_previous_minutes(db, meeting_id)[:3]

    current_agendas = (
        db.query(models.Agenda)
        .filter(
            models.Agenda.meeting_id == meeting_id,
            models.Agenda.status == "ongoing",
        )
        .order_by(models.Agenda.created_at)
        .all()
    )

    pending_todos_text = ""
    if current_agendas:
        lines = []
        for a in current_agendas:
            dept = (
                a.department[0]
                if isinstance(a.department, list) and a.department
                else a.department
            ) or "미지정"
            due = a.due_date.strftime("%Y-%m-%d") if a.due_date else "마감 미정"
            lines.append(f"- [{dept}] {a.title} (마감: {due})")
        pending_todos_text = "\n".join(lines)

    file_texts = []
    for fid in selected_ids:
        try:
            report = (
                db.query(models.Report).filter(models.Report.id == int(fid)).first()
            )
            raw = None
            if report and report.file_path:
                from storage.r2_storage import (
                    is_r2_url as _is_r2,
                    url_to_key as _r2_key,
                    download_bytes as _r2_dl,
                )

                if _is_r2(report.file_path):
                    raw = _r2_dl(_r2_key(report.file_path))
                elif os.path.exists(report.file_path):
                    with open(report.file_path, "rb") as f:
                        raw = f.read()
            if report and raw:
                text = _extract_text_from_file(raw, report.file_name or "")
                if text.strip():
                    file_texts.append(f"[보고서: {report.file_name}]\n{text[:4000]}")
        except Exception as e:
            logger.warning(f"[DB 파일 추출 오류] {e}")

    current_minutes_texts = []  # 현재 회의록 (최우선 컨텍스트)
    for upload in files:
        if not upload or not upload.filename:
            continue
        try:
            raw = await upload.read()
            text = _extract_text_from_file(raw, upload.filename.lower())
            fname = upload.filename
            if text.strip():
                # 파일명에 "회의록" 포함 시 현재 회의록으로 분리
                if "회의록" in fname or "minutes" in fname.lower():
                    current_minutes_texts.append(text[:4000])
                else:
                    file_texts.append(f"[첨부: {fname}]\n{text[:4000]}")
            else:
                file_texts.append(f"[첨부: {fname}] - 텍스트 추출 불가")
        except Exception as e:
            logger.warning(f"[업로드 파일 추출 오류] {upload.filename}: {e}")

    # 현재 회의록을 이전 회의록보다 앞에 배치 (가장 최신 = 가장 높은 우선순위)
    all_minutes = current_minutes_texts + previous_minutes

    context_parts = [f"[회의체 정보]\n{meeting_context}"]
    if meeting.guidelines:
        context_parts.append(f"[회의 지침]\n{meeting.guidelines}")
    if all_minutes:
        context_parts.append(
            "[최근 회의록]\n"
            + "\n\n".join(f"[회의록 {i + 1}]\n{m}" for i, m in enumerate(all_minutes))
        )
    if pending_todos_text:
        context_parts.append(f"[미완료 과제]\n{pending_todos_text}")
    if file_texts:
        context_parts.append("[첨부 자료]\n" + "\n\n".join(file_texts))

    org_dept_list = (
        "\n".join(
            f"- {p['company']} / {p['department']}"
            if p.get("company")
            else f"- {p['department']}"
            for p in org_dept_pairs
        )
        if org_dept_pairs
        else "정보 없음"
    )

    try:
        parsed = await task_agent.extract_agendas_from_context(
            context_parts, org_dept_list, user_id=current_user.id
        )

        # ── draft 즉시 저장 + AgentLog ────────────────────────────────────
        import uuid as _uuid
        from datetime import datetime as _dt

        agendas_raw = parsed.get("agendas", [])
        draft_ids: list[int | None] = [None] * len(agendas_raw)
        agent_log_id: int | None = None
        try:
            for idx, ag in enumerate(agendas_raw):
                title = ag.get("title", "").strip()
                if not title:
                    continue
                due_val = None
                if ag.get("due_date"):
                    try:
                        due_val = _dt.strptime(ag["due_date"], "%Y-%m-%d")
                    except Exception:
                        pass
                dept_raw = ag.get("department")
                dept_json = [dept_raw] if dept_raw and dept_raw != "null" else None
                db_agenda = models.Agenda(
                    meeting_id=meeting_id,
                    # 출처 회의록 세션 — minutes(session_id 1:1)↔agenda 조인/발제세션 근거(B안, DDL 없이).
                    session_id=session_id,
                    title=title,
                    status="draft",
                    department=dept_json,
                    due_date=due_val,
                    ai_evidence=json.dumps(
                        {
                            "reasoning": ag.get("reasoning") or "",
                            "company": ag.get("company") or ag.get("organization"),
                            "start_date": ag.get("start_date"),
                        },
                        ensure_ascii=False,
                    ),
                )
                db.add(db_agenda)
                db.flush()
                draft_ids[idx] = db_agenda.id

            agent_log = models.AgentLog(
                task_id=str(_uuid.uuid4()),
                context_type="agenda_extraction",
                meeting_id=meeting_id,
                user_id=current_user.id,
                status="success",
                input_data={
                    "selected_file_ids": selected_ids,
                    "file_count": len(file_texts),
                    "prev_minutes_count": len(previous_minutes),
                },
                output_data={
                    "agenda_count": sum(1 for d in draft_ids if d),
                    "agenda_titles": [ag.get("title") for ag in agendas_raw],
                },
                ended_at=_dt.utcnow(),
            )
            db.add(agent_log)
            db.flush()
            agent_log_id = agent_log.id
            db.commit()
            # ── draft Agenda 를 Neo4j에 즉시 동기화 (background) ────────────────────────
            try:
                import asyncio as _asyncio
                from graphdb.neo4j_sync import sync_agenda as _sync_ag

                for idx, ag_raw_id in enumerate(draft_ids):
                    if ag_raw_id:
                        _asyncio.ensure_future(
                            _sync_ag(
                                agenda_id=ag_raw_id,
                                meeting_id=meeting_id,
                                title=agendas_raw[idx].get("title", ""),
                                status="draft",
                            )
                        )
            except Exception as _se:
                logger.warning(f"[extract-agendas] Neo4j draft sync 실패: {_se}")
        except Exception as e:
            db.rollback()
            logger.warning(f"[archive/extract-agendas] draft 저장 실패: {e}")

        # ── 컨텍스트 파일 pending → approved ─────────────────────────
        try:
            for fid in selected_ids:
                report = (
                    db.query(models.Report)
                    .filter(
                        models.Report.id == int(fid),
                        models.Report.human_status == "pending",
                    )
                    .first()
                )
                if report:
                    report.human_status = "approved"
            db.commit()
        except Exception as _e:
            logger.warning(f"[extract-agendas] 파일 상태 업데이트 실패: {_e}")

        return {
            "agent_log_id": agent_log_id,
            "agendas": [
                {
                    "title": ag.get("title", ""),
                    "company": ag.get("company") or ag.get("organization"),
                    "department": ag.get("department"),
                    "start_date": ag.get("start_date"),
                    "due_date": ag.get("due_date"),
                    "db_id": draft_ids[idx],
                    "_state": None,
                    "_editing": False,
                }
                for idx, ag in enumerate(agendas_raw)
            ],
            "context_used": {
                "minutes_count": len(previous_minutes),
                "current_agendas_count": len(current_agendas),
                "files_count": len(file_texts),
            },
        }
    except Exception as e:
        logger.error(f"[archive/extract-agendas 오류] {e}")
        return {"agendas": [], "error": f"AI 분석 중 오류: {str(e)}"}


# ─── 아카이브 채팅 기반 과제 업데이트 ────────────────────────────────────────
@router.post("/archive/chat-extract")
async def archive_chat_extract(
    data: schemas.AgentChatRequest,
    background_tasks: BackgroundTasks,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    meeting_id = data.meeting_id
    message = data.message or ""
    current_agendas = (
        data.chat_history[0].get("agendas", []) if data.chat_history else []
    )

    meeting_context = _get_meeting_context(db, meeting_id) if meeting_id else ""
    org_dept_pairs = _get_member_org_depts(db, meeting_id) if meeting_id else []
    org_dept_list = (
        "\n".join(
            f"- {p['company']} / {p['department']}"
            if p.get("company")
            else f"- {p['department']}"
            for p in org_dept_pairs
        )
        if org_dept_pairs
        else "정보 없음"
    )
    current_agendas_text = (
        json.dumps(current_agendas, ensure_ascii=False, indent=2)
        if current_agendas
        else "없음"
    )

    async def stream():
        _collector = TokenUsageCollector()
        _tok_ctx_token = _token_collector_var.set(_collector)
        _log_id = _create_log(
            context_type="agenda_extraction",
            meeting_id=meeting_id or None,
            session_id=None,
            user_id=current_user.id,
            input_data={"message": message[:300]},
        )
        _stream_error: BaseException | None = None
        try:
            cnt = len(current_agendas)
            # LLM이 요청 내용을 보고 처리 계획을 스스로 서술
            _plan_sys = (
                "업무 과제 관리 AI입니다. 사용자 요청을 바탕으로 과제 목록을 어떻게 처리할지 "
                "한국어로 2~3단계를 간결하게 나열하세요. 각 단계는 짧은 한 문장, 번호·기호 없이."
            )
            _plan_hmn = f"현재 과제 {cnt}건. 사용자 요청: {message[:300]}"
            async for _step in _stream_plan(_plan_sys, _plan_hmn):
                yield sse_event("planning", f"{_step}")

            parsed = await task_agent.chat_update_agendas(
                message, meeting_context, org_dept_list, current_agendas_text
            )
            if not parsed:
                parsed = {"agendas": current_agendas, "message": message}

            agendas = parsed.get("agendas", current_agendas)
            result = {
                "agendas": [
                    {
                        "title": ag.get("title", ""),
                        "company": ag.get("company") or ag.get("organization"),
                        "department": ag.get("department"),
                        "priority": ag.get("priority", "normal"),
                        "start_date": ag.get("start_date"),
                        "due_date": ag.get("due_date"),
                        "_state": None,
                        "_editing": False,
                    }
                    for ag in agendas
                ],
                "reply": parsed.get("message", "과제 목록을 업데이트했습니다."),
            }
            yield sse_event("result", result)
        except Exception as e:
            _stream_error = e
            logger.warning(f"[chat-extract] 오류: {e}")
            fallback = {"agendas": current_agendas, "reply": f"오류: {str(e)}"}
            yield sse_event("result", fallback)
        except BaseException as _e:
            _stream_error = _e
            raise
        finally:
            _token_collector_var.reset(_tok_ctx_token)
            _finalize(_log_id, _collector, _stream_error, None)
        yield sse_done()

    return StreamingResponse(stream(), media_type="text/event-stream")


# ─── 아카이브 파일 AI 검토 ────────────────────────────────────────────────────
@router.post("/archive/analyze-file")
async def analyze_archive_file(
    file: Optional[UploadFile] = File(None),
    file_name: str = Form(""),
    file_type: str = Form(""),
    dept_name: str = Form(""),
    graph_context: str = Form(""),
    candidate_agendas: str = Form("[]"),
    meeting_id: Optional[int] = Form(None),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # 후보 과제(JSON 문자열) 파싱
    try:
        candidate_list = json.loads(candidate_agendas) if candidate_agendas else []
    except Exception:
        candidate_list = []
    if not isinstance(candidate_list, list):
        candidate_list = []

    # 첨부 파일에서 실제 텍스트 추출 (PDF/DOCX/XLSX/텍스트)
    file_content = ""
    if file is not None:
        try:
            raw = await file.read()
            extracted = _extract_text_from_file(
                raw, (file.filename or file_name or "").lower()
            )
            extracted_clean = (extracted or "").strip()
            if len(extracted_clean) > 8000:
                file_content = extracted_clean[:4000] + "\n...(중략)...\n" + extracted_clean[-4000:]
            else:
                file_content = extracted_clean
            if not file_content:
                file_content = "[파일에서 텍스트를 추출하지 못했습니다 — 이미지 기반 PDF일 수 있음]"
        except Exception as e:
            logger.warning(f"[analyze-file] 텍스트 추출 실패: {e}")
            file_content = f"[파일 추출 오류: {e}]"
    else:
        file_content = "[파일 미첨부 — 이름만 입력됨]"

    # LangGraph 기반 아카이브 파일 검토 에이전트 실행
    try:
        return await report_agent.analyze_archive_file(
            file_name=file_name,
            file_type=file_type,
            dept_name=dept_name,
            file_content=file_content,
            graph_context=graph_context,
            candidate_agendas=candidate_list,
            user_id=current_user.id if current_user else None,
            meeting_id=meeting_id,
        )
    except Exception as e:
        logger.warning(f"[analyze-file] LangGraph 검토 실패: {e}")
        return {
            "score": 0,
            "detail_scores": {},
            "feedback": [f"AI 분석 중 오류: {str(e)}", "수동으로 검토해 주세요."],
            "matched_agendas": [],
            "agendas": [
                {"content": f"{file_name} 관련 안건 검토", "department": dept_name}
            ],
            "related_depts": [],
        }


# ─── 아카이브 파일 AI 검토 (스트리밍) ─────────────────────────────────────────
@router.post("/archive/analyze-file/stream")
async def analyze_archive_file_stream_ep(
    file: Optional[UploadFile] = File(None),
    file_name: str = Form(""),
    file_type: str = Form(""),
    dept_name: str = Form(""),
    graph_context: str = Form(""),
    candidate_agendas: str = Form("[]"),
    meeting_id: Optional[int] = Form(None),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # 후보 과제(JSON 문자열) 파싱
    try:
        candidate_list = json.loads(candidate_agendas) if candidate_agendas else []
    except Exception:
        candidate_list = []
    if not isinstance(candidate_list, list):
        candidate_list = []

    # 첨부 파일에서 실제 텍스트 추출 (요청 컨텍스트 내에서 먼저 읽어둠)
    file_content = ""
    if file is not None:
        try:
            raw = await file.read()
            extracted = _extract_text_from_file(
                raw, (file.filename or file_name or "").lower()
            )
            extracted_clean = (extracted or "").strip()
            if len(extracted_clean) > 8000:
                file_content = extracted_clean[:4000] + "\n...(중략)...\n" + extracted_clean[-4000:]
            else:
                file_content = extracted_clean
            if not file_content:
                file_content = "[파일에서 텍스트를 추출하지 못했습니다 — 이미지 기반 PDF일 수 있음]"
        except Exception as e:
            logger.warning(f"[analyze-file/stream] 텍스트 추출 실패: {e}")
            file_content = f"[파일 추출 오류: {e}]"
    else:
        file_content = "[파일 미첨부 — 이름만 입력됨]"

    async def stream():
        from core.service_guards import single_flight  # 사용자당 동시 1개 분석 (P3C-4)

        try:
            async with single_flight(current_user.id):
                async for event in report_agent.analyze_archive_file_stream(
                    file_name=file_name,
                    file_type=file_type,
                    dept_name=dept_name,
                    file_content=file_content,
                    graph_context=graph_context,
                    candidate_agendas=candidate_list,
                    user_id=current_user.id if current_user else None,
                    meeting_id=meeting_id,
                ):
                    yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        except HTTPException as he:
            yield f"data: {json.dumps({'type': 'error', 'data': {'message': he.detail}}, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"
            return
        except Exception as e:
            logger.warning(f"[analyze-file/stream] 검토 실패: {e}")
            err = {
                "type": "result",
                "data": {
                    "score": 0,
                    "detail_scores": {},
                    "feedback": [
                        f"AI 분석 중 오류: {str(e)}",
                        "수동으로 검토해 주세요.",
                    ],
                    "matched_agendas": [],
                    "agendas": [
                        {
                            "content": f"{file_name} 관련 안건 검토",
                            "department": dept_name,
                        }
                    ],
                    "related_depts": [],
                },
            }
            yield f"data: {json.dumps(err, ensure_ascii=False)}\n\n"
        # 이 라우트는 streamPostForm(JSON 이벤트 파서)이 소비 — v1 [DONE] 유지 (v2 전환은 파서와 함께)
        yield "data: [DONE]\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream")


# ─── 아젠다 commit (승인→ongoing 업데이트 / 반려→삭제) ────────────────────────
async def _compose_next_agenda_lines(titles: list[str]) -> list[str]:
    """다음 회의 안건 제목들을 회의록 본문에 넣을 자연스러운 한 줄 문장으로 다듬는다(LLM)."""
    import re as _re
    from llm.llm_factory import llm_factory
    from langchain_core.messages import SystemMessage, HumanMessage

    titles = [t for t in titles if t]
    if not titles:
        return []
    sys = (
        "당신은 회의록 작성 보조 AI입니다. 주어진 '다음 회의 안건' 제목들을 회의록의 "
        "'다음 회의 아젠다' 항목으로 자연스러운 한 문장씩으로 다듬으세요. "
        "각 항목은 명사형(예: '~ 검토', '~ 방안 논의')으로 간결하게. "
        "출력은 항목별 한 줄, 번호·기호·마크다운 없이 줄바꿈으로만 구분하세요."
    )
    human = "다음 회의 안건 제목:\n" + "\n".join(f"- {t}" for t in titles)
    try:
        llm = llm_factory("extract", temperature=0.3)
        resp = await llm.ainvoke(
            [SystemMessage(content=sys), HumanMessage(content=human)]
        )
        text = resp.content if isinstance(resp.content, str) else str(resp.content)
        lines = [
            _re.sub(r"^[\-\*\d\.\)\s]+", "", ln).strip()
            for ln in text.splitlines()
            if ln.strip()
        ]
        lines = [ln for ln in lines if ln]
        return lines or titles
    except Exception as e:
        logger.warning(f"[commit] 다음 안건 문장 구성 실패, 제목 그대로 사용: {e}")
        return titles


async def _update_next_agenda_section(
    db: Session, session_id: int, titles: list[str]
) -> None:
    """출처 회의록(content_original)의 '다음 회의 아젠다' 섹션을 저장된 안건으로 갱신한다.

    본문이 HTML(에디터 저장)인지 마크다운(생성 직후)인지 감지해 같은 형식으로 섹션을 재작성한다.
    기존 '다음 회의 아젠다' 섹션은 제거 후 새로 추가해 중복을 막는다.
    """
    import re as _re

    mn = (
        db.query(models.Minutes)
        .filter(models.Minutes.session_id == session_id)
        .first()
    )
    if not mn or not mn.content_original:
        return
    lines = await _compose_next_agenda_lines(titles)
    if not lines:
        return
    content = mn.content_original
    is_html = bool(_re.search(r"<(p|h[1-6]|ul|ol|div|br)\b", content, _re.IGNORECASE))

    if is_html:
        def _esc(s: str) -> str:
            return (
                s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            )

        items = "".join(f"<li>{_esc(ln)}</li>" for ln in lines)
        section = (
            '<h2 data-next-agenda="1">다음 회의 아젠다</h2>'
            f'<ul data-next-agenda="1">{items}</ul>'
        )
        # 이전에 자동 삽입한 블록 제거
        content = _re.sub(
            r'<h2 data-next-agenda="1">.*?</ul>',
            "",
            content,
            flags=_re.DOTALL,
        )
        new_content = content.rstrip() + section
    else:
        items = "\n".join(f"- {ln}" for ln in lines)
        section = f"\n\n## 다음 회의 아젠다\n{items}\n"
        # 기존 '## N. 다음 회의 아젠다' 섹션 제거 (다음 헤딩 전까지)
        content = _re.sub(
            r"\n#{1,3}\s*\d*\.?\s*다음 회의 아젠다.*?(?=\n#{1,3}\s|\Z)",
            "",
            content,
            flags=_re.DOTALL,
        )
        new_content = content.rstrip() + section

    mn.content_original = new_content
    db.commit()


@router.post("/archive/agendas/commit")
async def commit_draft_agendas(
    data: dict,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    import uuid as _uuid
    from datetime import datetime as _dt

    meeting_id: int = data.get("meeting_id", 0)
    if meeting_id:
        require_meeting_edit(db, current_user, meeting_id)
    approved: list = data.get("approved", [])
    from core.service_guards import idempotency_guard

    _ids = sorted(
        str(a.get("db_id"))
        if a.get("db_id") is not None
        else f"new:{a.get('title', '')[:60]}"
        for a in approved
        if isinstance(a, dict)
    )
    idempotency_guard(
        f"agenda-commit:{meeting_id}:{','.join(_ids)}:{sorted(data.get('rejected_ids', []))}"
    )  # P3C-2   # [{db_id, assignee_name, dept, due_date}]
    rejected_ids: list = data.get("rejected_ids", [])  # [int]

    # 반려된 draft 삭제
    if rejected_ids:
        db.query(models.Agenda).filter(
            models.Agenda.id.in_(rejected_ids),
            models.Agenda.status == "draft",
        ).delete(synchronize_session=False)

    # 승인된 항목 업데이트 또는 신규 생성
    updated_ids = []
    for item in approved:
        db_id = item.get("db_id")
        agenda = (
            db.query(models.Agenda).filter(models.Agenda.id == db_id).first()
            if db_id
            else None
        )

        if agenda:
            # 기존 draft 업데이트
            if item.get("title"):
                agenda.title = item["title"]
            agenda.status = "ongoing"
            if item.get("dept"):
                agenda.department = [item["dept"]]
            if item.get("due_date"):
                try:
                    agenda.due_date = _dt.strptime(item["due_date"], "%Y-%m-%d")
                except Exception:
                    pass
        else:
            # db_id 없는 신규 항목 직접 생성
            if not item.get("title") or not meeting_id:
                continue
            agenda = models.Agenda(
                meeting_id=meeting_id,
                title=item["title"],
                status="ongoing",
                department=[item["dept"]] if item.get("dept") else [],
            )
            if item.get("due_date"):
                try:
                    agenda.due_date = _dt.strptime(item["due_date"], "%Y-%m-%d")
                except Exception:
                    pass
            db.add(agenda)
            db.flush()

        updated_ids.append(agenda.id)

    # AgentLog 기록
    db.add(
        models.AgentLog(
            task_id=str(_uuid.uuid4()),
            context_type="agenda_commit",
            meeting_id=meeting_id or None,
            user_id=current_user.id,
            status="success",
            input_data={
                "approved_count": len(approved),
                "rejected_count": len(rejected_ids),
            },
            output_data={"updated_ids": updated_ids, "deleted_ids": rejected_ids},
            ended_at=_dt.utcnow(),
        )
    )
    db.commit()

    # Neo4j 동기화: 승인된 건 그래프에 추가, 반려된 건 그래프에서 삭제
    from graphdb.neo4j_sync import sync_agenda as _sync_ag, delete_agenda as _del_ag
    import json as _json

    for ag_id in updated_ids:
        ag = db.query(models.Agenda).filter(models.Agenda.id == ag_id).first()
        if ag:
            dept_str = (
                _json.dumps(ag.department, ensure_ascii=False)
                if isinstance(ag.department, (dict, list))
                else (ag.department or "")
            )
            try:
                await _sync_ag(
                    ag.id,
                    ag.meeting_id,
                    title=ag.title,
                    status=ag.status,
                    session_id=ag.session_id,  # 출처 회의록 세션 → 발제세션 엣지(minutes↔agenda 조인)
                    assignee_id=ag.assignee_id,
                    priority=ag.priority or "medium",
                    due_date=ag.due_date.isoformat() + "Z" if ag.due_date else None,
                    department=dept_str,
                    created_at=ag.created_at.isoformat() + "Z"
                    if ag.created_at
                    else None,
                )
            except Exception as e:
                logger.warning(f"[commit] Neo4j sync 실패 (agenda {ag_id}): {e}")
    for ag_id in rejected_ids:
        try:
            await _del_ag(ag_id)
        except Exception as e:
            logger.warning(f"[commit] Neo4j 삭제 실패 (agenda {ag_id}): {e}")

    # 저장된 다음 회의 아젠다를 출처 회의록 본문 '다음 회의 아젠다' 섹션에 LLM 문장으로 반영
    try:
        sess_titles: dict[int, list[str]] = {}
        for ag_id in updated_ids:
            ag = db.query(models.Agenda).filter(models.Agenda.id == ag_id).first()
            if ag and ag.session_id and ag.title:
                sess_titles.setdefault(ag.session_id, []).append(ag.title)
        for sid, titles in sess_titles.items():
            await _update_next_agenda_section(db, sid, titles)
    except Exception as e:
        logger.warning(f"[commit] 회의록 다음 안건 섹션 갱신 실패: {e}")

    return {"updated": updated_ids, "deleted": rejected_ids}


# ─── 회의체 draft 아젠다 조회 (과제추출 탭 복원용) ──────────────────────────
@router.get("/meetings/{meeting_id}/draft-agendas")
async def get_draft_agendas(
    meeting_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_meeting_member(db, current_user, meeting_id)
    agendas = (
        db.query(models.Agenda)
        .filter(models.Agenda.meeting_id == meeting_id, models.Agenda.status == "draft")
        .order_by(models.Agenda.created_at.asc())
        .all()
    )

    def _parse_ev(ev):
        if not ev:
            return {}
        try:
            return json.loads(ev)
        except Exception:
            return {}

    return [
        {
            "db_id": a.id,
            "title": a.title,
            "department": a.department,
            "due_date": a.due_date.strftime("%Y-%m-%d") if a.due_date else None,
            "start_date": _parse_ev(a.ai_evidence).get("start_date"),
            "company": _parse_ev(a.ai_evidence).get("company")
            or _parse_ev(a.ai_evidence).get("organization"),
        }
        for a in agendas
    ]


# ─── 회의체 아젠다 목록 조회 ──────────────────────────────────────────────────
@router.get("/meetings/{meeting_id}/agendas")
async def get_meeting_agendas(
    meeting_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_meeting_member(db, current_user, meeting_id)
    agendas = (
        db.query(models.Agenda)
        .filter(models.Agenda.meeting_id == meeting_id, models.Agenda.status != "draft")
        .order_by(models.Agenda.created_at.desc())
        .all()
    )

    def _dept_str(d):
        if not d:
            return None
        return d[0] if isinstance(d, list) else str(d)

    return [
        {
            "id": a.id,
            "title": a.title,
            "content": a.title,
            "status": a.status,
            "department": a.department,
            "dept": _dept_str(a.department),
            "assignee_id": a.assignee_id,
            "due_date": a.due_date.strftime("%Y-%m-%d") if a.due_date else None,
            "ai_evidence": a.ai_evidence,
            "created_at": a.created_at.isoformat() + "Z" if a.created_at else None,
        }
        for a in agendas
    ]


# ─── 아젠다 상세 수정 (제목/부서/마감일/우선순위) ───────────────────────────
@router.patch("/archive/agendas/{agenda_id}")
async def update_agenda(
    agenda_id: int,
    data: dict,
    background_tasks: BackgroundTasks,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    agenda = db.query(models.Agenda).filter(models.Agenda.id == agenda_id).first()
    if not agenda:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Agenda not found")
    require_owned_edit(db, current_user, agenda.meeting_id, agenda.assignee_id)
    if "title" in data and data["title"] is not None:
        agenda.title = data["title"]
    if "department" in data:
        raw_dept = data["department"]
        agenda.department = [raw_dept] if raw_dept else None
    if "due_date" in data:
        if data["due_date"]:
            from datetime import datetime as _dt

            try:
                agenda.due_date = _dt.strptime(data["due_date"][:10], "%Y-%m-%d")
            except Exception:
                pass
        else:
            agenda.due_date = None
    if "priority" in data and data["priority"] is not None:
        agenda.priority = data["priority"]
    if "status" in data and data["status"] is not None:
        agenda.status = data["status"]
    db.commit()
    db.refresh(agenda)
    # Neo4j 동기화
    from graphdb.neo4j_sync import sync_agenda as _sync_ag

    dept_str = (
        agenda.department[0]
        if isinstance(agenda.department, list) and agenda.department
        else (agenda.department or "")
    )
    background_tasks.add_task(
        _sync_ag,
        agenda_id=agenda.id,
        meeting_id=agenda.meeting_id,
        title=agenda.title,
        status=agenda.status or "ongoing",
        session_id=agenda.session_id,  # 출처 회의록 세션 유지(발제세션 엣지)
        priority=agenda.priority or "medium",
        due_date=agenda.due_date.isoformat() if agenda.due_date else None,
        department=dept_str,
    )
    return {
        "ok": True,
        "id": agenda.id,
        "title": agenda.title,
        "department": agenda.department,
        "due_date": agenda.due_date.isoformat() if agenda.due_date else None,
        "priority": agenda.priority,
        "status": agenda.status,
    }


# ─── 아젠다 상태 변경 (완료/진행 등) ─────────────────────────────────────────
@router.patch("/archive/agendas/{agenda_id}/status")
async def update_agenda_status(
    agenda_id: int,
    data: dict,
    background_tasks: BackgroundTasks,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    agenda = db.query(models.Agenda).filter(models.Agenda.id == agenda_id).first()
    if not agenda:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Agenda not found")
    require_owned_edit(db, current_user, agenda.meeting_id, agenda.assignee_id)
    new_status = data.get("status", "done")
    agenda.status = new_status
    db.commit()
    db.refresh(agenda)
    from graphdb.neo4j_sync import sync_agenda as _sync_ag

    dept_str = (
        agenda.department[0]
        if isinstance(agenda.department, list) and agenda.department
        else (agenda.department or "")
    )
    background_tasks.add_task(
        _sync_ag,
        agenda_id=agenda.id,
        meeting_id=agenda.meeting_id,
        title=agenda.title,
        status=new_status,
        priority=agenda.priority or "medium",
        due_date=agenda.due_date.isoformat() if agenda.due_date else None,
        department=dept_str,
    )
    return {"ok": True, "status": new_status}


# ─── 보고자료 편집 ────────────────────────────────────────────────────────────
@router.patch("/archive/reports/{report_id}")
async def update_report(
    report_id: int,
    data: dict,
    background_tasks: BackgroundTasks,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    from fastapi import HTTPException

    report = db.query(models.Report).filter(models.Report.id == report_id).first()
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    require_owned_edit(db, current_user, report.meeting_id, report.upload_id)
    if "file_name" in data and data["file_name"] is not None:
        report.file_name = data["file_name"]
    if "submitter_department" in data and data["submitter_department"] is not None:
        report.submitter_department = data["submitter_department"]
    if "human_status" in data and data["human_status"] is not None:
        report.human_status = data["human_status"]
    db.commit()
    db.refresh(report)
    from graphdb.neo4j_sync import sync_report as _sync_rp

    background_tasks.add_task(
        _sync_rp,
        report_id=report.id,
        meeting_id=report.meeting_id,
        file_name=report.file_name,
        file_path=report.file_path,
        submitter_department=report.submitter_department,
        human_status=report.human_status,
        related_agenda_ids=report.related_agenda_ids or [],
    )
    return {
        "ok": True,
        "id": report.id,
        "file_name": report.file_name,
        "submitter_department": report.submitter_department,
        "human_status": report.human_status,
    }


# ─── 회의록 편집 (session_id 기반 lookup) ────────────────────────────────────
@router.patch("/archive/minutes/by-session/{session_id}")
async def update_minutes_by_session(
    session_id: int,
    data: dict,
    background_tasks: BackgroundTasks,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    from fastapi import HTTPException

    minutes = (
        db.query(models.Minutes).filter(models.Minutes.session_id == session_id).first()
    )
    if not minutes:
        raise HTTPException(status_code=404, detail="Minutes not found for session")
    require_owned_edit(
        db, current_user, meeting_id_of_session(db, session_id), minutes.recorder_id
    )
    if "file_name" in data and data["file_name"] is not None:
        minutes.file_name = data["file_name"]
    if "status" in data and data["status"] is not None:
        minutes.status = data["status"]
    db.commit()
    db.refresh(minutes)
    from graphdb.neo4j_sync import sync_minutes as _sync_mn

    background_tasks.add_task(
        _sync_mn,
        minutes_id=minutes.id,
        session_id=minutes.session_id,
        file_name=minutes.file_name,
        file_path=minutes.file_path,
        recorder_id=minutes.recorder_id,
        content_summary=minutes.content_summary,
        content_original=minutes.content_original,
        status=minutes.status,
    )
    return {
        "ok": True,
        "id": minutes.id,
        "file_name": minutes.file_name,
        "status": minutes.status,
    }


# ─── 회의록 편집 ──────────────────────────────────────────────────────────────
@router.patch("/archive/minutes/{minutes_id}")
async def update_minutes(
    minutes_id: int,
    data: dict,
    background_tasks: BackgroundTasks,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    from fastapi import HTTPException

    minutes = db.query(models.Minutes).filter(models.Minutes.id == minutes_id).first()
    if not minutes:
        raise HTTPException(status_code=404, detail="Minutes not found")
    require_owned_edit(
        db,
        current_user,
        meeting_id_of_session(db, minutes.session_id),
        minutes.recorder_id,
    )
    if "file_name" in data and data["file_name"] is not None:
        minutes.file_name = data["file_name"]
    if "status" in data and data["status"] is not None:
        minutes.status = data["status"]
    db.commit()
    db.refresh(minutes)
    from graphdb.neo4j_sync import sync_minutes as _sync_mn

    background_tasks.add_task(
        _sync_mn,
        minutes_id=minutes.id,
        session_id=minutes.session_id,
        file_name=minutes.file_name,
        file_path=minutes.file_path,
        recorder_id=minutes.recorder_id,
        content_summary=minutes.content_summary,
        content_original=minutes.content_original,
        status=minutes.status,
    )
    return {
        "ok": True,
        "id": minutes.id,
        "file_name": minutes.file_name,
        "status": minutes.status,
    }


# ─── 아젠다 삭제 ──────────────────────────────────────────────────────────────
@router.delete("/archive/agendas/{agenda_id}")
async def delete_agenda_item(
    agenda_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    agenda = db.query(models.Agenda).filter(models.Agenda.id == agenda_id).first()
    if agenda is None:
        return {"ok": True}
    require_owned_edit(db, current_user, agenda.meeting_id, agenda.assignee_id)
    meeting_id_snap = agenda.meeting_id
    title_snap = agenda.title or ""
    created_at_snap = agenda.created_at.isoformat() + "Z" if agenda.created_at else None
    db.delete(agenda)
    db.commit()
    # audit log는 별도 세션으로 — 실패해도 삭제 결과에 영향 없음
    try:
        from sqlalchemy import text as _text
        from db.database import SessionLocal as _SL
        _adb = _SL()
        try:
            _adb.execute(
                _text(
                    "INSERT INTO audit_logs (actor_id, action, entity_type, detail, ip_addr, created_at) "
                    "VALUES (:actor, 'DELETE', 'agenda', CAST(:detail AS jsonb), NULL, now())"
                ),
                {
                    "actor": current_user.id,
                    "detail": json.dumps(
                        {"log_type": "agenda_delete", "meeting_id": meeting_id_snap,
                         "agenda_id": agenda_id, "title": title_snap,
                         "agenda_created_at": created_at_snap}
                    ),
                },
            )
            _adb.commit()
        finally:
            _adb.close()
    except Exception as _e:
        logger.warning(f"[AgendaDeleteLog] 기록 실패: {_e}")
    from graphdb.neo4j_sync import delete_agenda as _del_ag

    try:
        await _del_ag(agenda_id)
    except Exception:
        pass
    return {"ok": True}


# ─── 아젠다 삭제 로그 조회 ────────────────────────────────────────────────────
@router.get("/meetings/{meeting_id}/agenda-delete-logs")
async def get_agenda_delete_logs(
    meeting_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_meeting_member(db, current_user, meeting_id)
    from sqlalchemy import text as _text
    rows = db.execute(
        _text(
            "SELECT actor_id, detail, created_at FROM audit_logs "
            "WHERE entity_type = 'agenda' "
            "AND action = 'DELETE' "
            "AND (detail->>'log_type') = 'agenda_delete' "
            "AND (detail->>'meeting_id')::int = :mid "
            "ORDER BY created_at ASC"
        ),
        {"mid": meeting_id},
    ).fetchall()
    return [
        {
            "actor_id": r.actor_id,
            "agenda_id": r.detail.get("agenda_id"),
            "title": r.detail.get("title", ""),
            "agenda_created_at": r.detail.get("agenda_created_at"),
            "deleted_at": r.created_at.isoformat() + "Z" if r.created_at else None,
        }
        for r in rows
    ]
