"""E2E tests for full business flows across multiple endpoints."""

import pytest

from tests.e2e.conftest import AUTH_HEADERS


@pytest.mark.asyncio
async def test_employee_timesheet_salary_flow(client, created_employee):
    """Full flow: create employee -> mark timesheet -> calculate salary."""
    emp_id = created_employee["id"]

    # Mark timesheet for March 2024
    for day in range(1, 21):
        await client.post(
            "/api/v1/timesheet/mark",
            json={
                "employee_id": emp_id,
                "date": f"2024-03-{day:02d}",
                "mark_type": "present",
            },
            headers=AUTH_HEADERS,
        )

    # Check timesheet summary
    response = await client.get(f"/api/v1/timesheet/summary/{emp_id}?year=2024&month=3")
    assert response.status_code == 200
    assert response.json()["summary"]["present"] == 20

    # Calculate salary
    response = await client.post(
        "/api/v1/salary/calculate",
        json={"oklad": 30000, "rate": 1.0, "stazh_percent": 10, "category_percent": 5},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["nachisleno"] > 0
    assert data["na_ruki"] > 0
    assert data["na_ruki"] < data["nachisleno"]


@pytest.mark.asyncio
async def test_export_excel_flow(client):
    """Full flow: calculate payroll and export Excel."""
    response = await client.post(
        "/api/v1/salary/export-excel",
        json={
            "employees": [
                {"fio": "Ivanova A.", "oklad": 30000, "rate": 1.0, "stazh_percent": 10},
                {"fio": "Petrova B.", "oklad": 25000, "rate": 0.75, "stazh_percent": 5},
            ]
        },
    )
    assert response.status_code == 200
    assert "spreadsheetml" in response.headers["content-type"]
    # Verify it's a valid xlsx (starts with PK zip signature)
    assert response.content[:2] == b"PK"


@pytest.mark.asyncio
async def test_child_payment_flow(client, created_child):
    """Full flow: create child -> generate payment -> verify amount."""
    child_id = created_child["id"]
    discount = created_child["discount_percent"]  # 20%

    response = await client.post(
        "/api/v1/payments/generate",
        json={"child_id": child_id, "month": 3, "year": 2024, "attendance_days": 20},
        headers=AUTH_HEADERS,
    )
    assert response.status_code == 200
    data = response.json()

    # 20 days * 150 per day = 3000, with 20% discount = 2400
    assert data["amount_due"] == 3000
    assert data["discount_percent"] == discount
    assert data["amount_after_discount"] == 2400


@pytest.mark.asyncio
async def test_payroll_multiple_employees(client):
    """Full flow: payroll calculation for multiple employees."""
    response = await client.post(
        "/api/v1/salary/payroll",
        json={
            "employees": [
                {"fio": "Ivanova A.", "oklad": 30000, "rate": 1.0, "stazh_percent": 10},
                {"fio": "Petrova B.", "oklad": 25000, "rate": 1.0, "stazh_percent": 5},
                {"fio": "Sidorova C.", "oklad": 28000, "rate": 0.5, "stazh_percent": 0},
            ]
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data["employees"]) == 3
    assert data["totals"]["nachisleno"] > 0
    assert data["totals"]["na_ruki"] > 0
    assert data["totals"]["na_ruki"] < data["totals"]["nachisleno"]
