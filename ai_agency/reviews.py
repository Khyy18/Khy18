"""Система отзывов AI-агентства: автомодерация, публикация, социальное доказательство."""

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

# Minimum review length
_MIN_REVIEW_LENGTH = 10


def auto_moderate(text: str) -> bool:
    """
    Filter profanity and validate review text.

    Returns True if text is clean and valid, False otherwise.
    Checks:
    - No profanity words
    - Minimum length (10 characters)
    """
    # Check minimum length
    if len(text.strip()) < _MIN_REVIEW_LENGTH:
        return False

    # Check profanity
    words = text.lower().split()
    for word in words:
        # Strip punctuation
        clean_word = "".join(c for c in word if c.isalpha())
        if clean_word in _PROFANITY_WORDS:
            return False
    return True


async def submit_review(client_id: int, order_id: int, text: str, rating: int) -> Optional[int]:
    """
    Submit a review with auto-moderation.

    If AUTO_MODERATE_REVIEWS=True:
      - Passes filters -> auto-published (status='approved')
      - Fails filters -> queued for manual moderation (status='pending')
    If AUTO_MODERATE_REVIEWS=False:
      - All reviews go to manual moderation (status='pending')

    Returns review ID if saved, None if critically rejected.
    """
    if config.AUTO_MODERATE_REVIEWS:
        is_clean = auto_moderate(text)
        if is_clean:
            status = "approved"
            approved_at = datetime.utcnow().isoformat()
        else:
            # Failed auto-moderation -> queue for manual review
            status = "pending"
            approved_at = None
            logger.info(
                "Review from client %d failed auto-moderation, queued for manual check",
                client_id,
            )
    else:
        # All reviews go to manual moderation
        status = "pending"
        approved_at = None

    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        cursor = await db.execute(
            """INSERT INTO reviews (client_id, order_id, text, rating, status, created_at, approved_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (client_id, order_id, text, rating, status, datetime.utcnow().isoformat(), approved_at),
        )
        await db.commit()
        review_id = cursor.lastrowid

    if status == "approved":
        logger.info("Review %d auto-approved for client %d", review_id, client_id)

    return review_id


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
