"""Adaptive rate limiting that monitors channel health and adjusts sending rates."""

import logging
import time
from typing import Any

import redis.asyncio as aioredis
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class ThrottleDecision(BaseModel):
    """Decision from the adaptive throttle system."""

    action: str  # allow, slow, pause, shift
    delay_seconds: int = 0
    reason: str = ""
    recommended_hours: list[int] | None = None


class AdaptiveThrottle:
    """Adaptive rate limiting that monitors bounce rate, LinkedIn warnings,
    and call answer rates to automatically adjust sending behavior.

    Email: Monitor bounce rate. If > 5% -> slow. If > 10% -> pause.
    LinkedIn: Monitor warnings. On warning -> pause 4h. Second within 24h -> 24h.
    Voice: Monitor answer rate per hour. If < 20% -> mark hour as cold.
    """

    def __init__(self, redis_url: str, settings: Any) -> None:
        self._redis: aioredis.Redis = aioredis.from_url(redis_url)
        self._settings = settings
        self._bounce_threshold = float(
            getattr(settings, "adaptive_throttle_bounce_threshold", 0.05)
        )
        self._cooldown_minutes = int(
            getattr(settings, "adaptive_throttle_cooldown_minutes", 30)
        )

    # -------------------------------------------------------------------------
    # Email throttle
    # -------------------------------------------------------------------------

    async def check_email_throttle(self, tenant_id: str) -> ThrottleDecision:
        """Check email throttle based on bounce rate in the last hour.

        Returns allow/slow/pause with recommended delay.
        """
        sent_key = f"throttle:email:sent:{tenant_id}"
        bounce_key = f"throttle:email:bounce:{tenant_id}"

        try:
            sent_raw = await self._redis.get(sent_key)
            bounce_raw = await self._redis.get(bounce_key)
        except Exception:
            return ThrottleDecision(action="allow", reason="redis_unavailable")

        sent = int(sent_raw) if sent_raw else 0
        bounces = int(bounce_raw) if bounce_raw else 0

        if sent == 0:
            return ThrottleDecision(action="allow", reason="no_sends_yet")

        bounce_rate = bounces / sent

        if bounce_rate > 0.10:
            return ThrottleDecision(
                action="pause",
                delay_seconds=self._cooldown_minutes * 60,
                reason=f"bounce_rate={bounce_rate:.2%}_exceeds_10%",
            )
        elif bounce_rate > self._bounce_threshold:
            return ThrottleDecision(
                action="slow",
                delay_seconds=30,
                reason=f"bounce_rate={bounce_rate:.2%}_exceeds_threshold",
            )

        return ThrottleDecision(action="allow", reason="bounce_rate_normal")

    async def record_bounce(self, tenant_id: str) -> None:
        """Increment bounce counter for the current hour window."""
        bounce_key = f"throttle:email:bounce:{tenant_id}"
        try:
            await self._redis.incr(bounce_key)
            await self._redis.expire(bounce_key, 3600)
        except Exception as exc:
            logger.warning("Failed to record bounce: %s", exc)

    async def record_email_sent(self, tenant_id: str) -> None:
        """Increment sent counter for the current hour window."""
        sent_key = f"throttle:email:sent:{tenant_id}"
        try:
            await self._redis.incr(sent_key)
            await self._redis.expire(sent_key, 3600)
        except Exception as exc:
            logger.warning("Failed to record email sent: %s", exc)

    # -------------------------------------------------------------------------
    # LinkedIn throttle
    # -------------------------------------------------------------------------

    async def check_linkedin_throttle(self, tenant_id: str) -> ThrottleDecision:
        """Check LinkedIn throttle based on warning signals.

        On first warning -> pause 4h. On second warning within 24h -> pause 24h.
        """
        pause_key = f"throttle:linkedin:pause_until:{tenant_id}"
        warnings_key = f"throttle:linkedin:warnings:{tenant_id}"

        try:
            pause_until_raw = await self._redis.get(pause_key)
            if pause_until_raw:
                pause_until = float(pause_until_raw)
                remaining = int(pause_until - time.time())
                if remaining > 0:
                    return ThrottleDecision(
                        action="pause",
                        delay_seconds=remaining,
                        reason="linkedin_cooling_down",
                    )
                else:
                    await self._redis.delete(pause_key)
        except Exception:
            pass

        return ThrottleDecision(action="allow", reason="linkedin_healthy")

    async def record_linkedin_warning(self, tenant_id: str) -> None:
        """Record a LinkedIn warning event. Triggers pause."""
        warnings_key = f"throttle:linkedin:warnings:{tenant_id}"
        pause_key = f"throttle:linkedin:pause_until:{tenant_id}"

        try:
            warning_count = await self._redis.incr(warnings_key)
            await self._redis.expire(warnings_key, 86400)  # 24h window

            if warning_count >= 2:
                # Second warning within 24h -> 24h pause
                pause_until = time.time() + 86400
                await self._redis.set(pause_key, str(pause_until))
                await self._redis.expire(pause_key, 86400)
                logger.warning(
                    "LinkedIn paused 24h for tenant %s (2nd warning)", tenant_id
                )
            else:
                # First warning -> 4h pause
                pause_until = time.time() + 14400
                await self._redis.set(pause_key, str(pause_until))
                await self._redis.expire(pause_key, 14400)
                logger.warning(
                    "LinkedIn paused 4h for tenant %s (1st warning)", tenant_id
                )
        except Exception as exc:
            logger.warning("Failed to record LinkedIn warning: %s", exc)

    # -------------------------------------------------------------------------
    # Voice throttle
    # -------------------------------------------------------------------------

    async def check_voice_throttle(
        self, tenant_id: str, hour: int
    ) -> ThrottleDecision:
        """Check voice throttle for a given hour.

        If answer rate drops below 20% for the hour -> mark as cold,
        recommend adjacent hours.
        """
        answer_key = f"throttle:voice:answered:{tenant_id}:{hour}"
        total_key = f"throttle:voice:total:{tenant_id}:{hour}"

        try:
            answered_raw = await self._redis.get(answer_key)
            total_raw = await self._redis.get(total_key)
        except Exception:
            return ThrottleDecision(action="allow", reason="redis_unavailable")

        answered = int(answered_raw) if answered_raw else 0
        total = int(total_raw) if total_raw else 0

        if total < 5:
            # Not enough data to make a decision
            return ThrottleDecision(action="allow", reason="insufficient_data")

        answer_rate = answered / total

        if answer_rate < 0.20:
            # Recommend adjacent hours
            recommended = []
            if hour > 0:
                recommended.append(hour - 1)
            if hour < 23:
                recommended.append(hour + 1)
            return ThrottleDecision(
                action="shift",
                delay_seconds=0,
                reason=f"answer_rate={answer_rate:.2%}_below_20%_for_hour_{hour}",
                recommended_hours=recommended,
            )

        return ThrottleDecision(action="allow", reason="answer_rate_acceptable")

    async def record_call_result(
        self, tenant_id: str, hour: int, answered: bool
    ) -> None:
        """Track call answer rates per hour bucket."""
        total_key = f"throttle:voice:total:{tenant_id}:{hour}"
        answer_key = f"throttle:voice:answered:{tenant_id}:{hour}"

        try:
            await self._redis.incr(total_key)
            await self._redis.expire(total_key, 86400)
            if answered:
                await self._redis.incr(answer_key)
                await self._redis.expire(answer_key, 86400)
        except Exception as exc:
            logger.warning("Failed to record call result: %s", exc)

    # -------------------------------------------------------------------------
    # Status
    # -------------------------------------------------------------------------

    async def get_throttle_status(self, tenant_id: str) -> dict[str, Any]:
        """Return current throttle state for all channels."""
        email = await self.check_email_throttle(tenant_id)
        linkedin = await self.check_linkedin_throttle(tenant_id)

        return {
            "email": email.model_dump(),
            "linkedin": linkedin.model_dump(),
            "tenant_id": tenant_id,
        }

    async def close(self) -> None:
        """Close the Redis connection."""
        await self._redis.close()
