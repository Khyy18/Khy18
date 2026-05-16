"""Тесты для reconcile-логики и связанных доработок:
  - main._reconcile_arb_positions: сверка БД и реальных позиций на биржах.
  - arb_executor._compute_qty_base: применение slippage_buffer.
  - exchanges.{okx,binance}.get_funding_history: корректная сигнатура.
"""

from __future__ import annotations

import asyncio
import inspect
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Хелпер для запуска корутин в синхронных тестах.
# ---------------------------------------------------------------------------

def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro) if False else asyncio.run(coro)


# ---------------------------------------------------------------------------
# Reconcile tests.
# ---------------------------------------------------------------------------

class TestReconcileArbPositions:
    """Сверка локальной БД и реальных позиций на 8 биржах."""

    def _fake_position(self, **overrides: Any) -> dict[str, Any]:
        """Пара по умолчанию: BTCUSDT LONG@bybit / SHORT@okx, qty=0.01."""
        base = {
            "id": 1,
            "symbol": "BTCUSDT",
            "qty_base": 0.01,
            "long_exchange": "bybit",
            "short_exchange": "okx",
            "status": "OPEN",
        }
        base.update(overrides)
        return base

    def test_reconcile_finds_missing_position(self, monkeypatch):
        """Если в БД пара есть, а на бирже позиции нет — должен быть
        вызван arb_storage.mark_failed с reason position_missing_on_exchange.
        """
        import main

        pos = self._fake_position()
        # Мокаем БД: одна активная пара.
        monkeypatch.setattr(
            main.arb_storage, "get_all_active", lambda: [pos]
        )

        # Мокаем mark_failed — следим что вызывался.
        mark_failed_calls: list[tuple] = []
        monkeypatch.setattr(
            main.arb_storage, "mark_failed",
            lambda arb_id, reason: mark_failed_calls.append((arb_id, reason)),
        )

        # Адаптер: get_positions всегда возвращает [] (биржа не имеет позиции).
        empty_adapter = MagicMock()
        empty_adapter.get_positions = AsyncMock(return_value=[])

        monkeypatch.setattr(
            main, "_FUNDING_ADAPTERS",
            {"bybit": empty_adapter, "okx": empty_adapter},
        )

        # Мокаем telegram, чтобы не тыкаться в сеть.
        monkeypatch.setattr(
            main.telegram_bot, "send_message",
            AsyncMock(return_value=None),
        )

        # state не используется внутри reconcile, но передаётся.
        state = {"global": {}}
        _run(main._reconcile_arb_positions(MagicMock(), state))

        # Должно быть минимум одно mark_failed с правильным reason.
        assert len(mark_failed_calls) >= 1, "mark_failed должен быть вызван"
        arb_id, reason = mark_failed_calls[0]
        assert arb_id == 1
        assert reason.startswith("position_missing_on_exchange:"), reason

    def test_reconcile_qty_mismatch_warns(self, monkeypatch):
        """Если позиция на бирже есть, но qty отличается на 5% —
        должен быть warning (telegram), но БЕЗ mark_failed.
        """
        import main

        pos = self._fake_position(qty_base=0.01)
        monkeypatch.setattr(
            main.arb_storage, "get_all_active", lambda: [pos]
        )

        mark_failed_calls: list[tuple] = []
        monkeypatch.setattr(
            main.arb_storage, "mark_failed",
            lambda arb_id, reason: mark_failed_calls.append((arb_id, reason)),
        )

        # Адаптеры: возвращают позицию с qty 0.0105 — это +5% от 0.01,
        # больше допуска 1%.
        long_adapter = MagicMock()
        long_adapter.get_positions = AsyncMock(return_value=[
            {"side": "Buy", "size": 0.0105, "symbol": "BTCUSDT"},
        ])
        short_adapter = MagicMock()
        short_adapter.get_positions = AsyncMock(return_value=[
            {"side": "Sell", "size": 0.0105, "symbol": "BTCUSDT"},
        ])

        monkeypatch.setattr(
            main, "_FUNDING_ADAPTERS",
            {"bybit": long_adapter, "okx": short_adapter},
        )

        tg_calls: list[str] = []

        async def _send_message(_session, text, **_kwargs):
            tg_calls.append(text)
            return None

        monkeypatch.setattr(main.telegram_bot, "send_message", _send_message)

        state = {"global": {}}
        _run(main._reconcile_arb_positions(MagicMock(), state))

        # mark_failed НЕ должен был сработать — это лишь warn.
        assert mark_failed_calls == [], (
            f"mark_failed не должен вызываться при qty-mismatch, "
            f"got: {mark_failed_calls}"
        )
        # Должен быть хотя бы один warning в Telegram.
        warns = [t for t in tg_calls if "warning" in t.lower() or "mismatch" in t.lower()]
        assert warns, f"ожидался warning в Telegram, all calls: {tg_calls}"

    def test_reconcile_empty_db_does_nothing(self, monkeypatch):
        """Если БД пуста, ни одного RPC и ни одного алерта быть не должно."""
        import main

        monkeypatch.setattr(main.arb_storage, "get_all_active", lambda: [])

        mark_failed_calls: list[tuple] = []
        monkeypatch.setattr(
            main.arb_storage, "mark_failed",
            lambda arb_id, reason: mark_failed_calls.append((arb_id, reason)),
        )

        adapter = MagicMock()
        adapter.get_positions = AsyncMock(return_value=[])
        monkeypatch.setattr(
            main, "_FUNDING_ADAPTERS",
            {"bybit": adapter, "okx": adapter},
        )

        tg_calls: list[str] = []

        async def _send_message(_session, text, **_kwargs):
            tg_calls.append(text)
            return None

        monkeypatch.setattr(main.telegram_bot, "send_message", _send_message)

        _run(main._reconcile_arb_positions(MagicMock(), {"global": {}}))

        assert mark_failed_calls == []
        assert tg_calls == []
        # И ни одного RPC к адаптерам.
        adapter.get_positions.assert_not_awaited()


