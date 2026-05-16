"""Tests for audit log middleware and endpoint."""

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
async def test_audit_log_created_on_post(client):
    """POST operation should create an audit log entry."""
    # Create an employee (triggers audit)
    response = await client.post(
        "/api/v1/employees",
        json={"fio": "Test Worker", "position": "Cleaner", "rate": 1.0},
        headers=AUTH_HEADERS,
    )
    assert response.status_code == 201

    # Check audit log
    headers = {**AUTH_HEADERS, "X-User-Role": "admin"}
    response = await client.get("/api/v1/audit", headers=headers)
    assert response.status_code == 200
    logs = response.json()
    assert len(logs) >= 1
    # The most recent entry should be the POST
    post_logs = [entry for entry in logs if entry["action"] == "POST"]
    assert len(post_logs) >= 1


@pytest.mark.asyncio
async def test_audit_endpoint_returns_entries(client):
    """GET /api/v1/audit returns audit entries."""
    headers = {**AUTH_HEADERS, "X-User-Role": "admin"}
    response = await client.get("/api/v1/audit", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)


@pytest.mark.asyncio
async def test_audit_filter_by_entity_type(client):
    """GET /api/v1/audit with entity_type filter."""
    # Create employee to generate audit
    await client.post(
        "/api/v1/employees",
        json={"fio": "Filter Test", "position": "Worker", "rate": 1.0},
        headers=AUTH_HEADERS,
    )

    headers = {**AUTH_HEADERS, "X-User-Role": "admin"}
    response = await client.get("/api/v1/audit?entity_type=employees", headers=headers)
    assert response.status_code == 200
    logs = response.json()
    for log in logs:
        assert log["entity_type"] == "employees"
