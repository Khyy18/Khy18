"""TTS fallback: ElevenLabs primary with OpenAI TTS as fallback."""

import logging
import time
from typing import AsyncGenerator

import httpx

from channels.voice.tts import ElevenLabsTTS

logger = logging.getLogger(__name__)

OPENAI_TTS_URL = "https://api.openai.com/v1/audio/speech"

# Health thresholds
MAX_CONSECUTIVE_FAILURES = 3
COOLDOWN_SECONDS = 60.0


class FallbackTTS:
    """Text-to-speech with automatic failover from ElevenLabs to OpenAI TTS.

    Tracks consecutive failures per provider. After MAX_CONSECUTIVE_FAILURES,
    marks the provider as unhealthy and uses fallback directly.
    Recovers after COOLDOWN_SECONDS.
    """

    def __init__(
        self,
        primary: ElevenLabsTTS,
        openai_api_key: str,
        circuit_breaker_registry=None,
    ) -> None:
        self._primary = primary
        self._openai_api_key = openai_api_key
        self._circuit_breaker_registry = circuit_breaker_registry

        # Health tracking
        self._primary_failures: int = 0
        self._primary_unhealthy_since: float | None = None
        self._fallback_failures: int = 0
        self._fallback_unhealthy_since: float | None = None

    def _is_primary_healthy(self) -> bool:
        """Check if primary provider is healthy."""
        if self._primary_failures < MAX_CONSECUTIVE_FAILURES:
            return True
        # Check cooldown
        if self._primary_unhealthy_since is not None:
            elapsed = time.time() - self._primary_unhealthy_since
            if elapsed >= COOLDOWN_SECONDS:
                # Reset and allow retry
                self._primary_failures = 0
                self._primary_unhealthy_since = None
                return True
        return False

    def _is_fallback_healthy(self) -> bool:
        """Check if fallback provider is healthy."""
        if self._fallback_failures < MAX_CONSECUTIVE_FAILURES:
            return True
        if self._fallback_unhealthy_since is not None:
            elapsed = time.time() - self._fallback_unhealthy_since
            if elapsed >= COOLDOWN_SECONDS:
                self._fallback_failures = 0
                self._fallback_unhealthy_since = None
                return True
        return False

    def _record_primary_failure(self, error: str, latency: float) -> None:
        """Record a primary provider failure."""
        self._primary_failures += 1
        if self._primary_failures >= MAX_CONSECUTIVE_FAILURES:
            self._primary_unhealthy_since = time.time()
        logger.warning(
            "TTS fallback event: provider=elevenlabs, error=%s, latency=%.3fs, "
            "consecutive_failures=%d",
            error,
            latency,
            self._primary_failures,
        )

    def _record_primary_success(self) -> None:
        """Record a primary provider success."""
        self._primary_failures = 0
        self._primary_unhealthy_since = None

    def _record_fallback_failure(self, error: str, latency: float) -> None:
        """Record a fallback provider failure."""
        self._fallback_failures += 1
        if self._fallback_failures >= MAX_CONSECUTIVE_FAILURES:
            self._fallback_unhealthy_since = time.time()
        logger.warning(
            "TTS fallback event: provider=openai, error=%s, latency=%.3fs, "
            "consecutive_failures=%d",
            error,
            latency,
            self._fallback_failures,
        )

    def _record_fallback_success(self) -> None:
        """Record a fallback provider success."""
        self._fallback_failures = 0
        self._fallback_unhealthy_since = None

    async def synthesize(
        self, text: str, output_format: str = "ulaw_8000"
    ) -> AsyncGenerator[bytes, None]:
        """Synthesize speech, falling back to OpenAI TTS on primary failure.

        Yields audio chunks as bytes.
        """
        # Try primary if healthy
        if self._is_primary_healthy():
            start = time.time()
            try:
                chunks_yielded = False
                async for chunk in self._primary.synthesize(text, output_format):
                    chunks_yielded = True
                    yield chunk
                if chunks_yielded:
                    self._record_primary_success()
                    return
                else:
                    # No chunks returned - treat as failure
                    latency = time.time() - start
                    self._record_primary_failure("empty_response", latency)
            except Exception as exc:
                latency = time.time() - start
                self._record_primary_failure(str(exc), latency)

        # Try fallback if healthy
        if self._is_fallback_healthy():
            start = time.time()
            try:
                async for chunk in self._synthesize_openai(text, output_format):
                    yield chunk
                self._record_fallback_success()
                return
            except Exception as exc:
                latency = time.time() - start
                self._record_fallback_failure(str(exc), latency)

        logger.error("Both TTS providers are unhealthy for text: %s", text[:50])

    async def _synthesize_openai(
        self, text: str, output_format: str = "ulaw_8000"
    ) -> AsyncGenerator[bytes, None]:
        """Synthesize speech using OpenAI TTS API.

        Streams the audio response from OpenAI.
        """
        # Map output format to OpenAI response format
        response_format = "pcm"
        if "mp3" in output_format:
            response_format = "mp3"
        elif "opus" in output_format:
            response_format = "opus"

        headers = {
            "Authorization": f"Bearer {self._openai_api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": "tts-1",
            "voice": "alloy",
            "input": text,
            "response_format": response_format,
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            async with client.stream("POST", OPENAI_TTS_URL, json=payload, headers=headers) as response:
                if response.status_code != 200:
                    raise RuntimeError(
                        f"OpenAI TTS failed with status {response.status_code}"
                    )
                async for chunk in response.aiter_bytes(chunk_size=1024):
                    if chunk:
                        yield chunk
