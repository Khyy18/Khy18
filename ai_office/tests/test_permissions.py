"""Тесты для ролевой модели доступа."""

import pytest
import pytest_asyncio
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from ai_office.core.database import Base
from ai_office.core.models import Agent, User
from ai_office.core.permissions import (
    UserRole,
    check_permission,
    get_or_create_user,
    get_user_role,
    set_user_role,
)


@pytest_asyncio.fixture
async def permission_session(monkeypatch):
    """Фикстура с in-memory DB для тестирования разрешений."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
    )
    session_factory = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Подменяем async_session в модуле permissions
    monkeypatch.setattr("ai_office.core.permissions.async_session", session_factory)

    async with session_factory() as session:
        yield session

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await engine.dispose()


@pytest.mark.asyncio
async def test_first_user_becomes_owner(permission_session):
    """Первый пользователь автоматически получает роль owner."""
    user = await get_or_create_user(telegram_id=100001, username="first_user")
    assert user.role == "owner"
    assert user.telegram_id == 100001
    assert user.username == "first_user"


@pytest.mark.asyncio
async def test_subsequent_users_become_viewer(permission_session):
    """Последующие пользователи получают роль viewer."""
    # Первый пользователь - owner
    await get_or_create_user(telegram_id=100001, username="owner_user")

    # Второй пользователь - viewer
    user2 = await get_or_create_user(telegram_id=100002, username="viewer_user")
    assert user2.role == "viewer"

    # Третий пользователь - тоже viewer
    user3 = await get_or_create_user(telegram_id=100003, username="another_viewer")
    assert user3.role == "viewer"


@pytest.mark.asyncio
async def test_get_or_create_existing_user(permission_session):
    """Повторный вызов для существующего пользователя возвращает его."""
    user1 = await get_or_create_user(telegram_id=100001, username="user_one")
    user2 = await get_or_create_user(telegram_id=100001, username="user_one_updated")

    assert user1.id == user2.id
    assert user2.username == "user_one_updated"


@pytest.mark.asyncio
async def test_check_permission_owner(permission_session):
    """Owner имеет все права."""
    await get_or_create_user(telegram_id=100001, username="owner")

    assert await check_permission(100001, UserRole.VIEWER) is True
    assert await check_permission(100001, UserRole.ADMIN) is True
    assert await check_permission(100001, UserRole.OWNER) is True


@pytest.mark.asyncio
async def test_check_permission_admin(permission_session):
    """Admin имеет права admin и viewer, но не owner."""
    # Создаём owner первым
    await get_or_create_user(telegram_id=100001, username="owner")
    # Создаём viewer, затем повышаем до admin
    await get_or_create_user(telegram_id=100002, username="admin_user")
    await set_user_role(100002, UserRole.ADMIN)

    assert await check_permission(100002, UserRole.VIEWER) is True
    assert await check_permission(100002, UserRole.ADMIN) is True
    assert await check_permission(100002, UserRole.OWNER) is False


@pytest.mark.asyncio
async def test_check_permission_viewer(permission_session):
    """Viewer имеет только права viewer."""
    await get_or_create_user(telegram_id=100001, username="owner")
    await get_or_create_user(telegram_id=100002, username="viewer")

    assert await check_permission(100002, UserRole.VIEWER) is True
    assert await check_permission(100002, UserRole.ADMIN) is False
    assert await check_permission(100002, UserRole.OWNER) is False


@pytest.mark.asyncio
async def test_check_permission_unknown_user(permission_session):
    """Несуществующий пользователь не имеет прав."""
    assert await check_permission(999999, UserRole.VIEWER) is False


@pytest.mark.asyncio
async def test_set_user_role(permission_session):
    """set_user_role корректно меняет роль."""
    await get_or_create_user(telegram_id=100001, username="owner")
    await get_or_create_user(telegram_id=100002, username="user")

    # Повышаем до admin
    result = await set_user_role(100002, UserRole.ADMIN)
    assert result is True

    role = await get_user_role(100002)
    assert role == UserRole.ADMIN

    # Понижаем обратно до viewer
    result = await set_user_role(100002, UserRole.VIEWER)
    assert result is True

    role = await get_user_role(100002)
    assert role == UserRole.VIEWER


@pytest.mark.asyncio
async def test_set_user_role_nonexistent(permission_session):
    """set_user_role для несуществующего пользователя возвращает False."""
    result = await set_user_role(999999, UserRole.ADMIN)
    assert result is False


@pytest.mark.asyncio
async def test_get_user_role(permission_session):
    """get_user_role возвращает роль пользователя."""
    await get_or_create_user(telegram_id=100001, username="owner")
    role = await get_user_role(100001)
    assert role == UserRole.OWNER


@pytest.mark.asyncio
async def test_get_user_role_nonexistent(permission_session):
    """get_user_role для несуществующего пользователя возвращает None."""
    role = await get_user_role(999999)
    assert role is None


@pytest.mark.asyncio
async def test_auto_seed_agents(permission_session, monkeypatch):
    """Авто-создание агентов в БД при пустой таблице."""
    from ai_office.telegram.handlers import _auto_seed_agents

    # Подменяем async_session в handlers
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    monkeypatch.setattr("ai_office.telegram.handlers.async_session", session_factory)

    await _auto_seed_agents()

    async with session_factory() as session:
        result = await session.execute(select(func.count(Agent.id)))
        count = result.scalar()
        assert count == 8  # 8 агентов из реестра

    # Повторный вызов не дублирует агентов
    await _auto_seed_agents()

    async with session_factory() as session:
        result = await session.execute(select(func.count(Agent.id)))
        count = result.scalar()
        assert count == 8

    await engine.dispose()


@pytest.mark.asyncio
async def test_api_status_returns_role(test_client):
    """GET /api/status возвращает user_role."""
    response = await test_client.get("/api/status")
    assert response.status_code == 200
    data = response.json()
    assert "user_role" in data
    # В dev-режиме (skip_telegram_auth=True) роль owner
    assert data["user_role"] == "owner"


@pytest_asyncio.fixture
async def test_client():
    """Фикстура HTTP клиента для тестирования API."""
    from httpx import AsyncClient, ASGITransport
    from ai_office.api.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
