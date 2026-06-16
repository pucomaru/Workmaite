import asyncio
import logging
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session

from db import models
from core.auth import get_current_user
from db.database import get_db
from graphdb.neo4j_ids import to_mg_id
from graphdb.neo4j_client import run_cypher as _run_cypher  # 공유 Bolt 클라이언트
from graphdb.rel_schema import (
    ALLOWED_REL_TYPES,
    REL_MATRIX,
    REL_COLORS,
)  # 관계 스키마 SSOT

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/neo4j", tags=["neo4j"])

ALLOWED_LABELS = {
    "Meetings",
    "User",
    "Department",
    "Agenda",
    "Report",
    "Minutes",
    "Session",
    "Company",
}
# ALLOWED_REL_TYPES는 rel_schema.py(SSOT)에서 파생 — 여기서 손으로 정의하지 말 것.
# 통신부(_run_cypher)는 neo4j_client(Bolt)에서 import — 이 파일은 쿼리 로직만 담당.

_NODE_ID_PREFIXES = ("mg-", "session-", "agenda-", "doc-", "dept-", "p-", "company-")


def _normalize_node_id(raw: str) -> str:
    """이중 prefix 정규화: "mg-mg-001" → "mg-001"."""
    for p in _NODE_ID_PREFIXES:
        if raw.startswith(p + p):
            return raw[len(p) :]
    return raw


