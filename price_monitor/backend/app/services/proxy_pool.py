"""Proxy pool service - proxy rotation for parsers."""
from __future__ import annotations


import logging
import random
from pathlib import Path

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

class ProxyPool:
    """Manages a pool of proxies with health checking and rotation."""

    def __init__(self) -> None:
        self._proxies: list[str] = []
        self._healthy: list[str] = []

    def load_proxies(self) -> None:
        """Load proxies from configured file."""
        if not settings.proxy_list_file:
            return
        path = Path(settings.proxy_list_file)
        if not path.exists():
            logger.warning("Proxy file not found: %s", path)
            return
        self._proxies = [
            line.strip() for line in path.read_text().splitlines() if line.strip()
        ]
        self._healthy = list(self._proxies)
        logger.info("Loaded %d proxies", len(self._proxies))

    def get_proxy(self) -> str | None:
        """Get a random healthy proxy."""
        if not self._healthy:
            return None
        return random.choice(self._healthy)

    async def health_check(self) -> dict:
        """Check health of all proxies."""
        healthy = []
        for proxy in self._proxies:
            try:
                async with httpx.AsyncClient(proxy=proxy, timeout=10) as client:
                    resp = await client.get("https://httpbin.org/ip")
                    if resp.status_code == 200:
                        healthy.append(proxy)
            except Exception:
                pass

        self._healthy = healthy
        logger.info("Proxy health check: %d/%d healthy", len(healthy), len(self._proxies))
        return {
            "total": len(self._proxies),
            "healthy": len(healthy),
        }

proxy_pool = ProxyPool()
