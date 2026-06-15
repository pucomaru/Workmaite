"""
neo4j_sync.py — Neo4j 동기화 서비스
=====================================
원칙:
  - PostgreSQL이 Source of Truth
  - Neo4j 동기화는 항상 try/except로 감싸 실패해도 메인 흐름 중단 없음
"""

from __future__ import annotations
import hashlib
import json
import logging
import os
from typing import Any
from datetime import datetime, timezone

from sqlalchemy.orm import Session as DBSession

from db import models
from db.database import SessionLocal
from graphdb.neo4j_client import run_cypher
from graphdb.neo4j_ids import to_agenda_id, to_mg_id, to_report_id, to_session_id

# 임베딩 차원은 file_embedder에서 모델 기반으로 자동 도출 (단일 소스 — init_vector_index가 사용)
from graphdb.file_embedder import EMBED_DIM  # noqa: E402

UPLOAD_DIR = os.environ.get("UPLOAD_DIR", "/tmp/uploads")
logger = logging.getLogger(__name__)


# ─── VectorIndex 대상 노드 목록 ──────────────────────────────────────────────

# 인덱스 정의의 단일 소스는 retrieval_registry (P3B-6) — 여기서는 생성 목록만 파생
from graphdb.retrieval_registry import index_names_for_creation  # noqa: E402

_VECTOR_INDEXES: list[tuple[str, str, str]] = index_names_for_creation()


# ─── 유니크 제약 (P2-5) ───────────────────────────────────────────────────────
# (라벨, 제약 이름, 키 프로퍼티). User만 pg_id, 나머지는 id 문자열 키.
_UNIQUE_CONSTRAINTS: list[tuple[str, str, str]] = [
    ("User", "user_pg_id", "pg_id"),
    ("Meetings", "meetings_id", "id"),
    ("Session", "session_id", "id"),
    ("Agenda", "agenda_id", "id"),
    ("Minutes", "minutes_id", "id"),
    ("Report", "report_id", "id"),
    ("Department", "dept_name", "name"),
    ("Company", "company_name", "name"),
]


async def ensure_constraints() -> None:
    """중복 노드를 정리한 뒤 유니크 제약을 생성합니다 (P2-5, 시작 시 1회).

    MERGE 기반 upsert는 제약이 없으면 동시 실행 시 중복 노드를 만들 수 있다.
    중복 정리는 관계가 많은 노드를 남기고 나머지를 제거한다.
    """
    for label, name, prop in _UNIQUE_CONSTRAINTS:
        try:
            # 1) 중복 정리 — 차수(degree) 높은 노드를 보존
            await run_cypher(
                f"MATCH (n:{label}) WHERE n.{prop} IS NOT NULL "
                f"WITH n, COUNT {{ (n)--() }} AS deg ORDER BY deg DESC "
                f"WITH n.{prop} AS key, collect(n) AS nodes "
                f"WHERE size(nodes) > 1 "
                f"UNWIND nodes[1..] AS dup DETACH DELETE dup"
            )
            # 2) 제약 생성
            await run_cypher(
                f"CREATE CONSTRAINT {name} IF NOT EXISTS "
                f"FOR (n:{label}) REQUIRE n.{prop} IS UNIQUE"
            )
            logger.info(f"[Neo4jSync] 유니크 제약 '{name}' 보장 완료")
        except Exception as e:
            logger.warning(f"[Neo4jSync] 유니크 제약 '{name}' 생성 실패 (무시): {e}")


async def init_vector_index() -> None:
    """모든 노드 유형에 VectorIndex가 없으면 생성합니다."""
    for label, index_name, prop in _VECTOR_INDEXES:
        cypher = f"""
        CREATE VECTOR INDEX {index_name} IF NOT EXISTS
        FOR (n:{label}) ON (n.{prop})
        OPTIONS {{ indexConfig: {{ `vector.dimensions`: $dim, `vector.similarity_function`: 'cosine' }} }}
        """
        try:
            await run_cypher(cypher, {"dim": EMBED_DIM})
            logger.info(f"[Neo4jSync] VectorIndex '{index_name}' 초기화 완료")
        except Exception as e:
            logger.warning(
                f"[Neo4jSync] VectorIndex '{index_name}' 초기화 실패 (무시): {e}"
            )


async def _embed(text: str) -> list[float] | None:
    text = text.strip()
    if not text:
        return None
    try:
        from graphdb.file_embedder import embed_query

        return await embed_query(text)
    except Exception as e:
        logger.warning(f"[Neo4jSync] 임베딩 실패 (무시): {e}")
        return None


async def _embed_if_changed(label: str, key_prop: str, key_value, text: str):
    """content_hash 비교 후 변경 시에만 임베딩을 계산합니다 (P2-6 — OpenAI 호출 절감).

    반환: (embedding | None, content_hash | None) — 임베딩이 None이면 SET 생략(기존 값 유지).
    """
    text = (text or "").strip()
    if not text:
        return None, None
    content_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
    try:
        rows = await run_cypher(
            f"MATCH (n:{label} {{{key_prop}: $k}}) RETURN n.content_hash AS h",
            {"k": key_value},
        )
        if rows and rows[0].get("h") == content_hash:
            return None, content_hash  # 내용 동일 — 임베딩 재계산 생략
    except Exception as e:
        logger.warning(f"[Neo4jSync] content_hash 조회 실패 (임베딩 진행): {e}")
    return await _embed(text), content_hash


def _log_failure(
    operation: str,
    entity_type: str,
    entity_id: str,
    error: Exception,
    payload: dict | None = None,
) -> None:
    logger.warning(
        f"[Neo4jSync] 동기화 실패: {operation}/{entity_type}/{entity_id} — {error}"
    )


def _is_draft(status: str | None) -> bool:
    """Draft 상태 판별 (대소문자 무관) — Agenda 'draft' / Minutes 'DRAFT' 모두 포함."""
    return (status or "").strip().lower() == "draft"


async def _detach_node(label: str, key_prop: str, key_value) -> None:
    """Neo4j에서 해당 노드를 관계째 제거한다 (draft 전환 시 PG-only로 되돌리기 위함)."""
    try:
        await run_cypher(
            f"MATCH (n:{label} {{{key_prop}: $k}}) DETACH DELETE n",
            {"k": key_value},
        )
    except Exception as e:
        logger.warning(f"[Neo4jSync] {label} {key_value} Neo4j 제외 처리 실패 (무시): {e}")


