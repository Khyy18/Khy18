"""Idempotent demo data seed script.

Creates demo tenant, user, campaigns, leads, messages, calls, and events.
Checks for existing 'Demo Corp' tenant before creating to ensure idempotency.

Usage:
    DATABASE_URL=sqlite+aiosqlite:///demo.db python scripts/seed_demo.py
"""

import asyncio
import os
import random
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.models import (
    Base,
    Call,
    CallOutcome,
    CallStatus,
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
    User,
    UserRole,
)
from dashboard.auth import hash_password


DATABASE_URL = os.environ.get(
    "DATABASE_URL", "sqlite+aiosqlite:///demo.db"
)

DEMO_TENANT_NAME = "Demo Corp"
DEMO_USER_EMAIL = "demo@example.com"
DEMO_USER_PASSWORD = "demo123"

COMPANIES = [
    "Acme Corp",
    "TechFlow Inc",
    "DataPipe Solutions",
    "CloudScale AI",
    "NetVault Systems",
    "CyberPulse",
    "Quantum Dynamics",
    "SkyBridge Labs",
    "NovaStar Tech",
    "BlueShift Analytics",
]

TITLES = [
    "VP of Sales",
    "Head of Marketing",
    "CTO",
    "Director of Engineering",
    "CEO",
    "Head of Growth",
    "VP of Business Development",
    "Chief Revenue Officer",
    "Director of Operations",
    "VP of Product",
]

FIRST_NAMES = [
    "James", "Sarah", "Michael", "Emily", "David",
    "Jessica", "Robert", "Amanda", "William", "Rachel",
    "Daniel", "Laura", "Thomas", "Nicole", "Christopher",
    "Olivia", "Andrew", "Sophia", "Matthew", "Victoria",
]

LAST_NAMES = [
    "Johnson", "Williams", "Brown", "Jones", "Davis",
    "Miller", "Wilson", "Moore", "Taylor", "Anderson",
    "Thomas", "Jackson", "White", "Harris", "Martin",
    "Thompson", "Garcia", "Martinez", "Robinson", "Clark",
]

LEAD_STATUSES = list(LeadStatus)
MESSAGE_SUBJECTS = [
    "Quick question about your growth plans",
    "Thought you might find this interesting",
    "Following up on our conversation",
    "A tool that could help your team",
    "Congrats on the recent funding round",
]

CALL_TRANSCRIPTS = [
    "Agent: Hi, this is Alex from AI Outbound Agency. Is this a good time?\n"
    "Lead: Sure, I have a few minutes.\n"
    "Agent: Great. I noticed your team is scaling the sales org. We help companies automate outbound...\n"
    "Lead: That sounds interesting. Can you send me more details?\n"
    "Agent: Absolutely. I will send a follow-up email with a case study.",
    "Agent: Good morning. I am reaching out from AI Outbound Agency.\n"
    "Lead: Sorry, not interested right now.\n"
    "Agent: No problem. Would it be okay if I followed up in a month?\n"
    "Lead: Sure, that works.",
    "Agent: Hi there. I wanted to discuss how AI can help your sales pipeline.\n"
    "Lead: We are actually looking into solutions like this.\n"
    "Agent: Perfect timing. Would you be open to a 15-minute demo this week?\n"
    "Lead: Yes, how about Thursday at 2pm?\n"
    "Agent: That works. I will send a calendar invite.",
    "Agent: Hello, calling from AI Outbound Agency regarding sales automation.\n"
    "[Voicemail detected]\n"
    "Agent: Hi, this is Alex. I was calling about helping scale your outbound. "
    "I will follow up via email. Have a great day.",
    "Agent: Hi, is this the right number for the sales team?\n"
    "Lead: Yes, what is this about?\n"
    "Agent: We help companies like yours book more meetings using AI. "
    "Are you currently doing outbound?\n"
    "Lead: We have an SDR team but results have been declining.\n"
    "Agent: That is exactly the problem we solve. Can we schedule a quick call with your VP?",
]


