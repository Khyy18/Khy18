"""Tests for production calendar endpoint."""

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.app import create_app
from backend.database import Base, get_db

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"
test_engine = create_async_engine(TEST_DATABASE_URL, echo=False)
TestSessionLocal = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)


async def override_get_db():
    async with TestSessionLocal() as session:
        yield session


@pytest_asyncio.fixture
async def client():
    application = create_app()
    application.dependency_overrides[get_db] = override_get_db

    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    transport = ASGITransport(app=application)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.mark.asyncio
async def test_calendar_2024_march(client):
    """Test that March 2024 has 20 working days."""
    response = await client.get("/api/v1/calendar/2024/3")
    assert response.status_code == 200
    data = response.json()
    assert data["year"] == 2024
    assert data["month"] == 3
    assert data["working_days"] == 20
    assert data["total_days"] == 31
    assert 8 in data["holidays"]


@pytest.mark.asyncio
async def test_calendar_2025_january(client):
    """Test that January 2025 has 17 working days."""
    response = await client.get("/api/v1/calendar/2025/1")
    assert response.status_code == 200
    data = response.json()
    assert data["working_days"] == 17
    assert data["holidays"] == [1, 2, 3, 4, 5, 6, 7, 8]


@pytest.mark.asyncio
async def test_calendar_unknown_year(client):
    """Test 404 for unknown year."""
    response = await client.get("/api/v1/calendar/2020/1")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_calendar_unknown_month(client):
    """Test 404 for invalid month."""
    response = await client.get("/api/v1/calendar/2024/13")
    assert response.status_code == 404
