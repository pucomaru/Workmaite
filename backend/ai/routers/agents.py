import os
from typing import List
from fastapi import APIRouter, Depends, UploadFile, File, Form, BackgroundTasks
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
import models, schemas
from database import get_db, SessionLocal
from auth import get_current_user
from agents import task_agent, knowledge_agent, minutes_agent, report_agent
from datetime import datetime
from neo4j_client import get_meeting_graph_context, graph_context_to_str, run_cypher

router = APIRouter(prefix="/api/agent", tags=["agents"])


def _log_activity(meeting_id: int, agent: str, action: str, detail: str = ""):
    """AI 에이전트 활동을 agent_logs에 기록."""
    if not meeting_id:
        return
    db = SessionLocal()
    try:
        log = models.AgentLog(
            operation=f"agent_{agent.lower()}",
            entity_type="meeting",
            entity_id=str(meeting_id),
            status="success",
            error_detail=f"[{agent}] {action}: {detail}" if detail else f"[{agent}] {action}",
        )
        db.add(log)
        db.commit()
    except Exception as e:
        print(f"[ActivityLog Error] {e}")
    finally:
        db.close()


def _get_knowledge(db: Session, meeting_id: int = None) -> List[dict]:
    """지식 베이스 조회 — 현재 비활성화 (TacitKnowledge 테이블 제거됨)."""
    return []


def _get_meeting_context(db: Session, meeting_id: int) -> str:
    """회의체 기본 맥락 문자열 구성 — Supervisor 패턴으로 서브에이전트에 주입."""
    if not meeting_id:
        return ""
    meeting = db.query(models.Meeting).filter(models.Meeting.id == meeting_id).first()
    if not meeting:
        return ""
    lines = [f"회의체 이름: {meeting.title}"]
    if meeting.purpose:
        lines.append(f"회의 목적: {meeting.purpose}")
    members = db.query(models.MeetingMember).filter(
        models.MeetingMember.meeting_id == meeting_id
    ).all()
    if members:
        member_parts = []
        for m in members:
            user = db.query(models.User).filter(models.User.id == m.user_id).first()
            if user:
                role_label = "운영자" if m.role == "admin" else "참여자"
                dept = user.department or ""
                member_parts.append(f"{user.name}({dept}, {role_label})")
        if member_parts:
            lines.append(f"참여자: {', '.join(member_parts)}")
    return "\n".join(lines)


# ─── 아라 Agent ───────────────────────────────
@router.post("/minutes/sessions-chat", summary="Minutes Sessions Chat")
async def ara_sessions_chat(
    data: schemas.AgentChatRequest,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """회의 탭 전용 아라: 전체/특정 세션 요약·질의응답."""
    # 전체 세션 목록 + 회의록 수집
    sessions = (
        db.query(models.MeetingSession)
        .filter(models.MeetingSession.meeting_id == data.meeting_id)
        .order_by(models.MeetingSession.id.desc())
        .all()
    )
    sessions_info = []
    for s in sessions:
        info = {
            "id": s.id,
            "title": s.title,
            "status": s.status,
            "summary": s.minutes.content_summary if s.minutes and s.minutes.content_summary else None,
        }
        sessions_info.append(info)

    agendas = db.query(models.Agenda).filter(
        models.Agenda.meeting_id == data.meeting_id,
    ).all()
    agendas_list = [{"content": a.title, "status": a.status} for a in agendas]

    # 세션 요약들을 previous_minutes 형태로 전달
    session_summaries = [
        f"[{s['title']}] {s['summary']}"
        for s in sessions_info if s["summary"]
    ]
    # 세션 목록 컨텍스트 (요약 없는 것 포함)
    session_list_text = "\n".join([
        f"- {s['title']} ({s['status']})" + (f": 요약 있음" if s['summary'] else ": 요약 없음")
        for s in sessions_info
    ])
    extra_context = f"[회의 세션 목록]\n{session_list_text}"
    if session_summaries:
        extra_context += f"\n\n[세션별 회의록]\n" + "\n\n".join(session_summaries)

    async def stream():
        async for chunk in minutes_agent.chat_stream(
            message=data.message,
            chat_history=data.chat_history or [],
            previous_minutes=[extra_context],
            current_agendas=agendas_list,
            meeting_context=_get_meeting_context(db, data.meeting_id),
        ):
            yield f"data: {chunk.replace(chr(10), chr(92)+chr(110))}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream")


@router.post("/minutes/generate-minutes", summary="Minutes Generate Minutes")
async def ara_generate_minutes(
    data: schemas.AgentChatRequest,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """STT 대화 기록을 받아 구조화된 회의록을 스트리밍으로 생성."""
    from datetime import datetime
    transcript = data.message or ""
    meeting_context = _get_meeting_context(db, data.meeting_id) if data.meeting_id else ""
    agendas = db.query(models.Agenda).filter(models.Agenda.meeting_id == data.meeting_id).all() if data.meeting_id else []
    agenda_text = "\n".join([f"- {a.content} ({a.status})" for a in agendas]) or "없음"
    now = datetime.now().strftime("%Y년 %m월 %d일")

    async def stream():
        async for chunk in ara.generate_minutes_stream(transcript, meeting_context, agenda_text, now):
            yield f"data: {chunk.replace(chr(10), chr(92)+chr(110))}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream")


# ─── report_agent (구 혜안) ───────────────────────────────
@router.post("/report/status", summary="Report Status")
async def hyean_status(
    data: schemas.HyeanStatusRequest,
    background_tasks: BackgroundTasks,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    meeting_status = _build_meeting_status(db, data.meeting_id)
    knowledge = _get_knowledge(db, data.meeting_id)
    background_tasks.add_task(_log_activity, data.meeting_id, "report_agent", "회의 현황 분석 요청", "")

    async def stream():
        async for chunk in report_agent.status_stream(
            meeting_status=meeting_status,
            user_role=data.user_role,
            active_knowledge=knowledge,
            user_name=current_user.name,
        ):
            yield f"data: {chunk.replace(chr(10), chr(92)+chr(110))}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream")


