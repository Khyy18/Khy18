"""Заготовка для Betfair Exchange Streaming API.

Для production необходимо:
  - Колокация в дата-центре Betfair (Лондон)
  - Betfair Premium API доступ
  - Реальный WebSocket клиент для stream-api.betfair.com

TODO: Реализовать реальное WebSocket подключение.
"""

from __future__ import annotations

from typing import Any, Callable, Optional

from arbitrage import config


class BetfairStreamClient:
    """WebSocket-клиент для Betfair Streaming API (заготовка)."""

    def __init__(
        self,
        app_key: Optional[str] = None,
        session_token: Optional[str] = None,
    ) -> None:
        self._app_key: str = app_key or config.BETFAIR_APP_KEY
        self._session_token: str = session_token or config.BETFAIR_SESSION_TOKEN
        self._subscriptions: dict[str, Callable[[dict[str, Any]], None]] = {}
        self._connected: bool = False
        self._price_callback: Optional[Callable[[dict[str, Any]], None]] = None

    async def connect(self) -> None:
        """Подключиться к Betfair Streaming API. TODO: реальная реализация."""
        # TODO: WebSocket подключение к stream-api.betfair.com:443
        print("[BETFAIR_STREAM] connect() - заглушка, реальное подключение не реализовано")
        self._connected = True

    async def disconnect(self) -> None:
        """Отключиться от потока."""
        self._connected = False
        self._subscriptions.clear()
        print("[BETFAIR_STREAM] disconnect()")

    async def subscribe_market(self, market_id: str) -> None:
        """Подписаться на обновления рынка. TODO: реальная подписка."""
        # TODO: Отправить marketSubscription message через WebSocket
        print(f"[BETFAIR_STREAM] subscribe_market({market_id}) - заглушка")

    def on_price_change(self, callback: Callable[[dict[str, Any]], None]) -> None:
        """Зарегистрировать callback для обновления цен."""
        self._price_callback = callback
        print("[BETFAIR_STREAM] on_price_change callback зарегистрирован")
