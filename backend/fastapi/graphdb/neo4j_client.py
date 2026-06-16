"""Neo4j Bolt 클라이언트 — 모든 에이전트/라우터가 공유합니다.

이전에는 HTTP REST(/tx/commit)를 사용했으나 Bolt 프로토콜(기본 7687)로 전환했다.
run_cypher 시그니처(statement, parameters) -> list[dict]는 그대로 유지하므로
호출부(에이전트·라우터·동기화)는 변경할 필요가 없다.
"""

import asyncio
import os
import re

from fastapi import HTTPException
from neo4j import (
    AsyncDriver,
    AsyncGraphDatabase,
    NotificationDisabledClassification,
)
from neo4j.exceptions import Neo4jError

from graphdb.neo4j_ids import to_mg_id

NEO4J_URL = os.environ["NEO4J_URL"]
NEO4J_USER = os.environ["NEO4J_USER"]
NEO4J_PASSWORD = os.environ["NEO4J_PASSWORD"]
NEO4J_DB = os.environ["NEO4J_DATABASE"]


def _bolt_uri() -> str:
    """NEO4J_URL을 Bolt 드라이버용 URI로 정규화한다.

    레거시 http://host:7474(REST) 설정도 bolt://host:7687로 변환해 그대로 동작시킨다.
    이미 bolt:// 또는 neo4j:// URI면 그대로 사용한다.
    """
    url = NEO4J_URL.strip().rstrip("/")
    if url.startswith(("http://", "https://")):
        # REST 경로(/db/...)가 붙어 있으면 호스트:포트까지만 사용
        url = re.sub(r"(/db/.*)$", "", url)
        url = re.sub(r"^https?://", "bolt://", url)
        url = re.sub(r":747[34](?=$|/)", ":7687", url)
    return url


_driver: AsyncDriver | None = None
_driver_lock = asyncio.Lock()


async def _get_driver() -> AsyncDriver:
    """공유 Bolt 드라이버(커넥션 풀) — 첫 호출 시 1회 생성."""
    global _driver
    if _driver is None:
        async with _driver_lock:
            if _driver is None:
                _driver = AsyncGraphDatabase.driver(
                    _bolt_uri(),
                    auth=(NEO4J_USER, NEO4J_PASSWORD),
                    connection_acquisition_timeout=10.0,
                    max_connection_pool_size=20,
                    # 스키마가 점진적으로 채워지는 그래프라 OPTIONAL MATCH로 '아직 없는'
                    # 관계 타입(예: 담당)·속성을 자주 참조한다. 이때 서버가 보내는
                    # 01N42(UNRECOGNIZED) 알림은 양성(빈 매치=null)이며 로그만 더럽히므로 억제한다.
                    # (오타로 인한 실제 누락도 가릴 수 있으니 새 Cypher 작성 시 주의)
                    notifications_disabled_classifications=[
                        NotificationDisabledClassification.UNRECOGNIZED
                    ],
                )
    return _driver


async def close_driver() -> None:
    """앱 종료 시 드라이버 커넥션 풀을 닫는다 (lifespan에서 호출)."""
    global _driver
    if _driver is not None:
        await _driver.close()
        _driver = None


