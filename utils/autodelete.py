"""Utility for scheduling auto-deletion of messages."""

import asyncio
import logging

from telegram import Message

logger = logging.getLogger(__name__)


def schedule_autodelete(message: Message, delay: int = 300) -> asyncio.Task:
    """Schedule a message for deletion after `delay` seconds.

    Args:
        message: Telegram message to delete.
        delay: Seconds to wait before deleting (default 300 = 5 minutes).

    Returns:
        The asyncio Task handling the deletion.
    """

    async def _delete_later():
        try:
            await asyncio.sleep(delay)
            await message.delete()
        except Exception as exc:
            logger.debug("Auto-delete failed (message may already be deleted): %s", exc)

    return asyncio.create_task(_delete_later())
