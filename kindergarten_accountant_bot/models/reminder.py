"""Reminder model for managing deadline notification preferences."""

from datetime import date, timedelta

import aiosqlite

from kindergarten_accountant_bot.config import DB_PATH
from kindergarten_accountant_bot.data.deadlines import DEADLINES


async def set_reminder_status(chat_id: int, reminder_name: str, enabled: bool) -> None:
    """Enable or disable a reminder for a chat. Upsert into reminders table."""
    async with aiosqlite.connect(DB_PATH) as db:
        existing = await db.execute(
            "SELECT id FROM reminders WHERE chat_id = ? AND name = ?",
            (chat_id, reminder_name),
        )
        row = await existing.fetchone()
        if row:
            await db.execute(
                "UPDATE reminders SET enabled = ? WHERE chat_id = ? AND name = ?",
                (1 if enabled else 0, chat_id, reminder_name),
            )
        else:
            await db.execute(
                "INSERT INTO reminders (chat_id, name, enabled) VALUES (?, ?, ?)",
                (chat_id, reminder_name, 1 if enabled else 0),
            )
        await db.commit()


async def get_enabled_reminders(chat_id: int) -> list:
    """Return list of enabled reminder names for chat."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT name FROM reminders WHERE chat_id = ? AND enabled = 1",
            (chat_id,),
        )
        rows = await cursor.fetchall()
        return [row["name"] for row in rows]


async def get_all_reminders_status(chat_id: int) -> dict:
    """Return dict of {reminder_name: enabled} for all known deadlines."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT name, enabled FROM reminders WHERE chat_id = ?",
            (chat_id,),
        )
        rows = await cursor.fetchall()
        stored = {row["name"]: bool(row["enabled"]) for row in rows}

    result = {}
    for deadline in DEADLINES:
        name = deadline["name"]
        result[name] = stored.get(name, False)
    return result


def get_next_deadline_date(deadline: dict, from_date: date = None) -> date:
    """Calculate the next occurrence of a deadline from a given date."""
    if from_date is None:
        from_date = date.today()

    day = deadline["day_of_month"]
    months = deadline["months"]

    # Try current month first, then subsequent months
    for offset in range(13):
        month = from_date.month + offset
        year = from_date.year + (month - 1) // 12
        month = ((month - 1) % 12) + 1

        if month not in months:
            continue

        try:
            candidate = date(year, month, day)
        except ValueError:
            # Handle months with fewer days
            if month in (4, 6, 9, 11):
                candidate = date(year, month, 30)
            elif month == 2:
                candidate = date(year, month, 28)
            else:
                continue

        if candidate >= from_date:
            return candidate

    # Fallback: shouldn't happen with valid data
    return from_date + timedelta(days=30)


async def get_chats_with_reminders() -> list:
    """Return list of distinct chat_ids that have at least one enabled reminder."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT DISTINCT chat_id FROM reminders WHERE enabled = 1"
        )
        rows = await cursor.fetchall()
        return [row[0] for row in rows]
