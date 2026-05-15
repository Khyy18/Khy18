"""Tests for the FastAPI backend."""

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


# --- Health check ---


@pytest.mark.asyncio
async def test_health(client):
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


# --- Salary calculator ---


@pytest.mark.asyncio
async def test_salary_calculate(client):
    response = await client.post(
        "/api/v1/salary/calculate",
        json={"oklad": 30000, "rate": 1.0, "stazh_percent": 10, "category_percent": 5},
    )
    assert response.status_code == 200
    data = response.json()
    # nachisleno = 30000 * 1.0 * (1 + 10/100 + 5/100) = 34500
    assert abs(data["nachisleno"] - 34500.0) < 0.01
    assert abs(data["ndfl"] - 34500.0 * 0.13) < 0.01
    assert abs(data["na_ruki"] - (34500.0 - 34500.0 * 0.13)) < 0.01


@pytest.mark.asyncio
async def test_salary_calculate_basic(client):
    response = await client.post(
        "/api/v1/salary/calculate",
        json={"oklad": 20000, "rate": 0.5, "stazh_percent": 0},
    )
    assert response.status_code == 200
    data = response.json()
    # 20000 * 0.5 * (1 + 0 + 0) = 10000
    assert abs(data["nachisleno"] - 10000.0) < 0.01


# --- Vacation calculator ---


@pytest.mark.asyncio
async def test_vacation_calculate(client):
    response = await client.post(
        "/api/v1/vacation/calculate",
        json={"total_12_months": 360000, "days": 28},
    )
    assert response.status_code == 200
    data = response.json()
    # avg_daily = 360000 / 12 / 29.3 = 1023.89...
    avg_daily = 360000 / 12 / 29.3
    expected_gross = avg_daily * 28
    assert abs(data["avg_daily"] - avg_daily) < 0.01
    assert abs(data["vacation_gross"] - expected_gross) < 0.01
    assert abs(data["vacation_net"] - expected_gross * 0.87) < 0.01


# --- Sick leave calculator ---


@pytest.mark.asyncio
async def test_sick_calculate(client):
    response = await client.post(
        "/api/v1/sick/calculate",
        json={"earnings_2y": 730000, "stazh_bracket": ">8", "days": 10},
    )
    assert response.status_code == 200
    data = response.json()
    # daily = (730000 / 730) * 1.0 = 1000
    assert abs(data["daily"] - 1000.0) < 0.01
    assert abs(data["total_gross"] - 10000.0) < 0.01
    assert data["percent"] == 1.0


