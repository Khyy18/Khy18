"""AI pipeline orchestration: STT (Groq), LLM (Claude), TTS (ElevenLabs), lip-sync (Simli)."""

import logging
from typing import Optional

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


async def transcribe_audio(audio_bytes: bytes) -> str:
    """Transcribe audio using Groq Distil-Whisper API.

    Sends audio bytes to the Groq API for speech-to-text processing.
    """
    if not settings.groq_api_key:
        logger.warning("Groq API key not configured, returning empty transcript")
        return ""

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            "https://api.groq.com/openai/v1/audio/transcriptions",
            headers={"Authorization": f"Bearer {settings.groq_api_key}"},
            files={"file": ("audio.webm", audio_bytes, "audio/webm")},
            data={"model": "distil-whisper-large-v3-en", "language": "ru"},
        )
        response.raise_for_status()
        result = response.json()
        return result.get("text", "")


async def generate_response(transcript: str, system_prompt: str) -> str:
    """Generate a text response using Claude 3.5 Sonnet via Anthropic API.

    Takes the user's transcribed speech and the session system prompt
    to produce the astrologer's response.
    """
    if not settings.anthropic_api_key:
        logger.warning("Anthropic API key not configured, returning placeholder")
        return "Ой, у меня сейчас связь барахлит, подожди секунду!"

    async with httpx.AsyncClient(timeout=60.0) as client:
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
                "messages": [{"role": "user", "content": transcript}],
            },
        )
        response.raise_for_status()
        result = response.json()
        return result["content"][0]["text"]


async def synthesize_speech(text: str) -> bytes:
    """Convert text to speech using ElevenLabs API.

    Returns audio bytes in mp3 format.
    """
    if not settings.elevenlabs_api_key:
        logger.warning("ElevenLabs API key not configured, returning empty bytes")
        return b""

    voice_id = settings.elevenlabs_voice_id

    async with httpx.AsyncClient(timeout=30.0) as client:
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

    def __init__(self, system_prompt: str):
        self.system_prompt = system_prompt
        self.conversation_history: list[dict[str, str]] = []

    async def process_audio(self, audio_bytes: bytes) -> dict:
        """Process incoming audio through the full pipeline.

        Returns a dict with transcript, response_text, audio_bytes, and video_bytes.
        """
        transcript = await transcribe_audio(audio_bytes)
        if not transcript:
            return {
                "transcript": "",
                "response_text": "",
                "audio_bytes": b"",
                "video_bytes": None,
            }

        self.conversation_history.append({"role": "user", "content": transcript})

        response_text = await generate_response(transcript, self.system_prompt)

        self.conversation_history.append(
            {"role": "assistant", "content": response_text}
        )

        audio_response = await synthesize_speech(response_text)

        video_response = await get_lip_sync_video(audio_response)

        return {
            "transcript": transcript,
            "response_text": response_text,
            "audio_bytes": audio_response,
            "video_bytes": video_response,
        }
