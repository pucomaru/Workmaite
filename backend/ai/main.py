import asyncio
import logging
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv
from sqlalchemy.orm import Session

# Workmaite/.env 를 override=True로 로드 (기존 환경변수 덮어쓰기)
_base = os.path.dirname(__file__)
load_dotenv(os.path.join(_base, "..", "..", ".env"), override=True)

# LangSmith 트레이싱 비활성화 (유효한 API 키 없을 때 403 방지)
os.environ["LANGCHAIN_TRACING_V2"] = "false"
os.environ["LANGSMITH_TRACING"] = "false"

from database import engine, get_db
import models
from websocket_manager import manager
from auth import get_current_user

from routers import notifications, agents, chat_history, neo4j_graph, sync as sync_router
from routers import auth as auth_router
from routers import meetings as meetings_router
from routers import sessions as sessions_router
from routers import stt as stt_router
from neo4j_sync import init_vector_index, retry_failed_syncs, sync_all_from_pg

logger = logging.getLogger(__name__)

# Neo4j 재시도 주기 (초). 환경변수로 조정 가능.
_RETRY_INTERVAL_SEC = int(os.getenv("NEO4J_RETRY_INTERVAL_SEC", "300"))


async def _startup_sync_task() -> None:
    """서버 시작 시 PostgreSQL → Neo4j 전체 동기화 (백그라운드, 1회)."""
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
    # FastAPI가 관리하는 AI 전용 테이블만 생성
    # (users, meetings 등 공유 테이블은 SpringBoot ddl-auto:update가 생성)
    ai_only_tables = [
        models.User.__table__,
        models.Notification.__table__,
        models.ChatMessage.__table__,
        models.AgentLog.__table__,
        models.TokenUsageLog.__table__,
        models.HitlReview.__table__,
        models.ArchiveCombined.__table__,
    ]
    models.Base.metadata.create_all(bind=engine, tables=ai_only_tables, checkfirst=True)
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

# Static files for uploads
os.makedirs("uploads", exist_ok=True)
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")

# 라우터
app.include_router(auth_router.router)
app.include_router(notifications.router)
app.include_router(agents.router)
app.include_router(chat_history.router)
app.include_router(neo4j_graph.router)
app.include_router(sync_router.router)
app.include_router(meetings_router.router)
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


@app.websocket("/ws/notifications/{user_id}")
async def ws_notifications(user_id: int, websocket: WebSocket):
    await manager.connect_user(user_id, websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect_user(user_id)


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
