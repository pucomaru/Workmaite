import asyncio
import logging
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from sqlalchemy.orm import Session

# Workmaite/.env 를 override=True로 로드 (기존 환경변수 덮어쓰기)
_base = os.path.dirname(__file__)
load_dotenv(os.path.join(_base, "..", "..", ".env"), override=True)

# LangSmith 트레이싱 비활성화 (유효한 API 키 없을 때 403 방지)
os.environ["LANGCHAIN_TRACING_V2"] = "false"
os.environ["LANGSMITH_TRACING"] = "false"

from database import get_db
from websocket_manager import manager
from auth import get_current_user

from routers import supervisor, chat_history, neo4j_graph, sync as sync_router
from routers import auth as auth_router
from routers import meetings as meetings_router
from routers import sessions as sessions_router
from routers import stt as stt_router
from neo4j_sync import init_vector_index, retry_failed_syncs, sync_all_from_pg

logger = logging.getLogger(__name__)

# Neo4j 재시도 주기 (초). 환경변수로 조정 가능.
_RETRY_INTERVAL_SEC = int(os.environ["NEO4J_RETRY_INTERVAL_SEC"])


async def _cleanup_stale_neo4j_nodes() -> None:
    """잘못 생성된 Todo 노드, todo-* Agenda, draft 상태 Agenda 노드를 정리합니다."""
    from neo4j_client import run_cypher as _run
    try:
        await _run(
            "MATCH (n) WHERE n:Todo "
            "   OR (n:Agenda AND n.id IS NOT NULL AND n.id STARTS WITH 'todo-') "
            "   OR (n:Agenda AND n.status = 'draft') "
            "DETACH DELETE n"
        )
        logger.info("[Cleanup] 스테일 Todo/Agenda(todo-*, draft) 노드 정리 완료")
    except Exception as e:
        logger.warning(f"[Cleanup] 노드 정리 실패 (무시): {e}")


async def _startup_sync_task() -> None:
    """서버 시작 시 PostgreSQL → Neo4j 전체 동기화 (백그라운드, 1회)."""
    await _cleanup_stale_neo4j_nodes()
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
    await init_vector_index()

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


app = FastAPI(title="workma!te AI API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 라우터
app.include_router(auth_router.router)
app.include_router(supervisor.router)
app.include_router(chat_history.router)
app.include_router(neo4j_graph.router)
app.include_router(sync_router.router)
app.include_router(meetings_router.router)
app.include_router(meetings_router.ai_router)
app.include_router(sessions_router.router)
app.include_router(stt_router.router)


# WebSocket endpoints
@app.websocket("/ws/meetings/{meeting_id}/agenda")
async def ws_meeting_agenda(meeting_id: int, websocket: WebSocket):
    await manager.connect_meeting(meeting_id, websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect_meeting(meeting_id, websocket)


@app.websocket("/ws/sessions/{session_id}/minutes")
async def ws_session_minutes(session_id: int, websocket: WebSocket):
    await manager.connect_session(session_id, websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect_session(session_id, websocket)


@app.get("/health")
def health():
    return {"status": "ok"}
