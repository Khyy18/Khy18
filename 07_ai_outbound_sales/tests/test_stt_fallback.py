"""Tests for the STT Fallback module."""

import time

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from channels.voice.stt_fallback import FallbackSTT, COOLDOWN_SECONDS


@pytest.fixture
def mock_primary():
    """Mock DeepgramSTT."""
    primary = MagicMock()
    primary.start_stream = AsyncMock()
    primary.send_audio = AsyncMock()
    primary.stop_stream = AsyncMock()
    primary.is_streaming = True
    return primary


@pytest.fixture
def fallback_stt(mock_primary):
    """Create FallbackSTT with mocked primary."""
    return FallbackSTT(
        primary=mock_primary,
        openai_api_key="test-openai-key",
    )


class TestPrimaryStreamSuccess:
    """Test that primary STT streaming works normally."""

    async def test_start_stream_uses_primary(self, fallback_stt, mock_primary):
        """When primary is healthy, should use Deepgram streaming."""
        await fallback_stt.start_stream(language="en")

        mock_primary.start_stream.assert_called_once()
        assert not fallback_stt.in_fallback_mode

    async def test_send_audio_forwards_to_primary(self, fallback_stt, mock_primary):
        """Audio should be forwarded to primary when streaming."""
        await fallback_stt.start_stream(language="en")
        await fallback_stt.send_audio(b"audio_data")

        mock_primary.send_audio.assert_called_once_with(b"audio_data")

    async def test_primary_success_resets_failures(self, fallback_stt, mock_primary):
        """Successful primary connection should reset failure count."""
        fallback_stt._primary_failures = 2
        await fallback_stt.start_stream(language="en")

        assert fallback_stt._primary_failures == 0


class TestFallbackToBatchMode:
    """Test fallback to Whisper batch mode on primary failure."""

    async def test_connection_failure_activates_fallback(self, fallback_stt, mock_primary):
        """When Deepgram connection fails, should activate batch mode."""
        mock_primary.start_stream = AsyncMock(
            side_effect=ConnectionError("WebSocket failed")
        )

        await fallback_stt.start_stream(language="en")

        assert fallback_stt.in_fallback_mode
        assert fallback_stt._primary_failures == 1

    async def test_unhealthy_primary_goes_to_fallback(self, fallback_stt):
        """When primary is unhealthy, should go straight to fallback mode."""
        fallback_stt._primary_failures = 3
        fallback_stt._primary_unhealthy_since = time.time()

        await fallback_stt.start_stream(language="en")

        assert fallback_stt.in_fallback_mode

    async def test_mid_stream_failure_switches_to_fallback(self, fallback_stt, mock_primary):
        """If primary fails mid-stream, should switch to buffer mode."""
        await fallback_stt.start_stream(language="en")

        # Simulate mid-stream failure
        mock_primary.send_audio = AsyncMock(
            side_effect=ConnectionError("Connection lost")
        )

        await fallback_stt.send_audio(b"audio_data")

        assert fallback_stt.in_fallback_mode
        assert fallback_stt._audio_buffer == bytearray(b"audio_data")


class TestAudioBuffering:
    """Test audio buffering in fallback mode."""

    async def test_audio_buffered_in_fallback_mode(self, fallback_stt, mock_primary):
        """In fallback mode, audio should be buffered."""
        mock_primary.start_stream = AsyncMock(
            side_effect=ConnectionError("Failed")
        )
        await fallback_stt.start_stream(language="en")

        await fallback_stt.send_audio(b"chunk1")
        await fallback_stt.send_audio(b"chunk2")

        assert fallback_stt._audio_buffer == bytearray(b"chunk1chunk2")

    async def test_flush_batch_sends_to_whisper(self, fallback_stt, mock_primary):
        """flush_batch should send buffered audio to Whisper API."""
        mock_primary.start_stream = AsyncMock(
            side_effect=ConnectionError("Failed")
        )
        await fallback_stt.start_stream(language="en")
        await fallback_stt.send_audio(b"audio_data")

        # Mock Whisper transcription
        fallback_stt._transcribe_whisper = AsyncMock(
            return_value="Hello world"
        )

        result = await fallback_stt.flush_batch()

        assert result == "Hello world"
        fallback_stt._transcribe_whisper.assert_called_once_with(b"audio_data")

    async def test_flush_batch_clears_buffer(self, fallback_stt, mock_primary):
        """After flush, buffer should be cleared."""
        mock_primary.start_stream = AsyncMock(
            side_effect=ConnectionError("Failed")
        )
        await fallback_stt.start_stream(language="en")
        await fallback_stt.send_audio(b"data")

        fallback_stt._transcribe_whisper = AsyncMock(return_value="text")
        await fallback_stt.flush_batch()

        assert fallback_stt._audio_buffer == bytearray()

    async def test_flush_batch_empty_when_not_fallback(self, fallback_stt, mock_primary):
        """flush_batch should return empty if not in fallback mode."""
        await fallback_stt.start_stream(language="en")

        result = await fallback_stt.flush_batch()
        assert result == ""

    async def test_flush_batch_calls_on_transcript(self, fallback_stt, mock_primary):
        """flush_batch should invoke the on_transcript callback."""
        transcript_results = []

        def on_transcript(data):
            transcript_results.append(data)

        mock_primary.start_stream = AsyncMock(
            side_effect=ConnectionError("Failed")
        )
        await fallback_stt.start_stream(language="en", on_transcript=on_transcript)
        await fallback_stt.send_audio(b"audio")

        fallback_stt._transcribe_whisper = AsyncMock(return_value="Hello")
        await fallback_stt.flush_batch()

        assert len(transcript_results) == 1
        assert transcript_results[0]["text"] == "Hello"
        assert transcript_results[0]["is_final"] is True


class TestHealthRecovery:
    """Test health recovery after cooldown."""

    async def test_recovery_after_cooldown(self, fallback_stt):
        """Primary should recover after cooldown period."""
        fallback_stt._primary_failures = 3
        fallback_stt._primary_unhealthy_since = time.time() - COOLDOWN_SECONDS - 1

        assert fallback_stt._is_primary_healthy()
        assert fallback_stt._primary_failures == 0
