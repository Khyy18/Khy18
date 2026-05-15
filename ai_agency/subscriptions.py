"""Система подписок AI-агентства: проверка, активация, лимиты."""

import logging
from datetime import datetime, timedelta
from typing import Optional

import config
import database
from models import SubscriptionTier

logger = logging.getLogger(__name__)

# Лимиты заказов по тарифам
TIER_ORDER_LIMITS = {
    SubscriptionTier.BASIC: config.SUBSCRIPTION_BASIC_ORDERS,
    SubscriptionTier.PRO: None,  # безлимит
}

# Цены тарифов
TIER_PRICES = {
    SubscriptionTier.BASIC: config.SUBSCRIPTION_BASIC_PRICE,
    SubscriptionTier.PRO: config.SUBSCRIPTION_PRO_PRICE,
}


async def check_subscription(telegram_id: int) -> Optional[dict]:
    """
    Проверить активную подписку пользователя.

    Возвращает dict подписки или None если нет активной.
    """
    sub = await database.get_subscription(telegram_id)
    if not sub:
        return None

    # Проверяем срок действия
    expires_at = sub.get("expires_at")
    if expires_at:
        try:
            expires_dt = datetime.fromisoformat(expires_at)
            if expires_dt < datetime.utcnow():
                # Подписка истекла
                await database.update_subscription(sub["id"], status="expired")
                return None
        except (ValueError, TypeError):
            pass

    return sub


async def can_place_order(telegram_id: int) -> bool:
    """
    Проверить, может ли пользователь разместить заказ по подписке.

    True если подписка активна и лимит не исчерпан (PRO - безлимит).
    """
    sub = await check_subscription(telegram_id)
    if not sub:
        return False

    tier = sub.get("tier", "none")
    if tier == SubscriptionTier.PRO.value:
        return True

    if tier == SubscriptionTier.BASIC.value:
        orders_used = sub.get("orders_used", 0)
        limit = TIER_ORDER_LIMITS.get(SubscriptionTier.BASIC, 0)
        if limit is None:
            return True
        return orders_used < limit

    return False


async def atomic_use_subscription(telegram_id: int) -> bool:
    """
    Атомарно проверить и инкрементировать использование подписки.

    Использует UPDATE ... WHERE с проверкой лимита в одном запросе,
    что исключает race condition при параллельных запросах.
    Возвращает True если заказ по подписке разрешён и учтён.
    """
    sub = await check_subscription(telegram_id)
    if not sub:
        return False

    tier = sub.get("tier", "none")
    if tier == SubscriptionTier.PRO.value:
        return await database.atomic_increment_subscription_usage_unlimited(telegram_id)

    if tier == SubscriptionTier.BASIC.value:
        limit = TIER_ORDER_LIMITS.get(SubscriptionTier.BASIC, 0)
        if limit is None:
            return await database.atomic_increment_subscription_usage_unlimited(telegram_id)
        return await database.atomic_increment_subscription_usage(telegram_id, limit)

    return False


async def increment_subscription_usage(telegram_id: int) -> None:
    """Увеличить счётчик использованных заказов в подписке."""
    sub = await check_subscription(telegram_id)
    if not sub:
        return

    new_count = sub.get("orders_used", 0) + 1
    await database.update_subscription(sub["id"], orders_used=new_count)


async def activate_subscription(
    telegram_id: int,
    tier: str,
    yookassa_sub_id: Optional[str] = None,
) -> None:
    """
    Активировать подписку для пользователя.

    Срок действия - 30 дней от момента активации.
    """
    expires_at = (datetime.utcnow() + timedelta(days=30)).isoformat()
    await database.create_subscription(
        client_id=telegram_id,
        tier=tier,
        expires_at=expires_at,
        yookassa_subscription_id=yookassa_sub_id,
    )
    logger.info(
        "Подписка %s активирована для клиента %d, до %s",
        tier, telegram_id, expires_at,
    )


async def expire_subscriptions() -> None:
    """
    Пометить истёкшие подписки как expired.

    Вызывается периодически (по расписанию).
    Маршрутизирует через database модуль для единообразия.
    """
    count = await database.expire_active_subscriptions()
    if count > 0:
        logger.info("Истекло подписок: %d", count)
