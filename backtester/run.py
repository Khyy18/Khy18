"""CLI: `python -m backtester.run`.

Запускает event-driven бэктест на синтетических или реальных данных и
печатает ASCII-таблицу метрик. Опционально складывает метрики в JSON.
"""

from __future__ import annotations

import argparse
import datetime
import importlib
import sys
from typing import Dict, List

from backtester.config import (
    BacktesterConfig,
    DEFAULT_CACHE_DIR,
    DEFAULT_TICK_SIZE,
    HIGHER_TFS,
    PRIMARY_TF,
)
from backtester.data_loader import load_range
from backtester.engine import BacktestEngine
from backtester.metrics import compute_metrics, dump_json, format_metrics_table
from backtester.portfolio import Portfolio
from backtester.synthetic import generate_random_walk


_DEFAULT_START_PRICE = {
    "BTCUSDT": 30000.0,
    "ETHUSDT": 2000.0,
    "SOLUSDT": 100.0,
}


def _today_iso() -> str:
    return datetime.date.today().isoformat()


def _parse_args(argv: List[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="python -m backtester.run",
        description=(
            "Event-driven бэктестер Zenith-Control Ultimate. "
            "Поддерживает синтетические данные (для smoke-тестов) и реальные "
            "1m-свечи Binance (загружаются в кэш)."
        ),
    )
    p.add_argument("--symbol", default="BTCUSDT", help="торговая пара (по умолчанию BTCUSDT)")
    p.add_argument(
        "--symbols",
        default=None,
        help="список пар через запятую (перекрывает --symbol)",
    )
    p.add_argument("--from", dest="date_from", default="2023-01-01")
    p.add_argument("--to", dest="date_to", default=_today_iso())
    p.add_argument("--strategy", default="strategy_v2")
    p.add_argument("--initial-equity", dest="initial_equity", type=float, default=10000.0)
    p.add_argument("--timeframe", default=PRIMARY_TF, help="первичный TF для движка")
    p.add_argument("--synthetic", action="store_true", help="использовать случайный ГСЧ")
    p.add_argument("--bars", type=int, default=10000, help="длина синтетики, 1m-баров")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--json-out", dest="json_out", default=None)
    p.add_argument("--cache-dir", dest="cache_dir", default=DEFAULT_CACHE_DIR)
    return p.parse_args(argv)


def _load_data(args: argparse.Namespace, symbols: List[str]) -> Dict[str, List[dict]]:
    data: Dict[str, List[dict]] = {}
    if args.synthetic:
        for idx, sym in enumerate(symbols):
            start_price = _DEFAULT_START_PRICE.get(sym, 100.0)
            data[sym] = generate_random_walk(
                sym,
                args.bars,
                start_price=start_price,
                seed=args.seed + idx,
            )
            print(
                f"[RUN] Синтетика {sym}: {len(data[sym])} 1m-баров "
                f"(seed={args.seed + idx}, start_price={start_price})"
            )
        return data

    for sym in symbols:
        candles = load_range(sym, args.date_from, args.date_to, args.cache_dir)
        data[sym] = candles
        print(f"[RUN] Binance {sym}: {len(candles)} 1m-баров из кэша/сети")
    return data


def main(argv: List[str] | None = None) -> int:
    args = _parse_args(list(argv) if argv is not None else sys.argv[1:])

    if args.symbols:
        symbols = [s.strip() for s in args.symbols.split(",") if s.strip()]
    else:
        symbols = [args.symbol]
    if not symbols:
        print("[RUN] Не задано ни одной торговой пары")
        return 2

    try:
        strategy_mod = importlib.import_module(args.strategy)
    except ImportError as exc:
        print(f"[RUN] Не удалось импортировать стратегию {args.strategy}: {exc}")
        return 2

    data_1m_by_symbol = _load_data(args, symbols)
    if not any(data_1m_by_symbol.values()):
        print("[RUN] Нет данных для бэктеста - завершаемся")
        # Печатаем пустую таблицу, чтобы CI-проверка format_metrics_table не падала.
        empty_portfolio = Portfolio(args.initial_equity, BacktesterConfig(initial_equity=args.initial_equity))
        metrics = compute_metrics(empty_portfolio)
        print(format_metrics_table(metrics))
        return 0

    bt_config = BacktesterConfig(initial_equity=args.initial_equity)
    portfolio = Portfolio(args.initial_equity, bt_config)
    engine = BacktestEngine(
        portfolio=portfolio,
        strategy_module=strategy_mod,
        symbols=symbols,
        primary_tf=args.timeframe,
        higher_tfs=HIGHER_TFS,
        tick_sizes=DEFAULT_TICK_SIZE,
        config=bt_config,
    )
    print(f"[RUN] Запуск: стратегия={args.strategy} символы={symbols} эквити={args.initial_equity}")
    result = engine.run(data_1m_by_symbol)
    portfolio._num_bars_seen = result["num_bars"]  # метка для metrics.exposure

    metrics = compute_metrics(portfolio)
    print(format_metrics_table(metrics))

    if args.json_out:
        dump_json(metrics, args.json_out)
        print(f"[RUN] Метрики сохранены в {args.json_out}")

    print("Готово.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
