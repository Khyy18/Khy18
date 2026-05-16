"""Инструменты для работы с голосом (Whisper, TTS)."""

import logging
import os
from pathlib import Path

import httpx
from langchain_core.tools import tool

from ai_office.core.config import settings

logger = logging.getLogger(__name__)

OPENAI_API_URL = "https://api.openai.com/v1"


@tool
async def transcribe_voice(file_path: str) -> str:
    """Транскрибировать голосовое сообщение в текст через OpenAI Whisper API.

    Args:
        file_path: Путь к аудиофайлу для транскрипции

    Returns:
        Текст транскрипции или сообщение об ошибке
    """
    if not settings.openai_api_key:
        return "Ошибка: отсутствует OPENAI_API_KEY для транскрипции"

    path = Path(file_path)
    if not path.exists():
        return f"Ошибка: файл не найден: {file_path}"

    try:
        async with httpx.AsyncClient() as client:
            with open(path, "rb") as audio_file:
                response = await client.post(
                    f"{OPENAI_API_URL}/audio/transcriptions",
                    headers={"Authorization": f"Bearer {settings.openai_api_key}"},
                    data={"model": settings.whisper_model},
                    files={"file": (path.name, audio_file, "audio/ogg")},
                    timeout=60.0,
                )

        if response.status_code != 200:
            return f"Ошибка транскрипции: HTTP {response.status_code}"

        data = response.json()
        return data.get("text", "")

    except httpx.TimeoutException:
        return "Ошибка: превышено время ожидания при транскрипции"
    except Exception as e:
        logger.error("Ошибка транскрипции: %s", str(e))
        return f"Ошибка транскрипции: {str(e)}"


@tool
async def synthesize_speech(text: str, voice: str = "alloy") -> str:
    """Синтезировать речь из текста через OpenAI TTS API.

    Args:
        text: Текст для озвучивания
        voice: Голос (alloy, echo, fable, onyx, nova, shimmer)

    Returns:
        Путь к сгенерированному аудиофайлу или сообщение об ошибке
    """
    if not settings.openai_api_key:
        return "Ошибка: отсутствует OPENAI_API_KEY для синтеза речи"

    if not text.strip():
        return "Ошибка: передан пустой текст для синтеза"

    valid_voices = {"alloy", "echo", "fable", "onyx", "nova", "shimmer"}
    if voice not in valid_voices:
        voice = "alloy"

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{OPENAI_API_URL}/audio/speech",
                headers={
                    "Authorization": f"Bearer {settings.openai_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": settings.tts_model,
                    "input": text,
                    "voice": voice,
                },
                timeout=60.0,
            )

        if response.status_code != 200:
            return f"Ошибка синтеза речи: HTTP {response.status_code}"

        # Сохраняем аудио во временный файл
        output_dir = Path("/tmp/ai_office_tts")
        output_dir.mkdir(parents=True, exist_ok=True)

        import hashlib
        filename = hashlib.md5(text[:100].encode()).hexdigest()[:12] + ".mp3"
        output_path = output_dir / filename

        with open(output_path, "wb") as f:
            f.write(response.content)

        return str(output_path)

    except httpx.TimeoutException:
        return "Ошибка: превышено время ожидания при синтезе речи"
    except Exception as e:
        logger.error("Ошибка синтеза речи: %s", str(e))
        return f"Ошибка синтеза речи: {str(e)}"
