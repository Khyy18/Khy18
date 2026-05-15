"""Модуль управления рекламой AI-агентства: бюджет, каналы, ROI."""

import logging
from datetime import datetime, timedelta
from typing import List, Optional

import aiosqlite

import config
import database

logger = logging.getLogger(__name__)


async def calculate_ad_budget(days: int = 7) -> float:
    """
    Calculate ad budget as AD_BUDGET_PERCENT% of last week revenue.
    """
    _, revenue = await database.get_stats_for_period(days)
    budget = revenue * config.AD_BUDGET_PERCENT / 100
    return round(budget, 2)


async def recommend_channels(topic: str, budget: float) -> List[dict]:
    """
    Mock Telega.in API integration - recommend channels for advertising.
    Structure ready for real API integration.
    """
    # Mock recommendations based on topic and budget
    recommendations = []

    if budget >= 1000:
        recommendations.append({
            "channel": f"@{topic}_news",
            "subscribers": 15000,
            "cpm": 150.0,
            "estimated_reach": int(budget / 150 * 1000),
            "topic": topic,
        })
    if budget >= 2000:
        recommendations.append({
            "channel": f"@{topic}_pro",
            "subscribers": 50000,
            "cpm": 200.0,
            "estimated_reach": int(budget / 200 * 1000),
            "topic": topic,
        })
    if budget >= 5000:
        recommendations.append({
            "channel": f"@{topic}_top",
            "subscribers": 100000,
            "cpm": 300.0,
            "estimated_reach": int(budget / 300 * 1000),
            "topic": topic,
        })

    return recommendations


async def track_utm(client_id: int, source: str) -> None:
    """Record ad source from deep link UTM."""
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        await db.execute(
            """INSERT INTO ad_campaigns (channel_name, budget, clicks, conversions, roi, source, created_at)
               VALUES (?, 0, 1, 0, 0, ?, ?)
               ON CONFLICT DO NOTHING""",
            (source, source, datetime.utcnow().isoformat()),
        )
        # Try to increment clicks for existing source
        await db.execute(
            "UPDATE ad_campaigns SET clicks = clicks + 1 WHERE source = ?",
            (source,),
        )
        await db.commit()


async def calculate_roi(source: str) -> float:
    """Calculate ROI for a specific ad channel/source."""
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM ad_campaigns WHERE source = ?", (source,)
        )
        row = await cursor.fetchone()
        if not row:
            return 0.0

        campaign = dict(row)
        budget = campaign.get("budget", 0)
        if budget == 0:
            return 0.0

        # ROI = (revenue - cost) / cost * 100
        conversions = campaign.get("conversions", 0)
        # Estimate revenue from conversions (avg order value)
        avg_check = await database.get_avg_check()
        revenue = conversions * avg_check
        roi = (revenue - budget) / budget * 100 if budget > 0 else 0
        return round(roi, 2)


async def get_ad_stats() -> dict:
    """Get advertising statistics summary for admin."""
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM ad_campaigns ORDER BY created_at DESC LIMIT 20"
        )
        rows = await cursor.fetchall()
        campaigns = [dict(row) for row in rows]

    total_budget = sum(c.get("budget", 0) for c in campaigns)
    total_clicks = sum(c.get("clicks", 0) for c in campaigns)
    total_conversions = sum(c.get("conversions", 0) for c in campaigns)

    weekly_budget = await calculate_ad_budget(7)

    return {
        "campaigns": campaigns,
        "total_budget": total_budget,
        "total_clicks": total_clicks,
        "total_conversions": total_conversions,
        "weekly_budget": weekly_budget,
        "conversion_rate": (
            total_conversions / total_clicks * 100 if total_clicks > 0 else 0
        ),
    }


async def create_ad_campaign(channel: str, budget: float) -> int:
    """Create a new ad campaign record."""
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        cursor = await db.execute(
            """INSERT INTO ad_campaigns (channel_name, budget, clicks, conversions, roi, source, created_at)
               VALUES (?, ?, 0, 0, 0, ?, ?)""",
            (channel, budget, channel, datetime.utcnow().isoformat()),
        )
        await db.commit()
        return cursor.lastrowid
