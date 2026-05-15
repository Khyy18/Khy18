"""Bayesian-like оптимизатор параметров momentum-стратегии.

Запуск:
    python optimize.py [--symbol BTCUSDT] [--days 90] [--iterations 50]

Перебирает комбинации EMA_FAST, EMA_SLOW, SL, TP, ATR_MIN и находит
набор с лучшим Sharpe-подобным score = total_pnl / max_drawdown.

Алгоритм: random search + hill climbing (простая альтернатива Bayesian
без scipy/sklearn). Первые 30 итераций — random, потом мутации лучших.

Без heavy deps — stdlib + aiohttp + backtest_momentum.run_backtest().
"""

from __future__ import annotations

import argparse
import asyncio
import random
import time
from typing import Any

import aiohttp

import backtest_momentum
import combo_config as cfg


# ─── Пространство параметров ──────────────────────────────────────────

PARAM_SPACE = {
    "ema_fast": (5, 15),       # int
    "ema_slow": (18, 50),      # int
    "stop_loss_pct": (0.01, 0.04),  # float
    "take_profit_pct": (0.02, 0.08),  # float
    "min_atr_pct": (0.003, 0.01),    # float
    "trail_activate_pct": (0.01, 0.04),  # float
    "trail_distance_pct": (0.005, 0.02),  # float
}


def _random_params() -> dict[str, Any]:
    """Сгенерировать случайный набор параметров."""
    ema_fast = random.randint(*PARAM_SPACE["ema_fast"])
    ema_slow = random.randint(*PARAM_SPACE["ema_slow"])
    # Гарантируем fast < slow
    if ema_fast >= ema_slow:
        ema_slow = ema_fast + random.randint(5, 15)

    return {
        "ema_fast": ema_fast,
        "ema_slow": ema_slow,
        "stop_loss_pct": round(random.uniform(*PARAM_SPACE["stop_loss_pct"]), 4),
        "take_profit_pct": round(random.uniform(*PARAM_SPACE["take_profit_pct"]), 4),
        "min_atr_pct": round(random.uniform(*PARAM_SPACE["min_atr_pct"]), 5),
        "trail_activate_pct": round(random.uniform(*PARAM_SPACE["trail_activate_pct"]), 4),
        "trail_distance_pct": round(random.uniform(*PARAM_SPACE["trail_distance_pct"]), 4),
    }


def _mutate_params(params: dict[str, Any]) -> dict[str, Any]:
    """Мутировать лучший набор параметров (hill climbing step)."""
    mutated = dict(params)
    # Выбираем 1-2 параметра для мутации
    keys = list(PARAM_SPACE.keys())
    n_mutations = random.randint(1, 2)
    for _ in range(n_mutations):
        key = random.choice(keys)
        low, high = PARAM_SPACE[key]
        if isinstance(low, int):
            delta = random.randint(-3, 3)
            mutated[key] = max(low, min(high, mutated[key] + delta))
        else:
            delta = random.uniform(-0.005, 0.005)
            mutated[key] = max(low, min(high, round(mutated[key] + delta, 5)))

    # Гарантируем fast < slow
    if mutated["ema_fast"] >= mutated["ema_slow"]:
        mutated["ema_slow"] = mutated["ema_fast"] + 5

    return mutated


def _score_result(result: dict[str, Any]) -> float:
    """Scoring function: PnL / max_dd (Calmar-like ratio).

    Чем выше — тем лучше. Штрафуем за мало сделок.
    """
    if "error" in result or result.get("trades", 0) < 5:
        return -999.0

    total_pnl = result.get("total_pnl_pct", 0.0)
    max_dd = result.get("max_drawdown_pct", 1.0)
    n_trades = result.get("trades", 1)

    if max_dd <= 0:
        max_dd = 0.001

    # Calmar = PnL / DD, бонус за количество сделок (стабильность)
    calmar = total_pnl / max_dd
    trade_bonus = min(1.0, n_trades / 20.0)  # max bonus при >= 20 trades

    return calmar * trade_bonus


# ─── Main ──────────────────────────────────────────────────────────────

