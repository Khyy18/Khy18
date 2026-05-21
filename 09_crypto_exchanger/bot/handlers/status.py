"""/status command and status refresh handlers."""

import logging

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from bot.card_builder import error_card, status_card
from bot.keyboards import status_keyboard
from db.repository import get_exchange_by_id, get_user_active_exchanges
from services.exchange_router import get_status
from services.changenow import ChangeNowError
from services.exolix import ExolixError

logger = logging.getLogger(__name__)

router = Router(name="status")


@router.message(Command("status"))
async def cmd_status(message: Message) -> None:
    """Show user's active exchanges."""
    if not message.from_user:
        return

    exchanges = await get_user_active_exchanges(message.from_user.id)

    if not exchanges:
        await message.answer(
            "\U0001f4ad No active exchanges.\n\nUse /exchange to start a new one.",
            parse_mode="HTML",
        )
        return

    for ex in exchanges:
        card = status_card(
            exchange_id=ex.get("exchange_id", "N/A"),
            from_currency=ex["from_currency"],
            to_currency=ex["to_currency"],
            amount=ex["amount"],
            estimated=ex.get("estimated_amount", 0),
            status=ex["status"],
        )
        await message.answer(
            card,
            parse_mode="HTML",
            reply_markup=status_keyboard(str(ex["id"])),
        )


@router.callback_query(F.data.startswith("refresh_"))
async def on_refresh_status(callback: CallbackQuery) -> None:
    """Refresh exchange status on button click."""
    row_id_str = callback.data.split("_", 1)[-1]  # type: ignore[union-attr]
    try:
        row_id = int(row_id_str)
    except ValueError:
        await callback.answer("Invalid exchange ID")
        return

    exchange = await get_exchange_by_id(row_id)
    if not exchange:
        await callback.answer("Exchange not found")
        return

    exchange_id = exchange.get("exchange_id")
    provider = exchange.get("provider", "changenow")

    if exchange_id:
        try:
            status_data = await get_status(exchange_id, provider)
            new_status = status_data["status"]
            if new_status != exchange["status"]:
                from db.repository import update_exchange
                await update_exchange(row_id, status=new_status)
                exchange["status"] = new_status
        except (ChangeNowError, ExolixError):
            logger.warning("Failed to refresh status for %s", exchange_id)

    card = status_card(
        exchange_id=exchange.get("exchange_id", "N/A"),
        from_currency=exchange["from_currency"],
        to_currency=exchange["to_currency"],
        amount=exchange["amount"],
        estimated=exchange.get("estimated_amount", 0),
        status=exchange["status"],
    )

    await callback.message.edit_text(  # type: ignore[union-attr]
        card,
        parse_mode="HTML",
        reply_markup=status_keyboard(str(row_id)),
    )
    await callback.answer("Status updated")
