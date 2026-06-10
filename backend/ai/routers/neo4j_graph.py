import os
import asyncio
import base64
import httpx
import re
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session

import models
from auth import get_current_user
from database import get_db

router = APIRouter(prefix="/api/neo4j", tags=["neo4j"])

NEO4J_URL = os.environ["NEO4J_URL"]
NEO4J_USER = os.environ["NEO4J_USER"]
NEO4J_PASSWORD = os.environ["NEO4J_PASSWORD"]
NEO4J_DB = os.environ["NEO4J_DATABASE"]

ALLOWED_LABELS = {"Meetings", "User", "Department", "Agenda", "Report", "Minutes", "Session", "Company"}
ALLOWED_REL_TYPES = {
    "소속", "참여", "간사", "구성원", "포함",
    "관할", "담당", "첨부", "제출",
    "개최", "도출", "산출", "근거", "원인",
    "추천", "참조", "후속", "다룸멌", "판단",
    # 프론트 자유 관계 타입
    "연결", "협업", "공유", "지원", "검토", "상위", "관련", "후속회의", "출처", "생성", "세션출처",
}


def _cypher_endpoint():
    url = NEO4J_URL
    if url.startswith(("bolt://", "neo4j://")):
        url = re.sub(r"^bolt://|^neo4j://", "http://", url)
        url = re.sub(r":7687(?=$|/)", ":7474", url)
    return f"{url.rstrip('/')}/db/{NEO4J_DB}/tx/commit"


