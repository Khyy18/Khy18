"""Тесты periodic position check (orphaned leg detection)."""

from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.fixture(autouse=True)
def _patch_config(monkeypatch):
    """Минимальная подготовка config для импорта main."""
    import config
    monkeypatch.setattr(config, "POSITION_CHECK_INTERVAL_SEC", 0.0, raising=False)
    monkeypatch.setattr(config, "FUNDING_SCAN_EXCHANGES", (), raising=False)


@pytest.mark.asyncio
async def test_position_check_detects_orphan(monkeypatch):
    """Мок adapter.get_positions возвращает [] для одной ноги → mark_failed вызван."""
    import arb_storage
    import config

    # Подготовка: mock arb_storage.
    fake_pos = {
        "id": 42,
        "symbol": "BTCUSDT",
        "long_exchange": "bybit",
        "short_exchange": "okx",
        "qty_base": 0.01,
        "status": "OPEN",
    }
    monkeypatch.setattr(arb_storage, "get_all_active", lambda: [fake_pos])

    # Трекаем mark_failed.
    mark_failed_calls: list[tuple] = []
    original_mark_failed = arb_storage.mark_failed

    def _mock_mark_failed(arb_id, reason):
        mark_failed_calls.append((arb_id, reason))

    monkeypatch.setattr(arb_storage, "mark_failed", _mock_mark_failed)

    # Адаптер bybit — вернёт [] (позиция пропала).
    mock_bybit_adapter = MagicMock()
    mock_bybit_adapter.get_positions = AsyncMock(return_value=[])

    # Адаптер okx — вернёт позицию (всё ок на этой стороне).
    mock_okx_adapter = MagicMock()
    mock_okx_adapter.get_positions = AsyncMock(return_value=[{"size": "0.01"}])

    # Мок _close_leg.
    import arb_executor
    monkeypatch.setattr(
        arb_executor, "_close_leg",
        AsyncMock(return_value={"fill_price": 50000.0}),
    )

    # Импортируем main и подменяем _FUNDING_ADAPTERS.
    import main
    monkeypatch.setattr(main, "_FUNDING_ADAPTERS", {
        "bybit": mock_bybit_adapter,
        "okx": mock_okx_adapter,
    })

    # Подготовка state.
    state: dict = {"global": {"last_position_check_epoch": 0}}
    session = MagicMock()

    # Мок _notify чтобы не лезть в Telegram.
    monkeypatch.setattr(main, "_notify", AsyncMock())

    from datetime import datetime, timezone
    now = datetime.now(tz=timezone.utc)

    await main._position_check_tick(session, state, now)

    # Проверяем что mark_failed был вызван.
    assert len(mark_failed_calls) == 1
    assert mark_failed_calls[0][0] == 42
    assert "orphaned_leg" in mark_failed_calls[0][1]
    assert "LONG" in mark_failed_calls[0][1]


@pytest.mark.asyncio
async def test_position_check_ok_when_both_present(monkeypatch):
    """Обе ноги на месте → ничего не происходит, mark_failed не вызван."""
    import arb_storage
    import config

    fake_pos = {
        "id": 10,
        "symbol": "ETHUSDT",
        "long_exchange": "binance",
        "short_exchange": "gate",
        "qty_base": 0.5,
        "status": "OPEN",
    }
    monkeypatch.setattr(arb_storage, "get_all_active", lambda: [fake_pos])

    mark_failed_calls: list = []
    monkeypatch.setattr(arb_storage, "mark_failed", lambda *a: mark_failed_calls.append(a))

    # Оба адаптера вернут позиции.
    mock_binance = MagicMock()
    mock_binance.get_positions = AsyncMock(return_value=[{"size": "0.5"}])

    mock_gate = MagicMock()
    mock_gate.get_positions = AsyncMock(return_value=[{"qty": "0.5"}])

    import main
    monkeypatch.setattr(main, "_FUNDING_ADAPTERS", {
        "binance": mock_binance,
        "gate": mock_gate,
    })

    state: dict = {"global": {"last_position_check_epoch": 0}}
    session = MagicMock()
    monkeypatch.setattr(main, "_notify", AsyncMock())

    from datetime import datetime, timezone
    now = datetime.now(tz=timezone.utc)

    await main._position_check_tick(session, state, now)

    # mark_failed НЕ вызывался.
    assert len(mark_failed_calls) == 0
