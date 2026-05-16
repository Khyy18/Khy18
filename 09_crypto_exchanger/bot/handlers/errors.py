"""Global error handler for the bot."""

import logging

from aiogram import Router
from aiogram.types import ErrorEvent

from bot.card_builder import error_card
from services.changenow import ChangeNowError
from services.exolix import ExolixError

logger = logging.getLogger(__name__)

router = Router(name="errors")


@router.error()
async def global_error_handler(event: ErrorEvent) -> bool:
    """Handle all unhandled exceptions in handlers.

    Shows user-friendly messages for known errors,
    logs details for unknown ones.
    """
    exception = event.exception
    update = event.update

    if isinstance(exception, (ChangeNowError, ExolixError)):
        # API provider errors - show technical break card
        logger.warning("Provider API error: %s", exception)
        if update and update.message:
            await update.message.answer(
                error_card(
                    "Service temporarily unavailable.\n"
                    "Our exchange providers are experiencing issues.\n"
                    "Please try again in a few minutes."
                ),
                parse_mode="HTML",
            )
        elif update and update.callback_query and update.callback_query.message:
            await update.callback_query.message.answer(  # type: ignore[union-attr]
                error_card(
                    "Service temporarily unavailable.\n"
                    "Please try again in a few minutes."
                ),
                parse_mode="HTML",
            )
        return True

    # Unknown errors - log and show generic message
    logger.exception("Unhandled error: %s", exception)
    if update and update.message:
        await update.message.answer(
            error_card("An unexpected error occurred.\nPlease try again later."),
            parse_mode="HTML",
        )
    elif update and update.callback_query and update.callback_query.message:
        await update.callback_query.message.answer(  # type: ignore[union-attr]
            error_card("An unexpected error occurred.\nPlease try again later."),
            parse_mode="HTML",
        )

    return True
