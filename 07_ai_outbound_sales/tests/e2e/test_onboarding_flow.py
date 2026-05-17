"""E2E tests for the onboarding step-based flow."""

from unittest.mock import patch

import pytest


async def test_onboarding_step1_company_info(client, auth_headers, e2e_session_factory):
    """Test step 1: store company name and domain."""
    with patch("dashboard.auth.settings") as mock_settings:
        mock_settings.jwt_secret_key = "test-secret-key"
        mock_settings.jwt_algorithm = "HS256"

        response = await client.post(
            "/api/onboarding/step1",
            json={
                "company_name": "E2E Test Corp",
                "domain": "e2etestcorp.com",
            },
            headers=auth_headers,
        )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["next_step"] == "smtp_connected"


async def test_onboarding_step2_smtp_config(client, auth_headers):
    """Test step 2: validate SMTP config (mocked connection)."""
    # First complete step 1
    with patch("dashboard.auth.settings") as mock_settings:
        mock_settings.jwt_secret_key = "test-secret-key"
        mock_settings.jwt_algorithm = "HS256"

        await client.post(
            "/api/onboarding/step1",
            json={"company_name": "Step2 Corp", "domain": "step2.com"},
            headers=auth_headers,
        )

    # Step 2 - mock the SMTP connection
    with (
        patch("dashboard.auth.settings") as mock_settings,
        patch("dashboard.routes.onboarding.aiosmtplib.SMTP") as mock_smtp_class,
    ):
        mock_settings.jwt_secret_key = "test-secret-key"
        mock_settings.jwt_algorithm = "HS256"

        mock_smtp = mock_smtp_class.return_value
        mock_smtp.connect = pytest.importorskip("unittest.mock").AsyncMock()
        mock_smtp.login = pytest.importorskip("unittest.mock").AsyncMock()
        mock_smtp.quit = pytest.importorskip("unittest.mock").AsyncMock()

        response = await client.post(
            "/api/onboarding/step2",
            json={
                "smtp_host": "smtp.example.com",
                "smtp_port": 587,
                "smtp_user": "user@example.com",
                "smtp_password": "smtp_pass",
            },
            headers=auth_headers,
        )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["next_step"] == "icp_uploaded"


async def test_onboarding_step3_icp_data(client, auth_headers):
    """Test step 3: store ICP data."""
    # Complete step 1 and 2 first
    with patch("dashboard.auth.settings") as mock_settings:
        mock_settings.jwt_secret_key = "test-secret-key"
        mock_settings.jwt_algorithm = "HS256"

        await client.post(
            "/api/onboarding/step1",
            json={"company_name": "Step3 Corp", "domain": "step3.com"},
            headers=auth_headers,
        )

    with (
        patch("dashboard.auth.settings") as mock_settings,
        patch("dashboard.routes.onboarding.aiosmtplib.SMTP") as mock_smtp_class,
    ):
        mock_settings.jwt_secret_key = "test-secret-key"
        mock_settings.jwt_algorithm = "HS256"

        mock_smtp = mock_smtp_class.return_value
        mock_smtp.connect = pytest.importorskip("unittest.mock").AsyncMock()
        mock_smtp.login = pytest.importorskip("unittest.mock").AsyncMock()
        mock_smtp.quit = pytest.importorskip("unittest.mock").AsyncMock()

        await client.post(
            "/api/onboarding/step2",
            json={
                "smtp_host": "smtp.example.com",
                "smtp_port": 587,
                "smtp_user": "user@example.com",
                "smtp_password": "smtp_pass",
            },
            headers=auth_headers,
        )

    # Step 3
    with patch("dashboard.auth.settings") as mock_settings:
        mock_settings.jwt_secret_key = "test-secret-key"
        mock_settings.jwt_algorithm = "HS256"

        response = await client.post(
            "/api/onboarding/step3",
            json={
                "industry": "SaaS",
                "company_size": "50-200",
                "titles": ["VP of Sales", "Head of Growth"],
                "geo": "US",
            },
            headers=auth_headers,
        )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["next_step"] == "campaign_activated"


async def test_full_onboarding_flow(client, auth_headers):
    """Test the complete 4-step onboarding flow end-to-end."""
    with patch("dashboard.auth.settings") as mock_settings:
        mock_settings.jwt_secret_key = "test-secret-key"
        mock_settings.jwt_algorithm = "HS256"

        # Step 1
        r1 = await client.post(
            "/api/onboarding/step1",
            json={"company_name": "Full Flow Corp", "domain": "fullflow.com"},
            headers=auth_headers,
        )
        assert r1.status_code == 200

    # Step 2
    with (
        patch("dashboard.auth.settings") as mock_settings,
        patch("dashboard.routes.onboarding.aiosmtplib.SMTP") as mock_smtp_class,
    ):
        mock_settings.jwt_secret_key = "test-secret-key"
        mock_settings.jwt_algorithm = "HS256"

        mock_smtp = mock_smtp_class.return_value
        mock_smtp.connect = pytest.importorskip("unittest.mock").AsyncMock()
        mock_smtp.login = pytest.importorskip("unittest.mock").AsyncMock()
        mock_smtp.quit = pytest.importorskip("unittest.mock").AsyncMock()

        r2 = await client.post(
            "/api/onboarding/step2",
            json={
                "smtp_host": "smtp.fullflow.com",
                "smtp_port": 587,
                "smtp_user": "outbound@fullflow.com",
                "smtp_password": "secret",
            },
            headers=auth_headers,
        )
        assert r2.status_code == 200

    with patch("dashboard.auth.settings") as mock_settings:
        mock_settings.jwt_secret_key = "test-secret-key"
        mock_settings.jwt_algorithm = "HS256"

        # Step 3
        r3 = await client.post(
            "/api/onboarding/step3",
            json={
                "industry": "Fintech",
                "company_size": "200-1000",
                "titles": ["CTO", "VP Engineering"],
                "geo": "EU",
            },
            headers=auth_headers,
        )
        assert r3.status_code == 200

        # Step 4
        r4 = await client.post(
            "/api/onboarding/step4",
            json={"campaign_name": "Fintech Outreach"},
            headers=auth_headers,
        )
        assert r4.status_code == 200
        data = r4.json()
        assert data["status"] == "ok"
        assert "campaign_id" in data
        assert "Onboarding complete" in data["message"]


async def test_onboarding_step_out_of_order(client, auth_headers):
    """Test that skipping steps returns 400."""
    with patch("dashboard.auth.settings") as mock_settings:
        mock_settings.jwt_secret_key = "test-secret-key"
        mock_settings.jwt_algorithm = "HS256"

        # Try step 3 without completing steps 1 and 2
        response = await client.post(
            "/api/onboarding/step3",
            json={
                "industry": "SaaS",
                "company_size": "50-200",
                "titles": ["VP"],
                "geo": "US",
            },
            headers=auth_headers,
        )

    assert response.status_code == 400
