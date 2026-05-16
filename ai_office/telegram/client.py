"""Telegram клиент на базе Pyrogram для AI Office."""

import asyncio

from pyrogram import Client, filters
from pyrogram.types import Message

from ai_office.core.config import settings
from ai_office.telegram.handlers import (
    handle_command,
    handle_grant_admin,
    handle_grant_viewer,
    handle_message,
    handle_revoke_admin,
    handle_start,
)


class TelegramClient:
    """Обертка над Pyrogram Client для AI Office.

    Инициализирует бота, регистрирует обработчики команд и сообщений,
    управляет жизненным циклом клиента.
    """

    def __init__(self) -> None:
        """Инициализация клиента с параметрами из конфигурации."""
        self.app = Client(
            name="ai_office_bot",
            api_id=settings.telegram_api_id,
            api_hash=settings.telegram_api_hash,
            bot_token=settings.telegram_bot_token,
            in_memory=True,
        )
        self._register_handlers()

    def _register_handlers(self) -> None:
        """Регистрация обработчиков сообщений и команд."""

        # Все команды для фильтрации
        all_commands = [
            "start", "agents", "tasks", "status",
            "grant_admin", "grant_viewer", "revoke_admin",
        ]

        @self.app.on_message(filters.command(["start"]))
        async def on_start(client: Client, message: Message) -> None:
            """Обработка /start - онбординг."""
            await handle_start(client, message)

        @self.app.on_message(filters.command(["grant_admin"]))
        async def on_grant_admin(client: Client, message: Message) -> None:
            """Обработка /grant_admin."""
            await handle_grant_admin(client, message)

        @self.app.on_message(filters.command(["grant_viewer"]))
        async def on_grant_viewer(client: Client, message: Message) -> None:
            """Обработка /grant_viewer."""
            await handle_grant_viewer(client, message)

        @self.app.on_message(filters.command(["revoke_admin"]))
        async def on_revoke_admin(client: Client, message: Message) -> None:
            """Обработка /revoke_admin."""
            await handle_revoke_admin(client, message)

        @self.app.on_message(filters.command(["agents", "tasks", "status"]))
        async def on_command(client: Client, message: Message) -> None:
            """Обработка команд бота."""
            await handle_command(client, message)

        @self.app.on_message(filters.text & ~filters.command(all_commands))
        async def on_message(client: Client, message: Message) -> None:
            """Обработка обычных текстовых сообщений."""
            # Имитация задержки для реалистичности
            await asyncio.sleep(0.5)
            await handle_message(client, message)

    async def start(self) -> None:
        """Запуск Telegram клиента."""
        await self.app.start()

    async def stop(self) -> None:
        """Остановка Telegram клиента."""
        await self.app.stop()

    async def run(self) -> None:
        """Запуск клиента в режиме polling (idle)."""
        await self.start()
        await asyncio.Event().wait()  # Бесконечное ожидание
