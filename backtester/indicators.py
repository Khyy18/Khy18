"""Совместимый слой индикаторов для бэктестера.

Чтобы индикаторы стратегии и бэктестера не расходились, мы не дублируем код,
а переиспользуем pure-Python реализацию из `strategy_v2` (которая, в свою
очередь, тянет EMA из `strategy_v1`). Доп. утилита `stdev_sqrt_annual`
вынесена сюда, т.к. её используют только метрики бэктестера.
"""

from __future__ import annotations

import math
import statistics

from strategy_v2 import ema, atr, adx, highest, lowest  # noqa: F401


def stdev_sqrt_annual(returns: list[float], periods_per_year: int) -> float:
    """Годовая волатильность серии доходностей.

    Формула: stdev(returns) * sqrt(periods_per_year). Защищаемся от
    вырожденных случаев (len < 2 или нулевой stdev) возвратом 0.0.
    """
    if returns is None or len(returns) < 2:
        return 0.0
    try:
        s = statistics.stdev(returns)
    except statistics.StatisticsError:
        return 0.0
    if s <= 0 or periods_per_year <= 0:
        return 0.0
    return float(s) * math.sqrt(float(periods_per_year))
