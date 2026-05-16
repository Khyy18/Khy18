"""Per-exchange circuit breaker.

Защищает от death-loop'ов: если биржа стабильно возвращает ошибки или
таймауты, мы перестаём её опрашивать, чтобы не валить логи и не тратить
rate-limit'ы.

Используется в обёртке вокруг каждого ExchangeAdapter:
  - на каждый исключения из adapter.* инкрементируется счётчик ошибок;
  - если за окно WINDOW_SEC накопилось >= FAIL_THRESHOLD ошибок, breaker
    переходит в OPEN на COOLDOWN_SEC;
  - в OPEN все вызовы возвращают None / [] немедленно;
  - после COOLDOWN_SEC breaker → HALF_OPEN: следующий вызов реальный, и
    если успех — CLOSED, если фейл — снова OPEN.

Простой 3-state state machine (Hystrix-like). Без зависимостей.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Optional


# --- Параметры (можно переопределить через env в config.py) ----------

WINDOW_SEC = 60.0          # окно подсчёта ошибок
FAIL_THRESHOLD = 5         # ошибок в окне для перехода в OPEN
COOLDOWN_SEC = 600.0       # сколько сидим в OPEN до HALF_OPEN (10 минут)


@dataclass
class _BreakerState:
    """Состояние breaker'а одной биржи."""
    state: str = "CLOSED"             # CLOSED / OPEN / HALF_OPEN
    failures: list[float] = field(default_factory=list)  # epoch-моменты ошибок
    opened_at: Optional[float] = None  # когда перешли в OPEN
    last_failure_msg: str = ""


class CircuitBreaker:
    """Container для всех breaker'ов: один на биржу.

    Используется так:
        cb = CircuitBreaker()
        if cb.is_open("bybit"):
            return None  # не вызываем биржу
        try:
            result = await adapter.get_funding_info(...)
            cb.record_success("bybit")
            return result
        except Exception as exc:
            cb.record_failure("bybit", str(exc))
            return None
    """

    def __init__(
        self,
        window_sec: float = WINDOW_SEC,
        fail_threshold: int = FAIL_THRESHOLD,
        cooldown_sec: float = COOLDOWN_SEC,
    ) -> None:
        self._window = window_sec
        self._threshold = fail_threshold
        self._cooldown = cooldown_sec
        self._states: dict[str, _BreakerState] = {}

    def _state(self, exchange: str) -> _BreakerState:
        key = exchange.lower()
        if key not in self._states:
            self._states[key] = _BreakerState()
        return self._states[key]

    def is_open(self, exchange: str) -> bool:
        """Проверить, заблокирована ли биржа в момент вызова.

        Если breaker был OPEN и cooldown истёк — переводим в HALF_OPEN
        и разрешаем один пробный вызов.
        """
        st = self._state(exchange)
        now = time.time()

        if st.state == "OPEN":
            if st.opened_at and (now - st.opened_at) >= self._cooldown:
                st.state = "HALF_OPEN"
                print(
                    f"[BREAKER] {exchange}: cooldown {self._cooldown:.0f}с "
                    "истёк, переход в HALF_OPEN"
                )
                return False
            return True
        return False

    def record_success(self, exchange: str) -> None:
        """Успешный вызов. В HALF_OPEN — закрываем breaker. В CLOSED — чистим окно."""
        st = self._state(exchange)
        if st.state == "HALF_OPEN":
            print(f"[BREAKER] {exchange}: HALF_OPEN успех, переход в CLOSED")
        st.state = "CLOSED"
        st.failures = []
        st.opened_at = None
        st.last_failure_msg = ""

    def record_failure(self, exchange: str, message: str = "") -> None:
        """Зафиксировать ошибку и, если порог превышен, открыть breaker."""
        st = self._state(exchange)
        now = time.time()
        st.last_failure_msg = message[:200]

        if st.state == "HALF_OPEN":
            # Пробный вызов в HALF_OPEN провалился — снова OPEN.
            st.state = "OPEN"
            st.opened_at = now
            print(
                f"[BREAKER] {exchange}: HALF_OPEN провал — снова OPEN на "
                f"{self._cooldown:.0f}с"
            )
            return

        # Чистим устаревшие записи и добавляем новую.
        cutoff = now - self._window
        st.failures = [t for t in st.failures if t >= cutoff]
        st.failures.append(now)

        if len(st.failures) >= self._threshold and st.state == "CLOSED":
            st.state = "OPEN"
            st.opened_at = now
            print(
                f"[BREAKER] {exchange}: {len(st.failures)} ошибок за "
                f"{self._window:.0f}с — OPEN на {self._cooldown:.0f}с. "
                f"Last: {message[:80]}"
            )

    def status_snapshot(self) -> dict[str, Any]:
        """Снимок состояний всех бирж — для дашборда / Telegram."""
        out: dict[str, Any] = {}
        for ex, st in self._states.items():
            entry = {
                "state": st.state,
                "recent_failures": len(st.failures),
                "last_failure_msg": st.last_failure_msg,
            }
            if st.state == "OPEN" and st.opened_at:
                remaining = max(0.0, self._cooldown - (time.time() - st.opened_at))
                entry["cooldown_remaining_sec"] = int(remaining)
            out[ex] = entry
        return out

    def reset(self, exchange: str) -> None:
        """Принудительный сброс (например, через Telegram-команду)."""
        st = self._state(exchange)
        st.state = "CLOSED"
        st.failures = []
        st.opened_at = None
        print(f"[BREAKER] {exchange}: ручной reset")


# --- Singleton для всего процесса -----------------------------------

_GLOBAL: Optional[CircuitBreaker] = None


def get_breaker() -> CircuitBreaker:
    """Глобальный экземпляр. Конфигурация подгружается лениво из config.py."""
    global _GLOBAL
    if _GLOBAL is None:
        try:
            import config
            _GLOBAL = CircuitBreaker(
                window_sec=float(getattr(config, "BREAKER_WINDOW_SEC", WINDOW_SEC)),
                fail_threshold=int(getattr(config, "BREAKER_FAIL_THRESHOLD", FAIL_THRESHOLD)),
                cooldown_sec=float(getattr(config, "BREAKER_COOLDOWN_SEC", COOLDOWN_SEC)),
            )
        except ImportError:
            _GLOBAL = CircuitBreaker()
    return _GLOBAL
