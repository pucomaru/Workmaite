"""
neo4j_sync.py — Neo4j 동기화 서비스
=====================================
원칙:
  - PostgreSQL이 Source of Truth
  - Neo4j 동기화는 항상 try/except로 감싸 실패해도 메인 흐름 중단 없음
  - 실패 시 agent_logs(postgres)에 기록 → retry_failed_syncs으로 복구

Neo4j 노드 유형:
  MeetingGroup  ← PG Meeting
  Session       ← PG MeetingSession
  Agenda        ← PG Agenda / Todo
  Person        ← PG User
  Department    ← PG User.department (집계)
  Organization  ← PG User.company (집계)
  Document      ← 업로드 파일
  DocumentChunk ← 파일 청크 + embedding (VectorIndex)
  Minutes       ← PG Minutes
  AIJudgment    ← PG Report (AI 검토 레이어 결과)
  HumanJudgment ← PG HitlReview (사람 판단)
  Role          ← 관계 속성 (간사/참여자) — 별도 노드 없음
"""

from __future__ import annotations
import asyncio
import json
import logging
import os
from datetime import datetime
from itertools import groupby
from typing import Any, Optional

from sqlalchemy.orm import Session as DBSession

from database import SessionLocal
from neo4j_client import run_cypher

# file_embedder는 순환 임포트 방지를 위해 각 함수 내에서 지연 임포트합니다.
# (file_embedder → neo4j_sync → file_embedder 순환 참조 차단)
EMBED_DIM = 1536  # text-embedding-3-small 고정값

UPLOAD_DIR = os.environ["UPLOAD_DIR"]
logger = logging.getLogger(__name__)

# ─── VectorIndex 초기화 ───────────────────────────────────────────────────────

# ─── VectorIndex 대상 노드 목록 ──────────────────────────────────────────────
# (노드 레이블, 인덱스 이름, 프로퍼티)
_VECTOR_INDEXES: list[tuple[str, str, str]] = [
    ("DocumentChunk", "documentChunkEmbedding",  "embedding"),
    ("Agenda",        "agendaEmbedding",          "embedding"),
    ("Session",       "sessionEmbedding",         "embedding"),
    ("Document",      "documentEmbedding",        "embedding"),
    ("AIJudgment",    "aiJudgmentEmbedding",      "embedding"),
    ("HumanJudgment", "humanJudgmentEmbedding",   "embedding"),
]

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
            logger.warning(f"[Neo4jSync] VectorIndex '{index_name}' 초기화 실패 (무시): {e}")


async def _embed(text: str) -> list[float] | None:
    """텍스트를 임베딩 벡터로 변환합니다. 빈 문자열 또는 실패 시 None 반환."""
    text = text.strip()
    if not text:
        return None
    try:
        from file_embedder import embed_query  # 지연 임포트 (순환 참조 방지)
        return await embed_query(text)
    except Exception as e:
        logger.warning(f"[Neo4jSync] 임베딩 실패 (무시): {e}")
        return None


# ─── 실패 로그 ────────────────────────────────────────────────────────────────

def _log_failure(operation: str, entity_type: str, entity_id: str,
                 error: Exception, payload: dict | None = None) -> None:
    db: DBSession = SessionLocal()
    try:
        import models
        db.add(models.AgentLog(
            operation=operation, entity_type=entity_type, entity_id=str(entity_id),
            status="failed", error_detail=str(error)[:2000],
            payload=payload, retry_count=0,
        ))
        db.commit()
    except Exception as e2:
        logger.error(f"[Neo4jSync] agent_logs 기록 실패: {e2}")
    finally:
        db.close()


# ─── MeetingGroup 동기화 (PG Meeting) ────────────────────────────────────────

async def sync_meeting_group(
    meeting_id: int,
    title: str,
    purpose: str | None = None,
    status: str = "ACTIVE",
    meeting_type: str | None = None,
    start_date: str | None = None,
    created_at: str | None = None,
) -> None:
    """MeetingGroup 노드를 Neo4j에 upsert합니다."""
    mg_id = f"mg-{meeting_id}"
    cypher = """
    MERGE (mg:MeetingGroup {id: $id})
    SET mg.pg_id      = $pg_id,
        mg.title      = $title,
        mg.purpose    = $purpose,
        mg.status     = $status,
        mg.type       = $type,
        mg.start_date = $start_date,
        mg.created_at = $created_at,
        mg.updated_at = $updated_at
    """
    params = {
        "id": mg_id, "pg_id": meeting_id,
        "title": title, "purpose": purpose or "",
        "status": status, "type": meeting_type or "",
        "start_date": start_date or "",
        "created_at": created_at or "",
        "updated_at": datetime.utcnow().isoformat(),
    }
    try:
        await run_cypher(cypher, params)
        logger.debug(f"[Neo4jSync] MeetingGroup {meeting_id} 동기화 완료")
    except Exception as e:
        logger.error(f"[Neo4jSync] MeetingGroup {meeting_id} 실패: {e}")
        _log_failure("sync_meeting_group", "meeting_group", str(meeting_id), e, params)

