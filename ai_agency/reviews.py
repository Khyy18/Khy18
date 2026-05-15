"""Система отзывов AI-агентства: модерация, публикация, социальное доказательство."""

import logging
from datetime import datetime
from typing import List, Optional

import aiosqlite

import config

logger = logging.getLogger(__name__)

# Basic profanity word list (Russian + English)
_PROFANITY_WORDS = {
    # Russian
    "блять", "сука", "хуй", "пизда", "ебать", "нахуй", "пиздец",
    "мудак", "дебил", "идиот", "урод", "гандон", "залупа", "шлюха",
    # English
    "fuck", "shit", "bitch", "asshole", "bastard", "dick", "crap",
    "damn", "hell", "whore", "slut",
}


def auto_moderate(text: str) -> bool:
    """
    Filter profanity from review text.

    Returns True if text is clean, False if contains profanity.
    """
    words = text.lower().split()
    for word in words:
        # Strip punctuation
        clean_word = "".join(c for c in word if c.isalpha())
        if clean_word in _PROFANITY_WORDS:
            return False
    return True


async def submit_review(client_id: int, order_id: int, text: str, rating: int) -> Optional[int]:
    """
    Submit a review. Auto-moderate and save to DB.

    Returns review ID if saved, None if rejected by auto-moderation.
    """
    is_clean = auto_moderate(text)
    status = "pending" if is_clean else "rejected"

    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        cursor = await db.execute(
            """INSERT INTO reviews (client_id, order_id, text, rating, status, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (client_id, order_id, text, rating, status, datetime.utcnow().isoformat()),
        )
        await db.commit()
        return cursor.lastrowid if is_clean else None


async def approve_review(review_id: int) -> None:
    """Approve a pending review."""
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        await db.execute(
            "UPDATE reviews SET status = 'approved', approved_at = ? WHERE id = ?",
            (datetime.utcnow().isoformat(), review_id),
        )
        await db.commit()


async def reject_review(review_id: int) -> None:
    """Reject a pending review."""
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        await db.execute(
            "UPDATE reviews SET status = 'rejected' WHERE id = ?",
            (review_id,),
        )
        await db.commit()


async def get_pending_reviews() -> List[dict]:
    """Get all pending reviews for admin moderation."""
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM reviews WHERE status = 'pending' ORDER BY created_at DESC"
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


async def get_approved_reviews(limit: int = 10) -> List[dict]:
    """Get approved reviews for landing page display."""
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM reviews WHERE status = 'approved' ORDER BY approved_at DESC LIMIT ?",
            (limit,),
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


async def get_review_count() -> int:
    """Get count of approved reviews for social proof counter."""
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        cursor = await db.execute(
            "SELECT COUNT(*) FROM reviews WHERE status = 'approved'"
        )
        row = await cursor.fetchone()
        return row[0] if row else 0


async def post_best_reviews(bot) -> None:
    """Post best approved reviews to channel (for scheduler)."""
    if not config.CHANNEL_ID:
        return

    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """SELECT * FROM reviews
               WHERE status = 'approved' AND rating >= 4
               ORDER BY approved_at DESC LIMIT 3"""
        )
        reviews = await cursor.fetchall()

    for review in reviews:
        review_dict = dict(review)
        stars = "\u2b50" * review_dict["rating"]
        text = (
            f"\U0001f4ac <b>Отзыв клиента</b>\n\n"
            f"{stars}\n\n"
            f"\"{review_dict['text']}\"\n\n"
            f"#отзыв #AIагентство"
        )
        try:
            await bot.send_message(
                chat_id=config.CHANNEL_ID,
                text=text,
                parse_mode="HTML",
            )
        except Exception as e:
            logger.error("Ошибка публикации отзыва в канал: %s", e)
