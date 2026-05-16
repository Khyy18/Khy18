"""Tests for role-based access control."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from kindergarten_accountant_bot.utils.roles import (
    _parse_ids,
    get_user_roles,
    require_roles,
)


def test_parse_ids_empty():
    """Empty string returns empty set."""
    assert _parse_ids("") == set()
    assert _parse_ids("  ") == set()


def test_parse_ids_single():
    """Single ID parsed correctly."""
    assert _parse_ids("123") == {123}


def test_parse_ids_multiple():
    """Multiple comma-separated IDs parsed correctly."""
    assert _parse_ids("123,456,789") == {123, 456, 789}


def test_parse_ids_with_spaces():
    """IDs with surrounding spaces parsed correctly."""
    assert _parse_ids(" 123 , 456 , 789 ") == {123, 456, 789}


def test_parse_ids_invalid_ignored():
    """Non-numeric values are ignored."""
    assert _parse_ids("123,abc,456") == {123, 456}


@patch("kindergarten_accountant_bot.utils.roles.BOT_ADMIN_IDS", "100,200")
@patch("kindergarten_accountant_bot.utils.roles.BOT_CASHIER_IDS", "200,300")
@patch("kindergarten_accountant_bot.utils.roles.BOT_DIRECTOR_IDS", "400")
def test_get_user_roles_admin():
    """User 100 is admin only."""
    roles = get_user_roles(100)
    assert roles == {"admin"}


@patch("kindergarten_accountant_bot.utils.roles.BOT_ADMIN_IDS", "100,200")
@patch("kindergarten_accountant_bot.utils.roles.BOT_CASHIER_IDS", "200,300")
@patch("kindergarten_accountant_bot.utils.roles.BOT_DIRECTOR_IDS", "400")
def test_get_user_roles_multi():
    """User 200 is both admin and cashier."""
    roles = get_user_roles(200)
    assert roles == {"admin", "cashier"}


@patch("kindergarten_accountant_bot.utils.roles.BOT_ADMIN_IDS", "100")
@patch("kindergarten_accountant_bot.utils.roles.BOT_CASHIER_IDS", "200")
@patch("kindergarten_accountant_bot.utils.roles.BOT_DIRECTOR_IDS", "300")
def test_get_user_roles_unknown():
    """User 999 has no roles."""
    roles = get_user_roles(999)
    assert roles == set()


@pytest.mark.asyncio
@patch("kindergarten_accountant_bot.utils.roles.BOT_ADMIN_IDS", "100")
@patch("kindergarten_accountant_bot.utils.roles.BOT_CASHIER_IDS", "")
@patch("kindergarten_accountant_bot.utils.roles.BOT_DIRECTOR_IDS", "")
async def test_require_roles_allows_matching_role():
    """Handler is called if user has matching role."""
    handler = AsyncMock(return_value="ok")
    decorated = require_roles("admin")(handler)

    update = MagicMock()
    update.effective_chat.id = 100
    update.callback_query = None
    update.message = None
    context = MagicMock()

    result = await decorated(update, context)
    handler.assert_called_once()
    assert result == "ok"


@pytest.mark.asyncio
@patch("kindergarten_accountant_bot.utils.roles.BOT_ADMIN_IDS", "100")
@patch("kindergarten_accountant_bot.utils.roles.BOT_CASHIER_IDS", "")
@patch("kindergarten_accountant_bot.utils.roles.BOT_DIRECTOR_IDS", "")
async def test_require_roles_denies_non_matching():
    """Handler is NOT called if user lacks required role."""
    handler = AsyncMock(return_value="ok")
    decorated = require_roles("admin")(handler)

    update = MagicMock()
    update.effective_chat.id = 999
    update.callback_query = None
    update.message = AsyncMock()
    update.message.reply_text = AsyncMock()
    context = MagicMock()

    result = await decorated(update, context)
    handler.assert_not_called()
    assert result is None
    update.message.reply_text.assert_called_once()
    assert "нет доступа" in update.message.reply_text.call_args[0][0]


@pytest.mark.asyncio
@patch("kindergarten_accountant_bot.utils.roles.BOT_ADMIN_IDS", "")
@patch("kindergarten_accountant_bot.utils.roles.BOT_CASHIER_IDS", "")
@patch("kindergarten_accountant_bot.utils.roles.BOT_DIRECTOR_IDS", "")
async def test_require_roles_dev_mode_allows_all():
    """When no IDs are configured, everyone is allowed (dev mode)."""
    handler = AsyncMock(return_value="ok")
    decorated = require_roles("admin")(handler)

    update = MagicMock()
    update.effective_chat.id = 999
    context = MagicMock()

    result = await decorated(update, context)
    handler.assert_called_once()
    assert result == "ok"


@pytest.mark.asyncio
@patch("kindergarten_accountant_bot.utils.roles.BOT_ADMIN_IDS", "100")
@patch("kindergarten_accountant_bot.utils.roles.BOT_CASHIER_IDS", "200")
@patch("kindergarten_accountant_bot.utils.roles.BOT_DIRECTOR_IDS", "")
async def test_require_roles_callback_query_denied():
    """Denial message via callback_query.answer when update is callback-based."""
    handler = AsyncMock(return_value="ok")
    decorated = require_roles("admin")(handler)

    update = MagicMock()
    update.effective_chat.id = 200  # cashier, not admin
    update.callback_query = AsyncMock()
    update.callback_query.answer = AsyncMock()
    update.message = None
    context = MagicMock()

    await decorated(update, context)
    handler.assert_not_called()
    update.callback_query.answer.assert_called_once()
    call_kwargs = update.callback_query.answer.call_args
    assert call_kwargs.kwargs.get("show_alert") is True
