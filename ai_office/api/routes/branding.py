"""Эндпоинты для управления брендингом."""

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_office.api.schemas import BrandingConfigResponse, BrandingConfigUpdate
from ai_office.core.branding import BrandingConfig
from ai_office.core.database import get_session
from ai_office.core.models import Workspace

router = APIRouter(prefix="/api/branding", tags=["branding"])


@router.get("", response_model=BrandingConfigResponse)
async def get_branding(
    session: AsyncSession = Depends(get_session),
):
    """Получить конфигурацию брендинга."""
    result = await session.execute(select(Workspace).limit(1))
    workspace = result.scalar_one_or_none()
    config = BrandingConfig.from_workspace(workspace)
    return BrandingConfigResponse(**config)


@router.patch("", response_model=BrandingConfigResponse)
async def update_branding(
    body: BrandingConfigUpdate,
    session: AsyncSession = Depends(get_session),
):
    """Обновить конфигурацию брендинга."""
    result = await session.execute(select(Workspace).limit(1))
    workspace = result.scalar_one_or_none()

    if workspace is None:
        # Create a default workspace for branding storage
        workspace = Workspace(
            telegram_chat_id=0,
            name="Default",
            owner_telegram_id=0,
        )
        session.add(workspace)
        await session.flush()

    updates = body.model_dump(exclude_none=True)
    BrandingConfig.update_workspace_branding(workspace, updates)
    await session.commit()
    await session.refresh(workspace)

    config = BrandingConfig.from_workspace(workspace)
    return BrandingConfigResponse(**config)
