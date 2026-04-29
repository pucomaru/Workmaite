import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv
from sqlalchemy.orm import Session

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

from database import engine, get_db
import models
from websocket_manager import manager
from auth import get_current_user

from routers import auth, meetings, agendas, todos, reports, sessions, notifications, card_news, tacit_knowledge, agents, chat_history, livekit


@asynccontextmanager
async def lifespan(app: FastAPI):
    models.Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(title="WorkMate API", lifespan=lifespan)

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

# Routers
app.include_router(auth.router)
app.include_router(meetings.router)
app.include_router(agendas.router)
app.include_router(todos.router)
app.include_router(reports.router)
app.include_router(sessions.router)
app.include_router(notifications.router)
app.include_router(card_news.router)
app.include_router(tacit_knowledge.router)
app.include_router(agents.router)
app.include_router(chat_history.router)
app.include_router(livekit.router)


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
