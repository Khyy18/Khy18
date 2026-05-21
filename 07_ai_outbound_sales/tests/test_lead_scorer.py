"""Tests for the LeadScorer module."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from agents.lead_scorer import LeadScorer, trigger_score_update
from core.models import (
    ChannelType,
    EventType,
    LeadStatus,
    MessageDirection,
    MessageStatus,
)
from tests.conftest import (
    make_campaign,
    make_event,
    make_lead,
    make_message,
    make_tenant,
)


@pytest.fixture
def scorer(session_factory):
    """Create a LeadScorer instance with the test session factory."""
    return LeadScorer(session_factory)


async def _setup_lead_with_messages(session: AsyncSession, tenant_id=None, lead_kwargs=None, num_messages=1, campaign_id=None):
    """Helper to create a tenant, lead, campaign, and messages in the DB."""
    tenant = make_tenant(id=tenant_id or uuid.uuid4())
    session.add(tenant)
    await session.flush()

    lead = make_lead(tenant_id=tenant.id, **(lead_kwargs or {}))
    session.add(lead)
    await session.flush()

    campaign = make_campaign(tenant_id=tenant.id, id=campaign_id or uuid.uuid4())
    session.add(campaign)
    await session.flush()

    messages = []
    for _ in range(num_messages):
        msg = make_message(lead_id=lead.id, campaign_id=campaign.id)
        session.add(msg)
        messages.append(msg)
    await session.flush()

    return tenant, lead, campaign, messages


@pytest.mark.asyncio
async def test_score_lead_engagement_open(async_session, scorer):
    """Open events add +5 each, capped at 3."""
    tenant, lead, campaign, messages = await _setup_lead_with_messages(async_session)

    # Add 4 open events (should cap at 3 * 5 = 15)
    for i in range(4):
        evt = make_event(message_id=messages[0].id, event_type=EventType.open)
        async_session.add(evt)
    await async_session.commit()

    score = await scorer.score_lead(lead.id)
    # 3 opens * 5 = 15
    assert score == 15.0


@pytest.mark.asyncio
async def test_score_lead_engagement_click(async_session, scorer):
    """Click events add +10 each, capped at 3."""
    tenant, lead, campaign, messages = await _setup_lead_with_messages(async_session)

    # Add 5 click events (should cap at 3 * 10 = 30)
    for i in range(5):
        evt = make_event(message_id=messages[0].id, event_type=EventType.click)
        async_session.add(evt)
    await async_session.commit()

    score = await scorer.score_lead(lead.id)
    # 3 clicks * 10 = 30
    assert score == 30.0


@pytest.mark.asyncio
async def test_score_lead_engagement_reply(async_session, scorer):
    """Lead with replied status gets +20."""
    tenant, lead, campaign, messages = await _setup_lead_with_messages(
        async_session, lead_kwargs={"status": LeadStatus.replied}
    )
    await async_session.commit()

    score = await scorer.score_lead(lead.id)
    assert score == 20.0


@pytest.mark.asyncio
async def test_score_lead_engagement_booked(async_session, scorer):
    """Lead with booked status gets +100."""
    tenant, lead, campaign, messages = await _setup_lead_with_messages(
        async_session, lead_kwargs={"status": LeadStatus.booked}
    )
    await async_session.commit()

    score = await scorer.score_lead(lead.id)
    assert score == 100.0


@pytest.mark.asyncio
async def test_score_lead_icp_fit(async_session, scorer):
    """Lead with ICP match flags gets appropriate ICP points."""
    enrichment = {
        "company_size_match": True,
        "industry_match": True,
        "title_seniority_match": True,
        "tech_stack_match": True,
        "trigger_events": ["funding_round"],
    }
    tenant, lead, campaign, messages = await _setup_lead_with_messages(
        async_session, lead_kwargs={"enrichment_data": enrichment}
    )
    await async_session.commit()

    score = await scorer.score_lead(lead.id)
    # 20 + 15 + 25 + 10 + 15 = 85
    assert score == 85.0


@pytest.mark.asyncio
async def test_score_lead_combined(async_session, scorer):
    """Combined engagement + ICP fit score."""
    enrichment = {
        "company_size_match": True,
        "industry_match": True,
    }
    tenant, lead, campaign, messages = await _setup_lead_with_messages(
        async_session, lead_kwargs={"enrichment_data": enrichment}
    )

    # Add 2 open events
    for _ in range(2):
        evt = make_event(message_id=messages[0].id, event_type=EventType.open)
        async_session.add(evt)
    await async_session.commit()

    score = await scorer.score_lead(lead.id)
    # engagement: 2 opens * 5 = 10
    # ICP: 20 + 15 = 35
    # total = 45
    assert score == 45.0


@pytest.mark.asyncio
async def test_bulk_rescore(async_session, scorer):
    """bulk_rescore updates all leads in a campaign."""
    tenant = make_tenant()
    async_session.add(tenant)
    await async_session.flush()

    campaign = make_campaign(tenant_id=tenant.id)
    async_session.add(campaign)
    await async_session.flush()

    # Create 3 leads with messages in the same campaign
    leads = []
    for i in range(3):
        lead = make_lead(
            tenant_id=tenant.id,
            enrichment_data={"company_size_match": True},  # +20
        )
        async_session.add(lead)
        await async_session.flush()
        leads.append(lead)

        msg = make_message(lead_id=lead.id, campaign_id=campaign.id)
        async_session.add(msg)
        await async_session.flush()

    await async_session.commit()

    count = await scorer.bulk_rescore(campaign.id)
    assert count == 3

    # Verify scores were updated
    for lead in leads:
        async with scorer._session_factory() as check_session:
            from sqlalchemy import select as sel
            from core.models import Lead

            result = await check_session.execute(sel(Lead).where(Lead.id == lead.id))
            refreshed = result.scalar_one()
            assert refreshed.score == 20.0  # company_size_match only


@pytest.mark.asyncio
async def test_get_hot_leads(async_session, scorer):
    """get_hot_leads returns only leads above threshold sorted desc."""
    tenant = make_tenant()
    async_session.add(tenant)
    await async_session.flush()

    # Create leads with different scores
    lead_high = make_lead(tenant_id=tenant.id, score=95.0)
    lead_medium = make_lead(tenant_id=tenant.id, score=85.0)
    lead_low = make_lead(tenant_id=tenant.id, score=50.0)
    async_session.add_all([lead_high, lead_medium, lead_low])
    await async_session.commit()

    hot = await scorer.get_hot_leads(tenant.id, threshold=80.0)
    assert len(hot) == 2
    assert hot[0].score == 95.0
    assert hot[1].score == 85.0


@pytest.mark.asyncio
async def test_trigger_score_update_handles_missing_lead(session_factory):
    """trigger_score_update does not raise for nonexistent lead."""
    fake_id = uuid.uuid4()
    # Should not raise
    await trigger_score_update(fake_id, session_factory)


@pytest.mark.asyncio
async def test_predict_score():
    """predict_score returns a percentage based on engagement and ICP data."""
    lead_data = {
        "company_size_match": True,
        "industry_match": True,
    }
    engagement_data = {
        "opens": 2,
        "clicks": 1,
        "replied": True,
    }
    result = LeadScorer.predict_score(lead_data, engagement_data)
    # engagement: 2*5 + 1*10 + 20 = 40
    # ICP: 20 + 15 = 35
    # total = 75, max = 315 (MAX_TOTAL_SCORE), percentage = 75/315*100 = 23.8
    assert result == 23.8


@pytest.mark.asyncio
async def test_score_lead_linkedin_connection(async_session, scorer):
    """LinkedIn connection message adds +15."""
    tenant = make_tenant()
    async_session.add(tenant)
    await async_session.flush()

    lead = make_lead(tenant_id=tenant.id)
    async_session.add(lead)
    await async_session.flush()

    campaign = make_campaign(tenant_id=tenant.id)
    async_session.add(campaign)
    await async_session.flush()

    # LinkedIn message with sent status
    msg = make_message(
        lead_id=lead.id,
        campaign_id=campaign.id,
        channel=ChannelType.linkedin,
        status=MessageStatus.sent,
    )
    async_session.add(msg)
    await async_session.commit()

    score = await scorer.score_lead(lead.id)
    assert score == 15.0
