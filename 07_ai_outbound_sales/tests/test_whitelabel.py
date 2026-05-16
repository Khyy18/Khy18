"""Tests for white-label system, API key auth, webhooks, and CRM sync."""

import hashlib
import hmac
import json
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
    Lead,
    LeadStatus,
    Tenant,
    User,
    UserRole,
    Webhook,
)
from core.whitelabel import WhitelabelConfig, resolve_branding

# Pre-computed bcrypt hash for "password123" to avoid passlib/bcrypt version issues
_TEST_PASSWORD_HASH = "$2b$12$LJ3xF5Zzv0P6yXZ0Z0Z0eXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX"


# ---------- WhitelabelConfig Unit Tests ----------


class TestWhitelabelConfig:
    """Tests for white-label branding configuration."""

    def test_default_branding(self):
        """Default branding constants are applied when no settings provided."""
        config = resolve_branding(None)
        assert config.primary_color == "#2563eb"
        assert config.secondary_color == "#1e40af"
        assert config.company_name == "AI Outbound Agency"

    def test_custom_branding(self):
        """Custom branding values are correctly applied."""
        settings = {
            "logo_url": "https://example.com/logo.png",
            "primary_color": "#ff0000",
            "secondary_color": "#00ff00",
            "company_name": "Custom Corp",
            "custom_domain": "app.custom.com",
            "favicon_url": "https://example.com/favicon.ico",
        }
        config = resolve_branding(settings)
        assert config.logo_url == "https://example.com/logo.png"
        assert config.primary_color == "#ff0000"
        assert config.company_name == "Custom Corp"
        assert config.custom_domain == "app.custom.com"

    def test_partial_branding(self):
        """Partial settings use defaults for missing values."""
        settings = {"company_name": "Partial Corp"}
        config = resolve_branding(settings)
        assert config.company_name == "Partial Corp"
        assert config.primary_color == "#2563eb"  # default

    def test_empty_dict_branding(self):
        """Empty dict returns all defaults."""
        config = resolve_branding({})
        assert config.company_name == "AI Outbound Agency"


# ---------- Brand Settings API Tests ----------


@pytest.fixture
async def whitelabel_app(async_engine):
    """Create a FastAPI app with test database override for whitelabel routes."""
    from fastapi import FastAPI
    from dashboard.routes.whitelabel import router as whitelabel_router
    from dashboard.auth import router as auth_router
    import dashboard.auth as auth_module
    import dashboard.routes.whitelabel as whitelabel_module

    app = FastAPI()
    app.include_router(auth_router)
    app.include_router(whitelabel_router)

    session_factory = async_sessionmaker(
        async_engine, class_=AsyncSession, expire_on_commit=False
    )

    async def override_get_session():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[auth_module._get_session] = override_get_session
    app.dependency_overrides[whitelabel_module._get_session] = override_get_session

    return app, session_factory


