"""Anomaly detector через скользящее окно + z-score.

Идея: тонкие аномалии (постепенный рост latency биржи перед падением,
аномальный spread относительно нормы для пары) детектируются raw rules
плохо. Z-score на скользящем окне выдаёт сигнал ровно когда метрика
выходит за 3σ от привычного для этой комбинации (биржа, символ, метрика).

Алгоритм:
- Welford's online mean/std (без хранения всех точек, O(1) memory).
- Окно фиксированной длины (default 100 значений) — старые значения
  выпадают, новые добавляются.
- Триггер: |z| > threshold (default 3.0) — alert dict в Telegram.
- Anti-spam: каждый (metric_name, sign(z)) — один alert в час.
"""

from __future__ import annotations
import time
from collections import deque
from typing import Optional


class MetricTracker:
    """Скользящее окно последних N значений + Welford-агрегаты.

    На каждый add возвращает z-score этого значения относительно
    предыдущих. Если в окне меньше 10 значений (warm-up) — None.
    """

    def __init__(self, window_size: int = 100) -> None:
        self._window_size = window_size
        self._values: deque[float] = deque(maxlen=window_size)
        # Welford для текущего содержимого окна.
        self._n = 0
        self._mean = 0.0
        self._m2 = 0.0  # сумма квадратов отклонений от среднего

    def _recompute(self) -> None:
        """Полный пересчёт после deque-trim — Welford incremental не работает с trim'ом."""
        self._n = len(self._values)
        if self._n == 0:
            self._mean = 0.0
            self._m2 = 0.0
            return
        self._mean = sum(self._values) / self._n
        self._m2 = sum((v - self._mean) ** 2 for v in self._values)

    def add(self, value: float) -> Optional[float]:
        """Добавить значение, вернуть z-score этого значения.

        None если в окне до добавления было < 10 значений (warm-up).
        Z-score считается относительно состояния ДО добавления — это
        корректно: новое значение сравнивается с предысторией.
        """
        # Защита от NaN/Inf/нечисловых значений.
        if not isinstance(value, (int, float)) or value != value:  # NaN check
            return None

        # Состояние ДО добавления — для z-score.
        prev_n = len(self._values)
        if prev_n >= 10:
            try:
                std = (self._m2 / prev_n) ** 0.5 if self._m2 >= 0 else 0.0
            except (ValueError, ZeroDivisionError):
                std = 0.0
            z = (value - self._mean) / std if std > 1e-9 else 0.0
        else:
            z = None

        # Добавляем в окно. Если выпал старый — пересчитываем.
        was_full = len(self._values) >= self._window_size
        self._values.append(float(value))
        if was_full:
            self._recompute()
        else:
            # Welford incremental.
            self._n = len(self._values)
            delta = value - self._mean
            self._mean += delta / self._n
            self._m2 += delta * (value - self._mean)

        return z

    def mean(self) -> float:
        return self._mean

    def std(self) -> float:
        if self._n < 2:
            return 0.0
        try:
            return (self._m2 / self._n) ** 0.5
        except (ValueError, ZeroDivisionError):
            return 0.0


class AnomalyDetector:
    """Менеджер MetricTracker'ов по разным именам метрик + cooldown alerts."""

    def __init__(
        self,
        threshold: float = 3.0,
        window_size: int = 100,
        alert_cooldown_sec: float = 3600.0,
    ) -> None:
        self._threshold = threshold
        self._window_size = window_size
        self._cooldown = alert_cooldown_sec
        self._trackers: dict[str, MetricTracker] = {}
        self._last_alert_ts: dict[str, float] = {}  # ключ: f"{metric}:{sign}"

    def record(self, metric_name: str, value: float) -> Optional[dict]:
        """Записать метрику. Если |z| > threshold и cooldown прошёл — вернуть alert."""
        if metric_name not in self._trackers:
            self._trackers[metric_name] = MetricTracker(self._window_size)
        tracker = self._trackers[metric_name]
        z = tracker.add(value)
        if z is None or abs(z) < self._threshold:
            return None
        # Cooldown по знаку z (отдельно для positive/negative выбросов).
        sign = "+" if z > 0 else "-"
        key = f"{metric_name}:{sign}"
        now = time.time()
        last = self._last_alert_ts.get(key, 0.0)
        if (now - last) < self._cooldown:
            return None
        self._last_alert_ts[key] = now
        return {
            "metric": metric_name,
            "value": value,
            "z_score": z,
            "mean": tracker.mean(),
            "std": tracker.std(),
        }

    def status(self) -> dict[str, dict]:
        """Снимок состояния всех трекеров — для дашборда / Telegram-команды."""
        return {
            name: {
                "mean": t.mean(),
                "std": t.std(),
                "n_samples": len(t._values),
            }
            for name, t in self._trackers.items()
        }

    def reset(self, metric_name: Optional[str] = None) -> None:
        """Очистить один трекер или все. Для тестов / ручного reset через TG."""
        if metric_name is None:
            self._trackers.clear()
            self._last_alert_ts.clear()
        elif metric_name in self._trackers:
            del self._trackers[metric_name]
            for k in list(self._last_alert_ts.keys()):
                if k.startswith(f"{metric_name}:"):
                    del self._last_alert_ts[k]


# Singleton для main.py
_GLOBAL_DETECTOR: Optional[AnomalyDetector] = None


def get_detector() -> AnomalyDetector:
    """Получить глобальный singleton (создаётся лениво)."""
    global _GLOBAL_DETECTOR
    if _GLOBAL_DETECTOR is None:
        try:
            import config
            _GLOBAL_DETECTOR = AnomalyDetector(
                threshold=float(getattr(config, "ANOMALY_Z_THRESHOLD", 3.0)),
                window_size=int(getattr(config, "ANOMALY_WINDOW_SIZE", 100)),
                alert_cooldown_sec=float(getattr(config, "ANOMALY_ALERT_COOLDOWN_SEC", 3600.0)),
            )
        except Exception:
            # Любая ошибка чтения конфига — graceful: используем дефолты.
            _GLOBAL_DETECTOR = AnomalyDetector()
    return _GLOBAL_DETECTOR


def reset_detector() -> None:
    """Сбросить глобальный singleton — нужно для изоляции тестов."""
    global _GLOBAL_DETECTOR
    _GLOBAL_DETECTOR = None
