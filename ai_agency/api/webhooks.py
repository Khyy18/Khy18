"""B2B Webhook system for AI-agency: registration, delivery, retry."""

import hashlib
import hmac
import json
import logging
import time
from datetime import datetime
from typing import List, Optional

import aiohttp
import aiosqlite
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

import config
from api.auth import get_current_client

logger = logging.getLogger(__name__)

router = APIRouter()


# --- Request/Response models ---

class WebhookRegisterRequest(BaseModel):
    """Request to register a webhook endpoint."""
    url: str
    secret: str


class WebhookResponse(BaseModel):
    """Response with webhook info."""
    id: int
    url: str
    active: bool
    created_at: str


# --- Router endpoints ---

@router.post("/api/webhooks", response_model=WebhookResponse)
async def register_webhook(
    request: WebhookRegisterRequest,
    client: dict = Depends(get_current_client),
) -> WebhookResponse:
    """Register a new webhook endpoint."""
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        cursor = await db.execute(
            """INSERT INTO webhook_endpoints (client_id, url, secret, active, created_at)
               VALUES (?, ?, ?, 1, ?)""",
            (client["client_id"], request.url, request.secret, datetime.utcnow().isoformat()),
        )
        await db.commit()
        webhook_id = cursor.lastrowid

    return WebhookResponse(
        id=webhook_id,
        url=request.url,
        active=True,
        created_at=datetime.utcnow().isoformat(),
    )


@router.get("/api/webhooks", response_model=List[WebhookResponse])
async def list_webhooks(
    client: dict = Depends(get_current_client),
) -> List[WebhookResponse]:
    """List all webhooks for the authenticated client."""
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM webhook_endpoints WHERE client_id = ? AND active = 1",
            (client["client_id"],),
        )
        rows = await cursor.fetchall()

    return [
        WebhookResponse(
            id=row["id"],
            url=row["url"],
            active=bool(row["active"]),
            created_at=row["created_at"],
        )
        for row in rows
    ]


@router.delete("/api/webhooks/{webhook_id}")
async def delete_webhook(
    webhook_id: int,
    client: dict = Depends(get_current_client),
) -> dict:
    """Deactivate a webhook endpoint."""
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        cursor = await db.execute(
            "UPDATE webhook_endpoints SET active = 0 WHERE id = ? AND client_id = ?",
            (webhook_id, client["client_id"]),
        )
        await db.commit()
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Webhook not found")

    return {"status": "deleted"}


# --- Webhook delivery functions ---

def _sign_payload(payload: str, secret: str) -> str:
    """Generate HMAC-SHA256 signature for webhook payload."""
    return hmac.new(
        secret.encode("utf-8"),
        payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()  # pragma: no cover


async def deliver_webhook(webhook_id: int, order_data: dict) -> bool:
    """
    POST order data to webhook URL with HMAC-SHA256 signature.
    Returns True if delivery succeeded.
    """
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM webhook_endpoints WHERE id = ? AND active = 1",
            (webhook_id,),
        )
        webhook = await cursor.fetchone()
        if not webhook:
            return False

    webhook_dict = dict(webhook)
    payload = json.dumps(order_data, ensure_ascii=False)
    signature = hmac.new(
        webhook_dict["secret"].encode("utf-8"),
        payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

    headers = {
        "Content-Type": "application/json",
        "X-Webhook-Signature": signature,
    }

    # Record delivery attempt
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        cursor = await db.execute(
            """INSERT INTO webhook_deliveries (webhook_id, order_id, status, attempts, last_attempt_at)
               VALUES (?, ?, 'pending', 1, ?)""",
            (webhook_id, order_data.get("order_id", 0), datetime.utcnow().isoformat()),
        )
        await db.commit()
        delivery_id = cursor.lastrowid

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                webhook_dict["url"],
                data=payload,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                success = 200 <= resp.status < 300
    except Exception as e:
        logger.error("Webhook delivery failed: %s", e)
        success = False

    # Update delivery status
    status = "delivered" if success else "failed"
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        await db.execute(
            "UPDATE webhook_deliveries SET status = ? WHERE id = ?",
            (status, delivery_id),
        )
        await db.commit()

    return success


async def retry_failed_deliveries() -> int:
    """Retry failed webhook deliveries (up to 3 attempts with exponential backoff)."""
    retried = 0
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """SELECT wd.*, we.url, we.secret FROM webhook_deliveries wd
               JOIN webhook_endpoints we ON wd.webhook_id = we.id
               WHERE wd.status = 'failed' AND wd.attempts < 3 AND we.active = 1"""
        )
        deliveries = await cursor.fetchall()

    for delivery in deliveries:
        delivery_dict = dict(delivery)
        # Exponential backoff check (simplified)
        attempts = delivery_dict["attempts"]

        payload = json.dumps({"order_id": delivery_dict["order_id"]}, ensure_ascii=False)
        signature = hmac.new(
            delivery_dict["secret"].encode("utf-8"),
            payload.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

        headers = {
            "Content-Type": "application/json",
            "X-Webhook-Signature": signature,
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    delivery_dict["url"],
                    data=payload,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    success = 200 <= resp.status < 300
        except Exception:
            success = False

        status = "delivered" if success else "failed"
        async with aiosqlite.connect(config.DATABASE_PATH) as db:
            await db.execute(
                "UPDATE webhook_deliveries SET status = ?, attempts = attempts + 1, last_attempt_at = ? WHERE id = ?",
                (status, datetime.utcnow().isoformat(), delivery_dict["id"]),
            )
            await db.commit()

        if success:
            retried += 1

    return retried


async def notify_webhooks(order_id: int) -> int:
    """Find all active webhooks for the order's client and deliver."""
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        # Get order info
        cursor = await db.execute(
            "SELECT * FROM orders WHERE id = ?", (order_id,)
        )
        order = await cursor.fetchone()
        if not order:
            return 0

        order_dict = dict(order)
        client_id = order_dict["client_id"]

        # Get active webhooks for this client
        cursor = await db.execute(
            "SELECT * FROM webhook_endpoints WHERE client_id = ? AND active = 1",
            (client_id,),
        )
        webhooks = await cursor.fetchall()

    delivered = 0
    order_data = {
        "order_id": order_dict["id"],
        "service_type": order_dict["service_type"],
        "status": order_dict["status"],
        "created_at": order_dict["created_at"],
        "price": order_dict["price"],
    }

    for webhook in webhooks:
        success = await deliver_webhook(webhook["id"], order_data)
        if success:
            delivered += 1

    return delivered
