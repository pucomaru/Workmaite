"""
neo4j_sync.py — Dual-Write 동기화 서비스
=========================================
원칙:
  - PostgreSQL이 Source of Truth
  - Neo4j 동기화는 항상 try/except로 감싸 실패해도 메인 흐름 중단 없음
  - 실패 시 agent_logs(postgres)에 기록 → 재시도 작업(retry_failed_syncs)으로 복구
  - VectorIndex: 문서 청크 임베딩을 Neo4j에 저장하고 유사도 검색 지원

지원 노드 유형:
  Meeting       → :Meeting          (pg_id=PostgreSQL PK)
  Session       → :Session          (pg_id=PostgreSQL PK)
  User          → :Person           (pg_id=PostgreSQL PK)
  Agenda        → :Agenda           (pg_id=PostgreSQL PK)
  Minutes       → :Minutes          (pg_id=PostgreSQL PK)
  MeetingMember → (Person)-[]->(Meeting) 관계
  FileChunk     → :DocumentChunk    (with embedding vector)
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

UPLOAD_DIR = os.getenv("UPLOAD_DIR", "uploads")

logger = logging.getLogger(__name__)

# ─── Neo4j VectorIndex 초기화 Cypher ────────────────────────────────────────
# 서버 기동 시 main.py lifespan에서 한 번 실행
INIT_VECTOR_INDEX_CYPHER = """
CREATE VECTOR INDEX documentChunkEmbedding IF NOT EXISTS
FOR (n:DocumentChunk)
ON (n.embedding)
OPTIONS {
  indexConfig: {
    `vector.dimensions`: 1536,
    `vector.similarity_function`: 'cosine'
  }
}
"""


async def init_vector_index() -> None:
    """Neo4j VectorIndex가 없으면 생성합니다."""
    try:
        await run_cypher(INIT_VECTOR_INDEX_CYPHER)
        logger.info("[Neo4jSync] VectorIndex 초기화 완료")
    except Exception as e:
        logger.warning(f"[Neo4jSync] VectorIndex 초기화 실패 (무시): {e}")


# ─── 실패 로그 기록 ──────────────────────────────────────────────────────────

def _log_failure(
    operation: str,
    entity_type: str,
    entity_id: str,
    error: Exception,
    payload: dict | None = None,
) -> None:
    """동기화 실패를 agent_logs 테이블에 기록합니다 (동기 DB 세션 사용)."""
    db: DBSession = SessionLocal()
    try:
        import models
        log = models.AgentLog(
            operation=operation,
            entity_type=entity_type,
            entity_id=str(entity_id),
            status="failed",
            error_detail=str(error)[:2000],
            payload=payload,
            retry_count=0,
        )
        db.add(log)
        db.commit()
    except Exception as e2:
        logger.error(f"[Neo4jSync] agent_logs 기록 실패: {e2}")
    finally:
        db.close()


def _mark_recovered(log_id: int) -> None:
    """재시도 성공 시 agent_logs 상태를 'recovered'로 업데이트합니다."""
    db: DBSession = SessionLocal()
    try:
        import models
        log = db.query(models.AgentLog).filter(models.AgentLog.id == log_id).first()
        if log:
            log.status = "recovered"
            log.updated_at = datetime.utcnow()
            db.commit()
    except Exception as e:
        logger.error(f"[Neo4jSync] mark_recovered 실패: {e}")
    finally:
        db.close()


# ─── Meeting 동기화 ──────────────────────────────────────────────────────────

async def sync_meeting(
    meeting_id: int,
    title: str,
    purpose: str | None = None,
    status: str = "ACTIVE",
    meeting_type: str | None = None,
) -> None:
    """Meeting 노드를 Neo4j에 upsert합니다."""
    cypher = """
    MERGE (m:Meeting {pg_id: $pg_id})
    SET m.title       = $title,
        m.purpose     = $purpose,
        m.status      = $status,
        m.type        = $type,
        m.updated_at  = $updated_at
    """
    params = {
        "pg_id": meeting_id,
        "title": title,
        "purpose": purpose or "",
        "status": status,
        "type": meeting_type or "",
        "updated_at": datetime.utcnow().isoformat(),
    }
    try:
        await run_cypher(cypher, params)
        logger.debug(f"[Neo4jSync] Meeting {meeting_id} 동기화 완료")
    except Exception as e:
        logger.error(f"[Neo4jSync] Meeting {meeting_id} 동기화 실패: {e}")
        _log_failure("sync_meeting", "meeting", str(meeting_id), e, params)


# ─── Session 동기화 ──────────────────────────────────────────────────────────

async def sync_session(
    session_id: int,
    meeting_id: int,
    title: str,
    status: str = "scheduled",
    scheduled_at: str | None = None,
) -> None:
    """Session 노드를 Neo4j에 upsert하고 Meeting 노드와 관계를 맺습니다."""
    cypher = """
    MERGE (s:Session {pg_id: $pg_id})
    SET s.title        = $title,
        s.status       = $status,
        s.scheduled_at = $scheduled_at,
        s.meeting_id   = $meeting_id,
        s.updated_at   = $updated_at
    WITH s
    MATCH (m:Meeting {pg_id: $meeting_id})
    MERGE (s)-[:`소속`]->(m)
    """
    params = {
        "pg_id": session_id,
        "meeting_id": meeting_id,
        "title": title,
        "status": status,
        "scheduled_at": scheduled_at or "",
        "updated_at": datetime.utcnow().isoformat(),
    }
    try:
        await run_cypher(cypher, params)
        logger.debug(f"[Neo4jSync] Session {session_id} 동기화 완료")
    except Exception as e:
        logger.error(f"[Neo4jSync] Session {session_id} 동기화 실패: {e}")
        _log_failure("sync_session", "session", str(session_id), e, params)


# ─── User(Person) 동기화 ─────────────────────────────────────────────────────

async def sync_user(
    user_id: int,
    name: str,
    email: str,
    department: str | None = None,
    company: str | None = None,
    position: str | None = None,
) -> None:
    """Person 노드를 Neo4j에 upsert합니다."""
    cypher = """
    MERGE (p:Person {pg_id: $pg_id})
    SET p.name       = $name,
        p.email      = $email,
        p.department = $department,
        p.company    = $company,
        p.position   = $position,
        p.updated_at = $updated_at
    """
    params = {
        "pg_id": user_id,
        "name": name,
        "email": email,
        "department": department or "",
        "company": company or "",
        "position": position or "",
        "updated_at": datetime.utcnow().isoformat(),
    }
    try:
        await run_cypher(cypher, params)
    except Exception as e:
        logger.error(f"[Neo4jSync] User {user_id} 동기화 실패: {e}")
        _log_failure("sync_user", "user", str(user_id), e, params)


# ─── Agenda 동기화 ───────────────────────────────────────────────────────────

async def sync_agenda(
    agenda_id: int,
    meeting_id: int,
    title: str,
    content: str | None = None,
    status: str = "ON_HOLD",
    order_index: int = 0,
    assignee_id: int | None = None,
) -> None:
    """Agenda 노드를 Neo4j에 upsert하고 Meeting 노드와 관계를 맺습니다."""
    cypher = """
    MERGE (ag:Agenda {pg_id: $pg_id})
    SET ag.meeting_id   = $meeting_id,
        ag.title        = $title,
        ag.content      = $content,
        ag.status       = $status,
        ag.order_index  = $order_index,
        ag.updated_at   = $updated_at
    WITH ag
    MATCH (m:Meeting {pg_id: $meeting_id})
    MERGE (ag)-[:`관할`]->(m)
    WITH ag
    OPTIONAL MATCH (p:Person {pg_id: $assignee_id})
    FOREACH (_ IN CASE WHEN p IS NOT NULL THEN [1] ELSE [] END |
        MERGE (p)-[:`담당`]->(ag)
    )
    """
    params = {
        "pg_id": agenda_id,
        "meeting_id": meeting_id,
        "title": title,
        "content": content or "",
        "status": status,
        "order_index": order_index,
        "assignee_id": assignee_id,
        "updated_at": datetime.utcnow().isoformat(),
    }
    try:
        await run_cypher(cypher, params)
        logger.debug(f"[Neo4jSync] Agenda {agenda_id} 동기화 완료")
    except Exception as e:
        logger.error(f"[Neo4jSync] Agenda {agenda_id} 동기화 실패: {e}")
        _log_failure("sync_agenda", "agenda", str(agenda_id), e, params)


# ─── Minutes 동기화 ───────────────────────────────────────────────────────────

async def sync_minutes(
    minutes_id: int,
    session_id: int,
    content_summary: str | None = None,
    decisions: list | None = None,
) -> None:
    """Minutes 노드를 Neo4j에 upsert하고 Session과 관계를 맺습니다."""
    cypher = """
    MERGE (mn:Minutes {pg_id: $pg_id})
    SET mn.session_id      = $session_id,
        mn.content_summary = $content_summary,
        mn.decisions       = $decisions,
        mn.updated_at      = $updated_at
    WITH mn
    MATCH (s:Session {pg_id: $session_id})
    MERGE (mn)-[:`생성`]->(s)
    """
    params = {
        "pg_id": minutes_id,
        "session_id": session_id,
        "content_summary": content_summary or "",
        "decisions": json.dumps(decisions or []),
        "updated_at": datetime.utcnow().isoformat(),
    }
    try:
        await run_cypher(cypher, params)
        logger.debug(f"[Neo4jSync] Minutes {minutes_id} 동기화 완료")
    except Exception as e:
        logger.error(f"[Neo4jSync] Minutes {minutes_id} 동기화 실패: {e}")
        _log_failure("sync_minutes", "minutes", str(minutes_id), e, params)


# ─── MeetingMember 관계 동기화 ────────────────────────────────────────────────

async def sync_meeting_member(
    meeting_id: int,
    user_id: int,
    role: str = "MEMBER",
) -> None:
    """Person → Meeting 멤버십 관계를 Neo4j에 upsert합니다."""
    rel = "간사" if role.upper() in ("ADMIN", "ADMIN_OF", "간사") else "구성원"
    cypher = f"""
    MATCH (m:Meeting {{pg_id: $meeting_id}})
    MATCH (p:Person {{pg_id: $user_id}})
    MERGE (p)-[:`{rel}`]->(m)
    """
    params = {"meeting_id": meeting_id, "user_id": user_id}
    try:
        await run_cypher(cypher, params)
        logger.debug(f"[Neo4jSync] MeetingMember {meeting_id}/{user_id} 동기화 완료")
    except Exception as e:
        logger.error(f"[Neo4jSync] MeetingMember {meeting_id}/{user_id} 동기화 실패: {e}")
        _log_failure(
            "sync_meeting_member", "meeting_member", f"{meeting_id}_{user_id}", e,
            {"meeting_id": meeting_id, "user_id": user_id, "role": role},
        )


# ─── DocumentChunk (파일 임베딩) 동기화 ──────────────────────────────────────

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
    """
    DocumentChunk 노드를 Neo4j에 저장합니다.
    embedding 벡터가 함께 저장되므로 VectorIndex로 유사도 검색이 가능합니다.
    """
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
    // Meeting과 연결
    OPTIONAL MATCH (m:Meeting {pg_id: $meeting_id})
    FOREACH (_ IN CASE WHEN m IS NOT NULL THEN [1] ELSE [] END |
        MERGE (dc)-[:`출처`]->(m)
    )
    WITH dc
    // Session과 연결
    OPTIONAL MATCH (s:Session {pg_id: $session_id})
    FOREACH (_ IN CASE WHEN s IS NOT NULL THEN [1] ELSE [] END |
        MERGE (dc)-[:`세션출처`]->(s)
    )
    """
    params = {
        "chunk_id": chunk_id,
        "source_file": source_file,
        "meeting_id": meeting_id,
        "session_id": session_id,
        "chunk_index": chunk_index,
        "text": text,
        "embedding": embedding,
        "metadata": json.dumps(metadata or {}),
        "updated_at": datetime.utcnow().isoformat(),
    }
    try:
        await run_cypher(cypher, params)
        logger.debug(f"[Neo4jSync] DocumentChunk {chunk_id} 저장 완료")
    except Exception as e:
        logger.error(f"[Neo4jSync] DocumentChunk {chunk_id} 저장 실패: {e}")
        _log_failure(
            "sync_file_chunk", "file_chunk", chunk_id, e,
            {k: v for k, v in params.items() if k != "embedding"},  # 임베딩 제외 저장
        )


