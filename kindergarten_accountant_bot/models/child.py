from typing import List, Optional

import aiosqlite

from kindergarten_accountant_bot import config


async def add_child(child_fio: str, group_name: str, parent_fio: str, discount_percent: float) -> int:
    """Add child, return ID."""
    async with aiosqlite.connect(config.get_db_path()) as db:
        cursor = await db.execute(
            "INSERT INTO children (child_fio, group_name, parent_fio, discount_percent) VALUES (?, ?, ?, ?)",
            (child_fio, group_name, parent_fio, discount_percent),
        )
        await db.commit()
        return cursor.lastrowid


async def get_children() -> List[dict]:
    """Return all children."""
    async with aiosqlite.connect(config.get_db_path()) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM children ORDER BY id")
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


async def get_child(child_id: int) -> Optional[dict]:
    """Get single child by ID."""
    async with aiosqlite.connect(config.get_db_path()) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM children WHERE id = ?", (child_id,)
        )
        row = await cursor.fetchone()
        return dict(row) if row else None


async def delete_child(child_id: int) -> bool:
    """Delete child."""
    async with aiosqlite.connect(config.get_db_path()) as db:
        cursor = await db.execute(
            "DELETE FROM children WHERE id = ?", (child_id,)
        )
        await db.commit()
        return cursor.rowcount > 0


async def get_children_by_group(group_name: str) -> List[dict]:
    """Get children filtered by group."""
    async with aiosqlite.connect(config.get_db_path()) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM children WHERE group_name = ? ORDER BY id",
            (group_name,),
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]
