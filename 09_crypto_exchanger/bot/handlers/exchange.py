"""Exchange flow FSM handlers - full exchange creation process."""

import logging
import re
from typing import Any

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.card_builder import (
    _card,
    deposit_card,
    error_card,
    exchange_card,
    format_number,
)
from bot.keyboards import (
    confirm_keyboard,
    currency_keyboard,
    flow_keyboard,
    status_keyboard,
)
from bot.states import ExchangeStates
from db.repository import create_exchange, increment_user_stats, update_exchange
from services.exchange_router import create_exchange as api_create_exchange
from services.exchange_router import get_estimate, get_range
from services.exolix import ExolixError
from services.changenow import ChangeNowError

logger = logging.getLogger(__name__)

router = Router(name="exchange")

# Basic wallet address validation patterns
WALLET_PATTERNS = {
    "btc": re.compile(r"^(1|3|bc1)[a-zA-HJ-NP-Z0-9]{25,62}$"),
    "eth": re.compile(r"^0x[a-fA-F0-9]{40}$"),
    "trx": re.compile(r"^T[a-zA-HJ-NP-Z0-9]{33}$"),
    "ltc": re.compile(r"^(L|M|ltc1)[a-zA-HJ-NP-Z0-9]{25,62}$"),
    "sol": re.compile(r"^[1-9A-HJ-NP-Za-km-z]{32,44}$"),
}


def _validate_address(currency: str, address: str) -> bool:
    """Basic wallet address validation."""
    pattern = WALLET_PATTERNS.get(currency.lower())
    if pattern:
        return bool(pattern.match(address))
    # For currencies without specific patterns, basic length check
    return 10 <= len(address) <= 128


@router.message(Command("exchange"))
async def cmd_exchange(message: Message, state: FSMContext) -> None:
    """Start exchange flow - select source currency."""
    await state.clear()
    await state.set_state(ExchangeStates.select_from_currency)
    await message.answer(
        "\U0001f4b1 <b>Select source currency:</b>",
        parse_mode="HTML",
        reply_markup=currency_keyboard(page=0, prefix="from"),
    )


@router.callback_query(F.data.startswith("cur_from_"))
async def on_from_currency(callback: CallbackQuery, state: FSMContext) -> None:
    """Handle source currency selection."""
    currency = callback.data.split("_")[-1]  # type: ignore[union-attr]
    await state.update_data(from_currency=currency)
    await state.set_state(ExchangeStates.select_to_currency)

    await callback.message.edit_text(  # type: ignore[union-attr]
        f"\u2705 From: <b>{currency}</b>\n\n\U0001f4b1 <b>Select target currency:</b>",
        parse_mode="HTML",
        reply_markup=currency_keyboard(page=0, prefix="to"),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("cur_to_"))
async def on_to_currency(callback: CallbackQuery, state: FSMContext) -> None:
    """Handle target currency selection."""
    currency = callback.data.split("_")[-1]  # type: ignore[union-attr]
    data = await state.get_data()
    from_currency = data.get("from_currency", "???")

    if currency.lower() == from_currency.lower():
        await callback.answer("Source and target must be different!", show_alert=True)
        return

    await state.update_data(to_currency=currency)

    # Ask for rate type
    await callback.message.edit_text(  # type: ignore[union-attr]
        f"\u2705 Pair: <b>{from_currency} \u2192 {currency}</b>\n\n"
        f"\U0001f4ca <b>Select rate type:</b>",
        parse_mode="HTML",
        reply_markup=flow_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("flow_"))
