import os
import base64
import httpx
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session

import models
from auth import get_current_user
from database import get_db

router = APIRouter(prefix="/api/neo4j", tags=["neo4j"])

NEO4J_URL = os.getenv("NEO4J_URL", "http://localhost:7474")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "neo4j")
NEO4J_DB = os.getenv("NEO4J_DATABASE", "neo4j")

ALLOWED_LABELS = {"MeetingGroup", "Person", "Department", "Agenda", "Document", "Session"}
ALLOWED_REL_TYPES = {
    "BELONGS_TO", "PARTICIPATES_IN", "ADMIN_OF", "MEMBER_OF", "PART_OF",
    "OWNED_BY", "ASSIGNED_TO", "ATTACHED_TO", "SUBMITTED",
    "HELD_BY", "COVERS", "PRODUCED", "BASED_ON", "CAUSED_BY",
    "RECOMMENDED", "REFERENCES", "FOLLOWED_BY",
    # 프론트 자유 관계 타입 (한국어 포함)
    "참여", "관련", "연결", "포함", "협업", "공유", "지원", "검토",
}


def _cypher_endpoint():
    return f"{NEO4J_URL}/db/{NEO4J_DB}/tx/commit"


def _auth_header():
    creds = base64.b64encode(f"{NEO4J_USER}:{NEO4J_PASSWORD}".encode()).decode()
    return {
        "Authorization": f"Basic {creds}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


async def _run_cypher(statement: str, parameters: dict | None = None) -> list[dict]:
    stmt_obj: dict = {"statement": statement}
    if parameters:
        stmt_obj["parameters"] = parameters
    async with httpx.AsyncClient(timeout=10.0) as client:
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
    """인증된 사용자의 소속 회의체만 반환. Neo4j Person에 없으면 빈 결과."""
    try:
        # ── 현재 사용자가 속한 Neo4j 회의체 ID 조회 ──
        # email 또는 이름으로 Neo4j Person 매칭
        user_email = current_user.email or ""
        user_name = current_user.name or ""

        # Neo4j: pg_id 기반(새 sync) 또는 id 기반(시드 데이터) 모두 조회
        person_rows = await _run_cypher(
            "MATCH (p:Person) WHERE p.email = $email OR p.name = $name "
            "RETURN coalesce(p.id, toString(p.pg_id)) AS pid, p.name AS pname, p.pg_id AS pg_id",
            {"email": user_email, "name": user_name},
        )

        # admin 계정(position 기준)은 전체 조회
        is_admin = current_user.position in ("대표", "CEO", "임원")

        if person_rows:
            person_id = person_rows[0]["pid"]
            # ── :MeetingGroup (시드) + :Meeting (pg_id 방식, 신규 sync) 모두 조회 ──
            allowed_mg_ids_rows = await _run_cypher(
                """
                MATCH (p:Person)-[:ADMIN_OF|MEMBER_OF]->(mg)
                WHERE (p.id = $pid OR toString(p.pg_id) = $pid)
                  AND (mg:MeetingGroup OR mg:Meeting)
                RETURN coalesce(mg.id, 'mg-sqlite-' + toString(mg.pg_id)) AS mg_id
                """,
                {"pid": person_id},
            )
            allowed_mg_ids = {r["mg_id"] for r in allowed_mg_ids_rows}
        elif is_admin:
            # admin은 전체 회의체
            all_mg = await _run_cypher(
                "MATCH (mg) WHERE mg:MeetingGroup OR mg:Meeting "
                "RETURN coalesce(mg.id, 'mg-sqlite-' + toString(mg.pg_id)) AS mg_id"
            )
            allowed_mg_ids = {r["mg_id"] for r in all_mg}
        else:
            allowed_mg_ids = set()

        # SQLite 회의체도 항상 포함 (Neo4j background sync 전이어도 표시)
        sqlite_member_rows = db.query(models.MeetingMember).filter(
            models.MeetingMember.user_id == current_user.id
        ).all()
        for row in sqlite_member_rows:
            allowed_mg_ids.add(f"mg-sqlite-{row.meeting_id}")

        if not allowed_mg_ids:
            # 소속 회의체 없음 — 본인 노드만 반환
            return {
                "meetings": [],
                "minutes": [],
                "reports": [],
                "departments": [],
                "current_person": {
                    "id": f"user-{current_user.id}",
                    "name": current_user.name,
                    "email": current_user.email or "",
                    "position": current_user.position or "",
                    "department": current_user.department or "",
                },
            }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Neo4j 연결 실패: {str(e)}")

    try:
        mg_rows = await _run_cypher("""
            MATCH (mg) WHERE mg:MeetingGroup OR mg:Meeting
            OPTIONAL MATCH (p:Person)-[rel:ADMIN_OF|MEMBER_OF]->(mg)
            OPTIONAL MATCH (p)-[:BELONGS_TO]->(d:Department)
            RETURN
                coalesce(mg.id, 'mg-sqlite-' + toString(mg.pg_id)) AS mg_id,
                coalesce(mg.title, '') AS title,
                coalesce(mg.meeting_type, mg.type) AS meeting_type,
                coalesce(mg.status, 'active') AS status,
                mg.purpose AS purpose,
                coalesce(p.id, toString(p.pg_id)) AS person_id,
                p.name AS person_name, p.email AS email,
                p.position AS position, type(rel) AS role, d.name AS department
            ORDER BY mg_id
        """)

        agenda_rows = await _run_cypher("""
            MATCH (ag:Agenda)-[:OWNED_BY]->(mg)
            WHERE mg:MeetingGroup OR mg:Meeting
            OPTIONAL MATCH (p:Person)-[:ASSIGNED_TO]->(ag)
            OPTIONAL MATCH (p)-[:BELONGS_TO]->(d:Department)
            RETURN
                coalesce(mg.id, 'mg-sqlite-' + toString(mg.pg_id)) AS meetingId,
                coalesce(ag.id, toString(ag.pg_id)) AS id,
                coalesce(ag.title, ag.content) AS content,
                ag.description AS description, ag.category AS category,
                ag.priority AS priority, ag.status AS status,
                toString(ag.due_date) AS due_date,
                toString(ag.created_at) AS created_at,
                p.name AS assignee_name, coalesce(d.name, '') AS assignee_dept
        """)

        session_rows = await _run_cypher("""
            MATCH (s:Session)-[:HELD_BY|BELONGS_TO]->(mg)
            WHERE mg:MeetingGroup OR mg:Meeting
            OPTIONAL MATCH (s)-[:PRODUCED]->(doc:Document)
            RETURN
                coalesce(mg.id, 'mg-sqlite-' + toString(mg.pg_id)) AS meetingId,
                coalesce(mg.title, '') AS meetingTitle,
                coalesce(s.id, toString(s.pg_id)) AS id,
                s.title AS session_title,
                s.session_number AS session_number,
                toString(coalesce(s.date, s.scheduled_at)) AS date,
                s.session_type AS session_type,
                s.description AS description,
                toString(s.ended_at) AS ended_at,
                doc.file_name AS file_name, doc.id AS doc_id,
                doc.title AS doc_title, doc.doc_type AS doc_type,
                doc.author AS doc_author,
                toString(doc.created_at) AS doc_created_at
        """)

        report_rows = await _run_cypher("""
            MATCH (doc:Document)-[:ATTACHED_TO]->(mg)
            WHERE (mg:MeetingGroup OR mg:Meeting) AND NOT doc.doc_type = '회의록'
            OPTIONAL MATCH (dept:Department)-[:SUBMITTED]->(doc)
            RETURN
                coalesce(mg.id, 'mg-sqlite-' + toString(mg.pg_id)) AS meetingId,
                coalesce(mg.title, '') AS meetingTitle,
                doc.id AS id, doc.title AS title,
                doc.file_name AS file_name, doc.doc_type AS doc_type,
                doc.author AS author, doc.file_url AS file_url,
                coalesce(toString(doc.created_at), toString(doc.uploaded_at)) AS submitted_at,
                coalesce(dept.name, '') AS department
        """)

        org_rows = await _run_cypher(
            "MATCH (o:Organization) RETURN o.id AS id, o.name AS name, o.org_type AS org_type LIMIT 1"
        )

        dept_rows = await _run_cypher(
            "MATCH (d:Department) RETURN d.id AS id, d.name AS name, d.code AS code ORDER BY d.name"
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Neo4j 연결 실패: {str(e)}")

    meetings_map: dict[str, dict] = {}

    for row in mg_rows:
        mg_id = row["mg_id"]
        if mg_id not in allowed_mg_ids:  # 접근 가능한 회의체만 포함
            continue
        if mg_id not in meetings_map:
            meetings_map[mg_id] = {
                "id": mg_id,
                "title": row.get("title", ""),
                "meeting_type": row.get("meeting_type"),
                "status": row.get("status", "active"),
                "purpose": row.get("purpose"),
                "members": [],
                "tasks": [],
                "minutes": [],
                "reports": [],
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
                    "role": "admin" if row.get("role") == "ADMIN_OF" else "presenter",
                    "department": row.get("department") or "",
                })

    for row in agenda_rows:
        mg_id = row.get("meetingId")
        if mg_id and mg_id in meetings_map:
            meetings_map[mg_id]["tasks"].append({
                "id": row["id"],
                "meetingId": mg_id,
                "content": row.get("content", ""),
                "description": row.get("description", ""),
                "category": row.get("category"),
                "priority": row.get("priority", "low"),
                "status": row.get("status", "pending"),
                "due_date": row.get("due_date"),
                "created_at": row.get("created_at"),
                "assignee_name": row.get("assignee_name"),
                "assignee_dept": row.get("assignee_dept", ""),
            })

    seen_sessions: set[str] = set()
    for row in session_rows:
        mg_id = row.get("meetingId")
        session_id = row.get("id")
        if mg_id and mg_id in meetings_map and session_id not in seen_sessions:
            seen_sessions.add(session_id)
            meetings_map[mg_id]["minutes"].append({
                "id": session_id,
                "meeting_id": mg_id,
                "meeting_title": row.get("meetingTitle", ""),
                "session_title": row.get("session_title", ""),
                "session_number": row.get("session_number"),
                "date": row.get("date"),
                "session_type": row.get("session_type"),
                "description": row.get("description"),
                "ended_at": row.get("ended_at"),
                "file_name": row.get("file_name"),
                "doc_title": row.get("doc_title"),
                "doc_type": row.get("doc_type"),
                "doc_author": row.get("doc_author"),
                "doc_created_at": row.get("doc_created_at"),
            })

    for row in report_rows:
        mg_id = row.get("meetingId")
        if mg_id and mg_id in meetings_map:
            meetings_map[mg_id]["reports"].append({
                "id": row["id"],
                "meeting_id": mg_id,
                "meeting_title": row.get("meetingTitle", ""),
                "title": row.get("title", ""),
                "file_name": row.get("file_name", ""),
                "doc_type": row.get("doc_type", ""),
                "author": row.get("author"),
                "file_url": row.get("file_url"),
                "submitted_at": row.get("submitted_at"),
                "department": row.get("department", ""),
            })

    # meetings 리스트는 SQLite 보완 이후에 최종 빌드 (아래 SQLite 보완 블록 후에 계산)

    # 현재 사용자 Person 노드 (소속 여부와 무관하게 항상 포함)
    if person_rows:
        pr = person_rows[0]
        current_person = {
            "id": pr["pid"],
            "name": pr["pname"],
            "email": user_email,
            "position": current_user.position or "",
            "department": current_user.department or "",
        }
    else:
        current_person = {
            "id": f"user-{current_user.id}",
            "name": current_user.name,
            "email": user_email,
            "position": current_user.position or "",
            "department": current_user.department or "",
        }

    # ── SQLite 회의체 보완: Neo4j에 아직 반영 안 된 신규 회의체도 포함 ──
    sqlite_meetings = (
        db.query(models.Meeting)
        .join(models.MeetingMember, models.MeetingMember.meeting_id == models.Meeting.id)
        .filter(models.MeetingMember.user_id == current_user.id)
        .all()
    )
    for m in sqlite_meetings:
        sqlite_mg_id = f"mg-sqlite-{m.id}"
        if sqlite_mg_id not in meetings_map:
            # Neo4j에 없는 회의체 — SQLite 데이터로 보완
            members_db = (
                db.query(models.MeetingMember, models.User)
                .join(models.User, models.User.id == models.MeetingMember.user_id)
                .filter(models.MeetingMember.meeting_id == m.id)
                .all()
            )
            members_list = [
                {
                    "meetingId": sqlite_mg_id,
                    "userId": f"user-{u.id}",
                    "userName": u.name or "",
                    "email": u.email or "",
                    "position": u.position or "",
                    "role": "admin" if str(mb.role) == "admin" else "presenter",
                    "department": u.department or "",
                }
                for mb, u in members_db
            ]
            meetings_map[sqlite_mg_id] = {
                "id": sqlite_mg_id,
                "title": m.title,
                "meeting_type": str(m.type) if m.type else None,
                "status": m.status or "active",
                "purpose": m.purpose,
                "members": members_list,
                "tasks": [],
                "minutes": [],
                "reports": [],
            }

    meetings = list(meetings_map.values())
    minutes = [mn for mg in meetings for mn in mg["minutes"]]
    reports = [r for mg in meetings for r in mg["reports"]]

    return {
        "meetings": meetings,
        "minutes": minutes,
        "reports": reports,
        "departments": dept_rows,
        "org": org_rows[0] if org_rows else None,
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
            f"MATCH (a {{id: $from_id}}), (b {{id: $to_id}}) MERGE (a)-[:{safe_rel}]->(b)",
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
            cypher_fwd = f"MATCH (a {{id: $from_id}})-[r:{use_rel_type}]->(b {{id: $to_id}}) DELETE r"
            cypher_rev = f"MATCH (a {{id: $to_id}})-[r:{use_rel_type}]->(b {{id: $from_id}}) DELETE r"
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
            f"MATCH (a {{id: $from_id}})-[r:{old_rel}]->(b {{id: $to_id}}) DELETE r",
            {"from_id": from_id, "to_id": to_id},
        )
        await _run_cypher(
            f"MATCH (a {{id: $from_id}}), (b {{id: $to_id}}) MERGE (a)-[:{new_rel}]->(b)",
            {"from_id": from_id, "to_id": to_id},
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Neo4j 연결 실패: {str(e)}")
    return {"ok": True}


@router.post("/meeting-groups")
async def create_meeting_group(data: dict):
    """MeetingGroup 노드 생성 및 Organization에 연결"""
    mg_id = data.get("id", "")
    title = data.get("title", "")
    meeting_type = data.get("meeting_type", "")
    purpose = data.get("purpose", "")
    org_id = data.get("org_id", "")
    creator_name = data.get("creator_name", "")
    creator_email = data.get("creator_email", "")
    try:
        await _run_cypher(
            """
            MERGE (mg:MeetingGroup {id: $id})
            SET mg.title = $title, mg.meeting_type = $meeting_type,
                mg.purpose = $purpose, mg.status = 'active'
            """,
            {"id": mg_id, "title": title, "meeting_type": meeting_type, "purpose": purpose},
        )
        if org_id:
            await _run_cypher(
                "MATCH (mg:MeetingGroup {id: $mg_id}), (o:Organization {id: $org_id}) MERGE (mg)-[:PART_OF]->(o)",
                {"mg_id": mg_id, "org_id": org_id},
            )
        if creator_email or creator_name:
            await _run_cypher(
                """
                MATCH (mg:MeetingGroup {id: $mg_id})
                MATCH (p:Person) WHERE p.email = $email OR p.name = $name
                MERGE (p)-[:ADMIN_OF]->(mg)
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
    """MeetingGroup 노드 속성 수정"""
    fields = {k: v for k, v in data.items() if k in ("title", "purpose", "guidelines", "status", "meeting_type")}
    if not fields:
        return {"ok": True}
    set_clause = ", ".join(f"mg.{k} = ${k}" for k in fields)
    try:
        await _run_cypher(
            f"MATCH (mg:MeetingGroup {{id: $mg_id}}) SET {set_clause}",
            {"mg_id": mg_id, **fields},
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Neo4j 연결 실패: {str(e)}")
    return {"ok": True}


@router.delete("/meeting-groups/{mg_id}")
async def delete_meeting_group(mg_id: str):
    """MeetingGroup 노드 및 연결 관계 삭제"""
    try:
        await _run_cypher(
            "MATCH (mg:MeetingGroup {id: $mg_id}) DETACH DELETE mg",
            {"mg_id": mg_id},
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Neo4j 연결 실패: {str(e)}")
    return {"ok": True}


@router.post("/meeting-groups/{mg_id}/members")
async def add_member_to_group(mg_id: str, data: dict):
    """Person → MeetingGroup 멤버 관계 추가"""
    person_name = data.get("name", "")
    person_email = data.get("email", "")
    role = data.get("role", "member")  # admin | member
    rel = "ADMIN_OF" if role == "admin" else "MEMBER_OF"
    try:
        await _run_cypher(
            f"""
            MATCH (mg:MeetingGroup {{id: $mg_id}})
            MATCH (p:Person) WHERE p.email = $email OR p.name = $name
            MERGE (p)-[:{rel}]->(mg)
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
    """Person → MeetingGroup 멤버 관계 삭제"""
    person_name = data.get("name", "")
    person_email = data.get("email", "")
    try:
        await _run_cypher(
            """
            MATCH (p:Person)-[r:ADMIN_OF|MEMBER_OF]->(mg:MeetingGroup {id: $mg_id})
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
    """Session 노드 생성 및 MeetingGroup에 연결"""
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
                "MATCH (s:Session {id: $s_id}), (mg:MeetingGroup {id: $mg_id}) MERGE (s)-[:HELD_BY]->(mg)",
                {"s_id": s_id, "mg_id": mg_id},
            )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Neo4j 연결 실패: {str(e)}")
    return {"ok": True}


@router.post("/agendas")
async def create_agenda_node(data: dict):
    """Agenda 노드 생성 및 MeetingGroup에 연결"""
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
                "MATCH (ag:Agenda {id: $ag_id}), (mg:MeetingGroup {id: $mg_id}) MERGE (ag)-[:OWNED_BY]->(mg)",
                {"ag_id": ag_id, "mg_id": mg_id},
            )
        if assignee_name:
            await _run_cypher(
                "MATCH (ag:Agenda {id: $ag_id}), (p:Person {name: $name}) MERGE (p)-[:ASSIGNED_TO]->(ag)",
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

