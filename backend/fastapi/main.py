import asyncio
import logging
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

# Workmaite/.env 를 override=True로 로드 (기존 환경변수 덮어쓰기)
_base = os.path.dirname(__file__)
load_dotenv(os.path.join(_base, "..", "..", ".env"), override=True)

# 로깅 설정 — 기본 INFO. 미설정 시 파이썬 기본은 WARNING이라 앱의 INFO 로그(예: [Realtime STT]
# 이벤트 추적)가 콘솔에 안 보인다. LOG_LEVEL env(DEBUG/INFO/WARNING)로 조정.
_log_level = getattr(logging, os.environ.get("LOG_LEVEL", "INFO").upper(), logging.INFO)
logging.basicConfig(
    level=_log_level,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logging.getLogger().setLevel(
    _log_level
)  # uvicorn이 root 핸들러를 이미 붙였어도 레벨 보장

# LangSmith 트레이싱: API 키가 있고 LANGSMITH_TRACING=true일 때만 활성화 (키 없이 켜면 403 스팸)
_tracing_on = os.environ.get("LANGSMITH_TRACING", "").lower() == "true" and bool(
    os.environ.get("LANGSMITH_API_KEY")
)
os.environ["LANGCHAIN_TRACING_V2"] = "true" if _tracing_on else "false"
os.environ["LANGSMITH_TRACING"] = "true" if _tracing_on else "false"

from realtime.websocket_manager import manager
from realtime import transcription as transcription_ws

from routers import supervisor, chat_history, neo4j_graph, sync as sync_router
from routers import archive as archive_router
from routers import graph_analysis as graph_analysis_router
from routers import hitl_reviews as hitl_router
from routers import knowledge as knowledge_router
from routers import meetings as meetings_router
from routers import sessions as sessions_router
from routers import stt as stt_router
from routers import upload as upload_router
from routers import usage as usage_router
from graphdb.neo4j_sync import (
    ensure_constraints,
    init_vector_index,
    sync_all_from_pg,
)
from prometheus_fastapi_instrumentator import Instrumentator

logger = logging.getLogger(__name__)


async def _run_pg_migrations() -> None:
    import anyio
    from sqlalchemy import text
    from db.database import engine

    migrations = [
        "ALTER TABLE meeting_sessions ADD COLUMN IF NOT EXISTS created_at timestamp without time zone DEFAULT (now() AT TIME ZONE 'UTC')",
        "ALTER TABLE meeting_sessions ALTER COLUMN created_at SET DEFAULT (now() AT TIME ZONE 'UTC')",
        # KST로 잘못 저장된 기존 값 보정 (9시간 빼기)
        "UPDATE meeting_sessions SET created_at = created_at - INTERVAL '9 hours' WHERE created_at IS NOT NULL AND created_at > (now() AT TIME ZONE 'UTC') + INTERVAL '1 hour'",
        # 사용자 하드 삭제 지원: FK 컬럼을 nullable로 변경
        "ALTER TABLE reports ALTER COLUMN upload_id DROP NOT NULL",
        "ALTER TABLE chat_messages ALTER COLUMN user_id DROP NOT NULL",
        "ALTER TABLE chat_feedback ALTER COLUMN user_id DROP NOT NULL",
        "ALTER TABLE audit_logs ALTER COLUMN actor_id DROP NOT NULL",
    ]

    def _apply():
        with engine.begin() as conn:
            for sql in migrations:
                conn.execute(text(sql))

    try:
        await anyio.to_thread.run_sync(_apply)
        logger.info("[Migration] PostgreSQL 마이그레이션 완료")
    except Exception as e:
        logger.error(f"[Migration] 오류: {e}")


async def _cleanup_stale_neo4j_nodes() -> None:
    """레거시 Todo 노드와 todo-* Agenda 노드만 정리합니다.

    주의: draft 상태 Agenda는 삭제하지 않는다 — 사용자가 검토 중인 추출 결과일 수 있어
    재시작 시점 일괄 삭제는 데이터 유실로 이어진다 (Plan.md P0-7).
    """
    from graphdb.neo4j_client import run_cypher as _run

    try:
        await _run(
            "MATCH (n) WHERE n:Todo "
            "   OR (n:Agenda AND n.id IS NOT NULL AND n.id STARTS WITH 'todo-') "
            "DETACH DELETE n"
        )
        logger.info("[Cleanup] 노드 정리 완료")
    except Exception as e:
        logger.warning(f"[Cleanup] 노드 정리 실패 (무시): {e}")


async def _startup_sync_task() -> None:
    """서버 시작 시 정리 작업 + (옵션) PostgreSQL → Neo4j 전체 동기화.

    증분 동기화는 아웃박스(P2-4)가 보장하므로 전체 resync는 복구용 옵션이다 (P2-6).
    STARTUP_FULL_RESYNC=true 일 때만 수행 (content_hash 덕에 임베딩 재계산은 없음).
    """
    await _cleanup_stale_neo4j_nodes()
    if os.environ.get("STARTUP_FULL_RESYNC", "false").lower() != "true":
        logger.info("[StartupSync] 전체 resync 생략 (STARTUP_FULL_RESYNC=false)")
        return
    try:
        result = await sync_all_from_pg()
        logger.info(f"[StartupSync] 완료: {result}")
    except Exception as e:
        logger.error(f"[StartupSync] 오류: {e}")


async def _periodic_resync_task() -> None:
    """주기적으로 PostgreSQL 기준 전체 재동기화(orphan 정리 포함)를 수행하는 백그라운드 태스크.

    증분 동기화의 안전망 — 삭제 전파 누락·User 미동기화 등으로 Neo4j가 PG와 어긋나거나
    잔재(orphan)가 쌓이는 것을 주기적으로 바로잡는다. content_hash 덕에 변경 없는 임베딩은
    재계산하지 않아 반복 실행 비용이 낮다. 주기는 RESYNC_INTERVAL_SEC(기본 1800초=30분).
    """
    interval = int(os.environ.get("RESYNC_INTERVAL_SEC", "1800"))
    while True:
        await asyncio.sleep(interval)
        try:
            result = await sync_all_from_pg()
            removed = result.get("removed") or {}
            n_removed = sum(removed.values()) if isinstance(removed, dict) else 0
            synced = {k: v for k, v in result.items() if k != "removed"}
            if n_removed > 0:
                logger.info(
                    f"[AutoResync] 완료 — synced={synced}, removed={n_removed} (orphan 정리)"
                )
            else:
                logger.debug(f"[AutoResync] 완료 — synced={synced}, removed=0")
        except Exception as e:
            logger.error(f"[AutoResync] 오류: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    from llm.graph_runtime import init_checkpointer, close_checkpointer

    await init_checkpointer()  # HITL 영속화 (P3A-1) — 그래프 compile 전에 준비
    await _run_pg_migrations()  # 누락 컬럼 자동 추가
    await ensure_constraints()  # 중복 정리 + 유니크 제약 (P2-5)
    await init_vector_index()
    from graphdb.retrieval_registry import ensure_fulltext_indexes

    await ensure_fulltext_indexes()  # 하이브리드 검색용 (P3B-6)

    asyncio.create_task(_startup_sync_task())
    resync_task = asyncio.create_task(_periodic_resync_task())
    try:
        yield
    finally:
        resync_task.cancel()
        try:
            await resync_task
        except asyncio.CancelledError:
            pass
        await close_checkpointer()
        from graphdb.neo4j_client import close_driver

        await close_driver()  # Bolt 드라이버 커넥션 풀 종료


app = FastAPI(title="workma!te AI API", lifespan=lifespan)

# CORS: 허용 오리진 화이트리스트 (추가 오리진은 CORS_ALLOWED_ORIGINS 환경변수, 콤마 구분)
_default_origins = [
    "https://workmaite.project.skala-ai.com",
    "http://localhost:5173",
    "http://localhost:4173",
]
_extra_origins = [
    o.strip()
    for o in os.environ.get("CORS_ALLOWED_ORIGINS", "").split(",")
    if o.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(dict.fromkeys(_default_origins + _extra_origins)),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

Instrumentator().instrument(app).expose(app, endpoint="/metrics")

# 감사 로그 — 변경성 요청을 audit_logs에 기록 (P1-6)
from core.audit_middleware import AuditLogMiddleware  # noqa: E402

app.add_middleware(AuditLogMiddleware)

# 요청 단위 모델 오버라이드 — X-LLM-Model 헤더를 모든 LLM 호출에 적용 (P1)
from core.model_override import ModelOverrideMiddleware  # noqa: E402

app.add_middleware(ModelOverrideMiddleware)

# 라우터 — 인증(가입/로그인/토큰 발급)은 Spring 단일 주체, FastAPI는 검증만 (P1-1)
# supervisor는 P3A-4에서 graph_analysis/knowledge/archive/hitl_reviews로 분리됨
app.include_router(supervisor.router)
app.include_router(graph_analysis_router.router)
app.include_router(knowledge_router.router)
app.include_router(archive_router.router)
app.include_router(hitl_router.router)
app.include_router(chat_history.router)
app.include_router(neo4j_graph.router)
app.include_router(sync_router.router)
app.include_router(meetings_router.router)
app.include_router(meetings_router.ai_router)
app.include_router(sessions_router.router)
app.include_router(stt_router.router)
app.include_router(upload_router.router)
app.include_router(usage_router.router)
app.include_router(transcription_ws.router)  # 실시간 전사 WS (P5)


# WebSocket endpoints
def _ws_user_id(websocket: WebSocket) -> int | None:
    """쿼리 파라미터 token의 JWT를 검증해 user id를 반환합니다 (실패 시 None)."""
    from jose import jwt as _jwt, JWTError as _JWTError
    from core.auth import SECRET_KEY, ALGORITHMS

    token = websocket.query_params.get("token", "")
    if not token:
        return None
    try:
        payload = _jwt.decode(token, SECRET_KEY, algorithms=ALGORITHMS)
        if payload.get("type") == "refresh":
            return None  # refresh token으로 WS 인증 불가 (SEC-7)
        sub = payload.get("sub")
        return int(sub) if sub is not None else None
    except (_JWTError, ValueError):
        return None


@app.websocket("/ws/meetings/{meeting_id}/agenda")
async def ws_meeting_agenda(meeting_id: int, websocket: WebSocket):
    if _ws_user_id(websocket) is None:
        await websocket.close(code=4401)
        return
    await manager.connect_meeting(meeting_id, websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect_meeting(meeting_id, websocket)


@app.websocket("/ws/sessions/{session_id}/minutes")
async def ws_session_minutes(session_id: int, websocket: WebSocket):
    if _ws_user_id(websocket) is None:
        await websocket.close(code=4401)
        return
    await manager.connect_session(session_id, websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect_session(session_id, websocket)


@app.get("/health")
def health():
    return {"status": "ok"}
