"""White-label branding settings endpoints."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.models import Tenant, User
from core.whitelabel import WhitelabelConfig, resolve_branding
from dashboard.auth import get_current_user

router = APIRouter(prefix="/api/whitelabel", tags=["whitelabel"])


async def _get_session():
    from core.db import get_session as _gs

    async for session in _gs():
        yield session


@router.get("/settings", response_model=WhitelabelConfig)
async def get_brand_settings(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(_get_session),
) -> WhitelabelConfig:
    """Return brand settings for the current tenant."""
    result = await session.execute(
        select(Tenant).where(Tenant.id == current_user.tenant_id)
    )
    tenant = result.scalar_one_or_none()
    if tenant is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found"
        )
    return resolve_branding(tenant.brand_settings)


@router.put("/settings", response_model=WhitelabelConfig)
async def update_brand_settings(
    data: WhitelabelConfig,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(_get_session),
) -> WhitelabelConfig:
    """Update brand settings for the current tenant."""
    result = await session.execute(
        select(Tenant).where(Tenant.id == current_user.tenant_id)
    )
    tenant = result.scalar_one_or_none()
    if tenant is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found"
        )
    tenant.brand_settings = data.model_dump()
    await session.flush()
    await session.refresh(tenant)
    return resolve_branding(tenant.brand_settings)


@router.get("/preview")
async def get_preview(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(_get_session),
) -> dict:
    """Return preview data for a branded email template."""
    result = await session.execute(
        select(Tenant).where(Tenant.id == current_user.tenant_id)
    )
    tenant = result.scalar_one_or_none()
    if tenant is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found"
        )
    branding = resolve_branding(tenant.brand_settings)
    return {
        "branding": branding.model_dump(),
        "sample_subject": f"Hello from {branding.company_name}",
        "sample_body": (
            f"<div style='color: {branding.primary_color};'>"
            f"<img src='{branding.logo_url}' alt='{branding.company_name}' />"
            f"<p>This is a preview of your branded email template.</p>"
            f"</div>"
        ),
    }
