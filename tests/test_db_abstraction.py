"""Тесты для модуля db/ (абстракция хранилища)."""
from __future__ import annotations

import os

import pytest

from db.factory import get_storage
from db.sqlite_backend import SQLiteBackend


@pytest.fixture()
def storage(tmp_path):
    """Создаёт SQLiteBackend с временной БД для каждого теста."""
    db_path = str(tmp_path / "test.db")
    backend = SQLiteBackend(db_path=db_path)
    backend.init_db()
    return backend


class TestFactory:
    """Тесты фабрики get_storage."""

    def test_sqlite_url_returns_sqlite_backend(self, tmp_path):
        """sqlite:/// URL возвращает SQLiteBackend."""
        db_path = str(tmp_path / "factory.db")
        s = get_storage(f"sqlite:///{db_path}")
        assert isinstance(s, SQLiteBackend)

    def test_plain_path_returns_sqlite_backend(self, tmp_path):
        """Простой путь без схемы возвращает SQLiteBackend."""
        db_path = str(tmp_path / "plain.db")
        s = get_storage(db_path)
        assert isinstance(s, SQLiteBackend)

    def test_postgres_url_returns_postgres_backend(self):
        """postgresql:// URL возвращает PostgresBackend."""
        from db.postgres_backend import PostgresBackend
        s = get_storage("postgresql://user:pass@localhost/testdb")
        assert isinstance(s, PostgresBackend)


class TestSQLiteBackendTrades:
    """Тесты CRUD операций с trades."""

    def test_record_trade_returns_id(self, storage):
        """record_trade возвращает целочисленный id."""
        trade_id = storage.record_trade(
            symbol="BTCUSDT",
            side="BUY",
            entry=50000.0,
            qty=0.01,
            ema_val=49000.0,
            rsi_val=55.0,
            atr_val=500.0,
            ai_reason="test",
            outcome="OPEN",
        )
        assert trade_id is not None
        assert isinstance(trade_id, int)
        assert trade_id > 0

    def test_update_trade_outcome(self, storage):
        """update_trade_outcome обновляет pnl и outcome."""
        trade_id = storage.record_trade(
            symbol="ETHUSDT", side="SELL", entry=3000.0, qty=0.5
        )
        storage.update_trade_outcome(
            trade_id=trade_id, exit_price=2900.0, pnl=50.0, outcome="WIN"
        )
        # Проверяем через get_stats
        stats = storage.get_stats()
        assert stats["wins"] == 1
        assert stats["pnl_sum"] == 50.0

    def test_get_open_trades(self, storage):
        """get_open_trades возвращает только открытые сделки."""
        storage.record_trade(symbol="BTCUSDT", side="BUY", entry=50000.0, qty=0.01)
        tid2 = storage.record_trade(
            symbol="ETHUSDT", side="SELL", entry=3000.0, qty=0.5
        )
        storage.update_trade_outcome(tid2, 2900.0, 50.0, "WIN")

        open_trades = storage.get_open_trades()
        assert len(open_trades) == 1
        assert open_trades[0]["symbol"] == "BTCUSDT"

    def test_get_recent_errors(self, storage):
        """get_recent_errors возвращает только LOSS-сделки."""
        tid = storage.record_trade(
            symbol="SOLUSDT", side="BUY", entry=100.0, qty=10.0
        )
        storage.update_trade_outcome(tid, 90.0, -100.0, "LOSS")
        # WIN-сделка не должна попасть
        tid2 = storage.record_trade(
            symbol="BTCUSDT", side="BUY", entry=50000.0, qty=0.01
        )
        storage.update_trade_outcome(tid2, 51000.0, 10.0, "WIN")

        errors = storage.get_recent_errors(limit=10)
        assert len(errors) == 1
        assert errors[0]["outcome"] == "LOSS"


