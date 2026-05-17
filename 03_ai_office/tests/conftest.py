"""Фикстуры для тестов AI Office."""

from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from ai_office.core.database import Base, get_session
from ai_office.core.models import (
    Agent,
    Task,
    ActivityLog,
    Plan,
    PlanStep,
    Tenant,
    User,
    TenantAgent,
)
from ai_office.api.main import app
from ai_office.api.auth import hash_password, create_access_token


@pytest_asyncio.fixture
async def async_session():
    """Фикстура асинхронной сессии с in-memory SQLite."""
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

    async with session_factory() as session:
        yield session

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await engine.dispose()


@pytest_asyncio.fixture
async def test_client(async_session: AsyncSession):
    """Фикстура HTTP клиента для тестирования FastAPI."""

    async def override_get_session():
        yield async_session

    app.dependency_overrides[get_session] = override_get_session

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def create_tenant(async_session: AsyncSession) -> Tenant:
    """Create a test tenant."""
    tenant = Tenant(
        name="Test Company",
        email="admin@testcompany.com",
        plan_name="trial",
    )
    async_session.add(tenant)
    await async_session.commit()
    await async_session.refresh(tenant)
    return tenant


@pytest_asyncio.fixture
async def create_user(async_session: AsyncSession, create_tenant: Tenant) -> User:
    """Create a test user for the test tenant."""
    user = User(
        tenant_id=create_tenant.id,
        email="user@testcompany.com",
        password_hash=hash_password("testpassword123"),
        role="admin",
        is_super_admin=False,
    )
    async_session.add(user)
    await async_session.commit()
    await async_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def auth_headers(create_user: User, create_tenant: Tenant) -> dict:
    """Return Authorization headers with a valid JWT token."""
    token_data = {"sub": create_user.id, "tenant_id": create_tenant.id}
    token = create_access_token(token_data)
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def seed_data(async_session: AsyncSession):
    """Фикстура с тестовыми данными: агенты, задачи, логи активности."""
    # Создаем агентов
    alice = Agent(
        name="Alice",
        role="Персональный ассистент",
        system_prompt="Ты Alice - персональный ассистент.",
        status="idle",
    )
    sam = Agent(
        name="Sam",
        role="Разработчик",
        system_prompt="Ты Sam - разработчик.",
        status="busy",
    )
    async_session.add_all([alice, sam])
    await async_session.flush()

    # Создаем задачи
    task1 = Task(
        description="Написать документацию",
        creator_type="user",
        creator_id="user_123",
        executor_id=alice.id,
        status="open",
        priority="high",
    )
    task2 = Task(
        description="Исправить баг в API",
        creator_type="agent",
        creator_id="alice",
        executor_id=sam.id,
        status="in_progress",
        priority="medium",
    )
    async_session.add_all([task1, task2])
    await async_session.flush()

    # Создаем логи активности
    log1 = ActivityLog(
        agent_id=alice.id,
        action_type="task_created",
        action_description="Создана задача: Написать документацию",
    )
    log2 = ActivityLog(
        agent_id=sam.id,
        action_type="task_started",
        action_description="Начата работа над: Исправить баг в API",
    )
    async_session.add_all([log1, log2])
    await async_session.commit()

    return {"agents": [alice, sam], "tasks": [task1, task2], "logs": [log1, log2]}
