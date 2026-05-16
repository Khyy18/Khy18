"""Простой backtester для momentum-стратегии (EMA cross + ATR фильтр).

Запуск:
    python backtest_momentum.py [--symbol BTCUSDT] [--days 90] [--tf 15]

Использует публичные klines Bybit V5 (без ключей). Выводит:
  - Количество сделок
  - Winrate
  - Суммарный PnL (%)
  - Max drawdown
  - Средняя длительность сделки

Без внешних зависимостей (только aiohttp + stdlib).
"""

from __future__ import annotations

import argparse
import asyncio
import time
from typing import Any

import aiohttp

# Используем функции из momentum_engine напрямую
import momentum_engine
import combo_config as cfg


# ─── Маппинг символа для OKX ───────────────────────────────────────────

def _bybit_symbol_to_okx(symbol: str) -> str:
    """Конвертировать символ Bybit -> OKX instId.

    BTCUSDT -> BTC-USDT-SWAP
    ETHUSDT -> ETH-USDT-SWAP
    """
    base = symbol.replace("USDT", "")
    return f"{base}-USDT-SWAP"


# ─── Загрузка свечей с OKX ─────────────────────────────────────────────

async def _fetch_klines_okx(
    session: aiohttp.ClientSession,
    symbol: str,
    interval: str,
    days: int,
) -> list[dict[str, Any]]:
    """Загрузить свечи с OKX публичного API (fallback).

    OKX отдаёт max 100 свечей за запрос. Используем пагинацию через after.
    """
    url = "https://www.okx.com/api/v5/market/history-candles"
    inst_id = _bybit_symbol_to_okx(symbol)
    bar = f"{interval}m"
    all_klines: list[dict[str, Any]] = []

    # Сколько свечей нужно
    interval_min = int(interval)
    candles_needed = (days * 24 * 60) // interval_min
    batch_size = 100

    after: str | None = None

    while len(all_klines) < candles_needed:
        params: dict[str, str] = {
            "instId": inst_id,
            "bar": bar,
            "limit": str(batch_size),
        }
        if after is not None:
            params["after"] = after

        try:
            async with session.get(url, params=params, timeout=15) as resp:
                if resp.status != 200:
                    print(f"[BT][OKX] HTTP {resp.status}")
                    break
                data = await resp.json()
        except Exception as exc:
            print(f"[BT][OKX] Ошибка загрузки: {exc}")
            break

        if data.get("code") != "0":
            print(f"[BT][OKX] API ошибка: {data.get('msg')}")
            break

        raw_list = data.get("data") or []
        if not raw_list:
            break

        batch: list[dict[str, Any]] = []
        for k in raw_list:
            try:
                batch.append({
                    "ts": int(k[0]),
                    "open": float(k[1]),
                    "high": float(k[2]),
                    "low": float(k[3]),
                    "close": float(k[4]),
                    "volume": float(k[5]),
                })
            except (IndexError, TypeError, ValueError):
                continue

        if not batch:
            break

        all_klines.extend(batch)
        # OKX возвращает от новых к старым - берём самый ранний ts для пагинации
        earliest_ts = min(k["ts"] for k in batch)
        after = str(earliest_ts)

        # Rate-limit
        await asyncio.sleep(0.2)

    # Сортируем по времени (старые первыми)
    all_klines.sort(key=lambda k: k["ts"])

    # Убираем дубликаты по ts
    seen: set[int] = set()
    unique: list[dict[str, Any]] = []
    for k in all_klines:
        if k["ts"] not in seen:
            seen.add(k["ts"])
            unique.append(k)

    return unique[-candles_needed:]


# ─── Загрузка исторических свечей с Bybit (с fallback на OKX) ──────────