async def seed_demo_data(session: AsyncSession) -> dict:
    """Create demo data. Returns summary of created objects.

    Idempotent: checks if Demo Corp tenant already exists.
    """
    # Check if tenant already exists
    result = await session.execute(
        select(Tenant).where(Tenant.name == DEMO_TENANT_NAME)
    )
    existing = result.scalar_one_or_none()
    if existing is not None:
        return {"status": "skipped", "reason": "Demo Corp tenant already exists"}

    # Create tenant
    tenant = Tenant(
        id=uuid.uuid4(),
        name=DEMO_TENANT_NAME,
        domain="democorp.com",
        settings={"timezone": "America/New_York"},
    )
    session.add(tenant)
    await session.flush()

    # Create user
    user = User(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        email=DEMO_USER_EMAIL,
        password_hash=hash_password(DEMO_USER_PASSWORD),
        role=UserRole.admin,
    )
    session.add(user)
    await session.flush()

    # Create campaigns
    campaigns_data = [
        ("Cold Email Blast", CampaignStatus.active),
        ("LinkedIn Outreach", CampaignStatus.active),
        ("Voice Campaign", CampaignStatus.draft),
    ]
    campaigns = []
    for name, status in campaigns_data:
        campaign = Campaign(
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            name=name,
            icp_filter={"industry": "technology", "company_size": "50-500"},
            status=status,
            created_at=datetime.now(timezone.utc) - timedelta(days=random.randint(1, 30)),
        )
        session.add(campaign)
        campaigns.append(campaign)
    await session.flush()

    # Create 50 leads
    leads = []
    for i in range(50):
        first_name = FIRST_NAMES[i % len(FIRST_NAMES)]
        last_name = LAST_NAMES[i % len(LAST_NAMES)]
        company = COMPANIES[i % len(COMPANIES)]
        lead = Lead(
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            email=f"{first_name.lower()}.{last_name.lower()}{i}@{company.lower().replace(' ', '')}.com",
            first_name=first_name,
            last_name=last_name,
            company=company,
            title=TITLES[i % len(TITLES)],
            status=LEAD_STATUSES[i % len(LEAD_STATUSES)],
            score=round(random.uniform(0.1, 0.95), 2),
            enrichment_data={
                "linkedin_connections": random.randint(100, 5000),
                "company_size": random.choice(["10-50", "50-200", "200-1000"]),
            },
            created_at=datetime.now(timezone.utc) - timedelta(days=random.randint(1, 60)),
        )
        session.add(lead)
        leads.append(lead)
    await session.flush()

    # Create 20 messages
    messages = []
    for i in range(20):
        lead = leads[i % len(leads)]
        campaign = campaigns[i % len(campaigns)]
        channel = ChannelType.email if i % 3 != 2 else ChannelType.linkedin
        msg = Message(
            id=uuid.uuid4(),
            lead_id=lead.id,
            campaign_id=campaign.id,
            channel=channel,
            direction=MessageDirection.outbound,
            content=f"Hi {lead.first_name}, I noticed your team at {lead.company} is growing. "
                    f"We help similar companies automate their outbound sales pipeline.",
            subject=MESSAGE_SUBJECTS[i % len(MESSAGE_SUBJECTS)],
            status=random.choice([MessageStatus.sent, MessageStatus.opened, MessageStatus.replied]),
            sent_at=datetime.now(timezone.utc) - timedelta(days=random.randint(1, 14)),
        )
        session.add(msg)
        messages.append(msg)
    await session.flush()

    # Create events for some messages
    events_created = 0
    for msg in messages[:10]:
        event_types = [EventType.open]
        if random.random() > 0.5:
            event_types.append(EventType.click)
        if random.random() > 0.7:
            event_types.append(EventType.reply)
        for et in event_types:
            event = Event(
                id=uuid.uuid4(),
                message_id=msg.id,
                event_type=et,
                occurred_at=msg.sent_at + timedelta(hours=random.randint(1, 48)),
                meta={},
            )
            session.add(event)
            events_created += 1
    await session.flush()

    # Create 5 calls
    call_outcomes = [
        CallOutcome.qualified,
        CallOutcome.not_interested,
        CallOutcome.voicemail,
        CallOutcome.no_answer,
        CallOutcome.qualified,
    ]
    calls_created = []
    for i in range(5):
        lead = leads[i]
        call = Call(
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            lead_id=lead.id,
            campaign_id=campaigns[2].id,
            status=CallStatus.completed,
            duration_seconds=random.randint(30, 300),
            started_at=datetime.now(timezone.utc) - timedelta(days=random.randint(1, 7)),
            ended_at=datetime.now(timezone.utc) - timedelta(days=random.randint(0, 6)),
            transcript=CALL_TRANSCRIPTS[i],
            outcome=call_outcomes[i],
            cost_cents=random.randint(5, 50),
        )
        session.add(call)
        calls_created.append(call)
    await session.flush()

    await session.commit()

    return {
        "status": "created",
        "tenant": DEMO_TENANT_NAME,
        "user": DEMO_USER_EMAIL,
        "campaigns": len(campaigns),
        "leads": len(leads),
        "messages": len(messages),
        "events": events_created,
        "calls": len(calls_created),
    }


async def run_seed() -> dict:
    """Main entry point for seeding demo data."""
    engine = create_async_engine(DATABASE_URL, echo=False)

    # Create tables if they don't exist (for SQLite)
    if "sqlite" in DATABASE_URL:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with session_factory() as session:
        result = await seed_demo_data(session)

    await engine.dispose()
    return result


if __name__ == "__main__":
    result = asyncio.run(run_seed())
    print(f"Seed result: {result}")
