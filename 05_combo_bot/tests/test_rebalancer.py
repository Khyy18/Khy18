"""Тесты rebalancer'а — monitoring + advisor балансов USDT.

Проверяем 4 сценария:
  1. Балансы в пределах ±10% от target → план пустой, None.
  2. Один баланс сильно ниже остальных → рекомендуется конкретный transfer.
  3. Мелкие переводы (< MIN_TRANSFER_USDT) фильтруются.
  4. Тот же план не отсылается чаще раз в cooldown.
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
    """Из словаря {имя_биржи: баланс} собрать словарь адаптеров."""
    return {name: _make_adapter(bal) for name, bal in balances.items()}


class TestRebalancerLogic:
    """Голая функция _build_transfer_plan — без сети, без notify."""

    def test_no_recommendation_when_balanced(self):
        """Все ±10% от target — пустой план, потому что не превышен порог 30%."""
        from rebalancer import _build_transfer_plan

        balances = {
            "bybit": 240.0,    # +4% от 230
            "okx": 220.0,      # -4%
            "binance": 250.0,  # +9%
            "bitget": 210.0,   # -9%
        }
        plan = _build_transfer_plan(balances, threshold_pct=0.30, min_transfer_usdt=50.0)
        assert plan == []

    def test_recommends_transfer_on_skew(self):
        """Один баланс 50, остальные 250 → рекомендация transfer 200 USDT
        в пустую биржу из самой жирной.
        """
        from rebalancer import _build_transfer_plan

        balances = {
            "okx": 250.0,
            "binance": 250.0,
            "bybit": 250.0,
            "bitget": 50.0,    # сильно пустая
        }
        # total=800, target=200. dev(bitget)=-75% > 30% → план не пуст.
        plan = _build_transfer_plan(balances, threshold_pct=0.30, min_transfer_usdt=50.0)

        assert plan, f"ожидался план переводов, got {plan}"
        # Получатель — всегда bitget (самая пустая).
        assert all(t[1] == "bitget" for t in plan), plan
        # Суммарно переводим 150 USDT (deficit bitget = 200 - 50 = 150).
        total_transferred = sum(t[2] for t in plan)
        assert total_transferred == pytest.approx(150.0)
        # Первая рекомендация — из самой жирной (excess одинаковый,
        # любая из okx/binance/bybit подойдёт), на bitget, ~50.
        first_from, first_to, first_amount = plan[0]
        assert first_to == "bitget"
        assert first_from in {"okx", "binance", "bybit"}
        assert first_amount > 0

    def test_min_transfer_filter(self):
        """Если жадный алгоритм нагенерил перевод < MIN_TRANSFER_USDT,
        он должен быть отброшен."""
        from rebalancer import _build_transfer_plan

        # У bitget дефицит ровно 60 USDT, у двух жирных — по 30 на каждой.
        # Если порог 50, то 30 + 30 не пройдут (каждый < 50).
        balances = {
            "okx": 230.0,      # +30 excess
            "binance": 230.0,  # +30 excess
            "bybit": 200.0,    # ровно target
            "bitget": 140.0,   # -60 deficit
        }
        # total=800, target=200.
        # dev(bitget) = -30% — на границе порога. Чтобы _build_transfer_plan
        # перешёл в построение плана, опускаем threshold чуть ниже.
        plan = _build_transfer_plan(balances, threshold_pct=0.25, min_transfer_usdt=50.0)
        # Каждый предложенный transfer был бы 30 USDT (< 50) → не добавлен.
        # Алгоритм ничего не возвращает.
        assert plan == [], f"мелкие (<50) переводы не должны попадать в план, got {plan}"

        # А если опустить порог до 25 — переводы в 30 USDT уже проходят.
        plan2 = _build_transfer_plan(balances, threshold_pct=0.25, min_transfer_usdt=25.0)
        assert plan2, "при min_transfer=25 план должен сформироваться"
        for from_ex, to_ex, amount in plan2:
            assert amount >= 25.0


class TestRebalancerAlertCooldown:
    """check_and_alert — интеграционный тест с мокнутыми adapter и notify."""

    def test_alert_cooldown(self, monkeypatch):
        """Повторный одинаковый план не отправляется в течение cooldown.

        Сценарий:
          1. Первый прогон → notify вызвался.
          2. Второй прогон с тем же раскладом балансов → notify НЕ
             вызывается, но check_and_alert всё равно возвращает план
             (для отладки/UI).
        """
        import rebalancer
        import config

        # Большой cooldown, чтобы второй вызов точно попал в "ещё не пора".
        monkeypatch.setattr(config, "REBALANCE_ALERT_COOLDOWN_SEC", 6 * 3600.0, raising=False)
        monkeypatch.setattr(config, "REBALANCE_THRESHOLD_PCT", 0.30, raising=False)
        monkeypatch.setattr(config, "REBALANCE_MIN_TRANSFER_USDT", 50.0, raising=False)

        adapters = _adapters({
            "okx": 250.0,
            "binance": 250.0,
            "bybit": 250.0,
            "bitget": 50.0,
        })

        notify_calls: list[str] = []

        async def _notify(text: str) -> None:
            notify_calls.append(text)

        state: dict[str, Any] = {}

        # Первый прогон — должен сработать.
        plan1 = _run(rebalancer.check_and_alert(
            MagicMock(), adapters, _notify, state,
        ))
        assert plan1, "первый план должен быть не пустой"
        assert len(notify_calls) == 1, "notify должен вызваться один раз"

        # Второй прогон — тот же расклад. notify НЕ должен сработать.
        plan2 = _run(rebalancer.check_and_alert(
            MagicMock(), adapters, _notify, state,
        ))
        assert plan2, "второй план тоже не пустой (расклад не поменялся)"
        assert len(notify_calls) == 1, (
            f"повторный одинаковый план должен быть подавлен cooldown, "
            f"got {len(notify_calls)} notify calls"
        )

    def test_alert_not_sent_when_balanced(self, monkeypatch):
        """Если все биржи в пределах threshold, notify не вызывается
        и check_and_alert возвращает None."""
        import rebalancer
        import config

        monkeypatch.setattr(config, "REBALANCE_THRESHOLD_PCT", 0.30, raising=False)
        monkeypatch.setattr(config, "REBALANCE_MIN_TRANSFER_USDT", 50.0, raising=False)

        adapters = _adapters({
            "bybit": 240.0,
            "okx": 220.0,
            "binance": 250.0,
            "bitget": 210.0,
        })

        notify_calls: list[str] = []

        async def _notify(text: str) -> None:
            notify_calls.append(text)

        state: dict[str, Any] = {}
        result = _run(rebalancer.check_and_alert(
            MagicMock(), adapters, _notify, state,
        ))

        assert result is None, f"при сбалансированных биржах ожидаем None, got {result}"
        assert notify_calls == [], "notify не должен вызываться"

    def test_alert_skips_unavailable_exchanges(self, monkeypatch):
        """Биржи, у которых get_balance вернул None, в расчёте не участвуют."""
        import rebalancer
        import config

        monkeypatch.setattr(config, "REBALANCE_THRESHOLD_PCT", 0.30, raising=False)
        monkeypatch.setattr(config, "REBALANCE_MIN_TRANSFER_USDT", 50.0, raising=False)
        monkeypatch.setattr(config, "REBALANCE_ALERT_COOLDOWN_SEC", 6 * 3600.0, raising=False)

        # mexc возвращает None — должен быть выкинут из расчёта.
        adapters = _adapters({
            "okx": 250.0,
            "binance": 250.0,
            "bybit": 250.0,
            "bitget": 50.0,
            "mexc": None,
        })

        notify_calls: list[str] = []

        async def _notify(text: str) -> None:
            notify_calls.append(text)

        state: dict[str, Any] = {}
        plan = _run(rebalancer.check_and_alert(
            MagicMock(), adapters, _notify, state,
        ))

        assert plan, "план должен сформироваться по 4 рабочим биржам"
        # mexc не должен фигурировать в списке переводов.
        for from_ex, to_ex, _ in plan:
            assert from_ex != "mexc" and to_ex != "mexc", plan
        # Текст алерта тоже не должен упоминать mexc.
        assert notify_calls
        assert "mexc" not in notify_calls[0]
