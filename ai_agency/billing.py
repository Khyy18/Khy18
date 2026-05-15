"""Модуль биллинга AI-агентства: проверка баланса, списание, пополнение, подписки."""

import aiosqlite

import config
import database
import subscriptions


async def check_balance(telegram_id: int, amount: float) -> bool:
    """Проверить, достаточно ли средств на балансе клиента."""
    balance = await database.get_client_balance(telegram_id)
    return balance >= amount


async def charge_client(telegram_id: int, amount: float) -> bool:
    """
    Атомарно списать средства с баланса клиента.
    Возвращает True если списание прошло, False если недостаточно средств.
    Использует атомарный UPDATE с проверкой balance >= amount.
    """
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        cursor = await db.execute(
            "UPDATE clients SET balance = balance - ? WHERE telegram_id = ? AND balance >= ?",
            (amount, telegram_id, amount),
        )
        if cursor.rowcount != 1:
            await db.rollback()
            return False
        await db.execute(
            "UPDATE clients SET total_spent = total_spent + ? WHERE telegram_id = ?",
            (amount, telegram_id),
        )
        await db.commit()
    return True


async def top_up_balance(telegram_id: int, amount: float, method: str = "manual") -> float:
    """
    Атомарно пополнить баланс клиента.
    Возвращает новый баланс.
    """
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        await db.execute(
            "UPDATE clients SET balance = balance + ? WHERE telegram_id = ?",
            (amount, telegram_id),
        )
        await db.commit()

    await database.add_payment(telegram_id, amount, method)
    new_balance = await database.get_client_balance(telegram_id)
    return new_balance


async def check_can_order(telegram_id: int, price: float) -> bool:
    """
    Проверить, может ли клиент оформить заказ.

    Сначала проверяет подписку (если активна и лимит не исчерпан - True).
    Если нет подписки - делегирует проверку charge_or_use_subscription,
    которая атомарно проверяет и списывает. Здесь только проверяем подписку.
    """
    # Проверяем подписку
    if await subscriptions.can_place_order(telegram_id):
        return True
    # Нет подписки или лимит исчерпан - проверяем баланс (только для UX)
    balance = await database.get_client_balance(telegram_id)
    return balance >= price


async def charge_or_use_subscription(telegram_id: int, price: float) -> bool:
    """
    Списать средства: подписка или баланс.

    Если есть активная подписка с доступным лимитом - атомарно проверяет
    и инкрементирует usage (исключает race condition).
    Иначе списывает с баланса.
    Возвращает True если успешно, False если недостаточно средств.
    """
    # Пробуем атомарно использовать подписку
    if await subscriptions.atomic_use_subscription(telegram_id):
        return True
    # Списываем с баланса
    return await charge_client(telegram_id, price)


async def check_free_trial(telegram_id: int) -> bool:
    """
    Проверить, доступен ли бесплатный пробный заказ.

    Возвращает True если free_trial_used == 0 (триал не использован).
    """
    return not await database.get_client_trial_used(telegram_id)


async def mark_free_trial_used(telegram_id: int) -> None:
    """Отметить бесплатный пробный заказ как использованный."""
    await database.mark_trial_used(telegram_id)