# ---------------------------------------------------------------------------
# Slippage buffer test.
# ---------------------------------------------------------------------------

class TestSlippageBufferReducesQty:
    """_compute_qty_base должен уменьшать qty_target на slippage_buffer
    до валидации, так что итоговый qty будет на ~buffer% меньше."""

    def test_slippage_buffer_reduces_qty(self):
        import arb_executor as ae

        # Адаптеры с identity validate_and_round_qty (без округления).
        identity = MagicMock()
        identity.validate_and_round_qty = MagicMock(side_effect=lambda q, *a, **kw: q)

        notional = 1000.0
        mark = 100.0  # qty_target без буфера = 10.0
        info = {"min_qty": 0.0, "qty_step": 0.0, "min_notional": 0.0}

        qty_no_buffer = ae._compute_qty_base(
            notional, mark, info, info, identity, identity,
            slippage_buffer=0.0,
        )
        qty_with_buffer = ae._compute_qty_base(
            notional, mark, info, info, identity, identity,
            slippage_buffer=0.001,  # 0.1%
        )

        # Без буфера: ровно 10.0.
        assert qty_no_buffer == pytest.approx(10.0)
        # С буфером 0.1%: ровно 10.0 * 0.999 = 9.99.
        assert qty_with_buffer == pytest.approx(9.99)
        # И главное — со включённым буфером значение МЕНЬШЕ.
        assert qty_with_buffer < qty_no_buffer

    def test_slippage_buffer_default_from_config(self, monkeypatch):
        """Если slippage_buffer не передан — должен браться из config.ARB_SLIPPAGE_BUFFER."""
        import arb_executor as ae
        import config

        monkeypatch.setattr(config, "ARB_SLIPPAGE_BUFFER", 0.01, raising=False)

        identity = MagicMock()
        identity.validate_and_round_qty = MagicMock(side_effect=lambda q, *a, **kw: q)

        info = {"min_qty": 0.0, "qty_step": 0.0, "min_notional": 0.0}
        # notional=1000, mark=100 → qty_target=10. С buffer=0.01 → 9.9.
        qty = ae._compute_qty_base(
            1000.0, 100.0, info, info, identity, identity,
        )
        assert qty == pytest.approx(9.9)

    def test_slippage_buffer_invalid_treated_as_zero(self):
        """Отрицательный/слишком большой буфер интерпретируем как 0
        (защита от мусора в env)."""
        import arb_executor as ae

        identity = MagicMock()
        identity.validate_and_round_qty = MagicMock(side_effect=lambda q, *a, **kw: q)

        info = {"min_qty": 0.0, "qty_step": 0.0, "min_notional": 0.0}
        qty_neg = ae._compute_qty_base(
            1000.0, 100.0, info, info, identity, identity,
            slippage_buffer=-0.5,
        )
        qty_huge = ae._compute_qty_base(
            1000.0, 100.0, info, info, identity, identity,
            slippage_buffer=1.5,
        )
        assert qty_neg == pytest.approx(10.0)
        assert qty_huge == pytest.approx(10.0)


