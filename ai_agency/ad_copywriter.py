"""Модуль генерации рекламных текстов AI-агентства."""

import logging
import hashlib
from typing import List, Dict, Optional

import config

logger = logging.getLogger(__name__)

# Попытка импорта openai (graceful)
try:
    from openai import AsyncOpenAI
except ImportError:
    AsyncOpenAI = None

# Lazy-singleton клиент
_client: Optional[object] = None


def _get_client():
    """Получить или создать OpenAI клиент."""
    global _client
    if _client is None and AsyncOpenAI is not None:
        _client = AsyncOpenAI(api_key=config.OPENAI_API_KEY)
    return _client


def generate_utm_link(campaign_id: str, variant: str) -> str:
    """
    Генерировать UTM deep link для A/B отслеживания.

    Args:
        campaign_id: идентификатор кампании
        variant: вариант (short, medium, long)

    Returns:
        Deep link для Telegram бота с UTM-параметрами
    """
    bot_username = config.BOT_USERNAME or "bot"
    utm_source = f"ad_{campaign_id}_{variant}"
    return f"https://t.me/{bot_username}?start=ad_{utm_source}"


def _generate_campaign_id(niche: str, style: str) -> str:
    """Генерировать уникальный ID кампании из параметров."""
    raw = f"{niche}_{style}_{config.BOT_USERNAME}"
    return hashlib.md5(raw.encode()).hexdigest()[:8]


async def generate_ad_copy(
    niche: str, audience_size: int, style: str = "informal"
) -> List[Dict]:
    """
    Генерировать 3 варианта рекламного текста.

    Args:
        niche: ниша/тематика (например "beauty salon", "IT courses")
        audience_size: размер аудитории канала
        style: стиль текста ("formal" или "informal")

    Returns:
        Список из 3 dict с ключами: variant, text, utm_link, length_type
    """
    campaign_id = _generate_campaign_id(niche, style)

    client = _get_client()
    if client is None:
        # Возвращаем шаблоны если OpenAI недоступен
        return _generate_fallback(niche, audience_size, style, campaign_id)

    style_instruction = (
        "формальный деловой стиль" if style == "formal"
        else "неформальный дружеский стиль с эмодзи"
    )

    prompt = (
        f"Сгенерируй 3 варианта рекламного поста для Telegram-канала.\n\n"
        f"Ниша: {niche}\n"
        f"Размер аудитории: {audience_size}\n"
        f"Стиль: {style_instruction}\n\n"
        f"Варианты:\n"
        f"1. КОРОТКИЙ (2-3 предложения, до 100 слов)\n"
        f"2. СРЕДНИЙ (1 абзац, 100-200 слов)\n"
        f"3. ДЛИННЫЙ (2-3 абзаца, 200-400 слов, с историей)\n\n"
        f"Каждый вариант должен содержать:\n"
        f"- Цепляющий заголовок\n"
        f"- Основной текст\n"
        f"- Призыв к действию (CTA)\n\n"
        f"Разделяй варианты строкой '---'\n"
        f"Формат: только тексты без нумерации и комментариев."
    )

    try:
        response = await client.chat.completions.create(
            model=config.DEFAULT_MODEL,
            messages=[
                {"role": "system", "content": "Ты эксперт по рекламным текстам для Telegram."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.8,
            max_tokens=2000,
        )
        content = response.choices[0].message.content.strip()
        variants = content.split("---")
    except Exception as e:
        logger.warning("Ошибка генерации ad copy через OpenAI: %s", e)
        return _generate_fallback(niche, audience_size, style, campaign_id)

    length_types = ["short", "medium", "long"]
    results = []

    for i, variant_text in enumerate(variants[:3]):
        length_type = length_types[i] if i < len(length_types) else "medium"
        results.append({
            "variant": f"variant_{i + 1}",
            "text": variant_text.strip(),
            "utm_link": generate_utm_link(campaign_id, length_type),
            "length_type": length_type,
        })

    # Дополняем если вариантов меньше 3
    while len(results) < 3:
        idx = len(results)
        length_type = length_types[idx] if idx < len(length_types) else "medium"
        results.append({
            "variant": f"variant_{idx + 1}",
            "text": f"[Вариант {idx + 1} для ниши: {niche}]",
            "utm_link": generate_utm_link(campaign_id, length_type),
            "length_type": length_type,
        })

    return results


def _generate_fallback(
    niche: str, audience_size: int, style: str, campaign_id: str
) -> List[Dict]:
    """Генерировать шаблонные варианты без API."""
    emoji = "\U0001f525" if style == "informal" else "\U0001f4bc"

    templates = [
        {
            "variant": "variant_1",
            "text": (
                f"{emoji} {niche.capitalize()} - ваш ключ к успеху!\n\n"
                f"Попробуйте прямо сейчас \u2192"
            ),
            "utm_link": generate_utm_link(campaign_id, "short"),
            "length_type": "short",
        },
        {
            "variant": "variant_2",
            "text": (
                f"{emoji} <b>{niche.capitalize()}</b>\n\n"
                f"Аудитория {audience_size}+ человек уже оценила.\n"
                f"Профессиональный контент за минуты, а не дни.\n\n"
                f"Начните бесплатно \u2192"
            ),
            "utm_link": generate_utm_link(campaign_id, "medium"),
            "length_type": "medium",
        },
        {
            "variant": "variant_3",
            "text": (
                f"{emoji} <b>{niche.capitalize()}: как получить результат быстрее</b>\n\n"
                f"Знакомо? Тратите часы на тексты, а результат не радует.\n\n"
                f"Наш AI-сервис создаёт контент за 2 минуты:\n"
                f"\u2022 Посты для соцсетей\n"
                f"\u2022 Статьи и SEO-тексты\n"
                f"\u2022 Деловые документы\n\n"
                f"Более {audience_size} пользователей доверяют нам.\n"
                f"Первый заказ бесплатно! \u2192"
            ),
            "utm_link": generate_utm_link(campaign_id, "long"),
            "length_type": "long",
        },
    ]
    return templates


async def store_campaign(
    niche: str, audience_size: int, style: str, variants: List[Dict]
) -> Optional[int]:
    """Сохранить кампанию в БД ad_campaigns."""
    try:
        import aiosqlite
        async with aiosqlite.connect(config.DATABASE_PATH) as db:
            cursor = await db.execute(
                """INSERT INTO ad_campaigns (channel_name, budget, source)
                   VALUES (?, ?, ?)""",
                (f"AdCopy: {niche}", float(audience_size), style),
            )
            await db.commit()
            return cursor.lastrowid
    except Exception as e:
        logger.debug("Ошибка сохранения кампании: %s", e)
        return None
