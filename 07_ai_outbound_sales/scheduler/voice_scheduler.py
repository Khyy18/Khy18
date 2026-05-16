"""Voice Scheduler - manages the voice call queue and dispatches calls."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

import redis.asyncio as aioredis
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from core.config import Settings
from core.models import Call, CallStatus

logger = logging.getLogger(__name__)

# Redis key patterns
_VOICE_QUEUE_KEY = "voice:queue:{tenant_id}"
_VOICE_ACTIVE_KEY = "voice:active:{tenant_id}"
_VOICE_RETRY_KEY = "voice:retry:{call_id}"

# Maximum retry attempts
_MAX_RETRY_ATTEMPTS = 3


class VoiceScheduler:
    """Manages voice call scheduling, queuing, and dispatch."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        call_manager: Any,
        settings: Settings,
        redis_url: str,
    ) -> None:
        self._session_factory = session_factory
        self._call_manager = call_manager
        self._settings = settings
        self._redis_url = redis_url
        self._redis: aioredis.Redis | None = None

    async def _get_redis(self) -> aioredis.Redis:
        """Get or create Redis connection."""
        if self._redis is None:
            self._redis = aioredis.from_url(self._redis_url, decode_responses=True)
        return self._redis

    async def run_voice_tick(self) -> None:
        """Process pending voice calls from the queue.

        Called periodically by the scheduler loop. Checks calling hours,
        concurrent call limits, and dispatches queued calls.
        """
        if not await self._is_within_calling_hours():
            logger.debug("Outside calling hours, skipping voice tick")
            return

        redis = await self._get_redis()

        # Get all tenant queues
        cursor = 0
        tenant_queues: list[str] = []
        while True:
            cursor, keys = await redis.scan(
                cursor=cursor, match="voice:queue:*", count=100
            )
            tenant_queues.extend(keys)
            if cursor == 0:
                break

        for queue_key in tenant_queues:
            tenant_id = queue_key.split(":")[-1]
            await self._process_tenant_queue(tenant_id)

    async def schedule_call(
        self,
        lead_id: str | uuid.UUID,
        tenant_id: str | uuid.UUID,
        campaign_id: str | uuid.UUID | None = None,
        script_id: str | uuid.UUID | None = None,
        priority: int = 0,
    ) -> str:
        """Add a call to the priority queue.

        Args:
            lead_id: UUID of the lead to call.
            tenant_id: UUID of the tenant.
            campaign_id: Optional campaign ID.
            script_id: Optional script ID.
            priority: Priority score (higher = sooner). Defaults to 0.

        Returns:
            Queue entry ID.
        """
        redis = await self._get_redis()
        entry_id = str(uuid.uuid4())
        queue_key = _VOICE_QUEUE_KEY.format(tenant_id=str(tenant_id))

        # Store call metadata
        entry_data = {
            "entry_id": entry_id,
            "lead_id": str(lead_id),
            "tenant_id": str(tenant_id),
            "campaign_id": str(campaign_id) if campaign_id else "",
            "script_id": str(script_id) if script_id else "",
            "attempts": 0,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

        # Store metadata
        await redis.set(f"voice:entry:{entry_id}", str(entry_data), ex=86400)

        # Add to sorted set with priority as score (higher priority = higher score)
        await redis.zadd(queue_key, {entry_id: priority})

        logger.info(
            "Scheduled voice call for lead %s (tenant=%s, priority=%d, entry=%s)",
            lead_id,
            tenant_id,
            priority,
            entry_id,
        )
        return entry_id

    async def _is_within_calling_hours(self, timezone_str: str = "UTC") -> bool:
        """Check if current time is within allowed calling hours.

        Args:
            timezone_str: Timezone string (currently uses UTC).

        Returns:
            True if within calling hours.
        """
        now = datetime.now(timezone.utc)
        start_hour = self._settings.voice_calling_hours_start
        end_hour = self._settings.voice_calling_hours_end
        return start_hour <= now.hour < end_hour

    async def _get_concurrent_calls_count(self, tenant_id: str) -> int:
        """Get the number of currently active calls for a tenant.

        Args:
            tenant_id: Tenant UUID string.

        Returns:
            Number of active calls.
        """
        redis = await self._get_redis()
        active_key = _VOICE_ACTIVE_KEY.format(tenant_id=tenant_id)
        count = await redis.scard(active_key)
        return count or 0

    async def _should_retry(self, call_record: dict[str, Any]) -> bool:
        """Determine if a failed call should be retried.

        Args:
            call_record: Dict with call attempt info including 'attempts' count.

        Returns:
            True if retry is appropriate (under max attempts).
        """
        attempts = call_record.get("attempts", 0)
        return attempts < _MAX_RETRY_ATTEMPTS

    async def _get_next_calls(
        self, tenant_id: str, limit: int = 5
    ) -> list[dict[str, Any]]:
        """Get the next calls to make from the priority queue.

        Args:
            tenant_id: Tenant UUID string.
            limit: Maximum number of calls to retrieve.

        Returns:
            List of call entry dicts sorted by priority (highest first).
        """
        redis = await self._get_redis()
        queue_key = _VOICE_QUEUE_KEY.format(tenant_id=tenant_id)

        # Get top entries by score (highest priority first)
        entries = await redis.zrevrange(queue_key, 0, limit - 1)

        results: list[dict[str, Any]] = []
        for entry_id in entries:
            raw = await redis.get(f"voice:entry:{entry_id}")
            if raw:
                try:
                    entry_data = eval(raw)  # noqa: S307
                    results.append(entry_data)
                except Exception:
                    results.append({"entry_id": entry_id, "tenant_id": tenant_id})
            else:
                results.append({"entry_id": entry_id, "tenant_id": tenant_id})

        return results

    async def _process_tenant_queue(self, tenant_id: str) -> None:
        """Process the call queue for a single tenant."""
        concurrent_count = await self._get_concurrent_calls_count(tenant_id)
        max_concurrent = self._settings.voice_concurrent_calls_limit

        available_slots = max_concurrent - concurrent_count
        if available_slots <= 0:
            logger.debug(
                "Tenant %s at concurrent call limit (%d/%d)",
                tenant_id,
                concurrent_count,
                max_concurrent,
            )
            return

        next_calls = await self._get_next_calls(tenant_id, limit=available_slots)
        redis = await self._get_redis()
        queue_key = _VOICE_QUEUE_KEY.format(tenant_id=tenant_id)
        active_key = _VOICE_ACTIVE_KEY.format(tenant_id=tenant_id)

        for entry in next_calls:
            entry_id = entry.get("entry_id", "")
            lead_id = entry.get("lead_id", "")
            campaign_id = entry.get("campaign_id") or None
            script_id = entry.get("script_id") or None

            if not lead_id:
                await redis.zrem(queue_key, entry_id)
                continue

            try:
                result = await self._call_manager.start_call(
                    lead_id=lead_id,
                    tenant_id=tenant_id,
                    campaign_id=campaign_id,
                    script_id=script_id,
                )

                # Remove from queue and track as active
                await redis.zrem(queue_key, entry_id)
                call_id = result.get("call_id", entry_id)
                await redis.sadd(active_key, call_id)
                await redis.expire(active_key, 3600)  # Expire after 1 hour

                logger.info(
                    "Dispatched voice call %s for lead %s (tenant=%s)",
                    call_id,
                    lead_id,
                    tenant_id,
                )
            except Exception as exc:
                logger.error(
                    "Failed to dispatch call for lead %s: %s", lead_id, exc
                )
                # Check retry eligibility
                if await self._should_retry(entry):
                    entry["attempts"] = entry.get("attempts", 0) + 1
                    await redis.set(
                        f"voice:entry:{entry_id}", str(entry), ex=86400
                    )
                else:
                    await redis.zrem(queue_key, entry_id)
                    logger.warning(
                        "Max retries reached for entry %s, removing from queue",
                        entry_id,
                    )
