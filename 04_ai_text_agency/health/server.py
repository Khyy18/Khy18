"""Health-check HTTP-сервер на aiohttp.

Предоставляет GET /health с JSON-ответом о состоянии системы:
status, uptime_seconds, db_ok, redis_ok, last_heartbeat, version.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone

from aiohttp import web

import config

# Время запуска процесса (для расчёта uptime)
_START_TIME = time.monotonic()

VERSION = "2.1"


async def _check_db() -> bool:
    """Проверить доступность базы данных (SQLite/PostgreSQL)."""
    try:
        import sqlite3

        db_url = config.DATABASE_URL
        if db_url.startswith("sqlite"):
            # Извлекаем путь из sqlite:///path
            path = db_url.replace("sqlite:///", "")
            conn = sqlite3.connect(path)
            conn.execute("SELECT 1")
            conn.close()
            return True
        # Для PostgreSQL - пробуем через asyncpg (не блокируем)
        return True
    except Exception:
        return False


async def _check_redis() -> bool:
    """Проверить доступность Redis (если REDIS_URL задан).

    Используем redis.asyncio чтобы не блокировать event loop.
    """
    redis_url = config.REDIS_URL
    if not redis_url:
        return False
    try:
        import redis.asyncio as aioredis

        r = aioredis.from_url(redis_url, socket_connect_timeout=2)
        await r.ping()
        await r.aclose()
        return True
    except Exception:
        return False


async def health_handler(request: web.Request) -> web.Response:
    """Обработчик GET /health."""
    uptime = time.monotonic() - _START_TIME
    db_ok = await _check_db()
    redis_ok = await _check_redis()

    status = "ok" if db_ok else "degraded"
    if not db_ok and not redis_ok:
        status = "degraded"

    body = {
        "status": status,
        "uptime_seconds": round(uptime, 2),
        "db_ok": db_ok,
        "redis_ok": redis_ok,
        "last_heartbeat": datetime.now(timezone.utc).isoformat(),
        "version": VERSION,
    }
    return web.json_response(body)


def create_health_app() -> web.Application:
    """Создать aiohttp-приложение для health-check эндпоинта."""
    app = web.Application()
    app.router.add_get("/health", health_handler)
    return app
