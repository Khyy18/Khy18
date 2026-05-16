"""E2E tests for authentication and authorization flows."""

import pytest


@pytest.mark.asyncio
async def test_unauthenticated_post_rejected(client):
    """POST without auth header returns 401."""
    response = await client.post(
        "/api/v1/employees",
        json={"fio": "Test", "position": "Worker", "rate": 1.0},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_unauthenticated_delete_rejected(client):
    """DELETE without auth header returns 401."""
    response = await client.delete("/api/v1/employees/1")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_valid_bearer_token_accepted(client):
    """Request with valid Bearer token succeeds."""
    from tests.e2e.conftest import AUTH_HEADERS

    response = await client.post(
        "/api/v1/employees",
        json={"fio": "Test Worker", "position": "Cleaner", "rate": 0.5},
        headers=AUTH_HEADERS,
    )
    assert response.status_code == 201
    assert response.json()["fio"] == "Test Worker"


@pytest.mark.asyncio
async def test_invalid_bearer_token_rejected(client):
    """Request with invalid Bearer token returns 401."""
    response = await client.post(
        "/api/v1/employees",
        json={"fio": "Test", "position": "Worker", "rate": 1.0},
        headers={"Authorization": "Bearer wrong-token-value"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_admin_can_access_audit(client):
    """Admin role can access audit endpoint."""
    from tests.e2e.conftest import ADMIN_HEADERS

    response = await client.get("/api/v1/audit", headers=ADMIN_HEADERS)
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_cashier_cannot_access_audit(client):
    """Cashier role is forbidden from audit endpoint."""
    from tests.e2e.conftest import CASHIER_HEADERS

    response = await client.get("/api/v1/audit", headers=CASHIER_HEADERS)
    assert response.status_code == 403
