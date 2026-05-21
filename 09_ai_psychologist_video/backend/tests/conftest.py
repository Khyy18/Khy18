"""
Фикстуры для тестов: in-memory SQLite, тестовый клиент, тестовый пользователь.
"""
import asyncio
import uuid
from decimal import Decimal
from datetime import datetime, timedelta

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.pool import StaticPool

from app.models.database import Base, User, PromoCode, Session, Transaction, TransactionType
from app.auth.jwt import create_token
from app.config import settings


# Тестовая БД в памяти
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for the test session."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture
async def test_engine():
    """Создание тестового движка с in-memory SQLite и StaticPool."""
    engine = create_async_engine(
        TEST_DATABASE_URL,
        echo=False,
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def test_session(test_engine):
    """Тестовая сессия БД."""
    session_factory = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session


@pytest_asyncio.fixture
async def client(test_engine, monkeypatch):
    """
    Тестовый HTTP-клиент. Подменяет async_session_factory на тестовую
    во всех модулях, которые его импортируют.
    """
    from app.models import database as db_module
    from app.sessions import router as sessions_router_mod
    from app.billing import payment as billing_payment_mod
    from app.billing import promo as billing_promo_mod
    from app.admin import router as admin_router_mod
    from app.subscriptions import router as subscriptions_router_mod
    from app.auth import router as auth_router_mod
    from app.referral import router as referral_router_mod
    from app.billing import worker as billing_worker_mod
    from app import main as main_mod

    test_factory = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)

    # Patch async_session_factory in all modules that import it
    monkeypatch.setattr(db_module, "async_session_factory", test_factory)
    monkeypatch.setattr(sessions_router_mod, "async_session_factory", test_factory)
    monkeypatch.setattr(billing_payment_mod, "async_session_factory", test_factory)
    monkeypatch.setattr(billing_promo_mod, "async_session_factory", test_factory)
    monkeypatch.setattr(admin_router_mod, "async_session_factory", test_factory)
    monkeypatch.setattr(subscriptions_router_mod, "async_session_factory", test_factory)
    monkeypatch.setattr(auth_router_mod, "async_session_factory", test_factory)
    monkeypatch.setattr(referral_router_mod, "async_session_factory", test_factory)
    monkeypatch.setattr(billing_worker_mod, "async_session_factory", test_factory)
    monkeypatch.setattr(main_mod, "async_session_factory", test_factory)

    from app.main import app
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest_asyncio.fixture
async def test_user(test_engine):
    """Создает тестового пользователя, возвращает (user_id, token)."""
    test_factory = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)

    user_id = str(uuid.uuid4())
    async with test_factory() as session:
        user = User(
            id=user_id,
            telegram_id=123456789,
            username="testuser",
            first_name="Test",
            balance=Decimal("100.00"),
        )
        session.add(user)
        await session.commit()

    token = create_token(user_id)
    return user_id, token


@pytest_asyncio.fixture
async def test_promo(test_engine):
    """Создает тестовый промокод."""
    test_factory = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)

    promo_id = str(uuid.uuid4())
    async with test_factory() as session:
        promo = PromoCode(
            id=promo_id,
            code="TEST100",
            amount=Decimal("100.00"),
            max_uses=5,
            current_uses=0,
            expires_at=datetime.utcnow() + timedelta(days=30),
        )
        session.add(promo)

        # Expired promo
        expired_promo = PromoCode(
            id=str(uuid.uuid4()),
            code="EXPIRED",
            amount=Decimal("50.00"),
            max_uses=5,
            current_uses=0,
            expires_at=datetime.utcnow() - timedelta(days=1),
        )
        session.add(expired_promo)

        # Max uses reached promo
        maxed_promo = PromoCode(
            id=str(uuid.uuid4()),
            code="MAXED",
            amount=Decimal("25.00"),
            max_uses=1,
            current_uses=1,
        )
        session.add(maxed_promo)

        await session.commit()
    return promo_id
