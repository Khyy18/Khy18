"""Tests for one-time download links."""

import base64
import time

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

AUTH_HEADERS = {"Authorization": "Bearer change-me-in-production"}


async def override_get_db():
    async with TestSessionLocal() as session:
        yield session


@pytest_asyncio.fixture
async def app():
    application = create_app()
    application.dependency_overrides[get_db] = override_get_db
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield application
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.mark.asyncio
async def test_create_download_link(client):
    """POST /api/v1/downloads/create should return token and url."""
    content = base64.b64encode(b"Hello, World!").decode()
    response = await client.post(
        "/api/v1/downloads/create",
        json={"content_base64": content, "filename": "test.txt"},
        headers=AUTH_HEADERS,
    )
    assert response.status_code == 200
    data = response.json()
    assert "token" in data
    assert "url" in data
    assert "expires_at" in data
    assert data["url"].startswith("/api/v1/downloads/")


@pytest.mark.asyncio
async def test_download_once_works(client):
    """First download should succeed and return file content."""
    content = base64.b64encode(b"Secret content").decode()
    create_resp = await client.post(
        "/api/v1/downloads/create",
        json={"content_base64": content, "filename": "secret.txt"},
        headers=AUTH_HEADERS,
    )
    token = create_resp.json()["token"]

    # First download
    response = await client.get(f"/api/v1/downloads/{token}")
    assert response.status_code == 200
    assert response.content == b"Secret content"


@pytest.mark.asyncio
async def test_second_download_returns_404(client):
    """Second download of the same token should return 404."""
    content = base64.b64encode(b"One-time data").decode()
    create_resp = await client.post(
        "/api/v1/downloads/create",
        json={"content_base64": content, "filename": "once.txt"},
        headers=AUTH_HEADERS,
    )
    token = create_resp.json()["token"]

    # First download (consumes token)
    await client.get(f"/api/v1/downloads/{token}")

    # Second download should fail
    response = await client.get(f"/api/v1/downloads/{token}")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_expired_token_returns_404(client):
    """Expired token should return 404."""
    content = base64.b64encode(b"Expiring data").decode()
    create_resp = await client.post(
        "/api/v1/downloads/create",
        json={"content_base64": content, "filename": "expire.txt"},
        headers=AUTH_HEADERS,
    )
    token = create_resp.json()["token"]

    # Manually expire the token
    from backend.routers.downloads import _download_store
    _download_store[token]["expires_at"] = time.time() - 1

    # Download should fail
    response = await client.get(f"/api/v1/downloads/{token}")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_invalid_token_returns_404(client):
    """Non-existent token should return 404."""
    response = await client.get("/api/v1/downloads/non-existent-token")
    assert response.status_code == 404
