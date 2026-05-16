"""Метрики бэктеста + рендер ASCII-таблицы + JSON-дамп.

Формулы:
  total_return_pct   = (final / initial - 1) * 100
  cagr               = (final / initial)^(1/years) - 1, в процентах
  sharpe             = mean(r)/stdev(r) * sqrt(periods_per_year)
  sortino            = mean(r)/stdev(r[r<0]) * sqrt(periods_per_year)
  max_drawdown_pct   = min((eq - running_max)/running_max) * 100
  profit_factor      = sum(win_pnl) / |sum(loss_pnl)|
  calmar             = (cagr_fraction) / |max_drawdown_pct/100|
  exposure_pct       = in_position_bars / num_bars * 100

На пустых/вырожденных входах возвращаем 0.0 / inf там, где это логично.
"""

from __future__ import annotations

import json
import math
import statistics
from typing import Any, Dict, List


def _returns_from_equity(equity_curve: List[tuple]) -> List[float]:
    returns: List[float] = []
    for i in range(1, len(equity_curve)):
        prev = equity_curve[i - 1][1]
        cur = equity_curve[i][1]
        if prev > 0:
            returns.append((cur - prev) / prev)
    return returns


def _max_drawdown_pct(equity_curve: List[tuple]) -> float:
    if not equity_curve:
        return 0.0
    peak = equity_curve[0][1]
    mdd = 0.0
    for _, eq in equity_curve:
        if eq > peak:
            peak = eq
        if peak > 0:
            dd = (eq - peak) / peak
            if dd < mdd:
                mdd = dd
    return mdd * 100.0


def _sharpe(returns: List[float], periods_per_year: int) -> float:
    if len(returns) < 2:
        return 0.0
    try:
        s = statistics.stdev(returns)
    except statistics.StatisticsError:
        return 0.0
    if s <= 0:
        return 0.0
    m = statistics.fmean(returns)
    return (m / s) * math.sqrt(float(periods_per_year))


def _sortino(returns: List[float], periods_per_year: int) -> float:
    if len(returns) < 2:
        return 0.0
    neg = [r for r in returns if r < 0]
    if len(neg) < 2:
        return 0.0
    try:
        s = statistics.stdev(neg)
    except statistics.StatisticsError:
        return 0.0
    if s <= 0:
        return 0.0
    m = statistics.fmean(returns)
    return (m / s) * math.sqrt(float(periods_per_year))


def compute_metrics(
    portfolio,
    *,
    periods_per_year: int = 365 * 24,
) -> Dict[str, Any]:
    """Собрать метрики бэктеста из состояния портфеля."""
    eq_curve: List[tuple] = list(portfolio.equity_curve)
    trades: List[dict] = list(portfolio.closed_trades)
    initial = float(portfolio.initial_equity)
    final = float(eq_curve[-1][1]) if eq_curve else initial

    total_return_pct = (final / initial - 1.0) * 100.0 if initial > 0 else 0.0

    # CAGR по времени между первой и последней точкой equity.
    cagr_pct = 0.0
    if eq_curve and len(eq_curve) >= 2 and initial > 0:
        elapsed_ms = eq_curve[-1][0] - eq_curve[0][0]
        elapsed_years = elapsed_ms / (1000.0 * 60.0 * 60.0 * 24.0 * 365.0)
        if elapsed_years > 0 and final > 0:
            try:
                cagr = (final / initial) ** (1.0 / elapsed_years) - 1.0
                cagr_pct = cagr * 100.0
            except (ValueError, ZeroDivisionError):
                cagr_pct = 0.0

    returns = _returns_from_equity(eq_curve)
    sharpe = _sharpe(returns, periods_per_year)
    sortino = _sortino(returns, periods_per_year)
    mdd_pct = _max_drawdown_pct(eq_curve)

    wins = [t["pnl"] for t in trades if t.get("pnl", 0.0) > 0]
    losses = [t["pnl"] for t in trades if t.get("pnl", 0.0) < 0]
    sum_wins = sum(wins)
    sum_losses = sum(losses)
    if sum_losses < 0 and wins:
        profit_factor = sum_wins / abs(sum_losses)
    elif wins and not losses:
        profit_factor = float("inf")
    else:
        profit_factor = 0.0

    num_trades = len(trades)
    win_rate_pct = (100.0 * len(wins) / num_trades) if num_trades > 0 else 0.0
    avg_win = (sum_wins / len(wins)) if wins else 0.0
    avg_loss = (sum_losses / len(losses)) if losses else 0.0

    cagr_fraction = cagr_pct / 100.0
    calmar = (cagr_fraction / abs(mdd_pct / 100.0)) if mdd_pct != 0 else 0.0

    num_bars = max(int(getattr(portfolio, "_num_bars_seen", 0)), len(eq_curve))
    in_position_bars = int(getattr(portfolio, "in_position_bars", 0))
    exposure_pct = (100.0 * in_position_bars / num_bars) if num_bars > 0 else 0.0

    if num_trades > 0:
        holding_hours = [
            (t["exit_ts"] - t["entry_ts"]) / (1000.0 * 3600.0) for t in trades
        ]
        avg_holding_hours = sum(holding_hours) / len(holding_hours)
    else:
        avg_holding_hours = 0.0

    return {
        "total_return_pct": round(total_return_pct, 4),
        "cagr": round(cagr_pct, 4),
        "sharpe": round(sharpe, 4),
        "sortino": round(sortino, 4),
        "max_drawdown_pct": round(mdd_pct, 4),
        "profit_factor": (
            float("inf")
            if profit_factor == float("inf")
            else round(profit_factor, 4)
        ),
        "win_rate_pct": round(win_rate_pct, 4),
        "avg_win": round(avg_win, 4),
        "avg_loss": round(avg_loss, 4),
        "calmar": round(calmar, 4),
        "exposure_pct": round(exposure_pct, 4),
        "num_trades": num_trades,
        "avg_holding_hours": round(avg_holding_hours, 4),
        "final_equity": round(final, 4),
        "initial_equity": round(initial, 4),
    }