# 하위 호환 alias
async def sync_meeting(*args, **kwargs):
    return await sync_meeting_group(*args, **kwargs)


# ─── Session 동기화 (PG MeetingSession) ──────────────────────────────────────

async def sync_session(
    session_id: int,
    meeting_id: int,
    title: str,
    status: str = "SCHEDULED",
    scheduled_at: str | None = None,
    location: str | None = None,
    meeting_type: str | None = None,  # 대면/비대면
    description: str | None = None,
) -> None:
    """Session 노드를 Neo4j에 upsert하고 MeetingGroup과 관계를 맺습니다."""
    mg_id = f"mg-{meeting_id}"
    s_id  = f"session-{session_id}"
    cypher = """
    MERGE (s:Session {id: $id})
    SET s.pg_id        = $pg_id,
        s.title        = $title,
        s.status       = $status,
        s.scheduled_at = $scheduled_at,
        s.location     = $location,
        s.meeting_type = $meeting_type,
        s.description  = $description,
        s.updated_at   = $updated_at
    WITH s
    MATCH (mg:MeetingGroup {id: $mg_id})
    MERGE (s)-[:소속]->(mg)
    """
    emb_text = " ".join(filter(None, [title, description]))
    embedding = await _embed(emb_text)
    cypher_with_emb = cypher + ("\n    SET s.embedding = $embedding" if embedding else "")
    params = {
        "id": s_id, "pg_id": session_id,
        "title": title, "status": status,
        "scheduled_at": scheduled_at or "", "location": location or "",
        "meeting_type": meeting_type or "", "description": description or "",
        "mg_id": mg_id, "updated_at": datetime.utcnow().isoformat(),
    }
    if embedding:
        params["embedding"] = embedding
    try:
        await run_cypher(cypher_with_emb, params)
        logger.debug(f"[Neo4jSync] Session {session_id} 동기화 완료")
    except Exception as e:
        logger.error(f"[Neo4jSync] Session {session_id} 실패: {e}")
        _log_failure("sync_session", "session", str(session_id), e, params)


# ─── Person 동기화 (PG User) ──────────────────────────────────────────────────

async def sync_user(
    user_id: int,
    name: str,
    email: str,
    department: str | None = None,
    company: str | None = None,
    position: str | None = None,
    status: str = "재직",
) -> None:
    """Person 노드를 upsert하고 Department / Organization 노드와 연결합니다."""
    p_id = f"p-{user_id}"
    cypher = """
    MERGE (p:Person {email: $email})
    ON CREATE SET p.id = $id
    SET p.pg_id      = $pg_id,
        p.id         = $id,
        p.name       = $name,
        p.email      = $email,
        p.department = $department,
        p.company    = $company,
        p.position   = $position,
        p.status     = $status,
        p.updated_at = $updated_at
    WITH p
    // Department 연결
    FOREACH (_ IN CASE WHEN $dept <> '' THEN [1] ELSE [] END |
        MERGE (d:Department {name: $dept})
        ON CREATE SET d.id = $dept_id, d.created_at = $updated_at
        MERGE (p)-[:소속]->(d)
    )
    WITH p
    // Organization 연결
    FOREACH (_ IN CASE WHEN $org <> '' THEN [1] ELSE [] END |
        MERGE (o:Organization {name: $org})
        ON CREATE SET o.id = $org_id, o.type = '회사', o.created_at = $updated_at
        MERGE (p)-[:소속조직]->(o)
    )
    """
    dept = department or ""
    org  = company or ""
    params = {
        "id": p_id, "pg_id": user_id,
        "name": name, "email": email,
        "department": dept, "company": org,
        "position": position or "", "status": status,
        "dept": dept, "dept_id": f"dept-{dept.replace(' ', '_')}",
        "org": org,  "org_id": f"org-{org.replace(' ', '_')}",
        "updated_at": datetime.utcnow().isoformat(),
    }
    try:
        await run_cypher(cypher, params)
    except Exception as e:
        logger.error(f"[Neo4jSync] User {user_id} 실패: {e}")
        _log_failure("sync_user", "user", str(user_id), e, params)


# ─── Department 독립 upsert ───────────────────────────────────────────────────

async def sync_department(dept_name: str, founded_at: str | None = None) -> None:
    """Department 노드를 단독으로 upsert합니다."""
    dept_id = f"dept-{dept_name.replace(' ', '_')}"
    cypher = """
    MERGE (d:Department {name: $name})
    ON CREATE SET d.id = $id, d.created_at = $created_at
    SET d.updated_at = $updated_at
    """
    try:
        await run_cypher(cypher, {
            "id": dept_id, "name": dept_name,
            "created_at": founded_at or datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
        })
    except Exception as e:
        logger.error(f"[Neo4jSync] Department '{dept_name}' 실패: {e}")


# ─── Organization 독립 upsert ─────────────────────────────────────────────────

