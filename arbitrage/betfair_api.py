"""Асинхронный клиент к Betfair Exchange API.

Betfair - биржа ставок. Позволяет делать back/lay-ставки,
что открывает возможности для арбитража с обычными букмекерами.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

import aiohttp

from arbitrage import config

logger = logging.getLogger(__name__)

API_URL: str = "https://api.betfair.com/exchange/betting/rest/v1.0/"
KEEP_ALIVE_URL: str = "https://identitysso.betfair.com/api/keepAlive"


class BetfairClient:
    """Клиент для Betfair Exchange API."""

    def __init__(
        self,
        app_key: Optional[str] = None,
        session_token: Optional[str] = None,
        session: Optional[aiohttp.ClientSession] = None,
    ) -> None:
        self._app_key: str = app_key or config.BETFAIR_APP_KEY
        self._session_token: str = session_token or config.BETFAIR_SESSION_TOKEN
        self._session: Optional[aiohttp.ClientSession] = session
        self._owns_session: bool = False

    @property
    def _headers(self) -> dict[str, str]:
        """Стандартные заголовки для Betfair API."""
        return {
            "X-Application": self._app_key,
            "X-Authentication": self._session_token,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

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

    async def _post(self, endpoint: str, payload: dict[str, Any]) -> Any:
        """Выполняет POST-запрос к Betfair API с retry."""
        from arbitrage.retry import retry_request

        session = await self._get_session()
        url = f"{API_URL}{endpoint}"

        logger.debug("Betfair запрос: %s", endpoint)
        resp = await retry_request(session, "POST", url, json=payload, headers=self._headers)
        try:
            if resp.status != 200:
                text = await resp.text()
                logger.error("Betfair ошибка %d: %s", resp.status, text)
                return []
            data: Any = await resp.json()
            return data
        finally:
            resp.release()

    async def login(self) -> bool:
        """Проверяет валидность текущего session_token (keep-alive)."""
        session = await self._get_session()
        headers = {
            "X-Application": self._app_key,
            "X-Authentication": self._session_token,
            "Accept": "application/json",
        }
        async with session.get(KEEP_ALIVE_URL, headers=headers) as resp:
            if resp.status != 200:
                logger.error("Betfair login/keep-alive failed: %d", resp.status)
                return False
            data = await resp.json()
            status = data.get("status", "")
            if status == "SUCCESS":
                self._session_token = data.get("token", self._session_token)
                logger.info("Betfair keep-alive: успешно")
                return True
            logger.error("Betfair keep-alive: %s", data.get("error", "unknown"))
            return False

    async def list_event_types(self) -> list[dict[str, Any]]:
        """Получает список типов событий (спортов)."""
        payload: dict[str, Any] = {"filter": {}}
        result = await self._post("listEventTypes/", payload)
        if not isinstance(result, list):
            return []
        return result

    async def list_market_catalogue(
        self,
        filter_params: Optional[dict[str, Any]] = None,
        max_results: int = 100,
        market_projection: Optional[list[str]] = None,
    ) -> list[dict[str, Any]]:
        """Получает каталог рынков по фильтру.

        Args:
            filter_params: фильтр событий (eventTypeIds, marketTypeCodes и т.д.)
            max_results: максимальное количество результатов
            market_projection: какие данные включить (RUNNER_DESCRIPTION, EVENT и т.д.)
        """
        if filter_params is None:
            filter_params = {}
        if market_projection is None:
            market_projection = ["RUNNER_DESCRIPTION", "EVENT", "COMPETITION"]

        payload: dict[str, Any] = {
            "filter": filter_params,
            "maxResults": max_results,
            "marketProjection": market_projection,
        }
        result = await self._post("listMarketCatalogue/", payload)
        if not isinstance(result, list):
            return []
        return result

    async def list_market_book(
        self,
        market_ids: list[str],
        price_projection: Optional[dict[str, Any]] = None,
    ) -> list[dict[str, Any]]:
        """Получает книгу ставок (текущие back/lay цены) для рынков.

        Args:
            market_ids: список ID рынков
            price_projection: параметры запроса цен
        """
        if price_projection is None:
            price_projection = {
                "priceData": ["EX_BEST_OFFERS"],
                "virtualise": True,
            }

        payload: dict[str, Any] = {
            "marketIds": market_ids,
            "priceProjection": price_projection,
        }
        result = await self._post("listMarketBook/", payload)
        if not isinstance(result, list):
            return []
        return result

    async def place_orders(
        self,
        market_id: str,
        instructions: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Размещает ставки на рынке.

        Args:
            market_id: ID рынка
            instructions: список инструкций (selectionId, side, orderType, limitOrder)
        """
        payload: dict[str, Any] = {
            "marketId": market_id,
            "instructions": instructions,
        }
        result = await self._post("placeOrders/", payload)
        if not isinstance(result, dict):
            return {}
        return result
