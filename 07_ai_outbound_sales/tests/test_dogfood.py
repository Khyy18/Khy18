"""Tests for the Dogfooding System."""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock

from sqlalchemy import select

from agents.dogfood import DogfoodAgent
from core.models import Campaign, CampaignStatus, Sequence, Tenant


@pytest.fixture
def dogfood_settings():
    """Create mock settings for dogfood agent."""
    s = MagicMock()
    s.dogfood_sending_domain = "test-dogfood.example.com"
    s.dogfood_enabled = True
    return s


@pytest.fixture
def dogfood_agent(dogfood_settings, session_factory):
    """Create a DogfoodAgent instance for testing."""
    return DogfoodAgent(
        settings=dogfood_settings,
        session_factory=session_factory,
    )


async def test_initialize_dogfood_campaign_creates_tenant(dogfood_agent, session_factory):
    """initialize_dogfood_campaign should create a dogfood tenant."""
    result = await dogfood_agent.initialize_dogfood_campaign()

    assert result["status"] == "initialized"
    assert result["tenant_id"] is not None

    # Verify tenant was created
    async with session_factory() as session:
        tenant_result = await session.execute(
            select(Tenant).where(Tenant.name == "AI Outbound Agency - Dogfood")
        )
        tenant = tenant_result.scalar_one_or_none()
        assert tenant is not None
        assert tenant.domain == "test-dogfood.example.com"


async def test_initialize_dogfood_campaign_creates_campaign(dogfood_agent, session_factory):
    """initialize_dogfood_campaign should create a campaign with ICP filter."""
    result = await dogfood_agent.initialize_dogfood_campaign()

    assert result["campaign_id"] is not None

    # Verify campaign was created
    async with session_factory() as session:
        camp_result = await session.execute(
            select(Campaign).where(Campaign.name == "Dogfood - Sell AI Outbound")
        )
        campaign = camp_result.scalar_one_or_none()
        assert campaign is not None
        assert campaign.status == CampaignStatus.active
        assert campaign.icp_filter["industry"] == "B2B SaaS"


async def test_initialize_dogfood_campaign_idempotent(dogfood_agent, session_factory):
    """Calling initialize_dogfood_campaign twice should not create duplicates."""
    result1 = await dogfood_agent.initialize_dogfood_campaign()
    result2 = await dogfood_agent.initialize_dogfood_campaign()

    assert result1["tenant_id"] == result2["tenant_id"]
    assert result1["campaign_id"] == result2["campaign_id"]

    # Verify only one tenant exists
    async with session_factory() as session:
        tenant_result = await session.execute(
            select(Tenant).where(Tenant.name == "AI Outbound Agency - Dogfood")
        )
        tenants = tenant_result.scalars().all()
        assert len(tenants) == 1


async def test_run_dogfood_tick_returns_status(dogfood_agent):
    """run_dogfood_tick should return a status dict."""
    result = await dogfood_agent.run_dogfood_tick()

    assert result["status"] == "tick_complete"
    assert result["leads_found"] == 0
