"""Модуль антифрода: обнаружение искусственного завышения цен перед скидкой."""

import logging
from dataclasses import dataclass

from openai import AsyncOpenAI

from bot.config import settings

logger = logging.getLogger(__name__)


@dataclass
class FraudResult:
    """Результат проверки на фейковую скидку."""

    is_fraud: bool
    confidence: float  # 0.0 - 1.0
    reason: str


class AntifraudDetector:
    """Детектор фейковых скидок на маркетплейсах."""

    def __init__(self) -> None:
        self._llm = AsyncOpenAI(
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url,
        )

    async def is_fake_discount(
        self,
        product_id: str,
        current_price: float,
        old_price: float,
        price_history: list[float],
    ) -> FraudResult:
        """Проверить, является ли скидка фейковой.

        Анализирует историю цен и текущую скидку.
        Для неоднозначных случаев использует LLM.
        """
        # Нет скидки - нет фрода
        if old_price <= 0 or current_price >= old_price:
            return FraudResult(is_fraud=False, confidence=1.0, reason="Нет скидки")

        discount_percent = (1 - current_price / old_price) * 100

        # Эвристика 1: старая цена появилась менее 7 дней назад (мало данных)
        if len(price_history) < 7:
            if discount_percent > 20:
                return FraudResult(
                    is_fraud=True,
                    confidence=0.8,
                    reason="Старая цена появилась недавно, скидка >20%",
                )

        # Эвристика 2: цена была поднята, а потом снижена за 14 дней
        if len(price_history) >= 3:
            recent = price_history[-14:] if len(price_history) >= 14 else price_history
            if len(recent) >= 3:
                min_price = min(recent[:-1])
                max_price = max(recent[:-1])
                # Цена сначала выросла, потом упала
                if max_price > min_price * 1.15 and current_price <= min_price * 1.05:
                    return FraudResult(
                        is_fraud=True,
                        confidence=0.9,
                        reason="Цена была поднята и снижена в течение 14 дней",
                    )

        # Эвристика 3: слишком большая скидка при малом числе отзывов
        if discount_percent > 70:
            return FraudResult(
                is_fraud=False,
                confidence=0.6,
                reason="Очень большая скидка (>70%), подозрительно",
            )

        # Для неоднозначных случаев (confidence 0.4-0.7) используем LLM
        if 0.4 <= self._heuristic_confidence(price_history, discount_percent) <= 0.7:
            return await self._ask_llm(product_id, current_price, old_price, price_history)

        return FraudResult(
            is_fraud=False,
            confidence=0.9,
            reason="Скидка выглядит реальной по истории цен",
        )

    def _heuristic_confidence(
        self, price_history: list[float], discount_percent: float
    ) -> float:
        """Оценка уверенности эвристик (внутренний метод)."""
        if not price_history:
            return 0.5
        # Если цена стабильна - маловероятен фрод
        if len(price_history) >= 7:
            avg = sum(price_history[-7:]) / 7
            variance = sum((p - avg) ** 2 for p in price_history[-7:]) / 7
            relative_var = variance / (avg ** 2) if avg > 0 else 0
            if relative_var < 0.01:
                return 0.2  # стабильная цена, скидка скорее всего реальная
            if relative_var > 0.1:
                return 0.6  # высокая волатильность
        return 0.5

    async def _ask_llm(
        self,
        product_id: str,
        current_price: float,
        old_price: float,
        price_history: list[float],
    ) -> FraudResult:
        """Спросить LLM для финального вердикта."""
        try:
            history_str = ", ".join(f"{p:.0f}" for p in price_history[-14:])
            prompt = (
                f"Товар ID: {product_id}\n"
                f"Текущая цена: {current_price:.0f} руб.\n"
                f"Старая цена: {old_price:.0f} руб.\n"
                f"История цен (последние дни): [{history_str}]\n\n"
                "Оцени, является ли скидка фейковой (цену сначала подняли, потом снизили). "
                "Ответь одним словом: ФРОД или РЕАЛЬНАЯ, затем кратко причину."
            )

            response = await self._llm.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "Ты аналитик маркетплейсов. Определяешь фейковые скидки."},
                    {"role": "user", "content": prompt},
                ],
                max_tokens=100,
                temperature=0.1,
            )

            answer = response.choices[0].message.content or ""
            is_fraud = "ФРОД" in answer.upper() or "FRAUD" in answer.upper()
            reason = answer.strip()

            return FraudResult(
                is_fraud=is_fraud,
                confidence=0.7,
                reason=reason,
            )
        except Exception as e:
            logger.error("Ошибка LLM антифрод: %s", e)
            return FraudResult(
                is_fraud=False,
                confidence=0.5,
                reason="Не удалось проверить через LLM",
            )
