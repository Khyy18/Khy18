"""Адаптер Bybit V5 (обёртка над api_engine.py).

Это промежуточная реализация: api_engine.py остаётся рабочим модулем,
а BybitAdapter делегирует ему вызовы, нормализуя возвраты.
В будущем логика может быть перенесена полностью в этот файл.
"""

from __future__ import annotations

from typing import Any, Optional

import api_engine
import config
from .base import ExchangeAdapter


class BybitAdapter(ExchangeAdapter):
    """Bybit V5 Unified Trading Account (линейные перпетуалы)."""

    name = "bybit"

    def __init__(self, **kwargs: Any) -> None:
        self.is_testnet = config.IS_TESTNET

    async def get_server_time(self, session: Any) -> Optional[int]:
        resp = await api_engine.get_server_time(session)
        if resp and resp.get("retCode") == 0:
            try:
                return int((resp.get("result") or {}).get("timeNano", 0)) // 1_000_000
            except (TypeError, ValueError):
                return None
        return None

    async def get_balance(self, session: Any, coin: str = "USDT") -> Optional[float]:
        return await api_engine.get_balance(session, coin)

    async def get_klines(
        self, session: Any, symbol: str, interval: str, limit: int = 250
    ) -> list[dict[str, Any]]:
        raw = await api_engine.get_klines(session, symbol, interval, limit)
        # api_engine уже возвращает reversed (старые первыми), формат list[list[str]].
        result: list[dict[str, Any]] = []
        for k in raw:
            try:
                result.append({
                    "ts": int(k[0]),
                    "open": float(k[1]),
                    "high": float(k[2]),
                    "low": float(k[3]),
                    "close": float(k[4]),
                    "volume": float(k[5]),
                })
            except (IndexError, TypeError, ValueError):
                continue
        return result

    async def get_instrument_info(
        self, session: Any, symbol: str
    ) -> Optional[dict[str, float]]:
        return await api_engine.instrument_info_cached(session, symbol)

    async def get_orderbook_top(
        self, session: Any, symbol: str
    ) -> Optional[tuple[float, float]]:
        return await api_engine.get_orderbook_top(session, symbol)

    async def get_positions(
        self, session: Any, symbol: str
    ) -> list[dict[str, Any]]:
        return await api_engine.get_positions(session, symbol)

    async def get_closed_pnl(
        self, session: Any, symbol: str, limit: int = 10
    ) -> list[dict[str, Any]]:
        return await api_engine.get_closed_pnl(session, symbol, limit)

    async def get_execution_history(
        self, session: Any, symbol: str, order_id: str, limit: int = 10
    ) -> list[dict[str, Any]]:
        return await api_engine.get_execution_history(session, symbol, order_id, limit)

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
        # Maker-only mode: только для open-сделок (reduce_only=False).
        # Для close используем стандартный fallback - закрытие должно уйти
        # быстро, иначе margin guard / time-stop сработают.
        if (
            getattr(config, "ARB_MAKER_ONLY_ENABLED", False)
            and not reduce_only
        ):
            return await api_engine.place_maker_only_with_repeg(
                session,
                symbol=symbol,
                side=side,
                qty=qty,
                stop_loss=stop_loss,
                take_profit=take_profit,
                reduce_only=reduce_only,
            )
        # FIX: передаём post_only_timeout_sec в api_engine, чтобы
        # каждый вызов мог переопределить глобальный POST_ONLY_TIMEOUT_SEC.
        return await api_engine.place_order_with_fallback(
            session,
            symbol=symbol,
            side=side,
            qty=qty,
            stop_loss=stop_loss,
            take_profit=take_profit,
            reduce_only=reduce_only,
            post_only_timeout_sec=post_only_timeout_sec,
        )

    async def set_trading_stop(
        self,
        session: Any,
        symbol: str,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
    ) -> Optional[dict[str, Any]]:
        return await api_engine.set_trading_stop(session, symbol, stop_loss, take_profit)

    async def cancel_order(
        self, session: Any, symbol: str, order_id: str
    ) -> Optional[dict[str, Any]]:
        return await api_engine.cancel_order(session, symbol, order_id)

    async def get_open_orders(
        self, session: Any, symbol: str
    ) -> list[dict[str, Any]]:
        return await api_engine.get_open_orders(session, symbol)

    async def panic_sell(
        self, session: Any, symbol: str
    ) -> list[dict[str, Any]]:
        return await api_engine.panic_sell(session, symbol)

    def validate_and_round_qty(
        self, qty: float, info: dict[str, float], price: float
    ) -> float:
        return api_engine.validate_and_round_qty(qty, info, price)

    async def get_funding_info(
        self, session: Any, symbol: str
    ) -> Optional[dict[str, Any]]:
        """Funding rate из публичного /v5/market/tickers (linear).

        Bybit отдаёт `fundingRate` (текущее значение), `nextFundingTime` (ms,
        UTC) и `markPrice` в одном запросе. Интервал у Bybit для большинства
        перпов 8ч; вычислять его из (next - prev) нельзя, потому что prev в
        ответе нет. Берём фиксированно 8 - это правильно для всех ликвидных
        BTC/ETH/SOL/...USDT на Bybit. Если позже обнаружим часовые перпы -
        зашьём через override-словарь.
        """
        params = {"category": "linear", "symbol": symbol}
        resp = await api_engine._request(
            session, "GET", "/v5/market/tickers", params=params, auth=False
        )
        if not resp or resp.get("retCode") != 0:
            if resp:
                print(f"[BYBIT] get_funding_info({symbol}): {resp.get('retMsg')}")
            return None
        items = ((resp.get("result") or {}).get("list") or [])
        if not items:
            return None
        item = items[0]
        try:
            funding_rate = float(item.get("fundingRate") or 0.0)
            next_ts = int(item.get("nextFundingTime") or 0)
            mark = float(item.get("markPrice") or item.get("lastPrice") or 0.0)
        except (TypeError, ValueError) as exc:
            print(f"[BYBIT] get_funding_info({symbol}): парс {exc}")
            return None
        if mark <= 0:
            return None
        return {
            "symbol": symbol,
            "funding_rate": funding_rate,
            "next_funding_ts": next_ts,
            "mark_price": mark,
            "interval_hours": 8.0,
        }


    async def get_funding_history(
        self,
        session: Any,
        symbol: str,
        since_ms: Optional[int] = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Реальные funding-выплаты по символу с Bybit (delegate в api_engine)."""
        return await api_engine.get_funding_history(
            session, symbol, since_ms=since_ms, limit=limit,
        )
