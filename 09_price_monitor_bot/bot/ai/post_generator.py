"""Генератор постов для Telegram-канала через LLM."""

import logging
from typing import Any

from openai import AsyncOpenAI

from bot.config import settings

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
Ты копирайтер для Telegram-канала о скидках на маркетплейсах.
Твоя задача - написать привлекательный пост о товаре со скидкой.

Правила:
- Пиши на русском языке
- Используй эмодзи для привлечения внимания
- Обязательно укажи старую и новую цену
- Создай ощущение срочности (ограниченное время, быстро разбирают)
- Если есть информация об отзывах, кратко упомяни
- В конце добавь ссылку с текстом "Купить со скидкой" используя placeholder {affiliate_link}
- Формат: HTML для Telegram (только теги: <b>, <i>, <u>, <s>, <a>, <code>, <pre>)
- Длина: 3-5 предложений максимум
- Старую цену оберни в <s> тег
"""


class PostGenerator:
    """Генератор рекламных постов для Telegram-канала."""

    def __init__(self) -> None:
        self._llm = AsyncOpenAI(
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url,
        )

    async def generate_post(
        self,
        product: dict[str, Any],
        discount_info: dict[str, Any],
        reviews_summary: str | None = None,
    ) -> str:
        """Сгенерировать пост для Telegram-канала.

        Args:
            product: dict с информацией о товаре (name, brand, price, old_price).
            discount_info: dict со скидкой (discount_percent, is_fraud).
            reviews_summary: краткая сводка отзывов (опционально).

        Returns:
            HTML-текст поста для Telegram с placeholder {affiliate_link}.
        """
        user_message = self._build_prompt(product, discount_info, reviews_summary)

        try:
            response = await self._llm.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": user_message},
                ],
                max_tokens=500,
                temperature=0.8,
            )

            post_text = response.choices[0].message.content or ""

            # Убедимся, что в тексте есть placeholder для ссылки
            if "{affiliate_link}" not in post_text:
                post_text += '\n\n<a href="{affiliate_link}">Купить со скидкой</a>'

            return post_text.strip()
        except Exception as e:
            logger.error("Ошибка генерации поста: %s", e)
            return self._fallback_post(product, discount_info)

    def _build_prompt(
        self,
        product: dict[str, Any],
        discount_info: dict[str, Any],
        reviews_summary: str | None,
    ) -> str:
        """Построить промпт для LLM."""
        lines = [
            f"Товар: {product.get('name', 'Неизвестный товар')}",
            f"Бренд: {product.get('brand', 'Нет')}",
            f"Текущая цена: {product.get('price', 0):.0f} руб.",
            f"Старая цена: {product.get('old_price', 0):.0f} руб.",
            f"Скидка: {discount_info.get('discount_percent', 0)}%",
        ]

        if reviews_summary:
            lines.append(f"Отзывы покупателей: {reviews_summary}")

        lines.append(
            "\nСоздай пост для Telegram-канала. "
            "Формат HTML. Вставь {affiliate_link} как URL ссылки."
        )
        return "\n".join(lines)

    @staticmethod
    def _fallback_post(product: dict[str, Any], discount_info: dict[str, Any]) -> str:
        """Запасной шаблон поста, если LLM недоступен."""
        name = product.get("name", "Товар")
        price = product.get("price", 0)
        old_price = product.get("old_price", 0)
        discount = discount_info.get("discount_percent", 0)

        return (
            f"\U0001f525 <b>{name}</b>\n\n"
            f"\U0001f4b0 Цена: <s>{old_price:.0f} \u20bd</s> \u2192 <b>{price:.0f} \u20bd</b>\n"
            f"\U0001f4c9 Скидка: {discount}%\n\n"
            f"\u26a1 Скорее забирай, пока не разобрали!\n\n"
            f'<a href="{{affiliate_link}}">Купить со скидкой</a>'
        )
