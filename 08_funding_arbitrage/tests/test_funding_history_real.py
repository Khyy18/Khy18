"""Тесты для real funding-PnL по всем биржам и maker-only mode.

1. test_all_adapters_have_get_funding_history — у всех зарегистрированных
   адаптеров метод существует и является корутиной.
2. test_get_funding_history_returns_list_on_failure — при ошибке session
   метод возвращает [], а не исключение.
3. test_maker_only_returns_none_on_timeout — мокаем session так, чтобы
   limit-ордер никогда не filled. place_maker_only_with_repeg должен
   вернуть None и не уйти в Market IOC.
4. test_maker_only_skipped_for_reduce_only — при reduce_only=True
   адаптер использует обычный fallback, а не maker-only (даже если
   ARB_MAKER_ONLY_ENABLED=True).
"""

from __future__ import annotations

import asyncio
import inspect
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _run(coro: Any) -> Any:
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# 1. Все адаптеры имеют get_funding_history.
# ---------------------------------------------------------------------------

class TestAllAdaptersHaveGetFundingHistory:
    """Проверяем что у всех зарегистрированных адаптеров метод есть и он
    корутина с ожидаемой сигнатурой (self, session, symbol, since_ms, limit)."""

    def test_all_adapters_have_get_funding_history(self):
        from exchanges import _REGISTRY

        # Должно быть 8 бирж (bybit, okx, binance, gate, bitget, mexc, htx, bingx).
        assert len(_REGISTRY) >= 8, f"в реестре биржи: {sorted(_REGISTRY.keys())}"
        for name, cls in _REGISTRY.items():
            assert hasattr(cls, "get_funding_history"), (
                f"{name}: нет метода get_funding_history"
            )
            method = getattr(cls, "get_funding_history")
            assert inspect.iscoroutinefunction(method), (
                f"{name}: get_funding_history не корутина"
            )
            sig = inspect.signature(method)
            params = list(sig.parameters.keys())
            assert params == ["self", "session", "symbol", "since_ms", "limit"], (
                f"{name}: неверная сигнатура {params}"
            )
            assert sig.parameters["since_ms"].default is None, (
                f"{name}: since_ms должен по умолчанию быть None"
            )
            assert isinstance(sig.parameters["limit"].default, int), (
                f"{name}: limit должен быть int по умолчанию"
            )


# ---------------------------------------------------------------------------
# 2. На ошибку каждый адаптер возвращает [], а не исключение.
# ---------------------------------------------------------------------------

class TestGetFundingHistoryReturnsListOnFailure:
    """Если HTTP-вызов возвращает None или dict с ошибкой - метод
    отдаёт [], а не пробрасывает исключение."""

    def test_gate_returns_empty_on_error(self):
        from exchanges.gate import GateAdapter

        adapter = GateAdapter()
        adapter._get = AsyncMock(return_value={"label": "INVALID_KEY"})
        result = _run(adapter.get_funding_history(MagicMock(), "BTCUSDT"))
        assert result == []

    def test_bitget_returns_empty_on_error(self):
        from exchanges.bitget import BitgetAdapter

        adapter = BitgetAdapter()
        adapter._get = AsyncMock(return_value={"code": "40001", "msg": "fail"})
        result = _run(adapter.get_funding_history(MagicMock(), "BTCUSDT"))
        assert result == []

    def test_mexc_returns_empty_on_error(self):
        from exchanges.mexc import MEXCAdapter

        adapter = MEXCAdapter()
        adapter._get = AsyncMock(return_value={"success": False, "message": "bad"})
        result = _run(adapter.get_funding_history(MagicMock(), "BTCUSDT"))
        assert result == []

    def test_htx_returns_empty_on_error(self):
        from exchanges.htx import HTXAdapter

        adapter = HTXAdapter()
        adapter._post = AsyncMock(return_value={"status": "error", "err_msg": "x"})
        result = _run(adapter.get_funding_history(MagicMock(), "BTCUSDT"))
        assert result == []

    def test_bingx_returns_empty_on_error(self):
        from exchanges.bingx import BingXAdapter

        adapter = BingXAdapter()
        adapter._get = AsyncMock(return_value={"code": -1, "msg": "fail"})
        result = _run(adapter.get_funding_history(MagicMock(), "BTCUSDT"))
        assert result == []

    def test_gate_returns_empty_on_none(self):
        from exchanges.gate import GateAdapter

        adapter = GateAdapter()
        adapter._get = AsyncMock(return_value=None)
        result = _run(adapter.get_funding_history(MagicMock(), "BTCUSDT"))
        assert result == []

    def test_bingx_parses_response(self):
        """BingX: нормальный ответ парсится в {symbol, ts, funding}."""
        from exchanges.bingx import BingXAdapter

        adapter = BingXAdapter()
        adapter._get = AsyncMock(return_value={
            "code": 0,
            "data": [
                {"time": 1700000000000, "symbol": "BTC-USDT", "income": "0.42"},
                {"time": 1700001000000, "symbol": "BTC-USDT", "income": "-0.11"},
            ],
        })
        result = _run(adapter.get_funding_history(MagicMock(), "BTCUSDT"))
        assert len(result) == 2
        assert result[0]["ts"] == 1700000000000
        assert result[0]["funding"] == pytest.approx(0.42)
        assert result[1]["funding"] == pytest.approx(-0.11)


