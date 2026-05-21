import asyncio
import email
import logging
import uuid
from datetime import datetime, timezone
from email.header import decode_header
from typing import Any, Callable

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from core.models import (
    ChannelType,
    Event,
    EventType,
    Lead,
    LeadStatus,
    Message,
    MessageDirection,
    MessageStatus,
)

logger = logging.getLogger(__name__)


def _decode_header_value(value: str | None) -> str:
    """Decode an email header value."""
    if not value:
        return ""
    decoded_parts = decode_header(value)
    result = []
    for part, charset in decoded_parts:
        if isinstance(part, bytes):
            result.append(part.decode(charset or "utf-8", errors="replace"))
        else:
            result.append(part)
    return "".join(result)


class InboxListener:
    """IMAP inbox listener that polls for replies and matches them to outbound messages."""

    def __init__(
        self,
        imap_host: str,
        imap_port: int,
        imap_user: str,
        imap_password: str,
        session_factory: Callable[..., Any],
    ) -> None:
        self._host = imap_host
        self._port = imap_port
        self._user = imap_user
        self._password = imap_password
        self._session_factory = session_factory
        self._running = False

    async def _connect(self) -> Any:
        """Connect to the IMAP server."""
        import aioimaplib

        imap = aioimaplib.IMAP4_SSL(host=self._host, port=self._port)
        await imap.wait_hello_from_server()
        await imap.login(self._user, self._password)
        await imap.select("INBOX")
        return imap

    async def _parse_message(self, raw_data: bytes) -> dict[str, Any]:
        """Parse raw email bytes into a structured dict."""
        msg = email.message_from_bytes(raw_data)

        # Extract body
        body = ""
        if msg.is_multipart():
            for part in msg.walk():
                content_type = part.get_content_type()
                if content_type == "text/plain":
                    payload = part.get_payload(decode=True)
                    if payload:
                        body = payload.decode("utf-8", errors="replace")
                    break
                elif content_type == "text/html" and not body:
                    payload = part.get_payload(decode=True)
                    if payload:
                        body = payload.decode("utf-8", errors="replace")
        else:
            payload = msg.get_payload(decode=True)
            if payload:
                body = payload.decode("utf-8", errors="replace")

        return {
            "from": _decode_header_value(msg.get("From")),
            "subject": _decode_header_value(msg.get("Subject")),
            "in_reply_to": msg.get("In-Reply-To", ""),
            "references": msg.get("References", ""),
            "message_id": msg.get("Message-ID", ""),
            "body": body,
        }

    async def _match_to_outbound(
        self, parsed: dict[str, Any], session: AsyncSession
    ) -> Message | None:
        """Try to match an inbound email to an outbound message."""
        # Match by In-Reply-To header against message_id in metadata
        in_reply_to = parsed.get("in_reply_to", "").strip()
        if in_reply_to:
            # Strip angle brackets for matching
            clean_id = in_reply_to.strip("<>")
            result = await session.execute(
                select(Message).where(
                    Message.direction == MessageDirection.outbound,
                    Message.meta["message_id_header"].astext == in_reply_to,
                )
            )
            outbound = result.scalars().first()
            if outbound:
                return outbound

            # Also try matching without angle brackets
            result = await session.execute(
                select(Message).where(
                    Message.direction == MessageDirection.outbound,
                    Message.meta["message_id_header"].astext == clean_id,
                )
            )
            outbound = result.scalars().first()
            if outbound:
                return outbound

        # Fallback: match by subject line (strip Re: prefix)
        subject = parsed.get("subject", "")
        clean_subject = subject
        for prefix in ("Re: ", "RE: ", "re: ", "Fwd: ", "FWD: "):
            if clean_subject.startswith(prefix):
                clean_subject = clean_subject[len(prefix):]

        if clean_subject:
            result = await session.execute(
                select(Message).where(
                    Message.direction == MessageDirection.outbound,
                    Message.subject == clean_subject,
                )
            )
            outbound = result.scalars().first()
            if outbound:
                return outbound

        return None

    async def poll_inbox(self) -> list[dict[str, Any]]:
        """Poll the inbox for unseen messages and match them to outbound messages.

        Returns a list of matched replies with lead_id, campaign_id, message_content,
        and original_message_id.
        """
        matched_replies: list[dict[str, Any]] = []

        try:
            imap = await self._connect()
        except Exception as exc:
            logger.error("Failed to connect to IMAP: %s", str(exc))
            return matched_replies

        try:
            # Search for unseen messages
            status, data = await imap.search("UNSEEN")
            if status != "OK" or not data[0]:
                await imap.logout()
                return matched_replies

            message_nums = data[0].split()
            logger.info("Found %d unseen messages", len(message_nums))

            for num in message_nums:
                try:
                    status, msg_data = await imap.fetch(num.decode(), "(RFC822)")
                    if status != "OK":
                        continue

                    # Extract raw email bytes from response
                    raw_email = None
                    for item in msg_data:
                        if isinstance(item, tuple) and len(item) == 2:
                            raw_email = item[1]
                            break

                    if raw_email is None:
                        continue

                    parsed = await self._parse_message(
                        raw_email if isinstance(raw_email, bytes) else raw_email.encode()
                    )

                    # Match to outbound message
                    async with self._session_factory() as session:
                        outbound = await self._match_to_outbound(parsed, session)
                        if outbound is None:
                            continue

                        # Create inbound Message record
                        inbound_msg = Message(
                            id=uuid.uuid4(),
                            lead_id=outbound.lead_id,
                            campaign_id=outbound.campaign_id,
                            channel=ChannelType.email,
                            direction=MessageDirection.inbound,
                            content=parsed["body"],
                            subject=parsed["subject"],
                            status=MessageStatus.sent,
                            sent_at=datetime.now(timezone.utc),
                            meta={
                                "from": parsed["from"],
                                "in_reply_to": parsed["in_reply_to"],
                                "original_message_id": str(outbound.id),
                            },
                        )
                        session.add(inbound_msg)

                        # Create reply event
                        reply_event = Event(
                            id=uuid.uuid4(),
                            message_id=outbound.id,
                            event_type=EventType.reply,
                            occurred_at=datetime.now(timezone.utc),
                            meta={"inbound_message_id": str(inbound_msg.id)},
                        )
                        session.add(reply_event)

                        # Update outbound message status
                        await session.execute(
                            update(Message)
                            .where(Message.id == outbound.id)
                            .values(status=MessageStatus.replied)
                        )

                        # Update lead status to replied
                        await session.execute(
                            update(Lead)
                            .where(Lead.id == outbound.lead_id)
                            .values(status=LeadStatus.replied)
                        )

                        await session.commit()

                        matched_replies.append({
                            "lead_id": str(outbound.lead_id),
                            "campaign_id": str(outbound.campaign_id),
                            "message_content": parsed["body"],
                            "original_message_id": str(outbound.id),
                        })

                        logger.info(
                            "Matched reply from %s to message %s",
                            parsed["from"],
                            str(outbound.id),
                        )
                except Exception as exc:
                    logger.error("Error processing message %s: %s", num, str(exc))
                    continue

        except Exception as exc:
            logger.error("Error polling inbox: %s", str(exc))
        finally:
            try:
                await imap.logout()
            except Exception:
                pass

        return matched_replies

    async def start_polling(self, interval_seconds: int = 60) -> None:
        """Start polling the inbox at regular intervals."""
        self._running = True
        logger.info("Starting inbox polling every %d seconds", interval_seconds)
        while self._running:
            try:
                replies = await self.poll_inbox()
                if replies:
                    logger.info("Processed %d replies", len(replies))
            except Exception as exc:
                logger.error("Polling error: %s", str(exc))
            await asyncio.sleep(interval_seconds)

    def stop_polling(self) -> None:
        """Stop the polling loop."""
        self._running = False
        logger.info("Inbox polling stopped")
