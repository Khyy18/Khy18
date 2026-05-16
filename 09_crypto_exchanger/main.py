"""Main entry point for the Crypto Exchanger bot."""

import asyncio
import logging
import sys

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from bot.handlers import get_all_routers
from config import config
from db.models import init_db
from services.status_poller import poll_statuses

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)


async def on_startup(bot: Bot) -> None:
    """Actions on bot startup."""
    logger.info("Initializing database...")
    await init_db()
    logger.info("Database initialized")

    # Start status polling background task
    asyncio.create_task(poll_statuses(bot))
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


async def main() -> None:
    """Initialize and start the bot."""
    if not config.TELEGRAM_BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN is not set!")
        sys.exit(1)

    bot = Bot(
        token=config.TELEGRAM_BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher(storage=MemoryStorage())

    # Register all routers
    for r in get_all_routers():
        dp.include_router(r)

    # Register startup hook
    dp.startup.register(on_startup)

    logger.info("Starting bot...")
    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())


if __name__ == "__main__":
    asyncio.run(main())
