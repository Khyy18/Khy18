"""Domain Reputation Tracking - composite scoring and daily limit adjustment."""

from __future__ import annotations

import logging
from datetime import date
from typing import Any

import redis.asyncio as aioredis

logger = logging.getLogger(__name__)


class DomainReputationTracker:
    """Tracks and manages domain reputation scores for email deliverability.

    Calculates composite reputation based on bounce rate (40%), spam complaints (30%),
    and blacklist presence (30%). Stores 7-day rolling history in Redis.
    """

    def __init__(self, redis_url: str) -> None:
        self._redis = aioredis.from_url(redis_url, decode_responses=True)

    async def get_reputation_score(self, domain: str) -> int:
        """Calculate composite reputation score for a domain.

        Score ranges from 0-100. Starts at 100, with penalties applied based on:
        - Bounce rate (weight 40%): >5% bounce rate reduces score
        - Spam complaint rate (weight 30%): complaints reduce score
        - Blacklist presence (weight 30%): listed on blacklist reduces score

        Args:
            domain: The sending domain.

        Returns:
            Reputation score 0-100.
        """
        score = 100

        # Bounce rate penalty (weight 40%)
        bounce_rate = await self._get_bounce_rate(domain)
        if bounce_rate > 0:
            # Every 1% bounce rate loses 4 points (up to 40 max penalty)
            bounce_penalty = min(40, int(bounce_rate * 100 * 4))
            score -= bounce_penalty

        # Spam complaint rate penalty (weight 30%)
        complaint_rate = await self._get_complaint_rate(domain)
        if complaint_rate > 0:
            # Every 0.1% complaint rate loses 3 points (up to 30 max penalty)
            complaint_penalty = min(30, int(complaint_rate * 1000 * 3))
            score -= complaint_penalty

        # Blacklist presence penalty (weight 30%)
        is_blacklisted = await self._is_blacklisted(domain)
        if is_blacklisted:
            score -= 30

        return max(0, min(100, score))

    def categorize_domain(self, score: int) -> str:
        """Categorize a domain based on its reputation score.

        Args:
            score: Reputation score 0-100.

        Returns:
            Category string: 'healthy', 'warning', or 'critical'.
        """
        if score > 80:
            return "healthy"
        elif score >= 60:
            return "warning"
        else:
            return "critical"

    async def record_complaint(self, domain: str) -> None:
        """Record a spam complaint for a domain.

        Args:
            domain: The sending domain.
        """
        today = date.today().isoformat()
        key = f"complaints:{domain}:{today}"
        pipe = self._redis.pipeline()
        pipe.incr(key)
        pipe.expire(key, 86400 * 7)  # 7-day rolling window
        await pipe.execute()
        logger.info("Spam complaint recorded for domain %s", domain)

    async def get_adjusted_daily_limit(self, domain: str, base_limit: int) -> int:
        """Get the adjusted daily send limit based on domain reputation.

        Args:
            domain: The sending domain.
            base_limit: The base daily limit for the domain.

        Returns:
            Adjusted limit: base_limit if healthy, base_limit // 2 if warning, 0 if critical.
        """
        score = await self.get_reputation_score(domain)
        category = self.categorize_domain(score)

        if category == "critical":
            return 0
        elif category == "warning":
            return base_limit // 2
        else:
            return base_limit

    async def run_daily_check(self, domains: list[str]) -> dict[str, Any]:
        """Run daily reputation check for all configured domains.

        Calculates and stores scores in Redis with 7-day rolling history.

        Args:
            domains: List of domains to check.

        Returns:
            Dict mapping domain to score and category.
        """
        today = date.today().isoformat()
        results: dict[str, Any] = {}

        for domain in domains:
            score = await self.get_reputation_score(domain)
            category = self.categorize_domain(score)

            # Store in Redis with 7-day TTL
            key = f"reputation:{domain}:{today}"
            await self._redis.set(key, str(score))
            await self._redis.expire(key, 86400 * 7)

            results[domain] = {"score": score, "category": category}

            if category == "critical":
                logger.warning(
                    "Domain %s has critical reputation score: %d", domain, score
                )
            elif category == "warning":
                logger.warning(
                    "Domain %s has warning reputation score: %d", domain, score
                )

        return results

    async def _get_bounce_rate(self, domain: str) -> float:
        """Get bounce rate for a domain from Redis.

        Returns:
            Bounce rate as float (0.0-1.0).
        """
        today = date.today().isoformat()
        bounce_key = f"bounces:{domain}:{today}"
        send_key = f"sends:{domain}:{today}"

        bounces = await self._redis.get(bounce_key)
        sends = await self._redis.get(send_key)

        bounce_count = int(bounces) if bounces else 0
        send_count = int(sends) if sends else 0

        if send_count == 0:
            return 0.0

        return bounce_count / send_count

    async def _get_complaint_rate(self, domain: str) -> float:
        """Get spam complaint rate for a domain.

        Returns:
            Complaint rate as float (0.0-1.0).
        """
        today = date.today().isoformat()
        complaint_key = f"complaints:{domain}:{today}"
        send_key = f"sends:{domain}:{today}"

        complaints = await self._redis.get(complaint_key)
        sends = await self._redis.get(send_key)

        complaint_count = int(complaints) if complaints else 0
        send_count = int(sends) if sends else 0

        if send_count == 0:
            return 0.0

        return complaint_count / send_count

    async def _is_blacklisted(self, domain: str) -> bool:
        """Check if domain is flagged as blacklisted in Redis.

        Returns:
            True if domain is blacklisted.
        """
        key = f"blacklisted:{domain}"
        result = await self._redis.get(key)
        return result == "1"

    async def close(self) -> None:
        """Close the Redis connection."""
        await self._redis.close()
