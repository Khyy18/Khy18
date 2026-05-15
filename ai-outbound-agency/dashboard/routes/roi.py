"""ROI analytics dashboard endpoints."""

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.models import (
    Lead,
    LeadStatus,
    Plan,
    Subscription,
    SubscriptionStatus,
    User,
)
from dashboard.auth import get_current_user

router = APIRouter(prefix="/api/analytics/roi", tags=["roi"])


async def _get_session():
    from core.db import get_session as _gs

    async for session in _gs():
        yield session


@router.get("/")
async def get_roi_metrics(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(_get_session),
) -> dict:
    """Calculate ROI metrics for the current month."""
    now = datetime.now(timezone.utc)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    # Count meetings booked this month
    meetings_result = await session.execute(
        select(func.count(Lead.id)).where(
            Lead.tenant_id == current_user.tenant_id,
            Lead.status == LeadStatus.booked,
            Lead.created_at >= month_start,
        )
    )
    meetings_booked = meetings_result.scalar() or 0

    # Get tenant settings for avg_deal_size
    from core.models import Tenant

    tenant_result = await session.execute(
        select(Tenant).where(Tenant.id == current_user.tenant_id)
    )
    tenant = tenant_result.scalar_one_or_none()
    tenant_settings = (tenant.settings or {}) if tenant else {}
    avg_deal_size = tenant_settings.get("avg_deal_size", 5000)

    # Pipeline value
    pipeline_value = meetings_booked * avg_deal_size

    # Get subscription cost (current active subscription)
    sub_result = await session.execute(
        select(Plan.price_cents)
        .join(Subscription, Subscription.plan_id == Plan.id)
        .where(
            Subscription.tenant_id == current_user.tenant_id,
            Subscription.status == SubscriptionStatus.active,
        )
        .limit(1)
    )
    price_cents = sub_result.scalar() or 0
    subscription_cost = price_cents / 100.0

    # Cost per meeting
    cost_per_meeting = (subscription_cost / meetings_booked) if meetings_booked > 0 else 0.0

    # SDR equivalent cost
    sdr_equivalent = meetings_booked * 500

    # ROI multiplier
    if subscription_cost > 0:
        roi_multiplier = (pipeline_value - subscription_cost) / subscription_cost
    else:
        roi_multiplier = 0.0

    # Time saved
    time_saved_hours = meetings_booked * 4

    return {
        "meetings_booked": meetings_booked,
        "pipeline_value": pipeline_value,
        "cost_per_meeting": round(cost_per_meeting, 2),
        "sdr_equivalent": sdr_equivalent,
        "roi_multiplier": round(roi_multiplier, 2),
        "time_saved_hours": time_saved_hours,
    }


@router.get("/trend")
async def get_roi_trend(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(_get_session),
) -> dict:
    """Return monthly meetings booked and pipeline values for last 6 months."""
    now = datetime.now(timezone.utc)

    from core.models import Tenant

    tenant_result = await session.execute(
        select(Tenant).where(Tenant.id == current_user.tenant_id)
    )
    tenant = tenant_result.scalar_one_or_none()
    tenant_settings = (tenant.settings or {}) if tenant else {}
    avg_deal_size = tenant_settings.get("avg_deal_size", 5000)

    months_data = []
    for i in range(5, -1, -1):
        # Calculate month boundaries
        target = now - timedelta(days=i * 30)
        month_start = target.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        if month_start.month == 12:
            month_end = month_start.replace(year=month_start.year + 1, month=1)
        else:
            month_end = month_start.replace(month=month_start.month + 1)

        meetings_result = await session.execute(
            select(func.count(Lead.id)).where(
                Lead.tenant_id == current_user.tenant_id,
                Lead.status == LeadStatus.booked,
                Lead.created_at >= month_start,
                Lead.created_at < month_end,
            )
        )
        meetings = meetings_result.scalar() or 0
        months_data.append({
            "month": month_start.strftime("%Y-%m"),
            "meetings_booked": meetings,
            "pipeline_value": meetings * avg_deal_size,
        })

    return {"trend": months_data}


@router.get("/projected")
async def get_roi_projected(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(_get_session),
) -> dict:
    """Simple linear projection based on recent trend."""
    now = datetime.now(timezone.utc)

    from core.models import Tenant

    tenant_result = await session.execute(
        select(Tenant).where(Tenant.id == current_user.tenant_id)
    )
    tenant = tenant_result.scalar_one_or_none()
    tenant_settings = (tenant.settings or {}) if tenant else {}
    avg_deal_size = tenant_settings.get("avg_deal_size", 5000)

    # Get last 3 months of data for projection
    monthly_meetings = []
    for i in range(2, -1, -1):
        target = now - timedelta(days=i * 30)
        month_start = target.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        if month_start.month == 12:
            month_end = month_start.replace(year=month_start.year + 1, month=1)
        else:
            month_end = month_start.replace(month=month_start.month + 1)

        meetings_result = await session.execute(
            select(func.count(Lead.id)).where(
                Lead.tenant_id == current_user.tenant_id,
                Lead.status == LeadStatus.booked,
                Lead.created_at >= month_start,
                Lead.created_at < month_end,
            )
        )
        meetings = meetings_result.scalar() or 0
        monthly_meetings.append(meetings)

    # Simple linear projection: average growth rate
    if len(monthly_meetings) >= 2 and monthly_meetings[0] > 0:
        growth_rates = []
        for i in range(1, len(monthly_meetings)):
            if monthly_meetings[i - 1] > 0:
                rate = (monthly_meetings[i] - monthly_meetings[i - 1]) / monthly_meetings[i - 1]
                growth_rates.append(rate)
        avg_growth = sum(growth_rates) / len(growth_rates) if growth_rates else 0.0
    else:
        avg_growth = 0.0

    last_meetings = monthly_meetings[-1] if monthly_meetings else 0
    projected_meetings = max(0, int(last_meetings * (1 + avg_growth)))
    projected_pipeline = projected_meetings * avg_deal_size

    return {
        "projected_meetings": projected_meetings,
        "projected_pipeline_value": projected_pipeline,
        "growth_rate": round(avg_growth, 4),
    }
