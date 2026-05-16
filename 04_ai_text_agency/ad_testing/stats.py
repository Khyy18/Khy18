"""Статистические функции для A/B-тестирования.

Использует scipy.stats.chi2_contingency для теста значимости различий
в конверсиях между двумя рекламными каналами.
"""

from __future__ import annotations

import numpy as np
from scipy.stats import chi2_contingency


def chi_squared_test(
    conversions_a: int,
    trials_a: int,
    conversions_b: int,
    trials_b: int,
) -> tuple[float, float]:
    """Тест хи-квадрат для 2x2 таблицы сопряженности.

    Возвращает (chi2_statistic, p_value).
    При нулевых trials или одинаковых конверсионных ставках
    возвращает (0.0, 1.0) - различия не значимы.
    """
    # Обработка граничных случаев
    if trials_a <= 0 or trials_b <= 0:
        return (0.0, 1.0)

    # Ограничиваем конверсии диапазоном [0, trials]
    conversions_a = max(0, min(conversions_a, trials_a))
    conversions_b = max(0, min(conversions_b, trials_b))

    # Таблица сопряженности: [[успех_a, неуспех_a], [успех_b, неуспех_b]]
    table = np.array([
        [conversions_a, trials_a - conversions_a],
        [conversions_b, trials_b - conversions_b],
    ])

    # Если все значения в столбце/строке нулевые - нет различий
    if table.sum() == 0:
        return (0.0, 1.0)

    # Если конверсионные ставки идентичны
    rate_a = conversions_a / trials_a
    rate_b = conversions_b / trials_b
    if rate_a == rate_b:
        return (0.0, 1.0)

    try:
        chi2, p_value, _, _ = chi2_contingency(table, correction=False)
        return (float(chi2), float(p_value))
    except ValueError:
        return (0.0, 1.0)
