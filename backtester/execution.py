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
    EXECUTION_SLIPPAGE_BPS,
    FUNDING_RATE_PER_8H,
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
        """Market-открытие: taker, 1 тик проскальзывания + slippage_bps."""
        side = order["side"]
        qty = float(order["qty"])
        if qty <= 0:
            return None
        slip_ticks = self.config.market_slippage_ticks * float(tick_size or 0.0)
        slip_bps = float(ref_price) * (
            float(self.config.execution_slippage_bps) / 10000.0
        )
        slip = slip_ticks + slip_bps
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
        """Market-закрытие: taker, 1 тик проскальзывания + slippage_bps + funding."""
        slip_ticks = self.config.market_slippage_ticks * float(tick_size or 0.0)
        slip_bps = float(ref_price) * (
            float(self.config.execution_slippage_bps) / 10000.0
        )
        slip = slip_ticks + slip_bps
        # Для LONG закрываемся Sell-ом (цена хуже = ref-slip). Для SHORT -
        # Buy-ом (цена хуже = ref+slip).
        if position.side == "Buy":
            fill_price = float(ref_price) - slip
        else:
            fill_price = float(ref_price) + slip
        funding_cost = self._funding_cost(position, ts)
        # Funding cost списывается ДО закрытия как добавочная fee.
        # close_position сам спишет fee из cash, поэтому мы суммируем
        # taker fee + funding в одну сумму fee.
        fee = position.qty * fill_price * self.config.taker_fee + funding_cost
        trade = portfolio.close_position(
            symbol=position.symbol,
            exit_price=fill_price,
            fee=fee,
            ts=ts,
            reason=reason,
        )
        # Вернём тот же словарь, что и closed_trades, плюс тип для симметрии
        # и компоненты cost для аудита.
        trade = dict(trade)
        trade["type"] = "market_close"
        trade["funding_cost"] = funding_cost
        return trade

    def _funding_cost(self, position: Position, exit_ts: int) -> float:
        """Funding cost за время удержания позиции.

        Bybit V5 списывает funding каждые 8 часов в моменты 00:00 / 08:00 / 16:00 UTC.
        В backtest не имеет смысла моделировать точные моменты — погрешность
        копеечная — поэтому считаем непрерывное накопление: rate_per_8h *
        (hours_held / 8) * notional. Знак всегда отрицательный (см. комментарий
        в config: pessimistic case без учёта sign-flip).

        ts в backtester'е может быть как unix-секундах, так и в ms. Нормализуем
        через эвристику: если значение > 10^11, считаем ms.
        """
        rate_per_8h = float(self.config.funding_rate_per_8h or 0.0)
        if rate_per_8h <= 0:
            return 0.0
        ts_entry = int(position.entry_ts or 0)
        ts_exit = int(exit_ts or 0)
        if ts_exit <= ts_entry:
            return 0.0
        if ts_entry > 10**11:
            elapsed_sec = (ts_exit - ts_entry) / 1000.0
        else:
            elapsed_sec = float(ts_exit - ts_entry)
        hours = max(0.0, elapsed_sec / 3600.0)
        notional = float(position.qty) * float(position.entry_price)
        return notional * rate_per_8h * (hours / 8.0)


# Алиасы комиссий для внешнего использования (тесты/метрики).
__all__ = [
    "ExecutionSimulator",
    "TAKER_FEE",
    "MAKER_FEE",
    "MARKET_SLIPPAGE_TICKS",
    "FUNDING_RATE_PER_8H",
    "EXECUTION_SLIPPAGE_BPS",
]