# ─── 벡터 유사도 검색 ────────────────────────────────────────────────────────

async def vector_search(
    query_embedding: list[float],
    top_k: int = 5,
    meeting_id: int | None = None,
) -> list[dict]:
    """
    DocumentChunk 벡터 인덱스에서 유사도 검색을 수행합니다.
    meeting_id를 지정하면 해당 회의체 문서만 검색합니다.
    """
    if meeting_id is not None:
        cypher = """
        CALL db.index.vector.queryNodes('documentChunkEmbedding', $top_k, $embedding)
        YIELD node AS dc, score
        WHERE dc.meeting_id = $meeting_id
        RETURN dc.chunk_id   AS chunk_id,
               dc.source_file AS source_file,
               dc.text        AS text,
               dc.chunk_index AS chunk_index,
               score
        ORDER BY score DESC
        """
        params = {"top_k": top_k * 3, "embedding": query_embedding, "meeting_id": meeting_id}
    else:
        cypher = """
        CALL db.index.vector.queryNodes('documentChunkEmbedding', $top_k, $embedding)
        YIELD node AS dc, score
        RETURN dc.chunk_id   AS chunk_id,
               dc.source_file AS source_file,
               dc.text        AS text,
               dc.chunk_index AS chunk_index,
               score
        ORDER BY score DESC
        """
        params = {"top_k": top_k, "embedding": query_embedding}

    try:
        rows = await run_cypher(cypher, params)
        return rows[:top_k]
    except Exception as e:
        logger.error(f"[Neo4jSync] vector_search 실패: {e}")
        return []