async def sync_organization(org_name: str, org_type: str = "회사", founded_at: str | None = None) -> None:
    """Organization 노드를 단독으로 upsert합니다."""
    org_id = f"org-{org_name.replace(' ', '_')}"
    cypher = """
    MERGE (o:Organization {name: $name})
    ON CREATE SET o.id = $id, o.type = $type, o.created_at = $created_at
    SET o.updated_at = $updated_at
    """
    try:
        await run_cypher(cypher, {
            "id": org_id, "name": org_name, "type": org_type,
            "created_at": founded_at or datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
        })
    except Exception as e:
        logger.error(f"[Neo4jSync] Organization '{org_name}' 실패: {e}")


# ─── Agenda 동기화 ───────────────────────────────────────────────────────────

async def sync_agenda(
    agenda_id: int,
    meeting_id: int,
    title: str,
    content: str | None = None,
    status: str = "ON_HOLD",
    order_index: int = 0,
    assignee_id: int | None = None,
    priority: str = "중",
    due_date: str | None = None,
    category: str | None = None,
    created_at: str | None = None,
) -> None:
    """Agenda 노드를 upsert하고 MeetingGroup / 담당자와 연결합니다."""
    ag_id = f"agenda-{agenda_id}"
    mg_id = f"mg-{meeting_id}"
    cypher = """
    MERGE (ag:Agenda {id: $id})
    SET ag.pg_id       = $pg_id,
        ag.title       = $title,
        ag.content     = $content,
        ag.category    = $category,
        ag.status      = $status,
        ag.priority    = $priority,
        ag.order_index = $order_index,
        ag.due_date    = $due_date,
        ag.created_at  = $created_at,
        ag.updated_at  = $updated_at
    WITH ag
    MATCH (mg:MeetingGroup {id: $mg_id})
    MERGE (ag)-[:관할]->(mg)
    WITH ag
    OPTIONAL MATCH (p:Person {pg_id: $assignee_id})
    FOREACH (_ IN CASE WHEN p IS NOT NULL THEN [1] ELSE [] END |
        MERGE (p)-[:담당]->(ag)
    )
    """
    emb_text = " ".join(filter(None, [title, content]))
    embedding = await _embed(emb_text)
    cypher_with_emb = cypher + ("\n    SET ag.embedding = $embedding" if embedding else "")
    params = {
        "id": ag_id, "pg_id": agenda_id,
        "title": title, "content": content or "",
        "category": category or "", "status": status,
        "priority": priority, "order_index": order_index,
        "due_date": due_date or "", "created_at": created_at or "",
        "mg_id": mg_id, "assignee_id": assignee_id,
        "updated_at": datetime.utcnow().isoformat(),
    }
    if embedding:
        params["embedding"] = embedding
    try:
        await run_cypher(cypher_with_emb, params)
        logger.debug(f"[Neo4jSync] Agenda {agenda_id} 동기화 완료")
    except Exception as e:
        logger.error(f"[Neo4jSync] Agenda {agenda_id} 실패: {e}")
        _log_failure("sync_agenda", "agenda", str(agenda_id), e, params)


# ─── Minutes 동기화 ──────────────────────────────────────────────────────────

async def sync_minutes(
    minutes_id: int,
    session_id: int,
    content_summary: str | None = None,
    decisions: list | None = None,
) -> None:
    """Minutes 노드를 upsert하고 Session과 연결합니다."""
    s_id = f"session-{session_id}"
    cypher = """
    MERGE (mn:Minutes {pg_id: $pg_id})
    SET mn.session_id      = $session_id,
        mn.content_summary = $content_summary,
        mn.decisions       = $decisions,
        mn.updated_at      = $updated_at
    WITH mn
    MATCH (s:Session {id: $s_id})
    MERGE (mn)-[:생성]->(s)
    """
    params = {
        "pg_id": minutes_id, "session_id": session_id, "s_id": s_id,
        "content_summary": content_summary or "",
        "decisions": json.dumps(decisions or []),
        "updated_at": datetime.utcnow().isoformat(),
    }
    try:
        await run_cypher(cypher, params)
    except Exception as e:
        logger.error(f"[Neo4jSync] Minutes {minutes_id} 실패: {e}")
        _log_failure("sync_minutes", "minutes", str(minutes_id), e, params)


# ─── MeetingMember 관계 동기화 ────────────────────────────────────────────────

async def sync_meeting_member(meeting_id: int, user_id: int, role: str = "MEMBER") -> None:
    """Person → MeetingGroup 멤버십 관계를 upsert합니다."""
    rel   = "간사" if role.upper() in ("ADMIN", "간사") else "구성원"
    mg_id = f"mg-{meeting_id}"
    p_id  = f"p-{user_id}"
    cypher = f"""
    MATCH (mg:MeetingGroup {{id: $mg_id}})
    MATCH (p:Person {{id: $p_id}})
    MERGE (p)-[:`{rel}`]->(mg)
    """
    params = {"mg_id": mg_id, "p_id": p_id}
    try:
        await run_cypher(cypher, params)
    except Exception as e:
        logger.error(f"[Neo4jSync] MeetingMember {meeting_id}/{user_id} 실패: {e}")
        _log_failure("sync_meeting_member", "meeting_member",
                     f"{meeting_id}_{user_id}", e,
                     {"meeting_id": meeting_id, "user_id": user_id, "role": role})


