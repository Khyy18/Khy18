"""Shared test fixtures for the AI Outbound Agency test suite."""

import uuid
from datetime import datetime, timezone
from typing import Any, AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import JSON, event
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from core.models import (
    Base,
    Campaign,
    CampaignStatus,
    ChannelType,
    CostRecord,
    Event,
    EventType,
    Lead,
    LeadStatus,
    Message,
    MessageDirection,
    MessageStatus,
    Plan,
    PlanName,
    Sequence,
    Subscription,
    SubscriptionStatus,
    Tenant,
    User,
    UserRole,
    ABTest,
    ABTestAssignment,
    ABTestStatus,
    Call,
    CallScript,
    CallStatus,
    CallOutcome,
    VoiceAddon,
    VoiceAddonPlan,
    LeadInteraction,
    Webhook,
    WebhookDelivery,
)


@pytest.fixture
async def async_engine():
    """Create an async in-memory SQLite engine for testing.

    Maps PostgreSQL-specific types (JSONB, UUID) to SQLite-compatible types.
    """
    from sqlalchemy import String

    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
    )

    # SQLite does not enforce FK constraints by default; enable them.
    @event.listens_for(engine.sync_engine, "connect")
    def _set_sqlite_pragma(dbapi_conn, connection_record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    # Patch JSONB and UUID columns to work with SQLite before creating tables
    from sqlalchemy import Uuid, TypeDecorator, String as SAString
    import uuid as _uuid_mod

    class SQLiteUUID(TypeDecorator):
        """UUID type for SQLite that stores as string and accepts both UUID and str."""
        impl = SAString(36)
        cache_ok = True

        def process_bind_param(self, value, dialect):
            if value is None:
                return None
            if isinstance(value, _uuid_mod.UUID):
                return str(value)
            return str(value)

        def process_result_value(self, value, dialect):
            if value is None:
                return None
            if isinstance(value, _uuid_mod.UUID):
                return value
            return _uuid_mod.UUID(value)

    for table in Base.metadata.tables.values():
        for column in table.columns:
            if isinstance(column.type, JSONB):
                column.type = JSON()
            elif isinstance(column.type, PG_UUID):
                column.type = SQLiteUUID()

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.fixture
async def async_session(async_engine) -> AsyncGenerator[AsyncSession, None]:
    """Provide an async session bound to the in-memory SQLite engine."""
    session_factory = async_sessionmaker(
        async_engine, class_=AsyncSession, expire_on_commit=False
    )
    async with session_factory() as session:
        yield session


@pytest.fixture
def session_factory(async_engine) -> async_sessionmaker[AsyncSession]:
    """Return a session factory for code that needs async_sessionmaker."""
    return async_sessionmaker(
        async_engine, class_=AsyncSession, expire_on_commit=False
    )


@pytest.fixture
def mock_llm_client() -> AsyncMock:
    """Mock LLMClient that returns configurable responses."""
    client = AsyncMock()
    client.generate = AsyncMock(return_value="SUBJECT: Test Subject\nBODY: Test body content")
    return client


@pytest.fixture
def mock_email_sender() -> AsyncMock:
    """Mock AsyncEmailSender using AsyncMock."""
    sender = AsyncMock()
    sender.send_email = AsyncMock(
        return_value={"success": True, "domain_used": "example.com", "message_id_header": "<test@example.com>"}
    )
    return sender


@pytest.fixture
def mock_redis() -> AsyncMock:
    """Mock Redis client using AsyncMock with dict-based state."""
    redis = AsyncMock()
    store: dict[str, str] = {}

    async def mock_get(key):
        return store.get(key)

    async def mock_set(key, value, **kwargs):
        nx = kwargs.get("nx", False)
        if nx and key in store:
            return None  # Key already exists
        store[key] = str(value)
        return True

    async def mock_incr(key):
        current = int(store.get(key, "0"))
        store[key] = str(current + 1)
        return current + 1

    async def mock_delete(key):
        store.pop(key, None)
        return 1

    async def mock_setex(key, ttl, value):
        store[key] = str(value)
        return True

    async def mock_eval(script, num_keys, *args):
        # Simulate the Lua check-and-increment script
        key = args[0]
        limit = int(args[1])
        amount = int(args[2])
        current = int(store.get(key, "0"))
        if limit == -1 or current + amount <= limit:
            store[key] = str(current + amount)
            return 1
        return 0

    def _make_pipeline():
        pipe = MagicMock()
        pipe.incr = MagicMock(return_value=pipe)
        pipe.expire = MagicMock(return_value=pipe)
        pipe.execute = AsyncMock(return_value=[1, True])
        return pipe

    redis.get = AsyncMock(side_effect=mock_get)
    redis.set = AsyncMock(side_effect=mock_set)
    redis.incr = AsyncMock(side_effect=mock_incr)
    redis.delete = AsyncMock(side_effect=mock_delete)
    redis.setex = AsyncMock(side_effect=mock_setex)
    redis.eval = AsyncMock(side_effect=mock_eval)
    redis.expire = AsyncMock(return_value=True)
    redis.pipeline = MagicMock(return_value=_make_pipeline())
    redis.close = AsyncMock()
    redis._store = store  # Expose for test assertions

    return redis


@pytest.fixture
def mock_settings() -> MagicMock:
    """Mock Settings object with test values."""
    s = MagicMock()
    s.jwt_secret_key = "test-secret-key"
    s.jwt_algorithm = "HS256"
    s.redis_url = "redis://localhost:6379/0"
    s.openai_api_key = "test-openai-key"
    s.anthropic_api_key = "test-anthropic-key"
    s.tracking_base_url = "http://localhost:8000"
    s.tracking_secret = "test-tracking-secret"
    s.stripe_secret_key = "sk_test_123"
    s.stripe_webhook_secret = "whsec_test_123"
    s.slack_webhook_url = ""
    s.telegram_bot_token = ""
    s.telegram_chat_id = ""
    s.approval_required_company_size = 500
    s.metrics_auth_token = ""
    return s


# ---------- Factory Functions ----------

def make_tenant(**kwargs) -> Tenant:
    """Create a Tenant instance with defaults."""
    defaults = {
        "id": uuid.uuid4(),
        "name": "Test Corp",
        "domain": "testcorp.com",
        "settings": {},
        "created_at": datetime.now(timezone.utc),
    }
    defaults.update(kwargs)
    return Tenant(**defaults)


def make_user(tenant_id: uuid.UUID | None = None, **kwargs) -> User:
    """Create a User instance with defaults."""
    defaults = {
        "id": uuid.uuid4(),
        "tenant_id": tenant_id or uuid.uuid4(),
        "email": f"user-{uuid.uuid4().hex[:8]}@testcorp.com",
        "password_hash": "$2b$12$LJ3/xF5Zzv0P6yXZ0Z0Z0eXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX",
        "role": UserRole.admin,
        "created_at": datetime.now(timezone.utc),
    }
    defaults.update(kwargs)
    return User(**defaults)


def make_lead(tenant_id: uuid.UUID | None = None, **kwargs) -> Lead:
    """Create a Lead instance with defaults."""
    defaults = {
        "id": uuid.uuid4(),
        "tenant_id": tenant_id or uuid.uuid4(),
        "email": f"lead-{uuid.uuid4().hex[:8]}@example.com",
        "first_name": "John",
        "last_name": "Doe",
        "company": "Acme Inc",
        "title": "VP of Sales",
        "enrichment_data": {},
        "status": LeadStatus.new,
        "score": 0.0,
        "created_at": datetime.now(timezone.utc),
    }
    defaults.update(kwargs)
    return Lead(**defaults)


def make_campaign(tenant_id: uuid.UUID | None = None, **kwargs) -> Campaign:
    """Create a Campaign instance with defaults."""
    defaults = {
        "id": uuid.uuid4(),
        "tenant_id": tenant_id or uuid.uuid4(),
        "name": "Test Campaign",
        "icp_filter": {},
        "status": CampaignStatus.draft,
        "created_at": datetime.now(timezone.utc),
    }
    defaults.update(kwargs)
    return Campaign(**defaults)


def make_sequence(tenant_id: uuid.UUID | None = None, **kwargs) -> Sequence:
    """Create a Sequence instance with defaults."""
    defaults = {
        "id": uuid.uuid4(),
        "tenant_id": tenant_id or uuid.uuid4(),
        "name": "Test Sequence",
        "steps": [
            {"step_type": "initial", "delay_days": 0},
            {"step_type": "follow_up_1", "delay_days": 3},
            {"step_type": "follow_up_2", "delay_days": 5},
            {"step_type": "breakup", "delay_days": 7},
        ],
    }
    defaults.update(kwargs)
    return Sequence(**defaults)


def make_message(
    lead_id: uuid.UUID | None = None,
    campaign_id: uuid.UUID | None = None,
    **kwargs,
) -> Message:
    """Create a Message instance with defaults."""
    defaults = {
        "id": uuid.uuid4(),
        "lead_id": lead_id or uuid.uuid4(),
        "campaign_id": campaign_id or uuid.uuid4(),
        "channel": ChannelType.email,
        "direction": MessageDirection.outbound,
        "content": "Hello, this is a test message.",
        "subject": "Test Subject",
        "status": MessageStatus.sent,
        "sent_at": datetime.now(timezone.utc),
    }
    defaults.update(kwargs)
    return Message(**defaults)


def make_event(message_id: uuid.UUID | None = None, **kwargs) -> Event:
    """Create an Event instance with defaults."""
    defaults = {
        "id": uuid.uuid4(),
        "message_id": message_id or uuid.uuid4(),
        "event_type": EventType.open,
        "occurred_at": datetime.now(timezone.utc),
    }
    defaults.update(kwargs)
    return Event(**defaults)


def make_plan(**kwargs) -> Plan:
    """Create a Plan instance with defaults."""
    defaults = {
        "id": uuid.uuid4(),
        "name": PlanName.starter,
        "stripe_price_id": "price_test_123",
        "leads_limit": 500,
        "emails_limit": 1000,
        "linkedin_limit": 100,
        "campaigns_limit": 5,
        "domains_limit": 1,
        "voice_calls_limit": 0,
        "price_cents": 2900,
        "created_at": datetime.now(timezone.utc),
    }
    defaults.update(kwargs)
    return Plan(**defaults)


def make_subscription(
    tenant_id: uuid.UUID | None = None,
    plan_id: uuid.UUID | None = None,
    **kwargs,
) -> Subscription:
    """Create a Subscription instance with defaults."""
    defaults = {
        "id": uuid.uuid4(),
        "tenant_id": tenant_id or uuid.uuid4(),
        "plan_id": plan_id or uuid.uuid4(),
        "stripe_subscription_id": "sub_test_123",
        "stripe_customer_id": "cus_test_123",
        "status": SubscriptionStatus.active,
        "created_at": datetime.now(timezone.utc),
    }
    defaults.update(kwargs)
    return Subscription(**defaults)


def make_call(
    tenant_id: uuid.UUID | None = None,
    lead_id: uuid.UUID | None = None,
    **kwargs,
) -> Call:
    """Create a Call instance with defaults."""
    defaults = {
        "id": uuid.uuid4(),
        "tenant_id": tenant_id or uuid.uuid4(),
        "lead_id": lead_id or uuid.uuid4(),
        "twilio_sid": f"CA{uuid.uuid4().hex[:32]}",
        "status": CallStatus.initiated,
        "started_at": datetime.now(timezone.utc),
        "created_at": datetime.now(timezone.utc),
    }
    defaults.update(kwargs)
    return Call(**defaults)


def make_call_script(
    tenant_id: uuid.UUID | None = None,
    **kwargs,
) -> CallScript:
    """Create a CallScript instance with defaults."""
    defaults = {
        "id": uuid.uuid4(),
        "tenant_id": tenant_id or uuid.uuid4(),
        "name": "Test Script",
        "script_json": {"greeting_template": "Hello!", "topics": ["product demo"]},
        "voice_id": "default",
        "language": "en",
        "created_at": datetime.now(timezone.utc),
    }
    defaults.update(kwargs)
    return CallScript(**defaults)


def make_voice_addon(
    tenant_id: uuid.UUID | None = None,
    **kwargs,
) -> VoiceAddon:
    """Create a VoiceAddon instance with defaults."""
    defaults = {
        "id": uuid.uuid4(),
        "tenant_id": tenant_id or uuid.uuid4(),
        "plan_name": VoiceAddonPlan.voice_starter,
        "stripe_subscription_id": "sub_voice_test_123",
        "calls_limit": 50,
        "calls_used_this_period": 0,
        "overage_rate_cents": 50,
        "period_start": datetime.now(timezone.utc),
        "period_end": None,
        "is_active": True,
        "created_at": datetime.now(timezone.utc),
    }
    defaults.update(kwargs)
    return VoiceAddon(**defaults)


def make_lead_interaction(
    lead_id: uuid.UUID | None = None,
    tenant_id: uuid.UUID | None = None,
    **kwargs,
) -> LeadInteraction:
    """Create a LeadInteraction instance with defaults."""
    defaults = {
        "id": uuid.uuid4(),
        "lead_id": lead_id or uuid.uuid4(),
        "tenant_id": tenant_id or uuid.uuid4(),
        "interaction_type": "call",
        "channel": "voice",
        "summary": "Test interaction summary",
        "context_json": {},
        "created_at": datetime.now(timezone.utc),
    }
    defaults.update(kwargs)
    return LeadInteraction(**defaults)