@router.post("/supervisor/chat")
async def supervisor_chat(
    data: schemas.AgentChatRequest,
    background_tasks: BackgroundTasks,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """워크메이트 Supervisor — 사용자 메시지를 분석해 적절한 서브에이전트에 투명하게 위임."""
    msg = data.message or ""
    msg_lower = msg.lower()

    # ── 인텐트 분류 (키워드 기반, 추후 LLM 분류로 교체 가능) ──────────────
    if any(kw in msg_lower for kw in [
        '아젠다', '의제', '과제', '할 일', '할일', '투두', 'todo', 'agenda',
        '추출', '과제 목록', '안건', '다음 회의'
    ]):
        _route = 'task_agent'
    elif any(kw in msg_lower for kw in [
        '통역', '번역', '실시간 회의', '회의 진행', '발표', '회의록 작성',
        '속기', '회의 보조'
    ]):
        _route = 'minutes_agent'
    elif any(kw in msg_lower for kw in [
        '검토', '보고서', '자료 분석', '리뷰', 'review', '문제점', '개선',
        '첨삭', '피드백', '문서 검토', '파일 검토'
    ]):
        _route = 'report_agent'
    else:
        _route = 'report_agent'

    knowledge = _get_knowledge(db, data.meeting_id)
    background_tasks.add_task(
        _log_activity, data.meeting_id, f"워크메이트[{_route}]",
        "Supervisor 대화", f'"{msg[:80]}"'
    )

    # ── 현재 사용자 접근 권한 범위 사전 확인 ────────────────────────────
    user_person_id: str | None = None
    user_allowed_mg_ids: set[str] = set()
    is_admin = (
        current_user.position in ("대표", "CEO", "임원")
    )
    try:
        p_rows = await run_cypher(
            "MATCH (p:Person) WHERE p.email = $email OR p.name = $name "
            "RETURN p.id AS pid LIMIT 1",
            {"email": current_user.email or "", "name": current_user.name or ""},
        )
        if p_rows:
            user_person_id = p_rows[0]["pid"]
            mg_access_rows = await run_cypher(
                "MATCH (p:Person {id: $pid})-[:`간사`|`구성원`]->(mg:MeetingGroup) "
                "RETURN mg.id AS mg_id",
                {"pid": user_person_id},
            )
            user_allowed_mg_ids = {r["mg_id"] for r in mg_access_rows}
    except Exception:
        pass  # Neo4j 불가 → SQLite fallback 사용

    # SQLite 기반 소속 meeting_id 집합 (fallback)
    user_sqlite_meeting_ids: set[int] = {
        mm.meeting_id
        for mm in db.query(models.MeetingMember).filter(
            models.MeetingMember.user_id == current_user.id
        ).all()
    }

    async def stream():
        # ── Neo4j 사고 과정 스트리밍 ────────────────────────────────────
        neo4j_ctx = {}
        neo4j_ctx_str = ""
        hl_candidates: list[str] = []  # AI 답변과 대조할 그래프 노드 레이블 후보
        try:
            yield f"data: [PLANNING] 질문 의도 파악 중... (라우팅: {_route})\n\n"

            if data.meeting_id:
                mid_neo4j = f"mg-{int(data.meeting_id):03d}"

                # ── 접근 권한 확인 ──
                if not is_admin:
                    if user_allowed_mg_ids:
                        has_access = mid_neo4j in user_allowed_mg_ids
                    else:
                        # Neo4j 조회 실패 시 SQLite 멤버십으로 확인
                        has_access = data.meeting_id in user_sqlite_meeting_ids
                    if not has_access:
                        yield f"data: [PLANNING] 접근 권한 없음 — {current_user.name}님은 이 회의체에 대한 접근 권한이 없습니다\n\n"
                        yield "data: 이 회의체에 대한 접근 권한이 없습니다.\n\n"
                        yield "data: [DONE]\n\n"
                        return

                yield f"data: [PLANNING] 회의체 데이터 검색 중...\n\n"
                neo4j_ctx = await get_meeting_graph_context(data.meeting_id)

                if neo4j_ctx.get("meeting", {}).get("title"):
                    mg_title = neo4j_ctx["meeting"]["title"]
                    yield f"data: [PLANNING] [{mg_title}] 회의체 정보 확인\n\n"

                if neo4j_ctx.get("agendas"):
                    count = len(neo4j_ctx["agendas"])
                    yield f"data: [PLANNING] 아젠다 {count}건 분석\n\n"

                if neo4j_ctx.get("decisions"):
                    count = len(neo4j_ctx["decisions"])
                    yield f"data: [PLANNING] 의사결정 사항 {count}건 확인\n\n"

                neo4j_ctx_str = graph_context_to_str(neo4j_ctx)

                # HL 후보 수집: 회의체/아젠다/세션/의사결정 레이블
                if neo4j_ctx.get("meeting", {}).get("title"):
                    hl_candidates.append(neo4j_ctx["meeting"]["title"])
                for ag in neo4j_ctx.get("agendas", []):
                    if ag.get("title"): hl_candidates.append(ag["title"])
                for s in neo4j_ctx.get("recent_sessions", []):
                    if s.get("title"): hl_candidates.append(s["title"])
                for dec in neo4j_ctx.get("decisions", []):
                    c = dec.get("content", "")
                    if c: hl_candidates.append(c[:30])
            else:
                yield f"data: [PLANNING] {current_user.name}님의 업무 지식 그래프 탐색 중\n\n"
                try:
                    if user_person_id:
                        # 현재 사용자의 소속 회의체만 조회
                        person_rows = await run_cypher(
                            "MATCH (p:Person {id: $pid})-[r:`구성원`|`간사`]->(mg:MeetingGroup) "
                            "RETURN p.name AS person, mg.title AS meeting, type(r) AS role",
                            {"pid": user_person_id},
                        )
                    elif is_admin:
                        person_rows = await run_cypher(
                            "MATCH (p:Person)-[r:`구성원`]->(mg:MeetingGroup) "
                            "RETURN p.name AS person, mg.title AS meeting, r.role AS role"
                        )
                    else:
                        person_rows = []
                    if person_rows:
                        yield f"data: [PLANNING] 구성원 소속 회의체 {len(person_rows)}건 확인\n\n"
                        lines = []
                        from collections import defaultdict
                        pm: dict = defaultdict(list)
                        for row in person_rows:
                            pm[row.get("person", "?")].append(row.get("meeting", "?"))
                        for person, mtgs in pm.items():
                            lines.append(f"- {person}: {', '.join(mtgs)}")
                        neo4j_ctx_str = "[구성원 소속 회의체]\n" + "\n".join(lines)
                        # HL 후보: 소속 회의체 이름
                        for row in person_rows:
                            t = row.get("meeting", "")
                            if t and t not in hl_candidates:
                                hl_candidates.append(t)
                    else:
                        org_rows = await run_cypher(
                            "MATCH (org:Organization) RETURN org.name AS name LIMIT 1"
                        )
                        if org_rows:
                            yield f"data: [PLANNING] 조직: {org_rows[0].get('name', '?')} 확인\n\n"
                except Exception:
                    pass

            yield f"data: [PLANNING] {_route} 에이전트에 위임 — 응답 생성 중...\n\n"
        except Exception as e:
            yield f"data: [PLANNING] 지식 그래프 조회 중 오류 발생\n\n"

        # ── 서브에이전트 스트리밍 ────────────────────────────────────────
        _user_scope_header = (
            f"[현재 사용자] {current_user.name}"
            + (f" / {current_user.position}" if current_user.position else "")
            + (f" / {current_user.department}" if current_user.department else "")
            + "\n[데이터 접근 범위] 본인이 소속된 회의체의 정보만 제공합니다. "
            "다른 사용자 또는 비소속 회의체의 민감 정보는 노출하지 마세요.\n"
        )

        def _enrich(base_ctx: str) -> str:
            """사용자 범위 헤더 + SQLite 컨텍스트 + Neo4j 그래프 컨텍스트를 합칩니다."""
            parts = [_user_scope_header, base_ctx]
            if neo4j_ctx_str and neo4j_ctx_str != "(Neo4j 데이터 없음)":
                parts.append(f"[Neo4j 그래프 컨텍스트]\n{neo4j_ctx_str}")
            return "\n\n".join(parts)

        if _route == 'task_agent':
            previous_minutes = _get_previous_minutes(db, data.meeting_id)
            departments = _get_member_departments(db, data.meeting_id)
            meeting_context = _enrich(_get_meeting_context(db, data.meeting_id))
            gen = task_agent.chat_stream(
                message=msg, chat_history=data.chat_history or [],
                previous_minutes=previous_minutes, knowledge=knowledge,
                departments=departments, meeting_context=meeting_context,
            )
        elif _route == 'minutes_agent':
            previous_minutes = _get_previous_minutes(db, data.meeting_id)
            agendas = db.query(models.Agenda).filter(
                models.Agenda.meeting_id == data.meeting_id,
                models.Agenda.status.in_(["ON_HOLD", "IN_PROGRESS"]),
            ).all()
            gen = minutes_agent.chat_stream(
                message=msg, chat_history=data.chat_history or [],
                previous_minutes=previous_minutes,
                current_agendas=[{'content': a.title, 'status': a.status} for a in agendas],
                meeting_context=_enrich(_get_meeting_context(db, data.meeting_id)),
            )
        elif _route == 'report_agent':
            meeting_context = _enrich(_get_meeting_context(db, data.meeting_id))
            gen = report_agent.chat_stream(
                message=msg, chat_history=data.chat_history or [],
                knowledge=knowledge, meeting_context=meeting_context,
            )
        else:  # default → report_agent (meeting status)
            member = db.query(models.MeetingMember).filter(
                models.MeetingMember.meeting_id == data.meeting_id,
                models.MeetingMember.user_id == current_user.id,
            ).first()
            meeting_status = await _build_neo4j_meeting_status(
                person_id=None if is_admin else user_person_id
            )
            if not meeting_status:
                meeting_status = _build_all_meetings_status(
                    db, user_id=None if is_admin else current_user.id
                )
            if data.meeting_id and neo4j_ctx:
                meeting_status["current_meeting"] = neo4j_ctx
            elif data.meeting_id:
                meeting_status["current_meeting"] = _build_meeting_status(db, data.meeting_id)
            gen = report_agent.status_stream(
                meeting_status=meeting_status,
                user_role=member.role if member else "presenter",
                active_knowledge=knowledge,
                chat_history=data.chat_history,
                message=msg,
                user_name=current_user.name,
                meeting_context=_enrich(_get_meeting_context(db, data.meeting_id)),
            )
        # ── LLM 응답 스트리밍 + 전체 텍스트 수집 ──────────────────────
        collected: list[str] = []
        async for chunk in gen:
            collected.append(chunk)
            yield f"data: {chunk.replace(chr(10), chr(92)+chr(110))}\n\n"

        # ── AI 기반 하이라이팅: 답변에 실제 언급된 그래프 노드 추출 ──────
        if hl_candidates and collected:
            import json as _json
            full_text = "".join(collected)
            matched = [c for c in hl_candidates if c and c in full_text]
            if matched:
                yield f"data: [HIGHLIGHT] {_json.dumps(matched, ensure_ascii=False)}\n\n"

        yield "data: [DONE]\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream")


