from __future__ import annotations
"""STT fallback: Deepgram primary with OpenAI Whisper API as fallback."""

import logging
import time
from typing import Any, Callable

import httpx

from channels.voice.stt import DeepgramSTT

logger = logging.getLogger(__name__)

OPENAI_TRANSCRIPTION_URL = "https://api.openai.com/v1/audio/transcriptions"

# Health thresholds
MAX_CONSECUTIVE_FAILURES = 3
COOLDOWN_SECONDS = 60.0


class FallbackSTT:
    """Speech-to-text with automatic failover from Deepgram to OpenAI Whisper.

    Primary: DeepgramSTT (real-time streaming).
    Fallback: OpenAI Whisper API (non-streaming batch mode).

    Tracks consecutive failures per provider. After MAX_CONSECUTIVE_FAILURES,
    marks the provider as unhealthy and uses fallback directly.
    Recovers after COOLDOWN_SECONDS.
    """

    def __init__(self, primary: DeepgramSTT, openai_api_key: str) -> None:
        self._primary = primary
        self._openai_api_key = openai_api_key

        # Health tracking
        self._primary_failures: int = 0
        self._primary_unhealthy_since: float | None = None

        # Fallback state
        self._in_fallback_mode: bool = False
        self._audio_buffer: bytearray = bytearray()
        self._on_transcript: Callable[[dict[str, Any]], None] | None = None
        self._language: str = "en"

    def _is_primary_healthy(self) -> bool:
        """Check if primary provider is healthy."""
        if self._primary_failures < MAX_CONSECUTIVE_FAILURES:
            return True
        if self._primary_unhealthy_since is not None:
            elapsed = time.time() - self._primary_unhealthy_since
            if elapsed >= COOLDOWN_SECONDS:
                self._primary_failures = 0
                self._primary_unhealthy_since = None
                return True
        return False

    def _record_primary_failure(self, error: str) -> None:
        """Record a primary provider failure."""
        self._primary_failures += 1
        if self._primary_failures >= MAX_CONSECUTIVE_FAILURES:
            self._primary_unhealthy_since = time.time()
        logger.warning(
            "STT fallback event: provider=deepgram, error=%s, "
            "consecutive_failures=%d",
            error,
            self._primary_failures,
        )

    def _record_primary_success(self) -> None:
        """Record a primary provider success."""
        self._primary_failures = 0
        self._primary_unhealthy_since = None

    @property
    def in_fallback_mode(self) -> bool:
        """Return whether currently operating in fallback (batch) mode."""
        return self._in_fallback_mode

    async def start_stream(
        self,
        language: str = "en",
        on_transcript: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        """Start a speech-to-text stream.

        Tries primary Deepgram streaming. On connection failure,
        falls back to batch mode (buffering audio for Whisper).
        """
        self._on_transcript = on_transcript
        self._language = language
        self._audio_buffer = bytearray()
        self._in_fallback_mode = False

        if self._is_primary_healthy():
            try:
                await self._primary.start_stream(
                    language=language, on_transcript=on_transcript
                )
                self._record_primary_success()
                return
            except Exception as exc:
                self._record_primary_failure(str(exc))

        # Fall back to batch mode
        self._in_fallback_mode = True
        logger.info(
            "STT operating in fallback batch mode (Whisper API), language=%s",
            language,
        )

    async def send_audio(self, audio_bytes: bytes) -> None:
        """Send audio data.

        In primary mode: forwards to Deepgram stream.
        In fallback mode: buffers audio for later batch transcription.
        """
        if self._in_fallback_mode:
            self._audio_buffer.extend(audio_bytes)
        else:
            try:
                await self._primary.send_audio(audio_bytes)
            except Exception as exc:
                # Connection lost mid-stream, switch to fallback
                self._record_primary_failure(str(exc))
                self._in_fallback_mode = True
                self._audio_buffer.extend(audio_bytes)
                logger.info("STT switched to fallback mode mid-stream")

    async def flush_batch(self) -> str:
        """Flush buffered audio to Whisper API and return transcript.

        Only applicable in fallback mode. Returns empty string if
        no audio buffered or not in fallback mode.
        """
        if not self._in_fallback_mode or not self._audio_buffer:
            return ""

        audio_data = bytes(self._audio_buffer)
        self._audio_buffer = bytearray()

        try:
            transcript = await self._transcribe_whisper(audio_data)
            if self._on_transcript and transcript:
                self._on_transcript({
                    "text": transcript,
                    "is_final": True,
                    "confidence": 0.9,
                })
            return transcript
        except Exception as exc:
            logger.error("Whisper transcription failed: %s", exc)
            return ""

    async def _transcribe_whisper(self, audio_data: bytes) -> str:
        """Transcribe audio using OpenAI Whisper API."""
        headers = {
            "Authorization": f"Bearer {self._openai_api_key}",
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            files = {
                "file": ("audio.wav", audio_data, "audio/wav"),
            }
            data = {
                "model": "whisper-1",
                "language": self._language,
            }
            response = await client.post(
                OPENAI_TRANSCRIPTION_URL,
                headers=headers,
                files=files,
                data=data,
            )
            if response.status_code != 200:
                raise RuntimeError(
                    f"Whisper API failed with status {response.status_code}"
                )
            result = response.json()
            return result.get("text", "")

    async def stop_stream(self) -> None:
        """Stop the STT stream."""
        if not self._in_fallback_mode:
            await self._primary.stop_stream()
        self._audio_buffer = bytearray()
        self._in_fallback_mode = False
