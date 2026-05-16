"""Inline keyboard builders for the bot."""

from typing import Optional

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


POPULAR_CURRENCIES = [
    "BTC", "ETH", "USDT", "BNB", "SOL", "XRP", "ADA", "DOGE",
    "TRX", "LTC", "MATIC", "AVAX", "DOT", "LINK", "ATOM",
]

ITEMS_PER_PAGE = 15


def currency_keyboard(
    page: int = 0,
    prefix: str = "from",
    selected: Optional[str] = None,
) -> InlineKeyboardMarkup:
    """Build paginated currency selection keyboard.

    Args:
        page: Current page (0-indexed).
        prefix: Callback prefix ('from' or 'to').
        selected: Currently selected currency to highlight.
    """
    start = page * ITEMS_PER_PAGE
    end = start + ITEMS_PER_PAGE
    currencies = POPULAR_CURRENCIES[start:end]

    buttons: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []

    for cur in currencies:
        label = f"\u2705 {cur}" if cur == selected else cur
        row.append(
            InlineKeyboardButton(
                text=label,
                callback_data=f"cur_{prefix}_{cur}",
            )
        )
        if len(row) == 3:
            buttons.append(row)
            row = []

    if row:
        buttons.append(row)

    # Navigation buttons
    nav_row: list[InlineKeyboardButton] = []
    if page > 0:
        nav_row.append(
            InlineKeyboardButton(text="\u25c0 Back", callback_data=f"page_{prefix}_{page - 1}")
        )
    if end < len(POPULAR_CURRENCIES):
        nav_row.append(
            InlineKeyboardButton(text="Next \u25b6", callback_data=f"page_{prefix}_{page + 1}")
        )
    if nav_row:
        buttons.append(nav_row)

    # Cancel button
    buttons.append(
        [InlineKeyboardButton(text="\u274c Cancel", callback_data="cancel_exchange")]
    )

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def flow_keyboard() -> InlineKeyboardMarkup:
    """Build rate type selection keyboard."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="\U0001f4a8 Standard (floating)",
                    callback_data="flow_standard",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="\U0001f512 Fixed Rate",
                    callback_data="flow_fixed-rate",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="\u274c Cancel",
                    callback_data="cancel_exchange",
                ),
            ],
        ]
    )


def confirm_keyboard() -> InlineKeyboardMarkup:
    """Build exchange confirmation keyboard."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="\u2705 Confirm Exchange",
                    callback_data="confirm_yes",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="\u274c Cancel",
                    callback_data="confirm_no",
                ),
            ],
        ]
    )


def status_keyboard(exchange_id: str) -> InlineKeyboardMarkup:
    """Build status check keyboard."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="\U0001f504 Refresh Status",
                    callback_data=f"refresh_{exchange_id}",
                ),
            ],
        ]
    )


def admin_keyboard() -> InlineKeyboardMarkup:
    """Build admin panel keyboard."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="\U0001f4ca Daily Stats",
                    callback_data="admin_stats",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="\U0001f504 Active Exchanges",
                    callback_data="admin_active",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="\u274c Failed Exchanges",
                    callback_data="admin_failed",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="\u23f0 Stuck Exchanges",
                    callback_data="admin_stuck",
                ),
            ],
        ]
    )