# --- Рендер таблицы ---

_ROWS = (
    ("Итоговый возврат, %", "total_return_pct"),
    ("CAGR, %", "cagr"),
    ("Sharpe", "sharpe"),
    ("Sortino", "sortino"),
    ("Макс. просадка, %", "max_drawdown_pct"),
    ("Profit factor", "profit_factor"),
    ("Win rate, %", "win_rate_pct"),
    ("Средний выигрыш", "avg_win"),
    ("Средний проигрыш", "avg_loss"),
    ("Calmar", "calmar"),
    ("Экспозиция, %", "exposure_pct"),
    ("Сделок", "num_trades"),
    ("Среднее удержание, ч", "avg_holding_hours"),
    ("Начальное эквити", "initial_equity"),
    ("Конечное эквити", "final_equity"),
)


def format_metrics_table(metrics: Dict[str, Any]) -> str:
    """Сформировать ASCII-таблицу с русскими заголовками."""
    label_w = 28
    value_w = 24
    # Полная ширина линии = "+{-*(lw+2)}+{-*(vw+2)}+" = 1 + lw+2 + 1 + vw+2 + 1
    total = label_w + value_w + 7
    line = "+" + "-" * (label_w + 2) + "+" + "-" * (value_w + 2) + "+"
    title = "Метрики бэктеста"
    # В заголовке формат "| <title><pad> |" имеет рамку из 4 символов (| + пробел слева, пробел + | справа).
    pad = max(0, total - len(title) - 4)
    header = "| " + title + " " * pad + " |"
    out = [line, header, line]
    for human, key in _ROWS:
        raw = metrics.get(key, 0.0)
        if isinstance(raw, float) and raw == float("inf"):
            val_str = "inf"
        elif isinstance(raw, float):
            val_str = f"{raw:,.4f}"
        else:
            val_str = str(raw)
        out.append(
            "| {label:<{lw}} | {value:>{vw}} |".format(
                label=human, lw=label_w, value=val_str, vw=value_w
            )
        )
    out.append(line)
    return "\n".join(out)


def dump_json(metrics: Dict[str, Any], path: str) -> None:
    """Сохранить метрики в JSON (UTF-8, без escape-ния кириллицы)."""
    safe: Dict[str, Any] = {}
    for k, v in metrics.items():
        if isinstance(v, float) and v == float("inf"):
            safe[k] = "inf"
        else:
            safe[k] = v
    with open(path, "w", encoding="utf-8") as f:
        json.dump(safe, f, ensure_ascii=False, indent=2)