async def delete_meeting_member(meeting_id: int, user_id: int) -> None:
    mg_id = f"mg-{meeting_id}"
    p_id  = f"p-{user_id}"
    cypher = """
    MATCH (p:Person {id: $p_id})-[r:`간사`|`구성원`]->(mg:MeetingGroup {id: $mg_id})
    DELETE r
    """
    try:
        await run_cypher(cypher, {"mg_id": mg_id, "p_id": p_id})
    except Exception as e:
        logger.error(f"[Neo4jSync] MeetingMember 삭제 실패: {e}")


async def update_meeting_member_role(meeting_id: int, user_id: int, new_role: str) -> None:
    await delete_meeting_member(meeting_id, user_id)
    await sync_meeting_member(meeting_id, user_id, new_role)


# ─── AIJudgment 동기화 (PG Report) ───────────────────────────────────────────

async def sync_ai_judgment(
    report_id: int,
    meeting_id: int,
    summary: str,
    recommendation: str | None = None,
    confidence: float | None = None,
    version: int = 1,
    generated_at: str | None = None,
) -> None:
    """AIJudgment 노드를 upsert하고 MeetingGroup과 연결합니다."""
    ai_id = f"ai-{report_id}"
    mg_id = f"mg-{meeting_id}"
    cypher = """
    MERGE (ai:AIJudgment {id: $id})
    SET ai.pg_id          = $pg_id,
        ai.summary        = $summary,
        ai.recommendation = $recommendation,
        ai.confidence     = $confidence,
        ai.version        = $version,
        ai.generated_at   = $generated_at,
        ai.updated_at     = $updated_at
    WITH ai
    MATCH (mg:MeetingGroup {id: $mg_id})
    MERGE (ai)-[:분석대상]->(mg)
    """
    emb_text = " ".join(filter(None, [summary, recommendation]))
    embedding = await _embed(emb_text)
    cypher_with_emb = cypher + ("\n    SET ai.embedding = $embedding" if embedding else "")
    params = {
        "id": ai_id, "pg_id": report_id,
        "summary": summary, "recommendation": recommendation or "",
        "confidence": confidence or 0.0, "version": version,
        "generated_at": generated_at or datetime.utcnow().isoformat(),
        "mg_id": mg_id, "updated_at": datetime.utcnow().isoformat(),
    }
    if embedding:
        params["embedding"] = embedding
    try:
        await run_cypher(cypher_with_emb, params)
        logger.debug(f"[Neo4jSync] AIJudgment {report_id} 동기화 완료")
    except Exception as e:
        logger.error(f"[Neo4jSync] AIJudgment {report_id} 실패: {e}")
        _log_failure("sync_ai_judgment", "ai_judgment", str(report_id), e, params)


# ─── HumanJudgment 동기화 (PG HitlReview) ────────────────────────────────────

async def sync_human_judgment(
    review_id: int,
    meeting_id: int | None,
    judgment: str,          # APPROVED | REJECTED | REVISED
    reason: str | None = None,
    version: int = 1,
    reviewer_id: int | None = None,
    judged_at: str | None = None,
    ai_judgment_id: int | None = None,  # 연결할 AIJudgment Report ID
) -> None:
    """HumanJudgment 노드를 upsert하고 MeetingGroup / AIJudgment와 연결합니다."""
    hj_id = f"hj-{review_id}"
    cypher = """
    MERGE (hj:HumanJudgment {id: $id})
    SET hj.pg_id    = $pg_id,
        hj.judgment = $judgment,
        hj.reason   = $reason,
        hj.version  = $version,
        hj.judged_at = $judged_at,
        hj.updated_at = $updated_at
    WITH hj
    OPTIONAL MATCH (mg:MeetingGroup {id: $mg_id})
    FOREACH (_ IN CASE WHEN mg IS NOT NULL THEN [1] ELSE [] END |
        MERGE (hj)-[:판단대상]->(mg)
    )
    WITH hj
    OPTIONAL MATCH (p:Person {pg_id: $reviewer_id})
    FOREACH (_ IN CASE WHEN p IS NOT NULL THEN [1] ELSE [] END |
        MERGE (p)-[:판단자]->(hj)
    )
    WITH hj
    OPTIONAL MATCH (ai:AIJudgment {id: $ai_id})
    FOREACH (_ IN CASE WHEN ai IS NOT NULL THEN [1] ELSE [] END |
        MERGE (hj)-[:검토대상]->(ai)
    )
    """
    emb_text = " ".join(filter(None, [judgment, reason]))
    embedding = await _embed(emb_text)
    cypher_with_emb = cypher + ("\n    SET hj.embedding = $embedding" if embedding else "")
    params = {
        "id": hj_id, "pg_id": review_id,
        "judgment": judgment, "reason": reason or "",
        "version": version,
        "judged_at": judged_at or datetime.utcnow().isoformat(),
        "mg_id": f"mg-{meeting_id}" if meeting_id else "",
        "reviewer_id": reviewer_id,
        "ai_id": f"ai-{ai_judgment_id}" if ai_judgment_id else "",
        "updated_at": datetime.utcnow().isoformat(),
    }
    if embedding:
        params["embedding"] = embedding
    try:
        await run_cypher(cypher_with_emb, params)
        logger.debug(f"[Neo4jSync] HumanJudgment {review_id} 동기화 완료")
    except Exception as e:
        logger.error(f"[Neo4jSync] HumanJudgment {review_id} 실패: {e}")
        _log_failure("sync_human_judgment", "human_judgment", str(review_id), e, params)


