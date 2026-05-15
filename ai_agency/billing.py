"""Модуль биллинга AI-агентства: проверка баланса, списание, пополнение."""

import aiosqlite

import config
import database


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
