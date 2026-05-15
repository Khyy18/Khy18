from typing import List

import aiosqlite

from kindergarten_accountant_bot.config import DB_PATH
from kindergarten_accountant_bot.utils.constants import MARK_TYPES


async def add_mark(employee_id: int, date: str, mark_type: str) -> int:
    """Add timesheet mark for date (format YYYY-MM-DD). If mark exists for this employee+date, update it."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT id FROM timesheet_marks WHERE employee_id = ? AND date = ?",
            (employee_id, date),
        )
        existing = await cursor.fetchone()
        if existing:
            await db.execute(
                "UPDATE timesheet_marks SET mark_type = ? WHERE id = ?",
                (mark_type, existing[0]),
            )
            await db.commit()
            return existing[0]
        else:
            cursor = await db.execute(
                "INSERT INTO timesheet_marks (employee_id, date, mark_type) VALUES (?, ?, ?)",
                (employee_id, date, mark_type),
            )
            await db.commit()
            return cursor.lastrowid


async def get_marks_for_month(employee_id: int, year: int, month: int) -> List[dict]:
    """Return all marks for employee in given month."""
    date_prefix = f"{year:04d}-{month:02d}"
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM timesheet_marks WHERE employee_id = ? AND date LIKE ?",
            (employee_id, f"{date_prefix}%"),
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


async def get_monthly_summary(employee_id: int, year: int, month: int) -> dict:
    """Return dict like {"Я": 18, "Б": 2, "О": 0, "ОТ": 1, "П": 1}."""
    marks = await get_marks_for_month(employee_id, year, month)
    summary = {key: 0 for key in MARK_TYPES}
    for mark in marks:
        mt = mark["mark_type"]
        if mt in summary:
            summary[mt] += 1
    return summary
