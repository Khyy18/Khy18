"""Ежедневный автоотчёт владельцу: выручка, заказы, клиенты, расходы, алерты."""

import logging
from datetime import datetime, timedelta
from typing import List, Optional

import aiosqlite

import config
import database
from utils import _card, format_number, sparkline

logger = logging.getLogger(__name__)


async def get_revenue_today() -> float:
    """Get today's revenue from completed orders."""
    today = datetime.utcnow().strftime("%Y-%m-%d")
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        cursor = await db.execute(
            """SELECT COALESCE(SUM(price), 0) FROM orders
               WHERE DATE(created_at) = ? AND status = 'completed'""",
            (today,),
        )
        row = await cursor.fetchone()
        return row[0] if row else 0.0


async def get_revenue_yesterday() -> float:
    """Get yesterday's revenue from completed orders."""
    yesterday = (datetime.utcnow() - timedelta(days=1)).strftime("%Y-%m-%d")
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        cursor = await db.execute(
            """SELECT COALESCE(SUM(price), 0) FROM orders
               WHERE DATE(created_at) = ? AND status = 'completed'""",
            (yesterday,),
        )
        row = await cursor.fetchone()
        return row[0] if row else 0.0


async def get_orders_today() -> int:
    """Get count of orders created today."""
    today = datetime.utcnow().strftime("%Y-%m-%d")
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        cursor = await db.execute(
            "SELECT COUNT(*) FROM orders WHERE DATE(created_at) = ?",
            (today,),
        )
        row = await cursor.fetchone()
        return row[0] if row else 0


async def get_new_clients_today() -> int:
    """Get count of new clients registered today."""
    today = datetime.utcnow().strftime("%Y-%m-%d")
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        cursor = await db.execute(
            "SELECT COUNT(*) FROM clients WHERE DATE(registered_at) = ?",
            (today,),
        )
        row = await cursor.fetchone()
        return row[0] if row else 0


async def get_avg_check_today() -> float:
    """Get average check for today's completed orders."""
    today = datetime.utcnow().strftime("%Y-%m-%d")
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        cursor = await db.execute(
            """SELECT AVG(price) FROM orders
               WHERE DATE(created_at) = ? AND status = 'completed' AND price > 0""",
            (today,),
        )
        row = await cursor.fetchone()
        return row[0] if row and row[0] else 0.0


async def get_api_costs_today() -> float:
    """
    Estimate API costs for today based on completed orders.
    Approximation: each order uses ~2K tokens on average.
    """
    orders_today = await get_orders_today()
    avg_tokens_per_order = 2.0  # 2K tokens per order average
    cost = orders_today * avg_tokens_per_order * config.OPENAI_TOKEN_COST_PER_1K
    return round(cost, 2)


async def get_revenue_last_7_days() -> List[float]:
    """Get daily revenue for last 7 days as a list of floats."""
    values = []
    for i in range(6, -1, -1):
        day = (datetime.utcnow() - timedelta(days=i)).strftime("%Y-%m-%d")
        async with aiosqlite.connect(config.DATABASE_PATH) as db:
            cursor = await db.execute(
                """SELECT COALESCE(SUM(price), 0) FROM orders
                   WHERE DATE(created_at) = ? AND status = 'completed'""",
                (day,),
            )
            row = await cursor.fetchone()
            values.append(row[0] if row else 0.0)
    return values


async def get_alerts() -> List[str]:
    """Check for system alerts/problems."""
    alerts = []

    # Check if queue is near capacity
    try:
        async with aiosqlite.connect(config.DATABASE_PATH) as db:
            cursor = await db.execute(
                "SELECT COUNT(*) FROM orders WHERE status = 'pending'"
            )
            row = await cursor.fetchone()
            pending = row[0] if row else 0
            if pending > config.QUEUE_MAX_SIZE * 0.8:
                alerts.append(f"\U0001f534 Очередь переполнена: {pending}/{config.QUEUE_MAX_SIZE}")
    except Exception:
        pass

    # Check for failed orders today
    try:
        today = datetime.utcnow().strftime("%Y-%m-%d")
        async with aiosqlite.connect(config.DATABASE_PATH) as db:
            cursor = await db.execute(
                "SELECT COUNT(*) FROM orders WHERE DATE(created_at) = ? AND status = 'failed'",
                (today,),
            )
            row = await cursor.fetchone()
            failed = row[0] if row else 0
            if failed > 0:
                alerts.append(f"\U0001f534 Ошибки API: {failed} заказов с ошибками")
    except Exception:
        pass

    return alerts


def _pnl_indicator(current: float, previous: float) -> str:
    """Format PnL change with arrow indicator."""
    if previous == 0:
        if current > 0:
            return "\u25b2 new"
        return "\u2014"
    change = (current - previous) / previous * 100
    if change > 0:
        return f"\u25b2+{change:.0f}%"
    elif change < 0:
        return f"\u25bc{change:.0f}%"
    else:
        return "\u2014 0%"


def _status_dot(value: float, threshold_green: float, threshold_yellow: float) -> str:
    """Return status indicator based on value thresholds."""
    if value >= threshold_green:
        return "\U0001f7e2"  # green
    elif value >= threshold_yellow:
        return "\U0001f7e1"  # yellow
    else:
        return "\U0001f534"  # red


async def generate_daily_report() -> str:
    """
    Generate daily report card for owner.

    Returns formatted HTML string ready for Telegram.
    """
    revenue_today = await get_revenue_today()
    revenue_yesterday = await get_revenue_yesterday()
    orders_today = await get_orders_today()
    new_clients = await get_new_clients_today()
    avg_check = await get_avg_check_today()
    api_costs = await get_api_costs_today()
    revenue_7d = await get_revenue_last_7_days()
    alerts = await get_alerts()

    # PnL indicator
    pnl = _pnl_indicator(revenue_today, revenue_yesterday)

    # Balance (revenue - costs)
    balance = revenue_today - api_costs

    # Sparkline
    spark = sparkline(revenue_7d) if any(v > 0 for v in revenue_7d) else "\u2581" * 7

    # Status dot based on revenue
    status = _status_dot(revenue_today, 5000, 1000)

    # Build body lines
    body_lines = [
        f"<pre>",
        f"{status} Выручка:     {format_number(revenue_today)} \u20bd  {pnl}",
        f"\U0001f4e6 Заказов:      {orders_today}",
        f"\U0001f464 Новых:        {new_clients}",
        f"\U0001f4b3 Средний чек:  {format_number(avg_check)} \u20bd",
        f"\U0001f4b8 Расходы API:  {format_number(api_costs)} \u20bd",
        f"\U0001f4b0 Баланс:       {format_number(balance)} \u20bd",
        f"",
        f"\U0001f4c8 7 дней: {spark}",
        f"</pre>",
    ]

    # Add alerts if any
    if alerts:
        body_lines.append("")
        body_lines.append("<b>Алерты:</b>")
        for alert in alerts:
            body_lines.append(f"  {alert}")

    return _card("Дневной отчёт", "\U0001f4ca", body_lines)


async def send_daily_report(bot) -> None:
    """Send daily report to admin/owner via Telegram."""
    admin_id = config.ADMIN_TELEGRAM_ID
    if not admin_id:
        return

    try:
        report = await generate_daily_report()
        await bot.send_message(
            chat_id=admin_id,
            text=report,
            parse_mode="HTML",
        )
        logger.info("Daily report sent to admin %d", admin_id)
    except Exception as e:
        logger.error("Failed to send daily report: %s", e)
