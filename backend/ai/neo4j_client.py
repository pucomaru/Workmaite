"""Neo4j HTTP REST 클라이언트 — 모든 에이전트/라우터가 공유합니다."""
import os, base64
import httpx
from fastapi import HTTPException

NEO4J_URL      = os.getenv("NEO4J_URL",      "http://localhost:7474")
NEO4J_USER     = os.getenv("NEO4J_USER",     "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "skala-2-team9")
NEO4J_DB       = os.getenv("NEO4J_DATABASE", "neo4j")


def _cypher_endpoint() -> str:
    return f"{NEO4J_URL}/db/{NEO4J_DB}/tx/commit"


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
        result = body["results"][0] if body.get("results") else {"columns": [], "data": []}
        columns = result["columns"]
        return [dict(zip(columns, row["row"])) for row in result["data"]]


async def get_meeting_graph_context(meeting_id: str | int | None) -> dict:
    """회의체 ID로 Neo4j에서 관련 그래프 컨텍스트를 수집합니다.
    neo4j_sync.py가 생성하는 Meeting {pg_id} 스키마를 우선 사용하고,
    기존 MeetingGroup {id} 스키마를 폴백으로 지원합니다.
    """
    if not meeting_id:
        return {}

    try:
        pg_id = int(meeting_id)
    except (ValueError, TypeError):
        pg_id = None

    # pg_id 문자열 ID ("mg-001" 형식) 변환 시도
    if pg_id is None:
        s = str(meeting_id)
        if s.startswith("mg-") and s[3:].isdigit():
            pg_id = int(s[3:])

    try:
        # ── 1차: Meeting {pg_id} 스키마 (neo4j_sync.py 동기화 데이터) ──
        if pg_id is not None:
            mg_rows = await run_cypher(
                """MATCH (m:Meeting {pg_id: $pg_id})
                   RETURN m.pg_id AS neo_id, m.title AS title,
                          m.purpose AS purpose, m.status AS status LIMIT 1""",
                {"pg_id": pg_id},
            )
            if mg_rows:
                agenda_rows = await run_cypher(
                    """MATCH (ag:Agenda)-[:OWNED_BY]->(m:Meeting {pg_id: $pg_id})
                       OPTIONAL MATCH (p:Person)-[:ASSIGNED_TO]->(ag)
                       RETURN ag.content AS title, ag.status AS status,
                              p.name AS assignee LIMIT 20""",
                    {"pg_id": pg_id},
                )
                session_rows = await run_cypher(
                    """MATCH (s:Session)-[:BELONGS_TO]->(m:Meeting {pg_id: $pg_id})
                       RETURN s.title AS title, s.pg_id AS num,
                              s.scheduled_at AS ended_at
                       ORDER BY s.pg_id DESC LIMIT 5""",
                    {"pg_id": pg_id},
                )
                todo_rows = await run_cypher(
                    """MATCH (t:Todo)-[:BELONGS_TO]->(m:Meeting {pg_id: $pg_id})
                       OPTIONAL MATCH (p:Person)-[:ASSIGNED_TO]->(t)
                       RETURN t.content AS content, t.status AS status,
                              t.due_date AS due_date, p.name AS assignee LIMIT 15""",
                    {"pg_id": pg_id},
                )
                return {
                    "meeting": mg_rows[0],
                    "agendas": agenda_rows,
                    "recent_sessions": session_rows,
                    "todos": todo_rows,
                    "decisions": [],
                }

        # ── 2차 폴백: MeetingGroup {id} 스키마 (시드 데이터 / 프론트 생성) ──
        mid_str = str(meeting_id)
        if pg_id is not None:
            mid_str_alt = f"mg-{pg_id:03d}"
        else:
            mid_str_alt = mid_str

        mg_rows = await run_cypher(
            """MATCH (mg:MeetingGroup) WHERE mg.id = $id1 OR mg.id = $id2
               RETURN mg.id AS neo_id, mg.title AS title,
                      mg.purpose AS purpose, mg.status AS status LIMIT 1""",
            {"id1": mid_str, "id2": mid_str_alt},
        )
        if not mg_rows:
            return {}
        neo_id = mg_rows[0].get("neo_id", mid_str)

        agenda_rows = await run_cypher(
            """MATCH (ag:Agenda)-[:OWNED_BY]->(mg:MeetingGroup {id: $id})
               OPTIONAL MATCH (p:Person)-[:ASSIGNED_TO]->(ag)
               RETURN ag.title AS title, ag.status AS status,
                      p.name AS assignee LIMIT 20""",
            {"id": neo_id},
        )
        session_rows = await run_cypher(
            """MATCH (s:Session)-[:HELD_BY]->(mg:MeetingGroup {id: $id})
               RETURN s.title AS title, s.session_number AS num,
                      toString(s.ended_at) AS ended_at
               ORDER BY s.session_number DESC LIMIT 5""",
            {"id": neo_id},
        )
        decision_rows = await run_cypher(
            """MATCH (dec:Decision)-[:BASED_ON]->(s:Session)-[:HELD_BY]->(mg:MeetingGroup {id: $id})
               OPTIONAL MATCH (dec)-[:CAUSED_BY]->(ag:Agenda)
               RETURN dec.content AS content, ag.title AS agenda LIMIT 10""",
            {"id": neo_id},
        )
        return {
            "meeting": mg_rows[0],
            "agendas": agenda_rows,
            "recent_sessions": session_rows,
            "decisions": decision_rows,
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
    agendas = ctx.get("agendas", [])
    if agendas:
        lines.append(f"[아젠다 {len(agendas)}건]")
        for a in agendas[:8]:
            assignee = f" → {a['assignee']}" if a.get("assignee") else ""
            lines.append(f"  - {a.get('title','')} ({a.get('status','')}){assignee}")
    sessions = ctx.get("recent_sessions", [])
    if sessions:
        lines.append("[최근 세션]")
        for s in sessions:
            lines.append(f"  - {s.get('num', s.get('session_number','?'))}회차: {s.get('title','')} ({s.get('ended_at','?')})")
    todos = ctx.get("todos", [])
    if todos:
        lines.append(f"[할 일 {len(todos)}건]")
        for t in todos[:5]:
            assignee = f" → {t['assignee']}" if t.get("assignee") else ""
            lines.append(f"  - [{t.get('status','')}] {t.get('content','')}{assignee}")
    decisions = ctx.get("decisions", [])
    if decisions:
        lines.append(f"[의사결정 {len(decisions)}건]")
        for d in decisions[:5]:
            lines.append(f"  - {d.get('content','')}")
    return "\n".join(lines) if lines else "(Neo4j 데이터 없음)"
