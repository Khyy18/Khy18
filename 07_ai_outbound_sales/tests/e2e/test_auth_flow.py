"""E2E tests for the authentication flow."""
from __future__ import annotations

import uuid
from unittest.mock import patch

import pytest


async def test_register_new_user(client):
    """Test registering a new user returns 201 with user data."""
    with patch("dashboard.auth.settings") as mock_settings:
        mock_settings.jwt_secret_key = "test-secret-key"
        mock_settings.jwt_algorithm = "HS256"
        mock_settings.stripe_secret_key = ""

        response = await client.post(
            "/api/auth/register",
            json={
                "email": f"new-{uuid.uuid4().hex[:8]}@company.com",
                "password": "strong_pass_123",
                "tenant_name": "New Company",
            },
        )

    assert response.status_code == 201
    data = response.json()
    assert "id" in data
    assert "email" in data
    assert data["role"] == "admin"
    assert "tenant_id" in data


async def test_register_duplicate_email_fails(client, registered_user):
    """Test registering with an existing email returns 409."""
    with patch("dashboard.auth.settings") as mock_settings:
        mock_settings.jwt_secret_key = "test-secret-key"
        mock_settings.jwt_algorithm = "HS256"
        mock_settings.stripe_secret_key = ""

        response = await client.post(
            "/api/auth/register",
            json={
                "email": registered_user["email"],
                "password": "another_pass_123",
                "tenant_name": "Duplicate Corp",
            },
        )

    assert response.status_code == 409


async def test_login_with_valid_credentials(client, registered_user):
    """Test login with correct credentials returns a JWT token."""
    with patch("dashboard.auth.settings") as mock_settings:
        mock_settings.jwt_secret_key = "test-secret-key"
        mock_settings.jwt_algorithm = "HS256"

        response = await client.post(
            "/api/auth/login",
            json={
                "email": registered_user["email"],
                "password": "secure_pass_123",
            },
        )

    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"


async def test_login_with_wrong_password(client, registered_user):
    """Test login with wrong password returns 401."""
    with patch("dashboard.auth.settings") as mock_settings:
        mock_settings.jwt_secret_key = "test-secret-key"
        mock_settings.jwt_algorithm = "HS256"

        response = await client.post(
            "/api/auth/login",
            json={
                "email": registered_user["email"],
                "password": "wrong_password",
            },
        )

    assert response.status_code == 401


async def test_get_me_with_valid_token(client, auth_headers):
    """Test GET /api/auth/me returns current user info."""
    with patch("dashboard.auth.settings") as mock_settings:
        mock_settings.jwt_secret_key = "test-secret-key"
        mock_settings.jwt_algorithm = "HS256"

        response = await client.get("/api/auth/me", headers=auth_headers)

    assert response.status_code == 200
    data = response.json()
    assert "email" in data
    assert "id" in data
    assert data["role"] == "admin"


async def test_refresh_token(client, auth_headers):
    """Test token refresh returns a new valid token."""
    with patch("dashboard.auth.settings") as mock_settings:
        mock_settings.jwt_secret_key = "test-secret-key"
        mock_settings.jwt_algorithm = "HS256"

        response = await client.post("/api/auth/refresh", headers=auth_headers)

    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"


async def test_access_protected_endpoint_without_token(client):
    """Test accessing a protected endpoint without a token returns 401/403."""
    response = await client.get("/api/auth/me")
    assert response.status_code in (401, 403)
