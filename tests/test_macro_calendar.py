"""Tests for macro_calendar.py."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime, timezone, timedelta
import macro_calendar


def test_is_blackout_during_fomc():
    """During FOMC announcement time should be blackout."""
    # FOMC 2025-01-29 18:00 UTC
    dt = datetime(2025, 1, 29, 18, 0, tzinfo=timezone.utc)
    is_bl, name = macro_calendar.is_macro_blackout(dt)
    assert is_bl is True
    assert name == "FOMC"


def test_is_not_blackout_normal_time():
    """Normal time far from any event should not be blackout."""
    dt = datetime(2025, 1, 20, 10, 0, tzinfo=timezone.utc)
    is_bl, name = macro_calendar.is_macro_blackout(dt)
    assert is_bl is False
    assert name == ""


def test_blackout_window_before_and_after():
    """Blackout starts 30min before and ends 60min after event."""
    # FOMC 2025-03-19 18:00 UTC
    event_dt = datetime(2025, 3, 19, 18, 0, tzinfo=timezone.utc)

    # 30 min before = exactly at boundary -> should be blackout
    before = event_dt - timedelta(minutes=30)
    is_bl, name = macro_calendar.is_macro_blackout(before)
    assert is_bl is True
    assert name == "FOMC"

    # 31 min before = outside window
    outside_before = event_dt - timedelta(minutes=31)
    is_bl, name = macro_calendar.is_macro_blackout(outside_before)
    assert is_bl is False

    # 60 min after = exactly at boundary -> should be blackout
    after = event_dt + timedelta(minutes=60)
    is_bl, name = macro_calendar.is_macro_blackout(after)
    assert is_bl is True
    assert name == "FOMC"

    # 61 min after = outside window
    outside_after = event_dt + timedelta(minutes=61)
    is_bl, name = macro_calendar.is_macro_blackout(outside_after)
    assert is_bl is False


def test_blackout_cpi():
    """CPI event blackout works."""
    # CPI 2025-02-12 12:30 UTC
    dt = datetime(2025, 2, 12, 12, 30, tzinfo=timezone.utc)
    is_bl, name = macro_calendar.is_macro_blackout(dt)
    assert is_bl is True
    assert name == "CPI"


def test_blackout_nfp():
    """NFP event blackout works."""
    # NFP 2025-01-10 12:30 UTC
    dt = datetime(2025, 1, 10, 12, 30, tzinfo=timezone.utc)
    is_bl, name = macro_calendar.is_macro_blackout(dt)
    assert is_bl is True
    assert name == "NFP"
