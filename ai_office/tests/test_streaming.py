"""Tests for StreamingCallback - broadcasting LLM tokens via WebSocket."""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ai_office.core.streaming import StreamingCallback


@pytest.fixture
def callback():
    """Create a StreamingCallback instance for testing."""
    return StreamingCallback(agent_name="alice")


class TestStreamingCallbackInit:
    """Test StreamingCallback initialization."""

    def test_has_agent_name(self, callback):
        assert callback.agent_name == "alice"

    def test_has_message_id(self, callback):
        assert isinstance(callback.message_id, uuid.UUID)

    def test_buffer_starts_empty(self, callback):
        assert callback._buffer == []

    def test_unique_message_ids(self):
        cb1 = StreamingCallback(agent_name="alice")
        cb2 = StreamingCallback(agent_name="alice")
        assert cb1.message_id != cb2.message_id


class TestOnLlmNewToken:
    """Test on_llm_new_token accumulates buffer and broadcasts."""

    @pytest.mark.asyncio
    async def test_accumulates_buffer(self, callback):
        with patch("ai_office.core.streaming.broadcast_event", new_callable=AsyncMock):
            await callback.on_llm_new_token("Hello")
            await callback.on_llm_new_token(" world")
            assert callback._buffer == ["Hello", " world"]

    @pytest.mark.asyncio
    async def test_broadcasts_chunk_event(self, callback):
        with patch("ai_office.core.streaming.broadcast_event", new_callable=AsyncMock) as mock_broadcast:
            await callback.on_llm_new_token("Hi")

            mock_broadcast.assert_called_once_with(
                "agent_typing_chunk",
                {
                    "agent": "alice",
                    "chunk": "Hi",
                    "message_id": str(callback.message_id),
                },
            )

    @pytest.mark.asyncio
    async def test_broadcasts_each_token_separately(self, callback):
        with patch("ai_office.core.streaming.broadcast_event", new_callable=AsyncMock) as mock_broadcast:
            await callback.on_llm_new_token("A")
            await callback.on_llm_new_token("B")
            assert mock_broadcast.call_count == 2


class TestOnLlmEnd:
    """Test on_llm_end sends complete event with full text."""

    @pytest.mark.asyncio
    async def test_broadcasts_complete_event_from_response(self, callback):
        with patch("ai_office.core.streaming.broadcast_event", new_callable=AsyncMock) as mock_broadcast:
            # Mock LLMResult structure
            generation = MagicMock()
            generation.text = "Full response text"
            response = MagicMock()
            response.generations = [[generation]]

            await callback.on_llm_end(response)

            mock_broadcast.assert_called_once_with(
                "agent_response_complete",
                {
                    "agent": "alice",
                    "message_id": str(callback.message_id),
                    "full_text": "Full response text",
                },
            )

    @pytest.mark.asyncio
    async def test_falls_back_to_buffer_on_empty_response(self, callback):
        with patch("ai_office.core.streaming.broadcast_event", new_callable=AsyncMock) as mock_broadcast:
            # Accumulate buffer first
            callback._buffer = ["Hello", " ", "world"]

            # Mock LLMResult with no generations
            response = MagicMock()
            response.generations = []

            await callback.on_llm_end(response)

            mock_broadcast.assert_called_once_with(
                "agent_response_complete",
                {
                    "agent": "alice",
                    "message_id": str(callback.message_id),
                    "full_text": "Hello world",
                },
            )

    @pytest.mark.asyncio
    async def test_event_format_matches_spec(self, callback):
        with patch("ai_office.core.streaming.broadcast_event", new_callable=AsyncMock) as mock_broadcast:
            generation = MagicMock()
            generation.text = "test"
            response = MagicMock()
            response.generations = [[generation]]

            await callback.on_llm_end(response)

            call_args = mock_broadcast.call_args
            event_type = call_args[0][0]
            data = call_args[0][1]

            assert event_type == "agent_response_complete"
            assert "agent" in data
            assert "message_id" in data
            assert "full_text" in data
