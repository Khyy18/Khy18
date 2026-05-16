"""Дедупликация арбитражных возможностей."""

import time
from typing import Any


class ArbDeduplicator:
    """In-memory дедупликатор арбитражей с TTL 5 минут."""

    def __init__(self, ttl_sec: float = 300.0) -> None:
        self._seen: dict[str, float] = {}
        self._ttl = ttl_sec

    def _make_key(self, opp: dict[str, Any]) -> str:
        home = opp.get("home", "")
        away = opp.get("away", "")
        market = opp.get("details", {}).get("market", opp.get("type", ""))
        arb_type = opp.get("type", "")
        return f"{home}_{away}_{market}_{arb_type}"

    def _cleanup(self) -> None:
        now = time.time()
        expired = [k for k, ts in self._seen.items() if now - ts > self._ttl]
        for k in expired:
            del self._seen[k]

    def is_duplicate(self, opp: dict[str, Any]) -> bool:
        """Проверяет, является ли возможность дубликатом."""
        self._cleanup()
        key = self._make_key(opp)
        return key in self._seen

    def mark_executed(self, opp: dict[str, Any]) -> None:
        """Отмечает возможность как исполненную."""
        key = self._make_key(opp)
        self._seen[key] = time.time()
