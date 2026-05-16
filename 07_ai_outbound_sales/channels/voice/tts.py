try:
    import audioop
except (ImportError, ModuleNotFoundError):
    try:
        import audioop_lts as audioop  # type: ignore[no-redef]
    except (ImportError, ModuleNotFoundError):
        audioop = None  # type: ignore[assignment]
import logging
from typing import AsyncGenerator

import httpx

logger = logging.getLogger(__name__)

ELEVENLABS_STREAM_URL = "https://api.elevenlabs.io/v1/text-to-speech/{voice_id}/stream"


class ElevenLabsTTS:
    """Text-to-speech using ElevenLabs streaming API."""

    def __init__(self, api_key: str, voice_id: str = "default") -> None:
        self._api_key = api_key
        self._voice_id = voice_id

    async def synthesize(
        self, text: str, output_format: str = "ulaw_8000"
    ) -> AsyncGenerator[bytes, None]:
        """Stream synthesized audio from ElevenLabs.

        Yields audio chunks as they arrive from the API.
        """
        url = ELEVENLABS_STREAM_URL.format(voice_id=self._voice_id)
        headers = {
            "xi-api-key": self._api_key,
            "Content-Type": "application/json",
            "Accept": "audio/basic",
        }
        payload = {
            "text": text,
            "model_id": "eleven_monolingual_v1",
            "voice_settings": {
                "stability": 0.5,
                "similarity_boost": 0.75,
            },
            "output_format": output_format,
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            async with client.stream("POST", url, json=payload, headers=headers) as response:
                if response.status_code != 200:
                    logger.error(
                        "ElevenLabs TTS failed with status %d", response.status_code
                    )
                    return
                async for chunk in response.aiter_bytes(chunk_size=1024):
                    if chunk:
                        yield chunk

    @staticmethod
    def convert_to_mulaw(audio_bytes: bytes) -> bytes:
        """Convert 16-bit PCM audio to mu-law encoded audio."""
        if audioop is not None:
            return audioop.lin2ulaw(audio_bytes, 2)
        # Fallback: manual mu-law encoding using struct
        import struct

        num_samples = len(audio_bytes) // 2
        samples = struct.unpack(f"<{num_samples}h", audio_bytes)
        result = bytearray(num_samples)
        MULAW_BIAS = 33
        MULAW_MAX = 0x1FFF
        for i, sample in enumerate(samples):
            sign = 0x80 if sample < 0 else 0
            sample = min(abs(sample), 32635)
            sample = sample + MULAW_BIAS
            exponent = 7
            for exp_val in (0x4000, 0x2000, 0x1000, 0x800, 0x400, 0x200, 0x100):
                if sample >= exp_val:
                    break
                exponent -= 1
            mantissa = (sample >> (exponent + 3)) & 0x0F
            result[i] = ~(sign | (exponent << 4) | mantissa) & 0xFF
        return bytes(result)
