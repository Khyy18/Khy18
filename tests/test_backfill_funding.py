"""Тест backfill_funding.py: main() не падает при network error."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_backfill_main_handles_no_network(monkeypatch, tmp_path):
    """Мок aiohttp.ClientSession: все запросы кидают Exception.
    Проверяем что main() не падает и возвращает 0 (graceful degradation).
    """
    import memory
    import funding_history

    # Перенаправляем DB в tmp чтобы не трогать рабочую.
    db_path = str(tmp_path / "test_backfill.db")
    monkeypatch.setattr(memory, "DB_PATH", db_path)

    # Инициализируем БД.
    funding_history.init_db()

    # Мок aiohttp: все запросы кидают ConnectionError.
    class FakeResp:
        status = 500

        async def json(self):
            return {}

        async def __aenter__(self):
            raise ConnectionError("network unavailable")

        async def __aexit__(self, *args):
            pass

    class FakeSession:
        def get(self, url, **kwargs):
            return FakeResp()

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

    monkeypatch.setattr("aiohttp.ClientSession", lambda **kw: FakeSession())

    import backfill_funding

    # Вызываем run напрямую с мок-символами.
    result = await backfill_funding.run(
        days=3,
        exchanges=["bybit", "binance"],
        symbols=["BTCUSDT"],
    )

    # Не упал, вернул 0 (нет данных, но это не ошибка).
    assert result == 0


def test_backfill_main_cli_handles_no_network(monkeypatch, tmp_path):
    """Проверяем CLI entry point main() — не падает и возвращает 0."""
    import memory
    import funding_history

    db_path = str(tmp_path / "test_backfill_cli.db")
    monkeypatch.setattr(memory, "DB_PATH", db_path)
    funding_history.init_db()

    # Мок aiohttp.
    class FakeResp:
        status = 500

        async def json(self):
            return {}

        async def __aenter__(self):
            raise ConnectionError("no network")

        async def __aexit__(self, *args):
            pass

    class FakeSession:
        def get(self, url, **kwargs):
            return FakeResp()

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

    monkeypatch.setattr("aiohttp.ClientSession", lambda **kw: FakeSession())

    import backfill_funding
    result = backfill_funding.main(["--days", "1", "--symbols", "BTCUSDT"])
    assert result == 0
