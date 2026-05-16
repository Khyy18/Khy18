"""Proxy rotation manager for LinkedIn browser sessions.

Provides round-robin proxy selection with health scoring, sticky sessions,
provider API integration (BrightData/Smartproxy), and fingerprint randomization.
"""

from __future__ import annotations

import logging
import random
import time
from typing import Any

import httpx

logger = logging.getLogger(__name__)

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
]

TIMEZONES = [
    "America/New_York",
    "America/Chicago",
    "America/Denver",
    "America/Los_Angeles",
    "Europe/London",
    "Europe/Paris",
    "Europe/Berlin",
]

LANGUAGES = ["en-US", "en-GB", "en"]

SCREEN_RESOLUTIONS = [
    {"width": 1920, "height": 1080},
    {"width": 1366, "height": 768},
    {"width": 1536, "height": 864},
    {"width": 1440, "height": 900},
    {"width": 1280, "height": 720},
    {"width": 2560, "height": 1440},
]


class ProxyManager:
    """Manages a pool of residential proxies with health scoring and rotation."""

    def __init__(
        self,
        proxy_pool: list[dict],
        provider_api_key: str = "",
        provider: str = "static",
    ) -> None:
        self._proxy_pool: list[dict] = []
        for p in proxy_pool:
            proxy = {
                "url": p.get("url", ""),
                "username": p.get("username", ""),
                "password": p.get("password", ""),
                "type": p.get("type", "residential"),
                "health_score": p.get("health_score", 1.0),
                "last_used": p.get("last_used"),
                "session_id": p.get("session_id"),
            }
            self._proxy_pool.append(proxy)

        self._provider_api_key = provider_api_key
        self._provider = provider
        self._round_robin_index = 0
        self._sticky_sessions: dict[str, dict] = {}

    @property
    def proxy_pool(self) -> list[dict]:
        """Return current proxy pool."""
        return self._proxy_pool

    def get_proxy(self, session_id: str | None = None) -> dict | None:
        """Get a proxy from the pool.

        If session_id is provided, return the sticky proxy for that session.
        Otherwise, use round-robin with health weighting.
        """
        if not self._proxy_pool:
            return None

        if session_id and session_id in self._sticky_sessions:
            return self._sticky_sessions[session_id]

        healthy = self.get_healthy_proxies()
        if not healthy:
            return None

        # Round-robin through healthy proxies
        proxy = healthy[self._round_robin_index % len(healthy)]
        self._round_robin_index += 1
        proxy["last_used"] = time.time()

        if session_id:
            proxy["session_id"] = session_id
            self._sticky_sessions[session_id] = proxy

        return proxy

    def release_proxy(self, session_id: str) -> None:
        """Release a sticky session proxy."""
        if session_id in self._sticky_sessions:
            proxy = self._sticky_sessions.pop(session_id)
            proxy["session_id"] = None

    def report_failure(self, proxy_url: str) -> None:
        """Decrease health_score by 0.2 (minimum 0.0) for a proxy."""
        for proxy in self._proxy_pool:
            if proxy["url"] == proxy_url:
                proxy["health_score"] = max(0.0, proxy["health_score"] - 0.2)
                logger.info(
                    "Proxy %s health decreased to %.1f",
                    proxy_url,
                    proxy["health_score"],
                )
                break

    def report_success(self, proxy_url: str) -> None:
        """Increase health_score by 0.1 (maximum 1.0) for a proxy."""
        for proxy in self._proxy_pool:
            if proxy["url"] == proxy_url:
                proxy["health_score"] = min(1.0, proxy["health_score"] + 0.1)
                break

    async def health_check(self) -> dict:
        """Ping all proxies and return health status."""
        results: dict[str, Any] = {}
        for proxy in self._proxy_pool:
            url = proxy["url"]
            try:
                proxies_config = {"http://": url, "https://": url}
                async with httpx.AsyncClient(
                    proxies=proxies_config, timeout=10.0
                ) as client:
                    resp = await client.get("https://httpbin.org/ip")
                    results[url] = {
                        "status": "healthy" if resp.status_code == 200 else "unhealthy",
                        "response_code": resp.status_code,
                        "health_score": proxy["health_score"],
                    }
            except Exception as exc:
                results[url] = {
                    "status": "unreachable",
                    "error": str(exc),
                    "health_score": proxy["health_score"],
                }
        return results

    def get_healthy_proxies(self) -> list[dict]:
        """Return proxies with health_score > 0.3."""
        return [p for p in self._proxy_pool if p["health_score"] > 0.3]

    def rotate_for_session(self, session_id: str) -> dict | None:
        """Force rotation: assign a new proxy to the session.

        Releases the current proxy and assigns a different one.
        """
        current = self._sticky_sessions.get(session_id)
        self.release_proxy(session_id)

        healthy = self.get_healthy_proxies()
        if not healthy:
            return None

        # Pick a different proxy if possible
        candidates = [p for p in healthy if p != current] if current else healthy
        if not candidates:
            candidates = healthy

        proxy = candidates[self._round_robin_index % len(candidates)]
        self._round_robin_index += 1
        proxy["last_used"] = time.time()
        proxy["session_id"] = session_id
        self._sticky_sessions[session_id] = proxy
        return proxy

    async def refresh_pool_from_provider(self) -> list[dict]:
        """Fetch proxy list from BrightData or Smartproxy provider API.

        Returns the updated proxy pool.
        """
        if self._provider == "static" or not self._provider_api_key:
            return self._proxy_pool

        try:
            if self._provider == "brightdata":
                url = "https://brightdata.com/api/zone/ips"
                headers = {"Authorization": f"Bearer {self._provider_api_key}"}
            elif self._provider == "smartproxy":
                url = "https://api.smartproxy.com/v1/endpoints"
                headers = {"Authorization": f"Token {self._provider_api_key}"}
            else:
                return self._proxy_pool

            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(url, headers=headers)
                if resp.status_code == 200:
                    data = resp.json()
                    new_proxies = []
                    for item in data if isinstance(data, list) else data.get("ips", []):
                        proxy_url = item if isinstance(item, str) else item.get("url", "")
                        new_proxies.append({
                            "url": proxy_url,
                            "username": item.get("username", "") if isinstance(item, dict) else "",
                            "password": item.get("password", "") if isinstance(item, dict) else "",
                            "type": "residential",
                            "health_score": 1.0,
                            "last_used": None,
                            "session_id": None,
                        })
                    if new_proxies:
                        self._proxy_pool = new_proxies
                        logger.info(
                            "Refreshed proxy pool from %s: %d proxies",
                            self._provider,
                            len(new_proxies),
                        )
        except Exception as exc:
            logger.error("Failed to refresh proxy pool from %s: %s", self._provider, exc)

        return self._proxy_pool

    @staticmethod
    def generate_fingerprint() -> dict:
        """Generate a random browser fingerprint for session isolation.

        Returns dict with user_agent, timezone, language, and screen_resolution.
        """
        return {
            "user_agent": random.choice(USER_AGENTS),
            "timezone": random.choice(TIMEZONES),
            "language": random.choice(LANGUAGES),
            "screen_resolution": random.choice(SCREEN_RESOLUTIONS),
        }
