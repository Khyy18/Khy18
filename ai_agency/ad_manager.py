"""Модуль управления рекламой AI-агентства: бюджет, каналы, ROI, автопилот."""

import logging
from datetime import datetime, timedelta
from typing import List, Optional

import aiosqlite

import config
import database

logger = logging.getLogger(__name__)

# Graceful import ad_copywriter
try:
    import ad_copywriter
except ImportError:
    ad_copywriter = None


async def calculate_ad_budget(days: int = 7) -> float:
    """
    Calculate ad budget as AD_BUDGET_PERCENT% of last week revenue.
    """
    _, revenue = await database.get_stats_for_period(days)
    budget = revenue * config.AD_BUDGET_PERCENT / 100
    return round(budget, 2)


async def recommend_channels(topic: str, budget: float) -> List[dict]:
    """
    Recommend channels for advertising based on topic and budget.
    Uses Telega.in API if key available, otherwise mock data.
    """
    # Try Telega.in API if key is configured
    if config.TELEGA_IN_API_KEY:
        channels = await _telega_in_search(topic, budget)
        if channels:
            return channels

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


async def _telega_in_search(topic: str, budget: float) -> List[dict]:
    """Search channels via Telega.in API."""
    try:
        import aiohttp
        async with aiohttp.ClientSession() as session:
            headers = {"Authorization": f"Bearer {config.TELEGA_IN_API_KEY}"}
            params = {"query": topic, "budget_max": int(budget)}
            async with session.get(
                "https://telega.in/api/channels/search",
                headers=headers,
                params=params,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    channels = []
                    for ch in data.get("channels", [])[:10]:
                        channels.append({
                            "channel": ch.get("username", ""),
                            "subscribers": ch.get("subscribers", 0),
                            "cpm": ch.get("cpm", 0),
                            "estimated_reach": ch.get("reach", 0),
                            "topic": topic,
                        })
                    return channels
    except Exception as e:
        logger.warning("Telega.in API error: %s", e)
    return []


async def _telega_in_place_ad(channel: str, text: str, budget: float) -> bool:
    """Place ad via Telega.in API."""
    try:
        import aiohttp
        async with aiohttp.ClientSession() as session:
            headers = {"Authorization": f"Bearer {config.TELEGA_IN_API_KEY}"}
            payload = {
                "channel": channel,
                "text": text,
                "budget": budget,
            }
            async with session.post(
                "https://telega.in/api/orders/create",
                headers=headers,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status in (200, 201):
                    logger.info("Ad placed on %s via Telega.in (budget=%.0f)", channel, budget)
                    return True
                else:
                    logger.warning("Telega.in place ad failed (status=%d)", resp.status)
    except Exception as e:
        logger.warning("Telega.in place ad error: %s", e)
    return False


async def get_best_roi_channels(limit: int = 5) -> List[dict]:
    """Get channels with best ROI from campaign history."""
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """SELECT channel_name, SUM(budget) as total_budget,
                      SUM(clicks) as total_clicks, SUM(conversions) as total_conversions,
                      AVG(roi) as avg_roi
               FROM ad_campaigns
               WHERE budget > 0
               GROUP BY channel_name
               ORDER BY avg_roi DESC
               LIMIT ?""",
            (limit,),
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


async def run_autopilot(bot) -> None:
    """
    Run ad autopilot: calculate budget, generate creatives, place ads.

    Called weekly by scheduler when AD_AUTOPILOT=True.
    """
    if not config.AD_AUTOPILOT:
        return

    budget = await calculate_ad_budget(7)
    if budget < 500:
        logger.info("Ad autopilot: budget too low (%.0f), skipping", budget)
        return

    # Get best performing channels from history
    best_channels = await get_best_roi_channels(3)

    # Determine topic from kwork keywords
    keywords = config.KWORK_KEYWORDS.split(",")
    topic = keywords[0].strip() if keywords else "copywriting"

    # If no history, get recommendations
    if not best_channels:
        best_channels_list = await recommend_channels(topic, budget)
        target_channels = [ch["channel"] for ch in best_channels_list[:3]]
    else:
        target_channels = [ch["channel_name"] for ch in best_channels]

    # Generate creative via ad_copywriter
    creative_text = ""
    if ad_copywriter:
        try:
            variants = await ad_copywriter.generate_ad_copy(topic, 10000, "informal")
            if variants:
                creative_text = variants[0].get("text", "")
        except Exception as e:
            logger.warning("Ad copywriter error: %s", e)

    if not creative_text:
        creative_text = f"AI-{topic} - profессиональный контент за минуты!"

    # Distribute budget among channels
    budget_per_channel = budget / max(len(target_channels), 1)

    placed = 0
    for channel in target_channels:
        if config.TELEGA_IN_API_KEY:
            success = await _telega_in_place_ad(channel, creative_text, budget_per_channel)
        else:
            # Mock placement (log only)
            success = True
            logger.info("Ad autopilot [mock]: placed on %s (budget=%.0f)", channel, budget_per_channel)

        if success:
            await create_ad_campaign(channel, budget_per_channel)
            placed += 1

    # Notify admin about autopilot actions
    admin_id = config.ADMIN_TELEGRAM_ID
    if admin_id and placed > 0:
        text = (
            f"\U0001f680 <b>Автопилот рекламы</b>\n\n"
            f"Бюджет: {budget:.0f} \u20bd\n"
            f"Размещено: {placed} каналов\n"
            f"Бюджет/канал: {budget_per_channel:.0f} \u20bd\n\n"
            f"Каналы: {', '.join(target_channels[:3])}"
        )
        try:
            await bot.send_message(chat_id=admin_id, text=text, parse_mode="HTML")
        except Exception as e:
            logger.debug("Не удалось уведомить о размещении: %s", e)

    logger.info("Ad autopilot: placed %d ads, budget=%.0f", placed, budget)


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


async def get_demo_creatives() -> List[dict]:
    """Get demo creatives from demo_generator for ad campaigns."""
    try:
        import demo_generator
        return await demo_generator.get_demo_creatives()
    except ImportError:
        logger.debug("demo_generator not available")
        return []
    except Exception as e:
        logger.error("Error getting demo creatives: %s", e)
        return []
