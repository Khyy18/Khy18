"""Pagination utility for bot list views."""

from typing import List, Tuple

from telegram import InlineKeyboardButton


def paginate_items(
    items: list,
    page: int,
    page_size: int = 5,
    callback_prefix: str = "page",
) -> Tuple[list, List[List[InlineKeyboardButton]]]:
    """Return a slice of items for the current page and navigation buttons.

    Args:
        items: Full list of items to paginate.
        page: Current page number (0-indexed).
        page_size: Number of items per page.
        callback_prefix: Prefix for callback_data in navigation buttons.

    Returns:
        Tuple of (page_items, nav_buttons) where nav_buttons is a list of
        InlineKeyboardButton rows for prev/page indicator/next navigation.
    """
    total = len(items)
    total_pages = max(1, (total + page_size - 1) // page_size)

    # Clamp page to valid range
    page = max(0, min(page, total_pages - 1))

    start = page * page_size
    end = start + page_size
    page_items = items[start:end]

    # Build navigation row
    nav_buttons: List[List[InlineKeyboardButton]] = []
    if total_pages > 1:
        row = []
        if page > 0:
            row.append(
                InlineKeyboardButton(
                    "\u25c0 Назад",
                    callback_data=f"{callback_prefix}_{page - 1}",
                )
            )
        row.append(
            InlineKeyboardButton(
                f"{page + 1}/{total_pages}",
                callback_data=f"{callback_prefix}_noop",
            )
        )
        if page < total_pages - 1:
            row.append(
                InlineKeyboardButton(
                    "Вперёд \u25b6",
                    callback_data=f"{callback_prefix}_{page + 1}",
                )
            )
        nav_buttons.append(row)

    return page_items, nav_buttons