async def async_main() -> None:
    parser = argparse.ArgumentParser(description="Optimize momentum parameters")
    parser.add_argument("--symbol", default="BTCUSDT")
    parser.add_argument("--days", type=int, default=90)
    parser.add_argument("--tf", default="15")
    parser.add_argument("--iterations", type=int, default=50)
    args = parser.parse_args()

    print(f"[OPT] Загрузка {args.symbol} {args.tf}m за {args.days} дней...")

    async with aiohttp.ClientSession() as session:
        klines = await backtest_momentum.fetch_klines(
            session, args.symbol, args.tf, args.days
        )

    print(f"[OPT] Загружено {len(klines)} свечей")
    if len(klines) < 200:
        print("[OPT] Слишком мало данных")
        return

    best_score = -999.0
    best_params: dict[str, Any] = {}
    best_result: dict[str, Any] = {}
    all_results: list[tuple[float, dict[str, Any], dict[str, Any]]] = []

    random_phase = int(args.iterations * 0.6)  # 60% random, 40% mutation

    print(f"[OPT] Итераций: {args.iterations} (random: {random_phase}, hill: {args.iterations - random_phase})")
    print("-" * 60)

    for i in range(args.iterations):
        # Генерируем параметры
        if i < random_phase or best_score <= -999:
            params = _random_params()
        else:
            params = _mutate_params(best_params)

        # Бэктест
        result = backtest_momentum.run_backtest(
            klines=klines,
            ema_fast=params["ema_fast"],
            ema_slow=params["ema_slow"],
            stop_loss_pct=params["stop_loss_pct"],
            take_profit_pct=params["take_profit_pct"],
            min_atr_pct=params["min_atr_pct"],
            trail_activate_pct=params["trail_activate_pct"],
            trail_distance_pct=params["trail_distance_pct"],
            fee_per_side=0.00055,
            leverage=cfg.MOMENTUM_LEVERAGE,
            confirmation_bar=True,
        )

        score = _score_result(result)
        all_results.append((score, params, result))

        if score > best_score:
            best_score = score
            best_params = params
            best_result = result
            print(
                f"  [{i+1:3d}] NEW BEST score={score:.3f} | "
                f"EMA {params['ema_fast']}/{params['ema_slow']} | "
                f"SL {params['stop_loss_pct']*100:.1f}% TP {params['take_profit_pct']*100:.1f}% | "
                f"trades={result.get('trades', 0)} wr={result.get('winrate', 0)*100:.0f}% "
                f"pnl={result.get('total_pnl_pct', 0)*100:+.1f}%"
            )

    # Итоговый отчёт
    print()
    print("=" * 60)
    print("  ЛУЧШИЙ НАБОР ПАРАМЕТРОВ")
    print("=" * 60)
    print(f"  Score (Calmar × trade_bonus): {best_score:.3f}")
    print()
    print(f"  MOMENTUM_EMA_FAST = {best_params.get('ema_fast')}")
    print(f"  MOMENTUM_EMA_SLOW = {best_params.get('ema_slow')}")
    print(f"  MOMENTUM_STOP_LOSS_PCT = {best_params.get('stop_loss_pct')}")
    print(f"  MOMENTUM_TAKE_PROFIT_PCT = {best_params.get('take_profit_pct')}")
    print(f"  MOMENTUM_MIN_ATR_PCT = {best_params.get('min_atr_pct')}")
    print(f"  MOMENTUM_TRAIL_ACTIVATE_PCT = {best_params.get('trail_activate_pct')}")
    print(f"  MOMENTUM_TRAIL_DISTANCE_PCT = {best_params.get('trail_distance_pct')}")
    print()
    print(f"  Результат:")
    print(f"    Сделок: {best_result.get('trades', 0)}")
    print(f"    Winrate: {best_result.get('winrate', 0)*100:.1f}%")
    print(f"    PnL: {best_result.get('total_pnl_pct', 0)*100:+.1f}%")
    print(f"    PnL (3x): {best_result.get('total_pnl_pct', 0)*300:+.1f}%")
    print(f"    Max DD: {best_result.get('max_drawdown_pct', 0)*100:.1f}%")
    print(f"    Equity: {best_result.get('equity_final', 1.0):.3f}x")
    print("=" * 60)

    # Top-5
    all_results.sort(key=lambda x: x[0], reverse=True)
    print()
    print("  TOP-5:")
    for rank, (sc, p, r) in enumerate(all_results[:5], 1):
        print(
            f"    #{rank} score={sc:.3f} EMA {p['ema_fast']}/{p['ema_slow']} "
            f"SL {p['stop_loss_pct']*100:.1f}% TP {p['take_profit_pct']*100:.1f}% "
            f"trades={r.get('trades', 0)} pnl={r.get('total_pnl_pct', 0)*100:+.1f}%"
        )


if __name__ == "__main__":
    asyncio.run(async_main())