def _auth_header():
    creds = base64.b64encode(f"{NEO4J_USER}:{NEO4J_PASSWORD}".encode()).decode()
    return {
        "Authorization": f"Basic {creds}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


# ── 공유 커넥션 풀 (요청마다 TCP 재연결 방지) ─────────────────
_http_client: httpx.AsyncClient | None = None

def _get_http_client() -> httpx.AsyncClient:
    global _http_client
    if _http_client is None or _http_client.is_closed:
        _http_client = httpx.AsyncClient(
            timeout=10.0,
            limits=httpx.Limits(max_connections=10, max_keepalive_connections=5),
        )
    return _http_client


async def _run_cypher(statement: str, parameters: dict | None = None) -> list[dict]:
    stmt_obj: dict = {"statement": statement}
    if parameters:
        stmt_obj["parameters"] = parameters
    client = _get_http_client()
    resp = await client.post(
        _cypher_endpoint(),
        json={"statements": [stmt_obj]},
        headers=_auth_header(),
    )
    resp.raise_for_status()
    body = resp.json()
    if body.get("errors"):
        raise HTTPException(status_code=500, detail=body["errors"])
    result = body["results"][0] if body.get("results") else {"columns": [], "data": []}
    columns = result["columns"]
    return [dict(zip(columns, row["row"])) for row in result["data"]]


@router.get("/archive")
async def get_archive(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """인증된 사용자의 소속 회의체만 반환 — Neo4j 기반, Postgres는 meeting_id 보완에만 사용."""
    user_email = current_user.email or ""
    user_name  = current_user.name  or ""

    # ── Postgres: 현재 유저의 소속 meeting_id 목록 (빠른 단순 조회) ──
    pg_meeting_ids = {
        f"mg-{row.meeting_id}"
        for row in db.query(models.MeetingMember.meeting_id)
                     .filter(models.MeetingMember.user_id == current_user.id)
                     .all()
    }

    # ── Step 1+2: User 조회 / org / dept — 동시에 시작 ─────────
    # User 결과가 나와야 allowed_mg 쿼리를 보낼 수 있으므로,
    # User 는 별도 태스크로 먼저 쏘고 org/dept 와 concurrently 대기한다.
    try:
        person_rows, org_rows, dept_rows = await asyncio.gather(
            _run_cypher(
                "MATCH (p:User) WHERE p.email = $email OR p.name = $name "
                "RETURN coalesce(p.id, toString(p.pg_id)) AS pid, p.name AS pname",
                {"email": user_email, "name": user_name},
            ),
            _run_cypher(
                "MATCH (o:Company) RETURN o.id AS id, o.name AS name LIMIT 1"
            ),
            _run_cypher(
                "MATCH (d:Department) RETURN d.id AS id, d.name AS name, d.code AS code ORDER BY d.name"
            ),
        )
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Neo4j 연결 실패: {str(e)}")

    # ── Step 2: 소속 회의체 ID 조회 ──────────────────────────────
    try:
        if person_rows:
            person_id = person_rows[0]["pid"]
            allowed_rows = await _run_cypher(
                """
                MATCH (p:User)-[:`간사`|`구성원`]->(mg)
                WHERE (p.id = $pid OR toString(p.pg_id) = $pid)
                  AND (mg:Meetings OR mg:Meeting_session)
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
            "meetings": [], "minutes": [], "reports": [],
            "departments": dept_rows,
            "org": org_rows[0] if org_rows else None,
            "current_person": current_person,
        }

    # ── Step 3: 회의체 상세 데이터 4종 — 병렬 조회 ───────────────
    mg_ids_list = list(allowed_mg_ids)
    try:
        mg_rows, agenda_rows, session_rows, report_rows = await asyncio.gather(
            _run_cypher(
                """
                MATCH (mg) WHERE (mg:Meetings OR mg:Meeting_session)
                  AND mg.id IN $ids
                OPTIONAL MATCH (p:User)-[rel:`간사`|`구성원`|`참여`]->(mg)
                OPTIONAL MATCH (p)-[:`소속`|`소속부서`]->(d:Department)
                RETURN
                    mg.id AS mg_id,
                    coalesce(mg.title, '') AS title,
                    coalesce(mg.meeting_type, mg.type) AS meeting_type,
                    coalesce(mg.status, 'active') AS status,
                    coalesce(mg.description, mg.purpose, '') AS purpose,
                    coalesce(mg.guidelines, '') AS guidelines,
                    mg.start_date AS start_date,
                    mg.end_date AS end_date,
                    coalesce(p.id, toString(p.pg_id)) AS person_id,
                    p.name AS person_name, p.email AS email,
                    p.position AS position, type(rel) AS role, rel.role AS rel_role,
                    coalesce(d.name, p.department, '') AS department
                ORDER BY mg_id
                """,
                {"ids": mg_ids_list},
            ),
            _run_cypher(
                """
                MATCH (ag:Agenda)-[:`관할`]->(mg)
                WHERE (mg:Meetings OR mg:Meeting_session)
                  AND mg.id IN $ids
                OPTIONAL MATCH (p:User)-[:`담당`]->(ag)
                OPTIONAL MATCH (p)-[:`소속`|`소속부서`]->(d:Department)
                RETURN
                    mg.id AS meetingId,
                    coalesce(ag.id, toString(ag.pg_id)) AS id,
                    coalesce(ag.title, ag.content) AS content,
                    ag.description AS description, ag.category AS category,
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
                MATCH (s:Session)-[:`개최`|`소속`]->(mg)
                WHERE (mg:Meetings OR mg:Meeting_session)
                  AND mg.id IN $ids
                OPTIONAL MATCH (s)-[:`산출`]->(doc) WHERE doc:Report OR doc:Minutes
                OPTIONAL MATCH (mn:Minutes)-[:`생성`]->(s)
                OPTIONAL MATCH (u:User)-[:참석]->(s)
                WITH mg, s, doc, mn,
                     collect(CASE WHEN u IS NOT NULL THEN {userId: u.pg_id, userName: u.name, department: u.department} END) AS participants
                RETURN
                    mg.id AS meetingId,
                    coalesce(mg.title, '') AS meetingTitle,
                    coalesce(s.id, toString(s.pg_id)) AS id,
                    s.title AS session_title,
                    s.session_number AS session_number,
                    toString(coalesce(s.date, s.scheduled_at)) AS date,
                    toString(s.started_at) AS started_at,
                    s.session_type AS session_type,
                    s.description AS description,
                    s.location AS location,
                    s.status AS session_status,
                    toString(s.ended_at) AS ended_at,
                    doc.file_name AS file_name, doc.id AS doc_id,
                    doc.title AS doc_title, doc.doc_type AS doc_type,
                    doc.author AS doc_author,
                    toString(doc.created_at) AS doc_created_at,
                    mn.content_summary AS content_summary,
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
                MATCH (doc:Report)-[:`첨부`]->(mg)
                WHERE (mg:Meetings OR mg:Meeting_session)
                  AND mg.id IN $ids
                OPTIONAL MATCH (dept:Department)-[:`제출`]->(doc)
                OPTIONAL MATCH (doc)-[:`첨부`]->(ag:Agenda)
                RETURN
                    mg.id AS meetingId,
                    coalesce(mg.title, '') AS meetingTitle,
                    doc.id AS id, doc.title AS title,
                    doc.file_name AS file_name, doc.doc_type AS doc_type,
                    doc.author AS author, doc.file_url AS file_url,
                    coalesce(toString(doc.created_at), toString(doc.uploaded_at)) AS submitted_at,
                    coalesce(dept.name, '') AS department,
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
                "start_date": row.get("start_date"),
                "end_date": row.get("end_date"),
                "members": [], "tasks": [], "minutes": [], "reports": [],
                "minutes_agendas": [], "session_agendas": [], "derivations": [], "human_judgments": [],
            }
        if row.get("person_id"):
            mg = meetings_map[mg_id]
            if not any(m["userId"] == row["person_id"] for m in mg["members"]):
                mg["members"].append({
                    "meetingId": mg_id,
                    "userId": row["person_id"],
                    "userName": row.get("person_name", "?"),
                    "email": row.get("email", ""),
                    "position": row.get("position", ""),
                    "role": "admin" if row.get("role") == "간사" or row.get("rel_role") == "admin" else "member",
                    "department": row.get("department") or "",
                })

    # 동일 Agenda에 담당 관계가 여러 개면 중복 row가 생기므로 id 기준으로 병합
    agenda_map: dict[str, dict] = {}
    for row in agenda_rows:
        mg_id = row.get("meetingId")
        ag_id = row.get("id")
        if not mg_id or mg_id not in meetings_map or not ag_id:
            continue
        if ag_id not in agenda_map:
            agenda_map[ag_id] = {
                "id": ag_id, "meetingId": mg_id,
                "content": row.get("content", ""),
                "description": row.get("description", ""),
                "category": row.get("category"),
                "priority": row.get("priority", "low"),
                "status": row.get("status", "pending"),
                "due_date": row.get("due_date"),
                "created_at": row.get("created_at"),
                "ai_evidence": row.get("ai_evidence"),
                "assignee_names": [],   # 담당자 여러 명 지원
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
        if mg_id and mg_id in meetings_map and session_id not in seen_sessions:
            seen_sessions.add(session_id)
            meetings_map[mg_id]["minutes"].append({
                "id": session_id, "meeting_id": mg_id,
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
                "minutes_file_name": row.get("minutes_file_name"),
                "minutes_status": row.get("minutes_status"),
                "minutes_pg_id": row.get("minutes_pg_id"),
                "generated_at": row.get("generated_at"),
                "participants": row.get("participants", []),
            })

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
        meetings_map[mg_id]["reports"].append({
            "id": pg_id, "meeting_id": mg_id,
            "meeting_title": row.get("meetingTitle", ""),
            "title": row.get("title", ""),
            "file_name": row.get("file_name", ""),
            "doc_type": row.get("doc_type", ""),
            "author": row.get("author"),
            "file_url": row.get("file_url"),
            "submitted_at": row.get("submitted_at"),
            "department": row.get("department", ""),
            "related_todo_id": row.get("related_todo_id"),
        })

    # ── 회의 생명주기: Minutes→Agenda(도출) + Session→Agenda(다룸멌) + Session→Agenda(도출 이월) 조회 ──
    try:
        mn_ag_rows, sess_ag_rows, deriv_rows = await asyncio.gather(
            _run_cypher(
                """
                MATCH (mn:Minutes)-[:`생성`]->(s:Session)-[:`진행`|`다룸멌`|`도출`]->(ag:Agenda)-[:`관할`]->(mg)
                WHERE (mg:Meetings OR mg:Meeting_session) AND mg.id IN $ids
                RETURN mg.id AS meetingId,
                       coalesce(s.id, toString(s.pg_id)) AS session_id,
                       coalesce(ag.id, toString(ag.pg_id)) AS agenda_id
                """,
                {"ids": mg_ids_list},
            ),
            _run_cypher(
                """
                MATCH (s:Session)-[:`다룸멌`|`진행`]->(ag:Agenda)-[:`관할`]->(mg)
                WHERE (mg:Meetings OR mg:Meeting_session) AND mg.id IN $ids
                RETURN mg.id AS meetingId,
                       coalesce(s.id, toString(s.pg_id)) AS session_id,
                       coalesce(ag.id, toString(ag.pg_id)) AS agenda_id
                """,
                {"ids": mg_ids_list},
            ),
            _run_cypher(
                """
                MATCH (s:Session)-[:`도출`]->(ag:Agenda)-[:`관할`]->(mg)
                WHERE (mg:Meetings OR mg:Meeting_session) AND mg.id IN $ids
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
                meetings_map[mg_id]["minutes_agendas"].append({
                    "session_id": row.get("session_id"),
                    "agenda_id": row.get("agenda_id"),
                })
        for row in sess_ag_rows:
            mg_id = row.get("meetingId")
            if mg_id in meetings_map:
                meetings_map[mg_id]["session_agendas"].append({
                    "session_id": row.get("session_id"),
                    "agenda_id": row.get("agenda_id"),
                })
        for row in deriv_rows:
            mg_id = row.get("meetingId")
            if mg_id in meetings_map:
                meetings_map[mg_id]["derivations"].append({
                    "session_id": row.get("session_id"),
                    "agenda_id": row.get("agenda_id"),
                })
    except Exception:
        pass  # 생명주기 데이터 없어도 메인 그래프는 정상 반환

    # ── Postgres 보완: 모든 회의체의 reports를 PostgreSQL에서 채움 ──
    all_raw_ids = [int(mid.replace("mg-", "")) for mid in meetings_map.keys() if mid.replace("mg-", "").isdigit()]
    if all_raw_ids:
        rows = (
            db.query(models.Report, models.HitlReview, models.ReportScore)
            .outerjoin(
                models.HitlReview,
                (models.HitlReview.target_type == "report") &
                (models.HitlReview.target_id == models.Report.id),
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
            sid = f"mg-{r.meeting_id}"
            if sid not in meetings_map:
                continue
            meetings_map[sid]["reports"].append({
                "id": r.id,
                "meetingId": sid,
                "file_name": r.file_name,
                "file_path": r.file_path,
                "human_status": r.human_status,
                "version": r.version,
                "parent_id": r.parent_id,
                "submitter_department": r.submitter_department,
                "created_at": r.created_at.isoformat() + 'Z' if r.created_at else None,
                "reviewed_at": hr.reviewed_at.isoformat() + 'Z' if hr and hr.reviewed_at else None,
                "related_agenda_ids": r.related_agenda_ids or [],
                "ai_status": rs.ai_status if rs else None,
                "score": rs.total_score if rs else None,
                "total_score": rs.total_score if rs else None,
                "detail_scores": rs.detail_scores if rs else None,
                "feedback": rs.feedback if rs else None,
                "score_created_at": rs.created_at.isoformat() + 'Z' if rs and rs.created_at else None,
            })

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
                "session_title":    s.title or "",
                "description":      s.description or "",
                "location":         s.location or "",
                "session_type":     str(s.type) if s.type else "",
                "date":             s.scheduled_at.isoformat() + 'Z' if s.scheduled_at else "",
                "started_at":       s.started_at.isoformat() + 'Z' if s.started_at else "",
                "ended_at":         s.ended_at.isoformat() + 'Z' if s.ended_at else "",
                "session_status":   s.status or "",
                "content_summary":  mn.content_summary if mn else "",
                "minutes_file_name": mn.file_name if mn else "",
                "minutes_status":   mn.status if mn else "",
                "generated_at":     mn.generated_at.isoformat() + 'Z' if mn and mn.generated_at else "",
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

    # ── HumanJudgment (의사결정) 노드 조회 ────────────────────────
    try:
        hj_rows = await _run_cypher(
            """
            MATCH (hj:HumanJudgment)
            WHERE hj.target_type = 'agenda'
            MATCH (ag:Agenda)-[:`관할`]->(mg)
            WHERE mg.id IN $ids AND ag.pg_id = hj.target_id
            RETURN
                mg.id AS meetingId,
                hj.id AS id,
                hj.pg_id AS pg_id,
                hj.judgment AS judgment,
                hj.reason AS reason,
                hj.target_id AS target_id,
                coalesce(ag.id, toString(ag.pg_id)) AS agenda_id,
                toString(hj.judged_at) AS judged_at,
                hj.version AS version
            """,
            {"ids": mg_ids_list},
        )
        seen_hj: set[str] = set()
        for row in hj_rows:
            mg_id = row.get("meetingId")
            hj_id = row.get("id")
            if not mg_id or mg_id not in meetings_map or not hj_id:
                continue
            if hj_id in seen_hj:
                continue
            seen_hj.add(hj_id)
            meetings_map[mg_id]["human_judgments"].append({
                "id":        hj_id,
                "pg_id":     row.get("pg_id"),
                "judgment":  row.get("judgment"),
                "reason":    row.get("reason") or "",
                "target_id": row.get("target_id"),
                "agenda_id": row.get("agenda_id"),
                "judged_at": row.get("judged_at"),
                "version":   row.get("version"),
            })
    except Exception:
        pass  # HumanJudgment 없어도 그래프 정상 반환

    # ── Postgres 보완: Neo4j 미동기 신규 회의체 (기본 정보만) ──────
    missing_pg_ids = pg_meeting_ids - meetings_map.keys()
    if missing_pg_ids:
        raw_ids = [int(mid.replace("mg-", "")) for mid in missing_pg_ids if mid.replace("mg-", "").isdigit()]
        pg_meetings = db.query(models.Meeting).filter(models.Meeting.id.in_(raw_ids)).all()
        for m in pg_meetings:
            sid = f"mg-{m.id}"
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
                "start_date": m.start_date.isoformat() + 'Z' if m.start_date else None,
                "end_date": m.end_date.isoformat() + 'Z' if m.end_date else None,
                "members": [
                    {
                        "meetingId": sid, "userId": f"user-{u.id}",
                        "userName": u.name or "", "email": u.email or "",
                        "position": u.position or "",
                        "role": "admin" if str(mb.role) == "admin" else "presenter",
                        "department": u.department or "",
                    }
                    for mb, u in members_db
                ],
                "tasks": [], "minutes": [],
                "reports": [
                    {
                        "id": r.id,
                        "meetingId": sid,
                        "file_name": r.file_name,
                        "file_path": r.file_path,
                        "human_status": r.human_status,
                        "submitter_department": r.submitter_department,
                        "created_at": r.created_at.isoformat() + 'Z' if r.created_at else None,
                        "related_agenda_ids": r.related_agenda_ids or [],
                    }
                    for r in db.query(models.Report).filter(
                        models.Report.meeting_id == m.id,
                    ).all()
                ],
            }

    meetings = list(meetings_map.values())
    minutes  = [mn for mg in meetings for mn in mg["minutes"]]
    reports  = [r  for mg in meetings for r  in mg["reports"]]

    current_person = {
        "id":         person_rows[0]["pid"]   if person_rows else f"user-{current_user.id}",
        "name":       person_rows[0]["pname"] if person_rows else current_user.name,
        "email":      user_email,
        "position":   current_user.position   or "",
        "department": current_user.department or "",
    }

    return {
        "meetings": meetings,
        "minutes":  minutes,
        "reports":  reports,
        "departments": dept_rows,
        "org":         org_rows[0] if org_rows else None,
        "current_person": current_person,
    }

@router.post("/relationships")
async def create_relationship(data: dict):
    from_id = data.get("from_id", "")
    rel_type = data.get("rel_type", "")
    to_id = data.get("to_id", "")
    if not rel_type:
        raise HTTPException(status_code=400, detail="rel_type 필수")
    # Cypher 관계 타입: 영문/숫자/밑줄만 허용 (한국어는 백틱으로 감싸기)
    import re
    safe_rel = rel_type if re.match(r'^[A-Za-z_][A-Za-z0-9_]*$', rel_type) else None
    if not safe_rel:
        # 한국어 등 특수문자 관계명은 ALLOWED_REL_TYPES 내에 있어야 함
        if rel_type not in ALLOWED_REL_TYPES:
            raise HTTPException(status_code=400, detail=f"허용되지 않는 관계 유형: {rel_type}")
        safe_rel = rel_type
    try:
        await _run_cypher(
            f"MATCH (a {{id: $from_id}}), (b {{id: $to_id}}) MERGE (a)-[:`{safe_rel}`]->(b)",
            {"from_id": from_id, "to_id": to_id},
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Neo4j 연결 실패: {str(e)}")
    return {"ok": True}


@router.delete("/relationships")
async def delete_relationship(data: dict):
    """두 노드 사이의 특정 관계 삭제"""
    from_id = data.get("from_id", "")
    rel_type = data.get("rel_type", "")
    to_id = data.get("to_id", "")

    # ID 이중 prefix 정규화: "mg-mg-001" → "mg-001"
    def normalize_id(raw: str) -> str:
        for p in ["mg-", "session-", "agenda-", "doc-", "dept-", "p-", "org-"]:
            if raw.startswith(p + p):
                return raw[len(p):]
        return raw

    from_id = normalize_id(from_id)
    to_id = normalize_id(to_id)

    # rel_type이 없거나 허용되지 않으면 타입 무관 전체 삭제
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
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Neo4j 연결 실패: {str(e)}")
    return {"ok": True}


@router.put("/relationships")
async def update_relationship(data: dict):
    """관계 유형 변경 (old → new)"""
    from_id = data.get("from_id", "")
    old_rel = data.get("old_rel", "")
    new_rel = data.get("new_rel", "")
    to_id = data.get("to_id", "")
    if old_rel not in ALLOWED_REL_TYPES or new_rel not in ALLOWED_REL_TYPES:
        raise HTTPException(status_code=400, detail="허용되지 않는 관계 유형")
    try:
        await _run_cypher(
            f"MATCH (a {{id: $from_id}})-[r:`{old_rel}`]->(b {{id: $to_id}}) DELETE r",
            {"from_id": from_id, "to_id": to_id},
        )
        await _run_cypher(
            f"MATCH (a {{id: $from_id}}), (b {{id: $to_id}}) MERGE (a)-[:`{new_rel}`]->(b)",
            {"from_id": from_id, "to_id": to_id},
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Neo4j 연결 실패: {str(e)}")
    return {"ok": True}


@router.post("/meeting-groups")
async def create_meeting_group(data: dict):
    """Meetings 노드 생성 및 Company에 연결"""
    mg_id = data.get("id", "")
    title = data.get("title", "")
    meeting_type = data.get("meeting_type", "")
    description = data.get("description", data.get("purpose", ""))
    org_id = data.get("org_id", "")
    creator_name = data.get("creator_name", "")
    creator_email = data.get("creator_email", "")
    try:
        await _run_cypher(
            """
            MERGE (mg:Meetings {id: $id})
            SET mg.title = $title, mg.meeting_type = $meeting_type,
                mg.description = $description, mg.status = 'active'
            """,
            {"id": mg_id, "title": title, "meeting_type": meeting_type, "description": description},
        )
        if org_id:
            await _run_cypher(
                "MATCH (mg:Meetings {id: $mg_id}), (o:Company {id: $org_id}) MERGE (mg)-[:`포함`]->(o)",
                {"mg_id": mg_id, "org_id": org_id},
            )
        if creator_email or creator_name:
            await _run_cypher(
                """
                MATCH (mg:Meetings {id: $mg_id})
                MATCH (p:User) WHERE p.email = $email OR p.name = $name
                MERGE (p)-[:`간사`]->(mg)
                """,
                {"mg_id": mg_id, "email": creator_email, "name": creator_name},
            )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Neo4j 연결 실패: {str(e)}")
    return {"ok": True}


@router.put("/meeting-groups/{mg_id}")
async def update_meeting_group(mg_id: str, data: dict):
    """Meetings 노드 속성 수정"""
    fields = {k: v for k, v in data.items() if k in ("title", "purpose", "guidelines", "status", "meeting_type")}
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
async def delete_meeting_group(mg_id: str):
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
async def add_member_to_group(mg_id: str, data: dict):
    """User → Meetings 멤버 관계 추가"""
    person_name = data.get("name", "")
    person_email = data.get("email", "")
    role = data.get("role", "member")  # admin | member
    rel = "간사" if role == "admin" else "구성원"
    try:
        await _run_cypher(
            f"""
            MATCH (mg:Meetings {{id: $mg_id}})
            MATCH (p:User) WHERE p.email = $email OR p.name = $name
            MERGE (p)-[:`{rel}`]->(mg)
            """,
            {"mg_id": mg_id, "email": person_email, "name": person_name},
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Neo4j 연결 실패: {str(e)}")
    return {"ok": True}


@router.delete("/meeting-groups/{mg_id}/members")
async def remove_member_from_group(mg_id: str, data: dict):
    """User → Meetings 멤버 관계 삭제"""
    person_name = data.get("name", "")
    person_email = data.get("email", "")
    try:
        await _run_cypher(
            """
            MATCH (p:User)-[r:`간사`|`구성원`]->(mg:Meetings {id: $mg_id})
            WHERE p.email = $email OR p.name = $name
            DELETE r
            """,
            {"mg_id": mg_id, "email": person_email, "name": person_name},
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Neo4j 연결 실패: {str(e)}")
    return {"ok": True}


@router.post("/sessions")
async def create_session_node(data: dict):
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
            {"id": s_id, "title": title, "session_number": session_number,
             "session_type": session_type, "description": description, "date": date},
        )
        if mg_id:
            await _run_cypher(
                "MATCH (s:Session {id: $s_id}), (mg:Meetings {id: $mg_id}) MERGE (s)-[:`개최`]->(mg)",
                {"s_id": s_id, "mg_id": mg_id},
            )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Neo4j 연결 실패: {str(e)}")
    return {"ok": True}


@router.post("/agendas")
async def create_agenda_node(data: dict):
    """Agenda 노드 생성 및 Meetings에 연결"""
    ag_id = data.get("id", "")
    content = data.get("content", "")
    category = data.get("category", "")
    priority = data.get("priority", "low")
    status = data.get("status", "pending")
    due_date = data.get("due_date", "")
    mg_id = data.get("mg_id", "")
    assignee_name = data.get("assignee_name", "")
    try:
        await _run_cypher(
            """
            MERGE (ag:Agenda {id: $id})
            SET ag.title = $content, ag.category = $category,
                ag.priority = $priority, ag.status = $status,
                ag.due_date = $due_date,
                ag.created_at = datetime()
            """,
            {"id": ag_id, "content": content, "category": category,
             "priority": priority, "status": status, "due_date": due_date},
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
async def update_agenda_node(ag_id: str, data: dict):
    """Agenda 노드 속성 수정"""
    allowed = ("content", "category", "priority", "status", "due_date", "description")
    fields = {k: v for k, v in data.items() if k in allowed}
    if not fields:
        return {"ok": True}
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

