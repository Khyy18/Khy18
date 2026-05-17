"""External API endpoints for integrations (Zapier/Make/CRM)."""
from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from core.models import (
    ApiKey,
    Campaign,
    CampaignStatus,
    Event,
    Lead,
    LeadStatus,
    Message,
    Tenant,
    Webhook,
    _utcnow,
    _uuid,
)

router = APIRouter(prefix="/api/v1", tags=["integrations"])

# Module-level lazy-initialized Redis instance for rate limiting
_rate_limit_redis = None


async def _get_rate_limit_redis():
    """Get or create a shared Redis connection for rate limiting."""
    global _rate_limit_redis
    if _rate_limit_redis is None:
        import redis.asyncio as aioredis
        from core.config import settings

        _rate_limit_redis = aioredis.from_url(settings.redis_url)
    return _rate_limit_redis


async def _get_session():
    from core.db import get_session as _gs

    async for session in _gs():
        yield session


def _hash_api_key(key: str) -> str:
    """Hash an API key using SHA-256."""
    return hashlib.sha256(key.encode()).hexdigest()


async def get_api_key_tenant(
    x_api_key: str = Header(..., alias="X-API-Key"),
    session: AsyncSession = Depends(_get_session),
) -> Tenant:
    """Authenticate request via X-API-Key header.

    Looks up the hashed key in the ApiKey table and enforces rate limiting
    of 100 requests per minute via Redis.
    """
    key_hash = _hash_api_key(x_api_key)
    result = await session.execute(
        select(ApiKey).where(ApiKey.key_hash == key_hash, ApiKey.is_active == True)
    )
    api_key = result.scalar_one_or_none()
    if api_key is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or inactive API key",
        )

    # Rate limiting: 100 requests per minute
    try:
        redis_client = await _get_rate_limit_redis()
        rate_key = f"api_rate:{api_key.tenant_id}:{int(datetime.now(timezone.utc).timestamp()) // 60}"
        current = await redis_client.incr(rate_key)
        if current == 1:
            await redis_client.expire(rate_key, 60)
        if current > 100:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Rate limit exceeded: 100 requests per minute",
            )
    except HTTPException:
        raise
    except Exception:
        # If Redis is unavailable, allow the request through
        pass

    # Update last_used_at
    api_key.last_used_at = _utcnow()
    await session.flush()

    # Load tenant
    tenant_result = await session.execute(
        select(Tenant).where(Tenant.id == api_key.tenant_id)
    )
    tenant = tenant_result.scalar_one_or_none()
    if tenant is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Tenant not found",
        )
    return tenant


# ---------- Request/Response Schemas ----------


class LeadCreate(BaseModel):
    email: str
    first_name: str
    last_name: str
    company: str
    title: str
    linkedin_url: Optional[str] = None
    enrichment_data: Optional[dict] = None


class LeadBulkCreate(BaseModel):
    leads: list[LeadCreate] = Field(..., max_length=100)


class LeadStatusResponse(BaseModel):
    id: str
    status: str
    score: Optional[float] = None


class WebhookCreate(BaseModel):
    url: str
    events: list[str] = Field(default_factory=list)


class WebhookResponse(BaseModel):
    id: str
    url: str
    events: list[str]
    is_active: bool
    created_at: datetime


class EventResponse(BaseModel):
    id: str
    event_type: str
    occurred_at: datetime
    metadata: Optional[dict] = None


# ---------- Endpoints ----------


@router.post("/leads", status_code=status.HTTP_201_CREATED)
async def create_lead_via_api(
    data: LeadCreate,
    tenant: Tenant = Depends(get_api_key_tenant),
    session: AsyncSession = Depends(_get_session),
) -> dict:
    """Create a lead via API key authentication."""
    lead = Lead(
        tenant_id=tenant.id,
        email=data.email,
        first_name=data.first_name,
        last_name=data.last_name,
        company=data.company,
        title=data.title,
        linkedin_url=data.linkedin_url,
        enrichment_data=data.enrichment_data or {},
        status=LeadStatus.new,
    )
    session.add(lead)
    await session.flush()
    await session.refresh(lead)
    return {"id": str(lead.id), "email": lead.email, "status": lead.status.value}