@router.post("/report/chat", summary="Report Chat")
async def hyean_chat(
    data: schemas.AgentChatRequest,
    background_tasks: BackgroundTasks,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    member = db.query(models.MeetingMember).filter(
        models.MeetingMember.meeting_id == data.meeting_id,
        models.MeetingMember.user_id == current_user.id,
    ).first()
    user_role = member.role if member else "presenter"

    # 현재 사용자 접근 범위 확인
    is_admin_hyean = (
        current_user.position in ("대표", "CEO", "임원")
    )
    hyean_person_id: str | None = None
    try:
        p_rows = await run_cypher(
            "MATCH (p:Person) WHERE p.email = $email OR p.name = $name RETURN p.id AS pid LIMIT 1",
            {"email": current_user.email or "", "name": current_user.name or ""},
        )
        if p_rows:
            hyean_person_id = p_rows[0]["pid"]
    except Exception:
        pass

    meeting_status = await _build_neo4j_meeting_status(
        person_id=None if is_admin_hyean else hyean_person_id
    )
    if not meeting_status:
        meeting_status = _build_all_meetings_status(
            db, user_id=None if is_admin_hyean else current_user.id
        )
    if data.meeting_id:
        meeting_status["current_meeting"] = _build_meeting_status(db, data.meeting_id)
    knowledge = _get_knowledge(db, data.meeting_id)
    meeting_context = _get_meeting_context(db, data.meeting_id)
    background_tasks.add_task(_log_activity, data.meeting_id, "report_agent", "현황 대화", f'"{ data.message[:80] }"')

    async def stream():
        async for chunk in report_agent.status_stream(
            meeting_status=meeting_status,
            user_role=user_role,
            active_knowledge=knowledge,
            chat_history=data.chat_history,
            message=data.message,
            user_name=current_user.name,
            meeting_context=meeting_context,
        ):
            yield f"data: {chunk.replace(chr(10), chr(92)+chr(110))}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream")


