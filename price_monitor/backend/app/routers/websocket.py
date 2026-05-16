"""WebSocket endpoint for real-time price updates."""
from __future__ import annotations

import logging
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
from app.middleware.auth import verify_token

logger = logging.getLogger(__name__)
router = APIRouter(tags=["websocket"])


class ConnectionManager:
    """Manages active WebSocket connections."""

    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        for connection in self.active_connections[:]:
            try:
                await connection.send_json(message)
            except Exception:
                self.active_connections.remove(connection)


manager = ConnectionManager()


@router.websocket("/ws/prices")
async def websocket_prices(websocket: WebSocket, token: str = Query("")):
    """WebSocket endpoint for live price updates.

    Authenticate via ?token=JWT query parameter.
    """
    # Verify JWT token
    try:
        payload = verify_token(token)
    except Exception:
        await websocket.close(code=4001)
        return

    await manager.connect(websocket)
    try:
        while True:
            # Keep connection alive, wait for client messages (heartbeat)
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        manager.disconnect(websocket)


async def broadcast_price_update(
    product_id: int, old_price: float, new_price: float, discount_percent: float
):
    """Broadcast price update to all connected WebSocket clients."""
    await manager.broadcast({
        "type": "price_update",
        "product_id": str(product_id),
        "old_price": old_price,
        "new_price": new_price,
        "discount_percent": discount_percent,
    })
