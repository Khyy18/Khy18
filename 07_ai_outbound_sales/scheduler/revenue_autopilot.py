"""Revenue Autopilot - automated business logic for growth and retention."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from core.config import Settings
from core.models import (
    Campaign,
    CampaignStatus,
    Lead,
    Message,
    MessageStatus,
    Plan,
    Subscription,
    SubscriptionStatus,
    Tenant,
)

logger = logging.getLogger(__name__)


class RevenueAutopilot:
    """Automated business logic for revenue growth and client retention.

    Runs periodic checks on campaigns, tenants, and subscriptions to
    surface actionable insights and prevent churn.
    """

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        settings: Settings,
    ) -> None:
        self._session_factory = session_factory
        self._settings = settings

    async def run_autopilot_tick(self) -> None:
        """Run all autopilot checks in one tick."""
        async with self._session_factory() as session:
            await self.check_lead_pool_depletion(session)
            await self.check_inactive_clients(session)
            await self.check_subscription_expiry(session)
            await self.check_performance_drop(session)

    async def check_lead_pool_depletion(self, session: AsyncSession) -> None:
        """Check active campaigns for low lead counts.

        If a campaign has fewer than 10 remaining new leads,
        log a suggestion to broaden the ICP.
        """
        result = await session.execute(
            select(Campaign).where(Campaign.status == CampaignStatus.active)
        )
        campaigns = result.scalars().all()

        for campaign in campaigns:
            lead_count_result = await session.execute(
                select(func.count(Lead.id)).where(
                    Lead.tenant_id == campaign.tenant_id,
                    Lead.status == "new",
                )
            )
            lead_count = lead_count_result.scalar() or 0

            if lead_count < 10:
                logger.warning(
                    "Campaign '%s' (id=%s) has only %d new leads remaining. "
                    "Consider broadening ICP filters.",
                    campaign.name,
                    campaign.id,
                    lead_count,
                )

    async def check_inactive_clients(self, session: AsyncSession) -> None:
        """Find tenants with no messages sent in the last 7 days.

        These tenants may need engagement or re-activation outreach.
        """
        seven_days_ago = datetime.now(timezone.utc) - timedelta(days=7)

        result = await session.execute(select(Tenant))
        tenants = result.scalars().all()

        for tenant in tenants:
            msg_result = await session.execute(
                select(func.count(Message.id)).where(
                    Message.campaign_id.in_(
                        select(Campaign.id).where(Campaign.tenant_id == tenant.id)
                    ),
                    Message.sent_at >= seven_days_ago,
                    Message.status != MessageStatus.draft,
                )
            )
            msg_count = msg_result.scalar() or 0

            if msg_count == 0:
                logger.warning(
                    "Tenant '%s' (id=%s) has sent no messages in the last 7 days. "
                    "Engagement action needed.",
                    tenant.name,
                    tenant.id,
                )

    async def check_subscription_expiry(self, session: AsyncSession) -> None:
        """Find subscriptions expiring within the next 7 days.

        Log renewal reminders for subscriptions nearing their period end.
        """
        now = datetime.now(timezone.utc)
        seven_days_from_now = now + timedelta(days=7)

        result = await session.execute(
            select(Subscription).where(
                Subscription.status == SubscriptionStatus.active,
                Subscription.current_period_end != None,  # noqa: E711
                Subscription.current_period_end <= seven_days_from_now,
                Subscription.current_period_end >= now,
            )
        )
        expiring = result.scalars().all()

        for sub in expiring:
            logger.warning(
                "Subscription %s (tenant_id=%s) expires on %s. "
                "Renewal reminder needed.",
                sub.id,
                sub.tenant_id,
                sub.current_period_end,
            )

    async def check_performance_drop(self, session: AsyncSession) -> None:
        """Compare this week vs last week message counts per campaign.

        If a campaign shows a 50%+ drop, log an adjustment needed warning.
        """
        now = datetime.now(timezone.utc)
        one_week_ago = now - timedelta(days=7)
        two_weeks_ago = now - timedelta(days=14)

        result = await session.execute(
            select(Campaign).where(Campaign.status == CampaignStatus.active)
        )
        campaigns = result.scalars().all()

        for campaign in campaigns:
            # This week's message count
            this_week_result = await session.execute(
                select(func.count(Message.id)).where(
                    Message.campaign_id == campaign.id,
                    Message.sent_at >= one_week_ago,
                    Message.status != MessageStatus.draft,
                )
            )
            this_week = this_week_result.scalar() or 0

            # Last week's message count
            last_week_result = await session.execute(
                select(func.count(Message.id)).where(
                    Message.campaign_id == campaign.id,
                    Message.sent_at >= two_weeks_ago,
                    Message.sent_at < one_week_ago,
                    Message.status != MessageStatus.draft,
                )
            )
            last_week = last_week_result.scalar() or 0

            if last_week > 0 and this_week < last_week * 0.5:
                logger.warning(
                    "Campaign '%s' (id=%s) performance dropped: "
                    "%d messages this week vs %d last week (>50%% drop). "
                    "Adjustment needed.",
                    campaign.name,
                    campaign.id,
                    this_week,
                    last_week,
                )

    async def track_mrr(self, session: AsyncSession) -> dict:
        """Query active subscriptions and calculate MRR.

        Returns dict with mrr_cents and active_subscriptions count.
        """
        result = await session.execute(
            select(
                func.sum(Plan.price_cents),
                func.count(Subscription.id),
            )
            .join(Plan, Subscription.plan_id == Plan.id)
            .where(Subscription.status == SubscriptionStatus.active)
        )
        row = result.one()
        total_mrr = row[0] or 0
        active_count = row[1] or 0

        return {
            "mrr_cents": total_mrr,
            "active_subscriptions": active_count,
        }
