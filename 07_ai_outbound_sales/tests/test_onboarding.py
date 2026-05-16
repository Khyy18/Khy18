"""Tests for the self-serve onboarding flow."""

import json
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select

from core.models import Campaign, CampaignStatus, Sequence, Tenant
from dashboard.routes.onboarding import OnboardingService

# Import factory functions from conftest (available as module-level functions)
from tests.conftest import make_campaign, make_sequence, make_tenant, make_user


@pytest.fixture
def sample_onboarding_data():
    """Sample onboarding questionnaire data."""
    return {
        "company_description": "We build AI-powered sales tools",
        "ideal_customer_industry": "SaaS",
        "ideal_customer_company_size": "50-200",
        "ideal_customer_titles": "VP Sales, Head of Growth, CRO",
        "problem_solved": "Manual outbound is slow and expensive",
        "differentiator": "Fully autonomous AI that books meetings",
        "tone": "professional",
        "website_url": "https://example.com",
    }


@pytest.fixture
def mock_llm_for_onboarding():
    """Mock LLM client that returns a valid campaign plan JSON."""
    client = AsyncMock()
    plan = {
        "campaign_name": "SaaS Growth Outbound",
        "value_proposition": "Fully autonomous AI that books meetings for SaaS companies",
        "icp_filter": {
            "industry": "SaaS",
            "company_size": "50-200",
            "titles": "VP Sales, Head of Growth, CRO",
        },
        "sequence": [
            {
                "step_type": "initial",
                "subject": "Quick question about your outbound",
                "body": "Hi {{first_name}}, noticed your team is growing...",
            },
            {
                "step_type": "follow_up_1",
                "subject": "Following up",
                "body": "Hi {{first_name}}, just checking if you saw my previous note...",
            },
            {
                "step_type": "follow_up_2",
                "subject": "One last thought",
                "body": "Hi {{first_name}}, I wanted to share one more thing...",
            },
        ],
    }
    client.generate = AsyncMock(return_value=json.dumps(plan))
    return client


async def test_setup_stores_onboarding_data(async_session, sample_onboarding_data):
    """Test that setup endpoint stores onboarding data in tenant settings."""
    tenant = make_tenant(settings={})
    async_session.add(tenant)
    await async_session.flush()

    service = OnboardingService(session=async_session)
    result = await service.store_setup_data(
        tenant_id=tenant.id,
        data=sample_onboarding_data,
    )

    assert result == {"status": "ok", "step": "generate"}

    # Verify data is stored in tenant settings
    await async_session.refresh(tenant)
    assert tenant.settings["onboarding_data"] == sample_onboarding_data


async def test_generate_creates_campaign_and_sequence(
    async_session, sample_onboarding_data, mock_llm_for_onboarding
):
    """Test that generate endpoint creates a Campaign and Sequence in DB."""
    tenant = make_tenant(settings={"onboarding_data": sample_onboarding_data})
    async_session.add(tenant)
    await async_session.flush()

    service = OnboardingService(
        session=async_session, llm_client=mock_llm_for_onboarding
    )
    preview = await service.generate_campaign(tenant_id=tenant.id)

    # Verify preview structure
    assert "campaign_name" in preview
    assert "value_proposition" in preview
    assert "icp_filter" in preview
    assert "sequence" in preview
    assert "campaign_id" in preview
    assert "sequence_id" in preview

    # Verify Campaign was created
    campaigns = (
        await async_session.execute(
            select(Campaign).where(Campaign.tenant_id == tenant.id)
        )
    ).scalars().all()
    assert len(campaigns) == 1
    assert campaigns[0].status == CampaignStatus.draft
    assert campaigns[0].name == "SaaS Growth Outbound"

    # Verify Sequence was created
    sequences = (
        await async_session.execute(
            select(Sequence).where(Sequence.tenant_id == tenant.id)
        )
    ).scalars().all()
    assert len(sequences) == 1
    assert len(sequences[0].steps) == 3

    # Verify LLM was called
    mock_llm_for_onboarding.generate.assert_called_once()


async def test_confirm_activates_campaign(async_session):
    """Test that confirm endpoint activates the draft campaign."""
    tenant = make_tenant(settings={})
    async_session.add(tenant)
    await async_session.flush()

    # Create a draft campaign
    sequence = make_sequence(tenant_id=tenant.id)
    async_session.add(sequence)
    await async_session.flush()

    campaign = make_campaign(
        tenant_id=tenant.id,
        sequence_id=sequence.id,
        status=CampaignStatus.draft,
    )
    async_session.add(campaign)
    await async_session.flush()

    service = OnboardingService(session=async_session)
    result = await service.confirm_campaign(tenant_id=tenant.id)

    assert result["status"] == "activated"
    assert result["campaign_id"] == str(campaign.id)
    assert "3-5 days" in result["message"]

    # Verify campaign is now active
    await async_session.refresh(campaign)
    assert campaign.status == CampaignStatus.active


async def test_generate_without_setup_returns_error(async_session):
    """Test that calling generate without setup data returns an error."""
    tenant = make_tenant(settings={})
    async_session.add(tenant)
    await async_session.flush()

    mock_llm = AsyncMock()
    service = OnboardingService(session=async_session, llm_client=mock_llm)

    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc_info:
        await service.generate_campaign(tenant_id=tenant.id)

    assert exc_info.value.status_code == 400
    assert "No onboarding data found" in exc_info.value.detail


async def test_confirm_without_draft_returns_error(async_session):
    """Test that calling confirm with no draft campaign returns an error."""
    tenant = make_tenant(settings={})
    async_session.add(tenant)
    await async_session.flush()

    service = OnboardingService(session=async_session)

    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc_info:
        await service.confirm_campaign(tenant_id=tenant.id)

    assert exc_info.value.status_code == 404
    assert "No draft campaign found" in exc_info.value.detail


async def test_generate_handles_invalid_llm_response(
    async_session, sample_onboarding_data
):
    """Test that generate handles non-JSON LLM response gracefully with fallback."""
    tenant = make_tenant(settings={"onboarding_data": sample_onboarding_data})
    async_session.add(tenant)
    await async_session.flush()

    # LLM returns non-JSON
    mock_llm = AsyncMock()
    mock_llm.generate = AsyncMock(return_value="Sorry, I cannot generate that.")

    service = OnboardingService(session=async_session, llm_client=mock_llm)
    preview = await service.generate_campaign(tenant_id=tenant.id)

    # Should still work with fallback plan
    assert "campaign_name" in preview
    assert "sequence" in preview

    # Verify Campaign and Sequence still created
    campaigns = (
        await async_session.execute(
            select(Campaign).where(Campaign.tenant_id == tenant.id)
        )
    ).scalars().all()
    assert len(campaigns) == 1


async def test_setup_stores_data_preserving_existing_settings(async_session, sample_onboarding_data):
    """Test that setup preserves existing tenant settings."""
    tenant = make_tenant(settings={"existing_key": "existing_value"})
    async_session.add(tenant)
    await async_session.flush()

    service = OnboardingService(session=async_session)
    await service.store_setup_data(tenant_id=tenant.id, data=sample_onboarding_data)

    await async_session.refresh(tenant)
    assert tenant.settings["existing_key"] == "existing_value"
    assert tenant.settings["onboarding_data"] == sample_onboarding_data
