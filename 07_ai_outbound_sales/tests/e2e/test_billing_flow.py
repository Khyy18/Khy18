"""E2E tests for the billing flow."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from core.models import Plan, PlanName, Subscription, SubscriptionStatus


async def test_list_plans_empty(client, auth_headers):
    """Test listing plans when none are configured."""
    with patch("dashboard.auth.settings") as mock_settings:
        mock_settings.jwt_secret_key = "test-secret-key"
        mock_settings.jwt_algorithm = "HS256"

        response = await client.get("/api/billing/plans", headers=auth_headers)

    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)


async def test_list_plans_with_seeded_plans(client, auth_headers, e2e_session_factory):
    """Test listing plans returns seeded plan data."""
    # Seed plans
    async with e2e_session_factory() as session:
        plan = Plan(
            id=uuid.uuid4(),
            name=PlanName.starter,
            stripe_price_id="price_starter_123",
            leads_limit=500,
            emails_limit=1000,
            linkedin_limit=100,
            campaigns_limit=5,
            domains_limit=1,
            voice_calls_limit=0,
            price_cents=2900,
            created_at=datetime.now(timezone.utc),
        )
        session.add(plan)
        await session.commit()

    with patch("dashboard.auth.settings") as mock_settings:
        mock_settings.jwt_secret_key = "test-secret-key"
        mock_settings.jwt_algorithm = "HS256"

        response = await client.get("/api/billing/plans", headers=auth_headers)

    assert response.status_code == 200
    data = response.json()
    assert len(data) >= 1
    assert any(p["name"] == "starter" for p in data)


async def test_get_subscription_no_subscription(client, auth_headers):
    """Test getting subscription when none exists returns 404."""
    with patch("dashboard.auth.settings") as mock_settings:
        mock_settings.jwt_secret_key = "test-secret-key"
        mock_settings.jwt_algorithm = "HS256"

        response = await client.get("/api/billing/subscription", headers=auth_headers)

    assert response.status_code == 404


async def test_get_usage(client, auth_headers):
    """Test getting usage info (mocked limiter)."""
    with (
        patch("dashboard.auth.settings") as mock_settings,
        patch("compliance.usage_limiter.get_usage_limiter") as mock_get_limiter,
    ):
        mock_settings.jwt_secret_key = "test-secret-key"
        mock_settings.jwt_algorithm = "HS256"

        mock_limiter = AsyncMock()
        mock_limiter.get_usage = AsyncMock(return_value={
            "leads": {"current": 10, "limit": 500},
            "emails": {"current": 50, "limit": 1000},
            "linkedin": {"current": 5, "limit": 100},
            "campaigns": {"current": 2, "limit": 5},
        })
        mock_get_limiter.return_value = mock_limiter

        response = await client.get("/api/billing/usage", headers=auth_headers)

    assert response.status_code == 200
    data = response.json()
    assert data["leads_used"] == 10
    assert data["leads_limit"] == 500
    assert data["emails_used"] == 50
    assert data["emails_limit"] == 1000
    assert data["campaigns_active"] == 2
    assert data["campaigns_limit"] == 5


async def test_checkout_without_subscription(client, auth_headers):
    """Test that checkout without an existing subscription returns 400."""
    with (
        patch("dashboard.auth.settings") as mock_settings,
        patch("dashboard.routes.billing.settings") as mock_billing_settings,
    ):
        mock_settings.jwt_secret_key = "test-secret-key"
        mock_settings.jwt_algorithm = "HS256"
        mock_billing_settings.stripe_secret_key = "sk_test_123"

        response = await client.post(
            "/api/billing/subscribe",
            json={
                "plan_id": str(uuid.uuid4()),
                "success_url": "http://localhost/success",
                "cancel_url": "http://localhost/cancel",
            },
            headers=auth_headers,
        )

    # Should fail because no subscription record exists
    assert response.status_code in (400, 404)
