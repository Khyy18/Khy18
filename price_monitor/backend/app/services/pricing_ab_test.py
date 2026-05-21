"""A/B тесты тарифов подписки."""

import hashlib
import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class PricingPlan:
    plan_id: str
    name: str
    price_rub: int
    duration_days: int
    features: list[str]


# Варианты тарифов для A/B теста
PRICING_VARIANTS = {
    "A": [
        PricingPlan("vip_month", "VIP Месяц", 499, 30, [
            "Мгновенные уведомления",
            "Без рекламы",
            "Персональный дайджест",
        ]),
        PricingPlan("vip_year", "VIP Год", 3990, 365, [
            "Всё из Месяца",
            "Приоритетная поддержка",
            "Арбитраж цен",
        ]),
    ],
    "B": [
        PricingPlan("vip_month", "VIP Месяц", 690, 30, [
            "Мгновенные уведомления",
            "Без рекламы",
            "Персональный дайджест",
            "Арбитраж цен",
        ]),
        PricingPlan("vip_year", "VIP Год", 4990, 365, [
            "Всё из Месяца",
            "Приоритетная поддержка",
            "Сравнение товаров",
            "Прогноз цен",
        ]),
    ],
    "C": [
        PricingPlan("vip_week", "VIP Неделя", 149, 7, [
            "Без рекламы",
            "Мгновенные уведомления",
        ]),
        PricingPlan("vip_month", "VIP Месяц", 399, 30, [
            "Всё из Недели",
            "Персональный дайджест",
            "Арбитраж цен",
        ]),
        PricingPlan("vip_year", "VIP Год", 2990, 365, [
            "Всё из Месяца",
            "Прогноз цен",
            "Сравнение товаров",
            "Приоритетная поддержка",
        ]),
    ],
}


class PricingABTest:
    """A/B тест тарифов - детерминистическое распределение по user_id."""

    @staticmethod
    def get_variant(user_id: int) -> str:
        """Определить вариант тарифа для пользователя (стабильный хеш)."""
        hash_val = hashlib.md5(f"pricing_{user_id}".encode()).hexdigest()
        bucket = int(hash_val[:8], 16) % 3
        variants = list(PRICING_VARIANTS.keys())
        return variants[bucket]

    @staticmethod
    def get_plans(user_id: int) -> list[dict]:
        """Получить тарифы для пользователя."""
        variant = PricingABTest.get_variant(user_id)
        plans = PRICING_VARIANTS[variant]
        return [
            {
                "plan_id": p.plan_id,
                "name": p.name,
                "price_rub": p.price_rub,
                "duration_days": p.duration_days,
                "features": p.features,
                "variant": variant,
            }
            for p in plans
        ]


pricing_ab_test = PricingABTest()