# ─── Helpers ─────────────────────────────────
def _extract_text_from_file(raw: bytes, filename: str) -> str:
    """파일 종류에 따라 텍스트 추출."""
    import io

    # PDF
    if filename.endswith(".pdf"):
        try:
            import pdfplumber
            with pdfplumber.open(io.BytesIO(raw)) as pdf:
                pages = [p.extract_text() or "" for p in pdf.pages]
            return "\n".join(pages).strip()
        except Exception as e:
            return f"[PDF 추출 오류: {e}]"

    # DOCX
    if filename.endswith(".docx"):
        try:
            import docx as _docx
            doc = _docx.Document(io.BytesIO(raw))
            return "\n".join(p.text for p in doc.paragraphs if p.text.strip())
        except Exception as e:
            return f"[DOCX 추출 오류: {e}]"

    # XLSX
    if filename.endswith((".xlsx", ".xls")):
        try:
            import openpyxl
            wb = openpyxl.load_workbook(io.BytesIO(raw), data_only=True)
            lines = []
            for ws in wb.worksheets:
                for row in ws.iter_rows(values_only=True):
                    row_text = "\t".join(str(c) if c is not None else "" for c in row)
                    if row_text.strip():
                        lines.append(row_text)
            return "\n".join(lines)
        except Exception as e:
            return f"[XLSX 추출 오류: {e}]"

    # 텍스트 파일 (txt, csv, md 등)
    for enc in ("utf-8", "euc-kr", "cp949"):
        try:
            return raw.decode(enc)
        except Exception:
            pass

    return ""


def _get_member_departments(db: Session, meeting_id: int) -> List[str]:
    from sqlalchemy.orm import joinedload
    members = (
        db.query(models.MeetingMember)
        .options(joinedload(models.MeetingMember.user))
        .filter(models.MeetingMember.meeting_id == meeting_id)
        .all()
    )
    return list({m.user.department for m in members if m.user and m.user.department})


def _save_extracted(db: Session, meeting_id: int, result: dict):
    import json as _json

    saved_agendas = []
    existing_count = db.query(models.Agenda).filter(
        models.Agenda.meeting_id == meeting_id
    ).count()
    for idx, a in enumerate(result.get("agendas", [])):
        raw = a.get("content", "") or a.get("title", "")
        if not raw.strip():
            continue
        agenda = models.Agenda(
            meeting_id=meeting_id,
            title=raw[:255],
            content=raw if len(raw) > 255 else None,
            order_index=existing_count + idx + 1,
        )
        db.add(agenda)
        db.flush()
        saved_agendas.append({"id": agenda.id, "title": agenda.title})

    # Todo → HitlReview (target_type="extracted_item") 로 저장
    saved_reviews = []
    for t in result.get("todos", []):
        if not t.get("content", "").strip():
            continue
        review = models.HitlReview(
            meeting_id=meeting_id,
            target_type="extracted_item",
            status="PENDING",
            ai_output=_json.dumps({
                "content": t["content"],
                "department": t.get("department"),
                "due_date": t.get("due_date"),
            }, ensure_ascii=False),
        )
        db.add(review)
        db.flush()
        saved_reviews.append({"id": review.id, "content": t["content"]})

    db.commit()
    return saved_agendas, saved_reviews


def _get_previous_minutes(db: Session, meeting_id: int) -> List[str]:
    sessions = db.query(models.MeetingSession).filter(
        models.MeetingSession.meeting_id == meeting_id,
        models.MeetingSession.status == "ENDED",
    ).all()
    result = []
    for s in sessions:
        if s.minutes and s.minutes.content_summary:
            result.append(s.minutes.content_summary)
    return result