@router.post("/leads/bulk", status_code=status.HTTP_201_CREATED)
async def bulk_create_leads(
    data: LeadBulkCreate,
    tenant: Tenant = Depends(get_api_key_tenant),
    session: AsyncSession = Depends(_get_session),
) -> dict:
    """Bulk create leads (max 100 per request)."""
    created = []
    for lead_data in data.leads:
        lead = Lead(
            tenant_id=tenant.id,
            email=lead_data.email,
            first_name=lead_data.first_name,
            last_name=lead_data.last_name,
            company=lead_data.company,
            title=lead_data.title,
            linkedin_url=lead_data.linkedin_url,
            enrichment_data=lead_data.enrichment_data or {},
            status=LeadStatus.new,
        )
        session.add(lead)
        created.append(lead)
    await session.flush()
    for lead in created:
        await session.refresh(lead)
    return {
        "created": len(created),
        "leads": [{"id": str(l.id), "email": l.email} for l in created],
    }


@router.get("/leads/{lead_id}/status", response_model=LeadStatusResponse)
async def get_lead_status(
    lead_id: UUID,
    tenant: Tenant = Depends(get_api_key_tenant),
    session: AsyncSession = Depends(_get_session),
) -> dict:
    """Get lead status and score."""
    result = await session.execute(
        select(Lead).where(Lead.id == lead_id, Lead.tenant_id == tenant.id)
    )
    lead = result.scalar_one_or_none()
    if lead is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found"
        )
    return {"id": str(lead.id), "status": lead.status.value, "score": lead.score}


@router.post("/campaigns/{campaign_id}/trigger")
async def trigger_campaign(
    campaign_id: UUID,
    tenant: Tenant = Depends(get_api_key_tenant),
    session: AsyncSession = Depends(_get_session),
) -> dict:
    """Trigger a campaign run."""
    result = await session.execute(
        select(Campaign).where(
            Campaign.id == campaign_id, Campaign.tenant_id == tenant.id
        )
    )
    campaign = result.scalar_one_or_none()
    if campaign is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found"
        )
    if campaign.status != CampaignStatus.active:
        campaign.status = CampaignStatus.active
        await session.flush()
    return {"id": str(campaign.id), "status": campaign.status.value, "triggered": True}


@router.get("/events")
async def get_events(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    tenant: Tenant = Depends(get_api_key_tenant),
    session: AsyncSession = Depends(_get_session),
) -> dict:
    """Get recent events (last 24h, paginated) for the authenticated tenant."""
    since = datetime.now(timezone.utc) - timedelta(hours=24)
    result = await session.execute(
        select(Event)
        .join(Message, Event.message_id == Message.id)
        .join(Campaign, Message.campaign_id == Campaign.id)
        .where(Campaign.tenant_id == tenant.id)
        .where(Event.occurred_at >= since)
        .order_by(Event.occurred_at.desc())
        .limit(limit)
        .offset(offset)
    )
    events = list(result.scalars().all())
    return {
        "events": [
            {
                "id": str(e.id),
                "event_type": e.event_type.value,
                "occurred_at": e.occurred_at.isoformat() if e.occurred_at else None,
                "metadata": e.meta,
            }
            for e in events
        ],
        "limit": limit,
        "offset": offset,
    }


@router.post("/webhooks", status_code=status.HTTP_201_CREATED)
async def register_webhook(
    data: WebhookCreate,
    tenant: Tenant = Depends(get_api_key_tenant),
    session: AsyncSession = Depends(_get_session),
) -> dict:
    """Register an outgoing webhook URL."""
    secret = secrets.token_hex(32)
    webhook = Webhook(
        tenant_id=tenant.id,
        url=data.url,
        events=data.events,
        secret=secret,
        is_active=True,
    )
    session.add(webhook)
    await session.flush()
    await session.refresh(webhook)
    return {
        "id": str(webhook.id),
        "url": webhook.url,
        "events": webhook.events,
        "secret": secret,
        "is_active": webhook.is_active,
    }


@router.delete("/webhooks/{webhook_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_webhook(
    webhook_id: UUID,
    tenant: Tenant = Depends(get_api_key_tenant),
    session: AsyncSession = Depends(_get_session),
) -> None:
    """Remove a webhook."""
    result = await session.execute(
        select(Webhook).where(
            Webhook.id == webhook_id, Webhook.tenant_id == tenant.id
        )
    )
    webhook = result.scalar_one_or_none()
    if webhook is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Webhook not found"
        )
    await session.delete(webhook)
    await session.flush()
