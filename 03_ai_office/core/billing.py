"""Billing plan definitions and limit enforcement helpers."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_office.core.models import Task, Tenant, TenantAgent

# Plan definitions
PLANS: Dict[str, Dict[str, Any]] = {
    "trial": {
        "name": "Trial",
        "price": 0,
        "max_agents": 3,
        "max_tasks_per_month": 100,
        "features": ["basic"],
    },
    "starter": {
        "name": "Starter",
        "price": 4900,
        "max_agents": 3,
        "max_tasks_per_month": 100,
        "features": ["basic"],
    },
    "pro": {
        "name": "Pro",
        "price": 14900,
        "max_agents": 8,
        "max_tasks_per_month": -1,
        "features": ["basic", "priority_support"],
    },
    "agency": {
        "name": "Agency",
        "price": 49900,
        "max_agents": -1,
        "max_tasks_per_month": -1,
        "features": ["basic", "priority_support", "api_access", "white_label"],
    },
}


def get_tenant_plan(tenant: Tenant) -> Dict[str, Any]:
    """Return the plan dict for a tenant's current plan_name."""
    return PLANS.get(tenant.plan_name, PLANS["trial"])


def get_billing_period_start() -> datetime:
    """Return the first day of the current month (UTC)."""
    now = datetime.now(timezone.utc)
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


async def check_task_limit(tenant_id: str, session: AsyncSession) -> bool:
    """Check if tenant is under their task limit for the current billing period.

    Returns True if the tenant can create more tasks (under limit).
    Returns False if at or over the limit.
    """
    # Get tenant to determine plan
    result = await session.execute(select(Tenant).where(Tenant.id == tenant_id))
    tenant = result.scalar_one_or_none()
    if tenant is None:
        return False

    plan = get_tenant_plan(tenant)
    max_tasks = plan["max_tasks_per_month"]

    # -1 means unlimited
    if max_tasks == -1:
        return True

    # Count tasks in current billing period
    period_start = get_billing_period_start()
    count_query = select(func.count(Task.id)).where(
        Task.tenant_id == tenant_id,
        Task.created_at >= period_start,
    )
    count_result = await session.execute(count_query)
    task_count = count_result.scalar() or 0

    return task_count < max_tasks


async def check_agent_limit(tenant_id: str, session: AsyncSession) -> bool:
    """Check if tenant is under their agent limit.

    Returns True if the tenant can enable more agents (under limit).
    Returns False if at or over the limit.
    """
    # Get tenant to determine plan
    result = await session.execute(select(Tenant).where(Tenant.id == tenant_id))
    tenant = result.scalar_one_or_none()
    if tenant is None:
        return False

    plan = get_tenant_plan(tenant)
    max_agents = plan["max_agents"]

    # -1 means unlimited
    if max_agents == -1:
        return True

    # Count enabled agents
    count_query = select(func.count(TenantAgent.id)).where(
        TenantAgent.tenant_id == tenant_id,
        TenantAgent.is_enabled == True,  # noqa: E712
    )
    count_result = await session.execute(count_query)
    agent_count = count_result.scalar() or 0

    return agent_count < max_agents