async def fetch_klines(
    session: aiohttp.ClientSession,
    symbol: str,
    interval: str,
    days: int,
) -> list[dict[str, Any]]:
    """Загрузить свечи с Bybit V5 публичного API.

    Bybit отдаёт max 200 свечей за запрос. Делаем несколько запросов.
    Если Bybit недоступен (не-200), переключаемся на OKX.
    """
    url = "https://api.bybit.com/v5/market/kline"
    all_klines: list[dict[str, Any]] = []

    # Сколько свечей нужно
    interval_min = int(interval)
    candles_needed = (days * 24 * 60) // interval_min
    batch_size = 200

    end_ts = int(time.time() * 1000)

    first_request = True

    while len(all_klines) < candles_needed:
        params = {
            "category": "linear",
            "symbol": symbol,
            "interval": interval,
            "limit": str(batch_size),
            "end": str(end_ts),
        }
        try:
            async with session.get(url, params=params, timeout=15) as resp:
                if resp.status != 200:
                    if first_request:
                        print(f"[BT] Bybit недоступен (HTTP {resp.status}), пробую OKX...")
                        return await _fetch_klines_okx(session, symbol, interval, days)
                    print(f"[BT] HTTP {resp.status}")
                    break
                data = await resp.json()
        except Exception as exc:
            print(f"[BT] Ошибка загрузки: {exc}")
            break

        first_request = False

        if data.get("retCode") != 0:
            print(f"[BT] API ошибка: {data.get('retMsg')}")
            break

        raw_list = (data.get("result") or {}).get("list") or []
        if not raw_list:
            break

        batch: list[dict[str, Any]] = []
        for k in raw_list:
            try:
                batch.append({
                    "ts": int(k[0]),
                    "open": float(k[1]),
                    "high": float(k[2]),
                    "low": float(k[3]),
                    "close": float(k[4]),
                    "volume": float(k[5]),
                })
            except (IndexError, TypeError, ValueError):
                continue

        if not batch:
            break

        all_klines.extend(batch)
        # Bybit возвращает от новых к старым — берём самый ранний ts
        earliest_ts = min(k["ts"] for k in batch)
        end_ts = earliest_ts - 1

        # Rate-limit
        await asyncio.sleep(0.2)

    # Сортируем по времени (старые первыми)
    all_klines.sort(key=lambda k: k["ts"])

    # Убираем дубликаты по ts
    seen: set[int] = set()
    unique: list[dict[str, Any]] = []
    for k in all_klines:
        if k["ts"] not in seen:
            seen.add(k["ts"])
            unique.append(k)

    return unique[-candles_needed:]  # обрезаем до нужного количества


# ─── Backtester ────────────────────────────────────────────────────────

