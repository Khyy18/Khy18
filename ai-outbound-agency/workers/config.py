"""ARQ worker configuration."""

from __future__ import annotations

from arq.connections import RedisSettings

from core.config import settings


def get_redis_settings() -> RedisSettings:
    """Parse redis URL from settings and return ARQ RedisSettings."""
    url = settings.arq_redis_url or settings.redis_url
    # Parse redis://host:port/db format
    # RedisSettings accepts host, port, database
    from urllib.parse import urlparse

    parsed = urlparse(url)
    host = parsed.hostname or "localhost"
    port = parsed.port or 6379
    database = int(parsed.path.lstrip("/") or "0")
    password = parsed.password or None

    return RedisSettings(
        host=host,
        port=port,
        database=database,
        password=password,
    )


redis_settings = get_redis_settings()
