"""Точка входа приложения AI Office.

Запуск Pyrogram client + FastAPI (uvicorn) параллельно через asyncio.
Graceful shutdown при получении SIGINT/SIGTERM.
"""

import asyncio
import signal

import uvicorn

from ai_office.api.main import app
from ai_office.core.database import engine
from ai_office.telegram.client import TelegramClient

shutdown_event = asyncio.Event()


async def run_api():
    """Запуск FastAPI через uvicorn с поддержкой graceful shutdown."""
    config = uvicorn.Config(app, host="0.0.0.0", port=8000, log_level="info")
    server = uvicorn.Server(config)
    server.should_exit = False
    task = asyncio.create_task(server.serve())
    await shutdown_event.wait()
    server.should_exit = True
    await task


async def run_telegram():
    """Запуск Telegram клиента с поддержкой graceful shutdown."""
    client = TelegramClient()
    await client.start()
    await shutdown_event.wait()
    await client.stop()


async def main():
    """Главная функция - параллельный запуск всех сервисов с graceful shutdown."""
    loop = asyncio.get_event_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, lambda: shutdown_event.set())

    await asyncio.gather(
        run_api(),
        run_telegram(),
        return_exceptions=True,
    )

    # Освобождение ресурсов
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
