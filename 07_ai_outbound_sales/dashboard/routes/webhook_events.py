"""Webhook event log API routes - delivery event listing and detail."""

from __future__ import annotations

import logging
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.models import User, WebhookDelivery
from dashboard.auth import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/integrations/webhooks", tags=["webhook_events"])


async def _get_session():
    """Lazy wrapper around core.db.get_session."""
    from core.db import get_session as _gs

    async for session in _gs():
        yield session


@router.get("/events")
async def list_webhook_events(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(_get_session),
    event_type: Optional[str] = Query(None),
    delivery_status: Optional[str] = Query(None, alias="status"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> dict:
    """List webhook delivery events for the tenant.

    Filterable by event_type and status (pending, delivered, failed).
    """
    query = select(WebhookDelivery).where(
        WebhookDelivery.tenant_id == current_user.tenant_id
    )

    if event_type:
        query = query.where(WebhookDelivery.event_type == event_type)
    if delivery_status:
        query = query.where(WebhookDelivery.status == delivery_status)

    query = query.order_by(WebhookDelivery.created_at.desc()).offset(offset).limit(limit)

    result = await session.execute(query)
    events = result.scalars().all()

    return {
        "events": [
            {
                "id": str(e.id),
                "webhook_id": str(e.webhook_id),
                "event_type": e.event_type,
                "status": e.status,
                "attempts": e.attempts,
                "response_code": e.response_code,
                "last_attempt_at": e.last_attempt_at.isoformat() if e.last_attempt_at else None,
                "created_at": e.created_at.isoformat() if e.created_at else None,
            }
            for e in events
        ],
        "limit": limit,
        "offset": offset,
    }


@router.get("/events/{event_id}")
async def get_webhook_event(
    event_id: UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(_get_session),
) -> dict:
    """Get a single webhook delivery event with full detail."""
    result = await session.execute(
        select(WebhookDelivery).where(
            WebhookDelivery.id == event_id,
            WebhookDelivery.tenant_id == current_user.tenant_id,
        )
    )
    event = result.scalar_one_or_none()

    if event is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Webhook event not found",
        )

    return {
        "id": str(event.id),
        "webhook_id": str(event.webhook_id),
        "tenant_id": str(event.tenant_id),
        "event_type": event.event_type,
        "payload": event.payload,
        "status": event.status,
        "attempts": event.attempts,
        "response_code": event.response_code,
        "last_attempt_at": event.last_attempt_at.isoformat() if event.last_attempt_at else None,
        "created_at": event.created_at.isoformat() if event.created_at else None,
    }
