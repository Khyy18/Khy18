"""Tests for payroll calculation and Excel export endpoints."""

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
async def test_payroll_two_employees(client):
    """Test payroll calculation with 2 employees."""
    payload = {
        "employees": [
            {"fio": "Ivanova A.B.", "oklad": 30000, "rate": 1.0, "stazh_percent": 10, "category_percent": 5},
            {"fio": "Petrov C.D.", "oklad": 25000, "rate": 0.5, "stazh_percent": 0, "category_percent": 0},
        ]
    }
    response = await client.post("/api/v1/salary/payroll", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert len(data["employees"]) == 2

    # First employee: 30000 * 1.0 * (1 + 0.10 + 0.05) = 34500
    emp1 = data["employees"][0]
    assert emp1["fio"] == "Ivanova A.B."
    assert abs(emp1["nachisleno"] - 34500.0) < 0.01
    assert abs(emp1["ndfl"] - 34500.0 * 0.13) < 0.01
    assert abs(emp1["na_ruki"] - (34500.0 - 34500.0 * 0.13)) < 0.01

    # Second employee: 25000 * 0.5 * 1.0 = 12500
    emp2 = data["employees"][1]
    assert emp2["fio"] == "Petrov C.D."
    assert abs(emp2["nachisleno"] - 12500.0) < 0.01

    # Check totals
    totals = data["totals"]
    assert abs(totals["nachisleno"] - (34500.0 + 12500.0)) < 0.01


@pytest.mark.asyncio
async def test_payroll_validation_error(client):
    """Test that invalid input is rejected."""
    payload = {
        "employees": [
            {"fio": "", "oklad": -100, "rate": 1.0},
        ]
    }
    response = await client.post("/api/v1/salary/payroll", json=payload)
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_export_excel(client):
    """Test Excel export returns valid xlsx content-type."""
    payload = {
        "employees": [
            {"fio": "Ivanova A.B.", "oklad": 30000, "rate": 1.0, "stazh_percent": 10, "category_percent": 5},
            {"fio": "Petrov C.D.", "oklad": 25000, "rate": 0.5, "stazh_percent": 0, "category_percent": 0},
        ]
    }
    response = await client.post("/api/v1/salary/export-excel", json=payload)
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    assert "payroll.xlsx" in response.headers["content-disposition"]
    # Verify it's a valid xlsx (starts with PK zip signature)
    assert response.content[:2] == b"PK"
