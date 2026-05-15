"""Tests for journal model (operations journal)."""

import pytest
import pytest_asyncio
from unittest.mock import patch

from kindergarten_accountant_bot.models.database import init_db
from kindergarten_accountant_bot.models.journal import (
    add_entry,
    get_entries_for_period,
    get_totals_for_period,
)


@pytest_asyncio.fixture
async def journal_db(tmp_path):
    """Fixture that patches get_db_path and initializes the database."""
    db_file = str(tmp_path / "test_journal.db")
    with patch("kindergarten_accountant_bot.config.get_db_path", return_value=db_file):
        await init_db()
        yield db_file


@pytest.mark.asyncio
async def test_add_entry(journal_db):
    """Test adding a journal entry returns an ID."""
    entry_id = await add_entry("2025-01-15", 15000.0, "income", "Иванов", "Род. плата")
    assert entry_id is not None
    assert entry_id > 0


@pytest.mark.asyncio
async def test_add_multiple_entries(journal_db):
    """Test adding multiple entries returns unique IDs."""
    id1 = await add_entry("2025-01-10", 10000.0, "income", "Петров", "Оплата")
    id2 = await add_entry("2025-01-12", 5000.0, "expense", "ООО Рога", "Продукты")
    assert id1 != id2


@pytest.mark.asyncio
async def test_get_entries_for_period(journal_db):
    """Test getting entries for a specific period."""
    await add_entry("2025-01-10", 10000.0, "income", "Петров", "Оплата")
    await add_entry("2025-01-20", 5000.0, "expense", "ООО Рога", "Продукты")
    await add_entry("2025-02-05", 8000.0, "income", "Сидоров", "Оплата")

    entries = await get_entries_for_period("2025-01-01", "2025-01-31")
    assert len(entries) == 2
    assert entries[0]["amount"] == 10000.0
    assert entries[1]["amount"] == 5000.0


@pytest.mark.asyncio
async def test_get_entries_for_period_empty(journal_db):
    """Test getting entries for a period with no data."""
    entries = await get_entries_for_period("2025-03-01", "2025-03-31")
    assert entries == []


@pytest.mark.asyncio
async def test_get_totals_for_period(journal_db):
    """Test totals calculation for a period."""
    await add_entry("2025-01-10", 15000.0, "income", "Петров", "Оплата")
    await add_entry("2025-01-15", 10000.0, "income", "Сидоров", "Оплата")
    await add_entry("2025-01-20", 5000.0, "expense", "ООО Рога", "Продукты")
    await add_entry("2025-01-25", 3000.0, "expense", "ИП Жук", "Канцтовары")

    totals = await get_totals_for_period("2025-01-01", "2025-01-31")
    assert totals["income"] == 25000.0
    assert totals["expense"] == 8000.0
    assert totals["balance"] == 17000.0


@pytest.mark.asyncio
async def test_get_totals_for_period_empty(journal_db):
    """Test totals for period with no data returns zeros."""
    totals = await get_totals_for_period("2025-03-01", "2025-03-31")
    assert totals["income"] == 0
    assert totals["expense"] == 0
    assert totals["balance"] == 0


@pytest.mark.asyncio
async def test_entries_ordered_by_date(journal_db):
    """Test that entries are returned ordered by date."""
    await add_entry("2025-01-20", 5000.0, "expense", "B", "B doc")
    await add_entry("2025-01-05", 10000.0, "income", "A", "A doc")
    await add_entry("2025-01-15", 3000.0, "expense", "C", "C doc")

    entries = await get_entries_for_period("2025-01-01", "2025-01-31")
    dates = [e["date"] for e in entries]
    assert dates == sorted(dates)