# ─── Document 노드 동기화 ────────────────────────────────────────────────────

async def sync_document(
    doc_id: str,
    file_name: str,
    title: str,
    doc_type: str,
    file_url: str | None = None,
    created_at: str | None = None,
    meeting_id: int | None = None,
    mg_id: str | None = None,
    agenda_neo4j_id: str | None = None,
    uploader_id: int | None = None,
) -> None:
    """Document 노드를 upsert하고 MeetingGroup / Agenda와 연결합니다."""
    emb_text = " ".join(filter(None, [title, file_name, doc_type]))
    embedding = await _embed(emb_text)
    emb_clause = "\n            d.embedding   = $embedding," if embedding else ""
    doc_params: dict = {
        "doc_id": doc_id, "file_name": file_name, "title": title,
        "doc_type": doc_type, "file_url": file_url or "",
        "created_at": created_at or datetime.utcnow().isoformat(),
        "uploader_id": uploader_id,
        "updated_at": datetime.utcnow().isoformat(),
    }
    if embedding:
        doc_params["embedding"] = embedding
    await run_cypher(
        f"""
        MERGE (d:Document {{id: $doc_id}})
        SET d.file_name   = $file_name,
            d.title       = $title,
            d.doc_type    = $doc_type,
            d.file_url    = $file_url,
            d.created_at  = $created_at,
            d.uploader_id = $uploader_id,{emb_clause}
            d.updated_at  = $updated_at
        """,
        doc_params,
    )
    # MeetingGroup 연결
    target_mg = mg_id or (f"mg-{meeting_id}" if meeting_id else None)
    if target_mg:
        try:
            await run_cypher(
                "MATCH (d:Document {id: $doc_id}), (mg:MeetingGroup {id: $mg_id}) "
                "MERGE (d)-[:첨부]->(mg)",
                {"doc_id": doc_id, "mg_id": target_mg},
            )
        except Exception as e:
            logger.warning(f"[Neo4jSync] Document-MeetingGroup 연결 실패 (무시): {e}")
    # Agenda 연결
    if agenda_neo4j_id:
        try:
            await run_cypher(
                "MATCH (d:Document {id: $doc_id}) "
                "OPTIONAL MATCH (ag:Agenda) WHERE ag.id = $ag_id OR toString(ag.pg_id) = $ag_id "
                "FOREACH (_ IN CASE WHEN ag IS NOT NULL THEN [1] ELSE [] END | MERGE (d)-[:첨부]->(ag))",
                {"doc_id": doc_id, "ag_id": agenda_neo4j_id},
            )
        except Exception as e:
            logger.warning(f"[Neo4jSync] Document-Agenda 연결 실패 (무시): {e}")
    logger.debug(f"[Neo4jSync] Document {doc_id} 저장 완료")


# ─── DocumentChunk (파일 임베딩) ──────────────────────────────────────────────

async def sync_document_chunk(
    chunk_id: str,
    source_file: str,
    meeting_id: int | None,
    session_id: int | None,
    chunk_index: int,
    text: str,
    embedding: list[float],
    metadata: dict | None = None,
) -> None:
    """DocumentChunk 노드를 VectorIndex와 함께 저장합니다."""
    mg_id = f"mg-{meeting_id}" if meeting_id else None
    s_id  = f"session-{session_id}" if session_id else None
    cypher = """
    MERGE (dc:DocumentChunk {chunk_id: $chunk_id})
    SET dc.source_file  = $source_file,
        dc.meeting_id   = $meeting_id,
        dc.session_id   = $session_id,
        dc.chunk_index  = $chunk_index,
        dc.text         = $text,
        dc.embedding    = $embedding,
        dc.metadata     = $metadata,
        dc.updated_at   = $updated_at
    WITH dc
    OPTIONAL MATCH (mg:MeetingGroup {id: $mg_id})
    FOREACH (_ IN CASE WHEN mg IS NOT NULL THEN [1] ELSE [] END |
        MERGE (dc)-[:출처]->(mg)
    )
    WITH dc
    OPTIONAL MATCH (s:Session {id: $s_id})
    FOREACH (_ IN CASE WHEN s IS NOT NULL THEN [1] ELSE [] END |
        MERGE (dc)-[:세션출처]->(s)
    )
    """
    params = {
        "chunk_id": chunk_id, "source_file": source_file,
        "meeting_id": meeting_id, "session_id": session_id,
        "mg_id": mg_id, "s_id": s_id,
        "chunk_index": chunk_index, "text": text,
        "embedding": embedding,
        "metadata": json.dumps(metadata or {}),
        "updated_at": datetime.utcnow().isoformat(),
    }
    try:
        await run_cypher(cypher, params)
        logger.debug(f"[Neo4jSync] DocumentChunk {chunk_id} 저장 완료")
    except Exception as e:
        logger.error(f"[Neo4jSync] DocumentChunk {chunk_id} 실패: {e}")
        _log_failure("sync_file_chunk", "file_chunk", chunk_id, e,
                     {k: v for k, v in params.items() if k != "embedding"})


