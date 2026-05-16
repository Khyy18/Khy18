"""Role-based access control for bot commands."""

import functools
from typing import Callable, Set, Tuple

from telegram import Update
from telegram.ext import ContextTypes

from kindergarten_accountant_bot.config import (
    BOT_ADMIN_IDS,
    BOT_CASHIER_IDS,
    BOT_DIRECTOR_IDS,
)


def _parse_ids(env_value: str) -> Set[int]:
    """Parse comma-separated chat IDs from environment variable."""
    if not env_value.strip():
        return set()
    ids = set()
    for part in env_value.split(","):
        part = part.strip()
        if part.isdigit():
            ids.add(int(part))
    return ids


def get_admin_ids() -> Set[int]:
    return _parse_ids(BOT_ADMIN_IDS)


def get_cashier_ids() -> Set[int]:
    return _parse_ids(BOT_CASHIER_IDS)


def get_director_ids() -> Set[int]:
    return _parse_ids(BOT_DIRECTOR_IDS)


def get_user_roles(chat_id: int) -> Set[str]:
    """Return set of roles for the given chat_id."""
    roles = set()
    if chat_id in get_admin_ids():
        roles.add("admin")
    if chat_id in get_cashier_ids():
        roles.add("cashier")
    if chat_id in get_director_ids():
        roles.add("director")
    return roles


def _no_ids_configured() -> bool:
    """Check if no role IDs are configured (dev mode - allow all)."""
    return (
        not BOT_ADMIN_IDS.strip()
        and not BOT_CASHIER_IDS.strip()
        and not BOT_DIRECTOR_IDS.strip()
    )


def require_roles(*allowed_roles: str) -> Callable:
    """Decorator that restricts handler to users with specified roles.

    If no role IDs are configured at all (dev mode), access is allowed for everyone.
    """

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
            # Dev mode: if no IDs configured, allow all
            if _no_ids_configured():
                return await func(update, context, *args, **kwargs)

            chat_id = update.effective_chat.id
            user_roles = get_user_roles(chat_id)

            if user_roles.intersection(set(allowed_roles)):
                return await func(update, context, *args, **kwargs)

            # Access denied
            if update.callback_query:
                await update.callback_query.answer(
                    "У вас нет доступа к этой команде.", show_alert=True
                )
            elif update.message:
                await update.message.reply_text("У вас нет доступа к этой команде.")
            return None

        return wrapper

    return decorator
