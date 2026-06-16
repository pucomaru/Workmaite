"""그래프 분석·관계 정규화 라우터 (P3A-4 — routers/supervisor.py에서 분리)."""

import logging
from typing import cast

from fastapi import APIRouter, BackgroundTasks, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from db import models
from realtime.sse import sse_done, sse_error, sse_event, sse_token
from llm.agent_logging import (
    TokenUsageCollector,
    _token_collector_var,
    _create_log,
    _finalize,
)
from agents import (
    knowledge_manager as knowledge_agent,
)
from core.auth import get_current_user
from db.database import get_db, SessionLocal
from graphdb.neo4j_client import run_cypher
from services.supervisor_helpers import (
    _log_activity,
    _stream_plan,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/agent", tags=["agents"])

# ─── Supervisor 그래프 분석 ───────────────────────────────────────────────────
# 유사도 임계값은 core.ai_config로 집약(env로 튜닝 가능, 하드코딩 금지)
from core.ai_config import (  # noqa: E402
    AGENDA_LINK_THRESHOLD as _AGENDA_LINK_THRESHOLD,
    DOC_LINK_THRESHOLD as _DOC_LINK_THRESHOLD,
    PRUNE_THRESHOLD as _PRUNE_THRESHOLD,
)


async def _count_nodes(label: str) -> int:
    try:
        r = await run_cypher(f"MATCH (n:{label}) RETURN count(n) AS c")
        return r[0]["c"] if r else 0
    except Exception:
        return 0


async def _analyze_graph() -> dict:
    semantic: dict[str, list] = {"agenda_links": [], "doc_links": []}
    structural: dict[str, list] = {
        "session_chains": [],
        "lifecycle_gaps": [],
        "stale_links": [],
        "ownerless_agendas": [],
        "orphan_documents": [],
        "minuteless_sessions": [],
        "isolated_persons": [],
    }
    membership: dict[str, list] = {"issues": []}

    counts = {
        "agendas": await _count_nodes("Agenda"),
        "documents": (await _count_nodes("Report")) + (await _count_nodes("Minutes")),
        "meetings": await _count_nodes("Meetings"),
        "persons": await _count_nodes("User"),
        "sessions": await _count_nodes("Session"),
    }

    # ⓪ 세션 시간순 체인 점검
    try:
        ch_rows = await run_cypher(
            "MATCH (s:Session)-[:`소속`]->(mg:Meetings) "
            "WITH mg, s ORDER BY CASE WHEN coalesce(s.scheduled_at,'')='' THEN 1 ELSE 0 END, "
            "     s.scheduled_at, s.id "
            "WITH mg, collect({id:s.id, title:coalesce(s.title,'')}) AS sess "
            "WHERE size(sess) >= 2 "
            "RETURN mg.id AS mg_id, coalesce(mg.title,'') AS mg_title, sess AS ordered"
        )
        existing_followups: set = set()
        try:
            ex_rows = await run_cypher(
                "MATCH (a:Session)-[:`후속`]->(b:Session) RETURN a.id AS a, b.id AS b"
            )
            existing_followups = {(r.get("a"), r.get("b")) for r in ex_rows}
        except Exception:
            pass
        for r in ch_rows:
            ordered = r.get("ordered", []) or []
            missing = [
                {
                    "a_id": ordered[i].get("id"),
                    "a_title": ordered[i].get("title", ""),
                    "b_id": ordered[i + 1].get("id"),
                    "b_title": ordered[i + 1].get("title", ""),
                }
                for i in range(len(ordered) - 1)
                if (ordered[i].get("id"), ordered[i + 1].get("id"))
                not in existing_followups
            ]
            if missing:
                structural["session_chains"].append(
                    {
                        "mg": r.get("mg_title", ""),
                        "count": len(ordered),
                        "missing": missing,
                    }
                )
    except Exception as e:
        logger.warning(f"[Supervisor] 세션 체인 분석 실패(무시): {e}")

    # ⓪-b 회의 생명주기 공백
    try:
        lg_rows = await run_cypher(
            "MATCH (mn:Minutes)<-[:`기록`]-(s:Session)-[:`소속`]->(mg:Meetings) "
            "WHERE coalesce(mn.content_summary,'') <> '' AND NOT (mn)-[:`도출`]->(:Agenda) "
            "OPTIONAL MATCH (mg)-[:`추출`|`관할`]-(ag:Agenda) "
            "WITH mn, s, mg, collect(DISTINCT {id: coalesce(ag.id, toString(ag.pg_id)), title: ag.title})[..25] AS ags "
            "RETURN mn.pg_id AS minutes_pg_id, s.id AS session_id, coalesce(s.title,'') AS session_title, "
            "       coalesce(mg.title,'') AS mg, left(mn.content_summary, 1800) AS content, ags AS agendas "
            "LIMIT 10"
        )
        for r in lg_rows:
            structural["lifecycle_gaps"].append(
                {
                    "minutes_pg_id": r.get("minutes_pg_id"),
                    "session_id": r.get("session_id"),
                    "session_title": r.get("session_title", ""),
                    "mg": r.get("mg", ""),
                    "content": r.get("content", ""),
                    "agendas": [a for a in (r.get("agendas") or []) if a.get("title")],
                }
            )
    except Exception as e:
        logger.warning(f"[Supervisor] 생명주기 공백 분석 실패(무시): {e}")

    # ① 잠재 연결 — 회의 간 의미 유사 안건쌍
    try:
        rows = await run_cypher(
            "MATCH (mga:Meetings)-[:`추출`|`관할`]-(a:Agenda) "
            "WHERE a.embedding IS NOT NULL "
            "CALL db.index.vector.queryNodes('agendaEmbedding', 5, a.embedding) "
            "YIELD node, score "
            "WITH a, mga, node, score "
            "WHERE a.id < node.id AND score >= $th AND node.embedding IS NOT NULL "
            "MATCH (mgb:Meetings)-[:`추출`|`관할`]-(node) "
            "WHERE mgb.id <> mga.id AND NOT (a)-[:`관련`]-(node) "
            "RETURN a.id AS a_id, a.title AS a_title, mga.title AS a_mg, "
            "       node.id AS b_id, node.title AS b_title, mgb.title AS b_mg, score "
            "ORDER BY score DESC LIMIT 30",
            {"th": _AGENDA_LINK_THRESHOLD},
        )
        for r in rows:
            semantic["agenda_links"].append(
                {
                    "a_id": r.get("a_id"),
                    "a_title": r.get("a_title", "?"),
                    "a_mg": r.get("a_mg", ""),
                    "b_id": r.get("b_id"),
                    "b_title": r.get("b_title", "?"),
                    "b_mg": r.get("b_mg", ""),
                    "score": float(r.get("score") or 0.0),
                }
            )
    except Exception as e:
        logger.warning(f"[Supervisor] 안건 유사도 분석 실패(무시): {e}")

    # ① 잠재 연결 — 문서 ↔ 안건 적합도
    try:
        rows = await run_cypher(
            "MATCH (d) WHERE (d:Report OR d:Minutes) AND d.embedding IS NOT NULL "
            "CALL db.index.vector.queryNodes('agendaEmbedding', 3, d.embedding) "
            "YIELD node, score "
            "WITH d, node, score "
            # 문서→안건은 보고자료=취급, 회의록=도출 — 이미 연결된 건 제외 (레거시 발제도 제외)
            "WHERE score >= $th AND NOT (d)-[:`취급`|`도출`|`발제`]->(node) "
            "RETURN d.id AS doc_id, coalesce(d.title, d.file_name) AS doc_title, "
            "       node.id AS ag_id, node.title AS ag_title, score "
            "ORDER BY score DESC LIMIT 30",
            {"th": _DOC_LINK_THRESHOLD},
        )
        for r in rows:
            semantic["doc_links"].append(
                {
                    "doc_id": r.get("doc_id"),
                    "doc_title": r.get("doc_title", "?"),
                    "ag_id": r.get("ag_id"),
                    "ag_title": r.get("ag_title", "?"),
                    "score": float(r.get("score") or 0.0),
                }
            )
    except Exception as e:
        logger.warning(f"[Supervisor] 문서-안건 적합도 분석 실패(무시): {e}")

    # ② 구조 공백 — 담당자 없는 안건
    try:
        rows = await run_cypher(
            "MATCH (ag:Agenda) WHERE NOT (:User)-[:`담당`]->(ag) "
            "OPTIONAL MATCH (mg:Meetings)-[:`추출`|`관할`]-(ag) "
            "RETURN ag.id AS id, ag.title AS title, mg.title AS mg LIMIT 50"
        )
        structural["ownerless_agendas"] = [
            {"id": r.get("id"), "title": r.get("title", "?"), "mg": r.get("mg", "")}
            for r in rows
        ]
    except Exception:
        pass

    # ② 구조 공백 — 고아 문서
    try:
        rows = await run_cypher(
            "MATCH (d:Report) WHERE NOT (d)-[:`첨부`|`발제`]->() "
            "RETURN d.id AS id, coalesce(d.title, d.file_name) AS title, "
            "       (d.embedding IS NOT NULL) AS emb LIMIT 50"
        )
        structural["orphan_documents"] = [
            {"id": r.get("id"), "title": r.get("title", "?"), "emb": bool(r.get("emb"))}
            for r in rows
        ]
    except Exception:
        pass

    # ② 구조 공백 — 회의록 없는 세션
    try:
        rows = await run_cypher(
            "MATCH (s:Session) WHERE NOT (:Minutes)<-[:`기록`]-(s) "
            "OPTIONAL MATCH (s)-[:`소속`]->(mg:Meetings) "
            "RETURN s.id AS id, mg.title AS mg LIMIT 50"
        )
        structural["minuteless_sessions"] = [
            {"id": r.get("id"), "mg": r.get("mg", "")} for r in rows
        ]
    except Exception:
        pass

    # ② 구조 공백 — 고립 인물
    try:
        rows = await run_cypher(
            "MATCH (p:User) WHERE NOT (p)--() RETURN p.id AS id, p.name AS name LIMIT 50"
        )
        structural["isolated_persons"] = [
            {"id": r.get("id"), "name": r.get("name", "?")} for r in rows
        ]
    except Exception:
        pass

    # ③ 소속 무결성
    for cypher, issue_type, extra_key in [
        (
            "MATCH (p:User)-[:`소속부서`]->(d:Department) "
            "RETURN p.id AS pid, p.name AS name, d.name AS dept",
            "legacy",
            None,
        ),
        (
            "MATCH (p:User) WHERE coalesce(p.department, '') <> '' "
            "  AND NOT (p)-[:`소속`]->(:Department) "
            "RETURN p.id AS pid, p.name AS name, p.department AS dept",
            "missing",
            None,
        ),
        (
            "MATCH (p:User)-[:`소속`]->(d:Department) "
            "WHERE coalesce(p.department, '') <> '' AND d.name <> p.department "
            "RETURN p.id AS pid, p.name AS name, p.department AS dept, d.name AS wrong",
            "mismatch",
            "wrong",
        ),
    ]:
        try:
            for r in await run_cypher(cypher):
                entry = {
                    "type": issue_type,
                    "pid": r.get("pid"),
                    "person": r.get("name", "?"),
                    "dept": r.get("dept", ""),
                    "current": r.get(extra_key) if extra_key else None,
                }
                membership["issues"].append(entry)
        except Exception:
            pass

    # ① 불필요 연결 탐지 — 임계값은 모듈 상단의 _PRUNE_THRESHOLD(core.ai_config) 사용

    # stale carry-forward: 완료된 안건에 달린 세션 도출(이월) 관계
    try:
        rows = await run_cypher(
            "MATCH (s:Session)-[r:`도출`]->(ag:Agenda) "
            "WHERE r.kind = 'carry_forward' "
            "  AND ag.status IN ['DONE', 'COMPLETED', 'CLOSED', 'RESOLVED'] "
            "RETURN s.id AS session_id, ag.id AS agenda_id, ag.title AS agenda_title"
        )
        for r in rows:
            structural["stale_links"].append(
                {
                    "kind": "stale_carry",
                    "from_id": r.get("session_id"),
                    "to_id": r.get("agenda_id"),
                    "label": f"이월 → [{r.get('agenda_title', '?')}] (완료된 안건)",
                    "rel": "도출",
                }
            )
    except Exception:
        pass

    # stale lifecycle: 완료된 안건에 달린 Minutes 도출 관계
    try:
        rows = await run_cypher(
            "MATCH (mn:Minutes)-[r:`도출`]->(ag:Agenda) "
            "WHERE r.kind = 'minutes_agenda' "
            "  AND ag.status IN ['DONE', 'COMPLETED', 'CLOSED', 'RESOLVED'] "
            "RETURN mn.pg_id AS mn_id, ag.id AS agenda_id, ag.title AS agenda_title"
        )
        for r in rows:
            structural["stale_links"].append(
                {
                    "kind": "stale_lifecycle",
                    "from_id": str(r.get("mn_id", "")),
                    "to_id": r.get("agenda_id"),
                    "label": f"회의록도출 → [{r.get('agenda_title', '?')}] (완료된 안건)",
                    "rel": "도출",
                }
            )
    except Exception:
        pass

    # weak 관련 (낙은 유사도 자동 생성 안건시안 링크)
    try:
        rows = await run_cypher(
            "MATCH (a:Agenda)-[r:`관련`]-(b:Agenda) "
            "WHERE r.discovered_by = 'knowledge_agent' AND r.score IS NOT NULL AND r.score < $th "
            "RETURN a.id AS from_id, b.id AS to_id, a.title AS a_title, b.title AS b_title, r.score AS score "
            "LIMIT 30",
            {"th": _PRUNE_THRESHOLD},
        )
        for r in rows:
            structural["stale_links"].append(
                {
                    "kind": "weak_related",
                    "from_id": r.get("from_id"),
                    "to_id": r.get("to_id"),
                    "label": f"[{r.get('a_title', '?')}]↔[{r.get('b_title', '?')}] ({float(r.get('score') or 0) * 100:.0f}%)",
                    "rel": "관련",
                    "score": float(r.get("score") or 0),
                }
            )
    except Exception:
        pass

    # weak 문서→안건 (낮은 유사도 자동 첨부/도출 연결 — AI가 discovered_by로 생성한 것만)
    # 라이프사이클 도출(r.kind 보유)·사용자 수동 연결은 제외한다.
    try:
        rows = await run_cypher(
            "MATCH (d)-[r:`취급`|`도출`|`발제`]->(ag:Agenda) "
            "WHERE (d:Report OR d:Minutes) AND r.discovered_by = 'knowledge_agent' "
            "  AND r.kind IS NULL AND r.score IS NOT NULL AND r.score < $th "
            "RETURN d.id AS from_id, ag.id AS to_id, type(r) AS rel, "
            "       coalesce(d.title, d.file_name, '?') AS doc_title, ag.title AS ag_title, r.score AS score "
            "LIMIT 30",
            {"th": _PRUNE_THRESHOLD},
        )
        for r in rows:
            structural["stale_links"].append(
                {
                    "kind": "weak_ref",
                    "from_id": r.get("from_id"),
                    "to_id": r.get("to_id"),
                    "label": f"문서[{r.get('doc_title', '?')}]→안건[{r.get('ag_title', '?')}] ({float(r.get('score') or 0) * 100:.0f}%)",
                    "rel": r.get("rel", "도출"),
                    "score": float(r.get("score") or 0),
                }
            )
    except Exception:
        pass

    # weak 자동연결 (낮은 유사도 auto_linked 문서→안건 — 도출, 구 데이터는 첨부)
    try:
        rows = await run_cypher(
            "MATCH (d)-[r:`취급`|`도출`|`발제`]->(ag:Agenda) "
            "WHERE (d:Report OR d:Minutes) AND r.auto_linked = true AND r.score IS NOT NULL AND r.score < $th "
            "RETURN d.id AS from_id, ag.id AS to_id, type(r) AS rel, "
            "       coalesce(d.title, d.file_name, '?') AS doc_title, ag.title AS ag_title, r.score AS score "
            "LIMIT 30",
            {"th": _PRUNE_THRESHOLD},
        )
        for r in rows:
            structural["stale_links"].append(
                {
                    "kind": "weak_attach",
                    "from_id": r.get("from_id"),
                    "to_id": r.get("to_id"),
                    "label": f"문서[{r.get('doc_title', '?')}]→안건[{r.get('ag_title', '?')}] 도출 ({float(r.get('score') or 0) * 100:.0f}%)",
                    "rel": r.get("rel", "도출"),
                    "score": float(r.get("score") or 0),
                }
            )
    except Exception:
        pass

    return {
        "semantic": semantic,
        "structural": structural,
        "membership": membership,
        "counts": counts,
    }


async def _normalize_rel_directions() -> dict:
    """관계 방향·명칭을 정규 흐름(REL_MATRIX)에 맞게 일괄 정규화합니다.
    Neo4j는 엣지 방향을 in-place 변경할 수 없으므로 DELETE → MERGE 패턴을 사용합니다.
    """
    # 원칙: 포함/소속은 작은 단위 → 큰 단위 방향 (child → parent)
    # 라이프사이클(agenda→session→minutes)은 흐름 방향 유지
    steps = [
        # (설명, 카운트 쿼리, 수정 쿼리)
        # ── 포함 관계: 잘못된 big→small 복구 ──────────────────────────
        (
            "회의체→회사 방향 복구 (포함, 작은→큰)",
            "MATCH (co:Company)-[r:`포함`]->(mg:Meetings) RETURN count(r) AS cnt",
            "MATCH (co:Company)-[r:`포함`]->(mg:Meetings) MERGE (mg)-[:`포함`]->(co) DELETE r",
        ),
        (
            "부서→회사 방향 복구 (소속, 작은→큰)",
            "MATCH (co:Company)-[r:`소속`|`포함`]->(d:Department) RETURN count(r) AS cnt",
            "MATCH (co:Company)-[r:`소속`|`포함`]->(d:Department) MERGE (d)-[:`소속`]->(co) DELETE r",
        ),
        (
            "사람→부서 방향 복구 (소속, 작은→큰)",
            "MATCH (d:Department)-[r:`소속`]->(u:User) RETURN count(r) AS cnt",
            "MATCH (d:Department)-[r:`소속`]->(u:User) MERGE (u)-[:`소속`]->(d) DELETE r",
        ),
        # ── 관계명·방향 변경 마이그레이션 (신 스키마) ─────────────────────
        # 안건↔회의체: 과거 'agenda→관할→Meetings'(및 역방향)를 'Meetings→추출→agenda'로 일원화.
        # 프로퍼티 보존. 'agenda→dept 담당부서'는 별개라 영향 없음(라벨로 한정).
        (
            "관할(아젠다→회의체) → 추출(회의체→아젠다) 변경",
            "MATCH (ag:Agenda)-[r:`관할`]->(mg:Meetings) RETURN count(r) AS cnt",
            "MATCH (ag:Agenda)-[old:`관할`]->(mg:Meetings) "
            "MERGE (mg)-[new:`추출`]->(ag) SET new += properties(old) DELETE old",
        ),
        (
            "관할(회의체→아젠다, 역방향) → 추출 변경",
            "MATCH (mg:Meetings)-[r:`관할`]->(ag:Agenda) RETURN count(r) AS cnt",
            "MATCH (mg:Meetings)-[old:`관할`]->(ag:Agenda) "
            "MERGE (mg)-[new:`추출`]->(ag) SET new += properties(old) DELETE old",
        ),
        # 보고자료→회의체: 발제 → 첨부. (라벨로 Meetings 한정)
        (
            "보고자료→회의체 관계명 변경 (발제→첨부)",
            "MATCH (r:Report)-[rel:`발제`]->(mg:Meetings) RETURN count(rel) AS cnt",
            "MATCH (r:Report)-[old:`발제`]->(mg:Meetings) "
            "MERGE (r)-[new:`첨부`]->(mg) SET new += properties(old) DELETE old",
        ),
        # 보고자료→안건: 발제·도출 → 취급. (라벨로 Report·Agenda 한정 → minutes→agenda '도출'은 보존)
        (
            "보고자료→안건 관계명 변경 (발제→취급)",
            "MATCH (r:Report)-[rel:`발제`]->(ag:Agenda) RETURN count(rel) AS cnt",
            "MATCH (r:Report)-[old:`발제`]->(ag:Agenda) "
            "MERGE (r)-[new:`취급`]->(ag) SET new += properties(old) DELETE old",
        ),
        (
            "보고자료→안건 관계명 변경 (도출→취급)",
            "MATCH (r:Report)-[rel:`도출`]->(ag:Agenda) RETURN count(rel) AS cnt",
            "MATCH (r:Report)-[old:`도출`]->(ag:Agenda) "
            "MERGE (r)-[new:`취급`]->(ag) SET new += properties(old) DELETE old",
        ),
        # 잔여 폐지 관계 정리 (위 마이그레이션 후 남은 것 — 안전망)
        (
            "폐지 관계 '관할' 잔여 삭제 (canonical=추출)",
            "MATCH ()-[r:`관할`]->() RETURN count(r) AS cnt",
            "MATCH ()-[r:`관할`]->() DELETE r",
        ),
        (
            "폐지 관계 '발제' 잔여 삭제 (canonical=첨부/취급)",
            "MATCH ()-[r:`발제`]->() RETURN count(r) AS cnt",
            "MATCH ()-[r:`발제`]->() DELETE r",
        ),
        # ── 폐지 관계 purge ──────────────────────────────────────────────
        # canonical(논의·기록)은 PG sync가 만든다. 과거 reconcile/인코딩 버그가 남긴 잔재
        # (다룸멌·다룸·진행·생성)는 마이그레이션 없이 삭제만 한다. 정상 경로(sync·버튼·reconcile)는
        # 더이상 이 이름을 만들지 않으므로, 그래프가 한 번 정리되면 이 purge 단계도 제거 가능.
        (
            "폐지 관계 '다룸멌'(깨진 이름) 삭제",
            "MATCH ()-[r:`다룸멌`]->() RETURN count(r) AS cnt",
            "MATCH ()-[r:`다룸멌`]->() DELETE r",
        ),
        (
            "폐지 관계 '다룸' 삭제 (canonical=논의)",
            "MATCH ()-[r:`다룸`]->() RETURN count(r) AS cnt",
            "MATCH ()-[r:`다룸`]->() DELETE r",
        ),
        (
            "폐지 관계 '진행' 삭제 (canonical=논의)",
            "MATCH ()-[r:`진행`]->() RETURN count(r) AS cnt",
            "MATCH ()-[r:`진행`]->() DELETE r",
        ),
        (
            "폐지 관계 '생성' 삭제 (canonical=기록)",
            "MATCH ()-[r:`생성`]->() RETURN count(r) AS cnt",
            "MATCH ()-[r:`생성`]->() DELETE r",
        ),
    ]

    total = 0
    details: dict[str, int] = {}
    for desc, count_q, fix_q in steps:
        try:
            rows = await run_cypher(count_q)
            cnt = int(rows[0]["cnt"]) if rows else 0
            if cnt:
                await run_cypher(fix_q)
                details[desc] = cnt
                total += cnt
                logger.info(f"[RelNorm] {desc}: {cnt}건")
        except Exception as e:
            logger.warning(f"[RelNorm] {desc} 실패 (무시): {e}")

    return {"total": total, "details": details}


@router.post(
    "/knowledge/analyze-relationships",
    summary="지식 그래프 관계 분석·재구성 — SSE 스트리밍",
)
async def analyze_relationships_stream(
    background_tasks: BackgroundTasks,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """전체 지식 그래프를 점검해 끊긴 흐름·미연결 안건/문서를 찾아 자동 재구성한다.

    분석 계획·진행·요약을 SSE(text/event-stream)로 스트리밍하며, 관계 방향·명칭
    정규화도 수행한다. (로그인 사용자 인증)
    """
    background_tasks.add_task(
        _log_activity,
        0,
        "워크메이트[supervisor→knowledge]",
        "관계도 분석·재구성",
        f"요청자: {current_user.name}",
    )

    async def stream():
        _collector = TokenUsageCollector()
        _tok_ctx_token = _token_collector_var.set(_collector)
        _log_id = _create_log(
            context_type="archive_analyze_stream",
            meeting_id=None,
            session_id=None,
            user_id=current_user.id,
            input_data=None,
        )
        _stream_error: BaseException | None = None
        _assistant_chunks: list[str] = []  # 채팅 영속화용 — 요약 토큰 누적
        try:
            import asyncio as _asyncio

            # 그래프 분석과 병렬로 LLM이 작업 계획을 서술
            analysis_task = _asyncio.create_task(_analyze_graph())
            _pre_sys = (
                "업무 지식 그래프를 점검하는 AI입니다. 지금 막 전체 그래프를 분석하려 합니다. "
                "어떤 항목들을 살펴볼지 한국어로 2~3단계 간결하게 나열하세요. 번호·기호 없이."
            )
            _pre_hmn = "회의체·세션·안건·문서·구성원의 관계 전체를 점검합니다."
            async for _step in _stream_plan(_pre_sys, _pre_hmn):
                yield sse_event("planning", f"{_step}")
            analysis = await analysis_task

            sem = analysis["semantic"]
            struct = analysis["structural"]
            member = analysis["membership"]
            counts = analysis["counts"]

            chains = struct.get("session_chains", [])
            lifecycle = struct.get("lifecycle_gaps", [])
            stale = struct.get("stale_links", [])
            ag_links = sem["agenda_links"]
            doc_links = sem["doc_links"]
            ownerless = struct["ownerless_agendas"]
            orphans = struct["orphan_documents"]
            embeddable_orphans = [d for d in orphans if d.get("emb")]
            missing_seq = sum(len(c["missing"]) for c in chains)
            lifecycle_n = len(lifecycle)
            stale_n = len(stale)

            # 세션→안건 미연결 건수 (원칙: 회의는 아젠다와 연결되어야 한다)
            try:
                _sa_rows = await run_cypher(
                    "MATCH (s:Session)-[:`소속`]->(mg:Meetings) "
                    "WHERE (mg)-[:`추출`|`관할`]-(:Agenda) "
                    "  AND NOT (:Agenda)-[:`논의`]->(s) "
                    "RETURN count(s) AS cnt"
                )
                session_no_agenda_n = _sa_rows[0].get("cnt", 0) if _sa_rows else 0
            except Exception:
                session_no_agenda_n = 0

            # ── LLM이 분석 결과를 보고 현황·계획을 스스로 서술 ──────────
            findings_text = (
                f"회의체 {counts['meetings']}개 / 세션 {counts['sessions']}개 / "
                f"안건 {counts['agendas']}개 / 문서 {counts['documents']}개 스캔 완료.\n"
                f"끊긴 세션 흐름: {missing_seq}건, "
                f"세션→안건 미연결: {session_no_agenda_n}건, "
                f"회의록→안건 미연결: {lifecycle_n}건, "
                f"불필요 연결(이월·저유사도): {stale_n}건.\n"
                f"회의 간 유사 안건: {len(ag_links)}쌍"
                + (
                    f" (상위: [{ag_links[0]['a_title']}] ↔ [{ag_links[0]['b_title']}], "
                    f"{ag_links[0]['score'] * 100:.0f}%)"
                    if ag_links
                    else ""
                )
                + f"\n미연결 문서: {len(doc_links)}건, "
                f"담당자 없는 안건: {len(ownerless)}건, "
                f"고아 문서: {len(orphans)}건, "
                f"소속 이슈: {len(member.get('issues', []))}건."
            )
            if chains:
                c0 = chains[0]
                findings_text += (
                    f"\n예시: '{c0['mg']}' 회의체에서 {c0['count']}개 회차 미연결."
                )

            system_findings = (
                "당신은 업무 지식 그래프를 관리하는 AI입니다. "
                "아래 그래프 분석 수치를 보고, 현재 상태와 앞으로 할 작업을 "
                "자연스러운 한국어로 간결하게 나열하세요. "
                "각 항목은 한 줄, 총 3~6개, 마크다운·번호·기호 없이 plain text만."
            )
            async for step in _stream_plan(system_findings, findings_text):
                yield sse_event("planning", f"{step}")

            # ── 실제 그래프 재구성 수행 ──────────────────────────────────
            actionable = (
                missing_seq
                + session_no_agenda_n
                + lifecycle_n
                + stale_n
                + len(ag_links)
                + len(doc_links)
                + len(embeddable_orphans)
                + len(member.get("issues", []))
            )

            if actionable == 0:
                result = {
                    "actions": [],
                    "stats": {
                        "session_links": 0,
                        "lifecycle_links": 0,
                        "carry_links": 0,
                        "related_agendas": 0,
                        "doc_refs": 0,
                        "doc_attached": 0,
                        "membership_fixed": 0,
                        "pruned_links": 0,
                    },
                    "advisories": {
                        "ownerless_agendas": ownerless,
                        "minuteless_sessions": struct["minuteless_sessions"],
                        "isolated_persons": struct["isolated_persons"],
                    },
                }
            else:
                result = await knowledge_agent.reconcile_graph(analysis)
                stats = cast(dict, result["stats"])

                # LLM이 수행 결과를 보고 planning 단계를 서술
                done_items = [
                    label.format(stats[k])
                    for k, label in [
                        ("session_links", "끊긴 회의 흐름 {}건 → 시간순 연결"),
                        ("session_agenda_links", "세션→안건 연결 {}건 생성"),
                        ("lifecycle_links", "회의록 {}개를 관련 안건과 연결"),
                        ("carry_links", "미해결 안건 {}건 다음 회차로 이월"),
                        ("related_agendas", "회의 간 유사 안건 링크 {}건 생성"),
                        ("doc_refs", "문서 참조 링크 {}건 생성"),
                        ("doc_attached", "고아 문서 {}건 → 적합 안건 자동 연결"),
                        ("membership_fixed", "소속 무결성 {}건 보정"),
                        ("pruned_links", "불필요 연결 {}건 정리"),
                    ]
                    if stats.get(k)
                ]
                if done_items:
                    actions_text = "수행한 작업 목록:\n" + "\n".join(
                        f"- {d}" for d in done_items
                    )
                    system_actions = (
                        "당신은 업무 지식 그래프 관리 AI입니다. "
                        "방금 그래프에 적용한 작업들을 바탕으로, 어떤 개선이 이루어졌는지 "
                        "자연스러운 한국어로 2~4줄로 서술하세요. "
                        "마크다운·번호·기호 없이 plain text만."
                    )
                    async for step in _stream_plan(system_actions, actions_text):
                        yield sse_event("planning", f"{step}")

            # ── 관계 방향·명칭 정규화 (항상 실행) ────────────────────
            try:
                norm = await _normalize_rel_directions()
                if norm["total"]:
                    yield sse_event(
                        "planning", f"관계 방향·명칭 정규화 {norm['total']}건 완료"
                    )
            except Exception:
                pass

            _hl = set()
            for lk in ag_links:
                _hl.add(lk.get("a_title"))
                _hl.add(lk.get("b_title"))
            for lk in doc_links:
                _hl.add(lk.get("ag_title"))
            for g in lifecycle:
                _hl.add(g.get("session_title"))
            for a in cast(list, result.get("actions", [])):
                if a.get("highlight"):
                    _hl.add(a["highlight"])
            _hl.discard(None)
            _hl.discard("")
            if _hl:
                yield sse_event("highlight", list(_hl))

            report = {
                **result,
                "counts": counts,
                "findings": {
                    "session_missing": missing_seq,
                    "session_groups": len(chains),
                    "lifecycle_gaps": lifecycle_n,
                    "stale_links": stale_n,
                    "agenda_links": len(ag_links),
                    "doc_links": len(doc_links),
                    "ownerless": len(ownerless),
                    "orphans": len(orphans),
                    "examples": ag_links[:5],
                    "doc_examples": doc_links[:5],
                    "chain_examples": chains[:3],
                },
            }
            async for chunk in knowledge_agent.summarize_relationship_analysis(report):
                _assistant_chunks.append(chunk)
                yield sse_token(chunk)

        except Exception as e:
            _stream_error = e
            yield sse_error(f"관계도 분석 중 오류가 발생했습니다: {str(e)}")
        except BaseException as _e:
            _stream_error = _e
            raise
        finally:
            _token_collector_var.reset(_tok_ctx_token)
            _finalize(_log_id, _collector, _stream_error, None)
            # 채팅 기록 영속화 — archive 스레드(archive_<uid>)에 user 요청 + assistant 요약 저장.
            # 저장하지 않으면 supervisor 채팅과 달리 새로고침/사이드바 재열기 시 분석 대화가 사라진다.
            try:
                _assistant_text = "".join(_assistant_chunks).strip()
                _thread_id = f"archive_{current_user.id}"
                _save_db = SessionLocal()
                try:
                    _save_db.add(
                        models.ChatMessage(
                            thread_id=_thread_id,
                            user_id=current_user.id,
                            role="user",
                            content="회의별로 흩어진 지식을 분석해서 연관된 안건·문서를 서로 연결해줘",
                            context_type="supervisor",
                        )
                    )
                    if _assistant_text:
                        _save_db.add(
                            models.ChatMessage(
                                thread_id=_thread_id,
                                user_id=current_user.id,
                                role="assistant",
                                content=_assistant_text,
                                context_type="supervisor",
                            )
                        )
                    _save_db.commit()
                finally:
                    _save_db.close()
            except Exception as _persist_err:
                logger.warning(
                    f"[analyze-relationships] 채팅 기록 저장 실패: {_persist_err}"
                )
        yield sse_done()

    return StreamingResponse(stream(), media_type="text/event-stream")


@router.post(
    "/knowledge/fill-fields",
    summary="안건 빈 필드 자동 채우기 — SSE 스트리밍",
)
async def fill_fields_stream(
    background_tasks: BackgroundTasks,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """'채우기' — 사용자가 비워둔 안건 필드(담당 부서)·우선순위·완료 상태를 맥락에 맞게 자동 보정한다.

    기존 analyze-relationships('관계 재설정')와 달리 노드 메타데이터를 채우는 데 집중하며,
    진행·요약을 SSE(text/event-stream)로 스트리밍한다.
    스코프: 사용자가 속한 회의체(관리자는 자사 구성원 회의체까지).
    """
    is_admin = current_user.company_role == "SYSTEM_ADMIN"
    pg_meeting_ids = {
        row.meeting_id
        for row in db.query(models.MeetingMember.meeting_id)
        .filter(models.MeetingMember.user_id == current_user.id)
        .all()
    }
    if is_admin or (
        current_user.company_role == "COMPANY_ADMIN"
        and current_user.company_id is not None
    ):
        q = db.query(models.MeetingMember.meeting_id).join(
            models.User, models.User.id == models.MeetingMember.user_id
        )
        if not is_admin:
            q = q.filter(models.User.company_id == current_user.company_id)
        pg_meeting_ids |= {row.meeting_id for row in q.all()}
    meeting_ids = list(pg_meeting_ids)

    background_tasks.add_task(
        _log_activity,
        0,
        "워크메이트[채우기]",
        "안건 필드 채우기",
        f"요청자: {current_user.name}",
    )

    async def stream():
        _collector = TokenUsageCollector()
        _tok_ctx_token = _token_collector_var.set(_collector)
        _log_id = _create_log(
            context_type="archive_analyze_stream",
            meeting_id=None,
            session_id=None,
            user_id=current_user.id,
            input_data=None,
        )
        _stream_error: BaseException | None = None
        _assistant_chunks: list[str] = []
        try:
            async for _step in _stream_plan(
                "안건의 비어있는 필드와 우선순위·완료 상태를 점검하는 AI입니다. "
                "어떤 작업을 할지 한국어로 2~3단계 간결하게 나열하세요. 번호·기호 없이.",
                "회의 안건의 비어있는 담당 부서·우선순위·완료 상태를 맥락에 맞게 채웁니다.",
            ):
                yield sse_event("planning", f"{_step}")

            result = await knowledge_agent.fill_agenda_fields(meeting_ids)
            actions = cast(list, result.get("actions", []))
            stats = cast(dict, result.get("stats", {}))

            for a in actions[:30]:
                _ch = " · ".join(a.get("changed", []))
                yield sse_event("planning", f"{a.get('detail', '')} {_ch}".strip())

            _hl = [a["highlight"] for a in actions if a.get("highlight")]
            if _hl:
                yield sse_event("highlight", _hl)

            # 결과 요약 스트리밍
            from llm.llm_factory import llm_factory
            from langchain_core.messages import (
                SystemMessage as _Sys,
                HumanMessage as _Hmn,
            )

            _sum_sys = (
                "회의 안건의 비어있는 필드·우선순위·완료 상태를 자동 보정한 결과를 사용자에게 보고하는 비서입니다. "
                "무엇을 몇 건 채웠는지와 대표 예시 1~2개를 한국어로 간결하게(마크다운·번호·기호 없이). "
                "변경이 하나도 없으면 '추가로 채울 수 있는 빈 항목을 찾지 못했습니다'라고만 답하세요. 마무리 인사 금지."
            )
            _sum_hmn = (
                f"부서 채움 {stats.get('department', 0)}건, 마감일 채움 {stats.get('due_date', 0)}건, "
                f"우선순위 보정 {stats.get('priority', 0)}건, 상태 보정 {stats.get('status', 0)}건.\n"
                + "\n".join(
                    f"- {a.get('detail', '')} {' · '.join(a.get('changed', []))}: {a.get('evidence', '')}"
                    for a in actions[:12]
                )
            )
            async for _c in llm_factory("knowledge", streaming=True).astream(
                [_Sys(content=_sum_sys), _Hmn(content=_sum_hmn)]
            ):
                _t = _c.content if isinstance(_c.content, str) else str(_c.content)
                if _t:
                    _assistant_chunks.append(_t)
                    yield sse_token(_t)

        except Exception as e:
            _stream_error = e
            yield sse_error(f"채우기 중 오류가 발생했습니다: {str(e)}")
        except BaseException as _e:
            _stream_error = _e
            raise
        finally:
            _token_collector_var.reset(_tok_ctx_token)
            _finalize(_log_id, _collector, _stream_error, None)
            try:
                _assistant_text = "".join(_assistant_chunks).strip()
                _thread_id = f"archive_{current_user.id}"
                _save_db = SessionLocal()
                try:
                    _save_db.add(
                        models.ChatMessage(
                            thread_id=_thread_id,
                            user_id=current_user.id,
                            role="user",
                            content="비어있는 안건 필드와 우선순위·상태를 맥락에 맞게 채워줘",
                            context_type="supervisor",
                        )
                    )
                    if _assistant_text:
                        _save_db.add(
                            models.ChatMessage(
                                thread_id=_thread_id,
                                user_id=current_user.id,
                                role="assistant",
                                content=_assistant_text,
                                context_type="supervisor",
                            )
                        )
                    _save_db.commit()
                finally:
                    _save_db.close()
            except Exception as _persist_err:
                logger.warning(f"[fill-fields] 채팅 기록 저장 실패: {_persist_err}")
        yield sse_done()

    return StreamingResponse(stream(), media_type="text/event-stream")
