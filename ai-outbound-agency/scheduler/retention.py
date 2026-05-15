"""Retention Engine - milestone celebrations, engagement monitoring, and upsell triggers."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from core.config import Settings
from core.models import (
    Campaign,
    Lead,
    LeadStatus,
    Message,
    MessageStatus,
    Plan,
    Subscription,
    SubscriptionStatus,
    UsageRecord,
)
from integrations.notifications import _get_tenant_notification_config, _send_to_channels

logger = logging.getLogger(__name__)

# Milestone thresholds for celebration notifications
_MILESTONES = [1, 10, 25, 50, 100]


class RetentionEngine:
    """Automated retention checks: milestones, engagement, churn prevention, upsell.

    Follows the same pattern as RevenueAutopilot (session_factory, settings).
    """

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        settings: Settings,
    ) -> None:
        self._session_factory = session_factory
        self._settings = settings

    async def check_milestones(
        self, tenant_id: UUID, session: AsyncSession
    ) -> int | None:
        """Check if tenant hit a booking milestone.

        Queries count of leads with status=booked for the tenant.
        Returns the milestone number if hit, None otherwise.
        """
        result = await session.execute(
            select(func.count(Lead.id)).where(
                Lead.tenant_id == tenant_id,
                Lead.status == LeadStatus.booked,
            )
        )
        booked_count = result.scalar() or 0

        milestone_hit: int | None = None
        for milestone in _MILESTONES:
            if booked_count >= milestone:
                milestone_hit = milestone
            else:
                break

        if milestone_hit is not None:
            # Send celebration notification
            channels, _ = await _get_tenant_notification_config(tenant_id, session)
            if channels:
                message_text = (
                    f"Milestone reached! You have booked {milestone_hit} "
                    f"meeting{'s' if milestone_hit > 1 else ''}. Keep it up!"
                )
                await _send_to_channels(channels, message_text)
            logger.info(
                "Tenant %s hit milestone: %d booked meetings", tenant_id, milestone_hit
            )

        return milestone_hit

    async def check_engagement(
        self, tenant_id: UUID, session: AsyncSession
    ) -> dict[str, Any]:
        """Check tenant engagement based on recent message activity.

        If no messages sent in the last 7 days, returns inactive status
        with a suggestion to send a weekly summary.
        """
        seven_days_ago = datetime.now(timezone.utc) - timedelta(days=7)

        result = await session.execute(
            select(func.count(Message.id)).where(
                Message.campaign_id.in_(
                    select(Campaign.id).where(Campaign.tenant_id == tenant_id)
                ),
                Message.sent_at >= seven_days_ago,
                Message.status != MessageStatus.draft,
            )
        )
        msg_count = result.scalar() or 0

        if msg_count == 0:
            return {
                "status": "inactive",
                "suggestion": "Send weekly summary to re-engage tenant",
                "days_inactive": 7,
            }

        return {"status": "active", "messages_sent_7d": msg_count}

    async def check_performance_drop(
        self, tenant_id: UUID, session: AsyncSession
    ) -> dict[str, Any] | None:
        """Compare this week vs last week message counts for tenant.

        If there is a >50% drop, returns alert data.
        """
        now = datetime.now(timezone.utc)
        one_week_ago = now - timedelta(days=7)
        two_weeks_ago = now - timedelta(days=14)

        # This week message count
        this_week_result = await session.execute(
            select(func.count(Message.id)).where(
                Message.campaign_id.in_(
                    select(Campaign.id).where(Campaign.tenant_id == tenant_id)
                ),
                Message.sent_at >= one_week_ago,
                Message.status != MessageStatus.draft,
            )
        )
        this_week = this_week_result.scalar() or 0

        # Last week message count
        last_week_result = await session.execute(
            select(func.count(Message.id)).where(
                Message.campaign_id.in_(
                    select(Campaign.id).where(Campaign.tenant_id == tenant_id)
                ),
                Message.sent_at >= two_weeks_ago,
                Message.sent_at < one_week_ago,
                Message.status != MessageStatus.draft,
            )
        )
        last_week = last_week_result.scalar() or 0

        if last_week > 0 and this_week < last_week * 0.5:
            return {
                "alert": "performance_drop",
                "this_week": this_week,
                "last_week": last_week,
                "drop_percent": round((1 - this_week / last_week) * 100, 1),
            }

        return None

    async def check_lead_pool(
        self, tenant_id: UUID, session: AsyncSession
    ) -> dict[str, Any] | None:
        """Count new leads for tenant. If < 10, return depletion warning."""
        result = await session.execute(
            select(func.count(Lead.id)).where(
                Lead.tenant_id == tenant_id,
                Lead.status == LeadStatus.new,
            )
        )
        new_lead_count = result.scalar() or 0

        if new_lead_count < 10:
            return {
                "warning": "lead_pool_depleting",
                "new_leads_remaining": new_lead_count,
                "suggestion": "Broaden ICP filters or import new leads",
            }

        return None

    async def check_upsell_triggers(
        self, tenant_id: UUID, session: AsyncSession
    ) -> dict[str, Any] | None:
        """Check usage vs plan limits. If any metric at 80%+, return upsell recommendation."""
        # Get active subscription and plan
        sub_result = await session.execute(
            select(Subscription)
            .where(
                Subscription.tenant_id == tenant_id,
                Subscription.status == SubscriptionStatus.active,
            )
            .limit(1)
        )
        subscription = sub_result.scalar_one_or_none()
        if subscription is None:
            return None

        plan_result = await session.execute(
            select(Plan).where(Plan.id == subscription.plan_id)
        )
        plan = plan_result.scalar_one_or_none()
        if plan is None:
            return None

        # Get latest usage record
        usage_result = await session.execute(
            select(UsageRecord)
            .where(UsageRecord.tenant_id == tenant_id)
            .order_by(UsageRecord.period_start.desc())
            .limit(1)
        )
        usage = usage_result.scalar_one_or_none()
        if usage is None:
            return None

        # Check each metric against 80% threshold
        triggers: list[dict[str, Any]] = []

        if plan.leads_limit > 0:
            leads_pct = usage.leads_used / plan.leads_limit
            if leads_pct >= 0.8:
                triggers.append({
                    "metric": "leads",
                    "used": usage.leads_used,
                    "limit": plan.leads_limit,
                    "percent": round(leads_pct * 100, 1),
                })

        if plan.emails_limit > 0:
            emails_pct = usage.emails_used / plan.emails_limit
            if emails_pct >= 0.8:
                triggers.append({
                    "metric": "emails",
                    "used": usage.emails_used,
                    "limit": plan.emails_limit,
                    "percent": round(emails_pct * 100, 1),
                })

        if plan.linkedin_limit > 0:
            linkedin_pct = usage.linkedin_used / plan.linkedin_limit
            if linkedin_pct >= 0.8:
                triggers.append({
                    "metric": "linkedin",
                    "used": usage.linkedin_used,
                    "limit": plan.linkedin_limit,
                    "percent": round(linkedin_pct * 100, 1),
                })

        if triggers:
            return {
                "recommendation": "upsell",
                "current_plan": plan.name.value if hasattr(plan.name, "value") else str(plan.name),
                "triggers": triggers,
            }

        return None

    async def run_retention_check(self, tenant_id: UUID) -> dict[str, Any]:
        """Orchestrate all retention checks for one tenant.

        Returns a dict with results from each check.
        """
        async with self._session_factory() as session:
            milestone = await self.check_milestones(tenant_id, session)
            engagement = await self.check_engagement(tenant_id, session)
            performance_drop = await self.check_performance_drop(tenant_id, session)
            lead_pool = await self.check_lead_pool(tenant_id, session)
            upsell = await self.check_upsell_triggers(tenant_id, session)

        return {
            "tenant_id": str(tenant_id),
            "milestone": milestone,
            "engagement": engagement,
            "performance_drop": performance_drop,
            "lead_pool": lead_pool,
            "upsell": upsell,
        }
