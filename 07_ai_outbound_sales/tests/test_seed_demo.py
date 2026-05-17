"""Tests for the demo seed script."""

import ast
import os
import uuid
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.models import (
    Campaign,
    CampaignStatus,
    Call,
    Lead,
    LeadStatus,
    Message,
    Tenant,
    User,
)


def test_seed_demo_syntax():
    """Verify seed_demo.py is syntactically valid Python."""
    script_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)), "scripts", "seed_demo.py"
    )
    with open(script_path) as f:
        source = f.read()
    # This will raise SyntaxError if the file is invalid
    ast.parse(source)


def test_seed_demo_importable():
    """Verify seed_demo module can be imported."""
    from scripts import seed_demo

    assert hasattr(seed_demo, "seed_demo_data")
    assert hasattr(seed_demo, "run_seed")
    assert hasattr(seed_demo, "DEMO_TENANT_NAME")
    assert seed_demo.DEMO_TENANT_NAME == "Demo Corp"
    assert seed_demo.DEMO_USER_EMAIL == "demo@example.com"


async def test_seed_demo_creates_data(async_session: AsyncSession):
    """Test that seed_demo_data creates expected demo data."""
    from scripts.seed_demo import seed_demo_data

    result = await seed_demo_data(async_session)

    assert result["status"] == "created"
    assert result["tenant"] == "Demo Corp"
    assert result["campaigns"] == 3
    assert result["leads"] == 50
    assert result["messages"] == 20
    assert result["calls"] == 5

    # Verify tenant was created
    tenant_result = await async_session.execute(
        select(Tenant).where(Tenant.name == "Demo Corp")
    )
    tenant = tenant_result.scalar_one()
    assert tenant.domain == "democorp.com"

    # Verify user
    user_result = await async_session.execute(
        select(User).where(User.email == "demo@example.com")
    )
    user = user_result.scalar_one()
    assert user.tenant_id == tenant.id

    # Verify campaigns
    campaigns_result = await async_session.execute(
        select(Campaign).where(Campaign.tenant_id == tenant.id)
    )
    campaigns = campaigns_result.scalars().all()
    assert len(campaigns) == 3
    campaign_names = {c.name for c in campaigns}
    assert "Cold Email Blast" in campaign_names
    assert "LinkedIn Outreach" in campaign_names
    assert "Voice Campaign" in campaign_names

    # Verify leads
    leads_result = await async_session.execute(
        select(Lead).where(Lead.tenant_id == tenant.id)
    )
    leads = leads_result.scalars().all()
    assert len(leads) == 50


async def test_seed_demo_idempotent(async_session: AsyncSession):
    """Test that running seed_demo_data twice does not create duplicates."""
    from scripts.seed_demo import seed_demo_data

    # First run - creates data
    result1 = await seed_demo_data(async_session)
    assert result1["status"] == "created"

    # Second run - should skip
    result2 = await seed_demo_data(async_session)
    assert result2["status"] == "skipped"
    assert "already exists" in result2["reason"]

    # Verify only one tenant exists
    tenant_result = await async_session.execute(
        select(Tenant).where(Tenant.name == "Demo Corp")
    )
    tenants = tenant_result.scalars().all()
    assert len(tenants) == 1


async def test_seed_demo_varied_statuses(async_session: AsyncSession):
    """Test that leads are created with varied statuses."""
    from scripts.seed_demo import seed_demo_data

    await seed_demo_data(async_session)

    leads_result = await async_session.execute(select(Lead))
    leads = leads_result.scalars().all()

    statuses = {lead.status for lead in leads}
    # Should have multiple different statuses
    assert len(statuses) > 1


async def test_seed_demo_calls_have_transcripts(async_session: AsyncSession):
    """Test that calls are created with transcripts and outcomes."""
    from scripts.seed_demo import seed_demo_data

    await seed_demo_data(async_session)

    calls_result = await async_session.execute(select(Call))
    calls = calls_result.scalars().all()

    assert len(calls) == 5
    for call in calls:
        assert call.transcript is not None
        assert len(call.transcript) > 0
        assert call.outcome is not None
        assert call.duration_seconds is not None
        assert call.duration_seconds > 0
