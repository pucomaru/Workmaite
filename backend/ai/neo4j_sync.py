"""
neo4j_sync.py — Neo4j 동기화 서비스
=====================================
원칙:
  - PostgreSQL이 Source of Truth
  - Neo4j 동기화는 항상 try/except로 감싸 실패해도 메인 흐름 중단 없음

Neo4j 노드 유형:
  User          ← PG users
  Meetings      ← PG meetings
  Session       ← PG meeting_sessions
  Agenda        ← PG agenda
  Minutes       ← PG minutes
  AIJudgment    ← PG reports + report_scores
  HumanJudgment ← PG hitl_reviews
"""

from __future__ import annotations
import json
import logging
import os
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session as DBSession

from database import SessionLocal
from neo4j_client import run_cypher

EMBED_DIM = 1536
UPLOAD_DIR = os.environ.get("UPLOAD_DIR", "/tmp/uploads")
logger = logging.getLogger(__name__)


# ─── VectorIndex 대상 노드 목록 ──────────────────────────────────────────────

_VECTOR_INDEXES: list[tuple[str, str, str]] = [
    ("Meetings",      "meetingsEmbedding",      "embedding"),
    ("Agenda",        "agendaEmbedding",        "embedding"),
    ("Session",       "sessionEmbedding",       "embedding"),
    ("Minutes",       "minutesEmbedding",       "embedding"),
    ("AIJudgment",    "aiJudgmentEmbedding",    "embedding"),
    ("HumanJudgment", "humanJudgmentEmbedding", "embedding"),
    ("DocumentChunk", "documentChunkEmbedding", "embedding"),
    ("ReportChunk",   "reportChunkEmbedding",   "embedding"),
    ("MinutesChunk",  "minutesChunkEmbedding",  "embedding"),
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
    text = text.strip()
    if not text:
        return None
    try:
        from file_embedder import embed_query
        return await embed_query(text)
    except Exception as e:
        logger.warning(f"[Neo4jSync] 임베딩 실패 (무시): {e}")
        return None


def _log_failure(operation: str, entity_type: str, entity_id: str,
                 error: Exception, payload: dict | None = None) -> None:
    logger.warning(f"[Neo4jSync] 동기화 실패: {operation}/{entity_type}/{entity_id} — {error}")


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
    now = datetime.utcnow().isoformat()
    cypher = """
    MERGE (u:User {pg_id: $pg_id})
    SET u.name       = $name,
        u.email      = $email,
        u.company    = $company,
        u.department = $department,
        u.position   = $position,
        u.created_at = coalesce(u.created_at, $created_at),
        u.updated_at = $updated_at
    """
    try:
        await run_cypher(cypher, {
            "pg_id":      user_id,
            "name":       name,
            "email":      email,
            "company":    company or "",
            "department": department or "",
            "position":   position or "",
            "created_at": created_at or now,
            "updated_at": now,
        })
    except Exception as e:
        logger.error(f"[Neo4jSync] sync_user 실패 (user_id={user_id}): {e}")


async def sync_meeting_member(
    meeting_id: int,
    user_id: int,
    role: str,
) -> None:
    """User-Meetings 참여 관계를 upsert합니다."""
    cypher = """
    MATCH (u:User {pg_id: $user_id})
    MATCH (mg:Meetings {id: $mg_id})
    MERGE (u)-[r:참여]->(mg)
    SET r.role = $role
    """
    try:
        await run_cypher(cypher, {
            "user_id": user_id,
            "mg_id":   f"mg-{meeting_id}",
            "role":    role,
        })
    except Exception as e:
        logger.error(f"[Neo4jSync] sync_meeting_member 실패 (meeting_id={meeting_id}, user_id={user_id}): {e}")


async def delete_meeting_member(
    meeting_id: int,
    user_id: int,
) -> None:
    """User-Meetings 참여 관계를 삭제합니다."""
    cypher = """
    MATCH (u:User {pg_id: $user_id})-[r:참여]->(mg:Meetings {id: $mg_id})
    DELETE r
    """
    try:
        await run_cypher(cypher, {"user_id": user_id, "mg_id": f"mg-{meeting_id}"})
    except Exception as e:
        logger.error(f"[Neo4jSync] delete_meeting_member 실패 (meeting_id={meeting_id}, user_id={user_id}): {e}")


async def update_meeting_member_role(
    meeting_id: int,
    user_id: int,
    role: str,
) -> None:
    """User-Meetings 참여 관계의 role을 업데이트합니다."""
    cypher = """
    MATCH (u:User {pg_id: $user_id})-[r:참여]->(mg:Meetings {id: $mg_id})
    SET r.role = $role
    """
    try:
        await run_cypher(cypher, {
            "user_id": user_id,
            "mg_id":   f"mg-{meeting_id}",
            "role":    role,
        })
    except Exception as e:
        logger.error(f"[Neo4jSync] update_meeting_member_role 실패 (meeting_id={meeting_id}, user_id={user_id}): {e}")


# ─── Meetings 동기화 (PG meetings) ───────────────────────────────────────────

async def sync_meeting_group(
    meeting_id: int,
    title: str,
    description: str | None = None,
    guidelines: str | None = None,
    status: str = "active",
    meeting_type: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    created_by: int | None = None,
    created_at: str | None = None,
) -> None:
    """Meetings 노드를 Neo4j에 upsert합니다."""
    mg_id = f"mg-{meeting_id}"
    cypher = """
    MERGE (mg:Meetings {id: $id})
    SET mg.pg_id       = $pg_id,
        mg.title       = $title,
        mg.description = $description,
        mg.guidelines  = $guidelines,
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
        MERGE (creator)-[:생성]->(mg)
    )
    """
    params = {
        "id": mg_id, "pg_id": meeting_id,
        "title": title,
        "description": description or "",
        "guidelines": guidelines or "",
        "status": status,
        "type": meeting_type or "",
        "start_date": start_date or "",
        "end_date": end_date or "",
        "created_by": created_by,
        "created_at": created_at or "",
        "updated_at": datetime.utcnow().isoformat(),
    }
    embedding = await _embed(guidelines or "")
    if embedding:
        cypher += "\n    WITH mg SET mg.embedding = $embedding"
        params["embedding"] = embedding
    try:
        await run_cypher(cypher, params)
        logger.debug(f"[Neo4jSync] Meetings {meeting_id} 동기화 완료")
    except Exception as e:
        logger.error(f"[Neo4jSync] Meetings {meeting_id} 실패: {e}")
        _log_failure("sync_meeting_group", "meeting_group", str(meeting_id), e, params)

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
) -> None:
    """Session 노드를 Neo4j에 upsert하고 Meetings과 관계를 맺습니다."""
    mg_id = f"mg-{meeting_id}"
    s_id  = f"session-{session_id}"
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
    MATCH (mg:Meetings {id: $mg_id})
    MERGE (s)-[:소속]->(mg)
    """
    emb_text = " ".join(filter(None, [title, description, location]))
    embedding = await _embed(emb_text)
    if embedding:
        cypher += "\n    WITH s SET s.embedding = $embedding"
    params = {
        "id": s_id, "pg_id": session_id,
        "title": title, "status": status,
        "scheduled_at": scheduled_at or "",
        "started_at": started_at or "",
        "ended_at": ended_at or "",
        "location": location or "",
        "session_type": session_type or "",
        "description": description or "",
        "mg_id": mg_id,
        "updated_at": datetime.utcnow().isoformat(),
    }
    if embedding:
        params["embedding"] = embedding
    try:
        await run_cypher(cypher, params)
        logger.debug(f"[Neo4jSync] Session {session_id} 동기화 완료")
    except Exception as e:
        logger.error(f"[Neo4jSync] Session {session_id} 실패: {e}")
        _log_failure("sync_session", "session", str(session_id), e, params)


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
) -> None:
    """Agenda 노드를 upsert하고 Meetings / Session / 담당자와 연결합니다."""
    ag_id = f"agenda-{agenda_id}"
    mg_id = f"mg-{meeting_id}"
    s_id  = f"session-{session_id}" if session_id else None
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
        ag.updated_at   = $updated_at
    WITH ag
    MATCH (mg:Meetings {id: $mg_id})
    MERGE (ag)-[:관할]->(mg)
    WITH ag
    OPTIONAL MATCH (s:Session {id: $s_id})
    FOREACH (_ IN CASE WHEN s IS NOT NULL THEN [1] ELSE [] END |
        MERGE (ag)-[:발제세션]->(s)
    )
    WITH ag
    OPTIONAL MATCH (assignee:User {pg_id: $assignee_id})
    FOREACH (_ IN CASE WHEN assignee IS NOT NULL THEN [1] ELSE [] END |
        MERGE (assignee)-[:담당]->(ag)
    )
    """
    if isinstance(ai_evidence, (dict, list)):
        ai_evidence = json.dumps(ai_evidence, ensure_ascii=False)
    emb_text = " ".join(filter(None, [title, ai_evidence]))
    embedding = await _embed(emb_text)
    if embedding:
        cypher += "\n    WITH ag SET ag.embedding = $embedding"
    params = {
        "id": ag_id, "pg_id": agenda_id,
        "title": title,
        "status": status,
        "assignee_id": assignee_id,
        "priority": priority,
        "due_date": due_date or "",
        "department": department or "",
        "ai_evidence": ai_evidence or "",
        "created_at": created_at or "",
        "mg_id": mg_id, "s_id": s_id,
        "updated_at": datetime.utcnow().isoformat(),
    }
    if embedding:
        params["embedding"] = embedding
    try:
        await run_cypher(cypher, params)
        logger.debug(f"[Neo4jSync] Agenda {agenda_id} 동기화 완료")
    except Exception as e:
        logger.error(f"[Neo4jSync] Agenda {agenda_id} 실패: {e}")
        _log_failure("sync_agenda", "agenda", str(agenda_id), e, params)


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
    """Minutes 노드를 upsert하고 Session / recorder User와 연결합니다."""
    s_id = f"session-{session_id}"
    cypher = """
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
    MATCH (s:Session {id: $s_id})
    MERGE (mn)-[:생성]->(s)
    WITH mn
    OPTIONAL MATCH (recorder:User {pg_id: $recorder_id})
    FOREACH (_ IN CASE WHEN recorder IS NOT NULL THEN [1] ELSE [] END |
        MERGE (recorder)-[:작성]->(mn)
    )
    """
    emb_text = " ".join(filter(None, [content_summary, file_name]))
    embedding = await _embed(emb_text)
    if embedding:
        cypher += "\n    WITH mn SET mn.embedding = $embedding"
    params = {
        "pg_id": minutes_id, "session_id": session_id, "s_id": s_id,
        "content_summary": content_summary or "",
        "content_original": content_original or "",
        "file_name": file_name or "",
        "file_path": file_path or "",
        "recorder_id": recorder_id,
        "status": status or "draft",
        "generated_at": generated_at or "",
        "updated_at": datetime.utcnow().isoformat(),
    }
    if embedding:
        params["embedding"] = embedding
    try:
        await run_cypher(cypher, params)
        logger.debug(f"[Neo4jSync] Minutes {minutes_id} 동기화 완료")
    except Exception as e:
        logger.error(f"[Neo4jSync] Minutes {minutes_id} 실패: {e}")
        _log_failure("sync_minutes", "minutes", str(minutes_id), e, params)


