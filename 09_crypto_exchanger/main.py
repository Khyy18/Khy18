"""Main entry point for the Crypto Exchanger bot."""

import asyncio
import logging
import sys
from typing import Optional

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from bot.handlers import get_all_routers
from config import config
from db.models import init_db
from services.status_poller import poll_statuses
from services.changenow import close_session as close_changenow_session
from services.exolix import close_session as close_exolix_session

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)

# Hold a reference to the poller task so it is not garbage-collected
_poller_task: Optional[asyncio.Task] = None


def _poller_done_callback(task: asyncio.Task) -> None:
    """Log if the status poller task exits unexpectedly."""
    if task.cancelled():
        logger.warning("Status poller task was cancelled")
        return
    exc = task.exception()
    if exc:
        logger.error("Status poller task died with exception: %s", exc, exc_info=exc)


async def on_startup(bot: Bot) -> None:
    """Actions on bot startup."""
    global _poller_task

    logger.info("Initializing database...")
    await init_db()
    logger.info("Database initialized")

    # Start status polling background task and keep reference
    _poller_task = asyncio.create_task(poll_statuses(bot))
    _poller_task.add_done_callback(_poller_done_callback)
    logger.info("Status poller started")

    if config.ADMIN_CHAT_ID:
        try:
            await bot.send_message(
                config.ADMIN_CHAT_ID,
                "\U0001f7e2 <b>Bot started successfully!</b>",
                parse_mode="HTML",
            )
        except Exception:
            logger.warning("Could not notify admin about startup")


async def on_shutdown(bot: Bot) -> None:
    """Cleanup on bot shutdown."""
    global _poller_task

    # Cancel the poller task
    if _poller_task and not _poller_task.done():
        _poller_task.cancel()
        try:
            await _poller_task
        except asyncio.CancelledError:
            pass

    # Close shared aiohttp sessions
    await close_changenow_session()
    await close_exolix_session()
    logger.info("Cleanup complete")


async def main() -> None:
    """Initialize and start the bot."""
    if not config.TELEGRAM_BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN is not set!")
        sys.exit(1)

    # Validate API keys - warn but don't crash (fallback may still work)
    if not config.CHANGENOW_API_KEY:
        logger.warning(
            "CHANGENOW_API_KEY is not set - primary exchange provider will fail"
        )
    if not config.EXOLIX_API_KEY:
        logger.warning(
            "EXOLIX_API_KEY is not set - fallback exchange provider will fail"
        )

    bot = Bot(
        token=config.TELEGRAM_BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher(storage=MemoryStorage())

    # Register all routers
    for r in get_all_routers():
        dp.include_router(r)

    # Register startup and shutdown hooks
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)

    logger.info("Starting bot...")
    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())


if __name__ == "__main__":
    asyncio.run(main())
