"""Macro economic calendar - trading blackout periods.

Определяет периоды блэкаута вокруг ключевых макро-событий:
  - FOMC (Federal Open Market Committee)
  - CPI (Consumer Price Index)
  - NFP (Non-Farm Payrolls)

Блэкаут: 30 минут до и 60 минут после события.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Tuple

# Формат: (month, day, hour, minute) in UTC
# FOMC 2025 schedule (announcement times, 18:00 UTC typically)
_FOMC_2025 = [
    (1, 29, 18, 0),
    (3, 19, 18, 0),
    (5, 7, 18, 0),
    (6, 18, 18, 0),
    (7, 30, 18, 0),
    (9, 17, 18, 0),
    (10, 29, 18, 0),
    (12, 17, 18, 0),
]

# CPI 2025 schedule (release at 12:30 UTC)
_CPI_2025 = [
    (1, 15, 12, 30),
    (2, 12, 12, 30),
    (3, 12, 12, 30),
    (4, 10, 12, 30),
    (5, 13, 12, 30),
    (6, 11, 12, 30),
    (7, 15, 12, 30),
    (8, 12, 12, 30),
    (9, 10, 12, 30),
    (10, 14, 12, 30),
    (11, 12, 12, 30),
    (12, 10, 12, 30),
]

# NFP 2025 schedule (first Friday, 12:30 UTC)
_NFP_2025 = [
    (1, 10, 12, 30),
    (2, 7, 12, 30),
    (3, 7, 12, 30),
    (4, 4, 12, 30),
    (5, 2, 12, 30),
    (6, 6, 12, 30),
    (7, 3, 12, 30),
    (8, 1, 12, 30),
    (9, 5, 12, 30),
    (10, 3, 12, 30),
    (11, 7, 12, 30),
    (12, 5, 12, 30),
]

_BEFORE_MINUTES = 30
_AFTER_MINUTES = 60


def _build_events() -> list[tuple[datetime, str]]:
    """Build list of (event_datetime, event_name)."""
    events = []
    for m, d, h, mi in _FOMC_2025:
        events.append((datetime(2025, m, d, h, mi, tzinfo=timezone.utc), "FOMC"))
    for m, d, h, mi in _CPI_2025:
        events.append((datetime(2025, m, d, h, mi, tzinfo=timezone.utc), "CPI"))
    for m, d, h, mi in _NFP_2025:
        events.append((datetime(2025, m, d, h, mi, tzinfo=timezone.utc), "NFP"))
    return events


_EVENTS = _build_events()


def is_macro_blackout(dt: datetime) -> Tuple[bool, str]:
    """Check if given datetime falls within a macro event blackout window.

    Returns (is_blackout, event_name). If not in blackout, returns (False, "").
    Blackout window: 30 minutes before event to 60 minutes after event (inclusive).
    """
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)

    for event_dt, event_name in _EVENTS:
        window_start = event_dt - timedelta(minutes=_BEFORE_MINUTES)
        window_end = event_dt + timedelta(minutes=_AFTER_MINUTES)
        if window_start <= dt <= window_end:
            return True, event_name

    return False, ""