# ─── 실패 재시도 ──────────────────────────────────────────────────────────────

async def retry_failed_syncs(max_retries: int = 3) -> dict:
    """
    agent_logs에서 status='failed'인 항목을 꺼내 재시도합니다.
    최대 max_retries 회 이상 실패한 항목은 건너뜁니다.
    파일 청크는 소스 파일 단위로 묶어 재임베딩합니다.
    """
    db: DBSession = SessionLocal()
    result = {"retried": 0, "recovered": 0, "skipped": 0}
    try:
        import models
        pending = (
            db.query(models.AgentLog)
            .filter(
                models.AgentLog.status == "failed",
                models.AgentLog.retry_count < max_retries,
            )
            .order_by(models.AgentLog.created_at)
            .limit(200)
            .all()
        )

        # 파일 청크와 일반 엔티티 분리
        chunk_logs = [l for l in pending if l.operation == "sync_file_chunk"]
        entity_logs = [l for l in pending if l.operation != "sync_file_chunk"]

        # ── 일반 엔티티 재시도 ────────────────────────────────────────────────
        for log in entity_logs:
            result["retried"] += 1
            payload: dict = log.payload or {}
            success = False
            try:
                op = log.operation
                if op == "sync_meeting":
                    await sync_meeting(
                        meeting_id=int(payload.get("pg_id", log.entity_id)),
                        title=payload.get("title", ""),
                        purpose=payload.get("purpose"),
                        status=payload.get("status", "ACTIVE"),
                        meeting_type=payload.get("type"),
                    )
                    success = True
                elif op == "sync_session":
                    await sync_session(
                        session_id=int(payload.get("pg_id", log.entity_id)),
                        meeting_id=int(payload.get("meeting_id", 0)),
                        title=payload.get("title", ""),
                        status=payload.get("status", "scheduled"),
                        scheduled_at=payload.get("scheduled_at"),
                    )
                    success = True
                elif op == "sync_user":
                    await sync_user(
                        user_id=int(payload.get("pg_id", log.entity_id)),
                        name=payload.get("name", ""),
                        email=payload.get("email", ""),
                        department=payload.get("department"),
                        company=payload.get("company"),
                        position=payload.get("position"),
                    )
                    success = True
                elif op == "sync_agenda":
                    await sync_agenda(
                        agenda_id=int(payload.get("pg_id", log.entity_id)),
                        meeting_id=int(payload.get("meeting_id", 0)),
                        title=payload.get("title", ""),
                        content=payload.get("content"),
                        status=payload.get("status", "ON_HOLD"),
                        order_index=int(payload.get("order_index", 0)),
                        assignee_id=payload.get("assignee_id"),
                    )
                    success = True
                elif op == "sync_minutes":
                    decisions_raw = payload.get("decisions", "[]")
                    decisions_list = json.loads(decisions_raw) if isinstance(decisions_raw, str) else decisions_raw
                    await sync_minutes(
                        minutes_id=int(payload.get("pg_id", log.entity_id)),
                        session_id=int(payload.get("session_id", 0)),
                        content_summary=payload.get("content_summary"),
                        decisions=decisions_list,
                    )
                    success = True
                elif op == "sync_meeting_member":
                    await sync_meeting_member(
                        meeting_id=int(payload.get("meeting_id", 0)),
                        user_id=int(payload.get("user_id", 0)),
                        role=payload.get("role", "MEMBER"),
                    )
                    success = True
                else:
                    logger.warning(f"[Retry] 알 수 없는 operation: {op}")
                    result["skipped"] += 1
                    continue

            except Exception as e:
                logger.error(f"[Retry] {log.id} 재시도 실패: {e}")
                log.retry_count += 1
                log.updated_at = datetime.utcnow()
                db.commit()
                continue

            if success:
                log.status = "recovered"
                log.updated_at = datetime.utcnow()
                db.commit()
                result["recovered"] += 1

        # ── 파일 청크 재시도: 소스 파일 단위로 묶어 재임베딩 ──────────────────
        if chunk_logs:
            from file_embedder import process_and_embed_file

            def _source_key(l: Any) -> str:
                return (l.payload or {}).get("source_file", "") if l.payload else ""

            sorted_chunks = sorted(chunk_logs, key=_source_key)
            for source_file, group_iter in groupby(sorted_chunks, key=_source_key):
                group_list = list(group_iter)
                result["retried"] += len(group_list)

                if not source_file:
                    result["skipped"] += len(group_list)
                    continue

                file_path = os.path.join(UPLOAD_DIR, source_file)
                if not os.path.exists(file_path):
                    logger.warning(f"[Retry] 파일 없음: {file_path}, 재시도 건너뜀")
                    for l in group_list:
                        l.retry_count = max_retries  # 파일 없으면 더 이상 재시도 안 함
                        l.updated_at = datetime.utcnow()
                    db.commit()
                    result["skipped"] += len(group_list)
                    continue

                first_payload = group_list[0].payload or {}
                meta_raw = first_payload.get("metadata", "{}")
                meta: dict = json.loads(meta_raw) if isinstance(meta_raw, str) else (meta_raw or {})
                meeting_id_val = first_payload.get("meeting_id") or meta.get("meeting_id")
                session_id_val = first_payload.get("session_id") or meta.get("session_id")

                try:
                    embed_result = await process_and_embed_file(
                        file_path=file_path,
                        file_name=source_file,
                        meeting_id=int(meeting_id_val) if meeting_id_val else None,
                        session_id=int(session_id_val) if session_id_val else None,
                    )
                    if embed_result["embedded"] > 0:
                        for l in group_list:
                            l.status = "recovered"
                            l.updated_at = datetime.utcnow()
                        db.commit()
                        result["recovered"] += len(group_list)
                        logger.info(f"[Retry] 파일 재임베딩 성공: {source_file} ({len(group_list)}청크)")
                    else:
                        for l in group_list:
                            l.retry_count += 1
                            l.updated_at = datetime.utcnow()
                        db.commit()
                except Exception as e:
                    logger.error(f"[Retry] 파일 재임베딩 실패 {source_file}: {e}")
                    for l in group_list:
                        l.retry_count += 1
                        l.updated_at = datetime.utcnow()
                    db.commit()

    finally:
        db.close()

    return result


