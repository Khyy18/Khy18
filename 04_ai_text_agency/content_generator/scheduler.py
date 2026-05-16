"""ARQ-задача для ежедневной генерации контента.

Генерирует 1 пост в день на случайную тему или по данным из RAG.
"""

from __future__ import annotations

import random
from typing import Any

from logging_config import get_logger

log = get_logger(__name__)

_TOPICS = [
    "Автоматизация бизнес-процессов с помощью Telegram-ботов",
    "Как ИИ помогает фрилансерам находить заказы",
    "Тренды в разработке на Python в 2024 году",
    "Преимущества микросервисной архитектуры",
    "Как правильно оценивать стоимость IT-проекта",
    "SEO-оптимизация для технических блогов",
    "Парсинг данных: легальные способы и лучшие практики",
    "Криптотрейдинг и автоматизация: с чего начать",
]


async def content_generation_task(ctx: dict[str, Any]) -> str:
    """ARQ задача: сгенерировать 1 пост в день."""
    import aiohttp

    from content_generator.generator import ContentGenerator

    topic = random.choice(_TOPICS)
    generator = ContentGenerator()

    async with aiohttp.ClientSession() as session:
        post = await generator.generate_channel_post(session, topic)

    if post:
        log.info("content_task_generated", topic=topic, length=len(post))
        return f"generated_post:topic={topic}"

    log.warning("content_task_failed", topic=topic)
    return "content_generation_failed"
