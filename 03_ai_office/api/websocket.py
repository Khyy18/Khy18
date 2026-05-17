"""WebSocket endpoint для real-time обновлений в Mini App."""

from __future__ import annotations

from typing import Optional

from fastapi import WebSocket, WebSocketDisconnect
from jose import JWTError, jwt

from ai_office.core.config import settings


ALGORITHM = "HS256"


class ConnectionManager:
    """Менеджер WebSocket соединений с поддержкой tenant isolation."""

    def __init__(self):
        # Connections grouped by tenant_id. None key is for unauthenticated.
        self.connections_by_tenant: dict[Optional[str], list[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, tenant_id: Optional[str] = None):
        """Принять и зарегистрировать новое соединение."""
        await websocket.accept()
        if tenant_id not in self.connections_by_tenant:
            self.connections_by_tenant[tenant_id] = []
        self.connections_by_tenant[tenant_id].append(websocket)

    def disconnect(self, websocket: WebSocket, tenant_id: Optional[str] = None):
        """Удалить соединение из списка активных."""
        connections = self.connections_by_tenant.get(tenant_id, [])
        if websocket in connections:
            connections.remove(websocket)
            if not connections:
                del self.connections_by_tenant[tenant_id]

    async def broadcast(self, message: dict, tenant_id: Optional[str] = None):
        """Отправить сообщение клиентам.

        If tenant_id is specified, only broadcast to that tenant's connections.
        If tenant_id is None, broadcast to all connections (backward compat).
        """
        if tenant_id is not None:
            # Send only to the specified tenant's connections
            connections = self.connections_by_tenant.get(tenant_id, [])[:]
            for connection in connections:
                try:
                    await connection.send_json(message)
                except Exception:
                    self.connections_by_tenant.get(tenant_id, []).remove(connection)
        else:
            # Broadcast to all connections (backward compat)
            for tid, connections in list(self.connections_by_tenant.items()):
                for connection in connections[:]:
                    try:
                        await connection.send_json(message)
                    except Exception:
                        connections.remove(connection)


manager = ConnectionManager()


def _extract_tenant_from_token(token: Optional[str]) -> Optional[str]:
    """Extract tenant_id from a JWT token. Returns None on failure."""
    if not token:
        return None
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[ALGORITHM])
        return payload.get("tenant_id")
    except JWTError:
        return None


async def broadcast_event(
    event_type: str, data: dict = None, tenant_id: Optional[str] = None
):
    """Отправить событие WebSocket клиентам.

    If tenant_id is specified, only broadcast to that tenant's connections.
    If None, broadcast to all (backward compat).
    """
    message = {"event": event_type, "data": data or {}}
    await manager.broadcast(message, tenant_id=tenant_id)


async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint - поддерживает соединение и слушает отключение."""
    # Try to extract tenant_id from token query param
    token = websocket.query_params.get("token")
    tenant_id = _extract_tenant_from_token(token)

    await manager.connect(websocket, tenant_id=tenant_id)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket, tenant_id=tenant_id)
