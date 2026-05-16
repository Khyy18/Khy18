"""E2E tests for audit trail functionality."""

import pytest

from tests.e2e.conftest import ADMIN_HEADERS, AUTH_HEADERS


@pytest.mark.asyncio
async def test_create_employee_creates_audit_entry(client):
    """Creating an employee generates an audit log entry."""
    # Create employee
    response = await client.post(
        "/api/v1/employees",
        json={"fio": "Audit Test", "position": "Worker", "rate": 1.0},
        headers=AUTH_HEADERS,
    )
    assert response.status_code == 201

    # Check audit log
    response = await client.get("/api/v1/audit", headers=ADMIN_HEADERS)
    assert response.status_code == 200
    entries = response.json()
    assert len(entries) >= 1

    # Find the POST employees entry
    emp_entries = [e for e in entries if e["entity_type"] == "employees" and e["action"] == "POST"]
    assert len(emp_entries) >= 1


@pytest.mark.asyncio
async def test_delete_employee_creates_audit_entry(client, created_employee):
    """Deleting an employee generates a DELETE audit log entry."""
    emp_id = created_employee["id"]

    # Delete employee
    response = await client.delete(f"/api/v1/employees/{emp_id}", headers=AUTH_HEADERS)
    assert response.status_code == 204

    # Check audit log for DELETE entry
    response = await client.get("/api/v1/audit", headers=ADMIN_HEADERS)
    assert response.status_code == 200
    entries = response.json()

    delete_entries = [e for e in entries if e["action"] == "DELETE" and e["entity_type"] == "employees"]
    assert len(delete_entries) >= 1
    assert delete_entries[0]["entity_id"] == str(emp_id)


@pytest.mark.asyncio
async def test_audit_returns_correct_entity_type(client):
    """Audit log entries have correct entity_type for different operations."""
    # Create a child
    await client.post(
        "/api/v1/children",
        json={
            "child_fio": "Audit Kid",
            "group_name": "Stars",
            "parent_fio": "Parent",
            "discount_percent": 0,
        },
        headers=AUTH_HEADERS,
    )

    # Create an employee
    await client.post(
        "/api/v1/employees",
        json={"fio": "Audit Emp", "position": "Teacher", "rate": 1.0},
        headers=AUTH_HEADERS,
    )

    # Check audit has both entity types
    response = await client.get("/api/v1/audit", headers=ADMIN_HEADERS)
    assert response.status_code == 200
    entries = response.json()

    entity_types = {e["entity_type"] for e in entries}
    assert "employees" in entity_types
    assert "children" in entity_types


@pytest.mark.asyncio
async def test_audit_filter_by_entity_type(client):
    """Audit log can be filtered by entity_type."""
    # Create employee to ensure audit entries exist
    await client.post(
        "/api/v1/employees",
        json={"fio": "Filter Test", "position": "Worker", "rate": 1.0},
        headers=AUTH_HEADERS,
    )

    # Create child
    await client.post(
        "/api/v1/children",
        json={
            "child_fio": "Filter Kid",
            "group_name": "Moon",
            "parent_fio": "Parent",
            "discount_percent": 10,
        },
        headers=AUTH_HEADERS,
    )

    # Filter by entity_type=employees
    response = await client.get(
        "/api/v1/audit?entity_type=employees", headers=ADMIN_HEADERS
    )
    assert response.status_code == 200
    entries = response.json()
    assert len(entries) >= 1
    assert all(e["entity_type"] == "employees" for e in entries)


@pytest.mark.asyncio
async def test_audit_entries_have_ip_address(client):
    """Audit log entries include IP address."""
    await client.post(
        "/api/v1/employees",
        json={"fio": "IP Test", "position": "Worker", "rate": 1.0},
        headers=AUTH_HEADERS,
    )

    response = await client.get("/api/v1/audit", headers=ADMIN_HEADERS)
    assert response.status_code == 200
    entries = response.json()
    assert len(entries) >= 1
    # IP address should be present (testclient typically uses 127.0.0.1)
    assert entries[0]["ip_address"] is not None