# ---------------------------------------------------------------------------
# 3. Maker-only возвращает None при timeout (никаких Market IOC).
# ---------------------------------------------------------------------------

class TestMakerOnlyReturnsNoneOnTimeout:
    """place_maker_only_with_repeg никогда не fall-back'ает в market.
    Если за timeout не filled - возвращает None."""

    def test_maker_only_returns_none_on_timeout(self, monkeypatch):
        import api_engine
        import config

        # Сжимаем timeout до 0.3с и интервал до 0.05с — тест должен пройти быстро.
        monkeypatch.setattr(config, "ARB_MAKER_ONLY_TIMEOUT_SEC", 0.3, raising=False)
        monkeypatch.setattr(config, "ARB_MAKER_PEG_INTERVAL_SEC", 0.05, raising=False)
        monkeypatch.setattr(config, "ARB_MAKER_REPEG_THRESHOLD_TICKS", 5, raising=False)

        # instrument_info_cached: возвращаем фиктивный info с tickSize.
        async def fake_info(_session, _symbol):
            return {"tickSize": 0.1, "qtyStep": 0.001, "minOrderQty": 0.001,
                    "minNotionalValue": 0.0}

        # get_orderbook_top: всегда отдаёт стабильный стакан.
        async def fake_top(_session, _symbol):
            return (100.0, 100.2)

        # place_post_only_limit: успешно размещает ордер id=ORDER_X.
        async def fake_place(_session, **_kwargs):
            return {
                "retCode": 0,
                "retMsg": "OK",
                "result": {"orderId": "ORDER_X"},
            }

        # get_open_orders: ордер ВСЕГДА всё ещё активен — никогда не filled.
        async def fake_open(_session, _symbol):
            return [{"orderId": "ORDER_X", "price": "99.9"}]

        # cancel_order: успешно.
        cancel_calls: list[str] = []

        async def fake_cancel(_session, _symbol, order_id):
            cancel_calls.append(order_id)
            return {"retCode": 0}

        monkeypatch.setattr(api_engine, "instrument_info_cached", fake_info)
        monkeypatch.setattr(api_engine, "get_orderbook_top", fake_top)
        monkeypatch.setattr(api_engine, "place_post_only_limit", fake_place)
        monkeypatch.setattr(api_engine, "get_open_orders", fake_open)
        monkeypatch.setattr(api_engine, "cancel_order", fake_cancel)

        # Не должны вызываться - стал бы taker'ом.
        market_calls: list[Any] = []

        async def fake_market(_session, **kwargs):
            market_calls.append(kwargs)
            return {"retCode": 0, "result": {"orderId": "MARKET_X"}}

        monkeypatch.setattr(api_engine, "place_market_order", fake_market)

        result = _run(api_engine.place_maker_only_with_repeg(
            MagicMock(), symbol="BTCUSDT", side="Buy", qty=0.01,
        ))
        # Главные инварианты:
        assert result is None, "maker-only должен вернуть None при timeout"
        assert "ORDER_X" in cancel_calls, "висящий ордер должен быть отменён"
        assert market_calls == [], "maker-only НИКОГДА не должен делать Market IOC"

    def test_maker_only_returns_filled_when_order_disappears_with_executions(
        self, monkeypatch
    ):
        """Если ордер исчезает из open_orders и в execution history есть
        заполненные сделки — maker-only возвращает result с fill_price/qty."""
        import api_engine
        import config

        monkeypatch.setattr(config, "ARB_MAKER_ONLY_TIMEOUT_SEC", 1.0, raising=False)
        monkeypatch.setattr(config, "ARB_MAKER_PEG_INTERVAL_SEC", 0.05, raising=False)

        async def fake_info(_s, _sym):
            return {"tickSize": 0.1}

        async def fake_top(_s, _sym):
            return (100.0, 100.2)

        async def fake_place(_s, **_kw):
            return {"retCode": 0, "result": {"orderId": "ORDER_FILLED"}}

        # Первый раз - ордер активен, второй раз - исчез.
        call_count = {"n": 0}

        async def fake_open(_s, _sym):
            call_count["n"] += 1
            if call_count["n"] >= 2:
                return []  # ордер исчез
            return [{"orderId": "ORDER_FILLED"}]

        async def fake_execs(_s, _sym, _oid, limit=10):
            return [{"execQty": "0.01", "execPrice": "100.0"}]

        async def fake_cancel(_s, _sym, _oid):
            return {"retCode": 0}

        async def fake_set_stop(*_a, **_kw):
            return None

        async def fake_market(_s, **_kw):
            raise AssertionError("market не должен вызываться в maker-only")

        monkeypatch.setattr(api_engine, "instrument_info_cached", fake_info)
        monkeypatch.setattr(api_engine, "get_orderbook_top", fake_top)
        monkeypatch.setattr(api_engine, "place_post_only_limit", fake_place)
        monkeypatch.setattr(api_engine, "get_open_orders", fake_open)
        monkeypatch.setattr(api_engine, "get_execution_history", fake_execs)
        monkeypatch.setattr(api_engine, "cancel_order", fake_cancel)
        monkeypatch.setattr(api_engine, "set_trading_stop", fake_set_stop)
        monkeypatch.setattr(api_engine, "place_market_order", fake_market)

        result = _run(api_engine.place_maker_only_with_repeg(
            MagicMock(), symbol="BTCUSDT", side="Buy", qty=0.01,
        ))
        assert result is not None
        assert result.get("retCode") == 0
        assert result.get("fill_price") == pytest.approx(100.0)
        assert result.get("fill_qty") == pytest.approx(0.01)


