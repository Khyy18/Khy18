"""Tests for the /audit command handler."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from kindergarten_accountant_bot.handlers.audit import audit_command


def _make_update_and_context():
    """Create mock update and context for command handlers."""
    update = MagicMock()
    update.message = AsyncMock()
    update.message.reply_text = AsyncMock()
    update.effective_chat.id = 100

    context = MagicMock()
    return update, context


@pytest.mark.asyncio
@patch("kindergarten_accountant_bot.utils.roles._no_ids_configured", return_value=True)
async def test_audit_command_success(mock_no_ids):
    """Test audit command fetches and displays entries."""
    update, context = _make_update_and_context()

    mock_entries = [
        {
            "id": 1,
            "timestamp": "2024-01-15 10:30:00",
            "user_id": "admin",
            "action": "CREATE",
            "entity_type": "employee",
            "entity_id": "1",
            "old_value": None,
            "new_value": "{}",
            "ip_address": "127.0.0.1",
        },
        {
            "id": 2,
            "timestamp": "2024-01-15 11:00:00",
            "user_id": "cashier",
            "action": "UPDATE",
            "entity_type": "salary",
            "entity_id": "2",
            "old_value": "{}",
            "new_value": "{}",
            "ip_address": "127.0.0.1",
        },
    ]

    mock_response = MagicMock()
    mock_response.json.return_value = mock_entries
    mock_response.raise_for_status = MagicMock()

    with patch("kindergarten_accountant_bot.handlers.audit.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        await audit_command(update, context)

    update.message.reply_text.assert_called_once()
    call_text = update.message.reply_text.call_args[0][0]
    assert "Журнал аудита" in call_text
    assert "CREATE" in call_text
    assert "employee" in call_text


@pytest.mark.asyncio
@patch("kindergarten_accountant_bot.utils.roles._no_ids_configured", return_value=True)
async def test_audit_command_empty(mock_no_ids):
    """Test audit command with no entries."""
    update, context = _make_update_and_context()

    mock_response = MagicMock()
    mock_response.json.return_value = []
    mock_response.raise_for_status = MagicMock()

    with patch("kindergarten_accountant_bot.handlers.audit.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        await audit_command(update, context)

    update.message.reply_text.assert_called_once()
    call_text = update.message.reply_text.call_args[0][0]
    assert "пуст" in call_text


@pytest.mark.asyncio
@patch("kindergarten_accountant_bot.utils.roles._no_ids_configured", return_value=True)
async def test_audit_command_backend_unavailable(mock_no_ids):
    """Test audit command when backend is unreachable."""
    update, context = _make_update_and_context()

    with patch("kindergarten_accountant_bot.handlers.audit.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=Exception("Connection refused"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        await audit_command(update, context)

    update.message.reply_text.assert_called_once()
    call_text = update.message.reply_text.call_args[0][0]
    assert "недоступен" in call_text
