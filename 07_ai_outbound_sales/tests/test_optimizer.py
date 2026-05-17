"""Tests for the OptimizerAgent."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from agents.optimizer import OptimizerAgent
from core.models import (
    ABTest,
    ABTestAssignment,
    ABTestStatus,
    Campaign,
    CampaignStatus,
    ChannelType,
    Event,
    EventType,
    Lead,
    LeadStatus,
    Message,
    MessageDirection,
    MessageStatus,
    Tenant,
)
from tests.conftest import make_campaign, make_lead, make_message, make_tenant


@pytest.fixture
def optimizer(mock_llm_client, session_factory):
    return OptimizerAgent(
        llm_client=mock_llm_client,
        session_factory=session_factory,
        redis_url="redis://localhost:6379/0",
    )


async def test_assign_variant_round_robin(optimizer, async_session, session_factory):
    """Test assign_variant uses round-robin (lowest count gets next assignment)."""
    tenant_id = uuid.uuid4()
    tenant = make_tenant(id=tenant_id)
    async_session.add(tenant)

    campaign = make_campaign(tenant_id=tenant_id)
    async_session.add(campaign)
    await async_session.flush()

    # Create A/B test with 2 variants
    test = ABTest(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        campaign_id=campaign.id,
        name="Subject Line Test",
        status=ABTestStatus.running,
        variants=[{"key": "A"}, {"key": "B"}],
        min_sends_per_variant=100,
    )
    async_session.add(test)
    await async_session.flush()

    # Assign first lead - should get variant with lowest count (both 0, picks first = "A")
    lead1 = make_lead(tenant_id=tenant_id)
    async_session.add(lead1)
    await async_session.flush()

    variant1 = await optimizer.assign_variant(test.id, lead1.id, async_session)
    await async_session.flush()

    # Assign second lead - should get "B" since "A" now has 1
    lead2 = make_lead(tenant_id=tenant_id)
    async_session.add(lead2)
    await async_session.flush()

    variant2 = await optimizer.assign_variant(test.id, lead2.id, async_session)

    assert variant1 == "A"
    assert variant2 == "B"


async def test_assign_variant_existing_assignment(optimizer, async_session, session_factory):
    """Test assign_variant returns existing assignment if lead already assigned."""
    tenant_id = uuid.uuid4()
    tenant = make_tenant(id=tenant_id)
    async_session.add(tenant)

    campaign = make_campaign(tenant_id=tenant_id)
    async_session.add(campaign)
    await async_session.flush()

    test = ABTest(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        campaign_id=campaign.id,
        name="Test",
        status=ABTestStatus.running,
        variants=[{"key": "A"}, {"key": "B"}],
        min_sends_per_variant=100,
    )
    async_session.add(test)

    lead = make_lead(tenant_id=tenant_id)
    async_session.add(lead)
    await async_session.flush()

    # Pre-create assignment
    assignment = ABTestAssignment(
        test_id=test.id,
        lead_id=lead.id,
        variant_key="B",
    )
    async_session.add(assignment)
    await async_session.flush()

    result = await optimizer.assign_variant(test.id, lead.id, async_session)
    assert result == "B"


async def test_check_significance_insufficient_sends(optimizer, async_session):
    """Test check_significance returns not significant when sends below minimum."""
    tenant_id = uuid.uuid4()
    tenant = make_tenant(id=tenant_id)
    async_session.add(tenant)

    campaign = make_campaign(tenant_id=tenant_id)
    async_session.add(campaign)
    await async_session.flush()

    test = ABTest(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        campaign_id=campaign.id,
        name="Test",
        status=ABTestStatus.running,
        variants=[{"key": "A"}, {"key": "B"}],
        min_sends_per_variant=100,  # Need 100, will have 0
    )
    async_session.add(test)
    await async_session.flush()

    result = await optimizer.check_significance(test.id, async_session)

    assert result["is_significant"] is False
    assert result["p_value"] == 1.0
    assert result["winner_key"] is None


async def test_check_significance_with_data(optimizer, async_session):
    """Test check_significance with known contingency table data."""
    tenant_id = uuid.uuid4()
    tenant = make_tenant(id=tenant_id)
    async_session.add(tenant)

    campaign = make_campaign(tenant_id=tenant_id)
    async_session.add(campaign)
    await async_session.flush()

    test = ABTest(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        campaign_id=campaign.id,
        name="Test",
        status=ABTestStatus.running,
        variants=[{"key": "A"}, {"key": "B"}],
        min_sends_per_variant=5,  # Low threshold for testing
    )
    async_session.add(test)
    await async_session.flush()

    # Create leads and assignments for variant A (high conversion)
    leads_a = []
    for _ in range(20):
        lead = make_lead(tenant_id=tenant_id)
        async_session.add(lead)
        leads_a.append(lead)

    # Create leads for variant B (low conversion)
    leads_b = []
    for _ in range(20):
        lead = make_lead(tenant_id=tenant_id)
        async_session.add(lead)
        leads_b.append(lead)

    await async_session.flush()

    # Assign to variants
    for lead in leads_a:
        async_session.add(ABTestAssignment(test_id=test.id, lead_id=lead.id, variant_key="A"))
    for lead in leads_b:
        async_session.add(ABTestAssignment(test_id=test.id, lead_id=lead.id, variant_key="B"))
    await async_session.flush()

    # Create messages (sends) for all leads
    for lead in leads_a + leads_b:
        msg = make_message(
            lead_id=lead.id,
            campaign_id=campaign.id,
            direction=MessageDirection.outbound,
            status=MessageStatus.sent,
        )
        async_session.add(msg)

    await async_session.flush()

    # Create reply events for 15/20 of variant A leads (75% conversion)
    from sqlalchemy import select
    for lead in leads_a[:15]:
        stmt = select(Message).where(Message.lead_id == lead.id)
        msg_result = await async_session.execute(stmt)
        msg = msg_result.scalar_one()
        evt = Event(
            message_id=msg.id,
            event_type=EventType.reply,
            occurred_at=datetime.now(timezone.utc),
        )
        async_session.add(evt)

    # Create reply events for 2/20 of variant B leads (10% conversion)
    for lead in leads_b[:2]:
        stmt = select(Message).where(Message.lead_id == lead.id)
        msg_result = await async_session.execute(stmt)
        msg = msg_result.scalar_one()
        evt = Event(
            message_id=msg.id,
            event_type=EventType.reply,
            occurred_at=datetime.now(timezone.utc),
        )
        async_session.add(evt)

    await async_session.flush()

    result = await optimizer.check_significance(test.id, async_session)

    # With 75% vs 10% on 20 sends each, chi-squared should find significance
    assert result["is_significant"] == True
    assert result["p_value"] < 0.05
    assert result["winner_key"] == "A"


async def test_promote_winner(optimizer, async_session):
    """Test promote_winner sets status=completed and winner_variant_key."""
    tenant_id = uuid.uuid4()
    tenant = make_tenant(id=tenant_id)
    async_session.add(tenant)

    campaign = make_campaign(tenant_id=tenant_id)
    async_session.add(campaign)
    await async_session.flush()

    test = ABTest(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        campaign_id=campaign.id,
        name="Test",
        status=ABTestStatus.running,
        variants=[{"key": "A"}, {"key": "B"}],
        min_sends_per_variant=5,
    )
    async_session.add(test)
    await async_session.flush()

    # Create enough data to have a winner
    leads_a = []
    for _ in range(10):
        lead = make_lead(tenant_id=tenant_id)
        async_session.add(lead)
        leads_a.append(lead)

    leads_b = []
    for _ in range(10):
        lead = make_lead(tenant_id=tenant_id)
        async_session.add(lead)
        leads_b.append(lead)

    await async_session.flush()

    for lead in leads_a:
        async_session.add(ABTestAssignment(test_id=test.id, lead_id=lead.id, variant_key="A"))
    for lead in leads_b:
        async_session.add(ABTestAssignment(test_id=test.id, lead_id=lead.id, variant_key="B"))
    await async_session.flush()

    for lead in leads_a + leads_b:
        msg = make_message(lead_id=lead.id, campaign_id=campaign.id, direction=MessageDirection.outbound, status=MessageStatus.sent)
        async_session.add(msg)
    await async_session.flush()

    # Give variant A better performance
    from sqlalchemy import select
    for lead in leads_a[:8]:
        stmt = select(Message).where(Message.lead_id == lead.id)
        msg_result = await async_session.execute(stmt)
        msg = msg_result.scalar_one()
        async_session.add(Event(message_id=msg.id, event_type=EventType.reply, occurred_at=datetime.now(timezone.utc)))
    await async_session.flush()

    result = await optimizer.promote_winner(test.id, async_session)

    assert result["status"] == "completed"
    assert result["winner_variant_key"] is not None
    # Verify the test record was updated
    assert test.status == ABTestStatus.completed
    assert test.completed_at is not None
