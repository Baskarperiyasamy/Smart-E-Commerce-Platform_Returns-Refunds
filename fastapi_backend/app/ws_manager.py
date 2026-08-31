import asyncio
from typing import Dict, List

from fastapi import WebSocket

# Captured on app startup (see main.py) so that regular ("sync") request
# handlers running in FastAPI's worker threadpool can still schedule a
# broadcast back onto the main asyncio event loop that owns the actual
# WebSocket connections.
main_loop: asyncio.AbstractEventLoop | None = None


class ConnectionManager:
    """Tracks active WebSocket connections, keyed by user_id. A user can have
    more than one connection open (e.g. two browser tabs)."""

    def __init__(self):
        self.active: Dict[str, List[WebSocket]] = {}

    async def connect(self, user_id: str, websocket: WebSocket):
        await websocket.accept()
        self.active.setdefault(user_id, []).append(websocket)

    def disconnect(self, user_id: str, websocket: WebSocket):
        conns = self.active.get(user_id)
        if conns and websocket in conns:
            conns.remove(websocket)
            if not conns:
                self.active.pop(user_id, None)

    async def send_to_user(self, user_id: str, event: str, data: dict):
        conns = list(self.active.get(user_id, []))
        payload = {"event": event, "data": data}
        for ws in conns:
            try:
                await ws.send_json(payload)
            except Exception:
                self.disconnect(user_id, ws)


manager = ConnectionManager()


def broadcast(user_id: str, event: str, data: dict):
    """Sync-callable entry point. Safe to call from a regular ('def', not
    'async def') route handler running in FastAPI's threadpool — schedules
    the actual send onto the main event loop instead of trying (and failing)
    to run async code directly in a worker thread."""
    if main_loop is None:
        return
    asyncio.run_coroutine_threadsafe(manager.send_to_user(user_id, event, data), main_loop)