class TestSQLiteBackendStats:
    """Тесты статистики."""

    def test_empty_stats(self, storage):
        """Пустая база возвращает нулевую статистику."""
        stats = storage.get_stats()
        assert stats["count"] == 0
        assert stats["wins"] == 0
        assert stats["losses"] == 0
        assert stats["winrate"] == 0.0
        assert stats["pnl_sum"] == 0.0

    def test_winrate_calculation(self, storage):
        """Корректный расчёт winrate."""
        for i in range(3):
            tid = storage.record_trade(
                symbol="BTCUSDT", side="BUY", entry=50000.0, qty=0.01
            )
            storage.update_trade_outcome(tid, 51000.0, 10.0, "WIN")
        tid = storage.record_trade(
            symbol="BTCUSDT", side="BUY", entry=50000.0, qty=0.01
        )
        storage.update_trade_outcome(tid, 49000.0, -10.0, "LOSS")

        stats = storage.get_stats()
        assert stats["count"] == 4
        assert stats["wins"] == 3
        assert stats["losses"] == 1
        assert stats["winrate"] == 75.0


class TestSQLiteBackendKV:
    """Тесты kv_set / kv_get."""

    def test_kv_set_and_get(self, storage):
        """Записанное значение можно прочитать."""
        storage.kv_set("test_key", {"status": "active", "value": 42})
        result = storage.kv_get("test_key")
        assert result == {"status": "active", "value": 42}

    def test_kv_get_default(self, storage):
        """Отсутствующий ключ возвращает default."""
        result = storage.kv_get("nonexistent", default="fallback")
        assert result == "fallback"

    def test_kv_overwrite(self, storage):
        """Повторная запись перезаписывает значение."""
        storage.kv_set("key", "first")
        storage.kv_set("key", "second")
        assert storage.kv_get("key") == "second"

    def test_kv_various_types(self, storage):
        """kv_store сохраняет разные типы (int, list, None)."""
        storage.kv_set("number", 123)
        storage.kv_set("list", [1, 2, 3])
        storage.kv_set("null", None)

        assert storage.kv_get("number") == 123
        assert storage.kv_get("list") == [1, 2, 3]
        assert storage.kv_get("null") is None


class TestSQLiteBackendEquity:
    """Тесты equity_curve."""

    def test_record_and_get_equity(self, storage):
        """record_equity + get_hwm + get_current_drawdown."""
        storage.record_equity(equity=10000.0, hwm=10000.0, drawdown=0.0)
        storage.record_equity(equity=10500.0, hwm=10500.0, drawdown=0.0)
        storage.record_equity(equity=10200.0, hwm=10500.0, drawdown=0.0286)

        assert storage.get_hwm() == 10500.0
        assert abs(storage.get_current_drawdown() - 0.0286) < 0.001

    def test_get_equity_curve_empty(self, storage):
        """Пустая equity_curve возвращает пустой список."""
        curve = storage.get_equity_curve(days=7)
        assert curve == []


class TestSQLiteBackendRejections:
    """Тесты отклонений."""

    def test_record_rejection_v1(self, storage):
        """record_rejection + get_last_rejection."""
        storage.record_rejection(
            reason="low_confidence",
            confidence=30,
            ctx={"symbol": "BTCUSDT", "rsi": 45.0},
        )
        last = storage.get_last_rejection()
        assert last is not None
        assert last["reason"] == "low_confidence"
        assert last["confidence"] == 30
        assert last["context"]["symbol"] == "BTCUSDT"

    def test_record_rejected_check_v2(self, storage):
        """record_rejected_check + get_recent_rejected_checks."""
        storage.record_rejected_check(
            symbol="ETHUSDT",
            filter="donchian",
            detail="price below channel",
            indicators={"atr": 50.0, "donchian_high": 3100.0},
        )
        checks = storage.get_recent_rejected_checks(limit=5)
        assert len(checks) == 1
        assert checks[0]["symbol"] == "ETHUSDT"
        assert checks[0]["filter"] == "donchian"
        assert checks[0]["indicators"]["atr"] == 50.0

    def test_get_last_rejected_check(self, storage):
        """get_last_rejected_check возвращает последнее отклонение."""
        storage.record_rejected_check("BTC", "blackout", "macro event")
        storage.record_rejected_check("ETH", "regime", "CRISIS mode")
        last = storage.get_last_rejected_check()
        assert last is not None
        assert last["symbol"] == "ETH"
        assert last["filter"] == "regime"