@router.get("/archive")
async def get_archive(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """인증된 사용자의 소속 회의체만 반환 — Neo4j 기반, Postgres는 meeting_id 보완에만 사용."""
    user_email = current_user.email or ""

    # ── Postgres: 그래프에 포함할 meeting_id 범위 (조회 스코프) ──
    # access_guard.viewable_meeting_ids로 일원화 — company_role 규칙을 단일 정의에서 따른다.
    #   SYSTEM_ADMIN → None(전체 회의체), COMPANY_ADMIN → 자사 구성원 참여 회의체, USER → 본인 소속.
    # (기존엔 SYSTEM_ADMIN을 따로 처리하지 않아 시스템 관리자도 본인 소속 회의체만 보였다 → 전체
    #  연결관계가 안 보이는 버그.)
    from core.access_guard import viewable_meeting_ids

    _vis = viewable_meeting_ids(db, current_user)
    if _vis is None:  # SYSTEM_ADMIN — 전체 회의체
        _raw_ids = {row.id for row in db.query(models.Meeting.id).all()}
    else:
        _raw_ids = set(_vis)
    pg_meeting_ids = {to_mg_id(mid) for mid in _raw_ids}

    # ── Step 1+2: User 조회 / company / dept — 동시에 시작 ──────
    # User 결과가 나와야 allowed_mg 쿼리를 보낼 수 있으므로,
    # User 는 별도 태스크로 먼저 쏘고 company/dept 와 concurrently 대기한다.
    try:
        person_rows, company_rows, dept_rows = await asyncio.gather(
            _run_cypher(
                # 사용자 매칭은 pg_id 단일 키 (email/name 매칭은 동명이인·개명 시 오인 — SEC-12)
                "MATCH (p:User {pg_id: $pg_id}) "
                "RETURN coalesce(p.id, toString(p.pg_id)) AS pid, p.name AS pname",
                {"pg_id": current_user.id},
            ),
            _run_cypher("MATCH (o:Company) RETURN o.name AS name LIMIT 1"),
            _run_cypher("MATCH (d:Department) RETURN d.name AS name ORDER BY d.name"),
        )
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Neo4j 연결 실패: {str(e)}")

    # ── Step 2: 소속 회의체 ID 조회 ──────────────────────────────
    try:
        if person_rows:
            person_id = person_rows[0]["pid"]
            allowed_rows = await _run_cypher(
                """
                MATCH (p:User)-[:`참여`|`운영`]->(mg:Meetings)
                WHERE (p.id = $pid OR toString(p.pg_id) = $pid)
                RETURN mg.id AS mg_id
                """,
                {"pid": person_id},
            )
        else:
            person_id = None
            allowed_rows = []
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Neo4j 연결 실패: {str(e)}")

    allowed_mg_ids = {r["mg_id"] for r in allowed_rows} | pg_meeting_ids

    if not allowed_mg_ids:
        current_person = {
            "id": person_rows[0]["pid"] if person_rows else f"user-{current_user.id}",
            "name": person_rows[0]["pname"] if person_rows else current_user.name,
            "email": user_email,
            "position": current_user.position or "",
            "department": current_user.department or "",
        }
        return {
            "meetings": [],
            "minutes": [],
            "reports": [],
            "departments": dept_rows,
            "company": company_rows[0] if company_rows else None,
            "current_person": current_person,
        }

    # ── Step 3: 회의체 상세 데이터 4종 — 병렬 조회 ───────────────
    mg_ids_list = list(allowed_mg_ids)
    try:
        mg_rows, agenda_rows, session_rows, report_rows = await asyncio.gather(
            _run_cypher(
                """
                MATCH (mg:Meetings) WHERE mg.id IN $ids
                OPTIONAL MATCH (p:User)-[rel:`운영`|`참여`]->(mg)
                OPTIONAL MATCH (p)-[:`소속`]->(d:Department)
                RETURN
                    mg.id AS mg_id,
                    coalesce(mg.title, '') AS title,
                    coalesce(mg.type) AS meeting_type,
                    coalesce(mg.status, 'active') AS status,
                    coalesce(mg.description, '') AS purpose,
                    coalesce(mg.guidelines, '') AS guidelines,
                    coalesce(mg.context, '') AS context,
                    mg.start_date AS start_date,
                    mg.end_date AS end_date,
                    coalesce(p.id, toString(p.pg_id)) AS person_id,
                    p.name AS person_name, p.email AS email,
                    p.position AS position, type(rel) AS role, rel.role AS rel_role,
                    coalesce(d.name, p.department, '') AS department,
                    coalesce(p.company, '') AS company
                ORDER BY mg_id
                """,
                {"ids": mg_ids_list},
            ),
            _run_cypher(
                """
                MATCH (ag:Agenda)-[:`관할`]->(mg:Meetings)
                WHERE mg.id IN $ids AND coalesce(ag.status, '') <> 'draft'
                OPTIONAL MATCH (p:User)-[:`담당`]->(ag)
                OPTIONAL MATCH (p)-[:`소속`]->(d:Department)
                RETURN
                    mg.id AS meetingId,
                    coalesce(ag.id, toString(ag.pg_id)) AS id,
                    coalesce(ag.title, ag.content) AS content,
                    ag.description AS description,
                    ag.priority AS priority, ag.status AS status,
                    toString(ag.due_date) AS due_date,
                    toString(ag.created_at) AS created_at,
                    ag.ai_evidence AS ai_evidence,
                    p.name AS assignee_name, coalesce(d.name, '') AS assignee_dept
                """,
                {"ids": mg_ids_list},
            ),
            _run_cypher(
                """
                MATCH (s:Session)-[:`소속`]->(mg:Meetings) WHERE mg.id IN $ids
                // 아카이브에 저장(확정)된 회의록만 노출 — DRAFT 회의록은 시각화하지 않는다
                OPTIONAL MATCH (mn:Minutes)-[:`기록`]->(s)
                WHERE toLower(coalesce(mn.status, '')) = 'completed'
                OPTIONAL MATCH (u:User)-[:`참석`]->(s)
                WITH mg, s, mn,
                     collect(CASE WHEN u IS NOT NULL THEN {userId: u.pg_id, userName: u.name, department: u.department} END) AS participants
                RETURN
                    mg.id AS meetingId,
                    coalesce(mg.title, '') AS meetingTitle,
                    coalesce(s.id, toString(s.pg_id)) AS id,
                    s.title AS session_title,
                    toString(coalesce(s.scheduled_at)) AS date,
                    toString(s.started_at) AS started_at,
                    s.type AS session_type,
                    s.description AS description,
                    s.location AS location,
                    s.status AS session_status,
                    toString(s.ended_at) AS ended_at,
                    mn.content_summary AS content_summary,
                    mn.short_summary AS short_summary,
                    mn.file_name AS minutes_file_name,
                    mn.status AS minutes_status,
                    mn.pg_id AS minutes_pg_id,
                    toString(mn.generated_at) AS generated_at,
                    participants
                """,
                {"ids": mg_ids_list},
            ),
            _run_cypher(
                """
                MATCH (doc:Report)-[:`발제`]->(mg:Meetings) WHERE mg.id IN $ids
                OPTIONAL MATCH (doc)-[:`도출`]->(ag:Agenda)
                RETURN
                    mg.id AS meetingId,
                    coalesce(mg.title, '') AS meetingTitle,
                    doc.id AS id, doc.file_name AS file_name,
                    doc.submitter_department AS department,
                    coalesce(toString(doc.created_at)) AS submitted_at,
                    coalesce(ag.id, toString(ag.pg_id)) AS related_todo_id
                """,
                {"ids": mg_ids_list},
            ),
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Neo4j 연결 실패: {str(e)}")

    # ── 결과 조합 ─────────────────────────────────────────────────
    meetings_map: dict[str, dict] = {}

    for row in mg_rows:
        mg_id = row["mg_id"]
        if mg_id not in meetings_map:
            meetings_map[mg_id] = {
                "id": mg_id,
                "title": row.get("title", ""),
                "meeting_type": row.get("meeting_type"),
                "status": row.get("status", "active"),
                "purpose": row.get("purpose"),
                "guidelines": row.get("guidelines", ""),
                "context": row.get("context", ""),
                "start_date": row.get("start_date"),
                "end_date": row.get("end_date"),
                "members": [],
                "tasks": [],
                "minutes": [],
                "reports": [],
                "minutes_agendas": [],
                "session_agendas": [],
                "derivations": [],
            }
        if row.get("person_id"):
            mg = meetings_map[mg_id]
            if not any(m["userId"] == row["person_id"] for m in mg["members"]):
                mg["members"].append(
                    {
                        "meetingId": mg_id,
                        "userId": row["person_id"],
                        "userName": row.get("person_name", "?"),
                        "email": row.get("email", ""),
                        "position": row.get("position", ""),
                        "role": "admin"
                        if row.get("role") == "간사" or row.get("rel_role") == "admin"
                        else "member",
                        "department": row.get("department") or "",
                        "company": row.get("company") or "",
                    }
                )

    # ── PG meeting_members로 멤버 보완 (권위 소스) ───────────────────────────────
    # Neo4j 구성원/간사 엣지는 User 동기화 누락 시 빠질 수 있어 참여자(member)가 그래프에서
    # 사라진다 → PG meeting_members 기준으로 누락 멤버를 채운다. 스코프(allowed_mg_ids)는 이미 적용됨.
    _mgid_by_pg: dict[int, str] = {}
    for _mgid in meetings_map:
        try:
            _mgid_by_pg[int(str(_mgid).split("-")[-1])] = _mgid
        except (ValueError, IndexError):
            pass
    if _mgid_by_pg:
        _co_names = {c.id: c.name for c in db.query(models.Company).all()}
        _mem_rows = (
            db.query(models.MeetingMember, models.User)
            .join(models.User, models.User.id == models.MeetingMember.user_id)
            .filter(
                models.MeetingMember.meeting_id.in_(list(_mgid_by_pg.keys())),
                models.User.is_active.is_(True),
            )
            .all()
        )
        for _mm, _u in _mem_rows:
            _mk = _mgid_by_pg.get(_mm.meeting_id)
            if not _mk:
                continue
            _members = meetings_map[_mk]["members"]
            if any(str(m["userId"]) == str(_u.id) for m in _members):
                continue
            _members.append(
                {
                    "meetingId": _mk,
                    "userId": _u.id,
                    "userName": _u.name,
                    "email": _u.email or "",
                    "position": _u.position or "",
                    "role": "admin" if _mm.meeting_role == "admin" else "member",
                    "department": _u.department or "",
                    "company": _co_names.get(_u.company_id, "") or "",
                }
            )

    # 동일 Agenda에 담당 관계가 여러 개면 중복 row가 생기므로 id 기준으로 병합
    agenda_map: dict[str, dict] = {}
    for row in agenda_rows:
        mg_id = row.get("meetingId")
        ag_id = row.get("id")
        if not mg_id or mg_id not in meetings_map or not ag_id:
            continue
        if ag_id not in agenda_map:
            raw_created_at = row.get("created_at")
            if (
                raw_created_at
                and not raw_created_at.endswith("Z")
                and "+" not in raw_created_at
            ):
                raw_created_at = raw_created_at + "Z"
            agenda_map[ag_id] = {
                "id": ag_id,
                "meetingId": mg_id,
                "content": row.get("content", ""),
                "description": row.get("description", ""),
                "category": row.get("category"),
                "priority": row.get("priority", "low"),
                "status": row.get("status", "pending"),
                "due_date": row.get("due_date"),
                "created_at": raw_created_at,
                "ai_evidence": row.get("ai_evidence"),
                "assignee_names": [],  # 담당자 여러 명 지원
                "assignee_dept": row.get("assignee_dept", ""),
            }
        if row.get("assignee_name"):
            names = agenda_map[ag_id]["assignee_names"]
            if row["assignee_name"] not in names:
                names.append(row["assignee_name"])
    for ag in agenda_map.values():
        # assignee_name: 첫 번째 담당자 (하위 호환), assignee_names: 전체 목록
        ag["assignee_name"] = ag["assignee_names"][0] if ag["assignee_names"] else None
        meetings_map[ag["meetingId"]]["tasks"].append(ag)

    seen_sessions: set[str] = set()
    for row in session_rows:
        mg_id = row.get("meetingId")
        session_id = row.get("id")
        if (
            mg_id
            and session_id
            and mg_id in meetings_map
            and session_id not in seen_sessions
        ):
            seen_sessions.add(session_id)
            meetings_map[mg_id]["minutes"].append(
                {
                    "id": session_id,
                    "meeting_id": mg_id,
                    "meeting_title": row.get("meetingTitle", ""),
                    "session_title": row.get("session_title", ""),
                    "session_number": row.get("session_number"),
                    "date": row.get("date"),
                    "started_at": row.get("started_at"),
                    "ended_at": row.get("ended_at"),
                    "session_type": row.get("session_type"),
                    "description": row.get("description"),
                    "location": row.get("location"),
                    "session_status": row.get("session_status"),
                    "file_name": row.get("file_name"),
                    "doc_title": row.get("doc_title"),
                    "doc_type": row.get("doc_type"),
                    "doc_author": row.get("doc_author"),
                    "doc_created_at": row.get("doc_created_at"),
                    "content_summary": row.get("content_summary"),
                    "short_summary": row.get("short_summary"),
                    "minutes_file_name": row.get("minutes_file_name"),
                    "minutes_status": row.get("minutes_status"),
                    "minutes_pg_id": row.get("minutes_pg_id"),
                    "generated_at": row.get("generated_at"),
                    "participants": row.get("participants", []),
                }
            )

    def _neo4j_report_pg_id(neo4j_id) -> int | None:
        """'report-N' 형태 Neo4j ID에서 PostgreSQL 정수 ID 추출."""
        if isinstance(neo4j_id, int):
            return neo4j_id
        if isinstance(neo4j_id, str):
            parts = neo4j_id.split("-")
            try:
                return int(parts[-1])
            except (ValueError, IndexError):
                pass
        return None

    seen_report_ids: dict[str, set] = {}
    for row in report_rows:
        mg_id = row.get("meetingId")
        doc_id = row.get("id")
        if not mg_id or mg_id not in meetings_map or not doc_id:
            continue
        pg_id = _neo4j_report_pg_id(doc_id)
        if not pg_id:
            continue
        if mg_id not in seen_report_ids:
            seen_report_ids[mg_id] = set()
        if pg_id in seen_report_ids[mg_id]:
            continue
        seen_report_ids[mg_id].add(pg_id)
        meetings_map[mg_id]["reports"].append(
            {
                "id": pg_id,
                "meeting_id": mg_id,
                "meeting_title": row.get("meetingTitle", ""),
                "title": row.get("title", ""),
                "file_name": row.get("file_name", ""),
                "doc_type": row.get("doc_type", ""),
                "author": row.get("author"),
                "file_url": row.get("file_url"),
                "submitted_at": row.get("submitted_at"),
                "department": row.get("department", ""),
                "related_todo_id": row.get("related_todo_id"),
            }
        )

    # ── 회의 생명주기: Agenda→Session(논의) 조회 ──
    try:
        mn_ag_rows, sess_ag_rows, deriv_rows = await asyncio.gather(
            _run_cypher(
                """
                MATCH (mn:Minutes)-[:`기록`]->(s:Session)<-[:`논의`]-(ag:Agenda)-[:`관할`]->(mg:Meetings)
                WHERE mg.id IN $ids AND toLower(coalesce(mn.status, '')) = 'completed'
                RETURN mg.id AS meetingId,
                       coalesce(s.id, toString(s.pg_id)) AS session_id,
                       coalesce(ag.id, toString(ag.pg_id)) AS agenda_id
                """,
                {"ids": mg_ids_list},
            ),
            _run_cypher(
                """
                MATCH (ag:Agenda)-[:`논의`]->(s:Session)-[:`소속`]->(mg:Meetings)
                WHERE mg.id IN $ids
                RETURN mg.id AS meetingId,
                       coalesce(s.id, toString(s.pg_id)) AS session_id,
                       coalesce(ag.id, toString(ag.pg_id)) AS agenda_id
                """,
                {"ids": mg_ids_list},
            ),
            _run_cypher(
                """
                MATCH (ag:Agenda)-[:`소속`]->(s:Session)-[:`소속`]->(mg:Meetings)
                WHERE mg.id IN $ids
                RETURN mg.id AS meetingId,
                       coalesce(s.id, toString(s.pg_id)) AS session_id,
                       coalesce(ag.id, toString(ag.pg_id)) AS agenda_id
                """,
                {"ids": mg_ids_list},
            ),
        )
        for row in mn_ag_rows:
            mg_id = row.get("meetingId")
            if mg_id in meetings_map:
                meetings_map[mg_id]["minutes_agendas"].append(
                    {
                        "session_id": row.get("session_id"),
                        "agenda_id": row.get("agenda_id"),
                    }
                )
        for row in sess_ag_rows:
            mg_id = row.get("meetingId")
            if mg_id in meetings_map:
                meetings_map[mg_id]["session_agendas"].append(
                    {
                        "session_id": row.get("session_id"),
                        "agenda_id": row.get("agenda_id"),
                    }
                )
        for row in deriv_rows:
            mg_id = row.get("meetingId")
            if mg_id in meetings_map:
                meetings_map[mg_id]["derivations"].append(
                    {
                        "session_id": row.get("session_id"),
                        "agenda_id": row.get("agenda_id"),
                    }
                )
    except Exception:
        pass  # 생명주기 데이터 없어도 메인 그래프는 정상 반환

    # ── Postgres 보완: 모든 회의체의 reports를 PostgreSQL에서 채움 ──
    all_raw_ids = [
        int(mid.replace("mg-", ""))
        for mid in meetings_map.keys()
        if mid.replace("mg-", "").isdigit()
    ]
    if all_raw_ids:
        rows = (
            db.query(models.Report, models.HitlReview, models.ReportScore)
            .outerjoin(
                models.HitlReview,
                models.HitlReview.report_id == models.Report.id,
            )
            .outerjoin(
                models.ReportScore,
                models.ReportScore.report_id == models.Report.id,
            )
            .filter(models.Report.meeting_id.in_(all_raw_ids))
            .all()
        )
        # PG가 보고서의 단일 출처 — Neo4j 데이터를 PG로 완전 교체
        for sid in meetings_map:
            meetings_map[sid]["reports"] = []
        for r, hr, rs in rows:
            sid = to_mg_id(r.meeting_id)
            if sid not in meetings_map:
                continue
            meetings_map[sid]["reports"].append(
                {
                    "id": r.id,
                    "meetingId": sid,
                    "file_name": r.file_name,
                    "file_path": r.file_path,
                    "human_status": r.human_status,
                    "version": r.version,
                    "parent_id": r.parent_id,
                    "submitter_department": r.submitter_department,
                    "created_at": r.created_at.isoformat() + "Z"
                    if r.created_at
                    else None,
                    "reviewed_at": hr.reviewed_at.isoformat() + "Z"
                    if hr and hr.reviewed_at
                    else None,
                    "related_agenda_ids": r.related_agenda_ids or [],
                    "ai_status": rs.ai_status if rs else None,
                    "score": rs.total_score if rs else None,
                    "total_score": rs.total_score if rs else None,
                    "detail_scores": rs.detail_scores if rs else None,
                    "feedback": rs.feedback if rs else None,
                    "score_created_at": rs.created_at.isoformat() + "Z"
                    if rs and rs.created_at
                    else None,
                }
            )

    # ── Postgres 보완: meeting_sessions + minutes 데이터로 session 정보 채움 ──
    if all_raw_ids:
        pg_sessions = (
            db.query(models.MeetingSession, models.Minutes)
            .outerjoin(
                models.Minutes,
                models.Minutes.session_id == models.MeetingSession.id,
            )
            .filter(models.MeetingSession.meeting_id.in_(all_raw_ids))
            .all()
        )
        pg_session_map: dict[int, dict] = {}
        for s, mn in pg_sessions:
            pg_session_map[s.id] = {
                "session_title": s.title or "",
                "description": s.description or "",
                "location": s.location or "",
                "session_type": str(s.type) if s.type else "",
                "date": s.scheduled_at.isoformat() + "Z" if s.scheduled_at else "",
                "created_at": s.created_at.isoformat() + "Z" if s.created_at else "",
                "started_at": s.started_at.isoformat() + "Z" if s.started_at else "",
                "ended_at": s.ended_at.isoformat() + "Z" if s.ended_at else "",
                "session_status": s.status or "",
                "content_summary": mn.content_summary if mn else "",
                "short_summary": getattr(mn, "short_summary", None) if mn else None,
                "minutes_file_name": mn.file_name if mn else "",
                "minutes_status": mn.status if mn else "",
                "generated_at": mn.generated_at.isoformat() + "Z"
                if mn and mn.generated_at
                else "",
            }
        for mg_data in meetings_map.values():
            for sess in mg_data.get("minutes", []):
                sess_neo_id = sess.get("id", "")
                pg_id = None
                if isinstance(sess_neo_id, str) and "-" in sess_neo_id:
                    try:
                        pg_id = int(sess_neo_id.split("-")[-1])
                    except (ValueError, IndexError):
                        pass
                elif isinstance(sess_neo_id, int):
                    pg_id = sess_neo_id
                if pg_id and pg_id in pg_session_map:
                    sess.update(pg_session_map[pg_id])

        # ── PG 세션 미동기 보완: Neo4j에 없는 신규 세션도 포함 ──────────────────
        neo4j_session_pg_ids: set[int] = set()
        for mg_data in meetings_map.values():
            for sess in mg_data.get("minutes", []):
                sess_neo_id = sess.get("id", "")
                if isinstance(sess_neo_id, str) and "-" in sess_neo_id:
                    try:
                        neo4j_session_pg_ids.add(int(sess_neo_id.split("-")[-1]))
                    except (ValueError, IndexError):
                        pass
                elif isinstance(sess_neo_id, int):
                    neo4j_session_pg_ids.add(sess_neo_id)
        for s, mn in pg_sessions:
            if s.id not in neo4j_session_pg_ids:
                mg_id = to_mg_id(s.meeting_id)
                if mg_id in meetings_map:
                    meetings_map[mg_id]["minutes"].append(
                        {
                            "id": f"session-{s.id}",
                            "meeting_id": mg_id,
                            "meeting_title": meetings_map[mg_id].get("title", ""),
                            "session_title": s.title or "",
                            "description": s.description or "",
                            "location": s.location or "",
                            "session_type": str(s.type) if s.type else "",
                            "date": s.scheduled_at.isoformat() + "Z"
                            if s.scheduled_at
                            else "",
                            "created_at": s.created_at.isoformat() + "Z"
                            if s.created_at
                            else "",
                            "started_at": s.started_at.isoformat() + "Z"
                            if s.started_at
                            else "",
                            "ended_at": s.ended_at.isoformat() + "Z"
                            if s.ended_at
                            else "",
                            "session_status": str(s.status) if s.status else "",
                            "content_summary": mn.content_summary if mn else "",
                            "short_summary": getattr(mn, "short_summary", None)
                            if mn
                            else None,
                            "minutes_file_name": mn.file_name if mn else "",
                            "minutes_status": mn.status if mn else "",
                            "minutes_pg_id": mn.id if mn else None,
                            "generated_at": mn.generated_at.isoformat() + "Z"
                            if mn and mn.generated_at
                            else "",
                            "session_number": None,
                            "doc_title": None,
                            "doc_type": None,
                            "doc_author": None,
                            "doc_created_at": None,
                            "file_name": None,
                            "participants": [],
                        }
                    )

    # ── Postgres 보완: Neo4j 미동기 신규 회의체 (기본 정보만) ──────
    missing_pg_ids = pg_meeting_ids - meetings_map.keys()
    if missing_pg_ids:
        raw_ids = [
            int(mid.replace("mg-", ""))
            for mid in missing_pg_ids
            if mid.replace("mg-", "").isdigit()
        ]
        pg_meetings = (
            db.query(models.Meeting).filter(models.Meeting.id.in_(raw_ids)).all()
        )
        for m in pg_meetings:
            sid = to_mg_id(m.id)
            members_db = (
                db.query(models.MeetingMember, models.User)
                .join(models.User, models.User.id == models.MeetingMember.user_id)
                .filter(models.MeetingMember.meeting_id == m.id)
                .all()
            )
            meetings_map[sid] = {
                "id": sid,
                "title": m.title,
                "meeting_type": str(m.type) if m.type else None,
                "status": m.status or "active",
                "description": m.description,
                "start_date": m.start_date.isoformat() + "Z" if m.start_date else None,
                "end_date": m.end_date.isoformat() + "Z" if m.end_date else None,
                "members": [
                    {
                        "meetingId": sid,
                        "userId": f"user-{u.id}",
                        "userName": u.name or "",
                        "email": u.email or "",
                        "position": u.position or "",
                        "role": "admin"
                        if str(mb.meeting_role) == "admin"
                        else "member",
                        "department": u.department or "",
                        "company": u.company_name or "",
                    }
                    for mb, u in members_db
                ],
                "tasks": [],
                "minutes": [],
                "reports": [
                    {
                        "id": r.id,
                        "meetingId": sid,
                        "file_name": r.file_name,
                        "file_path": r.file_path,
                        "human_status": r.human_status,
                        "submitter_department": r.submitter_department,
                        "created_at": r.created_at.isoformat() + "Z"
                        if r.created_at
                        else None,
                        "related_agenda_ids": r.related_agenda_ids or [],
                    }
                    for r in db.query(models.Report)
                    .filter(
                        models.Report.meeting_id == m.id,
                    )
                    .all()
                ],
            }

    # ── 사용자가 수동으로 만든 자유 관계 — 소스 오브 트루스인 PostgreSQL(graph_relations)에서 읽는다 ──
    # (buildGraphNodes는 PG 엔티티에서 구조 엣지를 파생하므로, 수동 관계는 이 경로로만 그래프에 복원된다.
    #  프런트는 양 끝 노드가 현재 그래프에 존재하는 엣지만 렌더링하므로 스코프 밖 관계는 자연히 무시된다.)
    manual_relations: list[dict] = []
    try:
        for gr in (
            db.query(models.GraphRelation)
            .order_by(models.GraphRelation.id.desc())
            .limit(5000)
            .all()
        ):
            manual_relations.append(
                {"from_id": gr.from_node_id, "to_id": gr.to_node_id, "rel": gr.rel_type}
            )
    except Exception as e:
        logger.warning(f"[graph] 수동 관계 조회 실패: {e}")  # 메인 그래프는 정상 동작

    meetings = list(meetings_map.values())
    minutes = [mn for mg in meetings for mn in mg["minutes"]]
    reports = [r for mg in meetings for r in mg["reports"]]

    current_person = {
        "id": person_rows[0]["pid"] if person_rows else f"user-{current_user.id}",
        "name": person_rows[0]["pname"] if person_rows else current_user.name,
        "email": user_email,
        "position": current_user.position or "",
        "department": current_user.department or "",
    }

    return {
        "meetings": meetings,
        "minutes": minutes,
        "reports": reports,
        "departments": dept_rows,
        "company": company_rows[0] if company_rows else None,
        "current_person": current_person,
        "manual_relations": manual_relations,
    }


@router.get("/rel-schema")
async def get_rel_schema(current_user: models.User = Depends(get_current_user)):
    """관계 스키마 SSOT — 프런트가 번들 기본값을 이 값으로 덮어쓴다."""
    return {"matrix": REL_MATRIX, "colors": REL_COLORS}


@router.post("/relationships")
async def create_relationship(
    data: dict,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """수동 관계 추가 — PostgreSQL(소스 오브 트루스)에 저장하고 Neo4j에 동기화한다."""
    from_id = _normalize_node_id((data.get("from_id") or "").strip())
    rel_type = (data.get("rel_type") or "").strip()
    to_id = _normalize_node_id((data.get("to_id") or "").strip())
    if not rel_type:
        raise HTTPException(status_code=400, detail="rel_type 필수")
    if not from_id or not to_id:
        raise HTTPException(status_code=400, detail="from_id, to_id 필수")
    if from_id == to_id:
        raise HTTPException(
            status_code=400, detail="자기 자신과의 관계는 만들 수 없습니다."
        )
    # Cypher 관계 타입: 영문/숫자/밑줄만 허용 (한국어는 백틱으로 감싸되 허용 목록 내여야 함)
    import re

    safe_rel = rel_type if re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", rel_type) else None
    if not safe_rel:
        if rel_type not in ALLOWED_REL_TYPES:
            raise HTTPException(
                status_code=400, detail=f"허용되지 않는 관계 유형: {rel_type}"
            )
        safe_rel = rel_type

    # 1) PostgreSQL(소스 오브 트루스) — 멱등 INSERT
    try:
        exists = (
            db.query(models.GraphRelation.id)
            .filter_by(from_node_id=from_id, rel_type=rel_type, to_node_id=to_id)
            .first()
        )
        if not exists:
            db.add(
                models.GraphRelation(
                    from_node_id=from_id,
                    rel_type=rel_type,
                    to_node_id=to_id,
                    created_by=current_user.id,
                )
            )
            db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"[graph] 관계 PG 저장 실패: {e}")
        raise HTTPException(status_code=500, detail="관계 저장에 실패했습니다.")

    # 2) Neo4j 동기화(MERGE) — 실패해도 PG가 진실이라 다음 조회 시 manual_relations로 복원되므로 비치명적
    try:
        await _run_cypher(
            f"MATCH (a {{id: $from_id}}), (b {{id: $to_id}}) MERGE (a)-[:`{safe_rel}`]->(b)",
            {"from_id": from_id, "to_id": to_id},
        )
    except Exception as e:
        logger.warning(f"[graph] 관계 Neo4j 동기화 실패(PG에는 저장됨): {e}")
    return {"ok": True}


@router.delete("/relationships")
async def delete_relationship(
    data: dict,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """두 노드 사이의 관계 삭제 — PostgreSQL에서 삭제하고 Neo4j에 동기화한다."""
    from_id = _normalize_node_id((data.get("from_id") or "").strip())
    rel_type = (data.get("rel_type") or "").strip()
    to_id = _normalize_node_id((data.get("to_id") or "").strip())

    # 1) PostgreSQL 삭제(소스 오브 트루스) — from→to 방향. rel_type 있으면 해당 타입만.
    try:
        q = db.query(models.GraphRelation).filter_by(
            from_node_id=from_id, to_node_id=to_id
        )
        if rel_type:
            q = q.filter_by(rel_type=rel_type)
        q.delete(synchronize_session=False)
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"[graph] 관계 PG 삭제 실패: {e}")
        raise HTTPException(status_code=500, detail="관계 삭제에 실패했습니다.")

    # 2) Neo4j 동기화 삭제 — rel_type이 없거나 허용목록 밖이면 타입 무관 전체 삭제. 비치명적.
    use_rel_type = rel_type if rel_type and rel_type in ALLOWED_REL_TYPES else None
    try:
        if use_rel_type:
            cypher_fwd = f"MATCH (a {{id: $from_id}})-[r:`{use_rel_type}`]->(b {{id: $to_id}}) DELETE r"
            cypher_rev = f"MATCH (a {{id: $to_id}})-[r:`{use_rel_type}`]->(b {{id: $from_id}}) DELETE r"
        else:
            cypher_fwd = "MATCH (a {id: $from_id})-[r]->(b {id: $to_id}) DELETE r"
            cypher_rev = "MATCH (a {id: $to_id})-[r]->(b {id: $from_id}) DELETE r"
        await _run_cypher(cypher_fwd, {"from_id": from_id, "to_id": to_id})
        await _run_cypher(cypher_rev, {"from_id": from_id, "to_id": to_id})
    except Exception as e:
        logger.warning(f"[graph] 관계 Neo4j 삭제 동기화 실패(PG는 삭제됨): {e}")
    return {"ok": True}


@router.put("/relationships")
async def update_relationship(
    data: dict,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """관계 유형 변경 (old → new) — PostgreSQL에서 변경하고 Neo4j에 동기화한다."""
    from_id = _normalize_node_id((data.get("from_id") or "").strip())
    old_rel = (data.get("old_rel") or "").strip()
    new_rel = (data.get("new_rel") or "").strip()
    to_id = _normalize_node_id((data.get("to_id") or "").strip())
    if old_rel not in ALLOWED_REL_TYPES or new_rel not in ALLOWED_REL_TYPES:
        raise HTTPException(status_code=400, detail="허용되지 않는 관계 유형")

    # 1) PostgreSQL — old 삭제 후 new upsert (UNIQUE 충돌 방지)
    try:
        db.query(models.GraphRelation).filter_by(
            from_node_id=from_id, rel_type=old_rel, to_node_id=to_id
        ).delete(synchronize_session=False)
        exists = (
            db.query(models.GraphRelation.id)
            .filter_by(from_node_id=from_id, rel_type=new_rel, to_node_id=to_id)
            .first()
        )
        if not exists:
            db.add(
                models.GraphRelation(
                    from_node_id=from_id,
                    rel_type=new_rel,
                    to_node_id=to_id,
                    created_by=current_user.id,
                )
            )
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"[graph] 관계 PG 변경 실패: {e}")
        raise HTTPException(status_code=500, detail="관계 변경에 실패했습니다.")

    # 2) Neo4j 동기화 (비치명적)
    try:
        await _run_cypher(
            f"MATCH (a {{id: $from_id}})-[r:`{old_rel}`]->(b {{id: $to_id}}) DELETE r",
            {"from_id": from_id, "to_id": to_id},
        )
        await _run_cypher(
            f"MATCH (a {{id: $from_id}}), (b {{id: $to_id}}) MERGE (a)-[:`{new_rel}`]->(b)",
            {"from_id": from_id, "to_id": to_id},
        )
    except Exception as e:
        logger.warning(f"[graph] 관계 Neo4j 변경 동기화 실패(PG는 변경됨): {e}")
    return {"ok": True}


@router.post("/meeting-groups")
async def create_meeting_group(
    data: dict, current_user: models.User = Depends(get_current_user)
):
    """Meetings 노드 생성 및 Company에 연결"""
    mg_id = data.get("id", "")
    title = data.get("title", "")
    meeting_type = data.get("meeting_type", "")
    description = data.get("description", data.get("purpose", ""))
    org_id = data.get("org_id", "")
    # 간사 연결은 호출자 본인(pg_id) 기준 — email/name 페이로드 매칭 제거 (SEC-12)
    try:
        await _run_cypher(
            """
            MERGE (mg:Meetings {id: $id})
            SET mg.title = $title, mg.meeting_type = $meeting_type,
                mg.description = $description, mg.status = 'active'
            """,
            {
                "id": mg_id,
                "title": title,
                "meeting_type": meeting_type,
                "description": description,
            },
        )
        if org_id:
            await _run_cypher(
                "MATCH (mg:Meetings {id: $mg_id}), (o:Company {id: $org_id}) MERGE (mg)-[:`포함`]->(o)",
                {"mg_id": mg_id, "org_id": org_id},
            )
        await _run_cypher(
            """
            MATCH (mg:Meetings {id: $mg_id})
            MATCH (p:User {pg_id: $pg_id})
            MERGE (p)-[:`운영`]->(mg)
            """,
            {"mg_id": mg_id, "pg_id": current_user.id},
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Neo4j 연결 실패: {str(e)}")
    return {"ok": True}


@router.put("/meeting-groups/{mg_id}")
async def update_meeting_group(
    mg_id: str, data: dict, current_user: models.User = Depends(get_current_user)
):
    """Meetings 노드 속성 수정"""
    fields = {
        k: v
        for k, v in data.items()
        if k in ("title", "purpose", "guidelines", "status", "meeting_type")
    }
    if not fields:
        return {"ok": True}
    set_clause = ", ".join(f"mg.{k} = ${k}" for k in fields)
    try:
        await _run_cypher(
            f"MATCH (mg:Meetings {{id: $mg_id}}) SET {set_clause}",
            {"mg_id": mg_id, **fields},
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Neo4j 연결 실패: {str(e)}")
    return {"ok": True}


@router.delete("/meeting-groups/{mg_id}")
async def delete_meeting_group(
    mg_id: str, current_user: models.User = Depends(get_current_user)
):
    """Meetings 노드 및 연결 관계 삭제"""
    try:
        await _run_cypher(
            "MATCH (mg:Meetings {id: $mg_id}) DETACH DELETE mg",
            {"mg_id": mg_id},
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Neo4j 연결 실패: {str(e)}")
    return {"ok": True}


@router.post("/meeting-groups/{mg_id}/members")
async def add_member_to_group(
    mg_id: str, data: dict, current_user: models.User = Depends(get_current_user)
):
    """User → Meetings 멤버 관계 추가"""
    user_id = data.get("user_id")
    if not user_id:
        raise HTTPException(status_code=400, detail="user_id가 필요합니다.")
    role = data.get("role", "member")  # admin | member
    rel = "간사" if role == "admin" else "구성원"
    try:
        await _run_cypher(
            f"""
            MATCH (mg:Meetings {{id: $mg_id}})
            MATCH (p:User {{pg_id: $pg_id}})
            MERGE (p)-[:`{rel}`]->(mg)
            """,
            {"mg_id": mg_id, "pg_id": int(user_id)},
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Neo4j 연결 실패: {str(e)}")
    return {"ok": True}


@router.delete("/meeting-groups/{mg_id}/members")
async def remove_member_from_group(
    mg_id: str, data: dict, current_user: models.User = Depends(get_current_user)
):
    """User → Meetings 멤버 관계 삭제"""
    user_id = data.get("user_id")
    if not user_id:
        raise HTTPException(status_code=400, detail="user_id가 필요합니다.")
    try:
        await _run_cypher(
            """
            MATCH (p:User {pg_id: $pg_id})-[r:`운영`|`참여`]->(mg:Meetings {id: $mg_id})
            DELETE r
            """,
            {"mg_id": mg_id, "pg_id": int(user_id)},
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Neo4j 연결 실패: {str(e)}")
    return {"ok": True}


@router.post("/sessions")
async def create_session_node(
    data: dict, current_user: models.User = Depends(get_current_user)
):
    """Session 노드 생성 및 Meetings에 연결"""
    s_id = data.get("id", "")
    title = data.get("title", "")
    session_number = data.get("session_number", 1)
    session_type = data.get("session_type", "정기")
    description = data.get("description", "")
    date = data.get("date", "")
    mg_id = data.get("mg_id", "")
    try:
        await _run_cypher(
            """
            MERGE (s:Session {id: $id})
            SET s.title = $title, s.session_number = $session_number,
                s.session_type = $session_type, s.description = $description,
                s.date = $date
            """,
            {
                "id": s_id,
                "title": title,
                "session_number": session_number,
                "session_type": session_type,
                "description": description,
                "date": date,
            },
        )
        if mg_id:
            await _run_cypher(
                "MATCH (s:Session {id: $s_id}), (mg:Meetings {id: $mg_id}) MERGE (s)-[:`소속`]->(mg)",
                {"s_id": s_id, "mg_id": mg_id},
            )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Neo4j 연결 실패: {str(e)}")
    return {"ok": True}


@router.post("/agendas")
async def create_agenda_node(
    data: dict, current_user: models.User = Depends(get_current_user)
):
    """Agenda 노드 생성 및 Meetings에 연결"""
    ag_id = data.get("id", "")
    content = data.get("content", "")
    category = data.get("category", "")
    priority = data.get("priority", "low")
    status = data.get("status", "pending")
    due_date = data.get("due_date", "")
    mg_id = data.get("mg_id", "")
    assignee_name = data.get("assignee_name", "")
    # Draft는 PostgreSQL에만 보관 — Neo4j 연동 안 함 (기존 노드 있으면 제거)
    if (status or "").strip().lower() == "draft":
        try:
            await _run_cypher(
                "MATCH (ag:Agenda {id: $id}) DETACH DELETE ag", {"id": ag_id}
            )
        except Exception:
            pass
        return {"ok": True, "skipped": "draft"}
    try:
        await _run_cypher(
            """
            MERGE (ag:Agenda {id: $id})
            SET ag.title = $content, ag.category = $category,
                ag.priority = $priority, ag.status = $status,
                ag.due_date = $due_date,
                ag.created_at = datetime()
            """,
            {
                "id": ag_id,
                "content": content,
                "category": category,
                "priority": priority,
                "status": status,
                "due_date": due_date,
            },
        )
        if mg_id:
            await _run_cypher(
                "MATCH (ag:Agenda {id: $ag_id}), (mg:Meetings {id: $mg_id}) MERGE (ag)-[:`관할`]->(mg)",
                {"ag_id": ag_id, "mg_id": mg_id},
            )
        if assignee_name:
            await _run_cypher(
                "MATCH (ag:Agenda {id: $ag_id}), (p:User {name: $name}) MERGE (p)-[:`담당`]->(ag)",
                {"ag_id": ag_id, "name": assignee_name},
            )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Neo4j 연결 실패: {str(e)}")
    return {"ok": True}


@router.patch("/agendas/{ag_id}")
async def update_agenda_node(
    ag_id: str, data: dict, current_user: models.User = Depends(get_current_user)
):
    """Agenda 노드 속성 수정"""
    allowed = ("content", "category", "priority", "status", "due_date", "description")
    fields = {k: v for k, v in data.items() if k in allowed}
    if not fields:
        return {"ok": True}
    # Draft로 전환되면 PostgreSQL에만 보관 — Neo4j 노드 제거
    if (fields.get("status") or "").strip().lower() == "draft":
        try:
            await _run_cypher(
                "MATCH (ag:Agenda {id: $ag_id}) DETACH DELETE ag", {"ag_id": ag_id}
            )
        except Exception:
            pass
        return {"ok": True, "skipped": "draft"}
    # content → title (Neo4j 스키마)
    if "content" in fields:
        fields["title"] = fields.pop("content")
    set_clause = ", ".join(f"ag.{k} = ${k}" for k in fields)
    try:
        await _run_cypher(
            f"MATCH (ag:Agenda {{id: $ag_id}}) SET {set_clause}",
            {"ag_id": ag_id, **fields},
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Neo4j 연결 실패: {str(e)}")
    return {"ok": True}