# ─── MeetingMember 관계 동기화 ────────────────────────────────────────────────

# ─── AIJudgment 동기화 (PG reports + report_scores) ──────────────────────────

async def sync_ai_judgment(
    report_id: int,
    meeting_id: int,
    # PG reports 필드
    upload_id: int | None = None,
    version: int = 1,
    submitter_department: str | None = None,
    file_name: str | None = None,
    file_path: str | None = None,
    human_status: str = "pending",
    parent_id: int | None = None,
    created_at: str | None = None,
    # PG report_scores 필드 (있을 때만)
    ai_status: str | None = None,
    total_score: float | None = None,
    detail_scores: dict | None = None,
    feedback: str | None = None,
    # AI 분석 레이어 (에이전트가 채우는 값)
    summary: str | None = None,
    recommendation: str | None = None,
    confidence: float | None = None,
) -> None:
    """AIJudgment 노드를 upsert하고 Meetings / uploader User와 연결합니다."""
    ai_id = f"ai-{report_id}"
    mg_id = f"mg-{meeting_id}"
    cypher = """
    MERGE (ai:AIJudgment {id: $id})
    SET ai.pg_id                = $pg_id,
        ai.meeting_id           = $meeting_id,
        ai.upload_id            = $upload_id,
        ai.version              = $version,
        ai.submitter_department = $submitter_department,
        ai.file_name            = $file_name,
        ai.file_path            = $file_path,
        ai.human_status         = $human_status,
        ai.parent_id            = $parent_id,
        ai.ai_status            = $ai_status,
        ai.total_score          = $total_score,
        ai.detail_scores        = $detail_scores,
        ai.feedback             = $feedback,
        ai.summary              = $summary,
        ai.recommendation       = $recommendation,
        ai.confidence           = $confidence,
        ai.created_at           = $created_at,
        ai.updated_at           = $updated_at
    WITH ai
    MATCH (mg:Meetings {id: $mg_id})
    MERGE (ai)-[:분석대상]->(mg)
    WITH ai
    OPTIONAL MATCH (uploader:User {pg_id: $upload_id})
    FOREACH (_ IN CASE WHEN uploader IS NOT NULL THEN [1] ELSE [] END |
        MERGE (uploader)-[:제출]->(ai)
    )
    """
    emb_text = " ".join(filter(None, [summary, recommendation, feedback, file_name]))
    embedding = await _embed(emb_text)
    if embedding:
        cypher += "\n    WITH ai SET ai.embedding = $embedding"
    params = {
        "id": ai_id, "pg_id": report_id,
        "meeting_id": meeting_id,
        "upload_id": upload_id,
        "version": version,
        "submitter_department": submitter_department or "",
        "file_name": file_name or "",
        "file_path": file_path or "",
        "human_status": human_status,
        "parent_id": parent_id,
        "ai_status": ai_status or "pending",
        "total_score": total_score,
        "detail_scores": json.dumps(detail_scores or {}),
        "feedback": feedback or "",
        "summary": summary or "",
        "recommendation": recommendation or "",
        "confidence": confidence or 0.0,
        "created_at": created_at or "",
        "mg_id": mg_id,
        "updated_at": datetime.utcnow().isoformat(),
    }
    if embedding:
        params["embedding"] = embedding
    try:
        await run_cypher(cypher, params)
        logger.debug(f"[Neo4jSync] AIJudgment {report_id} 동기화 완료")
    except Exception as e:
        logger.error(f"[Neo4jSync] AIJudgment {report_id} 실패: {e}")
        _log_failure("sync_ai_judgment", "ai_judgment", str(report_id), e, params)


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
) -> None:
    """Report 노드를 upsert하고 Meetings에 [:첨부] 관계로 연결합니다."""
    report_neo_id = f"report-{report_id}"
    mg_id = f"mg-{meeting_id}"
    cypher = """
    MERGE (r:Report {id: $id})
    SET r.pg_id                = $pg_id,
        r.meeting_id           = $meeting_id,
        r.file_name            = $file_name,
        r.file_path            = $file_path,
        r.submitter_department = $submitter_department,
        r.human_status         = $human_status,
        r.created_at           = $created_at,
        r.updated_at           = $updated_at
    WITH r
    MATCH (mg:Meetings {id: $mg_id})
    MERGE (r)-[:`첨부`]->(mg)
    """
    if related_agenda_ids:
        for ag_id in related_agenda_ids:
            cypher += f"""
    WITH r
    OPTIONAL MATCH (ag:Agenda {{id: '{ag_id}'}})
    FOREACH (_ IN CASE WHEN ag IS NOT NULL THEN [1] ELSE [] END |
        MERGE (r)-[:`첨부`]->(ag)
    )"""
    params = {
        "id": report_neo_id, "pg_id": report_id,
        "meeting_id": meeting_id,
        "file_name": file_name or "",
        "file_path": file_path or "",
        "submitter_department": submitter_department or "",
        "human_status": human_status,
        "created_at": created_at or "",
        "mg_id": mg_id,
        "updated_at": datetime.utcnow().isoformat(),
    }
    try:
        await run_cypher(cypher, params)
        logger.debug(f"[Neo4jSync] Report {report_id} 동기화 완료")
    except Exception as e:
        logger.error(f"[Neo4jSync] Report {report_id} 실패: {e}")
        _log_failure("sync_report", "report", str(report_id), e, params)


