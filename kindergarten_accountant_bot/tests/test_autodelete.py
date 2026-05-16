"""Tests for auto-delete utility."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from kindergarten_accountant_bot.utils.autodelete import schedule_autodelete


@pytest.mark.asyncio
async def test_schedule_autodelete_calls_delete():
    """Message.delete() is called after the delay."""
    message = AsyncMock()
    message.delete = AsyncMock()

    task = schedule_autodelete(message, delay=0)
    await task

    message.delete.assert_called_once()


@pytest.mark.asyncio
async def test_schedule_autodelete_returns_task():
    """schedule_autodelete returns an asyncio Task."""
    message = AsyncMock()
    message.delete = AsyncMock()

    task = schedule_autodelete(message, delay=0)
    assert isinstance(task, asyncio.Task)
    await task


@pytest.mark.asyncio
async def test_schedule_autodelete_handles_exception():
    """If message.delete raises, the task does not propagate the error."""
    message = AsyncMock()
    message.delete = AsyncMock(side_effect=Exception("Forbidden"))

    task = schedule_autodelete(message, delay=0)
    # Should not raise
    await task


@pytest.mark.asyncio
async def test_schedule_autodelete_default_delay():
    """Default delay is 300 seconds (verified by checking the function signature)."""
    import inspect
    sig = inspect.signature(schedule_autodelete)
    assert sig.parameters["delay"].default == 300