def _build_meeting_status(db: Session, meeting_id: int) -> dict:
    # meeting_id가 없으면 전체 회의체·구성원 현황 반환
    if not meeting_id:
        return _build_all_meetings_status(db)

    meeting = db.query(models.Meeting).filter(models.Meeting.id == meeting_id).first()
    agendas = db.query(models.Agenda).filter(models.Agenda.meeting_id == meeting_id).all()
    reports = db.query(models.Report).filter(models.Report.meeting_id == meeting_id).all()
    sessions = db.query(models.MeetingSession).filter(
        models.MeetingSession.meeting_id == meeting_id
    ).all()
    members = db.query(models.MeetingMember).filter(
        models.MeetingMember.meeting_id == meeting_id
    ).all()
    pending_reviews = db.query(models.HitlReview).filter(
        models.HitlReview.meeting_id == meeting_id,
        models.HitlReview.status == "PENDING",
    ).count()

    agenda_list = [
        {"content": a.title, "status": a.status}
        for a in agendas
    ]
    member_list = []
    for m in members:
        u = db.query(models.User).filter(models.User.id == m.user_id).first()
        if u:
            member_list.append({"name": u.name, "department": u.department or "", "role": m.role})

    return {
        "meeting": {"title": meeting.title if meeting else "", "purpose": meeting.purpose if meeting else ""},
        "members": member_list,
        "agendas": {
            "total": len(agendas),
            "in_progress": sum(1 for a in agendas if a.status == "IN_PROGRESS"),
            "done": sum(1 for a in agendas if a.status == "DONE"),
            "items": agenda_list,
        },
        "reports": {
            "total": len(reports),
            "submitted": sum(1 for r in reports if r.status == "SUBMITTED"),
            "approved": sum(1 for r in reports if r.status == "APPROVED"),
            "rejected": sum(1 for r in reports if r.status == "REJECTED"),
        },
        "pending_reviews": pending_reviews,
        "sessions": {"total": len(sessions), "ended": sum(1 for s in sessions if s.status == "ENDED")},
    }


def _build_all_meetings_status(db: Session, user_id: int | None = None) -> dict:
    """SQLite 기반 조직 현황. user_id가 주어지면 해당 사용자의 소속 회의체만 반환."""
    if user_id is not None:
        allowed_ids = {
            mm.meeting_id
            for mm in db.query(models.MeetingMember).filter(
                models.MeetingMember.user_id == user_id
            ).all()
        }
        meetings = db.query(models.Meeting).filter(models.Meeting.id.in_(allowed_ids)).all()
    else:
        meetings = db.query(models.Meeting).all()
    all_members = db.query(models.MeetingMember).all()
    all_users = {u.id: u for u in db.query(models.User).all()}

    # 구성원별 소속 회의체 매핑
    person_map: dict = {}
    for mm in all_members:
        u = all_users.get(mm.user_id)
        if not u:
            continue
        if u.name not in person_map:
            person_map[u.name] = {
                "name": u.name,
                "department": u.department or "",
                "position": u.position or "",
                "meetings": [],
            }
        mtg = next((m for m in meetings if m.id == mm.meeting_id), None)
        if mtg:
            person_map[u.name]["meetings"].append({
                "title": mtg.title,
                "role": mm.role,
                "purpose": mtg.purpose or "",
            })

    # 회의체별 요약
    meeting_summaries = []
    for m in meetings:
        mems = [mm for mm in all_members if mm.meeting_id == m.id]
        member_names = []
        for mm in mems:
            u = all_users.get(mm.user_id)
            if u:
                member_names.append(u.name)
        pending_reviews = db.query(models.HitlReview).filter(
            models.HitlReview.meeting_id == m.id,
            models.HitlReview.status == "PENDING",
        ).count()
        meeting_summaries.append({
            "title": m.title,
            "purpose": m.purpose or "",
            "members": member_names,
            "pending_reviews": pending_reviews,
        })

    if user_id:
        _u = db.query(models.User).filter(models.User.id == user_id).first()
        scope_label = f"{_u.name}의 소속 회의체" if _u else "소속 회의체"
    else:
        scope_label = "전체 조직"
    return {
        "scope": scope_label,
        "meetings": meeting_summaries,
        "persons": list(person_map.values()),
    }


