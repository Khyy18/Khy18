from typing import List, Optional

import aiosqlite

from kindergarten_accountant_bot import config


async def create_fee_record(child_id: int, month: int, year: int, attendance_days: int, amount_due: float) -> int:
    """Create or update fee record for child/month/year."""
    async with aiosqlite.connect(config.get_db_path()) as db:
        cursor = await db.execute(
            "SELECT id FROM parent_payments WHERE child_id = ? AND month = ? AND year = ?",
            (child_id, month, year),
        )
        existing = await cursor.fetchone()
        if existing:
            await db.execute(
                "UPDATE parent_payments SET attendance_days = ?, amount_due = ? WHERE id = ?",
                (attendance_days, amount_due, existing[0]),
            )
            await db.commit()
            return existing[0]
        else:
            cursor = await db.execute(
                "INSERT INTO parent_payments (child_id, month, year, attendance_days, amount_due, amount_paid) "
                "VALUES (?, ?, ?, ?, ?, 0)",
                (child_id, month, year, attendance_days, amount_due),
            )
            await db.commit()
            return cursor.lastrowid


async def record_payment(child_id: int, month: int, year: int, amount: float) -> bool:
    """Add payment amount to existing record. Returns True if a record was updated, False otherwise."""
    async with aiosqlite.connect(config.get_db_path()) as db:
        cursor = await db.execute(
            "UPDATE parent_payments SET amount_paid = amount_paid + ?, paid_at = CURRENT_TIMESTAMP "
            "WHERE child_id = ? AND month = ? AND year = ?",
            (amount, child_id, month, year),
        )
        await db.commit()
        return cursor.rowcount > 0


async def get_payment_record(child_id: int, month: int, year: int) -> Optional[dict]:
    """Get payment record for specific child/month/year."""
    async with aiosqlite.connect(config.get_db_path()) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM parent_payments WHERE child_id = ? AND month = ? AND year = ?",
            (child_id, month, year),
        )
        row = await cursor.fetchone()
        return dict(row) if row else None


async def get_debts() -> List[dict]:
    """Return all records where amount_paid < amount_due, joined with children info."""
    async with aiosqlite.connect(config.get_db_path()) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT pp.*, c.child_fio, c.group_name, c.parent_fio "
            "FROM parent_payments pp "
            "JOIN children c ON pp.child_id = c.id "
            "WHERE pp.amount_paid < pp.amount_due "
            "ORDER BY pp.year, pp.month"
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]