# ─── HumanJudgment 동기화 (PG hitl_reviews) ──────────────────────────────────

async def sync_human_judgment(
    review_id: int,
    meeting_id: int | None,
    judgment: str,              # PG status: approved | rejected | pending
    reason: str | None = None,  # PG review_comment
    version: int = 1,
    reviewer_id: int | None = None,
    judged_at: str | None = None,
    ai_judgment_id: int | None = None,  # 연결할 AIJudgment (PG report_id)
    target_type: str | None = None,
    target_id: int | None = None,
    review_prompt: str | None = None,
    ai_rationale: str | None = None,
    created_at: str | None = None,
) -> None:
    """HumanJudgment 노드를 upsert하고 Meetings / AIJudgment / reviewer와 연결합니다."""
    hj_id = f"hj-{review_id}"
    cypher = """
    MERGE (hj:HumanJudgment {id: $id})
    SET hj.pg_id         = $pg_id,
        hj.judgment      = $judgment,
        hj.reason        = $reason,
        hj.version       = $version,
        hj.target_type   = $target_type,
        hj.target_id     = $target_id,
        hj.review_prompt = $review_prompt,
        hj.ai_rationale  = $ai_rationale,
        hj.judged_at     = $judged_at,
        hj.created_at    = $created_at,
        hj.updated_at    = $updated_at
    WITH hj
    OPTIONAL MATCH (mg:Meetings {id: $mg_id})
    FOREACH (_ IN CASE WHEN mg IS NOT NULL THEN [1] ELSE [] END |
        MERGE (hj)-[:판단대상]->(mg)
    )
    WITH hj
    OPTIONAL MATCH (p:User {pg_id: $reviewer_id})
    FOREACH (_ IN CASE WHEN p IS NOT NULL THEN [1] ELSE [] END |
        MERGE (p)-[:판단자]->(hj)
    )
    WITH hj
    OPTIONAL MATCH (ai:AIJudgment {id: $ai_id})
    FOREACH (_ IN CASE WHEN ai IS NOT NULL THEN [1] ELSE [] END |
        MERGE (hj)-[:검토대상]->(ai)
    )
    """
    emb_text = " ".join(filter(None, [judgment, reason, ai_rationale]))
    embedding = await _embed(emb_text)
    if embedding:
        cypher += "\n    WITH hj SET hj.embedding = $embedding"
    params = {
        "id": hj_id, "pg_id": review_id,
        "judgment": judgment,
        "reason": reason or "",
        "version": version,
        "target_type": target_type or "",
        "target_id": target_id,
        "review_prompt": review_prompt or "",
        "ai_rationale": ai_rationale or "",
        "judged_at": judged_at or "",
        "created_at": created_at or "",
        "mg_id": f"mg-{meeting_id}" if meeting_id else "",
        "reviewer_id": reviewer_id,
        "ai_id": f"ai-{ai_judgment_id}" if ai_judgment_id else "",
        "updated_at": datetime.utcnow().isoformat(),
    }
    if embedding:
        params["embedding"] = embedding
    try:
        await run_cypher(cypher, params)
        logger.debug(f"[Neo4jSync] HumanJudgment {review_id} 동기화 완료")
    except Exception as e:
        logger.error(f"[Neo4jSync] HumanJudgment {review_id} 실패: {e}")
        _log_failure("sync_human_judgment", "human_judgment", str(review_id), e, params)


