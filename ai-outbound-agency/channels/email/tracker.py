import base64
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


class EmailTracker:
    """Generates tracking URLs for email open/click tracking."""

    def __init__(self, tracking_base_url: str) -> None:
        self._base_url = tracking_base_url.rstrip("/")

    def generate_tracking_pixel_url(self, message_id: str) -> str:
        """Generate a tracking pixel URL for open tracking."""
        payload = json.dumps({"msg_id": message_id})
        token = base64.urlsafe_b64encode(payload.encode()).decode()
        return f"{self._base_url}/track/open/{token}"

    def generate_click_url(self, message_id: str, original_url: str) -> str:
        """Generate a tracked click URL that records clicks and redirects."""
        payload = json.dumps({"msg_id": message_id, "url": original_url})
        token = base64.urlsafe_b64encode(payload.encode()).decode()
        return f"{self._base_url}/track/click/{token}"


def _decode_token(token: str) -> dict:
    """Decode a base64-encoded JSON token."""
    padded = token + "=" * (-len(token) % 4)
    raw = base64.urlsafe_b64decode(padded)
    return json.loads(raw)


router = APIRouter(prefix="/track")


@router.get("/open/{token}")
async def track_open(
    token: str,
    session: AsyncSession = Depends(get_session),
) -> Response:
    """Record an email open event and return a 1x1 transparent GIF."""
    try:
        data = _decode_token(token)
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
    session: AsyncSession = Depends(get_session),
) -> RedirectResponse:
    """Record an email click event and redirect to the original URL."""
    original_url = "/"
    try:
        data = _decode_token(token)
        message_id = data["msg_id"]
        original_url = data["url"]

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
    except Exception as exc:
        logger.error("Failed to track click: %s", str(exc))

    return RedirectResponse(url=original_url, status_code=302)