async def on_flow_selected(callback: CallbackQuery, state: FSMContext) -> None:
    """Handle rate type selection, then ask for amount."""
    flow = callback.data.split("_", 1)[-1]  # type: ignore[union-attr]
    data = await state.get_data()
    from_currency = data.get("from_currency", "???")
    to_currency = data.get("to_currency", "???")

    await state.update_data(flow=flow)
    await state.set_state(ExchangeStates.enter_amount)

    # Try to get range limits
    range_info = ""
    try:
        limits = await get_range(from_currency, to_currency)
        min_amount = limits.get("minAmount")
        max_amount = limits.get("maxAmount")
        if min_amount:
            range_info = f"\n\U0001f4cf Min: {format_number(float(min_amount))} {from_currency}"
        if max_amount:
            range_info += f"\n\U0001f4cf Max: {format_number(float(max_amount))} {from_currency}"
    except Exception:
        pass

    flow_label = "\U0001f512 Fixed" if flow == "fixed-rate" else "\U0001f4a8 Float"
    await callback.message.edit_text(  # type: ignore[union-attr]
        f"\u2705 Pair: <b>{from_currency} \u2192 {to_currency}</b>\n"
        f"\u2705 Mode: <b>{flow_label}</b>{range_info}\n\n"
        f"\U0001f4b0 <b>Enter amount of {from_currency} to send:</b>",
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(ExchangeStates.enter_amount)
async def on_amount_entered(message: Message, state: FSMContext) -> None:
    """Handle amount input and show estimate."""
    text = (message.text or "").strip().replace(",", ".")
    try:
        amount = float(text)
        if amount <= 0:
            raise ValueError("Amount must be positive")
    except ValueError:
        await message.answer(
            error_card("Invalid amount. Please enter a positive number."),
            parse_mode="HTML",
        )
        return

    data = await state.get_data()
    from_currency = data.get("from_currency", "")
    to_currency = data.get("to_currency", "")
    flow = data.get("flow", "standard")

    # Get estimate
    try:
        estimate = await get_estimate(from_currency, to_currency, amount, flow)
    except (ChangeNowError, ExolixError):
        await message.answer(
            error_card(
                "Service temporarily unavailable.\n"
                "Please try again later or choose another pair."
            ),
            parse_mode="HTML",
        )
        return

    to_amount = estimate["toAmount"]
    provider = estimate["provider"]
    markup_amount = estimate["markupAmount"]
    rate_id = estimate.get("rateId")

    await state.update_data(
        amount=amount,
        estimated_amount=to_amount,
        provider=provider,
        markup_amount=markup_amount,
        rate_id=rate_id,
    )
    await state.set_state(ExchangeStates.enter_wallet)

    card = exchange_card(from_currency, to_currency, amount, to_amount, provider, flow)
    await message.answer(
        f"{card}\n\n\U0001f4dd <b>Enter your {to_currency.upper()} wallet address:</b>",
        parse_mode="HTML",
    )


@router.message(ExchangeStates.enter_wallet)
async def on_wallet_entered(message: Message, state: FSMContext) -> None:
    """Handle wallet address input and validate."""
    address = (message.text or "").strip()
    data = await state.get_data()
    to_currency = data.get("to_currency", "")

    if not _validate_address(to_currency, address):
        await message.answer(
            error_card(
                f"Invalid {to_currency.upper()} address format.\n"
                "Please check and re-enter your wallet address."
            ),
            parse_mode="HTML",
        )
        return

    await state.update_data(payout_address=address)
    await state.set_state(ExchangeStates.confirm_exchange)

    from_currency = data.get("from_currency", "")
    amount = data.get("amount", 0)
    estimated_amount = data.get("estimated_amount", 0)
    flow = data.get("flow", "standard")

    summary = _card(
        "Confirm Exchange",
        "\U0001f4cb",
        [
            f"Send:     {format_number(amount)} {from_currency.upper()}",
            f"Receive:  {format_number(estimated_amount)} {to_currency.upper()}",
            f"Address:  {address[:20]}...{address[-8:]}",
            f"Mode:     {'Fixed' if flow == 'fixed-rate' else 'Float'}",
        ],
        footer="\u2753 Confirm this exchange?",
    )

    await message.answer(summary, parse_mode="HTML", reply_markup=confirm_keyboard())


@router.callback_query(F.data == "confirm_yes", ExchangeStates.confirm_exchange)
async def on_confirm(callback: CallbackQuery, state: FSMContext) -> None:
    """Handle exchange confirmation - create exchange via API."""
    data = await state.get_data()
    from_currency = data.get("from_currency", "")
    to_currency = data.get("to_currency", "")
    amount = data.get("amount", 0)
    estimated_amount = data.get("estimated_amount", 0)
    payout_address = data.get("payout_address", "")
    provider = data.get("provider", "changenow")
    flow = data.get("flow", "standard")
    rate_id = data.get("rate_id")
    markup_amount = data.get("markup_amount", 0)

    await callback.message.edit_text(  # type: ignore[union-attr]
        "\u23f3 <b>Creating exchange...</b>",
        parse_mode="HTML",
    )

    try:
        result = await api_create_exchange(
            from_currency=from_currency,
            to_currency=to_currency,
            amount=amount,
            address=payout_address,
            flow=flow,
            rate_id=rate_id,
            provider=provider,
        )
    except (ChangeNowError, ExolixError):
        await callback.message.edit_text(  # type: ignore[union-attr]
            error_card(
                "Failed to create exchange.\n"
                "Please try again later."
            ),
            parse_mode="HTML",
        )
        await state.clear()
        await callback.answer()
        return

    exchange_id = result["id"]
    deposit_address = result.get("depositAddress", "")
    actual_provider = result.get("provider", provider)

    # Save to database
    user_id = callback.from_user.id
    row_id = await create_exchange(
        user_id=user_id,
        from_currency=from_currency,
        to_currency=to_currency,
        amount=amount,
        estimated_amount=estimated_amount,
        provider=actual_provider,
        payout_address=payout_address,
        markup_amount=markup_amount,
        fixed_rate_id=rate_id,
    )
    await update_exchange(
        row_id,
        exchange_id=exchange_id,
        deposit_address=deposit_address,
        status="waiting",
    )
    await increment_user_stats(user_id, amount)

    # Show deposit card
    card = deposit_card(from_currency, amount, deposit_address, exchange_id)
    await callback.message.edit_text(  # type: ignore[union-attr]
        card,
        parse_mode="HTML",
        reply_markup=status_keyboard(str(row_id)),
    )
    await state.clear()
    await callback.answer()


@router.callback_query(F.data == "confirm_no")
async def on_cancel_confirm(callback: CallbackQuery, state: FSMContext) -> None:
    """Handle exchange cancellation at confirmation step."""
    await state.clear()
    await callback.message.edit_text(  # type: ignore[union-attr]
        "\u274c Exchange cancelled.",
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data == "cancel_exchange")
async def on_cancel_exchange(callback: CallbackQuery, state: FSMContext) -> None:
    """Handle exchange cancellation at any step."""
    await state.clear()
    await callback.message.edit_text(  # type: ignore[union-attr]
        "\u274c Exchange cancelled.",
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("page_from_"))
async def on_page_from(callback: CallbackQuery, state: FSMContext) -> None:
    """Handle pagination for source currency selection."""
    page = int(callback.data.split("_")[-1])  # type: ignore[union-attr]
    await callback.message.edit_reply_markup(  # type: ignore[union-attr]
        reply_markup=currency_keyboard(page=page, prefix="from"),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("page_to_"))
async def on_page_to(callback: CallbackQuery, state: FSMContext) -> None:
    """Handle pagination for target currency selection."""
    page = int(callback.data.split("_")[-1])  # type: ignore[union-attr]
    await callback.message.edit_reply_markup(  # type: ignore[union-attr]
        reply_markup=currency_keyboard(page=page, prefix="to"),
    )
    await callback.answer()
