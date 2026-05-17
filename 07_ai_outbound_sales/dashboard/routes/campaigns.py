from __future__ import annotations
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.models import Campaign, CampaignStatus, User
from dashboard.auth import get_current_user
from dashboard.schemas import (
    CampaignCreate,
    CampaignListResponse,
    CampaignResponse,
    CampaignUpdate,
)

router = APIRouter(prefix="/api/campaigns", tags=["campaigns"])


async def _get_session():
    from core.db import get_session as _gs

    async for session in _gs():
        yield session


@router.post("/", response_model=CampaignResponse, status_code=status.HTTP_201_CREATED)
async def create_campaign(
    data: CampaignCreate,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(_get_session),
) -> Campaign:
    # Check campaign limit for the tenant
    from compliance.usage_limiter import UsageLimiter
    from core.config import settings

    usage_limiter = UsageLimiter(redis_url=settings.redis_url)
    try:
        # Count existing active campaigns
        active_count_result = await session.execute(
            select(func.count()).select_from(Campaign).where(
                Campaign.tenant_id == current_user.tenant_id,
                Campaign.status == CampaignStatus.active,
            )
        )
        active_count = active_count_result.scalar() or 0

        usage = await usage_limiter.get_usage(str(current_user.tenant_id))
        campaigns_limit = usage["campaigns"]["limit"]

        if campaigns_limit != -1 and active_count >= campaigns_limit:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Campaign limit exceeded for your plan",
            )
    finally:
        await usage_limiter.close()

    campaign = Campaign(
        tenant_id=current_user.tenant_id,
        name=data.name,
        icp_filter=data.icp_filter,
        sequence_id=data.sequence_id,
    )
    session.add(campaign)
    await session.flush()
    await session.refresh(campaign)
    return campaign


@router.get("/", response_model=CampaignListResponse)
async def list_campaigns(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    status_filter: Optional[str] = Query(default=None, alias="status"),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(_get_session),
) -> dict:
    base_query = select(Campaign).where(Campaign.tenant_id == current_user.tenant_id)
    count_query = select(func.count()).select_from(Campaign).where(
        Campaign.tenant_id == current_user.tenant_id
    )

    if status_filter:
        base_query = base_query.where(Campaign.status == status_filter)
        count_query = count_query.where(Campaign.status == status_filter)

    total_result = await session.execute(count_query)
    total = total_result.scalar() or 0

    result = await session.execute(
        base_query.order_by(Campaign.created_at.desc()).limit(limit).offset(offset)
    )
    items = list(result.scalars().all())

    return {"items": items, "total": total, "limit": limit, "offset": offset}


@router.get("/{campaign_id}", response_model=CampaignResponse)
async def get_campaign(
    campaign_id: UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(_get_session),
) -> Campaign:
    result = await session.execute(
        select(Campaign).where(
            Campaign.id == campaign_id,
            Campaign.tenant_id == current_user.tenant_id,
        )
    )
    campaign = result.scalar_one_or_none()
    if campaign is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found")
    return campaign


@router.put("/{campaign_id}", response_model=CampaignResponse)
async def update_campaign(
    campaign_id: UUID,
    data: CampaignUpdate,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(_get_session),
) -> Campaign:
    result = await session.execute(
        select(Campaign).where(
            Campaign.id == campaign_id,
            Campaign.tenant_id == current_user.tenant_id,
        )
    )
    campaign = result.scalar_one_or_none()
    if campaign is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found")

    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(campaign, field, value)

    await session.flush()
    await session.refresh(campaign)
    return campaign


@router.post("/{campaign_id}/activate", response_model=CampaignResponse)
async def activate_campaign(
    campaign_id: UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(_get_session),
) -> Campaign:
    result = await session.execute(
        select(Campaign).where(
            Campaign.id == campaign_id,
            Campaign.tenant_id == current_user.tenant_id,
        )
    )
    campaign = result.scalar_one_or_none()
    if campaign is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found")

    if campaign.status == CampaignStatus.active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Campaign is already active",
        )

    campaign.status = CampaignStatus.active
    await session.flush()
    await session.refresh(campaign)
    return campaign


@router.post("/{campaign_id}/pause", response_model=CampaignResponse)
async def pause_campaign(
    campaign_id: UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(_get_session),
) -> Campaign:
    result = await session.execute(
        select(Campaign).where(
            Campaign.id == campaign_id,
            Campaign.tenant_id == current_user.tenant_id,
        )
    )
    campaign = result.scalar_one_or_none()
    if campaign is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found")

    campaign.status = CampaignStatus.paused
    await session.flush()
    await session.refresh(campaign)
    return campaign


@router.delete("/{campaign_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_campaign(
    campaign_id: UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(_get_session),
) -> None:
    result = await session.execute(
        select(Campaign).where(
            Campaign.id == campaign_id,
            Campaign.tenant_id == current_user.tenant_id,
        )
    )
    campaign = result.scalar_one_or_none()
    if campaign is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found")

    await session.delete(campaign)
    await session.flush()
