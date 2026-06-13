"""Neo4j HTTP REST 클라이언트 — 모든 에이전트/라우터가 공유합니다."""

import asyncio
import os
import base64
import re
import httpx
from fastapi import HTTPException
from neo4j_ids import to_mg_id

NEO4J_URL = os.environ["NEO4J_URL"]
NEO4J_USER = os.environ["NEO4J_USER"]
NEO4J_PASSWORD = os.environ["NEO4J_PASSWORD"]
NEO4J_DB = os.environ["NEO4J_DATABASE"]


def _cypher_endpoint() -> str:
    # Support cases where NEO4J_URL is provided as a bolt:// or neo4j:// URI
    url = NEO4J_URL
    if url.startswith(("bolt://", "neo4j://")):
        # convert bolt://host:7687 -> http://host:7474
        url = re.sub(r"^bolt://|^neo4j://", "http://", url)
        url = re.sub(r":7687(?=$|/)", ":7474", url)
    return f"{url.rstrip('/')}/db/{NEO4J_DB}/tx/commit"


def _auth_header() -> dict:
    creds = base64.b64encode(f"{NEO4J_USER}:{NEO4J_PASSWORD}".encode()).decode()
    return {
        "Authorization": f"Basic {creds}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


async def run_cypher(statement: str, parameters: dict | None = None) -> list[dict]:
    """Cypher 쿼리를 실행하고 행 목록을 반환합니다."""
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
        result = (
            body["results"][0] if body.get("results") else {"columns": [], "data": []}
        )
        columns = result["columns"]
        return [dict(zip(columns, row["row"])) for row in result["data"]]


async def get_meeting_graph_context(meeting_id: str | int | None) -> dict:
    """회의체 ID로 Neo4j에서 관련 그래프 컨텍스트를 수집합니다.
    Meetings {id: 'mg-N'} 스키마만 사용합니다.
    """
    if not meeting_id:
        return {}

    try:
        pg_id = int(meeting_id)
    except (ValueError, TypeError):
        pg_id = None

    if pg_id is None:
        s = str(meeting_id)
        if s.startswith("mg-") and s[3:].isdigit():
            pg_id = int(s[3:])

    mg_neo_id = to_mg_id(pg_id) if pg_id is not None else str(meeting_id)

    try:
        mg_rows = await run_cypher(
            """MATCH (mg:Meetings {id: $id})
               RETURN mg.id AS neo_id, mg.title AS title,
                      coalesce(mg.description, '') AS purpose,
                      mg.status AS status LIMIT 1""",
            {"id": mg_neo_id},
        )
        if not mg_rows:
            return {}

        agenda_rows, session_rows, member_rows, report_rows = await asyncio.gather(
            run_cypher(
                """MATCH (ag:Agenda)-[:`관할`]->(mg:Meetings {id: $id})
                   OPTIONAL MATCH (p:User)-[:`담당`]->(ag)
                   RETURN ag.title AS title, ag.status AS status,
                          p.name AS assignee LIMIT 20""",
                {"id": mg_neo_id},
            ),
            run_cypher(
                """MATCH (s:Session)-[:`소속`]->(mg:Meetings {id: $id})
                   RETURN s.title AS title, s.pg_id AS num,
                          s.scheduled_at AS ended_at
                   ORDER BY s.pg_id DESC LIMIT 5""",
                {"id": mg_neo_id},
            ),
            run_cypher(
                """MATCH (p:User)-[r:`간사`|`구성원`]->(mg:Meetings {id: $id})
                   RETURN p.name AS name, coalesce(p.department, '') AS dept,
                          coalesce(p.company, '') AS company, type(r) AS role
                   ORDER BY type(r), p.name""",
                {"id": mg_neo_id},
            ),
            run_cypher(
                """MATCH (d)-[:`첨부`]->(mg:Meetings {id: $id})
                   WHERE d:Report OR d:Minutes
                   RETURN coalesce(d.title, d.file_name, '(제목없음)') AS title,
                          labels(d)[0] AS doc_type,
                          coalesce(d.created_at, '') AS created_at
                   ORDER BY d.created_at DESC LIMIT 10""",
                {"id": mg_neo_id},
            ),
        )
        return {
            "meeting": mg_rows[0],
            "agendas": agenda_rows,
            "recent_sessions": session_rows,
            "members": member_rows,
            "reports": report_rows,
            "decisions": [],
        }
    except Exception:
        return {}


def graph_context_to_str(ctx: dict) -> str:
    """그래프 컨텍스트 dict → 에이전트 프롬프트용 문자열 변환."""
    lines = []
    mg = ctx.get("meeting", {})
    if mg.get("title"):
        lines.append(f"[회의체] {mg['title']} (상태: {mg.get('status', '?')})")
        if mg.get("purpose"):
            lines.append(f"  목적: {mg['purpose']}")

    members = ctx.get("members", [])
    if members:
        secretaries = [m for m in members if m.get("role") == "간사"]
        regulars = [m for m in members if m.get("role") != "간사"]
        if secretaries:
            sec_str = ", ".join(
                m.get("name", "?") + (f"({m['dept']})" if m.get("dept") else "")
                for m in secretaries
            )
            lines.append(f"[간사] {sec_str}")
        if regulars:
            depts = list(
                dict.fromkeys(m.get("dept", "") for m in regulars if m.get("dept"))
            )
            if depts:
                lines.append(f"[참여부서] {', '.join(depts)}")
            mem_str = ", ".join(
                m.get("name", "?") + (f"({m['dept']})" if m.get("dept") else "")
                for m in regulars[:15]
            )
            lines.append(f"[구성원 {len(regulars)}명] {mem_str}")

    agendas = ctx.get("agendas", [])
    if agendas:
        lines.append(f"[아젠다 {len(agendas)}건]")
        for a in agendas[:8]:
            assignee = f" → {a['assignee']}" if a.get("assignee") else ""
            lines.append(f"  - {a.get('title', '')} ({a.get('status', '')}){assignee}")

    sessions = ctx.get("recent_sessions", [])
    if sessions:
        lines.append("[최근 세션]")
        for s in sessions:
            lines.append(
                f"  - {s.get('num', s.get('session_number', '?'))}회차: {s.get('title', '')} ({s.get('ended_at', '?')})"
            )

    reports = ctx.get("reports", [])
    if reports:
        lines.append(f"[보고자료 {len(reports)}건]")
        for r in reports[:8]:
            doc_label = "보고자료" if r.get("doc_type") == "Report" else "회의록"
            lines.append(f"  - [{doc_label}] {r.get('title', '?')}")

    return "\n".join(lines) if lines else "(Neo4j 데이터 없음)"
