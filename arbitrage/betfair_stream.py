"""Заготовка для Betfair Exchange Streaming API.

Для production необходимо:
  - Колокация в дата-центре Betfair (Лондон)
  - Betfair Premium API доступ
  - Реальный WebSocket клиент для stream-api.betfair.com

TODO: Реализовать реальное WebSocket подключение.
"""

from __future__ import annotations

import asyncio
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
