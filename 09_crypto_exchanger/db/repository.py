"""CRUD operations for exchanges and users."""

from datetime import datetime, timedelta
from typing import Any, Optional

from db.models import get_db


async def get_or_create_user(
    user_id: int, username: Optional[str] = None, first_name: Optional[str] = None
) -> dict[str, Any]:
    """Get existing user or create new one."""
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT * FROM users WHERE user_id = ?", (user_id,)
        )
        row = await cursor.fetchone()
        if row:
            return dict(row)

        await db.execute(
            "INSERT INTO users (user_id, username, first_name) VALUES (?, ?, ?)",
            (user_id, username, first_name),
        )
        await db.commit()
        return {
            "user_id": user_id,
            "username": username,
            "first_name": first_name,
            "exchanges_count": 0,
            "total_volume": 0.0,
        }
    finally:
        await db.close()


async def create_exchange(
    user_id: int,
    from_currency: str,
    to_currency: str,
    amount: float,
    estimated_amount: float,
    provider: str,
    payout_address: str,
    markup_amount: float = 0.0,
    fixed_rate_id: Optional[str] = None,
) -> int:
    """Create a new exchange record. Returns the exchange row ID."""
    db = await get_db()
    try:
        cursor = await db.execute(
            """INSERT INTO exchanges
            (user_id, from_currency, to_currency, amount, estimated_amount,
             provider, payout_address, markup_amount, fixed_rate_id, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'new')""",
            (
                user_id,
                from_currency,
                to_currency,
                amount,
                estimated_amount,
                provider,
                payout_address,
                markup_amount,
                fixed_rate_id,
            ),
        )
        await db.commit()
        return cursor.lastrowid  # type: ignore[return-value]
    finally:
        await db.close()


async def update_exchange(
    row_id: int, **kwargs: Any
) -> None:
    """Update exchange fields by row ID."""
    if not kwargs:
        return
    kwargs["updated_at"] = datetime.utcnow().isoformat()
    fields = ", ".join(f"{k} = ?" for k in kwargs)
    values = list(kwargs.values())
    values.append(row_id)
    db = await get_db()
    try:
        await db.execute(
            f"UPDATE exchanges SET {fields} WHERE id = ?", values
        )
        await db.commit()
    finally:
        await db.close()


async def get_exchange_by_id(row_id: int) -> Optional[dict[str, Any]]:
    """Get exchange by row ID."""
    db = await get_db()
    try:
        cursor = await db.execute("SELECT * FROM exchanges WHERE id = ?", (row_id,))
        row = await cursor.fetchone()
        return dict(row) if row else None
    finally:
        await db.close()


async def get_exchange_by_exchange_id(exchange_id: str) -> Optional[dict[str, Any]]:
    """Get exchange by provider exchange ID."""
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT * FROM exchanges WHERE exchange_id = ?", (exchange_id,)
        )
        row = await cursor.fetchone()
        return dict(row) if row else None
    finally:
        await db.close()


async def get_active_exchanges() -> list[dict[str, Any]]:
    """Get all exchanges with active statuses."""
    active_statuses = ("new", "waiting", "confirming", "exchanging", "sending")
    placeholders = ",".join("?" * len(active_statuses))
    db = await get_db()
    try:
        cursor = await db.execute(
            f"SELECT * FROM exchanges WHERE status IN ({placeholders})",
            active_statuses,
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]
    finally:
        await db.close()


async def get_user_active_exchanges(user_id: int) -> list[dict[str, Any]]:
    """Get active exchanges for a specific user."""
    active_statuses = ("new", "waiting", "confirming", "exchanging", "sending")
    placeholders = ",".join("?" * len(active_statuses))
    db = await get_db()
    try:
        cursor = await db.execute(
            f"SELECT * FROM exchanges WHERE user_id = ? AND status IN ({placeholders})",
            (user_id, *active_statuses),
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]
    finally:
        await db.close()


async def get_stuck_exchanges(timeout_minutes: int = 60) -> list[dict[str, Any]]:
    """Get exchanges stuck for more than timeout_minutes."""
    cutoff = (datetime.utcnow() - timedelta(minutes=timeout_minutes)).isoformat()
    db = await get_db()
    try:
        cursor = await db.execute(
            """SELECT * FROM exchanges
            WHERE status IN ('waiting', 'confirming', 'exchanging', 'sending')
            AND updated_at < ?""",
            (cutoff,),
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]
    finally:
        await db.close()


async def get_failed_exchanges(limit: int = 20) -> list[dict[str, Any]]:
    """Get recent failed/refunded exchanges."""
    db = await get_db()
    try:
        cursor = await db.execute(
            """SELECT * FROM exchanges
            WHERE status IN ('failed', 'refunded')
            ORDER BY updated_at DESC LIMIT ?""",
            (limit,),
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]
    finally:
        await db.close()


async def get_daily_stats() -> dict[str, Any]:
    """Get today's exchange statistics."""
    today = datetime.utcnow().strftime("%Y-%m-%d")
    db = await get_db()
    try:
        cursor = await db.execute(
            """SELECT
                COUNT(*) as total_count,
                COALESCE(SUM(amount), 0) as total_volume,
                COALESCE(SUM(markup_amount), 0) as total_profit,
                COUNT(CASE WHEN status = 'finished' THEN 1 END) as completed,
                COUNT(CASE WHEN status = 'failed' THEN 1 END) as failed
            FROM exchanges
            WHERE date(created_at) = ?""",
            (today,),
        )
        row = await cursor.fetchone()
        return dict(row) if row else {
            "total_count": 0,
            "total_volume": 0.0,
            "total_profit": 0.0,
            "completed": 0,
            "failed": 0,
        }
    finally:
        await db.close()


async def increment_user_stats(user_id: int, amount: float) -> None:
    """Increment user exchange count and volume."""
    db = await get_db()
    try:
        await db.execute(
            """UPDATE users
            SET exchanges_count = exchanges_count + 1,
                total_volume = total_volume + ?
            WHERE user_id = ?""",
            (amount, user_id),
        )
        await db.commit()
    finally:
        await db.close()