def run_backtest(
    klines: list[dict[str, Any]],
    ema_fast: int,
    ema_slow: int,
    stop_loss_pct: float,
    take_profit_pct: float,
    min_atr_pct: float,
    trail_activate_pct: float,
    trail_distance_pct: float,
    fee_per_side: float = 0.00055,
    leverage: int = 3,
    confirmation_bar: bool = True,
) -> dict[str, Any]:
    """Прогнать momentum-стратегию на исторических свечах.

    Возвращает статистику: trades, winrate, pnl_pct, max_dd, avg_hold.
    """
    if len(klines) < ema_slow + 10:
        return {"error": "Недостаточно свечей"}

    closes = [k["close"] for k in klines]
    fast_ema = momentum_engine.calc_ema(closes, ema_fast)
    slow_ema = momentum_engine.calc_ema(closes, ema_slow)

    trades: list[dict[str, Any]] = []
    position: dict[str, Any] | None = None
    equity_curve: list[float] = [1.0]  # нормализованный equity
    pending_signal: str | None = None  # для confirmation bar

    for i in range(ema_slow + 1, len(klines)):
        price = closes[i]

        # ATR фильтр
        atr = momentum_engine.calc_atr(klines[:i + 1], period=14)
        atr_pct = atr / price if price > 0 else 0.0

        if position is not None:
            # Управление позицией
            entry = position["entry"]
            side = position["side"]

            if side == "LONG":
                pnl_pct = (price - entry) / entry
            else:
                pnl_pct = (entry - price) / entry

            # Trailing stop
            current_sl = position["sl"]
            if trail_activate_pct > 0 and pnl_pct >= trail_activate_pct:
                if side == "LONG":
                    new_sl = price * (1 - trail_distance_pct)
                    if new_sl > current_sl:
                        position["sl"] = new_sl
                        current_sl = new_sl
                else:
                    new_sl = price * (1 + trail_distance_pct)
                    if new_sl < current_sl:
                        position["sl"] = new_sl
                        current_sl = new_sl

            # Проверка выхода
            should_close = False
            reason = ""

            # SL
            if side == "LONG" and price <= current_sl:
                should_close = True
                reason = "SL"
            elif side == "SHORT" and price >= current_sl:
                should_close = True
                reason = "SL"

            # TP
            if take_profit_pct > 0 and pnl_pct >= take_profit_pct:
                should_close = True
                reason = "TP"

            # Обратный сигнал
            signal = momentum_engine.detect_crossover(fast_ema[:i + 1], slow_ema[:i + 1])
            if side == "LONG" and signal == "SHORT":
                should_close = True
                reason = "CROSS"
            elif side == "SHORT" and signal == "LONG":
                should_close = True
                reason = "CROSS"

            if should_close:
                position["exit"] = price
                position["exit_i"] = i
                # #10: Вычитаем комиссии (open + close) и slippage
                raw_pnl = pnl_pct
                fee_drag = fee_per_side * 2  # open + close
                position["pnl_pct"] = raw_pnl - fee_drag
                position["reason"] = reason
                trades.append(position)
                position = None

                # Обновляем equity с leverage и комиссиями
                eq = equity_curve[-1] * (1 + (raw_pnl - fee_drag) * leverage)
                equity_curve.append(eq)
            else:
                equity_curve.append(equity_curve[-1])

        else:
            # Ищем сигнал
            signal = momentum_engine.detect_crossover(fast_ema[:i + 1], slow_ema[:i + 1])

            # #2: Confirmation bar — вход на следующем баре после кросса
            if confirmation_bar:
                if signal:
                    # Кросс произошёл сейчас — сохраняем, не входим
                    pending_signal = signal
                    signal = None
                elif pending_signal:
                    # Следующий бар после кросса — проверяем подтверждение
                    if pending_signal == "LONG" and fast_ema[i] > slow_ema[i]:
                        signal = pending_signal
                    elif pending_signal == "SHORT" and fast_ema[i] < slow_ema[i]:
                        signal = pending_signal
                    pending_signal = None

            if signal and atr_pct >= min_atr_pct:
                if signal == "LONG":
                    sl = price * (1 - stop_loss_pct)
                else:
                    sl = price * (1 + stop_loss_pct)

                position = {
                    "side": signal,
                    "entry": price,
                    "entry_i": i,
                    "sl": sl,
                }
            equity_curve.append(equity_curve[-1])

    # Закрываем незакрытую позицию
    if position is not None:
        price = closes[-1]
        entry = position["entry"]
        side = position["side"]
        if side == "LONG":
            pnl_pct = (price - entry) / entry
        else:
            pnl_pct = (entry - price) / entry
        position["exit"] = price
        position["exit_i"] = len(klines) - 1
        position["pnl_pct"] = pnl_pct
        position["reason"] = "END"
        trades.append(position)

    # Статистика
    n_trades = len(trades)
    if n_trades == 0:
        return {
            "trades": 0,
            "winrate": 0.0,
            "total_pnl_pct": 0.0,
            "max_drawdown_pct": 0.0,
            "avg_hold_bars": 0,
            "equity_final": 1.0,
        }

    wins = sum(1 for t in trades if t["pnl_pct"] > 0)
    total_pnl = sum(t["pnl_pct"] for t in trades)
    avg_hold = sum(t["exit_i"] - t["entry_i"] for t in trades) / n_trades

    # Max drawdown на equity curve
    peak = equity_curve[0]
    max_dd = 0.0
    for eq in equity_curve:
        if eq > peak:
            peak = eq
        dd = (peak - eq) / peak if peak > 0 else 0.0
        if dd > max_dd:
            max_dd = dd

    return {
        "trades": n_trades,
        "winrate": wins / n_trades,
        "total_pnl_pct": total_pnl,
        "max_drawdown_pct": max_dd,
        "avg_hold_bars": int(avg_hold),
        "equity_final": equity_curve[-1],
        "wins": wins,
        "losses": n_trades - wins,
        "best_trade_pct": max(t["pnl_pct"] for t in trades),
        "worst_trade_pct": min(t["pnl_pct"] for t in trades),
        "trades_detail": trades[-10:],  # последние 10 для отладки
    }


