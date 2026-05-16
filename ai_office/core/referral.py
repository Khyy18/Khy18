"""Логика реферальной системы с 3-уровневым отслеживанием."""

import secrets
import string

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from ai_office.core.models import Referral


def _generate_code() -> str:
    """Генерация уникального 8-символьного алфанумерического кода."""
    alphabet = string.ascii_uppercase + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(8))


async def generate_referral_code(
    user_telegram_id: int, session: AsyncSession
) -> str:
    """Создает уникальный реферальный код и сохраняет в БД.

    Args:
        user_telegram_id: Telegram ID пользователя-реферера
        session: Асинхронная сессия БД

    Returns:
        Уникальный 8-символьный код
    """
    # Проверяем, есть ли уже код у пользователя
    result = await session.execute(
        select(Referral).where(
            Referral.referrer_telegram_id == user_telegram_id,
            Referral.referred_telegram_id.is_(None),
        )
    )
    existing = result.scalar_one_or_none()
    if existing:
        return existing.referral_code

    # Генерируем уникальный код
    for _ in range(10):
        code = _generate_code()
        check = await session.execute(
            select(Referral).where(Referral.referral_code == code)
        )
        if check.scalar_one_or_none() is None:
            break
    else:
        code = _generate_code()

    referral = Referral(
        referrer_telegram_id=user_telegram_id,
        referral_code=code,
        level=1,
    )
    session.add(referral)
    await session.commit()
    return code


async def apply_referral(
    new_user_telegram_id: int, code: str, session: AsyncSession
) -> dict:
    """Применяет реферальный код для нового пользователя.

    Отслеживает цепочку до 3 уровней:
    - L1: реферер +100 сообщений, приглашенный +100
    - L2: оригинальный реферер +50
    - L3: оригинальный реферер +25

    Args:
        new_user_telegram_id: Telegram ID нового пользователя
        code: Реферальный код
        session: Асинхронная сессия БД

    Returns:
        Словарь с информацией о результате
    """
    # Находим реферальную запись по коду
    result = await session.execute(
        select(Referral).where(
            Referral.referral_code == code,
            Referral.referred_telegram_id.is_(None),
        )
    )
    referral = result.scalar_one_or_none()

    if referral is None:
        return {"success": False, "message": "Код не найден или уже использован", "bonus_granted": 0}

    # Нельзя реферить самого себя
    if referral.referrer_telegram_id == new_user_telegram_id:
        return {"success": False, "message": "Нельзя использовать свой код", "bonus_granted": 0}

    # Проверяем, не применял ли уже этот пользователь реферальный код
    existing_check = await session.execute(
        select(Referral).where(
            Referral.referred_telegram_id == new_user_telegram_id,
            Referral.level == 1,
        )
    )
    if existing_check.scalar_one_or_none() is not None:
        return {"success": False, "message": "Вы уже использовали реферальный код", "bonus_granted": 0}

    # Применяем L1 бонус
    referral.referred_telegram_id = new_user_telegram_id
    referral.bonus_granted = True
    referral.level = 1

    total_bonus = 100  # L1: +100 рефереру, +100 приглашенному

    # Ищем L2: кто пригласил нашего реферера?
    l2_result = await session.execute(
        select(Referral).where(
            Referral.referred_telegram_id == referral.referrer_telegram_id,
            Referral.level == 1,
        )
    )
    l2_referral = l2_result.scalar_one_or_none()

    if l2_referral is not None:
        # Создаем L2 запись
        l2_entry = Referral(
            referrer_telegram_id=l2_referral.referrer_telegram_id,
            referred_telegram_id=new_user_telegram_id,
            referral_code=code + "_L2",
            level=2,
            bonus_granted=True,
        )
        session.add(l2_entry)
        total_bonus += 50

        # Ищем L3: кто пригласил L2 реферера?
        l3_result = await session.execute(
            select(Referral).where(
                Referral.referred_telegram_id == l2_referral.referrer_telegram_id,
                Referral.level == 1,
            )
        )
        l3_referral = l3_result.scalar_one_or_none()

        if l3_referral is not None:
            l3_entry = Referral(
                referrer_telegram_id=l3_referral.referrer_telegram_id,
                referred_telegram_id=new_user_telegram_id,
                referral_code=code + "_L3",
                level=3,
                bonus_granted=True,
            )
            session.add(l3_entry)
            total_bonus += 25

    await session.commit()

    return {
        "success": True,
        "message": "Реферальный код применен! Бонус начислен.",
        "bonus_granted": total_bonus,
    }


async def get_referral_stats(
    user_telegram_id: int, session: AsyncSession
) -> dict:
    """Возвращает статистику рефералов пользователя.

    Args:
        user_telegram_id: Telegram ID пользователя
        session: Асинхронная сессия БД

    Returns:
        Словарь со статистикой: direct_referrals, level_2, level_3, total_bonus
    """
    # L1 - прямые рефералы
    l1_result = await session.execute(
        select(func.count(Referral.id)).where(
            Referral.referrer_telegram_id == user_telegram_id,
            Referral.level == 1,
            Referral.referred_telegram_id.isnot(None),
        )
    )
    direct_referrals = l1_result.scalar() or 0

    # L2
    l2_result = await session.execute(
        select(func.count(Referral.id)).where(
            Referral.referrer_telegram_id == user_telegram_id,
            Referral.level == 2,
        )
    )
    level_2 = l2_result.scalar() or 0

    # L3
    l3_result = await session.execute(
        select(func.count(Referral.id)).where(
            Referral.referrer_telegram_id == user_telegram_id,
            Referral.level == 3,
        )
    )
    level_3 = l3_result.scalar() or 0

    total_bonus = (direct_referrals * 100) + (level_2 * 50) + (level_3 * 25)

    return {
        "direct_referrals": direct_referrals,
        "level_2": level_2,
        "level_3": level_3,
        "total_bonus": total_bonus,
    }
