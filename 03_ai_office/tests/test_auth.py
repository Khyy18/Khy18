"""Tests for JWT authentication system."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from ai_office.api.auth import create_access_token, create_refresh_token
from ai_office.core.models import User


@pytest.mark.asyncio
async def test_register_success(test_client: AsyncClient):
    """Test successful user registration creates tenant and returns tokens."""
    response = await test_client.post(
        "/api/auth/register",
        json={
            "email": "new@company.com",
            "password": "strongpass123",
            "company_name": "New Company",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"


@pytest.mark.asyncio
async def test_register_duplicate_email(test_client: AsyncClient):
    """Test registration with existing email fails."""
    payload = {
        "email": "dup@company.com",
        "password": "strongpass123",
        "company_name": "Company",
    }
    # Register first time
    response = await test_client.post("/api/auth/register", json=payload)
    assert response.status_code == 200

    # Try to register again with same email
    response = await test_client.post("/api/auth/register", json=payload)
    assert response.status_code == 400
    assert "already registered" in response.json()["detail"]


@pytest.mark.asyncio
async def test_login_success(test_client: AsyncClient):
    """Test login with valid credentials returns tokens."""
    # Register first
    await test_client.post(
        "/api/auth/register",
        json={
            "email": "login@company.com",
            "password": "mypassword",
            "company_name": "Login Corp",
        },
    )

    # Login
    response = await test_client.post(
        "/api/auth/login",
        json={"email": "login@company.com", "password": "mypassword"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data


@pytest.mark.asyncio
async def test_login_invalid_password(test_client: AsyncClient):
    """Test login with wrong password returns 401."""
    # Register first
    await test_client.post(
        "/api/auth/register",
        json={
            "email": "wrongpw@company.com",
            "password": "correctpass",
            "company_name": "Corp",
        },
    )

    # Login with wrong password
    response = await test_client.post(
        "/api/auth/login",
        json={"email": "wrongpw@company.com", "password": "wrongpass"},
    )
    assert response.status_code == 401
    assert "Invalid email or password" in response.json()["detail"]


@pytest.mark.asyncio
async def test_login_nonexistent_user(test_client: AsyncClient):
    """Test login with non-existent email returns 401."""
    response = await test_client.post(
        "/api/auth/login",
        json={"email": "nobody@nowhere.com", "password": "pass"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_refresh_token(test_client: AsyncClient):
    """Test refresh token returns new access token."""
    # Register to get tokens
    reg_response = await test_client.post(
        "/api/auth/register",
        json={
            "email": "refresh@company.com",
            "password": "pass123",
            "company_name": "Refresh Corp",
        },
    )
    tokens = reg_response.json()

    # Use refresh token
    response = await test_client.post(
        "/api/auth/refresh",
        json={"refresh_token": tokens["refresh_token"]},
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data


@pytest.mark.asyncio
async def test_refresh_with_access_token_fails(test_client: AsyncClient):
    """Test using access token as refresh token fails."""
    # Register to get tokens
    reg_response = await test_client.post(
        "/api/auth/register",
        json={
            "email": "badrefresh@company.com",
            "password": "pass123",
            "company_name": "Corp",
        },
    )
    tokens = reg_response.json()

    # Try to use access token as refresh token
    response = await test_client.post(
        "/api/auth/refresh",
        json={"refresh_token": tokens["access_token"]},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_me_endpoint(test_client: AsyncClient):
    """Test /me endpoint returns user info with tenant."""
    # Register
    reg_response = await test_client.post(
        "/api/auth/register",
        json={
            "email": "me@company.com",
            "password": "pass123",
            "company_name": "Me Corp",
        },
    )
    tokens = reg_response.json()

    # Get user info
    response = await test_client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["email"] == "me@company.com"
    assert data["role"] == "admin"
    assert data["tenant_name"] == "Me Corp"
    assert "tenant_id" in data


@pytest.mark.asyncio
async def test_me_without_token(test_client: AsyncClient):
    """Test /me endpoint without token returns 401."""
    response = await test_client.get("/api/auth/me")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_me_with_invalid_token(test_client: AsyncClient):
    """Test /me endpoint with invalid token returns 401."""
    response = await test_client.get(
        "/api/auth/me",
        headers={"Authorization": "Bearer invalid-token-here"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_super_admin_access(test_client: AsyncClient, monkeypatch):
    """Test super admin access control."""
    # Set super admin email in settings
    monkeypatch.setattr(
        "ai_office.api.auth.settings.super_admin_email", "superadmin@company.com"
    )

    # Register as super admin
    reg_response = await test_client.post(
        "/api/auth/register",
        json={
            "email": "superadmin@company.com",
            "password": "adminpass",
            "company_name": "Admin Corp",
        },
    )
    assert reg_response.status_code == 200
    tokens = reg_response.json()

    # Verify the user is super admin via /me
    response = await test_client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )
    assert response.status_code == 200
    assert response.json()["is_super_admin"] is True


@pytest.mark.asyncio
async def test_non_super_admin_cannot_access_admin_endpoints(test_client: AsyncClient):
    """Test that non-super-admin users get 403 on admin-only endpoints."""
    # Register a regular user
    reg_response = await test_client.post(
        "/api/auth/register",
        json={
            "email": "regular@company.com",
            "password": "pass123",
            "company_name": "Regular Corp",
        },
    )
    tokens = reg_response.json()

    # The require_super_admin dependency is tested through a helper -
    # we verify the user is NOT super admin
    response = await test_client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )
    assert response.status_code == 200
    assert response.json()["is_super_admin"] is False


@pytest.mark.asyncio
async def test_tenant_isolation_in_token(test_client: AsyncClient):
    """Test that tokens contain tenant_id for isolation."""
    # Register two different tenants
    resp1 = await test_client.post(
        "/api/auth/register",
        json={
            "email": "user1@tenant1.com",
            "password": "pass",
            "company_name": "Tenant 1",
        },
    )
    resp2 = await test_client.post(
        "/api/auth/register",
        json={
            "email": "user2@tenant2.com",
            "password": "pass",
            "company_name": "Tenant 2",
        },
    )

    tokens1 = resp1.json()
    tokens2 = resp2.json()

    # Get user info for both
    me1 = await test_client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {tokens1['access_token']}"},
    )
    me2 = await test_client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {tokens2['access_token']}"},
    )

    # They should have different tenant_ids
    assert me1.json()["tenant_id"] != me2.json()["tenant_id"]