def _parse_dept_names(department: str | None) -> list[str]:
    """department 문자열(또는 JSON string)에서 부서명 목록을 추출합니다."""
    if not department or not department.strip():
        return []
    try:
        parsed = json.loads(department)
        if isinstance(parsed, list):
            return [str(x).strip() for x in parsed if x and str(x).strip()]
        if isinstance(parsed, dict):
            val = (
                parsed.get("dept")
                or parsed.get("department")
                or parsed.get("name")
                or ""
            )
            return [str(val).strip()] if val else []
        return [str(parsed).strip()] if str(parsed).strip() else []
    except (json.JSONDecodeError, ValueError):
        return [department.strip()] if department.strip() else []


# ─── Department 동기화 ───────────────────────────────────────────────────────


async def sync_department(name: str) -> None:
    """Department 노드를 upsert합니다."""
    if not name or not name.strip():
        return
    try:
        await run_cypher(
            "MERGE (d:Department {name: $name}) SET d.updated_at = $updated_at",
            {
                "name": name.strip(),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            },
        )
    except Exception as e:
        logger.error(f"[Neo4jSync] sync_department 실패 ({name}): {e}")


async def sync_company(name: str) -> None:
    """Company 노드를 upsert합니다."""
    if not name or not name.strip():
        return
    try:
        await run_cypher(
            "MERGE (c:Company {name: $name}) SET c.updated_at = $updated_at",
            {
                "name": name.strip(),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            },
        )
    except Exception as e:
        logger.error(f"[Neo4jSync] sync_company 실패 ({name}): {e}")


async def rename_company(old_name: str, new_name: str) -> None:
    """Company 노드명 변경 + 소속 User 노드의 company 속성 일괄 갱신 (name 기반 식별)."""
    old, new = (old_name or "").strip(), (new_name or "").strip()
    if not old or not new or old == new:
        return
    try:
        await run_cypher(
            "MATCH (c:Company {name: $old}) SET c.name = $new", {"old": old, "new": new}
        )
        await run_cypher(
            "MATCH (u:User {company: $old}) SET u.company = $new",
            {"old": old, "new": new},
        )
    except Exception as e:
        logger.error(f"[Neo4jSync] rename_company 실패 ({old}→{new}): {e}")


async def rename_department(
    old_name: str, new_name: str, company_name: str | None = None
) -> None:
    """부서명 변경 — User 노드의 department 속성 일괄 갱신 (department 문자열 기반 식별).

    부서는 별도 노드 없이 User.department 속성으로만 존재하므로 해당 속성을 변경한다.
    company_name이 주어지면 그 회사 소속 User로 한정해 타 회사 동명 부서 오염을 막는다.
    """
    old, new = (old_name or "").strip(), (new_name or "").strip()
    co = (company_name or "").strip()
    if not old or not new or old == new:
        return
    try:
        if co:
            await run_cypher(
                "MATCH (u:User {department: $old, company: $co}) SET u.department = $new",
                {"old": old, "new": new, "co": co},
            )
        else:
            await run_cypher(
                "MATCH (u:User {department: $old}) SET u.department = $new",
                {"old": old, "new": new},
            )
    except Exception as e:
        logger.error(f"[Neo4jSync] rename_department 실패 ({old}→{new}): {e}")


# ─── User 동기화 (PG users) ──────────────────────────────────────────────────


async def sync_user(
    user_id: int,
    name: str,
    email: str,
    company: str | None = None,
    department: str | None = None,
    position: str | None = None,
    created_at: str | None = None,
) -> None:
    """User 노드를 upsert합니다."""
    now = datetime.now(timezone.utc).isoformat()
    cypher = """
    MERGE (u:User {pg_id: $pg_id})
    SET u.name       = $name,
        u.email      = $email,
        u.company    = $company,
        u.department = $department,
        u.position   = $position,
        u.created_at = coalesce(u.created_at, $created_at),
        u.updated_at = $updated_at
    WITH u
    FOREACH (_ IN CASE WHEN $company <> '' THEN [1] ELSE [] END |
        MERGE (co:Company {name: $company})
        MERGE (u)-[:`소속회사`]->(co)
    )
    """
    try:
        await run_cypher(
            cypher,
            {
                "pg_id": user_id,
                "name": name,
                "email": email,
                "company": company or "",
                "department": department or "",
                "position": position or "",
                "created_at": created_at or now,
                "updated_at": now,
            },
        )
    except Exception as e:
        logger.error(f"[Neo4jSync] sync_user 실패 (user_id={user_id}): {e}")

    # 인원→부서 연결 (소속): 변경 반영 위해 기존 소속 엣지를 정리하고 현재 부서로 재연결한다.
    # department가 JSON("[\"전략기획팀\"]")이든 평문이든 _parse_dept_names로 일관 처리.
    dept_names = _parse_dept_names(department)
    try:
        await run_cypher(
            """
            MATCH (u:User {pg_id: $pg_id})
            OPTIONAL MATCH (u)-[old:`소속`]->(:Department)
            DELETE old
            WITH u
            UNWIND $dept_names AS dname
            MERGE (d:Department {name: dname})
            MERGE (u)-[:`소속`]->(d)
        """,
            {"pg_id": user_id, "dept_names": dept_names},
        )
    except Exception as e:
        logger.warning(f"[Neo4jSync] User {user_id} 부서(소속) 연결 실패 (무시): {e}")


async def sync_meeting_member(
    meeting_id: int,
    user_id: int,
    role: str,
) -> None:
    """User-Meetings 구성원 관계를 upsert합니다."""
    cypher = """
    MATCH (u:User {pg_id: $user_id})
    MATCH (mg:Meetings {id: $mg_id})
    MERGE (u)-[r:`참여`]->(mg)
    SET r.role = $role
    """
    try:
        await run_cypher(
            cypher,
            {
                "user_id": user_id,
                "mg_id": to_mg_id(meeting_id),
                "role": role,
            },
        )
    except Exception as e:
        logger.error(
            f"[Neo4jSync] sync_meeting_member 실패 (meeting_id={meeting_id}, user_id={user_id}): {e}"
        )


async def delete_meeting_member(
    meeting_id: int,
    user_id: int,
) -> None:
    """User-Meetings 구성원 관계를 삭제합니다."""
    cypher = """
    MATCH (u:User {pg_id: $user_id})-[r:`참여`]->(mg:Meetings {id: $mg_id})
    DELETE r
    """
    try:
        await run_cypher(cypher, {"user_id": user_id, "mg_id": to_mg_id(meeting_id)})
    except Exception as e:
        logger.error(
            f"[Neo4jSync] delete_meeting_member 실패 (meeting_id={meeting_id}, user_id={user_id}): {e}"
        )


