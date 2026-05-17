"""Tests for code review fixes: cross-tenant events, CRM since filter, ML deterministic hash, warmup TTL, Redis reuse."""
from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from core.models import (
    ApiKey,
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


# ---------- Fix 1: Events endpoint cross-tenant isolation ----------


@pytest.fixture
async def events_app(async_engine):
    """Create a FastAPI app with test database override for integrations routes."""
    from fastapi import FastAPI
    from dashboard.routes.integrations_api import router as api_router, get_api_key_tenant
    import dashboard.routes.integrations_api as integrations_module

    app = FastAPI()
    app.include_router(api_router)

    session_factory = async_sessionmaker(
        async_engine, class_=AsyncSession, expire_on_commit=False
    )

    async def override_get_session():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[integrations_module._get_session] = override_get_session

    return app, session_factory


@pytest.mark.asyncio
async def test_events_endpoint_filters_by_tenant(events_app):
    """GET /api/v1/events only returns events for the authenticated tenant."""
    from dashboard.routes.integrations_api import get_api_key_tenant

    app, session_factory = events_app

    tenant1_id = uuid.uuid4()
    tenant2_id = uuid.uuid4()

    async with session_factory() as session:
        # Create two tenants
        tenant1 = Tenant(
            id=tenant1_id, name="Tenant 1", domain="t1.com",
            created_at=datetime.now(timezone.utc),
        )
        tenant2 = Tenant(
            id=tenant2_id, name="Tenant 2", domain="t2.com",
            created_at=datetime.now(timezone.utc),
        )
        session.add_all([tenant1, tenant2])
        await session.flush()

        # Create a lead and campaign for each tenant
        lead1 = Lead(
            id=uuid.uuid4(), tenant_id=tenant1_id, email="lead1@t1.com",
            first_name="A", last_name="B", company="C1", title="VP",
            status=LeadStatus.new, created_at=datetime.now(timezone.utc),
        )
        lead2 = Lead(
            id=uuid.uuid4(), tenant_id=tenant2_id, email="lead2@t2.com",
            first_name="D", last_name="E", company="C2", title="CTO",
            status=LeadStatus.new, created_at=datetime.now(timezone.utc),
        )
        campaign1 = Campaign(
            id=uuid.uuid4(), tenant_id=tenant1_id, name="Camp1",
            status=CampaignStatus.active, created_at=datetime.now(timezone.utc),
        )
        campaign2 = Campaign(
            id=uuid.uuid4(), tenant_id=tenant2_id, name="Camp2",
            status=CampaignStatus.active, created_at=datetime.now(timezone.utc),
        )
        session.add_all([lead1, lead2, campaign1, campaign2])
        await session.flush()

        # Create messages
        msg1 = Message(
            id=uuid.uuid4(), lead_id=lead1.id, campaign_id=campaign1.id,
            channel=ChannelType.email, direction=MessageDirection.outbound,
            content="msg1", status=MessageStatus.sent,
            sent_at=datetime.now(timezone.utc),
        )
        msg2 = Message(
            id=uuid.uuid4(), lead_id=lead2.id, campaign_id=campaign2.id,
            channel=ChannelType.email, direction=MessageDirection.outbound,
            content="msg2", status=MessageStatus.sent,
            sent_at=datetime.now(timezone.utc),
        )
        session.add_all([msg1, msg2])
        await session.flush()

        # Create events
        event1 = Event(
            id=uuid.uuid4(), message_id=msg1.id, event_type=EventType.open,
            occurred_at=datetime.now(timezone.utc),
        )
        event2 = Event(
            id=uuid.uuid4(), message_id=msg2.id, event_type=EventType.click,
            occurred_at=datetime.now(timezone.utc),
        )
        session.add_all([event1, event2])
        await session.commit()

    # Override auth to return tenant1
    async def override_api_key_tenant():
        return tenant1

    app.dependency_overrides[get_api_key_tenant] = override_api_key_tenant

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get(
            "/api/v1/events",
            headers={"X-API-Key": "test-key"},
        )
        assert resp.status_code == 200
        data = resp.json()

        # Should only see tenant1's event
        assert len(data["events"]) == 1
        assert data["events"][0]["event_type"] == "open"


@pytest.mark.asyncio
async def test_events_endpoint_no_events_for_other_tenant(events_app):
    """Tenant with no events gets empty list."""
    from dashboard.routes.integrations_api import get_api_key_tenant

    app, session_factory = events_app

    tenant_id = uuid.uuid4()
    async with session_factory() as session:
        tenant = Tenant(
            id=tenant_id, name="Empty Tenant", domain="empty.com",
            created_at=datetime.now(timezone.utc),
        )
        session.add(tenant)
        await session.commit()

    async def override_api_key_tenant():
        return tenant

    app.dependency_overrides[get_api_key_tenant] = override_api_key_tenant

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get(
            "/api/v1/events",
            headers={"X-API-Key": "test-key"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["events"] == []


# ---------- Fix 4: HubSpot sync_from_crm passes since parameter ----------


@pytest.mark.asyncio
async def test_hubspot_sync_passes_since_filter():
    """HubSpot sync_from_crm passes filterGroups when since is provided."""
    from integrations.crm_sync import HubSpotAdapter

    adapter = HubSpotAdapter(api_key="test-key", base_url="http://fake-hubspot")

    with patch("integrations.crm_sync.httpx.AsyncClient") as mock_client_cls:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"results": [{"id": "1", "properties": {}}]}

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client_cls.return_value = mock_client

        since_ts = "2024-01-01T00:00:00Z"
        results = await adapter.sync_from_crm(since=since_ts)

        # Verify the params passed to client.get include filterGroups
        call_kwargs = mock_client.get.call_args[1]
        params = call_kwargs["params"]
        assert "filterGroups" in params
        assert params["limit"] == 100


@pytest.mark.asyncio
async def test_hubspot_sync_without_since():
    """HubSpot sync_from_crm without since only passes limit."""
    from integrations.crm_sync import HubSpotAdapter

    adapter = HubSpotAdapter(api_key="test-key", base_url="http://fake-hubspot")

    with patch("integrations.crm_sync.httpx.AsyncClient") as mock_client_cls:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"results": []}

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client_cls.return_value = mock_client

        results = await adapter.sync_from_crm(since=None)

        # Verify the params passed to client.get only have limit
        call_kwargs = mock_client.get.call_args[1]
        params = call_kwargs["params"]
        assert params == {"limit": 100}
        assert "filterGroups" not in params


# ---------- Fix 5: ML industry encoding is deterministic ----------


class TestMLDeterministicIndustryEncoding:
    """Test that ML industry encoding is deterministic across calls."""

    def test_industry_encoding_deterministic(self):
        """Same industry always produces the same encoded value."""
        from agents.ml_scorer import MLLeadScorer

        scorer = MLLeadScorer(model_path="/tmp/nonexistent.joblib")

        features1 = {"industry": "technology", "company_size_bucket": "medium"}
        features2 = {"industry": "technology", "company_size_bucket": "medium"}

        arr1 = scorer._features_to_array(features1)
        arr2 = scorer._features_to_array(features2)

        # Industry value (index 1) should be identical
        assert arr1[0][1] == arr2[0][1]

    def test_industry_encoding_consistent_across_invocations(self):
        """Industry encoding uses hashlib, producing same value every time."""
        from agents.ml_scorer import MLLeadScorer

        scorer1 = MLLeadScorer(model_path="/tmp/nonexistent1.joblib")
        scorer2 = MLLeadScorer(model_path="/tmp/nonexistent2.joblib")

        features = {"industry": "healthcare", "company_size_bucket": "large"}

        arr1 = scorer1._features_to_array(features)
        arr2 = scorer2._features_to_array(features)

        assert arr1[0][1] == arr2[0][1]

    def test_industry_encoding_uses_hashlib(self):
        """Verify the encoding matches our expected hashlib formula."""
        from agents.ml_scorer import MLLeadScorer

        scorer = MLLeadScorer(model_path="/tmp/nonexistent.joblib")

        industry = "finance"
        expected = int(hashlib.md5(industry.encode()).hexdigest()[:8], 16) % 1000 / 1000.0

        features = {"industry": industry, "company_size_bucket": "small"}
        arr = scorer._features_to_array(features)

        assert arr[0][1] == expected

    def test_different_industries_produce_different_values(self):
        """Different industries produce different encoded values."""
        from agents.ml_scorer import MLLeadScorer

        scorer = MLLeadScorer(model_path="/tmp/nonexistent.joblib")

        features_tech = {"industry": "technology", "company_size_bucket": "medium"}
        features_health = {"industry": "healthcare", "company_size_bucket": "medium"}

        arr_tech = scorer._features_to_array(features_tech)
        arr_health = scorer._features_to_array(features_health)

        assert arr_tech[0][1] != arr_health[0][1]


# ---------- Fix 3: Warmup Redis keys have TTL ----------


@pytest.mark.asyncio
async def test_record_send_sets_ttl(mock_redis):
    """record_send sets expire on Redis keys."""
    from channels.email.warmup_network import WarmupNetwork

    with patch("channels.email.warmup_network.aioredis") as mock_aioredis:
        mock_aioredis.from_url.return_value = mock_redis
        network = WarmupNetwork(
            redis_url="redis://localhost:6379/0",
            session_factory=MagicMock(),
        )
        network._redis = mock_redis

    mock_redis.hset = AsyncMock(return_value=True)
    mock_redis.incr = AsyncMock(return_value=1)
    mock_redis.expire = AsyncMock(return_value=True)

    await network.record_send("test.com", "msg-123", "info@test.com", "hello@other.com")

    # Verify expire was called with 48h TTL (172800 seconds)
    expire_calls = mock_redis.expire.call_args_list
    assert len(expire_calls) >= 2  # At least for sends_key and msg_key

    # Check TTL values are 172800 (48 hours)
    for call in expire_calls:
        assert call[0][1] == 172800


@pytest.mark.asyncio
async def test_record_send_uses_date_partitioned_keys(mock_redis):
    """record_send uses date-partitioned keys (e.g., sends:2024-01-01)."""
    from channels.email.warmup_network import WarmupNetwork

    with patch("channels.email.warmup_network.aioredis") as mock_aioredis:
        mock_aioredis.from_url.return_value = mock_redis
        network = WarmupNetwork(
            redis_url="redis://localhost:6379/0",
            session_factory=MagicMock(),
        )
        network._redis = mock_redis

    mock_redis.hset = AsyncMock(return_value=True)
    mock_redis.incr = AsyncMock(return_value=1)
    mock_redis.expire = AsyncMock(return_value=True)

    await network.record_send("test.com", "msg-456", "a@test.com", "b@other.com")

    # Check that incr was called with a date-partitioned key
    incr_call = mock_redis.incr.call_args_list[0]
    key = incr_call[0][0]
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    assert f"warmup_network:test.com:sends:{today}" == key


# ---------- Fix 6: Redis connection reuse in rate limiter ----------


def test_rate_limit_redis_module_level():
    """Verify _get_rate_limit_redis and _rate_limit_redis exist as module-level."""
    from dashboard.routes import integrations_api

    assert hasattr(integrations_api, "_rate_limit_redis")
    assert hasattr(integrations_api, "_get_rate_limit_redis")


@pytest.mark.asyncio
async def test_rate_limit_redis_reuses_connection():
    """_get_rate_limit_redis returns the same instance on repeated calls."""
    import dashboard.routes.integrations_api as module

    # Reset module state
    original = module._rate_limit_redis
    module._rate_limit_redis = None

    try:
        mock_instance = AsyncMock()

        with patch.dict("sys.modules", {"redis.asyncio": MagicMock(from_url=MagicMock(return_value=mock_instance))}):
            with patch("core.config.settings") as mock_settings:
                mock_settings.redis_url = "redis://localhost:6379/0"

                # Reload to pick up the mocked module
                # Instead, just directly set the global and call
                module._rate_limit_redis = None

                # Simulate what _get_rate_limit_redis does
                import redis.asyncio as aioredis_mod
                with patch("redis.asyncio.from_url", return_value=mock_instance):
                    # First call should create
                    result1 = await module._get_rate_limit_redis()
                    # Second call should reuse
                    result2 = await module._get_rate_limit_redis()

                    assert result1 is result2
    finally:
        module._rate_limit_redis = original


# ---------- Fix 2: Alembic migration exists ----------


def test_alembic_migration_006_exists():
    """Migration 006_add_phase2_tables.py exists and has correct structure."""
    import os

    migration_path = os.path.join(
        os.path.dirname(__file__), "..", "alembic", "versions", "006_add_phase2_tables.py"
    )
    assert os.path.exists(migration_path), "Migration 006 file should exist"

    with open(migration_path) as f:
        content = f.read()

    # Verify revision chain
    assert 'revision: str = "006"' in content
    assert 'down_revision: Union[str, None] = "005"' in content

    # Verify it creates the right tables
    assert "api_keys" in content
    assert "webhooks" in content
    assert "brand_settings" in content

    # Verify upgrade and downgrade functions exist
    assert "def upgrade() -> None:" in content
    assert "def downgrade() -> None:" in content
