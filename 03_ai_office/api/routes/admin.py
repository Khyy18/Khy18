"""Super-admin panel routes for platform management."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_office.api.auth import require_super_admin
from ai_office.core.database import get_session
from ai_office.core.models import Task, Tenant, TenantAgent, User

router = APIRouter(
    prefix="/api/admin",
    tags=["admin"],
    dependencies=[Depends(require_super_admin)],
)


@router.get("/tenants")
async def list_tenants(
    limit: int = 20,
    offset: int = 0,
    session: AsyncSession = Depends(get_session),
):
    """List all tenants with task count and agent count. Paginated."""
    # Query tenants with counts
    result = await session.execute(
        select(Tenant).order_by(Tenant.created_at.desc()).offset(offset).limit(limit)
    )
    tenants = result.scalars().all()

    tenant_list = []
    for tenant in tenants:
        # Count tasks for tenant
        task_count_result = await session.execute(
            select(func.count(Task.id)).where(Task.tenant_id == tenant.id)
        )
        task_count = task_count_result.scalar() or 0

        # Count active agents for tenant
        agent_count_result = await session.execute(
            select(func.count(TenantAgent.id)).where(
                TenantAgent.tenant_id == tenant.id,
                TenantAgent.is_enabled == True,  # noqa: E712
            )
        )
        agent_count = agent_count_result.scalar() or 0

        tenant_list.append(
            {
                "id": tenant.id,
                "name": tenant.name,
                "email": tenant.email,
                "plan_name": tenant.plan_name,
                "is_active": tenant.is_active,
                "task_count": task_count,
                "agent_count": agent_count,
                "created_at": tenant.created_at.isoformat() if tenant.created_at else None,
            }
        )

    return tenant_list


@router.get("/tenants/{tenant_id}")
async def get_tenant_detail(
    tenant_id: str,
    session: AsyncSession = Depends(get_session),
):
    """Get full detail for one tenant including users and agents."""
    result = await session.execute(select(Tenant).where(Tenant.id == tenant_id))
    tenant = result.scalar_one_or_none()

    if tenant is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tenant not found",
        )

    users = [
        {
            "id": u.id,
            "email": u.email,
            "role": u.role,
            "is_super_admin": u.is_super_admin,
        }
        for u in tenant.users
    ]

    agents = [
        {
            "id": a.id,
            "agent_name": a.agent_name,
            "is_enabled": a.is_enabled,
        }
        for a in tenant.tenant_agents
    ]

    return {
        "id": tenant.id,
        "name": tenant.name,
        "email": tenant.email,
        "plan_name": tenant.plan_name,
        "is_active": tenant.is_active,
        "created_at": tenant.created_at.isoformat() if tenant.created_at else None,
        "users": users,
        "tenant_agents": agents,
    }


@router.get("/stats")
async def get_platform_stats(
    session: AsyncSession = Depends(get_session),
):
    """Platform-wide statistics."""
    # Total tenants
    total_tenants_result = await session.execute(select(func.count(Tenant.id)))
    total_tenants = total_tenants_result.scalar() or 0

    # Active tenants
    active_tenants_result = await session.execute(
        select(func.count(Tenant.id)).where(Tenant.is_active == True)  # noqa: E712
    )
    active_tenants = active_tenants_result.scalar() or 0

    # Total tasks today
    today_start = datetime.now(timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    total_tasks_today_result = await session.execute(
        select(func.count(Task.id)).where(Task.created_at >= today_start)
    )
    total_tasks_today = total_tasks_today_result.scalar() or 0

    # Total users
    total_users_result = await session.execute(select(func.count(User.id)))
    total_users = total_users_result.scalar() or 0

    return {
        "total_tenants": total_tenants,
        "active_tenants": active_tenants,
        "total_tasks_today": total_tasks_today,
        "total_users": total_users,
    }


@router.post("/tenants/{tenant_id}/suspend")
async def suspend_tenant(
    tenant_id: str,
    session: AsyncSession = Depends(get_session),
):
    """Suspend a tenant by setting is_active to False."""
    result = await session.execute(select(Tenant).where(Tenant.id == tenant_id))
    tenant = result.scalar_one_or_none()

    if tenant is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tenant not found",
        )

    tenant.is_active = False
    await session.commit()
    await session.refresh(tenant)

    return {
        "id": tenant.id,
        "name": tenant.name,
        "email": tenant.email,
        "plan_name": tenant.plan_name,
        "is_active": tenant.is_active,
        "created_at": tenant.created_at.isoformat() if tenant.created_at else None,
    }
