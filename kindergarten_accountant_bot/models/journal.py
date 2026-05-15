"""Journal model for operations journal (income/expense tracking)."""

import aiosqlite

from kindergarten_accountant_bot.config import DB_PATH


async def add_entry(
    date: str,
    amount: float,
    entry_type: str,
    counterparty: str,
    basis: str,
) -> int:
    """Add journal entry. entry_type is 'income' or 'expense'. Returns ID."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            """INSERT INTO journal_entries (date, amount, entry_type, counterparty, basis)
               VALUES (?, ?, ?, ?, ?)""",
            (date, amount, entry_type, counterparty, basis),
        )
        await db.commit()
        return cursor.lastrowid


async def get_entries_for_period(start_date: str, end_date: str) -> list:
    """Get all entries between start and end date (YYYY-MM-DD format), ordered by date."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """SELECT id, date, amount, entry_type, counterparty, basis
               FROM journal_entries
               WHERE date >= ? AND date <= ?
               ORDER BY date""",
            (start_date, end_date),
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


async def get_totals_for_period(start_date: str, end_date: str) -> dict:
    """Return {'income': float, 'expense': float, 'balance': float} for period."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            """SELECT
                 COALESCE(SUM(CASE WHEN entry_type='income' THEN amount ELSE 0 END), 0) as income,
                 COALESCE(SUM(CASE WHEN entry_type='expense' THEN amount ELSE 0 END), 0) as expense
               FROM journal_entries
               WHERE date >= ? AND date <= ?""",
            (start_date, end_date),
        )
        row = await cursor.fetchone()
        income = row[0]
        expense = row[1]
        return {
            "income": income,
            "expense": expense,
            "balance": income - expense,
        }
