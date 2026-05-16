"""Tests for timesheet bulk-mark endpoint."""

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.app import create_app
from backend.database import Base, get_db

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"
test_engine = create_async_engine(TEST_DATABASE_URL, echo=False)
TestSessionLocal = async_sessionmaker(
    test_engine, class_=AsyncSession, expire_on_commit=False
)

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
async def test_bulk_mark_creates_marks(client):
    """Test that bulk-mark creates timesheet marks for multiple employees."""
    # Create employees first
    resp1 = await client.post(
        "/api/v1/employees",
        json={"fio": "Иванова А.Б.", "position": "Воспитатель", "rate": 1.0},
        headers=AUTH_HEADERS,
    )
    assert resp1.status_code == 201
    emp1_id = resp1.json()["id"]

    resp2 = await client.post(
        "/api/v1/employees",
        json={"fio": "Петрова В.Г.", "position": "Няня", "rate": 0.5},
        headers=AUTH_HEADERS,
    )
    assert resp2.status_code == 201
    emp2_id = resp2.json()["id"]

    # Bulk mark
    response = await client.post(
        "/api/v1/timesheet/bulk-mark",
        json={
            "date": "2025-06-10",
            "status": "present",
            "employee_ids": [emp1_id, emp2_id],
        },
        headers=AUTH_HEADERS,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["updated"] == 2

    # Verify marks were created
    summary1 = await client.get(
        f"/api/v1/timesheet/summary/{emp1_id}",
        params={"year": 2025, "month": 6},
    )
    assert summary1.status_code == 200
    assert summary1.json()["summary"].get("Я", 0) >= 1

    summary2 = await client.get(
        f"/api/v1/timesheet/summary/{emp2_id}",
        params={"year": 2025, "month": 6},
    )
    assert summary2.status_code == 200
    assert summary2.json()["summary"].get("Я", 0) >= 1


@pytest.mark.asyncio
async def test_bulk_mark_updates_existing(client):
    """Test that bulk-mark updates existing marks instead of duplicating."""
    resp = await client.post(
        "/api/v1/employees",
        json={"fio": "Сидорова Д.Е.", "position": "Повар", "rate": 1.0},
        headers=AUTH_HEADERS,
    )
    assert resp.status_code == 201
    emp_id = resp.json()["id"]

    # First mark as present
    await client.post(
        "/api/v1/timesheet/bulk-mark",
        json={
            "date": "2025-07-01",
            "status": "present",
            "employee_ids": [emp_id],
        },
        headers=AUTH_HEADERS,
    )

    # Update to sick
    response = await client.post(
        "/api/v1/timesheet/bulk-mark",
        json={
            "date": "2025-07-01",
            "status": "sick",
            "employee_ids": [emp_id],
        },
        headers=AUTH_HEADERS,
    )
    assert response.status_code == 200

    # Summary should show sick, not present
    summary = await client.get(
        f"/api/v1/timesheet/summary/{emp_id}",
        params={"year": 2025, "month": 7},
    )
    assert summary.status_code == 200
    s = summary.json()["summary"]
    assert s.get("Б", 0) == 1
    assert s.get("Я", 0) == 0


@pytest.mark.asyncio
async def test_bulk_mark_requires_auth(client):
    """Test that bulk-mark requires authentication."""
    response = await client.post(
        "/api/v1/timesheet/bulk-mark",
        json={
            "date": "2025-06-10",
            "status": "present",
            "employee_ids": [1, 2],
        },
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_bulk_mark_vacation_status(client):
    """Test that vacation status maps to correct mark code."""
    resp = await client.post(
        "/api/v1/employees",
        json={"fio": "Козлова Ж.З.", "position": "Логопед", "rate": 1.0},
        headers=AUTH_HEADERS,
    )
    assert resp.status_code == 201
    emp_id = resp.json()["id"]

    response = await client.post(
        "/api/v1/timesheet/bulk-mark",
        json={
            "date": "2025-08-15",
            "status": "vacation",
            "employee_ids": [emp_id],
        },
        headers=AUTH_HEADERS,
    )
    assert response.status_code == 200

    summary = await client.get(
        f"/api/v1/timesheet/summary/{emp_id}",
        params={"year": 2025, "month": 8},
    )
    assert summary.status_code == 200
    assert summary.json()["summary"].get("О", 0) == 1
