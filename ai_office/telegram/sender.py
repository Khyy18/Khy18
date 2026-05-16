"""Helper module for sending proactive messages to Telegram chat."""

import logging

from pyrogram import Client

from ai_office.core.config import settings

logger = logging.getLogger(__name__)


async def send_to_chat(text: str) -> None:
    """Send a message to the target Telegram chat.

    Creates a temporary Pyrogram Client to send the message.
    Handles gracefully if Telegram is not configured (logs warning).

    Args:
        text: Message text to send
    """
    if not settings.telegram_bot_token or not settings.target_chat_id:
        logger.warning(
            "Telegram not configured (missing bot_token or target_chat_id). "
            "Skipping message send."
        )
        return

    if not settings.telegram_api_id or not settings.telegram_api_hash:
        logger.warning(
            "Telegram not configured (missing api_id or api_hash). "
            "Skipping message send."
        )
        return

    try:
        async with Client(
            name="proactive_sender",
            api_id=settings.telegram_api_id,
            api_hash=settings.telegram_api_hash,
            bot_token=settings.telegram_bot_token,
            in_memory=True,
        ) as client:
            await client.send_message(
                chat_id=settings.target_chat_id,
                text=text,
            )
            logger.info("Proactive message sent to chat %d", settings.target_chat_id)
    except Exception as e:
        logger.error("Failed to send Telegram message: %s", str(e))
