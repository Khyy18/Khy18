"""Эндпоинты управления подпиской."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_office.api.schemas import SubscriptionStatusResponse
from ai_office.core.database import get_session
from ai_office.core.models import Workspace
from ai_office.core.subscription import TIERS, get_subscription_status

router = APIRouter(prefix="/api/subscription", tags=["subscription"])


class UpgradeRequest(BaseModel):
    """Запрос на повышение тарифа."""

    tier: str


@router.get("/status", response_model=SubscriptionStatusResponse)
async def subscription_status(
    session: AsyncSession = Depends(get_session),
):
    """Получить текущий статус подписки workspace."""
    # Get first workspace (in real app, would use auth context)
    result = await session.execute(select(Workspace).limit(1))
    workspace = result.scalar_one_or_none()
    if workspace is None:
        return SubscriptionStatusResponse(
            tier="free",
            messages_remaining=100,
            messages_limit=100,
            messages_used=0,
            agents_available=TIERS["free"]["allowed_agents"],
        )

    status = await get_subscription_status(workspace.id, session)
    return SubscriptionStatusResponse(**status)


@router.post("/upgrade", response_model=SubscriptionStatusResponse)
async def upgrade_subscription(
    body: UpgradeRequest,
    session: AsyncSession = Depends(get_session),
):
    """Повысить тарифный план workspace."""
    if body.tier not in TIERS:
        raise HTTPException(status_code=400, detail=f"Unknown tier: {body.tier}")

    result = await session.execute(select(Workspace).limit(1))
    workspace = result.scalar_one_or_none()
    if workspace is None:
        raise HTTPException(status_code=404, detail="Workspace not found")

    workspace.subscription_tier = body.tier
    await session.commit()

    status = await get_subscription_status(workspace.id, session)
    return SubscriptionStatusResponse(**status)
