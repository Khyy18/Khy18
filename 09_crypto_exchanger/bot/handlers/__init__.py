"""Bot handlers registration."""

from aiogram import Router

from bot.handlers.admin import router as admin_router
from bot.handlers.errors import router as errors_router
from bot.handlers.exchange import router as exchange_router
from bot.handlers.start import router as start_router
from bot.handlers.status import router as status_router


def get_all_routers() -> list[Router]:
    """Return all bot routers in priority order."""
    return [
        admin_router,
        start_router,
        exchange_router,
        status_router,
        errors_router,
    ]
