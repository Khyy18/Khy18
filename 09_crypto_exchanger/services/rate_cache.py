"""TTL-based cache for rate estimates."""

import time
from typing import Any, Optional

from config import config


class RateCache:
    """Simple in-memory TTL cache for exchange rate estimates."""

    def __init__(self, ttl: int = 0):
        self._ttl = ttl or config.RATE_CACHE_TTL
        self._cache: dict[str, tuple[float, Any]] = {}

    def _make_key(
        self, from_currency: str, to_currency: str, amount: float, flow: str
    ) -> str:
        """Generate cache key."""
        return f"{from_currency.lower()}:{to_currency.lower()}:{amount}:{flow}"

    def get(
        self, from_currency: str, to_currency: str, amount: float, flow: str = "standard"
    ) -> Optional[Any]:
        """Get cached rate estimate if not expired."""
        key = self._make_key(from_currency, to_currency, amount, flow)
        if key in self._cache:
            timestamp, data = self._cache[key]
            if time.time() - timestamp < self._ttl:
                return data
            del self._cache[key]
        return None

    def set(
        self,
        from_currency: str,
        to_currency: str,
        amount: float,
        flow: str,
        data: Any,
    ) -> None:
        """Store rate estimate in cache."""
        key = self._make_key(from_currency, to_currency, amount, flow)
        self._cache[key] = (time.time(), data)

    def invalidate(
        self,
        from_currency: str,
        to_currency: str,
        amount: float,
        flow: str = "standard",
    ) -> None:
        """Remove a specific cache entry."""
        key = self._make_key(from_currency, to_currency, amount, flow)
        self._cache.pop(key, None)

    def clear(self) -> None:
        """Clear entire cache."""
        self._cache.clear()

    def cleanup(self) -> None:
        """Remove all expired entries."""
        now = time.time()
        expired_keys = [
            k for k, (ts, _) in self._cache.items() if now - ts >= self._ttl
        ]
        for k in expired_keys:
            del self._cache[k]


rate_cache = RateCache()
