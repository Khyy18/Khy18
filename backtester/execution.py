"""Симуляция исполнения ордеров под правилами Bybit V5 linear-perp.

  - Market/IOC: taker fee, 1 тик проскальзывания в сторону убытка.
  - PostOnly limit: maker fee; если уровень при постановке уже пересекает
    противоположную сторону бара, ордер отменяется (skip-on-cross). Иначе
    фиксируется факт постановки и ожидается касание лимита следующими барами.

Симулятор - чистый враппер над `Portfolio`: никакого скрытого состояния,
вся информация приходит в аргументах.
"""

from __future__ import annotations

from typing import Optional

from backtester.config import (
    BacktesterConfig,
    MAKER_FEE,
    MARKET_SLIPPAGE_TICKS,
    TAKER_FEE,
)
from backtester.portfolio import Portfolio, Position


class ExecutionSimulator:
    """Бесфреймовый помощник: принимает ссылку на портфель и ордер,
    возвращает dict-описание филла (или None) и изменяет портфель."""

    def __init__(self, config: Optional[BacktesterConfig] = None) -> None:
        self.config = config or BacktesterConfig()

    # ---------- ОТКРЫТИЕ ----------

    def fill_market_open(
        self,
        portfolio: Portfolio,
        order: dict,
        ref_price: float,
        tick_size: float,
        ts: int,
    ) -> Optional[dict]:
        """Market-открытие: taker, 1 тик проскальзывания в «плохую» сторону."""
        side = order["side"]
        qty = float(order["qty"])
        if qty <= 0:
            return None
        slip = self.config.market_slippage_ticks * float(tick_size or 0.0)
        if side == "Buy":
            fill_price = float(ref_price) + slip
        else:
            fill_price = float(ref_price) - slip
        fee = qty * fill_price * self.config.taker_fee
        portfolio.open_position(
            symbol=order["symbol"],
            side=side,
            qty=qty,
            entry_price=fill_price,
            fee=fee,
            ts=ts,
            hard_stop=float(order["hard_stop"]),
            atr_at_entry=float(order.get("meta", {}).get("indicators", {}).get("atr_1h", 0.0)),
            meta=order.get("meta"),
        )
        return {
            "symbol": order["symbol"],
            "side": side,
            "qty": qty,
            "fill_price": fill_price,
            "fee": fee,
            "ts": int(ts),
            "type": "market_open",
            "meta": order.get("meta"),
        }

    def fill_limit_postonly_open(
        self,
        portfolio: Portfolio,
        order: dict,
        next_bar: dict,
        tick_size: float,
        ts: int,
    ) -> Optional[dict]:
        """PostOnly-лимит: делаем заявку на close текущего часа, пробуем
        поймать её на следующем 1h-баре.

          - skip-on-cross: если лимит сразу «заезжает за» противоположный
            экстремум следующего бара, отменяем (без филла).
          - фикс, если следующий бар коснулся лимита: Buy при low<=limit,
            Sell при high>=limit. Цена = limit_price (maker).
        """
        side = order["side"]
        qty = float(order["qty"])
        if qty <= 0:
            return None
        limit_price = float(order["limit_price"])
        _ = tick_size  # в этой модели tick_size нужен только для market

        bar_high = float(next_bar["high"])
        bar_low = float(next_bar["low"])

        # skip-on-cross: PostOnly отменяется, если сразу пересекает книгу.
        if side == "Buy" and limit_price >= bar_high:
            return None
        if side == "Sell" and limit_price <= bar_low:
            return None

        # Касается ли следующий бар лимитного уровня?
        hit = (side == "Buy" and bar_low <= limit_price) or (
            side == "Sell" and bar_high >= limit_price
        )
        if not hit:
            return None

        fill_price = limit_price
        fee = qty * fill_price * self.config.maker_fee
        portfolio.open_position(
            symbol=order["symbol"],
            side=side,
            qty=qty,
            entry_price=fill_price,
            fee=fee,
            ts=ts,
            hard_stop=float(order["hard_stop"]),
            atr_at_entry=float(order.get("meta", {}).get("indicators", {}).get("atr_1h", 0.0)),
            meta=order.get("meta"),
        )
        return {
            "symbol": order["symbol"],
            "side": side,
            "qty": qty,
            "fill_price": fill_price,
            "fee": fee,
            "ts": int(ts),
            "type": "limit_postonly_open",
            "meta": order.get("meta"),
        }

    # ---------- ЗАКРЫТИЕ ----------

    def fill_market_close(
        self,
        portfolio: Portfolio,
        position: Position,
        ref_price: float,
        tick_size: float,
        ts: int,
        reason: str,
    ) -> dict:
        """Market-закрытие: taker, 1 тик проскальзывания в «плохую» сторону."""
        slip = self.config.market_slippage_ticks * float(tick_size or 0.0)
        # Для LONG закрываемся Sell-ом (цена хуже = ref-slip). Для SHORT -
        # Buy-ом (цена хуже = ref+slip).
        if position.side == "Buy":
            fill_price = float(ref_price) - slip
        else:
            fill_price = float(ref_price) + slip
        fee = position.qty * fill_price * self.config.taker_fee
        trade = portfolio.close_position(
            symbol=position.symbol,
            exit_price=fill_price,
            fee=fee,
            ts=ts,
            reason=reason,
        )
        # Вернём тот же словарь, что и closed_trades, плюс тип для симметрии.
        trade = dict(trade)
        trade["type"] = "market_close"
        return trade


# Алиасы комиссий для внешнего использования (тесты/метрики).
__all__ = [
    "ExecutionSimulator",
    "TAKER_FEE",
    "MAKER_FEE",
    "MARKET_SLIPPAGE_TICKS",
]
