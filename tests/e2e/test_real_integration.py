"""Real integration tests with actual DB - comprehensive E2E scenarios."""

import pytest

from tests.e2e.conftest import AUTH_HEADERS, ADMIN_HEADERS, CASHIER_HEADERS


@pytest.mark.asyncio
async def test_full_employee_lifecycle(client):
    """Full lifecycle: create employee -> verify exists -> delete -> verify gone."""
    # Create
    response = await client.post(
        "/api/v1/employees",
        json={"fio": "Lifecycle Test", "position": "Teacher", "rate": 1.0},
        headers=AUTH_HEADERS,
    )
    assert response.status_code == 201
    emp = response.json()
    emp_id = emp["id"]
    assert emp["fio"] == "Lifecycle Test"
    assert emp["position"] == "Teacher"
    assert emp["rate"] == 1.0

    # Verify listed
    response = await client.get("/api/v1/employees")
    assert response.status_code == 200
    employees = response.json()
    assert any(e["id"] == emp_id for e in employees)

    # Delete
    response = await client.delete(f"/api/v1/employees/{emp_id}", headers=AUTH_HEADERS)
    assert response.status_code == 204

    # Verify gone
    response = await client.get("/api/v1/employees")
    assert response.status_code == 200
    employees = response.json()
    assert not any(e["id"] == emp_id for e in employees)


@pytest.mark.asyncio
async def test_timesheet_mark_and_summary(client, created_employee):
    """Mark 20 days present, verify summary counts are correct."""
    emp_id = created_employee["id"]

    for day in range(1, 21):
        response = await client.post(
            "/api/v1/timesheet/mark",
            json={
                "employee_id": emp_id,
                "date": f"2024-03-{day:02d}",
                "mark_type": "present",
            },
            headers=AUTH_HEADERS,
        )
        assert response.status_code == 201

    # Verify summary
    response = await client.get(f"/api/v1/timesheet/summary/{emp_id}?year=2024&month=3")
    assert response.status_code == 200
    data = response.json()
    assert data["summary"]["present"] == 20


@pytest.mark.asyncio
async def test_salary_calculation_correct(client):
    """Verify salary math: NDFL, PFR, OMS, FSS deductions are correct."""
    response = await client.post(
        "/api/v1/salary/calculate",
        json={"oklad": 40000, "rate": 1.0, "stazh_percent": 15, "category_percent": 10},
    )
    assert response.status_code == 200
    data = response.json()

    # Expected: 40000 * 1.0 * (1 + 0.15 + 0.10) = 50000
    expected_nachisleno = 50000.0
    assert abs(data["nachisleno"] - expected_nachisleno) < 0.01

    # NDFL = 13% of nachisleno
    expected_ndfl = expected_nachisleno * 0.13
    assert abs(data["ndfl"] - expected_ndfl) < 0.01

    # na_ruki = nachisleno - ndfl
    expected_na_ruki = expected_nachisleno - expected_ndfl
    assert abs(data["na_ruki"] - expected_na_ruki) < 0.01

    # PFR = 22% of nachisleno
    expected_pfr = expected_nachisleno * 0.22
    assert abs(data["pfr"] - expected_pfr) < 0.01

    # OMS = 5.1% of nachisleno
    expected_oms = expected_nachisleno * 0.051
    assert abs(data["oms"] - expected_oms) < 0.01

    # FSS = 2.9% of nachisleno
    expected_fss = expected_nachisleno * 0.029
    assert abs(data["fss"] - expected_fss) < 0.01


@pytest.mark.asyncio
async def test_salary_export_excel_valid(client):
    """Export Excel and verify it is a valid xlsx file (PK zip signature)."""
    response = await client.post(
        "/api/v1/salary/export-excel",
        json={
            "employees": [
                {"fio": "Excel Test A.", "oklad": 35000, "rate": 1.0, "stazh_percent": 5},
            ]
        },
    )
    assert response.status_code == 200
    assert "spreadsheetml" in response.headers["content-type"]
    # Valid xlsx starts with PK zip signature
    assert response.content[:2] == b"PK"
    # File should be non-trivial size
    assert len(response.content) > 1000


