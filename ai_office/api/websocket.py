"""WebSocket endpoint для real-time обновлений в Mini App."""

from fastapi import WebSocket, WebSocketDisconnect


class ConnectionManager:
    """Менеджер WebSocket соединений."""

    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        """Принять и зарегистрировать новое соединение."""
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        """Удалить соединение из списка активных."""
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        """Отправить сообщение всем подключенным клиентам."""
        for connection in self.active_connections[:]:
            try:
                await connection.send_json(message)
            except Exception:
                self.active_connections.remove(connection)


manager = ConnectionManager()


async def broadcast_event(event_type: str, data: dict = None):
    """Отправить событие всем подключенным WebSocket клиентам."""
    message = {"event": event_type, "data": data or {}}
    await manager.broadcast(message)


async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint - поддерживает соединение и слушает отключение."""
    await manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)
