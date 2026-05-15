"""Macro calendar filter: blackout windows around major economic events."""

from __future__ import annotations
from datetime import datetime, timedelta, timezone
from typing import Tuple

import combo_config as cfg

# Schedule: (month, day, hour, minute) in UTC
MACRO_EVENTS: dict[str, list[tuple[int, int, int, int]]] = {
    "FOMC": [
        (1, 29, 18, 0), (3, 19, 18, 0), (5, 7, 18, 0), (6, 18, 18, 0),
        (7, 30, 18, 0), (9, 17, 18, 0), (10, 29, 18, 0), (12, 17, 18, 0),
    ],
    "CPI": [
        (1, 15, 12, 30), (2, 12, 12, 30), (3, 12, 12, 30), (4, 10, 12, 30),
        (5, 13, 12, 30), (6, 11, 12, 30), (7, 15, 12, 30), (8, 12, 12, 30),
        (9, 10, 12, 30), (10, 14, 12, 30), (11, 12, 12, 30), (12, 10, 12, 30),
    ],
    "NFP": [
        (1, 10, 12, 30), (2, 7, 12, 30), (3, 7, 12, 30), (4, 4, 12, 30),
        (5, 2, 12, 30), (6, 6, 12, 30), (7, 3, 12, 30), (8, 1, 12, 30),
        (9, 5, 12, 30), (10, 3, 12, 30), (11, 7, 12, 30), (12, 5, 12, 30),
    ],
}


def is_macro_blackout(dt: datetime) -> Tuple[bool, str]:
    """Check if dt is within a macro event blackout window.

    Returns (True, event_name) if in blackout, (False, "") otherwise.
    Blackout = MACRO_BLACKOUT_BEFORE_MIN before to MACRO_BLACKOUT_AFTER_MIN after event.
    """
    if not cfg.MACRO_CALENDAR_ENABLED:
        return (False, "")

    before_delta = timedelta(minutes=cfg.MACRO_BLACKOUT_BEFORE_MIN)
    after_delta = timedelta(minutes=cfg.MACRO_BLACKOUT_AFTER_MIN)

    year = dt.year
    for event_name, schedule in MACRO_EVENTS.items():
        for month, day, hour, minute in schedule:
            try:
                event_dt = datetime(year, month, day, hour, minute, tzinfo=timezone.utc)
            except ValueError:
                continue
            if (event_dt - before_delta) <= dt <= (event_dt + after_delta):
                return (True, event_name)
    return (False, "")