# ─── 벡터 유사도 검색 ────────────────────────────────────────────────────────

async def vector_search(
    query_embedding: list[float],
    top_k: int = 5,
    meeting_id: int | None = None,
) -> list[dict]:
    """DocumentChunk VectorIndex 유사도 검색."""
    if meeting_id is not None:
        cypher = """
        CALL db.index.vector.queryNodes('documentChunkEmbedding', $top_k, $embedding)
        YIELD node AS dc, score
        WHERE dc.meeting_id = $meeting_id
        RETURN dc.chunk_id AS chunk_id, dc.source_file AS source_file,
               dc.text AS text, dc.chunk_index AS chunk_index, score
        ORDER BY score DESC
        """
        params: dict = {"top_k": top_k * 3, "embedding": query_embedding, "meeting_id": meeting_id}
    else:
        cypher = """
        CALL db.index.vector.queryNodes('documentChunkEmbedding', $top_k, $embedding)
        YIELD node AS dc, score
        RETURN dc.chunk_id AS chunk_id, dc.source_file AS source_file,
               dc.text AS text, dc.chunk_index AS chunk_index, score
        ORDER BY score DESC
        """
        params = {"top_k": top_k, "embedding": query_embedding}
    try:
        rows = await run_cypher(cypher, params)
        return rows[:top_k]
    except Exception as e:
        logger.error(f"[Neo4jSync] vector_search 실패: {e}")
        return []


# ─── 노드 유형별 벡터 유사도 검색 ───────────────────────────────────────────

# 노드 레이블 → (VectorIndex 이름, 반환 프로퍼티 목록)
_NODE_SEARCH_CONFIG: dict[str, tuple[str, list[str]]] = {
    "DocumentChunk": ("documentChunkEmbedding",  ["chunk_id", "source_file", "text", "chunk_index"]),
    "Agenda":        ("agendaEmbedding",          ["id", "pg_id", "title", "content", "status", "category"]),
    "Session":       ("sessionEmbedding",         ["id", "pg_id", "title", "description", "scheduled_at"]),
    "Document":      ("documentEmbedding",        ["id", "file_name", "title", "doc_type", "file_url"]),
    "AIJudgment":    ("aiJudgmentEmbedding",      ["id", "pg_id", "summary", "recommendation", "confidence", "version"]),
    "HumanJudgment": ("humanJudgmentEmbedding",   ["id", "pg_id", "judgment", "reason", "judged_at"]),
}


