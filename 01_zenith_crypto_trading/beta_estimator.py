"""Rolling beta для correlation guard.

Зачем: статические BTC=1.0, ETH=1.2, SOL=1.6 в main._BETA_TO_BTC -
средне-долгосрочная оценка. В реальности 30-дневная бета сильно дрейфует
(SOL в кризис апреля 2024 имела бету 2.5+, в боковике 2025 - около 1.0),
и фиксированные значения пере- или недо-капают correlation guard.

Решение: раз в сутки пересчитываем беты по реальным дневным доходностям
символов из state["symbols"][sym]["daily_ohlc"]. Используем 30-дневное
окно (или сколько есть, минимум 10 дней - меньше уже не статистика).

Беты сохраняются в memory.kv_store под ключом "rolling_betas_v1" со
своим updated_iso, чтобы после рестарта мы не пересчитывали сразу,
если нет свежих данных.

Формула: β = cov(r_sym, r_btc) / var(r_btc), где r_x - дневные
log-returns. BTCUSDT всегда имеет бету 1.0 (численно близко - но мы
жёстко прибиваем как референс).
"""

from __future__ import annotations

import math
import statistics
from datetime import datetime, timezone
from typing import Optional


# Минимум баров для устойчивой оценки беты. Меньше - возвращаем None,
# вызывающий код упадёт обратно на статические значения из main._BETA_TO_BTC.
MIN_BARS_FOR_BETA = 10
# Идеальное окно для среднесрочного риск-управления.
ROLLING_WINDOW_DAYS = 30

# Безопасные дефолты для случая, когда rolling-бета ещё не насчитана
# (первый запуск, нет дневных данных). Совпадают со старым _BETA_TO_BTC,
# чтобы поведение было идентично прошлой версии.
DEFAULT_BETAS: dict[str, float] = {
    "BTCUSDT": 1.0,
    "ETHUSDT": 1.2,
    "SOLUSDT": 1.6,
}

# Жёсткие границы: даже если оценка скажет "бета 4.0" (бывает на сильных
# выбросах), мы клипуем для устойчивости correlation guard. 0.5..3.0
# покрывает реалистичный диапазон для крупных альтов.
BETA_MIN = 0.5
BETA_MAX = 3.0

# Ключ в memory.kv_store.
_KV_KEY = "rolling_betas_v1"
# Как часто пересчитывать (24 часа). Беты не меняются мгновенно.
RECALC_INTERVAL_SEC = 24 * 3600


def _log_returns(closes: list[float]) -> list[float]:
    """Логарифмические дневные доходности. Длина = len(closes) - 1."""
    out: list[float] = []
    for i in range(1, len(closes)):
        prev = float(closes[i - 1])
        cur = float(closes[i])
        if prev <= 0 or cur <= 0:
            continue
        out.append(math.log(cur / prev))
    return out


def _beta_vs_btc(returns_sym: list[float], returns_btc: list[float]) -> Optional[float]:
    """β = cov(sym, btc) / var(btc). Берём ровно столько баров, сколько
    есть с обеих сторон (выравнивание по хвосту - это последние N дней)."""
    n = min(len(returns_sym), len(returns_btc))
    if n < MIN_BARS_FOR_BETA:
        return None
    s = returns_sym[-n:]
    b = returns_btc[-n:]
    try:
        var_b = statistics.pvariance(b)
        if var_b <= 0:
            return None
        mean_s = statistics.fmean(s)
        mean_b = statistics.fmean(b)
        cov = sum((s[i] - mean_s) * (b[i] - mean_b) for i in range(n)) / n
        beta = cov / var_b
    except statistics.StatisticsError:
        return None
    if not math.isfinite(beta):
        return None
    # Клипуем к разумным границам для устойчивости correlation guard.
    return max(BETA_MIN, min(BETA_MAX, float(beta)))


def compute_betas(
    daily_closes_by_symbol: dict[str, list[float]],
    btc_symbol: str = "BTCUSDT",
) -> dict[str, float]:
    """Пересчитать беты на основе словаря symbol -> daily closes.

    Возвращает словарь symbol -> beta. BTC жёстко = 1.0 (референс).
    Если для символа недостаточно данных или вариация ноль - используем
    DEFAULT_BETAS как fallback.
    """
    btc_closes = daily_closes_by_symbol.get(btc_symbol, [])
    btc_returns = _log_returns(btc_closes)
    if len(btc_returns) < MIN_BARS_FOR_BETA:
        return dict(DEFAULT_BETAS)

    # Берём последние ROLLING_WINDOW_DAYS дней (или сколько есть).
    btc_returns = btc_returns[-ROLLING_WINDOW_DAYS:]

    out: dict[str, float] = {btc_symbol: 1.0}
    for sym, closes in daily_closes_by_symbol.items():
        if sym == btc_symbol:
            continue
        sym_returns = _log_returns(closes)[-ROLLING_WINDOW_DAYS:]
        beta = _beta_vs_btc(sym_returns, btc_returns)
        if beta is None:
            beta = DEFAULT_BETAS.get(sym, 1.0)
        out[sym] = float(beta)
    # Дозаполняем символами, которые есть в DEFAULT_BETAS но не было в
    # data (защита от частичных данных).
    for sym, val in DEFAULT_BETAS.items():
        out.setdefault(sym, val)
    return out


def _utc_now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat(timespec="seconds")


def load_cached() -> dict[str, float]:
    """Загрузить последние сохранённые беты из kv_store. На любой ошибке
    или старте - DEFAULT_BETAS."""
    try:
        import memory

        snap = memory.kv_get(_KV_KEY, default=None)
    except Exception as exc:  # noqa: BLE001
        print(f"[BETA] load_cached: {exc}")
        return dict(DEFAULT_BETAS)
    if not isinstance(snap, dict):
        return dict(DEFAULT_BETAS)
    betas = snap.get("betas")
    if not isinstance(betas, dict):
        return dict(DEFAULT_BETAS)
    out: dict[str, float] = {}
    for sym, val in betas.items():
        try:
            out[str(sym)] = float(val)
        except (TypeError, ValueError):
            continue
    # Подмешиваем дефолты для отсутствующих символов.
    for sym, val in DEFAULT_BETAS.items():
        out.setdefault(sym, val)
    return out


def save_cached(betas: dict[str, float]) -> None:
    """Сохранить беты в kv_store. Плюс пометка времени для is_stale."""
    try:
        import memory

        memory.kv_set(
            _KV_KEY,
            {"betas": dict(betas), "updated_iso": _utc_now_iso()},
        )
    except Exception as exc:  # noqa: BLE001
        print(f"[BETA] save_cached: {exc}")


def is_stale(max_age_sec: float = RECALC_INTERVAL_SEC) -> bool:
    """True если кэшированные беты старше max_age_sec (или их вообще нет)."""
    try:
        import memory

        snap = memory.kv_get(_KV_KEY, default=None)
    except Exception:
        return True
    if not isinstance(snap, dict):
        return True
    iso = snap.get("updated_iso")
    if not iso:
        return True
    try:
        when = datetime.fromisoformat(str(iso))
        if when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)
        now = datetime.now(tz=timezone.utc)
        age = (now - when).total_seconds()
    except (TypeError, ValueError):
        return True
    return age > float(max_age_sec)
