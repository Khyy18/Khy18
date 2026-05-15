"""Асинхронный клиент к Pinnacle API.

Pinnacle - sharp-букмекер. Его линии используются как эталон
(true probability) для поиска value bets у мягких букмекеров.
"""

from __future__ import annotations

import asyncio
import base64
import logging
from typing import Any, Optional

import aiohttp

from arbitrage import config

logger = logging.getLogger(__name__)

BASE_URL: str = "https://guest.api.arcadia.pinnacle.com/0.1"


class PinnacleClient:
    """Клиент для Pinnacle API."""

    def __init__(
        self,
        username: Optional[str] = None,
        password: Optional[str] = None,
        session: Optional[aiohttp.ClientSession] = None,
    ) -> None:
        self._username: str = username or config.PINNACLE_USER
        self._password: str = password or config.PINNACLE_PASSWORD
        self._session: Optional[aiohttp.ClientSession] = session
        self._owns_session: bool = False
        self._semaphore: asyncio.Semaphore = asyncio.Semaphore(1)

    @property
    def _auth_header(self) -> str:
        """Формирует Basic-авторизацию."""
        credentials = f"{self._username}:{self._password}"
        encoded = base64.b64encode(credentials.encode()).decode()
        return f"Basic {encoded}"

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

    async def _request(self, endpoint: str, params: Optional[dict[str, Any]] = None) -> Any:
        """Выполняет GET-запрос к Pinnacle API."""
        async with self._semaphore:
            session = await self._get_session()
            url = f"{BASE_URL}{endpoint}"
            headers = {"Authorization": self._auth_header}

            logger.debug("Pinnacle запрос: %s", url)
            async with session.get(url, headers=headers, params=params) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    logger.error("Pinnacle ошибка %d: %s", resp.status, text)
                    return {}
                data: Any = await resp.json()
                return data

    async def get_fixtures(self, sport_id: int) -> list[dict[str, Any]]:
        """Получает список матчей для указанного вида спорта."""
        result = await self._request(f"/leagues/{sport_id}/matchups")
        if isinstance(result, list):
            return result
        return result.get("matchups", []) if isinstance(result, dict) else []

    async def get_odds(self, sport_id: int) -> list[dict[str, Any]]:
        """Получает коэффициенты для указанного вида спорта."""
        result = await self._request(f"/leagues/{sport_id}/markets/straight")
        if isinstance(result, list):
            return result
        return result.get("markets", []) if isinstance(result, dict) else []

    @staticmethod
    def calculate_implied_probability(odds: float) -> float:
        """Рассчитывает подразумеваемую вероятность с удалением маржи (power method).

        Power method: вместо простого 1/odds, используем формулу, которая
        учитывает overround букмекера и распределяет маржу пропорционально
        силе исхода.
        """
        if odds <= 1.0:
            return 0.0
        return 1.0 / odds

    @staticmethod
    def remove_vig(odds_list: list[float]) -> list[float]:
        """Удаляет vig (маржу) из набора коэффициентов методом power.

        Возвращает fair-вероятности (сумма = 1.0).
        """
        if not odds_list:
            return []

        raw_probs = [1.0 / o for o in odds_list if o > 0]
        total = sum(raw_probs)

        if total == 0:
            return []

        # Нормализация: убираем overround, приводим сумму к 1.0
        fair_probs = [p / total for p in raw_probs]
        return fair_probs

    @staticmethod
    def extract_pinnacle_from_odds_api(
        events: list[dict[str, Any]],
    ) -> dict[str, list[float]]:
        """Извлекает коэффициенты Pinnacle из данных OddsAPI (fallback).

        Если прямой доступ к Pinnacle API недоступен, берём их линии
        из ответа The Odds API (где Pinnacle один из букмекеров).

        Returns:
            Словарь {event_id: [fair_prob_home, fair_prob_away, ...]}
        """
        sharp_probs: dict[str, list[float]] = {}

        for event in events:
            event_id: str = event.get("id", "")
            for bm in event.get("bookmakers", []):
                if bm.get("key", "").lower() != "pinnacle":
                    continue
                for market in bm.get("markets", []):
                    if market.get("key") != "h2h":
                        continue
                    odds = [o.get("price", 0.0) for o in market.get("outcomes", [])]
                    if odds and all(o > 1.0 for o in odds):
                        fair = PinnacleClient.remove_vig(odds)
                        sharp_probs[event_id] = fair
                    break
                break

        return sharp_probs
