"""Tests for reminders model and deadline date calculation."""

from datetime import date

import pytest
import pytest_asyncio
from unittest.mock import patch

from kindergarten_accountant_bot.data.deadlines import DEADLINES
from kindergarten_accountant_bot.models.database import init_db
from kindergarten_accountant_bot.models.reminder import (
    get_all_reminders_status,
    get_enabled_reminders,
    get_next_deadline_date,
    set_reminder_status,
)


@pytest_asyncio.fixture
async def reminder_db(tmp_path):
    """Fixture that patches get_db_path and initializes the database."""
    db_file = str(tmp_path / "test_reminder.db")
    with patch("kindergarten_accountant_bot.config.get_db_path", return_value=db_file):
        await init_db()
        yield db_file


@pytest.mark.asyncio
async def test_set_reminder_status_enable(reminder_db):
    """Test enabling a reminder."""
    with patch("kindergarten_accountant_bot.config.get_db_path", return_value=reminder_db):
        await set_reminder_status(123, "6-НДФЛ", True)
        enabled = await get_enabled_reminders(123)
        assert "6-НДФЛ" in enabled


@pytest.mark.asyncio
async def test_set_reminder_status_disable(reminder_db):
    """Test disabling a reminder."""
    with patch("kindergarten_accountant_bot.config.get_db_path", return_value=reminder_db):
        await set_reminder_status(123, "6-НДФЛ", True)
        await set_reminder_status(123, "6-НДФЛ", False)
        enabled = await get_enabled_reminders(123)
        assert "6-НДФЛ" not in enabled


@pytest.mark.asyncio
async def test_get_enabled_reminders_only_enabled(reminder_db):
    """Test that only enabled reminders are returned."""
    with patch("kindergarten_accountant_bot.config.get_db_path", return_value=reminder_db):
        await set_reminder_status(123, "6-НДФЛ", True)
        await set_reminder_status(123, "РСВ", True)
        await set_reminder_status(123, "СЗВ-М (ЕФС-1)", False)
        enabled = await get_enabled_reminders(123)
        assert "6-НДФЛ" in enabled
        assert "РСВ" in enabled
        assert "СЗВ-М (ЕФС-1)" not in enabled


@pytest.mark.asyncio
async def test_get_all_reminders_status(reminder_db):
    """Test getting all reminders status returns dict for all deadlines."""
    with patch("kindergarten_accountant_bot.config.get_db_path", return_value=reminder_db):
        await set_reminder_status(123, "6-НДФЛ", True)
        await set_reminder_status(123, "РСВ", False)
        statuses = await get_all_reminders_status(123)
        assert isinstance(statuses, dict)
        assert len(statuses) == len(DEADLINES)
        assert statuses["6-НДФЛ"] is True
        assert statuses["РСВ"] is False
        # Unset reminders default to False
        assert statuses["Страховые взносы"] is False


@pytest.mark.asyncio
async def test_get_all_reminders_status_empty(reminder_db):
    """Test getting status when nothing is set returns all False."""
    with patch("kindergarten_accountant_bot.config.get_db_path", return_value=reminder_db):
        statuses = await get_all_reminders_status(999)
        assert all(v is False for v in statuses.values())


def test_get_next_deadline_date_monthly():
    """Test next deadline calculation for monthly deadline."""
    deadline = {
        "name": "СЗВ-М (ЕФС-1)",
        "recurrence": "monthly",
        "day_of_month": 15,
        "months": list(range(1, 13)),
    }
    # From Jan 10 -> should be Jan 15
    result = get_next_deadline_date(deadline, date(2025, 1, 10))
    assert result == date(2025, 1, 15)

    # From Jan 15 -> should be Jan 15 (same day counts)
    result = get_next_deadline_date(deadline, date(2025, 1, 15))
    assert result == date(2025, 1, 15)

    # From Jan 16 -> should be Feb 15
    result = get_next_deadline_date(deadline, date(2025, 1, 16))
    assert result == date(2025, 2, 15)


def test_get_next_deadline_date_quarterly():
    """Test next deadline calculation for quarterly deadline."""
    deadline = {
        "name": "6-НДФЛ",
        "recurrence": "quarterly",
        "day_of_month": 25,
        "months": [4, 7, 10, 1],
    }
    # From Jan 20 -> should be Jan 25 (January is in the months list)
    result = get_next_deadline_date(deadline, date(2025, 1, 20))
    assert result == date(2025, 1, 25)

    # From Jan 26 -> should be Apr 25
    result = get_next_deadline_date(deadline, date(2025, 1, 26))
    assert result == date(2025, 4, 25)

    # From May 1 -> should be Jul 25
    result = get_next_deadline_date(deadline, date(2025, 5, 1))
    assert result == date(2025, 7, 25)


def test_get_next_deadline_date_year_boundary():
    """Test deadline calculation across year boundary."""
    deadline = {
        "name": "6-НДФЛ",
        "recurrence": "quarterly",
        "day_of_month": 25,
        "months": [4, 7, 10, 1],
    }
    # From Nov 1 -> should be Jan 25 next year
    result = get_next_deadline_date(deadline, date(2025, 11, 1))
    assert result == date(2026, 1, 25)


def test_deadlines_has_at_least_7():
    """DEADLINES should contain at least 7 entries."""
    assert len(DEADLINES) >= 7


def test_deadlines_structure():
    """Each deadline should have required fields."""
    for d in DEADLINES:
        assert "name" in d
        assert "description" in d
        assert "recurrence" in d
        assert "day_of_month" in d
        assert "months" in d
        assert d["recurrence"] in ("monthly", "quarterly")
