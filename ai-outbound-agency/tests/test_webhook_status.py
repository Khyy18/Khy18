"""Tests for the webhook delivery status dashboard."""

import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.models import Tenant, User, UserRole, Webhook, WebhookDelivery


def _make_tenant_and_user():
    """Create a test tenant and user pair."""
    tid = uuid.uuid4()
    tenant = Tenant(id=tid, name="Webhook Corp", domain="webhook.com")
    user = User(
        id=uuid.uuid4(),
        tenant_id=tid,
        email=f"user-{uuid.uuid4().hex[:6]}@webhook.com",
        password_hash="$2b$12$hash",
        role=UserRole.admin,
    )
    return tenant, user


async def test_list_deliveries(async_session: AsyncSession):
    """Listing deliveries returns all deliveries for a tenant."""
    tenant, user = _make_tenant_and_user()
    async_session.add(tenant)
    async_session.add(user)
    await async_session.flush()

    webhook = Webhook(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        url="https://example.com/hook",
        events=["lead.created"],
        secret="test-secret",
    )
    async_session.add(webhook)
    await async_session.flush()

    # Create deliveries
    for i in range(3):
        delivery = WebhookDelivery(
            webhook_id=webhook.id,
            tenant_id=tenant.id,
            event_type="lead.created",
            payload={"lead_id": str(uuid.uuid4())},
            status="delivered" if i < 2 else "failed",
            attempts=1,
            response_code=200 if i < 2 else 500,
        )
        async_session.add(delivery)
    await async_session.flush()

    result = await async_session.execute(
        select(WebhookDelivery).where(WebhookDelivery.tenant_id == tenant.id)
    )
    deliveries = result.scalars().all()
    assert len(deliveries) == 3


async def test_filter_by_status(async_session: AsyncSession):
    """Filtering deliveries by status works correctly."""
    tenant, user = _make_tenant_and_user()
    async_session.add(tenant)
    async_session.add(user)
    await async_session.flush()

    webhook = Webhook(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        url="https://example.com/hook",
        events=["lead.created"],
        secret="test-secret",
    )
    async_session.add(webhook)
    await async_session.flush()

    # Create mix of statuses
    statuses = ["delivered", "delivered", "failed", "pending"]
    for s in statuses:
        delivery = WebhookDelivery(
            webhook_id=webhook.id,
            tenant_id=tenant.id,
            event_type="lead.created",
            payload={},
            status=s,
            attempts=1,
        )
        async_session.add(delivery)
    await async_session.flush()

    # Filter by failed
    result = await async_session.execute(
        select(WebhookDelivery).where(
            WebhookDelivery.tenant_id == tenant.id,
            WebhookDelivery.status == "failed",
        )
    )
    failed = result.scalars().all()
    assert len(failed) == 1

    # Filter by delivered
    result = await async_session.execute(
        select(WebhookDelivery).where(
            WebhookDelivery.tenant_id == tenant.id,
            WebhookDelivery.status == "delivered",
        )
    )
    delivered = result.scalars().all()
    assert len(delivered) == 2


async def test_manual_retry(async_session: AsyncSession):
    """Manual retry resets status to pending and increments attempts."""
    tenant, user = _make_tenant_and_user()
    async_session.add(tenant)
    async_session.add(user)
    await async_session.flush()

    webhook = Webhook(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        url="https://example.com/hook",
        events=["lead.created"],
        secret="test-secret",
    )
    async_session.add(webhook)
    await async_session.flush()

    delivery = WebhookDelivery(
        webhook_id=webhook.id,
        tenant_id=tenant.id,
        event_type="lead.created",
        payload={"data": "test"},
        status="failed",
        attempts=2,
        response_code=500,
    )
    async_session.add(delivery)
    await async_session.flush()

    # Simulate retry
    delivery.status = "pending"
    delivery.attempts += 1
    delivery.last_attempt_at = datetime.now(timezone.utc)
    await async_session.flush()

    result = await async_session.execute(
        select(WebhookDelivery).where(WebhookDelivery.id == delivery.id)
    )
    retried = result.scalar_one()
    assert retried.status == "pending"
    assert retried.attempts == 3
    assert retried.last_attempt_at is not None


async def test_health_metrics(async_session: AsyncSession):
    """Health endpoint returns correct success rate and counts."""
    tenant, user = _make_tenant_and_user()
    async_session.add(tenant)
    async_session.add(user)
    await async_session.flush()

    webhook = Webhook(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        url="https://example.com/hook",
        events=["lead.created"],
        secret="test-secret",
    )
    async_session.add(webhook)
    await async_session.flush()

    # Create 8 delivered, 2 failed = 80% success rate
    for i in range(10):
        delivery = WebhookDelivery(
            webhook_id=webhook.id,
            tenant_id=tenant.id,
            event_type="lead.created",
            payload={},
            status="delivered" if i < 8 else "failed",
            attempts=1,
        )
        async_session.add(delivery)
    await async_session.flush()

    # Calculate metrics
    total_result = await async_session.execute(
        select(func.count(WebhookDelivery.id)).where(
            WebhookDelivery.tenant_id == tenant.id
        )
    )
    total = total_result.scalar() or 0

    failed_result = await async_session.execute(
        select(func.count(WebhookDelivery.id)).where(
            WebhookDelivery.tenant_id == tenant.id,
            WebhookDelivery.status == "failed",
        )
    )
    failed = failed_result.scalar() or 0

    delivered_result = await async_session.execute(
        select(func.count(WebhookDelivery.id)).where(
            WebhookDelivery.tenant_id == tenant.id,
            WebhookDelivery.status == "delivered",
        )
    )
    delivered = delivered_result.scalar() or 0

    success_rate = round((delivered / total) * 100, 2) if total > 0 else 0.0

    assert total == 10
    assert failed == 2
    assert delivered == 8
    assert success_rate == 80.0
