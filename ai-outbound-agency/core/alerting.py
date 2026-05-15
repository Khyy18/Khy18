"""Alerting Engine - monitors system health and dispatches notifications.

Provides 8 alert conditions with configurable thresholds, multi-channel
dispatch (Telegram, Slack, email), and Redis-backed cooldown to prevent
duplicate notifications within a configurable window.
"""

from __future__ import annotations

import logging
import shutil
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Awaitable

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

logger = logging.getLogger(__name__)

# Type alias for check functions
CheckResult = tuple[bool, float, str]


@dataclass
class AlertCondition:
    """Definition of a single alert condition."""

    name: str
    threshold: float
    channels: list[str] = field(default_factory=lambda: ["telegram", "slack"])
    cooldown_seconds: int = 3600
    description: str = ""


class AlertingEngine:
    """Engine that evaluates alert conditions and dispatches notifications.

    Supports 8 built-in conditions covering email delivery, LLM errors,
    infrastructure health, revenue metrics, and service connectivity.
    Uses Redis for cooldown tracking to prevent alert fatigue.
    """

    # Default alert conditions configuration
    DEFAULT_CONDITIONS: list[dict[str, Any]] = [
        {
            "name": "bounce_rate_high",
            "threshold": 5.0,
            "channels": ["telegram", "slack"],
            "cooldown_seconds": 3600,
            "description": "Email bounce rate exceeds 5% in the last hour",
        },
        {
            "name": "llm_error_rate_high",
            "threshold": 20.0,
            "channels": ["telegram", "slack"],
            "cooldown_seconds": 3600,
            "description": "LLM API error rate exceeds 20% of requests in the last hour",
        },
        {
            "name": "no_sends_business_hours",
            "threshold": 0,
            "channels": ["telegram", "slack", "email"],
            "cooldown_seconds": 3600,
            "description": "Zero emails sent during business hours (9am-6pm) in the last 6 hours",
        },
        {
            "name": "disk_usage_high",
            "threshold": 80.0,
            "channels": ["telegram"],
            "cooldown_seconds": 3600,
            "description": "Disk usage exceeds 80%",
        },
        {
            "name": "memory_usage_high",
            "threshold": 90.0,
            "channels": ["telegram"],
            "cooldown_seconds": 3600,
            "description": "Memory usage exceeds 90%",
        },
        {
            "name": "linkedin_session_failures",
            "threshold": 0,
            "channels": ["telegram", "slack"],
            "cooldown_seconds": 3600,
            "description": "All LinkedIn sessions restricted in the last hour",
        },
        {
            "name": "mrr_drop",
            "threshold": 20.0,
            "channels": ["telegram", "slack", "email"],
            "cooldown_seconds": 3600,
            "description": "MRR dropped more than 20% day-over-day",
        },
        {
            "name": "db_pool_exhaustion",
            "threshold": 80.0,
            "channels": ["telegram"],
            "cooldown_seconds": 3600,
            "description": "Database connection pool usage exceeds 80%",
        },
    ]

    def __init__(
        self,
        settings: Any,
        session_factory: async_sessionmaker[AsyncSession],
        redis: Any,
    ) -> None:
        """Initialize the AlertingEngine.

        Args:
            settings: Application settings with notification config.
            session_factory: SQLAlchemy async session factory.
            redis: Async Redis client instance.
        """
        self._settings = settings
        self._session_factory = session_factory
        self._redis = redis
        self._conditions: list[AlertCondition] = [
            AlertCondition(**cond) for cond in self.DEFAULT_CONDITIONS
        ]

    @property
    def conditions(self) -> list[AlertCondition]:
        """Return the list of configured alert conditions."""
        return self._conditions

    async def check_all_conditions(self) -> list[dict[str, Any]]:
        """Check all alert conditions and return triggered alerts.

        Returns:
            List of dicts with keys: name, value, message, channels.
        """
        triggered: list[dict[str, Any]] = []

        check_methods: dict[str, Callable[..., Awaitable[CheckResult]]] = {
            "bounce_rate_high": self._check_bounce_rate,
            "llm_error_rate_high": self._check_llm_error_rate,
            "no_sends_business_hours": self._check_no_sends_business_hours,
            "disk_usage_high": self._check_disk_usage,
            "memory_usage_high": self._check_memory_usage,
            "linkedin_session_failures": self._check_linkedin_failures,
            "mrr_drop": self._check_mrr_drop,
            "db_pool_exhaustion": self._check_db_pool_exhaustion,
        }

        for condition in self._conditions:
            check_fn = check_methods.get(condition.name)
            if check_fn is None:
                continue

            try:
                is_triggered, current_value, message = await check_fn(condition.threshold)
            except Exception as exc:
                logger.error("Error checking condition %s: %s", condition.name, exc)
                continue

            if is_triggered:
                in_cooldown = await self.is_in_cooldown(condition.name)
                if not in_cooldown:
                    triggered.append({
                        "name": condition.name,
                        "value": current_value,
                        "message": message,
                        "channels": condition.channels,
                    })
                    # Send alerts to all configured channels
                    for channel in condition.channels:
                        await self.send_alert(condition.name, channel, message)
                    # Set cooldown after sending
                    await self.set_cooldown(condition.name)

        return triggered

    async def send_alert(self, condition_name: str, channel: str, message: str) -> bool:
        """Send alert to specified channel.

        Args:
            condition_name: Name of the alert condition.
            channel: Target channel - 'telegram', 'slack', or 'email'.
            message: Alert message text.

        Returns:
            True if alert was sent successfully, False otherwise.
        """
        from integrations.notifications import (
            send_telegram_notification,
            send_slack_notification,
            send_email_digest,
        )

        alert_text = f"[ALERT] {condition_name}: {message}"

        try:
            if channel == "telegram":
                bot_token = getattr(self._settings, "telegram_bot_token", "")
                chat_id = getattr(self._settings, "telegram_chat_id", "")
                return await send_telegram_notification(bot_token, chat_id, alert_text)
            elif channel == "slack":
                webhook_url = getattr(self._settings, "slack_webhook_url", "")
                blocks = [
                    {
                        "type": "section",
                        "text": {"type": "mrkdwn", "text": alert_text},
                    }
                ]
                return await send_slack_notification(webhook_url, blocks)
            elif channel == "email":
                # Send to a configured alert email address
                alert_email = getattr(self._settings, "alert_email", "")
                if alert_email:
                    return await send_email_digest(
                        to_email=alert_email,
                        subject=f"Alert: {condition_name}",
                        html_body=f"<p>{alert_text}</p>",
                    )
                return False
            else:
                logger.warning("Unknown alert channel: %s", channel)
                return False
        except Exception as exc:
            logger.error("Failed to send alert via %s: %s", channel, exc)
            return False

    async def is_in_cooldown(self, condition_name: str) -> bool:
        """Check if the condition is currently in cooldown.

        Args:
            condition_name: Name of the alert condition.

        Returns:
            True if cooldown is active (alert should be suppressed).
        """
        key = f"alert_cooldown:{condition_name}"
        value = await self._redis.get(key)
        return value is not None

    async def set_cooldown(self, condition_name: str) -> None:
        """Set cooldown for a condition using Redis SET with EX.

        Args:
            condition_name: Name of the alert condition.
        """
        key = f"alert_cooldown:{condition_name}"
        # Find cooldown duration for this condition
        cooldown_seconds = 3600  # default
        for cond in self._conditions:
            if cond.name == condition_name:
                cooldown_seconds = cond.cooldown_seconds
                break
        await self._redis.set(key, "1", ex=cooldown_seconds)

    # ---------- Check Methods ----------

    async def _check_bounce_rate(self, threshold: float) -> CheckResult:
        """Check if email bounce rate exceeds threshold in the last hour.

        Args:
            threshold: Maximum acceptable bounce rate percentage.

        Returns:
            Tuple of (is_triggered, current_value, message).
        """
        from datetime import timedelta
        from core.models import Event, EventType, Message, MessageStatus

        one_hour_ago = datetime.now(timezone.utc) - timedelta(hours=1)

        async with self._session_factory() as session:
            # Total messages sent in last hour
            sent_result = await session.execute(
                select(func.count(Message.id)).where(
                    Message.sent_at >= one_hour_ago,
                    Message.status != MessageStatus.draft,
                )
            )
            total_sent = sent_result.scalar() or 0

            if total_sent == 0:
                return False, 0.0, "No messages sent in last hour"

            # Bounces in last hour
            bounce_result = await session.execute(
                select(func.count(Event.id)).where(
                    Event.event_type == EventType.bounce,
                    Event.occurred_at >= one_hour_ago,
                )
            )
            bounces = bounce_result.scalar() or 0

            bounce_rate = (bounces / total_sent) * 100
            is_triggered = bounce_rate > threshold
            message = f"Bounce rate: {bounce_rate:.1f}% ({bounces}/{total_sent} messages)"
            return is_triggered, bounce_rate, message

    async def _check_llm_error_rate(self, threshold: float) -> CheckResult:
        """Check if LLM error rate exceeds threshold.

        Uses Redis counters for LLM requests and errors.

        Args:
            threshold: Maximum acceptable error rate percentage.

        Returns:
            Tuple of (is_triggered, current_value, message).
        """
        total_str = await self._redis.get("llm_requests_total")
        errors_str = await self._redis.get("llm_errors_total")

        total = int(total_str) if total_str else 0
        errors = int(errors_str) if errors_str else 0

        if total == 0:
            return False, 0.0, "No LLM requests recorded"

        error_rate = (errors / total) * 100
        is_triggered = error_rate > threshold
        message = f"LLM error rate: {error_rate:.1f}% ({errors}/{total} requests)"
        return is_triggered, error_rate, message

    async def _check_no_sends_business_hours(self, threshold: float) -> CheckResult:
        """Check if zero emails sent during business hours (9am-6pm) in last 6 hours.

        Args:
            threshold: Not used (always checks for zero sends).

        Returns:
            Tuple of (is_triggered, current_value, message).
        """
        from datetime import timedelta
        from core.models import Message, MessageStatus

        now = datetime.now(timezone.utc)
        current_hour = now.hour

        # Only check during business hours (9am - 6pm UTC)
        if current_hour < 9 or current_hour >= 18:
            return False, 0.0, "Outside business hours"

        six_hours_ago = now - timedelta(hours=6)

        async with self._session_factory() as session:
            sent_result = await session.execute(
                select(func.count(Message.id)).where(
                    Message.sent_at >= six_hours_ago,
                    Message.status == MessageStatus.sent,
                )
            )
            sent_count = sent_result.scalar() or 0

        is_triggered = sent_count == 0
        message = f"Emails sent in last 6 hours during business hours: {sent_count}"
        return is_triggered, float(sent_count), message

    async def _check_disk_usage(self, threshold: float) -> CheckResult:
        """Check if disk usage exceeds threshold.

        Args:
            threshold: Maximum acceptable disk usage percentage.

        Returns:
            Tuple of (is_triggered, current_value, message).
        """
        usage = shutil.disk_usage("/")
        percent_used = (usage.used / usage.total) * 100
        is_triggered = percent_used > threshold
        message = f"Disk usage: {percent_used:.1f}% ({usage.used // (1024**3)}GB / {usage.total // (1024**3)}GB)"
        return is_triggered, percent_used, message

    async def _check_memory_usage(self, threshold: float) -> CheckResult:
        """Check if memory usage exceeds threshold.

        Uses psutil if available, otherwise returns not triggered.

        Args:
            threshold: Maximum acceptable memory usage percentage.

        Returns:
            Tuple of (is_triggered, current_value, message).
        """
        try:
            import psutil
            mem = psutil.virtual_memory()
            percent_used = mem.percent
            is_triggered = percent_used > threshold
            message = f"Memory usage: {percent_used:.1f}%"
            return is_triggered, percent_used, message
        except ImportError:
            return False, 0.0, "psutil not available, skipping memory check"

    async def _check_linkedin_failures(self, threshold: float) -> CheckResult:
        """Check if all LinkedIn sessions are restricted.

        Uses Redis counters for LinkedIn total sessions and failures.
        When total sessions data is unavailable, falls back to checking
        if failures exceed a minimum threshold of 1.

        Args:
            threshold: Not used (triggers when all sessions have failed).

        Returns:
            Tuple of (is_triggered, current_value, message).
        """
        failures_str = await self._redis.get("linkedin_failures_1h")
        total_str = await self._redis.get("linkedin_sessions_total")
        failures = int(failures_str) if failures_str else 0
        total_sessions = int(total_str) if total_str else 0

        if total_sessions == 0:
            # Fallback: if total sessions key is not set, use simple threshold logic.
            # Alert fires if there are any failures recorded (failures > 0).
            if failures > 0:
                is_triggered = True
                message = f"LinkedIn failures detected: {failures} (total sessions unknown)"
                return is_triggered, float(failures), message
            return False, 0.0, "No LinkedIn sessions configured"

        is_triggered = failures >= total_sessions
        message = f"LinkedIn sessions restricted: {failures}/{total_sessions}"
        return is_triggered, float(failures), message

    async def _check_mrr_drop(self, threshold: float) -> CheckResult:
        """Check if MRR dropped more than threshold% day-over-day.

        Compares today's MRR (active subscriptions) to yesterday's stored value.

        Args:
            threshold: Maximum acceptable MRR drop percentage.

        Returns:
            Tuple of (is_triggered, current_value, message).
        """
        from core.models import Subscription, SubscriptionStatus, Plan

        async with self._session_factory() as session:
            # Current MRR: sum of price_cents for all active subscriptions
            result = await session.execute(
                select(func.sum(Plan.price_cents)).join(
                    Subscription, Subscription.plan_id == Plan.id
                ).where(Subscription.status == SubscriptionStatus.active)
            )
            current_mrr = result.scalar() or 0

        # Get yesterday's MRR from Redis
        yesterday_mrr_str = await self._redis.get("mrr_yesterday")
        yesterday_mrr = int(yesterday_mrr_str) if yesterday_mrr_str else 0

        if yesterday_mrr == 0:
            # Store current MRR for tomorrow's comparison
            await self._redis.set("mrr_yesterday", str(current_mrr))
            return False, 0.0, "No previous MRR data for comparison"

        drop_percent = ((yesterday_mrr - current_mrr) / yesterday_mrr) * 100
        is_triggered = drop_percent > threshold
        message = f"MRR change: {drop_percent:.1f}% drop (yesterday: {yesterday_mrr}, today: {current_mrr})"
        return is_triggered, drop_percent, message

    async def _check_db_pool_exhaustion(self, threshold: float) -> CheckResult:
        """Check if database connection pool is over threshold.

        Uses engine pool status if available.

        Args:
            threshold: Maximum acceptable pool usage percentage.

        Returns:
            Tuple of (is_triggered, current_value, message).
        """
        try:
            from core.db import engine as db_engine

            pool = db_engine.pool
            pool_size = pool.size()
            checked_out = pool.checkedout()

            if pool_size == 0:
                return False, 0.0, "Pool size is 0"

            usage_percent = (checked_out / pool_size) * 100
            is_triggered = usage_percent > threshold
            message = f"DB pool usage: {usage_percent:.1f}% ({checked_out}/{pool_size} connections)"
            return is_triggered, usage_percent, message
        except Exception as exc:
            logger.debug("Cannot check DB pool: %s", exc)
            return False, 0.0, f"Cannot check DB pool: {exc}"
