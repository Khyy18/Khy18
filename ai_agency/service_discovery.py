"""Модуль обнаружения трендов и новых услуг AI-агентства."""

import logging
from collections import Counter
from datetime import datetime, timedelta
from typing import List, Optional

import aiosqlite

import config

logger = logging.getLogger(__name__)

# Keywords for grouping similar requests
_CATEGORY_KEYWORDS = {
    "перевод": ["перевод", "translate", "translation", "переведи"],
    "дизайн": ["дизайн", "design", "логотип", "баннер", "макет"],
    "код": ["код", "code", "программ", "скрипт", "бот", "сайт"],
    "видео": ["видео", "video", "монтаж", "ролик", "клип"],
    "аудио": ["аудио", "audio", "озвучк", "подкаст", "музык"],
    "маркетинг": ["маркетинг", "реклам", "smm", "таргет", "продвиж"],
    "аналитика": ["аналитик", "дашборд", "отчёт", "статистик"],
    "юридический": ["договор", "юрид", "правов", "иск", "контракт"],
}


def _categorize_request(text: str) -> str:
    """Categorize a request text by keywords. Returns category or 'other'."""
    text_lower = text.lower()
    for category, keywords in _CATEGORY_KEYWORDS.items():
        for keyword in keywords:
            if keyword in text_lower:
                return category
    return "other"


async def log_unrecognized_request(client_id: int, text: str) -> None:
    """Save unrecognized request to database for trend analysis."""
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        await db.execute(
            "INSERT INTO unrecognized_requests (client_id, text, created_at) VALUES (?, ?, ?)",
            (client_id, text, datetime.utcnow().isoformat()),
        )
        await db.commit()


async def analyze_trends(days: int = 7) -> List[dict]:
    """
    Group similar requests and detect trends.
    If >5 similar in a week, return as detected trend.
    """
    since = (datetime.utcnow() - timedelta(days=days)).isoformat()

    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM unrecognized_requests WHERE created_at >= ? ORDER BY created_at DESC",
            (since,),
        )
        rows = await cursor.fetchall()

    # Group by category
    categories: dict = {}
    for row in rows:
        row_dict = dict(row)
        category = _categorize_request(row_dict["text"])
        if category not in categories:
            categories[category] = []
        categories[category].append(row_dict)

    # Detect trends (>5 requests in category)
    trends = []
    for category, requests in categories.items():
        if len(requests) > 5:
            trends.append({
                "category": category,
                "count": len(requests),
                "sample_requests": [r["text"] for r in requests[:5]],
            })

    return sorted(trends, key=lambda x: x["count"], reverse=True)


def suggest_service_prompt(topic: str, sample_requests: List[str]) -> str:
    """Generate a system prompt suggestion for a new service based on topic and samples."""
    samples_text = "\n".join(f"- {r}" for r in sample_requests[:5])
    prompt = (
        f"You are an AI assistant specializing in {topic}.\n"
        f"Based on user requests like:\n{samples_text}\n\n"
        f"Provide high-quality {topic} services. "
        f"Be professional, accurate, and deliver results in the requested format."
    )
    return prompt


async def get_unrecognized_requests(days: int = 7) -> List[dict]:
    """Get unrecognized requests for admin review."""
    since = (datetime.utcnow() - timedelta(days=days)).isoformat()

    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM unrecognized_requests WHERE created_at >= ? ORDER BY created_at DESC",
            (since,),
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


async def notify_admin_trends(bot) -> None:
    """Send detected trends to admin via bot message."""
    trends = await analyze_trends(days=7)
    if not trends:
        return

    text = "\U0001f4ca <b>Обнаружены тренды запросов</b>\n\n"
    for trend in trends:
        text += (
            f"\U0001f525 <b>{trend['category']}</b>: "
            f"{trend['count']} запросов за неделю\n"
            f"  Примеры: {', '.join(trend['sample_requests'][:3])}\n\n"
        )

    try:
        await bot.send_message(
            chat_id=config.ADMIN_TELEGRAM_ID,
            text=text,
            parse_mode="HTML",
        )
    except Exception as e:
        logger.error("Ошибка отправки трендов админу: %s", e)
