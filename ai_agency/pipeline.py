"""Пайплайн обработки заказов: вызов OpenAI API с проверками качества."""

import logging
from typing import Optional

from openai import AsyncOpenAI

import config
from models import ServiceType
from services import get_service

logger = logging.getLogger(__name__)


def _check_quality(text: str, min_words: int, required_keywords: list) -> bool:
    """Проверка качества результата."""
    words = text.split()
    if len(words) < min_words:
        return False
    if required_keywords:
        text_lower = text.lower()
        for keyword in required_keywords:
            if keyword.lower() not in text_lower:
                return False
    return True


async def process_order(service_type: ServiceType, input_text: str) -> Optional[str]:
    """
    Обработать заказ через OpenAI API.

    1. Получает определение услуги (промпты, проверки)
    2. Вызывает OpenAI API
    3. Проверяет качество результата
    4. При неудаче повторяет один раз
    5. Возвращает текст результата или None при ошибке
    """
    service = get_service(service_type)
    quality = service.quality_checks

    client = AsyncOpenAI(api_key=config.OPENAI_API_KEY)

    user_prompt = service.user_prompt_template.format(input_text=input_text)

    messages = [
        {"role": "system", "content": service.system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    max_attempts = quality.max_retry + 1

    for attempt in range(max_attempts):
        try:
            response = await client.chat.completions.create(
                model=config.DEFAULT_MODEL,
                messages=messages,
                temperature=0.7,
                max_tokens=4000,
            )

            result_text = response.choices[0].message.content.strip()

            # Проверка качества
            if _check_quality(
                result_text,
                quality.min_words,
                quality.required_keywords,
            ):
                return result_text

            # Если качество не прошло и есть повторные попытки
            if attempt < max_attempts - 1:
                logger.warning(
                    "Проверка качества не пройдена для %s, попытка %d/%d",
                    service_type.value,
                    attempt + 1,
                    max_attempts,
                )
                # Добавляем инструкцию для улучшения
                messages.append({"role": "assistant", "content": result_text})
                messages.append({
                    "role": "user",
                    "content": (
                        "Текст недостаточно подробный. Пожалуйста, расширь ответ, "
                        "добавь больше деталей и убедись, что он содержит минимум "
                        f"{quality.min_words} слов."
                    ),
                })
            else:
                # Последняя попытка - возвращаем что есть
                return result_text

        except Exception as e:
            logger.error("Ошибка вызова OpenAI API: %s", str(e))
            if attempt < max_attempts - 1:
                continue
            return None

    return None
