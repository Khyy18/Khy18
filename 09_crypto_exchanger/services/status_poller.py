"""Background task that polls active exchange statuses."""

import asyncio
import logging
from typing import Optional

from aiogram import Bot

from bot.card_builder import status_card
from bot.keyboards import status_keyboard
from config import config
from db.repository import get_active_exchanges, get_stuck_exchanges, update_exchange
from services.exchange_router import get_status
from services.changenow import ChangeNowError
from services.exolix import ExolixError
from services.rate_cache import rate_cache

logger = logging.getLogger(__name__)

# Statuses that indicate completion
FINAL_STATUSES = ("finished", "failed", "refunded")

# Status change messages for users
STATUS_MESSAGES = {
    "waiting": "\U0001f7e1 Waiting for your deposit...",
    "confirming": "\U0001f7e0 Deposit received, confirming...",
    "exchanging": "\U0001f535 Exchange in progress...",
    "sending": "\U0001f7e3 Sending funds to your wallet...",
    "finished": "\U0001f7e2 Exchange complete! Funds sent.",
    "failed": "\U0001f534 Exchange failed. Contact support.",
    "refunded": "\u26aa Refunded to original address.",
}


async def poll_statuses(bot: Bot) -> None:
    """Main polling loop - checks active exchanges every POLL_INTERVAL seconds."""
    logger.info("Status poller started (interval: %ds)", config.STATUS_POLL_INTERVAL)

    while True:
        try:
            await _check_all_active(bot)
        except Exception:
            logger.exception("Error in status polling loop")

        # Evict expired rate cache entries to prevent unbounded growth
        rate_cache.cleanup()

        await asyncio.sleep(config.STATUS_POLL_INTERVAL)


async def _check_all_active(bot: Bot) -> None:
    """Check all active exchanges and notify users on status changes."""
    exchanges = await get_active_exchanges()

    for ex in exchanges:
        exchange_id = ex.get("exchange_id")
        provider = ex.get("provider", "changenow")

        if not exchange_id:
            continue

        try:
            status_data = await get_status(exchange_id, provider)
            new_status = status_data["status"]
        except (ChangeNowError, ExolixError):
            logger.warning("Failed to poll status for %s", exchange_id)
            continue

        old_status = ex["status"]
        if new_status != old_status:
            # Update database
            await update_exchange(ex["id"], status=new_status)
            logger.info(
                "Exchange %s status: %s -> %s", exchange_id, old_status, new_status
            )

            # Notify user
            await _notify_user(bot, ex, new_status)

    # Check for stuck exchanges and alert admin
    await _check_stuck(bot)


async def _notify_user(
    bot: Bot, exchange: dict, new_status: str
) -> None:
    """Send status update notification to user."""
    user_id = exchange["user_id"]
    card = status_card(
        exchange_id=exchange.get("exchange_id", "N/A"),
        from_currency=exchange["from_currency"],
        to_currency=exchange["to_currency"],
        amount=exchange["amount"],
        estimated=exchange.get("estimated_amount", 0),
        status=new_status,
    )

    msg = STATUS_MESSAGES.get(new_status, f"Status updated: {new_status}")

    try:
        await bot.send_message(
            user_id,
            f"{msg}\n\n{card}",
            parse_mode="HTML",
            reply_markup=status_keyboard(str(exchange["id"])),
        )
    except Exception:
        logger.warning("Failed to notify user %d", user_id)


async def _check_stuck(bot: Bot) -> None:
    """Alert admin about stuck exchanges."""
    if not config.ADMIN_CHAT_ID:
        return

    stuck = await get_stuck_exchanges(config.EXCHANGE_TIMEOUT_MINUTES)
    if stuck:
        from bot.card_builder import _card, format_number, status_icon

        lines = []
        for ex in stuck[:10]:
            icon = status_icon(ex["status"])
            lines.append(
                f"{icon} {ex.get('exchange_id', '?')} "
                f"{ex['from_currency']}->{ex['to_currency']} "
                f"{format_number(ex['amount'])} [{ex['status']}]"
            )

        card = _card(
            f"\u26a0\ufe0f Stuck Exchanges ({len(stuck)})",
            "\u23f0",
            lines,
        )
        try:
            await bot.send_message(
                config.ADMIN_CHAT_ID,
                card,
                parse_mode="HTML",
            )
        except Exception:
            logger.warning("Failed to alert admin about stuck exchanges")
