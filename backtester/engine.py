"""Event-driven движок бэктестера.

Архитектурное решение для FEAT-003: обрабатываем символы последовательно
(один цикл на символ), при этом портфель общий. На каждом 1h-баре:
  1. Формируем контекст стратегии (candles_1h - включая текущий закрытый бар,
     candles_4h/1d - строго ЗАКРЫТЫЕ бары с ts < current ts).
  2. Вызываем strategy_module.on_bar(ctx); если получили ордер - проверяем
     лимит позиций на символ и глобальный риск-кап, затем отправляем в
     ExecutionSimulator. Для лимит-ордеров (PostOnly) филл моделируется на
     СЛЕДУЮЩЕМ 1h-баре того же символа.
  3. Для всех открытых позиций обновляем high/low since entry, двигаем
     chandelier-trail (только в плюс), проверяем hard_stop и time_stop.
  4. Отмечаем equity по последним известным ценам всех символов.

Движок детерминирован - никакого random или wall-clock чтения.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from backtester.config import (
    BacktesterConfig,
    DEFAULT_TICK_SIZE,
    HIGHER_TFS,
    PRIMARY_TF,
    TF_MINUTES,
)
from backtester.execution import ExecutionSimulator
from backtester.portfolio import Portfolio
from backtester.resample import resample


def _ts_to_iso(ts_ms: int) -> str:
    """Преобразовать ms epoch в ISO-строку UTC (нужно для should_time_stop)."""
    return datetime.fromtimestamp(ts_ms / 1000.0, tz=timezone.utc).isoformat()


class BacktestEngine:
    def __init__(
        self,
        portfolio: Portfolio,
        strategy_module,
        symbols: List[str],
        primary_tf: str = PRIMARY_TF,
        higher_tfs: Tuple[str, ...] = HIGHER_TFS,
        tick_sizes: Optional[Dict[str, float]] = None,
        config: Optional[BacktesterConfig] = None,
    ) -> None:
        self.portfolio = portfolio
        self.strategy = strategy_module
        self.symbols = list(symbols)
        self.primary_tf = primary_tf
        self.higher_tfs = tuple(higher_tfs)
        self.tick_sizes = dict(tick_sizes or DEFAULT_TICK_SIZE)
        self.config = config or BacktesterConfig()
        self.execution = ExecutionSimulator(self.config)

    # --------- основной цикл ---------

    def run(self, data_1m_by_symbol: Dict[str, List[dict]]) -> Dict[str, Any]:
        """Прогнать стратегию на словаре symbol -> 1m-свечи.

        Реализация: линеаризация по символу (простая, одна позиция на символ).
        После каждого обработанного бара обновляем mark-to-market по всем
        известным last close всех символов - equity_curve получается корректной.
        """
        # 1) Ресемплим каждый символ на все нужные TF.
        resampled: Dict[str, Dict[str, List[dict]]] = {}
        for sym, c1m in data_1m_by_symbol.items():
            resampled[sym] = {
                self.primary_tf: resample(c1m, TF_MINUTES[self.primary_tf]),
            }
            for tf in self.higher_tfs:
                resampled[sym][tf] = resample(c1m, TF_MINUTES[tf])

        # 2) Последние известные marks (для честного пересчёта equity).
        last_marks: Dict[str, float] = {}

        total_bars = 0
        # 3) Проходим по символам последовательно. Для FEAT-003 это допустимо:
        #    стратегия не имеет межсимвольной синхронизации (кроме глобального
        #    риск-капа, который проверяется в момент каждого ордера).
        for sym in self.symbols:
            primary = resampled.get(sym, {}).get(self.primary_tf, [])
            if not primary:
                continue
            total_bars += len(primary)

            # Подготовим «ранее сформировавшийся» ордер, который ждёт филла
            # на СЛЕДУЮЩЕМ баре (PostOnly-лимит).
            pending_limit_order: Optional[dict] = None

            higher_tf_cache = {tf: resampled[sym].get(tf, []) for tf in self.higher_tfs}

            for bar_idx, bar in enumerate(primary):
                ts = int(bar["ts"])
                bar_close = float(bar["close"])
                bar_high = float(bar["high"])
                bar_low = float(bar["low"])

                # a) Попробовать исполнить pending PostOnly-лимит
                #    на ТЕКУЩЕМ (следующем после постановки) баре.
                if pending_limit_order is not None:
                    self._try_fill_pending_limit(
                        pending_limit_order, bar, ts, sym
                    )
                    pending_limit_order = None

                # b) Обновить трейлинг/стопы по открытой позиции
                #    на экстремумах ТЕКУЩЕГО бара, затем проверить выходы.
                self._maybe_exit(sym, bar, ts)

                # c) Построить контекст для стратегии и получить ордер.
                equity_now = self.portfolio._current_equity(last_marks or {sym: bar_close})
                ctx = self._build_ctx(
                    sym,
                    primary,
                    bar_idx,
                    higher_tf_cache,
                    equity_now,
                )
                try:
                    order = self.strategy.on_bar(ctx)
                except Exception as exc:  # pragma: no cover
                    print(f"[ENGINE] Ошибка стратегии {sym}@{ts}: {exc}")
                    order = None

                # d) Проверить лимиты и зарегистрировать/исполнить ордер.
                if order is not None and sym not in self.portfolio.positions:
                    self._submit_order(order, bar, ts, sym, last_marks, pending_setter=True)
                    if order.get("type") == "limit":
                        pending_limit_order = order
                else:
                    pending_limit_order = None  # очищаем, чтобы не тащить старые

                # e) Обновить last_marks и отметить equity.
                last_marks[sym] = bar_close
                # Funding-fee начисляется ДО mark(), чтобы equity_curve
                # сразу отражала просадку от funding.
                self.portfolio.accrue_funding(ts, last_marks)
                self.portfolio.mark(ts, last_marks)
                if self.portfolio.positions:
                    self.portfolio.in_position_bars += 1

        final_equity = (
            self.portfolio.equity_curve[-1][1]
            if self.portfolio.equity_curve
            else self.portfolio.initial_equity
        )
        return {
            "equity_curve": list(self.portfolio.equity_curve),
            "trades": list(self.portfolio.closed_trades),
            "final_equity": float(final_equity),
            "in_position_bars": int(self.portfolio.in_position_bars),
            "num_bars": int(total_bars),
            "funding_fees_total": float(self.portfolio.funding_fees_total),
        }

    # --------- вспомогательные ---------

    def _build_ctx(
        self,
        sym: str,
        primary: List[dict],
        bar_idx: int,
        higher_tf_cache: Dict[str, List[dict]],
        equity_now: float,
    ) -> Dict[str, Any]:
        # candles_1h: все закрытые бары ВКЛЮЧАЯ текущий (стратегия получает
        # уже закрытые бары, согласно convention из strategy_v2).
        c1h = primary[: bar_idx + 1]
        cur_ts = int(primary[bar_idx]["ts"])
        # На старших TF отбрасываем формирующийся бар (ts > cur_ts - 1).
        c4h = [c for c in higher_tf_cache.get("4h", []) if int(c["ts"]) < cur_ts]
        c1d = [c for c in higher_tf_cache.get("1d", []) if int(c["ts"]) < cur_ts]

        # Вычисляем atr_1h для ctx (стратегия сама пересчитает, но lump-sum
        # полезно иметь в meta и для риск-капа).
        atr_val = 0.0
        try:
            from strategy_v2 import atr as _atr  # локальный импорт - избежать цикла

            highs = [float(c["high"]) for c in c1h]
            lows = [float(c["low"]) for c in c1h]
            closes = [float(c["close"]) for c in c1h]
            series = _atr(highs, lows, closes, 14)
            if series and series[-1] is not None:
                atr_val = float(series[-1])
        except Exception:
            atr_val = 0.0

        return {
            "symbol": sym,
            "candles_1h": c1h,
            "candles_4h": c4h,
            "candles_1d": c1d,
            "equity": float(equity_now),
            "atr_1h_now": atr_val,
            "blackout": False,
            "regime": "TRENDING",
        }

    def _submit_order(
        self,
        order: dict,
        bar: dict,
        ts: int,
        sym: str,
        last_marks: Dict[str, float],
        pending_setter: bool = False,
    ) -> None:
        # Проверить глобальный риск-кап.
        limit_price = float(order.get("limit_price") or bar["close"])
        hard_stop = float(order["hard_stop"])
        qty = float(order["qty"])
        equity = max(self.portfolio._current_equity(last_marks or {sym: float(bar["close"])}), 1.0)
        added_risk = abs(limit_price - hard_stop) * qty / equity
        if self.portfolio.current_risk(last_marks) + added_risk > self.config.global_risk_cap:
            return

        tick_size = self.tick_sizes.get(sym, 0.0)
        order_type = order.get("type", "market")

        if order_type == "limit":
            # PostOnly - исполним на СЛЕДУЮЩЕМ баре. Здесь ничего не делаем:
            # движок сам возьмёт pending_limit_order на след. итерации.
            _ = pending_setter
            return

        # market / fallback: филл на close ТЕКУЩЕГО бара + slippage.
        self.execution.fill_market_open(
            self.portfolio,
            order,
            ref_price=float(bar["close"]),
            tick_size=tick_size,
            ts=ts,
        )

    def _try_fill_pending_limit(
        self,
        order: dict,
        bar: dict,
        ts: int,
        sym: str,
    ) -> None:
        if sym in self.portfolio.positions:
            return
        tick_size = self.tick_sizes.get(sym, 0.0)
        self.execution.fill_limit_postonly_open(
            self.portfolio,
            order,
            next_bar=bar,
            tick_size=tick_size,
            ts=ts,
        )

    def _maybe_exit(self, sym: str, bar: dict, ts: int) -> None:
        pos = self.portfolio.positions.get(sym)
        if pos is None:
            return

        bar_high = float(bar["high"])
        bar_low = float(bar["low"])
        bar_close = float(bar["close"])
        tick_size = self.tick_sizes.get(sym, 0.0)

        # Обновить трейлинг-экстремумы ДО проверки выхода.
        self.portfolio.update_trailing(sym, bar_high, bar_low)

        # 1) Hard stop.
        if pos.side == "Buy" and bar_low <= pos.hard_stop:
            self.execution.fill_market_close(
                self.portfolio, pos, pos.hard_stop, tick_size, ts, reason="hard_stop"
            )
            return
        if pos.side == "Sell" and bar_high >= pos.hard_stop:
            self.execution.fill_market_close(
                self.portfolio, pos, pos.hard_stop, tick_size, ts, reason="hard_stop"
            )
            return

        # 2) Chandelier-trail: подтягиваем hard_stop только в «плюс».
        try:
            compute_chandelier = getattr(self.strategy, "compute_chandelier", None)
            if compute_chandelier is not None:
                import config as root_config  # type: ignore

                new_trail = compute_chandelier(
                    pos.high_since_entry,
                    pos.low_since_entry,
                    pos.atr_at_entry or 0.0,
                    pos.side,
                    pos.entry_price,
                    activation_atr=pos.atr_at_entry or 0.0,
                    trail_mult=float(getattr(root_config, "ATR_TRAIL_MULT", 3.0)),
                )
                if new_trail is not None:
                    if pos.side == "Buy" and new_trail > pos.hard_stop:
                        pos.hard_stop = float(new_trail)
                    elif pos.side == "Sell" and new_trail < pos.hard_stop:
                        pos.hard_stop = float(new_trail)
        except Exception:
            pass

        # 3) Time stop.
        try:
            should_time_stop = getattr(self.strategy, "should_time_stop", None)
            if should_time_stop is not None:
                import config as root_config  # type: ignore

                stop = bool(
                    should_time_stop(
                        _ts_to_iso(pos.entry_ts),
                        _ts_to_iso(ts),
                        pos.side,
                        pos.entry_price,
                        bar_close,
                        hours=float(getattr(root_config, "TIME_STOP_HOURS", 48)),
                    )
                )
                if stop:
                    self.execution.fill_market_close(
                        self.portfolio, pos, bar_close, tick_size, ts, reason="time_stop"
                    )
                    return
        except Exception:
            pass
