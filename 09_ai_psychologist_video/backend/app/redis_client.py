"""
Shared Redis client module.

In dev mode, uses a shared FakeServer instance so that all FakeRedis clients
(billing worker, WebSocket handler) share state and pubsub works between them.
"""

import logging

from app.config import settings

logger = logging.getLogger(__name__)

# Shared FakeServer instance for dev mode (ensures pubsub works across clients)
_fake_server = None


def _get_fake_server():
    """Get or create the shared FakeServer singleton."""
    global _fake_server
    if _fake_server is None:
        import fakeredis
        _fake_server = fakeredis.FakeServer()
    return _fake_server


async def get_redis():
    """
    Get a Redis client instance.

    Tries to connect to real Redis first. Falls back to fakeredis with a
    shared FakeServer so pubsub messages are delivered between all clients
    (billing worker, WebSocket handler, etc.).
    """
    try:
        import redis.asyncio as aioredis
        r = aioredis.from_url(settings.REDIS_URL)
        await r.ping()
        return r
    except Exception:
        import fakeredis.aioredis
        server = _get_fake_server()
        logger.info("Using fakeredis with shared server (dev mode)")
        return fakeredis.aioredis.FakeRedis(server=server)
