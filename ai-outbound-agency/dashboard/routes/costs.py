"""Cost tracking API routes - per-tenant cost recording and P&L dashboard."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.models import (
    CostRecord,
    Plan,
    Subscription,
    SubscriptionStatus,
    Tenant,
    User,
)
from dashboard.auth import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/costs", tags=["costs"])


async def _get_session():
    """Lazy wrapper around core.db.get_session."""
    from core.db import get_session as _gs

    async for session in _gs():
        yield session


# ---------- Request/Response Models ----------


class RecordCostRequest(BaseModel):
    """Request body for recording a cost entry."""

    tenant_id: UUID
    cost_type: str  # "llm", "email", "api", "proxy"
    amount_cents: int
    description: str | None = None


class TenantCostBreakdown(BaseModel):
    """Cost breakdown by type for a single tenant."""

    tenant_id: UUID
    llm_cost_cents: int = 0
    email_cost_cents: int = 0
    api_cost_cents: int = 0
    proxy_cost_cents: int = 0
    total_cost_cents: int = 0


class PLSummaryItem(BaseModel):
    """P&L summary for a single tenant."""

    tenant_id: UUID
    tenant_name: str
    revenue_cents: int
    cost_cents: int
    profit_cents: int
    is_profitable: bool


class UnprofitableAlert(BaseModel):
    """Alert for a tenant that has been unprofitable for 7+ days."""

    tenant_id: UUID
    tenant_name: str
    total_cost_cents: int
    total_revenue_cents: int
    days_unprofitable: int


# ---------- Endpoints ----------


@router.get("/tenant/{tenant_id}", response_model=TenantCostBreakdown)
async def get_tenant_costs(
    tenant_id: UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(_get_session),
) -> TenantCostBreakdown:
    """Get cost breakdown by type for a specific tenant.

    Returns aggregated costs grouped by cost_type (llm, email, api, proxy).
    """
    result = await session.execute(
        select(
            CostRecord.cost_type,
            func.sum(CostRecord.amount_cents).label("total"),
        )
        .where(CostRecord.tenant_id == tenant_id)
        .group_by(CostRecord.cost_type)
    )
    rows = result.all()

    breakdown = {
        "llm": 0,
        "email": 0,
        "api": 0,
        "proxy": 0,
    }
    for row in rows:
        cost_type = row[0]
        total = row[1] or 0
        if cost_type in breakdown:
            breakdown[cost_type] = total

    total_cost = sum(breakdown.values())

    return TenantCostBreakdown(
        tenant_id=tenant_id,
        llm_cost_cents=breakdown["llm"],
        email_cost_cents=breakdown["email"],
        api_cost_cents=breakdown["api"],
        proxy_cost_cents=breakdown["proxy"],
        total_cost_cents=total_cost,
    )


@router.get("/summary", response_model=list[PLSummaryItem])
async def get_pl_summary(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(_get_session),
) -> list[PLSummaryItem]:
    """Get P&L summary across all tenants.

    For each tenant: revenue (subscription price_cents) minus total costs.
    """
    # Get all tenants
    tenants_result = await session.execute(select(Tenant))
    tenants = tenants_result.scalars().all()

    summary: list[PLSummaryItem] = []

    for tenant in tenants:
        # Get revenue from active subscription
        sub_result = await session.execute(
            select(Plan.price_cents)
            .join(Subscription, Subscription.plan_id == Plan.id)
            .where(
                Subscription.tenant_id == tenant.id,
                Subscription.status == SubscriptionStatus.active,
            )
        )
        revenue_row = sub_result.first()
        revenue_cents = revenue_row[0] if revenue_row else 0

        # Get total costs
        cost_result = await session.execute(
            select(func.sum(CostRecord.amount_cents)).where(
                CostRecord.tenant_id == tenant.id
            )
        )
        cost_cents = cost_result.scalar() or 0

        profit_cents = revenue_cents - cost_cents

        summary.append(
            PLSummaryItem(
                tenant_id=tenant.id,
                tenant_name=tenant.name,
                revenue_cents=revenue_cents,
                cost_cents=cost_cents,
                profit_cents=profit_cents,
                is_profitable=profit_cents >= 0,
            )
        )

    return summary


@router.get("/alerts", response_model=list[UnprofitableAlert])
async def get_unprofitable_alerts(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(_get_session),
) -> list[UnprofitableAlert]:
    """Get list of tenants that have been unprofitable for more than 7 days.

    A tenant is considered unprofitable if their costs in the last 7 days
    exceed their subscription revenue for that period.
    """
    seven_days_ago = datetime.now(timezone.utc) - timedelta(days=7)

    # Get all tenants
    tenants_result = await session.execute(select(Tenant))
    tenants = tenants_result.scalars().all()

    alerts: list[UnprofitableAlert] = []

    for tenant in tenants:
        # Get revenue (monthly subscription, prorated to 7 days)
        sub_result = await session.execute(
            select(Plan.price_cents)
            .join(Subscription, Subscription.plan_id == Plan.id)
            .where(
                Subscription.tenant_id == tenant.id,
                Subscription.status == SubscriptionStatus.active,
            )
        )
        revenue_row = sub_result.first()
        monthly_revenue = revenue_row[0] if revenue_row else 0
        # Prorate to 7 days (monthly / 30 * 7)
        revenue_7d = int(monthly_revenue * 7 / 30) if monthly_revenue > 0 else 0

        # Get costs in last 7 days
        cost_result = await session.execute(
            select(func.sum(CostRecord.amount_cents)).where(
                CostRecord.tenant_id == tenant.id,
                CostRecord.created_at >= seven_days_ago,
            )
        )
        cost_7d = cost_result.scalar() or 0

        if cost_7d > revenue_7d and cost_7d > 0:
            # Calculate approximate days unprofitable
            # Check each of the last 7 days
            days_unprofitable = 0
            for day_offset in range(7):
                day_start = datetime.now(timezone.utc) - timedelta(days=day_offset + 1)
                day_end = datetime.now(timezone.utc) - timedelta(days=day_offset)
                day_cost_result = await session.execute(
                    select(func.sum(CostRecord.amount_cents)).where(
                        CostRecord.tenant_id == tenant.id,
                        CostRecord.created_at >= day_start,
                        CostRecord.created_at < day_end,
                    )
                )
                day_cost = day_cost_result.scalar() or 0
                daily_revenue = int(monthly_revenue / 30) if monthly_revenue > 0 else 0
                if day_cost > daily_revenue:
                    days_unprofitable += 1

            if days_unprofitable >= 7:
                alerts.append(
                    UnprofitableAlert(
                        tenant_id=tenant.id,
                        tenant_name=tenant.name,
                        total_cost_cents=cost_7d,
                        total_revenue_cents=revenue_7d,
                        days_unprofitable=days_unprofitable,
                    )
                )

    return alerts


@router.post("/record", status_code=status.HTTP_201_CREATED)
async def record_cost(
    data: RecordCostRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(_get_session),
) -> dict[str, Any]:
    """Record a cost entry for a tenant.

    Args:
        data: Cost record data (tenant_id, cost_type, amount_cents, description).

    Returns:
        The created cost record with its ID.
    """
    valid_types = {"llm", "email", "api", "proxy"}
    if data.cost_type not in valid_types:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid cost_type. Must be one of: {', '.join(valid_types)}",
        )

    cost_record = CostRecord(
        tenant_id=data.tenant_id,
        cost_type=data.cost_type,
        amount_cents=data.amount_cents,
        description=data.description,
    )
    session.add(cost_record)
    await session.commit()
    await session.refresh(cost_record)

    return {
        "id": str(cost_record.id),
        "tenant_id": str(cost_record.tenant_id),
        "cost_type": cost_record.cost_type,
        "amount_cents": cost_record.amount_cents,
        "description": cost_record.description,
        "created_at": cost_record.created_at.isoformat() if cost_record.created_at else None,
    }