@pytest.mark.asyncio
async def test_sick_calculate_low_stazh(client):
    response = await client.post(
        "/api/v1/sick/calculate",
        json={"earnings_2y": 730000, "stazh_bracket": "<5", "days": 5},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["percent"] == 0.6
    # daily = (730000 / 730) * 0.6 = 600
    assert abs(data["daily"] - 600.0) < 0.01


# --- Employees CRUD ---


@pytest.mark.asyncio
async def test_employees_crud(client):
    # Create
    response = await client.post(
        "/api/v1/employees",
        json={"fio": "Ivanova A.B.", "position": "Vospitatel", "rate": 1.0},
    )
    assert response.status_code == 201
    emp = response.json()
    assert emp["fio"] == "Ivanova A.B."
    emp_id = emp["id"]

    # List
    response = await client.get("/api/v1/employees")
    assert response.status_code == 200
    assert len(response.json()) == 1

    # Delete
    response = await client.delete(f"/api/v1/employees/{emp_id}")
    assert response.status_code == 204

    # Verify deleted
    response = await client.get("/api/v1/employees")
    assert response.status_code == 200
    assert len(response.json()) == 0


# --- Children CRUD ---


@pytest.mark.asyncio
async def test_children_crud(client):
    response = await client.post(
        "/api/v1/children",
        json={
            "child_fio": "Petrov M.",
            "group_name": "Solnyshko",
            "parent_fio": "Petrova N.",
            "discount_percent": 20,
        },
    )
    assert response.status_code == 201
    child = response.json()
    assert child["discount_percent"] == 20
    child_id = child["id"]

    response = await client.get("/api/v1/children")
    assert response.status_code == 200
    assert len(response.json()) == 1

    response = await client.delete(f"/api/v1/children/{child_id}")
    assert response.status_code == 204


# --- Journal ---


@pytest.mark.asyncio
async def test_journal_operations(client):
    # Add entries
    await client.post(
        "/api/v1/journal",
        json={"date": "2024-01-15", "amount": 100000, "entry_type": "income", "counterparty": "Budget"},
    )
    await client.post(
        "/api/v1/journal",
        json={"date": "2024-01-20", "amount": 30000, "entry_type": "expense", "counterparty": "Supplier"},
    )

    # List
    response = await client.get("/api/v1/journal")
    assert response.status_code == 200
    assert len(response.json()) == 2

    # Totals
    response = await client.get("/api/v1/journal/totals")
    assert response.status_code == 200
    totals = response.json()
    assert totals["income"] == 100000
    assert totals["expense"] == 30000
    assert totals["balance"] == 70000


# --- Timesheet ---


@pytest.mark.asyncio
async def test_timesheet(client):
    # Create employee first
    resp = await client.post(
        "/api/v1/employees",
        json={"fio": "Test", "position": "Worker", "rate": 1.0},
    )
    emp_id = resp.json()["id"]

    # Add marks
    await client.post(
        "/api/v1/timesheet/mark",
        json={"employee_id": emp_id, "date": "2024-03-01", "mark_type": "present"},
    )
    await client.post(
        "/api/v1/timesheet/mark",
        json={"employee_id": emp_id, "date": "2024-03-02", "mark_type": "present"},
    )
    await client.post(
        "/api/v1/timesheet/mark",
        json={"employee_id": emp_id, "date": "2024-03-03", "mark_type": "sick"},
    )

    # Summary
    response = await client.get(f"/api/v1/timesheet/summary/{emp_id}?year=2024&month=3")
    assert response.status_code == 200
    data = response.json()
    assert data["summary"]["present"] == 2
    assert data["summary"]["sick"] == 1


# --- KBK ---


@pytest.mark.asyncio
async def test_kbk_search(client):
    response = await client.get("/api/v1/kbk/search?q=\u041d\u0414\u0424\u041b")
    assert response.status_code == 200
    data = response.json()
    assert data["count"] >= 1


@pytest.mark.asyncio
async def test_kbk_popular(client):
    response = await client.get("/api/v1/kbk/popular")
    assert response.status_code == 200
    data = response.json()
    assert data["count"] == 10


# --- Reminders ---


@pytest.mark.asyncio
async def test_reminders_upcoming(client):
    response = await client.get("/api/v1/reminders/upcoming")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)


# --- Payments ---


@pytest.mark.asyncio
async def test_payment_generate(client):
    # Create a child first
    resp = await client.post(
        "/api/v1/children",
        json={
            "child_fio": "Kid A.",
            "group_name": "Stars",
            "parent_fio": "Parent A.",
            "discount_percent": 50,
        },
    )
    child_id = resp.json()["id"]

    response = await client.post(
        "/api/v1/payments/generate",
        json={"child_id": child_id, "month": 3, "year": 2024, "attendance_days": 20},
    )
    assert response.status_code == 200
    data = response.json()
    # 20 * 150 = 3000, with 50% discount = 1500
    assert data["amount_due"] == 3000
    assert data["amount_after_discount"] == 1500


# --- Auth module ---


@pytest.mark.asyncio
async def test_auth_verify_telegram_init_data():
    """Test that the HMAC validation logic works correctly."""
    import hashlib
    import hmac
    from urllib.parse import urlencode

    from backend.auth import verify_telegram_init_data

    bot_token = "123456:ABC-DEF"
    # Build valid initData
    data_params = {
        "user": '{"id":12345,"first_name":"Test"}',
        "auth_date": "1678000000",
        "query_id": "abc123",
    }

    # Compute correct hash
    data_check_string = "\n".join(
        f"{k}={data_params[k]}" for k in sorted(data_params.keys())
    )
    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    correct_hash = hmac.new(
        secret_key, data_check_string.encode(), hashlib.sha256
    ).hexdigest()

    data_params["hash"] = correct_hash
    init_data = urlencode(data_params)

    result = verify_telegram_init_data(init_data, bot_token)
    assert result["auth_date"] == "1678000000"
    assert "user" in result


@pytest.mark.asyncio
async def test_auth_verify_telegram_invalid():
    """Test that invalid hash is rejected."""
    from urllib.parse import urlencode

    from backend.auth import verify_telegram_init_data

    data_params = {
        "user": '{"id":12345}',
        "auth_date": "1678000000",
        "hash": "invalid_hash_value",
    }
    init_data = urlencode(data_params)

    with pytest.raises(ValueError, match="Invalid initData hash"):
        verify_telegram_init_data(init_data, "123456:ABC-DEF")
