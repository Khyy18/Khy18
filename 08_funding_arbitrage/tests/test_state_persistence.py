"""Тесты state_persistence: persist/load, merge, сериализация set/deque."""

from __future__ import annotations

from collections import deque

import pytest


@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    """SQLite в tmp_path вместо рабочего trades.db."""
    db_path = str(tmp_path / "test_state.db")
    import memory
    monkeypatch.setattr(memory, "DB_PATH", db_path)
    import state_persistence
    state_persistence.init_db()
    return db_path


def test_persist_and_load_roundtrip(tmp_db):
    """persist state, load обратно, cooldown'ы совпадают."""
    import state_persistence

    state: dict = {
        "global": {
            "bot_running": True,
            "funding_alert_seen": {"bybit:BTCUSDT": 1700000000.0},
            "rebalance_alert_seen": {"okx": 1700000001.0},
            "daily_anchor_iso": "2024-01-15T00:00:00+00:00",
            "weekly_anchor_iso": "2024-01-15T00:00:00+00:00",
            "last_heartbeat_epoch": 12345.0,
        }
    }

    state_persistence.persist(state)
    loaded = state_persistence.load()

    assert loaded is not None
    assert loaded["funding_alert_seen"] == {"bybit:BTCUSDT": 1700000000.0}
    assert loaded["rebalance_alert_seen"] == {"okx": 1700000001.0}
    assert loaded["daily_anchor_iso"] == "2024-01-15T00:00:00+00:00"
    assert loaded["weekly_anchor_iso"] == "2024-01-15T00:00:00+00:00"
    assert loaded["last_heartbeat_epoch"] == 12345.0


def test_merge_preserves_bot_running(tmp_db):
    """saved имеет bot_running=False, merge НЕ перезаписывает (остаётся True)."""
    import state_persistence

    state: dict = {
        "global": {
            "bot_running": True,
            "funding_alert_seen": {},
            "daily_anchor_iso": None,
        }
    }

    saved = {
        "bot_running": False,
        "funding_alert_seen": {"gate:ETHUSDT": 1700000000.0},
        "daily_anchor_iso": "2024-02-01T00:00:00+00:00",
    }

    state_persistence.merge_into_state(state, saved)

    # bot_running НЕ перезаписывается — всегда True на старте.
    assert state["global"]["bot_running"] is True
    # Cooldown'ы мёржатся.
    assert state["global"]["funding_alert_seen"] == {"gate:ETHUSDT": 1700000000.0}
    assert state["global"]["daily_anchor_iso"] == "2024-02-01T00:00:00+00:00"


def test_handles_set_and_deque(tmp_db):
    """state с set/deque сериализуется без ошибок (конвертируются в list)."""
    import state_persistence

    state: dict = {
        "global": {
            "disabled_exchanges": {"bybit", "okx"},
            "some_deque": deque([1, 2, 3], maxlen=10),
            "funding_alert_seen": {},
        }
    }

    # Не должно упасть с TypeError.
    state_persistence.persist(state)
    loaded = state_persistence.load()

    assert loaded is not None
    # set → list (порядок не гарантирован).
    assert set(loaded["disabled_exchanges"]) == {"bybit", "okx"}
    # deque → list.
    assert loaded["some_deque"] == [1, 2, 3]