# ---------------------------------------------------------------------------
# Funding history signature tests.
# ---------------------------------------------------------------------------

class TestFundingHistorySignatures:
    """Проверяем что новые get_funding_history методы OKX/Binance имеют
    корректную сигнатуру и совпадают с базовой схемой ExchangeAdapter."""

    def test_okx_get_funding_history_signature(self):
        from exchanges.okx import OKXAdapter

        sig = inspect.signature(OKXAdapter.get_funding_history)
        params = list(sig.parameters.keys())
        # self, session, symbol, since_ms, limit
        assert params == ["self", "session", "symbol", "since_ms", "limit"], params
        # since_ms по умолчанию None, limit по умолчанию число.
        assert sig.parameters["since_ms"].default is None
        assert isinstance(sig.parameters["limit"].default, int)
        assert inspect.iscoroutinefunction(OKXAdapter.get_funding_history)

    def test_binance_get_funding_history_signature(self):
        from exchanges.binance import BinanceAdapter

        sig = inspect.signature(BinanceAdapter.get_funding_history)
        params = list(sig.parameters.keys())
        assert params == ["self", "session", "symbol", "since_ms", "limit"], params
        assert sig.parameters["since_ms"].default is None
        assert isinstance(sig.parameters["limit"].default, int)
        assert inspect.iscoroutinefunction(BinanceAdapter.get_funding_history)

    def test_okx_returns_empty_on_error(self, monkeypatch):
        """Если _request вернул не-успех, get_funding_history отдаёт []."""
        from exchanges.okx import OKXAdapter

        adapter = OKXAdapter()
        adapter._request = AsyncMock(return_value=None)

        result = _run(adapter.get_funding_history(MagicMock(), "BTCUSDT"))
        assert result == []

    def test_binance_returns_empty_on_error(self, monkeypatch):
        """Если _get вернул dict с ошибкой, get_funding_history отдаёт []."""
        from exchanges.binance import BinanceAdapter

        adapter = BinanceAdapter()
        adapter._get = AsyncMock(return_value={"code": -1, "msg": "fail"})

        result = _run(adapter.get_funding_history(MagicMock(), "BTCUSDT"))
        assert result == []

    def test_okx_parses_response(self):
        """OKX: ответ {data: [{ts, instId, pnl}]} парсится в нужную схему."""
        from exchanges.okx import OKXAdapter

        adapter = OKXAdapter()
        adapter._request = AsyncMock(return_value={
            "code": "0",
            "data": [
                {"ts": "1700000000000", "instId": "BTC-USDT-SWAP", "pnl": "0.123"},
                {"ts": "1700001000000", "instId": "BTC-USDT-SWAP", "pnl": "-0.05"},
            ],
        })
        result = _run(adapter.get_funding_history(MagicMock(), "BTCUSDT"))
        assert len(result) == 2
        assert result[0] == {"symbol": "BTCUSDT", "ts": 1700000000000, "funding": 0.123}
        assert result[1]["funding"] == pytest.approx(-0.05)

    def test_binance_parses_response(self):
        """Binance: ответ list[{time, symbol, income}] парсится в нужную схему."""
        from exchanges.binance import BinanceAdapter

        adapter = BinanceAdapter()
        adapter._get = AsyncMock(return_value=[
            {"time": 1700000000000, "symbol": "BTCUSDT", "income": "0.42"},
            {"time": 1700001000000, "symbol": "BTCUSDT", "income": "-0.11"},
        ])
        result = _run(adapter.get_funding_history(MagicMock(), "BTCUSDT"))
        assert len(result) == 2
        assert result[0]["symbol"] == "BTCUSDT"
        assert result[0]["ts"] == 1700000000000
        assert result[0]["funding"] == pytest.approx(0.42)
        assert result[1]["funding"] == pytest.approx(-0.11)
