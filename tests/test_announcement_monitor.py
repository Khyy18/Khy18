"""Тесты announcement_monitor: классификация regex-правилами + blacklist."""

from __future__ import annotations

import time

import announcement_monitor as am


def test_classify_delisting():
    """'Delisting of XYZUSDT scheduled' -> critical/delisting/[XYZUSDT]."""
    res = am.classify_announcement("Delisting of XYZUSDT scheduled")
    assert res["severity"] == "critical"
    assert res["category"] == "delisting"
    assert "XYZUSDT" in res["symbols"]


def test_classify_maintenance():
    """'Scheduled system maintenance' -> warning/maintenance/[]."""
    res = am.classify_announcement("Scheduled system maintenance window")
    assert res["severity"] == "warning"
    assert res["category"] == "maintenance"
    assert res["symbols"] == []


def test_classify_other():
    """Анонс не из списка категорий -> info/other."""
    res = am.classify_announcement("Bitget Wins Award for Innovation")
    assert res["severity"] == "info"
    assert res["category"] == "other"


def test_extract_multiple_symbols():
    """Из заголовка с несколькими символами извлекаются все."""
    res = am.classify_announcement("Delisting BTCUSDT and ETHUSDT pairs")
    assert res["category"] == "delisting"
    assert "BTCUSDT" in res["symbols"]
    assert "ETHUSDT" in res["symbols"]


def test_is_blacklisted_true_then_false_for_other():
    """Установить blacklist в state, проверить True для key, False для другого."""
    expires = int(time.time() * 1000) + 3600 * 1000
    state = {
        "announcement_blacklist": {
            "bybit:XYZUSDT": expires,
        }
    }
    assert am.is_blacklisted("bybit", "XYZUSDT", state) is True
    assert am.is_blacklisted("BYBIT", "XYZUSDT", state) is True  # case-insensitive
    assert am.is_blacklisted("bybit", "BTCUSDT", state) is False
    assert am.is_blacklisted("okx", "XYZUSDT", state) is False


def test_is_blacklisted_expired():
    """Истёкшая запись не считается активной."""
    state = {
        "announcement_blacklist": {
            "bybit:OLDUSDT": int(time.time() * 1000) - 1000,
        }
    }
    assert am.is_blacklisted("bybit", "OLDUSDT", state) is False


def test_is_blacklisted_empty_state():
    """Пустой state — graceful, возвращаем False."""
    assert am.is_blacklisted("bybit", "BTCUSDT", {}) is False
    assert am.is_blacklisted("bybit", "BTCUSDT", {"announcement_blacklist": {}}) is False
