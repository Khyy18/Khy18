import asyncio
import json
import logging
import time
from typing import Any, Callable

import websockets

logger = logging.getLogger(__name__)

DEEPGRAM_WS_URL = "wss://api.deepgram.com/v1/listen"
SILENCE_THRESHOLD_SECONDS = 1.5

# Maps country codes / locales to Deepgram language codes
LANGUAGE_MAP: dict[str, str] = {
    "US": "en",
    "GB": "en",
    "AU": "en",
    "CA": "en",
    "RU": "ru",
    "DE": "de",
    "AT": "de",
    "CH": "de",
    "ES": "es",
    "MX": "es",
    "AR": "es",
    "CO": "es",
}


class DeepgramSTT:
    """Real-time speech-to-text using Deepgram streaming WebSocket API."""

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key
        self._ws: Any = None
        self._on_transcript: Callable[[dict[str, Any]], None] | None = None
        self._listener_task: asyncio.Task[None] | None = None
        self._last_final_time: float = 0.0
        self._is_streaming: bool = False

    @property
    def is_streaming(self) -> bool:
        return self._is_streaming

    @property
    def silence_duration(self) -> float:
        """Seconds since last final transcript. Returns 0 if no finals received."""
        if self._last_final_time == 0.0:
            return 0.0
        return time.time() - self._last_final_time

    @property
    def is_turn_end(self) -> bool:
        """True if silence exceeds the turn-end threshold."""
        return self.silence_duration > SILENCE_THRESHOLD_SECONDS

    async def start_stream(
        self, language: str = "en", on_transcript: Callable[[dict[str, Any]], None] | None = None
    ) -> None:
        """Open a streaming connection to Deepgram."""
        self._on_transcript = on_transcript
        self._last_final_time = 0.0

        url = (
            f"{DEEPGRAM_WS_URL}"
            f"?language={language}"
            f"&punctuate=true"
            f"&interim_results=true"
            f"&encoding=mulaw"
            f"&sample_rate=8000"
        )
        headers = {"Authorization": f"Token {self._api_key}"}

        self._ws = await websockets.connect(url, extra_headers=headers)
        self._is_streaming = True
        self._listener_task = asyncio.create_task(self._listen())

    async def send_audio(self, audio_bytes: bytes) -> None:
        """Send an audio chunk to the Deepgram stream."""
        if self._ws and self._is_streaming:
            await self._ws.send(audio_bytes)

    async def stop_stream(self) -> None:
        """Close the streaming connection."""
        self._is_streaming = False
        if self._ws:
            try:
                await self._ws.close()
            except Exception:
                pass
            self._ws = None
        if self._listener_task and not self._listener_task.done():
            self._listener_task.cancel()
            try:
                await self._listener_task
            except asyncio.CancelledError:
                pass
            self._listener_task = None

    async def _listen(self) -> None:
        """Listen for transcript results from Deepgram."""
        try:
            async for message in self._ws:
                if not self._is_streaming:
                    break
                try:
                    data = json.loads(message)
                    self._handle_transcript(data)
                except (json.JSONDecodeError, KeyError):
                    continue
        except websockets.ConnectionClosed:
            logger.debug("Deepgram WebSocket connection closed")
        except Exception as e:
            logger.error("Deepgram listener error: %s", e)
        finally:
            self._is_streaming = False

    def _handle_transcript(self, result: dict[str, Any]) -> None:
        """Process a transcript result from Deepgram."""
        channel_data = result.get("channel", {})
        alternatives = channel_data.get("alternatives", [])
        if not alternatives:
            return

        best = alternatives[0]
        text = best.get("transcript", "")
        confidence = best.get("confidence", 0.0)
        is_final = result.get("is_final", False)

        if is_final and text:
            self._last_final_time = time.time()

        if self._on_transcript and text:
            self._on_transcript({
                "text": text,
                "is_final": is_final,
                "confidence": confidence,
            })
