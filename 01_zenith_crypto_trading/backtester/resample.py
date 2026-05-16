"""Ресемплинг 1m-свечей в любой старший таймфрейм (15m/1h/4h/1d).

Стратегия v2 работает на 1h/4h/1d, но исходная мелкая гранулярность
(Binance 1m или синтетика) позволяет пересобирать любые TF без потери
точности high/low. Реализация - одиночный проход, stdlib only.
"""

from __future__ import annotations

from typing import List


def resample(candles_1m: List[dict], tf_minutes: int) -> List[dict]:
    """Собрать candles_1m в бары длительности `tf_minutes`.

    Алгоритм:
      1. Группируем по bucket = floor(ts / bucket_ms) * bucket_ms.
      2. Как только bucket меняется, эмитим предыдущий (агрегат).
      3. Последний (частично закрытый) bucket отбрасываем: движок
         должен видеть только ЗАКРЫТЫЕ бары, иначе стратегия начнёт
         принимать решения по формирующейся свече.
    """
    if tf_minutes <= 0 or not candles_1m:
        return []

    bucket_ms = tf_minutes * 60 * 1000
    # Страхуемся: вдруг вход не отсортирован.
    sorted_in = sorted(candles_1m, key=lambda c: c["ts"])

    out: List[dict] = []
    cur_bucket_start: int | None = None
    cur_open = 0.0
    cur_high = float("-inf")
    cur_low = float("inf")
    cur_close = 0.0
    cur_volume = 0.0

    for c in sorted_in:
        ts = int(c["ts"])
        bucket_start = (ts // bucket_ms) * bucket_ms
        if cur_bucket_start is None:
            cur_bucket_start = bucket_start
            cur_open = float(c["open"])
            cur_high = float(c["high"])
            cur_low = float(c["low"])
            cur_close = float(c["close"])
            cur_volume = float(c["volume"])
            continue

        if bucket_start != cur_bucket_start:
            # Завершаем прошлый bucket и начинаем новый.
            out.append(
                {
                    "ts": cur_bucket_start,
                    "open": cur_open,
                    "high": cur_high,
                    "low": cur_low,
                    "close": cur_close,
                    "volume": cur_volume,
                }
            )
            cur_bucket_start = bucket_start
            cur_open = float(c["open"])
            cur_high = float(c["high"])
            cur_low = float(c["low"])
            cur_close = float(c["close"])
            cur_volume = float(c["volume"])
        else:
            cur_high = max(cur_high, float(c["high"]))
            cur_low = min(cur_low, float(c["low"]))
            cur_close = float(c["close"])
            cur_volume += float(c["volume"])

    # Последний bucket - частичный, НЕ эмитим (см. docstring).
    return out
