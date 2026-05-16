"""E2E test fixtures for cross-component integration tests."""

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.app import create_app
from backend.database import Base, get_db

# Test database - in-memory SQLite
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"
test_engine = create_async_engine(TEST_DATABASE_URL, echo=False)
TestSessionLocal = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)

# Auth headers
AUTH_HEADERS = {"Authorization": "Bearer change-me-in-production"}
ADMIN_HEADERS = {**AUTH_HEADERS, "X-User-Role": "admin"}
CASHIER_HEADERS = {**AUTH_HEADERS, "X-User-Role": "cashier"}


async def override_get_db():
    async with TestSessionLocal() as session:
        yield session


@pytest_asyncio.fixture
async def app():
    """Create test app with test database."""
    application = create_app()
    application.dependency_overrides[get_db] = override_get_db

    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield application

    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def client(app):
    """Create async test client."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest_asyncio.fixture
async def created_employee(client):
    """Helper fixture: create and return an employee."""
    response = await client.post(
        "/api/v1/employees",
        json={"fio": "Ivanova A.B.", "position": "Vospitatel", "rate": 1.0},
        headers=AUTH_HEADERS,
    )
    assert response.status_code == 201
    return response.json()


@pytest_asyncio.fixture
async def created_child(client):
    """Helper fixture: create and return a child."""
    response = await client.post(
        "/api/v1/children",
        json={
            "child_fio": "Petrov M.",
            "group_name": "Solnyshko",
            "parent_fio": "Petrova N.",
            "discount_percent": 20,
        },
        headers=AUTH_HEADERS,
    )
    assert response.status_code == 201
    return response.json()
