"""
AI Pipeline: цепочка обработки аудио в реальном времени.

Архитектура pipeline:
    Аудио от клиента -> STT -> LLM -> TTS -> Avatar -> Видео клиенту

STT реализован через Groq Whisper API с VAD (Voice Activity Detection)
для определения пауз в речи. LLM/TTS/Avatar - стабы для будущей интеграции.
"""

import asyncio
import logging
from typing import AsyncGenerator

import httpx

from app.config import settings
from app.prompts.psychologist import SYSTEM_PROMPT

logger = logging.getLogger(__name__)


class AIPipeline:
    """
    Класс управления AI pipeline для обработки голосового ввода
    и генерации аудио/видео ответа психолога.
    """

    MAX_HISTORY_LENGTH = 50  # Maximum number of messages to keep in history
    # Fallback: transcribe after accumulating this many chunks (~10s at 250ms interval)
    MAX_CHUNKS_BEFORE_TRANSCRIBE = 40

    def __init__(self, session_id: str):
        self.session_id = session_id
        self._audio_buffer: list[bytes] = []
        self._conversation_history: list[dict] = [
            {"role": "system", "content": SYSTEM_PROMPT}
        ]
        self._last_transcription: str = ""

        # Chunk counter for size-based fallback transcription
        self._chunk_count: int = 0

    def _trim_history(self) -> None:
        """Trim conversation history to MAX_HISTORY_LENGTH, keeping system prompt."""
        if len(self._conversation_history) > self.MAX_HISTORY_LENGTH:
            # Always keep the system prompt (first message), trim oldest after it
            system_msg = self._conversation_history[0]
            trimmed = self._conversation_history[-(self.MAX_HISTORY_LENGTH - 1):]
            self._conversation_history = [system_msg] + trimmed

    async def process_audio_chunk(self, chunk: bytes) -> None:
        """
        Обработка аудио-чанка от клиента.

        Накапливаем аудио-чанки в буфере. Транскрипция запускается либо:
        1. По сигналу speech_end от клиентского VAD (через force_transcribe())
        2. По достижению MAX_CHUNKS_BEFORE_TRANSCRIBE как fallback (~10 секунд)
        """
        self._audio_buffer.append(chunk)
        self._chunk_count += 1

        # Size-based fallback: transcribe after ~10 seconds of audio
        if self._chunk_count >= self.MAX_CHUNKS_BEFORE_TRANSCRIBE:
            await self._trigger_transcription()

    async def force_transcribe(self) -> None:
        """
        Принудительный запуск транскрипции по сигналу speech_end от фронтенда.
        Вызывается из WebSocket handler при получении control message.
        """
        if self._audio_buffer:
            await self._trigger_transcription()

    async def _trigger_transcription(self) -> None:
        """Собираем буфер и отправляем на STT."""
        audio_data = b"".join(self._audio_buffer)
        self._audio_buffer.clear()
        self._chunk_count = 0

        transcription = await self._transcribe_audio(audio_data)
        if transcription.strip():
            self._last_transcription = transcription
            logger.info(
                "Transcription for session %s: %s",
                self.session_id,
                transcription[:100],
            )

    async def _transcribe_audio(self, audio_data: bytes) -> str:
        """
        Транскрипция аудио через Groq Whisper API.

        Если STT_API_KEY не задан, возвращает mock текст для dev-режима.
        """
        if not settings.STT_API_KEY:
            return "[mock] Я чувствую тревогу."

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    "https://api.groq.com/openai/v1/audio/transcriptions",
                    headers={"Authorization": f"Bearer {settings.STT_API_KEY}"},
                    files={"file": ("audio.webm", audio_data, "audio/webm")},
                    data={"model": "whisper-large-v3", "language": "ru"},
                )
                response.raise_for_status()
                result = response.json()
                return result.get("text", "")
        except httpx.HTTPStatusError as e:
            logger.error("Groq STT API error: %s", e.response.status_code)
            return ""
        except httpx.RequestError as e:
            logger.error("Groq STT request failed: %s", e)
            return ""

    async def get_response_stream(self) -> AsyncGenerator[dict, None]:
        """
        Генерация потокового ответа: текст -> аудио -> видео.

        Шаг 1: LLM (Claude или GPT-4o)
        ----------------------------------
        ```python
        # Вариант A: Anthropic Claude
        import anthropic
        client = anthropic.AsyncAnthropic(api_key=settings.LLM_API_KEY)
        async with client.messages.stream(
            model="claude-sonnet-4-20250514",
            max_tokens=150,  # Короткие ответы для голоса
            system=SYSTEM_PROMPT,
            messages=self._conversation_history
        ) as stream:
            async for text in stream.text_stream:
                yield {"type": "text_delta", "content": text}

        # Вариант B: OpenAI GPT-4o
        from openai import AsyncOpenAI
        client = AsyncOpenAI(api_key=settings.LLM_API_KEY)
        stream = await client.chat.completions.create(
            model="gpt-4o",
            messages=self._conversation_history,
            max_tokens=150,
            stream=True
        )
        ```

        Шаг 2: TTS (ElevenLabs)
        -------------------------
        ```python
        # ElevenLabs Streaming TTS с низкой задержкой
        async with httpx.AsyncClient() as client:
            async with client.stream(
                "POST",
                f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}/stream",
                headers={"xi-api-key": settings.TTS_API_KEY},
                json={
                    "text": response_text,
                    "model_id": "eleven_multilingual_v2",
                    "voice_settings": {"stability": 0.7, "similarity_boost": 0.8}
                }
            ) as response:
                async for audio_chunk in response.aiter_bytes(1024):
                    yield {"type": "audio", "data": audio_chunk}
        ```

        Шаг 3: Avatar (Simli или LiveKit Agents)
        -------------------------------------------
        ```python
        # Вариант A: Simli API для lip-sync аватара
        # Отправляем аудио-чанки на Simli, получаем видео-фреймы
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://api.simli.ai/startAudioToVideoSession",
                json={"faceId": face_id, "audioData": base64_audio}
            )

        # Вариант B: LiveKit Agents для реального видео-стриминга
        # Используем LiveKit room для передачи видео-трека клиенту
        # room.local_participant.publish_track(video_track)
        ```
        """
        if not self._last_transcription:
            return

        # Добавляем в историю диалога
        self._conversation_history.append({
            "role": "user",
            "content": self._last_transcription
        })

        # Стаб: mock ответ психолога в dev-режиме
        mock_response = (
            "Я слышу вас. Тревога - это сигнал вашего тела. "
            "Расскажите подробнее, когда вы впервые заметили это чувство?"
        )

        self._conversation_history.append({
            "role": "assistant",
            "content": mock_response
        })

        # Trim history to prevent unbounded growth
        self._trim_history()

        # Эмулируем потоковую отдачу текста
        words = mock_response.split()
        for i in range(0, len(words), 3):
            chunk_text = " ".join(words[i:i+3])
            yield {"type": "text_delta", "content": chunk_text + " "}
            await asyncio.sleep(0.1)

        # Эмулируем аудио-чанк (в реальности здесь будут байты от TTS)
        yield {"type": "audio", "data": b"\x00" * 1024}

        # Сброс транскрипции
        self._last_transcription = ""