async def vector_search_node(
    query_text: str,
    node_label: str,
    top_k: int = 5,
    meeting_id: int | None = None,
) -> list[dict]:
    """
    임의의 노드 유형에 대해 텍스트 유사도 검색을 수행합니다.

    Args:
        query_text: 검색할 자연어 쿼리
        node_label: 'Agenda' | 'Session' | 'Document' | 'AIJudgment' | 'HumanJudgment' | 'DocumentChunk'
        top_k: 반환할 결과 수
        meeting_id: 지정 시 해당 MeetingGroup에 연결된 노드만 필터링

    Returns:
        [{score, ...node_properties}, ...]
    """
    if node_label not in _NODE_SEARCH_CONFIG:
        raise ValueError(f"지원하지 않는 노드 레이블: {node_label}. "
                         f"가능한 값: {list(_NODE_SEARCH_CONFIG.keys())}")

    index_name, return_props = _NODE_SEARCH_CONFIG[node_label]
    from file_embedder import embed_query  # 지연 임포트 (순환 참조 방지)
    query_emb = await embed_query(query_text)
    return_clause = ", ".join(f"n.{p} AS {p}" for p in return_props)

    if meeting_id is not None:
        mg_id = f"mg-{meeting_id}"
        cypher = f"""
        CALL db.index.vector.queryNodes('{index_name}', $top_k, $embedding)
        YIELD node AS n, score
        WHERE EXISTS {{
            MATCH (n)-[*1..2]->(mg:MeetingGroup {{id: $mg_id}})
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
    rel_map = {"PARENT_OF": "상위", "RELATED_TO": "관련", "FOLLOW_UP": "후속회의"}
    rel = rel_map.get(relation_type.upper(), "관련")
    cypher = f"""
    MATCH (src:MeetingGroup {{id: $src_id}})
    MATCH (tgt:MeetingGroup {{id: $tgt_id}})
    MERGE (src)-[:`{rel}`]->(tgt)
    """
    try:
        await run_cypher(cypher, {
            "src_id": f"mg-{source_meeting_id}",
            "tgt_id": f"mg-{target_meeting_id}",
        })
    except Exception as e:
        logger.error(f"[Neo4jSync] MeetingRelation 실패: {e}")
        _log_failure("sync_meeting_relation", "meeting_relation",
                     f"{source_meeting_id}_{target_meeting_id}", e, {})


# ─── 삭제 동기화 ──────────────────────────────────────────────────────────────

async def delete_meeting(meeting_id: int) -> None:
    try:
        await run_cypher("MATCH (mg:MeetingGroup {id: $id}) DETACH DELETE mg",
                         {"id": f"mg-{meeting_id}"})
    except Exception as e:
        logger.error(f"[Neo4jSync] MeetingGroup 삭제 실패: {e}")

async def delete_session(session_id: int) -> None:
    try:
        await run_cypher("MATCH (s:Session {id: $id}) DETACH DELETE s",
                         {"id": f"session-{session_id}"})
    except Exception as e:
        logger.error(f"[Neo4jSync] Session 삭제 실패: {e}")

async def delete_agenda(agenda_id: int) -> None:
    try:
        await run_cypher("MATCH (ag:Agenda {id: $id}) DETACH DELETE ag",
                         {"id": f"agenda-{agenda_id}"})
    except Exception as e:
        logger.error(f"[Neo4jSync] Agenda 삭제 실패: {e}")


# ─── 실패 재시도 ──────────────────────────────────────────────────────────────

async def retry_failed_syncs(max_retries: int = 3) -> dict:
    """agent_logs status='failed' 항목을 재시도합니다."""
    db: DBSession = SessionLocal()
    result = {"retried": 0, "recovered": 0, "skipped": 0}
    try:
        import models
        pending = (
            db.query(models.AgentLog)
            .filter(models.AgentLog.status == "failed",
                    models.AgentLog.retry_count < max_retries)
            .order_by(models.AgentLog.created_at)
            .limit(200).all()
        )

        chunk_logs  = [l for l in pending if l.operation == "sync_file_chunk"]
        entity_logs = [l for l in pending if l.operation != "sync_file_chunk"]

        _RETRY_MAP = {
            "sync_meeting_group": lambda p: sync_meeting_group(
                int(p.get("pg_id", 0)), p.get("title", ""), p.get("purpose"),
                p.get("status", "ACTIVE"), p.get("type")),
            "sync_meeting": lambda p: sync_meeting_group(
                int(p.get("pg_id", 0)), p.get("title", ""), p.get("purpose"),
                p.get("status", "ACTIVE"), p.get("type")),
            "sync_session": lambda p: sync_session(
                int(p.get("pg_id", 0)), int(p.get("meeting_id", 0)), p.get("title", ""),
                p.get("status", "SCHEDULED"), p.get("scheduled_at")),
            "sync_user": lambda p: sync_user(
                int(p.get("pg_id", 0)), p.get("name", ""), p.get("email", ""),
                p.get("department"), p.get("company"), p.get("position")),
            "sync_agenda": lambda p: sync_agenda(
                int(p.get("pg_id", 0)), int(p.get("meeting_id", 0)), p.get("title", ""),
                p.get("content"), p.get("status", "ON_HOLD"), int(p.get("order_index", 0)),
                p.get("assignee_id")),
            "sync_minutes": lambda p: sync_minutes(
                int(p.get("pg_id", 0)), int(p.get("session_id", 0)),
                p.get("content_summary"),
                json.loads(p["decisions"]) if isinstance(p.get("decisions"), str) else p.get("decisions")),
            "sync_meeting_member": lambda p: sync_meeting_member(
                int(p.get("meeting_id", 0)), int(p.get("user_id", 0)), p.get("role", "MEMBER")),
            "sync_ai_judgment": lambda p: sync_ai_judgment(
                int(p.get("pg_id", 0)), int(p.get("meeting_id", 0)),
                p.get("summary", ""), p.get("recommendation"), p.get("confidence")),
            "sync_human_judgment": lambda p: sync_human_judgment(
                int(p.get("pg_id", 0)), p.get("meeting_id"),
                p.get("judgment", "PENDING"), p.get("reason")),
            "sync_meeting_relation": lambda p: sync_meeting_relation(
                int(p.get("src_id", 0)), int(p.get("tgt_id", 0)), p.get("relation_type", "RELATED_TO")),
        }

        for log in entity_logs:
            result["retried"] += 1
            payload = log.payload or {}
            fn = _RETRY_MAP.get(log.operation)
            if not fn:
                result["skipped"] += 1; continue
            try:
                await fn(payload)
                log.status = "recovered"; log.updated_at = datetime.utcnow()
                db.commit(); result["recovered"] += 1
            except Exception as e:
                logger.error(f"[Retry] {log.id} 실패: {e}")
                log.retry_count += 1; log.updated_at = datetime.utcnow()
                db.commit()

        # 파일 청크 재시도
        if chunk_logs:
            from file_embedder import process_and_embed_file

            def _src(l: Any) -> str:
                return (l.payload or {}).get("source_file", "")

            for source_file, grp in groupby(sorted(chunk_logs, key=_src), key=_src):
                group = list(grp)
                result["retried"] += len(group)
                if not source_file:
                    result["skipped"] += len(group); continue

                from r2_storage import is_r2_url as _is_r2
                file_path = source_file if _is_r2(source_file) else os.path.join(UPLOAD_DIR, source_file)
                if not _is_r2(source_file) and not os.path.exists(file_path):
                    for l in group: l.retry_count = max_retries; l.updated_at = datetime.utcnow()
                    db.commit(); result["skipped"] += len(group); continue

                first = group[0].payload or {}
                try:
                    er = await process_and_embed_file(
                        file_path=file_path, file_name=source_file,
                        meeting_id=int(first["meeting_id"]) if first.get("meeting_id") else None,
                        session_id=int(first["session_id"]) if first.get("session_id") else None,
                    )
                    if er["embedded"] > 0:
                        for l in group: l.status = "recovered"; l.updated_at = datetime.utcnow()
                        result["recovered"] += len(group)
                    else:
                        for l in group: l.retry_count += 1; l.updated_at = datetime.utcnow()
                    db.commit()
                except Exception as e:
                    logger.error(f"[Retry] 파일 재임베딩 실패 {source_file}: {e}")
                    for l in group: l.retry_count += 1; l.updated_at = datetime.utcnow()
                    db.commit()
    finally:
        db.close()
    return result


# ─── PostgreSQL 전체 동기화 ───────────────────────────────────────────────────

async def sync_all_from_pg(db: DBSession | None = None) -> dict:
    """PostgreSQL 전체 → Neo4j 부트스트랩 동기화."""
    import models

    close_db = False
    if db is None:
        db = SessionLocal(); close_db = True

    stats: dict[str, int] = {
        "users": 0, "meeting_groups": 0, "members": 0,
        "sessions": 0, "agendas": 0, "minutes": 0,
        "meeting_relations": 0, "ai_judgments": 0, "human_judgments": 0,
    }
    try:
        # Person + Department + Organization
        for u in db.query(models.User).all():
            await sync_user(u.id, u.name, u.email, u.department, u.company, u.position)
            stats["users"] += 1

        # MeetingGroup
        for m in db.query(models.Meeting).all():
            await sync_meeting_group(
                m.id, m.title, m.purpose,
                str(m.status or "ACTIVE"), str(m.type or ""),
                m.start_date.isoformat() if m.start_date else None,
                m.created_at.isoformat() if m.created_at else None,
            )
            stats["meeting_groups"] += 1

        # MeetingMembers
        for mm in db.query(models.MeetingMember).all():
            await sync_meeting_member(mm.meeting_id, mm.user_id, mm.role)
            stats["members"] += 1

        # Sessions
        for s in db.query(models.MeetingSession).all():
            await sync_session(
                s.id, s.meeting_id, s.title or "",
                str(s.status or "SCHEDULED"),
                s.scheduled_at.isoformat() if s.scheduled_at else None,
                s.location,
            )
            stats["sessions"] += 1

        # Agendas
        for ag in db.query(models.Agenda).all():
            await sync_agenda(
                ag.id, ag.meeting_id, ag.title, ag.content,
                str(ag.status or "ON_HOLD"), ag.order_index or 0, ag.assignee_id,
                created_at=ag.created_at.isoformat() if ag.created_at else None,
            )
            stats["agendas"] += 1

        # Minutes
        for mn in db.query(models.Minutes).all():
            await sync_minutes(mn.id, mn.session_id, mn.content_summary)
            stats["minutes"] += 1

        # MeetingRelations
        if hasattr(models, "MeetingRelation"):
            for mr in db.query(models.MeetingRelation).all():
                await sync_meeting_relation(mr.source_meeting_id, mr.target_meeting_id, mr.relation_type)
                stats["meeting_relations"] += 1

        # AIJudgment ← Report (layer 결과 있는 것만)
        if hasattr(models, "Report"):
            for rp in db.query(models.Report).filter(models.Report.score.isnot(None)).all():
                summary = rp.layer3_result or rp.layer2_result or rp.layer1_result or ""
                if summary:
                    await sync_ai_judgment(
                        rp.id, rp.meeting_id,
                        summary=summary[:500],
                        confidence=round((rp.score or 0) / 100, 2),
                        version=rp.version or 1,
                        generated_at=rp.created_at.isoformat() if rp.created_at else None,
                    )
                    stats["ai_judgments"] += 1

        # HumanJudgment ← HitlReview (검토 완료된 것만)
        if hasattr(models, "HitlReview"):
            for hr in db.query(models.HitlReview).filter(
                models.HitlReview.status.in_(["APPROVED", "REJECTED", "REVISED"])
            ).all():
                await sync_human_judgment(
                    hr.id, hr.meeting_id,
                    judgment=hr.status,
                    reason=hr.comment,
                    reviewer_id=hr.reviewer_id,
                    judged_at=hr.reviewed_at.isoformat() if hr.reviewed_at else None,
                )
                stats["human_judgments"] += 1

    finally:
        if close_db:
            db.close()

    logger.info(f"[Neo4jSync] sync_all_from_pg 완료: {stats}")
    return stats