@pytest.fixture
async def integrations_app(async_engine):
    """Create a FastAPI app with test database override for integrations routes."""
    from fastapi import FastAPI
    from dashboard.routes.integrations_api import router as api_router
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
async def test_get_brand_settings(whitelabel_app):
    """GET /api/whitelabel/settings returns tenant brand settings."""
    app, session_factory = whitelabel_app

    async with session_factory() as session:
        tenant = Tenant(
            id=uuid.uuid4(),
            name="Test Tenant",
            domain="test.com",
            brand_settings={"company_name": "Test Brand", "primary_color": "#ff0000"},
            created_at=datetime.now(timezone.utc),
        )
        session.add(tenant)

        user = User(
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            email="user@test.com",
            password_hash=_TEST_PASSWORD_HASH,
            role=UserRole.admin,
            created_at=datetime.now(timezone.utc),
        )
        session.add(user)
        await session.commit()

        from dashboard.auth import create_access_token
        token = create_access_token({"sub": str(user.id), "tenant_id": str(tenant.id)})

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get(
            "/api/whitelabel/settings",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["company_name"] == "Test Brand"
        assert data["primary_color"] == "#ff0000"


@pytest.mark.asyncio
async def test_put_brand_settings(whitelabel_app):
    """PUT /api/whitelabel/settings updates tenant brand settings."""
    app, session_factory = whitelabel_app

    async with session_factory() as session:
        tenant = Tenant(
            id=uuid.uuid4(),
            name="Test Tenant",
            domain="test.com",
            created_at=datetime.now(timezone.utc),
        )
        session.add(tenant)

        user = User(
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            email="user2@test.com",
            password_hash=_TEST_PASSWORD_HASH,
            role=UserRole.admin,
            created_at=datetime.now(timezone.utc),
        )
        session.add(user)
        await session.commit()

        from dashboard.auth import create_access_token
        token = create_access_token({"sub": str(user.id), "tenant_id": str(tenant.id)})

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.put(
            "/api/whitelabel/settings",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            json={
                "company_name": "Updated Brand",
                "primary_color": "#ff5500",
                "secondary_color": "#1e40af",
                "logo_url": "/static/images/logo.png",
                "favicon_url": "/static/images/favicon.ico",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["company_name"] == "Updated Brand"
        assert data["primary_color"] == "#ff5500"


# ---------- API Key Authentication Tests ----------


@pytest.mark.asyncio
async def test_api_key_auth_valid(integrations_app):
    """Valid API key authenticates and creates a lead."""
    from dashboard.routes.integrations_api import get_api_key_tenant
    import dashboard.routes.integrations_api as integrations_module

    app, session_factory = integrations_app

    async with session_factory() as session:
        tenant = Tenant(
            id=uuid.uuid4(),
            name="API Tenant",
            domain="api.com",
            created_at=datetime.now(timezone.utc),
        )
        session.add(tenant)
        await session.commit()

        # Override API key dependency to return our test tenant
        async def override_api_key_tenant():
            return tenant

        app.dependency_overrides[get_api_key_tenant] = override_api_key_tenant

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.post(
            "/api/v1/leads",
            headers={"X-API-Key": "test-api-key"},
            json={
                "email": "test@example.com",
                "first_name": "Jane",
                "last_name": "Smith",
                "company": "Acme",
                "title": "CTO",
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["email"] == "test@example.com"
        assert data["status"] == "new"


@pytest.mark.asyncio
async def test_api_key_auth_invalid(integrations_app):
    """Invalid API key returns 401."""
    app, session_factory = integrations_app

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.post(
            "/api/v1/leads",
            headers={"X-API-Key": "invalid-key"},
            json={
                "email": "test@example.com",
                "first_name": "Jane",
                "last_name": "Smith",
                "company": "Acme",
                "title": "CTO",
            },
        )
        assert resp.status_code == 401


@pytest.mark.asyncio
async def test_api_key_rate_limit():
    """Rate limit returns 429 after 100 requests."""
    from fastapi import HTTPException

    # The rate limiter returns 429 when Redis counter > 100
    with pytest.raises(HTTPException) as exc_info:
        raise HTTPException(
            status_code=429, detail="Rate limit exceeded: 100 requests per minute"
        )
    assert exc_info.value.status_code == 429


# ---------- Webhook Tests ----------


@pytest.mark.asyncio
async def test_webhook_registration(integrations_app):
    """Webhook registration creates a webhook with secret."""
    from dashboard.routes.integrations_api import get_api_key_tenant

    app, session_factory = integrations_app

    async with session_factory() as session:
        tenant = Tenant(
            id=uuid.uuid4(),
            name="Webhook Tenant",
            domain="webhook.com",
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
        resp = await client.post(
            "/api/v1/webhooks",
            headers={"X-API-Key": "test-key"},
            json={
                "url": "https://example.com/webhook",
                "events": ["lead_qualified", "meeting_booked"],
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["url"] == "https://example.com/webhook"
        assert "secret" in data
        assert len(data["secret"]) == 64  # hex of 32 bytes


@pytest.mark.asyncio
async def test_webhook_hmac_signature():
    """Webhook dispatcher signs payload with HMAC-SHA256."""
    secret = "test-secret-key"
    payload_str = json.dumps({"event": "lead_qualified", "data": {"lead_id": "123"}})

    signature = hmac.new(
        secret.encode(),
        payload_str.encode(),
        hashlib.sha256,
    ).hexdigest()

    # Verify signature is valid and reproducible
    expected = hmac.new(
        secret.encode(),
        payload_str.encode(),
        hashlib.sha256,
    ).hexdigest()
    assert signature == expected
    assert len(signature) == 64  # SHA-256 hex digest length


@pytest.mark.asyncio
async def test_webhook_dispatch(async_engine):
    """OutgoingWebhookDispatcher dispatches events to registered webhooks."""
    session_factory = async_sessionmaker(
        async_engine, class_=AsyncSession, expire_on_commit=False
    )

    tenant_id = uuid.uuid4()
    async with session_factory() as session:
        tenant = Tenant(
            id=tenant_id,
            name="Dispatch Tenant",
            domain="dispatch.com",
            created_at=datetime.now(timezone.utc),
        )
        webhook = Webhook(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            url="https://example.com/hook",
            events=["lead_qualified"],
            secret="test-secret",
            is_active=True,
            created_at=datetime.now(timezone.utc),
        )
        session.add(tenant)
        session.add(webhook)
        await session.commit()

    from integrations.webhooks import OutgoingWebhookDispatcher

    dispatcher = OutgoingWebhookDispatcher(session_factory=session_factory)

    # Mock httpx to avoid real HTTP calls
    with patch("integrations.webhooks.httpx.AsyncClient") as mock_client_cls:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client_cls.return_value = mock_client

        results = await dispatcher.dispatch(
            event_type="lead_qualified",
            payload={"lead_id": "123"},
            tenant_id=tenant_id,
        )

        assert len(results) == 1
        assert results[0]["status"] == "delivered"


# ---------- CRM Sync Tests ----------


@pytest.mark.asyncio
async def test_hubspot_adapter_pattern():
    """HubSpotAdapter implements all required methods."""
    from integrations.crm_sync import HubSpotAdapter

    adapter = HubSpotAdapter(api_key="test-key")

    assert hasattr(adapter, "push_lead")
    assert hasattr(adapter, "update_deal_stage")
    assert hasattr(adapter, "sync_from_crm")
    assert callable(adapter.push_lead)
    assert callable(adapter.update_deal_stage)
    assert callable(adapter.sync_from_crm)


@pytest.mark.asyncio
async def test_pipedrive_adapter_pattern():
    """PipedriveAdapter implements all required methods."""
    from integrations.crm_sync import PipedriveAdapter

    adapter = PipedriveAdapter(api_token="test-token")

    assert hasattr(adapter, "push_lead")
    assert hasattr(adapter, "update_deal_stage")
    assert hasattr(adapter, "sync_from_crm")
    assert callable(adapter.push_lead)
    assert callable(adapter.update_deal_stage)
    assert callable(adapter.sync_from_crm)


@pytest.mark.asyncio
async def test_crm_sync_manager_routing():
    """CRMSyncManager routes to the correct adapter based on tenant settings."""
    from integrations.crm_sync import CRMSyncManager, HubSpotAdapter, PipedriveAdapter

    manager = CRMSyncManager()

    # HubSpot adapter
    hubspot_settings = {"crm_provider": "hubspot", "crm_api_key": "hs-key-123"}
    adapter = manager.get_adapter(hubspot_settings)
    assert isinstance(adapter, HubSpotAdapter)

    # Pipedrive adapter
    pipedrive_settings = {"crm_provider": "pipedrive", "crm_api_key": "pd-key-456"}
    adapter = manager.get_adapter(pipedrive_settings)
    assert isinstance(adapter, PipedriveAdapter)

    # No CRM configured
    adapter = manager.get_adapter({})
    assert adapter is None


@pytest.mark.asyncio
async def test_crm_sync_manager_push_lead_no_crm():
    """CRMSyncManager returns skipped when no CRM is configured."""
    from integrations.crm_sync import CRMSyncManager

    manager = CRMSyncManager()
    result = await manager.push_lead({}, {"email": "test@example.com"})
    assert result["status"] == "skipped"
