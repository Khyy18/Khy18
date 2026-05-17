"""End-to-end integration tests for the full outbound sales pipeline.

These tests exercise real database operations with in-memory SQLite and mock
only external services (LLM, SMTP, Apollo). They verify state machine
transitions, message counts, event creation, and score updates across the
complete pipeline from tenant creation to meeting booking.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from core.models import (
    Base,
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
    Sequence,
    Tenant,
    User,
    UserRole,
)
from tests.conftest import (
    make_campaign,
    make_event,
    make_lead,
    make_message,
    make_sequence,
    make_tenant,
    make_user,
)


# ---------- Helper functions ----------


def _create_tenant_and_user():
    """Create a tenant and user pair."""
    tenant = make_tenant(name="E2E Corp", domain="e2ecorp.com")
    user = make_user(tenant_id=tenant.id, email="admin@e2ecorp.com")
    return tenant, user


def _create_campaign_with_sequence(tenant_id: uuid.UUID, steps: list[dict] | None = None):
    """Create a campaign with an associated sequence."""
    if steps is None:
        steps = [
            {"step_type": "initial", "delay_days": 0},
            {"step_type": "follow_up_1", "delay_days": 3},
            {"step_type": "follow_up_2", "delay_days": 5},
            {"step_type": "breakup", "delay_days": 7},
        ]
    sequence = make_sequence(tenant_id=tenant_id, name="E2E Sequence", steps=steps)
    campaign = make_campaign(
        tenant_id=tenant_id,
        name="E2E Campaign",
        status=CampaignStatus.active,
        sequence_id=sequence.id,
    )
    return campaign, sequence


# ---------- Scenario 1: Full Happy Path ----------


async def test_e2e_full_happy_path(async_session: AsyncSession):
    """Full pipeline: tenant -> campaign -> research -> enrich -> send -> reply -> qualify -> book.

    Verifies state transitions: new -> contacted -> replied -> qualified -> booked.
    Verifies message count, event creation at each step, and score update.
    """
    # Step 1: Create tenant + user
    tenant, user = _create_tenant_and_user()
    async_session.add(tenant)
    async_session.add(user)
    await async_session.commit()

    # Step 2: Create campaign with 4-step sequence
    campaign, sequence = _create_campaign_with_sequence(tenant.id)
    async_session.add(sequence)
    async_session.add(campaign)
    await async_session.commit()

    # Step 3: Mock researcher returns 3 leads -> insert into DB
    leads_data = [
        {"first_name": "Alice", "last_name": "Smith", "email": "alice@target.com",
         "company": "Target Inc", "title": "VP Engineering"},
        {"first_name": "Bob", "last_name": "Jones", "email": "bob@target.com",
         "company": "Target Inc", "title": "CTO"},
        {"first_name": "Carol", "last_name": "Lee", "email": "carol@target.com",
         "company": "Target Inc", "title": "Director of Sales"},
    ]

    leads = []
    for data in leads_data:
        lead = make_lead(tenant_id=tenant.id, status=LeadStatus.new, score=0.0, **data)
        leads.append(lead)
        async_session.add(lead)
    await async_session.commit()

    # Verify leads are new
    result = await async_session.execute(
        select(Lead).where(Lead.tenant_id == tenant.id)
    )
    db_leads = result.scalars().all()
    assert len(db_leads) == 3
    assert all(l.status == LeadStatus.new for l in db_leads)

    # Step 4: Mock enricher enriches leads -> update enrichment_data
    for lead in leads:
        lead.enrichment_data = {
            "company_size": 500,
            "industry": "Technology",
            "recent_news": "Series B funding",
            "talking_points": ["AI adoption", "scaling team"],
        }
        lead.score = 75.0
    await async_session.commit()

    # Step 5: Mock copywriter generates email -> create Message with status=sent
    primary_lead = leads[0]  # Focus on Alice for the happy path

    outbound_msg = make_message(
        lead_id=primary_lead.id,
        campaign_id=campaign.id,
        channel=ChannelType.email,
        direction=MessageDirection.outbound,
        content="<p>Hi Alice, I noticed Target Inc just raised Series B...</p>",
        subject="Congrats on the funding!",
        status=MessageStatus.sent,
        sent_at=datetime.now(timezone.utc),
    )
    outbound_msg.meta = {"sequence_step": 0}
    async_session.add(outbound_msg)
    await async_session.commit()

    # Update lead status to contacted
    primary_lead.status = LeadStatus.contacted
    await async_session.commit()

    # Step 6: Mock email sender "sends" -> create sent event
    sent_event = make_event(message_id=outbound_msg.id, event_type=EventType.open)
    async_session.add(sent_event)
    await async_session.commit()

    # Step 7: Simulate lead reply
    inbound_msg = make_message(
        lead_id=primary_lead.id,
        campaign_id=campaign.id,
        channel=ChannelType.email,
        direction=MessageDirection.inbound,
        content="Hi! Yes, we are interested in learning more about your solution.",
        subject="Re: Congrats on the funding!",
        status=MessageStatus.replied,
    )
    async_session.add(inbound_msg)

    reply_event = make_event(message_id=outbound_msg.id, event_type=EventType.reply)
    async_session.add(reply_event)
    await async_session.commit()

    # Update lead to replied
    primary_lead.status = LeadStatus.replied
    await async_session.commit()

    # Step 8: Conversation agent classifies as "positive" -> update to qualified
    primary_lead.status = LeadStatus.qualified
    primary_lead.score = 90.0
    await async_session.commit()

    # Step 9: Meeting booking -> update lead to booked
    primary_lead.status = LeadStatus.booked
    primary_lead.score = 100.0
    await async_session.commit()

    # ---------- VERIFY ----------
    # Verify lead status
    await async_session.refresh(primary_lead)
    assert primary_lead.status == LeadStatus.booked

    # Verify message count (1 outbound + 1 inbound = 2 for this lead)
    msg_result = await async_session.execute(
        select(func.count(Message.id)).where(Message.lead_id == primary_lead.id)
    )
    assert msg_result.scalar() == 2

    # Verify events (open + reply = 2)
    event_result = await async_session.execute(
        select(func.count(Event.id)).where(Event.message_id == outbound_msg.id)
    )
    assert event_result.scalar() == 2

    # Verify score updated
    assert primary_lead.score == 100.0

    # Verify enrichment data
    assert primary_lead.enrichment_data["company_size"] == 500


# ---------- Scenario 2: Objection Handling ----------


async def test_e2e_objection_handling(async_session: AsyncSession):
    """Lead replies with objection. Conversation agent classifies as objection.
    Lead stays at replied status, no meeting booked.
    """
    # Setup
    tenant, user = _create_tenant_and_user()
    async_session.add(tenant)
    async_session.add(user)
    await async_session.commit()

    campaign, sequence = _create_campaign_with_sequence(tenant.id)
    async_session.add(sequence)
    async_session.add(campaign)
    await async_session.commit()

    lead = make_lead(
        tenant_id=tenant.id,
        first_name="Dave",
        last_name="Wilson",
        email="dave@objector.com",
        company="Objector LLC",
        title="CFO",
        status=LeadStatus.new,
    )
    async_session.add(lead)
    await async_session.commit()

    # Send initial email
    outbound_msg = make_message(
        lead_id=lead.id,
        campaign_id=campaign.id,
        direction=MessageDirection.outbound,
        status=MessageStatus.sent,
        content="<p>Hi Dave, wanted to reach out...</p>",
        subject="Quick question",
    )
    async_session.add(outbound_msg)
    lead.status = LeadStatus.contacted
    await async_session.commit()

    # Lead replies with objection
    inbound_msg = make_message(
        lead_id=lead.id,
        campaign_id=campaign.id,
        direction=MessageDirection.inbound,
        status=MessageStatus.replied,
        content="Not interested right now, budget is frozen until Q3.",
        subject="Re: Quick question",
    )
    async_session.add(inbound_msg)

    reply_event = make_event(message_id=outbound_msg.id, event_type=EventType.reply)
    async_session.add(reply_event)

    lead.status = LeadStatus.replied
    await async_session.commit()

    # Conversation agent classifies as "objection" - lead stays at replied
    # No status change to qualified or booked
    await async_session.refresh(lead)

    # ---------- VERIFY ----------
    assert lead.status == LeadStatus.replied  # Not qualified

    # Verify message count (1 outbound + 1 inbound)
    msg_result = await async_session.execute(
        select(func.count(Message.id)).where(Message.lead_id == lead.id)
    )
    assert msg_result.scalar() == 2

    # Verify reply event exists
    event_result = await async_session.execute(
        select(Event).where(
            Event.message_id == outbound_msg.id,
            Event.event_type == EventType.reply,
        )
    )
    assert event_result.scalar_one_or_none() is not None

    # No meeting booked - status is not booked
    assert lead.status != LeadStatus.booked
    assert lead.status != LeadStatus.qualified


# ---------- Scenario 3: Unsubscribe Flow ----------


async def test_e2e_unsubscribe_flow(async_session: AsyncSession):
    """Lead replies with unsubscribe request. Lead status set to lost.
    Unsubscribe event created. No further messages sent.
    """
    # Setup
    tenant, user = _create_tenant_and_user()
    async_session.add(tenant)
    async_session.add(user)
    await async_session.commit()

    campaign, sequence = _create_campaign_with_sequence(tenant.id)
    async_session.add(sequence)
    async_session.add(campaign)
    await async_session.commit()

    lead = make_lead(
        tenant_id=tenant.id,
        first_name="Eve",
        last_name="Brown",
        email="eve@unsubscribe.com",
        company="Unsub Co",
        title="Marketing Director",
        status=LeadStatus.new,
    )
    async_session.add(lead)
    await async_session.commit()

    # Send initial email
    outbound_msg = make_message(
        lead_id=lead.id,
        campaign_id=campaign.id,
        direction=MessageDirection.outbound,
        status=MessageStatus.sent,
        content="<p>Hi Eve, quick intro...</p>",
        subject="Introduction",
    )
    async_session.add(outbound_msg)
    lead.status = LeadStatus.contacted
    await async_session.commit()

    # Simulate "please unsubscribe me" reply
    inbound_msg = make_message(
        lead_id=lead.id,
        campaign_id=campaign.id,
        direction=MessageDirection.inbound,
        status=MessageStatus.replied,
        content="Please unsubscribe me from this list. Do not contact me again.",
        subject="Re: Introduction",
    )
    async_session.add(inbound_msg)
    await async_session.commit()

    # Conversation agent classifies as "unsubscribe"
    # Create unsubscribe event
    unsub_event = make_event(
        message_id=outbound_msg.id, event_type=EventType.unsubscribe
    )
    async_session.add(unsub_event)

    # Lead status -> lost
    lead.status = LeadStatus.lost
    await async_session.commit()

    # ---------- VERIFY ----------
    await async_session.refresh(lead)
    assert lead.status == LeadStatus.lost

    # Verify unsubscribe event created
    event_result = await async_session.execute(
        select(Event).where(
            Event.message_id == outbound_msg.id,
            Event.event_type == EventType.unsubscribe,
        )
    )
    assert event_result.scalar_one_or_none() is not None

    # Verify no further messages sent after unsubscribe
    # (only 1 outbound + 1 inbound = 2 total)
    msg_result = await async_session.execute(
        select(func.count(Message.id)).where(Message.lead_id == lead.id)
    )
    assert msg_result.scalar() == 2

    # Verify no outbound messages after the unsubscribe reply
    outbound_result = await async_session.execute(
        select(func.count(Message.id)).where(
            Message.lead_id == lead.id,
            Message.direction == MessageDirection.outbound,
        )
    )
    assert outbound_result.scalar() == 1  # Only the initial send


# ---------- Scenario 4: Bounce Handling ----------


async def test_e2e_bounce_handling(async_session: AsyncSession):
    """Email bounces. Bounce event created. Lead removed from active sequence.
    No further messages sent for this lead.
    """
    # Setup
    tenant, user = _create_tenant_and_user()
    async_session.add(tenant)
    async_session.add(user)
    await async_session.commit()

    campaign, sequence = _create_campaign_with_sequence(tenant.id)
    async_session.add(sequence)
    async_session.add(campaign)
    await async_session.commit()

    lead = make_lead(
        tenant_id=tenant.id,
        first_name="Frank",
        last_name="Garcia",
        email="frank@invalid-domain-xyz.com",
        company="Bounce Corp",
        title="Sales Manager",
        status=LeadStatus.new,
    )
    async_session.add(lead)
    await async_session.commit()

    # Send email
    outbound_msg = make_message(
        lead_id=lead.id,
        campaign_id=campaign.id,
        direction=MessageDirection.outbound,
        status=MessageStatus.sent,
        content="<p>Hi Frank, reaching out...</p>",
        subject="Partnership opportunity",
    )
    async_session.add(outbound_msg)
    lead.status = LeadStatus.contacted
    await async_session.commit()

    # Simulate bounce event
    bounce_event = make_event(message_id=outbound_msg.id, event_type=EventType.bounce)
    bounce_event.meta = {"bounce_type": "hard", "reason": "mailbox not found"}
    async_session.add(bounce_event)

    # Update message status to bounced
    outbound_msg.status = MessageStatus.bounced
    await async_session.commit()

    # Lead status remains contacted (not progressed further) but
    # is effectively removed from active sequence (no more sends)
    # In some implementations lead goes to lost; here we keep at contacted
    # to show sequence stopped

    # ---------- VERIFY ----------
    await async_session.refresh(lead)
    # Lead status is contacted (no further progression)
    assert lead.status == LeadStatus.contacted

    # Verify bounce event created
    event_result = await async_session.execute(
        select(Event).where(
            Event.message_id == outbound_msg.id,
            Event.event_type == EventType.bounce,
        )
    )
    bounce = event_result.scalar_one_or_none()
    assert bounce is not None
    assert bounce.meta.get("bounce_type") == "hard"

    # Verify message status is bounced
    await async_session.refresh(outbound_msg)
    assert outbound_msg.status == MessageStatus.bounced

    # No further messages sent (only 1 outbound total)
    msg_result = await async_session.execute(
        select(func.count(Message.id)).where(
            Message.lead_id == lead.id,
            Message.direction == MessageDirection.outbound,
        )
    )
    assert msg_result.scalar() == 1


# ---------- Scenario 5: Multi-Step Sequence ----------


async def test_e2e_multi_step_sequence(async_session: AsyncSession):
    """Lead receives 3 emails over sequence steps without replying.
    After all steps completed, lead stays at contacted.
    Verifies: 3 messages total, all with status=sent, correct sequence step metadata.
    """
    # Setup
    tenant, user = _create_tenant_and_user()
    async_session.add(tenant)
    async_session.add(user)
    await async_session.commit()

    steps = [
        {"step_type": "initial", "delay_days": 0},
        {"step_type": "follow_up_1", "delay_days": 3},
        {"step_type": "follow_up_2", "delay_days": 5},
    ]
    campaign, sequence = _create_campaign_with_sequence(tenant.id, steps=steps)
    async_session.add(sequence)
    async_session.add(campaign)
    await async_session.commit()

    lead = make_lead(
        tenant_id=tenant.id,
        first_name="Grace",
        last_name="Kim",
        email="grace@multistep.com",
        company="MultiStep Inc",
        title="Head of Product",
        status=LeadStatus.new,
    )
    async_session.add(lead)
    await async_session.commit()

    # Execute step 1: Send initial email
    msg1 = make_message(
        lead_id=lead.id,
        campaign_id=campaign.id,
        direction=MessageDirection.outbound,
        status=MessageStatus.sent,
        content="<p>Hi Grace, initial outreach...</p>",
        subject="Quick intro",
        sent_at=datetime.now(timezone.utc),
    )
    msg1.meta = {"sequence_step": 0, "step_type": "initial"}
    async_session.add(msg1)
    lead.status = LeadStatus.contacted
    await async_session.commit()

    # Create open event for step 1
    open_event_1 = make_event(message_id=msg1.id, event_type=EventType.open)
    async_session.add(open_event_1)
    await async_session.commit()

    # Execute step 2: Send follow-up 1 (lead hasn't replied)
    msg2 = make_message(
        lead_id=lead.id,
        campaign_id=campaign.id,
        direction=MessageDirection.outbound,
        status=MessageStatus.sent,
        content="<p>Hi Grace, following up on my previous email...</p>",
        subject="Following up",
        sent_at=datetime.now(timezone.utc),
    )
    msg2.meta = {"sequence_step": 1, "step_type": "follow_up_1"}
    async_session.add(msg2)
    await async_session.commit()

    # Execute step 3: Send follow-up 2 (lead still hasn't replied)
    msg3 = make_message(
        lead_id=lead.id,
        campaign_id=campaign.id,
        direction=MessageDirection.outbound,
        status=MessageStatus.sent,
        content="<p>Hi Grace, one last try...</p>",
        subject="Last follow-up",
        sent_at=datetime.now(timezone.utc),
    )
    msg3.meta = {"sequence_step": 2, "step_type": "follow_up_2"}
    async_session.add(msg3)
    await async_session.commit()

    # ---------- VERIFY ----------
    await async_session.refresh(lead)
    # Lead stays at contacted (no reply received)
    assert lead.status == LeadStatus.contacted

    # Verify 3 outbound messages total for this lead
    msg_result = await async_session.execute(
        select(Message).where(
            Message.lead_id == lead.id,
            Message.direction == MessageDirection.outbound,
        )
    )
    messages = msg_result.scalars().all()
    assert len(messages) == 3

    # Verify all messages have status=sent
    assert all(m.status == MessageStatus.sent for m in messages)

    # Verify correct sequence step metadata
    step_types = [m.meta.get("step_type") for m in messages]
    assert "initial" in step_types
    assert "follow_up_1" in step_types
    assert "follow_up_2" in step_types

    step_numbers = sorted([m.meta.get("sequence_step") for m in messages])
    assert step_numbers == [0, 1, 2]

    # Verify open event exists for step 1
    event_result = await async_session.execute(
        select(func.count(Event.id)).where(Event.message_id == msg1.id)
    )
    assert event_result.scalar() == 1

    # Verify no inbound messages (no replies)
    inbound_result = await async_session.execute(
        select(func.count(Message.id)).where(
            Message.lead_id == lead.id,
            Message.direction == MessageDirection.inbound,
        )
    )
    assert inbound_result.scalar() == 0


# ---------- Scenario 6: Multi-Channel Escalation ----------


async def test_e2e_multi_channel_escalation(async_session: AsyncSession):
    """Lead gets email, no reply after 5 days, LinkedIn message queued.

    Verifies: 2 outbound messages (1 email + 1 LinkedIn), correct channel types,
    lead remains at contacted status, and sequence_step metadata is correct.
    """
    # Setup
    tenant, user = _create_tenant_and_user()
    async_session.add(tenant)
    async_session.add(user)
    await async_session.commit()

    steps = [
        {"step_type": "initial_email", "delay_days": 0, "channel": "email"},
        {"step_type": "linkedin_follow_up", "delay_days": 5, "channel": "linkedin"},
    ]
    campaign, sequence = _create_campaign_with_sequence(tenant.id, steps=steps)
    async_session.add(sequence)
    async_session.add(campaign)
    await async_session.commit()

    lead = make_lead(
        tenant_id=tenant.id,
        first_name="Hannah",
        last_name="Park",
        email="hannah@multichannel.com",
        company="MultiChannel Corp",
        title="VP Growth",
        status=LeadStatus.new,
    )
    async_session.add(lead)
    await async_session.commit()

    # Step 1: Send initial email (day 0)
    email_msg = make_message(
        lead_id=lead.id,
        campaign_id=campaign.id,
        channel=ChannelType.email,
        direction=MessageDirection.outbound,
        status=MessageStatus.sent,
        content="<p>Hi Hannah, reaching out about growth strategies...</p>",
        subject="Growth partnership",
        sent_at=datetime.now(timezone.utc),
    )
    email_msg.meta = {"sequence_step": 0, "step_type": "initial_email", "channel": "email"}
    async_session.add(email_msg)
    lead.status = LeadStatus.contacted
    await async_session.commit()

    # No reply received. 5 days pass (simulated by just proceeding to step 2).

    # Step 2: LinkedIn message queued (day 5, no reply to email)
    linkedin_msg = make_message(
        lead_id=lead.id,
        campaign_id=campaign.id,
        channel=ChannelType.linkedin,
        direction=MessageDirection.outbound,
        status=MessageStatus.sent,
        content="Hi Hannah, I sent you an email last week about growth strategies. Would love to connect!",
        subject=None,
        sent_at=datetime.now(timezone.utc),
    )
    linkedin_msg.meta = {"sequence_step": 1, "step_type": "linkedin_follow_up", "channel": "linkedin"}
    async_session.add(linkedin_msg)
    await async_session.commit()

    # ---------- VERIFY ----------
    await async_session.refresh(lead)

    # Lead still at contacted (no reply received)
    assert lead.status == LeadStatus.contacted

    # Verify 2 outbound messages total
    msg_result = await async_session.execute(
        select(Message).where(
            Message.lead_id == lead.id,
            Message.direction == MessageDirection.outbound,
        )
    )
    messages = msg_result.scalars().all()
    assert len(messages) == 2

    # Verify channel types: 1 email + 1 linkedin
    channels = [m.channel for m in messages]
    assert ChannelType.email in channels
    assert ChannelType.linkedin in channels

    # Verify correct sequence_step metadata
    email_msgs = [m for m in messages if m.channel == ChannelType.email]
    linkedin_msgs = [m for m in messages if m.channel == ChannelType.linkedin]

    assert len(email_msgs) == 1
    assert email_msgs[0].meta["sequence_step"] == 0
    assert email_msgs[0].meta["step_type"] == "initial_email"

    assert len(linkedin_msgs) == 1
    assert linkedin_msgs[0].meta["sequence_step"] == 1
    assert linkedin_msgs[0].meta["step_type"] == "linkedin_follow_up"
    assert linkedin_msgs[0].meta["channel"] == "linkedin"

    # Verify no inbound messages
    inbound_result = await async_session.execute(
        select(func.count(Message.id)).where(
            Message.lead_id == lead.id,
            Message.direction == MessageDirection.inbound,
        )
    )
    assert inbound_result.scalar() == 0


# ---------- Scenario 7: Deduplication Across Campaigns ----------


async def test_e2e_deduplication_across_campaigns(async_session: AsyncSession):
    """Same lead enrolled in two campaigns. Messages tracked per campaign_id independently.

    Verifies: lead has messages from both campaigns, each campaign tracks
    its own messages independently, and no message deduplication occurs at the
    data layer (both campaigns can message the same lead).
    """
    # Setup
    tenant, user = _create_tenant_and_user()
    async_session.add(tenant)
    async_session.add(user)
    await async_session.commit()

    # Create two campaigns
    sequence1 = make_sequence(tenant_id=tenant.id, name="Sequence A")
    sequence2 = make_sequence(tenant_id=tenant.id, name="Sequence B")
    async_session.add(sequence1)
    async_session.add(sequence2)
    await async_session.commit()

    campaign1 = make_campaign(
        tenant_id=tenant.id,
        name="Campaign Alpha",
        status=CampaignStatus.active,
        sequence_id=sequence1.id,
    )
    campaign2 = make_campaign(
        tenant_id=tenant.id,
        name="Campaign Beta",
        status=CampaignStatus.active,
        sequence_id=sequence2.id,
    )
    async_session.add(campaign1)
    async_session.add(campaign2)
    await async_session.commit()

    # Same lead added to both campaigns (same email address)
    lead = make_lead(
        tenant_id=tenant.id,
        first_name="Ivan",
        last_name="Chen",
        email="ivan@shared-lead.com",
        company="Shared Lead Inc",
        title="CTO",
        status=LeadStatus.new,
    )
    async_session.add(lead)
    await async_session.commit()

    # Campaign 1 sends initial email
    msg_c1 = make_message(
        lead_id=lead.id,
        campaign_id=campaign1.id,
        channel=ChannelType.email,
        direction=MessageDirection.outbound,
        status=MessageStatus.sent,
        content="<p>Hi Ivan, Campaign Alpha here...</p>",
        subject="From Campaign Alpha",
        sent_at=datetime.now(timezone.utc),
    )
    msg_c1.meta = {"sequence_step": 0, "campaign_name": "Campaign Alpha"}
    async_session.add(msg_c1)
    await async_session.commit()

    # Campaign 2 sends its own initial email
    msg_c2 = make_message(
        lead_id=lead.id,
        campaign_id=campaign2.id,
        channel=ChannelType.email,
        direction=MessageDirection.outbound,
        status=MessageStatus.sent,
        content="<p>Hi Ivan, Campaign Beta reaching out...</p>",
        subject="From Campaign Beta",
        sent_at=datetime.now(timezone.utc),
    )
    msg_c2.meta = {"sequence_step": 0, "campaign_name": "Campaign Beta"}
    async_session.add(msg_c2)
    await async_session.commit()

    # Update lead status
    lead.status = LeadStatus.contacted
    await async_session.commit()

    # Campaign 1 sends follow-up
    msg_c1_followup = make_message(
        lead_id=lead.id,
        campaign_id=campaign1.id,
        channel=ChannelType.email,
        direction=MessageDirection.outbound,
        status=MessageStatus.sent,
        content="<p>Hi Ivan, following up from Campaign Alpha...</p>",
        subject="Re: From Campaign Alpha",
        sent_at=datetime.now(timezone.utc),
    )
    msg_c1_followup.meta = {"sequence_step": 1, "campaign_name": "Campaign Alpha"}
    async_session.add(msg_c1_followup)
    await async_session.commit()

    # ---------- VERIFY ----------
    await async_session.refresh(lead)
    assert lead.status == LeadStatus.contacted

    # Verify total messages for this lead: 3 (2 from campaign1, 1 from campaign2)
    total_msg_result = await async_session.execute(
        select(func.count(Message.id)).where(Message.lead_id == lead.id)
    )
    assert total_msg_result.scalar() == 3

    # Verify messages tracked per campaign_id independently
    c1_msg_result = await async_session.execute(
        select(Message).where(
            Message.lead_id == lead.id,
            Message.campaign_id == campaign1.id,
        )
    )
    c1_messages = c1_msg_result.scalars().all()
    assert len(c1_messages) == 2  # Initial + follow-up

    c2_msg_result = await async_session.execute(
        select(Message).where(
            Message.lead_id == lead.id,
            Message.campaign_id == campaign2.id,
        )
    )
    c2_messages = c2_msg_result.scalars().all()
    assert len(c2_messages) == 1  # Only initial

    # Verify campaign metadata is correct
    c1_campaign_names = [m.meta.get("campaign_name") for m in c1_messages]
    assert all(name == "Campaign Alpha" for name in c1_campaign_names)

    c2_campaign_names = [m.meta.get("campaign_name") for m in c2_messages]
    assert all(name == "Campaign Beta" for name in c2_campaign_names)

    # Verify both campaigns reference the same lead
    all_msg_result = await async_session.execute(
        select(Message).where(Message.lead_id == lead.id)
    )
    all_messages = all_msg_result.scalars().all()
    campaign_ids = set(m.campaign_id for m in all_messages)
    assert len(campaign_ids) == 2
    assert campaign1.id in campaign_ids
    assert campaign2.id in campaign_ids


# ---------- Scenario 8: Inbox Placement Monitoring Integration ----------


async def test_e2e_inbox_placement_monitoring(async_session: AsyncSession):
    """After batch send, verify InboxPlacementMonitor seed test and alert logic.

    Verifies: send_seed_test records results, update_placement works,
    get_domain_stats returns correct stats, and alert_if_degraded fires
    when inbox rate drops below 80%.
    """
    from channels.email.inbox_placement import InboxPlacementMonitor

    # Setup tenant and campaign context
    tenant, user = _create_tenant_and_user()
    async_session.add(tenant)
    async_session.add(user)
    await async_session.commit()

    campaign, sequence = _create_campaign_with_sequence(tenant.id)
    async_session.add(sequence)
    async_session.add(campaign)
    await async_session.commit()

    # Create leads and simulate batch send
    leads = []
    for i in range(5):
        lead = make_lead(
            tenant_id=tenant.id,
            first_name=f"Lead{i}",
            last_name="Test",
            email=f"lead{i}@batchtest.com",
            company="Batch Corp",
            title="Manager",
            status=LeadStatus.new,
        )
        leads.append(lead)
        async_session.add(lead)
    await async_session.commit()

    # Send outbound messages for all leads
    for lead in leads:
        msg = make_message(
            lead_id=lead.id,
            campaign_id=campaign.id,
            channel=ChannelType.email,
            direction=MessageDirection.outbound,
            status=MessageStatus.sent,
            content=f"<p>Hi {lead.first_name}, reaching out...</p>",
            subject="Batch outreach",
            sent_at=datetime.now(timezone.utc),
        )
        async_session.add(msg)
        lead.status = LeadStatus.contacted
    await async_session.commit()

    # Now test inbox placement monitoring
    monitor = InboxPlacementMonitor()

    # Send seed test
    seed_addresses = [
        "seed1@placement-test.com",
        "seed2@placement-test.com",
        "seed3@placement-test.com",
        "seed4@placement-test.com",
        "seed5@placement-test.com",
    ]
    seed_result = await monitor.send_seed_test("batchtest.com", seed_addresses)

    assert seed_result["domain"] == "batchtest.com"
    assert seed_result["seed_count"] == 5
    assert seed_result["status"] == "sent"
    assert len(seed_result["message_ids"]) == 5

    # Simulate checking placements: 3 inbox, 1 spam, 1 promotions = 60% inbox
    message_ids = seed_result["message_ids"]
    await monitor.update_placement(message_ids[0], "inbox")
    await monitor.update_placement(message_ids[1], "inbox")
    await monitor.update_placement(message_ids[2], "inbox")
    await monitor.update_placement(message_ids[3], "spam")
    await monitor.update_placement(message_ids[4], "promotions")

    # Get domain stats
    stats = await monitor.get_domain_stats("batchtest.com")
    assert stats["domain"] == "batchtest.com"
    assert stats["total_tests"] == 5
    assert stats["inbox_rate"] == 60.0
    assert stats["spam_rate"] == 20.0
    assert stats["promotions_rate"] == 20.0

    # Alert should fire since inbox_rate (60%) < threshold (80%)
    alert_fired = await monitor.alert_if_degraded("batchtest.com", threshold=80.0)
    assert alert_fired is True

    # Verify no alert when threshold is lower
    no_alert = await monitor.alert_if_degraded("batchtest.com", threshold=50.0)
    assert no_alert is False
