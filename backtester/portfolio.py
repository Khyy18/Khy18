"""Учёт портфеля бэктестера (multi-symbol, cross-margin приближение).

Семантика (самая простая корректная):
  - При открытии позиции только списываем комиссию из cash. Номинал
    (entry_price * qty) не списываем - считаем позицию маржируемой с
    нулевым использованием cash (грубая, но рабочая модель Bybit cross).
  - Equity на любом баре = cash + sum(нереализованный PnL по открытым позициям).
  - При закрытии: cash += realized_pnl - closing_fee. Запись идёт в closed_trades.

PnL:
  - LONG:  unrealized = (price - entry) * qty
  - SHORT: unrealized = (entry - price) * qty
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from backtester.config import BacktesterConfig


@dataclass
class Position:
    symbol: str
    side: str  # 'Buy' (LONG) или 'Sell' (SHORT) в терминологии Bybit V5.
    qty: float
    entry_price: float
    entry_ts: int  # миллисекунды epoch
    hard_stop: float
    atr_at_entry: float
    high_since_entry: float
    low_since_entry: float
    meta: dict = field(default_factory=dict)


class Portfolio:
    """Cross-margin приближение под Bybit linear-perpetual."""

    def __init__(self, initial_equity: float, config: BacktesterConfig) -> None:
        self.config = config
        self.initial_equity = float(initial_equity)
        self.cash: float = float(initial_equity)
        self.equity_curve: List[Tuple[int, float]] = []
        self.positions: Dict[str, Position] = {}
        self.closed_trades: List[dict] = []
        self.hwm: float = float(initial_equity)
        self.in_position_bars: int = 0

    # ---------- вспомогательные методы ----------

    def _unrealized(self, position: Position, price: float) -> float:
        if position.side == "Buy":
            return (price - position.entry_price) * position.qty
        return (position.entry_price - price) * position.qty

    def _current_equity(self, marks: Dict[str, float]) -> float:
        eq = self.cash
        for sym, pos in self.positions.items():
            price = marks.get(sym, pos.entry_price)
            eq += self._unrealized(pos, price)
        return eq

    # ---------- публичные методы ----------

    def mark(self, ts: int, marks: Dict[str, float]) -> None:
        """Пересчитать equity, обновить HWM и дописать точку в equity_curve."""
        eq = self._current_equity(marks)
        if eq > self.hwm:
            self.hwm = eq
        self.equity_curve.append((int(ts), float(eq)))

    def open_position(
        self,
        *,
        symbol: str,
        side: str,
        qty: float,
        entry_price: float,
        fee: float,
        ts: int,
        hard_stop: float,
        atr_at_entry: float,
        meta: Optional[dict] = None,
    ) -> Position:
        """Зарегистрировать новую позицию. Комиссия списывается из cash."""
        self.cash -= float(fee)
        pos = Position(
            symbol=symbol,
            side=side,
            qty=float(qty),
            entry_price=float(entry_price),
            entry_ts=int(ts),
            hard_stop=float(hard_stop),
            atr_at_entry=float(atr_at_entry),
            high_since_entry=float(entry_price),
            low_since_entry=float(entry_price),
            meta=dict(meta or {}),
        )
        self.positions[symbol] = pos
        return pos

    def close_position(
        self,
        *,
        symbol: str,
        exit_price: float,
        fee: float,
        ts: int,
        reason: str,
    ) -> dict:
        """Закрыть позицию: списать комиссию, начислить realized PnL."""
        pos = self.positions.pop(symbol, None)
        if pos is None:
            raise KeyError(f"Нет открытой позиции {symbol}")
        realized = self._unrealized(pos, float(exit_price))
        self.cash += realized - float(fee)
        trade = {
            "symbol": symbol,
            "side": pos.side,
            "qty": pos.qty,
            "entry": pos.entry_price,
            "exit": float(exit_price),
            "entry_ts": pos.entry_ts,
            "exit_ts": int(ts),
            "pnl": realized - float(fee),
            "fee": float(fee),
            "reason": reason,
        }
        self.closed_trades.append(trade)
        return trade

    def current_risk(self, marks: Dict[str, float]) -> float:
        """Сумма потенциального убытка по открытым позициям до стопа / equity.

        Используется движком для контроля `GLOBAL_RISK_CAP`: не даём суммарному
        «от-entry-до-hard_stop» риску выйти за лимит.
        """
        eq = self._current_equity(marks)
        if eq <= 0:
            return 0.0
        total = 0.0
        for pos in self.positions.values():
            total += abs(pos.entry_price - pos.hard_stop) * pos.qty
        return total / eq

    def update_trailing(self, symbol: str, bar_high: float, bar_low: float) -> None:
        """Подтянуть high_since_entry / low_since_entry in-place."""
        pos = self.positions.get(symbol)
        if pos is None:
            return
        if bar_high > pos.high_since_entry:
            pos.high_since_entry = float(bar_high)
        if bar_low < pos.low_since_entry:
            pos.low_since_entry = float(bar_low)