# ---------------------------------------------------------------------------
# 4. Maker-only skipped for reduce_only.
# ---------------------------------------------------------------------------

class TestMakerOnlySkippedForReduceOnly:
    """Когда ARB_MAKER_ONLY_ENABLED=True и reduce_only=True - адаптер
    должен использовать обычный place_order_with_fallback (PostOnly→IOC),
    а не maker-only. Это критично: закрытие позиции должно завершиться
    быстро, иначе сработают margin guard / time-stop."""

    def test_close_uses_standard_fallback_even_with_maker_enabled(
        self, monkeypatch
    ):
        import api_engine
        import config
        from exchanges.bybit import BybitAdapter

        monkeypatch.setattr(config, "ARB_MAKER_ONLY_ENABLED", True, raising=False)

        # Шпион на оба пути: обычный fallback и maker-only.
        fallback_calls: list[dict[str, Any]] = []
        maker_calls: list[dict[str, Any]] = []

        async def fake_fallback(_s, **kw):
            fallback_calls.append(kw)
            return {"retCode": 0, "result": {"orderId": "STD_X"},
                    "fill_price": 100.0, "fill_qty": 0.01}

        async def fake_maker(_s, **kw):
            maker_calls.append(kw)
            return {"retCode": 0, "result": {"orderId": "MAKER_X"}}

        monkeypatch.setattr(api_engine, "place_order_with_fallback", fake_fallback)
        monkeypatch.setattr(api_engine, "place_maker_only_with_repeg", fake_maker)

        adapter = BybitAdapter()

        # 1. reduce_only=True должно использовать обычный fallback (НЕ maker-only).
        result_close = _run(adapter.place_order_with_fallback(
            MagicMock(), symbol="BTCUSDT", side="Sell", qty=0.01, reduce_only=True,
        ))
        assert result_close is not None
        assert len(fallback_calls) == 1, "close должен вызвать обычный fallback"
        assert len(maker_calls) == 0, "close НИКОГДА не должен идти через maker-only"
        assert fallback_calls[0]["reduce_only"] is True

        # 2. reduce_only=False (открытие) - наоборот, должно идти в maker-only.
        result_open = _run(adapter.place_order_with_fallback(
            MagicMock(), symbol="BTCUSDT", side="Buy", qty=0.01, reduce_only=False,
        ))
        assert result_open is not None
        assert len(maker_calls) == 1, "open должен вызвать maker-only"
        # fallback не должен вырасти выше 1 (только close).
        assert len(fallback_calls) == 1

    def test_open_uses_standard_fallback_when_maker_disabled(
        self, monkeypatch
    ):
        """Sanity: при ARB_MAKER_ONLY_ENABLED=False даже open идёт через
        стандартный fallback."""
        import api_engine
        import config
        from exchanges.bybit import BybitAdapter

        monkeypatch.setattr(config, "ARB_MAKER_ONLY_ENABLED", False, raising=False)

        fallback_calls: list[dict[str, Any]] = []
        maker_calls: list[dict[str, Any]] = []

        async def fake_fallback(_s, **kw):
            fallback_calls.append(kw)
            return {"retCode": 0}

        async def fake_maker(_s, **kw):
            maker_calls.append(kw)
            return {"retCode": 0}

        monkeypatch.setattr(api_engine, "place_order_with_fallback", fake_fallback)
        monkeypatch.setattr(api_engine, "place_maker_only_with_repeg", fake_maker)

        adapter = BybitAdapter()
        _run(adapter.place_order_with_fallback(
            MagicMock(), symbol="BTCUSDT", side="Buy", qty=0.01, reduce_only=False,
        ))
        assert len(fallback_calls) == 1
        assert len(maker_calls) == 0
