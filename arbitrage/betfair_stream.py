"""Betfair Exchange Streaming API клиент.

WebSocket-клиент для получения обновлений цен в реальном времени
через stream-api.betfair.com. Поддерживает:
  - Аутентификацию через appKey и session token
  - Подписку на рынки (marketSubscription)
  - Обработку MCM (market change messages)
  - Автоматическое переподключение с экспоненциальным backoff
  - Heartbeat / clk tracking для reconnection
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from typing import Any, Callable, Optional

import aiohttp

from arbitrage import config

# Импорт ai_router из корневого проекта
_parent = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _parent not in sys.path:
    sys.path.insert(0, _parent)
try:
    import ai_router
except ImportError:
    ai_router = None  # type: ignore

logger = logging.getLogger(__name__)

STREAM_URL: str = "wss://stream-api.betfair.com/stream"
RECONNECT_BASE_DELAY: float = 1.0
RECONNECT_MAX_DELAY: float = 30.0
HEARTBEAT_TIMEOUT: float = 60.0


class BetfairStreamClient:
    """WebSocket-клиент для Betfair Streaming API."""

    def __init__(
        self,
        app_key: Optional[str] = None,
        session_token: Optional[str] = None,
    ) -> None:
        self._app_key: str = app_key or config.BETFAIR_APP_KEY
        self._session_token: str = session_token or config.BETFAIR_SESSION_TOKEN
        self._ws: Optional[aiohttp.ClientWebSocketResponse] = None
        self._http_session: Optional[aiohttp.ClientSession] = None
        self._connected: bool = False
        self._running: bool = False
        self._connection_id: Optional[str] = None
        self._clk: Optional[str] = None
        self._initial_clk: Optional[str] = None
        self._subscription_id: int = 0
        self._subscribed_markets: list[str] = []
        self._price_callback: Optional[Callable[[dict[str, Any]], None]] = None
        self._reconnect_attempts: int = 0
        self._last_heartbeat: float = 0.0
        self._listen_task: Optional[asyncio.Task[None]] = None

    @property
    def connected(self) -> bool:
        """Флаг подключения."""
        return self._connected

    async def connect(self) -> None:
        """Подключиться к Betfair Streaming API и аутентифицироваться."""
        if self._http_session is None or self._http_session.closed:
            self._http_session = aiohttp.ClientSession()

        try:
            self._ws = await self._http_session.ws_connect(STREAM_URL)
            self._connected = True
            self._running = True
            self._reconnect_attempts = 0
            logger.info("Betfair Stream: WebSocket подключен к %s", STREAM_URL)

            # Ждем connection message
            msg = await self._ws.receive(timeout=10.0)
            if msg.type == aiohttp.WSMsgType.TEXT:
                data = json.loads(msg.data)
                self._handle_message(data)

            # Отправляем authentication
            await self._authenticate()

            # Запускаем фоновый listener
            self._listen_task = asyncio.create_task(self._listen_loop())

        except Exception as exc:
            logger.error("Betfair Stream: ошибка подключения: %s", exc)
            self._connected = False
            raise

    async def disconnect(self) -> None:
        """Отключиться от потока."""
        self._running = False
        self._connected = False

        if self._listen_task and not self._listen_task.done():
            self._listen_task.cancel()
            try:
                await self._listen_task
            except asyncio.CancelledError:
                pass

        if self._ws and not self._ws.closed:
            await self._ws.close()

        if self._http_session and not self._http_session.closed:
            await self._http_session.close()

        self._subscribed_markets.clear()
        logger.info("Betfair Stream: отключен")

    async def _authenticate(self) -> None:
        """Отправить сообщение аутентификации.

        WARNING: The session token is sent over TLS (wss://) which provides
        transit encryption. However, certificate pinning is NOT implemented.
        In corporate/VPS environments with MITM proxies, the token could
        potentially be intercepted. Consider implementing certificate pinning
        for production deployments in untrusted network environments.
        """
        if not self._ws or self._ws.closed:
            return

        auth_msg = {
            "op": "authentication",
            "appKey": self._app_key,
            "session": self._session_token,
        }
        await self._ws.send_json(auth_msg)
        logger.debug("Betfair Stream: отправлена аутентификация")

        # Ждем ответ status
        msg = await self._ws.receive(timeout=10.0)
        if msg.type == aiohttp.WSMsgType.TEXT:
            data = json.loads(msg.data)
            self._handle_message(data)
            if data.get("op") == "status" and data.get("statusCode") != "SUCCESS":
                error_msg = data.get("errorMessage", "unknown")
                logger.error("Betfair Stream: аутентификация неудачна: %s", error_msg)
                raise ConnectionError(f"Auth failed: {error_msg}")

    async def subscribe_market(self, market_id: str) -> None:
        """Подписаться на обновления рынка.

        Args:
            market_id: ID рынка Betfair (например '1.234567890')
        """
        if not self._ws or self._ws.closed:
            logger.warning("Betfair Stream: невозможно подписаться - нет соединения")
            return

        self._subscription_id += 1
        sub_msg: dict[str, Any] = {
            "op": "marketSubscription",
            "id": self._subscription_id,
            "marketFilter": {"marketIds": [market_id]},
            "marketDataFilter": {"fields": ["EX_BEST_OFFERS"]},
        }

        # Если есть clk от предыдущей сессии, используем для reconnection
        if self._clk:
            sub_msg["clk"] = self._clk
        if self._initial_clk:
            sub_msg["initialClk"] = self._initial_clk

        await self._ws.send_json(sub_msg)

        if market_id not in self._subscribed_markets:
            self._subscribed_markets.append(market_id)

        logger.info("Betfair Stream: подписка на рынок %s (id=%d)", market_id, self._subscription_id)

    def on_price_change(self, callback: Callable[[dict[str, Any]], None]) -> None:
        """Зарегистрировать callback для обновления цен.

        Callback вызывается с dict содержащим:
          market_id, runners (list of {selectionId, back_prices, lay_prices})
        """
        self._price_callback = callback
        logger.debug("Betfair Stream: on_price_change callback зарегистрирован")

    async def _listen_loop(self) -> None:
        """Фоновый цикл приема сообщений от WebSocket."""
        import time

        self._last_heartbeat = time.time()

        while self._running and self._ws and not self._ws.closed:
            try:
                msg = await asyncio.wait_for(
                    self._ws.receive(),
                    timeout=HEARTBEAT_TIMEOUT,
                )

                if msg.type == aiohttp.WSMsgType.TEXT:
                    self._last_heartbeat = time.time()
                    data = json.loads(msg.data)
                    self._handle_message(data)

                elif msg.type == aiohttp.WSMsgType.CLOSED:
                    logger.warning("Betfair Stream: WebSocket закрыт сервером")
                    break

                elif msg.type == aiohttp.WSMsgType.ERROR:
                    logger.error("Betfair Stream: ошибка WebSocket: %s", self._ws.exception())
                    break

            except asyncio.TimeoutError:
                logger.warning("Betfair Stream: heartbeat timeout, переподключение...")
                break
            except asyncio.CancelledError:
                return
            except Exception as exc:
                logger.error("Betfair Stream: ошибка в listen_loop: %s", exc)
                break

        # Если цикл завершился и мы должны работать - переподключаемся
        if self._running:
            self._connected = False
            await self._reconnect()

    def _handle_message(self, data: dict[str, Any]) -> None:
        """Обработать входящее сообщение.

        Типы сообщений:
          - connection: сохраняем connectionId
          - status: проверяем statusCode
          - mcm (market change message): извлекаем данные цен
        """
        op = data.get("op", "")

        if op == "connection":
            self._connection_id = data.get("connectionId")
            logger.info("Betfair Stream: connection id=%s", self._connection_id)

        elif op == "status":
            status_code = data.get("statusCode", "")
            if status_code != "SUCCESS" and data.get("id"):
                logger.warning("Betfair Stream: status %s: %s",
                               status_code, data.get("errorMessage", ""))

        elif op == "mcm":
            # Обновляем clk для reconnection
            if "clk" in data:
                self._clk = data["clk"]
            if "initialClk" in data:
                self._initial_clk = data["initialClk"]

            # Извлекаем данные рынков
            market_changes = data.get("mc", [])
            for mc in market_changes:
                market_id = mc.get("id", "")
                runners = mc.get("rc", [])
                if runners and self._price_callback:
                    parsed_runners: list[dict[str, Any]] = []
                    for runner in runners:
                        selection_id = runner.get("id")
                        # atb = available to back, atl = available to lay
                        back_prices = runner.get("atb", [])
                        lay_prices = runner.get("atl", [])
                        parsed_runners.append({
                            "selectionId": selection_id,
                            "back_prices": back_prices,
                            "lay_prices": lay_prices,
                        })
                    self._price_callback({
                        "market_id": market_id,
                        "runners": parsed_runners,
                    })

    async def _reconnect(self) -> None:
        """Переподключиться с экспоненциальным backoff."""
        while self._running:
            delay = min(
                RECONNECT_BASE_DELAY * (2 ** self._reconnect_attempts),
                RECONNECT_MAX_DELAY,
            )
            self._reconnect_attempts += 1
            logger.info(
                "Betfair Stream: переподключение через %.1f сек (попытка %d)",
                delay, self._reconnect_attempts,
            )
            await asyncio.sleep(delay)

            try:
                # Закрываем старые ресурсы
                if self._ws and not self._ws.closed:
                    await self._ws.close()
                try:
                    if self._http_session and not self._http_session.closed:
                        await self._http_session.close()
                except Exception as close_exc:
                    logger.warning(
                        "Betfair Stream: ошибка при закрытии старой сессии: %s", close_exc
                    )

                self._http_session = aiohttp.ClientSession()
                self._ws = await self._http_session.ws_connect(STREAM_URL)
                self._connected = True
                self._reconnect_attempts = 0

                # Ждем connection message
                msg = await self._ws.receive(timeout=10.0)
                if msg.type == aiohttp.WSMsgType.TEXT:
                    data = json.loads(msg.data)
                    self._handle_message(data)

                # Re-authenticate
                await self._authenticate()

                # Re-subscribe to markets
                for market_id in self._subscribed_markets:
                    await self.subscribe_market(market_id)

                # Restart listen loop
                self._listen_task = asyncio.create_task(self._listen_loop())
                logger.info("Betfair Stream: переподключение успешно")
                return

            except Exception as exc:
                logger.error("Betfair Stream: ошибка переподключения: %s", exc)
                self._connected = False
                continue


class MarketMaker:
    """Стратегия маркет-мейкинга на Betfair Exchange (только DRY RUN)."""

    async def analyze_spread(
        self,
        session: aiohttp.ClientSession,
        back_price: float,
        lay_price: float,
        volume: float,
        event_name: str,
    ) -> dict[str, Any]:
        """Проанализировать спред и рекомендовать позиции.

        Всегда работает в DRY_RUN режиме (только логирование, без реальных ордеров).

        Args:
            session: aiohttp сессия.
            back_price: текущая цена back.
            lay_price: текущая цена lay.
            volume: объем торгов на рынке.
            event_name: название события.

        Returns:
            dict с ключами: recommended_back, recommended_lay,
                           stake_back, stake_lay, confidence, dry_run.
        """
        default: dict[str, Any] = {
            "recommended_back": back_price,
            "recommended_lay": lay_price,
            "stake_back": 0.0,
            "stake_lay": 0.0,
            "confidence": 0,
            "dry_run": True,
        }

        if ai_router is None:
            logger.debug("ai_router недоступен, MarketMaker возвращает default")
            return default

        spread = lay_price - back_price
        spread_pct = (spread / back_price * 100.0) if back_price > 0 else 0.0

        prompt = (
            "Ты - эксперт по маркет-мейкингу на биржевых ставках. "
            "Проанализируй текущий спред и рекомендуй оптимальные позиции.\n\n"
            f"Событие: {event_name}\n"
            f"Back цена: {back_price}\n"
            f"Lay цена: {lay_price}\n"
            f"Спред: {spread:.3f} ({spread_pct:.2f}%)\n"
            f"Объем: {volume:.0f}\n\n"
            "Рекомендуй back и lay цены внутри спреда для получения прибыли.\n"
            "Учитывай: комиссия биржи ~2-5%, ликвидность, волатильность.\n\n"
            "Ответь строго в формате JSON:\n"
            '{"recommended_back": <цена back>, '
            '"recommended_lay": <цена lay>, '
            '"stake_back": <размер ставки back>, '
            '"stake_lay": <размер ставки lay>, '
            '"confidence": <0-100>}'
        )

        try:
            resp = await ai_router.call_llm_json(
                session,
                prompt,
                max_output_tokens=256,
                temperature=0.2,
                timeout=25,
            )
        except Exception as exc:
            logger.warning("Ошибка LLM в MarketMaker: %s", exc)
            return default

        if resp is None:
            return default

        recommended_back = float(resp.get("recommended_back", back_price))
        recommended_lay = float(resp.get("recommended_lay", lay_price))
        stake_back = float(resp.get("stake_back", 0.0))
        stake_lay = float(resp.get("stake_lay", 0.0))
        confidence = int(resp.get("confidence", 0))
        confidence = max(0, min(100, confidence))

        result: dict[str, Any] = {
            "recommended_back": recommended_back,
            "recommended_lay": recommended_lay,
            "stake_back": stake_back,
            "stake_lay": stake_lay,
            "confidence": confidence,
            "dry_run": True,
        }
        logger.info(
            "MarketMaker DRY RUN: %s back=%.2f lay=%.2f conf=%d",
            event_name, recommended_back, recommended_lay, confidence,
        )
        return result


async def market_maker_loop(state: dict[str, Any], session: aiohttp.ClientSession) -> None:
    """Фоновый цикл маркет-мейкера (каждый час, только логирование).

    Placeholder - логирует статус, реальные ордера не размещаются.
    """
    interval = 3600  # 1 час

    while True:
        try:
            logger.info("MarketMaker: DRY RUN mode, no real orders")
        except Exception as exc:
            logger.error("market_maker_loop ошибка: %s", exc)

        await asyncio.sleep(interval)
