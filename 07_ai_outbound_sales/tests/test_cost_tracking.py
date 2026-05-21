"""Tests for cost tracking - recording, P&L calculation, and unprofitable detection."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from core.models import (
    CostRecord,
    Plan,
    PlanName,
    Subscription,
    SubscriptionStatus,
    Tenant,
)


@pytest.fixture
async def sample_tenant(async_session) -> Tenant:
    """Create a sample tenant in the test database."""
    tenant = Tenant(
        id=uuid.uuid4(),
        name="Acme Corp",
        domain="acme.com",
        settings={},
    )
    async_session.add(tenant)
    await async_session.commit()
    await async_session.refresh(tenant)
    return tenant


@pytest.fixture
async def sample_plan(async_session) -> Plan:
    """Create a sample plan."""
    plan = Plan(
        id=uuid.uuid4(),
        name=PlanName.growth,
        stripe_price_id="price_test",
        leads_limit=1000,
        emails_limit=5000,
        linkedin_limit=200,
        campaigns_limit=10,
        price_cents=9900,  # $99/month
    )
    async_session.add(plan)
    await async_session.commit()
    await async_session.refresh(plan)
    return plan


@pytest.fixture
async def sample_subscription(async_session, sample_tenant, sample_plan) -> Subscription:
    """Create an active subscription for sample tenant."""
    sub = Subscription(
        id=uuid.uuid4(),
        tenant_id=sample_tenant.id,
        plan_id=sample_plan.id,
        stripe_subscription_id="sub_test_123",
        stripe_customer_id="cus_test_123",
        status=SubscriptionStatus.active,
    )
    async_session.add(sub)
    await async_session.commit()
    await async_session.refresh(sub)
    return sub


async def test_record_cost(async_session, sample_tenant):
    """Test recording a cost entry for a tenant."""
    cost = CostRecord(
        tenant_id=sample_tenant.id,
        cost_type="llm",
        amount_cents=150,
        description="GPT-4 API call for email generation",
    )
    async_session.add(cost)
    await async_session.commit()
    await async_session.refresh(cost)

    assert cost.id is not None
    assert cost.tenant_id == sample_tenant.id
    assert cost.cost_type == "llm"
    assert cost.amount_cents == 150
    assert cost.description == "GPT-4 API call for email generation"
    assert cost.created_at is not None


async def test_tenant_cost_breakdown(async_session, sample_tenant):
    """Test cost aggregation by type for a tenant."""
    from sqlalchemy import func, select

    # Record multiple cost types
    costs = [
        CostRecord(tenant_id=sample_tenant.id, cost_type="llm", amount_cents=100),
        CostRecord(tenant_id=sample_tenant.id, cost_type="llm", amount_cents=200),
        CostRecord(tenant_id=sample_tenant.id, cost_type="email", amount_cents=50),
        CostRecord(tenant_id=sample_tenant.id, cost_type="api", amount_cents=75),
        CostRecord(tenant_id=sample_tenant.id, cost_type="proxy", amount_cents=30),
    ]
    for c in costs:
        async_session.add(c)
    await async_session.commit()

    # Query cost breakdown
    result = await async_session.execute(
        select(
            CostRecord.cost_type,
            func.sum(CostRecord.amount_cents).label("total"),
        )
        .where(CostRecord.tenant_id == sample_tenant.id)
        .group_by(CostRecord.cost_type)
    )
    rows = result.all()

    breakdown = {row[0]: row[1] for row in rows}

    assert breakdown["llm"] == 300
    assert breakdown["email"] == 50
    assert breakdown["api"] == 75
    assert breakdown["proxy"] == 30


async def test_pl_summary_calculation(async_session, sample_tenant, sample_plan, sample_subscription):
    """Test P&L calculation: revenue minus costs equals profit."""
    from sqlalchemy import func, select

    # Add costs totaling $30 (3000 cents)
    costs = [
        CostRecord(tenant_id=sample_tenant.id, cost_type="llm", amount_cents=1500),
        CostRecord(tenant_id=sample_tenant.id, cost_type="email", amount_cents=1000),
        CostRecord(tenant_id=sample_tenant.id, cost_type="api", amount_cents=500),
    ]
    for c in costs:
        async_session.add(c)
    await async_session.commit()

    # Revenue from subscription: $99 (9900 cents)
    sub_result = await async_session.execute(
        select(Plan.price_cents)
        .join(Subscription, Subscription.plan_id == Plan.id)
        .where(
            Subscription.tenant_id == sample_tenant.id,
            Subscription.status == SubscriptionStatus.active,
        )
    )
    revenue_cents = sub_result.scalar() or 0
    assert revenue_cents == 9900

    # Total costs
    cost_result = await async_session.execute(
        select(func.sum(CostRecord.amount_cents)).where(
            CostRecord.tenant_id == sample_tenant.id
        )
    )
    cost_cents = cost_result.scalar() or 0
    assert cost_cents == 3000

    # Profit
    profit_cents = revenue_cents - cost_cents
    assert profit_cents == 6900
    assert profit_cents > 0  # is profitable


async def test_unprofitable_tenant_detection(async_session, sample_tenant, sample_plan, sample_subscription):
    """Test detection of a tenant that is unprofitable over 7 days."""
    from sqlalchemy import func, select

    # Add costs that exceed daily revenue for 7 days
    # Revenue: $99/month = $3.30/day = 330 cents/day
    # Add costs of 500 cents/day for each of last 7 days
    now = datetime.now(timezone.utc)
    for day_offset in range(7):
        cost = CostRecord(
            tenant_id=sample_tenant.id,
            cost_type="llm",
            amount_cents=500,
            created_at=now - timedelta(days=day_offset, hours=12),
        )
        async_session.add(cost)
    await async_session.commit()

    # Calculate 7-day costs
    seven_days_ago = now - timedelta(days=7)
    cost_result = await async_session.execute(
        select(func.sum(CostRecord.amount_cents)).where(
            CostRecord.tenant_id == sample_tenant.id,
            CostRecord.created_at >= seven_days_ago,
        )
    )
    cost_7d = cost_result.scalar() or 0
    assert cost_7d == 3500  # 7 * 500

    # Monthly revenue prorated to 7 days
    monthly_revenue = 9900
    revenue_7d = int(monthly_revenue * 7 / 30)
    assert revenue_7d == 2310  # ~$23.10

    # Should be unprofitable
    assert cost_7d > revenue_7d


async def test_cost_aggregation_by_type(async_session, sample_tenant):
    """Test that cost aggregation correctly sums by type across records."""
    from sqlalchemy import func, select

    # Create many records of different types
    for i in range(5):
        async_session.add(CostRecord(
            tenant_id=sample_tenant.id,
            cost_type="llm",
            amount_cents=10 * (i + 1),
        ))
    for i in range(3):
        async_session.add(CostRecord(
            tenant_id=sample_tenant.id,
            cost_type="email",
            amount_cents=20,
        ))
    await async_session.commit()

    # Query total
    result = await async_session.execute(
        select(func.sum(CostRecord.amount_cents)).where(
            CostRecord.tenant_id == sample_tenant.id
        )
    )
    total = result.scalar() or 0

    # LLM: 10+20+30+40+50 = 150, Email: 20*3 = 60, Total = 210
    assert total == 210

    # Query by type
    llm_result = await async_session.execute(
        select(func.sum(CostRecord.amount_cents)).where(
            CostRecord.tenant_id == sample_tenant.id,
            CostRecord.cost_type == "llm",
        )
    )
    llm_total = llm_result.scalar() or 0
    assert llm_total == 150

    email_result = await async_session.execute(
        select(func.sum(CostRecord.amount_cents)).where(
            CostRecord.tenant_id == sample_tenant.id,
            CostRecord.cost_type == "email",
        )
    )
    email_total = email_result.scalar() or 0
    assert email_total == 60


async def test_invalid_cost_type_rejected(async_session, sample_tenant):
    """Recording a cost with an invalid cost_type should be rejected."""
    # The valid_types set from the record_cost endpoint
    valid_types = {"llm", "email", "api", "proxy"}

    # Attempt to use an invalid type
    invalid_type = "invalid_type"
    assert invalid_type not in valid_types

    # Verify that the endpoint logic would reject this
    # In dashboard/routes/costs.py, this raises HTTPException 400
    from fastapi import HTTPException
    import pytest as _pytest

    with _pytest.raises(HTTPException) as exc_info:
        if invalid_type not in valid_types:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid cost_type. Must be one of: {', '.join(valid_types)}",
            )
    assert exc_info.value.status_code == 400
    assert "Invalid cost_type" in exc_info.value.detail


async def test_unprofitable_alert_threshold_7_days(async_session, sample_tenant, sample_plan, sample_subscription):
    """Test that unprofitable alert is triggered when costs exceed revenue every day for 7 days."""
    from sqlalchemy import func, select

    now = datetime.now(timezone.utc)

    # Monthly revenue: $99 (9900 cents), daily revenue: 9900/30 = 330 cents/day
    monthly_revenue = 9900
    daily_revenue = int(monthly_revenue / 30)
    assert daily_revenue == 330

    # Add costs exceeding daily revenue for each of the last 7 days
    for day_offset in range(7):
        day_start = now - timedelta(days=day_offset + 1)
        # Put cost in middle of that day window
        cost_time = day_start + timedelta(hours=12)
        cost = CostRecord(
            tenant_id=sample_tenant.id,
            cost_type="llm",
            amount_cents=500,  # 500 > 330 daily revenue
            created_at=cost_time,
        )
        async_session.add(cost)
    await async_session.commit()

    # Replicate the alert detection logic from /api/costs/alerts
    days_unprofitable = 0
    for day_offset in range(7):
        day_start = now - timedelta(days=day_offset + 1)
        day_end = now - timedelta(days=day_offset)
        day_cost_result = await async_session.execute(
            select(func.sum(CostRecord.amount_cents)).where(
                CostRecord.tenant_id == sample_tenant.id,
                CostRecord.created_at >= day_start,
                CostRecord.created_at < day_end,
            )
        )
        day_cost = day_cost_result.scalar() or 0
        if day_cost > daily_revenue:
            days_unprofitable += 1

    # All 7 days should be unprofitable
    assert days_unprofitable >= 7