# ─── 삭제 동기화 ──────────────────────────────────────────────────────────────

async def delete_meeting(meeting_id: int) -> None:
    """Meeting 노드 및 연결된 모든 관계/하위 노드를 Neo4j에서 삭제합니다."""
    cypher = "MATCH (m:Meeting {pg_id: $pg_id}) DETACH DELETE m"
    try:
        await run_cypher(cypher, {"pg_id": meeting_id})
        logger.debug(f"[Neo4jSync] Meeting {meeting_id} 삭제 완료")
    except Exception as e:
        logger.error(f"[Neo4jSync] Meeting {meeting_id} 삭제 실패: {e}")
        _log_failure("delete_meeting", "meeting", str(meeting_id), e)


async def delete_session(session_id: int) -> None:
    """Session 노드를 Neo4j에서 삭제합니다."""
    cypher = "MATCH (s:Session {pg_id: $pg_id}) DETACH DELETE s"
    try:
        await run_cypher(cypher, {"pg_id": session_id})
        logger.debug(f"[Neo4jSync] Session {session_id} 삭제 완료")
    except Exception as e:
        logger.error(f"[Neo4jSync] Session {session_id} 삭제 실패: {e}")
        _log_failure("delete_session", "session", str(session_id), e)


async def delete_agenda(agenda_id: int) -> None:
    """Agenda 노드를 Neo4j에서 삭제합니다."""
    cypher = "MATCH (ag:Agenda {pg_id: $pg_id}) DETACH DELETE ag"
    try:
        await run_cypher(cypher, {"pg_id": agenda_id})
        logger.debug(f"[Neo4jSync] Agenda {agenda_id} 삭제 완료")
    except Exception as e:
        logger.error(f"[Neo4jSync] Agenda {agenda_id} 삭제 실패: {e}")
        _log_failure("delete_agenda", "agenda", str(agenda_id), e)