async def _build_neo4j_meeting_status(person_id: str | None = None) -> dict:
    """Neo4j에서 조직 현황 구성 — hyean의 primary 소스.
    person_id가 주어지면 해당 Person이 소속된 회의체만 반환."""
    try:
        if person_id:
            # 해당 사용자의 소속 회의체만 조회
            mg_rows = await run_cypher(
                "MATCH (me:Person {id: $pid})-[:`간사`|`구성원`]->(mg:MeetingGroup) "
                "OPTIONAL MATCH (p:Person)-[rel:`간사`|`구성원`]->(mg) "
                "OPTIONAL MATCH (p)-[:`소속`]->(d:Department) "
                "RETURN mg.id AS mg_id, mg.title AS title, mg.purpose AS purpose, "
                "       p.name AS person_name, p.id AS person_id, "
                "       type(rel) AS rel_type, d.name AS department",
                {"pid": person_id},
            )
            agenda_rows = await run_cypher(
                "MATCH (me:Person {id: $pid})-[:`간사`|`구성원`]->(mg:MeetingGroup) "
                "MATCH (ag:Agenda)-[:`관할`]->(mg) "
                "RETURN mg.id AS mg_id, ag.title AS content, ag.status AS status, "
                "       ag.priority AS priority",
                {"pid": person_id},
            )
            person_rows = await run_cypher(
                "MATCH (me:Person {id: $pid})-[:`간사`|`구성원`]->(mg:MeetingGroup) "
                "MATCH (p:Person)-[r:`구성원`|`간사`]->(mg) "
                "RETURN p.name AS person, mg.title AS meeting, type(r) AS role",
                {"pid": person_id},
            )
            scope_label = "소속 회의체 (Neo4j)"
        else:
            # admin: 전체 조회
            mg_rows = await run_cypher(
                "MATCH (mg:MeetingGroup) "
                "OPTIONAL MATCH (p:Person)-[rel:`간사`|`구성원`]->(mg) "
                "OPTIONAL MATCH (p)-[:`소속`]->(d:Department) "
                "RETURN mg.id AS mg_id, mg.title AS title, mg.purpose AS purpose, "
                "       p.name AS person_name, p.id AS person_id, "
                "       type(rel) AS rel_type, d.name AS department"
            )
            agenda_rows = await run_cypher(
                "MATCH (ag:Agenda)-[:`관할`]->(mg:MeetingGroup) "
                "RETURN mg.id AS mg_id, ag.title AS content, ag.status AS status, "
                "       ag.priority AS priority"
            )
            person_rows = await run_cypher(
                "MATCH (p:Person)-[r:`구성원`|`간사`]->(mg:MeetingGroup) "
                "RETURN p.name AS person, mg.title AS meeting, type(r) AS role"
            )
            scope_label = "전체 조직 (Neo4j)"
    except Exception as e:
        return {}  # Neo4j 불가 시 빈 dict 반환 → caller에서 fallback

    # 회의체별 빌드
    meetings_map: dict = {}
    for row in mg_rows:
        mg_id = row.get("mg_id", "")
        if mg_id not in meetings_map:
            meetings_map[mg_id] = {
                "id": mg_id,
                "title": row.get("title", ""),
                "purpose": row.get("purpose", ""),
                "members": [],
                "agendas": [],
            }
        if row.get("person_id"):
            mg = meetings_map[mg_id]
            if not any(m["name"] == row["person_name"] for m in mg["members"]):
                mg["members"].append({
                    "name": row.get("person_name", "?"),
                    "department": row.get("department") or "",
                    "role": "admin" if row.get("rel_type") == "간사" else "member",
                })
    for row in agenda_rows:
        mg_id = row.get("mg_id", "")
        if mg_id in meetings_map:
            meetings_map[mg_id]["agendas"].append({
                "content": row.get("content", ""),
                "status": row.get("status", ""),
                "priority": row.get("priority", ""),
            })

    # 구성원별 소속 회의체 매핑
    from collections import defaultdict
    pm: dict = defaultdict(list)
    for row in person_rows:
        pm[row.get("person", "?")].append({
            "title": row.get("meeting", "?"),
            "role": "admin" if row.get("role") == "간사" else "member",
        })
    persons = [
        {"name": name, "meetings": mtgs}
        for name, mtgs in pm.items()
    ]

    return {
        "scope": scope_label,
        "meetings": list(meetings_map.values()),
        "persons": persons,
    }


