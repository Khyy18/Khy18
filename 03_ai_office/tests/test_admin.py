"""Tests for super-admin panel routes."""

from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import AsyncClient

from ai_office.api.auth import create_access_token, hash_password
from ai_office.core.models import Task, Tenant, TenantAgent, User


@pytest_asyncio.fixture
async def super_admin_tenant(async_session):
    """Create a tenant for the super admin."""
    tenant = Tenant(
        name="Platform Admin",
        email="admin@platform.com",
        plan_name="agency",
    )
    async_session.add(tenant)
    await async_session.commit()
    await async_session.refresh(tenant)
    return tenant


@pytest_asyncio.fixture
async def super_admin_user(async_session, super_admin_tenant):
    """Create a super admin user."""
    user = User(
        tenant_id=super_admin_tenant.id,
        email="superadmin@platform.com",
        password_hash=hash_password("superadminpass"),
        role="admin",
        is_super_admin=True,
    )
    async_session.add(user)
    await async_session.commit()
    await async_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def super_admin_headers(super_admin_user, super_admin_tenant):
    """Authorization headers for super admin."""
    token_data = {"sub": super_admin_user.id, "tenant_id": super_admin_tenant.id}
    token = create_access_token(token_data)
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def regular_tenant(async_session):
    """Create a regular tenant."""
    tenant = Tenant(
        name="Regular Corp",
        email="info@regular.com",
        plan_name="starter",
    )
    async_session.add(tenant)
    await async_session.commit()
    await async_session.refresh(tenant)
    return tenant


@pytest_asyncio.fixture
async def regular_user(async_session, regular_tenant):
    """Create a regular (non-admin) user."""
    user = User(
        tenant_id=regular_tenant.id,
        email="user@regular.com",
        password_hash=hash_password("userpass"),
        role="member",
        is_super_admin=False,
    )
    async_session.add(user)
    await async_session.commit()
    await async_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def regular_headers(regular_user, regular_tenant):
    """Authorization headers for a regular user."""
    token_data = {"sub": regular_user.id, "tenant_id": regular_tenant.id}
    token = create_access_token(token_data)
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_list_tenants_super_admin(
    test_client: AsyncClient,
    super_admin_headers: dict,
    super_admin_tenant: Tenant,
):
    """Super admin can list all tenants."""
    response = await test_client.get(
        "/api/admin/tenants", headers=super_admin_headers
    )
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) >= 1
    # Should contain the super admin's tenant
    tenant_ids = [t["id"] for t in data]
    assert super_admin_tenant.id in tenant_ids
    # Check structure of returned tenant
    tenant_data = next(t for t in data if t["id"] == super_admin_tenant.id)
    assert "name" in tenant_data
    assert "email" in tenant_data
    assert "plan_name" in tenant_data
    assert "is_active" in tenant_data
    assert "task_count" in tenant_data
    assert "agent_count" in tenant_data
    assert "created_at" in tenant_data


@pytest.mark.asyncio
async def test_list_tenants_non_super_admin_returns_403(
    test_client: AsyncClient,
    regular_headers: dict,
):
    """Non-super-admin user gets 403 on admin endpoints."""
    response = await test_client.get(
        "/api/admin/tenants", headers=regular_headers
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_get_platform_stats(
    test_client: AsyncClient,
    super_admin_headers: dict,
    super_admin_tenant: Tenant,
):
    """Super admin can get platform-wide stats."""
    response = await test_client.get(
        "/api/admin/stats", headers=super_admin_headers
    )
    assert response.status_code == 200
    data = response.json()
    assert "total_tenants" in data
    assert "active_tenants" in data
    assert "total_tasks_today" in data
    assert "total_users" in data
    assert data["total_tenants"] >= 1
    assert data["active_tenants"] >= 1
    assert data["total_users"] >= 1


@pytest.mark.asyncio
async def test_suspend_tenant(
    test_client: AsyncClient,
    async_session,
    super_admin_headers: dict,
    regular_tenant: Tenant,
):
    """Super admin can suspend a tenant."""
    response = await test_client.post(
        f"/api/admin/tenants/{regular_tenant.id}/suspend",
        headers=super_admin_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["is_active"] is False
    assert data["id"] == regular_tenant.id


@pytest.mark.asyncio
async def test_suspend_tenant_not_found(
    test_client: AsyncClient,
    super_admin_headers: dict,
):
    """Suspending a non-existent tenant returns 404."""
    response = await test_client.post(
        "/api/admin/tenants/nonexistent-id/suspend",
        headers=super_admin_headers,
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_tenant_detail(
    test_client: AsyncClient,
    async_session,
    super_admin_headers: dict,
    super_admin_tenant: Tenant,
):
    """Super admin can get detailed info for a tenant."""
    # Create a separate tenant with user and agent for this test
    tenant = Tenant(
        name="Detail Corp",
        email="detail@corp.com",
        plan_name="pro",
    )
    async_session.add(tenant)
    await async_session.flush()

    user = User(
        tenant_id=tenant.id,
        email="detailuser@corp.com",
        password_hash=hash_password("detailpass"),
        role="member",
        is_super_admin=False,
    )
    async_session.add(user)

    agent = TenantAgent(
        tenant_id=tenant.id,
        agent_name="Alice",
        is_enabled=True,
    )
    async_session.add(agent)
    await async_session.commit()

    response = await test_client.get(
        f"/api/admin/tenants/{tenant.id}",
        headers=super_admin_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == tenant.id
    assert data["name"] == "Detail Corp"
    assert "users" in data
    assert "tenant_agents" in data
    assert len(data["users"]) >= 1
    assert len(data["tenant_agents"]) >= 1
