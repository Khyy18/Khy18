"""Telegram Bot Runner - long-polling based runner for the client Telegram bot."""

from __future__ import annotations

import asyncio
import logging
from uuid import UUID

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from core.models import Tenant
from integrations.telegram_client_bot import TelegramClientBot

logger = logging.getLogger(__name__)


class TelegramBotRunner:
    """Long-polling runner for the multi-tenant Telegram client bot."""

    def __init__(self, bot: TelegramClientBot, session_factory: async_sessionmaker[AsyncSession]):
        """Initialize the bot runner.

        Args:
            bot: The TelegramClientBot instance.
            session_factory: Async session factory for database access.
        """
        self._bot = bot
        self._session_factory = session_factory
        self._offset = 0
        self._running = False
        self._tenant_cache: dict[str, UUID] = {}  # chat_id -> tenant_id mapping

    def start(self) -> None:
        """Set the running flag to True."""
        self._running = True

    def stop(self) -> None:
        """Set the running flag to False to stop the polling loop."""
        self._running = False

    async def _poll_updates(self) -> list[dict]:
        """Poll for updates from the Telegram Bot API using long-polling.

        Returns:
            List of update dicts from the Telegram API.
        """
        url = f"{self._bot._base_url}/getUpdates"
        params = {
            "offset": self._offset,
            "timeout": 30,
        }

        try:
            async with httpx.AsyncClient(timeout=40.0) as client:
                response = await client.get(url, params=params)
                data = response.json()
                if data.get("ok"):
                    return data.get("result", [])
                logger.warning("getUpdates error: %s", data.get("description"))
                return []
        except httpx.HTTPError as exc:
            logger.error("Failed to poll updates: %s", exc)
            return []

    async def _process_update(self, update: dict) -> None:
        """Route an update to the appropriate handler.

        Args:
            update: The update dict from the Telegram API.
        """
        if "callback_query" in update:
            await self._handle_callback(update["callback_query"])
        elif "message" in update:
            message = update["message"]
            text = message.get("text", "")
            if text.startswith("/"):
                await self._handle_command(message)

    async def _handle_command(self, message: dict) -> None:
        """Parse and dispatch a command message.

        Args:
            message: The message dict from the Telegram API.
        """
        chat_id = str(message["chat"]["id"])
        text = message.get("text", "").strip()

        # Parse command and arguments
        parts = text.split(maxsplit=1)
        command = parts[0].lower()
        args = parts[1] if len(parts) > 1 else ""

        # Remove @bot_username suffix if present
        if "@" in command:
            command = command.split("@")[0]

        # Resolve tenant
        tenant_id = await self._resolve_tenant(chat_id)
        if tenant_id is None:
            await self._bot.send_message(
                chat_id, "This chat is not linked to any tenant. Please configure your telegram_client_chat_id in tenant settings."
            )
            return

        # Dispatch commands
        if command == "/status":
            await self._bot.handle_status(chat_id, tenant_id)
        elif command == "/hot":
            await self._bot.handle_hot(chat_id, tenant_id)
        elif command == "/pending":
            await self._bot.handle_pending(chat_id, tenant_id)
        elif command == "/approve":
            if args:
                await self._bot.handle_approve(chat_id, tenant_id, args.strip())
            else:
                await self._bot.send_message(chat_id, "Usage: /approve <approval_id>")
        elif command == "/reject":
            if args:
                await self._bot.handle_reject(chat_id, tenant_id, args.strip())
            else:
                await self._bot.send_message(chat_id, "Usage: /reject <approval_id>")
        elif command == "/pause":
            if args:
                await self._bot.handle_pause(chat_id, tenant_id, args.strip())
            else:
                await self._bot.send_message(chat_id, "Usage: /pause <campaign_name>")
        elif command == "/resume":
            if args:
                await self._bot.handle_resume(chat_id, tenant_id, args.strip())
            else:
                await self._bot.send_message(chat_id, "Usage: /resume <campaign_name>")
        else:
            await self._bot.send_message(
                chat_id,
                "Unknown command. Available: /status, /hot, /pending, /approve, /reject, /pause, /resume",
            )

    async def _handle_callback(self, callback_query: dict) -> None:
        """Handle an inline button callback.

        Args:
            callback_query: The callback query dict from the Telegram API.
        """
        callback_id = callback_query["id"]
        data = callback_query.get("data", "")
        message = callback_query.get("message", {})
        chat_id = str(message.get("chat", {}).get("id", ""))

        if not chat_id:
            await self._bot.answer_callback_query(callback_id, "Error: no chat context.")
            return

        tenant_id = await self._resolve_tenant(chat_id)
        if tenant_id is None:
            await self._bot.answer_callback_query(callback_id, "Chat not linked to tenant.")
            return

        # Parse callback_data format: "action:id"
        if ":" in data:
            action, approval_id = data.split(":", 1)
            if action == "approve":
                await self._bot.handle_approve(chat_id, tenant_id, approval_id)
                await self._bot.answer_callback_query(callback_id, "Approved!")
            elif action == "reject":
                await self._bot.handle_reject(chat_id, tenant_id, approval_id)
                await self._bot.answer_callback_query(callback_id, "Rejected!")
            else:
                await self._bot.answer_callback_query(callback_id, "Unknown action.")
        else:
            await self._bot.answer_callback_query(callback_id, "Invalid callback data.")

    async def _resolve_tenant(self, chat_id: str) -> UUID | None:
        """Resolve which tenant a chat_id belongs to.

        Queries tenants where settings->>'telegram_client_chat_id' matches chat_id.
        Results are cached for performance.

        Args:
            chat_id: The Telegram chat ID string.

        Returns:
            The tenant UUID, or None if no tenant is linked.
        """
        if chat_id in self._tenant_cache:
            return self._tenant_cache[chat_id]

        async with self._session_factory() as session:
            # Query tenants whose settings contain this chat_id
            result = await session.execute(select(Tenant))
            tenants = result.scalars().all()

            for tenant in tenants:
                settings = tenant.settings or {}
                if settings.get("telegram_client_chat_id") == chat_id:
                    self._tenant_cache[chat_id] = tenant.id
                    return tenant.id

        return None

    async def run(self) -> None:
        """Main async loop - poll updates, process each, handle errors with exponential backoff."""
        self.start()
        backoff = 1
        max_backoff = 60

        logger.info("Telegram bot runner started")

        while self._running:
            try:
                updates = await self._poll_updates()

                if updates:
                    backoff = 1  # Reset backoff on successful poll with results
                    for update in updates:
                        update_id = update.get("update_id", 0)
                        if update_id >= self._offset:
                            self._offset = update_id + 1
                        try:
                            await self._process_update(update)
                        except Exception as exc:
                            logger.error("Error processing update %s: %s", update_id, exc)
                else:
                    # Empty result is normal for long-polling timeout
                    backoff = 1

            except Exception as exc:
                logger.error("Polling error (backoff=%ds): %s", backoff, exc)
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, max_backoff)


if __name__ == "__main__":
    import asyncio

    from core.config import settings
    from core.db import async_session_factory

    logging.basicConfig(level=logging.INFO)

    bot = TelegramClientBot(
        bot_token=settings.client_telegram_bot_token,
        session_factory=async_session_factory,
    )
    runner = TelegramBotRunner(bot=bot, session_factory=async_session_factory)
    asyncio.run(runner.run())
