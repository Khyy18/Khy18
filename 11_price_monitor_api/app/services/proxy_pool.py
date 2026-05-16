"""Proxy rotation pool with health checking."""

import asyncio
import logging
from pathlib import Path

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


class ProxyPool:
    """Manages a pool of proxies with round-robin rotation and health checks."""

    def __init__(self):
        self._all_proxies: list[str] = []
        self._healthy_proxies: list[str] = []
        self._index: int = 0
        self._lock = asyncio.Lock()

    def load_proxies(self, file_path: str | None = None) -> None:
        """Load proxies from a file (one per line).

        Format: protocol://user:pass@host:port
        """
        path = file_path or settings.proxy_list_file
        if not path:
            logger.warning("No proxy list file configured")
            return

        p = Path(path)
        if not p.exists():
            logger.warning("Proxy file not found: %s", path)
            return

        lines = p.read_text().strip().splitlines()
        self._all_proxies = [line.strip() for line in lines if line.strip()]
        self._healthy_proxies = list(self._all_proxies)
        logger.info("Loaded %d proxies from %s", len(self._all_proxies), path)

    async def get_proxy(self) -> str | None:
        """Get next healthy proxy using round-robin rotation."""
        async with self._lock:
            if not self._healthy_proxies:
                return None
            proxy = self._healthy_proxies[self._index % len(self._healthy_proxies)]
            self._index += 1
            return proxy

    def mark_dead(self, proxy: str) -> None:
        """Mark a proxy as unhealthy."""
        if proxy in self._healthy_proxies:
            self._healthy_proxies.remove(proxy)
            logger.info("Proxy marked dead: %s", proxy)

    async def health_check(self) -> None:
        """Ping each proxy to check if it is alive."""
        healthy = []
        for proxy in self._all_proxies:
            try:
                async with httpx.AsyncClient(
                    proxy=proxy, timeout=5.0
                ) as client:
                    resp = await client.get("https://httpbin.org/ip")
                    if resp.status_code == 200:
                        healthy.append(proxy)
            except Exception:
                logger.debug("Proxy health check failed: %s", proxy)

        async with self._lock:
            self._healthy_proxies = healthy
            self._index = 0

        logger.info(
            "Proxy health check: %d/%d healthy",
            len(healthy),
            len(self._all_proxies),
        )

    def get_stats(self) -> dict:
        """Return proxy pool statistics."""
        return {
            "total": len(self._all_proxies),
            "healthy": len(self._healthy_proxies),
            "dead": len(self._all_proxies) - len(self._healthy_proxies),
        }


# Module-level singleton
proxy_pool = ProxyPool()
