"""Email deliverability testing infrastructure.

Tests email deliverability by sending to seed addresses and tracking placement.
Provides domain-level statistics, placement history, and alerting when inbox
placement degrades below configurable thresholds.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)


class DeliverabilityTester:
    """Tests email deliverability by sending to seed addresses and tracking placement."""

    def __init__(
        self,
        email_sender: Optional[Any] = None,
        redis_url: str = "",
    ) -> None:
        """Initialize the deliverability tester.

        Args:
            email_sender: Optional email sender instance for sending test emails.
            redis_url: Redis connection URL for persistence (unused in basic mode).
        """
        self._sender = email_sender
        self._redis_url = redis_url
        self._results: dict[str, list[dict]] = {}  # domain -> list of test results
        self._messages: dict[str, dict] = {}  # message_id -> result record

    async def send_test_email(self, domain: str, test_address: str) -> dict:
        """Send a test email and return message_id for tracking.

        Args:
            domain: The sending domain to test.
            test_address: The seed address to send to.

        Returns:
            Dictionary with message_id, domain, sent_at, and success status.
        """
        message_id = str(uuid.uuid4())
        sent_at = datetime.now(timezone.utc)

        result: dict[str, Any] = {
            "message_id": message_id,
            "domain": domain,
            "test_address": test_address,
            "sent_at": sent_at.isoformat(),
            "placement": "pending",
        }

        # Send via email sender if available
        if self._sender is not None:
            send_result = await self._sender.send_email(
                to=test_address,
                subject=f"Deliverability Test - {message_id[:8]}",
                html_body="<p>This is a deliverability test email.</p>",
                message_id=message_id,
            )
            result["send_success"] = send_result.get("success", False)
        else:
            result["send_success"] = True  # Assume success when no sender

        # Store result
        self._messages[message_id] = result
        if domain not in self._results:
            self._results[domain] = []
        self._results[domain].append(result)

        logger.info(
            "Deliverability test sent: domain=%s, address=%s, message_id=%s",
            domain,
            test_address,
            message_id,
        )

        return {
            "message_id": message_id,
            "domain": domain,
            "sent_at": sent_at.isoformat(),
        }

    async def check_placement(self, message_id: str) -> str:
        """Check placement of a test email.

        In production this would check via IMAP or a seed mailbox API.
        For now returns the stored result or 'pending'.

        Args:
            message_id: The message ID to check placement for.

        Returns:
            Placement status: inbox, spam, promotions, not_delivered, or pending.
        """
        record = self._messages.get(message_id)
        if record is None:
            return "pending"
        return record.get("placement", "pending")

    async def record_placement(self, message_id: str, placement: str) -> None:
        """Record actual placement result for a test email.

        Args:
            message_id: The message ID to update.
            placement: The placement result (inbox, spam, promotions, not_delivered).
        """
        if message_id in self._messages:
            self._messages[message_id]["placement"] = placement
            self._messages[message_id]["checked_at"] = datetime.now(
                timezone.utc
            ).isoformat()

            # Also update in the domain results list
            domain = self._messages[message_id]["domain"]
            if domain in self._results:
                for record in self._results[domain]:
                    if record["message_id"] == message_id:
                        record["placement"] = placement
                        record["checked_at"] = datetime.now(
                            timezone.utc
                        ).isoformat()
                        break

    async def get_placement_history(self, domain: str) -> list[dict]:
        """Return placement test history for a domain.

        Args:
            domain: The domain to get history for.

        Returns:
            List of placement test result dictionaries.
        """
        return self._results.get(domain, [])

    async def get_inbox_rate(self, domain: str) -> float:
        """Calculate inbox placement rate for a domain (percentage).

        Args:
            domain: The domain to calculate rate for.

        Returns:
            Inbox placement rate as a percentage (0.0 - 100.0).
            Returns 0.0 if no results exist.
        """
        results = self._results.get(domain, [])
        if not results:
            return 0.0

        # Only count results that have been checked (not pending)
        checked = [r for r in results if r.get("placement") != "pending"]
        if not checked:
            return 0.0

        inbox_count = sum(1 for r in checked if r.get("placement") == "inbox")
        return round((inbox_count / len(checked)) * 100, 2)

    async def alert_if_degraded(
        self, domain: str, threshold: float = 80.0
    ) -> bool:
        """Check if inbox rate is below threshold, return True if alert needed.

        Args:
            domain: The domain to check.
            threshold: Minimum acceptable inbox rate percentage (default 80.0).

        Returns:
            True if inbox rate is below threshold (alert needed), False otherwise.
        """
        inbox_rate = await self.get_inbox_rate(domain)

        # No data means no alert
        results = self._results.get(domain, [])
        checked = [r for r in results if r.get("placement") != "pending"]
        if not checked:
            return False

        if inbox_rate < threshold:
            logger.warning(
                "DELIVERABILITY ALERT: Domain %s inbox rate %.1f%% below threshold %.1f%%",
                domain,
                inbox_rate,
                threshold,
            )
            return True

        return False
