"""LLM-based customer support chatbot."""
from __future__ import annotations

import logging

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """Ты - AI-помощник сервиса мониторинга цен Price Monitor. Отвечай на вопросы пользователей кратко и по делу.

FAQ:
1. Как настроить алерт? - Перейдите в раздел "Оповещения", нажмите "+", укажите ключевое слово и максимальную цену.
2. Как подключить VIP? - Перейдите в "Профиль" -> "Улучшить". Доступна оплата через ЮKassa или Telegram Stars.
3. Что дает VIP? - Ранний доступ к скидкам (на 30 минут раньше), без рекламы, персональные дайджесты.
4. Как работает арбитраж? - Система сравнивает цены на один товар между WB и Ozon, показывая разницу в %.
5. Как работают реферралы? - В профиле есть реферальная ссылка. За каждого друга вы получаете бонусные дни VIP.
6. Как отменить подписку? - VIP автоматически истекает по окончании срока, продление только вручную.
7. Безопасны ли мои данные? - Мы храним только Telegram ID и настройки. Не собираем личные данные.

Если вопрос не связан с сервисом, вежливо перенаправь пользователя к нужному разделу."""


class SupportBot:
    """AI support bot using OpenAI-compatible API."""

    async def answer(self, user_message: str, history: list[dict] | None = None) -> str:
        """Generate support answer given user message and conversation history."""
        if not settings.openai_api_key:
            return "Извините, AI-помощник временно недоступен. Обратитесь в @price_monitor_support."

        messages: list[dict] = [{"role": "system", "content": SYSTEM_PROMPT}]
        if history:
            messages.extend(history[-10:])  # Last 10 messages for context
        messages.append({"role": "user", "content": user_message})

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    f"{settings.openai_base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {settings.openai_api_key}"},
                    json={
                        "model": "gpt-4o-mini",
                        "messages": messages,
                        "max_tokens": 500,
                        "temperature": 0.7,
                    },
                )
                if resp.status_code == 200:
                    data = resp.json()
                    return data["choices"][0]["message"]["content"].strip()
        except Exception as e:
            logger.error("Support bot error: %s", e)
        return "Извините, произошла ошибка. Попробуйте позже или обратитесь в @price_monitor_support."


support_bot = SupportBot()
