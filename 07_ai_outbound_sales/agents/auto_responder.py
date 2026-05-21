"""Автономный LLM-ответчик на входящие сообщения от лидов.

Полностью автоматический: классифицирует ответ, генерирует человечный reply,
отправляет без участия человека. Пробрасывает админу только сложные случаи.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class ReplyIntent(Enum):
    """Классификация намерения ответа."""
    INTERESTED = "interested"
    QUESTION = "question"
    OBJECTION = "objection"
    BOOKING = "booking"
    UNSUBSCRIBE = "unsubscribe"
    SPAM = "spam"
    COMPLEX = "complex"


@dataclass
class IncomingReply:
    """Входящий ответ от лида."""
    lead_id: str
    lead_name: str
    lead_company: str
    product_name: str
    message_text: str
    channel: str  # "email" или "telegram"


@dataclass
class AutoResponse:
    """Сгенерированный автоответ."""
    intent: ReplyIntent
    response_text: str
    should_forward_to_admin: bool
    confidence: float


PRODUCT_KNOWLEDGE = {
    "Price Monitor": {
        "what": "Мониторинг цен конкурентов на WB и Ozon в реальном времени",
        "price": "от 990 р/мес, есть бесплатный тест 7 дней",
        "benefits": [
            "Алерты при изменении цен конкурентов",
            "ИИ-прогноз цен",
            "Рекомендации оптимальной цены",
            "Аналитика категорий и трендов",
        ],
        "trial": "7 дней бесплатно, без карты",
        "bot_link": "@PriceMonitorBot",
    },
    "AI Text Agency": {
        "what": "ИИ-копирайтер для бизнеса",
        "price": "от 999 р/мес, первые 10 текстов бесплатно",
        "benefits": [
            "Посты для соцсетей в вашем стиле",
            "SEO-описания товаров",
            "Email-рассылки",
            "Обучается на ваших примерах",
        ],
        "trial": "10 текстов бесплатно",
        "bot_link": "@AITextAgencyBot",
    },
    "AI Office": {
        "what": "ИИ-ассистенты для автоматизации офисной рутины",
        "price": "от 4 990 р/мес, 14 дней бесплатно",
        "benefits": [
            "Автоматические отчёты",
            "Ответы на типовые письма",
            "Ведение CRM",
            "Планирование встреч",
        ],
        "trial": "14 дней бесплатно",
        "bot_link": "@AIOfficeBot",
    },
}


class AutoResponder:
    """LLM-автоответчик с человечным tone of voice."""

    def __init__(
        self,
        openai_api_key: str = "",
        openai_base_url: str = "https://api.groq.com/openai/v1",
        model: str = "llama-3.3-70b-versatile",
        admin_notify_url: str = "",
    ):
        self.api_key = openai_api_key
        self.base_url = openai_base_url
        self.model = model
        self.admin_notify_url = admin_notify_url

    async def process_reply(self, reply: IncomingReply) -> AutoResponse:
        """Обработать входящий ответ: классифицировать и сгенерировать ответ."""
        intent = await self._classify_intent(reply)
        logger.info(f"Reply from {reply.lead_name}: intent={intent.value}")

        if intent == ReplyIntent.UNSUBSCRIBE:
            return AutoResponse(
                intent=intent,
                response_text="",
                should_forward_to_admin=False,
                confidence=0.95,
            )

        if intent == ReplyIntent.SPAM:
            return AutoResponse(
                intent=intent,
                response_text="",
                should_forward_to_admin=False,
                confidence=0.9,
            )

        if intent == ReplyIntent.COMPLEX:
            return AutoResponse(
                intent=intent,
                response_text="",
                should_forward_to_admin=True,
                confidence=0.4,
            )

        response_text = await self._generate_response(reply, intent)
        should_forward = intent == ReplyIntent.BOOKING

        return AutoResponse(
            intent=intent,
            response_text=response_text,
            should_forward_to_admin=should_forward,
            confidence=0.85,
        )

    async def _classify_intent(self, reply: IncomingReply) -> ReplyIntent:
        """Классифицировать намерение через LLM."""
        system_prompt = (
            "Ты классификатор входящих email-ответов. Определи намерение:\n"
            "- interested: хочет узнать больше\n"
            "- question: задаёт конкретный вопрос\n"
            "- objection: возражает (дорого, не сейчас)\n"
            "- booking: готов к встрече/демо\n"
            "- unsubscribe: просит не писать\n"
            "- spam: автоответ, out of office\n"
            "- complex: непонятно, нужен человек\n\n"
            "Ответь ОДНИМ СЛОВОМ."
        )
        user_prompt = f"Сообщение от {reply.lead_name} ({reply.lead_company}):\n\n{reply.message_text[:500]}"

        result = await self._call_llm(system_prompt, user_prompt, max_tokens=20)
        result_lower = result.strip().lower()

        for intent in ReplyIntent:
            if intent.value in result_lower:
                return intent
        return ReplyIntent.COMPLEX

    async def _generate_response(self, reply: IncomingReply, intent: ReplyIntent) -> str:
        """Сгенерировать человечный ответ через LLM."""
        product = PRODUCT_KNOWLEDGE.get(reply.product_name, {})

        system_prompt = (
            "Ты менеджер по продажам. Пишешь от первого лица, по-человечески, без канцелярита.\n"
            "Стиль: дружелюбный, конкретный, без воды. Как будто пишешь знакомому коллеге.\n"
            "Максимум 4-5 предложений. Подписывайся: Алексей\n\n"
            f"Продукт: {reply.product_name}\n"
            f"Что это: {product.get('what', '')}\n"
            f"Цена: {product.get('price', '')}\n"
            f"Преимущества: {', '.join(product.get('benefits', []))}\n"
            f"Тест: {product.get('trial', '')}\n"
            f"Ссылка: {product.get('bot_link', '')}\n\n"
            f"Намерение собеседника: {intent.value}"
        )

        prompts = {
            ReplyIntent.INTERESTED: (
                f"{reply.lead_name} ответил что интересно:\n\"{reply.message_text[:300]}\"\n\n"
                "Подтверди интерес, дай ссылку на тест, предложи помочь с настройкой."
            ),
            ReplyIntent.QUESTION: (
                f"{reply.lead_name} задал вопрос:\n\"{reply.message_text[:300]}\"\n\n"
                "Ответь конкретно. Если не знаешь — предложи попробовать бесплатно."
            ),
            ReplyIntent.OBJECTION: (
                f"{reply.lead_name} возражает:\n\"{reply.message_text[:300]}\"\n\n"
                "Мягко обработай. Не дави. Упомяни бесплатный тест."
            ),
            ReplyIntent.BOOKING: (
                f"{reply.lead_name} готов к встрече:\n\"{reply.message_text[:300]}\"\n\n"
                "Подтверди, предложи 2-3 слота, дай ссылку на бот."
            ),
        }

        user_prompt = prompts.get(
            intent,
            f"{reply.lead_name} написал:\n\"{reply.message_text[:300]}\"\n\nОтветь уместно."
        )

        return await self._call_llm(system_prompt, user_prompt, max_tokens=300)

    async def _call_llm(self, system_prompt: str, user_prompt: str, max_tokens: int = 200) -> str:
        """Вызов LLM через OpenAI-совместимый API."""
        if not self.api_key:
            logger.warning("No API key, returning fallback")
            return self._fallback_response()

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.post(
                    f"{self.base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    json={
                        "model": self.model,
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_prompt},
                        ],
                        "max_tokens": max_tokens,
                        "temperature": 0.7,
                    },
                )
                response.raise_for_status()
                data = response.json()
                return data["choices"][0]["message"]["content"].strip()
        except Exception as e:
            logger.error(f"LLM call failed: {e}")
            return self._fallback_response()

    @staticmethod
    def _fallback_response() -> str:
        """Ответ если LLM недоступен."""
        return "Спасибо за ответ! Передал коллеге — свяжется в ближайшее время.\n\nАлексей"

    async def notify_admin(self, reply: IncomingReply, intent: ReplyIntent) -> None:
        """Уведомить админа о важном ответе."""
        if not self.admin_notify_url:
            logger.info(f"Would notify admin: {reply.lead_name} ({intent.value})")
            return

        text = (
            f"\u2501" * 24 + "\n"
            f"\U0001f4e8 Новый ответ от лида\n"
            f"\u2501" * 24 + "\n"
            f"\U0001f464 {reply.lead_name} ({reply.lead_company})\n"
            f"\U0001f4e6 Продукт: {reply.product_name}\n"
            f"\U0001f3f7 Намерение: {intent.value}\n"
            f"\u2501" * 24 + "\n"
            f"{reply.message_text[:200]}\n"
            f"\u2501" * 24
        )

        try:
            async with httpx.AsyncClient(timeout=10) as client:
                await client.post(self.admin_notify_url, json={"text": text})
        except Exception as e:
            logger.error(f"Failed to notify admin: {e}")


auto_responder = AutoResponder()
