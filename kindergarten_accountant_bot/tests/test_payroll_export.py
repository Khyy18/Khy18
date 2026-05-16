"""Tests for payroll export handler."""

import io
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

from kindergarten_accountant_bot.handlers.payroll import payroll_export


def _make_update_and_context():
    """Create mock update and context for callback query handlers."""
    update = MagicMock()
    update.callback_query = AsyncMock()
    update.callback_query.answer = AsyncMock()
    update.callback_query.edit_message_text = AsyncMock()
    update.effective_chat.id = 123

    context = MagicMock()
    context.bot = MagicMock()
    context.bot.send_document = AsyncMock()

    return update, context


@pytest.mark.asyncio
async def test_payroll_export_empty_employees():
    """Test payroll export with no employees in database."""
    update, context = _make_update_and_context()

    with patch(
        "kindergarten_accountant_bot.handlers.payroll.get_employees",
        new_callable=AsyncMock,
        return_value=[],
    ):
        await payroll_export(update, context)

    update.callback_query.answer.assert_called_once()
    update.callback_query.edit_message_text.assert_called_once()
    call_args = update.callback_query.edit_message_text.call_args
    assert "Нет сотрудников" in call_args[0][0] or "Нет сотрудников" in call_args.kwargs.get("text", call_args[0][0])


@pytest.mark.asyncio
async def test_payroll_export_generates_excel():
    """Test payroll export generates Excel and sends document."""
    update, context = _make_update_and_context()

    mock_employees = [
        {"fio": "Иванова А.А.", "oklad": 30000, "rate": 1.0, "stazh_percent": 10, "category_percent": 5},
        {"fio": "Петрова Б.Б.", "oklad": 25000, "rate": 0.5, "stazh_percent": 0, "category_percent": 0},
    ]

    with patch(
        "kindergarten_accountant_bot.handlers.payroll.get_employees",
        new_callable=AsyncMock,
        return_value=mock_employees,
    ):
        await payroll_export(update, context)

    # Should have called answer and edit_message_text (summary card)
    update.callback_query.answer.assert_called_once()
    update.callback_query.edit_message_text.assert_called_once()

    # Should have sent a document
    context.bot.send_document.assert_called_once()
    send_call = context.bot.send_document.call_args
    assert send_call.kwargs["chat_id"] == 123
    assert send_call.kwargs["filename"] == "payroll.xlsx"

    # Verify the document is a valid xlsx (check PK signature)
    doc_buffer = send_call.kwargs["document"]
    assert isinstance(doc_buffer, io.BytesIO)
    doc_buffer.seek(0)
    header = doc_buffer.read(4)
    assert header == b"PK\x03\x04"  # ZIP/xlsx signature


@pytest.mark.asyncio
async def test_payroll_export_summary_card_content():
    """Test that summary card contains employee names."""
    update, context = _make_update_and_context()

    mock_employees = [
        {"fio": "Сидорова В.В.", "oklad": 40000, "rate": 1.0, "stazh_percent": 0, "category_percent": 0},
    ]

    with patch(
        "kindergarten_accountant_bot.handlers.payroll.get_employees",
        new_callable=AsyncMock,
        return_value=mock_employees,
    ):
        await payroll_export(update, context)

    call_args = update.callback_query.edit_message_text.call_args
    card_text = call_args[0][0] if call_args[0] else call_args.kwargs.get("text", "")
    assert "Сидорова В.В." in card_text
    assert "Ведомость" in card_text


@pytest.mark.asyncio
async def test_payroll_export_uses_defaults():
    """Test payroll export uses defaults when employee has no oklad/stazh."""
    update, context = _make_update_and_context()

    mock_employees = [
        {"fio": "Козлова Г.Г.", "rate": 1.0},  # No oklad, stazh, category
    ]

    with patch(
        "kindergarten_accountant_bot.handlers.payroll.get_employees",
        new_callable=AsyncMock,
        return_value=mock_employees,
    ):
        await payroll_export(update, context)

    # Should succeed without errors
    context.bot.send_document.assert_called_once()
    send_call = context.bot.send_document.call_args
    assert send_call.kwargs["filename"] == "payroll.xlsx"
