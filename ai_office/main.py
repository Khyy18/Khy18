"""Точка входа приложения AI Office.

Запуск Pyrogram client + FastAPI (uvicorn) параллельно через asyncio.
"""

import asyncio

import uvicorn

from ai_office.api.main import app
from ai_office.telegram.client import TelegramClient


async def run_api():
    """Запуск FastAPI через uvicorn в асинхронном режиме."""
    config = uvicorn.Config(app, host="0.0.0.0", port=8000, log_level="info")
    server = uvicorn.Server(config)
    await server.serve()


async def run_telegram():
    """Запуск Telegram клиента."""
    client = TelegramClient()
    await client.run()


async def main():
    """Главная функция - параллельный запуск всех сервисов."""
    await asyncio.gather(
        run_api(),
        run_telegram(),
    )


if __name__ == "__main__":
    asyncio.run(main())
