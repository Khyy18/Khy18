import asyncio
import base64
import hashlib
import hmac
import json
import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Response
from fastapi.responses import RedirectResponse
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from core.db import get_session
from core.models import Event, EventType, Message, MessageStatus

logger = logging.getLogger(__name__)

# 1x1 transparent GIF (43 bytes)
_TRANSPARENT_GIF = (
    b"\x47\x49\x46\x38\x39\x61\x01\x00\x01\x00\x80\x00\x00"
    b"\xff\xff\xff\x00\x00\x00\x21\xf9\x04\x00\x00\x00\x00"
    b"\x00\x2c\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02"
    b"\x44\x01\x00\x3b"
)


def _compute_signature(payload: str, secret: str) -> str:
    """Compute HMAC-SHA256 signature for a payload."""
    return hmac.new(
        secret.encode(),
        payload.encode(),
        hashlib.sha256,
    ).hexdigest()


class EmailTracker:
    """Generates tracking URLs for email open/click tracking."""

    def __init__(self, tracking_base_url: str, secret: str = "") -> None:
        self._base_url = tracking_base_url.rstrip("/")
        self._secret = secret

    def _sign_payload(self, payload: str) -> str:
        """Sign a JSON payload string with HMAC-SHA256."""
        return hmac.new(
            self._secret.encode(),
            payload.encode(),
            hashlib.sha256,
        ).hexdigest()

    def generate_tracking_pixel_url(self, message_id: str) -> str:
        """Generate a tracking pixel URL for open tracking."""
        payload = json.dumps({"msg_id": message_id})
        sig = self._sign_payload(payload)
        token = base64.urlsafe_b64encode(payload.encode()).decode()
        return f"{self._base_url}/track/open/{token}?sig={sig}"

    def generate_click_url(self, message_id: str, original_url: str) -> str:
        """Generate a tracked click URL that records clicks and redirects."""
        payload = json.dumps({"msg_id": message_id, "url": original_url})
        sig = self._sign_payload(payload)
        token = base64.urlsafe_b64encode(payload.encode()).decode()
        return f"{self._base_url}/track/click/{token}?sig={sig}"


def _decode_and_verify_token(token: str, sig: str, secret: str) -> dict | None:
    """Decode a base64-encoded JSON token and verify its HMAC signature.

    Returns the decoded payload dict if valid, None otherwise.
    """
    try:
        padded = token + "=" * (-len(token) % 4)
        raw = base64.urlsafe_b64decode(padded)
        payload_str = raw.decode()
    except Exception:
        return None

    expected_sig = hmac.new(
        secret.encode(),
        payload_str.encode(),
        hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(expected_sig, sig):
        return None

    try:
        return json.loads(payload_str)
    except json.JSONDecodeError:
        return None


def _get_tracking_secret() -> str:
    """Get the tracking secret from settings (lazy import to avoid circular deps)."""
    from core.config import settings
    return settings.tracking_secret


router = APIRouter(prefix="/track")


@router.get("/open/{token}")
async def track_open(
    token: str,
    sig: str = "",
    session: AsyncSession = Depends(get_session),
) -> Response:
    """Record an email open event and return a 1x1 transparent GIF."""
    secret = _get_tracking_secret()
    data = _decode_and_verify_token(token, sig, secret)
    if data is None:
        logger.warning("Invalid or unsigned tracking open token")
        return Response(
            content=_TRANSPARENT_GIF,
            media_type="image/gif",
            headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
        )

    try:
        message_id = data["msg_id"]

        # Record open event
        event = Event(
            id=uuid.uuid4(),
            message_id=uuid.UUID(message_id),
            event_type=EventType.open,
            occurred_at=datetime.now(timezone.utc),
            meta={},
        )
        session.add(event)

        # Update message status to opened (only if currently 'sent')
        await session.execute(
            update(Message)
            .where(Message.id == uuid.UUID(message_id))
            .where(Message.status == MessageStatus.sent)
            .values(status=MessageStatus.opened)
        )
        await session.commit()
        logger.info("Tracked open for message %s", message_id)

        # Trigger score update (non-blocking)
        try:
            from agents.lead_scorer import trigger_score_update
            from core.db import _get_session_factory

            msg_result = await session.execute(
                select(Message.lead_id).where(Message.id == uuid.UUID(message_id))
            )
            lead_id_row = msg_result.scalar_one_or_none()
            if lead_id_row:
                asyncio.create_task(trigger_score_update(lead_id_row, _get_session_factory()))
        except Exception as exc:
            logger.debug("Score update trigger failed for open event (message %s): %s", message_id, exc)
    except Exception as exc:
        logger.error("Failed to track open: %s", str(exc))

    return Response(
        content=_TRANSPARENT_GIF,
        media_type="image/gif",
        headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
    )


@router.get("/click/{token}")
async def track_click(
    token: str,
    sig: str = "",
    session: AsyncSession = Depends(get_session),
) -> Response:
    """Record an email click event and redirect to the original URL."""
    secret = _get_tracking_secret()
    data = _decode_and_verify_token(token, sig, secret)
    if data is None:
        logger.warning("Invalid or unsigned tracking click token")
        return Response(status_code=400, content="Invalid token")

    original_url = data.get("url", "/")
    message_id = data.get("msg_id")

    try:
        if message_id:
            # Record click event
            event = Event(
                id=uuid.uuid4(),
                message_id=uuid.UUID(message_id),
                event_type=EventType.click,
                occurred_at=datetime.now(timezone.utc),
                meta={"url": original_url},
            )
            session.add(event)

            # Update message status to clicked
            await session.execute(
                update(Message)
                .where(Message.id == uuid.UUID(message_id))
                .where(
                    Message.status.in_([MessageStatus.sent, MessageStatus.opened])
                )
                .values(status=MessageStatus.clicked)
            )
            await session.commit()
            logger.info("Tracked click for message %s -> %s", message_id, original_url)

            # Trigger score update (non-blocking)
            try:
                from agents.lead_scorer import trigger_score_update
                from core.db import _get_session_factory

                msg_result = await session.execute(
                    select(Message.lead_id).where(Message.id == uuid.UUID(message_id))
                )
                lead_id_row = msg_result.scalar_one_or_none()
                if lead_id_row:
                    asyncio.create_task(trigger_score_update(lead_id_row, _get_session_factory()))
            except Exception as exc:
                logger.debug("Score update trigger failed for click event (message %s): %s", message_id, exc)
    except Exception as exc:
        logger.error("Failed to track click: %s", str(exc))

    return RedirectResponse(url=original_url, status_code=302)
