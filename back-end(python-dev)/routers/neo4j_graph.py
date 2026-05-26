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
        user_email = current_user.employee_id or ""
        user_name = current_user.name or ""

        person_rows = await _run_cypher(
            "MATCH (p:Person) WHERE p.email = $email OR p.name = $name "
            "RETURN p.id AS pid, p.name AS pname",
            {"email": user_email, "name": user_name},
        )

        # admin 계정(employee_id에 'admin' 포함)은 전체 조회
        is_admin = "admin" in user_email.lower() or current_user.position in ("대표", "CEO", "임원")

        if person_rows:
            person_id = person_rows[0]["pid"]
            allowed_mg_ids_rows = await _run_cypher(
                "MATCH (p:Person {id: $pid})-[:ADMIN_OF|MEMBER_OF]->(mg:MeetingGroup) "
                "RETURN mg.id AS mg_id",
                {"pid": person_id},
            )
            allowed_mg_ids = {r["mg_id"] for r in allowed_mg_ids_rows}
        elif is_admin:
            # admin은 전체 회의체
            all_mg = await _run_cypher("MATCH (mg:MeetingGroup) RETURN mg.id AS mg_id")
            allowed_mg_ids = {r["mg_id"] for r in all_mg}
        else:
            # Neo4j에 없고 admin도 아니면 — 본인 노드만 반환
            return {
                "meetings": [],
                "minutes": [],
                "reports": [],
                "departments": [],
                "current_person": {
                    "id": f"user-{current_user.id}",
                    "name": current_user.name,
                    "email": current_user.employee_id or "",
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
            MATCH (mg:MeetingGroup)
            OPTIONAL MATCH (p:Person)-[rel:ADMIN_OF|MEMBER_OF]->(mg)
            OPTIONAL MATCH (p)-[:BELONGS_TO]->(d:Department)
            RETURN mg.id AS mg_id, mg.title AS title,
                   mg.meeting_type AS meeting_type, mg.status AS status,
                   mg.purpose AS purpose,
                   p.id AS person_id, p.name AS person_name, p.email AS email,
                   p.position AS position, type(rel) AS role, d.name AS department
            ORDER BY mg.id
        """)

        agenda_rows = await _run_cypher("""
            MATCH (ag:Agenda)-[:OWNED_BY]->(mg:MeetingGroup)
            OPTIONAL MATCH (p:Person)-[:ASSIGNED_TO]->(ag)
            OPTIONAL MATCH (p)-[:BELONGS_TO]->(d:Department)
            RETURN mg.id AS meetingId, ag.id AS id, ag.title AS content,
                   ag.description AS description, ag.priority AS priority,
                   ag.status AS status, toString(ag.due_date) AS due_date,
                   p.name AS assignee_name, coalesce(d.name, '') AS assignee_dept
        """)

        session_rows = await _run_cypher("""
            MATCH (s:Session)-[:HELD_BY]->(mg:MeetingGroup)
            OPTIONAL MATCH (s)-[:PRODUCED]->(doc:Document)
            RETURN mg.id AS meetingId, mg.title AS meetingTitle,
                   s.id AS id, s.title AS session_title,
                   s.session_number AS session_number,
                   toString(s.ended_at) AS ended_at,
                   doc.file_name AS file_name, doc.id AS doc_id
        """)

        report_rows = await _run_cypher("""
            MATCH (doc:Document)-[:ATTACHED_TO]->(mg:MeetingGroup)
            WHERE NOT doc.doc_type = '회의록'
            OPTIONAL MATCH (dept:Department)-[:SUBMITTED]->(doc)
            RETURN mg.id AS meetingId, mg.title AS meetingTitle,
                   doc.id AS id, doc.title AS title,
                   doc.file_name AS file_name, doc.doc_type AS doc_type,
                   toString(doc.uploaded_at) AS submitted_at,
                   coalesce(dept.name, '') AS department
        """)

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
                "priority": row.get("priority", "low"),
                "status": row.get("status", "pending"),
                "due_date": row.get("due_date"),
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
                "ended_at": row.get("ended_at"),
                "file_name": row.get("file_name"),
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
                "submitted_at": row.get("submitted_at"),
                "department": row.get("department", ""),
            })

    meetings = list(meetings_map.values())
    minutes = [m for mg in meetings for m in mg["minutes"]]
    reports = [r for mg in meetings for r in mg["reports"]]

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

    return {
        "meetings": meetings,
        "minutes": minutes,
        "reports": reports,
        "departments": dept_rows,
        "current_person": current_person,
    }


@router.post("/relationships")
async def create_relationship(data: dict):
    from_id = data.get("from_id", "")
    rel_type = data.get("rel_type", "")
    to_id = data.get("to_id", "")
    if rel_type not in ALLOWED_REL_TYPES:
        raise HTTPException(status_code=400, detail=f"허용되지 않는 관계 유형: {rel_type}")
    try:
        await _run_cypher(
            f"MATCH (a {{id: $from_id}}), (b {{id: $to_id}}) MERGE (a)-[:{rel_type}]->(b)",
            {"from_id": from_id, "to_id": to_id},
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Neo4j 연결 실패: {str(e)}")
    return {"ok": True}

