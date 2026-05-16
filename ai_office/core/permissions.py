"""Ролевая модель доступа для AI Office."""

from enum import Enum
from typing import Optional

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from ai_office.core.database import async_session
from ai_office.core.models import User


class UserRole(str, Enum):
    """Роли пользователей в системе."""

    OWNER = "owner"
    ADMIN = "admin"
    VIEWER = "viewer"


# Иерархия ролей: owner > admin > viewer
ROLE_HIERARCHY = {
    UserRole.OWNER: 3,
    UserRole.ADMIN: 2,
    UserRole.VIEWER: 1,
}


async def get_or_create_user(
    telegram_id: int,
    username: str | None = None,
    session: Optional[AsyncSession] = None,
) -> User:
    """Получить или создать пользователя.

    Первый пользователь автоматически становится owner.
    Последующие пользователи получают роль viewer.

    Args:
        telegram_id: Telegram ID пользователя
        username: Username пользователя (опционально)
        session: Optional existing session to reuse (reduces connection churn)

    Returns:
        Объект User
    """
    if session is not None:
        return await _get_or_create_user_impl(telegram_id, username, session)

    async with async_session() as sess:
        return await _get_or_create_user_impl(telegram_id, username, sess)


async def _get_or_create_user_impl(
    telegram_id: int,
    username: str | None,
    session: AsyncSession,
) -> User:
    """Internal implementation for get_or_create_user."""
    # Ищем существующего пользователя
    result = await session.execute(
        select(User).where(User.telegram_id == telegram_id)
    )
    user = result.scalar_one_or_none()

    if user:
        # Обновляем username если изменился
        if username and user.username != username:
            user.username = username
            await session.commit()
        return user

    # Проверяем, есть ли уже пользователи в системе
    count_result = await session.execute(select(func.count(User.id)))
    user_count = count_result.scalar()

    # Первый пользователь - owner, остальные - viewer
    role = UserRole.OWNER.value if user_count == 0 else UserRole.VIEWER.value

    user = User(
        telegram_id=telegram_id,
        username=username,
        role=role,
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


async def check_permission(
    telegram_id: int,
    required_role: UserRole,
    session: Optional[AsyncSession] = None,
) -> bool:
    """Проверить, имеет ли пользователь необходимый уровень доступа.

    Args:
        telegram_id: Telegram ID пользователя
        required_role: Минимально необходимая роль
        session: Optional existing session to reuse (reduces connection churn)

    Returns:
        True если пользователь имеет достаточный уровень доступа
    """
    if session is not None:
        return await _check_permission_impl(telegram_id, required_role, session)

    async with async_session() as sess:
        return await _check_permission_impl(telegram_id, required_role, sess)


async def _check_permission_impl(
    telegram_id: int,
    required_role: UserRole,
    session: AsyncSession,
) -> bool:
    """Internal implementation for check_permission."""
    result = await session.execute(
        select(User).where(User.telegram_id == telegram_id)
    )
    user = result.scalar_one_or_none()

    if not user:
        return False

    user_level = ROLE_HIERARCHY.get(UserRole(user.role), 0)
    required_level = ROLE_HIERARCHY.get(required_role, 0)
    return user_level >= required_level


async def get_user_role(
    telegram_id: int,
    session: Optional[AsyncSession] = None,
) -> UserRole | None:
    """Получить роль пользователя по telegram_id.

    Args:
        telegram_id: Telegram ID пользователя
        session: Optional existing session to reuse

    Returns:
        UserRole или None если пользователь не найден
    """
    if session is not None:
        return await _get_user_role_impl(telegram_id, session)

    async with async_session() as sess:
        return await _get_user_role_impl(telegram_id, sess)


async def _get_user_role_impl(telegram_id: int, session: AsyncSession) -> UserRole | None:
    """Internal implementation for get_user_role."""
    result = await session.execute(
        select(User).where(User.telegram_id == telegram_id)
    )
    user = result.scalar_one_or_none()
    if user:
        return UserRole(user.role)
    return None


async def set_user_role(telegram_id: int, new_role: UserRole) -> bool:
    """Установить роль пользователя.

    Args:
        telegram_id: Telegram ID пользователя
        new_role: Новая роль

    Returns:
        True если роль успешно изменена
    """
    async with async_session() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == telegram_id)
        )
        user = result.scalar_one_or_none()
        if not user:
            return False

        user.role = new_role.value
        await session.commit()
        return True
