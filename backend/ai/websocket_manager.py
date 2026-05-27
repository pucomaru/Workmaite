from typing import Dict, List
from fastapi import WebSocket


class ConnectionManager:
    def __init__(self):
        # meeting_id -> list of websockets
        self.meeting_connections: Dict[int, List[WebSocket]] = {}
        # user_id -> websocket
        self.user_connections: Dict[int, WebSocket] = {}
        # session_id -> list of websockets
        self.session_connections: Dict[int, List[WebSocket]] = {}

    async def connect_meeting(self, meeting_id: int, ws: WebSocket):
        await ws.accept()
        self.meeting_connections.setdefault(meeting_id, []).append(ws)

    async def connect_user(self, user_id: int, ws: WebSocket):
        await ws.accept()
        self.user_connections[user_id] = ws

    async def connect_session(self, session_id: int, ws: WebSocket):
        await ws.accept()
        self.session_connections.setdefault(session_id, []).append(ws)

    def disconnect_meeting(self, meeting_id: int, ws: WebSocket):
        conns = self.meeting_connections.get(meeting_id, [])
        if ws in conns:
            conns.remove(ws)

    def disconnect_user(self, user_id: int):
        self.user_connections.pop(user_id, None)

    def disconnect_session(self, session_id: int, ws: WebSocket):
        conns = self.session_connections.get(session_id, [])
        if ws in conns:
            conns.remove(ws)

    async def broadcast_meeting(self, meeting_id: int, message: dict):
        for ws in self.meeting_connections.get(meeting_id, []):
            try:
                await ws.send_json(message)
            except Exception:
                pass

    async def send_to_user(self, user_id: int, message: dict):
        ws = self.user_connections.get(user_id)
        if ws:
            try:
                await ws.send_json(message)
            except Exception:
                pass

    async def broadcast_session(self, session_id: int, message: dict):
        for ws in self.session_connections.get(session_id, []):
            try:
                await ws.send_json(message)
            except Exception:
                pass


manager = ConnectionManager()
