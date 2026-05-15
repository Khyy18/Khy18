"""Standalone entry point for the scheduler service in Docker."""

import asyncio
import logging

from telegram import Bot

import config
import logging_config
import scheduler

logging_config.setup_logging()
logger = logging.getLogger(__name__)


async def run_scheduler():
    """Run scheduler tasks as a standalone service."""
    logger.info("Starting standalone scheduler...")

    bot = Bot(token=config.TELEGRAM_BOT_TOKEN)

    # Start all scheduler tasks
    scheduler.start_scheduler(bot)

    # Keep running forever
    try:
        while True:
            await asyncio.sleep(3600)
    except asyncio.CancelledError:
        logger.info("Scheduler shutting down...")


if __name__ == "__main__":
    asyncio.run(run_scheduler())
