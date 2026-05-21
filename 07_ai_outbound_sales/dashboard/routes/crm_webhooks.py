"""CRM webhook management endpoints with user-auth based access."""

import hashlib
import hmac
import json
import secrets
from typing import AsyncGenerator, Optional
from urllib.parse import urlparse
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.models import User, Webhook
from dashboard.auth import get_current_user

router = APIRouter(prefix="/api/integrations", tags=["crm_webhooks"])


async def _get_session() -> AsyncGenerator[AsyncSession, None]:
    """Lazy wrapper around core.db.get_session to avoid import-time engine creation."""
    from core.db import get_session as _gs

    async for session in _gs():
        yield session


# ---------- Schemas ----------


class WebhookCreateRequest(BaseModel):
    url: str
    events: list[str] = Field(default_factory=list)
    template_type: Optional[str] = None


class WebhookCreateResponse(BaseModel):
    id: str
    url: str
    events: list[str]
    template_type: Optional[str] = None
    secret: str
    is_active: bool


class WebhookListItem(BaseModel):
    id: str
    url: str
    events: list[str]
    template_type: Optional[str] = None
    is_active: bool
    created_at: str


class TestWebhookResponse(BaseModel):
    status: str
    status_code: Optional[int] = None
    error: Optional[str] = None


# ---------- Endpoints ----------


@router.post("/webhooks", status_code=status.HTTP_201_CREATED, response_model=WebhookCreateResponse)
async def create_webhook(
    data: WebhookCreateRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(_get_session),
) -> dict:
    """Create a new webhook for the current tenant."""
    # Validate webhook URL: must be well-formed with http or https scheme
    parsed = urlparse(data.url)
    if parsed.scheme not in ("http", "https"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Webhook URL must use http:// or https:// scheme.",
        )
    if not parsed.netloc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Webhook URL must have a valid hostname.",
        )

    secret = secrets.token_hex(32)
    webhook = Webhook(
        tenant_id=current_user.tenant_id,
        url=data.url,
        events=data.events,
        template_type=data.template_type,
        secret=secret,
        is_active=True,
    )
    session.add(webhook)
    await session.flush()
    await session.refresh(webhook)
    return {
        "id": str(webhook.id),
        "url": webhook.url,
        "events": webhook.events or [],
        "template_type": webhook.template_type,
        "secret": secret,
        "is_active": webhook.is_active,
    }


@router.get("/webhooks", response_model=list[WebhookListItem])
async def list_webhooks(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(_get_session),
) -> list[dict]:
    """List all webhooks for the current tenant (without secrets)."""
    result = await session.execute(
        select(Webhook).where(Webhook.tenant_id == current_user.tenant_id)
    )
    webhooks = result.scalars().all()
    return [
        {
            "id": str(w.id),
            "url": w.url,
            "events": w.events or [],
            "template_type": w.template_type,
            "is_active": w.is_active,
            "created_at": w.created_at.isoformat() if w.created_at else "",
        }
        for w in webhooks
    ]


@router.delete("/webhooks/{webhook_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_webhook(
    webhook_id: UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(_get_session),
) -> None:
    """Delete a webhook belonging to the current tenant."""
    result = await session.execute(
        select(Webhook).where(
            Webhook.id == webhook_id,
            Webhook.tenant_id == current_user.tenant_id,
        )
    )
    webhook = result.scalar_one_or_none()
    if webhook is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Webhook not found",
        )
    await session.delete(webhook)
    await session.flush()


@router.post("/webhooks/{webhook_id}/test", response_model=TestWebhookResponse)
async def test_webhook(
    webhook_id: UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(_get_session),
) -> dict:
    """Send a test payload to the webhook URL and return the result."""
    result = await session.execute(
        select(Webhook).where(
            Webhook.id == webhook_id,
            Webhook.tenant_id == current_user.tenant_id,
        )
    )
    webhook = result.scalar_one_or_none()
    if webhook is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Webhook not found",
        )

    test_payload = {
        "event": "test",
        "data": {
            "lead": {
                "email": "test@example.com",
                "first_name": "Test",
                "last_name": "User",
                "company": "Test Corp",
            }
        },
    }

    body = json.dumps(test_payload)
    signature = hmac.new(
        webhook.secret.encode(),
        body.encode(),
        hashlib.sha256,
    ).hexdigest()

    headers = {
        "Content-Type": "application/json",
        "X-Webhook-Signature": signature,
        "X-Webhook-Event": "test",
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(webhook.url, content=body, headers=headers)
            return {
                "status": "delivered",
                "status_code": response.status_code,
            }
    except Exception as exc:
        return {
            "status": "failed",
            "error": str(exc),
        }
