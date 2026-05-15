"""Асинхронный клиент к Betfair Exchange API.

Betfair - биржа ставок. Позволяет делать back/lay-ставки,
что открывает возможности для арбитража с обычными букмекерами.

Поддерживает:
  - Аутентификация через session token (keep-alive)
  - Аутентификация через сертификат (certlogin)
  - Получение типов событий, событий, каталога рынков, книги ставок
  - Размещение / отмена ордеров
  - Получение текущих ордеров
"""

from __future__ import annotations

import logging
from typing import Any, Optional

import aiohttp

from arbitrage import config

logger = logging.getLogger(__name__)

API_URL: str = "https://api.betfair.com/exchange/betting/rest/v1.0/"
KEEP_ALIVE_URL: str = "https://identitysso.betfair.com/api/keepAlive"
CERTLOGIN_URL: str = "https://identitysso-cert.betfair.com/api/certlogin"


class BetfairAPIError(Exception):
    """Ошибка при взаимодействии с Betfair API."""

    def __init__(self, message: str, status_code: int = 0, detail: str = "") -> None:
        self.status_code = status_code
        self.detail = detail
        super().__init__(message)


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
        """Возвращает (или создает) aiohttp-сессию."""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
            self._owns_session = True
        return self._session

    async def close(self) -> None:
        """Закрывает сессию, если она создана клиентом."""
        if self._owns_session and self._session and not self._session.closed:
            await self._session.close()

    async def _post(self, endpoint: str, payload: dict[str, Any]) -> Any:
        """Выполняет POST-запрос к Betfair API с retry.

        Raises:
            BetfairAPIError: при ошибках HTTP или API.
        """
        from arbitrage.retry import retry_request

        session = await self._get_session()
        url = f"{API_URL}{endpoint}"

        logger.debug("Betfair запрос: %s", endpoint)
        resp = await retry_request(session, "POST", url, json=payload, headers=self._headers)
        try:
            if resp.status != 200:
                text = await resp.text()
                logger.error("Betfair ошибка %d: %s", resp.status, text)
                raise BetfairAPIError(
                    f"Betfair API ошибка: {resp.status}",
                    status_code=resp.status,
                    detail=text,
                )
            data: Any = await resp.json()
            # Betfair может вернуть словарь с ошибкой вместо списка
            if isinstance(data, dict) and "faultcode" in data:
                fault = data.get("faultstring", "unknown fault")
                logger.error("Betfair fault: %s", fault)
                raise BetfairAPIError(
                    f"Betfair fault: {fault}",
                    detail=str(data),
                )
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
        try:
            async with session.get(KEEP_ALIVE_URL, headers=headers) as resp:
                if resp.status != 200:
                    logger.error("Betfair login/keep-alive failed: %d", resp.status)
                    raise BetfairAPIError(
                        "Keep-alive failed",
                        status_code=resp.status,
                    )
                data = await resp.json()
                status = data.get("status", "")
                if status == "SUCCESS":
                    self._session_token = data.get("token", self._session_token)
                    logger.info("Betfair keep-alive: успешно")
                    return True
                error_msg = data.get("error", "unknown")
                logger.error("Betfair keep-alive: %s", error_msg)
                raise BetfairAPIError(
                    f"Keep-alive error: {error_msg}",
                    detail=str(data),
                )
        except aiohttp.ClientError as exc:
            logger.error("Betfair keep-alive network error: %s", exc)
            raise BetfairAPIError(f"Network error: {exc}") from exc

    async def login_cert(
        self,
        username: str,
        password: str,
        cert_path: str,
        key_path: str,
    ) -> bool:
        """Аутентификация через сертификат (certlogin).

        Args:
            username: логин Betfair
            password: пароль Betfair
            cert_path: путь к файлу сертификата (.crt / .pem)
            key_path: путь к файлу приватного ключа (.key)

        Returns:
            True если аутентификация успешна.

        Raises:
            BetfairAPIError: при ошибке аутентификации.
        """
        import ssl

        ssl_ctx = ssl.create_default_context()
        ssl_ctx.load_cert_chain(certfile=cert_path, keyfile=key_path)

        headers = {
            "X-Application": self._app_key,
            "Content-Type": "application/x-www-form-urlencoded",
        }
        payload = f"username={username}&password={password}"

        session = await self._get_session()
        try:
            async with session.post(
                CERTLOGIN_URL,
                data=payload,
                headers=headers,
                ssl=ssl_ctx,
            ) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    logger.error("Betfair certlogin HTTP %d: %s", resp.status, text)
                    raise BetfairAPIError(
                        f"Certlogin HTTP error: {resp.status}",
                        status_code=resp.status,
                        detail=text,
                    )
                data = await resp.json()
                login_status = data.get("loginStatus", "")
                if login_status == "SUCCESS":
                    self._session_token = data.get("sessionToken", "")
                    logger.info("Betfair certlogin: успешно")
                    return True
                logger.error("Betfair certlogin: %s", login_status)
                raise BetfairAPIError(
                    f"Certlogin failed: {login_status}",
                    detail=str(data),
                )
        except aiohttp.ClientError as exc:
            logger.error("Betfair certlogin network error: %s", exc)
            raise BetfairAPIError(f"Network error: {exc}") from exc

    async def list_event_types(self) -> list[dict[str, Any]]:
        """Получает список типов событий (спортов).

        Raises:
            BetfairAPIError: при ошибке API.
        """
        payload: dict[str, Any] = {"filter": {}}
        result = await self._post("listEventTypes/", payload)
        if not isinstance(result, list):
            return []
        return result

    async def list_events(
        self,
        filter_params: Optional[dict[str, Any]] = None,
    ) -> list[dict[str, Any]]:
        """Получает список событий по фильтру.

        Args:
            filter_params: фильтр (eventTypeIds, competitionIds и т.д.)

        Returns:
            Список событий.

        Raises:
            BetfairAPIError: при ошибке API.
        """
        if filter_params is None:
            filter_params = {}
        payload: dict[str, Any] = {"filter": filter_params}
        result = await self._post("listEvents/", payload)
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

        Raises:
            BetfairAPIError: при ошибке API.
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

        Raises:
            BetfairAPIError: при ошибке API.
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

        Returns:
            Ответ API с полями status, instructionReports и т.д.

        Raises:
            BetfairAPIError: при ошибке API.
        """
        payload: dict[str, Any] = {
            "marketId": market_id,
            "instructions": instructions,
        }
        result = await self._post("placeOrders/", payload)
        if not isinstance(result, dict):
            return {}
        return result

    async def cancel_orders(
        self,
        market_id: str,
        bet_ids: Optional[list[str]] = None,
    ) -> dict[str, Any]:
        """Отменяет ордера на рынке.

        Args:
            market_id: ID рынка
            bet_ids: список ID ставок для отмены (None = отменить все на рынке)

        Returns:
            Ответ API с результатами отмены.

        Raises:
            BetfairAPIError: при ошибке API.
        """
        payload: dict[str, Any] = {"marketId": market_id}
        if bet_ids:
            payload["instructions"] = [
                {"betId": bet_id} for bet_id in bet_ids
            ]
        result = await self._post("cancelOrders/", payload)
        if not isinstance(result, dict):
            return {}
        return result

    async def list_current_orders(
        self,
        order_by: str = "BY_BET",
        from_record: int = 0,
        record_count: int = 100,
    ) -> dict[str, Any]:
        """Получает текущие (открытые) ордера.

        Args:
            order_by: порядок сортировки (BY_BET, BY_MARKET, BY_MATCH_TIME)
            from_record: начальная запись (для пагинации)
            record_count: количество записей

        Returns:
            Ответ API с полями currentOrders, moreAvailable.

        Raises:
            BetfairAPIError: при ошибке API.
        """
        payload: dict[str, Any] = {
            "orderBy": order_by,
            "fromRecord": from_record,
            "recordCount": record_count,
        }
        result = await self._post("listCurrentOrders/", payload)
        if not isinstance(result, dict):
            return {}
        return result
