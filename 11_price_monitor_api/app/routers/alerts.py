"""Alerts router - CRUD for price alerts."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Alert, User
from app.db.session import get_db
from app.middleware.auth import get_current_user
from app.schemas.alerts import AlertCreate, AlertOut, AlertToggle

router = APIRouter(prefix="/alerts", tags=["alerts"])


def _alert_to_out(alert: Alert) -> AlertOut:
    return AlertOut(
        id=str(alert.id),
        keyword=alert.keyword,
        maxPrice=alert.max_price,
        category=alert.category or "",
        active=alert.is_active,
        createdAt=alert.created_at.isoformat() if alert.created_at else "",
    )


@router.get("", response_model=list[AlertOut])
async def get_alerts(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Get all alerts for the current user."""
    result = await db.execute(
        select(Alert).where(Alert.user_id == user.id)
    )
    alerts = result.scalars().all()
    return [_alert_to_out(a) for a in alerts]


@router.post("", response_model=AlertOut, status_code=201)
async def create_alert(
    data: AlertCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Create a new alert."""
    alert = Alert(
        user_id=user.id,
        keyword=data.keyword,
        max_price=data.maxPrice,
        category=data.category or "",
        is_active=True,
    )
    db.add(alert)
    await db.commit()
    await db.refresh(alert)
    return _alert_to_out(alert)


@router.patch("/{alert_id}", response_model=AlertOut)
async def toggle_alert(
    alert_id: int,
    data: AlertToggle,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Toggle alert active status."""
    result = await db.execute(
        select(Alert).where(Alert.id == alert_id, Alert.user_id == user.id)
    )
    alert = result.scalar_one_or_none()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    alert.is_active = data.active
    await db.commit()
    await db.refresh(alert)
    return _alert_to_out(alert)


@router.delete("/{alert_id}", status_code=204)
async def delete_alert(
    alert_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Delete an alert."""
    result = await db.execute(
        select(Alert).where(Alert.id == alert_id, Alert.user_id == user.id)
    )
    alert = result.scalar_one_or_none()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    await db.delete(alert)
    await db.commit()