# ─── 아카이브 과제 추출 (컨텍스트 기반) ──────────────────────────────────
@router.post("/archive/extract-agendas")
async def archive_extract_agendas(
    meeting_id: int = Form(...),
    selected_file_ids: str = Form("[]"),   # JSON 문자열
    selected_similar_docs: str = Form("[]"),
    files: List[UploadFile] = File(default=[]),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    아카이브 과제 탭에서 호출되는 AI 과제 추출 엔드포인트.
    - 회의체 기본 정보 (목적, 지침, 구성원)
    - 최근 회의록 최대 3건
    - 미완료 과제
    - 선택된 파일 (DB 저장 파일 or 새로 업로드)
    를 컨텍스트로 조합해 LLM에 전달, 구조화된 과제 목록을 반환한다.
    """
    import json as _json, os as _os, re as _re

    selected_ids = _json.loads(selected_file_ids) if selected_file_ids else []

    # ── 1. 회의체 기본 정보 ────────────────────────────────────────────
    meeting = db.query(models.Meeting).filter(models.Meeting.id == meeting_id).first()
    if not meeting:
        return {"agendas": [], "error": "회의체를 찾을 수 없습니다."}

    meeting_context = _get_meeting_context(db, meeting_id)
    departments = _get_member_departments(db, meeting_id)
    knowledge = _get_knowledge(db, meeting_id)

    # ── 2. 최근 회의록 (최대 3건) ──────────────────────────────────────
    previous_minutes = _get_previous_minutes(db, meeting_id)[:3]

    # ── 3. 검토 대기 항목 (HitlReview PENDING) ───────────────────────
    pending_reviews = db.query(models.HitlReview).filter(
        models.HitlReview.meeting_id == meeting_id,
        models.HitlReview.status == "PENDING",
    ).order_by(models.HitlReview.created_at.desc()).limit(10).all()

    pending_todos_text = ""
    if pending_reviews:
        import json as _json2
        review_lines = []
        for r in pending_reviews:
            try:
                item = _json2.loads(r.ai_output or "{}")
                content = item.get("content", r.ai_output or "")
            except Exception:
                content = r.ai_output or ""
            review_lines.append(f"- [검토 대기] {content}")
        pending_todos_text = "\n".join(review_lines)

    # ── 4. 파일 텍스트 추출 ───────────────────────────────────────────
    file_texts = []

    # DB에 저장된 보고서
    for fid in selected_ids:
        try:
            report = db.query(models.Report).filter(models.Report.id == int(fid)).first()
            if report and report.file_path and _os.path.exists(report.file_path):
                with open(report.file_path, "rb") as f:
                    raw = f.read()
                text = _extract_text_from_file(raw, report.file_name or "")
                if text.strip():
                    file_texts.append(f"[보고서: {report.file_name}]\n{text[:4000]}")
        except Exception as e:
            print(f"[DB 파일 추출 오류] {e}")

    # 새로 업로드된 파일 (multipart)
    for upload in files:
        if not upload or not upload.filename:
            continue
        try:
            raw = await upload.read()
            fname = upload.filename.lower()
            text = _extract_text_from_file(raw, fname)
            if text.strip():
                file_texts.append(f"[첨부: {upload.filename}]\n{text[:4000]}")
            else:
                file_texts.append(f"[첨부: {upload.filename}] - 텍스트 추출 불가")
        except Exception as e:
            print(f"[업로드 파일 추출 오류] {upload.filename}: {e}")

    # ── 5. 프롬프트 구성 ──────────────────────────────────────────────
    context_parts = [f"[회의체 정보]\n{meeting_context}"]

    if meeting.guidelines:
        context_parts.append(f"[회의 지침]\n{meeting.guidelines}")

    if previous_minutes:
        minutes_text = "\n\n".join(
            f"[회의록 {i+1}]\n{m}" for i, m in enumerate(previous_minutes)
        )
        context_parts.append(f"[최근 회의록]\n{minutes_text}")

    if pending_todos_text:
        context_parts.append(f"[미완료 과제]\n{pending_todos_text}")

    if file_texts:
        context_parts.append(f"[첨부 자료]\n" + "\n\n".join(file_texts))

    if knowledge:
        kb_text = "\n".join(
            f"- [{k['category']}] {k['title']}: {k['content']}" for k in knowledge[:5]
        )
        context_parts.append(f"[조직 암묵지]\n{kb_text}")

    full_context = "\n\n".join(context_parts)

    # ── 6. LLM 호출 ───────────────────────────────────────────────────
    from langchain_openai import ChatOpenAI
    from langchain_core.messages import SystemMessage, HumanMessage

    llm = ChatOpenAI(
        model=_os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
        temperature=0.15,
        api_key=_os.getenv("OPENAI_API_KEY"),
    )

    dept_list = ", ".join(departments) if departments else "정보 없음"

    system_prompt = f"""당신은 회의체 운영 전문 AI입니다.
주어진 컨텍스트(회의체 정보, 회의록, 미완료 과제, 첨부 자료)를 분석하여
다음 회의에서 다뤄야 할 핵심 과제와 아젠다를 추출해 주세요.

참여 부서: {dept_list}

규칙:
1. 첨부 자료가 있으면 그 내용을 최우선으로 분석하여 구체적인 후속 과제를 추출하세요
2. 미완료 과제가 있으면 반드시 포함하되 중복은 제거하세요
3. 과제는 실행 가능하고 구체적으로 작성하세요 (문서에서 언급된 날짜, 수치, 담당자 반영)
4. bullets는 과제의 세부 실행 항목 2-4개로 작성하세요
5. 3-6개 과제를 추출하세요
6. 문서에 일정이 명시되어 있으면 bullets에 반드시 포함하세요

반드시 아래 JSON 형식으로만 응답하세요:
{{
  "agendas": [
    {{
      "title": "과제/아젠다 제목",
      "bullets": ["세부 항목1", "세부 항목2", "세부 항목3"],
      "department": "담당부서명 또는 null",
      "priority": "urgent_important" | "important" | "urgent" | "normal"
    }}
  ]
}}"""

    human_prompt = f"다음 컨텍스트를 바탕으로 과제를 추출해 주세요:\n\n{full_context}"

    try:
        response = await llm.ainvoke([
            SystemMessage(content=system_prompt),
            HumanMessage(content=human_prompt),
        ])
        raw_text = response.content.strip()
        print(f"[LLM RAW] {raw_text[:500]}")
        try:
            match = _re.search(r'\{[\s\S]*\}', raw_text)
            if match:
                json_str = match.group(0)
                open_count = json_str.count('{') - json_str.count('}')
                if open_count > 0:
                    json_str += '}' * open_count
                parsed = _json.loads(json_str)
            else:
                parsed = _json.loads(raw_text)
        except Exception as parse_err:
            print(f"[JSON 파싱 오류] {parse_err}")
            parsed = {"agendas": []}
        agendas = parsed.get("agendas", [])
        print(f"[AGENDAS] {agendas}")
        result = []
        for ag in agendas:
            result.append({
                "title": ag.get("title", ""),
                "bullets": ag.get("bullets", []),
                "department": ag.get("department"),
                "priority": ag.get("priority", "normal"),
                "_state": None,
                "_editing": False,
            })

        return {
            "agendas": result,
            "context_used": {
                "minutes_count": len(previous_minutes),
                "pending_reviews_count": len(pending_reviews),
                "files_count": len(file_texts),
            }
        }

    except Exception as e:
        print(f"[archive/extract-agendas 오류] {e}")
        return {"agendas": [], "error": f"AI 분석 중 오류: {str(e)}"}


# ─── 아카이브 채팅 기반 과제 업데이트 ──────────────────────────────────────
@router.post("/archive/chat-extract")
async def archive_chat_extract(
    data: schemas.AgentChatRequest,
    background_tasks: BackgroundTasks,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    아카이브 과제 탭 채팅 - 사용자가 채팅으로 과제를 수정/추가 요청하면
    현재 추출된 과제 목록을 업데이트해서 반환한다.
    """
    import json as _json, os as _os, re as _re
    from langchain_openai import ChatOpenAI
    from langchain_core.messages import SystemMessage, HumanMessage

    meeting_id = data.meeting_id
    message = data.message or ""
    current_agendas = data.chat_history[0].get("agendas", []) if data.chat_history else []

    meeting_context = _get_meeting_context(db, meeting_id) if meeting_id else ""
    departments = _get_member_departments(db, meeting_id) if meeting_id else []
    dept_list = ", ".join(departments) if departments else "정보 없음"

    llm = ChatOpenAI(
        model=_os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
        temperature=0.15,
        api_key=_os.getenv("OPENAI_API_KEY"),
    )

    current_agendas_text = _json.dumps(current_agendas, ensure_ascii=False, indent=2) if current_agendas else "없음"

    system_prompt = f"""당신은 회의체 과제 관리 AI입니다.
현재 추출된 과제 목록과 사용자의 요청을 바탕으로 과제 목록을 업데이트해주세요.

회의체 정보: {meeting_context}
참여 부서: {dept_list}

현재 과제 목록:
{current_agendas_text}

규칙:
1. 사용자가 과제 추가를 요청하면 새 과제를 목록에 추가하세요
2. 사용자가 과제 수정을 요청하면 해당 과제를 수정하세요
3. 사용자가 과제 삭제를 요청하면 해당 과제를 제거하세요
4. 변경되지 않은 과제는 그대로 유지하세요
5. 반드시 아래 JSON 형식으로 전체 과제 목록을 반환하세요

{{
  "agendas": [
    {{
      "title": "과제 제목",
      "bullets": ["세부 항목1", "세부 항목2"],
      "department": "담당부서 또는 null",
      "priority": "urgent_important" | "important" | "urgent" | "normal"
    }}
  ],
  "message": "변경 사항 설명 (한 문장)"
}}"""

    try:
        response = await llm.ainvoke([
            SystemMessage(content=system_prompt),
            HumanMessage(content=message),
        ])
        raw_text = response.content.strip()
        print(f"[chat-extract RAW] {raw_text[:300]}")

        try:
            match = _re.search(r'\{[\s\S]*\}', raw_text)
            if match:
                json_str = match.group(0)
                open_count = json_str.count('{') - json_str.count('}')
                if open_count > 0:
                    json_str += '}' * open_count
                parsed = _json.loads(json_str)
            else:
                parsed = _json.loads(raw_text)
        except Exception:
            parsed = {"agendas": current_agendas, "message": raw_text}

        agendas = parsed.get("agendas", current_agendas)
        reply_msg = parsed.get("message", "과제 목록을 업데이트했습니다.")

        result = [
            {
                "title": ag.get("title", ""),
                "bullets": ag.get("bullets", []),
                "department": ag.get("department"),
                "priority": ag.get("priority", "normal"),
                "_state": None,
                "_editing": False,
            }
            for ag in agendas
        ]
        return {"agendas": result, "reply": reply_msg}

    except Exception as e:
        print(f"[chat-extract 오류] {e}")
        return {"agendas": current_agendas, "reply": f"오류: {str(e)}"}

@router.post("/archive/analyze-file")
async def analyze_archive_file(
    data: dict,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    아카이브에서 자료 업로드 시 AI가 문서를 검토하고
    - 적합성 점수(0-100)
    - 검토 의견 (피드백 항목)
    - 제안 아젠다 목록
    - 유관부서 목록
    을 반환한다. GraphDB(온톨로지) 맥락도 활용한다.
    """
    import json as _json
    from langchain_openai import ChatOpenAI
    from langchain_core.messages import SystemMessage, HumanMessage

    file_name: str = data.get("file_name", "")
    file_type: str = data.get("file_type", "")
    dept_name: str = data.get("dept_name", "")
    graph_context: str = data.get("graph_context", "")
    file_content: str = data.get("file_content", "")

    has_content = file_content and file_content not in (
        "[파일 미첨부 — 이름만 입력됨]", "[바이너리 파일 — 내용 추출 불가]", ""
    )

    # 글로벌 암묵지 컨텍스트 로드
    knowledge_items = _get_knowledge(db)
    knowledge_text = "\n".join(
        f"[{k['category']}] {k['title']}: {k['content']}" for k in knowledge_items[:10]
    ) if knowledge_items else "없음"

    llm = ChatOpenAI(
        model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
        temperature=0.2,
        api_key=os.getenv("OPENAI_API_KEY"),
    )

    system_msg = SystemMessage(content="""당신은 조직 온톨로지·지식 관리 전문 AI입니다.
파일 이름, 유형, 업로드 부서, 실제 파일 내용(제공된 경우), 조직 그래프 맥락을 바탕으로
해당 자료의 적합성·완성도를 평가하고 아래 JSON을 반드시 반환하세요.

{
  "score": <0-100 정수>,
  "feedback": ["피드백 항목1", "피드백 항목2", ...],
  "agendas": [
    {"content": "아젠다 내용", "department": "담당부서명"}
  ],
  "related_depts": ["부서명1", "부서명2", ...]
}

중요 채점 기준:
- 파일 내용이 없거나 "[파일 미첨부]" 상태이면 score는 최대 30점이며, feedback에 "파일 내용 없음" 반드시 명시
- "[바이너리 파일]"이면 내용 평가 불가이므로 score는 최대 50점
- 실제 내용이 있으면 내용의 구체성, 완성도, 회의 적합성을 종합 평가 (0-100 전체 범위 사용)
- score: 파일명·유형·부서 적합성 + 실제 내용 완성도 + 그래프 맥락 연계도 종합
- feedback: 보완할 점, 잘된 점 포함 (3-5개, 구체적으로)
- agendas: 이 자료가 다음 회의에서 다뤄야 할 아젠다 제안 (1-3개)
- related_depts: 유관부서 (그래프에 이미 존재하는 부서 우선, 2-4개)
반드시 JSON만 반환하고 다른 설명은 쓰지 마세요.""")

    human_msg = HumanMessage(content=f"""파일 이름: {file_name}
파일 유형: {file_type}
업로드 부서: {dept_name}

[파일 내용]
{file_content if file_content else "[파일 미첨부 — 이름만 입력됨]"}

[현재 조직 그래프 맥락]
{graph_context or '(그래프 정보 없음)'}

[조직 암묵지]
{knowledge_text}
""")

    try:
        response = await llm.ainvoke([system_msg, human_msg])
        raw = response.content.strip()
        # JSON 추출
        import re as _re
        match = _re.search(r'\{[\s\S]*\}', raw)
        if match:
            result = _json.loads(match.group(0))
        else:
            result = _json.loads(raw)
        return {
            "score": int(result.get("score", 70)),
            "feedback": result.get("feedback", []),
            "agendas": result.get("agendas", []),
            "related_depts": result.get("related_depts", []),
        }
    except Exception as e:
        return {
            "score": 70,
            "feedback": [f"AI 분석 중 오류: {str(e)}", "수동으로 검토해 주세요."],
            "agendas": [{"content": f"{file_name} 관련 안건 검토", "department": dept_name}],
            "related_depts": [],
        }