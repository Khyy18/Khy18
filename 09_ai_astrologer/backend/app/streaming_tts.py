"""Streaming TTS pipeline using ElevenLabs streaming API."""

import logging
import re
from typing import AsyncGenerator

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

# Regex for splitting text into sentences (supports Russian punctuation)
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?…])\s+")


def split_sentences(text: str) -> list[str]:
    """Split text into sentences using Russian/English punctuation.

    Splits on period, exclamation mark, question mark, and ellipsis
    followed by whitespace.
    """
    sentences = _SENTENCE_SPLIT_RE.split(text.strip())
    return [s.strip() for s in sentences if s.strip()]


async def stream_tts_chunks(
    text: str,
    http_client: httpx.AsyncClient,
    voice_id: str | None = None,
) -> AsyncGenerator[bytes, None]:
    """Stream TTS audio chunks from ElevenLabs streaming API.

    Splits text into sentences, streams each one using ElevenLabs
    streaming endpoint, and yields audio chunks as they arrive.

    Args:
        text: The text to synthesize (can be multiple sentences).
        http_client: Shared httpx.AsyncClient instance.
        voice_id: Optional voice ID override. Defaults to settings.

    Yields:
        Audio bytes chunks as they arrive from the API.
    """
    if not settings.elevenlabs_api_key:
        logger.warning("ElevenLabs API key not configured, yielding empty")
        return

    vid = voice_id or settings.elevenlabs_voice_id
    sentences = split_sentences(text)

    if not sentences:
        return

    for sentence in sentences:
        url = f"https://api.elevenlabs.io/v1/text-to-speech/{vid}/stream"
        headers = {
            "xi-api-key": settings.elevenlabs_api_key,
            "content-type": "application/json",
        }
        payload = {
            "text": sentence,
            "model_id": "eleven_multilingual_v2",
            "voice_settings": {
                "stability": 0.5,
                "similarity_boost": 0.75,
            },
        }

        try:
            async with http_client.stream(
                "POST", url, headers=headers, json=payload
            ) as response:
                response.raise_for_status()
                async for chunk in response.aiter_bytes(chunk_size=4096):
                    if chunk:
                        yield chunk
        except httpx.HTTPStatusError as e:
            logger.error(f"ElevenLabs streaming error: {e}")
            return
        except Exception as e:
            logger.error(f"TTS streaming error: {e}")
            return
