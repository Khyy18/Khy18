"""Тесты lending advisor'а — рекомендации Earn-flex для idle USDT.

Проверяем 4 сценария:
  1. На всех биржах idle <= threshold → возвращает None.
  2. На одной бирже свободные средства большие → рекомендует idle USDT.
  3. Активная арб-пара уменьшает margin_in_use, что учтено в idle.
  4. Тот же план не отсылается чаще раз в cooldown (24ч).
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest


def _run(coro):
    return asyncio.run(coro)


def _make_adapter(usdt_balance: float | None) -> MagicMock:
    """Адаптер-мок с настроенным get_balance(USDT)."""
    a = MagicMock()
    a.get_balance = AsyncMock(return_value=usdt_balance)
    return a


def _adapters(balances: dict[str, float | None]) -> dict[str, Any]:
    return {name: _make_adapter(bal) for name, bal in balances.items()}


class TestLendingAdvisorLogic:
    """Голые helper-функции — без сети."""

    def test_no_advice_when_balanced(self, monkeypatch):
        """На всех биржах idle ниже threshold → пустой план."""
        from lending_advisor import _build_lending_plan

        # У всех бирж balance ровно 200 USDT, margin_in_use 0,
        # reserve = max(0.30 * 200, 50) = 60. idle = 200 - 0 - 60 = 140.
        # При threshold = 200 — план пустой (140 < 200).
        balances = {"bybit": 200.0, "okx": 200.0, "binance": 200.0}
        plan = _build_lending_plan(
            balances, margins={}, reserve_pct=0.30,
            min_reserve_usdt=50.0, idle_threshold_usdt=200.0,
        )
        assert plan == []

        # Тот же расклад, но threshold ниже idle → план не пустой
        # (sanity-check, что мы не прошли мимо порога случайно).
        plan2 = _build_lending_plan(
            balances, margins={}, reserve_pct=0.30,
            min_reserve_usdt=50.0, idle_threshold_usdt=100.0,
        )
        assert len(plan2) == 3

    def test_advises_when_idle_above_threshold(self):
        """Одна биржа: free 500, margin 50, reserve_pct 0.10 → reserve 50.
        idle = 500 - 50 - 50 = 400. Порог 100 → план на 400 USDT.
        """
        from lending_advisor import _build_lending_plan

        balances = {"bybit": 500.0}
        margins = {"bybit": 50.0}
        plan = _build_lending_plan(
            balances, margins, reserve_pct=0.10,
            min_reserve_usdt=50.0, idle_threshold_usdt=100.0,
        )
        assert len(plan) == 1
        ex, idle, bal, margin, reserve = plan[0]
        assert ex == "bybit"
        assert idle == pytest.approx(400.0)
        assert bal == pytest.approx(500.0)
        assert margin == pytest.approx(50.0)
        assert reserve == pytest.approx(50.0)

    def test_subtracts_active_margin(self):
        """С активной парой notional=200 leverage=3 → margin_per_leg=66.67.
        Биржа держит ОДНУ ногу, поэтому в margins[bybit] = 66.67.

        balance 500, reserve 50 (10% от 500 = 50, минимум тоже 50).
        idle = 500 - 66.67 - 50 ≈ 383.33. Учёт margin виден по разнице
        с idle без позиции (433.33 при margin=0).
        """
        from lending_advisor import (
            _build_lending_plan,
            _margin_in_use_per_exchange,
        )

        active = [
            {
                "id": 1,
                "symbol": "BTCUSDT",
                "long_exchange": "bybit",
                "short_exchange": "okx",
                "notional_usdt": 200.0,
            }
        ]
        margins = _margin_in_use_per_exchange(active, leverage=3.0)
        # Каждая биржа держит одну ногу с margin 200/3 ≈ 66.67.
        assert margins["bybit"] == pytest.approx(200.0 / 3.0)
        assert margins["okx"] == pytest.approx(200.0 / 3.0)

        balances = {"bybit": 500.0, "okx": 500.0}
        plan = _build_lending_plan(
            balances, margins, reserve_pct=0.10,
            min_reserve_usdt=50.0, idle_threshold_usdt=100.0,
        )
        assert len(plan) == 2
        # Сортировка по убыванию idle: обе биржи одинаковые → любая первая.
        for ex, idle, bal, margin, reserve in plan:
            # idle должен учитывать margin: 500 - 66.67 - 50 ≈ 383.33.
            assert idle == pytest.approx(500.0 - 200.0 / 3.0 - 50.0)
            assert margin == pytest.approx(200.0 / 3.0)


class TestLendingAdvisorAlertCooldown:
    """check_idle_balances — интеграция с моком adapter и notify."""

    def test_cooldown_blocks_repeat(self, monkeypatch):
        """Повторный одинаковый план не отправляется в течение cooldown.

        Сценарий:
          1. Первый прогон → notify вызвался.
          2. Второй прогон с тем же раскладом балансов → notify НЕ
             вызывается, но check_idle_balances всё равно возвращает план.
        """
        import lending_advisor
        import config

        monkeypatch.setattr(config, "LENDING_ALERT_COOLDOWN_SEC", 24 * 3600.0, raising=False)
        monkeypatch.setattr(config, "LENDING_IDLE_THRESHOLD_USDT", 100.0, raising=False)
        monkeypatch.setattr(config, "LENDING_RESERVE_PCT", 0.10, raising=False)
        monkeypatch.setattr(config, "LENDING_MIN_RESERVE_USDT", 50.0, raising=False)
        monkeypatch.setattr(config, "ARB_LEVERAGE", 3.0, raising=False)

        # Адаптеры с большими балансами → план гарантированно есть.
        adapters = _adapters({
            "bybit": 500.0,
            "okx": 400.0,
        })

        # Подмена arb_storage.get_all_active(), чтобы не лезть в БД.
        monkeypatch.setattr(
            "arb_storage.get_all_active", lambda: [], raising=False,
        )

        notify_calls: list[str] = []

        async def _notify(text: str) -> None:
            notify_calls.append(text)

        state: dict[str, Any] = {}

        # Первый прогон — notify должен сработать.
        plan1 = _run(lending_advisor.check_idle_balances(
            MagicMock(), adapters, _notify, state,
        ))
        assert plan1, "первый план должен быть не пустой"
        assert len(notify_calls) == 1, "notify должен вызваться один раз"

        # Второй прогон — расклад тот же. notify НЕ должен сработать.
        plan2 = _run(lending_advisor.check_idle_balances(
            MagicMock(), adapters, _notify, state,
        ))
        assert plan2, "второй план тоже не пустой"
        assert len(notify_calls) == 1, (
            f"повторный одинаковый план должен быть подавлен cooldown, "
            f"got {len(notify_calls)} notify calls"
        )

    def test_returns_none_when_all_below_threshold(self, monkeypatch):
        """Если у всех бирж idle <= threshold, check_idle_balances → None."""
        import lending_advisor
        import config

        # Высокий threshold → ни одна биржа не пройдёт.
        monkeypatch.setattr(config, "LENDING_IDLE_THRESHOLD_USDT", 10000.0, raising=False)
        monkeypatch.setattr(config, "LENDING_RESERVE_PCT", 0.30, raising=False)
        monkeypatch.setattr(config, "LENDING_MIN_RESERVE_USDT", 50.0, raising=False)

        adapters = _adapters({"bybit": 200.0, "okx": 200.0})

        monkeypatch.setattr(
            "arb_storage.get_all_active", lambda: [], raising=False,
        )

        notify_calls: list[str] = []

        async def _notify(text: str) -> None:
            notify_calls.append(text)

        state: dict[str, Any] = {}
        result = _run(lending_advisor.check_idle_balances(
            MagicMock(), adapters, _notify, state,
        ))

        assert result is None, f"ожидаем None, got {result}"
        assert notify_calls == [], "notify не должен вызываться"
