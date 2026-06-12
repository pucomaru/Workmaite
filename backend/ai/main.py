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

# LangSmith 트레이싱: API 키가 있고 LANGSMITH_TRACING=true일 때만 활성화 (키 없이 켜면 403 스팸)
_tracing_on = os.environ.get("LANGSMITH_TRACING", "").lower() == "true" and bool(os.environ.get("LANGSMITH_API_KEY"))
os.environ["LANGCHAIN_TRACING_V2"] = "true" if _tracing_on else "false"
os.environ["LANGSMITH_TRACING"] = "true" if _tracing_on else "false"

from websocket_manager import manager

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
from neo4j_sync import ensure_constraints, init_vector_index, retry_failed_syncs, sync_all_from_pg
from prometheus_fastapi_instrumentator import Instrumentator

logger = logging.getLogger(__name__)

# Neo4j 재시도 주기 (초). 환경변수로 조정 가능.
_RETRY_INTERVAL_SEC = int(os.environ["NEO4J_RETRY_INTERVAL_SEC"])


async def _cleanup_stale_neo4j_nodes() -> None:
    """레거시 Todo 노드와 todo-* Agenda 노드만 정리합니다.

    주의: draft 상태 Agenda는 삭제하지 않는다 — 사용자가 검토 중인 추출 결과일 수 있어
    재시작 시점 일괄 삭제는 데이터 유실로 이어진다 (Plan.md P0-7).
    """
    from neo4j_client import run_cypher as _run
    try:
        await _run(
            "MATCH (n) WHERE n:Todo "
            "   OR (n:Agenda AND n.id IS NOT NULL AND n.id STARTS WITH 'todo-') "
            "DETACH DELETE n"
        )
        logger.info("[Cleanup] 레거시 Todo/todo-* 노드 정리 완료")
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


async def _periodic_retry_task() -> None:
    """실패한 Neo4j 동기화를 주기적으로 재시도하는 백그라운드 태스크."""
    while True:
        await asyncio.sleep(_RETRY_INTERVAL_SEC)
        try:
            result = await retry_failed_syncs(max_retries=5)
            if result["retried"] > 0:
                logger.info(
                    f"[AutoRetry] retried={result['retried']} "
                    f"recovered={result['recovered']} skipped={result['skipped']}"
                )
        except Exception as e:
            logger.error(f"[AutoRetry] 오류: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    from graph_runtime import init_checkpointer, close_checkpointer
    await init_checkpointer()  # HITL 영속화 (P3A-1) — 그래프 compile 전에 준비
    await ensure_constraints()  # 중복 정리 + 유니크 제약 (P2-5)
    await init_vector_index()
    from retrieval_registry import ensure_fulltext_indexes
    await ensure_fulltext_indexes()  # 하이브리드 검색용 (P3B-6)

    asyncio.create_task(_startup_sync_task())
    retry_task = asyncio.create_task(_periodic_retry_task())
    try:
        yield
    finally:
        retry_task.cancel()
        try:
            await retry_task
        except asyncio.CancelledError:
            pass
        await close_checkpointer()


app = FastAPI(title="workma!te AI API", lifespan=lifespan)

# CORS: 허용 오리진 화이트리스트 (추가 오리진은 CORS_ALLOWED_ORIGINS 환경변수, 콤마 구분)
_default_origins = [
    "https://workmaite.project.skala-ai.com",
    "http://localhost:5173",
    "http://localhost:4173",
]
_extra_origins = [o.strip() for o in os.environ.get("CORS_ALLOWED_ORIGINS", "").split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(dict.fromkeys(_default_origins + _extra_origins)),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

Instrumentator().instrument(app).expose(app, endpoint="/metrics")

# 감사 로그 — 변경성 요청을 audit_logs에 기록 (P1-6)
from audit_middleware import AuditLogMiddleware  # noqa: E402
app.add_middleware(AuditLogMiddleware)

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


# WebSocket endpoints
def _ws_user_id(websocket: WebSocket) -> int | None:
    """쿼리 파라미터 token의 JWT를 검증해 user id를 반환합니다 (실패 시 None)."""
    from jose import jwt as _jwt, JWTError as _JWTError
    from auth import SECRET_KEY, ALGORITHM
    token = websocket.query_params.get("token", "")
    if not token:
        return None
    try:
        payload = _jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
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
