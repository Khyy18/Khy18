"""Admin panel handlers - restricted to ADMIN_CHAT_ID."""

import asyncio
import logging

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from bot.card_builder import _card, admin_stats_card, error_card, format_number, status_icon
from bot.keyboards import admin_keyboard
from config import config
from db.repository import (
    get_active_exchanges,
    get_daily_stats,
    get_failed_exchanges,
    get_stuck_exchanges,
    update_exchange,
)
from services.exchange_router import get_status
from services.changenow import ChangeNowError
from services.exolix import ExolixError

logger = logging.getLogger(__name__)

router = Router(name="admin")

# Maximum concurrent API checks for stuck exchanges
_MAX_CONCURRENT_CHECKS = 5
# Timeout per individual status check (seconds)
_CHECK_TIMEOUT = 10.0


def _is_admin(user_id: int) -> bool:
    """Check if user is admin."""
    return user_id == config.ADMIN_CHAT_ID


@router.message(Command("admin"))
async def cmd_admin(message: Message) -> None:
    """Show admin panel (restricted to ADMIN_CHAT_ID)."""
    if not message.from_user or not _is_admin(message.from_user.id):
        await message.answer(
            "\u26d4 Access denied.", parse_mode="HTML"
        )
        return

    await message.answer(
        "\U0001f6e0 <b>Admin Panel</b>",
        parse_mode="HTML",
        reply_markup=admin_keyboard(),
    )


@router.callback_query(F.data == "admin_stats")
async def on_admin_stats(callback: CallbackQuery) -> None:
    """Show daily exchange statistics."""
    if not _is_admin(callback.from_user.id):
        await callback.answer("Access denied", show_alert=True)
        return

    stats = await get_daily_stats()
    card = admin_stats_card(
        total_count=stats.get("total_count", 0),
        total_volume=stats.get("total_volume", 0.0),
        total_profit=stats.get("total_profit", 0.0),
        completed=stats.get("completed", 0),
        failed=stats.get("failed", 0),
    )
    await callback.message.edit_text(  # type: ignore[union-attr]
        card,
        parse_mode="HTML",
        reply_markup=admin_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data == "admin_active")
async def on_admin_active(callback: CallbackQuery) -> None:
    """Show active exchanges list."""
    if not _is_admin(callback.from_user.id):
        await callback.answer("Access denied", show_alert=True)
        return

    exchanges = await get_active_exchanges()
    if not exchanges:
        await callback.message.edit_text(  # type: ignore[union-attr]
            "\u2705 No active exchanges.",
            parse_mode="HTML",
            reply_markup=admin_keyboard(),
        )
        await callback.answer()
        return

    lines = []
    for ex in exchanges[:20]:
        icon = status_icon(ex["status"])
        lines.append(
            f"{icon} {ex['from_currency']}->{ex['to_currency']} "
            f"{format_number(ex['amount'])} [{ex['status']}]"
        )

    card = _card(
        f"Active Exchanges ({len(exchanges)})",
        "\U0001f504",
        lines,
    )
    await callback.message.edit_text(  # type: ignore[union-attr]
        card,
        parse_mode="HTML",
        reply_markup=admin_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data == "admin_failed")
async def on_admin_failed(callback: CallbackQuery) -> None:
    """Show failed exchanges list."""
    if not _is_admin(callback.from_user.id):
        await callback.answer("Access denied", show_alert=True)
        return

    exchanges = await get_failed_exchanges()
    if not exchanges:
        await callback.message.edit_text(  # type: ignore[union-attr]
            "\u2705 No failed exchanges.",
            parse_mode="HTML",
            reply_markup=admin_keyboard(),
        )
        await callback.answer()
        return

    lines = []
    for ex in exchanges[:20]:
        icon = status_icon(ex["status"])
        lines.append(
            f"{icon} {ex['from_currency']}->{ex['to_currency']} "
            f"{format_number(ex['amount'])} [{ex['status']}]"
        )

    card = _card(
        f"Failed Exchanges ({len(exchanges)})",
        "\u274c",
        lines,
    )
    await callback.message.edit_text(  # type: ignore[union-attr]
        card,
        parse_mode="HTML",
        reply_markup=admin_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data == "admin_stuck")
async def on_admin_stuck(callback: CallbackQuery) -> None:
    """Show stuck exchanges and offer to force-check them."""
    if not _is_admin(callback.from_user.id):
        await callback.answer("Access denied", show_alert=True)
        return

    exchanges = await get_stuck_exchanges(config.EXCHANGE_TIMEOUT_MINUTES)
    if not exchanges:
        await callback.message.edit_text(  # type: ignore[union-attr]
            "\u2705 No stuck exchanges.",
            parse_mode="HTML",
            reply_markup=admin_keyboard(),
        )
        await callback.answer()
        return

    lines = []
    for ex in exchanges[:20]:
        icon = status_icon(ex["status"])
        lines.append(
            f"{icon} ID:{ex.get('exchange_id', '?')} "
            f"{ex['from_currency']}->{ex['to_currency']} "
            f"[{ex['status']}]"
        )

    # Force-check stuck exchanges with concurrency limit and per-check timeout
    semaphore = asyncio.Semaphore(_MAX_CONCURRENT_CHECKS)

    async def _check_one(ex: dict) -> bool:
        """Check one exchange status. Returns True if updated."""
        exchange_id = ex.get("exchange_id")
        provider = ex.get("provider", "changenow")
        if not exchange_id:
            return False
        async with semaphore:
            try:
                status_data = await asyncio.wait_for(
                    get_status(exchange_id, provider),
                    timeout=_CHECK_TIMEOUT,
                )
                new_status = status_data["status"]
                if new_status != ex["status"]:
                    await update_exchange(ex["id"], status=new_status)
                    return True
            except (ChangeNowError, ExolixError, asyncio.TimeoutError):
                pass
        return False

    results = await asyncio.gather(
        *[_check_one(ex) for ex in exchanges], return_exceptions=True
    )
    checked = sum(1 for r in results if r is True)

    if checked:
        lines.append(f"")
        lines.append(f"\U0001f504 Updated {checked} exchange(s)")

    card = _card(
        f"Stuck Exchanges ({len(exchanges)})",
        "\u23f0",
        lines,
    )
    await callback.message.edit_text(  # type: ignore[union-attr]
        card,
        parse_mode="HTML",
        reply_markup=admin_keyboard(),
    )
    await callback.answer()
