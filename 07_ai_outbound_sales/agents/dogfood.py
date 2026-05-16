"""Dogfooding System - the system sells itself using its own capabilities."""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from core.config import Settings
from core.models import Campaign, CampaignStatus, Sequence, Tenant

logger = logging.getLogger(__name__)


class DogfoodAgent:
    """Meta-agent that uses the platform to sell itself.

    Configures a dedicated tenant and campaign that targets B2B SaaS
    companies who are hiring SDRs - using the platform's own outreach
    capabilities to generate new customers.
    """

    DOGFOOD_ICP: dict[str, Any] = {
        "industry": "B2B SaaS",
        "company_size": "10-100",
        "titles": ["CEO", "CTO", "VP Sales", "Head of Growth"],
        "signals": ["hiring SDRs", "sales development in job postings"],
    }

    DOGFOOD_VALUE_PROP: str = (
        "Replace your SDR team with an AI agent. "
        "$2K/mo, unlimited leads, meetings in your calendar."
    )

    DOGFOOD_SEQUENCE: list[dict[str, str]] = [
        {
            "step_type": "initial",
            "delay_days": "0",
            "subject": "Quick question about your SDR hiring",
            "body": (
                "Hi {{first_name}},\n\n"
                "Noticed {{company}} is hiring SDRs. What if you could get "
                "the same pipeline output without the headcount?\n\n"
                "Our AI agent handles prospecting, personalized outreach, and "
                "meeting booking - fully autonomous.\n\n"
                "Would you be open to a 15-min demo?\n\nBest"
            ),
        },
        {
            "step_type": "follow_up_1",
            "delay_days": "3",
            "subject": "Re: Quick question about your SDR hiring",
            "body": (
                "Hi {{first_name}},\n\n"
                "Just following up on my previous note. Companies like yours "
                "typically see 2-3x more meetings at a fraction of the cost "
                "of a human SDR team.\n\n"
                "Happy to share specifics. Worth a quick chat?\n\nBest"
            ),
        },
        {
            "step_type": "follow_up_2",
            "delay_days": "5",
            "subject": "Last note - AI outbound for {{company}}",
            "body": (
                "Hi {{first_name}},\n\n"
                "Last reach-out from me. If timing is not right, no worries at all.\n\n"
                "In case it helps: we offer a 14-day free trial, no credit card "
                "required. You can see real results before committing.\n\n"
                "Let me know if you would like to explore this.\n\nBest"
            ),
        },
    ]

    def __init__(
        self,
        settings: Settings,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        self._settings = settings
        self._session_factory = session_factory

    async def initialize_dogfood_campaign(self) -> dict[str, Any]:
        """Create the dogfood tenant, sequence, and campaign if they do not exist.

        Returns a dict with tenant_id, campaign_id, and status.
        """
        sending_domain = (
            self._settings.dogfood_sending_domain or "dogfood.ai-outbound.com"
        )

        async with self._session_factory() as session:
            # Check if dogfood tenant already exists
            result = await session.execute(
                select(Tenant).where(Tenant.name == "AI Outbound Agency - Dogfood")
            )
            tenant = result.scalar_one_or_none()

            if tenant is None:
                tenant = Tenant(
                    name="AI Outbound Agency - Dogfood",
                    domain=sending_domain,
                    settings={"is_dogfood": True},
                )
                session.add(tenant)
                await session.flush()
                logger.info("Created dogfood tenant: %s", tenant.id)

            # Check if sequence already exists for this tenant
            seq_result = await session.execute(
                select(Sequence).where(
                    Sequence.tenant_id == tenant.id,
                    Sequence.name == "Dogfood Outreach Sequence",
                )
            )
            sequence = seq_result.scalar_one_or_none()

            if sequence is None:
                sequence = Sequence(
                    tenant_id=tenant.id,
                    name="Dogfood Outreach Sequence",
                    steps=self.DOGFOOD_SEQUENCE,
                )
                session.add(sequence)
                await session.flush()
                logger.info("Created dogfood sequence: %s", sequence.id)

            # Check if campaign already exists for this tenant
            camp_result = await session.execute(
                select(Campaign).where(
                    Campaign.tenant_id == tenant.id,
                    Campaign.name == "Dogfood - Sell AI Outbound",
                )
            )
            campaign = camp_result.scalar_one_or_none()

            if campaign is None:
                campaign = Campaign(
                    tenant_id=tenant.id,
                    name="Dogfood - Sell AI Outbound",
                    icp_filter=self.DOGFOOD_ICP,
                    sequence_id=sequence.id,
                    status=CampaignStatus.active,
                )
                session.add(campaign)
                await session.flush()
                logger.info("Created dogfood campaign: %s", campaign.id)

            await session.commit()

            return {
                "tenant_id": str(tenant.id),
                "campaign_id": str(campaign.id),
                "status": "initialized",
            }

    async def run_dogfood_tick(self) -> dict[str, Any]:
        """Run one tick of the dogfood campaign.

        Placeholder that logs the tick. In production this would trigger
        the researcher and sequence runner for the dogfood tenant.
        """
        logger.info(
            "Dogfood tick - would run researcher + sequence for dogfood tenant"
        )
        return {"status": "tick_complete", "leads_found": 0}
