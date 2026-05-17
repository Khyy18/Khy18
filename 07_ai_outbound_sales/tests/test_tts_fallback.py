"""Tests for the TTS Fallback module."""

import time

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from channels.voice.tts_fallback import FallbackTTS, COOLDOWN_SECONDS


@pytest.fixture
def mock_primary():
    """Mock ElevenLabsTTS."""
    primary = MagicMock()

    async def _success_gen(text, output_format="ulaw_8000"):
        yield b"audio_chunk_1"
        yield b"audio_chunk_2"

    primary.synthesize = _success_gen
    return primary


@pytest.fixture
def fallback_tts(mock_primary):
    """Create FallbackTTS with mocked primary."""
    return FallbackTTS(
        primary=mock_primary,
        openai_api_key="test-openai-key",
    )


class TestPrimarySuccess:
    """Test that primary TTS works normally."""

    async def test_primary_success_yields_chunks(self, fallback_tts):
        """When primary works, should yield its audio chunks."""
        chunks = []
        async for chunk in fallback_tts.synthesize("Hello world"):
            chunks.append(chunk)

        assert len(chunks) == 2
        assert chunks[0] == b"audio_chunk_1"
        assert chunks[1] == b"audio_chunk_2"

    async def test_primary_success_resets_failure_count(self, fallback_tts):
        """Successful primary call should reset failure counter."""
        fallback_tts._primary_failures = 2

        chunks = []
        async for chunk in fallback_tts.synthesize("Hello"):
            chunks.append(chunk)

        assert len(chunks) > 0
        assert fallback_tts._primary_failures == 0


class TestPrimaryFailure:
    """Test that fallback is triggered on primary failure."""

    async def test_primary_failure_triggers_fallback(self, fallback_tts):
        """When primary fails, should use OpenAI TTS fallback."""

        async def _failing_gen(text, output_format="ulaw_8000"):
            raise RuntimeError("ElevenLabs API error")
            yield  # noqa: unreachable - makes this an async generator

        fallback_tts._primary.synthesize = _failing_gen

        # Mock the OpenAI fallback
        async def _fallback_gen(text, output_format="ulaw_8000"):
            yield b"openai_chunk_1"

        fallback_tts._synthesize_openai = _fallback_gen

        chunks = []
        async for chunk in fallback_tts.synthesize("Hello"):
            chunks.append(chunk)

        assert len(chunks) == 1
        assert chunks[0] == b"openai_chunk_1"
        assert fallback_tts._primary_failures == 1

    async def test_empty_response_triggers_fallback(self, fallback_tts):
        """When primary returns no chunks, should fall back."""

        async def _empty_gen(text, output_format="ulaw_8000"):
            return
            yield  # noqa: unreachable - makes this an async generator

        fallback_tts._primary.synthesize = _empty_gen

        async def _fallback_gen(text, output_format="ulaw_8000"):
            yield b"fallback_data"

        fallback_tts._synthesize_openai = _fallback_gen

        chunks = []
        async for chunk in fallback_tts.synthesize("Hello"):
            chunks.append(chunk)

        assert chunks == [b"fallback_data"]


class TestHealthRecovery:
    """Test health checking and recovery after cooldown."""

    async def test_unhealthy_after_consecutive_failures(self, fallback_tts):
        """After 3 consecutive failures, primary should be marked unhealthy."""
        fallback_tts._primary_failures = 3
        fallback_tts._primary_unhealthy_since = time.time()

        assert not fallback_tts._is_primary_healthy()

    async def test_recovery_after_cooldown(self, fallback_tts):
        """After cooldown period, primary should be healthy again."""
        fallback_tts._primary_failures = 3
        fallback_tts._primary_unhealthy_since = time.time() - COOLDOWN_SECONDS - 1

        assert fallback_tts._is_primary_healthy()
        assert fallback_tts._primary_failures == 0

    async def test_skips_unhealthy_primary(self, fallback_tts):
        """When primary is unhealthy, should go straight to fallback."""
        fallback_tts._primary_failures = 3
        fallback_tts._primary_unhealthy_since = time.time()

        async def _fallback_gen(text, output_format="ulaw_8000"):
            yield b"direct_fallback"

        fallback_tts._synthesize_openai = _fallback_gen

        chunks = []
        async for chunk in fallback_tts.synthesize("Hello"):
            chunks.append(chunk)

        assert chunks == [b"direct_fallback"]
