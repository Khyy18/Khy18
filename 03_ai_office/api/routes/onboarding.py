"""Onboarding flow routes for new tenants."""

from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_office.api.auth import get_current_user
from ai_office.core.database import get_session
from ai_office.core.models import Tenant, TenantAgent, User

# Known agent names that can be selected during onboarding
KNOWN_AGENTS: List[str] = [
    "Alice",
    "Sam",
    "Max",
    "Eva",
    "Leo",
    "Nova",
    "Iris",
    "Oscar",
    "outbound_sales",
    "zenith",
    "text_agency",
    "combo_bot",
]

router = APIRouter(
    prefix="/api/onboarding",
    tags=["onboarding"],
)


class SetupRequest(BaseModel):
    """Request body for onboarding setup."""

    company_name: str
    plan_choice: str
    selected_agents: List[str]


@router.post("/setup")
async def onboarding_setup(
    body: SetupRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Set up a tenant with company name and selected agents."""
    # Validate plan_choice
    valid_plans = {"starter", "pro", "agency"}
    if body.plan_choice not in valid_plans:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid plan_choice. Must be one of: {', '.join(sorted(valid_plans))}",
        )

    # Validate agent names
    valid_agents = [a for a in body.selected_agents if a in KNOWN_AGENTS]
    if not valid_agents:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No valid agent names provided",
        )

    # Update tenant name
    result = await session.execute(
        select(Tenant).where(Tenant.id == current_user.tenant_id)
    )
    tenant = result.scalar_one_or_none()
    if tenant is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tenant not found",
        )

    tenant.name = body.company_name

    # Create TenantAgent records for each valid agent
    for agent_name in valid_agents:
        tenant_agent = TenantAgent(
            tenant_id=current_user.tenant_id,
            agent_name=agent_name,
            is_enabled=True,
        )
        session.add(tenant_agent)

    await session.commit()

    return {"status": "completed", "agents_enabled": len(valid_agents)}


@router.get("/status")
async def onboarding_status(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Check onboarding completion status for current tenant."""
    # Count TenantAgent records
    count_result = await session.execute(
        select(func.count(TenantAgent.id)).where(
            TenantAgent.tenant_id == current_user.tenant_id
        )
    )
    agents_count = count_result.scalar() or 0

    # Get tenant name
    result = await session.execute(
        select(Tenant).where(Tenant.id == current_user.tenant_id)
    )
    tenant = result.scalar_one_or_none()
    tenant_name = tenant.name if tenant else ""

    return {
        "completed": agents_count > 0,
        "tenant_name": tenant_name,
        "agents_count": agents_count,
    }
