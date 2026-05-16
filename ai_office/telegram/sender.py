"""Helper module for sending proactive messages to Telegram chat.

Uses a module-level shared Pyrogram Client to avoid creating a new
TLS connection + Telegram auth handshake per message.
"""

import asyncio
import logging

from pyrogram import Client

from ai_office.core.config import settings

logger = logging.getLogger(__name__)

# Shared long-lived client for proactive sends
_shared_client: Client | None = None
_client_lock = asyncio.Lock()


async def _get_shared_client() -> Client | None:
    """Get or create the shared Pyrogram client for proactive sends."""
    global _shared_client

    if not settings.telegram_bot_token or not settings.target_chat_id:
        logger.warning(
            "Telegram not configured (missing bot_token or target_chat_id). "
            "Skipping message send."
        )
        return None

    if not settings.telegram_api_id or not settings.telegram_api_hash:
        logger.warning(
            "Telegram not configured (missing api_id or api_hash). "
            "Skipping message send."
        )
        return None

    async with _client_lock:
        if _shared_client is None:
            _shared_client = Client(
                name="proactive_sender",
                api_id=settings.telegram_api_id,
                api_hash=settings.telegram_api_hash,
                bot_token=settings.telegram_bot_token,
                in_memory=True,
            )
            await _shared_client.start()
            logger.info("Shared proactive sender client started")
        return _shared_client


async def stop_shared_client() -> None:
    """Stop the shared client gracefully (call on shutdown)."""
    global _shared_client
    async with _client_lock:
        if _shared_client is not None:
            try:
                await _shared_client.stop()
            except Exception as e:
                logger.warning("Error stopping shared sender client: %s", str(e))
            _shared_client = None
            logger.info("Shared proactive sender client stopped")


async def send_to_chat(text: str) -> None:
    """Send a message to the target Telegram chat.

    Reuses a shared long-lived Pyrogram Client to avoid per-message
    connection overhead.

    Args:
        text: Message text to send
    """
    try:
        client = await _get_shared_client()
        if client is None:
            return

        await client.send_message(
            chat_id=settings.target_chat_id,
            text=text,
        )
        logger.info("Proactive message sent to chat %d", settings.target_chat_id)
    except Exception as e:
        logger.error("Failed to send Telegram message: %s", str(e))
        # Reset the client on connection errors so next call reconnects
        global _shared_client
        async with _client_lock:
            _shared_client = None
