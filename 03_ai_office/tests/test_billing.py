"""Tests for billing system: plans, usage, limits, and webhooks."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from ai_office.api.auth import create_access_token
from ai_office.core.models import Task, Tenant, TenantAgent, User


@pytest.mark.asyncio
async def test_list_plans(test_client: AsyncClient):
    """GET /api/billing/plans returns all available plans."""
    response = await test_client.get("/api/billing/plans")
    assert response.status_code == 200
    plans = response.json()
    assert isinstance(plans, list)
    assert len(plans) == 4

    plan_keys = [p["key"] for p in plans]
    assert "trial" in plan_keys
    assert "starter" in plan_keys
    assert "pro" in plan_keys
    assert "agency" in plan_keys

    # Verify plan structure
    starter = next(p for p in plans if p["key"] == "starter")
    assert starter["name"] == "Starter"
    assert starter["price"] == 4900
    assert starter["max_agents"] == 3
    assert starter["max_tasks_per_month"] == 100
    assert "basic" in starter["features"]


@pytest.mark.asyncio
async def test_get_usage(
    test_client: AsyncClient,
    async_session: AsyncSession,
    create_tenant: Tenant,
    create_user: User,
    auth_headers: dict,
):
    """GET /api/billing/usage returns correct counts for authenticated user."""
    # Create some tasks for the tenant
    for i in range(5):
        task = Task(
            description=f"Test task {i}",
            creator_type="user",
            creator_id="api",
            status="open",
            priority="medium",
            tenant_id=create_tenant.id,
        )
        async_session.add(task)
    await async_session.commit()

    response = await test_client.get("/api/billing/usage", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["tasks_this_period"] == 5
    assert data["max_tasks_per_month"] == 100  # trial plan
    assert data["active_agents"] == 0
    assert data["max_agents"] == 3


@pytest.mark.asyncio
async def test_get_subscription(
    test_client: AsyncClient,
    create_tenant: Tenant,
    create_user: User,
    auth_headers: dict,
):
    """GET /api/billing/subscription returns current plan info."""
    response = await test_client.get("/api/billing/subscription", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["plan_name"] == "trial"
    assert data["is_active"] is True
    assert data["stripe_subscription_id"] is None


@pytest.mark.asyncio
async def test_task_limit_enforcement(
    test_client: AsyncClient,
    async_session: AsyncSession,
    create_tenant: Tenant,
    create_user: User,
    auth_headers: dict,
):
    """POST /api/tasks returns 402 when tenant exceeds task limit."""
    # Mock check_task_limit to return False (at limit)
    with patch(
        "ai_office.api.routes.tasks.check_task_limit",
        new_callable=AsyncMock,
        return_value=False,
    ):
        response = await test_client.post(
            "/api/tasks",
            json={"description": "Over limit task", "priority": "medium"},
            headers=auth_headers,
        )
        assert response.status_code == 402
        assert "Task limit reached" in response.json()["detail"]


@pytest.mark.asyncio
async def test_task_creation_under_limit(
    test_client: AsyncClient,
    async_session: AsyncSession,
    create_tenant: Tenant,
    create_user: User,
    auth_headers: dict,
):
    """POST /api/tasks succeeds when tenant is under task limit."""
    response = await test_client.post(
        "/api/tasks",
        json={"description": "Under limit task", "priority": "medium"},
        headers=auth_headers,
    )
    assert response.status_code == 201
    data = response.json()
    assert data["description"] == "Under limit task"


@pytest.mark.asyncio
async def test_task_creation_no_auth_skips_limit(
    test_client: AsyncClient,
    async_session: AsyncSession,
):
    """POST /api/tasks without auth skips limit check (backward compat)."""
    response = await test_client.post(
        "/api/tasks",
        json={"description": "No auth task", "priority": "low"},
    )
    assert response.status_code == 201


@pytest.mark.asyncio
async def test_webhook_checkout_completed(
    test_client: AsyncClient,
    async_session: AsyncSession,
    create_tenant: Tenant,
):
    """Stripe webhook updates tenant plan on checkout.session.completed."""
    event_data = {
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "metadata": {
                    "tenant_id": create_tenant.id,
                    "plan_name": "pro",
                },
                "customer": "cus_test123",
                "subscription": "sub_test123",
            }
        },
    }

    with patch("stripe.Webhook.construct_event", return_value=event_data):
        with patch("ai_office.core.config.settings.stripe_webhook_secret", "whsec_test"):
            response = await test_client.post(
                "/api/billing/webhook",
                content=b'{"test": true}',
                headers={"stripe-signature": "test_sig"},
            )
            assert response.status_code == 200

    # Verify tenant was updated
    await async_session.refresh(create_tenant)
    assert create_tenant.plan_name == "pro"
    assert create_tenant.stripe_customer_id == "cus_test123"
    assert create_tenant.stripe_subscription_id == "sub_test123"


@pytest.mark.asyncio
async def test_webhook_subscription_deleted(
    test_client: AsyncClient,
    async_session: AsyncSession,
    create_tenant: Tenant,
):
    """Stripe webhook sets plan to trial on subscription.deleted."""
    # Set up tenant with a paid plan
    create_tenant.plan_name = "pro"
    create_tenant.stripe_subscription_id = "sub_delete123"
    await async_session.commit()

    event_data = {
        "type": "customer.subscription.deleted",
        "data": {
            "object": {
                "id": "sub_delete123",
            }
        },
    }

    with patch("stripe.Webhook.construct_event", return_value=event_data):
        with patch("ai_office.core.config.settings.stripe_webhook_secret", "whsec_test"):
            response = await test_client.post(
                "/api/billing/webhook",
                content=b'{"test": true}',
                headers={"stripe-signature": "test_sig"},
            )
            assert response.status_code == 200

    # Verify tenant was downgraded
    await async_session.refresh(create_tenant)
    assert create_tenant.plan_name == "trial"
    assert create_tenant.stripe_subscription_id is None


@pytest.mark.asyncio
async def test_checkout_without_stripe_key(
    test_client: AsyncClient,
    create_tenant: Tenant,
    create_user: User,
    auth_headers: dict,
):
    """POST /api/billing/checkout returns 503 when Stripe is not configured."""
    with patch("ai_office.core.config.settings.stripe_secret_key", ""):
        response = await test_client.post(
            "/api/billing/checkout",
            json={"plan_name": "pro"},
            headers=auth_headers,
        )
        assert response.status_code == 503
        assert "Stripe is not configured" in response.json()["detail"]


@pytest.mark.asyncio
async def test_get_usage_with_agents(
    test_client: AsyncClient,
    async_session: AsyncSession,
    create_tenant: Tenant,
    create_user: User,
    auth_headers: dict,
):
    """GET /api/billing/usage counts active agents correctly."""
    # Create some tenant agents
    for i in range(2):
        agent = TenantAgent(
            tenant_id=create_tenant.id,
            agent_name=f"Agent {i}",
            is_enabled=True,
        )
        async_session.add(agent)
    # Add a disabled agent (should not count)
    disabled_agent = TenantAgent(
        tenant_id=create_tenant.id,
        agent_name="Disabled Agent",
        is_enabled=False,
    )
    async_session.add(disabled_agent)
    await async_session.commit()

    response = await test_client.get("/api/billing/usage", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["active_agents"] == 2