# ─── 노드 유형별 벡터 유사도 검색 ───────────────────────────────────────────

_NODE_SEARCH_CONFIG: dict[str, tuple[str, list[str]]] = {
    "Agenda":        ("agendaEmbedding",         ["id", "pg_id", "title", "content", "status", "category", "priority", "department"]),
    "Session":       ("sessionEmbedding",        ["id", "pg_id", "title", "description", "scheduled_at", "started_at", "ended_at", "type", "location"]),
    "Minutes":       ("minutesEmbedding",        ["pg_id", "file_name", "content_summary", "status", "generated_at"]),
    "AIJudgment":    ("aiJudgmentEmbedding",     ["id", "pg_id", "file_name", "summary", "recommendation", "confidence", "total_score", "human_status", "ai_status"]),
    "HumanJudgment": ("humanJudgmentEmbedding",  ["id", "pg_id", "judgment", "reason", "target_type", "judged_at"]),
}


async def vector_search_node(
    query_text: str,
    node_label: str,
    top_k: int = 5,
    meeting_id: int | None = None,
) -> list[dict]:
    """임의의 노드 유형에 대해 텍스트 유사도 검색을 수행합니다."""
    if node_label not in _NODE_SEARCH_CONFIG:
        raise ValueError(f"지원하지 않는 노드 레이블: {node_label}. "
                         f"가능한 값: {list(_NODE_SEARCH_CONFIG.keys())}")

    index_name, return_props = _NODE_SEARCH_CONFIG[node_label]
    from file_embedder import embed_query
    query_emb = await embed_query(query_text)
    return_clause = ", ".join(f"n.{p} AS {p}" for p in return_props)

    if meeting_id is not None:
        mg_id = f"mg-{meeting_id}"
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
    rel_map = {"PARENT_OF": "상위", "RELATED_TO": "관련", "FOLLOW_UP": "후속회의"}
    rel = rel_map.get(relation_type.upper(), "관련")
    cypher = f"""
    MATCH (src:Meetings {{id: $src_id}})
    MATCH (tgt:Meetings {{id: $tgt_id}})
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
        await run_cypher("MATCH (mg:Meetings {id: $id}) DETACH DELETE mg",
                         {"id": f"mg-{meeting_id}"})
    except Exception as e:
        logger.error(f"[Neo4jSync] Meetings 삭제 실패: {e}")

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
    return {"retried": 0, "recovered": 0, "skipped": 0}


# ─── PostgreSQL 전체 → Neo4j 마이그레이션 ────────────────────────────────────

async def sync_all_from_pg(db: DBSession | None = None) -> dict:
    """PostgreSQL 전체 → Neo4j 부트스트랩 동기화.
    앱 시작 시 또는 싱크 불일치 복구 시 호출합니다.
    처리 순서: User → Meetings → MeetingMember → Session → Agenda
               → Minutes → Report(AIJudgment)+ReportScore → HitlReview
    """
    import models

    close_db = False
    if db is None:
        db = SessionLocal(); close_db = True

    stats: dict[str, int] = {
        "users": 0, "meetings": 0, "meeting_members": 0,
        "sessions": 0, "agendas": 0,
        "minutes": 0, "ai_judgments": 0, "human_judgments": 0,
    }
    try:
        # 1. Users (Meetings 생성자/참여자 관계 연결을 위해 먼저 동기화)
        for u in db.query(models.User).all():
            await sync_user(
                user_id=u.id,
                name=u.name,
                email=u.email,
                company=u.company,
                department=u.department,
                position=u.position,
                created_at=u.created_at.isoformat() if u.created_at else None,
            )
            stats["users"] += 1

        # 2. Meetings
        for m in db.query(models.Meeting).all():
            await sync_meeting_group(
                m.id, m.title, m.description,
                guidelines=m.guidelines,
                status=str(m.status or "active"),
                meeting_type=str(m.type or ""),
                start_date=m.start_date.isoformat() if m.start_date else None,
                end_date=m.end_date.isoformat() if m.end_date else None,
                created_by=m.created_by,
                created_at=m.created_at.isoformat() if m.created_at else None,
            )
            stats["meetings"] += 1

        # 3. MeetingMembers (User-Meetings 참여 관계)
        for mm in db.query(models.MeetingMember).all():
            await sync_meeting_member(
                meeting_id=mm.meeting_id,
                user_id=mm.user_id,
                role=mm.role,
            )
            stats["meeting_members"] += 1

        # 4. Session
        for s in db.query(models.MeetingSession).all():
            await sync_session(
                s.id, s.meeting_id,
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
                ag.id, ag.meeting_id,
                title=ag.title,
                status=str(ag.status or "draft"),
                assignee_id=ag.assignee_id,
                priority=ag.priority or "medium",
                due_date=ag.due_date.isoformat() if ag.due_date else None,
                session_id=ag.session_id,
                department=dept_str,
                ai_evidence=ag.ai_evidence,
                created_at=ag.created_at.isoformat() if ag.created_at else None,
            )
            stats["agendas"] += 1

        # 6. Minutes
        for mn in db.query(models.Minutes).all():
            await sync_minutes(
                mn.id, mn.session_id,
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
                )
                stats["ai_judgments"] += 1

        # 8. HumanJudgment ← PG hitl_reviews
        if hasattr(models, "HitlReview"):
            for hr in db.query(models.HitlReview).all():
                await sync_human_judgment(
                    review_id=hr.id,
                    meeting_id=None,
                    judgment=hr.status,
                    reason=json.dumps(hr.review_comment, ensure_ascii=False) if isinstance(hr.review_comment, (dict, list)) else hr.review_comment,
                    reviewer_id=hr.reviewer_id,
                    judged_at=hr.reviewed_at.isoformat() if hr.reviewed_at else None,
                    target_type=hr.target_type,
                    target_id=hr.target_id,
                    review_prompt=json.dumps(hr.review_prompt, ensure_ascii=False) if isinstance(hr.review_prompt, (dict, list)) else hr.review_prompt,
                    ai_rationale=hr.ai_rationale,
                    created_at=hr.created_at.isoformat() if hr.created_at else None,
                )
                stats["human_judgments"] += 1

        # 7. PG에서 삭제된 노드 정리
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
    import models

    removed: dict[str, int] = {
        "users": 0, "meetings": 0, "sessions": 0, "agendas": 0,
        "minutes": 0, "ai_judgments": 0, "human_judgments": 0,
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
    pg_user_ids     = [row[0] for row in db.query(models.User.id).all()]
    pg_meeting_ids  = [row[0] for row in db.query(models.Meeting.id).all()]
    pg_session_ids  = [row[0] for row in db.query(models.MeetingSession.id).all()]
    pg_agenda_ids   = [row[0] for row in db.query(models.Agenda.id).all()]
    pg_minutes_ids  = [row[0] for row in db.query(models.Minutes.id).all()]

    await _detach_missing("User",      pg_user_ids,    "users")
    await _detach_missing("Meetings",  pg_meeting_ids, "meetings")
    await _detach_missing("Session",   pg_session_ids, "sessions")
    await _detach_missing("Agenda",    pg_agenda_ids,  "agendas")
    await _detach_missing("Minutes",   pg_minutes_ids, "minutes")

    if hasattr(models, "Report"):
        pg_report_ids = [row[0] for row in db.query(models.Report.id).all()]
        await _detach_missing("AIJudgment", pg_report_ids, "ai_judgments")

    if hasattr(models, "HitlReview"):
        pg_review_ids = [row[0] for row in db.query(models.HitlReview.id).all()]
        await _detach_missing("HumanJudgment", pg_review_ids, "human_judgments")

    logger.info(f"[Neo4jSync] cleanup_deleted_from_pg 완료: {removed}")
    return removed