def _jsonable(value):
    """Bolt 네이티브 타입을 JSON 친화 형태로 변환한다.

    기존 HTTP REST 응답과 동일하게 — 시간 타입(neo4j.time.*)은 ISO 문자열,
    노드/관계는 record.data()가 이미 프로퍼티 dict로 변환한다.
    """
    if hasattr(value, "iso_format"):  # neo4j.time.Date/Time/DateTime/Duration
        return value.iso_format()
    if isinstance(value, dict):
        return {k: _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    return value


async def run_cypher(statement: str, parameters: dict | None = None) -> list[dict]:
    """Cypher 쿼리를 실행하고 행 목록을 반환합니다 (autocommit, 호출당 1 트랜잭션)."""
    driver = await _get_driver()
    try:
        async with driver.session(database=NEO4J_DB) as session:
            result = await session.run(statement, parameters or {})
            return [_jsonable(record.data()) async for record in result]
    except Neo4jError as e:
        # 서버가 반환한 쿼리 오류 → 500 (기존 HTTP body["errors"] 경로와 동일).
        # 연결 실패(DriverError)는 그대로 전파해 호출부가 503으로 변환한다.
        raise HTTPException(status_code=500, detail=str(e))


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

        (
            agenda_rows,
            session_rows,
            member_rows,
            report_rows,
            peer_rows,
        ) = await asyncio.gather(
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
                """MATCH (p:User)-[r:`운영`|`참여`]->(mg:Meetings {id: $id})
                   RETURN p.name AS name, coalesce(p.department, '') AS dept,
                          coalesce(p.company, '') AS company, type(r) AS role
                   ORDER BY type(r), p.name""",
                {"id": mg_neo_id},
            ),
            run_cypher(
                """MATCH (d)-[:`발제`]->(mg:Meetings {id: $id})
                   WHERE d:Report OR d:Minutes
                   RETURN coalesce(d.title, d.file_name, '(제목없음)') AS title,
                          labels(d)[0] AS doc_type,
                          coalesce(d.created_at, '') AS created_at
                   ORDER BY d.created_at DESC LIMIT 10""",
                {"id": mg_neo_id},
            ),
            # 회의체↔회의체 `협의`(사용자 수동 연결, PG에 없는 Neo4j 전용). 방향 무관 조회.
            # 보안: 연결된 회의체의 제목·상태(메타데이터)만 노출하고 내부(안건·문서)는 펼치지 않는다.
            # 연결 회의체의 실제 내용 검색은 권한 스코프가 적용된 vector_search를 통해서만 이뤄진다.
            run_cypher(
                """MATCH (mg:Meetings {id: $id})-[:`협의`]-(peer:Meetings)
                   RETURN DISTINCT peer.title AS title, peer.pg_id AS pg_id,
                          coalesce(peer.status, '') AS status LIMIT 10""",
                {"id": mg_neo_id},
            ),
        )
        return {
            "meeting": mg_rows[0],
            "agendas": agenda_rows,
            "recent_sessions": session_rows,
            "members": member_rows,
            "reports": report_rows,
            "related_meetings": peer_rows,
            "decisions": [],
        }
    except Exception:
        return {}


_SESSION_STATUS_KO = {
    "scheduled": "예정됨",
    "ongoing": "진행 중",
    "ended": "종료됨",
    "archived": "완료",
    "active": "활성",
    "done": "완료",
    "completed": "완료",
    "pending": "대기",
    "draft": "초안",
}


def _sko(status: str) -> str:
    return _SESSION_STATUS_KO.get(str(status).lower().strip(), status)


def graph_context_to_str(ctx: dict) -> str:
    """그래프 컨텍스트 dict → 에이전트 프롬프트용 문자열 변환."""
    lines = []
    mg = ctx.get("meeting", {})
    if mg.get("title"):
        lines.append(f"[회의체] {mg['title']}")
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
            status_ko = _sko(a.get("status", "")) if a.get("status") else ""
            status_str = f" ({status_ko})" if status_ko else ""
            lines.append(f"  - {a.get('title', '')}{status_str}{assignee}")

    sessions = ctx.get("recent_sessions", [])
    if sessions:
        lines.append("[최근 세션]")
        for s in sessions:
            date_str = str(s.get("ended_at", ""))[:10].replace("-", ".")
            lines.append(f"  - {s.get('title', '(제목없음)')} ({date_str})")

    reports = ctx.get("reports", [])
    if reports:
        lines.append(f"[보고자료 {len(reports)}건]")
        for r in reports[:8]:
            doc_label = "보고자료" if r.get("doc_type") == "Report" else "회의록"
            lines.append(f"  - [{doc_label}] {r.get('title', '?')}")

    related = ctx.get("related_meetings", [])
    if related:
        peer_str = ", ".join(
            f"{m.get('title', '?')}"
            + (f"(상태: {m['status']})" if m.get("status") else "")
            for m in related
            if m.get("title")
        )
        if peer_str:
            lines.append(f"[협의 회의체] {peer_str}")

    return "\n".join(lines) if lines else "(Neo4j 데이터 없음)"
