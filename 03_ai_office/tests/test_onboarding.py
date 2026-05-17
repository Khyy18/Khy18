"""Tests for onboarding flow routes."""

from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import AsyncClient

from ai_office.api.auth import create_access_token, hash_password
from ai_office.core.models import Tenant, TenantAgent, User


@pytest_asyncio.fixture
async def onboarding_tenant(async_session):
    """Create a tenant for onboarding tests."""
    tenant = Tenant(
        name="New Startup",
        email="owner@startup.com",
        plan_name="trial",
    )
    async_session.add(tenant)
    await async_session.commit()
    await async_session.refresh(tenant)
    return tenant


@pytest_asyncio.fixture
async def onboarding_user(async_session, onboarding_tenant):
    """Create a user for onboarding tests."""
    user = User(
        tenant_id=onboarding_tenant.id,
        email="owner@startup.com",
        password_hash=hash_password("ownerpass"),
        role="admin",
        is_super_admin=False,
    )
    async_session.add(user)
    await async_session.commit()
    await async_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def onboarding_headers(onboarding_user, onboarding_tenant):
    """Authorization headers for onboarding user."""
    token_data = {"sub": onboarding_user.id, "tenant_id": onboarding_tenant.id}
    token = create_access_token(token_data)
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_onboarding_setup_creates_agents(
    test_client: AsyncClient,
    onboarding_headers: dict,
    onboarding_tenant: Tenant,
    async_session,
):
    """POST /api/onboarding/setup creates TenantAgent records."""
    response = await test_client.post(
        "/api/onboarding/setup",
        json={
            "company_name": "My Awesome Corp",
            "plan_choice": "pro",
            "selected_agents": ["Alice", "Sam", "Max"],
        },
        headers=onboarding_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "completed"
    assert data["agents_enabled"] == 3


@pytest.mark.asyncio
async def test_onboarding_status_before_setup(
    test_client: AsyncClient,
    onboarding_headers: dict,
):
    """GET /api/onboarding/status returns not completed when no agents exist."""
    response = await test_client.get(
        "/api/onboarding/status",
        headers=onboarding_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["completed"] is False
    assert data["agents_count"] == 0


@pytest.mark.asyncio
async def test_onboarding_status_after_setup(
    test_client: AsyncClient,
    onboarding_headers: dict,
    onboarding_tenant: Tenant,
    async_session,
):
    """GET /api/onboarding/status returns completed after setup."""
    # First do setup
    await test_client.post(
        "/api/onboarding/setup",
        json={
            "company_name": "Setup Corp",
            "plan_choice": "starter",
            "selected_agents": ["Alice", "Sam"],
        },
        headers=onboarding_headers,
    )

    response = await test_client.get(
        "/api/onboarding/status",
        headers=onboarding_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["completed"] is True
    assert data["agents_count"] == 2
    assert data["tenant_name"] == "Setup Corp"


@pytest.mark.asyncio
async def test_onboarding_setup_invalid_plan(
    test_client: AsyncClient,
    onboarding_headers: dict,
):
    """POST /api/onboarding/setup with invalid plan_choice returns 400."""
    response = await test_client.post(
        "/api/onboarding/setup",
        json={
            "company_name": "Bad Plan Corp",
            "plan_choice": "enterprise_ultra",
            "selected_agents": ["Alice"],
        },
        headers=onboarding_headers,
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_onboarding_setup_invalid_agents(
    test_client: AsyncClient,
    onboarding_headers: dict,
):
    """POST /api/onboarding/setup with all invalid agent names returns 400."""
    response = await test_client.post(
        "/api/onboarding/setup",
        json={
            "company_name": "Bad Agents Corp",
            "plan_choice": "starter",
            "selected_agents": ["NonExistentBot", "FakeAgent"],
        },
        headers=onboarding_headers,
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_onboarding_setup_mixed_agents(
    test_client: AsyncClient,
    onboarding_headers: dict,
):
    """POST /api/onboarding/setup with mix of valid and invalid agents succeeds for valid ones."""
    response = await test_client.post(
        "/api/onboarding/setup",
        json={
            "company_name": "Mixed Corp",
            "plan_choice": "pro",
            "selected_agents": ["Alice", "FakeAgent", "Sam"],
        },
        headers=onboarding_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["agents_enabled"] == 2
