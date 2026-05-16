"""Background tasks using arq (Redis-based task queue)."""
from __future__ import annotations


import logging
from datetime import datetime, timedelta

from arq import cron
from sqlalchemy import select

from app.config import settings
from app.db.models import Alert, Product, User
from app.db.session import async_session
from app.services.arbitrage_service import arbitrage_service
from app.services.niche_detector import niche_detector
from app.services.push_service import push_service

logger = logging.getLogger(__name__)

async def task_parse_marketplace(ctx: dict, marketplace: str = "wb") -> dict:
    """Background task: parse marketplace products."""

    logger.info("Starting parse for marketplace: %s", marketplace)
    # Actual parsing logic would use httpx + proxy_pool
    return {"marketplace": marketplace, "status": "completed"}

async def task_check_alerts(ctx: dict) -> dict:
    """Background task: check price alerts and notify users."""
    async with async_session() as db:
        result = await db.execute(
            select(Alert).where(Alert.is_active == True)
        )
        alerts = result.scalars().all()
        notified = 0

        for alert in alerts:
            # Check if any product matches alert criteria
            query = select(Product).where(
                Product.name.ilike(f"%{alert.keyword}%")
            )
            if alert.category:
                query = query.where(Product.category == alert.category)
            query = query.limit(1)

            product_result = await db.execute(query)
            product = product_result.scalar_one_or_none()
            if product:
                # Get user and send notification
                user_result = await db.execute(
                    select(User).where(User.id == alert.user_id)
                )
                user = user_result.scalar_one_or_none()
                if user and user.fcm_token:
                    await push_service.send_push(
                        user,
                        title="Товар найден!",
                        body=f"Найден товар по запросу '{alert.keyword}': {product.name}",
                        db=db,
                    )
                    notified += 1

    return {"checked": len(alerts), "notified": notified}

async def task_arbitrage_scan(ctx: dict) -> dict:
    """Background task: run arbitrage scan."""
    async with async_session() as db:
        count = await arbitrage_service.scan(
            category=None,
            min_diff_percent=10.0,
            limit=50,
            db=db,
        )
    return {"found": count}

async def task_niche_analysis(ctx: dict) -> dict:
    """Background task: analyze trending niches."""
    async with async_session() as db:
        results = await niche_detector.analyze(db)
    return {"niches_found": len(results)}

async def task_cleanup_expired_vip(ctx: dict) -> dict:
    """Background task: deactivate expired VIP subscriptions."""
    async with async_session() as db:
        result = await db.execute(
            select(User).where(
                User.is_vip == True,
                User.vip_expires_at < datetime.utcnow(),
            )
        )
        expired_users = result.scalars().all()
        for user in expired_users:
            user.is_vip = False
        await db.commit()
    return {"expired": len(expired_users)}

class WorkerSettings:
    """arq worker settings."""

    redis_settings = None  # Set dynamically from app.config

    functions = [
        task_parse_marketplace,
        task_check_alerts,
        task_arbitrage_scan,
        task_niche_analysis,
        task_cleanup_expired_vip,
    ]

    cron_jobs = [
        cron(task_check_alerts, hour=None, minute={0, 30}),  # Every 30 min
        cron(task_arbitrage_scan, hour={6, 12, 18}),  # 3 times a day
        cron(task_niche_analysis, hour={3}),  # Once a day at 3 AM
        cron(task_cleanup_expired_vip, hour={0}),  # Daily at midnight
    ]
