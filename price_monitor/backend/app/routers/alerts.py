"""Alerts router - CRUD for price alerts."""
from __future__ import annotations


from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Alert, User
from app.db.session import get_db
from app.middleware.auth import get_current_user
from app.schemas.alerts import AlertCreate, AlertOut, AlertUpdate

router = APIRouter(prefix="/alerts", tags=["alerts"])

@router.get("", response_model=list[AlertOut])
async def get_alerts(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Get all alerts for the current user."""

    result = await db.execute(
        select(Alert).where(Alert.user_id == user.id).order_by(Alert.created_at.desc())
    )
    alerts = result.scalars().all()
    return [
        AlertOut(
            id=a.id,
            keyword=a.keyword,
            max_price=a.max_price,
            category=a.category,
            is_active=a.is_active,
            created_at=a.created_at.isoformat(),
        )
        for a in alerts
    ]

@router.post("", response_model=AlertOut)
async def create_alert(
    data: AlertCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Create a new price alert."""
    alert = Alert(
        user_id=user.id,
        keyword=data.keyword,
        max_price=data.max_price,
        category=data.category,
    )
    db.add(alert)
    await db.commit()
    await db.refresh(alert)
    return AlertOut(
        id=alert.id,
        keyword=alert.keyword,
        max_price=alert.max_price,
        category=alert.category,
        is_active=alert.is_active,
        created_at=alert.created_at.isoformat(),
    )

@router.put("/{alert_id}", response_model=AlertOut)
async def update_alert(
    alert_id: int,
    data: AlertUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Update an existing alert."""
    result = await db.execute(
        select(Alert).where(Alert.id == alert_id, Alert.user_id == user.id)
    )
    alert = result.scalar_one_or_none()
    if not alert:
        raise HTTPException(status_code=404, detail="Оповещение не найдено")

    if data.keyword is not None:
        alert.keyword = data.keyword
    if data.max_price is not None:
        alert.max_price = data.max_price
    if data.category is not None:
        alert.category = data.category
    if data.is_active is not None:
        alert.is_active = data.is_active

    await db.commit()
    await db.refresh(alert)
    return AlertOut(
        id=alert.id,
        keyword=alert.keyword,
        max_price=alert.max_price,
        category=alert.category,
        is_active=alert.is_active,
        created_at=alert.created_at.isoformat(),
    )

@router.delete("/{alert_id}")
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
        raise HTTPException(status_code=404, detail="Оповещение не найдено")
    await db.delete(alert)
    await db.commit()
    return {"ok": True}
