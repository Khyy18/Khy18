"""Tests for the campaigns API endpoints."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from core.models import (
    Base,
    Campaign,
    CampaignStatus,
    Tenant,
    User,
    UserRole,
)
from dashboard.auth import create_access_token, hash_password


@pytest.fixture
async def app_with_db(async_engine):
    """Create a FastAPI app with test database override."""
    from fastapi import FastAPI
    from dashboard.routes.campaigns import router as campaigns_router
    from dashboard.auth import router as auth_router
    import dashboard.auth as auth_module
    import dashboard.routes.campaigns as campaigns_module

    app = FastAPI()
    app.include_router(auth_router)
    app.include_router(campaigns_router)

    session_factory = async_sessionmaker(
        async_engine, class_=AsyncSession, expire_on_commit=False
    )

    async def override_get_session():
        async with session_factory() as session:
            yield session

    # Override _get_session in both modules
    app.dependency_overrides[auth_module._get_session] = override_get_session
    app.dependency_overrides[campaigns_module._get_session] = override_get_session

    return app, session_factory


@pytest.fixture
async def seeded_data(app_with_db):
    """Seed database with test tenant and user."""
    app, session_factory = app_with_db

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
            email="test@test.com",
            password_hash=hash_password("password123"),
            role=UserRole.admin,
            created_at=datetime.now(timezone.utc),
        )
        session.add(user)
        await session.flush()
        await session.commit()

        # Create another tenant for isolation tests
        other_tenant = Tenant(
            id=uuid.uuid4(),
            name="Other Tenant",
            domain="other.com",
            created_at=datetime.now(timezone.utc),
        )
        session.add(other_tenant)

        other_user = User(
            id=uuid.uuid4(),
            tenant_id=other_tenant.id,
            email="other@other.com",
            password_hash=hash_password("password123"),
            role=UserRole.admin,
            created_at=datetime.now(timezone.utc),
        )
        session.add(other_user)
        await session.flush()
        await session.commit()

    return {
        "tenant": tenant,
        "user": user,
        "other_tenant": other_tenant,
        "other_user": other_user,
    }


@pytest.fixture
def auth_headers(seeded_data):
    """Get auth headers for the test user."""
    user = seeded_data["user"]
    with patch("dashboard.auth.settings") as mock_settings:
        mock_settings.jwt_secret_key = "test-secret-key"
        mock_settings.jwt_algorithm = "HS256"
        token = create_access_token({"sub": str(user.id), "tenant_id": str(user.tenant_id)})
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def other_auth_headers(seeded_data):
    """Get auth headers for the other tenant user."""
    user = seeded_data["other_user"]
    with patch("dashboard.auth.settings") as mock_settings:
        mock_settings.jwt_secret_key = "test-secret-key"
        mock_settings.jwt_algorithm = "HS256"
        token = create_access_token({"sub": str(user.id), "tenant_id": str(user.tenant_id)})
    return {"Authorization": f"Bearer {token}"}


async def test_create_campaign(app_with_db, seeded_data, auth_headers):
    """Test create campaign returns 201."""
    app, _ = app_with_db

    # Mock the usage limiter to allow campaign creation
    with patch("compliance.usage_limiter.UsageLimiter") as mock_limiter_cls:
        mock_limiter = AsyncMock()
        mock_limiter.get_usage = AsyncMock(return_value={
            "campaigns": {"current": 0, "limit": 10}
        })
        mock_limiter.close = AsyncMock()
        mock_limiter_cls.return_value = mock_limiter

        with patch("dashboard.auth.settings") as mock_settings:
            mock_settings.jwt_secret_key = "test-secret-key"
            mock_settings.jwt_algorithm = "HS256"

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.post(
                    "/api/campaigns/",
                    json={"name": "My Campaign", "icp_filter": {"industry": "SaaS"}},
                    headers=auth_headers,
                )

    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "My Campaign"
    assert data["status"] == "draft"


async def test_list_campaigns_with_pagination(app_with_db, seeded_data, auth_headers):
    """Test list campaigns with pagination."""
    app, session_factory = app_with_db
    tenant = seeded_data["tenant"]

    # Create some campaigns
    async with session_factory() as session:
        for i in range(5):
            campaign = Campaign(
                tenant_id=tenant.id,
                name=f"Campaign {i}",
                icp_filter={},
                status=CampaignStatus.draft,
                created_at=datetime.now(timezone.utc),
            )
            session.add(campaign)
        await session.commit()

    with patch("dashboard.auth.settings") as mock_settings:
        mock_settings.jwt_secret_key = "test-secret-key"
        mock_settings.jwt_algorithm = "HS256"

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                "/api/campaigns/?limit=2&offset=0",
                headers=auth_headers,
            )

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 5
    assert data["limit"] == 2
    assert len(data["items"]) == 2


async def test_get_campaign_by_id(app_with_db, seeded_data, auth_headers):
    """Test get campaign by ID."""
    app, session_factory = app_with_db
    tenant = seeded_data["tenant"]

    async with session_factory() as session:
        campaign = Campaign(
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            name="Get Me",
            icp_filter={"target": "engineering"},
            status=CampaignStatus.draft,
            created_at=datetime.now(timezone.utc),
        )
        session.add(campaign)
        await session.commit()

    with patch("dashboard.auth.settings") as mock_settings:
        mock_settings.jwt_secret_key = "test-secret-key"
        mock_settings.jwt_algorithm = "HS256"

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                f"/api/campaigns/{campaign.id}",
                headers=auth_headers,
            )

    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Get Me"


async def test_update_campaign(app_with_db, seeded_data, auth_headers):
    """Test update campaign."""
    app, session_factory = app_with_db
    tenant = seeded_data["tenant"]

    async with session_factory() as session:
        campaign = Campaign(
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            name="Original Name",
            icp_filter={},
            status=CampaignStatus.draft,
            created_at=datetime.now(timezone.utc),
        )
        session.add(campaign)
        await session.commit()

    with patch("dashboard.auth.settings") as mock_settings:
        mock_settings.jwt_secret_key = "test-secret-key"
        mock_settings.jwt_algorithm = "HS256"

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.put(
                f"/api/campaigns/{campaign.id}",
                json={"name": "Updated Name"},
                headers=auth_headers,
            )

    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Updated Name"


async def test_delete_campaign(app_with_db, seeded_data, auth_headers):
    """Test delete campaign returns 204."""
    app, session_factory = app_with_db
    tenant = seeded_data["tenant"]

    async with session_factory() as session:
        campaign = Campaign(
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            name="Delete Me",
            icp_filter={},
            status=CampaignStatus.draft,
            created_at=datetime.now(timezone.utc),
        )
        session.add(campaign)
        await session.commit()

    with patch("dashboard.auth.settings") as mock_settings:
        mock_settings.jwt_secret_key = "test-secret-key"
        mock_settings.jwt_algorithm = "HS256"

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.delete(
                f"/api/campaigns/{campaign.id}",
                headers=auth_headers,
            )

    assert response.status_code == 204


async def test_tenant_isolation(app_with_db, seeded_data, other_auth_headers):
    """Test tenant isolation - can't access other tenant's campaigns."""
    app, session_factory = app_with_db
    tenant = seeded_data["tenant"]

    async with session_factory() as session:
        campaign = Campaign(
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            name="Private Campaign",
            icp_filter={},
            status=CampaignStatus.draft,
            created_at=datetime.now(timezone.utc),
        )
        session.add(campaign)
        await session.commit()

    with patch("dashboard.auth.settings") as mock_settings:
        mock_settings.jwt_secret_key = "test-secret-key"
        mock_settings.jwt_algorithm = "HS256"

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # Other tenant tries to access this campaign
            response = await client.get(
                f"/api/campaigns/{campaign.id}",
                headers=other_auth_headers,
            )

    assert response.status_code == 404
