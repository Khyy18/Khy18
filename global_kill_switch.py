"""Глобальный kill-switch для КОМБО-бота.

Если суммарный drawdown по ВСЕМ стратегиям превышает порог
(GLOBAL_MAX_DRAWDOWN_PCT, по умолчанию 15%) — ВСЕ стратегии
останавливаются:
  - Funding-арб: force-close всех открытых пар.
  - Grid: отмена всех ордеров сетки.
  - Momentum: close всех позиций.

Снятие kill-switch — ТОЛЬКО вручную через Telegram.
"""

from __future__ import annotations

from typing import Any

import capital_allocator
import combo_config as cfg


def check_global_kill(state: dict[str, Any]) -> bool:
    """Проверить условие глобального kill-switch.

    Возвращает True если kill-switch АКТИВИРОВАН (нужна остановка).
    False — всё ОК, торгуем дальше.
    """
    g = state.get("global", {})

    # Если уже активирован — не пересчитываем, ждём ручного снятия.
    if g.get("global_kill_active", False):
        return True

    dd = capital_allocator.get_drawdown_pct(state)
    threshold = cfg.GLOBAL_MAX_DRAWDOWN_PCT

    if dd >= threshold:
        # Активируем kill-switch
        g["global_kill_active"] = True
        equity = capital_allocator.get_current_equity(state)
        hwm = float(g.get("hwm_equity", 0.0))
        g["global_kill_reason"] = (
            f"Drawdown {dd * 100:.1f}% >= порог {threshold * 100:.0f}%. "
            f"Equity: ${equity:.2f}, HWM: ${hwm:.2f}."
        )
        return True

    return False


def is_kill_active(state: dict[str, Any]) -> bool:
    """Активен ли глобальный kill-switch (read-only проверка)."""
    g = state.get("global", {})
    return bool(g.get("global_kill_active", False))


def get_kill_reason(state: dict[str, Any]) -> str:
    """Причина активации kill-switch."""
    g = state.get("global", {})
    return str(g.get("global_kill_reason", ""))


def manual_resume(state: dict[str, Any]) -> str:
    """Ручное снятие kill-switch (через Telegram).

    Возвращает текст подтверждения.
    """
    g = state.get("global", {})
    if not g.get("global_kill_active", False):
        return "Kill-switch не активен, снимать нечего."

    g["global_kill_active"] = False
    g["global_kill_reason"] = ""

    # Обновляем HWM до текущего equity, чтобы не сработал повторно сразу.
    equity = capital_allocator.get_current_equity(state)
    g["hwm_equity"] = equity

    return (
        f"Kill-switch снят. HWM сброшен на текущий equity: ${equity:.2f}. "
        "Стратегии возобновят работу на следующем тике."
    )


def manual_activate(state: dict[str, Any], reason: str = "manual") -> str:
    """Ручная активация kill-switch (через Telegram кнопку PANIC ALL).

    Возвращает текст подтверждения.
    """
    g = state.setdefault("global", {})
    g["global_kill_active"] = True
    g["global_kill_reason"] = f"Ручная активация: {reason}"
    return "Kill-switch активирован вручную. Все стратегии остановлены."


def get_status(state: dict[str, Any]) -> dict[str, Any]:
    """Полная информация о состоянии kill-switch для UI."""
    g = state.get("global", {})
    dd = capital_allocator.get_drawdown_pct(state)
    equity = capital_allocator.get_current_equity(state)
    hwm = float(g.get("hwm_equity", 0.0))
    threshold = cfg.GLOBAL_MAX_DRAWDOWN_PCT

    return {
        "active": bool(g.get("global_kill_active", False)),
        "reason": str(g.get("global_kill_reason", "")),
        "drawdown_pct": dd,
        "threshold_pct": threshold,
        "equity": equity,
        "hwm": hwm,
        "margin_to_kill": max(0.0, threshold - dd),
    }
