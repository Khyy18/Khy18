"""Модуль real-time WebSocket дашборда AI-агентства."""

import asyncio
import json
import logging
from datetime import datetime
from typing import Set, Optional

from aiohttp import web, WSMsgType

import config

logger = logging.getLogger(__name__)

# Активные WebSocket подключения
_ws_connections: Set[web.WebSocketResponse] = set()

# Попытка импорта aiosqlite (graceful)
try:
    import aiosqlite
except ImportError:
    aiosqlite = None


def _get_ws_auth_token() -> str:
    """Получить токен аутентификации для WebSocket."""
    return getattr(config, "WS_AUTH_TOKEN", "")


async def _get_live_counters() -> dict:
    """Получить текущие live-счётчики."""
    if aiosqlite is None:
        return {"revenue_today": 0, "orders_in_queue": 0, "active_clients": 0}

    try:
        async with aiosqlite.connect(config.DATABASE_PATH) as db:
            today = datetime.utcnow().strftime("%Y-%m-%d")

            # Revenue today
            cursor = await db.execute(
                "SELECT COALESCE(SUM(price), 0) FROM orders WHERE DATE(created_at) = ? AND status = 'completed'",
                (today,),
            )
            row = await cursor.fetchone()
            revenue_today = row[0] if row else 0

            # Orders in queue
            cursor = await db.execute(
                "SELECT COUNT(*) FROM orders WHERE status IN ('pending', 'processing')"
            )
            row = await cursor.fetchone()
            orders_in_queue = row[0] if row else 0

            # Active clients (ordered today)
            cursor = await db.execute(
                "SELECT COUNT(DISTINCT client_id) FROM orders WHERE DATE(created_at) = ?",
                (today,),
            )
            row = await cursor.fetchone()
            active_clients = row[0] if row else 0

            return {
                "revenue_today": revenue_today,
                "orders_in_queue": orders_in_queue,
                "active_clients": active_clients,
            }
    except Exception as e:
        logger.debug("Ошибка получения live counters: %s", e)
        return {"revenue_today": 0, "orders_in_queue": 0, "active_clients": 0}


async def websocket_handler(request: web.Request) -> web.WebSocketResponse:
    """
    WebSocket handler для real-time дашборда.

    Аутентификация через query param: /ws/dashboard?token=XXX
    """
    # Аутентификация
    token = request.query.get("token", "")
    expected_token = _get_ws_auth_token()

    ws = web.WebSocketResponse()
    await ws.prepare(request)

    if expected_token and token != expected_token:
        await ws.send_json({"type": "error", "message": "Unauthorized"})
        await ws.close()
        return ws

    # Добавляем подключение
    _ws_connections.add(ws)
    logger.info("WebSocket подключение установлено (всего: %d)", len(_ws_connections))

    # Отправляем начальные данные
    try:
        counters = await _get_live_counters()
        await ws.send_json({"type": "counters", "data": counters})
    except Exception as e:
        logger.debug("Ошибка отправки начальных данных WS: %s", e)

    # Слушаем входящие сообщения (ping/pong)
    try:
        async for msg in ws:
            if msg.type == WSMsgType.TEXT:
                data = msg.data
                if data == "ping":
                    await ws.send_str("pong")
                elif data == "get_counters":
                    counters = await _get_live_counters()
                    await ws.send_json({"type": "counters", "data": counters})
            elif msg.type in (WSMsgType.ERROR, WSMsgType.CLOSE):
                break
    except Exception as e:
        logger.debug("WebSocket ошибка: %s", e)
    finally:
        _ws_connections.discard(ws)
        logger.info(
            "WebSocket отключение (осталось: %d)", len(_ws_connections)
        )

    return ws


async def broadcast_event(event_type: str, data: Optional[dict] = None) -> int:
    """
    Отправить событие всем подключённым WebSocket-клиентам.

    Args:
        event_type: тип события (new_order, payment, rating)
        data: дополнительные данные события

    Returns:
        Количество успешно отправленных сообщений
    """
    if not _ws_connections:
        return 0

    message = json.dumps({
        "type": event_type,
        "data": data or {},
        "timestamp": datetime.utcnow().isoformat(),
    })

    sent = 0
    dead_connections = set()

    for ws in _ws_connections.copy():
        try:
            if not ws.closed:
                await ws.send_str(message)
                sent += 1
            else:
                dead_connections.add(ws)
        except Exception:
            dead_connections.add(ws)

    # Удаляем мёртвые подключения
    for dead in dead_connections:
        _ws_connections.discard(dead)

    return sent


def create_ws_handler():
    """Создать WebSocket handler для маршрутизации aiohttp."""
    return websocket_handler


def get_connection_count() -> int:
    """Получить количество активных WebSocket подключений."""
    return len(_ws_connections)