async def delete_meeting_member(meeting_id: int, user_id: int) -> None:
    """Person → Meeting 멤버십 관계를 Neo4j에서 삭제합니다."""
    cypher = """
    MATCH (p:Person {pg_id: $user_id})-[r:`간사`|`구성원`]->(m:Meeting {pg_id: $meeting_id})
    DELETE r
    """
    params = {"meeting_id": meeting_id, "user_id": user_id}
    try:
        await run_cypher(cypher, params)
        logger.debug(f"[Neo4jSync] MeetingMember {meeting_id}/{user_id} 관계 삭제 완료")
    except Exception as e:
        logger.error(f"[Neo4jSync] MeetingMember {meeting_id}/{user_id} 관계 삭제 실패: {e}")
        _log_failure("delete_meeting_member", "meeting_member", f"{meeting_id}_{user_id}", e, params)


async def sync_meeting_relation(
    source_meeting_id: int,
    target_meeting_id: int,
    relation_type: str,
) -> None:
    """회의체 간 관계(MeetingRelation)를 Neo4j에 upsert합니다."""
    rel_map = {
        "PARENT_OF": "상위",
        "RELATED_TO": "관련",
        "FOLLOW_UP": "후속회의",
    }
    rel = rel_map.get(relation_type.upper(), "RELATED_TO")
    cypher = f"""
    MATCH (src:Meeting {{pg_id: $src_id}})
    MATCH (tgt:Meeting {{pg_id: $tgt_id}})
    MERGE (src)-[:`{rel}`]->(tgt)
    """
    params = {"src_id": source_meeting_id, "tgt_id": target_meeting_id}
    try:
        await run_cypher(cypher, params)
        logger.debug(f"[Neo4jSync] MeetingRelation {source_meeting_id}-[{rel}]->{target_meeting_id} 완료")
    except Exception as e:
        logger.error(f"[Neo4jSync] MeetingRelation 동기화 실패: {e}")
        _log_failure(
            "sync_meeting_relation", "meeting_relation",
            f"{source_meeting_id}_{target_meeting_id}", e, params,
        )


