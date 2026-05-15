"""Обработка фото: извлечение текста через GPT-4o Vision."""

import base64
import logging
from typing import Optional

from telegram import Update
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


# ConversationHandler states
ENTER_TEXT = 1


async def extract_text_from_image(image_bytes: bytes) -> Optional[str]:
    """Извлечь текст из изображения через GPT-4o Vision."""
    try:
        client = _get_openai_client()
        b64_image = base64.b64encode(image_bytes).decode("utf-8")

        response = await client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": (
                                "Извлеки весь текст с этого изображения. "
                                "Если текста нет, опиши содержимое изображения. "
                                "Верни только текст без пояснений."
                            ),
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{b64_image}",
                            },
                        },
                    ],
                }
            ],
            max_tokens=1000,
        )
        return response.choices[0].message.content
    except Exception as e:
        logger.error("Ошибка GPT-4o Vision: %s", e)
        return None


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Обработка фото: извлечение текста через GPT-4o Vision.
    Устанавливает context.user_data["input_text"] и возвращает ENTER_TEXT
    так чтобы enter_text() обработал валидацию при следующем сообщении.
    """
    message = update.message
    photo = message.photo

    if not photo:
        await message.reply_text(
            "\u274c Не удалось получить фото. Попробуйте ещё раз.",
            parse_mode=ParseMode.HTML,
        )
        return ENTER_TEXT

    # Берём наибольший размер фото
    largest_photo = photo[-1]

    try:
        file = await context.bot.get_file(largest_photo.file_id)
        file_bytes = await file.download_as_bytearray()
    except Exception as e:
        logger.error("Ошибка скачивания фото: %s", e)
        await message.reply_text(
            "\u274c Ошибка загрузки фото. Попробуйте ещё раз.",
            parse_mode=ParseMode.HTML,
        )
        return ENTER_TEXT

    await message.reply_text(
        "\U0001f50d Анализирую изображение...",
        parse_mode=ParseMode.HTML,
    )

    # Извлекаем текст
    extracted_text = await extract_text_from_image(bytes(file_bytes))

    if not extracted_text:
        await message.reply_text(
            "\u274c Не удалось извлечь текст из изображения. Отправьте текст вручную.",
            parse_mode=ParseMode.HTML,
        )
        return ENTER_TEXT

    # Сохраняем извлечённый текст в user_data для использования enter_text()
    context.user_data["input_text"] = extracted_text

    body = [
        "<b>Извлечённый текст:</b>",
        f"<pre>{extracted_text[:500]}</pre>",
        "",
        "Отправьте любое сообщение для подтверждения или введите свой текст.",
    ]
    card = _card("Текст с изображения", "\U0001f4f7", body)

    await message.reply_text(card, parse_mode=ParseMode.HTML)

    return ENTER_TEXT
