"""Обработка голосовых сообщений: транскрипция через Whisper API."""

import logging
from typing import Optional

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

import config
from utils import _card

logger = logging.getLogger(__name__)

# Lazy OpenAI client
_openai_client = None


def _get_openai_client():
    """Получить или создать singleton AsyncOpenAI клиент."""
    global _openai_client
    if _openai_client is None:
        from openai import AsyncOpenAI
        _openai_client = AsyncOpenAI(api_key=config.OPENAI_API_KEY)
    return _openai_client


# ConversationHandler state
ENTER_TEXT = 1


async def transcribe_audio(file_bytes: bytes, filename: str = "voice.ogg") -> Optional[str]:
    """Транскрибировать аудио через OpenAI Whisper API."""
    try:
        client = _get_openai_client()
        response = await client.audio.transcriptions.create(
            model="whisper-1",
            file=(filename, file_bytes),
        )
        return response.text
    except Exception as e:
        logger.error("Ошибка транскрипции Whisper: %s", e)
        return None


async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Обработка голосового/аудио сообщения.
    Транскрибирует через Whisper, показывает текст с кнопками подтверждения.
    После подтверждения возвращает ENTER_TEXT для обработки как обычного текста.
    """
    message = update.message
    voice = message.voice or message.audio

    if not voice:
        await message.reply_text(
            "\u274c Не удалось получить аудио. Попробуйте ещё раз.",
            parse_mode=ParseMode.HTML,
        )
        return ENTER_TEXT

    # Скачиваем файл
    try:
        file = await context.bot.get_file(voice.file_id)
        file_bytes = await file.download_as_bytearray()
    except Exception as e:
        logger.error("Ошибка скачивания аудио: %s", e)
        await message.reply_text(
            "\u274c Ошибка загрузки аудио. Попробуйте ещё раз.",
            parse_mode=ParseMode.HTML,
        )
        return ENTER_TEXT

    # Транскрибируем
    await message.reply_text(
        "\U0001f3a4 Распознаю голосовое сообщение...",
        parse_mode=ParseMode.HTML,
    )

    text = await transcribe_audio(bytes(file_bytes))

    if not text:
        await message.reply_text(
            "\u274c Не удалось распознать речь. Попробуйте отправить текстом.",
            parse_mode=ParseMode.HTML,
        )
        return ENTER_TEXT

    # Сохраняем транскрипцию и показываем с кнопками подтверждения
    context.user_data["voice_transcription"] = text

    body = [
        "<b>Распознанный текст:</b>",
        f"<pre>{text[:500]}</pre>",
        "",
        "Использовать этот текст для заказа?",
    ]
    card = _card("Голосовой ввод", "\U0001f3a4", body)

    keyboard = [
        [
            InlineKeyboardButton("\u2705 Подтвердить", callback_data="voice_confirm"),
            InlineKeyboardButton("\u274c Отмена", callback_data="voice_cancel"),
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await message.reply_text(card, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
    return ENTER_TEXT


async def handle_voice_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка подтверждения/отмены голосового ввода."""
    query = update.callback_query
    await query.answer()

    if query.data == "voice_cancel":
        context.user_data.pop("voice_transcription", None)
        await query.edit_message_text(
            "\u274c Голосовой ввод отменён. Отправьте текст или голосовое сообщение.",
            parse_mode=ParseMode.HTML,
        )
        return ENTER_TEXT

    # voice_confirm - используем транскрипцию как input_text
    text = context.user_data.pop("voice_transcription", "")
    if not text:
        await query.edit_message_text(
            "\u274c Текст не найден. Попробуйте ещё раз.",
            parse_mode=ParseMode.HTML,
        )
        return ENTER_TEXT

    context.user_data["input_text"] = text
    return ENTER_TEXT