async def update_meeting_member_role(
    meeting_id: int,
    user_id: int,
    new_role: str,
) -> None:
    """
    Person → Meeting 멤버십 관계의 역할을 변경합니다.
    기존 ADMIN_OF / MEMBER_OF 관계를 삭제하고 새 관계를 생성합니다.
    """
    await delete_meeting_member(meeting_id, user_id)
    await sync_meeting_member(meeting_id, user_id, new_role)


# ─── PostgreSQL 전체 동기화 ───────────────────────────────────────────────────

async def sync_all_from_pg(db: DBSession | None = None) -> dict:
    """
    PostgreSQL의 모든 엔티티를 Neo4j에 전체 동기화합니다.
    서버 최초 기동 또는 Neo4j 재설치 후 부트스트랩 용도로 사용합니다.
    각 엔티티 sync 실패는 agent_logs에 기록되며 원본에 영향 없습니다.
    """
    import models

    close_db = False
    if db is None:
        db = SessionLocal()
        close_db = True

    stats: dict[str, int] = {
        "users": 0, "meetings": 0, "members": 0,
        "sessions": 0, "agendas": 0, "todos": 0,
        "minutes": 0, "meeting_relations": 0,
    }
    try:
        # Users → Person 노드
        for u in db.query(models.User).all():
            await sync_user(u.id, u.name, u.email, u.department, u.company, u.position)
            stats["users"] += 1

        # Meetings → Meeting 노드
        for m in db.query(models.Meeting).all():
            await sync_meeting(
                m.id, m.title, m.purpose,
                str(m.status or "ACTIVE"), str(m.type or ""),
            )
            stats["meetings"] += 1

        # MeetingMembers → (Person)-[MEMBER_OF/ADMIN_OF]->(Meeting)
        for mm in db.query(models.MeetingMember).all():
            await sync_meeting_member(mm.meeting_id, mm.user_id, mm.role)
            stats["members"] += 1

        # Sessions → Session 노드
        for s in db.query(models.MeetingSession).all():
            await sync_session(
                s.id, s.meeting_id, s.title or "",
                str(s.status or "scheduled"),
                s.scheduled_at.isoformat() if s.scheduled_at else None,
            )
            stats["sessions"] += 1

        # Agendas → Agenda 노드
        for ag in db.query(models.Agenda).all():
            await sync_agenda(
                ag.id, ag.meeting_id,
                ag.title,
                ag.content,
                str(ag.status or "ON_HOLD"),
                ag.order_index or 0,
                ag.assignee_id,
            )
            stats["agendas"] += 1

        # Todos → Todo 노드
        for t in db.query(models.Todo).all():
            await sync_todo(
                todo_id=t.id,
                meeting_id=t.meeting_id,
                content=t.content,
                user_id=t.user_id,
                assignee_name=getattr(t, "assignee_name", None),
                status=str(t.status or "pending"),
                due_date=t.due_date.isoformat() if t.due_date else None,
                priority=str(getattr(t, "priority", None) or "normal"),
            )
            stats["todos"] += 1

        # Minutes → Minutes 노드
        for mn in db.query(models.Minutes).all():
            await sync_minutes(
                mn.id, mn.session_id,
                mn.content_summary,
            )
            stats["minutes"] += 1

        # MeetingRelations → 회의체 간 관계
        if hasattr(models, "MeetingRelation"):
            for mr in db.query(models.MeetingRelation).all():
                await sync_meeting_relation(
                    mr.source_meeting_id,
                    mr.target_meeting_id,
                    mr.relation_type,
                )
                stats["meeting_relations"] += 1

    finally:
        if close_db:
            db.close()

    logger.info(f"[Neo4jSync] sync_all_from_pg 완료: {stats}")
    return stats
