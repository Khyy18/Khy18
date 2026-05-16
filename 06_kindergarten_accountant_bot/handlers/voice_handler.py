"""Voice message handler - transcribes voice via Groq Whisper and routes through AI."""

import logging

from telegram import Update
from telegram.ext import ContextTypes

from kindergarten_accountant_bot.config import GROQ_API_KEY, WHISPER_MODEL
from kindergarten_accountant_bot.handlers.ai_handler import _call_ai_backend
from kindergarten_accountant_bot.utils.formatting import _card

logger = logging.getLogger(__name__)


async def voice_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle incoming voice messages: transcribe and process through AI."""
    if not GROQ_API_KEY:
        await update.message.reply_text(
            "Голосовые сообщения не настроены (GROQ_API_KEY не задан)."
        )
        return

    # Send processing indicator
    processing_msg = await update.message.reply_text("Распознаю голос...")

    try:
        # Check file size before downloading (max 5 MB)
        voice = update.message.voice
        max_size = 5 * 1024 * 1024  # 5 MB
        if voice.file_size and voice.file_size > max_size:
            await processing_msg.edit_text(
                "Голосовое сообщение слишком большое (максимум 5 МБ)"
            )
            return

        # Download voice file
        file = await voice.get_file()
        audio_bytes = await file.download_as_bytearray()

        # Transcribe via Groq Whisper
        from groq import AsyncGroq

        client = AsyncGroq(api_key=GROQ_API_KEY)
        transcription = await client.audio.transcriptions.create(
            model=WHISPER_MODEL,
            file=("voice.ogg", bytes(audio_bytes), "audio/ogg"),
        )
        text = transcription.text.strip()

        if not text:
            await processing_msg.edit_text("Не удалось распознать речь. Попробуйте ещё раз.")
            return

        # Route through AI backend
        response_text = await _call_ai_backend(text, update.effective_chat.id)

        if response_text:
            body_lines = [
                f"Вы сказали: {text}",
                "",
                f"Ответ: {response_text}",
            ]
            card = _card("Голосовой запрос", "\U0001f3a4", body_lines)
            await processing_msg.edit_text(card, parse_mode="HTML")
        else:
            body_lines = [
                f"Распознано: {text}",
                "",
                "AI не смог обработать запрос.",
                "Используйте меню для навигации.",
            ]
            card = _card("Голосовой запрос", "\U0001f3a4", body_lines)
            await processing_msg.edit_text(card, parse_mode="HTML")

    except Exception as e:
        logger.error(f"Voice handler error: {e}")
        await processing_msg.edit_text(
            "Ошибка при обработке голосового сообщения. Попробуйте позже."
        )
