"""E2E tests for bot-to-backend integration scenarios."""

import base64

import pytest

from tests.e2e.conftest import AUTH_HEADERS


@pytest.mark.asyncio
async def test_salary_calculation_matches_bot_format(client):
    """Backend salary calculation returns data suitable for bot formatting."""
    response = await client.post(
        "/api/v1/salary/calculate",
        json={"oklad": 30000, "rate": 1.0, "stazh_percent": 10, "category_percent": 5},
    )
    assert response.status_code == 200
    data = response.json()

    # Verify all fields that bot uses for format_money
    assert "nachisleno" in data
    assert "ndfl" in data
    assert "na_ruki" in data
    assert "pfr" in data
    assert "oms" in data
    assert "fss" in data

    # Verify correct calculation: 30000 * 1.0 * (1 + 0.10 + 0.05) = 34500
    assert abs(data["nachisleno"] - 34500.0) < 0.01
    assert abs(data["ndfl"] - 34500.0 * 0.13) < 0.01
    assert abs(data["na_ruki"] - (34500.0 - 34500.0 * 0.13)) < 0.01


@pytest.mark.asyncio
async def test_payroll_returns_valid_data_for_bot(client):
    """Payroll endpoint returns properly structured data for bot consumption."""
    response = await client.post(
        "/api/v1/salary/payroll",
        json={
            "employees": [
                {"fio": "Ivanova A.", "oklad": 30000, "rate": 1.0, "stazh_percent": 10},
                {"fio": "Petrova B.", "oklad": 25000, "rate": 1.0, "stazh_percent": 5},
            ]
        },
    )
    assert response.status_code == 200
    data = response.json()

    assert "employees" in data
    assert "totals" in data
    assert len(data["employees"]) == 2

    # Each employee result has the fields bot needs
    for emp in data["employees"]:
        assert "fio" in emp
        assert "nachisleno" in emp
        assert "na_ruki" in emp
        assert emp["nachisleno"] > 0
        assert emp["na_ruki"] > 0

    # Totals are consistent
    total_nachisleno = sum(e["nachisleno"] for e in data["employees"])
    assert abs(data["totals"]["nachisleno"] - total_nachisleno) < 0.01


@pytest.mark.asyncio
async def test_one_time_download_create_and_consume(client):
    """One-time download: create link, download once, second attempt fails."""
    # Create a download link
    content = base64.b64encode(b"test file content for bot export").decode()
    response = await client.post(
        "/api/v1/downloads/create",
        json={"content_base64": content, "filename": "report.xlsx"},
        headers=AUTH_HEADERS,
    )
    assert response.status_code == 200
    data = response.json()
    assert "token" in data
    assert "url" in data

    token = data["token"]

    # First download succeeds
    response = await client.get(f"/api/v1/downloads/{token}")
    assert response.status_code == 200
    assert response.content == b"test file content for bot export"

    # Second download fails (one-time use)
    response = await client.get(f"/api/v1/downloads/{token}")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_download_nonexistent_token_returns_404(client):
    """Attempting to download with non-existent token returns 404."""
    response = await client.get("/api/v1/downloads/nonexistent-token-12345")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_download_requires_auth_to_create(client):
    """Creating download link requires authentication."""
    content = base64.b64encode(b"secret data").decode()
    response = await client.post(
        "/api/v1/downloads/create",
        json={"content_base64": content, "filename": "secret.pdf"},
    )
    assert response.status_code == 401
