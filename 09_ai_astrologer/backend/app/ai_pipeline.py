"""AI pipeline orchestration: STT (Groq), LLM (Claude), TTS (ElevenLabs), lip-sync (Simli)."""

import logging
from typing import Optional

import httpx

from app.circuit_breaker import (
    with_circuit_breaker,
    stt_circuit,
    llm_circuit,
    tts_circuit,
    STT_FALLBACK,
    LLM_FALLBACK,
    TTS_FALLBACK,
)
from app.config import settings
from app.http_client import get_http_client

logger = logging.getLogger(__name__)


@with_circuit_breaker(stt_circuit, STT_FALLBACK)
async def transcribe_audio(audio_bytes: bytes, client: httpx.AsyncClient) -> str:
    """Transcribe audio using Groq Distil-Whisper API.

    Sends audio bytes to the Groq API for speech-to-text processing.
    """
    if not settings.groq_api_key:
        logger.warning("Groq API key not configured, returning empty transcript")
        return ""

    response = await client.post(
        "https://api.groq.com/openai/v1/audio/transcriptions",
        headers={"Authorization": f"Bearer {settings.groq_api_key}"},
        files={"file": ("audio.webm", audio_bytes, "audio/webm")},
        data={"model": "distil-whisper-large-v3-en", "language": "ru"},
    )
    response.raise_for_status()
    result = response.json()
    return result.get("text", "")


@with_circuit_breaker(llm_circuit, LLM_FALLBACK)
async def generate_response(
    transcript: str,
    system_prompt: str,
    conversation_history: list[dict[str, str]] | None = None,
    client: httpx.AsyncClient | None = None,
) -> str:
    """Generate a text response using Claude 3.5 Sonnet via Anthropic API.

    Takes the user's transcribed speech, the session system prompt,
    and optional conversation history to produce the astrologer's response.
    """
    if not settings.anthropic_api_key:
        logger.warning("Anthropic API key not configured, returning placeholder")
        return LLM_FALLBACK

    if client is None:
        client = get_http_client()

    messages = conversation_history if conversation_history else [{"role": "user", "content": transcript}]

    response = await client.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": settings.anthropic_api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json={
            "model": "claude-sonnet-4-20250514",
            "max_tokens": 200,
            "system": system_prompt,
            "messages": messages,
        },
        timeout=60.0,
    )
    response.raise_for_status()
    result = response.json()
    return result["content"][0]["text"]


@with_circuit_breaker(tts_circuit, TTS_FALLBACK)
async def synthesize_speech(text: str, client: httpx.AsyncClient) -> bytes:
    """Convert text to speech using ElevenLabs API.

    Returns audio bytes in mp3 format.
    """
    if not settings.elevenlabs_api_key:
        logger.warning("ElevenLabs API key not configured, returning empty bytes")
        return b""

    voice_id = settings.elevenlabs_voice_id

    response = await client.post(
        f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}",
        headers={
            "xi-api-key": settings.elevenlabs_api_key,
            "content-type": "application/json",
        },
        json={
            "text": text,
            "model_id": "eleven_multilingual_v2",
            "voice_settings": {
                "stability": 0.5,
                "similarity_boost": 0.75,
            },
        },
    )
    response.raise_for_status()
    return response.content


async def get_lip_sync_video(audio_bytes: bytes) -> Optional[bytes]:
    """Generate lip-sync video from audio (placeholder for Simli/LiveKit integration).

    This is a placeholder that will be implemented when the Simli or LiveKit
    integration is ready. Currently returns None.
    """
    logger.info("Lip-sync generation placeholder called - not yet implemented")
    return None


class AIPipeline:
    """Orchestrates the full AI pipeline: STT -> LLM -> TTS -> Lip-sync."""

    def __init__(self, system_prompt: str, http_client: httpx.AsyncClient | None = None):
        self.system_prompt = system_prompt
        self.conversation_history: list[dict[str, str]] = []
        self._http_client = http_client

    @property
    def client(self) -> httpx.AsyncClient:
        """Get the httpx client, falling back to the shared one."""
        if self._http_client is not None:
            return self._http_client
        return get_http_client()

    async def process_audio(self, audio_bytes: bytes) -> dict:
        """Process incoming audio through the full pipeline.

        Returns a dict with transcript, response_text, audio_bytes, and video_bytes.
        """
        transcript = await transcribe_audio(audio_bytes, self.client)
        if not transcript:
            return {
                "transcript": "",
                "response_text": "",
                "audio_bytes": b"",
                "video_bytes": None,
            }

        self.conversation_history.append({"role": "user", "content": transcript})

        response_text = await generate_response(
            transcript, self.system_prompt, self.conversation_history, self.client
        )

        self.conversation_history.append(
            {"role": "assistant", "content": response_text}
        )

        audio_response = await synthesize_speech(response_text, self.client)

        video_response = await get_lip_sync_video(audio_response)

        return {
            "transcript": transcript,
            "response_text": response_text,
            "audio_bytes": audio_response,
            "video_bytes": video_response,
        }
