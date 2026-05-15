"""Tests for AI multi-turn conversation context."""

import pytest
from datetime import datetime, timedelta
from unittest.mock import patch

from backend.ai.router import _get_history, _update_history, _conversation_history, HISTORY_TIMEOUT_MINUTES


@pytest.fixture(autouse=True)
def clear_history():
    """Clear conversation history before each test."""
    _conversation_history.clear()
    yield
    _conversation_history.clear()


def test_get_history_unknown_chat_id():
    """Test that _get_history returns empty list for unknown chat_id."""
    result = _get_history(99999)
    assert result == []


def test_update_history_stores_messages():
    """Test that _update_history stores and retrieves messages."""
    _update_history(123, "Hello", "Hi there!")
    history = _get_history(123)
    assert len(history) == 2
    assert history[0] == {"role": "user", "content": "Hello"}
    assert history[1] == {"role": "assistant", "content": "Hi there!"}


def test_update_history_skips_zero_chat_id():
    """Test that chat_id=0 is not stored."""
    _update_history(0, "Hello", "Hi there!")
    assert 0 not in _conversation_history


def test_update_history_limits_messages():
    """Test that history is limited to HISTORY_MAX_MESSAGES pairs."""
    for i in range(10):
        _update_history(123, f"msg {i}", f"response {i}")

    history = _get_history(123)
    # Should keep only last 5 pairs = 10 items
    assert len(history) == 10
    # Last message should be the most recent
    assert history[-1]["content"] == "response 9"
    assert history[-2]["content"] == "msg 9"


def test_timeout_clears_history():
    """Test that 30-minute timeout clears history."""
    _update_history(123, "Hello", "Hi there!")

    # Manually set last_activity to 31 minutes ago
    _conversation_history[123]["last_activity"] = datetime.now() - timedelta(minutes=31)

    result = _get_history(123)
    assert result == []
    assert 123 not in _conversation_history


def test_multiple_chat_ids():
    """Test that different chat_ids have separate histories."""
    _update_history(100, "User A message", "Response to A")
    _update_history(200, "User B message", "Response to B")

    history_a = _get_history(100)
    history_b = _get_history(200)

    assert len(history_a) == 2
    assert len(history_b) == 2
    assert history_a[0]["content"] == "User A message"
    assert history_b[0]["content"] == "User B message"
