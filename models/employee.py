from typing import List, Optional

import aiosqlite

from kindergarten_accountant_bot import config


async def add_employee(fio: str, position: str, rate: float) -> int:
    """Add employee, return ID."""
    async with aiosqlite.connect(config.get_db_path()) as db:
        cursor = await db.execute(
            "INSERT INTO employees (fio, position, rate) VALUES (?, ?, ?)",
            (fio, position, rate),
        )
        await db.commit()
        return cursor.lastrowid


async def get_employees() -> List[dict]:
    """Return all employees as list of dicts."""
    async with aiosqlite.connect(config.get_db_path()) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM employees ORDER BY id")
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


async def get_employee(employee_id: int) -> Optional[dict]:
    """Get single employee by ID."""
    async with aiosqlite.connect(config.get_db_path()) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM employees WHERE id = ?", (employee_id,)
        )
        row = await cursor.fetchone()
        return dict(row) if row else None


async def delete_employee(employee_id: int) -> bool:
    """Delete employee, return True if deleted."""
    async with aiosqlite.connect(config.get_db_path()) as db:
        cursor = await db.execute(
            "DELETE FROM employees WHERE id = ?", (employee_id,)
        )
        await db.commit()
        return cursor.rowcount > 0
