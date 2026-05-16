"""Глобальный singleton state для модулей, которым нужно читать state без передачи.

Используется, когда расширение сигнатур функций нежелательно: например,
``arb_executor.evaluate_and_open`` уже имеет много параметров, и таскать
``state`` через все слои было бы шумно. Вместо этого main выставляет state
один раз при старте через :func:`set_state`, а слои-потребители читают
его через :func:`get_state` (возвращает ``state["global"]``).

В тестах модуль может оставаться в дефолтном (пустом) состоянии —
``get_state`` тогда вернёт ``None``, и потребитель должен корректно это
обработать (graceful fallback).
"""

from __future__ import annotations

from typing import Any, Optional

# Полный state бота (тот же dict, что собирается в main._build_state()).
_STATE: Optional[dict[str, Any]] = None


def set_state(state: dict[str, Any]) -> None:
    """Запомнить ссылку на глобальный state. Вызывается один раз из main()."""
    global _STATE
    _STATE = state


def get_state() -> Optional[dict[str, Any]]:
    """Вернуть подсловарь ``state["global"]`` или ``None``, если не выставлен.

    Возврат именно "global"-секции — соглашение всех существующих
    модулей-потребителей (heartbeat, anomaly, announcement_monitor),
    они работают со словарём global-флагов, а не с корневым state.
    """
    if _STATE is None:
        return None
    try:
        return _STATE.get("global")
    except AttributeError:
        return None


def reset() -> None:
    """Сброс для тестов."""
    global _STATE
    _STATE = None
