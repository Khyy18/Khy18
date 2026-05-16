"""WebSocket endpoint for real-time price updates."""
from __future__ import annotations

import logging
from fastapi import APIRouter, Header, HTTPException, WebSocket, WebSocketDisconnect, Query
from pydantic import BaseModel
from app.config import settings
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


class PriceUpdateNotification(BaseModel):
    product_id: int
    old_price: float
    new_price: float
    discount_percent: float


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


@router.post("/ws/notify-price-update")
async def notify_price_update(
    data: PriceUpdateNotification,
    x_internal_token: str = Header(""),
):
    """Internal endpoint for the bot/worker to notify about price changes.

    The bot calls this after detecting a price update, which then
    broadcasts the update to all connected WebSocket clients.
    Requires X-Internal-Token header matching INTERNAL_API_KEY.
    """
    if not settings.internal_api_key or x_internal_token != settings.internal_api_key:
        raise HTTPException(status_code=403, detail="Forbidden")
    await broadcast_price_update(
        product_id=data.product_id,
        old_price=data.old_price,
        new_price=data.new_price,
        discount_percent=data.discount_percent,
    )
    return {"ok": True, "clients_count": len(manager.active_connections)}


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