@pytest.mark.asyncio
async def test_child_payment_with_discount(client, created_child):
    """Create child with discount, generate payment, verify discount applied."""
    child_id = created_child["id"]
    discount = created_child["discount_percent"]  # 20%

    response = await client.post(
        "/api/v1/payments/generate",
        json={"child_id": child_id, "month": 5, "year": 2024, "attendance_days": 15},
        headers=AUTH_HEADERS,
    )
    assert response.status_code == 200
    data = response.json()

    # 15 days * 150 per day = 2250, with 20% discount = 1800
    assert data["amount_due"] == 2250
    assert data["discount_percent"] == discount
    assert data["amount_after_discount"] == 1800


@pytest.mark.asyncio
async def test_payroll_multiple_employees(client):
    """Bulk payroll for 3 employees, verify totals are consistent."""
    response = await client.post(
        "/api/v1/salary/payroll",
        json={
            "employees": [
                {"fio": "Worker A", "oklad": 30000, "rate": 1.0, "stazh_percent": 10},
                {"fio": "Worker B", "oklad": 25000, "rate": 1.0, "stazh_percent": 5},
                {"fio": "Worker C", "oklad": 28000, "rate": 0.5, "stazh_percent": 0},
            ]
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data["employees"]) == 3
    assert data["totals"]["nachisleno"] > 0
    assert data["totals"]["na_ruki"] > 0
    assert data["totals"]["na_ruki"] < data["totals"]["nachisleno"]

    # Totals match sum of individuals
    total_nachisleno = sum(e["nachisleno"] for e in data["employees"])
    total_na_ruki = sum(e["na_ruki"] for e in data["employees"])
    assert abs(data["totals"]["nachisleno"] - total_nachisleno) < 0.01
    assert abs(data["totals"]["na_ruki"] - total_na_ruki) < 0.01


@pytest.mark.asyncio
async def test_journal_entry_crud(client):
    """Create journal entry, list entries, verify data returned."""
    # Create income entry
    response = await client.post(
        "/api/v1/journal",
        json={
            "date": "2024-03-15",
            "amount": 50000.0,
            "entry_type": "income",
            "counterparty": "Budget Fund",
            "basis": "Grant #123",
        },
        headers=AUTH_HEADERS,
    )
    assert response.status_code == 201
    entry = response.json()
    assert entry["amount"] == 50000.0
    assert entry["entry_type"] == "income"
    assert entry["counterparty"] == "Budget Fund"

    # Create expense entry
    response = await client.post(
        "/api/v1/journal",
        json={
            "date": "2024-03-16",
            "amount": 15000.0,
            "entry_type": "expense",
            "counterparty": "Supplier LLC",
            "basis": "Invoice #456",
        },
        headers=AUTH_HEADERS,
    )
    assert response.status_code == 201

    # List entries
    response = await client.get("/api/v1/journal")
    assert response.status_code == 200
    entries = response.json()
    assert len(entries) >= 2

    # Verify totals
    response = await client.get("/api/v1/journal/totals")
    assert response.status_code == 200
    totals = response.json()
    assert totals["income"] >= 50000.0
    assert totals["expense"] >= 15000.0
    assert totals["balance"] == totals["income"] - totals["expense"]


@pytest.mark.asyncio
async def test_reminder_list(client):
    """List reminders endpoint returns data."""
    response = await client.get("/api/v1/reminders")
    assert response.status_code == 200
    # Response is a list (may be empty in clean DB)
    assert isinstance(response.json(), list)


@pytest.mark.asyncio
async def test_upcoming_deadlines(client):
    """Upcoming deadlines endpoint returns structured data."""
    response = await client.get("/api/v1/reminders/upcoming")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    # Each deadline has expected fields
    for item in data:
        assert "name" in item
        assert "description" in item
        assert "date" in item
        assert "days_left" in item
        assert item["days_left"] >= 0


@pytest.mark.asyncio
async def test_unauthenticated_all_mutations(client):
    """POST/DELETE to employees, children, timesheet without auth returns 401."""
    # POST employees
    response = await client.post(
        "/api/v1/employees",
        json={"fio": "Hacker", "position": "Spy", "rate": 1.0},
    )
    assert response.status_code == 401

    # DELETE employees
    response = await client.delete("/api/v1/employees/999")
    assert response.status_code == 401

    # POST children
    response = await client.post(
        "/api/v1/children",
        json={
            "child_fio": "Hacker Kid",
            "group_name": "Bad",
            "parent_fio": "Hacker",
            "discount_percent": 0,
        },
    )
    assert response.status_code == 401

    # POST timesheet mark
    response = await client.post(
        "/api/v1/timesheet/mark",
        json={"employee_id": 1, "date": "2024-01-01", "mark_type": "present"},
    )
    assert response.status_code == 401

    # POST journal
    response = await client.post(
        "/api/v1/journal",
        json={
            "date": "2024-01-01",
            "amount": 100,
            "entry_type": "income",
            "counterparty": "X",
            "basis": "Y",
        },
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_cashier_cannot_access_audit(client):
    """Cashier role gets 403 on GET /api/v1/audit."""
    response = await client.get("/api/v1/audit", headers=CASHIER_HEADERS)
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_admin_can_access_audit(client):
    """Admin role gets 200 on GET /api/v1/audit."""
    response = await client.get("/api/v1/audit", headers=ADMIN_HEADERS)
    assert response.status_code == 200
    assert isinstance(response.json(), list)


@pytest.mark.asyncio
async def test_director_can_access_audit(client):
    """Director role gets 200 on GET /api/v1/audit."""
    director_headers = {**AUTH_HEADERS, "X-User-Role": "director"}
    response = await client.get("/api/v1/audit", headers=director_headers)
    assert response.status_code == 200
    assert isinstance(response.json(), list)


@pytest.mark.asyncio
async def test_audit_log_created_on_mutation(client):
    """Creating an employee produces an audit log entry."""
    # Create employee
    response = await client.post(
        "/api/v1/employees",
        json={"fio": "Audit Check", "position": "Guard", "rate": 1.0},
        headers=AUTH_HEADERS,
    )
    assert response.status_code == 201

    # Check audit log has the entry
    response = await client.get("/api/v1/audit", headers=ADMIN_HEADERS)
    assert response.status_code == 200
    entries = response.json()
    assert len(entries) >= 1
    emp_entries = [
        e for e in entries if e["entity_type"] == "employees" and e["action"] == "POST"
    ]
    assert len(emp_entries) >= 1


@pytest.mark.asyncio
async def test_health_endpoint(client):
    """GET /health returns 200 with status ok."""
    response = await client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "uptime" in data


@pytest.mark.asyncio
async def test_kbk_search(client):
    """GET /api/v1/kbk/search returns matching KBK codes."""
    response = await client.get("/api/v1/kbk/search?q=НДФЛ")
    assert response.status_code == 200
    data = response.json()
    assert data["count"] >= 1
    assert len(data["results"]) >= 1
    # Each result has expected structure
    for item in data["results"]:
        assert "code" in item
        assert "short_name" in item
        assert "description" in item


@pytest.mark.asyncio
async def test_kbk_popular(client):
    """GET /api/v1/kbk/popular returns popular KBK codes."""
    response = await client.get("/api/v1/kbk/popular")
    assert response.status_code == 200
    data = response.json()
    assert data["count"] > 0
    assert len(data["results"]) > 0


@pytest.mark.asyncio
async def test_calendar_endpoint(client):
    """GET /api/v1/calendar/2024/3 returns production calendar data."""
    response = await client.get("/api/v1/calendar/2024/3")
    assert response.status_code == 200
    data = response.json()
    assert data["year"] == 2024
    assert data["month"] == 3
    assert data["working_days"] == 20
    assert data["total_days"] == 31
    assert "holidays" in data
    assert "weekend_days" in data
