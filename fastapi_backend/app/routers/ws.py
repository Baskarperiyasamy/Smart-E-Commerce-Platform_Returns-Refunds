from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user_ws
from app.ws_manager import manager

router = APIRouter(tags=["WebSocket"])


@router.websocket("/ws/notifications")
async def ws_notifications(
    websocket: WebSocket,
    token: str = Query(..., description="JWT access token (browsers can't send Authorization headers on a WebSocket handshake, so it's passed as a query param instead)"),
    db: Session = Depends(get_db),
):
    """
    Real-time channel for order_status_updated and cart_updated events.

    Connect from the browser with:
        new WebSocket(`ws://127.0.0.1:8000/ws/notifications?token=${accessToken}`)

    Example messages pushed to the client:
        {"event": "order_status_updated", "data": {"type": "order_shipped", "message": "...", "order_id": "..."}}
        {"event": "cart_updated", "data": {"items": [...], "cart_total": ..., "grand_total": ...}}
    """
    user = get_current_user_ws(token, db)
    if user is None:
        await websocket.close(code=4001)
        return

    await manager.connect(user.id, websocket)
    try:
        while True:
            # This endpoint is push-only from the server's side; incoming
            # messages are just read and discarded to keep the connection
            # alive and to detect disconnects promptly.
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(user.id, websocket)
