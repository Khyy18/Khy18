"""Асинхронный клиент к The Odds API v4 (the-odds-api.com).

Получает коэффициенты букмекеров по спортивным событиям.
Rate-limiting через asyncio.Semaphore (1 одновременный запрос).
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Optional

import aiohttp

from arbitrage import config

logger = logging.getLogger(__name__)

BASE_URL: str = "https://api.the-odds-api.com/v4"


class OddsAPIClient:
    """Клиент для The Odds API v4."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        session: Optional[aiohttp.ClientSession] = None,
    ) -> None:
        self._api_key: str = api_key or config.ODDS_API_KEY
        self._session: Optional[aiohttp.ClientSession] = session
        self._semaphore: asyncio.Semaphore = asyncio.Semaphore(1)
        self._owns_session: bool = False
        # Health monitoring
        self._remaining_quota: Optional[int] = None
        self._used_quota: Optional[int] = None
        self._last_latency_ms: float = 0.0

    async def _get_session(self) -> aiohttp.ClientSession:
        """Возвращает (или создаёт) aiohttp-сессию."""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
            self._owns_session = True
        return self._session

    async def close(self) -> None:
        """Закрывает сессию, если она создана клиентом."""
        if self._owns_session and self._session and not self._session.closed:
            await self._session.close()

    @property
    def remaining_quota(self) -> Optional[int]:
        """Оставшееся количество запросов к API."""
        return self._remaining_quota

    @property
    def used_quota(self) -> Optional[int]:
        """Использованное количество запросов к API."""
        return self._used_quota

    @property
    def last_latency_ms(self) -> float:
        """Задержка последнего запроса в миллисекундах."""
        return self._last_latency_ms

    def get_health(self) -> dict[str, Any]:
        """Возвращает словарь с информацией о здоровье API-клиента.

        Returns:
            dict с ключами: remaining_quota, used_quota, last_latency_ms
        """
        return {
            "remaining_quota": self._remaining_quota,
            "used_quota": self._used_quota,
            "last_latency_ms": round(self._last_latency_ms, 1),
        }

    async def _request(self, endpoint: str, params: Optional[dict[str, Any]] = None) -> Any:
        """Выполняет GET-запрос с rate-limiting."""
        async with self._semaphore:
            session = await self._get_session()
            url = f"{BASE_URL}{endpoint}"
            request_params: dict[str, Any] = {"apiKey": self._api_key}
            if params:
                request_params.update(params)

            logger.debug("OddsAPI запрос: %s params=%s", url, request_params)
            t_start: float = time.monotonic()
            async with session.get(url, params=request_params) as resp:
                t_end: float = time.monotonic()
                self._last_latency_ms = (t_end - t_start) * 1000.0

                # Захват квоты из заголовков
                remaining_hdr = resp.headers.get("x-requests-remaining")
                used_hdr = resp.headers.get("x-requests-used")
                if remaining_hdr is not None:
                    try:
                        self._remaining_quota = int(remaining_hdr)
                    except (ValueError, TypeError):
                        pass
                if used_hdr is not None:
                    try:
                        self._used_quota = int(used_hdr)
                    except (ValueError, TypeError):
                        pass

                if resp.status != 200:
                    text = await resp.text()
                    logger.error("OddsAPI ошибка %d: %s", resp.status, text)
                    return []
                data: Any = await resp.json()
                logger.debug(
                    "OddsAPI ответ: remaining=%s, used=%s, latency=%.0fms",
                    resp.headers.get("x-requests-remaining", "?"),
                    resp.headers.get("x-requests-used", "?"),
                    self._last_latency_ms,
                )
                return data

    async def get_sports(self) -> list[dict[str, Any]]:
        """Получает список доступных видов спорта."""
        result = await self._request("/sports")
        if not isinstance(result, list):
            return []
        return result

    async def get_odds(
        self,
        sport_key: str,
        markets: Optional[list[str]] = None,
        regions: Optional[list[str]] = None,
    ) -> list[dict[str, Any]]:
        """Получает коэффициенты для указанного вида спорта.

        Args:
            sport_key: ключ спорта (например 'soccer_epl')
            markets: рынки (h2h, totals, spreads)
            regions: регионы букмекеров (eu, uk, us)

        Returns:
            Список нормализованных событий с коэффициентами.
        """
        if markets is None:
            markets = ["h2h", "totals", "spreads"]
        if regions is None:
            regions = ["eu", "uk", "us"]

        params: dict[str, str] = {
            "markets": ",".join(markets),
            "regions": ",".join(regions),
            "oddsFormat": "decimal",
        }

        raw_events = await self._request(f"/sports/{sport_key}/odds", params)
        if not isinstance(raw_events, list):
            return []

        return self._normalize_events(raw_events, sport_key)

    @staticmethod
    def _normalize_events(
        raw_events: list[dict[str, Any]], sport_key: str
    ) -> list[dict[str, Any]]:
        """Нормализует ответ API в единую структуру."""
        normalized: list[dict[str, Any]] = []

        for event in raw_events:
            bookmakers_data: list[dict[str, Any]] = []

            for bm in event.get("bookmakers", []):
                markets_data: list[dict[str, Any]] = []
                for market in bm.get("markets", []):
                    outcomes: list[dict[str, Any]] = [
                        {"name": o.get("name", ""), "price": o.get("price", 0.0)}
                        for o in market.get("outcomes", [])
                    ]
                    markets_data.append({
                        "key": market.get("key", ""),
                        "outcomes": outcomes,
                    })
                bookmakers_data.append({
                    "key": bm.get("key", ""),
                    "title": bm.get("title", ""),
                    "markets": markets_data,
                })

            normalized.append({
                "id": event.get("id", ""),
                "sport": sport_key,
                "commence_time": event.get("commence_time", ""),
                "home_team": event.get("home_team", ""),
                "away_team": event.get("away_team", ""),
                "bookmakers": bookmakers_data,
            })

        return normalized
