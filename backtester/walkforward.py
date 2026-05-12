"""CLI: `python -m backtester.walkforward`.

Минимально жизнеспособный walk-forward: нарезаем интервал на tumbling окна
(train + test), для каждой комбинации гиперпараметров (param-grid) запускаем
два прогона через `BacktestEngine` и выводим сравнительную таблицу.

На этапе FEAT-003 каркас простой: если param-grid не задан - используем
один «пустой» набор параметров. Главное требование - минимум одно окно
train+test на синтетических данных должно выполняться без ошибок.
"""

from __future__ import annotations

import argparse
import datetime
import importlib
import itertools
import json
import sys
from typing import Any, Dict, List, Tuple

from backtester.config import (
    BacktesterConfig,
    DEFAULT_CACHE_DIR,
    DEFAULT_TICK_SIZE,
    HIGHER_TFS,
    PRIMARY_TF,
)
from backtester.data_loader import load_range
from backtester.engine import BacktestEngine
from backtester.metrics import compute_metrics
from backtester.portfolio import Portfolio
from backtester.synthetic import generate_random_walk


def _today_iso() -> str:
    return datetime.date.today().isoformat()


def _parse_args(argv: List[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="python -m backtester.walkforward",
        description=(
            "Walk-forward оптимизатор стратегий. Делит интервал на train/test "
            "окна, для каждой комбинации параметров печатает метрики."
        ),
    )
    p.add_argument("--symbol", default="BTCUSDT")
    p.add_argument("--from", dest="date_from", default="2023-01-01")
    p.add_argument("--to", dest="date_to", default=_today_iso())
    p.add_argument("--train-months", dest="train_months", type=int, default=18)
    p.add_argument("--test-months", dest="test_months", type=int, default=3)
    p.add_argument("--stride-months", dest="stride_months", type=int, default=3)
    p.add_argument("--param-grid", dest="param_grid", default=None)
    p.add_argument("--strategy", default="strategy_v2")
    p.add_argument("--initial-equity", dest="initial_equity", type=float, default=10000.0)
    p.add_argument("--synthetic", action="store_true")
    p.add_argument("--bars", type=int, default=10000)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--cache-dir", dest="cache_dir", default=DEFAULT_CACHE_DIR)
    return p.parse_args(argv)


def _load_param_grid(path: str | None) -> List[Dict[str, Any]]:
    if not path:
        return [{}]
    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except (OSError, ValueError) as exc:
        print(f"[WF] Не удалось прочитать {path}: {exc}. Используем один пустой набор.")
        return [{}]
    if not isinstance(raw, dict) or not raw:
        return [{}]
    keys = list(raw.keys())
    value_lists = [raw[k] if isinstance(raw[k], list) else [raw[k]] for k in keys]
    combos: List[Dict[str, Any]] = []
    for combo in itertools.product(*value_lists):
        combos.append({keys[i]: combo[i] for i in range(len(keys))})
    return combos or [{}]


def _load_full_data(args: argparse.Namespace) -> List[dict]:
    if args.synthetic:
        return generate_random_walk(
            args.symbol, args.bars, start_price=30000.0, seed=args.seed
        )
    return load_range(args.symbol, args.date_from, args.date_to, args.cache_dir)


def _slice_candles(candles: List[dict], ts_from: int, ts_to: int) -> List[dict]:
    return [c for c in candles if ts_from <= c["ts"] < ts_to]


def _run_window(
    candles: List[dict],
    strategy_mod,
    symbol: str,
    initial_equity: float,
) -> Tuple[Portfolio, Dict[str, Any]]:
    bt_config = BacktesterConfig(initial_equity=initial_equity)
    portfolio = Portfolio(initial_equity, bt_config)
    engine = BacktestEngine(
        portfolio=portfolio,
        strategy_module=strategy_mod,
        symbols=[symbol],
        primary_tf=PRIMARY_TF,
        higher_tfs=HIGHER_TFS,
        tick_sizes=DEFAULT_TICK_SIZE,
        config=bt_config,
    )
    result = engine.run({symbol: candles})
    portfolio._num_bars_seen = result["num_bars"]
    metrics = compute_metrics(portfolio)
    return portfolio, metrics


def _windows(candles: List[dict], train_months: int, test_months: int, stride_months: int):
    if not candles:
        return
    # Простая аппроксимация: 1 месяц ~ 30*24*60 минут для синтетики;
    # для реальных данных используем фактические timestamps.
    first_ts = candles[0]["ts"]
    last_ts = candles[-1]["ts"]
    month_ms = 30 * 24 * 60 * 60 * 1000
    train_ms = train_months * month_ms
    test_ms = test_months * month_ms
    stride_ms = stride_months * month_ms

    start = first_ts
    while start + train_ms + test_ms <= last_ts:
        train_from = start
        train_to = start + train_ms
        test_from = train_to
        test_to = test_from + test_ms
        yield (train_from, train_to, test_from, test_to)
        start += stride_ms
    # Если ни одно окно не помещается, но данные есть - даём хотя бы одно
    # усечённое окно train+test (половина / половина).
    if not any(True for _ in ()):  # заглушка: генератор уже отдал все окна
        return


def main(argv: List[str] | None = None) -> int:
    args = _parse_args(list(argv) if argv is not None else sys.argv[1:])

    try:
        strategy_mod = importlib.import_module(args.strategy)
    except ImportError as exc:
        print(f"[WF] Не удалось импортировать стратегию {args.strategy}: {exc}")
        return 2

    candles = _load_full_data(args)
    if not candles:
        print("[WF] Пусто: нет данных для walk-forward, завершаемся")
        return 0

    grid = _load_param_grid(args.param_grid)
    print(f"[WF] Параметров в сетке: {len(grid)} | данных 1m: {len(candles)} баров")

    windows = list(
        _windows(candles, args.train_months, args.test_months, args.stride_months)
    )
    if not windows:
        # Вынужденный fallback: половина на train, половина на test.
        mid = len(candles) // 2
        if mid < 10:
            print("[WF] Недостаточно данных для walk-forward")
            return 0
        train_from = candles[0]["ts"]
        train_to = candles[mid]["ts"]
        test_from = train_to
        test_to = candles[-1]["ts"] + 1
        windows = [(train_from, train_to, test_from, test_to)]
        print("[WF] Fallback-окно: 50/50 train/test")

    header = (
        "| {:<10} | {:<22} | {:>10} | {:>10} | {:>12} | {:>12} |".format(
            "win#", "params", "train_sh", "test_sh", "test_ret%", "test_mdd%"
        )
    )
    sep = "+" + "-" * 12 + "+" + "-" * 24 + "+" + "-" * 12 + "+" + "-" * 12 + "+" + "-" * 14 + "+" + "-" * 14 + "+"
    print(sep)
    print(header)
    print(sep)

    set_params = getattr(strategy_mod, "set_params", None)

    for w_idx, (train_from, train_to, test_from, test_to) in enumerate(windows):
        train = _slice_candles(candles, train_from, train_to)
        test = _slice_candles(candles, test_from, test_to)
        for combo in grid:
            if set_params is not None:
                try:
                    set_params(**combo)
                except TypeError:
                    pass
            _, train_m = _run_window(train, strategy_mod, args.symbol, args.initial_equity)
            _, test_m = _run_window(test, strategy_mod, args.symbol, args.initial_equity)
            row = "| {:<10} | {:<22} | {:>10} | {:>10} | {:>12} | {:>12} |".format(
                w_idx,
                str(combo)[:22],
                f"{train_m['sharpe']:.2f}",
                f"{test_m['sharpe']:.2f}",
                f"{test_m['total_return_pct']:.2f}",
                f"{test_m['max_drawdown_pct']:.2f}",
            )
            print(row)
    print(sep)
    print("Готово.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
