"""Модуль биллинга AI-агентства: проверка баланса, списание, пополнение."""

import database


async def check_balance(telegram_id: int, amount: float) -> bool:
    """Проверить, достаточно ли средств на балансе клиента."""
    balance = await database.get_client_balance(telegram_id)
    return balance >= amount


async def charge_client(telegram_id: int, amount: float) -> bool:
    """
    Списать средства с баланса клиента.
    Возвращает True если списание прошло, False если недостаточно средств.
    """
    balance = await database.get_client_balance(telegram_id)
    if balance < amount:
        return False

    new_balance = balance - amount
    await database.update_balance(telegram_id, new_balance)
    await database.update_total_spent(telegram_id, amount)
    return True


async def top_up_balance(telegram_id: int, amount: float, method: str = "manual") -> float:
    """
    Пополнить баланс клиента.
    Возвращает новый баланс.
    """
    current_balance = await database.get_client_balance(telegram_id)
    new_balance = current_balance + amount
    await database.update_balance(telegram_id, new_balance)
    await database.add_payment(telegram_id, amount, method)
    return new_balance
