"""
AI Pipeline: цепочка обработки аудио в реальном времени.

Архитектура pipeline:
    Аудио от клиента -> STT -> LLM -> TTS -> Avatar -> Видео клиенту

STT реализован через Groq Whisper API (или OpenAI Whisper как fallback)
с VAD (Voice Activity Detection) для определения пауз в речи.
LLM - Anthropic Claude или OpenAI GPT (настраивается через LLM_PROVIDER).
TTS - ElevenLabs Streaming API.
"""

import asyncio
import json
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

    @property
    def conversation_history(self) -> list[dict]:
        """Доступ к истории диалога для внешних модулей (например, генерация summary)."""
        return self._conversation_history

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
        Транскрипция аудио через Groq Whisper API или OpenAI Whisper.

        Логика выбора провайдера:
        - Если STT_API_KEY пустой -> mock текст для dev-режима
        - Если STT_API_KEY начинается с "sk-" -> OpenAI Whisper напрямую
        - Иначе -> Groq Whisper, с fallback на OpenAI Whisper при ошибке
        """
        if not settings.STT_API_KEY:
            return "[mock] Я чувствую тревогу."

        # Если ключ OpenAI (начинается с "sk-"), используем Whisper напрямую
        if settings.STT_API_KEY.startswith("sk-"):
            return await self._transcribe_openai(audio_data, settings.STT_API_KEY)

        # Основной путь: Groq Whisper API
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    "https://api.groq.com/openai/v1/audio/transcriptions",
                    headers={"Authorization": f"Bearer {settings.STT_API_KEY}"},
                    files={"file": ("audio.webm", audio_data, "audio/webm")},
                    data={"model": "whisper-large-v3"},
                )
                response.raise_for_status()
                result = response.json()
                return result.get("text", "")
        except (httpx.HTTPStatusError, httpx.RequestError) as e:
            logger.error("Groq STT failed: %s, trying OpenAI Whisper fallback", e)

        # Fallback: OpenAI Whisper если есть LLM_API_KEY
        if settings.LLM_API_KEY:
            return await self._transcribe_openai(audio_data, settings.LLM_API_KEY)

        return ""

    async def _transcribe_openai(self, audio_data: bytes, api_key: str) -> str:
        """Транскрипция через OpenAI Whisper API (fallback или основной путь)."""
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.post(
                    "https://api.openai.com/v1/audio/transcriptions",
                    headers={"Authorization": f"Bearer {api_key}"},
                    files={"file": ("audio.webm", audio_data, "audio/webm")},
                    data={"model": "whisper-1"},
                )
                response.raise_for_status()
                result = response.json()
                return result.get("text", "")
        except (httpx.HTTPStatusError, httpx.RequestError) as e:
            logger.error("OpenAI Whisper STT failed: %s", e)
            return ""

    async def get_response_stream(self) -> AsyncGenerator[dict, None]:
        """
        Генерация потокового ответа: текст (LLM) -> аудио (TTS).

        Выбор LLM провайдера через settings.LLM_PROVIDER:
        - "anthropic" -> Anthropic Claude (messages.stream)
        - "openai" -> OpenAI GPT (chat.completions.create stream)
        - Без ключа -> mock ответ для dev-режима
        """
        if not self._last_transcription:
            return

        # Добавляем в историю диалога
        self._conversation_history.append({
            "role": "user",
            "content": self._last_transcription
        })

        full_response = ""

        # Если LLM_API_KEY не задан, используем mock
        if not settings.LLM_API_KEY:
            mock_response = (
                "Я слышу вас. Тревога - это сигнал вашего тела. "
                "Расскажите подробнее, когда вы впервые заметили это чувство?"
            )
            self._conversation_history.append({
                "role": "assistant",
                "content": mock_response
            })
            self._trim_history()

            # Эмулируем потоковую отдачу текста
            words = mock_response.split()
            for i in range(0, len(words), 3):
                chunk_text = " ".join(words[i:i + 3])
                yield {"type": "text_delta", "content": chunk_text + " "}
                await asyncio.sleep(0.1)

            # Эмулируем аудио-чанк (тишина)
            yield {"type": "audio", "data": b"\x00" * 1024}
            self._last_transcription = ""
            return

        # Реальный LLM стриминг
        try:
            if settings.LLM_PROVIDER == "anthropic":
                async for chunk in self._stream_anthropic():
                    full_response += chunk["content"]
                    yield chunk
            elif settings.LLM_PROVIDER == "openai":
                async for chunk in self._stream_openai():
                    full_response += chunk["content"]
                    yield chunk
            else:
                logger.error("Unknown LLM_PROVIDER: %s", settings.LLM_PROVIDER)
                self._last_transcription = ""
                return
        except Exception as e:
            logger.error("LLM streaming failed: %s", e)
            # Fallback на mock при ошибке LLM
            fallback = "Извините, произошла техническая ошибка. Повторите, пожалуйста."
            full_response = fallback
            yield {"type": "text_delta", "content": fallback}

        # Сохраняем ответ в историю
        self._conversation_history.append({
            "role": "assistant",
            "content": full_response
        })
        self._trim_history()

        # TTS: озвучка ответа через ElevenLabs
        async for audio_chunk in self._synthesize_speech(full_response):
            yield audio_chunk

        # Сброс транскрипции
        self._last_transcription = ""

    async def _stream_anthropic(self) -> AsyncGenerator[dict, None]:
        """Стриминг ответа через Anthropic Claude API."""
        import anthropic

        client = anthropic.AsyncAnthropic(api_key=settings.LLM_API_KEY)

        # Для Anthropic system prompt передается отдельно, не в messages
        messages = [m for m in self._conversation_history if m["role"] != "system"]

        async with client.messages.stream(
            model=settings.LLM_MODEL,
            max_tokens=150,
            system=SYSTEM_PROMPT,
            messages=messages
        ) as stream:
            async for text in stream.text_stream:
                yield {"type": "text_delta", "content": text}

    async def _stream_openai(self) -> AsyncGenerator[dict, None]:
        """Стриминг ответа через OpenAI API."""
        from openai import AsyncOpenAI

        client = AsyncOpenAI(api_key=settings.LLM_API_KEY)

        stream = await client.chat.completions.create(
            model=settings.LLM_MODEL,
            messages=self._conversation_history,
            max_tokens=150,
            stream=True
        )

        async for chunk in stream:
            if chunk.choices and chunk.choices[0].delta.content:
                text = chunk.choices[0].delta.content
                yield {"type": "text_delta", "content": text}

    async def _synthesize_speech(self, text: str) -> AsyncGenerator[dict, None]:
        """
        TTS через ElevenLabs Streaming API.

        Если TTS_API_KEY пустой - возвращает тишину (text-only режим).
        """
        if not settings.TTS_API_KEY or not text.strip():
            # Тишина - text-only режим
            yield {"type": "audio", "data": b"\x00" * 1024}
            return

        voice_id = settings.ELEVENLABS_VOICE_ID or settings.TTS_VOICE_ID
        if not voice_id:
            logger.warning("TTS_API_KEY set but no voice ID configured, using silence")
            yield {"type": "audio", "data": b"\x00" * 1024}
            return

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                async with client.stream(
                    "POST",
                    f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}/stream",
                    headers={
                        "xi-api-key": settings.TTS_API_KEY,
                        "Content-Type": "application/json",
                    },
                    json={
                        "text": text,
                        "model_id": "eleven_multilingual_v2",
                        "voice_settings": {
                            "stability": 0.7,
                            "similarity_boost": 0.8,
                        },
                    },
                ) as response:
                    response.raise_for_status()
                    async for audio_chunk in response.aiter_bytes(4096):
                        yield {"type": "audio", "data": audio_chunk}
        except (httpx.HTTPStatusError, httpx.RequestError) as e:
            logger.error("ElevenLabs TTS failed: %s", e)
            # Fallback: тишина при ошибке TTS
            yield {"type": "audio", "data": b"\x00" * 1024}

    async def get_summary(self) -> dict:
        """
        Генерация итогов сессии через LLM.

        Возвращает dict с ключами: summary, homework, mood_score.
        Если LLM_API_KEY не задан или история слишком короткая - возвращает дефолт.
        """
        if not settings.LLM_API_KEY or len(self._conversation_history) < 3:
            return {
                "summary": "Сессия завершена.",
                "homework": "Практикуйте осознанность.",
                "mood_score": 5,
            }

        # Формируем запрос на summary
        summary_prompt = (
            "На основе диалога выше, составь краткое резюме сессии в формате JSON:\n"
            '{"summary": "краткое описание сессии (2-3 предложения)", '
            '"homework": "домашнее задание для клиента (1-2 предложения)", '
            '"mood_score": число от 1 до 10 (оценка эмоционального состояния клиента)}\n'
            "Ответь ТОЛЬКО валидным JSON без markdown."
        )

        messages = [m for m in self._conversation_history if m["role"] != "system"]
        messages.append({"role": "user", "content": summary_prompt})

        try:
            if settings.LLM_PROVIDER == "anthropic":
                import anthropic

                client = anthropic.AsyncAnthropic(api_key=settings.LLM_API_KEY)
                response = await client.messages.create(
                    model=settings.LLM_MODEL,
                    max_tokens=300,
                    system="Ты помощник психотерапевта. Генерируй резюме сессий в JSON.",
                    messages=messages,
                )
                raw_text = response.content[0].text
            elif settings.LLM_PROVIDER == "openai":
                from openai import AsyncOpenAI

                client = AsyncOpenAI(api_key=settings.LLM_API_KEY)
                response = await client.chat.completions.create(
                    model=settings.LLM_MODEL,
                    messages=[
                        {"role": "system", "content": "Ты помощник психотерапевта. Генерируй резюме сессий в JSON."}
                    ] + messages,
                    max_tokens=300,
                )
                raw_text = response.choices[0].message.content
            else:
                return {
                    "summary": "Сессия завершена.",
                    "homework": "Практикуйте осознанность.",
                    "mood_score": 5,
                }

            # Парсим JSON из ответа LLM
            result = json.loads(raw_text)
            return {
                "summary": result.get("summary", "Сессия завершена."),
                "homework": result.get("homework", "Практикуйте осознанность."),
                "mood_score": int(result.get("mood_score", 5)),
            }
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            logger.error("Failed to parse LLM summary response: %s", e)
            return {
                "summary": "Сессия завершена.",
                "homework": "Практикуйте осознанность.",
                "mood_score": 5,
            }
        except Exception as e:
            logger.error("LLM summary generation failed: %s", e)
            return {
                "summary": "Сессия завершена.",
                "homework": "Практикуйте осознанность.",
                "mood_score": 5,
            }
