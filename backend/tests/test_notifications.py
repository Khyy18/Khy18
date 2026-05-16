"""Tests for notification endpoints."""

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.app import create_app
from backend.database import Base, get_db
from backend.routers.notifications import _registered_tokens

# Test database - in-memory SQLite
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"
test_engine = create_async_engine(TEST_DATABASE_URL, echo=False)
TestSessionLocal = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)

# Auth header for protected endpoints
AUTH_HEADERS = {"Authorization": "Bearer change-me-in-production"}


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


@pytest_asyncio.fixture(autouse=True)
async def clear_tokens():
    """Clear tokens before each test."""
    _registered_tokens.clear()
    yield
    _registered_tokens.clear()


@pytest.mark.asyncio
async def test_register_token(client):
    """Test registering an FCM token."""
    response = await client.post(
        "/api/v1/notifications/register",
        json={"fcm_token": "test-token-123", "chat_id": 42, "device_info": "Android"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "registered"
    assert "token_count" not in data


@pytest.mark.asyncio
async def test_register_multiple_tokens(client):
    """Test registering multiple FCM tokens."""
    await client.post(
        "/api/v1/notifications/register",
        json={"fcm_token": "token-1", "chat_id": 1},
    )
    response = await client.post(
        "/api/v1/notifications/register",
        json={"fcm_token": "token-2", "chat_id": 2},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "registered"
    assert "token_count" not in response.json()


@pytest.mark.asyncio
async def test_register_token_empty_fails(client):
    """Test that empty token is rejected."""
    response = await client.post(
        "/api/v1/notifications/register",
        json={"fcm_token": "", "chat_id": 0},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_send_notification_requires_auth(client):
    """Test that send endpoint requires auth."""
    response = await client.post(
        "/api/v1/notifications/send",
        json={"title": "Test", "body": "Hello"},
    )
    assert response.status_code in (401, 403)


@pytest.mark.asyncio
async def test_send_notification_with_auth(client):
    """Test sending notification with valid auth."""
    # Register a token first
    await client.post(
        "/api/v1/notifications/register",
        json={"fcm_token": "token-1", "chat_id": 1},
    )

    response = await client.post(
        "/api/v1/notifications/send",
        json={"title": "Test Title", "body": "Test Body"},
        headers=AUTH_HEADERS,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "sent"
    assert data["sent_to"] == 1


@pytest.mark.asyncio
async def test_send_notification_with_target_filter(client):
    """Test sending to specific chat_ids."""
    await client.post(
        "/api/v1/notifications/register",
        json={"fcm_token": "token-1", "chat_id": 1},
    )
    await client.post(
        "/api/v1/notifications/register",
        json={"fcm_token": "token-2", "chat_id": 2},
    )

    response = await client.post(
        "/api/v1/notifications/send",
        json={"title": "Test", "body": "Hello", "target_chat_ids": [1]},
        headers=AUTH_HEADERS,
    )
    assert response.status_code == 200
    assert response.json()["sent_to"] == 1


@pytest.mark.asyncio
async def test_get_tokens_count_requires_auth(client):
    """Test tokens count endpoint requires auth."""
    response = await client.get("/api/v1/notifications/tokens")
    assert response.status_code in (401, 403)


@pytest.mark.asyncio
async def test_get_tokens_count(client):
    """Test getting registered tokens count."""
    await client.post(
        "/api/v1/notifications/register",
        json={"fcm_token": "token-1", "chat_id": 1},
    )

    response = await client.get(
        "/api/v1/notifications/tokens",
        headers=AUTH_HEADERS,
    )
    assert response.status_code == 200
    assert response.json()["token_count"] == 1
