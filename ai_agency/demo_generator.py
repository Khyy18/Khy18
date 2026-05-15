"""Генератор демо-контента и рекламных креативов."""

import logging
from typing import Dict, List, Optional

import config
import database

logger = logging.getLogger(__name__)

# Lazy OpenAI client
_openai_client = None

# Module-level cache for generated demos and creatives
_demo_cache: Dict[str, Optional[str]] = {}
_creative_cache: Dict[str, Dict[str, str]] = {}


def _get_openai_client():
    """Получить или создать singleton AsyncOpenAI клиент."""
    global _openai_client
    if _openai_client is None:
        from openai import AsyncOpenAI
        _openai_client = AsyncOpenAI(api_key=config.OPENAI_API_KEY)
    return _openai_client


# Описания сервисов для генерации демо
SERVICE_DESCRIPTIONS = {
    "copywriting": "копирайтинг (посты, статьи, описания товаров)",
    "rewrite": "рерайт (уникализация текста)",
    "seo": "SEO-оптимизация (ключевые слова, мета-теги)",
    "translation": "перевод текстов",
    "summary": "суммаризация (краткое изложение)",
    "smm": "SMM (контент для соцсетей)",
}


async def generate_demo_for_service(service_type: str) -> Optional[str]:
    """Сгенерировать демо-текст для указанного типа услуги."""
    description = SERVICE_DESCRIPTIONS.get(service_type, service_type)

    try:
        client = _get_openai_client()
        response = await client.chat.completions.create(
            model=config.DEFAULT_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Ты генератор примеров работы AI-агентства. "
                        "Создай короткий, но впечатляющий пример результата."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Создай демо-пример для услуги: {description}. "
                        "Покажи вход (задание) и выход (результат). "
                        "Формат: ЗАДАНИЕ: ... РЕЗУЛЬТАТ: ..."
                    ),
                },
            ],
            max_tokens=500,
            temperature=0.8,
        )
        return response.choices[0].message.content
    except Exception as e:
        logger.error("Ошибка генерации демо для %s: %s", service_type, e)
        return None


async def generate_ad_creative(service_type: str) -> Optional[Dict[str, str]]:
    """
    Сгенерировать рекламный креатив для услуги.
    Возвращает dict с headline, description, cta.
    """
    description = SERVICE_DESCRIPTIONS.get(service_type, service_type)

    try:
        client = _get_openai_client()
        response = await client.chat.completions.create(
            model=config.DEFAULT_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Ты копирайтер рекламных текстов. Пиши коротко и ярко."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Создай рекламный креатив для услуги: {description}. "
                        "Верни JSON: "
                        '{"headline": "заголовок до 50 символов", '
                        '"description": "описание до 100 символов", '
                        '"cta": "призыв к действию до 30 символов"}'
                    ),
                },
            ],
            max_tokens=200,
            temperature=0.7,
        )
        content = response.choices[0].message.content

        import json
        try:
            data = json.loads(content)
            return {
                "headline": data.get("headline", ""),
                "description": data.get("description", ""),
                "cta": data.get("cta", ""),
            }
        except (json.JSONDecodeError, TypeError):
            return {
                "headline": f"AI {description}",
                "description": content[:100],
                "cta": "Попробовать бесплатно",
            }
    except Exception as e:
        logger.error("Ошибка генерации креатива для %s: %s", service_type, e)
        return None


async def select_best_cases(limit: int = 5) -> List[dict]:
    """Выбрать лучшие заказы для рекламы (высокий рейтинг)."""
    try:
        async with __import__("aiosqlite").connect(config.DATABASE_PATH) as db:
            db.row_factory = __import__("aiosqlite").Row
            cursor = await db.execute(
                """SELECT * FROM orders
                   WHERE status = 'completed' AND rating >= 4
                   ORDER BY rating DESC, created_at DESC
                   LIMIT ?""",
                (limit,),
            )
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]
    except Exception as e:
        logger.error("Ошибка получения лучших кейсов: %s", e)
        return []


async def auto_generate_demos() -> Dict[str, Optional[str]]:
    """Сгенерировать демо для всех типов услуг и сохранить в кеш."""
    results = {}
    for service_type in SERVICE_DESCRIPTIONS:
        demo = await generate_demo_for_service(service_type)
        results[service_type] = demo
        if demo:
            _demo_cache[service_type] = demo
    return results


async def get_demo_creatives() -> List[dict]:
    """Получить рекламные креативы для всех услуг (из кеша или генерировать)."""
    creatives = []
    for service_type in SERVICE_DESCRIPTIONS:
        # Use cached creative if available
        if service_type in _creative_cache:
            creative = dict(_creative_cache[service_type])
            creative["service_type"] = service_type
            creatives.append(creative)
            continue
        creative = await generate_ad_creative(service_type)
        if creative:
            _creative_cache[service_type] = creative
            creative["service_type"] = service_type
            creatives.append(creative)
    return creatives
