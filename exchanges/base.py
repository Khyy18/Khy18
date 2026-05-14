"""Абстрактный интерфейс биржевого адаптера.

Все методы асинхронные. При сетевых/парс ошибках методы возвращают
None / [] / OrderResult(ok=False) вместо пробрасывания исключений.
Это гарантирует, что торговый цикл не падает от транзиентных сбоев.
"""

from __future__ import annotations

import abc
from typing import Any, Optional


class ExchangeAdapter(abc.ABC):
    """Базовый класс для всех биржевых коннекторов."""

    name: str = ""
    is_testnet: bool = False

    @abc.abstractmethod
    async def get_server_time(self, session: Any) -> Optional[int]:
        """Серверное время в ms. None при ошибке."""

    @abc.abstractmethod
    async def get_balance(self, session: Any, coin: str = "USDT") -> Optional[float]:
        """Баланс по монете. None при ошибке."""

    @abc.abstractmethod
    async def get_klines(
        self, session: Any, symbol: str, interval: str, limit: int = 250
    ) -> list[dict[str, Any]]:
        """Свечи в формате [{ts, open, high, low, close, volume}, ...], старые первыми."""

    @abc.abstractmethod
    async def get_instrument_info(
        self, session: Any, symbol: str
    ) -> Optional[dict[str, float]]:
        """Фильтры инструмента: {min_qty, qty_step, min_notional, tick_size}."""

    @abc.abstractmethod
    async def get_orderbook_top(
        self, session: Any, symbol: str
    ) -> Optional[tuple[float, float]]:
        """(best_bid, best_ask). None при ошибке."""

    @abc.abstractmethod
    async def get_positions(
        self, session: Any, symbol: str
    ) -> list[dict[str, Any]]:
        """Открытые позиции с ненулевым size."""

    @abc.abstractmethod
    async def get_closed_pnl(
        self, session: Any, symbol: str, limit: int = 10
    ) -> list[dict[str, Any]]:
        """Реализованный PnL недавних закрытий."""

    @abc.abstractmethod
    async def get_execution_history(
        self, session: Any, symbol: str, order_id: str, limit: int = 10
    ) -> list[dict[str, Any]]:
        """Список исполнений по order_id."""

    @abc.abstractmethod
    async def place_order_with_fallback(
        self,
        session: Any,
        symbol: str,
        side: str,
        qty: float,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
        reduce_only: bool = False,
        post_only_timeout_sec: Optional[int] = None,
    ) -> Optional[dict[str, Any]]:
        """PostOnly Limit -> IOC Market fallback. Возвращает dict с fill_price/fill_qty или None."""

    @abc.abstractmethod
    async def set_trading_stop(
        self,
        session: Any,
        symbol: str,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
    ) -> Optional[dict[str, Any]]:
        """Обновить SL/TP открытой позиции."""

    @abc.abstractmethod
    async def cancel_order(
        self, session: Any, symbol: str, order_id: str
    ) -> Optional[dict[str, Any]]:
        """Отменить ордер."""

    @abc.abstractmethod
    async def get_open_orders(
        self, session: Any, symbol: str
    ) -> list[dict[str, Any]]:
        """Список активных ордеров."""

    @abc.abstractmethod
    async def panic_sell(
        self, session: Any, symbol: str
    ) -> list[dict[str, Any]]:
        """Аварийное закрытие всех позиций по символу."""

    # FIX: убрали async — метод везде реализован синхронно; объявлять async
    # и реализовывать sync — нарушение контракта ABC и потенциальный баг
    # при любой будущей попытке использовать await на возвращаемом значении.
    @abc.abstractmethod
    def validate_and_round_qty(
        self, qty: float, info: dict[str, float], price: float
    ) -> float:
        """Привести qty к биржевым фильтрам. 0.0 если невалидно."""

    async def get_funding_info(
        self, session: Any, symbol: str
    ) -> Optional[dict[str, Any]]:
        """Информация о funding rate по символу.

        Возвращает dict со схемой:
            {
                "symbol": str,            # биржевой символ как у нас (например BTCUSDT)
                "funding_rate": float,    # текущая ставка за один интервал (доля, не %)
                "next_funding_ts": int,   # ms, время следующего расчёта
                "mark_price": float,      # mark/last для оценки маржи
                "interval_hours": float,  # период между расчётами (8.0 / 4.0 / 1.0)
            }
        Возвращает None при ошибке/отсутствии данных.

        НЕ abstractmethod, чтобы старые адаптеры (без поддержки) не падали;
        реализация по умолчанию - вернуть None, т.е. "биржа не участвует
        в funding-сканере".
        """
        return None