# ─── Вывод результатов ─────────────────────────────────────────────────

def print_results(symbol: str, days: int, results: dict[str, Any]) -> None:
    """Красивый вывод результатов бэктеста."""
    print()
    print("=" * 50)
    print(f"  BACKTEST MOMENTUM: {symbol} ({days} дней)")
    print("=" * 50)

    if "error" in results:
        print(f"  Ошибка: {results['error']}")
        return

    print(f"  EMA: {cfg.MOMENTUM_EMA_FAST}/{cfg.MOMENTUM_EMA_SLOW}")
    print(f"  SL: {cfg.MOMENTUM_STOP_LOSS_PCT*100:.1f}%  |  TP: {cfg.MOMENTUM_TAKE_PROFIT_PCT*100:.1f}%")
    print(f"  ATR фильтр: {cfg.MOMENTUM_MIN_ATR_PCT*100:.2f}%")
    print(f"  Trailing: activate {cfg.MOMENTUM_TRAIL_ACTIVATE_PCT*100:.0f}%, distance {cfg.MOMENTUM_TRAIL_DISTANCE_PCT*100:.0f}%")
    print(f"  Leverage: {cfg.MOMENTUM_LEVERAGE}x")
    print("-" * 50)
    print(f"  Сделок:        {results['trades']}")
    print(f"  Winrate:       {results['winrate']*100:.1f}%  ({results.get('wins', 0)}W / {results.get('losses', 0)}L)")
    print(f"  PnL (raw):     {results['total_pnl_pct']*100:+.1f}%")
    print(f"  PnL (3x lev):  {results['total_pnl_pct']*300:+.1f}%")
    print(f"  Max Drawdown:  {results['max_drawdown_pct']*100:.1f}%")
    print(f"  Equity (final):{results['equity_final']:.3f}x")
    print(f"  Avg hold:      {results['avg_hold_bars']} баров")
    if "best_trade_pct" in results:
        print(f"  Best trade:    {results['best_trade_pct']*100:+.2f}%")
        print(f"  Worst trade:   {results['worst_trade_pct']*100:+.2f}%")
    print("=" * 50)
    print()


# ─── Main ──────────────────────────────────────────────────────────────

async def async_main() -> None:
    parser = argparse.ArgumentParser(description="Backtest momentum strategy")
    parser.add_argument("--symbol", default="BTCUSDT", help="Символ (default: BTCUSDT)")
    parser.add_argument("--days", type=int, default=90, help="Период в днях (default: 90)")
    parser.add_argument("--tf", default="15", help="Таймфрейм в минутах (default: 15)")
    args = parser.parse_args()

    print(f"[BT] Загрузка {args.symbol} {args.tf}m за {args.days} дней...")

    async with aiohttp.ClientSession() as session:
        klines = await fetch_klines(session, args.symbol, args.tf, args.days)

    print(f"[BT] Загружено {len(klines)} свечей")

    if len(klines) < 100:
        print("[BT] Слишком мало данных для бэктеста")
        return

    results = run_backtest(
        klines=klines,
        ema_fast=cfg.MOMENTUM_EMA_FAST,
        ema_slow=cfg.MOMENTUM_EMA_SLOW,
        stop_loss_pct=cfg.MOMENTUM_STOP_LOSS_PCT,
        take_profit_pct=cfg.MOMENTUM_TAKE_PROFIT_PCT,
        min_atr_pct=cfg.MOMENTUM_MIN_ATR_PCT,
        trail_activate_pct=cfg.MOMENTUM_TRAIL_ACTIVATE_PCT,
        trail_distance_pct=cfg.MOMENTUM_TRAIL_DISTANCE_PCT,
        fee_per_side=0.00055,  # Bybit taker fee
        leverage=cfg.MOMENTUM_LEVERAGE,
        confirmation_bar=cfg.MOMENTUM_CONFIRMATION_BAR,
    )

    print_results(args.symbol, args.days, results)


if __name__ == "__main__":
    asyncio.run(async_main())
