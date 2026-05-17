"""E2E tests for campaign CRUD operations."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest


async def test_create_campaign(client, auth_headers):
    """Test creating a new campaign."""
    with (
        patch("dashboard.auth.settings") as mock_settings,
        patch("compliance.usage_limiter.UsageLimiter") as mock_limiter_cls,
    ):
        mock_settings.jwt_secret_key = "test-secret-key"
        mock_settings.jwt_algorithm = "HS256"

        mock_limiter = AsyncMock()
        mock_limiter.get_usage = AsyncMock(return_value={
            "campaigns": {"current": 0, "limit": 10},
        })
        mock_limiter.close = AsyncMock()
        mock_limiter_cls.return_value = mock_limiter

        response = await client.post(
            "/api/campaigns/",
            json={
                "name": "Test Campaign",
                "icp_filter": {"industry": "SaaS", "company_size": "50-200"},
            },
            headers=auth_headers,
        )

    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Test Campaign"
    assert data["icp_filter"]["industry"] == "SaaS"
    assert data["status"] == "draft"
    assert "id" in data


async def test_list_campaigns(client, auth_headers):
    """Test listing campaigns returns the created campaign."""
    with (
        patch("dashboard.auth.settings") as mock_settings,
        patch("compliance.usage_limiter.UsageLimiter") as mock_limiter_cls,
    ):
        mock_settings.jwt_secret_key = "test-secret-key"
        mock_settings.jwt_algorithm = "HS256"

        mock_limiter = AsyncMock()
        mock_limiter.get_usage = AsyncMock(return_value={
            "campaigns": {"current": 0, "limit": 10},
        })
        mock_limiter.close = AsyncMock()
        mock_limiter_cls.return_value = mock_limiter

        # Create a campaign first
        create_resp = await client.post(
            "/api/campaigns/",
            json={"name": "List Test Campaign", "icp_filter": {}},
            headers=auth_headers,
        )
        assert create_resp.status_code == 201

    with patch("dashboard.auth.settings") as mock_settings:
        mock_settings.jwt_secret_key = "test-secret-key"
        mock_settings.jwt_algorithm = "HS256"

        response = await client.get("/api/campaigns/", headers=auth_headers)

    assert response.status_code == 200
    data = response.json()
    assert data["total"] >= 1
    assert len(data["items"]) >= 1
    assert any(c["name"] == "List Test Campaign" for c in data["items"])


async def test_get_campaign_by_id(client, auth_headers):
    """Test retrieving a specific campaign by ID."""
    with (
        patch("dashboard.auth.settings") as mock_settings,
        patch("compliance.usage_limiter.UsageLimiter") as mock_limiter_cls,
    ):
        mock_settings.jwt_secret_key = "test-secret-key"
        mock_settings.jwt_algorithm = "HS256"

        mock_limiter = AsyncMock()
        mock_limiter.get_usage = AsyncMock(return_value={
            "campaigns": {"current": 0, "limit": 10},
        })
        mock_limiter.close = AsyncMock()
        mock_limiter_cls.return_value = mock_limiter

        create_resp = await client.post(
            "/api/campaigns/",
            json={"name": "Detail Campaign", "icp_filter": {"geo": "US"}},
            headers=auth_headers,
        )
        assert create_resp.status_code == 201
        campaign_id = create_resp.json()["id"]

    with patch("dashboard.auth.settings") as mock_settings:
        mock_settings.jwt_secret_key = "test-secret-key"
        mock_settings.jwt_algorithm = "HS256"

        response = await client.get(
            f"/api/campaigns/{campaign_id}", headers=auth_headers
        )

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == campaign_id
    assert data["name"] == "Detail Campaign"
    assert data["icp_filter"]["geo"] == "US"


async def test_delete_campaign(client, auth_headers):
    """Test deleting a campaign returns 204 and it is gone."""
    with (
        patch("dashboard.auth.settings") as mock_settings,
        patch("compliance.usage_limiter.UsageLimiter") as mock_limiter_cls,
    ):
        mock_settings.jwt_secret_key = "test-secret-key"
        mock_settings.jwt_algorithm = "HS256"

        mock_limiter = AsyncMock()
        mock_limiter.get_usage = AsyncMock(return_value={
            "campaigns": {"current": 0, "limit": 10},
        })
        mock_limiter.close = AsyncMock()
        mock_limiter_cls.return_value = mock_limiter

        create_resp = await client.post(
            "/api/campaigns/",
            json={"name": "Delete Me Campaign", "icp_filter": {}},
            headers=auth_headers,
        )
        assert create_resp.status_code == 201
        campaign_id = create_resp.json()["id"]

    with patch("dashboard.auth.settings") as mock_settings:
        mock_settings.jwt_secret_key = "test-secret-key"
        mock_settings.jwt_algorithm = "HS256"

        # Delete
        del_resp = await client.delete(
            f"/api/campaigns/{campaign_id}", headers=auth_headers
        )
        assert del_resp.status_code == 204

        # Verify it's gone
        get_resp = await client.get(
            f"/api/campaigns/{campaign_id}", headers=auth_headers
        )
        assert get_resp.status_code == 404


async def test_get_nonexistent_campaign_returns_404(client, auth_headers):
    """Test getting a campaign that does not exist returns 404."""
    import uuid

    with patch("dashboard.auth.settings") as mock_settings:
        mock_settings.jwt_secret_key = "test-secret-key"
        mock_settings.jwt_algorithm = "HS256"

        response = await client.get(
            f"/api/campaigns/{uuid.uuid4()}", headers=auth_headers
        )

    assert response.status_code == 404