async def update_meeting_member_role(
    meeting_id: int,
    user_id: int,
    role: str,
) -> None:
    """User-Meetings 구성원 관계의 role을 업데이트합니다."""
    cypher = """
    MATCH (u:User {pg_id: $user_id})-[r:`참여`]->(mg:Meetings {id: $mg_id})
    SET r.role = $role
    """
    try:
        await run_cypher(
            cypher,
            {
                "user_id": user_id,
                "mg_id": to_mg_id(meeting_id),
                "role": role,
            },
        )
    except Exception as e:
        logger.error(
            f"[Neo4jSync] update_meeting_member_role 실패 (meeting_id={meeting_id}, user_id={user_id}): {e}"
        )


# ─── Meetings 동기화 (PG meetings) ───────────────────────────────────────────


async def sync_meeting_group(
    meeting_id: int,
    title: str,
    description: str | None = None,
    guidelines: str | None = None,
    context: str | None = None,
    status: str = "active",
    meeting_type: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    created_by: int | None = None,
    created_at: str | None = None,
) -> None:
    """Meetings 노드를 Neo4j에 upsert합니다."""
    mg_id = to_mg_id(meeting_id)
    cypher = """
    MERGE (mg:Meetings {id: $id})
    SET mg.pg_id       = $pg_id,
        mg.title       = $title,
        mg.description = $description,
        mg.guidelines  = $guidelines,
        mg.context     = $context,
        mg.status      = $status,
        mg.type        = $type,
        mg.start_date  = $start_date,
        mg.end_date    = $end_date,
        mg.created_by  = $created_by,
        mg.created_at  = $created_at,
        mg.updated_at  = $updated_at
    WITH mg
    OPTIONAL MATCH (creator:User {pg_id: $created_by})
    FOREACH (_ IN CASE WHEN creator IS NOT NULL THEN [1] ELSE [] END |
        MERGE (creator)-[:`운영`]->(mg)
    )
    """
    params = {
        "id": mg_id,
        "pg_id": meeting_id,
        "title": title,
        "description": description or "",
        "guidelines": guidelines or "",
        "context": context or "",
        "status": status,
        "type": meeting_type or "",
        "start_date": start_date or "",
        "end_date": end_date or "",
        "created_by": created_by,
        "created_at": created_at or "",
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    embedding, content_hash = await _embed_if_changed(
        "Meetings", "id", mg_id, guidelines or ""
    )
    if embedding:
        cypher += "\n    WITH mg SET mg.embedding = $embedding, mg.content_hash = $content_hash"
        params["embedding"] = embedding
        params["content_hash"] = content_hash
    try:
        await run_cypher(cypher, params)
        logger.debug(f"[Neo4jSync] Meetings {meeting_id} 동기화 완료")
    except Exception as e:
        logger.error(f"[Neo4jSync] Meetings {meeting_id} 실패: {e}")
        _log_failure("sync_meeting_group", "meetings", str(meeting_id), e, params)


async def sync_meeting(*args, **kwargs):
    return await sync_meeting_group(*args, **kwargs)


# ─── Session 동기화 (PG meeting_sessions) ────────────────────────────────────


async def sync_session(
    session_id: int,
    meeting_id: int,
    title: str,
    status: str = "scheduled",
    scheduled_at: str | None = None,
    started_at: str | None = None,
    ended_at: str | None = None,
    location: str | None = None,
    session_type: str | None = None,  # PG: type (대면/비대면 등)
    description: str | None = None,
    attendees: list[dict] = [],
) -> None:
    """Session 노드를 Neo4j에 upsert하고 Meetings과 관계를 맺습니다."""
    mg_id = to_mg_id(meeting_id)
    s_id = to_session_id(session_id)
    cypher = """
    MERGE (s:Session {id: $id})
    SET s.pg_id        = $pg_id,
        s.title        = $title,
        s.status       = $status,
        s.scheduled_at = $scheduled_at,
        s.started_at   = $started_at,
        s.ended_at     = $ended_at,
        s.location     = $location,
        s.type         = $session_type,
        s.description  = $description,
        s.updated_at   = $updated_at
    WITH s
    OPTIONAL MATCH (mg:Meetings {id: $mg_id})
    FOREACH (_ IN CASE WHEN mg IS NOT NULL THEN [1] ELSE [] END |
        MERGE (s)-[:`소속`]->(mg)
    )
    """
    emb_text = " ".join(filter(None, [title, description, location]))
    embedding, content_hash = await _embed_if_changed("Session", "id", s_id, emb_text)
    if embedding:
        cypher += (
            "\n    WITH s SET s.embedding = $embedding, s.content_hash = $content_hash"
        )
    params = {
        "id": s_id,
        "pg_id": session_id,
        "title": title,
        "status": status,
        "scheduled_at": scheduled_at or "",
        "started_at": started_at or "",
        "ended_at": ended_at or "",
        "location": location or "",
        "session_type": session_type or "",
        "description": description or "",
        "mg_id": mg_id,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    if embedding:
        params["embedding"] = embedding
        params["content_hash"] = content_hash
    try:
        await run_cypher(cypher, params)
        logger.debug(f"[Neo4jSync] Session {session_id} 동기화 완료")
    except Exception as e:
        logger.error(f"[Neo4jSync] Session {session_id} 실패: {e}")
        _log_failure("sync_session", "session", str(session_id), e, params)

    if attendees:
        attendee_cypher = """
        UNWIND $attendees AS a
        MATCH (u:User {pg_id: a.user_id})
        MATCH (s:Session {id: $session_id})
        MERGE (u)-[r:`참석`]->(s)
        SET r.role = a.role
        """
        try:
            await run_cypher(
                attendee_cypher, {"attendees": attendees, "session_id": s_id}
            )
            logger.debug(
                f"[Neo4jSync] Session {session_id} 참석자 {len(attendees)}명 동기화 완료"
            )
        except Exception as e:
            logger.error(f"[Neo4jSync] Session {session_id} 참석자 관계 실패: {e}")


# ─── User 동기화 (PG users) ──────────────────────────────────────────────────

# ─── Agenda 동기화 (PG agenda) ───────────────────────────────────────────────


async def sync_agenda(
    agenda_id: int,
    meeting_id: int,
    title: str,
    status: str = "draft",
    assignee_id: int | None = None,
    priority: str = "medium",
    due_date: str | None = None,
    session_id: int | None = None,
    department: str | None = None,  # PG JSON → 문자열로 변환해서 전달
    ai_evidence: str | None = None,
    created_at: str | None = None,
    hitl_status: str | None = None,
    hitl_comment: str | None = None,
    hitl_rationale: str | None = None,
    hitl_reviewed_at: str | None = None,
) -> None:
    """Agenda 노드를 upsert하고 Meetings / Session / 담당자와 연결합니다.

    HITL 검토 결과(승인·반려 status·코멘트·ai_rationale)를 노드 속성으로 흡수하고
    임베딩 텍스트에도 포함해 벡터 검색에 활용한다 

    Draft 상태는 사용자 확인 전이므로 PostgreSQL에만 보관하고 Neo4j에는 연동하지 않는다.
    """
    ag_id = to_agenda_id(agenda_id)
    if _is_draft(status):
        await _detach_node("Agenda", "id", ag_id)  # draft 전환 시 기존 노드 제거
        return
    mg_id = to_mg_id(meeting_id)
    s_id = to_session_id(session_id) if session_id else None
    cypher = """
    MERGE (ag:Agenda {id: $id})
    SET ag.pg_id        = $pg_id,
        ag.title        = $title,
        ag.status       = $status,
        ag.assignee_id  = $assignee_id,
        ag.priority     = $priority,
        ag.due_date     = $due_date,
        ag.department   = $department,
        ag.ai_evidence  = $ai_evidence,
        ag.created_at   = $created_at,
        ag.hitl_status      = $hitl_status,
        ag.hitl_comment     = $hitl_comment,
        ag.hitl_rationale   = $hitl_rationale,
        ag.hitl_reviewed_at = $hitl_reviewed_at,
        ag.updated_at   = $updated_at
    WITH ag
    OPTIONAL MATCH (mg:Meetings {id: $mg_id})
    FOREACH (_ IN CASE WHEN mg IS NOT NULL THEN [1] ELSE [] END |
        MERGE (ag)-[:`관할`]->(mg)
    )
    WITH ag
    OPTIONAL MATCH (s:Session {id: $s_id})
    FOREACH (_ IN CASE WHEN s IS NOT NULL THEN [1] ELSE [] END |
        MERGE (ag)-[:`논의`]->(s)
    )
    WITH ag
    OPTIONAL MATCH (ag)-[old:`진행`|`다룸`|`도출`]->(s2:Session)
    DELETE old
    WITH ag
    OPTIONAL MATCH (s3:Session)-[old2:`진행`|`다룸`|`도출`]->(ag)
    DELETE old2
    WITH ag
    OPTIONAL MATCH (assignee:User {pg_id: $assignee_id})
    FOREACH (_ IN CASE WHEN assignee IS NOT NULL THEN [1] ELSE [] END |
        MERGE (assignee)-[:`담당`]->(ag)
    )
    """
    if isinstance(ai_evidence, (dict, list)):
        ai_evidence = json.dumps(ai_evidence, ensure_ascii=False)
    emb_text = " ".join(
        filter(None, [title, ai_evidence, hitl_status, hitl_comment, hitl_rationale])
    )
    embedding, content_hash = await _embed_if_changed("Agenda", "id", ag_id, emb_text)
    if embedding:
        cypher += "\n    WITH ag SET ag.embedding = $embedding, ag.content_hash = $content_hash"
    params = {
        "id": ag_id,
        "pg_id": agenda_id,
        "title": title,
        "status": status,
        "assignee_id": assignee_id,
        "priority": priority,
        "due_date": due_date or "",
        "department": department or "",
        "ai_evidence": ai_evidence or "",
        "created_at": created_at or "",
        "hitl_status": hitl_status or "",
        "hitl_comment": hitl_comment or "",
        "hitl_rationale": hitl_rationale or "",
        "hitl_reviewed_at": hitl_reviewed_at or "",
        "mg_id": mg_id,
        "s_id": s_id,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    if embedding:
        params["embedding"] = embedding
        params["content_hash"] = content_hash
    try:
        await run_cypher(cypher, params)
        logger.debug(f"[Neo4jSync] Agenda {agenda_id} 동기화 완료")
    except Exception as e:
        logger.error(f"[Neo4jSync] Agenda {agenda_id} 실패: {e}")
        _log_failure("sync_agenda", "agenda", str(agenda_id), e, params)
    # Department 노드 연결 (별도 쿼리 — CYPHER 흐름과 분리)
    dept_names_list = _parse_dept_names(department)
    if dept_names_list:
        try:
            await run_cypher(
                """
            MATCH (ag:Agenda {id: $ag_id})
            UNWIND $dept_names AS dept_name
            MERGE (d:Department {name: dept_name})
            MERGE (ag)-[:`담당부서`]->(d)
            """,
                {"ag_id": ag_id, "dept_names": dept_names_list},
            )
        except Exception as e:
            logger.warning(
                f"[Neo4jSync] Agenda {agenda_id} Department 연결 실패 (무시): {e}"
            )


# ─── Minutes 동기화 (PG minutes) ─────────────────────────────────────────────


async def sync_minutes(
    minutes_id: int,
    session_id: int,
    content_summary: str | None = None,
    content_original: str | None = None,
    file_name: str | None = None,
    file_path: str | None = None,
    recorder_id: int | None = None,
    status: str | None = None,
    generated_at: str | None = None,
) -> None:
    """Minutes 노드를 upsert하고 Session / recorder User와 연결합니다.

    Draft 상태는 PostgreSQL에만 보관하고 Neo4j에는 연동하지 않는다.
    """
    if _is_draft(status):
        await _detach_node("Minutes", "pg_id", minutes_id)  # draft 전환 시 기존 노드 제거
        return
    s_id = to_session_id(session_id)
    cypher = """
    // 세션당 회의록은 하나여야 한다 — 같은 세션의 다른 pg_id Minutes(과거 삭제·재생성 잔재)를
    // 먼저 제거해 아카이브에 회의록이 여러 개로 보이는 것을 막는다.
    OPTIONAL MATCH (stale:Minutes)
        WHERE stale.session_id = $session_id AND stale.pg_id <> $pg_id
    DETACH DELETE stale
    WITH count(*) AS _cleaned
    MERGE (mn:Minutes {pg_id: $pg_id})
    SET mn.session_id       = $session_id,
        mn.content_summary  = $content_summary,
        mn.content_original = $content_original,
        mn.file_name        = $file_name,
        mn.file_path        = $file_path,
        mn.recorder_id      = $recorder_id,
        mn.status           = $status,
        mn.generated_at     = $generated_at,
        mn.updated_at       = $updated_at
    WITH mn
    OPTIONAL MATCH (s:Session {id: $s_id})
    FOREACH (_ IN CASE WHEN s IS NOT NULL THEN [1] ELSE [] END |
        MERGE (mn)-[:`기록`]->(s)
    )
    WITH mn
    OPTIONAL MATCH (recorder:User {pg_id: $recorder_id})
    FOREACH (_ IN CASE WHEN recorder IS NOT NULL THEN [1] ELSE [] END |
        MERGE (recorder)-[:`작성`]->(mn)
    )
    """
    emb_text = " ".join(filter(None, [content_summary, file_name]))
    embedding, content_hash = await _embed_if_changed(
        "Minutes", "pg_id", minutes_id, emb_text
    )
    if embedding:
        cypher += "\n    WITH mn SET mn.embedding = $embedding, mn.content_hash = $content_hash"
    params = {
        "pg_id": minutes_id,
        "session_id": session_id,
        "s_id": s_id,
        "content_summary": content_summary or "",
        "content_original": content_original or "",
        "file_name": file_name or "",
        "file_path": file_path or "",
        "recorder_id": recorder_id,
        "status": status or "draft",
        "generated_at": generated_at or "",
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    if embedding:
        params["embedding"] = embedding
        params["content_hash"] = content_hash
    try:
        await run_cypher(cypher, params)
        logger.debug(f"[Neo4jSync] Minutes {minutes_id} 동기화 완료")
    except Exception as e:
        logger.error(f"[Neo4jSync] Minutes {minutes_id} 실패: {e}")
        _log_failure("sync_minutes", "minutes", str(minutes_id), e, params)


# ─── MeetingMember 관계 동기화 ────────────────────────────────────────────────

# ─── Report 동기화 (PG reports → Neo4j Report 노드) ──────────────────────────


async def sync_report(
    report_id: int,
    meeting_id: int,
    file_name: str | None = None,
    file_path: str | None = None,
    submitter_department: str | None = None,
    human_status: str = "pending",
    related_agenda_ids: list | None = None,
    created_at: str | None = None,
    hitl_status: str | None = None,
    hitl_comment: str | None = None,
    hitl_rationale: str | None = None,
    hitl_reviewed_at: str | None = None,
) -> None:
    """Report 노드를 upsert하고 Meetings에 [:`발제`], 안건에 [:`도출`] 관계로 연결합니다.

    HITL 검토 결과(status·코멘트·ai_rationale)를 노드 속성으로 흡수하고
    임베딩 텍스트에도 포함해 벡터 검색에 활용한다.
    """
    report_neo_id = to_report_id(report_id)
    mg_id = to_mg_id(meeting_id)
    cypher = """
    MERGE (r:Report {id: $id})
    SET r.pg_id                = $pg_id,
        r.meeting_id           = $meeting_id,
        r.file_name            = $file_name,
        r.file_path            = $file_path,
        r.submitter_department = $submitter_department,
        r.human_status         = $human_status,
        r.created_at           = $created_at,
        r.hitl_status          = $hitl_status,
        r.hitl_comment         = $hitl_comment,
        r.hitl_rationale       = $hitl_rationale,
        r.hitl_reviewed_at     = $hitl_reviewed_at,
        r.updated_at           = $updated_at
    WITH r
    OPTIONAL MATCH (mg:Meetings {id: $mg_id})
    FOREACH (_ IN CASE WHEN mg IS NOT NULL THEN [1] ELSE [] END |
        MERGE (r)-[:`발제`]->(mg)
    )
    """
    if related_agenda_ids:
        for ag_id in related_agenda_ids:
            cypher += f"""
    WITH r
    OPTIONAL MATCH (ag:Agenda {{id: '{ag_id}'}})
    FOREACH (_ IN CASE WHEN ag IS NOT NULL THEN [1] ELSE [] END |
        MERGE (r)-[:`도출`]->(ag)
    )"""
    params = {
        "id": report_neo_id,
        "pg_id": report_id,
        "meeting_id": meeting_id,
        "file_name": file_name or "",
        "file_path": file_path or "",
        "submitter_department": submitter_department or "",
        "human_status": human_status,
        "created_at": created_at or "",
        "hitl_status": hitl_status or "",
        "hitl_comment": hitl_comment or "",
        "hitl_rationale": hitl_rationale or "",
        "hitl_reviewed_at": hitl_reviewed_at or "",
        "mg_id": mg_id,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    emb_text = " ".join(
        filter(
            None,
            [
                file_name,
                submitter_department,
                hitl_status,
                hitl_comment,
                hitl_rationale,
            ],
        )
    )
    embedding, content_hash = await _embed_if_changed(
        "Report", "id", report_neo_id, emb_text
    )
    if embedding:
        cypher += (
            "\n    WITH r SET r.embedding = $embedding, r.content_hash = $content_hash"
        )
        params["embedding"] = embedding
        params["content_hash"] = content_hash
    try:
        await run_cypher(cypher, params)
        logger.debug(f"[Neo4jSync] Report {report_id} 동기화 완료")
    except Exception as e:
        logger.error(f"[Neo4jSync] Report {report_id} 실패: {e}")
        _log_failure("sync_report", "report", str(report_id), e, params)


# ─── HITL 검토 → 대상 노드(Agenda/Report) 속성 동기화 ────────────────────────
# 검토 결과를 검토 대상 노드의 속성·임베딩으로 흡수한다.


def _hitl_props(review) -> dict:
    """HitlReview → sync_agenda/sync_report에 넘길 hitl_* kwargs."""
    return {
        "hitl_status": review.status,
        "hitl_comment": review.comment,
        "hitl_rationale": review.ai_rationale,
        "hitl_reviewed_at": review.reviewed_at.isoformat()
        if review.reviewed_at
        else None,
    }


def _latest_hitl_map(db: DBSession) -> tuple[dict, dict]:
    """target별 최신 HITL 리뷰의 hitl_* kwargs 맵 (agenda_id→props, report_id→props)."""
    by_agenda: dict = {}
    by_report: dict = {}
    if not hasattr(models, "HitlReview"):
        return by_agenda, by_report
    for r in db.query(models.HitlReview).order_by(models.HitlReview.id.asc()).all():
        props = _hitl_props(r)
        if r.target_type == "agenda" and r.agenda_id:
            by_agenda[r.agenda_id] = props  # 높은 id가 나중에 덮어써 최신 유지
        elif r.target_type == "report" and r.report_id:
            by_report[r.report_id] = props
    return by_agenda, by_report


async def sync_hitl_target(review_id: int) -> None:
    """HITL 검토 결과를 대상 Agenda/Report 노드 속성·임베딩에 반영한다 (PG→Neo4j).

    검토 대상 노드를 PG에서 다시 로드해 status·comment·ai_rationale와 함께 재동기화하므로,
    임베딩이 검토 내용을 포함해 재계산되어 벡터 검색에 노출된다.
    """
    db = SessionLocal()
    try:
        r = (
            db.query(models.HitlReview)
            .filter(models.HitlReview.id == review_id)
            .first()
        )
        if not r:
            return
        hitl = _hitl_props(r)
        if r.target_type == "agenda" and r.agenda_id:
            ag = db.query(models.Agenda).filter(models.Agenda.id == r.agenda_id).first()
            if not ag:
                return
            dept_str = ""
            if ag.department:
                dept_str = (
                    json.dumps(ag.department, ensure_ascii=False)
                    if isinstance(ag.department, (dict, list))
                    else str(ag.department)
                )
            await sync_agenda(
                ag.id,
                ag.meeting_id,
                title=ag.title,
                status=str(ag.status or "draft"),
                assignee_id=ag.assignee_id,
                priority=ag.priority or "medium",
                due_date=ag.due_date.isoformat() if ag.due_date else None,
                session_id=ag.session_id,
                department=dept_str,
                ai_evidence=ag.ai_evidence,
                created_at=ag.created_at.isoformat() if ag.created_at else None,
                **hitl,
            )
        elif r.target_type == "report" and r.report_id and hasattr(models, "Report"):
            rep = (
                db.query(models.Report).filter(models.Report.id == r.report_id).first()
            )
            if not rep:
                return
            await sync_report(
                report_id=rep.id,
                meeting_id=rep.meeting_id,
                file_name=rep.file_name,
                file_path=rep.file_path,
                submitter_department=rep.submitter_department,
                human_status=rep.human_status or "pending",
                related_agenda_ids=rep.related_agenda_ids or [],
                created_at=rep.created_at.isoformat() if rep.created_at else None,
                **hitl,
            )
    except Exception as e:
        logger.warning(
            f"[Neo4jSync] HITL→대상노드 동기화 실패 (review={review_id}): {e}"
        )
    finally:
        db.close()


# ─── 노드 유형별 벡터 유사도 검색 ───────────────────────────────────────────

_NODE_SEARCH_CONFIG: dict[str, tuple[str, list[str]]] = {
    "Meetings": (
        "meetingsEmbedding",
        ["id", "pg_id", "title", "description", "status", "type"],
    ),
    "Agenda": (
        "agendaEmbedding",
        [
            "id",
            "pg_id",
            "title",
            "content",
            "status",
            "category",
            "priority",
            "department",
            "hitl_status",
            "hitl_comment",
            "hitl_rationale",
        ],
    ),
    "Session": (
        "sessionEmbedding",
        [
            "id",
            "pg_id",
            "title",
            "description",
            "scheduled_at",
            "started_at",
            "ended_at",
            "type",
            "location",
        ],
    ),
    "Minutes": (
        "minutesEmbedding",
        ["pg_id", "file_name", "content_summary", "status", "generated_at"],
    ),
    "Report": (
        "reportEmbedding",
        [
            "id",
            "pg_id",
            "file_name",
            "submitter_department",
            "human_status",
            "created_at",
            "hitl_status",
            "hitl_comment",
            "hitl_rationale",
        ],
    ),
}


async def vector_search_node(
    query_text: str,
    node_label: str,
    top_k: int = 5,
    meeting_id: int | None = None,
) -> list[dict]:
    """임의의 노드 유형에 대해 텍스트 유사도 검색을 수행합니다."""
    if node_label not in _NODE_SEARCH_CONFIG:
        raise ValueError(
            f"지원하지 않는 노드 레이블: {node_label}. "
            f"가능한 값: {list(_NODE_SEARCH_CONFIG.keys())}"
        )

    index_name, return_props = _NODE_SEARCH_CONFIG[node_label]
    from graphdb.file_embedder import embed_query

    query_emb = await embed_query(query_text)
    return_clause = ", ".join(f"n.{p} AS {p}" for p in return_props)

    if meeting_id is not None:
        mg_id = to_mg_id(meeting_id)
        cypher = f"""
        CALL db.index.vector.queryNodes('{index_name}', $top_k, $embedding)
        YIELD node AS n, score
        WHERE EXISTS {{
            MATCH (n)-[*1..2]->(mg:Meetings {{id: $mg_id}})
        }}
        RETURN {return_clause}, score
        ORDER BY score DESC
        """
        params: dict = {"top_k": top_k * 3, "embedding": query_emb, "mg_id": mg_id}
    else:
        cypher = f"""
        CALL db.index.vector.queryNodes('{index_name}', $top_k, $embedding)
        YIELD node AS n, score
        RETURN {return_clause}, score
        ORDER BY score DESC
        """
        params = {"top_k": top_k, "embedding": query_emb}

    try:
        rows = await run_cypher(cypher, params)
        return rows[:top_k]
    except Exception as e:
        logger.error(f"[Neo4jSync] vector_search_node({node_label}) 실패: {e}")
        return []


# ─── 회의체 간 관계 동기화 ───────────────────────────────────────────────────


async def sync_meeting_relation(
    source_meeting_id: int,
    target_meeting_id: int,
    relation_type: str,
) -> None:
    rel_map = {"PARENT_OF": "상위", "RELATED_TO": "관련", "FOLLOW_UP": "후속"} # 레거시 호환
    rel = rel_map.get(relation_type.upper(), "관련")
    cypher = f"""
    MATCH (src:Meetings {{id: $src_id}})
    MATCH (tgt:Meetings {{id: $tgt_id}})
    MERGE (src)-[:`{rel}`]->(tgt)
    """
    try:
        await run_cypher(
            cypher,
            {
                "src_id": to_mg_id(source_meeting_id),
                "tgt_id": to_mg_id(target_meeting_id),
            },
        )
    except Exception as e:
        logger.error(f"[Neo4jSync] MeetingRelation 실패: {e}")
        _log_failure(
            "sync_meeting_relation",
            "meeting_relation",
            f"{source_meeting_id}_{target_meeting_id}",
            e,
            {},
        )


# ─── 삭제 동기화 ──────────────────────────────────────────────────────────────


# 삭제 전파는 실패를 호출자에게 알려야 아웃박스가 재시도할 수 있다 (P2-4)
# — 예외를 삼키지 않고 전파한다. fire-and-forget이 필요한 호출자는 스스로 감싼다.
async def delete_meeting(meeting_id: int) -> None:
    # 회의체 삭제 시 자식 노드(Session/Minutes/Agenda/Report + 청크)까지 함께 제거한다.
    # Meetings 노드만 DETACH DELETE하면 자식들이 orphan으로 그래프에 남는다(아카이브 ghost).
    # DETACH DELETE는 이 회의체의 모든 관계를 함께 제거하므로, 사용자가 수동 연결한
    # 회의체↔회의체 `협의`(PG에 없는 Neo4j 전용 관계)도 이때만 정상적으로 끊어진다.
    # 일반 동기화(sync_meeting_group MERGE / cleanup_deleted_from_pg)는 회의체가 PG에 남아 있는 한
    # 노드·관계를 보존하므로 `협의`는 끊기지 않는다.
    await run_cypher(
        """
        MATCH (mg:Meetings {id: $id})
        OPTIONAL MATCH (s:Session)-[:`소속`]->(mg)
        OPTIONAL MATCH (mn:Minutes)-[:`기록`]->(s)
        OPTIONAL MATCH (ag:Agenda)-[:`관할`]->(mg)
        OPTIONAL MATCH (r:Report)-[:`발제`]->(mg)
        OPTIONAL MATCH (rc:ReportChunk)-[:`청크`]->(r)
        OPTIONAL MATCH (mc:MinutesChunk)-[:`청크`]->(mn)
        WITH collect(DISTINCT mg) + collect(DISTINCT s) + collect(DISTINCT mn)
           + collect(DISTINCT ag) + collect(DISTINCT r) + collect(DISTINCT rc)
           + collect(DISTINCT mc) AS nodes
        UNWIND nodes AS n
        DETACH DELETE n
        """,
        {"id": to_mg_id(meeting_id)},
    )


async def delete_session(session_id: int) -> None:
    # 세션 삭제 시 그 세션의 회의록(Minutes)+청크도 함께 제거한다. PG 캐스케이드로 minutes가
    # 지워지면 Neo4j Minutes가 orphan으로 남는다. Minutes는 session_id 속성 또는 `기록` 관계로 연결.
    await run_cypher(
        """
        OPTIONAL MATCH (s:Session {id: $id})
        OPTIONAL MATCH (mn:Minutes) WHERE mn.session_id = $pg_id
        OPTIONAL MATCH (mc:MinutesChunk)-[:`청크`]->(mn)
        WITH collect(DISTINCT s) + collect(DISTINCT mn) + collect(DISTINCT mc) AS nodes
        UNWIND nodes AS n
        DETACH DELETE n
        """,
        {"id": to_session_id(session_id), "pg_id": session_id},
    )


async def delete_agenda(agenda_id: int) -> None:
    await run_cypher(
        "MATCH (ag:Agenda {id: $id}) DETACH DELETE ag", {"id": to_agenda_id(agenda_id)}
    )


async def delete_user(user_id: int) -> None:
    await run_cypher(
        "MATCH (u:User {pg_id: $pg_id}) DETACH DELETE u", {"pg_id": user_id}
    )


# ─── 실패 재시도 ──────────────────────────────────────────────────────────────


async def retry_failed_syncs(max_retries: int = 3) -> dict:
    return {"retried": 0, "recovered": 0, "skipped": 0}


# ─── PostgreSQL 전체 → Neo4j 마이그레이션 ────────────────────────────────────


async def sync_all_from_pg(db: DBSession | None = None) -> dict:
    """PostgreSQL 전체 → Neo4j 부트스트랩 동기화.
    앱 시작 시 또는 싱크 불일치 복구 시 호출합니다.
    정렬 순서: User → Department → Meetings → MeetingMember → Session → Agenda
               → Minutes → Report + ReportScore
    """
    close_db = False
    if db is None:
        db = SessionLocal()
        close_db = True

    stats: dict[str, Any] = {
        "users": 0,
        "departments": 0,
        "companies": 0,
        "meetings": 0,
        "meeting_members": 0,
        "sessions": 0,
        "agendas": 0,
        "minutes": 0,
        "reports": 0,
    }
    try:
        # 1. Users (Meetings 생성자/참여자 관계 연결을 위해 먼저 동기화)
        for u in db.query(models.User).all():
            await sync_user(
                user_id=u.id,
                name=u.name,
                email=u.email,
                company=u.company_name,
                department=u.department,
                position=u.position,
                created_at=u.created_at.isoformat() if u.created_at else None,
            )
            stats["users"] += 1

        # 2. Departments (User.department 기반 파생 노드)
        dept_names: set[str] = set()
        for u in db.query(models.User).all():
            if u.department and u.department.strip():
                dept_names.add(u.department.strip())
        for dept_name in dept_names:
            await sync_department(dept_name)
            stats["departments"] += 1

        # 3. Companies (User.company 기반 파생 노드)
        company_names: set[str] = set()
        for c in db.query(models.Company).all():
            if c.name and c.name.strip():
                company_names.add(c.name.strip())
        for company_name in company_names:
            await sync_company(company_name)
            stats["companies"] += 1

        # 4. Meetings
        for m in db.query(models.Meeting).all():
            await sync_meeting_group(
                m.id,
                m.title,
                m.description,
                guidelines=m.guidelines,
                status=str(m.status or "active"),
                meeting_type=str(m.type or ""),
                start_date=m.start_date.isoformat() if m.start_date else None,
                end_date=m.end_date.isoformat() if m.end_date else None,
                created_by=m.created_by,
                created_at=m.created_at.isoformat() if m.created_at else None,
            )
            stats["meetings"] += 1

        # 5. MeetingMembers (User-Meetings 구성원 관계)
        for mm in db.query(models.MeetingMember).all():
            await sync_meeting_member(
                meeting_id=mm.meeting_id,
                user_id=mm.user_id,
                role=mm.meeting_role,
            )
            stats["meeting_members"] += 1

        # 4. Session
        for s in db.query(models.MeetingSession).all():
            await sync_session(
                s.id,
                s.meeting_id,
                title=s.title or "",
                status=str(s.status or "scheduled"),
                scheduled_at=s.scheduled_at.isoformat() if s.scheduled_at else None,
                started_at=s.started_at.isoformat() if s.started_at else None,
                ended_at=s.ended_at.isoformat() if s.ended_at else None,
                location=s.location,
                session_type=s.type,
                description=s.description,
            )
            stats["sessions"] += 1

        # HITL 검토 결과를 대상 노드에 흡수하기 위한 최신 리뷰 맵 (Agenda/Report)
        hitl_agenda_map, hitl_report_map = _latest_hitl_map(db)

        # 5. Agenda (draft 제외 — draft는 사용자 확인 전이므로 그래프에 노출 안 함)
        for ag in db.query(models.Agenda).filter(models.Agenda.status != "draft").all():
            dept_str = ""
            if ag.department:
                dept_str = (
                    json.dumps(ag.department, ensure_ascii=False)
                    if isinstance(ag.department, (dict, list))
                    else str(ag.department)
                )
            await sync_agenda(
                ag.id,
                ag.meeting_id,
                title=ag.title,
                status=str(ag.status or "draft"),
                assignee_id=ag.assignee_id,
                priority=ag.priority or "medium",
                due_date=ag.due_date.isoformat() if ag.due_date else None,
                session_id=ag.session_id,
                department=dept_str,
                ai_evidence=ag.ai_evidence,
                created_at=ag.created_at.isoformat() if ag.created_at else None,
                **hitl_agenda_map.get(ag.id, {}),
            )
            stats["agendas"] += 1

        # 6. Minutes
        for mn in db.query(models.Minutes).all():
            await sync_minutes(
                mn.id,
                mn.session_id,
                content_summary=mn.content_summary,
                content_original=mn.content_original,
                file_name=mn.file_name,
                file_path=mn.file_path,
                recorder_id=mn.recorder_id,
                status=mn.status,
                generated_at=mn.generated_at.isoformat() if mn.generated_at else None,
            )
            stats["minutes"] += 1

        # 7. Report ← PG reports (Neo4j Report 노드)
        if hasattr(models, "Report"):
            for r in db.query(models.Report).all():
                await sync_report(
                    report_id=r.id,
                    meeting_id=r.meeting_id,
                    file_name=r.file_name,
                    file_path=r.file_path,
                    submitter_department=r.submitter_department,
                    human_status=r.human_status or "pending",
                    related_agenda_ids=r.related_agenda_ids or [],
                    created_at=r.created_at.isoformat() if r.created_at else None,
                    **hitl_report_map.get(r.id, {}),
                )
                stats["reports"] += 1

        # 8. PG에서 삭제된 노드 정리
        cleanup_stats = await cleanup_deleted_from_pg(db)
        stats["removed"] = cleanup_stats

    finally:
        if close_db:
            db.close()

    logger.info(f"[Neo4jSync] sync_all_from_pg 완료: {stats}")
    return stats


# ─── PG 삭제분 Neo4j 정리 ─────────────────────────────────────────────────────


async def cleanup_deleted_from_pg(db: DBSession) -> dict:
    """PG에서 삭제된 레코드를 Neo4j에서도 제거합니다.
    pg_id 프로퍼티가 있는 노드만 대상으로 하며, AI 에이전트가 생성한
    KB 노드(pg_id 없음)는 건드리지 않습니다.
    PG 테이블이 완전히 비어있을 때는 실수로 전체 삭제되는 것을 막기 위해 스킵합니다.
    """
    removed: dict[str, int] = {
        "users": 0,
        "departments": 0,
        "companies": 0,
        "meetings": 0,
        "sessions": 0,
        "agendas": 0,
        "minutes": 0,
        "reports": 0,
    }

    async def _detach_missing(label: str, pg_ids: list[int], stat_key: str) -> None:
        if not pg_ids:
            return  # PG 테이블이 비어있으면 전체 삭제 방지
        try:
            rows = await run_cypher(
                f"MATCH (n:{label}) WHERE n.pg_id IS NOT NULL AND NOT n.pg_id IN $ids "
                "RETURN count(n) AS cnt",
                {"ids": pg_ids},
            )
            cnt = rows[0]["cnt"] if rows else 0
            if cnt:
                await run_cypher(
                    f"MATCH (n:{label}) WHERE n.pg_id IS NOT NULL AND NOT n.pg_id IN $ids "
                    "DETACH DELETE n",
                    {"ids": pg_ids},
                )
                removed[stat_key] += cnt
                logger.info(f"[Neo4jSync] cleanup {label}: {cnt}개 삭제")
        except Exception as e:
            logger.warning(f"[Neo4jSync] cleanup {label} 실패 (무시): {e}")

    # 각 엔티티의 현재 PG ID 목록 수집
    pg_user_ids = [row[0] for row in db.query(models.User.id).all()]
    pg_meeting_ids = [row[0] for row in db.query(models.Meeting.id).all()]
    pg_session_ids = [row[0] for row in db.query(models.MeetingSession.id).all()]
    pg_agenda_ids = [row[0] for row in db.query(models.Agenda.id).all()]
    pg_minutes_ids = [row[0] for row in db.query(models.Minutes.id).all()]

    await _detach_missing("User", pg_user_ids, "users")
    await _detach_missing("Meetings", pg_meeting_ids, "meetings")
    await _detach_missing("Session", pg_session_ids, "sessions")
    await _detach_missing("Agenda", pg_agenda_ids, "agendas")
    await _detach_missing("Minutes", pg_minutes_ids, "minutes")

    if hasattr(models, "Report"):
        pg_report_ids = [row[0] for row in db.query(models.Report.id).all()]
        await _detach_missing("Report", pg_report_ids, "reports")

    # Department: PG에 별도 테이블 없으므로 User.department 기반으로 정리
    pg_dept_names = [
        row[0]
        for row in db.query(models.User.department).all()
        if row[0] and row[0].strip()
    ]
    if pg_dept_names:
        try:
            rows = await run_cypher(
                "MATCH (d:Department) WHERE NOT d.name IN $names RETURN count(d) AS cnt",
                {"names": pg_dept_names},
            )
            cnt = rows[0]["cnt"] if rows else 0
            if cnt:
                await run_cypher(
                    "MATCH (d:Department) WHERE NOT d.name IN $names DETACH DELETE d",
                    {"names": pg_dept_names},
                )
                removed["departments"] += cnt
                logger.info(f"[Neo4jSync] cleanup Department: {cnt}개 삭제")
        except Exception as e:
            logger.warning(f"[Neo4jSync] cleanup Department 실패 (무시): {e}")

    # Company: User.company 기반으로 정리
    pg_company_names = [
        row[0]
        for row in db.query(models.Company.name).all()
        if row[0] and row[0].strip()
    ]
    if pg_company_names:
        try:
            rows = await run_cypher(
                "MATCH (co:Company) WHERE NOT co.name IN $names RETURN count(co) AS cnt",
                {"names": pg_company_names},
            )
            cnt = rows[0]["cnt"] if rows else 0
            if cnt:
                await run_cypher(
                    "MATCH (co:Company) WHERE NOT co.name IN $names DETACH DELETE co",
                    {"names": pg_company_names},
                )
                removed["companies"] += cnt
                logger.info(f"[Neo4jSync] cleanup Company: {cnt}개 삭제")
        except Exception as e:
            logger.warning(f"[Neo4jSync] cleanup Company 실패 (무시): {e}")

    logger.info(f"[Neo4jSync] cleanup_deleted_from_pg 완료: {removed}")
    return removed
