"""Тесты для API usage endpoint."""

from datetime import datetime, timezone

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from ai_office.api.main import app
from ai_office.core.database import Base, get_session
from ai_office.core.models import TokenUsage


@pytest_asyncio.fixture
async def usage_session():
    """Фикстура сессии для тестов usage."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    session_factory = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with session_factory() as session:
        yield session

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await engine.dispose()


@pytest_asyncio.fixture
async def usage_client(usage_session: AsyncSession):
    """Фикстура HTTP клиента для тестирования usage API."""

    async def override_get_session():
        yield usage_session

    app.dependency_overrides[get_session] = override_get_session

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def seed_usage(usage_session: AsyncSession):
    """Seed token_usage data."""
    now = datetime.now(timezone.utc)

    usages = [
        TokenUsage(
            provider="openai",
            model="gpt-4o-mini",
            prompt_tokens=100,
            completion_tokens=50,
            estimated_cost_usd=0.000045,
            agent_name="alice",
            timestamp=now,
        ),
        TokenUsage(
            provider="openai",
            model="gpt-4o-mini",
            prompt_tokens=200,
            completion_tokens=100,
            estimated_cost_usd=0.00009,
            agent_name="sam",
            timestamp=now,
        ),
        TokenUsage(
            provider="anthropic",
            model="claude-3-5-sonnet-20241022",
            prompt_tokens=150,
            completion_tokens=75,
            estimated_cost_usd=0.001575,
            agent_name="alice",
            timestamp=now,
        ),
    ]

    usage_session.add_all(usages)
    await usage_session.commit()
    return usages


@pytest.mark.asyncio
async def test_get_usage_empty(usage_client):
    """GET /api/usage возвращает пустую статистику без данных."""
    response = await usage_client.get("/api/usage")
    assert response.status_code == 200
    data = response.json()
    assert data["total_today"]["total_cost"] == 0
    assert data["total_today"]["prompt_tokens"] == 0
    assert data["total_today"]["completion_tokens"] == 0
    assert data["per_agent"] == []
    assert data["per_provider"] == []
    assert "daily_budget" in data
    assert "budget_remaining" in data


@pytest.mark.asyncio
async def test_get_usage_with_data(usage_client, seed_usage):
    """GET /api/usage возвращает корректную статистику с данными."""
    response = await usage_client.get("/api/usage")
    assert response.status_code == 200
    data = response.json()

    # Total
    assert data["total_today"]["prompt_tokens"] == 450  # 100 + 200 + 150
    assert data["total_today"]["completion_tokens"] == 225  # 50 + 100 + 75
    assert data["total_today"]["total_cost"] > 0

    # Per agent
    assert len(data["per_agent"]) == 2
    agent_names = [a["agent_name"] for a in data["per_agent"]]
    assert "alice" in agent_names
    assert "sam" in agent_names

    # Per provider
    assert len(data["per_provider"]) == 2
    providers = [p["provider"] for p in data["per_provider"]]
    assert "openai" in providers
    assert "anthropic" in providers

    # Budget fields
    assert data["daily_budget"] > 0
    assert "budget_remaining" in data
