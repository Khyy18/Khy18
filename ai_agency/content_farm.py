"""Автогенерация контента для Telegram-каналов."""

import json
import logging
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from telegram import Bot

import config

logger = logging.getLogger(__name__)

# Lazy OpenAI client
_openai_client = None

# Track last posted hour per channel to avoid double-posting
_last_posted_hour: Dict[str, int] = {}


def _get_openai_client():
    """Получить или создать singleton AsyncOpenAI клиент."""
    global _openai_client
    if _openai_client is None:
        from openai import AsyncOpenAI
        _openai_client = AsyncOpenAI(api_key=config.OPENAI_API_KEY)
    return _openai_client


# Ниши контента
NICHES = {
    "business_tips": {
        "name": "Бизнес-советы",
        "prompt": (
            "Напиши короткий пост для Telegram-канала о бизнесе. "
            "Тема: практический совет для предпринимателей. "
            "Формат: заголовок + 3-5 предложений + CTA. Используй эмодзи."
        ),
    },
    "marketing": {
        "name": "Маркетинг",
        "prompt": (
            "Напиши короткий пост для Telegram-канала о маркетинге. "
            "Тема: актуальный тренд или лайфхак. "
            "Формат: заголовок + 3-5 предложений + CTA. Используй эмодзи."
        ),
    },
    "ai_news": {
        "name": "AI-новости",
        "prompt": (
            "Напиши короткий пост для Telegram-канала об искусственном интеллекте. "
            "Тема: новость или полезный инструмент AI. "
            "Формат: заголовок + 3-5 предложений + CTA. Используй эмодзи."
        ),
    },
    "copywriting_hacks": {
        "name": "Копирайтинг",
        "prompt": (
            "Напиши короткий пост для Telegram-канала о копирайтинге. "
            "Тема: техника написания текстов или формула заголовков. "
            "Формат: заголовок + 3-5 предложений + CTA. Используй эмодзи."
        ),
    },
}


def _parse_channels() -> List[dict]:
    """Разобрать JSON конфигурацию каналов из CONTENT_FARM_CHANNELS."""
    try:
        channels = json.loads(config.CONTENT_FARM_CHANNELS)
        if not isinstance(channels, list):
            return []
        return channels
    except (json.JSONDecodeError, TypeError):
        return []


async def generate_post(niche: str) -> Optional[str]:
    """Сгенерировать пост для указанной ниши."""
    niche_config = NICHES.get(niche)
    if not niche_config:
        logger.warning("Неизвестная ниша: %s", niche)
        return None

    try:
        client = _get_openai_client()
        bot_username = config.BOT_USERNAME or "ai_agency_bot"
        cta = f"\n\n\U0001f449 Заказать текст: @{bot_username}"

        response = await client.chat.completions.create(
            model=config.DEFAULT_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": "Ты SMM-менеджер. Пишешь посты для Telegram-каналов.",
                },
                {"role": "user", "content": niche_config["prompt"]},
            ],
            max_tokens=500,
            temperature=0.8,
        )
        post_text = response.choices[0].message.content
        return post_text + cta
    except Exception as e:
        logger.error("Ошибка генерации поста для ниши %s: %s", niche, e)
        return None


async def check_and_post(bot: Optional[Bot] = None) -> int:
    """
    Проверить расписание и опубликовать посты в каналы.
    Возвращает количество опубликованных постов.
    Tracks last posted hour per channel to avoid double-posting.
    """
    channels = _parse_channels()
    if not channels or not bot:
        return 0

    posted = 0
    current_hour = datetime.utcnow().hour

    for channel_cfg in channels:
        channel_id = channel_cfg.get("channel_id")
        niche = channel_cfg.get("niche", "business_tips")
        schedule = channel_cfg.get("schedule", [9, 15, 20])

        if not channel_id:
            continue

        # Проверяем, попадает ли текущий час в расписание
        if current_hour not in schedule:
            continue

        # Skip if already posted this hour for this channel
        channel_key = str(channel_id)
        if _last_posted_hour.get(channel_key) == current_hour:
            continue

        post = await generate_post(niche)
        if not post:
            continue

        try:
            await bot.send_message(
                chat_id=channel_id,
                text=post,
                parse_mode="HTML",
            )
            posted += 1
            _last_posted_hour[channel_key] = current_hour
            logger.info("Опубликован пост в канал %s (ниша: %s)", channel_id, niche)
        except Exception as e:
            logger.error("Ошибка публикации в канал %s: %s", channel_id, e)

    return posted
