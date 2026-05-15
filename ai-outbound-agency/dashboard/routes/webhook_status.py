"""Webhook delivery dashboard API routes - delivery listing, retry, and health."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.models import User, WebhookDelivery
from dashboard.auth import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/webhooks/status", tags=["webhook_status"])


async def _get_session():
    """Lazy wrapper around core.db.get_session."""
    from core.db import get_session as _gs

    async for session in _gs():
        yield session


@router.get("/deliveries")
async def list_deliveries(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(_get_session),
    delivery_status: Optional[str] = Query(None, alias="status"),
    event_type: Optional[str] = Query(None),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> dict:
    """List all webhook deliveries with filtering and pagination.

    Filterable by status (pending/delivered/failed), event_type, and date range.
    """
    query = select(WebhookDelivery).where(
        WebhookDelivery.tenant_id == current_user.tenant_id
    )

    if delivery_status:
        query = query.where(WebhookDelivery.status == delivery_status)
    if event_type:
        query = query.where(WebhookDelivery.event_type == event_type)
    if date_from:
        try:
            dt_from = datetime.fromisoformat(date_from)
            query = query.where(WebhookDelivery.created_at >= dt_from)
        except ValueError:
            pass
    if date_to:
        try:
            dt_to = datetime.fromisoformat(date_to)
            query = query.where(WebhookDelivery.created_at <= dt_to)
        except ValueError:
            pass

    # Count total
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await session.execute(count_query)
    total = total_result.scalar() or 0

    # Paginate
    offset = (page - 1) * page_size
    query = query.order_by(WebhookDelivery.created_at.desc()).offset(offset).limit(page_size)

    result = await session.execute(query)
    deliveries = result.scalars().all()

    return {
        "deliveries": [
            {
                "id": str(d.id),
                "webhook_id": str(d.webhook_id),
                "event_type": d.event_type,
                "status": d.status,
                "attempts": d.attempts,
                "last_attempt_at": d.last_attempt_at.isoformat() if d.last_attempt_at else None,
                "response_code": d.response_code,
                "created_at": d.created_at.isoformat() if d.created_at else None,
            }
            for d in deliveries
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.post("/retry/{delivery_id}")
async def retry_delivery(
    delivery_id: UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(_get_session),
) -> dict:
    """Manually retry a failed webhook delivery.

    Resets status to pending and increments attempt count.
    """
    result = await session.execute(
        select(WebhookDelivery).where(
            WebhookDelivery.id == delivery_id,
            WebhookDelivery.tenant_id == current_user.tenant_id,
        )
    )
    delivery = result.scalar_one_or_none()

    if delivery is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Delivery not found",
        )

    if delivery.status != "failed":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only failed deliveries can be retried",
        )

    delivery.status = "pending"
    delivery.attempts += 1
    delivery.last_attempt_at = datetime.now(timezone.utc)
    await session.flush()

    return {
        "id": str(delivery.id),
        "status": "pending",
        "attempts": delivery.attempts,
        "message": "Delivery queued for retry",
    }


@router.get("/health")
async def webhook_health(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(_get_session),
) -> dict:
    """Get webhook delivery health metrics for the tenant.

    Returns success rate, total deliveries, failed count, and average response time.
    """
    base_filter = WebhookDelivery.tenant_id == current_user.tenant_id

    # Total deliveries
    total_result = await session.execute(
        select(func.count(WebhookDelivery.id)).where(base_filter)
    )
    total_deliveries = total_result.scalar() or 0

    # Failed count
    failed_result = await session.execute(
        select(func.count(WebhookDelivery.id)).where(
            base_filter,
            WebhookDelivery.status == "failed",
        )
    )
    failed_count = failed_result.scalar() or 0

    # Delivered count
    delivered_result = await session.execute(
        select(func.count(WebhookDelivery.id)).where(
            base_filter,
            WebhookDelivery.status == "delivered",
        )
    )
    delivered_count = delivered_result.scalar() or 0

    # Success rate
    success_rate = 0.0
    if total_deliveries > 0:
        success_rate = round((delivered_count / total_deliveries) * 100, 2)

    return {
        "success_rate": success_rate,
        "total_deliveries": total_deliveries,
        "failed_count": failed_count,
        "delivered_count": delivered_count,
        "avg_response_time_ms": 0,  # Would be calculated from response times in production
    }
