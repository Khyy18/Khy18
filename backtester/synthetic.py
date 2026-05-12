"""Генератор синтетических 1m-свечей для smoke-тестов бэктестера.

Параметры подобраны так, чтобы за ~5000 минут (~3.5 суток) при регулярных
сменах режима на `bars // 4` тиках появлялось достаточно Donchian-пробоев
(и у v1 было несколько RSI-пересечений). Главное требование -
детерминизм: для одного и того же seed + bars результат идентичен.
"""

from __future__ import annotations

import random
from typing import List


_START_EPOCH_MS = 1_700_000_000_000  # фиксированная точка старта (ноябрь 2023)


def generate_random_walk(
    symbol: str,
    bars: int,
    *,
    start_price: float = 30000.0,
    seed: int = 42,
    regime_shifts: bool = True,
) -> List[dict]:
    """Сгенерировать `bars` одноминутных свечей с чередованием режимов.

    Используется локальный `random.Random(seed)` - глобальное состояние
    модуля `random` не трогаем (иначе сломалась бы детерминированность).
    """
    if bars <= 0:
        return []

    rng = random.Random(seed)
    sigma = 0.001
    mu_amplitude = 0.00005
    regime_len = max(1, bars // 4)

    price = float(start_price)
    open_ = price
    candles: List[dict] = []

    for i in range(bars):
        if regime_shifts:
            # На каждом блоке regime_len флип знака тренда.
            block = i // regime_len
            mu = mu_amplitude if (block % 2 == 0) else -mu_amplitude
        else:
            mu = 0.0

        ret = rng.gauss(mu, sigma)
        close = max(price * (1.0 + ret), 0.01)

        wick_up = abs(rng.gauss(0.0, 0.0005))
        wick_dn = abs(rng.gauss(0.0, 0.0005))
        high = max(open_, close) * (1.0 + wick_up)
        low = min(open_, close) * (1.0 - wick_dn)
        if low <= 0:
            low = min(open_, close) * 0.999
        volume = rng.uniform(10.0, 100.0)

        candles.append(
            {
                "ts": _START_EPOCH_MS + i * 60_000,
                "open": float(open_),
                "high": float(high),
                "low": float(low),
                "close": float(close),
                "volume": float(volume),
            }
        )

        price = close
        open_ = close

    # Игнорируем параметр symbol намеренно: он нужен вызывающему коду
    # (для маршрутизации), но генератор симметричен для любых инструментов.
    _ = symbol
    return candles
