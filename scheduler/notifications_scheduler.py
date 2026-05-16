"""Notifications Scheduler - manages weekly digest and real-time alert dispatch."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

import redis.asyncio as aioredis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from core.models import Tenant
from integrations.notifications import (
    _get_tenant_notification_config,
    real_time_alert,
    weekly_digest,
)

logger = logging.getLogger(__name__)


class NotificationsScheduler:
    """Schedules and dispatches notification tasks.

    - Weekly digest: runs every hour, but only sends on Monday 9:00 AM UTC
    - Real-time alerts: provides method to be called by other components
    """

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        redis_url: str | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._redis_url = redis_url
        self._redis: aioredis.Redis | None = None

    async def _get_redis(self) -> aioredis.Redis | None:
        """Get or create Redis connection. Returns None if redis_url not configured."""
        if self._redis_url is None:
            return None
        if self._redis is None:
            self._redis = aioredis.from_url(self._redis_url, decode_responses=True)
        return self._redis

    async def weekly_digest_tick(self) -> None:
        """Check if it's Monday 9:00 AM UTC hour. If so, send digests to all tenants with weekly_digest enabled."""
        now = datetime.now(timezone.utc)

        # Only send on Monday (weekday 0) at 9:00 AM UTC hour
        if now.weekday() != 0 or now.hour != 9:
            logger.debug(
                "Not Monday 9 AM UTC (weekday=%d, hour=%d), skipping digest",
                now.weekday(),
                now.hour,
            )
            return

        logger.info("Monday 9 AM UTC - sending weekly digests")

        async with self._session_factory() as session:
            result = await session.execute(select(Tenant))
            tenants = result.scalars().all()

            for tenant in tenants:
                try:
                    # Idempotency guard: prevent duplicate digest sends
                    redis = await self._get_redis()
                    if redis is not None:
                        iso_year, week_number, _ = now.isocalendar()
                        idempotency_key = f"digest_sent:{tenant.id}:{iso_year}:{week_number}"
                        already_sent = not await redis.set(
                            idempotency_key, "1", nx=True, ex=604800
                        )
                        if already_sent:
                            logger.debug(
                                "Weekly digest already sent for tenant %s (week %d/%d), skipping",
                                tenant.id,
                                iso_year,
                                week_number,
                            )
                            continue

                    channels, preferences = await _get_tenant_notification_config(
                        tenant.id, session
                    )
                    if not preferences.get("weekly_digest", True):
                        logger.debug("Weekly digest disabled for tenant %s", tenant.id)
                        continue
                    if not channels:
                        logger.debug("No channels configured for tenant %s", tenant.id)
                        continue

                    await weekly_digest(tenant.id, session)
                    logger.info("Weekly digest sent for tenant %s", tenant.id)
                except Exception as exc:
                    logger.error(
                        "Failed to send weekly digest for tenant %s: %s",
                        tenant.id,
                        exc,
                    )

    async def send_real_time_alert(
        self, tenant_id: UUID, event_type: str, lead_data: dict[str, Any]
    ) -> None:
        """Non-blocking wrapper to send a real-time alert. Catches all exceptions."""
        try:
            async with self._session_factory() as session:
                await real_time_alert(tenant_id, event_type, lead_data, session)
        except Exception as exc:
            logger.error(
                "Failed to send real-time alert (tenant=%s, type=%s): %s",
                tenant_id,
                event_type,
                exc,
            )

    async def close(self) -> None:
        """Close Redis connection."""
        if self._redis:
            await self._redis.close()
            self._redis = None
