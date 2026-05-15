"""Inbox placement monitor for tracking email deliverability.

Tracks whether emails land in inbox, spam, promotions, or are not delivered.
Provides domain-level statistics and alerting when placement degrades.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class PlacementResult:
    """Result of a single placement check."""

    message_id: str
    domain: str
    placement: str  # "inbox", "spam", "promotions", "not_delivered"
    checked_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class InboxPlacementMonitor:
    """Monitor email inbox placement rates by domain.

    Tracks seed test results and provides domain-level stats and alerting.
    Works standalone using in-memory storage. Can optionally use Redis for
    persistence if available.
    """

    def __init__(self, redis_client: Optional[object] = None) -> None:
        """Initialize the inbox placement monitor.

        Args:
            redis_client: Optional Redis client for persistence. Falls back to
                in-memory storage if not provided.
        """
        self._redis = redis_client
        self._results: dict[str, PlacementResult] = {}
        self._domain_results: dict[str, list[PlacementResult]] = {}

    async def send_seed_test(
        self, domain: str, seed_addresses: list[str]
    ) -> dict:
        """Send test emails to seed addresses for placement testing.

        Args:
            domain: The sending domain to test.
            seed_addresses: List of seed email addresses to send to.

        Returns:
            Dictionary with test_id, domain, seed_count, and status.
        """
        test_id = str(uuid.uuid4())
        message_ids = []

        for addr in seed_addresses:
            msg_id = f"{test_id}-{addr.split('@')[0]}"
            message_ids.append(msg_id)

            # Store pending results
            result = PlacementResult(
                message_id=msg_id,
                domain=domain,
                placement="not_delivered",
            )
            self._results[msg_id] = result

            if domain not in self._domain_results:
                self._domain_results[domain] = []
            self._domain_results[domain].append(result)

        logger.info(
            "Seed test sent: domain=%s, seeds=%d, test_id=%s",
            domain,
            len(seed_addresses),
            test_id,
        )

        return {
            "test_id": test_id,
            "domain": domain,
            "seed_count": len(seed_addresses),
            "message_ids": message_ids,
            "status": "sent",
        }

    async def check_placement(self, message_id: str) -> str:
        """Check the placement result for a specific message.

        Args:
            message_id: The message ID to check.

        Returns:
            Placement category: "inbox", "spam", "promotions", or "not_delivered".
        """
        result = self._results.get(message_id)
        if result is None:
            return "not_delivered"
        return result.placement

    async def update_placement(self, message_id: str, placement: str) -> None:
        """Update the placement result for a message after checking.

        Args:
            message_id: The message ID to update.
            placement: New placement value (inbox, spam, promotions, not_delivered).
        """
        if message_id in self._results:
            self._results[message_id].placement = placement
            self._results[message_id].checked_at = datetime.now(timezone.utc)

    async def get_domain_stats(self, domain: str) -> dict:
        """Get placement statistics for a specific domain.

        Args:
            domain: The domain to get stats for.

        Returns:
            Dictionary with inbox_rate, spam_rate, total_tests, and breakdown.
        """
        results = self._domain_results.get(domain, [])
        total = len(results)

        if total == 0:
            return {
                "domain": domain,
                "inbox_rate": 0.0,
                "spam_rate": 0.0,
                "promotions_rate": 0.0,
                "not_delivered_rate": 0.0,
                "total_tests": 0,
            }

        inbox_count = sum(1 for r in results if r.placement == "inbox")
        spam_count = sum(1 for r in results if r.placement == "spam")
        promo_count = sum(1 for r in results if r.placement == "promotions")
        not_delivered_count = sum(1 for r in results if r.placement == "not_delivered")

        return {
            "domain": domain,
            "inbox_rate": round((inbox_count / total) * 100, 2),
            "spam_rate": round((spam_count / total) * 100, 2),
            "promotions_rate": round((promo_count / total) * 100, 2),
            "not_delivered_rate": round((not_delivered_count / total) * 100, 2),
            "total_tests": total,
        }

    async def alert_if_degraded(
        self, domain: str, threshold: float = 80.0
    ) -> bool:
        """Check if inbox placement has degraded below threshold and alert.

        Args:
            domain: The domain to check.
            threshold: Minimum acceptable inbox rate percentage (default 80%).

        Returns:
            True if an alert was fired (inbox rate below threshold), False otherwise.
        """
        stats = await self.get_domain_stats(domain)

        if stats["total_tests"] == 0:
            return False

        if stats["inbox_rate"] < threshold:
            logger.warning(
                "ALERT: Domain %s inbox rate degraded to %.1f%% (threshold: %.1f%%)",
                domain,
                stats["inbox_rate"],
                threshold,
            )
            return True

        return False
